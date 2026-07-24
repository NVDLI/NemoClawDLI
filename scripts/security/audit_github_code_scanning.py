#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Verify GitHub's host-side CodeQL check and pull-request alert state."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

GITHUB_API = "https://api.github.com"
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
CODEQL_APP = "github-advanced-security"
CODEQL_CHECK = "CodeQL"


def audit(check_runs: dict[str, Any], alerts: list[dict[str, Any]]) -> list[str]:
    """Return host-readiness failures from captured GitHub API responses."""
    findings: list[str] = []
    runs = check_runs.get("check_runs")
    if not isinstance(runs, list):
        return ["GitHub check-runs response is malformed"]
    host_checks = [
        item for item in runs
        if isinstance(item, dict)
        and item.get("name") == CODEQL_CHECK
        and isinstance(item.get("app"), dict)
        and item["app"].get("slug") == CODEQL_APP
    ]
    if len(host_checks) != 1:
        findings.append(
            f"expected one {CODEQL_APP}/{CODEQL_CHECK} host check, found {len(host_checks)}",
        )
    else:
        check = host_checks[0]
        if check.get("status") != "completed" or check.get("conclusion") != "success":
            title = check.get("output", {}).get("title") if isinstance(check.get("output"), dict) else None
            detail = f": {title}" if isinstance(title, str) and title else ""
            findings.append(
                f"host CodeQL check is {check.get('status')}/{check.get('conclusion')}{detail}",
            )

    if not isinstance(alerts, list):
        findings.append("GitHub code-scanning alert response is malformed")
    elif alerts:
        numbers = [
            str(item.get("number"))
            for item in alerts
            if isinstance(item, dict) and item.get("number") is not None
        ]
        suffix = f" ({', '.join(numbers[:8])}{'…' if len(numbers) > 8 else ''})" if numbers else ""
        findings.append(f"{len(alerts)} CodeQL alert(s) remain open on the pull-request merge ref{suffix}")
    return findings


def _get_json(path: str, token: str) -> Any:
    request = urllib.request.Request(
        GITHUB_API + path,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nemoclaw-code-scanning-audit",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def _load_json(path: str, label: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {label} snapshot {path}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", help="GitHub owner/repository")
    parser.add_argument("--pull-request", type=int, help="pull request number")
    parser.add_argument("--head-sha", help="exact pull request head commit")
    parser.add_argument("--check-runs-json", help="offline check-runs response")
    parser.add_argument("--alerts-json", help="offline open-alert response")
    args = parser.parse_args()

    offline = bool(args.check_runs_json or args.alerts_json)
    if offline:
        if not args.check_runs_json or not args.alerts_json:
            parser.error("offline mode requires --check-runs-json and --alerts-json")
        try:
            check_runs = _load_json(args.check_runs_json, "check-runs")
            alerts = _load_json(args.alerts_json, "alert")
        except ValueError as exc:
            print(f"GitHub CodeQL host audit: FAIL\n  - {exc}", file=sys.stderr)
            return 1
    else:
        if (
            not args.repository
            or not REPOSITORY_PATTERN.fullmatch(args.repository)
            or not args.pull_request
            or not args.head_sha
            or not SHA_PATTERN.fullmatch(args.head_sha)
        ):
            parser.error("live mode requires valid --repository, --pull-request, and --head-sha")
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            print("GitHub CodeQL host audit: FAIL\n  - GITHUB_TOKEN is required for live mode", file=sys.stderr)
            return 1
        repository = urllib.parse.quote(args.repository, safe="/")
        pull_ref = urllib.parse.quote(f"refs/pull/{args.pull_request}/merge", safe="")
        try:
            check_runs = _get_json(
                f"/repos/{repository}/commits/{args.head_sha}/check-runs?per_page=100",
                token,
            )
            alerts = _get_json(
                f"/repos/{repository}/code-scanning/alerts?state=open&ref={pull_ref}&per_page=100",
                token,
            )
        except (OSError, json.JSONDecodeError) as exc:
            print(f"GitHub CodeQL host audit: FAIL\n  - GitHub API request failed: {exc}", file=sys.stderr)
            return 1

    findings = audit(check_runs, alerts)
    if findings:
        print("GitHub CodeQL host audit: FAIL", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("GitHub CodeQL host audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
