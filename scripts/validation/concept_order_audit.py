#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Required first-use concept order checks for the agent curriculum.

This gate is intentionally narrow. It does not grade style and it does not create hover glossaries.
It protects the pages where reviewers flagged vocabulary arriving before the learner has a usable definition.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
COURSE = ROOT / "web" / "nemoclaw"
LESSON_MAP = COURSE / "lesson-map.json"
COURSE_CONTRACT = COURSE / "course_contract.json"
LESSON_RE = re.compile(r"^(?P<module>0[1-4])(?P<part>[a-c])-[a-z0-9-]+$")

CHECKS = [
    {
        "page": "01a-loop.html",
        "label": "tool introduced before action examples lean on it",
        "before": "code exposed to the model a <strong>tool</strong>",
        "after": "Calling a tool",
    },
    {
        "page": "01b-react.html",
        "label": "tool mechanics before ReAct tool-call discussion",
        "before": "A <strong>tool</strong> is code your harness can run for the model",
        "after": "offered a tool and asked",
    },
    {
        "page": "01c-tools.html",
        "label": "MCP acronym expanded before shorthand",
        "before": "Model Context Protocol (MCP)",
        "after": "Fetching tools from a separate server with MCP",
    },
    {
        "page": "01c-tools.html",
        "label": "MCP positioned as one serving interface",
        "required": "Use MCP when tool discovery and transport need a shared",
    },
    {
        "page": "01c-tools.html",
        "label": "required sub-agent and MCP boundary spine",
        "required": 'data-learning-spine="tool-boundaries"',
    },
    {
        "page": "01c-tools.html",
        "label": "tool contract connected to the scoped workflows that follow",
        "before": "Module 2 keeps this tool contract and changes the outer structure",
        "after": "Before you continue",
    },
    {
        "page": "02a-routing.html",
        "label": "workflow agent defined before pattern details",
        "before": "A <strong>workflow agent</strong> means an agent system",
        "after": "The model writes the full plan upfront",
    },
    {
        "page": "02a-routing.html",
        "label": "workflow scope named as the module control surface",
        "required": "The harness can scope a workflow around a model call",
    },
    {
        "page": "02a-routing.html",
        "label": "shared incident contrasts one loop with one workflow",
        "required": 'data-learning-spine="support-loop-workflow"',
    },
    {
        "page": "02a-routing.html",
        "label": "Promise.all explained before use as prerequisite",
        "before": "<code>Promise.all</code> is JavaScript's helper",
        "after": "Every query runs concurrently via <code>Promise.all</code>",
    },
    {
        "page": "02a-routing.html",
        "label": "fixed enum defined before router failure question",
        "before": "A <strong>fixed enum</strong>",
        "after": "The triage router has a fixed enum",
    },
    {
        "page": "02b-rag.html",
        "label": "index agent connected to scoped workflow before retrieval details",
        "before": "The Index Agent applies that workflow idea to outside knowledge",
        "after": "Naming the context bundle before you pick a store",
    },
    {
        "page": "02b-rag.html",
        "label": "fixed retrieval pipeline distinguished from its bounded context",
        "required": "It embeds and indexes a corpus ahead of time",
    },
    {
        "page": "02b-rag.html",
        "label": "generation to fixed RAG to agent-controlled retrieval ladder",
        "required": 'data-learning-spine="retrieval-ladder"',
    },
    {
        "page": "02c-deep.html",
        "label": "deep research pattern explained before formal roles",
        "before": "A <em>deep research agent</em> applies the same idea",
        "after": "The <strong>orchestrator</strong> turns the question",
    },
    {
        "page": "02c-deep.html",
        "label": "deep research connected to the module workflow through-line",
        "semantic": "workflow-scope",
        "after": "Index workflow.",
    },
    {
        "page": "02c-deep.html",
        "label": "planned outer workflow can compose an adaptive inner loop",
        "required": "Either workflow can place a ReAct loop inside a stage",
    },
    {
        "page": "02c-deep.html",
        "label": "research data flow taught before framework plumbing",
        "before": "How research moves through the workflow",
        "after": "1 · Connect the model",
    },
    {
        "page": "02c-deep.html",
        "label": "runnable research artifact appears before implementation details",
        "before": 'id="deep-cell"',
        "after": "Inspect the implementation",
    },
    {
        "page": "02c-deep.html",
        "label": "context isolation distinguished from operating-system containment",
        "required": "Fresh context is not a sandbox.",
    },
    {
        "page": "03a-kickstart.html",
        "label": "persistent runtime introduced from the browser-hosted workflows",
        "before": "In Modules 1 and 2, we kept orchestration in the browser",
        "after": "Start the launchable",
    },
    {
        "page": "03b-openclaw.html",
        "label": "file-backed agent context connected to the persistent runtime",
        "before": "Module 3a connected the browser to a persistent runtime",
        "after": "The workspace, from the agent's point of view",
    },
    {
        "page": "03c-always-on.html",
        "label": "autonomous triggers connected to the interactive agent",
        "before": "Module 3b ran the agent when you sent a message",
        "after": "How triggers choose context and instructions",
    },
    {
        "page": "04a-safety.html",
        "label": "product roles separated before enforcement layers",
        "before": "Keep the three product roles separate as you trace enforcement.",
        "after": "Where each defense layer intervenes",
    },
    {
        "page": "04a-safety.html",
        "label": "sandbox authority motivated by persistent autonomous behavior",
        "semantic": "persistent-authority",
        "after": "Keep the three product roles separate as you trace enforcement.",
    },
    {
        "page": "04a-safety.html",
        "label": "network namespace defined before reference glossary",
        "before": "A <strong>network namespace</strong> (<code>netns</code>)",
        "after": "<dt>Network namespace / <code>netns</code></dt>",
    },
    {
        "page": "04a-safety.html",
        "label": "CONNECT proxy defined before reference glossary",
        "before": "HTTP <strong>CONNECT proxy</strong> provides the only route out",
        "after": "<dt>CONNECT proxy</dt>",
    },
    {
        "page": "04a-safety.html",
        "label": "OPA acronym expanded before shorthand",
        "before": "Open Policy Agent (OPA)",
        "after": "<dt>OPA</dt>",
    },
    {
        "page": "04a-safety.html",
        "label": "Landlock explained before reference glossary",
        "before": "is a Linux Security Module that restricts future filesystem access",
        "after": "<dt>Landlock</dt>",
    },
    {
        "page": "04a-safety.html",
        "label": "seccomp and BPF explained before reference glossary",
        "before": "is Linux syscall filtering; its BPF filter",
        "after": "<dt>seccomp</dt>",
    },
    {
        "page": "04a-safety.html",
        "label": "EPERM translated before reference glossary",
        "before": "<code>EPERM</code>, meaning \"operation not permitted,\"",
        "after": "<dt><code>EPERM</code> / <code>EACCES</code></dt>",
    },
    {
        "page": "04a-safety.html",
        "label": "mechanisms framed as testable learner questions",
        "required": "How the sandbox mechanisms answer testable questions",
    },
    {
        "page": "04b-modern-clis.html",
        "label": "CLI comparison connected to application and OS enforcement layers",
        "before": "Module 4a separated application decisions from operating-system enforcement",
        "after": "Shared loop, different application defaults",
    },
    {
        "page": "04b-modern-clis.html",
        "label": "browser agent connected to the transferable interface lesson",
        "before": "Module 4c returns to this browser form factor",
        "after": "a CLI agent bound to the browser runtime",
    },
    {
        "page": "04c-going-further.html",
        "label": "portable web surface separated from host-specific authority",
        "before": "The browser artifact is a transferable agent surface",
        "after": "Transfer the interface contract, then adapt the environment.",
    },
    {
        "page": "04c-going-further.html",
        "label": "reference taxonomy matches the current four-module course",
        "required": "Module 4 · Evaluation and containment",
    },
]

