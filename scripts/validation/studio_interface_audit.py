#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit the course studio interface contract.

This is a static gate for the authoring studio. It checks that studio.html remains
self-hosted, that studio_main.js still supports lab writes plus static read-only
preview, exposes automated-test commands, and that the scripts SKILL documents those modes.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root

HERE = Path(__file__).resolve()
ROOT = find_repo_root(HERE)
COURSE = ROOT / "web" / "nemoclaw"
STUDIO_HTML = COURSE / "studio.html"
STUDIO_JS = COURSE / "scripts" / "studio_main.js"
SCRIPT_SKILL = COURSE / "scripts" / "SKILL.html"
RUNTIME_SKILL = ROOT / "scripts" / "runtime" / "SKILL.html"
ROOT_SCRIPT_SKILL = ROOT / "scripts" / "SKILL.html"
LAB_RUNTIME_DOC = ROOT / "docs" / "lab_runtime_testing.md"
RELEASE_PLAYBOOK = ROOT / "docs" / "release_playbook.md"
BROWSER_PROBE = ROOT / "scripts" / "runtime" / "browser_env_probe.sh"
HELPER_NOTEBOOK_AUDIT = ROOT / "scripts" / "validation" / "helper_notebook_runtime_audit.py"
STUDIO_RESPONSIVE_AUDIT = ROOT / "scripts" / "validation" / "studio_responsive_audit.py"

REQUIRED_IDS = {
    "mod-sel", "url-bar", "reload-btn", "sidebar-btn", "comment-btn",
    "edit-btn", "run-btn", "block-edit-btn", "lite-btn", "tb-status",
    "sidebar", "poll-on", "poll-secs", "lm-row", "jump-btn", "cmt-list",
    "cmt-badge", "ref-list", "autorun-on", "autoannotate-on", "run-note",
    "editmode-on", "write-note", "chg-list", "save-sel-btn", "studio-frame",
    "loading", "pick-ov", "block-editor", "be-ta", "studio-pop",
}

REQUIRED_JS = {
    "lab contents api candidate": "/lab/api/contents/web/nemoclaw/",
    "legacy contents api candidate": "/lab/api/contents/nemoclaw/",
    "lab-only authoring API": "const LAB_AUTHORING = location.pathname.startsWith('/lab/static/')",
    "static ready state": "let contentApiReady = !LAB_AUTHORING",
    "static page URL resolver": "function directPageUrl",
    "static read-only fallback": "Read-only preview: Jupyter contents API not available",
    "local comment fallback": "localStorage.setItem(commentStorageKey()",
    "reference inspector": "function renderReferences",
    "light export CSS": "styles/_lite_overlay.css",
    "run-all selector": ".cf-btn-run,.rc-run,.cell-run",
    "ordered run queue": "async function triggerRunAll",
    "run completion waiter": "function waitForRunComplete",
    "run failure collector": "const failures = []",
    "run failure summary": "runnable block(s) · ${failures.length} failed",
    "default page load": "loadPage(p || MODULES[0].file)",
    "block editor locator": "function _locateBlockInFile",
    "no stale lite CSS path": "styles/styles/_lite_overlay.css",
}

