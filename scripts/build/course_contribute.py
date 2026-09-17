#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run repository validation with public tools; never perform forge operations."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


MODES = ("doctor", "fast-gate", "ship-gate", "build-pages")


def commands(mode: str, changed_since: str | None, output: str) -> list[list[str]]:
    """Return literal argv lists. Repository scripts own the gate definitions."""
    if mode == "doctor":
        return [[sys.executable, "scripts/runtime/python_env_probe.py"],
                ["bash", "scripts/runtime/browser_env_probe.sh"]]
    if mode == "build-pages":
        return [["bash", "scripts/build/build_pages.sh", output]]
    command = [sys.executable, "scripts/validation/release_gate.py", "--tier",
               "fast" if mode == "fast-gate" else "ship", "--no-write"]
    if changed_since:
        command.extend(["--changed-since", changed_since])
    return [command]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("mode", choices=MODES)
    parser.add_argument("--changed-since", help="Explicit upstream base for a contribution gate")
    parser.add_argument("--output", default="public", help="Pages output directory")
    args = parser.parse_args(argv)
    if sys.platform != "linux":
        parser.error("repository validation requires Linux; use the shell entry point with an authorized executor")
    if args.changed_since and args.mode not in ("fast-gate", "ship-gate"):
        parser.error("--changed-since applies only to fast-gate and ship-gate")
    if args.changed_since and args.changed_since.startswith("-"):
        parser.error("--changed-since must be a Git revision, not an option")
    if args.output != "public" and args.mode != "build-pages":
        parser.error("--output applies only to build-pages")
    root = args.repo.resolve()
    if not (root / "scripts/validation/release_gate.py").is_file():
        parser.error("--repo must point to a course checkout containing the release gate")
    environment = os.environ.copy()
    if args.mode == "build-pages":
        # Deterministic source build; no implicit material refresh or report reuse.
        environment["BUILD_PAGES_PULL_MATERIALS"] = "0"
        environment["BUILD_PAGES_REUSE_VALIDATION"] = "0"
    for command in commands(args.mode, args.changed_since, args.output):
        result = subprocess.run(command, cwd=root, env=environment, check=False)
        if result.returncode:
            return result.returncode if result.returncode > 0 else 128 - result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
