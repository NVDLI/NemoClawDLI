#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bind a privileged job to the real GitLab job and protected project settings."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_BRANCH = "main"
API_SHA256 = "01e7cf008751c1f0d0861359eecfae7db764a8669480830b12cb2acd61f6e456"
PROJECT_ID_SHA256 = "b5f6d9ed42567913667c7ae35de34ba6e93a6a34d64bf7c337448f0202f39b7b"

_SAFE_VALUE_ERROR_CODES = {
    "GitLab trust metadata changed origin": "api-origin",
    "GitLab returned malformed trust metadata": "api-metadata",
    "protected GitLab read-token file is unavailable": "read-token-file",
    "protected GitLab read token is malformed": "read-token-value",
    "protected GitLab API origin is outside the reviewed boundary": "api-config",
    "GitLab job token is unavailable": "job-token",
    "current job is outside the reviewed project": "project-id",
    "current job has no bounded child pipeline": "pipeline-id",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward a trust credential through an HTTP redirect."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def _load(url: str, header: str, token: str) -> dict[str, object]:
    request = urllib.request.Request(url, headers={header: token})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        if response.geturl() != url:
            raise ValueError("GitLab trust metadata changed origin")
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("GitLab returned malformed trust metadata")
    return value


def _file_secret(path: str) -> str:
    target = Path(path)
    if not target.is_file() or target.stat().st_size > 65_536:
        raise ValueError("protected GitLab read-token file is unavailable")
    value = target.read_text(encoding="utf-8").strip()
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError("protected GitLab read token is malformed")
    return value


def protected_api_url(path: str) -> str:
    """Load the owner-managed GitLab trust origin without publishing a private hostname."""

    value = _file_secret(path).rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
        or parsed.port is not None or parsed.query or parsed.fragment or parsed.path != "/api/v4"
        or hashlib.sha256(value.encode("utf-8")).hexdigest() != API_SHA256
    ):
        raise ValueError("protected GitLab API origin is outside the reviewed boundary")
    return value


def trusted_project_id(value: object) -> bool:
    text = str(value)
    return text.isdecimal() and hashlib.sha256(text.encode("ascii")).hexdigest() == PROJECT_ID_SHA256


def safe_failure_code(exc: ValueError) -> str:
    """Return only reviewed diagnostics; never echo API, token, or filesystem data."""

    message = str(exc)
    if re.fullmatch(r"(?:binding|project-policy):[a-z-]+", message):
        return message
    if message.startswith("checkout "):
        return "checkout-head"
    return _SAFE_VALUE_ERROR_CODES.get(message, "value-error")


