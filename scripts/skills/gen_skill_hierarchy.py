#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generate the nested SKILL.html hub hierarchy:

    SKILL.html  (repository hub == bundle index, served at /lab/static/SKILL.html)
      ├─ web/SKILL.html  (surface hub)  ─→ each web/<course>/SKILL.html
            └─ <course>/SKILL.html  (course hub) ─→ its content

The root hub is the ONTOLOGY BEACON for the whole bundle: a semantically- and
statically-verifiable interface over its immediate children (execution surfaces,
reference layers, tooling, agent docs), not a pitch for any one course. Every page is
reachable from the task root through its surface + course hub, so the link graph forms
one tree of clusters budding from SKILL hubs. The pages are BOTH a machine-readable
brain (the `skill-meta` JSON block) AND a styled, human-centric web page that matches
the foyer/course aesthetic (NVIDIA dark theme, hero, card grid). Re-runnable; discovers
structure from disk. Hand-authored course SKILLs are NOT overwritten (only files
carrying the generated marker are refreshed).
"""
from __future__ import annotations
import html, json, os, re, sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

HERE = Path(__file__).resolve()
TASK1 = find_repo_root(HERE)
add_script_paths(TASK1 / "scripts")
import normalize_skill_headers
SURFACES = ("web",)
MARKER = "gen_skill_hierarchy.py"   # presence in a SKILL.html => safe to regenerate
RELEASE_STATUS = json.loads((TASK1 / "RELEASE_STATUS.json").read_text(encoding="utf-8"))

try:
    from link_projection import RELEASED   # single source for the released-course set
except Exception:
    RELEASED = ("nemoclaw",)

# Human-facing one-liner for the web bundle's released course. nemoclaw is what the release foyer surfaces.
WEB_COURSE_DESC = {
    "nemoclaw":      "Securing Agents: a browser-first course that runs against the lab's model gateway "
                     "and OpenClaw runtime. The pages build the agent loop, tools, retrieval, planning, "
                     "and sandbox controls as live artifacts. Learner-selected views collapse explicitly "
                     "optional prose and supporting code while keeping prerequisites, exercises, and safety limits visible.",
}
# One-line purpose per course page, so the rendered hub documents what each page does instead of listing bare filenames.
# Keyed by course then page stem; a missing entry just renders an empty desc.
WEB_PAGE_DESC = {
    "nemoclaw": {
        "01a-loop":          "The agent loop: a model call wrapped in a repeated perceive, reason, act cycle.",
        "01b-react":         "ReAct: reason, act, observe, repeat, with a maze artifact that keeps the code available but quiet.",
        "01c-tools":         "Tool calling: the model requests work, browser code runs it, and the model reads the result.",
        "02a-routing":       "Routing: planner, workers, and synthesis as separate calls with visible bounded orchestration.",
        "02b-rag":           "RAG: retrieval wired as a tool, from corpus chunks to grounded answer.",
        "02c-deep":          "Deep agents: a planner delegating to sub-agents over a shared filesystem.",
        "03a-kickstart":     "Connect NemoClaw: connect the browser course to the NemoClaw launchable and check the runtime endpoints.",
        "03b-openclaw":      "OpenClaw: the workspace folder is the agent's live configuration.",
        "03c-always-on":     "Always-on agents: a per-turn loop nested inside slower triggers.",
        "04a-safety":        "OpenShell in NemoClaw: policy and sandbox boundaries the prompt cannot talk past.",
        "04b-modern-clis":   "Modern CLI agents compared against the OpenShell/NemoClaw containment model.",
        "04c-going-further": "Going further: the layered view and where to take the lab next.",
        "index":             "Human entry: course landing, API-key setup, and iframe opt-in control.",
        "glossary":          "Searchable glossary of the course's agent terms.",
        "dependencies":      "Source-derived inventory of exact browser packages, licenses, hashes, and runtime references.",
        "studio":            "Authoring and inspection studio for the course pages.",
        "courses":           "Catalog redirect stub.",
    },
}
# Course support directories with hand-authored SKILL beacons stay reachable from the course hub.
WEB_SUPPORT = {
    "scripts": ("runtime scripts", "Browser modules for page chrome, runnable cells, canvas flows, OpenClaw controls, chat widgets, diagrams, retrieval helpers, and the studio tool."),
    "styles":  ("course styles", "Shared course CSS plus the light iframe/export overlay."),
    "assets":  ("image provenance", "Source, license, connection level, theme mode, mount style, and visual-preview duty for every image."),
    "mats":    ("material provenance", "Source and connection level for every companion essay."),
    "standalone": ("standalone export", "Standalone-export source and fixed assets generated from the canonical course."),
    "vendor": ("browser vendor", "Pinned same-origin browser packages, metadata, SBOM, and license texts."),
}

# Core tenets projected into root skill-meta; scripts/validation/tenets.py reports enforceable ones.
TENETS = {
    "purpose": [
        "Content is curated once and projected: pages live under execution surfaces, and "
        "bundle_standalone.py, build_pages.sh, and engine.js generate the standalone bundle, the "
        "Pages site, and the link graph from them. Add a delivery format by writing a generator, "
        "so a fix to the source reaches every format.",
        "Anchor each page in a task that runs: build a working artifact a reader executes against "
        "the lab, and cut a page that only fills an outline. The aim is a change in what a reader "
        "can do.",
        "Order is a default, not a gate: keep pages usable out of sequence, with no enforced "
        "prerequisites or knowledge checks, so a reader can act on partial understanding and "
        "return for the next layer.",
        "Target the NVIDIA-owned DLI course repository as a Full-OSS-Project after approval: OSS "
        "Type I, Apache 2.0, no gate or paywall, public course planning and contribution, the "
        "foyer surfacing only the selected courses, and mats cited by public URL. This does not "
        "classify or release the NemoClaw product or runtime.",
        "Keep the web surface browser-only and independent of student-provisioned local services.",
        "Keep production browser delivery static. Hosted model and NemoClaw endpoints supply live capabilities.",
        "Ideas stay easy to contribute through structured Issues and, after external intake is enabled, "
        "Discussions. Code stays "
        "difficult to accept: treat every patch as untrusted, require issue linkage, blast-radius "
        "evidence, deterministic gates, human ownership, protected refs, and gated releases.",
    ],
    "assumptions": [
        "The public GitHub repository is canonical and approved for public release. Private approval "
        "evidence remains in its governing system. Everything worth keeping lives here and is versioned; scratch "
        "goes to /tmp and is never committed.",
        "The web surface holds the browser-only course and its course-scoped reference packets.",
        "The brain is each source directory's SKILL.html skill-meta JSON, not a SKILL.md. Git-tracked "
        "and proposed files define the exhaustive directory set, with no opt-outs. Parse the current "
        "directory first, then walk children: task to surface to course to content. Visual work must also "
        "read the asset provenance beacon and validation beacon before edits.",
        "One link engine (scripts/runtime/engine.js) is the single source for resolution, crawl, "
        "reachability, and the release contract; it runs headless and in-browser, with no "
        "second implementation to drift.",
        "The released course is nemoclaw (Securing Agents); the foyer "
        "(web/index.html) surfaces only it.",
    ],
    "practices": [
        "Edit content in place; git history is the auditable record. Keep no parallel mirror.",
        "No em-dashes in authored prose: rewrite the construction so a dash was never needed. "
        "Never swap the glyph for a colon, semicolon, comma, or parentheses.",
        "No buzzy marketing cadence: avoid serial antithesis ('not X but Y', 'N X, one Y') and "
        "rule-of-three flourishes.",
        "Code-first: fixing a real code cell beats improving prose beats adding navigation. A "
        "change that teaches nothing new and prevents no bug is not worth making.",
        "Browser courses stay remote-services-only; never put keys in static files or depend on undeclared local services.",
        "Keep repository validation host-native; external isolation is an operator choice, not a shipped dependency.",
        "The course mats/ (web/nemoclaw/mats/) and repos/ are cited-by-URL reference packets: "
        "cite the external URL, never link the packet file.",
        "Run source_gate before adding assets, mats, datasets, cached references, or copied examples; "
        "every new source needs provenance and license disposition.",
        "When a change touches an image, SVG, diagram, canvas figure, or page placement, preview the "
        "rendered result through the active agent harness (Codex, Claude, Cursor, Playwright, or local "
        "browser smoke), inspect light and dark theme output when the asset can theme-switch, show the "
        "preview to the requester, and report that evidence or the exact blocker.",
        "Course-authored/provided SVGs under assets/figures mount with fig-embed/data-svg-src so theme "
        "variables and click-to-expand work. Plain img is only for fixed-white paper conversions documented "
        "as connection=conversion in asset provenance. Keep semantic figure labels; move only caption-like "
        "prose, contributor credit, or issue shorthand out of SVG source.",
        "Never commit lab-generated runtime output (artifacts/, export/, caches, the public/ build).",
    ],
    "cadences": [
        "Validate before pushing: validate_layout, skill_consistency, source_gate, run_engine --self-test, "
        "validate_bundle --scope ship. The same gates run at pre-push (install: "
        "bash scripts/build/install-hooks.sh).",
        "For visual work, run figure_audit, source_gate, validate_bundle --no-write --scope ship, and a "
        "rendered preview shown to the requester. Static pass without a rendered preview is incomplete "
        "unless the host harness cannot run and the blocker is named.",
        "A reported defect is a SAMPLE of a class: grep the whole repo across every course, "
        "surface, and duplicated copy before fixing, then fix every instance or name the deferrals.",
        "Improve one, improve all: a fix in one course propagates to its siblings.",
        "When scope is ambiguous, escalate; never truncate. If literal compliance is worse than "
        "the better thing, do the better thing and say so.",
    ],
    "creeds": [
        "Fix corruption markers on sight: apologetic prose, em-dashes, over-documentation, hedge "
        "phrases, deferred-dead questions, stale cross-references, a same-strength evaluation "
        "judge, commented-out runnable code.",
        "Lead-page parity: a later page must not regress from its course's lead page in heading "
        "voice, exercise density, or depth.",
        "Isolation: a course never links another course directly; only shared infra, SKILL hubs, "
        "and bundle-root files may cross.",
        "Trust the artifact over the summary: when your own text disagrees with the file, diff, "
        "or log, re-read the artifact.",
    ],
}


def courses_in(surface: str):
    """(name, skill_href|index_href) for each course dir under a surface."""
    root = TASK1 / surface
    if not root.is_dir():
        return []
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        if surface == "web" and d.name == "shared":
            continue
        if (d / "SKILL.html").is_file():
            out.append((d.name, f"{d.name}/SKILL.html"))
        else:
            for cand in ("index.html", "web/index.html"):
                if (d / cand).is_file():
                    out.append((d.name, f"{d.name}/{cand}")); break
    return out


def _nav(hub_dir, up_path=None, up_label=None):
    """Topbar nav for a framer hub: home -> the release foyer, up -> the parent SKILL, both
    as paths relative to this hub's directory so they resolve in the lab (served at /lab/static)."""
    nav = {"home": os.path.relpath("web/index.html", hub_dir) if hub_dir else "web/index.html"}
    if up_path:
        nav["up"] = {"label": up_label, "href": os.path.relpath(up_path, hub_dir) if hub_dir else up_path}
    return nav


