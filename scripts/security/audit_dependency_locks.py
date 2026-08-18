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
PNPM_PACKAGE_MANAGER = (
    "pnpm@10.34.5+sha512."
    "a4ee05f2f73658255bd6a89859c065a45c28a57daefae2c893a168ee2b73168c37b91e83e57ea67654ad03f03031746430e8bce38e362e042605fb8abc80192e"
)


def browser_runtime_contract(root: Path) -> tuple[str, str, list[str]]:
    path = root / "scripts/runtime/browser-runtime.json"
    errors: list[str] = []
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
        version = contract["playwright_core"]
        image = contract["playwright_image"]
    except (OSError, KeyError, json.JSONDecodeError, TypeError):
        return "", "", ["scripts/runtime/browser-runtime.json: invalid browser runtime contract"]
    if contract.get("schema") != "nemoclaw-browser-runtime/v1":
        errors.append("scripts/runtime/browser-runtime.json: unsupported schema")
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        errors.append("scripts/runtime/browser-runtime.json: playwright_core must be one exact version")
        version = ""
    expected = rf"mcr\.microsoft\.com/playwright:v{re.escape(version)}-noble@sha256:[0-9a-f]{{64}}"
    if not isinstance(image, str) or not re.fullmatch(expected, image):
        errors.append(
            "scripts/runtime/browser-runtime.json: playwright_image must match the reviewed "
            "Playwright version and use a full immutable digest"
        )
        image = ""
    return version, image, errors


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
            or "mcr.microsoft.com/playwright:" in block
        ):
            jobs.append((heading.group(1), block))
    return jobs


def gitlab_ci_paths(root: Path) -> list[Path]:
    paths = {
        *root.glob(".gitlab/**/*.yml"),
        *root.glob(".gitlab/**/*.yaml"),
    }
    root_pipeline = root / ".gitlab-ci.yml"
    if root_pipeline.is_file():
        paths.add(root_pipeline)
    return sorted(paths)


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
    playwright_version, playwright_image, contract_errors = browser_runtime_contract(root)
    errors.extend(contract_errors)
    runtime_package = root / "scripts/runtime/package.json"
    runtime_lock = root / "scripts/runtime/pnpm-lock.yaml"
    try:
        package_data = json.loads(runtime_package.read_text(encoding="utf-8"))
        declared = package_data["devDependencies"]["playwright-core"]
        package_manager = package_data.get("packageManager")
    except (OSError, KeyError, json.JSONDecodeError):
        declared = None
        package_manager = None
    if declared != playwright_version:
        errors.append(
            "scripts/runtime/package.json: playwright-core must match the reviewed runtime contract; "
            f"expected {playwright_version or 'missing'}, found {declared or 'missing'}"
        )
    if package_manager != PNPM_PACKAGE_MANAGER:
        errors.append("scripts/runtime/package.json: packageManager must remain exact and integrity-pinned")
    lock_text = runtime_lock.read_text(encoding="utf-8") if runtime_lock.is_file() else ""
    for token in (
        f"specifier: {playwright_version}",
        f"version: {playwright_version}",
        f"playwright-core@{playwright_version}:",
        "resolution: {integrity: sha512-",
    ):
        if token not in lock_text:
            errors.append(f"scripts/runtime/pnpm-lock.yaml: missing locked browser-runtime token: {token}")
    discovered = 0
    for path in gitlab_ci_paths(root):
        rel = path.relative_to(root).as_posix()
        browser_jobs = gitlab_browser_jobs(path.read_text(encoding="utf-8"))
        discovered += len(browser_jobs)
        for job_name, block in browser_jobs:
            if not playwright_image or playwright_image not in block:
                errors.append(
                    f"{rel}: browser-consuming job {job_name} must use "
                    "the reviewed Playwright image and immutable digest"
                )
    if not discovered:
        errors.append("GitLab CI: no browser-consuming validation jobs discovered")
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
        for rel in (
            "scripts/runtime/browser-runtime.json",
            "scripts/runtime/package.json",
            "scripts/runtime/pnpm-lock.yaml",
        ):
            dst = fixture / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        for source in gitlab_ci_paths(ROOT):
            rel = source.relative_to(ROOT)
            dst = fixture / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dst)
        playwright_version, playwright_image, contract_errors = browser_runtime_contract(fixture)
        if contract_errors:
            failures.extend(contract_errors)
            return failures
        mutations = (
            ("scripts/materials/requirements.lock", "requests==2.34.2", "requests==0.0.1"),
            ("scripts/materials/requirements.lock", "requests==2.34.2 \\", "requests==2.34.2"),
            ("scripts/security/requirements-sca.lock", "pip-audit==2.10.1", "# removed pip-audit"),
            (
                "scripts/runtime/browser-runtime.json",
                f'"playwright_core": "{playwright_version}"',
                '"playwright_core": "1.55.0"',
            ),
            (
                "scripts/runtime/browser-runtime.json",
                playwright_image,
                f"mcr.microsoft.com/playwright:v{playwright_version}-noble",
            ),
            (
                "scripts/runtime/package.json",
                f'"playwright-core": "{playwright_version}"',
                '"playwright-core": "1.55.0"',
            ),
            ("scripts/runtime/package.json", PNPM_PACKAGE_MANAGER, "pnpm@latest"),
            (
                "scripts/runtime/pnpm-lock.yaml",
                f"specifier: {playwright_version}",
                "specifier: 1.55.0",
            ),
            (".gitlab/ci/core.yml", playwright_image, f"mcr.microsoft.com/playwright:v{playwright_version}-noble"),
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
        nested_path = fixture / ".gitlab/ci/nested/new-runtime.yml"
        nested_path.parent.mkdir(parents=True, exist_ok=True)
        nested_path.write_text(
            "nested_browser_job:\n"
            "  image: mcr.microsoft.com/playwright:v0.0.1-noble@sha256:"
            + "0" * 64
            + "\n  script: [\"true\"]\n",
            encoding="utf-8",
        )
        if not audit(fixture):
            failures.append("novel nested GitLab browser job escaped detector")
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
