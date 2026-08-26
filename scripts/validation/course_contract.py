#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Required invariant for the English NemoClaw course title, abstract, and objectives."""
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
CONTRACT_PATH = ROOT / "web" / "nemoclaw" / "course_contract.json"
CANON_PATH = ROOT / "web" / "nemoclaw" / "COURSE_CANON.md"
COURSE_HOME = ROOT / "web" / "nemoclaw" / "index.html"
FOYER = ROOT / "web" / "index.html"

# Duplicated here intentionally. The JSON and Markdown files are human-readable canon,
# but this required gate must not trust a mutable data file as its only source of truth.
CANONICAL = {
    "title": "Securing Agents with OpenShell and NemoClaw",
    "abstract": "Modern agents are everywhere, and they’re conceptually simple: a model wired to tools, memory, and a routing decision that keeps running until the task is done. This course starts by building such a system from scratch, then connects those ideas to modern frameworks used by software engineers and non‑technical users alike. You’ll go from a single API call to agent coordination, grounded retrieval, deep planning, and safe deployment using NVIDIA OpenClaw and NVIDIA NemoClaw™.",
    "learning_objectives_intro": "Upon completion of this course, students will be able to:",
    "learning_objectives": [
        "Build a basic agent loop and identify its core components.",
        "Implement reliable tool use and function calling within an agent system.",
        "Design and coordinate multi-agent systems using structured routing patterns.",
        "Utilize OpenShell to configure agent identities and ensure safe, sandboxed operations.",
        "Deploy and manage autonomous agents while building persistent skill libraries.",
    ],
}


class TextById(HTMLParser):
    def __init__(self, target_id: str):
        super().__init__(convert_charrefs=True)
        self.target_id = target_id
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == self.target_id:
            self.depth = 1
        elif self.depth:
            self.depth += 1

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)


class LearningObjectiveIds(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []

    def handle_starttag(self, tag, attrs):
        identifier = dict(attrs).get("id", "")
        if re.fullmatch(r"learning-objective-\d+", identifier):
            self.ids.append(identifier)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def text_by_id(path: Path, target_id: str) -> str:
    parser = TextById(target_id)
    parser.feed(path.read_text(encoding="utf-8"))
    return norm("".join(parser.parts))


def learning_objective_ids(source: str) -> list[str]:
    parser = LearningObjectiveIds()
    parser.feed(source)
    return parser.ids


def course_homes() -> list[Path]:
    localized = sorted((ROOT / "i18n").glob("*/web/nemoclaw/index.html"))
    return [COURSE_HOME, *localized]


def expect(findings: list[str], label: str, actual: str, expected: str) -> None:
    if norm(actual) != norm(expected):
        findings.append(f"{label} changed; restore exact canonical text")


def audit() -> list[str]:
    findings: list[str] = []
    try:
        data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"course_contract.json cannot be read: {exc}"]

    for key in ("title", "abstract", "learning_objectives_intro"):
        if norm(data.get(key, "")) != norm(CANONICAL[key]):
            findings.append(f"course_contract.json {key} changed; restore exact canonical text")
    if data.get("learning_objectives") != CANONICAL["learning_objectives"]:
        findings.append("course_contract.json learning_objectives changed; restore exact canonical list and order")

    canon_text = CANON_PATH.read_text(encoding="utf-8") if CANON_PATH.is_file() else ""
    for item in [CANONICAL["title"], CANONICAL["abstract"], CANONICAL["learning_objectives_intro"], *CANONICAL["learning_objectives"]]:
        if item not in canon_text:
            findings.append(f"COURSE_CANON.md missing exact canonical text: {item[:80]}")

    expect(findings, "course home h1", text_by_id(COURSE_HOME, "course-title"), CANONICAL["title"])
    expect(findings, "course home abstract", text_by_id(COURSE_HOME, "course-abstract"), CANONICAL["abstract"])
    expect(findings, "course home objectives intro", text_by_id(COURSE_HOME, "learning-objectives-intro"), CANONICAL["learning_objectives_intro"])
    for idx, objective in enumerate(CANONICAL["learning_objectives"], start=1):
        expect(findings, f"course home objective {idx}", text_by_id(COURSE_HOME, f"learning-objective-{idx}"), objective)
    expected_ids = [
        f"learning-objective-{idx}"
        for idx in range(1, len(CANONICAL["learning_objectives"]) + 1)
    ]
    for path in course_homes():
        actual_ids = learning_objective_ids(path.read_text(encoding="utf-8"))
        if actual_ids != expected_ids:
            label = path.relative_to(ROOT).as_posix()
            findings.append(
                f"{label} objective IDs must be exactly {expected_ids}; found {actual_ids}"
            )

    expect(findings, "foyer card title", text_by_id(FOYER, "nemoclaw-course-title"), CANONICAL["title"])
    expect(findings, "foyer card abstract", text_by_id(FOYER, "nemoclaw-course-abstract"), CANONICAL["abstract"])
    return findings


run = audit


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate canonical NemoClaw course title, abstract, and learning objectives.")
    ap.add_argument("--json", action="store_true", help="print machine-readable findings")
    args = ap.parse_args()
    findings = audit()
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, indent=2))
    elif findings:
        for finding in findings:
            print(f"[course-contract] {finding}")
    else:
        print("course_contract: OK")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