def framer_page(meta, title, sections, actions=None, readme=None, summary=None, nav=None,
                framer_rel="web/_skill_explorer.js"):
    """Emit a SKILL hub as a framer-driven page: the skill-meta contract plus an explorer-config
    (hub mode) that the ONE renderer (web/_skill_explorer.js) turns into a live README reflection,
    repo linkage, and a build-guided query. The child links are mirrored as plain <a href> in
    <noscript>, so the link engine crawls them (it reads raw <a href>, never the JSON config) and a
    no-JS reader still navigates. Replaces the bespoke per-hub HTML, CSS, and self-test: the chrome
    and the link self-assess now live once, in the framer."""
    summary = summary or meta.get("thesis") or meta.get("title", "")
    groups = []
    if actions:
        groups.append({"title": "Start here", "items": [{"label": lbl, "href": href, "desc": ""}
                                                         for (lbl, href, _primary) in actions]})
    for (t, _help, items) in sections:
        if items:
            groups.append({"title": t, "items": [{"label": n, "href": h, "desc": d} for (n, h, d) in items]})
    cfg = {"mode": "hub", "title": title, "summary": summary, "ties": ["build"], "links": groups}
    if readme:
        cfg["readme"] = readme
    if nav:
        cfg["nav"] = nav
    ns = []
    for g in groups:
        lis = "\n".join(f'    <li><a href="{it["href"]}">{html.escape(it["label"])}</a></li>' for it in g["items"])
        ns.append(f'  <h2>{html.escape(g["title"])}</h2>\n  <ul>\n{lis}\n  </ul>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<!-- generated by scripts/{MARKER}; edit the generator and regenerate, do not hand-edit -->
<title>{html.escape(title)}</title>
<script type="application/json" id="skill-meta">
{json.dumps(meta, indent=2)}
</script>
<script type="application/json" id="explorer-config">
{json.dumps(cfg, indent=2)}
</script>
</head>
<body>
<div id="explorer"></div>
<noscript>
  <h1>{html.escape(title)}</h1>
{chr(10).join(ns)}
</noscript>
<script src="{framer_rel}"></script>
</body></html>
"""


def write(path: Path, content: str):
    if path.name == "SKILL.html":
        content = normalize_skill_headers.normalize(path, content)
    path.write_text(content); print("wrote", path.relative_to(TASK1))


def gen_task():
    """The root SKILL.html is served at /lab/static/SKILL.html. It is the
    ONTOLOGY BEACON for the whole bundle: an honest, statically-verifiable interface over
    its immediate children (the execution surfaces, the reference layers, the tooling, the
    agent docs), not a pitch for any one course. It descends into the per-surface hubs and
    points humans at the curated release foyer."""
    surfaces = [(s, f"{s}/SKILL.html") for s in SURFACES if (TASK1 / s).is_dir()]
    sdesc = {"web": "Browser frontends: the course as styled web pages, remote services only "
                    "(no local microservices). Assumes only a browser and declared hosted endpoints."}
    items = [(f"{s}/", h, sdesc.get(s, "")) for s, h in surfaces]

    # Non-course root layers: describe references, card tooling.
    ref_layers = []
    if (TASK1 / "web" / "nemoclaw" / "mats").is_dir():
        ref_layers.append({"name": "web/nemoclaw/mats", "role": "course-scoped curated reference "
                           "packets; joined to pages by the external URLs they cite and associated "
                           "through the link graph, never linked as files"})
    if (TASK1 / "repos").is_dir():
        ref_layers.append({"name": "repos", "role": "vendored external repositories kept for "
                           "context-sharing and retrieval; not student content"})
    if (TASK1 / "scripts").is_dir():
        ref_layers.append({"name": "scripts", "role": "bundle tooling: the projection engine, the "
                           "link-graph viewer, the validation cadence, this SKILL generator"})
    # describe only the layers that actually exist on disk (ref_layers is dir-gated)
    layers_html = ", ".join(f"<code>{r['name']}/</code>" for r in ref_layers) or "none present"
    ref_help = ("Immediate children of the bundle root that are not courses. "
                + " ".join(f"<code>{r['name']}/</code> {r['role']}." for r in ref_layers))
    # Source explorers and topology tools are discovered from disk.
    import re as _re
    explorers = []
    for d in sorted(p for p in TASK1.iterdir() if p.is_dir()):
        sk = d / "SKILL.html"
        if d.name in SURFACES or not sk.is_file():
            continue
        m = _re.search(r'<script type="application/json" id="skill-meta">(.*?)</script>', sk.read_text(), _re.S)
        try:
            em = json.loads(m.group(1)) if m else {}
        except Exception:
            em = {}
        if em.get("node_type") == "directory-explorer":
            explorers.append((f"{d.name}/", f"{d.name}/SKILL.html",
                              (em.get("summary", "") or "").split(". ")[0][:140]))
    priority_nodes = []
    if (TASK1 / "scripts" / "compliance" / "SKILL.html").is_file():
        priority_nodes.append((
            "License and distribution evidence",
            "scripts/compliance/SKILL.html",
            "Review shipped software, source terms, SBOM evidence, and downloadable inventories.",
        ))
    src_items = priority_nodes + list(explorers)
    if (TASK1 / "scripts" / "link_graph.html").is_file():
        src_items.append(("scripts/runtime/link_graph.html", "scripts/runtime/link_graph.html",
                          "Link + topology viewer: how every page resolves and what reaches a SKILL hub."))

    docs = [("README.md", "README.md", "What the public course is and how to run it (start here)."),
            ("RELEASE_STATUS.json", "RELEASE_STATUS.json", "Machine-readable publication and licensing state."),
            ("CHANGELOG.md", "CHANGELOG.md", "Version history for public releases and pending changes."),
            ("LICENSE", "LICENSE", "Apache License 2.0 for the public release."),
            ("SECURITY.md", "SECURITY.md", "Official NVIDIA private vulnerability-reporting policy."),
            ("AGENTS.md", "AGENTS.md", "Cross-harness agent contract and task routing."),
            ("CONTRIBUTING.md", "CONTRIBUTING.md", "How to contribute: hooks, the validation gate, conventions."),
            ("DCO.md", "DCO.md", "Required per-commit origin signoff and repair guidance."),
            ("CODE_OF_CONDUCT.md", "CODE_OF_CONDUCT.md", "Community behavior, private reporting, and enforcement."),
            ("SUPPORT.md", "SUPPORT.md", "Support scope, response expectation, and lifecycle policy."),
            ("scripts/compliance/docs/open_source_readiness.md", "scripts/compliance/docs/open_source_readiness.md", "Release-safe readiness checklist and roles."),
            ("scripts/compliance/docs/vendor_policy.md", "scripts/compliance/docs/vendor_policy.md", "Source and vendor-ingestion policy."),
            ("SKILL_CONTRACT.md", "SKILL_CONTRACT.md", "The SKILL.html beacon spec.")]
    docs = [(n, h, d) for n, h, d in docs if (TASK1 / h).is_file()]
    document_descriptions = {
        "agentic-compliance-suite.md": "How repository contracts guide agents from discovery through deterministic checks and protected human decisions.",
    }
    for p in (sorted((TASK1 / "docs").glob("*.md")) if (TASK1 / "docs").is_dir() else []):
        docs.append((f"docs/{p.name}", f"docs/{p.name}", document_descriptions.get(p.name, "")))

    # The release foyer is the CURATED student entry: it surfaces only the released courses (RELEASED).
    # This beacon documents the whole ontology; the foyer ships a subset.
    rel_courses = [c for c in RELEASED if (TASK1 / "web" / c).is_dir()]
    actions = [("Open the release foyer →", "web/index.html", True)]
    if (TASK1 / "web" / "nemoclaw" / "01a-loop.html").is_file():
        actions.append(("Securing Agents", "web/nemoclaw/01a-loop.html", False))

    meta = {"node_type": "hub", "level": "task", "title": "Building Agents · NVIDIA DLI bundle",
            "role": "bundle_index", "served_at": "/lab/static/SKILL.html", "self_path": "SKILL.html",
            "thesis": ("NVIDIA DLI's open-source course repository: the narrative, "
                       "the assets and the automatic "
                       "verification that keeps it honest, packaged so a person or an agent can stand it "
                       "up, navigate it, and check it end to end. Content is organized around the static web surface "
                       "so each piece declares what it needs to run; every page buds from "
                       "a SKILL hub, so the whole bundle is statically and semantically verifiable."),
            "surfaces": [{"name": s, "path": f"{s}/SKILL.html", "assumes": sdesc.get(s, "")} for s, _ in surfaces],
            "reference_layers": ref_layers,
            "release": {"surface": "web/index.html", "courses": rel_courses,
                        "publication_state": RELEASE_STATUS["publication_state"],
                        "external_mirror": RELEASE_STATUS["external_mirror"],
                        "external_repository": RELEASE_STATUS["external_repository"],
                        "intended_oss_type": RELEASE_STATUS["intended_oss_type"],
                        "oss_scope": RELEASE_STATUS["oss_scope"],
                        "excluded_product_scope": RELEASE_STATUS["excluded_product_scope"],
                        "target_license": RELEASE_STATUS["target_license"],
                        "notice_required": RELEASE_STATUS["notice_required"],
                        "status_path": "RELEASE_STATUS.json",
                        "note": "the foyer selection does not imply external publication approval"},
            "tenets": TENETS,
            "children": ([{"name": s, "path": f"{s}/SKILL.html"} for s, _ in surfaces]
                         + [{"name": n.rstrip("/"), "path": h} for (n, h, _d) in priority_nodes + explorers])}

    write(TASK1 / "SKILL.html",
          framer_page(meta, "Building Agents · NVIDIA DLI bundle",
               [("Execution surfaces", None, items),
                ("Source & tooling", None, src_items),
                ("Agent docs", None, docs)],
               actions=actions, readme="README.md", nav=_nav(""), framer_rel="web/_skill_explorer.js"))


def gen_surface(surface: str):
    cs = courses_in(surface)
    items = [(n, h, WEB_COURSE_DESC.get(n, "")) for n, h in cs] if surface == "web" \
        else [(f"{n}/", h, "") for n, h in cs]
    sections = [("Courses", None, items)]
    if surface == "web":   # the web surface also hosts the bundle's landing pages + LMS navigators
        landing = [(n, n, d) for n, d in
                   [("index.html", "Human entry: the release course picker."),
                    ("courses.html", "Catalog redirect stub.")]
                   if (TASK1 / "web" / n).is_file()]
        if landing:
            sections.append(("Landing pages", None, landing))
        shared = TASK1 / "web" / "shared" / "SKILL.html"
        if shared.is_file():
            sections.append(("Shared browser infrastructure", "Course-neutral browser assets used without linking one course to another.",
                             [("shared/", "shared/SKILL.html", "Pinned browser libraries, license evidence, and common NVIDIA favicon provenance.")]))
        nav = [(n, f"../scripts/{n}", d) for n, d in
               [("edx_navigator_quick.html", "Course LMS navigator."),
                ("edx_getting_started.html", "LMS getting-started page.")]
               if (TASK1 / "scripts" / n).is_file()]
        if nav:
            sections.append(("LMS navigators", None, nav))
    lead = ("The browser frontends: each course rendered as styled web pages, remote services only."
            if surface == "web" else SURFACE_LEAD.get(surface, f"Courses on the {surface} surface."))
    meta = {"node_type": "hub", "level": "surface", "surface": surface, "title": f"{surface} surface",
            "self_path": f"{surface}/SKILL.html",
            "children": ([{"name": n, "path": f"{surface}/{h}"} for n, h in cs]
                         + ([{"name": "shared", "path": "web/shared/SKILL.html"}]
                            if surface == "web" and (TASK1 / "web" / "shared" / "SKILL.html").is_file() else []))}
    write(TASK1 / surface / "SKILL.html",
          framer_page(meta, f"{surface}/ · surface hub", sections, summary=lead,
                      nav=_nav(surface, "SKILL.html", "task1"),
                      framer_rel=os.path.relpath("web/_skill_explorer.js", surface)))


def _declares_tool_role(path: Path) -> bool:
    """A page is a tool (carded separately from the student module flow) iff it says so in its
    own head: <meta name="page-role" content="tool">. The page self-declares; there is no central
    filename list to drift against the engine."""
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:2000]
    except OSError:
        return False
    return bool(re.search(r'<meta\s+name=["\']page-role["\']\s+content=["\']tool["\']', head))


def gen_web_course_hubs():
    """Web courses (frontends) often lack a SKILL.html. Give each a styled course hub so the
    web surface follows the task→surface→course→content shape. Refreshes only its own generated
    hubs (marker check); never clobbers a hand-authored course SKILL."""
    web = TASK1 / "web"
    if not web.is_dir():
        return
    for d in sorted(p for p in web.iterdir() if p.is_dir() and not p.name.startswith(".")):
        sk = d / "SKILL.html"
        if sk.is_file() and MARKER not in sk.read_text():
            continue
        # Tool pages self-declare via page-role=tool and live outside the student module grid.
        htmls = [p for p in d.glob("*.html") if not p.name.startswith("_")]
        tools = sorted(p for p in htmls if _declares_tool_role(p))
        flat = [p for p in htmls if p not in tools]
        nested = [p for p in (d / "web").glob("*.html")] if (d / "web").is_dir() else []
        edx = sorted((d / "edx").glob("*.html")) if (d / "edx").is_dir() else []
        shared_docs = sorted((d / "_shared").glob("*.md")) if (d / "_shared").is_dir() else []
        # Subdir index.html files pull whole sub-collections into the SKILL tree.
        SKIP_SUB = {"edx", "web", "_shared", "assets", "scripts", "_tools",
                    "standalone", "node_modules", "__pycache__", ".ipynb_checkpoints"}
        subindex = sorted(p for p in d.glob("*/index.html")
                          if p.parent.name not in SKIP_SUB and not p.parent.name.startswith((".", "_")))
        primary = sorted(flat or nested)
        pages = primary + subindex + edx + shared_docs + tools
        if not pages:
            continue

        def _label(p):
            return p.parent.name if p.name == "index.html" else p.stem

        pd = WEB_PAGE_DESC.get(d.name, {})
        support_files = [d / name / "SKILL.html" for name in WEB_SUPPORT]
        support_files = [p for p in support_files if p.is_file()]
        implementation = [p for p in support_files if p.parent.name in {"scripts", "styles"}]
        provenance = [p for p in support_files if p.parent.name in {"assets", "mats"}]
        distribution = [p for p in support_files if p.parent.name in {"standalone", "vendor"}]
        sections = [("Pages", None, [(p.stem, p.relative_to(d).as_posix(), pd.get(p.stem, "")) for p in primary])]
        if subindex:
            sections.append(("Collections", "Sub-collections with their own launcher; open one to "
                             "reach every page inside it.",
                             [(_label(p), p.relative_to(d).as_posix(), "") for p in subindex]))
        if edx:
            sections.append(("edX delivery", None, [(p.stem, p.relative_to(d).as_posix(), "") for p in edx]))
        if shared_docs:
            sections.append(("Shared", None, [(p.stem, p.relative_to(d).as_posix(), "") for p in shared_docs]))
        if tools:
            sections.append(("Tools", "Authoring and inspection tools for this course; open one to work "
                             "with the material directly. Not part of the student module flow.",
                             [(p.stem, p.relative_to(d).as_posix(), pd.get(p.stem, "")) for p in tools]))
        if implementation:
            sections.append(("Implementation", "Course-owned runtime assets that pages import or the bundler inlines.",
                             [(WEB_SUPPORT[p.parent.name][0], p.relative_to(d).as_posix(), WEB_SUPPORT[p.parent.name][1])
                              for p in implementation]))
        if provenance:
            sections.append(("Provenance", "Source, license, and connection level for the course's images "
                             "and companion materials.",
                             [(WEB_SUPPORT[p.parent.name][0], p.relative_to(d).as_posix(), WEB_SUPPORT[p.parent.name][1])
                              for p in provenance]))
        if distribution:
            sections.append(("Distribution", "Standalone and same-origin dependency surfaces shipped with the course.",
                             [(WEB_SUPPORT[p.parent.name][0], p.relative_to(d).as_posix(), WEB_SUPPORT[p.parent.name][1])
                              for p in distribution]))
        meta = {"node_type": "hub", "level": "course", "surface": "web", "course": d.name,
                "self_path": f"web/{d.name}/SKILL.html",
                "children": [{"name": _label(p), "path": p.relative_to(TASK1).as_posix()} for p in pages]
                            + [{"name": p.parent.name, "path": p.relative_to(TASK1).as_posix()} for p in support_files]}
        interface_inventory = d / "interface-inventory.json"
        if interface_inventory.is_file():
            contract = json.loads(interface_inventory.read_text(encoding="utf-8"))
            meta["interface_inventory"] = {
                "schema": contract.get("schema"),
                "source": interface_inventory.name,
            }
            meta["validation_profile"] = {
                "schema": "reacs-form-factor/1",
                "form_factors": contract.get("validation_profile", []),
            }
            interface_items = [
                ("interface inventory", interface_inventory.name,
                 "Factories, explicit roots, generated instances, authority classes, and required lifecycle states."),
            ]
            for name, profile in sorted(contract.get("form_factors", {}).items()):
                states = ", ".join(profile.get("states", []))
                interface_items.append((
                    name, interface_inventory.name,
                    f"Authority: {profile.get('authority', 'unknown')}. Required states: {states}.",
                ))
            sections.append(("Interfaces", "Machine-checked discovery rules and form-factor contracts for every course interface.", interface_items))
        lead = WEB_COURSE_DESC.get(d.name, f"The {d.name} browser course, {len(primary)} pages.")
        write(sk, framer_page(meta, f"web/{d.name} · course hub", sections, summary=lead,
                              nav=_nav("web/" + d.name, "web/SKILL.html", "web"),
                              framer_rel=os.path.relpath("web/_skill_explorer.js", "web/" + d.name)))


if __name__ == "__main__":
    gen_web_course_hubs()          # web course hubs first, so the bundle index can link them
    gen_task()
    for s in SURFACES:
        if (TASK1 / s).is_dir():
            gen_surface(s)
