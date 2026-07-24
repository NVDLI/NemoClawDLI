#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Classify public GitHub and internal GitLab source drift without changing either ref."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


SCHEMA = "nemoclaw-repository-sync/1"


def classify(*, trees_equal: bool, internal_is_ancestor: bool, external_is_ancestor: bool) -> str:
    if trees_equal:
        return "equivalent-tree"
    if internal_is_ancestor and not external_is_ancestor:
        return "external-ahead"
    if external_is_ancestor and not internal_is_ancestor:
        return "internal-ahead"
    return "diverged"


def requires_action(state: str) -> bool:
    return state != "equivalent-tree"


def next_action(state: str) -> str:
    return {
        "equivalent-tree": "no inbound integration MR is required",
        "external-ahead": "open a reviewed external-to-internal integration MR from canonical public GitHub",
        "internal-ahead": (
            "do not publish GitLab-only history; propose the change through public GitHub, then import it"
        ),
        "diverged": "reconcile from canonical public GitHub through a reviewed MR; never force-update either ref",
    }[state]


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed")
    return result


def ancestor(older: str, newer: str) -> bool:
    result = git("merge-base", "--is-ancestor", older, newer, check=False)
    if result.returncode not in {0, 1}:
        raise RuntimeError(result.stderr.strip() or "git merge-base failed")
    return result.returncode == 0


def audit(internal_ref: str, external_ref: str) -> dict:
    internal_sha = git("rev-parse", f"{internal_ref}^{{commit}}").stdout.strip()
    external_sha = git("rev-parse", f"{external_ref}^{{commit}}").stdout.strip()
    diff = git("diff", "--quiet", internal_sha, external_sha, check=False)
    if diff.returncode not in {0, 1}:
        raise RuntimeError(diff.stderr.strip() or "git diff failed")
    state = classify(
        trees_equal=diff.returncode == 0,
        internal_is_ancestor=ancestor(internal_sha, external_sha),
        external_is_ancestor=ancestor(external_sha, internal_sha),
    )
    changed = git("diff", "--name-only", internal_sha, external_sha).stdout.splitlines()
    action_required = requires_action(state)
    return {
        "schema": SCHEMA,
        "state": state,
        "action_required": action_required,
        "internal": {"ref": internal_ref, "commit": internal_sha},
        "external": {"ref": external_ref, "commit": external_sha},
        "changed_path_count": len(changed),
        "next_action": next_action(state),
    }


def self_test() -> list[str]:
    cases = (
        (dict(trees_equal=True, internal_is_ancestor=True, external_is_ancestor=True), "equivalent-tree", False),
        (dict(trees_equal=True, internal_is_ancestor=False, external_is_ancestor=False), "equivalent-tree", False),
        (dict(trees_equal=False, internal_is_ancestor=True, external_is_ancestor=False), "external-ahead", True),
        (dict(trees_equal=False, internal_is_ancestor=False, external_is_ancestor=True), "internal-ahead", True),
        (dict(trees_equal=False, internal_is_ancestor=False, external_is_ancestor=False), "diverged", True),
    )
    failures: list[str] = []
    for values, expected, expected_action in cases:
        state = classify(**values)
        if state != expected:
            failures.append(f"expected {expected}, got {state}")
        if requires_action(state) != expected_action:
            failures.append(f"expected action={expected_action} for {state}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--internal-ref")
    parser.add_argument("--external-ref")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        print("repository sync self-test: " + ("FAIL" if failures else "PASS"))
        for failure in failures:
            print("  " + failure)
        return 1 if failures else 0
    if not args.internal_ref or not args.external_ref:
        parser.error("--internal-ref and --external-ref are required")
    try:
        report = audit(args.internal_ref, args.external_ref)
    except RuntimeError as exc:
        print(f"repository sync audit: FAIL ({exc})")
        return 2
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    verdict = "ACTION REQUIRED" if report["action_required"] else "PASS"
    print(
        f"repository sync audit: {verdict} ({report['state']}, "
        f"{report['changed_path_count']} changed path(s))"
    )
    print("  " + report["next_action"])
    return 1 if report["action_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