BAD_TOKENS = {
    "02a-routing.html": [
        "service-level agreement failure",
        "might never sees",
    ],
    "01c-tools.html": [
        "the production standard for serving tools",
    ],
    "02c-deep.html": [
        "sub-agent</em> which inherit",
        "The four pieces a deep agent is built from",
        "Pointing LangChain at whichever endpoint is active",
        "This runs the full deep pattern from Part 5.",
    ],
    "04a-safety.html": [
        "sandbox guardrailing",
        "Filesystem capability dropping at the kernel, through",
    ],
}


def read(page: str) -> str:
    return (COURSE / page).read_text(encoding="utf-8")


def norm(raw: str) -> str:
    return re.sub(r"\s+", " ", raw)


def _lesson_pages(discovered_pages: set[str] | None = None) -> set[str]:
    if discovered_pages is not None:
        return set(discovered_pages)
    pages = set()
    for path in COURSE.rglob("*.html"):
        raw = path.read_text(encoding="utf-8")
        # A lesson remains discoverable when renamed or nested; a broken conventional
        # lesson still enters reconciliation even when its navigation was removed.
        if ('id="journey-map"' in raw or re.match(r"^\d+[a-z]-", path.name)):
            pages.add(path.relative_to(COURSE).with_suffix("").as_posix())
    return pages


