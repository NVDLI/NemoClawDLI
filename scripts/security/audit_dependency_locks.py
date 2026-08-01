#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject unpinned, unhashed, or stale material-tool and SCA dependency locks."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAIRS = (
    ("scripts/materials/requirements.lock.in", "scripts/materials/requirements.lock"),
    ("scripts/security/requirements-sca.lock.in", "scripts/security/requirements-sca.lock"),
)
PIN = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?==([^\s;]+)(?:\s*;\s*.+)?$")
HASH = re.compile(r"--hash=sha256:[0-9a-f]{64}")
PLAYWRIGHT_VERSION = "1.62.0"
PLAYWRIGHT_IMAGE = (
    "mcr.microsoft.com/playwright:v1.62.0-noble@sha256:"
    "baed2032d533817f3dbe6425de795788430ba345e819a1201337009ba17c9d07"
)
PNPM_PACKAGE_MANAGER = (
    "pnpm@10.34.5+sha512."
    "a4ee05f2f73658255bd6a89859c065a45c28a57daefae2c893a168ee2b73168c37b91e83e57ea67654ad03f03031746430e8bce38e362e042605fb8abc80192e"
)


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def logical_entries(path: Path) -> tuple[list[tuple[int, str]], list[str]]:
    """Join pip continuation lines without interpreting package metadata."""
    entries: list[tuple[int, str]] = []
    errors: list[str] = []
    parts: list[str] = []
    start = 0
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if not parts:
            start = line_no
        continued = line.endswith("\\")
        parts.append(line[:-1].strip() if continued else line)
        if not continued:
            entries.append((start, " ".join(parts)))
            parts = []
    if parts:
        errors.append(f"{path}:{start}: unterminated dependency continuation")
    return entries, errors


def pins(path: Path, *, require_hashes: bool = False) -> tuple[dict[str, str], list[str]]:
    found: dict[str, str] = {}
    errors: list[str] = []
    if not path.is_file():
        return found, [f"{path}: missing dependency file"]
    entries, entry_errors = logical_entries(path)
    errors.extend(entry_errors)
    for line_no, entry in entries:
        hashes = HASH.findall(entry)
        requirement = HASH.sub("", entry).strip()
        match = PIN.fullmatch(requirement)
        if not match:
            errors.append(f"{path}:{line_no}: dependency must use one exact == version: {entry}")
            continue
        if require_hashes and not hashes:
            errors.append(f"{path}:{line_no}: exact dependency lacks a SHA-256 artifact hash")
        name, version = norm(match.group(1)), match.group(2)
        if name in found and found[name] != version:
            errors.append(f"{path}:{line_no}: duplicate {name} versions {found[name]} and {version}")
        found[name] = version
    return found, errors


def gitlab_browser_jobs(source: str) -> list[tuple[str, str]]:
    """Discover top-level jobs that activate or directly consume browser tooling."""
    headings = list(re.finditer(r"(?m)^([A-Za-z][A-Za-z0-9_-]*):\s*$", source))
    jobs: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(source)
        block = source[heading.start():end]
        if (
            'BROWSER_TOOLS_REQUIRED: "1"' in block
            or "skill_renderer_runtime_audit.py" in block
        ):
            jobs.append((heading.group(1), block))
    return jobs


