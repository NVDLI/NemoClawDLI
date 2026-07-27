#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run a validator with every resource-backed locale page materialized for non-Python consumers."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

for _path in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_path / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_path / "scripts"))
        break
from _bootstrap import add_script_paths, find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
add_script_paths(ROOT / "scripts")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="materialize published locale pages, then run a non-Python validator")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")

    from translate.locale_pages import materialize

    with tempfile.TemporaryDirectory(prefix="locale-pages-") as staged:
        environment = dict(os.environ)
        environment["NEMOCLAW_LOCALE_PAGES"] = str(materialize(ROOT, Path(staged)))
        return subprocess.run(command, cwd=ROOT, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