def _profile_findings(
    profile_override: dict[str, object] | None = None,
    discovered_pages: set[str] | None = None,
    page_overrides: dict[str, str] | None = None,
) -> list[str]:
    findings: list[str] = []
    try:
        profile = profile_override if profile_override is not None else json.loads(
            LESSON_MAP.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        return [f"lesson-map.json: cannot read valid JSON: {exc}"]
    if not isinstance(profile, dict) or profile.get("schema") != "nemoclaw-lesson-map/1":
        return ["lesson-map.json: schema must be nemoclaw-lesson-map/1"]
    forbidden = {"profiles", "source_root", "content_root", "copied_tree", "lesson_tree"}
    if forbidden.intersection(profile):
        findings.append("lesson-map.json: mode profiles and copied lesson trees are retired")

    lessons = profile.get("lessons")
    if not isinstance(lessons, list):
        return findings + ["lesson-map.json: lessons must be a list"]
    try:
        objective_count = len(json.loads(COURSE_CONTRACT.read_text(encoding="utf-8"))["learning_objectives"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return findings + [f"course_contract.json: cannot discover objective ids: {exc}"]
    allowed_objectives = {f"learning-objective-{index}" for index in range(1, objective_count + 1)}
    expected_pages = _lesson_pages(discovered_pages)
    seen: set[str] = set()
    mapped: set[str] = set()
    roles: set[tuple[int, int]] = set()
    page_overrides = page_overrides or {}
    for index, lesson in enumerate(lessons):
        prefix = f"lesson-map.json: lesson {index + 1}"
        if not isinstance(lesson, dict):
            findings.append(f"{prefix} must be an object")
            continue
        lesson_id = lesson.get("id")
        if not isinstance(lesson_id, str):
            findings.append(f"{prefix} id must be a string")
            continue
        if lesson_id in seen:
            findings.append(f"lesson-map.json: duplicate lesson id {lesson_id}")
        seen.add(lesson_id)
        mapped.add(lesson_id)
        if not re.fullmatch(r"[a-z0-9-]+(?:/[a-z0-9-]+)*", lesson_id):
            findings.append(f"{prefix} has malformed id {lesson_id}")
        role = (lesson.get("module"), lesson.get("lesson"))
        if any(type(number) is not int or number < 1 for number in role):
            findings.append(f"{prefix} needs positive module/lesson metadata")
        elif role in roles:
            findings.append(f"{prefix} has duplicate module/lesson role {role}")
        else:
            roles.add(role)
        match = LESSON_RE.fullmatch(lesson_id)
        if match and role != (int(match.group("module")), ord(match.group("part")) - ord("a") + 1):
            findings.append(f"{prefix} module/lesson does not match {lesson_id}")
        if lesson.get("objective") not in allowed_objectives:
            findings.append(f"{prefix} maps unknown objective {lesson.get('objective')!r}")
        retired = {
            "action",
            "evidence",
            "evidence_target",
            "interaction",
            "recap",
            "transition",
        }.intersection(lesson)
        if retired:
            findings.append(
                f"{prefix} contains retired synthetic-checkpoint fields: {', '.join(sorted(retired))}"
            )
    for page in sorted(expected_pages - mapped):
        findings.append(f"lesson-map.json: discovered lesson {page}.html is not mapped")
    for page in sorted(mapped - expected_pages):
        findings.append(f"lesson-map.json: mapped lesson {page}.html does not exist")
    return findings


class VisibleBlocks(HTMLParser):
    """Keep concept evidence in visible prose, excluding hidden code and comments."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.parts = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        hidden = any(value for _, value in self.hidden) or tag in {"script", "style", "template", "pre"} or "hidden" in attributes or attributes.get("aria-hidden") == "true"
        if tag not in {"br", "img", "input", "meta", "link", "hr"}:
            self.hidden.append((tag, hidden))
        if tag in {"p", "li", "h1", "h2", "h3", "div"}:
            self.flush()

    def handle_endtag(self, tag):
        if tag in {"p", "li", "h1", "h2", "h3", "div"}:
            self.flush()
        for index in range(len(self.hidden) - 1, -1, -1):
            if self.hidden[index][0] == tag:
                del self.hidden[index:]
                break

    def handle_data(self, text):
        if not any(hidden for _, hidden in self.hidden):
            self.parts.append(text)

    def flush(self):
        text = norm("".join(self.parts)).strip()
        if text:
            self.blocks.append(text)
        self.parts.clear()


def semantic_order(raw: str, kind: str, after: str) -> bool:
    parser = VisibleBlocks()
    parser.feed(raw)
    parser.flush()
    uses = [i for i, block in enumerate(parser.blocks) if after.lower() in block.lower()]
    if not uses:
        return False
    for index, block in enumerate(parser.blocks):
        if index >= uses[0]:
            break
        text = block.lower()
        if re.search(r"\b(?:not|never|no)\b", text):
            continue
        if kind == "workflow-scope":
            match = re.search(r"(?:outer workflow|workflow boundary).{0,60}(?:owns|controls|defines|governs).{0,40}scope.{0,30}data flow", text)
        else:
            match = (re.search(r"(?:module 3|previous module)", text)
                     and re.search(r"files?.{0,35}(?:persistent )?context", text)
                     and re.search(r"(?:scheduled|unattended).{0,35}(?:jobs|work|operations)", text)
                     and re.search(r"(?:depend|rely).{0,55}authority", text))
        if match:
            return True
    return False


def _role_pages(profile: dict[str, object]) -> dict[str, str]:
    roles = {}
    for lesson in profile.get("lessons", []):
        if not isinstance(lesson, dict):
            continue
        module, part = lesson.get("module"), lesson.get("lesson")
        if type(module) is int and type(part) is int and 1 <= part <= 26 and isinstance(lesson.get("id"), str):
            roles[f"{module:02}{chr(96 + part)}"] = lesson["id"] + ".html"
    return roles


def audit(
    overrides: dict[str, str] | None = None,
    profile_override: dict[str, object] | None = None,
    discovered_pages: set[str] | None = None,
) -> list[str]:
    """Check order using optional in-memory page mutations for contract tests."""
    findings: list[str] = []
    cache: dict[str, str] = {}
    overrides = overrides or {}
    profile = profile_override if profile_override is not None else json.loads(LESSON_MAP.read_text(encoding="utf-8"))
    roles = _role_pages(profile)
    def source(page):
        if page not in cache:
            try:
                cache[page] = overrides[page] if page in overrides else read(page)
            except OSError:
                findings.append(f"{page}: required concept source is missing or unreadable")
                cache[page] = ""
        return cache[page]
    for check in CHECKS:
        page = roles.get(check["page"][:3], check["page"])
        raw = source(page)
        text = norm(raw)
        label = check["label"]
        if "semantic" in check:
            if not semantic_order(raw, check["semantic"], check["after"]):
                findings.append(f"{page}: missing or misplaced visible concept bridge: {label}")
            continue
        if "required" in check:
            if check["required"] not in text:
                findings.append(f"{page}: missing required concept framing: {label}")
            continue
        before = check["before"]
        after = check["after"]
        b = text.find(before)
        a = text.find(after)
        if b < 0:
            findings.append(f"{page}: missing concept definition token for {label}: {before}")
        if a < 0:
            findings.append(f"{page}: missing downstream use token for {label}: {after}")
        if b >= 0 and a >= 0 and b > a:
            findings.append(f"{page}: concept appears after first use: {label}")
    for page, tokens in BAD_TOKENS.items():
        page = roles.get(page[:3], page)
        text = source(page)
        for token in tokens:
            if token in text:
                findings.append(f"{page}: stale confusing wording remains: {token}")
    findings.extend(_profile_findings(profile_override, discovered_pages, overrides))
    return findings


run = audit


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate first-use definitions across the agent curriculum.")
    ap.add_argument("--json", action="store_true", help="print machine-readable findings")
    args = ap.parse_args()
    findings = audit()
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, indent=2))
    elif findings:
        for finding in findings:
            print(f"[concept-order] {finding}")
    else:
        print("concept_order_audit: OK")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
