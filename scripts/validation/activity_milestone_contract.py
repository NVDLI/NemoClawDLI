#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Generate and audit the Activity milestone projection from its Markdown source."""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
JSON_BLOCK = re.compile(r"^```json[ \t]*\n(.*?)^```[ \t]*$", re.MULTILINE | re.DOTALL)
PAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.html")
TARGET = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}")


def audit_course(course: Path, *, document: Path | None = None, write: bool = False) -> list[str]:
    findings = []
    document = document or course.parent.parent / "docs/ACTIVITY_MILESTONES.md"
    projection = course.parent / "activity/activity_milestones.json"
    if not document.is_file():
        return [f"{course.name}: missing required {document.name}"]
    try:
        doc = document.read_text(encoding="utf-8")
        blocks = JSON_BLOCK.findall(doc)
        if not doc.startswith("# Activity Milestones\n") or len(blocks) != 1:
            raise ValueError("documentation must contain exactly one fenced json block")
        config = json.loads(blocks[0])
        validated = subprocess.run(
            ["node", "--input-type=module", "-e",
             "import {readFileSync} from 'node:fs'; "
             "const sdk = await import(process.argv[1]); "
             "sdk.validateActivityMilestoneConfig(JSON.parse(readFileSync(0, 'utf8')));",
             (ROOT / "web/activity/activity-sdk.js").as_uri()],
            input=json.dumps(config, allow_nan=False), capture_output=True, text=True, timeout=15,
        )
        if validated.returncode:
            raise ValueError("native SDK rejected milestone configuration")
        milestones = config["milestones"]
        ids = [marker["id"] for marker in milestones]
        for marker in milestones:
            page, target = marker["href"].split("#")
            targets = [(page, target)] + [(rule["page"], rule["target"]) for rule in marker["evidence"]]
            if not marker["evidence"]:
                findings.append(f"{course.name}: {marker['id']} lacks success evidence")
            for page, target in targets:
                if not PAGE.fullmatch(page) or not TARGET.fullmatch(target):
                    findings.append(f"{course.name}: {marker['id']} has unsafe target")
                    continue
                source = course / page
                if not source.is_file() or target not in re.findall(r"\bid=[\"']([^\"']+)[\"']", source.read_text(encoding="utf-8")):
                    findings.append(f"{course.name}: {marker['id']} target {page}#{target} does not exist")
        for script in (course / "scripts").glob("*.js"):
            source = script.read_text(encoding="utf-8")
            if any(re.search(r"[\"']" + re.escape(identifier) + r"[\"']", source) for identifier in ids):
                findings.append(f"{course.name}: milestone IDs must stay in JSON, not {script.name}")
        for script in (course.parent / "activity").glob("*.js"):
            source = script.read_text(encoding="utf-8")
            if any(re.search(r"[\"']" + re.escape(identifier) + r"[\"']", source) for identifier in ids):
                findings.append(f"{course.name}: milestone IDs must stay in documentation, not {script.name}")
        parallel = course / "scripts/_activity_config.js"
        if parallel.exists():
            findings.append(f"{course.name}: parallel JavaScript milestone definition source")
        if not findings:
            expected = json.dumps(config, indent=2, ensure_ascii=False) + "\n"
            if write:
                projection.parent.mkdir(parents=True, exist_ok=True)
                projection.write_text(expected, encoding="utf-8")
            elif not projection.is_file():
                findings.append(f"{course.name}: missing required {projection.name}; run activity_milestone_contract.py --write")
            elif projection.read_text(encoding="utf-8") != expected:
                findings.append(f"{course.name}: generated JSON differs from canonical Markdown; run activity_milestone_contract.py --write")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        findings.append(f"{course.name}: invalid milestone contract ({error})")
    return findings


def audit(root: Path = ROOT, *, write: bool = False) -> list[str]:
    courses = [course for course in (root / "web").iterdir() if course.is_dir()
               and (course / "COURSE_CANON.md").is_file()]
    if not courses:
        return ["Activity milestone contract: no course home found"]
    return [finding for course in courses for finding in audit_course(course, write=write)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="regenerate runtime JSON after validating source and DOM targets")
    args = parser.parse_args()
    issues = audit(write=args.write)
    for issue in issues:
        print(issue)
    print(f"Activity milestone contract: {'FAIL' if issues else 'PASS'}")
    raise SystemExit(bool(issues))
