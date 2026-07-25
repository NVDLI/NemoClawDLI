#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Keep repository-owned container definitions out of this static course.

CI may execute on a hosted runner image. Contributors may also compose Python,
Node, and Chromium in an external container of their choosing. Neither case
justifies shipping a Dockerfile, Containerfile, Compose topology, or image build
command in this repository.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_NAMES = {".dockerignore", "Dockerfile", "Containerfile", "docker-compose.yml", "docker-compose.yaml"}
FORBIDDEN_SUFFIXES = (".Dockerfile", ".Containerfile")
COMMAND_MARKERS = ("docker build", "podman build", "docker compose", "podman compose")
TEXT_SUFFIXES = {".md", ".html", ".py", ".js", ".mjs", ".sh", ".yml", ".yaml"}


def tracked(root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, stdout=subprocess.PIPE, check=True
    )
    return [root / os.fsdecode(item) for item in proc.stdout.split(b"\0") if item]


def inspect(root: Path) -> list[str]:
    failures: list[str] = []
    for path in tracked(root):
        if not path.is_file():
            continue
        if path.name == "container_boundary_audit.py":
            continue
        if "web/nemoclaw/mats" in path.as_posix() or "web/nemoclaw/vendor" in path.as_posix():
            continue
        name = path.name
        if name in FORBIDDEN_NAMES or name.startswith("docker-compose.") or name.endswith(FORBIDDEN_SUFFIXES):
            failures.append(f"repository-owned container definition: {path.relative_to(root)}")
            continue
        if path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(errors="replace").lower()
        for marker in COMMAND_MARKERS:
            if marker in text:
                failures.append(f"repository-owned container command {marker!r}: {path.relative_to(root)}")
    return failures


def self_test() -> int:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / "safe.md").write_text("Use an external container if your organization requires one.\n")
        malformed = os.fsencode(root) + b"/safe-\xff.md"
        descriptor = os.open(malformed, os.O_WRONLY | os.O_CREAT, 0o600)
        os.write(descriptor, b"Safe source with a non-UTF-8 Git path.\n")
        os.close(descriptor)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        if inspect(root):
            print("container_boundary_audit self-test: FAIL (safe prose rejected)")
            return 1
        (root / "Dockerfile").write_text("FROM scratch\n")
        subprocess.run(["git", "add", "Dockerfile"], cwd=root, check=True)
        if not inspect(root):
            print("container_boundary_audit self-test: FAIL (Dockerfile accepted)")
            return 1
        (root / "Dockerfile").unlink()
        subprocess.run(["git", "add", "-u"], cwd=root, check=True)
        (root / "unsafe.md").write_text("Run docker build here.\n")
        subprocess.run(["git", "add", "unsafe.md"], cwd=root, check=True)
        if not inspect(root):
            print("container_boundary_audit self-test: FAIL (image build accepted)")
            return 1
        (root / ".dockerignore").write_text(".git\n")
        subprocess.run(["git", "add", ".dockerignore"], cwd=root, check=True)
        if not any(".dockerignore" in failure for failure in inspect(root)):
            print("container_boundary_audit self-test: FAIL (.dockerignore accepted)")
            return 1
    print("container_boundary_audit self-test: OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    failures = inspect(ROOT)
    if failures:
        print("container_boundary_audit: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("container_boundary_audit: OK (no repository-owned container stack)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