REQUIRED_SKILL = {
    "audit command": "python3 scripts/validation/studio_interface_audit.py",
    "helper notebook static audit": "python3 scripts/validation/helper_notebook_runtime_audit.py --static-only",
    "helper notebook runtime audit": "python3 scripts/validation/helper_notebook_runtime_audit.py",
    "lab authoring mode": "Lab authoring",
    "static review mode": "Read-only static preview",
    "light export mode": "Light export review",
    "openclaw mode": "OpenClaw controls",
    "studio testing split": "operator console for running or copying checks",
    "browser env probe": "scripts/runtime/browser_env_probe.sh",
    "browser smoke harness": "scripts/runtime/browser_runtime_test.sh --smoke",
    "render-only harness": "scripts/runtime/browser_runtime_test.sh --render-only",
    "helper notebook heading": "Helper notebook",
    "helper map cell": "helper-map-cell",
    "helper retrieval cell": "helper-retrieval-cell",
    "helper live cell": "helper-live-cell",
    "helper UI cell": "helper-ui-cell",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def html_ids(raw: str) -> set[str]:
    return set(re.findall(r'\bid=["\']([^"\']+)["\']', raw))


def lesson_pages() -> set[str]:
    return {p.name for p in COURSE.glob("[0-9][0-9][a-z]-*.html")}


def module_pages(js: str) -> set[str]:
    return set(re.findall(r"file:\s*['\"]([^'\"]+\.html)['\"]", js))


def audit() -> list[str]:
    findings: list[str] = []
    html = read(STUDIO_HTML)
    js = read(STUDIO_JS)
    skill = read(SCRIPT_SKILL)
    runtime_skill = read(RUNTIME_SKILL)
    root_script_skill = read(ROOT_SCRIPT_SKILL)
    lab_doc = read(LAB_RUNTIME_DOC)
    release_playbook = read(RELEASE_PLAYBOOK)
    browser_probe = read(BROWSER_PROBE) if BROWSER_PROBE.is_file() else ""

    missing_ids = sorted(REQUIRED_IDS - html_ids(html))
    for item in missing_ids:
        findings.append(f"studio.html missing required id #{item}")

    external_assets = re.findall(r'<(?:script|link)\b[^>]*(?:src|href)=["\']https?://[^"\']+', html, re.I)
    for item in external_assets:
        findings.append(f"studio.html imports external asset: {item}")
    if "cdnjs" in html.lower():
        findings.append("studio.html still references cdnjs")
    if 'href="styles/_style.css"' not in html:
        findings.append("studio.html does not use local styles/_style.css")

    pages = lesson_pages()
    modules = module_pages(js)
    for item in sorted(pages - modules):
        findings.append(f"studio_main.js MODULES omits lesson page {item}")
    for item in sorted(modules - pages):
        findings.append(f"studio_main.js MODULES references non-lesson page {item}")

    required_studio_css = {
        "topbar horizontal scroll": ".studio-topbar{height:var(--studio-top);display:flex;align-items:center;gap:.55rem;padding:0 max(1rem,calc((100vw - min(92rem,100%))/2));border-bottom:1px solid var(--bd);background:var(--bg);position:relative;z-index:20;overflow-x:auto",
        "topbar children no shrink": ".studio-topbar>*{flex-shrink:0}",
        "button min width": ".tb-btn{height:var(--studio-min-control);min-width:3.25rem;flex:0 0 auto",
        "sidebar min width": ".studio-sidebar{width:var(--studio-side);min-width:min(16rem,72vw);max-width:82vw",
        "sidebar scroll min height": ".sb-scroll{flex:1;overflow:auto",
        "section flex floor": ".sb-section{border:1px solid var(--bd);border-radius:8px;background:var(--bg);overflow:hidden;display:flex;flex-direction:column;min-height:2.1rem;flex:0 0 auto",
        "body min height": ".sb-body{padding:.7rem;display:flex;flex-direction:column;gap:.65rem;min-height:0}",
        "list scroll floors": "#cmt-list,#ref-list,#test-list,#chg-list{min-height:7rem;max-height:clamp(7rem,30vh,20rem);overflow-y:auto",
        "small viewport sidebar floor": "@media(max-width:900px){.tb-input{display:none}.tb-status{display:none}.studio-sidebar{width:17rem;min-width:min(15rem,78vw)}",
    }
    for label, token in required_studio_css.items():
        if token not in html:
            findings.append(f"studio.html missing responsive layout CSS {label}: {token}")

    for label, token in REQUIRED_JS.items():
        if label == "no stale lite CSS path":
            if token in js:
                findings.append("studio_main.js still has stale styles/styles/_lite_overlay.css path")
            continue
        if token not in js:
            findings.append(f"studio_main.js missing {label}: {token}")

    required_studio_tokens = {
        "test command model": "const TEST_COMMANDS",
        "test command renderer": "function renderTestCommands",
        "static audit command": "python3 scripts/validation/studio_interface_audit.py",
        "helper notebook static command": "python3 scripts/validation/helper_notebook_runtime_audit.py --static-only",
        "helper notebook browser command": "python3 scripts/validation/helper_notebook_runtime_audit.py",
        "studio responsive browser command": "python3 scripts/validation/studio_responsive_audit.py",
        "browser env probe command": "scripts/runtime/browser_env_probe.sh",
        "browser smoke command": "scripts/runtime/browser_runtime_test.sh --smoke",
        "render-only test command": "scripts/runtime/browser_runtime_test.sh --render-only",
    }
    for label, token in required_studio_tokens.items():
        if token not in js:
            findings.append(f"studio_main.js missing {label}: {token}")

    for label, token in REQUIRED_SKILL.items():
        if token not in skill:
            findings.append(f"web/nemoclaw/scripts/SKILL.html missing {label}: {token}")

    runtime_tokens = {
        "probe file": "browser_env_probe.sh",
        "probe command": "scripts/runtime/browser_env_probe.sh",
        "browser smoke": "scripts/runtime/browser_runtime_test.sh --smoke",
        "host prerequisites": "host Node.js, the pinned playwright-core API, and Chromium",
        "host browser entrypoint": "scripts/runtime/browser_runtime_test.sh --smoke",
    }
    for label, token in runtime_tokens.items():
        if token not in runtime_skill:
            findings.append(f"scripts/runtime/SKILL.html missing {label}: {token}")

    for label, token in {
        "scripts beacon probe": "scripts/runtime/browser_env_probe.sh",
        "scripts helper notebook link": "web/nemoclaw/scripts/SKILL.html",
        "scripts helper notebook style": "runnable notebook",
    }.items():
        if token not in root_script_skill:
            findings.append(f"scripts/SKILL.html missing {label}: {token}")

    for label, token in {
        "lab doc probe": "scripts/runtime/browser_env_probe.sh",
        "lab doc host prerequisites": "Python 3.11 or newer",
        "lab doc pinned browser API": "cd scripts/runtime && corepack enable && pnpm install --frozen-lockfile --ignore-scripts",
        "lab doc external isolation boundary": "does not build, scan, support, or distribute that environment",
    }.items():
        if token not in lab_doc:
            findings.append(f"docs/lab_runtime_testing.md missing {label}: {token}")

    for label, token in {
        "release playbook runtime guide": "lab_runtime_testing.md",
    }.items():
        if token not in release_playbook:
            findings.append(f"docs/release_playbook.md missing {label}: {token}")

    for label, token in {
        "probe host node status": "node:",
        "probe browser API status": "playwright-core:",
        "probe chromium status": "chromium/chrome:",
    }.items():
        if token not in browser_probe:
            findings.append(f"scripts/runtime/browser_env_probe.sh missing {label}: {token}")

    if not BROWSER_PROBE.is_file():
        findings.append("scripts/runtime/browser_env_probe.sh missing")
    elif not (BROWSER_PROBE.stat().st_mode & 0o111):
        findings.append("scripts/runtime/browser_env_probe.sh is not executable")

    if not HELPER_NOTEBOOK_AUDIT.is_file():
        findings.append("scripts/validation/helper_notebook_runtime_audit.py missing")
    elif not (HELPER_NOTEBOOK_AUDIT.stat().st_mode & 0o111):
        findings.append("scripts/validation/helper_notebook_runtime_audit.py is not executable")
    else:
        import helper_notebook_runtime_audit
        for item in helper_notebook_runtime_audit.static_audit():
            findings.append(item)

    if not STUDIO_RESPONSIVE_AUDIT.is_file():
        findings.append("scripts/validation/studio_responsive_audit.py missing")
    elif not (STUDIO_RESPONSIVE_AUDIT.stat().st_mode & 0o111):
        findings.append("scripts/validation/studio_responsive_audit.py is not executable")

    if "Write access: Jupyter contents API" not in js or "Read-only static preview" not in js:
        findings.append("studio_main.js must surface lab-write versus static-read-only state")

    return findings


def main() -> int:
    findings = audit()
    if findings:
        print("studio_interface_audit: FAIL")
        for row in findings:
            print(f"  - {row}")
        return 1
    print("studio_interface_audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
