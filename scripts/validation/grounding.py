#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Grounded self-validation for the bundle: deterministic material references, cached.

For each content page it builds a compact, reproducible "material reference" (title,
headings, the external citation URLs it shares with a mat, source-file citations, prose
em-dash count) and caches it by content hash, so a re-run only touches CHANGED pages.

Grounding = a page cites an external URL that a mat (the curated reference layer) also
cites; the link graph then associates page<->mat THROUGH that shared URL. mats are never
linked as files; you cite the source they vouch for.

No LLM, no network: every signal is deterministic and reproducible. An earlier 30b
"is-this-on-topic / toney" verdict layer was removed: it needed page-type carve-outs to
manage its noise, defaulted toward pass, and added vibes rather than honest signal.

Usage:
  python3 scripts/validation/grounding.py --scope ship       # all ship-target pages
  python3 scripts/validation/grounding.py --course nemoclaw  # one course
  python3 scripts/validation/grounding.py --report PATH      # aggregate findings + mat-association JSON
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

HERE = Path(__file__).resolve()
TASK1 = find_repo_root(HERE)
SCRIPTS = TASK1 / "scripts"
add_script_paths(SCRIPTS)
import link_projection as lp  # noqa: E402

CACHE = SCRIPTS / "grounding_cache"
# bump when the reference schema/logic changes (mat-association, vendored, cites, em-dash);
# a logic change then auto-invalidates the cache instead of serving stale records.
REF_VERSION = "r4"

_TAG = re.compile(r"<[^>]+>")
_SVG = re.compile(r"<svg\b.*?</svg>", re.I | re.S)   # diagram text is not prose
_WS = re.compile(r"[ \t]*\n[ \t]*")
_EMDASH = re.compile(r"\S\s*—\s*\S")
_HEADING_MD = re.compile(r"^#{1,4}\s+(.+)$", re.M)
_HEADING_HTML = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", re.I | re.S)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>|<h1[^>]*>(.*?)</h1>", re.I | re.S)

# ── mat-grounding by SHARED EXTERNAL URL ─────────────────────────────────────
# Mats are the curated reference layer: they cite external URLs (arxiv, build.nvidia.com,
# developer.nvidia.com, ...). A page is GROUNDED when it cites a URL a mat also cites; the
# link graph then associates page<->mat through that shared URL.
_URL_RE = re.compile(r'https?://[^\s)"\'<>\]\[(]+')
# asset CDNs + infra hosts are not CITATIONS (they are <script>/<link> loads).
_NOISE_HOST = {"localhost", "127.0.0.1", "0.0.0.0", "example.com", "bring-up.sh", "skill.md",
               "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com",
               "fonts.googleapis.com", "fonts.gstatic.com"}


def _is_object_store_host(host: str) -> bool:
    suffix = ".amazonaws.com"
    if not host.endswith(suffix):
        return False
    bucket, marker, service = host[:-len(suffix)].rpartition(".s3")
    if not marker or not bucket:
        return False
    if not service:
        return True
    return (
        service[0] in ".-"
        and len(service) > 1
        and all(char.isascii() and (char.isalnum() or char in ".-") for char in service[1:])
    )


def _norm_url(u: str) -> str:
    u = u.strip().rstrip('.,;:!').split('#')[0]
    m = re.match(r'(https?://)([^/]+)(.*)', u)
    return m.group(1).lower() + m.group(2).lower() + m.group(3).rstrip('/') if m else u.lower()


def _is_citation(u: str) -> bool:
    m = re.match(r'https?://([^/:]+)', u)
    if not m:
        return False
    host = m.group(1).lower()
    if (host in _NOISE_HOST or host == "w3.org" or host.endswith(".w3.org")
            or _is_object_store_host(host)
            or re.fullmatch(r'\d+\.\d+\.\d+\.\d+', host)):
        return False
    return "." in host


_MAT_INDEX = None
_MAT_HASH = None


