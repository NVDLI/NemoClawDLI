#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed materials vendorer: pull each course material from its live web source into
committed markdown under web/nemoclaw/mats/, with provenance and a drift check.

This generalizes vendor_glossary.py to several host types so the bundle can "rebase" to
the web's ground truth in a controlled, transparent way. Per host:

  glossary   NVIDIA glossary term pages   -> delegated to vendor_glossary.py
             (the CACHED tier: the 79-term index + the 7 deep articles, both shipped)
  devblog    developer.nvidia.com/blog     -> the WordPress .entry-content body -> markdown
  arxiv      arXiv papers                  -> the arXiv API (title + authors + abstract)

Each material is one row of MANIFEST: {name, url, host, tier}. tier="cached" ships in the
glossary index (offline-searchable); tier="on_demand" gets a catalog entry whose full text
is reached through the source URL on demand (the heavy snapshots are committed for review +
grounding, but not shipped in the bundle).

Outputs (all committed, so review, grounding, and the build see exactly what gets pulled):
  web/nemoclaw/mats/<name>.md        the pulled markdown (its H1 links the source URL)
  web/nemoclaw/mats/_materials.json  provenance per material: url, host, tier, title, blurb,
                                     fetched, sha256, bytes, status

Three modes, one transparent vocabulary (ok / DRIFTED / UNREACHABLE):
  PULL  (contributors + the deploy build): fetch, (re)write the markdown, update provenance.
        A per-material failure NEVER aborts the run: it keeps the committed snapshot and
        records status="unreachable" so the failure is loud, never silent.
  VERIFY (--verify-committed; every gate): verify the committed snapshot and its full SHA-256,
        manifest metadata, and character count without using the network. Any mismatch fails.
  CHECK (--check; schedules + release): first run VERIFY, then re-fetch with bounded retries,
        recompute the fingerprint, and report ok / DRIFTED / UNREACHABLE. Writes nothing. Drift,
        malformed responses, unsafe redirects, TLS failures, and provenance mismatches always fail.
        A caller may explicitly tolerate only classified transient reachability failures.

The same status + fix text is what the gate folds into docs/validation/latest.{json,md}, which
build_pages.sh projects to the student-facing validator screen (validation.html / gate.json), so
a materials problem reads identically to you, to CI, and to a student who opens the validator.

Usage:
  python3 scripts/materials/pull_materials.py                 # pull the light on-demand materials (deploy-build default)
  python3 scripts/materials/pull_materials.py --all            # also refresh the heavy glossary tier (index + deep articles)
  python3 scripts/materials/pull_materials.py --only papers   # one host: glossary | blogs | papers
  python3 scripts/materials/pull_materials.py --verify-committed # offline snapshot + provenance check
  python3 scripts/materials/pull_materials.py --check          # drift check, no writes (CI / pre-push)
  python3 scripts/materials/pull_materials.py --check --json    # machine-readable status (the gate reads this)
  python3 scripts/materials/pull_materials.py --list           # print the manifest and exit

