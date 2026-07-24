#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Guard the GitLab Pages storage contract.

This GitLab instance still uses classic Pages: only the job literally named
`pages` can publish. Branch previews therefore share the production Pages job and
produce large downloadable artifacts. This audit keeps the retention controls in
place without depending on PyYAML in the minimal runner image.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def _root() -> Path:
    for p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
        if (p / ".gitlab-ci.yml").exists():
            return p
    raise SystemExit("ci_storage_audit: could not find repo root")


def _job_block(text: str, job: str) -> str:
    m = re.search(rf"(?ms)^{re.escape(job)}:\n(?P<body>.*?)(?=^[A-Za-z0-9_.-]+:\n|\Z)", text)
    return m.group("body") if m else ""


def main() -> int:
    root = _root()
    ci = root / ".gitlab" / "ci" / "core.yml"
    text = ci.read_text(encoding="utf-8")
    gate = (root / "scripts/validation/release_gate.py").read_text(encoding="utf-8")
    findings: list[str] = []

    pages = _job_block(text, "pages")
    test = _job_block(text, "test")
    smoke = _job_block(text, "pages_smoke")
    human = _job_block(text, "human_review")

    if not pages:
        findings.append("missing pages job")

    checks = [
        (pages, r"install_branch_candidate\(\)", "pages job must install the tested branch candidate"),
        (pages, r"build_production_root_from_ref\(\)", "preview path must rebuild production root from a protected ref"),
        (pages, r"artifacts:\n(?:[ ]{2,}.*\n)*?[ ]{4}expire_in:\s*3 days", "pages artifacts must expire"),
        (pages, r"environment:\n(?:[ ]{2,}.*\n)*?[ ]{4}name:\s*[\"']?\$PAGES_ENVIRONMENT_NAME", "pages environment must be rule-scoped"),
        (pages, r"environment:\n(?:[ ]{2,}.*\n)*?[ ]{4}url:\s*[\"']?\$PAGES_DEPLOYED_URL", "pages environment must use the canonical deployed URL"),
        (pages, r"environment:\n(?:[ ]{2,}.*\n)*?[ ]{4}auto_stop_in:\s*[\"']?\$PAGES_AUTO_STOP_IN", "pages environment must use rule-scoped auto_stop_in"),
        (pages, r'pages_environment_url="\$\{PAGES_ENVIRONMENT_URL/http:/https:\}"', "pages environment must normalize the GitLab-provided HTTP URL to HTTPS"),
        (pages, r"dotenv:\s*pages-environment\.env", "pages environment must publish its canonical URL through dotenv"),
        (pages, r"PAGES_ENVIRONMENT_NAME:\s*[\"']?review/\$CI_COMMIT_REF_SLUG", "branch previews must use review environments"),
        (pages, r"PAGES_ENVIRONMENT_URL:\s*[\"']?\$CI_PAGES_URL/\$CI_COMMIT_REF_SLUG/web/nemoclaw/", "branch previews must keep their review URL"),
        (pages, r"PAGES_AUTO_STOP_IN:\s*[\"']?3 days", "branch previews must auto-stop"),
        (pages, r"PAGES_ENVIRONMENT_NAME:\s*[\"']?production", "production must use production environment"),
        (pages, r"PAGES_AUTO_STOP_IN:\s*[\"']?never", "production environment must not auto-stop"),
        (pages, r'preview_ref="\$\{CI_MERGE_REQUEST_SOURCE_BRANCH_NAME:-\$CI_COMMIT_REF_NAME\}"', "preview deploy must resolve branch and MR source refs"),
        (pages, r'CI_MERGE_REQUEST_SOURCE_PROJECT_URL', "fork previews must fetch from the MR source project"),
        (pages, r'preview_remote_ref=.*refresh_branch_ref', "preview deploy must resolve the refreshed source-project ref"),
        (pages, r'remote_sha=.*\$preview_remote_ref', "preview deploy must reject stale pipeline commits"),
        (pages, r"branch_preview_manifest_audit\.py --artifact-root public --manifest public/branches\.json", "pages job must validate root manifest paths"),
        (pages, r"branch_preview_manifest_audit\.py --artifact-root public --manifest \"public/\$CI_COMMIT_REF_SLUG/branches\.json\"", "pages job must validate branch foyer manifest paths"),
        (pages, r"--published-ref \"\$preview_ref=\$CI_COMMIT_REF_SLUG\"", "root manifest must list only the preview published in this artifact"),
        (test, r"allow_failure:\s*false", "test gate must block Pages deployment on required-tier failures"),
        (test, r"release_gate\.py --tier ship", "test job must run the shared ship gate"),
        (test, r'build_pages\.sh "\$CI_PROJECT_DIR/candidate"', "test job must build the Pages candidate without another worker stage"),
        (test, r"tar -czf validated-candidate\.tar\.gz -C candidate \.", "test job must archive the validated Pages candidate"),
        (test, r"- validated-candidate\.tar\.gz", "test job must hand the validated candidate archive to publication"),
        (pages, r"--archive validated-candidate\.tar\.gz --extract-to candidate", "pages job must validate and extract the tested candidate archive"),
        (pages, r'cp -a candidate/\. "public/\$CI_COMMIT_REF_SLUG/"', "preview publication must copy the tested candidate"),
        (gate, r'branch_preview_manifest_audit\.py", "--self-test"', "shared gate must self-test branch availability detection"),
        (smoke, r"needs:\s*\[\"pages\"\]", "live Pages smoke must wait for the deploy job"),
        (smoke, r'pages_base_url="\$\{CI_PAGES_URL/http:/https:\}"', "post-deploy job must normalize the GitLab-provided HTTP URL to HTTPS"),
        (smoke, r"branch_preview_manifest_audit\.py --base-url \"\$pages_base_url/\"", "post-deploy job must probe the canonical live Pages root"),
        (smoke, r'preview_ref="\$\{CI_MERGE_REQUEST_SOURCE_BRANCH_NAME:-\$CI_COMMIT_REF_NAME\}"', "branch smoke must resolve branch and MR source refs"),
        (smoke, r"--expect-preview \"\$preview_ref=\$CI_COMMIT_REF_SLUG\"", "branch smoke must require the deployed preview"),
        (smoke, r"--expect-git-sha \"\$CI_COMMIT_SHORT_SHA\"", "live Pages smoke must require the exact staged commit"),
        (smoke, r"--attempts 30 --delay 5", "live Pages smoke must tolerate deployment propagation"),
        (smoke, r"allow_failure:\s*false", "post-deploy Pages smoke must be blocking"),
        (human, r"resource_group:\s*pages-site", "human review must serialize with the shared Pages publisher"),
        (human, r'pages_base_url="\$\{CI_PAGES_URL/http:/https:\}"', "human review must normalize the GitLab-provided HTTP URL to HTTPS"),
        (human, r"branch_preview_manifest_audit\.py", "human review must recheck the live preview at approval time"),
        (human, r"--expect-preview \"\$preview_ref=\$CI_COMMIT_REF_SLUG\"", "human review must require its own branch preview"),
        (human, r"--expect-git-sha \"\$CI_COMMIT_SHORT_SHA\"", "human review must require the exact staged commit"),
        (human, r"Retry only the pages job", "stale human review must direct a targeted Pages restage"),
    ]
    for block, pattern, msg in checks:
        if block and not re.search(pattern, block):
            findings.append(msg)

    if _job_block(text, "pages_preview"):
        findings.append("classic GitLab Pages instance must not use pages_preview; only job name 'pages' can publish")
    if re.search(r"(?ms)^pages:\n(?P<body>.*?)(?=^[A-Za-z0-9_.-]+:\n|\Z)", text):
        if re.search(r"(?m)^[ ]{2}pages:", pages) or re.search(r"(?m)^[ ]{2}pages:\s*true", pages):
            findings.append("classic pages job must not use the newer pages: keyword on this GitLab instance")
    if re.search(r"pages:\n(?:[ ]{2,}.*\n)*?[ ]{4}path_prefix:", pages):
        findings.append("classic pages job must not use pages.path_prefix on this GitLab instance")
    if "expire_in: 3 days" not in pages:
        findings.append("pages job must keep 3-day downloadable artifact expiry")
    if re.search(r"(?m)^\s*- candidate/\s*$", test):
        findings.append("test job must not expose the unpacked candidate as a cross-job artifact")
    if not re.search(r"stages:\s*\[[^\]]*verify[^\]]*\]", text):
        findings.append("pipeline must retain a post-deploy verify stage")

    foyer = (_root() / "web" / "index.html").read_text(encoding="utf-8")
    if "b.preview_ready === true" not in foyer or 'method: "HEAD"' not in foyer:
        findings.append("foyer must require preview_ready and probe each branch target before showing it")

    if findings:
        print("ci_storage_audit: FAIL")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("ci_storage_audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
