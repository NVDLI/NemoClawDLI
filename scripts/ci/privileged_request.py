#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate the closed vocabulary for protected internal GitLab operations."""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from scripts.ci.trusted_gitlab_context import DEFAULT_BRANCH, trusted_project_id


REF = re.compile(r"^(?![-/])(?!.*(?:\.\.|//))[A-Za-z0-9][A-Za-z0-9._/-]{0,126}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
JOB = re.compile(r"^[1-9][0-9]{0,11}$")
LANG = re.compile(r"^[a-z]{2}(?:-[a-z0-9]+)?$")
OPERATIONS = {"live-interface-review", "cdn-publish"}
CHANNELS = {"immutable", "stable"}
COURSES = {"nemoclaw"}
PROVIDERS = {"cloudflare", "pomerium"}
CHILD_BINDINGS = (
    ("COURSE_OP", "DLI_REQUEST_OP"),
    ("CANDIDATE_REF", "DLI_REQUEST_CANDIDATE_REF"),
    ("CANDIDATE_SHA", "DLI_REQUEST_CANDIDATE_SHA"),
    ("CANDIDATE_TEST_JOB_ID", "DLI_REQUEST_CANDIDATE_TEST_JOB_ID"),
    ("CLAW_URL_1", "DLI_REQUEST_CLAW_URL_1"),
    ("CLAW_ACCESS_PROVIDER_1", "DLI_REQUEST_CLAW_ACCESS_PROVIDER_1"),
    ("CLAW_URL_2", "DLI_REQUEST_CLAW_URL_2"),
    ("CLAW_ACCESS_PROVIDER_2", "DLI_REQUEST_CLAW_ACCESS_PROVIDER_2"),
    ("PUBLISH_SOURCE_REF", "DLI_REQUEST_PUBLISH_SOURCE_REF"),
    ("PUBLISH_SOURCE_SHA", "DLI_REQUEST_PUBLISH_SOURCE_SHA"),
    ("PUBLISH_SOURCE_TEST_JOB_ID", "DLI_REQUEST_PUBLISH_SOURCE_TEST_JOB_ID"),
    ("PUBLISH_COURSES", "DLI_REQUEST_PUBLISH_COURSES"),
    ("PUBLISH_LANGUAGES", "DLI_REQUEST_PUBLISH_LANGUAGES"),
    ("PUBLISH_CHANNEL", "DLI_REQUEST_PUBLISH_CHANNEL"),
)


def child_request_env(env: dict[str, str]) -> dict[str, str]:
    """Project only the bridge's closed request vocabulary into canonical names."""

    return {canonical: env.get(child, "") for canonical, child in CHILD_BINDINGS}


def validate(operation: str, env: dict[str, str], root: Path, context: dict[str, object] | None = None) -> dict[str, object]:
    errors: list[str] = []
    if operation not in OPERATIONS or env.get("COURSE_OP") != operation:
        errors.append("COURSE_OP does not match the selected protected operation")
    if (
        not isinstance(context, dict) or context.get("schema") != "dli-trusted-gitlab-context/1"
        or not trusted_project_id(context.get("project_id")) or context.get("ref") != DEFAULT_BRANCH
    ):
        errors.append("protected operation lacks verified GitLab job context")

    prefix = "CANDIDATE" if operation == "live-interface-review" else "PUBLISH_SOURCE"
    ref = env.get(f"{prefix}_REF", "")
    sha = env.get(f"{prefix}_SHA", "")
    job = env.get("CANDIDATE_TEST_JOB_ID" if operation == "live-interface-review" else "PUBLISH_SOURCE_TEST_JOB_ID", "")
    if not REF.fullmatch(ref):
        errors.append(f"{prefix}_REF is outside the allowed branch vocabulary")
    if not SHA.fullmatch(sha):
        errors.append(f"{prefix}_SHA must be one full lowercase Git commit SHA")
    if not JOB.fullmatch(job):
        errors.append("artifact job ID must be a positive decimal GitLab job ID")

    result: dict[str, object] = {"operation": operation, "source_ref": ref, "source_sha": sha, "job_id": job}
    if operation == "live-interface-review":
        from urllib.parse import urlsplit
        targets = []
        for slot in (1, 2):
            provider = env.get(f"CLAW_ACCESS_PROVIDER_{slot}", "").strip().lower()
            url = env.get(f"CLAW_URL_{slot}", "").strip()
            if not provider and not url and slot == 2:
                continue
            if provider not in PROVIDERS:
                errors.append(f"CLAW_ACCESS_PROVIDER_{slot} must be cloudflare or pomerium")
            try:
                parsed = urlsplit(url)
                host = (parsed.hostname or "").lower()
                expected = "pomerium" if host.endswith(".apps.run.brev.nvidia.com") else "cloudflare" if host.endswith(".brevlab.com") else ""
                if parsed.scheme != "https" or parsed.path not in {"", "/"} or parsed.query or parsed.fragment or provider != expected:
                    raise ValueError
            except ValueError:
                errors.append(f"CLAW_URL_{slot} must be a provider-matching HTTPS Brev launchable root")
            targets.append({"slot": slot, "url": url, "provider": provider})
        if len({str(item["url"]) for item in targets}) != len(targets):
            errors.append("live launchable targets must be distinct")
        result["targets"] = targets
    else:
        channel = env.get("PUBLISH_CHANNEL", "")
        courses = [item.strip() for item in env.get("PUBLISH_COURSES", "").split(",") if item.strip()]
        requested = [item.strip() for item in env.get("PUBLISH_LANGUAGES", "").split(",") if item.strip()]
        if channel not in CHANNELS:
            errors.append("PUBLISH_CHANNEL must be immutable or stable")
        if not requested or len(requested) != len(set(requested)) or not all(LANG.fullmatch(item) for item in requested):
            errors.append("PUBLISH_LANGUAGES must be a unique comma-separated language list")
        if (
            not courses or len(courses) != len(set(courses))
            or not set(courses).issubset(COURSES) or "nemoclaw" not in courses
        ):
            errors.append("PUBLISH_COURSES must contain only nemoclaw")
        result.update({
            "channel": channel, "courses": courses, "languages": requested,
            "destination": sha if channel == "immutable" else "course-static",
        })
    if errors:
        raise ValueError("; ".join(errors))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument("--output")
    parser.add_argument("--context", required=True)
    args = parser.parse_args()
    try:
        context = json.loads(Path(args.context).read_text(encoding="utf-8"))
        result = validate(args.operation, child_request_env(dict(os.environ)), Path.cwd(), context)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"privileged request: FAIL: {exc}")
        return 1
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"privileged request: OK operation={result['operation']} source={result['source_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
