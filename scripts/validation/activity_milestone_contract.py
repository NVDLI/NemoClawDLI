#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Enforce course-home milestone documentation and actual exercise anchor parity."""
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
ROWS = re.compile(r"^\| `([^`]+)` \| \[([^\]]+)\]\(([^)]+)\) \| ([^|]+) \|$", re.MULTILINE)
PAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.html")
TARGET = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}")


def audit_course(course: Path) -> list[str]:
    findings = []
    for filename in ("ACTIVITY_MILESTONES.md", "activity_milestones.json"):
        if not (course / filename).is_file():
            findings.append(f"{course.name}: missing required {filename}")
    if findings:
        return findings
    try:
        config = json.loads((course / "activity_milestones.json").read_text(encoding="utf-8"))
        milestones = config["milestones"]
        if config["schemaVersion"] != 1 or not isinstance(milestones, list) or not 1 <= len(milestones) <= 1000:
            raise ValueError("invalid version or milestone list")
        ids = [marker["id"] for marker in milestones]
        if len(ids) != len(set(ids)):
            findings.append(f"{course.name}: duplicate milestone IDs")
        doc = (course / "ACTIVITY_MILESTONES.md").read_text(encoding="utf-8")
        expected = [(marker["id"], marker["label"], marker["href"], marker["description"]) for marker in milestones]
        observed = [(a, b, c, d.strip()) for a, b, c, d in ROWS.findall(doc)]
        if not doc.startswith("# Activity Milestones\n") or observed != expected:
            findings.append(f"{course.name}: Markdown differs from canonical JSON")
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
        parallel = course / "scripts/_activity_config.js"
        if parallel.exists():
            findings.append(f"{course.name}: parallel JavaScript milestone definition source")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        findings.append(f"{course.name}: invalid milestone contract ({error})")
    return findings


def audit(root: Path = ROOT) -> list[str]:
    courses = [course for course in (root / "web").iterdir() if course.is_dir()
               and ((course / "activity-policy.json").exists() or (course / "scripts/_activity.js").exists())]
    return [finding for course in courses for finding in audit_course(course)]


if __name__ == "__main__":
    issues = audit()
    for issue in issues:
        print(issue)
    print(f"Activity milestone contract: {'FAIL' if issues else 'PASS'}")
    raise SystemExit(bool(issues))
