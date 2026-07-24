#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fail early when repository tooling is running under an incompatible Python."""
from __future__ import annotations

import argparse
import importlib.util
import sys


MINIMUM = (3, 11)
TESTED = (3, 12)
MATERIAL_IMPORTS = ("requests", "bs4", "markdownify", "lxml")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-material-tools", action="store_true")
    args = parser.parse_args()
    version = sys.version_info[:2]
    if version < MINIMUM:
        print(
            f"python environment: FAIL (found {version[0]}.{version[1]}; Python 3.11+ is required)",
            file=sys.stderr,
        )
        print("Create a virtual environment with Python 3.12 and install the applicable pinned lock.", file=sys.stderr)
        return 2
    if args.require_material_tools:
        missing = [name for name in MATERIAL_IMPORTS if importlib.util.find_spec(name) is None]
        if missing:
            print("python environment: FAIL (missing material tools: " + ", ".join(missing) + ")", file=sys.stderr)
            print("Install scripts/materials/requirements.lock inside a virtual environment.", file=sys.stderr)
            return 2
    tested = "tested default" if version == TESTED else "compatible; Python 3.12 is the tested default"
    isolation = "virtual environment" if sys.prefix != sys.base_prefix else "system environment"
    print(f"python environment: OK ({version[0]}.{version[1]}, {tested}, {isolation})")
    if sys.prefix == sys.base_prefix:
        print("  note: use a virtual environment to avoid changing host-managed packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