def mat_source_hash() -> str:
    """Fingerprint the curated material set that supplies URL associations."""
    global _MAT_HASH
    if _MAT_HASH is not None:
        return _MAT_HASH
    digest = hashlib.sha256()
    root = TASK1 / lp.MAT_REL
    if root.is_dir():
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in (".md", ".html", ".htm"):
                continue
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    _MAT_HASH = digest.hexdigest()[:16]
    return _MAT_HASH


def mat_url_index() -> dict:
    """{normalized_url: {mat_basename, ...}} built from the curated source set in
    web/nemoclaw/mats/ (the course-scoped reference layer)."""
    global _MAT_INDEX
    if _MAT_INDEX is not None:
        return _MAT_INDEX
    idx: dict[str, set] = {}
    md = TASK1 / lp.MAT_REL
    if md.is_dir():
        for f in md.rglob("*"):
            if f.suffix.lower() not in (".md", ".html", ".htm"):
                continue
            for raw in _URL_RE.findall(f.read_text(errors="ignore")):
                u = _norm_url(raw)
                if _is_citation(u):
                    idx.setdefault(u, set()).add(f.name)
    _MAT_INDEX = idx
    return idx


def _text_of(f: Path):
    """Extract (title, headings, prose) from a page for the prose signal. Pulls them apart so the
    em-dash count is measured on PROSE only: diagram text, markup, and headings are not authored
    sentences, and counting dashes in them would file false advisories that can never be cleared."""
    raw, suf = lp._read_for_links(f)
    body = lp._strip_noncontent(raw, suf)         # drop scripts/styles/frontmatter before parsing
    if suf in (".html", ".htm"):
        body = _SVG.sub(" ", body)                    # exclude diagram text from the prose signal
        heads = [re.sub(_TAG, "", h).strip() for h in _HEADING_HTML.findall(body)]
        tm = _TITLE.search(body)
        title = re.sub(_TAG, "", (tm.group(1) or tm.group(2)) if tm else "").strip()
        prose = re.sub(_TAG, " ", body)
    else:
        heads = [h.strip() for h in _HEADING_MD.findall(body)]
        title = heads[0] if heads else ""
        prose = re.sub(r"^#{1,4}\s+", "", body, flags=re.M)
    prose = re.sub(r"[ \t]{2,}", " ", _WS.sub("\n", prose)).strip()
    return title, heads, prose


_SRC_EXT = (".py", ".yaml", ".yml", ".json", ".toml", ".cfg", ".sh", ".js", ".ts",
            ".dockerfile", ".conf")


def build_reference(f: Path, rel: str) -> dict:
    """The compact, reproducible grounding fingerprint of one page, cached by content hash. It is
    what lets the gate answer 'is this page grounded, and does its prose carry em-dashes' without an
    LLM or the network: every field here is deterministic, so the same page always yields the same
    record and a re-run only recomputes pages whose bytes changed."""
    title, heads, prose = _text_of(f)
    course = lp.course_of(rel)
    raw, suf = lp._read_for_links(f)
    txt = lp._strip_noncontent(raw, suf)
    base_dir = "/".join(rel.split("/")[:-1])           # the page's own directory, for relative links
    cites = 0                                          # resolvable source-file citations
    for m in set(lp._HREF.findall(txt)) | set(lp._MDL.findall(txt)):
        if lp._is_template_link(m) or m.startswith(("http", "//", "#", "mailto:", "data:", "tel:")):
            continue                                   # external / templated / anchor links are not source-file cites
        clean = m.split("#")[0].split("?")[0]
        resolved = clean[len("/lab/static/"):] if clean.startswith("/lab/static/") else lp._clamp(base_dir, clean)
        if resolved.lower().endswith(_SRC_EXT) and (TASK1 / resolved).is_file():
            cites += 1                                 # links to a real code/config file in the tree
    page_urls = {u for u in (_norm_url(x) for x in _URL_RE.findall(txt)) if _is_citation(u)}  # external citation URLs
    midx = mat_url_index()                             # {url: {mats that also cite it}}
    mat_assoc: dict[str, list] = {}
    for u in page_urls:                                # associate page->mat through each shared URL
        for mat in midx.get(u, ()):
            mat_assoc.setdefault(mat, []).append(u)
    uncovered = sorted(u for u in page_urls if u not in midx)  # cited URLs no mat vouches for
    # vendored = an external snapshot under the course mats/ (web/nemoclaw/mats/: scraped
    # build.nvidia.com / blog / brev / the developer-site learning path, a vendored NVIDIA
    # glossary page under glossary_raw/, or an arxiv- abstract pulled by pull_materials.py).
    # We cite these but do not rewrite their prose, so any em-dashes in them belong to the
    # original author. The sweep still surfaces and labels them so they are visible in the report.
    vendored = rel.startswith(lp.MAT_REL + "/") and (
        rel.startswith(lp.MAT_REL + "/glossary_raw/") or
        bool(re.search(r'(-(com|org|io)-|learning_path|^(build|developer|brev|module|nemoclaw|arxiv)-)',
                       rel.rsplit("/", 1)[-1])))
    return {"title": title, "course": course, "vendored": vendored, "headings": heads[:24],
            "em_dash_in_prose": len(_EMDASH.findall(prose)), "prose_chars": len(prose),
            "cites": cites, "ext_urls": len(page_urls), "mat_grounded": bool(mat_assoc),
            "mat_assoc": {m: sorted(us) for m, us in mat_assoc.items()},
            "uncovered_urls": uncovered[:20]}


