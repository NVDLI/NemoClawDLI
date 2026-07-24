#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Keep authored browser sinks behind their reviewed construction boundaries.

CodeQL discovers new data flows. This deterministic ReACS layer protects the controls that make
intentional browser parsing, preview execution, navigation, and tab-scoped credentials safe enough
for the static course design. Authored browser sources are discovered by default; publisher vendor
bytes are governed separately by the exact-hash SARIF disposition policy.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".html", ".js", ".mjs"}
AUTHORED_ROOTS = ("web", "scripts", "i18n")
PUBLISHER_TREES = ("/vendor/", "/mats/")

BOUNDARIES: tuple[tuple[str, str, str], ...] = (
    ("web/nemoclaw/scripts/_course_assistant.js", 'sandbox="allow-scripts"',
     "Course Assistant preview must retain an opaque origin"),
    ("web/nemoclaw/scripts/_course_assistant.js", "event.source!==parent",
     "Course Assistant child bridge must accept messages only from its parent"),
    ("web/nemoclaw/scripts/_course_assistant.js", "event.source !== artifactFrame.contentWindow",
     "Course Assistant parent bridge must accept messages only from its preview frame"),
    ("web/nemoclaw/scripts/_course_assistant.js", "connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'",
     "Course Assistant preview CSP must deny network, nested frames, workers, and objects"),
    ("web/nemoclaw/scripts/_course_assistant.js", "base,meta[http-equiv],iframe,object,embed",
     "Course Assistant static validation must reject navigation-capable elements"),
    ("web/nemoclaw/scripts/_course_assistant.js", r"\bwindow\.open\s*\(",
     "Course Assistant static validation must reject popup navigation"),
    ("web/nemoclaw/scripts/_course_assistant.js", r"\b(?:window\.)?location\s*=",
     "Course Assistant static validation must reject location assignment"),
    ("scripts/validation/learner_flow_runtime_audit.py", "Course Assistant artifact escaped its opaque-origin boundary",
     "Course Assistant runtime audit must prove parent access remains blocked"),
    ("scripts/validation/learner_flow_runtime_audit.py", "Course Assistant artifact admitted a navigation primitive",
     "Course Assistant runtime audit must exercise navigation attacks"),
    ("scripts/pyodide/examples/live-playground.js", 'document.createElement("template")',
     "Pyodide rich output must parse in an inert template"),
    ("scripts/pyodide/examples/live-playground.js", "if (!RICH_TAGS.has(node.tagName))",
     "Pyodide rich output must reconstruct only allowlisted elements"),
    ("scripts/pyodide/examples/live-playground.js", "BLOCKED_RICH_TAGS.has(node.tagName)",
     "Pyodide rich output must drop active elements instead of unwrapping them"),
    ("scripts/pyodide/examples/live-playground.js", "document.createTextNode(node.textContent",
     "Pyodide rich output must reconstruct text without HTML interpretation"),
    ("scripts/skills/skill_renderer_runtime_audit.py", "Pyodide rich output sanitizer admitted executable or network-active HTML",
     "The exhaustive browser matrix must exercise hostile rich output"),
    ("web/nemoclaw/scripts/studio_main.js", 'new DOMParser().parseFromString(String(source), "text/html")',
     "Studio preview must parse edited HTML in an inert document"),
    ("web/nemoclaw/scripts/studio_main.js", 'name.startsWith("on") || name === "srcdoc"',
     "Studio preview must remove event handlers and nested documents"),
    ("web/nemoclaw/scripts/studio_main.js", "safeStudioUrl(attribute.value, name)",
     "Studio preview must canonicalize every URL-bearing attribute"),
    ("scripts/validation/studio_responsive_audit.py", "Studio preview sanitizer admitted active content",
     "Studio browser validation must exercise active-content mutations"),
    ("scripts/edx/edx_getting_started.html", "if(parsed.username||parsed.password||parsed.port) return false",
     "edX lab links must reject credentials and non-default ports"),
    ("scripts/edx/edx_getting_started.html", "return allowed?'https://'+host+'/':false",
     "edX lab links must be rebuilt from an allowlisted host"),
    ("scripts/edx/edx_getting_started.html", "if(!trustedMessage(e)) return",
     "edX environment messages must pass source and origin validation"),
    ("scripts/edx/edx_getting_started.html", "e.source!==window&&e.source!==window.parent&&e.source!==window.top",
     "edX environment messages must come from the expected browsing context"),
    ("web/_skill_explorer.js", "safeNavigationHref(it.href)",
     "SKILL hub links must pass canonical navigation validation"),
    ("web/_skill_explorer.js", "safeNavigationHref(x.href)",
     "SKILL related links must pass canonical navigation validation"),
    ("scripts/skills/skill_renderer_runtime_audit.py", "unsafe navigation URL",
     "The exhaustive SKILL browser matrix must reject unsafe dynamic links"),
    ("web/nemoclaw/scripts/_figures.js", "if (url.origin !== location.origin) return null",
     "Figure fetches must remain same-origin"),
    ("web/nemoclaw/scripts/_figures.js", 'if (!/\\.svg$/i.test(url.pathname)) return null',
     "Figure fetches must remain SVG-only"),
    ("web/nemoclaw/scripts/_figures.js", "host.textContent = \"Figure could not be loaded.\"",
     "Figure failures must not create an attacker-controlled link"),
    ("scripts/runtime/engine.js", "function stripHtmlRawText",
     "Indexing must use the HTML raw-text scanner instead of a tag regex"),
    ("scripts/runtime/engine.js", "</script \\t\\n bogus>",
     "The engine self-test must cover permissive end-tag syntax"),
    ("docs/security-design.md", "browser storage is not a vault",
     "The security beacon must state the browser credential boundary"),
    ("docs/security-design.md", "same-origin credential broker",
     "The security design must name the server-side alternative to browser-held credentials"),
    ("docs/product-design.md", "Tab-scoped browser `sessionStorage`",
     "The product design must disclose model credential retention"),
)


