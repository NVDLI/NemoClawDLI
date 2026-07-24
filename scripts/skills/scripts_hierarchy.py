#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guardrail for the scripts/ hierarchy.

The scripts/ root is intentionally sparse so the repository browser shows the grouped
layout. Implementations and runnable entrypoints live under named subdirectories with
their own SKILL.html beacon. New root-level scripts are a regression.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"

ROOT_ALLOW = {".gitkeep", "SKILL.html", "_bootstrap.py"}
SKIP_DIRS = {"__pycache__", ".figtools", "grounding_cache"}
REQUIRED_RUNTIME_ASSETS = (
    "runtime/browser_runtime_test.sh", "runtime/host_browser.py",
    "runtime/package.json", "runtime/pnpm-lock.yaml",
)


def findings() -> list[str]:
    out: list[str] = []
    groups = sorted(path for path in SCRIPTS.iterdir() if path.is_dir() and path.name not in SKIP_DIRS)
    for group in groups:
        if not (group / "SKILL.html").is_file():
            out.append(f"missing scripts/{group.name}/SKILL.html")
    for rel in REQUIRED_RUNTIME_ASSETS:
        if not (SCRIPTS / rel).is_file():
            out.append(f"missing required runtime asset scripts/{rel}")
    for p in SCRIPTS.iterdir():
        if p.is_dir():
            continue
        if p.name not in ROOT_ALLOW:
            out.append(f"unexpected root scripts/ file {p.name}; move it into a grouped subdirectory")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="validate scripts/ hierarchy")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    rows = findings()
    if args.json:
        print(json.dumps({"findings": rows}, indent=2))
    elif rows:
        print("scripts_hierarchy: FAIL")
        for row in rows:
            print(f"  - {row}")
    else:
        print("scripts_hierarchy: OK")
    return 1 if rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
