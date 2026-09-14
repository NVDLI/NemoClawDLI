#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve and run the repository's host-native Node/Chromium test runtime."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_NODE_MODULES = ROOT / "scripts" / "runtime" / "node_modules"


class BrowserRuntimeError(RuntimeError):
    """The host-native browser runtime is incomplete."""


def executable(value: str | None) -> str | None:
    if not value:
        return None
    path = shutil.which(value) or value
    return str(Path(path).resolve()) if Path(path).is_file() and os.access(path, os.X_OK) else None


def resolve_node() -> str:
    node = executable(os.environ.get("NODE_BIN")) or executable("node")
    if not node:
        raise BrowserRuntimeError("Node.js 20+ is required; install it or set NODE_BIN")
    return node


def resolve_node_path() -> str:
    node_path = Path(os.environ.get("NODE_PATH", str(RUNTIME_NODE_MODULES))).resolve()
    if not (node_path / "playwright-core" / "package.json").is_file():
        raise BrowserRuntimeError(
            "playwright-core is missing; run: (cd scripts/runtime && corepack enable && pnpm install --frozen-lockfile --ignore-scripts)"
        )
    return str(node_path)


def resolve_chrome() -> str:
    try:
        result = subprocess.run(
            [resolve_node(), str(ROOT / "scripts/runtime/browser_environment.cjs"), "--chrome"],
            cwd=ROOT, env={**os.environ, "NODE_PATH": resolve_node_path()},
            text=True, capture_output=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BrowserRuntimeError(f"browser discovery failed: {exc}") from exc
    found = executable(result.stdout.strip()) if result.returncode == 0 else None
    if found:
        return found
    raise BrowserRuntimeError(result.stderr.strip() or "Browser discovery returned no executable")

def main() -> int:
    try:
        print(resolve_chrome())
    except BrowserRuntimeError as exc:
        print(f"browser runtime: {exc}")
        return 2
    return 0


def environment(**values: str | Path | None) -> dict[str, str]:
    env = os.environ.copy()
    env.update({"NODE_PATH": resolve_node_path(), "CHROME_BIN": resolve_chrome(), "COURSE_ROOT": str(ROOT)})
    env.update({key: str(value) for key, value in values.items() if value is not None})
    return env


def run_node(
    script: Path,
    *,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [resolve_node(), str(script), *(args or [])],
        cwd=ROOT,
        env=env or environment(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


if __name__ == "__main__":
    raise SystemExit(main())