def _hash(f: Path) -> str:
    return hashlib.sha256(f.read_bytes()).hexdigest()[:16]


def _cache_file(course: str, rel: str) -> Path:
    return CACHE / course / (rel.replace("/", "__") + ".json")


def ground_page(rel: str, force: bool = False) -> dict:
    f = TASK1 / rel
    course = lp.course_of(rel)
    h = _hash(f)
    material_hash = mat_source_hash()
    cf = _cache_file(course, rel)
    if cf.exists() and not force:
        try:
            old = json.loads(cf.read_text())
            if (old.get("hash") == h and old.get("mat_hash") == material_hash
                    and old.get("ref_version") == REF_VERSION):
                old["cached"] = True
                return old
        except Exception:
            pass
    rec = {"path": rel, "course": course, "hash": h, "mat_hash": material_hash,
           "ref_version": REF_VERSION,
           "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "reference": build_reference(f, rel), "cached": False}
    # The cache is an optimization, never a dependency: if the entry cannot be written (a stale
    # file left root-owned by an earlier in-container run, a read-only mount), use the record we
    # just computed in memory and move on. A cache glitch must never turn the whole check into a
    # crash that reads as "did not run"; the data is correct either way, only the speedup is lost.
    try:
        cf.parent.mkdir(parents=True, exist_ok=True)
        cf.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    except OSError:
        pass
    return rec


def _ship_pages():
    proj = lp.Projection(TASK1)
    for f in lp._iter_pages(TASK1):
        try:
            yield str(f.relative_to(proj.host_root))
        except ValueError:
            yield str(f.relative_to(TASK1))


def sweep(course, scope, limit=None, force=False):
    """Build one reference record per content page so a re-run only re-hashes CHANGED pages.
    Without this cache-backed pass, every gate run would re-parse every page from scratch and
    the report could not say which pages are ungrounded or carry authored em-dashes. The records
    it returns feed _findings (the advisories) and the mat-association JSON in the report."""
    recs = []
    for rel in _ship_pages():
        c = lp.course_of(rel)
        if course and c != course:                # --course filter: only that one course
            continue
        if not course and scope == "ship" and not lp.ship_relevant(rel):
            continue                              # scope=ship drops pages the bundle never ships
        if not rel.lower().endswith((".html", ".htm", ".md", ".ipynb")):
            continue                              # only content surfaces carry groundable prose
        recs.append(ground_page(rel, force=force))  # cache hit unless content hash / ref schema changed
        if limit and len(recs) >= limit:
            break
    return recs


def _groundable(rel: str) -> bool:
    """Should this page TRACE to a mat via a shared citation URL? Only the claim-bearing
    teaching explainers: the numbered nemoclaw web-course pages. Everything else is correctly
    ungrounded by TYPE (corpus data, skill configs, agent docs, persona, hubs, scripts, demo
    notes). Classifying makes 'ungrounded' a meaningful metric instead of a flood of
    non-explainer pages."""
    if "/data/" in rel:
        return False
    return bool(re.match(r'web/nemoclaw/\d', rel))


def _findings(recs):
    """Turn the reference records into the advisory list the gate reports. This is the check that
    catches a teaching page making claims with NO traceable source (a student cannot verify it) and
    authored em-dashes (the AI-cadence structure smell). Only claim-bearing explainers are held to
    the grounding bar; everything else is correctly ungrounded by type, so it never files an issue."""
    out = []
    for r in recs:
        ref = r.get("reference", {})
        issues = []
        # A substantial explainer that cites no source file AND shares no citation URL with a mat
        # is grounded in nothing, so a reader cannot trace its claims.
        if _groundable(r["path"]) and ref.get("prose_chars", 0) > 800 and not ref.get("cites") and not ref.get("mat_grounded"):
            issues.append("ungrounded (no source citation and no mat URL-association)")
        # Cites external URLs, but no mat vouches for any of them: the sources are unvetted.
        elif _groundable(r["path"]) and ref.get("uncovered_urls") and not ref.get("mat_grounded"):
            issues.append(f"unvetted sources: cites {len(ref['uncovered_urls'])} external URL(s) no mat covers")
        # An authored em-dash is a STRUCTURE smell: each one marks an AI-cadenced sentence. Swapping
        # the dash for ./;/() games the metric and reads worse, so rewrite the sentence. Vendored mats
        # are external snapshots whose punctuation is the original author's; we cite them and never
        # rewrite them, so their em-dashes are surfaced via vendored_em_dash(), not filed as an
        # advisory we could never honestly clear.
        if ref.get("em_dash_in_prose") and not ref.get("vendored"):
            issues.append(f"em-dash x{ref['em_dash_in_prose']} "
                          f"(STRUCTURE smell: rewrite each sentence, never substitute punctuation)")
        if issues:
            out.append({"path": r["path"], "course": r["course"], "issues": issues})
    return out


def vendored_em_dash(recs):
    """Vendored mats carrying the original author's em-dashes. Surfaced for visibility, never an
    advisory: we cite these external snapshots, we do not rewrite their prose."""
    return [(r["path"], r["reference"]["em_dash_in_prose"]) for r in recs
            if r.get("reference", {}).get("vendored") and r["reference"].get("em_dash_in_prose")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course", help="ground a single course (nemoclaw)")
    ap.add_argument("--scope", choices=["ship", "all"], default="ship")
    ap.add_argument("--force", action="store_true", help="ignore cache, re-ground every page")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--report", help="write an aggregate findings + mat-association JSON to PATH")
    a = ap.parse_args()

    recs = sweep(a.course, a.scope, limit=a.limit, force=a.force)
    findings = _findings(recs)
    cached = sum(1 for r in recs if r.get("cached"))
    grounded = sum(1 for r in recs if r.get("reference", {}).get("mat_grounded"))
    ungrounded = sum(1 for fo in findings if any("ungrounded" in i for i in fo["issues"]))

    print(f"grounding: {len(recs)} pages  (cached {cached})")
    print(f"  mat-associated: {grounded}/{len(recs)} pages share an external citation URL with a mat")
    print(f"  ungrounded: {ungrounded} content page(s) grounded in nothing")
    ved = vendored_em_dash(recs)
    if ved:
        print(f"  vendored em-dash: {len(ved)} external snapshot(s) carry the source's em-dashes "
              f"(surfaced, not advisories)")
    print(f"  findings: {len(findings)} page(s) with issues")
    for fo in findings[:40]:
        print(f"  {fo['path']}")
        for iss in fo["issues"]:
            print(f"      - {iss}")
    if a.report:
        assoc = {r["path"]: r["reference"]["mat_assoc"] for r in recs if r["reference"].get("mat_assoc")}
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(json.dumps(
            {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "pages": len(recs), "mat_associated": len(assoc),
             "findings": findings, "mat_association": assoc}, indent=2, ensure_ascii=False))
        print(f"  report -> {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
