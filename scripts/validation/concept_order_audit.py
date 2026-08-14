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
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
COURSE = ROOT / "web" / "nemoclaw"
LEARNING_PROFILE = COURSE / "learning-profile.json"
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
        "before": "Module 2 treats workflow scope as a control surface",
        "after": "How the workflow boundary changes",
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
        "after": "The two endpoints you work with from here",
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
        "before": "Module 3 gave OpenClaw persistent context and unattended triggers",
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
    return {path.stem for path in COURSE.glob("0[1-4][a-c]-*.html")}


def _profile_findings(
    profile_override: dict[str, object] | None = None,
    discovered_pages: set[str] | None = None,
    page_overrides: dict[str, str] | None = None,
) -> list[str]:
    findings: list[str] = []
    try:
        profile = profile_override if profile_override is not None else json.loads(
            LEARNING_PROFILE.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        return [f"learning-profile.json: cannot read valid JSON: {exc}"]
    if not isinstance(profile, dict) or profile.get("schema") != "nemoclaw-learning-profile/1":
        return ["learning-profile.json: schema must be nemoclaw-learning-profile/1"]
    profiles = profile.get("profiles")
    if not isinstance(profiles, dict):
        findings.append("learning-profile.json: profiles must be an object")
    else:
        guided = profiles.get("guided")
        if (
            set(profiles) != {"guided"}
            or not isinstance(guided, dict)
            or guided.get("query") != ""
            or guided.get("detail") != "guided"
            or guided.get("default") is not True
        ):
            findings.append("learning-profile.json: Guided must be the only default profile and use canonical lesson URLs")
        forbidden = {"source_root", "content_root", "copied_tree", "lesson_tree"}
        if isinstance(guided, dict) and forbidden.intersection(guided):
            findings.append("learning-profile.json: Guided must not define a copied lesson tree")

    lessons = profile.get("lessons")
    if not isinstance(lessons, list):
        return findings + ["learning-profile.json: lessons must be a list"]
    try:
        objective_count = len(json.loads(COURSE_CONTRACT.read_text(encoding="utf-8"))["learning_objectives"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return findings + [f"course_contract.json: cannot discover objective ids: {exc}"]
    allowed_objectives = {f"learning-objective-{index}" for index in range(1, objective_count + 1)}
    expected_pages = _lesson_pages(discovered_pages)
    seen: set[str] = set()
    mapped: set[str] = set()
    page_overrides = page_overrides or {}
    for index, lesson in enumerate(lessons):
        prefix = f"learning-profile.json: lesson {index + 1}"
        if not isinstance(lesson, dict):
            findings.append(f"{prefix} must be an object")
            continue
        lesson_id = lesson.get("id")
        if not isinstance(lesson_id, str):
            findings.append(f"{prefix} id must be a string")
            continue
        if lesson_id in seen:
            findings.append(f"learning-profile.json: duplicate lesson id {lesson_id}")
        seen.add(lesson_id)
        mapped.add(lesson_id)
        match = LESSON_RE.fullmatch(lesson_id)
        if not match:
            findings.append(f"{prefix} has malformed id {lesson_id}")
        else:
            expected_module = int(match.group("module"))
            expected_lesson = ord(match.group("part")) - ord("a") + 1
            if lesson.get("module") != expected_module or lesson.get("lesson") != expected_lesson:
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
        findings.append(f"learning-profile.json: discovered lesson {page}.html is not mapped")
    for page in sorted(mapped - expected_pages):
        findings.append(f"learning-profile.json: mapped lesson {page}.html does not exist")
    return findings


def audit(
    overrides: dict[str, str] | None = None,
    profile_override: dict[str, object] | None = None,
    discovered_pages: set[str] | None = None,
) -> list[str]:
    """Check order using optional in-memory page mutations for contract tests."""
    findings: list[str] = []
    cache: dict[str, str] = {}
    overrides = overrides or {}
    for check in CHECKS:
        page = check["page"]
        raw = cache.setdefault(page, overrides.get(page, read(page)))
        text = norm(raw)
        label = check["label"]
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
        text = cache.setdefault(page, overrides.get(page, read(page)))
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
