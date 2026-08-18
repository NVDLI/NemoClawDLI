#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject GitLab CI trust-boundary drift before pipeline execution or merge."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROOT_CI = """# This root is intentionally inert and exact. Add repository tests under tests/ and
# register them in the release gate. Delivery, SCA, and internal privileged operations live in
# exact owner-gated modules.
include:
  - local: "/.gitlab/ci/core.yml"
  - local: "/.gitlab/ci/sca.yml"
  - local: "/.gitlab/ci/privileged.yml"
"""
SCA_JOBS = ("security_browser_sca", "security_sca", "security_python_sca")
PRIVILEGED_DIGESTS = {
    ".gitlab/ci/privileged.yml": "1b143eb94e21e2f2f5e68e8496146fc926bc6bbb86ccb237cfbe9e7baca7c9e0",
    ".gitlab/ci/privileged-child.yml": "f22f1b260e2370ceb763e42295653070a12a4761d746101bad1c5ee0244159ab",
}
OWNER_PATHS = (
    "/.gitlab-ci.yml",
    "/.gitlab/ci/",
    "/.gitlab/CODEOWNERS",
    "/scripts/validation/gitlab_ci_policy.py",
    "/scripts/validation/contribution_safety_audit.py",
    "/scripts/validation/gitlab_governance_audit.py",
    "/scripts/validation/release_gate.py",
    "/scripts/validation/reacs_registry.py",
    "/scripts/validation/reacs_registry.json",
    "/scripts/ci/",
    "/scripts/git-hooks/",
    "/.github/workflows/",
)


def finding(code: str, path: str, message: str, fix: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message, "fix": fix}


def read(root: Path, rel: str, out: list[dict[str, str]]) -> str:
    path = root / rel
    if not path.is_file():
        out.append(finding("missing-file", rel, "required CI policy file is missing", "restore the reviewed file"))
        return ""
    return path.read_text(encoding="utf-8")


def job_block(source: str, name: str) -> str:
    matches = list(re.finditer(rf"(?ms)^{re.escape(name)}:\n(.*?)(?=^[A-Za-z0-9_.-]+:\n|\Z)", source))
    return matches[-1].group(1) if matches else ""


def active_yaml(source: str) -> str:
    """Remove YAML-only comments before policy token checks."""
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#")) + "\n"


def duplicate_top_keys(source: str) -> list[str]:
    keys = re.findall(r"(?m)^([A-Za-z0-9_.-]+):(?:\s|$)", active_yaml(source))
    return sorted({key for key in keys if keys.count(key) > 1})


def composed_ci(root: Path = ROOT) -> str:
    """Return the reviewed local modules as the effective repository CI contract."""
    return "\n".join(
        (root / rel).read_text(encoding="utf-8")
        for rel in (".gitlab/ci/core.yml", ".gitlab/ci/sca.yml", ".gitlab/ci/privileged.yml")
    )


def require(source: str, token: str, code: str, path: str, out: list[dict[str, str]], fix: str) -> None:
    if token not in source:
        out.append(finding(code, path, f"required token is absent: {token}", fix))


def audit(root: Path = ROOT) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    root_ci = read(root, ".gitlab-ci.yml", out)
    core = read(root, ".gitlab/ci/core.yml", out)
    sca = read(root, ".gitlab/ci/sca.yml", out)
    privileged = read(root, ".gitlab/ci/privileged.yml", out)
    privileged_child = read(root, ".gitlab/ci/privileged-child.yml", out)
    owners = read(root, ".gitlab/CODEOWNERS", out)
    release_gate = read(root, "scripts/validation/release_gate.py", out)
    pages_builder = read(root, "scripts/build/build_pages.sh", out)

    for rel, source in ((".gitlab/ci/core.yml", core), (".gitlab/ci/sca.yml", sca)):
        for key in duplicate_top_keys(source):
            out.append(finding("duplicate-ci-key", rel, f"effective YAML key is repeated: {key}",
                               "keep one unambiguous definition for every CI job and root key"))
    for rel, expected in PRIVILEGED_DIGESTS.items():
        path = root / rel
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
        if actual != expected:
            out.append(finding(
                "privileged-ci-bytes", rel,
                "privileged CI differs from the exact mutation-reviewed contract",
                "review the complete privileged flow and update its policy digest in the same owner-approved change",
            ))
    core, sca = map(active_yaml, (core, sca))
    privileged_all = active_yaml(privileged + "\n" + privileged_child)

    if root_ci != ROOT_CI:
        out.append(finding(
            "root-ci-not-inert", ".gitlab-ci.yml",
            "root CI differs from the exact three-module manifest",
            "put jobs and policy in the owner-gated modules; register repository tests in the release gate",
        ))

    if any(re.search(r"(?m)^include:\s*$", source) for source in (core, sca)):
        out.append(finding("nested-ci-include", ".gitlab/ci/", "a CI module adds another include boundary",
                           "keep the complete include set visible in the inert root manifest"))
    for name in SCA_JOBS:
        if re.search(rf"(?m)^{re.escape(name)}:\s*$", core):
            out.append(finding("sca-job-in-core", ".gitlab/ci/core.yml", f"{name} is defined outside the SCA module",
                               "keep scanner jobs self-contained in .gitlab/ci/sca.yml"))

    for token in ("extends:", "!reference", "trigger:", "needs:\n    - project:"):
        if token in sca:
            out.append(finding("sca-cross-config-reference", ".gitlab/ci/sca.yml",
                               f"SCA module uses cross-configuration behavior: {token}",
                               "keep scanner setup and execution self-contained"))
    for token in (
        "inherit:\n    default: false\n    variables: false",
        "node:20-bookworm-slim@sha256:25070a03f077f5860e4f2db8d147380678ed40ead415a21eaffd5a6208f61948",
        "retry_cmd apt-get install -y -qq --no-install-recommends python3 python3-pip python3-venv ca-certificates curl git",
    ):
        require(sca, token, "sca-self-contained", ".gitlab/ci/sca.yml", out,
                "restore the isolated image, inheritance boundary, and explicit scanner prerequisites")

    optional_mr = """- if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
      when: manual
      allow_failure: true"""
    schedule = """- if: '$CI_PIPELINE_SOURCE == "schedule"'
      when: on_success
      allow_failure: false"""
    for name in SCA_JOBS:
        body = job_block(sca, name)
        if not body:
            out.append(finding("missing-sca-job", ".gitlab/ci/sca.yml", f"{name} is missing",
                               "restore the reviewed scanner job"))
            continue
        require(body, "<<: *sca_base", "sca-base-bypass", ".gitlab/ci/sca.yml", out,
                f"make {name} inherit the isolated SCA base")
        require(body, schedule, "sca-schedule", ".gitlab/ci/sca.yml", out,
                f"keep {name} automatic and blocking on scheduled advisory refreshes")
        require(body, optional_mr, "sca-manual-opt-in", ".gitlab/ci/sca.yml", out,
                f"keep {name} available but non-blocking on unrelated merge requests")

    for name, changed_input in (
        ("security_browser_sca", "scripts/browser-vendor/package-lock.json"),
        ("security_python_sca", "scripts/materials/requirements.lock"),
    ):
        body = job_block(sca, name)
        require(body, changed_input, "sca-change-trigger", ".gitlab/ci/sca.yml", out,
                f"run {name} automatically when its dependency graph changes")
        require(body, ".gitlab/ci/sca.yml", "sca-policy-trigger", ".gitlab/ci/sca.yml", out,
                f"run {name} automatically when scanner policy changes")
        for broad_path in ("- .gitlab-ci.yml", "- .gitlab/ci/core.yml"):
            if broad_path in body:
                out.append(finding("sca-broad-trigger", ".gitlab/ci/sca.yml",
                                   f"{name} is coupled to unrelated CI changes through {broad_path[2:]}",
                                   "trigger from the self-contained SCA module and dependency inputs"))

    security_source = job_block(sca, "security_sca")
    for changed_input in (
        ".gitlab-ci.yml", ".gitlab/ci/core.yml", ".gitlab/ci/privileged.yml",
        ".gitlab/ci/privileged-child.yml", "scripts/ci/**/*",
        "scripts/validation/gitlab_ci_policy.py", "scripts/validation/reacs_registry.json",
    ):
        require(security_source, changed_input, "sca-security-surface-trigger", ".gitlab/ci/sca.yml", out,
                "run the focused full-source scan automatically when a CI or privileged-operation boundary changes")

    for token in (
        "npm audit --prefix scripts/browser-vendor --package-lock-only",
        "npm audit --prefix .cache/runtime-npm-audit --package-lock-only --audit-level=moderate",
        "scripts/security/reports/runtime-npm-audit.json",
        "scripts/runtime/pnpm-lock.yaml",
        ".sca-tools-venv/bin/python -m pip install --require-hashes --no-deps --only-binary=:all: -q -r scripts/security/requirements-sca.lock",
        ".sca-tools-venv/bin/pip-audit -r scripts/materials/requirements.lock",
        "audit_sbom_policy.py --sbom",
        "scripts/compliance/resolve_sbom_licenses.py --input scripts/security/reports/python-materials/python-env.raw.cdx.json",
        "--sbom scripts/security/reports/python-materials/python-env.cdx.json",
    ):
        require(sca, token, "sca-required-command", ".gitlab/ci/sca.yml", out,
                "restore the locked dependency scan and SBOM policy command")

    if "security_image_sca:" in sca or "security_deep_sca:" in sca:
        out.append(finding("retired-sca-job", ".gitlab/ci/sca.yml", "obsolete image or workspace scan returned",
                           "scan only the distributed browser graph and pinned material tools"))

    bridge = job_block(active_yaml(privileged), "privileged_course_operation")
    for token in (
        "inherit:\n    default: false\n    variables: false",
        "strategy: depend", "yaml_variables: true", "pipeline_variables: false",
        'local: "/.gitlab/ci/privileged-child.yml"', "DLI_REQUEST_OP",
    ):
        require(bridge, token, "privileged-bridge", ".gitlab/ci/privileged.yml", out,
                "restore the runnerless closed-variable child-pipeline bridge")
    for forbidden in ("script:", "image:", "tags:", "environment:", "services:"):
        if forbidden in bridge:
            out.append(finding("privileged-bridge-runner", ".gitlab/ci/privileged.yml",
                               f"runnerless bridge gained execution authority: {forbidden}",
                               "keep the parent bridge runnerless and forward no pipeline variables"))

    privileged_jobs = (
        "privileged_acquire_candidate", "prepare_live_runtime", "live_candidate_interfaces",
        "live_interface_review", "cdn_prepare", "cdn_publish",
    )
    for name in privileged_jobs:
        body = job_block(active_yaml(privileged_child), name)
        if not body:
            out.append(finding("missing-privileged-job", ".gitlab/ci/privileged.yml", f"{name} is missing",
                               "restore the fixed internal GitLab operation"))
            continue
        require(body, "inherit:\n    default: false", "privileged-inheritance", ".gitlab/ci/privileged.yml", out,
                f"make {name} reject root defaults")
        require(body, "allow_failure: false", "privileged-fail-closed", ".gitlab/ci/privileged.yml", out,
                f"keep {name} blocking whenever an operator requests it")
    for token in ("extends:", "!reference", "trigger:", "services:", "cache:", "allow_failure: true", "set -x", "<<:"):
        if token in privileged_child:
            out.append(finding("privileged-expansion", ".gitlab/ci/privileged-child.yml",
                               f"privileged module uses forbidden extensibility or disclosure: {token}",
                               "keep each privileged job self-contained and fail-closed"))
    for token in (
        "-m scripts.ci.fetch_validated_candidate", "-m scripts.validation.pages_artifact_integrity",
        "-m scripts.ci.trusted_gitlab_context",
        "-m scripts.ci.live_interface_review", "--assert-capabilities /tmp/validated-candidate",
        "-m scripts.ci.prepare_cdn_publication",
        "-m scripts.validation.sensitive_content_audit --root /tmp/validated-candidate "
        "--publication-source-root .",
        "-m scripts.validation.sensitive_content_audit --root cdn/publication "
        "--publication-source-root .",
        "tags: [dli-cdn-publisher]", 'GIT_STRATEGY: "none"',
        "resource_group: dli-cdn-production", "environment:\n    name: dli-cdn-production",
        "/opt/dli-course-publisher/publish", "unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN",
    ):
        require(privileged_all, token, "privileged-boundary", ".gitlab/ci/privileged-child.yml", out,
                "restore exact artifact verification, protected environments, and the root-installed publisher")
    if re.search(r"\bpython3\s+scripts/[A-Za-z0-9_./-]+\.py\b", privileged_all):
        out.append(finding(
            "privileged-direct-python", ".gitlab/ci/privileged-child.yml",
            "privileged child executes a repository Python file outside package module resolution",
            "invoke every repository Python entry with python3 -m and its dotted module name",
        ))
    if re.search(r"\$\{?AWS_(?:ACCESS|SECRET|SESSION)", privileged_all):
        out.append(finding("injected-aws-credential", ".gitlab/ci/privileged.yml",
                           "publisher expands a pipeline-provided AWS credential",
                           "use only the devbox runner's ambient identity after unsetting injected AWS variables"))
    for token in ("aws s3 sync", "aws s3 rm", "--delete", "PUBLISH_BUCKET", "PUBLISH_PREFIX", "PUBLISH_COMMAND"):
        if token in privileged_all:
            out.append(finding("publisher-free-form", ".gitlab/ci/privileged.yml",
                               f"publisher exposes destructive or free-form authority: {token}",
                               "derive the fixed bucket and destination inside the root-owned publisher"))
    live = job_block(active_yaml(privileged_child), "live_interface_review")
    runtime_prepare = job_block(active_yaml(privileged_child), "prepare_live_runtime")
    candidate_live = job_block(active_yaml(privileged_child), "live_candidate_interfaces")
    acquisition = job_block(active_yaml(privileged_child), "privileged_acquire_candidate")
    cdn_prepare = job_block(active_yaml(privileged_child), "cdn_prepare")
    require(candidate_live, "-m scripts.ci.assert_unprivileged_environment", "candidate-secret-boundary",
            ".gitlab/ci/privileged.yml", out,
            "reject protected variables before any candidate interface is opened")
    if "LIVE_" in candidate_live or "COURSE_GITLAB_" in candidate_live or re.search(r"\bAWS_[A-Z0-9_]+", candidate_live):
        out.append(finding(
            "candidate-secret-scope", ".gitlab/ci/privileged.yml",
            "candidate interface job references a protected live or AWS variable",
            "keep credentials environment-scoped to the later trusted job; candidate code receives none",
        ))
    require(runtime_prepare, "-m scripts.ci.assert_unprivileged_environment", "runtime-secret-boundary",
            ".gitlab/ci/privileged-child.yml", out,
            "build browser runtime dependencies only in a credential-free job")
    if "scripts.validation.interface_inventory_browser_audit" in runtime_prepare or "validated-candidate" in runtime_prepare:
        out.append(finding(
            "candidate-runtime-producer", ".gitlab/ci/privileged-child.yml",
            "the executable runtime producer opens or consumes candidate content",
            "keep executable dependency artifacts in a distinct job that never opens candidate bytes",
        ))
    require(live, "trusted-runtime/node-modules.tar.gz", "live-runtime-artifact",
            ".gitlab/ci/privileged-child.yml", out,
            "provide the trusted live job's browser runtime from the isolated dependency job")
    require(cdn_prepare, "-m scripts.ci.assert_unprivileged_environment", "candidate-secret-boundary",
            ".gitlab/ci/privileged.yml", out,
            "keep publication preparation separate from both live and AWS credentials")
    require(acquisition, "environment:\n    name: dli-source-review", "acquisition-secret-boundary",
            ".gitlab/ci/privileged-child.yml", out,
            "keep GitLab metadata credentials only in the acquisition job")
    if "scripts.validation.interface_inventory_browser_audit" in acquisition:
        out.append(finding("candidate-in-acquisition", ".gitlab/ci/privileged-child.yml",
                           "candidate browser execution shares the metadata-token job",
                           "pass only verified artifacts to the credential-free candidate job"))
    require(live, "LIVE_NVIDIA_API_KEY_FILE", "live-file-secret", ".gitlab/ci/privileged.yml", out,
            "provide live credentials only as protected GitLab file variables")
    require(live, "LIVE_BUILD_API_KEY_FILE", "live-file-secret", ".gitlab/ci/privileged.yml", out,
            "provide live credentials only as protected GitLab file variables")
    require(live, "LIVE_CLAW_SESSION_1_FILE", "live-file-secret", ".gitlab/ci/privileged.yml", out,
            "provide live credentials only as protected GitLab file variables")
    require(live, "LIVE_CLAW_SESSION_2_FILE", "live-file-secret", ".gitlab/ci/privileged.yml", out,
            "keep the optional second launchable session in a separate protected GitLab file variable")
    if "scripts.ci.assert_unprivileged_environment" in live:
        out.append(finding(
            "live-secret-inversion", ".gitlab/ci/privileged.yml",
            "trusted live job invokes the candidate-only secret rejection guard",
            "run the no-secret guard only before candidate execution and verify protected files in the trusted live job",
        ))
    github_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((root / ".github/workflows").glob("*.y*ml"))
    ) if (root / ".github/workflows").is_dir() else ""
    for token in (
        "COURSE_OP", "dli-cdn-publisher", "LIVE_CLAW_SESSION", "PUBLISH_SOURCE_TEST_JOB_ID",
        "CANDIDATE_TEST_JOB_ID", "cdn.dli.learn.nvidia.com", "aws s3", "/opt/dli-course-publisher",
    ):
        if token in github_text:
            out.append(finding("github-privilege-copy", ".github/workflows/",
                               f"internal GitLab authority was copied into public GitHub workflow syntax: {token}",
                               "keep privileged live review and CDN publication internal to GitLab"))
    if re.search(r"(?m)(?:^|[\s'\"])(?:\./)?scripts/ci(?:/|\.|['\"])", github_text):
        out.append(finding("github-privilege-copy", ".github/workflows/",
                           "public GitHub workflow reaches the internal operations module",
                           "remove every direct or wrapped GitHub execution edge into scripts/ci"))

    for path in OWNER_PATHS:
        if not re.search(rf"(?m)^{re.escape(path)}\s+@\S+", owners):
            out.append(finding("missing-code-owner", ".gitlab/CODEOWNERS",
                               f"security-sensitive path lacks a named owner: {path}",
                               "assign a real GitLab user or group and require Code Owner approval on main"))
    require(release_gate, 'unit_test("gitlab_ci_policy")', "ci-policy-not-gated",
            "scripts/validation/release_gate.py", out,
            "run the mutation-tested CI policy in both fast and ship gates")
    require(release_gate, "PRIVILEGED_COURSE_OPS_TESTS", "privileged-policy-not-gated",
            "scripts/validation/release_gate.py", out,
            "run the artifact, request, and publisher boundary mutations in both fast and ship gates")
    require(core, 'validator_specialization_audit.py --commit-range', "specialization-range-not-gated",
            ".gitlab/ci/core.yml", out,
            "reject course-specific validator literals across the complete merge-request history")
    require(core, "sensitive_content_audit.py --root public --publication-source-root .",
            "pages-sensitive-boundary",
            ".gitlab/ci/core.yml", out,
            "scan the exact assembled GitLab Pages artifact before its publication handoff")
    require(release_gate, 'unit_test("artifact_link_audit")', "artifact-policy-not-gated",
            "scripts/validation/release_gate.py", out,
            "run the exhaustive artifact-link mutation suite in both fast and ship gates")
    require(pages_builder, 'artifact_link_audit.py" "$OUT"', "artifact-boundary-not-gated",
            "scripts/build/build_pages.sh", out,
            "reject every broken, missing, absolute, or deployment-root-escaping local URL before Pages upload")
    return out


def self_test() -> list[str]:
    files = {
        rel: (ROOT / rel).read_text(encoding="utf-8")
        for rel in (
            ".gitlab-ci.yml", ".gitlab/ci/core.yml", ".gitlab/ci/sca.yml", ".gitlab/ci/privileged.yml",
            ".gitlab/ci/privileged-child.yml",
            ".gitlab/CODEOWNERS", "scripts/validation/release_gate.py", "scripts/build/build_pages.sh",
            ".github/workflows/pages.yml",
        )
    }
    root_owner_line = next(line for line in files[".gitlab/CODEOWNERS"].splitlines()
                           if line.startswith("/.gitlab-ci.yml "))
    cases = (
        ("root-ci-not-inert", ".gitlab-ci.yml", ROOT_CI, ROOT_CI + "variables: {EVIL: 1}\n"),
        ("duplicate-ci-key", ".gitlab/ci/core.yml", "test:\n", "test:\n  image: alpine\n\ntest:\n"),
        ("nested-ci-include", ".gitlab/ci/core.yml", "stages: [test, deploy, verify, review]",
         "include:\n  - remote: https://example.invalid/ci.yml\nstages: [test, deploy, verify, review]"),
        ("sca-self-contained", ".gitlab/ci/sca.yml", "variables: false", "variables: true"),
        ("sca-base-bypass", ".gitlab/ci/sca.yml", "security_browser_sca:\n  <<: *sca_base",
         "security_browser_sca:\n  # isolated base removed"),
        ("sca-broad-trigger", ".gitlab/ci/sca.yml", "        - .gitlab/ci/sca.yml",
         "        - .gitlab-ci.yml"),
        ("sca-required-command", ".gitlab/ci/sca.yml", "audit_sbom_policy.py --sbom",
         "audit_sbom_policy.py --help"),
        ("sca-security-surface-trigger", ".gitlab/ci/sca.yml", "        - .gitlab/ci/privileged.yml",
         "        - docs/pages_deploy.md"),
        ("retired-sca-job", ".gitlab/ci/sca.yml", "security_python_sca:",
         "security_deep_sca:"),
        ("privileged-ci-bytes", ".gitlab/ci/privileged.yml", "strategy: depend", "strategy: mirror"),
        ("privileged-ci-bytes", ".gitlab/ci/privileged-child.yml", "allow_failure: false", "allow_failure: true"),
        ("privileged-ci-bytes", ".gitlab/ci/privileged-child.yml", "cdn_publish:\n", 'cdn_publish:\n\n"cdn_publish":\n  script: [\"id\"]\n'),
        ("privileged-ci-bytes", ".gitlab/ci/privileged-child.yml", "tags: [dli-cdn-publisher]", "tags: [pages]"),
        ("privileged-boundary", ".gitlab/ci/privileged-child.yml",
         "-m scripts.validation.sensitive_content_audit --root /tmp/validated-candidate "
         "--publication-source-root .",
         "-m scripts.validation.sensitive_content_audit --help"),
        ("privileged-boundary", ".gitlab/ci/privileged-child.yml",
         "-m scripts.validation.sensitive_content_audit --root cdn/publication "
         "--publication-source-root .",
         "-m scripts.validation.sensitive_content_audit --help"),
        ("privileged-direct-python", ".gitlab/ci/privileged-child.yml",
         "python3 -m scripts.ci.privileged_request", "python3 scripts/ci/privileged_request.py"),
        ("github-privilege-copy", ".github/workflows/pages.yml", "name:", "COURSE_OP:"),
        ("missing-code-owner", ".gitlab/CODEOWNERS", root_owner_line,
         "/.gitlab-ci.yml"),
        ("ci-policy-not-gated", "scripts/validation/release_gate.py", 'unit_test("gitlab_ci_policy")',
         'unit_test("repository_sync_audit")'),
        ("privileged-policy-not-gated", "scripts/validation/release_gate.py", "PRIVILEGED_COURSE_OPS_TESTS",
         "REPOSITORY_SYNC_TESTS"),
        ("specialization-range-not-gated", ".gitlab/ci/core.yml",
         "validator_specialization_audit.py --commit-range",
         "validator_specialization_audit.py --json"),
        ("pages-sensitive-boundary", ".gitlab/ci/core.yml",
         "sensitive_content_audit.py --root public --publication-source-root .",
         "sensitive_content_audit.py --help"),
        ("artifact-policy-not-gated", "scripts/validation/release_gate.py", 'unit_test("artifact_link_audit")',
         'unit_test("repository_sync_audit")'),
        ("artifact-boundary-not-gated", "scripts/build/build_pages.sh", 'artifact_link_audit.py" "$OUT"',
         'artifact_link_audit.py" "$OPTIONAL_OUT"'),
    )
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as directory:
        fixture = Path(directory)
        for rel, content in files.items():
            path = fixture / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        if audit(fixture):
            failures.append("clean CI policy fixture rejected")
        for expected, rel, old, new in cases:
            path = fixture / rel
            original = files[rel]
            if old not in original:
                failures.append(f"fixture token missing for {expected}")
                continue
            path.write_text(original.replace(old, new), encoding="utf-8")
            codes = {item["code"] for item in audit(fixture)}
            if expected not in codes:
                failures.append(f"mutation escaped detector: {expected}")
            path.write_text(original, encoding="utf-8")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = ([finding("self-test", "fixtures", failure, "repair the detector")
                 for failure in self_test()] if args.self_test else audit())
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, indent=2))
    elif findings:
        print(f"gitlab CI policy: FAIL ({len(findings)})")
        for item in findings:
            print(f"  [{item['code']}] {item['path']}: {item['message']}")
            print(f"    fix: {item['fix']}")
    else:
        print(f"gitlab CI policy: OK ({'mutation self-test' if args.self_test else 'repository'})")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
