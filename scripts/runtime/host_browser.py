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
MAC_BROWSERS = (
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
)
PLAYWRIGHT_BROWSER_NAMES = (
    "chrome-headless-shell-linux64/chrome-headless-shell",
    "chrome-linux/chrome",
    "chrome-linux64/chrome",
)


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
    requested = executable(os.environ.get("CHROME_BIN"))
    if requested:
        return requested
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = executable(name)
        if found:
            return found
    roots = (
        Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/tmp/pw-browsers")),
        Path("/sandbox/.cache/ms-playwright"),
        Path(os.environ.get("HOME", "/root")) / ".cache/ms-playwright",
    )
    for root in roots:
        if not root.is_dir():
            continue
        for revision in sorted(root.iterdir()):
            for name in PLAYWRIGHT_BROWSER_NAMES:
                found = executable(str(revision / name))
                if found:
                    return found
    for path in MAC_BROWSERS:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise BrowserRuntimeError("Chromium or compatible Chrome is required; install it or set CHROME_BIN")


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