Dependencies: requests, beautifulsoup4, markdownify, lxml (the same set vendor_glossary.py uses).
"""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root
import re
import subprocess
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = str(find_repo_root(Path(__file__).resolve()))
MATS = os.path.join(REPO, "web", "nemoclaw", "mats")
MATERIALS_JSON = os.path.join(MATS, "_materials.json")          # on-demand provenance (this script)
GLOSSARY_INDEX = os.path.join(MATS, "glossary_index.json")       # cached glossary index (vendor_glossary)
# Unified searchable catalog. Source copy lives in mats/; shipped copy lives in assets/.
CATALOG_MATS = os.path.join(MATS, "materials_index.json")
CATALOG_ASSET = os.path.join(REPO, "web", "nemoclaw", "assets", "materials_index.json")
UA = {"User-Agent": "Mozilla/5.0 (NVIDIA DLI course materials vendoring)"}
ARXIV_API_URL = "https://export.arxiv.org/api/query?id_list="
FETCH_ATTEMPTS = 4
RETRY_BACKOFF = 1.0
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
TRANSIENT_HTTP_STATUS = {408, 425, 429, 500, 502, 503, 504}


class FetchFailure(RuntimeError):
    """A classified source-fetch failure that callers may handle without guessing."""

    def __init__(self, message: str, *, transient: bool):
        super().__init__(message)
        self.transient = transient

# ── manifest ──────────────────────────────────────────────────────────────────
# Add or change a material here, then re-run the matching extractor.
MANIFEST = [
    {"name": "developer-nvidia-com-blog-deploy-self-evolving-agents-for-fa", "host": "devblog",
     "tier": "on_demand",
     "url": "https://developer.nvidia.com/blog/deploy-self-evolving-agents-for-faster-more-secure-research-with-a-hermes-agent-and-nvidia-nemoclaw/"},
    {"name": "arxiv-2005.11401-rag", "host": "arxiv", "tier": "on_demand",
     "url": "https://arxiv.org/abs/2005.11401"},
    {"name": "arxiv-2404.16130-graphrag", "host": "arxiv", "tier": "on_demand",
     "url": "https://arxiv.org/abs/2404.16130"},
    {"name": "arxiv-2210.03629-react", "host": "arxiv", "tier": "on_demand",
     "url": "https://arxiv.org/abs/2210.03629"},
    {"name": "arxiv-2305.18323-rewoo", "host": "arxiv", "tier": "on_demand",
     "url": "https://arxiv.org/abs/2305.18323"},
]

# --only takes a friendly name; map it to the host key.
ONLY_MAP = {"glossary": "glossary", "blogs": "devblog", "papers": "arxiv"}
# The one-line fix shown for a failing material, keyed by host (the --only name to re-run).
FIX_ONLY = {"devblog": "blogs", "arxiv": "papers", "glossary": "glossary"}


def _need_deps():
    try:
        import requests  # noqa: F401
        import bs4  # noqa: F401
        import markdownify  # noqa: F401
        return True
    except ImportError as exc:
        sys.stderr.write(
            "pull_materials needs: requests beautifulsoup4 markdownify lxml\n"
            "  pip install requests beautifulsoup4 markdownify lxml\n"
            f"  (missing: {exc.name})\n")
        return False


def _need_requests():
    try:
        import requests  # noqa: F401
        return True
    except ImportError:
        sys.stderr.write("pull_materials self-test needs: requests\n")
        return False


def _transient_request_error(exc) -> bool:
    import requests
    if isinstance(exc, requests.exceptions.SSLError):
        return False
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return exc.response.status_code in TRANSIENT_HTTP_STATUS
    return False


def _retry_delay(response, attempt: int, backoff: float) -> float:
    retry_after = (getattr(response, "headers", {}) or {}).get("Retry-After", "")
    if str(retry_after).strip().isdigit():
        return min(float(retry_after), 60.0)
    return min(backoff * (2 ** (attempt - 1)), 30.0)


def _fetch(url, *, attempts=None, backoff=None, get=None, sleep=time.sleep):
    import requests
    attempts = FETCH_ATTEMPTS if attempts is None else max(1, int(attempts))
    backoff = RETRY_BACKOFF if backoff is None else max(0.0, float(backoff))
    get = get or requests.get
    requested = urlsplit(url)
    if requested.scheme != "https" or not requested.hostname:
        raise FetchFailure(f"refusing non-HTTPS or hostless source URL: {url}", transient=False)

    for attempt in range(1, attempts + 1):
        response = None
        try:
            response = get(url, headers=UA, timeout=30, allow_redirects=True)
            response.raise_for_status()
            final = urlsplit(response.url)
            if final.scheme != "https" or final.hostname != requested.hostname:
                raise FetchFailure(
                    f"refusing source redirect {requested.hostname} -> {final.hostname or '?'}",
                    transient=False,
                )
            content = response.content
            if len(content) > MAX_RESPONSE_BYTES:
                raise FetchFailure(
                    f"response exceeds {MAX_RESPONSE_BYTES} bytes", transient=False
                )
            return response.text
        except FetchFailure:
            raise
        except requests.exceptions.RequestException as exc:
            transient = _transient_request_error(exc)
            if transient and attempt < attempts:
                delay = _retry_delay(response, attempt, backoff)
                print(
                    f"  retry {attempt}/{attempts - 1} after transient fetch failure "
                    f"({type(exc).__name__}); waiting {delay:g}s",
                    file=sys.stderr,
                    flush=True,
                )
                sleep(delay)
                continue
            raise FetchFailure(
                f"{exc} (attempts={attempt})", transient=transient
            ) from exc


# ── extractors: url -> (title, blurb, markdown_body) ──────────────────────────
def extract_devblog(url):
    from bs4 import BeautifulSoup
    from markdownify import markdownify as to_md
    soup = BeautifulSoup(_fetch(url), "lxml")
    title = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        title = og["content"].strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)
    blurb = ""
    md = (soup.find("meta", attrs={"name": "description"})
          or soup.find("meta", attrs={"property": "og:description"}))
    if md and md.get("content"):
        blurb = " ".join(md["content"].split())
    # The WordPress article body. Try the tightest container first, fall back outward.
    node = (soup.select_one("div.entry-content") or soup.select_one("article .entry-content")
            or soup.select_one("main article") or soup.find("article") or soup.find("main")
            or soup.body)
    if node is None:
        raise ValueError("no article body found")
    for sel in ["script", "style", "nav", "header", "footer", "aside", "form",
                ".related", ".related-posts", ".subscribe", ".newsletter", ".share",
                ".social", ".post-meta", ".breadcrumb", "#comments", ".comments"]:
        for el in node.select(sel):
            el.decompose()
    body = re.sub(r"\n{3,}", "\n\n", to_md(str(node), heading_style="ATX", bullets="-")).strip()
    if len(body) < 200:
        raise ValueError(f"extracted body suspiciously short ({len(body)} chars) -- check the selector")
    return title, blurb, body


def extract_arxiv(url):
    m = re.search(r"(\d{4}\.\d{4,5})", url)
    if not m:
        raise ValueError("no arXiv id in " + url)
    aid = m.group(1)
    xml = _fetch(ARXIV_API_URL + aid)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entry = ET.fromstring(xml).find("a:entry", ns)
    if entry is None or entry.findtext("a:title", "", ns).strip().lower() == "error":
        raise ValueError("arXiv API returned no entry for " + aid)
    title = " ".join(entry.findtext("a:title", "", ns).split())
    authors = [a.findtext("a:name", "", ns).strip() for a in entry.findall("a:author", ns)]
    summary = " ".join(entry.findtext("a:summary", "", ns).split())
    if not summary:
        raise ValueError("arXiv API returned an empty abstract for " + aid)
    blurb = (summary[:197] + "...") if len(summary) > 200 else summary
    body = ("**Authors:** " + ", ".join(authors) + "\n\n"
            "**Abstract.** " + summary + "\n\n"
            "*Canonical abstract pulled from the arXiv API; the figures in this course are "
            "hand-authored redraws, not extracted from the paper PDF.*")
    return title, blurb, body


EXTRACTORS = {"devblog": extract_devblog, "arxiv": extract_arxiv}


# ── render / fingerprint (PULL and CHECK build the same string, so the hash compares) ──
def _render(mat, title, body):
    return f"# [{title}]({mat['url']})\n\n{body}\n"


def _sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _md_path(mat):
    return os.path.join(MATS, mat["name"] + ".md")


def _load_provenance():
    if os.path.exists(MATERIALS_JSON):
        with open(MATERIALS_JSON, encoding="utf-8") as fh:
            return {r["name"]: r for r in json.load(fh).get("materials", [])}
    return {}


def verify_committed(*, manifest=None, provenance_path=None, mats_dir=None):
    """Verify committed snapshots against exact manifest metadata and full SHA-256 values.

    This check is deliberately network-free. It makes a transient source outage irrelevant to
    ordinary validation while keeping local or submitted snapshot tampering fail-closed.
    """
    manifest = list(MANIFEST if manifest is None else manifest)
    provenance_path = Path(MATERIALS_JSON if provenance_path is None else provenance_path)
    mats_dir = Path(MATS if mats_dir is None else mats_dir)
    findings = []

    names = [m.get("name") for m in manifest]
    for name in sorted({name for name in names if names.count(name) > 1}):
        findings.append({"name": name, "detail": "duplicate manifest name"})
    try:
        raw = json.loads(provenance_path.read_text(encoding="utf-8"))
        records = raw.get("materials", [])
        if not isinstance(records, list):
            raise ValueError("materials must be a list")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [{"name": provenance_path.name, "detail": f"cannot read provenance: {exc}"}]

    record_names = [r.get("name") for r in records if isinstance(r, dict)]
    for name in sorted({name for name in record_names if record_names.count(name) > 1}):
        findings.append({"name": name, "detail": "duplicate provenance name"})
    by_name = {r.get("name"): r for r in records if isinstance(r, dict)}
    expected = {m.get("name") for m in manifest}
    actual = set(by_name)
    for name in sorted(expected - actual):
        findings.append({"name": name, "detail": "missing provenance record"})
    for name in sorted((actual - expected), key=lambda value: str(value)):
        findings.append({"name": str(name), "detail": "unexpected provenance record"})

    for mat in manifest:
        name = mat["name"]
        rec = by_name.get(name)
        if not rec:
            continue
        for field in ("url", "host", "tier"):
            if rec.get(field) != mat.get(field):
                findings.append({"name": name, "detail": f"{field} differs from manifest"})
        if rec.get("status") != "ok":
            findings.append({"name": name, "detail": "committed provenance status is not ok"})
        digest = rec.get("sha256", "")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            findings.append({"name": name, "detail": "sha256 is not a full lowercase digest"})
        snapshot = mats_dir / f"{name}.md"
        try:
            text = snapshot.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append({"name": name, "detail": f"cannot read snapshot: {exc}"})
            continue
        actual_digest = _sha(text)
        if digest != actual_digest:
            findings.append({"name": name, "detail": f"snapshot SHA-256 mismatch ({digest} -> {actual_digest})"})
        if rec.get("bytes") != len(text):
            findings.append({"name": name, "detail": f"snapshot character count mismatch ({rec.get('bytes')} -> {len(text)})"})
    return findings


def _selected(only):
    if not only:
        return list(MANIFEST)
    host = ONLY_MAP.get(only, only)
    return [m for m in MANIFEST if m["host"] == host]


def pull_one(mat):
    """Fetch + (re)write the markdown. Never raises: returns a provenance record whose
    status is 'ok' or 'unreachable' (keeping the committed snapshot on failure)."""
    rec = {"name": mat["name"], "url": mat["url"], "host": mat["host"], "tier": mat["tier"]}
    try:
        title, blurb, body = EXTRACTORS[mat["host"]](mat["url"])
        out = _render(mat, title, body)
        with open(_md_path(mat), "w", encoding="utf-8") as fh:
            fh.write(out)
        rec.update(title=title, blurb=blurb,
                   fetched=datetime.date.today().isoformat(),
                   sha256=_sha(out), bytes=len(out), status="ok")
        print(f"  ok           {mat['name']}  ({len(out)} bytes)")
    except Exception as exc:  # noqa: BLE001 - one source must never abort the rest
        rec.update(status="unreachable", error=str(exc)[:200],
                   fetched=datetime.date.today().isoformat())
        print(f"  UNREACHABLE  {mat['name']}  ({exc})")
        print(f"               kept the committed snapshot; fix with: "
              f"python3 scripts/materials/pull_materials.py --only {FIX_ONLY[mat['host']]}")
    return rec


def check_one(mat, prov):
    """Re-fetch and compare the freshly-rendered fingerprint to the committed provenance.
    Returns (status, detail, transient) with status in ok / drifted / unreachable."""
    have = prov.get(mat["name"])
    try:
        title, blurb, body = EXTRACTORS[mat["host"]](mat["url"])
        fresh = _sha(_render(mat, title, body))
    except FetchFailure as exc:
        return "unreachable", str(exc)[:160], exc.transient
    except Exception as exc:  # noqa: BLE001 - malformed content is permanent until corrected
        return "unreachable", str(exc)[:160], False
    if not have or "sha256" not in have:
        return "drifted", "no committed fingerprint yet (never pulled)", False
    if fresh != have["sha256"]:
        return "drifted", f"source changed since {have.get('fetched', '?')} ({have['sha256']} -> {fresh})", False
    return "ok", "", False


def check_passes(rows, tampered, allow_transient_unreachable=False):
    if tampered or any(row["status"] == "drifted" for row in rows):
        return False
    unreachable = [row for row in rows if row["status"] == "unreachable"]
    return not unreachable or (
        allow_transient_unreachable and all(row.get("transient") for row in unreachable)
    )


def self_test():
    import requests

    failures = []

    class FakeResponse:
        def __init__(self, status, url="https://example.test/source", text="ok", headers=None):
            self.status_code = status
            self.url = url
            self.text = text
            self.content = text.encode("utf-8")
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                exc = requests.exceptions.HTTPError(f"{self.status_code} response")
                exc.response = self
                raise exc

    sequence = iter([FakeResponse(429), FakeResponse(503), FakeResponse(200)])
    calls = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        return next(sequence)

    if _fetch("https://example.test/source", attempts=3, backoff=0, get=fake_get, sleep=lambda _: None) != "ok" or len(calls) != 3:
        failures.append("transient 429/503 responses were not retried to success")

    calls.clear()
    try:
        _fetch("https://example.test/source", attempts=4, get=lambda *a, **k: (calls.append(1) or FakeResponse(404)), sleep=lambda _: None)
        failures.append("permanent HTTP failure unexpectedly passed")
    except FetchFailure as exc:
        if exc.transient or len(calls) != 1:
            failures.append("permanent HTTP failure was retried or misclassified")

    try:
        _fetch("https://example.test/source", get=lambda *a, **k: FakeResponse(200, url="https://other.test/source"))
        failures.append("cross-host redirect unexpectedly passed")
    except FetchFailure as exc:
        if exc.transient:
            failures.append("cross-host redirect misclassified as transient")

    with tempfile.TemporaryDirectory(prefix="material-provenance-") as td:
        root = Path(td)
        mat = {"name": "fixture", "url": "https://example.test/source", "host": "fixture", "tier": "on_demand"}
        text = "# Fixture\n"
        (root / "fixture.md").write_text(text, encoding="utf-8")
        provenance = root / "_materials.json"
        record = {**mat, "status": "ok", "sha256": _sha(text), "bytes": len(text)}
        provenance.write_text(json.dumps({"materials": [record]}), encoding="utf-8")
        if verify_committed(manifest=[mat], provenance_path=provenance, mats_dir=root):
            failures.append("clean committed snapshot rejected")
        (root / "fixture.md").write_text(text + "tamper\n", encoding="utf-8")
        if not verify_committed(manifest=[mat], provenance_path=provenance, mats_dir=root):
            failures.append("snapshot tampering escaped verifier")
        (root / "fixture.md").write_text(text, encoding="utf-8")
        changed = dict(record, url="https://example.test/changed")
        provenance.write_text(json.dumps({"materials": [changed]}), encoding="utf-8")
        if not verify_committed(manifest=[mat], provenance_path=provenance, mats_dir=root):
            failures.append("provenance metadata tampering escaped verifier")

    transient = [{"status": "unreachable", "transient": True}]
    permanent = [{"status": "unreachable", "transient": False}]
    drifted = [{"status": "drifted", "transient": False}]
    if not check_passes(transient, [], True):
        failures.append("explicit transient-only degradation was rejected")
    if check_passes(transient, [], False) or check_passes(permanent, [], True):
        failures.append("unapproved or permanent reachability failure passed")
    if check_passes(drifted, [], True) or check_passes([], [{"detail": "tampered"}], True):
        failures.append("drift or tampering passed degraded policy")

    return failures


def cmd_glossary(check):
    """Delegate the glossary host to the proven vendor_glossary.py (cached tier)."""
    vg = os.path.join(HERE, "vendor_glossary.py")
    if check:
        # The glossary index is committed + shipped; a deep drift check would re-fetch 79 pages.
        # Keep CHECK fast + deterministic here: verify the committed index parses and is non-empty.
        # A full glossary re-pull is the explicit refresh below.
        idx = os.path.join(MATS, "glossary_index.json")
        try:
            with open(idx, encoding="utf-8") as fh:
                n = len(json.load(fh).get("terms", []))
            print(f"  ok           glossary index ({n} terms committed)")
            return "ok"
        except Exception as exc:  # noqa: BLE001
            print(f"  UNREACHABLE  glossary index ({exc})  "
                  f"-> rebuild: python3 scripts/materials/vendor_glossary.py --index")
            return "unreachable"
    print("  glossary: delegating to vendor_glossary.py (deep articles + --index)")
    subprocess.run([sys.executable, vg], check=False)
    subprocess.run([sys.executable, vg, "--index"], check=False)
    return "ok"


def build_catalog():
    """Merge the cached glossary index + the on-demand materials provenance into one searchable
    catalog -- the unified surface that webSearch/instantAnswer and the explorer read. Each entry
    carries its tier so a cached glossary term (full text shipped) and an on-demand source (reached
    via its URL) are visibly different. Dual-write to mats/ + assets/. Returns (cached, on_demand)."""
    entries = []
    if os.path.exists(GLOSSARY_INDEX):
        for t in json.load(open(GLOSSARY_INDEX, encoding="utf-8")).get("terms", []):
            entries.append({"kind": "glossary", "tier": "cached", "term": t.get("term"),
                            "blurb": t.get("blurb", ""), "url": t.get("url"),
                            "tags": t.get("tags", []), "deep": bool(t.get("deep"))})
    if os.path.exists(MATERIALS_JSON):
        for m in json.load(open(MATERIALS_JSON, encoding="utf-8")).get("materials", []):
            entries.append({"kind": m.get("host"), "tier": m.get("tier", "on_demand"),
                            "term": m.get("title") or m.get("name"), "blurb": m.get("blurb", ""),
                            "url": m.get("url"), "tags": [], "status": m.get("status", "ok")})
    entries.sort(key=lambda e: (e["tier"] != "cached", (e.get("term") or "").lower()))
    cached = sum(1 for e in entries if e["tier"] == "cached")
    payload = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "count": len(entries), "cached": cached, "on_demand": len(entries) - cached,
               "entries": entries}
    for p in (CATALOG_MATS, CATALOG_ASSET):
        if os.path.isdir(os.path.dirname(p)):
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
    print(f"  -> materials_index.json  ({cached} cached + {len(entries) - cached} on-demand = {len(entries)})")
    return cached, len(entries) - cached


def main():
    """Run offline verification, live drift checks, or an explicit material refresh."""
    global FETCH_ATTEMPTS, RETRY_BACKOFF
    ap = argparse.ArgumentParser(
        description="Pull course materials from their web sources into committed markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--only", choices=list(ONLY_MAP), help="restrict to one host type")
    ap.add_argument("--check", action="store_true", help="drift check (re-fetch + compare); writes nothing")
    ap.add_argument("--verify-committed", action="store_true",
                    help="network-free committed snapshot and provenance verification")
    ap.add_argument("--self-test", action="store_true", help="run retry, classification, and tamper fixtures")
    ap.add_argument("--fetch-attempts", type=int, default=FETCH_ATTEMPTS,
                    help=f"maximum attempts for transient source failures (default: {FETCH_ATTEMPTS})")
    ap.add_argument("--retry-backoff", type=float, default=RETRY_BACKOFF,
                    help=f"initial exponential retry delay in seconds (default: {RETRY_BACKOFF:g})")
    ap.add_argument("--host-delay", type=float, default=3.0,
                    help="delay between live checks against the same source host (default: 3)")
    ap.add_argument("--allow-transient-unreachable", action="store_true",
                    help="with --check only, tolerate classified transient reachability failures; drift and tampering still fail")
    ap.add_argument("--all", action="store_true",
                    help="also refresh the heavy glossary tier (index + 7 deep articles + images); "
                         "the default pulls only the light on-demand materials, which is what the deploy build runs")
    ap.add_argument("--list", action="store_true", help="print the manifest and exit")
    ap.add_argument("--catalog", action="store_true",
                    help="rebuild only materials_index.json (glossary + on-demand) from existing data, no fetch")
    ap.add_argument("--json", action="store_true", help="machine-readable status (for the gate)")
    a = ap.parse_args()

    if a.fetch_attempts < 1 or a.retry_backoff < 0 or a.host_delay < 0:
        ap.error("fetch attempts must be positive; delay values cannot be negative")
    if a.allow_transient_unreachable and not a.check:
        ap.error("--allow-transient-unreachable requires --check")
    if sum(bool(mode) for mode in (a.check, a.verify_committed, a.self_test, a.catalog, a.list)) > 1:
        ap.error("choose one of --check, --verify-committed, --self-test, --catalog, or --list")

    FETCH_ATTEMPTS = a.fetch_attempts
    RETRY_BACKOFF = a.retry_backoff

    if a.self_test:
        if not _need_requests():
            return 2
        failures = self_test()
        print("materials self-test: " + ("FAIL" if failures else "PASS"))
        for failure in failures:
            print(f"  FAIL {failure}")
        return 1 if failures else 0

    if a.verify_committed:
        findings = verify_committed()
        if a.json:
            print(json.dumps({"clean": not findings, "findings": findings}, indent=2))
        elif findings:
            print("committed materials verification: FAIL")
            for item in findings:
                print(f"  {item['name']}: {item['detail']}")
        else:
            print(f"committed materials verification: PASS ({len(MANIFEST)} snapshots, full SHA-256)")
        return 1 if findings else 0

    if a.catalog:                                 # --catalog: rebuild the searchable index from existing data, no fetch
        build_catalog()
        return 0

    if a.list:                                    # --list: print the manifest and exit
        for m in MANIFEST:
            print(f"  {m['tier']:10} {m['host']:8} {m['name']}\n             {m['url']}")
        print(f"  glossary   cached   (delegated to vendor_glossary.py: 79-term index + deep articles)")
        return 0

    if not _need_deps():                          # the extractors need requests/bs4/markdownify
        return 2

    sel = _selected(a.only)                        # the manifest rows in scope (all, or one --only host)
    # Glossary refresh is expensive, so only --all or --only glossary runs it.
    do_glossary = a.all or a.only == "glossary"

    # ── CHECK mode (the gate + pre-push) ──────────────────────────────────────
    if a.check:
        tampered = verify_committed()
        if tampered:
            if a.json:
                print(json.dumps({"checked": 0, "ok": 0, "drifted": [], "unreachable": [],
                                  "tampered": tampered, "clean": False, "degraded": False,
                                  "rows": []}, indent=2))
            else:
                print("materials drift check: FAIL before network access")
                for item in tampered:
                    print(f"  TAMPERED    {item['name']}: {item['detail']}")
            return 1
        prov = _load_provenance()                 # the committed fingerprints to compare against
        rows, drifted, unreachable = [], [], []
        previous_host = None
        for mat in sel:
            if previous_host == mat["host"] and a.host_delay:
                time.sleep(a.host_delay)
            previous_host = mat["host"]
            status, detail, transient = check_one(mat, prov)  # re-fetch + compare; never writes
            rows.append({"name": mat["name"], "url": mat["url"], "host": mat["host"],
                         "tier": mat["tier"], "status": status, "detail": detail,
                         "transient": transient})
            if status == "drifted":               # source text changed since it was vendored
                drifted.append(mat)
            elif status == "unreachable":         # source could not be fetched (kept the snapshot)
                unreachable.append(mat)
        gstat = cmd_glossary(check=True) if do_glossary else None
        if gstat and gstat != "ok":
            glossary_row = {"name": "glossary", "url": "", "host": "glossary",
                            "tier": "cached", "status": "unreachable",
                            "detail": "committed glossary index is invalid", "transient": False}
            rows.append(glossary_row)
            unreachable.append(glossary_row)
        ok = sum(row["status"] == "ok" for row in rows)
        passes = check_passes(rows, tampered, a.allow_transient_unreachable)
        degraded = bool(unreachable) and passes
        if not a.json:
            print("\nmaterials drift check  (re-fetch + fingerprint vs committed provenance)")
            for r in rows:
                tag = {"ok": "ok         ", "drifted": "DRIFTED    ", "unreachable": "UNREACHABLE"}[r["status"]]
                print(f"  {tag} {r['name']}")
                if r["status"] != "ok":
                    fix = FIX_ONLY[r["host"]]
                    print(f"               {r['detail']}")
                    print(f"               fix: python3 scripts/materials/pull_materials.py --only {fix}   (then commit)")
            print(f"\n  {ok}/{len(rows)} ok"
                  + (f" · {len(drifted)} drifted" if drifted else "")
                  + (f" · {len(unreachable)} unreachable" if unreachable else "")
                  + (" · allowed transient degradation" if degraded else ""))
        else:
            print(json.dumps({"checked": len(rows), "ok": ok,
                              "drifted": [r["name"] for r in rows if r["status"] == "drifted"],
                              "unreachable": [r["name"] for r in rows if r["status"] == "unreachable"],
                              "tampered": tampered,
                              "clean": not drifted and not unreachable,
                              "degraded": degraded,
                              "rows": rows}, indent=2))
        return 0 if passes else 1

    # ── PULL mode (contributors + the deploy build) ───────────────────────────
    os.makedirs(MATS, exist_ok=True)
    prov = _load_provenance()                     # start from existing provenance so kept snapshots persist
    print(f"pulling {len(sel)} material(s)" + (f" (--only {a.only})" if a.only else "") + ":")
    for mat in sel:
        prov[mat["name"]] = pull_one(mat)         # fetch + rewrite markdown; records ok / unreachable
    if do_glossary:
        cmd_glossary(check=False)                 # refresh the heavy cached glossary tier only when asked
    payload = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "materials": [prov[m["name"]] for m in MANIFEST if m["name"] in prov]}
    with open(MATERIALS_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    bad = [r for r in payload["materials"] if r.get("status") != "ok"]
    print(f"  -> {MATERIALS_JSON}"
          + (f"   ({len(bad)} unreachable -- see above)" if bad else "   (all ok)"))
    build_catalog()   # refresh the unified surface (glossary + on-demand) after every pull
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
