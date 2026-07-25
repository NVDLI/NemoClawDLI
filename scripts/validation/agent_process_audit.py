#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit repo-level agent process guardrails."""
from __future__ import annotations

import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root
import agent_model_experiment_audit
import codex_continuity_audit

ROOT = find_repo_root(Path(__file__).resolve())
FILES = {
    "process_doc": ROOT / "docs" / "agent_process.md",
    "agents": ROOT / "AGENTS.md",
    "root_skill": ROOT / "SKILL.html",
    "assets_skill": ROOT / "web" / "nemoclaw" / "assets" / "SKILL.html",
    "docs_skill": ROOT / "docs" / "SKILL.html",
    "validation_skill": ROOT / "scripts" / "validation" / "SKILL.html",
    "figures_skill": ROOT / "scripts" / "figures" / "SKILL.html",
    "pre_push": ROOT / "scripts" / "git-hooks" / "pre-push",
}

REQUIRED = {
    "process_doc": [
        "Addresses #N",
        "Closes #N",
        "Remaining issue work",
        "NemoClaw is the reference stack",
        "OpenClaw is the agent harness",
        "OpenShell is the sandbox boundary",
        "Brev launchable is the hosted course deployment",
        "Do not print token-bearing environment variables",
        "git credential fill",
        "BUILD_PAGES_LANGS=0 scripts/build/build_pages.sh",
        "`apply_patch` is unavailable",
        "Visual changes",
        "test the whole lifecycle",
        "both source and built Pages output",
        "computed visibility and persisted-state behavior",
        "Only paths present in the current classic-Pages artifact",
        "learner_flow_audit.py",
        "disclosure, prerequisite readiness, Run/Stop/Reset, error recovery, and viewport stability",
        "Contribution authority",
        "Treat every patch as untrusted input",
        "A hook must refuse and explain",
        "Use standalone validators while editing",
        "--changed-since origin/main",
    ],
    "agents": ["docs/agent_process.md", "docs/lab_runtime_testing.md", "docs/pages_deploy.md",
               "docs/release-test-plan.md", "web/nemoclaw/assets/SKILL.html",
               "scripts/validation/SKILL.html", "Do not flatten a diagram",
               "Treat code contribution as an untrusted proposal"],
    "root_skill": ["asset provenance beacon", "inspect light and dark theme output", "source_gate"],
    "assets_skill": ["theme/mount classification", "Semantic labels stay in diagrams", "visual_preview_policy",
                     "light and dark theme screenshots", "activate the lightbox", "horizontal panning"],
    "docs_skill": ["agent_process.md", "agent process", "agent_model_experiment.md",
                   "agent_model_experiment_protocol.json", "agent_model_experiment_prompts.json"],
    "validation_skill": ["agent_process_audit.py", "Agent process",
                         "agent_model_experiment_audit.py", "codex_continuity_audit.py",
                         "cell_ui_runtime_audit.py", "Rendered page screenshots",
                         "learner_flow_audit.py", "learner_flow_runtime_audit.py",
                         "contribution_safety_audit.py", "Contribution safety"],
    "figures_skill": ["rendered-preview", "harness screenshot"],
    "pre_push": ["release_gate.py", "--tier ship --no-write --changed-since origin/main --reuse-success", "contribution_safety_audit.py", "--commit-range \"$RANGE\"", "release_change_reminder.py", "REFUSING PUSH - origin/main is"],
}

FORBIDDEN_DOC_PATTERNS = (
    "env | rg TOKEN",
    "printenv | grep TOKEN",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def audit() -> list[str]:
    findings: list[str] = []
    for key, tokens in REQUIRED.items():
        path = FILES[key]
        if not path.is_file():
            findings.append(f"missing {path.relative_to(ROOT)}")
            continue
        raw = read(path)
        for token in tokens:
            if token not in raw:
                findings.append(f"{path.relative_to(ROOT)} missing {token}")
    raw_doc = read(FILES["process_doc"]) if FILES["process_doc"].is_file() else ""
    for token in FORBIDDEN_DOC_PATTERNS:
        if token in raw_doc:
            line = next((ln for ln in raw_doc.splitlines() if token in ln), "")
            if "Never run" not in line and "Do not" not in line:
                findings.append(f"docs/agent_process.md gives unsafe auth probe without banning it: {token}")
    findings.extend(codex_continuity_audit.audit(ROOT))
    findings.extend(agent_model_experiment_audit.audit(ROOT))
    return findings


def main() -> int:
    findings = audit()
    if findings:
        for item in findings:
            print(item)
        return 1
    print("agent process audit: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
