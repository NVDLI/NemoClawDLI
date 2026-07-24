#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Report external release evidence that a proposed diff requires an operator to refresh."""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

for _path in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_path / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_path / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())


@dataclass(frozen=True)
class FollowUp:
    id: str
    label: str
    action: str
    patterns: tuple[str, ...]


RULES = (
    FollowUp(
        "threat-architecture-review",
        "Threat and architecture assessment",
        "Refresh the authorized assessment when topology, trust boundaries, authentication, data flow, or deployment changed.",
        (
            ".github/workflows/*", ".gitlab-ci.yml", ".gitlab/ci/*", "scripts/cors-proxy/*",
            "docs/security-architecture.*", "docs/security-design.md",
            "web/nemoclaw/scripts/_openclaw.js", "web/nemoclaw/scripts/_shared.js",
        ),
    ),
    FollowUp(
        "authoritative-vulnerability-scan",
        "Authoritative vulnerability scan",
        "Rescan the final source and resolved release artifacts; bind dispositions to their immutable identities.",
        (
            "**/requirements*.txt", "**/requirements*.lock", "scripts/runtime/pnpm-lock.yaml",
            "scripts/browser-vendor/package.json", "scripts/browser-vendor/package-lock.json",
            "scripts/security/*", "web/nemoclaw/vendor/*",
        ),
    ),
    FollowUp(
        "privacy-data-review",
        "Privacy and data-use review",
        "Recheck the authorized privacy assessment when a destination, credential flow, browser storage, telemetry, or retention boundary changed.",
        (
            "docs/product-design.md", "docs/security-design.md", "web/nemoclaw/index.html",
            "web/nemoclaw/scripts/_keypanel.js", "web/nemoclaw/scripts/_openclaw.js",
            "web/nemoclaw/scripts/_shared.js",
        ),
    ),
    FollowUp(
        "open-source-license-review",
        "Open-source and license review",
        "Refresh component inventory, distribution method, license disposition, and authorized open-source review for changed third-party inputs.",
        (
            "**/requirements*.txt", "**/requirements*.lock", "scripts/runtime/pnpm-lock.yaml",
            "scripts/browser-vendor/*", "scripts/materials/*", "scripts/pyodide/*", "web/nemoclaw/mats/*",
            "web/nemoclaw/vendor/*",
        ),
    ),
    FollowUp(
        "verified-secret-scan",
        "Verified secret scan",
        "Run the authoritative secret scan on the final source ref after credential, workflow, proxy, or deployment handling changes.",
        (
            ".github/workflows/*", ".gitlab-ci.yml", ".gitlab/ci/*", "scripts/cors-proxy/*",
            "scripts/security/*", "web/nemoclaw/scripts/_openclaw.js", "web/nemoclaw/scripts/_shared.js",
        ),
    ),
    FollowUp(
        "final-artifact-evidence",
        "Final artifact security evidence",
        "Rebuild the immutable release artifact and refresh its SBOM, checksums, vulnerability result, malware result, and release decision.",
        (
            "i18n/*", "web/*", "**/requirements*.txt",
            "**/requirements*.lock", "scripts/build/*", "scripts/browser-vendor/*",
        ),
    ),
    FollowUp(
        "public-repository-work-products",
        "Public repository work-product review",
        "Re-review required, contextual, and optional public repository work products and record the designated approver's decision.",
        (
            "README.md", "LICENSE", "SECURITY.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md",
            "CHANGELOG.md", ".github/ISSUE_TEMPLATE/*", ".github/PULL_REQUEST_TEMPLATE.md",
            "docs/release_playbook.md", "docs/release-evidence.json",
            "scripts/validation/repository_work_products_audit.py",
        ),
    ),
)


def isolated_git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def matches(path: str, pattern: str) -> bool:
    if "**/" in pattern:
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern.replace("**/", ""))
    return fnmatch.fnmatch(path, pattern) or path.startswith(pattern.rstrip("*") + "/")


def classify(paths: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for rule in RULES:
        matched = sorted({path for path in paths if any(matches(path, pattern) for pattern in rule.patterns)})
        if matched:
            rows.append({
                "id": rule.id,
                "label": rule.label,
                "action": rule.action,
                "matched_paths": matched,
            })
    return rows


def changed_paths(commit_range: str, root: Path = ROOT) -> list[str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", commit_range, "--"],
        cwd=root,
        env=isolated_git_env(),
        check=False,
        text=True,
        capture_output=True,
    )
    if proc.returncode:
        raise RuntimeError(f"git diff failed for {commit_range}")
    return sorted({line.strip() for line in proc.stdout.splitlines() if line.strip()})


def self_test() -> list[str]:
    cases = (
        ("dependency", ["scripts/materials/requirements.lock"], {"authoritative-vulnerability-scan", "open-source-license-review", "final-artifact-evidence"}),
        ("topology", ["scripts/cors-proxy/reference.js"], {"threat-architecture-review", "verified-secret-scan"}),
        ("workflow", [".github/workflows/pages.yml"], {"threat-architecture-review", "verified-secret-scan"}),
        ("data route", ["web/nemoclaw/scripts/_shared.js"], {"threat-architecture-review", "privacy-data-review", "verified-secret-scan", "final-artifact-evidence"}),
        ("course", ["web/nemoclaw/01a-loop.html"], {"final-artifact-evidence"}),
        ("planned Pyodide", ["scripts/pyodide/candidate-components.json"], {"open-source-license-review"}),
        ("work products", ["CHANGELOG.md"], {"public-repository-work-products"}),
        ("ordinary docs", ["docs/issue_standards.md"], set()),
    )
    failures: list[str] = []
    for label, paths, expected in cases:
        actual = {row["id"] for row in classify(paths)}
        if actual != expected:
            failures.append(f"{label}: expected {sorted(expected)}, got {sorted(actual)}")
    combined = classify(["scripts/materials/requirements.lock", "scripts/cors-proxy/reference.js"])
    ids = [row["id"] for row in combined]
    if len(ids) != len(set(ids)):
        failures.append("combined paths emitted duplicate follow-up categories")
    return failures


def emit(paths: list[str], rows: list[dict[str, object]], commit_range: str, report: str | None) -> int:
    payload = {
        "schema": "release-change-reminder/1",
        "commit_range": commit_range,
        "changed_paths": paths,
        "follow_ups": rows,
        "repository_approval": False,
    }
    if report:
        target = Path(report)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if not rows:
        print(f"release change reminder: OK ({len(paths)} changed path(s); no conditional external follow-up)")
        return 0
    print(f"release change reminder: ACTION REQUIRED ({len(rows)} external follow-up area(s))")
    for row in rows:
        print(f"  - {row['label']}: {row['action']}")
        print("    triggered by: " + ", ".join(row["matched_paths"][:5]))
    print("Record links and decisions in the authorized release system; repository CI cannot complete or approve these actions.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit-range", metavar="BASE..HEAD")
    parser.add_argument("--path", action="append", default=[], help="classify an explicit repository path")
    parser.add_argument("--report")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        print("release change reminder self-test: " + ("FAIL" if failures else "PASS"))
        for failure in failures:
            print("  FAIL " + failure)
        return 1 if failures else 0
    if not args.commit_range and not args.path:
        parser.error("--commit-range or --path is required")
    try:
        paths = changed_paths(args.commit_range) if args.commit_range else sorted(set(args.path))
    except RuntimeError as exc:
        print(f"release change reminder: FAIL: {exc}")
        return 1
    return emit(paths, classify(paths), args.commit_range or "explicit paths", args.report)


if __name__ == "__main__":
    raise SystemExit(main())
