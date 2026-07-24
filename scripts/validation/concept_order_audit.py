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
        "before": "Try it · plan → investigate → synthesize",
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
        "before": "Modules 1 and 2 kept orchestration in the browser",
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


def audit() -> list[str]:
    findings: list[str] = []
    cache: dict[str, str] = {}
    for check in CHECKS:
        page = check["page"]
        raw = cache.setdefault(page, read(page))
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
        text = cache.setdefault(page, read(page))
        for token in tokens:
            if token in text:
                findings.append(f"{page}: stale confusing wording remains: {token}")
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
