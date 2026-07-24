#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject retired runtime packages from the two active Python tool locks.

Known-vulnerability evaluation belongs to the pinned pip-audit CI job. This fast
offline check keeps the removed application/lab runtime from returning through a
tooling manifest.
"""
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = (
    Path("scripts/materials/requirements.lock"),
    Path("scripts/security/requirements-sca.lock"),
)
FORBIDDEN_DIRECT_REQUIREMENTS = dict.fromkeys(
    ("fastapi", "uvicorn", "jupyterlab", "streamlit", "gradio", "torch", "litellm", "docker"),
    "application or container runtime package",
)


def names(path: Path) -> set[str]:
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==", line.strip())
        if match:
            found.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return found


def audit(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    for rel in MANIFESTS:
        path = root / rel
        if not path.is_file():
            failures.append(f"missing active tool lock: {rel}")
            continue
        for package in sorted(names(path) & FORBIDDEN_DIRECT_REQUIREMENTS.keys()):
            failures.append(f"{rel}: retired runtime component present: {package}")
    return failures


def self_test() -> list[str]:
    if audit():
        return ["baseline is not clean"]
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        for rel in MANIFESTS:
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
        target = root / MANIFESTS[0]
        target.write_text(target.read_text(encoding="utf-8") + "\nfastapi==1.0\n", encoding="utf-8")
        if not audit(root):
            return ["retired runtime mutation escaped"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    failures = self_test() if args.self_test else audit()
    if failures:
        print("python dependency boundary: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("python dependency boundary: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
