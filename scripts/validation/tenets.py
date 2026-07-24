#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Report the bundle's core tenets and the gate that enforces each.

This bundle ships no agent-tool config file (no CLAUDE.md or equivalent). The operating
creed is PROJECTED into the root SKILL.html skill-meta (key: tenets) by
gen_skill_hierarchy.py, so there is one source that any agent or person reading the brain
inherits. This script reads it back, prints it grouped (purpose / assumptions / practices /
cadences / creeds), and names the validator that enforces each checkable tenet.

  python3 scripts/validation/tenets.py            report the tenets + their enforcement
  python3 scripts/validation/tenets.py --check    verify the projection is present (exit 1 if gone)

The --check form is cheap enough to run in the validate cadence, so a regeneration can
never silently drop the projection.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import find_repo_root

TASK1 = find_repo_root(Path(__file__).resolve())
SKILL = TASK1 / "SKILL.html"
ORDER = ("purpose", "assumptions", "practices", "cadences", "creeds")

# Theme -> the gate that enforces tenets of that theme. Keyed by a substring that appears
# in the tenet text, so the mapping survives small wording changes. A tenet with no gate
# relies on discipline; this script labels it that way instead of claiming it is enforced.
ENFORCED_BY = [
    ("em-dash",               "validate_bundle.py --scope ship  (grounding em-dash check)"),
    ("corruption markers",    "validate_bundle.py --scope ship  (page audit)"),
    ("buzzy",                 "validate_bundle.py --scope ship  (page audit, advisory)"),
    ("isolation",             "validate_layout.py + run_engine.sh --check  (cross-course gate)"),
    ("links another course",  "validate_layout.py + run_engine.sh --check  (cross-course gate)"),
    ("released courses",      "run_engine.sh --self-test  (release/foyer contract)"),
    ("foyer",                 "run_engine.sh --self-test  (release/foyer contract)"),
    ("skill-meta json",       "skill_consistency.py  (skill-meta vs the real tree)"),
    ("validate before",       "install-hooks.sh wires the pre-push gate that runs all four"),
    ("ideas stay easy",       "contribution_safety_audit.py + required CI + protected host settings"),
    ("runtime output",        ".gitignore + the pre-commit / pre-push hooks"),
    ("single source",         "run_engine.sh --self-test  (one engine, pinned facts)"),
    ("lead-page parity",      "manual review (lead-page-parity); not auto-gated"),
    ("sample of a class",     "discipline (grep the repo before fixing); not auto-gated"),
]


def load_tenets():
    try:
        text = SKILL.read_text()
    except FileNotFoundError:
        return None
    m = re.search(r'<script type="application/json" id="skill-meta">(.*?)</script>', text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1)).get("tenets")
    except json.JSONDecodeError:
        return None


def gate_for(text: str):
    low = text.lower()
    for needle, gate in ENFORCED_BY:
        if needle in low:
            return gate
    return None


def main(argv) -> int:
    check = "--check" in argv
    tenets = load_tenets()
    if not tenets:
        print("tenets: FAIL. SKILL.html has no skill-meta.tenets projection.")
        print("        regenerate it: python3 scripts/skills/gen_skill_hierarchy.py")
        return 1
    if check:
        n = sum(len(tenets.get(k) or []) for k in ORDER)
        print(f"tenets: OK. The projection is present in SKILL.html with {n} tenets across {len(ORDER)} groups.")
        return 0
    label = {"purpose": "PURPOSE (what this platform is for)",
             "assumptions": "ASSUMPTIONS (what is true here)",
             "practices": "PRACTICES (how to work)",
             "cadences": "CADENCES (the rhythm and the gates)",
             "creeds": "CREEDS (the quality bar)"}
    total = 0
    for key in ORDER:
        items = tenets.get(key) or []
        if not items:
            continue
        print(f"\n== {label[key]} ==")
        for t in items:
            total += 1
            print(f"  - {t}")
            gate = gate_for(t)
            if gate:
                print(f"      enforced by: {gate}")
    print(f"\n{total} tenets projected from SKILL.html skill-meta (no agent-tool config file ships).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
