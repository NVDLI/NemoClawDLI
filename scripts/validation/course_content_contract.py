#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Course-specific content contracts that should not drift silently.

These are narrow regression guards for course promises that generic link, figure,
and prose validators cannot infer from first principles.
"""
from __future__ import annotations

import json
import re
import sys
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
COURSE = ROOT / "web" / "nemoclaw"
ASSETS = COURSE / "assets"
AUTHORED_TEXT_SUFFIXES = {".css", ".html", ".js", ".json", ".md", ".mjs", ".py"}
OBSOLETE_RUNTIME_RE = re.compile(
    r"\blab proxy\b|\bllm[_]client\b|(?:localhost|127\.0\.0\.1):9000|(?<!\d):9000\b",
    re.I,
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _has_all(text: str, tokens: tuple[str, ...]) -> bool:
    normalized = re.sub(r"\s+", " ", text).lower()
    return all(re.sub(r"\s+", " ", token).lower() in normalized for token in tokens)


def _json_script(text: str, script_id: str) -> dict:
    m = re.search(r'<script[^>]+id=["\']' + re.escape(script_id) + r'["\'][^>]*>(.*?)</script>', text, re.S)
    return json.loads(m.group(1)) if m else {}


def _literal_remote_image_uses() -> dict[str, list[str]]:
    """Discover literal remote image mounts across every course-language page."""
    roots = [COURSE]
    roots.extend(sorted(ROOT.glob("i18n/*/web/nemoclaw")))
    uses: dict[str, list[str]] = {}
    pattern = re.compile(r'<img\b[^>]*\bsrc=["\'](https://[^"\']+)["\']', re.I)
    for course_root in roots:
        if not course_root.is_dir():
            continue
        for page in sorted(course_root.glob("*.html")):
            relative = page.relative_to(ROOT).as_posix()
            for image_url in pattern.findall(page.read_text(encoding="utf-8", errors="replace")):
                uses.setdefault(unescape(image_url), []).append(relative)
    return uses


def _remote_image_filename(image_url: str) -> str:
    """Resolve a useful source filename, including image-resizing proxy URLs."""
    parsed = urlparse(image_url)
    nested = parse_qs(parsed.query).get("url", [])
    source = nested[0] if nested else image_url
    return Path(urlparse(source).path).name


def obsolete_runtime_references() -> list[str]:
    """Find retired course-runtime names in every authored course or material file."""
    roots = [COURSE, ROOT / "scripts" / "materials"]
    roots.extend(sorted(ROOT.glob("i18n/*/web/nemoclaw")))
    findings: list[str] = []
    visited: set[Path] = set()
    for source_root in roots:
        if not source_root.is_dir():
            continue
        for path in source_root.rglob("*"):
            if (
                path in visited
                or not path.is_file()
                or path.suffix.lower() not in AUTHORED_TEXT_SUFFIXES
                or "vendor" in path.parts
            ):
                continue
            visited.add(path)
            if OBSOLETE_RUNTIME_RE.search(path.read_text(encoding="utf-8", errors="replace")):
                findings.append(path.relative_to(ROOT).as_posix())
    return sorted(findings)


def run(verbose: bool = True) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    p02b = _read("web/nemoclaw/02b-rag.html")
    p01c = _read("web/nemoclaw/01c-tools.html")
    p03c = _read("web/nemoclaw/03c-always-on.html")
    p04a = _read("web/nemoclaw/04a-safety.html")
    p04b = _read("web/nemoclaw/04b-modern-clis.html")
    p04c = _read("web/nemoclaw/04c-going-further.html")
    mat_stack = _read("web/nemoclaw/mats/nvidia_openshell_nemoclaw.md")
    mat_safety = _read("web/nemoclaw/mats/agentic_safety_in_production.md")
    svg02b = _read("web/nemoclaw/assets/figures/02b-retrieval-boundaries.svg")
    svg04a = _read("web/nemoclaw/assets/figures/lethal-trifecta.svg")
    askill = _read("web/nemoclaw/assets/SKILL.html")

    if "assets/figures/02b-retrieval-boundaries.svg" not in p02b:
        findings.append(("web/nemoclaw/02b-rag.html", "missing retrieval boundary figure"))
    if not _has_all(p01c, ("Discovery is a trust boundary", "smallest useful scope", "audience-bound", "SSRF")):
        findings.append(("web/nemoclaw/01c-tools.html", "MCP lesson must distinguish tool discovery from consent, scoped credentials, and SSRF-safe connection handling"))
    if not _has_all(p02b, ("MCP", "A2A", "skills", "runtime", "generated UX")):
        findings.append(("web/nemoclaw/02b-rag.html", "retrieval boundary section must define MCP/A2A/skills/runtime/UX roles"))
    if re.search(r"Zenodia|@zcharpy|issue #\d+|issue-title|GitLab issue", p02b, re.I):
        findings.append(("web/nemoclaw/02b-rag.html", "learner-facing retrieval prose must not leak contributor or issue-thread shorthand"))
    if "Provenance" not in svg02b:
        findings.append(("web/nemoclaw/assets/figures/02b-retrieval-boundaries.svg", "retrieval boundary SVG lost provenance"))
    if "Retrieval is one boundary in a larger system" in svg02b:
        findings.append(("web/nemoclaw/assets/figures/02b-retrieval-boundaries.svg", "retrieval boundary SVG must not embed caption prose; keep captions in HTML figcaption"))

    if not _has_all(p03c, ("course configuration", "main, isolated, current, or a named session", "docs.openclaw.ai/cron-vs-heartbeat", "default: deny")):
        findings.append(("web/nemoclaw/03c-always-on.html", "automation lesson must scope session behavior to the course configuration and cite current OpenClaw/Hermes controls"))
    for stale in ("fresh per fire (isolation)", "each run gets a fresh session", "fresh-session-per-fire knob"):
        if stale in p03c:
            findings.append(("web/nemoclaw/03c-always-on.html", f"automation lesson must not present isolated cron as universal behavior: {stale}"))
    if not _has_all(p04b, ("raw.githubusercontent.com/openclaw/openclaw/main/README.md", "raw.githubusercontent.com/NousResearch/hermes-agent/main/README.md")):
        findings.append(("web/nemoclaw/04b-modern-clis.html", "CLI comparison must ground OpenClaw and Hermes descriptions in their current public repositories"))
    if not _has_all(p04c, ("4 vCPU", "GPU is optional", "requirements and interfaces evolve", "docs.nvidia.com/nemoclaw/latest/get-started/prerequisites")):
        findings.append(("web/nemoclaw/04c-going-further.html", "deployment guidance must distinguish the general CPU baseline from optional GPU paths and direct learners to version-sensitive requirements"))
    if not _has_all(p04c, ("14729249-use-live-artifacts-in-claude-cowork", "12515353-build-with-the-apps-sdk", "Transfer the interface contract, then adapt the environment", "cross-origin access")):
        findings.append(("web/nemoclaw/04c-going-further.html", "transferability guidance must ground current web-artifact examples and distinguish portable interface code from host-specific authority"))
    if not _has_all(mat_stack, ("alpha", "early preview", "Linux", "macOS", "WSL2", "DGX Spark", "hosted or local inference")):
        findings.append(("web/nemoclaw/mats/nvidia_openshell_nemoclaw.md", "stack essay must preserve current availability, platform, and inference qualifiers"))
    if "NemoClaw targets NVIDIA DGX Spark" in mat_stack:
        findings.append(("web/nemoclaw/mats/nvidia_openshell_nemoclaw.md", "DGX Spark playbook must not be presented as the NemoClaw product boundary"))
    if not _has_all(mat_safety, ("reference stack", "alpha", "early-preview", "version being deployed")):
        findings.append(("web/nemoclaw/mats/agentic_safety_in_production.md", "safety essay must preserve the version-sensitive alpha qualifier"))

    if "assets/figures/lethal-trifecta.svg" not in p04a:
        findings.append(("web/nemoclaw/04a-safety.html", "missing real lethal trifecta figure"))
    if not _has_all(p04a, ("Untrusted input", "private data", "external communication", "full-duplex")):
        findings.append(("web/nemoclaw/04a-safety.html", "lethal trifecta prose must define all three terms and the full-duplex risk"))
    if "How the sandbox mechanisms answer testable questions" not in p04a or not _has_all(p04a, ("compatibility mode", "OverlayFS", "handles opened before restriction")):
        findings.append(("web/nemoclaw/04a-safety.html", "filesystem lesson must qualify Landlock guarantees with compatibility, OverlayFS, and pre-opened-handle limits"))
    if not _has_all(p04a, ("does not prove escalation is impossible",)):
        findings.append(("web/nemoclaw/04a-safety.html", "non-root lesson must describe reduced blast radius without promising impossible escalation"))
    if not _has_all(p04a, ("Choose the control by failure mode", "Goal hijack or prompt injection", "Tool misuse", "Identity or privilege abuse", "Supply-chain or unexpected code execution", "Memory or context poisoning")):
        findings.append(("web/nemoclaw/04a-safety.html", "sandbox limits section must map major agentic failure modes to the layer that can enforce each control"))
    fig_idx = p04a.find("assets/figures/lethal-trifecta.svg")
    fig_tail = p04a[fig_idx:fig_idx + 1200] if fig_idx >= 0 else ""
    if "Prompt rules and application guardrails shape the agent before kernel containment" in fig_tail:
        findings.append(("web/nemoclaw/04a-safety.html", "lethal trifecta caption regressed to the old sandbox-boundary caption"))
    if not _has_all(fig_tail + p04a, ("network allowlist", "allowed connection", "private data", "untrusted input")):
        findings.append(("web/nemoclaw/04a-safety.html", "lethal trifecta caption/prose must explain why an allowlist alone is insufficient"))
    if not _has_all(svg04a, ("Lethal Trifecta", "Access to Secrets", "Protected Private Data", "Untrusted Input", "A Way Out", "Permitted Egress Path")):
        findings.append(("web/nemoclaw/assets/figures/lethal-trifecta.svg", "real lethal trifecta SVG lost its core labels"))
    if "Simon Willison" not in p04a or "simonwillison.net/2025/Jun/16/the-lethal-trifecta" not in p04a:
        findings.append(("web/nemoclaw/04a-safety.html", "lethal trifecta section must keep canonical Simon Willison reference"))

    process_ref = re.compile(r"Zenodia|@zcharpy|GitLab issue|issue #\d+|MR !?\d+|PR #?\d+", re.I)
    for rel, text in (
        ("web/nemoclaw/assets/SKILL.html", askill),
        ("web/nemoclaw/assets/figures/02b-retrieval-boundaries.svg", svg02b),
        ("web/nemoclaw/assets/figures/lethal-trifecta.svg", svg04a),
    ):
        if process_ref.search(text):
            findings.append((rel, "course assets must not expose issue-thread, MR/PR, or user-handle provenance"))
    if not _has_all(askill, ("02b-retrieval-boundaries.svg", "course-provided boundary map", "lethal-trifecta.svg", "Simon Willison")):
        findings.append(("web/nemoclaw/assets/SKILL.html", "asset provenance must document retrieval-boundary and lethal-trifecta figure sources"))

    provenance = _json_script(askill, "provenance")
    for row in provenance.get("figures", []):
        file_name = row.get("file", "")
        image_url = row.get("image_url", "")
        used_by = row.get("used_by", "")
        if bool(file_name) == bool(image_url):
            findings.append((
                "web/nemoclaw/assets/SKILL.html",
                "each image-provenance row must declare exactly one of file or image_url",
            ))
            continue
        if image_url:
            if not (
                str(image_url).startswith("https://")
                and str(row.get("source_url", "")).startswith("https://")
                and str(row.get("license_url", "")).startswith("https://")
                and row.get("license")
                and row.get("source")
                and row.get("source_authors")
                and row.get("connection") == "remote display"
                and row.get("distribution") == "not copied into this repository"
            ):
                findings.append((
                    "web/nemoclaw/assets/SKILL.html",
                    f"remote image lacks source, author, terms, or non-distribution evidence: {image_url}",
                ))
            if not used_by.endswith(".html"):
                findings.append((
                    "web/nemoclaw/assets/SKILL.html",
                    f"remote image lacks a canonical used_by page: {image_url}",
                ))
            else:
                try:
                    page = _read(f"web/nemoclaw/{used_by}")
                except FileNotFoundError:
                    findings.append((
                        "web/nemoclaw/assets/SKILL.html",
                        f"remote image used_by page is missing: {used_by}",
                    ))
                else:
                    if str(image_url) not in unescape(page):
                        findings.append((
                            "web/nemoclaw/assets/SKILL.html",
                            f"remote image provenance is stale: {image_url} is not referenced by {used_by}",
                        ))
            source_name = _remote_image_filename(str(image_url))
            if source_name:
                copied = sorted(
                    path.relative_to(ROOT).as_posix()
                    for path in ROOT.rglob(source_name)
                    if ".git" not in path.parts
                )
                if copied:
                    findings.append((
                        "web/nemoclaw/assets/SKILL.html",
                        f"remote image marked not copied is present in the repository: {', '.join(copied)}",
                    ))
            continue
        if not str(file_name).startswith("figures/") or not used_by.endswith(".html"):
            continue
        page_rel = f"web/nemoclaw/{used_by}"
        try:
            page = _read(page_rel)
        except FileNotFoundError:
            findings.append(("web/nemoclaw/assets/SKILL.html", f"asset provenance used_by page missing for {file_name}: {used_by}"))
            continue
        if file_name not in page:
            findings.append(("web/nemoclaw/assets/SKILL.html", f"asset provenance row is stale: {file_name} is not referenced by {used_by}"))

    remote_rows = {
        str(row.get("image_url")): row
        for row in provenance.get("figures", [])
        if row.get("image_url")
    }
    remote_uses = _literal_remote_image_uses()
    for image_url, pages in sorted(remote_uses.items()):
        if image_url not in remote_rows:
            findings.append((
                "web/nemoclaw/assets/SKILL.html",
                f"remote image lacks provenance: {image_url} used by {', '.join(pages)}",
            ))
            continue
        source_url = str(remote_rows[image_url].get("source_url", ""))
        for page_rel in pages:
            page = _read(page_rel)
            figure_match = re.search(
                r"<figure\b[^>]*>.*?<img\b[^>]*\bsrc=[\"']"
                + re.escape(image_url)
                + r"[\"'][^>]*>.*?</figure>",
                unescape(page),
                re.I | re.S,
            )
            if not figure_match:
                findings.append((
                    page_rel,
                    f"remote image must be presented inside a sourced figure: {image_url}",
                ))
                continue
            figure = figure_match.group(0)
            image_tag = re.search(
                r"<img\b[^>]*\bsrc=[\"']" + re.escape(image_url) + r"[\"'][^>]*>",
                figure,
                re.I,
            ).group(0)
            required_image_attributes = (
                r'\balt=["\'][^"\']+["\']',
                r'\bloading=["\']lazy["\']',
                r'\bdecoding=["\']async["\']',
                r'\breferrerpolicy=["\']no-referrer["\']',
            )
            if any(not re.search(pattern, image_tag, re.I) for pattern in required_image_attributes):
                findings.append((
                    page_rel,
                    f"remote image must carry alt, lazy loading, async decoding, and no-referrer attributes: {image_url}",
                ))
            if "<figcaption" not in figure.lower() or figure.count(source_url) < 2:
                findings.append((
                    page_rel,
                    "remote figure media and caption must both link to its recorded source",
                ))
    for image_url in sorted(set(remote_rows) - set(remote_uses)):
        findings.append((
            "web/nemoclaw/assets/SKILL.html",
            f"remote image provenance is unused across course-language pages: {image_url}",
        ))

    for path in obsolete_runtime_references():
        findings.append((
            path,
            "retired lab-proxy runtime vocabulary returned; describe the active configurable route instead",
        ))

    if verbose:
        if findings:
            print("course_content_contract: FAIL")
            for path, detail in findings:
                print(f"  - {path}: {detail}")
        else:
            print("course_content_contract: OK")
    return findings


if __name__ == "__main__":
    raise SystemExit(1 if run() else 0)