def repository_candidates(root: Path) -> list[Path]:
    """Return every tracked or proposed non-ignored repository file.

    CI may install ignored dependency trees before this audit runs. Git's candidate set keeps those
    transient publisher files outside the authored boundary while still discovering every added,
    renamed, copied, or untracked proposal without a file allowlist.
    """
    if (root / ".git").exists():
        result = subprocess.run(
            [
                "git", "-C", str(root), "ls-files", "-z",
                "--cached", "--others", "--exclude-standard", "--",
                *AUTHORED_ROOTS,
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return sorted(
                root / rel.decode("utf-8", errors="surrogateescape")
                for rel in result.stdout.split(b"\0")
                if rel and (root / rel.decode("utf-8", errors="surrogateescape")).is_file()
            )
    return sorted(
        path
        for source_root in AUTHORED_ROOTS
        for path in (root / source_root).rglob("*")
        if (root / source_root).is_dir() and path.is_file()
    )


def authored_sources(root: Path, overrides: dict[str, str] | None = None) -> list[Path]:
    """Discover every repository-owned browser source without a file opt-in list."""
    overrides = overrides or {}
    paths: list[Path] = []
    candidates = set(repository_candidates(root))
    for rel in overrides:
        path = root / rel
        if rel.split("/", 1)[0] in AUTHORED_ROOTS:
            candidates.add(path)
    for path in candidates:
        rel = "/" + path.relative_to(root).as_posix()
        if path.suffix.lower() not in TEXT_SUFFIXES or any(
            marker in rel for marker in PUBLISHER_TREES
        ):
            continue
        if path.is_file() or path.relative_to(root).as_posix() in overrides:
            paths.append(path)
    return sorted(paths)


def audit(root: Path = ROOT, overrides: dict[str, str] | None = None) -> list[str]:
    overrides = overrides or {}
    findings: list[str] = []

    def text(rel: str) -> str:
        if rel in overrides:
            return overrides[rel]
        path = root / rel
        if not path.is_file():
            findings.append(f"{rel}: reviewed browser boundary file is missing")
            return ""
        return path.read_text(encoding="utf-8")

    for rel, token, message in BOUNDARIES:
        if token not in text(rel):
            findings.append(f"{rel}: {message}")

    for path in authored_sources(root, overrides):
        rel = path.relative_to(root).as_posix()
        source = (
            overrides[rel]
            if rel in overrides
            else path.read_text(encoding="utf-8", errors="replace")
        )
        for match in re.finditer(r"""sandbox\s*=\s*["']([^"']*)["']""", source, re.I):
            capabilities = set(match.group(1).lower().split())
            if {"allow-scripts", "allow-same-origin"} <= capabilities:
                line = source[:match.start()].count("\n") + 1
                findings.append(
                    f"{rel}:{line}: sandbox combines scripts and same-origin, removing origin isolation"
                )
        for match in re.finditer(
            r"""localStorage\.setItem\(\s*["']([^"']*(?:nvapi|token|secret|authorization|credential)[^"']*)["']""",
            source,
            re.I,
        ):
            line = source[:match.start()].count("\n") + 1
            findings.append(
                f"{rel}:{line}: sensitive browser value {match.group(1)!r} must not enter persistent localStorage"
            )
        if rel == "web/_skill_explorer.js":
            for match in re.finditer(
                r"""\.href\s*=\s*(?:it\.href|x\.href|home|nav\.(?:up|map)\.href)\b""",
                source,
            ):
                line = source[:match.start()].count("\n") + 1
                findings.append(
                    f"{rel}:{line}: dynamic SKILL navigation bypasses canonical URL validation"
                )
    return findings


def self_test(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    baseline = audit(root)
    if baseline:
        failures.extend(f"baseline browser security boundary: {finding}" for finding in baseline)
        return failures

    cases = (
        ("opaque sandbox", "web/nemoclaw/scripts/_course_assistant.js",
         'sandbox="allow-scripts"', 'sandbox="allow-scripts allow-same-origin"',
         "removing origin isolation"),
        ("child source binding", "web/nemoclaw/scripts/_course_assistant.js",
         "event.source!==parent", "true",
         "child bridge"),
        ("preview CSP", "web/nemoclaw/scripts/_course_assistant.js",
         "connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'",
         "connect-src *; frame-src *; worker-src *; object-src *",
         "preview CSP"),
        ("Pyodide allowlist", "scripts/pyodide/examples/live-playground.js",
         "if (!RICH_TAGS.has(node.tagName))", "if (!true)",
         "allowlisted elements"),
        ("Studio URL validation", "web/nemoclaw/scripts/studio_main.js",
         "safeStudioUrl(attribute.value, name)", "attribute.value",
         "canonicalize every URL"),
        ("edX canonical host", "scripts/edx/edx_getting_started.html",
         "return allowed?'https://'+host+'/':false", "return u",
         "rebuilt from an allowlisted host"),
        ("SKILL navigation", "web/_skill_explorer.js",
         "safeNavigationHref(it.href)", "it.href",
         "bypasses canonical"),
        ("same-origin figure", "web/nemoclaw/scripts/_figures.js",
         "if (url.origin !== location.origin) return null", "",
         "same-origin"),
        ("HTML scanner", "scripts/runtime/engine.js",
         "function stripHtmlRawText", "function removedStripHtmlRawText",
         "raw-text scanner"),
        ("credential disclosure", "docs/security-design.md",
         "browser storage is not a vault", "browser storage protects secrets",
         "browser credential boundary"),
    )
    for label, rel, old, new, expected in cases:
        source = (root / rel).read_text(encoding="utf-8")
        if old not in source:
            failures.append(f"self-test fixture is stale: {label}")
            continue
        findings = audit(root, {rel: source.replace(old, new, 1)})
        if not any(expected in finding for finding in findings):
            failures.append(f"mutation was not detected: {label}")

    fixture = root / "web/nemoclaw/scripts/_course_assistant.js"
    source = fixture.read_text(encoding="utf-8")
    persistent = source + '\nlocalStorage.setItem("nvapi", apiKey);\n'
    if not any("persistent localStorage" in finding for finding in audit(
        root, {fixture.relative_to(root).as_posix(): persistent}
    )):
        failures.append("mutation was not detected: persistent browser credential")

    proposed = "web/proposed-browser-boundary.js"
    findings = audit(root, {
        proposed: '<iframe sandbox="allow-scripts allow-same-origin"></iframe>',
    })
    if not any(proposed in finding and "removing origin isolation" in finding for finding in findings):
        failures.append("mutation was not detected: newly proposed browser source")

    with tempfile.TemporaryDirectory(prefix="reacs-browser-discovery-") as temp:
        candidate_root = Path(temp)
        subprocess.run(
            ["git", "init", "-q", str(candidate_root)],
            capture_output=True,
            check=True,
        )
        (candidate_root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        proposed_path = candidate_root / "web/proposed.js"
        proposed_path.parent.mkdir(parents=True)
        proposed_path.write_text("export const proposed = true;\n", encoding="utf-8")
        installed_path = candidate_root / "scripts/tool/node_modules/publisher.js"
        installed_path.parent.mkdir(parents=True)
        installed_path.write_text("export const installed = true;\n", encoding="utf-8")
        discovered = {
            path.relative_to(candidate_root).as_posix()
            for path in authored_sources(candidate_root)
        }
        if "web/proposed.js" not in discovered:
            failures.append("repository discovery missed a non-ignored proposed browser source")
        if "scripts/tool/node_modules/publisher.js" in discovered:
            failures.append("repository discovery classified ignored installed dependencies as authored")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    findings = self_test() if args.self_test else audit()
    label = "browser_security_boundary_audit self-test" if args.self_test else "browser_security_boundary_audit"
    if findings:
        print(f"{label}: FAIL")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print(f"{label}: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
