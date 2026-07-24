# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared path helpers for scripts moved into subdirectories."""
from __future__ import annotations
from pathlib import Path
import sys


def find_repo_root(start: Path) -> Path:
    cur = start if start.is_dir() else start.parent
    for p in (cur, *cur.parents):
        if (p / "SKILL_CONTRACT.md").exists() and (p / "AGENTS.md").exists():
            return p
    raise RuntimeError(f"could not locate repo root from {start}")


def add_script_paths(scripts: Path) -> None:
    paths = [scripts] + [p for p in scripts.iterdir() if p.is_dir() and not p.name.startswith(".")]
    for p in reversed(paths):
        sp = str(p)
        if sp not in sys.path:
            sys.path.insert(0, sp)
