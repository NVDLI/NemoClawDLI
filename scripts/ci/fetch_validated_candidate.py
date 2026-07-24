#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fetch one exact successful GitLab gate artifact without leaking its job token."""
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from scripts.ci.trusted_gitlab_context import protected_api_url, trusted_project_id


JOB = re.compile(r"^[1-9][0-9]{0,11}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_ARTIFACT = "validated-candidate.tar.gz"
MAX_BYTES = 256 * 1024 * 1024


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Keep the GitLab token on GitLab and strip it from signed object-store redirects."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # noqa: ANN001
        redirected = super().redirect_request(request, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        old = urllib.parse.urlsplit(request.full_url)
        new = urllib.parse.urlsplit(newurl)
        if (new.scheme, new.hostname, new.port) != (old.scheme, old.hostname, old.port):
            for headers_map in (redirected.headers, redirected.unredirected_hdrs):
                for name in list(headers_map):
                    if name.lower() in {"job-token", "private-token", "authorization"}:
                        headers_map.pop(name, None)
        else:
            for name, value in request.header_items():
                if name.lower() in {"job-token", "private-token", "authorization"}:
                    redirected.add_header(name, value)
        return redirected


def _request(opener: urllib.request.OpenerDirector, url: str, header: str, token: str):
    return opener.open(urllib.request.Request(url, headers={header: token}), timeout=60)


def fetch(
    *, job: str, ref: str, sha: str, metadata_token: str, artifact_token: str,
    api: str, project_id: int, output: Path,
) -> dict[str, object]:
    if not JOB.fullmatch(job) or not SHA.fullmatch(sha):
        raise ValueError("job or source SHA is outside the closed vocabulary")
    if not trusted_project_id(project_id):
        raise ValueError("candidate fetch is outside the reviewed project")
    if any(not token or any(ord(char) < 32 for char in token) for token in (metadata_token, artifact_token)):
        raise ValueError("GitLab metadata or artifact token is unavailable")
    opener = urllib.request.build_opener(SafeRedirect())
    base = api + f"/projects/{project_id}/jobs/{job}"
    with _request(opener, base, "PRIVATE-TOKEN", metadata_token) as response:
        metadata = json.load(response)
    commit = metadata.get("commit") or {}
    pipeline = metadata.get("pipeline") or {}
    if metadata.get("name") != "test" or metadata.get("status") != "success":
        raise ValueError("source job is not the successful required gate")
    if metadata.get("ref") != ref or commit.get("id") != sha or pipeline.get("sha") != sha:
        raise ValueError("source job does not belong to the requested ref and commit")
    branch_url = api + f"/projects/{project_id}/repository/branches/{urllib.parse.quote(ref, safe='')}"
    with _request(opener, branch_url, "PRIVATE-TOKEN", metadata_token) as response:
        branch = json.load(response)
    if (branch.get("commit") or {}).get("id") != sha:
        raise ValueError("requested source is no longer the current branch head")

    pipeline_id = str(pipeline.get("id", ""))
    if not JOB.fullmatch(pipeline_id):
        raise ValueError("source job has no bounded pipeline identifier")
    pipeline_url = api + f"/projects/{project_id}/pipelines/{pipeline_id}"
    with _request(opener, pipeline_url, "PRIVATE-TOKEN", metadata_token) as response:
        pipeline_record = json.load(response)
    if (
        not isinstance(pipeline_record, dict)
        or str(pipeline_record.get("id", "")) != pipeline_id
        or pipeline_record.get("ref") != ref
        or pipeline_record.get("sha") != sha
        or pipeline_record.get("status") != "success"
    ):
        raise ValueError("source pipeline is not the successful exact branch pipeline")
    # GitLab omits superseded retries by default. Keep that latest-attempt view:
    # accepting an older successful retry could mask a newer failed gate.
    jobs: list[object] = []
    page = 1
    while True:
        jobs_url = api + f"/projects/{project_id}/pipelines/{pipeline_id}/jobs?per_page=100&page={page}"
        with _request(opener, jobs_url, "PRIVATE-TOKEN", metadata_token) as response:
            page_rows = json.load(response)
            next_page = str(response.headers.get("X-Next-Page", "")).strip()
        if not isinstance(page_rows, list):
            raise ValueError("source pipeline job inventory is malformed")
        jobs.extend(page_rows)
        if not next_page:
            break
        if not next_page.isdecimal() or int(next_page) != page + 1 or page >= 100:
            raise ValueError("source pipeline job pagination is malformed")
        page = int(next_page)
    latest: dict[str, dict[str, object]] = {}
    for item in jobs:
        if not isinstance(item, dict):
            raise ValueError("source pipeline job inventory is malformed")
        name = str(item.get("name", ""))
        if name in latest:
            raise ValueError(f"source pipeline has ambiguous latest job evidence: {name}")
        latest[name] = item
    for required in ("test", "pages", "pages_smoke", "theme_runtime"):
        if str(latest.get(required, {}).get("status", "")) != "success":
            raise ValueError(f"source pipeline required job is not successful: {required}")
    for security in ("security_browser_sca", "security_python_sca", "security_sca"):
        if str(latest.get(security, {}).get("status", "")) != "success":
            raise ValueError(f"source pipeline security evidence is not successful: {security}")
    artifact_url = base + "/artifacts/" + urllib.parse.quote(ALLOWED_ARTIFACT, safe="")
    output.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with _request(opener, artifact_url, "JOB-TOKEN", artifact_token) as response, output.open("wb") as stream:
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError("validated candidate archive exceeds the fixed size limit")
            stream.write(chunk)
    if total == 0:
        raise ValueError("validated candidate archive is empty")
    return {"job_id": job, "pipeline_id": pipeline.get("id"), "source_ref": ref, "source_sha": sha, "bytes": total}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--context", required=True)
    args = parser.parse_args()
    try:
        context = json.loads(Path(args.context).read_text(encoding="utf-8"))
        result = fetch(
            job=args.job, ref=args.ref, sha=args.sha,
            metadata_token=Path(os.environ.get("COURSE_GITLAB_READ_TOKEN_FILE", "")).read_text(encoding="utf-8").strip(),
            artifact_token=os.environ.get("CI_JOB_TOKEN", ""),
            api=protected_api_url(os.environ.get("COURSE_GITLAB_API_URL_FILE", "")),
            project_id=int(context.get("project_id", 0)),
            output=Path(args.output),
        )
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"validated candidate fetch: FAIL: {type(exc).__name__}")
        return 1
    print(f"validated candidate fetch: OK job={result['job_id']} bytes={result['bytes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