def detached_head(root: Path) -> str:
    """Read the runner checkout identity without relying on an undeclared Git binary."""

    root = root.resolve(strict=True)
    git_entry = root / ".git"
    if git_entry.is_symlink():
        raise ValueError("checkout has no bounded detached HEAD")
    if git_entry.is_dir():
        git_dir = git_entry
    elif git_entry.is_file() and git_entry.stat().st_size <= 4_096:
        pointer = git_entry.read_text(encoding="ascii").strip()
        match = re.fullmatch(r"gitdir: ([^\x00-\x1f\x7f]+)", pointer)
        if not match:
            raise ValueError("checkout has no bounded detached HEAD")
        candidate = Path(match.group(1))
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = Path(os.path.abspath(candidate))
        boundary = root.parent
        try:
            relative = candidate.relative_to(boundary)
        except ValueError as exc:
            raise ValueError("checkout Git metadata escapes its build boundary") from exc
        cursor = boundary
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise ValueError("checkout Git metadata uses a symlink")
        git_dir = candidate.resolve(strict=True)
        try:
            git_dir.relative_to(boundary)
        except ValueError as exc:
            raise ValueError("checkout Git metadata escapes its build boundary") from exc
    else:
        raise ValueError("checkout has no bounded detached HEAD")
    target = git_dir / "HEAD"
    if (
        git_dir.is_symlink() or not git_dir.is_dir()
        or target.is_symlink() or not target.is_file() or target.stat().st_size > 128
    ):
        raise ValueError("checkout has no bounded detached HEAD")
    value = target.read_text(encoding="ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError("checkout HEAD is not a detached commit")
    return value


def verify(
    *, expected_job: str, job_token: str, read_token: str, api: str, root: Path,
) -> dict[str, object]:
    if not job_token or any(ord(char) < 32 for char in job_token):
        raise ValueError("GitLab job token is unavailable")
    current = _load(api + "/job", "JOB-TOKEN", job_token)
    pipeline = current.get("pipeline") if isinstance(current.get("pipeline"), dict) else {}
    project_id = pipeline.get("project_id")
    if not trusted_project_id(project_id):
        raise ValueError("current job is outside the reviewed project")
    project = _load(api + f"/projects/{project_id}", "PRIVATE-TOKEN", read_token)
    head = detached_head(root)
    pipeline_id = str(pipeline.get("id", ""))
    if not pipeline_id.isdecimal():
        raise ValueError("current job has no bounded child pipeline")
    pipeline_record = _load(
        api + f"/projects/{project_id}/pipelines/{pipeline_id}", "PRIVATE-TOKEN", read_token,
    )
    branch_record = _load(
        api + f"/projects/{project_id}/repository/branches/{urllib.parse.quote(DEFAULT_BRANCH, safe='')}",
        "PRIVATE-TOKEN", read_token,
    )
    branch_commit = branch_record.get("commit") if isinstance(branch_record.get("commit"), dict) else {}
    commit = current.get("commit") if isinstance(current.get("commit"), dict) else {}
    bindings = (
        ("job-name", current.get("name") == expected_job),
        ("job-ref", current.get("ref") == DEFAULT_BRANCH),
        ("job-project", pipeline.get("project_id") == project_id),
        ("pipeline-ref", pipeline.get("ref") == DEFAULT_BRANCH),
        ("pipeline-head", pipeline.get("sha") == head),
        ("job-commit", commit.get("id") == head),
        ("pipeline-record-id", pipeline_record.get("id") == pipeline.get("id")),
        ("pipeline-source", pipeline_record.get("source") == "parent_pipeline"),
        ("pipeline-record-ref", pipeline_record.get("ref") == DEFAULT_BRANCH),
        ("pipeline-record-head", pipeline_record.get("sha") == head),
        ("branch-head", branch_commit.get("id") == head),
    )
    for code, satisfied in bindings:
        if not satisfied:
            raise ValueError(f"binding:{code}")
    policies = (
        ("project-id", project.get("id") == project_id),
        ("default-branch", project.get("default_branch") == DEFAULT_BRANCH),
        ("variable-override-role", project.get("ci_pipeline_variables_minimum_override_role") == "owner"),
    )
    for code, satisfied in policies:
        if not satisfied:
            raise ValueError(f"project-policy:{code}")
    return {
        "schema": "dli-trusted-gitlab-context/1", "project_id": project_id,
        "ref": DEFAULT_BRANCH, "sha": head, "job": expected_job,
        "pipeline_id": pipeline.get("id"),
    }


def bind_prior(current: dict[str, object], prior: dict[str, object]) -> None:
    for key in ("schema", "project_id", "ref", "sha", "pipeline_id"):
        if current.get(key) != prior.get(key):
            raise ValueError("privileged job context does not match acquisition context")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--prior")
    args = parser.parse_args()
    try:
        result = verify(
            expected_job=args.job, job_token=os.environ.get("CI_JOB_TOKEN", ""),
            read_token=_file_secret(os.environ.get("COURSE_GITLAB_READ_TOKEN_FILE", "")),
            api=protected_api_url(os.environ.get("COURSE_GITLAB_API_URL_FILE", "")),
            root=Path.cwd(),
        )
        if args.prior:
            bind_prior(result, json.loads(Path(args.prior).read_text(encoding="utf-8")))
        Path(args.output).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except ValueError as exc:
        print(f"trusted GitLab context: FAIL: ValueError:{safe_failure_code(exc)}")
        return 1
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"trusted GitLab context: FAIL: {type(exc).__name__}")
        return 1
    print(f"trusted GitLab context: OK job={result['job']} sha={str(result['sha'])[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