def audit(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for source_rel, lock_rel in PAIRS:
        source, source_errors = pins(root / source_rel)
        lock, lock_errors = pins(root / lock_rel, require_hashes=True)
        errors.extend(source_errors)
        errors.extend(lock_errors)
        for name, version in source.items():
            if lock.get(name) != version:
                errors.append(f"{lock_rel}: stale direct pin {name}; expected {version}, found {lock.get(name, 'missing')}")
    runtime_package = root / "scripts/runtime/package.json"
    runtime_lock = root / "scripts/runtime/pnpm-lock.yaml"
    gitlab_core = root / ".gitlab/ci/core.yml"
    try:
        package_data = json.loads(runtime_package.read_text(encoding="utf-8"))
        declared = package_data["devDependencies"]["playwright-core"]
        package_manager = package_data.get("packageManager")
    except (OSError, KeyError, json.JSONDecodeError):
        declared = None
        package_manager = None
    if declared != PLAYWRIGHT_VERSION:
        errors.append(
            "scripts/runtime/package.json: playwright-core must remain exactly "
            f"{PLAYWRIGHT_VERSION}; found {declared or 'missing'}"
        )
    if package_manager != PNPM_PACKAGE_MANAGER:
        errors.append("scripts/runtime/package.json: packageManager must remain exact and integrity-pinned")
    lock_text = runtime_lock.read_text(encoding="utf-8") if runtime_lock.is_file() else ""
    for token in (
        f"specifier: {PLAYWRIGHT_VERSION}",
        f"version: {PLAYWRIGHT_VERSION}",
        f"playwright-core@{PLAYWRIGHT_VERSION}:",
        "resolution: {integrity: sha512-",
    ):
        if token not in lock_text:
            errors.append(f"scripts/runtime/pnpm-lock.yaml: missing locked browser-runtime token: {token}")
    core_text = gitlab_core.read_text(encoding="utf-8") if gitlab_core.is_file() else ""
    browser_jobs = gitlab_browser_jobs(core_text)
    if not browser_jobs:
        errors.append(".gitlab/ci/core.yml: no browser-consuming validation jobs discovered")
    for job_name, block in browser_jobs:
        if PLAYWRIGHT_IMAGE not in block:
            errors.append(
                f".gitlab/ci/core.yml: browser-consuming job {job_name} must use "
                "the reviewed Playwright image and immutable digest"
            )
    return errors


def self_test() -> list[str]:
    failures: list[str] = []
    if audit(ROOT):
        return ["baseline dependency lock contract is not clean"]
    with tempfile.TemporaryDirectory(prefix="dependency-lock-audit-") as td:
        fixture = Path(td)
        for source, lock in PAIRS:
            for rel in (source, lock):
                dst = fixture / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, dst)
        for rel in ("scripts/runtime/package.json", "scripts/runtime/pnpm-lock.yaml", ".gitlab/ci/core.yml"):
            dst = fixture / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        mutations = (
            ("scripts/materials/requirements.lock", "requests==2.34.2", "requests==0.0.1"),
            ("scripts/materials/requirements.lock", "requests==2.34.2 \\", "requests==2.34.2"),
            ("scripts/security/requirements-sca.lock", "pip-audit==2.10.1", "# removed pip-audit"),
            ("scripts/runtime/package.json", '"playwright-core": "1.62.0"', '"playwright-core": "1.55.0"'),
            ("scripts/runtime/package.json", PNPM_PACKAGE_MANAGER, "pnpm@latest"),
            ("scripts/runtime/pnpm-lock.yaml", "specifier: 1.62.0", "specifier: 1.55.0"),
            (".gitlab/ci/core.yml", PLAYWRIGHT_IMAGE, "mcr.microsoft.com/playwright:v1.62.0-noble"),
        )
        for rel, old, new in mutations:
            path = fixture / rel
            baseline = path.read_text(encoding="utf-8")
            if old not in baseline:
                failures.append(f"fixture token missing: {rel}: {old}")
                continue
            path.write_text(baseline.replace(old, new, 1), encoding="utf-8")
            if not audit(fixture):
                failures.append(f"mutation escaped detector: {rel}")
            path.write_text(baseline, encoding="utf-8")
        core_path = fixture / ".gitlab/ci/core.yml"
        baseline = core_path.read_text(encoding="utf-8")
        core_path.write_text(
            baseline
            + '\nnovel_browser_job:\n'
            + '  image: node:20-bookworm-slim\n'
            + '  variables:\n'
            + '    BROWSER_TOOLS_REQUIRED: "1"\n'
            + '  script: ["true"]\n',
            encoding="utf-8",
        )
        if not audit(fixture):
            failures.append("novel browser-consuming GitLab job escaped detector")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    errors = self_test() if args.self_test else audit()
    if errors:
        print(f"dependency lock audit: FAIL ({len(errors)})")
        for error in errors:
            print(f"  {error}")
        return 1
    print("dependency lock audit: OK" + (" (mutation self-test)" if args.self_test else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
