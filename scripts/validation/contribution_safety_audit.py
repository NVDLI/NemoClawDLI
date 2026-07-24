#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Enforce low-friction idea intake and high-friction code/release boundaries."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
NVIDIA_APACHE_COPYRIGHT = "Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved."
DECISION_POLICY = {
    "default": "deny",
    "authorization_record": "external-not-repository",
    "repository_record": "approval-state-only",
    "private_details_permitted": False,
    "artifact_binding": "workflow-generated-provenance",
    "protected_environment_required": True,
    "independent_approver_required": True,
}
RELEASE_STATES = {
    "pending-osrb-approval": {
        "canonical_repository": "internal-gitlab",
        "external_mirror": "reserved-not-populated",
        "maintenance_status": "release-candidate",
        "community_intake": "disabled-pending-publication-approval",
    },
    "approved-for-publication": {
        "canonical_repository": "github",
        "external_mirror": "populated",
        "maintenance_status": "active",
        "community_intake": "ready",
    },
    "published": {
        "canonical_repository": "github",
        "external_mirror": "canonical-public",
        "maintenance_status": "active",
        "community_intake": "enabled",
    },
}

CONTRACT_FILES = (
    "RELEASE_STATUS.json",
    "CHANGELOG.md",
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "DCO.md",
    "SUPPORT.md",
    "AGENTS.md",
    "docs/release_playbook.md",
    "docs/release_artifacts.md",
    "docs/agent_process.md",
    "docs/course-prose-style.md",
    "scripts/compliance/docs/open_source_readiness.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/course-content.yml",
    ".github/ISSUE_TEMPLATE/runtime-deploy.yml",
    ".github/ISSUE_TEMPLATE/source-licensing.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/dependabot.yml",
    ".github/workflows/codeql.yml",
    ".github/workflows/dependency-review.yml",
    ".gitlab/merge_request_templates/Default.md",
    ".gitlab/issue_templates/Course content.md",
    ".gitlab/issue_templates/Runtime or deployment.md",
    ".gitlab/issue_templates/Source or licensing.md",
    ".github/workflows/pages.yml",
    ".github/workflows/release.yml",
    ".gitlab-ci.yml",
    ".gitlab/CODEOWNERS",
    ".gitlab/ci/core.yml",
    ".gitlab/ci/sca.yml",
    ".gitlab/ci/privileged.yml",
    "scripts/build/build_pages.sh",
    "scripts/build/install-hooks.sh",
    "scripts/build/build_branch_manifest.py",
    "scripts/build/package_release.py",
    "scripts/materials/pull_materials.py",
    "scripts/materials/requirements.lock",
    "scripts/security/audit_dependency_locks.py",
    "scripts/security/audit_sbom_policy.py",
    "scripts/compliance/sbom_evidence.py",
    "scripts/compliance/docs/sbom_evidence.json",
    "scripts/security/requirements-sca.lock",
    "scripts/git-hooks/pre-commit",
    "scripts/git-hooks/pre-push",
    "scripts/ci/assert_unprivileged_environment.py",
    "scripts/ci/devbox_cdn_publisher.py",
    "scripts/ci/fetch_validated_candidate.py",
    "scripts/ci/install_devbox_publisher.sh",
    "scripts/ci/live_interface_review.py",
    "scripts/ci/prepare_cdn_publication.py",
    "scripts/ci/privileged_request.py",
    "scripts/skills/gen_skill_hierarchy.py",
    "scripts/validation/SKILL.html",
    "scripts/validation/local_path_leak_audit.py",
    "scripts/validation/sensitive_content_audit.py",
    "scripts/validation/sensitive-content-policy.json",
    "scripts/validation/release_change_reminder.py",
    "scripts/validation/release_gate.py",
    "scripts/validation/reacs_registry.py",
    "scripts/validation/reacs_registry.json",
    "scripts/validation/validation_report_audit.py",
    "scripts/validation/pages_artifact_integrity.py",
    "scripts/validation/validate_bundle.py",
    "scripts/validation/gitlab_governance_audit.py",
    "scripts/validation/gitlab_ci_policy.py",
    "scripts/validation/interface_inventory_audit.py",
    "scripts/validation/interface_inventory_browser_audit.py",
    "scripts/validation/reacs_specialization_exceptions.json",
    "scripts/validation/validator_specialization_audit.py",
    "scripts/validation/container_boundary_audit.py",
    "web/nemoclaw/mats/_materials.json",
)

RETIRED_GUIDANCE = (
    "AGENT_QUICKSTART.md",
    "GOVERNANCE.json",
    "PHILOSOPHY.md",
    "QUALITY_DIRECTIVES.md",
    "RELEASE_STATUS.md",
    "docs/notebook_corruption_prevention.md",
)


def finding(code: str, path: str, message: str, fix: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message, "fix": fix}


def read(root: Path, rel: str, out: list[dict[str, str]]) -> str:
    path = root / rel
    if not path.is_file():
        out.append(finding("missing-file", rel, "required contribution boundary file is missing", f"restore {rel}"))
        return ""
    return path.read_text(encoding="utf-8")


def require(raw: str, token: str, rel: str, code: str, out: list[dict[str, str]], fix: str) -> None:
    if token not in raw:
        out.append(finding(code, rel, f"missing contract token: {token}", fix))


def top_permissions(workflow: str) -> str:
    match = re.search(r"(?ms)^permissions:\n((?:  [^\n]*\n)+)", workflow)
    return match.group(1) if match else ""


def workflow_job(workflow: str, name: str) -> str:
    """Return one top-level GitHub Actions job without relying on token counts."""
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow,
    )
    return match.group(0) if match else ""


def audit_workflow_pins(
    root: Path, text_overrides: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    overrides = text_overrides or {}
    for path in sorted((root / ".github/workflows").glob("*.yml")):
        rel = path.relative_to(root).as_posix()
        raw = overrides[rel] if rel in overrides else path.read_text(encoding="utf-8")
        for line_no, line in enumerate(raw.splitlines(), 1):
            action = re.search(r"\buses:\s*([^\s]+)", line)
            if action and not action.group(1).startswith("./"):
                ref = action.group(1).rsplit("@", 1)[-1]
                if not re.fullmatch(r"[0-9a-f]{40}", ref):
                    out.append(finding("mutable-action-ref", rel,
                                       f"line {line_no} action ref is not a full commit SHA: {action.group(1)}",
                                       "pin the reviewed action release to its immutable 40-character commit SHA"))
                if not re.search(r"#\s*v?[0-9]+(?:\.[0-9]+){1,2}\s*$", line):
                    out.append(finding("action-version-comment", rel,
                                       f"line {line_no} pinned action lacks a readable release comment",
                                       "retain the reviewed release as a trailing comment beside the SHA"))
            if re.search(r"\b(?:python3?\s+-m\s+)?pip\s+install\b", line):
                if not re.search(r"(?:--requirement|-r)\s+[^\s]+\.lock\b", line):
                    out.append(finding("unpinned-workflow-install", rel,
                                       f"line {line_no} installs Python packages without a reviewed lock",
                                       "install a scope-specific requirements.lock file instead of ad hoc package arguments"))
    return out


def release_status_findings(status: dict) -> list[dict[str, str]]:
    """Validate the public-safe lifecycle state without importing private approvals."""
    out: list[dict[str, str]] = []
    expected_common = {
        "schema": "nemoclaw-release-status/1",
        "external_repository": "https://github.com/NVDLI/NemoClawDLI",
        "target_license": "Apache-2.0",
    }
    for key, expected in expected_common.items():
        if status.get(key) != expected:
            out.append(finding(
                "release-status", "RELEASE_STATUS.json",
                f"{key} must be {expected!r}",
                "restore the reviewed public release contract",
            ))
    state = status.get("publication_state")
    expected_state = RELEASE_STATES.get(str(state))
    if expected_state is None:
        out.append(finding(
            "release-status", "RELEASE_STATUS.json",
            f"unsupported publication_state: {state!r}",
            "use a defined release lifecycle state",
        ))
    else:
        for key, expected in expected_state.items():
            if status.get(key) != expected:
                out.append(finding(
                    "release-status", "RELEASE_STATUS.json",
                    f"{key} must be {expected!r} when publication_state is {state!r}",
                    "change the lifecycle state and its dependent fields together",
                ))
    if status.get("decision_policy") != DECISION_POLICY:
        out.append(finding(
            "decision-policy", "RELEASE_STATUS.json",
            "release decision policy is missing or weakened",
            "restore the external authorization, protected-environment, provenance, and independence contract",
        ))
    if "publication_decision" in status:
        out.append(finding(
            "private-decision-record", "RELEASE_STATUS.json",
            "private approval details or placeholders must not be stored in the public repository",
            "retain only publication_state; keep the authorization record in its governing system",
        ))
    return out


def audit_publication_approval(root: Path = ROOT) -> list[dict[str, str]]:
    try:
        status = json.loads((root / "RELEASE_STATUS.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [finding("publication-approval", "RELEASE_STATUS.json",
                        "publication state cannot be read",
                        "restore the release status before any external write")]
    if status.get("publication_state") not in {"approved-for-publication", "published"}:
        return [finding("publication-approval", "RELEASE_STATUS.json",
                        "external publication is not approved",
                        "complete the governing approval, then update only the public-safe release state")]
    return release_status_findings(status)


def audit_repo(
    root: Path = ROOT, *, text_overrides: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    overrides = text_overrides or {}
    docs = {rel: overrides[rel] if rel in overrides else read(root, rel, out)
            for rel in CONTRACT_FILES}
    out.extend(audit_workflow_pins(root, overrides))
    for rel in RETIRED_GUIDANCE:
        if (root / rel).exists():
            out.append(finding("retired-guidance", rel,
                               "redundant guidance surface was restored",
                               "put the rule in its canonical owner and remove this file"))

    try:
        status = json.loads(docs["RELEASE_STATUS.json"])
    except (TypeError, json.JSONDecodeError):
        status = {}
        out.append(finding("release-status-json", "RELEASE_STATUS.json",
                           "release status is not valid JSON",
                           "restore the machine-readable release status contract"))
    out.extend(release_status_findings(status))
    notice_required = status.get("notice_required")
    if not isinstance(notice_required, bool):
        out.append(finding("notice-state", "RELEASE_STATUS.json",
                           "notice_required must be a boolean",
                           "record whether required downstream attributions exist"))
    elif notice_required != (root / "NOTICE.md").is_file():
        out.append(finding("notice-state", "NOTICE.md",
                           "NOTICE presence disagrees with RELEASE_STATUS.json",
                           "add NOTICE only for required attributions and update notice_required together"))

    for rel in ("README.md", "CONTRIBUTING.md",
                "docs/release_playbook.md", "scripts/compliance/docs/open_source_readiness.md"):
        require(re.sub(r"\s+", " ", docs[rel]), "approved for public release", rel,
                "release-status-language", out,
                "state the public-safe release authorization without copying private evidence")
    license_header = re.sub(r"\s+", " ", docs["LICENSE"]).strip()
    expected_license_header = (
        NVIDIA_APACHE_COPYRIGHT + " Apache License Version 2.0, January 2004"
    )
    if not license_header.startswith(expected_license_header):
        out.append(finding(
            "root-license", "LICENSE",
            "root LICENSE lacks the NVIDIA copyright followed by the canonical Apache License 2.0 header",
            "restore the reviewed NVIDIA copyright and Apache License 2.0 text at the root LICENSE path",
        ))
    require(docs["CODE_OF_CONDUCT.md"], "private content-reporting flow", "CODE_OF_CONDUCT.md",
            "conduct-report-route", out, "retain a public-safe, non-Issue conduct reporting route")
    require(docs["CODE_OF_CONDUCT.md"], "must not decide its outcome", "CODE_OF_CONDUCT.md",
            "conduct-recusal", out, "require recusal when a maintainer is named in a report")
    require(docs["SUPPORT.md"], "Triage is best-effort", "SUPPORT.md", "support-boundary", out,
            "state the support level without promising an unstaffed SLA")
    require(docs["SUPPORT.md"], "[#ask-security](https://nvidia.slack.com/archives/CAHCG5005)",
            "SUPPORT.md", "product-security-question-route", out,
            "route general employee product-security questions to #ask-security without replacing private vulnerability intake")
    require(docs["SUPPORT.md"], "Breaking changes and retirement decisions", "SUPPORT.md",
            "lifecycle-boundary", out, "document change, retirement, and archival expectations")
    require(docs["README.md"], "may approve its own protected merge or release", "README.md",
            "independent-review", out, "keep independent review explicit in role authority")
    require(docs["README.md"], "approval does not replace a missing control", "README.md",
            "approval-not-control", out, "keep unresolved release risk blocked until defended or deliberately accepted")
    require(docs["DCO.md"], "Developer Certificate of Origin 1.1", "DCO.md", "dco-policy", out,
            "document the inbound signoff policy and authoritative DCO version")
    require(docs["DCO.md"], "git commit --signoff", "DCO.md", "dco-repair", out,
            "give contributors an exact signoff command and repair path")
    require(docs["DCO.md"], "host-generated squash or merge commit", "DCO.md",
            "dco-stacked-merge", out,
            "prevent stacked proposal merges from replacing signed commits with unsigned generated commits")
    require(docs["CONTRIBUTING.md"], "stacked merge request", "CONTRIBUTING.md",
            "contributor-stacked-merge", out,
            "put the signed-commit preservation rule in contributor first-touch guidance")
    require(docs["CONTRIBUTING.md"], "Human review identifies accountability but is not a compensating",
            "CONTRIBUTING.md", "approval-not-control", out,
            "state that review ownership does not replace an enforceable defense")
    require(docs["CONTRIBUTING.md"], "does not require a separate contributor license agreement",
            "CONTRIBUTING.md", "cla-applicability", out,
            "state why Apache-2.0 plus DCO does not require a separate CLA")

    require(docs["CONTRIBUTING.md"], "Required CI and protected refs remain authoritative", "CONTRIBUTING.md",
            "hook-authority", out, "explain that required CI and protected refs remain authoritative")
    require(docs["CONTRIBUTING.md"], "Contributor credit and localization ownership",
            "CONTRIBUTING.md", "contributor-credit-policy", out,
            "document public Changelog credit and locale prose ownership")
    require(docs["CONTRIBUTING.md"], "Localization-Review:", "CONTRIBUTING.md",
            "localization-review-policy", out,
            "document the reviewer trailer for coordinated canonical and locale prose changes")
    require(docs["docs/agent_process.md"], "Preserve contributor and locale ownership",
            "docs/agent_process.md", "agent-localization-ownership", out,
            "keep contributor credit and locale ownership in the agent handoff checklist")
    require(docs["docs/agent_process.md"], "A human referral is not a defense",
            "docs/agent_process.md", "approval-not-control", out,
            "require an enforceable defense or a validated evidence-bound decision")
    require(docs["docs/release_playbook.md"], "Protected approval identifies who is accountable; it is not a compensating control",
            "docs/release_playbook.md", "approval-not-control", out,
            "keep plain approval from bypassing unresolved release controls")
    require(docs["docs/course-prose-style.md"], "Course prose writing contract",
            "docs/course-prose-style.md", "course-prose-contract", out,
            "keep durable learner-facing prose rules in one neutral contract")
    require(docs["docs/course-prose-style.md"], "Automated signals identify passages",
            "docs/course-prose-style.md", "prose-review-judgment", out,
            "state that automated prose signals require contextual human disposition")
    require(docs["docs/course-prose-style.md"], "Locale ownership",
            "docs/course-prose-style.md", "prose-locale-ownership", out,
            "preserve language-review ownership in the prose contract")
    require(docs["AGENTS.md"], "Treat code contribution as an untrusted proposal", "AGENTS.md",
            "agent-boundary", out, "put the trust boundary in the first agent beacon")
    require(docs["AGENTS.md"], "Every proposed commit", "AGENTS.md", "agent-dco", out,
            "put DCO signoff in the cross-harness agent entry point")

    issue_cfg = docs[".github/ISSUE_TEMPLATE/config.yml"]
    require(issue_cfg, "blank_issues_enabled: false", ".github/ISSUE_TEMPLATE/config.yml",
            "issue-structured", out, "keep structured issue intake enabled")
    require(issue_cfg, "/discussions", ".github/ISSUE_TEMPLATE/config.yml", "discussion-route", out,
            "route broad ideas and questions to Discussions")
    require(issue_cfg, "https://github.com/NVDLI/NemoClawDLI/discussions",
            ".github/ISSUE_TEMPLATE/config.yml", "external-repository", out,
            "route Discussions to the reserved NVDLI/NemoClawDLI repository")
    for rel in (".github/ISSUE_TEMPLATE/course-content.yml",
                ".github/ISSUE_TEMPLATE/runtime-deploy.yml",
                ".github/ISSUE_TEMPLATE/source-licensing.yml"):
        require(docs[rel], "static `web/nemoclaw/` course", rel, "issue-production-scope", out,
                "describe the static browser course without local CPU-service assumptions")
    required_sections = (
        "## Issue link", "## Surfaces touched", "## Blast radius checked",
        "## Validation evidence", "## Human ownership", "## Risk and rollback", "## Out of scope",
    )
    for rel in (".github/PULL_REQUEST_TEMPLATE.md", ".gitlab/merge_request_templates/Default.md"):
        for section in required_sections:
            require(docs[rel], section, rel, "submission-template", out,
                    f"add the required {section} section")
        require(docs[rel], "host-generated squash", rel, "stacked-submission-template", out,
                "require a signed-commit preservation plan for stacked proposals")
        require(docs[rel], "localized learner prose changed", rel,
                "localization-ownership-template", out,
                "ask who reviewed localized prose and where the contributor is credited")
        require(docs[rel], "review text is not a compensating control", rel,
                "submission-risk-decision", out,
                "require the exact artifact-bound decision fields when unresolved risk is accepted")
    retired_scope_tokens = (
        "`cpu/`", "`workspace/`", "`deploy/`", "Shared service stack",
        "Compose or nginx deployment", "Local authoring services",
    )
    scope_templates = (
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/course-content.yml",
        ".github/ISSUE_TEMPLATE/runtime-deploy.yml",
        ".github/ISSUE_TEMPLATE/source-licensing.yml",
        ".gitlab/merge_request_templates/Default.md",
        ".gitlab/issue_templates/Course content.md",
        ".gitlab/issue_templates/Runtime or deployment.md",
        ".gitlab/issue_templates/Source or licensing.md",
    )
    for rel in scope_templates:
        stale = [token for token in retired_scope_tokens if token in docs[rel]]
        if stale:
            out.append(finding(
                "retired-runtime-scope", rel,
                "retired repository runtime appears in contribution intake: " + ", ".join(stale),
                "describe host tooling, static delivery, and external runtime integration only",
            ))
    gitlab_template = docs[".gitlab/merge_request_templates/Default.md"]
    missing_in_window = [section for section in ("## Summary", *required_sections)
                         if section not in gitlab_template[:2700]]
    if missing_in_window:
        out.append(finding("gitlab-description-window", ".gitlab/merge_request_templates/Default.md",
                           "required headings fall outside GitLab's CI description window: "
                           + ", ".join(missing_in_window),
                           "keep the complete submission gate block within the first 2700 characters"))

    pages = docs[".github/workflows/pages.yml"]
    build_pages = docs["scripts/build/build_pages.sh"]
    require(build_pages, 'python3 "$T1/scripts/validation/validate_bundle.py" --scope ship',
            "scripts/build/build_pages.sh", "pages-fresh-validation-report", out,
            "regenerate validation by default when no trusted same-commit report is supplied")
    require(build_pages, 'validation_report_audit.py"',
            "scripts/build/build_pages.sh", "pages-report-reuse-audit", out,
            "validate schema, commit, scope, and required results before report reuse")
    require(build_pages,
            'if [ "$REUSE_VALIDATION" = "1" ] && [ "$PULL_MATERIALS" != "0" ]; then',
            "scripts/build/build_pages.sh", "pages-report-reuse-immutable", out,
            "prevent live material writes before auditing a same-commit report")
    require(build_pages, "-path 'web/nemoclaw/standalone' -prune",
            "scripts/build/build_pages.sh", "pages-source-mirror-prunes-generated", out,
            "exclude ignored standalone build output from the validated-source mirror")
    if re.search(r"validate_bundle\.py[^\n]*\|\|\s*true", build_pages):
        out.append(finding("pages-validation-fail-open", "scripts/build/build_pages.sh",
                           "Pages can retain and publish a stale validation report after refresh failure",
                           "fail the build when the current-tree report cannot be regenerated"))
    if re.search(r"validation_report_audit\.py[^\n]*(?:\|\|\s*true|&&\s*true)", build_pages):
        out.append(finding("pages-report-reuse-fail-open", "scripts/build/build_pages.sh",
                           "Pages can reuse a report after its trust audit fails",
                           "make same-commit report verification a required build step"))
    release_gate = docs["scripts/validation/release_gate.py"]
    fast_gate = re.search(r"(?ms)^FAST_COMMANDS:.*?(?=^SHIP_COMMANDS:)", release_gate)
    ship_gate = re.search(r"(?ms)^SHIP_COMMANDS:.*?(?=^# Mutation suites)", release_gate)
    fast_gate_text = fast_gate.group(0) if fast_gate else ""
    ship_gate_text = ship_gate.group(0) if ship_gate else ""
    if 'py("scripts/materials/pull_materials.py", "--verify-committed")' not in fast_gate_text:
        out.append(finding("shared-material-provenance", "scripts/validation/release_gate.py",
                           "fast gate lacks network-free committed material verification",
                           "verify committed material snapshots without network access from every shared gate"))
    if ('py("scripts/materials/pull_materials.py", "--verify-committed")' not in ship_gate_text
            or 'unit_test("materials")' not in ship_gate_text):
        out.append(finding("shared-material-selftest", "scripts/validation/release_gate.py",
                           "ship gate lacks material verification or its mutation fixtures",
                           "prove retry classification and provenance tamper detection from the ship gate"))
    local_path_selftest = 'unit_test("local_path_leak_audit")'
    if local_path_selftest not in fast_gate_text or local_path_selftest not in ship_gate_text:
        out.append(finding("shared-local-path-selftest", "scripts/validation/release_gate.py",
                           "fast or ship gate lacks workstation-path mutation coverage",
                           "run workstation-path mutations from both shared gate tiers"))
    sensitive_selftest = 'unit_test("sensitive_content_audit")'
    if sensitive_selftest not in fast_gate_text or sensitive_selftest not in ship_gate_text:
        out.append(finding("shared-sensitive-content", "scripts/validation/release_gate.py",
                           "fast or ship gate lacks sensitive-content mutation coverage",
                           "run sensitive-content mutations from both shared tiers; validate_bundle owns the tree scan"))
    reminder_selftest = 'unit_test("release_change_reminder")'
    if reminder_selftest not in fast_gate_text or reminder_selftest not in ship_gate_text:
        out.append(finding("shared-release-reminder", "scripts/validation/release_gate.py",
                           "fast or ship gate lacks release follow-up classifier mutations",
                           "run the release-change reminder self-test from both shared gate tiers"))
    for token, code, fix in (
        ('py("scripts/validation/contribution_safety_audit.py", "--self-test")',
         "shared-safety-gate",
         "run contribution-boundary mutations and emit its report from the shared gate"),
        ("CONTRIBUTION_LANGUAGE_OWNERSHIP_TESTS,",
         "shared-language-ownership-test",
         "run the standard visible-prose ownership tests from the shared gate"),
        ("docs/validation/contribution-safety.json", "shared-safety-report",
         "retain machine-readable contribution-boundary evidence in the shared gate"),
        ('py("scripts/build/package_release.py", "--self-test")', "shared-package-selftest",
         "test deterministic release packaging from the shared gate"),
        ('py("scripts/security/audit_sbom_policy.py", "--self-test")',
         "shared-sbom-policy-selftest",
         "prove the SBOM policy detector from the shared gate"),
        ('py("scripts/security/audit_dependency_locks.py", "--self-test")',
         "shared-lock-selftest",
         "prove dependency-lock mutations from the shared gate"),
    ):
        require(ship_gate_text, token, "scripts/validation/release_gate.py", code, out, fix)
    report_selftest = 'unit_test("validation_report_audit")'
    if report_selftest not in fast_gate_text or report_selftest not in ship_gate_text:
        out.append(finding("shared-report-reuse-selftest", "scripts/validation/release_gate.py",
                           "fast or ship gate lacks report-reuse mutation coverage",
                           "prove stale, failed, and mismatched reports from both shared tiers"))
    artifact_selftest = 'unit_test("pages_artifact_integrity")'
    if artifact_selftest not in fast_gate_text or artifact_selftest not in ship_gate_text:
        out.append(finding("shared-pages-artifact-selftest", "scripts/validation/release_gate.py",
                           "fast or ship gate lacks Pages artifact-integrity mutation coverage",
                           "prove artifact substitution, remote execution, and manifest mutations from both shared tiers"))
    if "HARNESS_CONTRACT" not in fast_gate_text or "HARNESS_CONTRACT" not in ship_gate_text:
        out.append(finding(
            "shared-standard-test-contract", "scripts/validation/release_gate.py",
            "fast or ship gate lacks standard-framework test-harness enforcement",
            "run the unittest harness contract from both shared tiers",
        ))
    for token, code, fix in (
        ('"--changed-since"', "shared-change-aware-gate", "retain fail-closed change-aware mutation selection"),
        ('"--timing-report"', "shared-gate-timing", "retain per-command latency evidence for CI optimization"),
        ('"--reuse-success"', "shared-local-reuse", "retain identical-clean-commit local success reuse"),
    ):
        require(release_gate, token, "scripts/validation/release_gate.py", code, out, fix)
    require(pages, "  pull_request:\n", ".github/workflows/pages.yml", "github-pr-trigger", out,
            "run the required static gate on pull_request")
    if "pull_request_target:" in pages:
        out.append(finding("unsafe-pr-trigger", ".github/workflows/pages.yml",
                           "pull_request_target may execute untrusted fork code with base-repo authority",
                           "use pull_request with a read-only token"))
    perms = top_permissions(pages)
    if "contents: read" not in perms or "pages: write" in perms or "id-token: write" in perms:
        out.append(finding("github-global-permissions", ".github/workflows/pages.yml",
                           "workflow-level permissions are not read-only",
                           "keep contents: read globally and grant Pages writes only to the deploy job"))
    production_condition = "if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'"
    for job_name in ("build-and-verify", "rebuild-for-comparison", "compare-builds", "attest-provenance", "deploy"):
        block = workflow_job(pages, job_name)
        if production_condition not in block:
            out.append(finding("pr-deploy-boundary", ".github/workflows/pages.yml",
                               f"production job {job_name} is not excluded from pull requests",
                               "bind every production artifact and deploy job to non-PR main runs"))
            out.append(finding("pages-main-only", ".github/workflows/pages.yml",
                               f"production job {job_name} is not bound to refs/heads/main",
                               "bind every production artifact and deploy job to non-PR main runs"))
    require(pages, "release_gate.py --tier ship", ".github/workflows/pages.yml",
            "github-safety-selftest", out, "run detector mutations in GitHub CI")
    require(pages, "pages_artifact_integrity.py --source-root .", ".github/workflows/pages.yml",
            "github-source-resource-preflight", out,
            "bound proposed source before dependency installation and expensive analysis")
    require(pages, '--changed-since "$GATE_BASE"', ".github/workflows/pages.yml",
            "github-change-aware-gate", out, "skip only unaffected mutation fixtures on proposal commits")
    require(pages, "--timing-report docs/validation/release-gate-timings.json",
            ".github/workflows/pages.yml", "github-gate-timing", out,
            "retain per-command gate timing evidence")
    test_job = workflow_job(pages, "test")
    browser_runtime_install = "pnpm install --frozen-lockfile --ignore-scripts"
    browser_runtime_context = (
        "working-directory: scripts/runtime",
        browser_runtime_install,
    )
    if any(token not in test_job for token in browser_runtime_context):
        out.append(finding(
            "github-browser-runtime-lock", ".github/workflows/pages.yml",
            "the GitHub test job does not install the nested pinned host-browser API",
            "run pnpm from scripts/runtime with --frozen-lockfile before the shared ship gate",
        ))
    elif test_job.index(browser_runtime_install) > test_job.index("release_gate.py --tier ship"):
        out.append(finding(
            "github-browser-runtime-order", ".github/workflows/pages.yml",
            "the pinned host-browser API is installed after Chromium-backed validation runs",
            "install the pinned browser API before the shared ship gate",
        ))
    for job_name in ("test", "build-and-verify"):
        if 'node-version: "24"' not in workflow_job(pages, job_name):
            out.append(finding(
                "github-node-runtime", ".github/workflows/pages.yml",
                f"GitHub job {job_name} does not use the supported Node.js 24 runtime",
                "run GitHub browser validation and assembly on Node.js 24",
            ))
    for job_name in ("build-and-verify", "rebuild-for-comparison"):
        block = workflow_job(pages, job_name)
        require(block, "BUILD_PAGES_REUSE_VALIDATION=1", ".github/workflows/pages.yml",
                "github-report-reuse", out,
                f"make {job_name} consume the required same-commit gate report")
        require(block, "BUILD_PAGES_PULL_MATERIALS=0", ".github/workflows/pages.yml",
                "github-immutable-report-reuse", out,
                f"make {job_name} assemble only committed material snapshots")
    require(pages, "contribution_safety_audit.py --require-publication-approved",
            ".github/workflows/pages.yml", "publication-deploy-guard", out,
            "refuse external Pages deployment until publication is approved")
    require(pages, "needs: [build-and-verify, rebuild-for-comparison]", ".github/workflows/pages.yml",
            "github-reviewed-artifact-handoff", out,
            "make provenance consume canonical and independently rebuilt artifacts")
    for token in (
        "actions/attest@a1948c3f048ba23858d222213b7c278aabede763",
        "subject-path: reviewed-pages/pages-sha256.txt",
        "compare-builds:",
        "attest-provenance:",
        "needs: compare-builds",
        "needs: attest-provenance",
        "pages-reviewed-manifest-${{ github.sha }}",
        "pages-comparison-${{ github.sha }}",
        "cmp reviewed-public/pages-sha256.txt",
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/pages.yml"',
        '--source-digest "$GITHUB_SHA" --source-ref "$GITHUB_REF"',
        "--deny-self-hosted-runners",
    ):
        require(pages, token, ".github/workflows/pages.yml", "github-pages-provenance", out,
                f"retain pre-authority Pages provenance control: {token}")
    signing_tokens = ("id-token: write", "attestations: write", "artifact-metadata: write")
    for job_name in ("build-and-verify", "rebuild-for-comparison", "compare-builds"):
        block = workflow_job(pages, job_name)
        for token in signing_tokens:
            if token in block:
                out.append(finding(
                    "github-pages-build-authority", ".github/workflows/pages.yml",
                    f"artifact builder {job_name} has signing authority: {token}",
                    "keep artifact generation unable to mint attestations or deployment identity",
                ))
        if "pip install" in block or "npm ci" in block:
            out.append(finding(
                "github-pages-build-dependency-isolation", ".github/workflows/pages.yml",
                f"Pages assembly job {job_name} installs executable package dependencies",
                "install dependencies only in validation; assemble from source and retained evidence",
            ))
    for token in signing_tokens:
        require(workflow_job(pages, "attest-provenance"), token,
                ".github/workflows/pages.yml", "github-pages-provenance-authority", out,
                f"grant {token} only to the post-build Pages provenance job")
    signing_block = workflow_job(pages, "attest-provenance")
    if "actions/checkout@" in signing_block or "scripts/" in signing_block:
        out.append(finding(
            "github-pages-signing-source-execution", ".github/workflows/pages.yml",
            "the provenance job can execute repository-controlled source while holding signing authority",
            "pass only the reviewed manifest into a no-checkout provenance job",
        ))
    deploy_block = workflow_job(pages, "deploy")
    if "actions/checkout@" in deploy_block or "run:" in deploy_block or "scripts/" in deploy_block:
        out.append(finding(
            "github-pages-deploy-source-execution", ".github/workflows/pages.yml",
            "the deployment job can execute repository-controlled source while holding deployment authority",
            "make the protected deploy job invoke only the pinned deploy action",
        ))
    require(pages, "name: github-pages", ".github/workflows/pages.yml",
            "github-pages-review-environment", out,
            "gate the deploy job behind the protected github-pages environment")
    require(pages, "runtime_integration_browser_audit.py --site-root public --timeout-ms 180000",
            ".github/workflows/pages.yml", "github-pages-browser-review", out,
            "exercise the generated course artifact in Chromium before requesting deployment approval")
    require(pages, "--write-manifest public/pages-sha256.txt",
            ".github/workflows/pages.yml", "github-pages-artifact-integrity", out,
            "hash and inspect the generated Pages tree before uploading it")
    for path, workflow in (
        (".github/workflows/pages.yml", pages),
        (".github/workflows/release.yml", docs[".github/workflows/release.yml"]),
    ):
        if "GITHUB_SHA::7" in workflow:
            out.append(finding(
                "artifact-full-commit-binding", path,
                "artifact validation abbreviates the source commit identity",
                "bind generated reports, manifests, and attestations to the full GITHUB_SHA",
            ))
    for job_name in ("compare-builds", "verify-deployment"):
        if "--check-manifest reviewed-public/pages-sha256.txt" not in workflow_job(pages, job_name):
            out.append(finding(
                "github-pages-artifact-reverification", ".github/workflows/pages.yml",
                f"job {job_name} does not verify the reviewed Pages manifest",
                "reverify the artifact before authority and against the live site",
            ))
    require(pages, "--submission-env CONTRIBUTION_BODY", ".github/workflows/pages.yml",
            "github-submission-contract", out, "validate the live pull-request body")
    require(pages, "--commit-range \"$DCO_RANGE\"", ".github/workflows/pages.yml",
            "github-dco-check", out, "validate every pull-request commit signoff")
    require(pages, 'local_path_leak_audit.py --commit-range "$PATH_RANGE"',
            ".github/workflows/pages.yml", "github-local-path-range", out,
            "reject contributor-local additions in every pull-request commit")
    require(pages, "sensitive_content_audit.py --submission-env SENSITIVE_TITLE",
            ".github/workflows/pages.yml", "github-sensitive-submission", out,
            "scan pull-request title, body, and source ref from the webhook event")
    require(pages, 'sensitive_content_audit.py --commit-range "$SENSITIVE_RANGE"',
            ".github/workflows/pages.yml", "github-sensitive-range", out,
            "reject restricted details in every pull-request commit")
    require(pages, 'release_change_reminder.py --commit-range "$RELEASE_CHANGE_RANGE"',
            ".github/workflows/pages.yml", "github-release-reminder", out,
            "show external release follow-ups from the pull-request diff")
    if pages.count("scripts/materials/requirements.lock") != 1:
        out.append(finding("github-material-lock", ".github/workflows/pages.yml",
                           "the live material check must install tooling once from the reviewed lock",
                           "install scripts/materials/requirements.lock in the test job only"))
    if not re.search(
        r"pip install[^\n]*--no-deps[^\n]*--only-binary=:all:[^\n]*scripts/materials/requirements\.lock",
        workflow_job(pages, "test"),
    ):
        out.append(finding(
            "github-binary-lock-install", ".github/workflows/pages.yml",
            "Pages validation may resolve undeclared dependencies or execute a source build",
            "install the complete material lock with --no-deps --only-binary=:all:",
        ))
    for rel in (".github/workflows/pages.yml", ".github/workflows/release.yml",
                ".github/workflows/codeql.yml", ".github/workflows/dependency-review.yml"):
        checkout_count = docs[rel].count("uses: actions/checkout@")
        hardened_count = docs[rel].count("persist-credentials: false")
        if hardened_count < checkout_count:
            out.append(finding("checkout-credential", rel,
                               f"{checkout_count - hardened_count} checkout step(s) persist credentials",
                               "set persist-credentials: false on every checkout step"))

    release = docs[".github/workflows/release.yml"]
    require(release, "pages_artifact_integrity.py --source-root .", ".github/workflows/release.yml",
            "release-source-resource-preflight", out,
            "bound release source before dependency installation and expensive analysis")
    require(release, "  workflow_dispatch:", ".github/workflows/release.yml", "release-manual", out,
            "make release preparation an explicit operator action")
    require(release, "name: github-release", ".github/workflows/release.yml", "release-environment", out,
            "gate release writes behind the github-release environment")
    require(release, "contents: write", ".github/workflows/release.yml", "release-write", out,
            "grant release write authority only to the draft-release job")
    require(release, "--draft --verify-tag", ".github/workflows/release.yml", "release-draft", out,
            "create a draft from an existing verified tag")
    require(release, "group: github-release", ".github/workflows/release.yml", "release-serial", out,
            "serialize release writes")
    require(release, "GH_REPO: ${{ github.repository }}", ".github/workflows/release.yml", "release-target", out,
            "bind gh release commands to the workflow repository")
    release_perms = top_permissions(release)
    if "contents: read" not in release_perms or "contents: write" in release_perms:
        out.append(finding("release-global-permissions", ".github/workflows/release.yml",
                           "release workflow has write authority outside the approved job",
                           "keep contents: read globally and grant contents: write only to draft-release"))
    require(release, "existing release is already published", ".github/workflows/release.yml",
            "release-immutable", out, "refuse to update a published release")
    require(release, 'git cat-file -t "refs/tags/$RELEASE_TAG"', ".github/workflows/release.yml",
            "release-annotated-tag", out, "refuse lightweight release tags")
    for token in (
        "dispatch the workflow from the exact release tag",
        "subject-checksums: release-assets/SHA256SUMS",
        "release-provenance.sigstore.json",
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/release.yml"',
        '--source-digest "$SOURCE_COMMIT" --source-ref "refs/tags/$RELEASE_TAG"',
        "--deny-self-hosted-runners",
    ):
        require(release, token, ".github/workflows/release.yml", "release-provenance", out,
                f"retain release provenance control: {token}")
    for token in signing_tokens:
        require(workflow_job(release, "attest-and-verify"), token,
                ".github/workflows/release.yml", "release-provenance-authority", out,
                f"grant {token} only to the post-build release provenance job")
    for job_name in ("validate-and-scan", "build-and-package", "rebuild-for-comparison"):
        block = workflow_job(release, job_name)
        for token in signing_tokens:
            if token in block:
                out.append(finding(
                    "release-build-authority", ".github/workflows/release.yml",
                    f"release pre-attestation job {job_name} has signing authority: {token}",
                    "keep validation and artifact generation unable to mint attestations or deployment identity",
                ))
    for job_name in ("build-and-package", "rebuild-for-comparison"):
        block = workflow_job(release, job_name)
        if "pip install" in block or "npm ci" in block:
            out.append(finding(
                "release-assembly-dependency-isolation", ".github/workflows/release.yml",
                f"final assembly job {job_name} installs executable package dependencies",
                "install and scan dependencies only in validation; assemble from source and retained evidence",
            ))
    for token in (
        "release-inputs-${{ inputs.tag }}",
        "release-comparison-${{ inputs.tag }}",
        "needs: [build-and-package, rebuild-for-comparison]",
        "cmp release-evidence/pages-sha256.txt",
        "needs: attest-and-verify",
    ):
        require(release, token, ".github/workflows/release.yml", "release-independent-rebuild", out,
                f"retain independent release assembly and comparison control: {token}")
    require(release, "release_gate.py --tier ship", ".github/workflows/release.yml",
            "release-shared-gate", out, "run the shared deterministic gate before packaging")
    release_validation_job = workflow_job(release, "validate-and-scan")
    release_browser_runtime_install = "pnpm install --frozen-lockfile --ignore-scripts"
    if (
        "working-directory: scripts/runtime" not in release_validation_job
        or release_browser_runtime_install not in release_validation_job
    ):
        out.append(finding(
            "release-browser-runtime-lock", ".github/workflows/release.yml",
            "the protected release job does not install the nested pinned host-browser API",
            "run pnpm from scripts/runtime with --frozen-lockfile before the shared ship gate",
        ))
    elif release_validation_job.index(release_browser_runtime_install) > release_validation_job.index(
        "release_gate.py --tier ship"
    ):
        out.append(finding(
            "release-browser-runtime-order", ".github/workflows/release.yml",
            "the pinned host-browser API is installed after protected release validation",
            "install the pinned browser API before the shared ship gate",
        ))
    if 'node-version: "24"' not in release_validation_job:
        out.append(finding(
            "release-node-runtime", ".github/workflows/release.yml",
            "the protected release job does not use the supported Node.js 24 runtime",
            "run protected release validation on Node.js 24",
        ))
    require(release, "pull_materials.py --check --fetch-attempts", ".github/workflows/release.yml",
            "release-live-material-check", out,
            "require a retried, strict live material check before release packaging")
    for token in ("test -f release-assets/release-manifest.json", "SHA256SUMS", "python-env.cdx.json", "release-assets/*"):
        require(release, token, ".github/workflows/release.yml", "release-artifact-set", out,
                f"retain required release artifact contract token: {token}")
    require(release, "contribution_safety_audit.py --require-publication-approved",
            ".github/workflows/release.yml", "publication-release-guard", out,
            "refuse external release preparation until publication is approved")
    if "pull_request:" in release or "pull_request_target:" in release:
        out.append(finding("release-pr-trigger", ".github/workflows/release.yml",
                           "release workflow can be started by an untrusted pull request",
                           "keep release workflow_dispatch-only"))
    require(release, "pip-audit -r scripts/materials/requirements.lock", ".github/workflows/release.yml",
            "release-material-sbom", out, "scan the pinned material-tool closure")
    require(release, "scripts/security/requirements-sca.lock", ".github/workflows/release.yml",
            "release-sca-lock", out, "install scanners from their isolated reviewed lock")
    validation_block = workflow_job(release, "validate-and-scan")
    for lock in (
        "scripts/materials/requirements.lock",
        "scripts/security/requirements-sca.lock",
    ):
        if not re.search(
            rf"pip install[^\n]*--no-deps[^\n]*--only-binary=:all:[^\n]*{re.escape(lock)}",
            validation_block,
        ):
            out.append(finding(
                "release-binary-lock-install", ".github/workflows/release.yml",
                f"validation lock may resolve undeclared dependencies or execute a source build: {lock}",
                "install the complete reviewed lock with --no-deps --only-binary=:all:",
            ))
    require(release, "--report release-security/sbom-policy.json", ".github/workflows/release.yml",
            "release-sbom-policy", out, "evaluate and retain SBOM policy evidence before release")
    for token in ("python-sbom-evidence.json", "python-license-appendix.md", "sbom-evidence-catalog.json"):
        require(release, token, ".github/workflows/release.yml", "release-sbom-evidence", out,
                f"retain versioned SBOM evidence asset: {token}")
    require(release, "--manifest-out release-security/python-sbom-evidence.json",
            ".github/workflows/release.yml", "release-sbom-evidence-generation", out,
            "generate the evidence manifest from the same Python SBOM packaged for release")

    dependency_review = docs[".github/workflows/dependency-review.yml"]
    require(dependency_review, "  pull_request:\n", ".github/workflows/dependency-review.yml",
            "dependency-review-trigger", out, "run dependency review on every pull request to main")
    require(dependency_review, "fail-on-severity: moderate", ".github/workflows/dependency-review.yml",
            "dependency-review-floor", out, "block moderate-or-higher vulnerable additions")
    if "pull_request_target:" in dependency_review or "secrets." in dependency_review:
        out.append(finding("dependency-review-fork-safety", ".github/workflows/dependency-review.yml",
                           "dependency review can acquire base-repository or secret authority",
                           "use pull_request with contents: read and no secrets"))

    codeql = docs[".github/workflows/codeql.yml"]
    for token in ("javascript-typescript", "python", "actions: read", "security-events: write", "schedule:"):
        require(codeql, token, ".github/workflows/codeql.yml", "codeql-baseline", out,
                f"retain public CodeQL baseline token: {token}")
    if "pull_request_target:" in codeql or "secrets." in codeql:
        out.append(finding("codeql-fork-safety", ".github/workflows/codeql.yml",
                           "CodeQL can acquire base-repository or secret authority",
                           "use pull_request with scoped security-events upload and no secrets"))

    dependabot = docs[".github/dependabot.yml"]
    for ecosystem in ("github-actions", "pip", "npm"):
        require(dependabot, f"package-ecosystem: {ecosystem}", ".github/dependabot.yml",
                "dependency-update-coverage", out, f"retain controlled {ecosystem} update coverage")

    for rel in ("scripts/materials/requirements.lock", "scripts/security/requirements-sca.lock"):
        if not docs[rel].strip():
            out.append(finding("dependency-lock", rel, "dependency lock is empty",
                               "regenerate the exact transitive Python 3.11 lock"))
        if "--hash=sha256:" not in docs[rel]:
            out.append(finding("dependency-hash-lock", rel, "dependency lock lacks artifact hashes",
                               "regenerate the exact lock with SHA-256 hashes"))
    for rel, workflow in (
        (".github/workflows/pages.yml", pages),
        (".github/workflows/release.yml", release),
    ):
        require(workflow, "--require-hashes --no-deps --only-binary=:all:", rel,
                "github-hash-lock-install", out,
                "install Python locks with hashes, no dependency resolution, and wheels only")
    require(docs["scripts/security/audit_dependency_locks.py"], "--self-test",
            "scripts/security/audit_dependency_locks.py", "dependency-lock-detector", out,
            "retain mutation tests for stale and unpinned dependency locks")
    require(docs["scripts/validation/container_boundary_audit.py"], 'FORBIDDEN_NAMES = {".dockerignore", "Dockerfile", "Containerfile"',
            "scripts/validation/container_boundary_audit.py", "container-boundary-detector", out,
            "reject repository-owned container definitions and build commands")
    require(docs["scripts/security/audit_sbom_policy.py"], "retired-component",
            "scripts/security/audit_sbom_policy.py", "sbom-policy-detector", out,
            "retain runtime SBOM completeness and retired-component enforcement")
    require(docs["scripts/compliance/sbom_evidence.py"], "nemoclaw:license-resolution:raw-sbom-sha256",
            "scripts/compliance/sbom_evidence.py", "sbom-evidence-detector", out,
            "retain distribution-aware SBOM evidence and immutable-link checks")
    require(docs["scripts/compliance/docs/sbom_evidence.json"], '"id": "python-material-tooling"',
            "scripts/compliance/docs/sbom_evidence.json", "sbom-evidence-catalog", out,
            "retain the CI-generated material-tool SBOM boundary")

    gitlab_core = docs[".gitlab/ci/core.yml"]
    gitlab_sca = docs[".gitlab/ci/sca.yml"]
    gitlab = gitlab_core + "\n" + gitlab_sca
    image = re.search(r"(?m)^  image: node:20-bookworm-slim@sha256:([0-9a-f]+)$", gitlab_core)
    if not image or len(image.group(1)) != 64:
        out.append(finding("gitlab-image-pin", ".gitlab-ci.yml",
                           "shared CI image is not pinned to a full immutable digest",
                           "pin the reviewed Node 20 image to its runner-resolved SHA-256 digest"))
    anchor = re.search(r"(?ms)^\.with_python_node:.*?(?=^test:\n)", gitlab)
    anchor_text = anchor.group(0) if anchor else ""
    for token in ("runner_system_failure", "stuck_or_timeout_failure", "api_failure", "scheduler_failure"):
        if token not in anchor_text:
            out.append(finding("gitlab-infrastructure-retry", ".gitlab-ci.yml",
                               f"shared jobs do not retry infrastructure class {token}",
                               "retry only runner and control-plane failures; never script failures"))
    if re.search(r"(?m)^\s*-\s+script_failure\s*$", anchor_text):
        out.append(finding("gitlab-script-retry", ".gitlab-ci.yml",
                           "shared jobs retry validation script failures",
                           "remove script_failure so drift and tampering remain fail-closed"))
    if ("scripts/materials/requirements.lock" not in anchor_text
            or 'MATERIAL_TOOLS_REQUIRED:-0' not in anchor_text or "|| true" in anchor_text):
        out.append(finding("gitlab-material-install", ".gitlab-ci.yml",
                           "material tooling is not conditionally installed from its lock with fail-closed setup",
                           "install the lock only for jobs that consume material tooling, with no fail-open operator"))
    pages_materials = re.search(r"(?ms)^pages:\n(.*?)(?=^pages_smoke:\n)", gitlab)
    if not pages_materials or 'MATERIAL_TOOLS_REQUIRED: "1"' not in pages_materials.group(1):
        out.append(finding("gitlab-pages-material-install", ".gitlab-ci.yml",
                           "Pages lacks material tooling needed by protected-root bundle validation",
                           "enable the locked material environment for every Pages build, including previews"))
    preview_fetch = 'git fetch "$preview_remote" "+refs/heads/$branch:refs/remotes/$preview_namespace/$branch" --quiet'
    if (gitlab.count(preview_fetch) != 1
            or gitlab.count('refresh_branch_ref "$preview_ref"') != 2
            or 'preview_remote="$CI_MERGE_REQUEST_SOURCE_PROJECT_URL"' not in gitlab
            or 'preview_namespace="preview-source"' not in gitlab
            or re.search(rf"{re.escape(preview_fetch)}[^\n]*\|\|\s*true", gitlab)):
        out.append(finding("gitlab-preview-ref-fetch", ".gitlab-ci.yml",
                           "Pages preview source-ref refresh is missing, fork-unaware, ambiguous, or fail-open",
                           "fetch the exact branch from the MR source project (or origin for branch pipelines) before comparing and publishing its SHA"))
    require(gitlab, "release_gate.py --tier ship", ".gitlab-ci.yml",
            "gitlab-safety-selftest", out, "run detector mutations in GitLab CI")
    test_job = re.search(r"(?ms)^test:\n(.*?)(?=^external_integration_audit:\n)", gitlab)
    pinned_browser_image = (
        "mcr.microsoft.com/playwright:v1.61.1-noble@sha256:"
        "5b8f294aff9041b7191c34a4bab3ac270157a28774d4b0660e9743297b697e48"
    )
    if (not test_job or pinned_browser_image not in test_job.group(1)
            or 'BROWSER_TOOLS_REQUIRED: "1"' not in test_job.group(1)
            or "cd scripts/runtime && pnpm install --frozen-lockfile --ignore-scripts" not in gitlab):
        out.append(finding("gitlab-report-browser-runtime", ".gitlab-ci.yml",
                           "the validation-report producer lacks the pinned browser runtime",
                           "run the ship gate with the locked Playwright API and digest-pinned browser image"))
    require(gitlab_core, "pages_artifact_integrity.py --source-root .", ".gitlab/ci/core.yml",
            "gitlab-source-resource-preflight", out,
            "bound proposed source before the canonical expensive gate")
    require(gitlab, 'GATE_ARGS+=(--changed-since "$GATE_BASE")', ".gitlab-ci.yml",
            "gitlab-change-aware-gate", out, "skip only unaffected mutation fixtures on proposal commits")
    require(gitlab, "--timing-report docs/validation/release-gate-timings.json",
            ".gitlab-ci.yml", "gitlab-gate-timing", out,
            "retain per-command gate timing evidence")
    for token in (
        "BUILD_PAGES_PULL_MATERIALS=0 \\",
        "BUILD_PAGES_REUSE_VALIDATION=1 \\",
        'bash scripts/build/build_pages.sh "$CI_PROJECT_DIR/candidate"',
        'git worktree add --quiet --detach "$candidate_source" "$CI_COMMIT_SHA"',
        'cp -a candidate/. "public/$CI_COMMIT_REF_SLUG/"',
        "cp -a candidate public",
    ):
        require(gitlab, token, ".gitlab-ci.yml", "gitlab-immutable-report-reuse", out,
                "build the candidate once on the required worker and copy it during publication")
    require(gitlab, 'git worktree add --quiet --detach /tmp/nemoclaw-prod-root "origin/$prod_ref"',
            ".gitlab-ci.yml", "gitlab-protected-root-worktree", out,
            "build protected-root previews from a real detached worktree so Git-backed audits remain available")
    require(gitlab, "pull_materials.py --check --allow-transient-unreachable",
            ".gitlab-ci.yml", "gitlab-transient-material-policy", out,
            "allow only classified transient source reachability on production-ref pushes")
    scheduled_material = re.search(
        r'if \[ "\$\{CI_PIPELINE_SOURCE:-\}" = "schedule" \]; then\n(?P<body>.*?)(?=\n\s+elif )',
        gitlab,
        re.S,
    )
    if (not scheduled_material
            or "pull_materials.py --check --fetch-attempts" not in scheduled_material.group("body")
            or "--allow-transient-unreachable" in scheduled_material.group("body")):
        out.append(finding("gitlab-scheduled-material-policy", ".gitlab-ci.yml",
                           "scheduled material check is absent or not strict",
                           "keep scheduled live checks strict and omit transient degradation"))
    require(gitlab, "CI_MERGE_REQUEST_DESCRIPTION", ".gitlab-ci.yml", "gitlab-submission-contract", out,
            "validate merge-request descriptions when CI has MR context")
    require(gitlab, 'GIT_DEPTH: "0"', ".gitlab-ci.yml", "gitlab-complete-history", out,
            "fetch complete history so every proposed commit can be scanned")
    require(gitlab, 'contribution_safety_audit.py --commit-range "${CI_MERGE_REQUEST_DIFF_BASE_SHA}..${CI_COMMIT_SHA}"',
            ".gitlab-ci.yml", "gitlab-dco-check", out,
            "validate every merge-request commit signoff")
    require(gitlab,
            'local_path_leak_audit.py --commit-range "${CI_MERGE_REQUEST_DIFF_BASE_SHA}..${CI_COMMIT_SHA}"',
            ".gitlab-ci.yml", "gitlab-local-path-range", out,
            "reject contributor-local additions in every merge-request commit")
    require(gitlab, "sensitive_content_audit.py --submission-env CI_MERGE_REQUEST_TITLE",
            ".gitlab-ci.yml", "gitlab-sensitive-submission", out,
            "scan merge-request metadata supplied by the host event")
    require(gitlab,
            'sensitive_content_audit.py --commit-range "${CI_MERGE_REQUEST_DIFF_BASE_SHA}..${CI_COMMIT_SHA}"',
            ".gitlab-ci.yml", "gitlab-sensitive-range", out,
            "reject restricted details in every merge-request commit")
    require(gitlab,
            'release_change_reminder.py --commit-range "${CI_MERGE_REQUEST_DIFF_BASE_SHA}..${CI_COMMIT_SHA}"',
            ".gitlab-ci.yml", "gitlab-release-reminder", out,
            "show external release follow-ups from the merge-request diff")
    require(gitlab, "audit_sbom_policy.py --sbom", ".gitlab-ci.yml", "gitlab-sbom-policy", out,
            "evaluate the generated runtime SBOM instead of only uploading it")
    require(gitlab, "scripts/compliance/resolve_sbom_licenses.py --input scripts/security/reports/python-materials/python-env.raw.cdx.json",
            ".gitlab/ci/sca.yml", "gitlab-sbom-evidence", out,
            "preserve the raw scan and resolve every package license before evidence emission")
    if "security_image_sca:" in gitlab_sca or "security_deep_sca:" in gitlab_sca:
        out.append(finding("retired-sca-job", ".gitlab/ci/sca.yml",
                           "obsolete image or workspace scanner returned",
                           "scan only the browser graph and pinned material tools"))
    scanner_install = ".sca-tools-venv/bin/python -m pip install --require-hashes --no-deps --only-binary=:all: -q -r scripts/security/requirements-sca.lock"
    for job_name in ("security_sca", "security_python_sca"):
        match = re.search(rf"(?ms)^{job_name}:\n(.*?)(?=^[A-Za-z0-9_.-]+:\n|\Z)", gitlab_sca)
        require(match.group(1) if match else "", scanner_install,
                ".gitlab/ci/sca.yml", "gitlab-sca-lock", out,
                f"install scanner tooling from its exact lock in {job_name}")
    optional_mr_scan = """    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
      when: manual
      allow_failure: true"""
    for job_name, automatic_path, code in (
        ("security_browser_sca", "scripts/browser-vendor/package-lock.json", "gitlab-browser-sca-rules"),
        ("security_python_sca", "scripts/materials/requirements.lock", "gitlab-python-sca-rules"),
    ):
        match = re.search(rf"(?ms)^{job_name}:\n(.*?)(?=^[A-Za-z0-9_.-]+:\n|\Z)", gitlab)
        body = match.group(1) if match else ""
        require(body, automatic_path, ".gitlab-ci.yml", code, out,
                f"run {job_name} automatically when its dependency surface changes")
        require(body, optional_mr_scan, ".gitlab-ci.yml", f"{code}-manual", out,
                f"leave {job_name} available as a non-blocking MR opt-in")
        require(body, "- .gitlab/ci/sca.yml", ".gitlab/ci/sca.yml", f"{code}-ci-sensitive", out,
                f"rerun {job_name} when its self-contained scanner policy changes")
    browser_scan = re.search(r"(?ms)^security_browser_sca:\n(.*?)(?=^[A-Za-z0-9_.-]+:\n|\Z)", gitlab_sca)
    browser_body = browser_scan.group(1) if browser_scan else ""
    for token in (
        "scripts/runtime/pnpm-lock.yaml",
        "npm audit --prefix .cache/runtime-npm-audit --package-lock-only --audit-level=moderate",
        "scripts/security/reports/runtime-npm-audit.json",
    ):
        require(browser_body, token, ".gitlab/ci/sca.yml", "gitlab-runtime-sca", out,
                "scan the locked host-browser validation dependency when it changes")

    material_puller = docs["scripts/materials/pull_materials.py"]
    for token, code, fix in (
        ("TRANSIENT_HTTP_STATUS = {", "material-transient-classification",
         "retain the bounded HTTP status allowlist for retries"),
        ("refusing source redirect", "material-redirect-boundary",
         "reject cross-host or non-HTTPS source redirects"),
        ('re.fullmatch(r"[0-9a-f]{64}"', "material-full-sha",
         "require a complete lowercase SHA-256 for every committed snapshot"),
        ("def verify_committed", "material-offline-verifier",
         "retain network-free snapshot, metadata, and digest verification"),
        ("def check_passes", "material-fail-closed-policy",
         "keep drift, permanent reachability failures, and tampering fail-closed"),
        ('"--allow-transient-unreachable"', "material-explicit-degradation",
         "make transient-only degradation an explicit caller decision"),
    ):
        require(material_puller, token, "scripts/materials/pull_materials.py", code, out, fix)
    try:
        material_records = json.loads(docs["web/nemoclaw/mats/_materials.json"]).get("materials", [])
    except (TypeError, json.JSONDecodeError):
        material_records = []
        out.append(finding("material-provenance-json", "web/nemoclaw/mats/_materials.json",
                           "material provenance is not valid JSON",
                           "restore the reviewed material provenance inventory"))
    for record in material_records:
        if not re.fullmatch(r"[0-9a-f]{64}", record.get("sha256", "")):
            out.append(finding("material-provenance-sha", "web/nemoclaw/mats/_materials.json",
                               f"{record.get('name', '?')} lacks a full lowercase SHA-256",
                               "refresh and review committed material provenance"))
    require(gitlab, 'CI_PIPELINE_SOURCE == "merge_request_event"', ".gitlab-ci.yml",
            "gitlab-mr-pipeline", out, "run open merge requests in MR context")
    require(gitlab, "$CI_COMMIT_BRANCH && $CI_OPEN_MERGE_REQUESTS", ".gitlab-ci.yml",
            "gitlab-pipeline-dedup", out, "suppress duplicate branch pipelines after an MR opens")
    require(gitlab, "CI_MERGE_REQUEST_SOURCE_BRANCH_NAME:-$CI_COMMIT_REF_NAME", ".gitlab-ci.yml",
            "gitlab-preview-ref", out, "resolve branch-preview refs in branch and MR pipelines")
    pages_body = pages_materials.group(1) if pages_materials else ""
    pages_header = pages_body.split("\n  script:\n", 1)[0]
    if not (re.search(r"(?m)^\s+- job:\s*test\s*$", pages_header) or 'needs: ["test"]' in pages_header):
        out.append(finding("gitlab-deploy-gate", ".gitlab-ci.yml",
                           "Pages does not declare the required test job as a dependency",
                           "keep Pages blocked on the required test job"))
    require(gitlab, "human_review:", ".gitlab-ci.yml", "gitlab-human-review", out,
            "keep an explicit human acceptance job after preview validation")
    require(gitlab, "theme_runtime:", ".gitlab-ci.yml", "gitlab-theme-runtime", out,
            "render every generated HTML file in the required dark/light browser matrix")
    require(gitlab, '--site-root "$THEME_SITE_ROOT" --scan-root "$THEME_SCAN_ROOT"', ".gitlab-ci.yml",
            "gitlab-theme-runtime-command", out,
            "serve the complete deployment while exhaustively scanning the owned artifact root")
    require(gitlab, "THEME_SITE_ROOT=public", ".gitlab-ci.yml",
            "gitlab-theme-runtime-deployed-root", out,
            "audit the complete deployed Pages tree, including protected production and previews")
    if 'THEME_SITE_ROOT="public/$CI_COMMIT_REF_SLUG"' in gitlab:
        out.append(finding(
            "gitlab-theme-runtime-narrowed-root", ".gitlab-ci.yml",
            "theme runtime narrows a combined Pages deployment to one preview subdirectory",
            "audit public so every deployed HTML file enters the browser matrix",
        ))
    require(
        gitlab,
        'project_artifact_manifests.py public --manifest-root "public/$CI_COMMIT_REF_SLUG"',
        ".gitlab-ci.yml", "gitlab-preview-manifest-projection", out,
        "reproject every branch mirror after CI rewrites the preview manifest",
    )
    if not re.search(r"(?m)^\s*python3 scripts/build/project_artifact_manifests\.py public\s*$", gitlab):
        out.append(finding(
            "gitlab-production-manifest-projection", ".gitlab-ci.yml",
            "production manifest rewrites are not projected into every discovered mirror",
            "run project_artifact_manifests.py public after rewriting public/branches.json",
        ))
    require(
        gitlab, 'artifact_link_audit.py "public/$CI_COMMIT_REF_SLUG"', ".gitlab-ci.yml",
        "gitlab-combined-artifact-link-audit", out,
        "reaudit the complete branch artifact after every CI manifest rewrite",
    )
    require(gitlab, 'needs: ["test", "pages_smoke", "theme_runtime"]', ".gitlab-ci.yml",
            "gitlab-human-review-needs", out,
            "make human acceptance wait for static gates, live preview smoke, and all-HTML theme rendering")
    require(gitlab, "name: human-review", ".gitlab-ci.yml", "gitlab-human-review-environment", out,
            "bind human acceptance to the protected human-review environment")
    human_review = re.search(r"(?ms)^human_review:\n(.*?)(?=^[A-Za-z0-9_.-]+:\n|\Z)", gitlab)
    if not human_review or "when: manual" not in human_review.group(1) or "allow_failure: false" not in human_review.group(1):
        out.append(finding("gitlab-human-review-blocking", ".gitlab-ci.yml",
                           "human_review is not a required manual MR action",
                           "keep human_review manual and blocking for merge-request pipelines"))

    install = docs["scripts/build/install-hooks.sh"]
    require(install, "git rev-parse --git-path hooks", "scripts/build/install-hooks.sh", "worktree-hooks", out,
            "resolve the real hooks directory for normal and linked worktrees")
    require(install, 'hook="$content_root/scripts/git-hooks/$name"', "scripts/build/install-hooks.sh",
            "worktree-hook-dispatch", out,
            "dispatch shared Git hooks to the active worktree's implementation")
    precommit = docs["scripts/git-hooks/pre-commit"]
    require(precommit, "REFUSING COMMIT on protected branch", "scripts/git-hooks/pre-commit",
            "protected-local-commit", out, "refuse local commits on main, nemoclaw-only, and release/*")
    require(precommit, "contribution_safety_audit.py", "scripts/git-hooks/pre-commit", "precommit-safety", out,
            "run the fast contribution-boundary audit before staged-file checks")
    require(precommit, "local_path_leak_audit.py", "scripts/git-hooks/pre-commit", "precommit-local-path", out,
            "reject contributor workstation paths before broader staged-file checks")
    require(precommit, '"$LOCAL_PATH_AUDIT" --staged', "scripts/git-hooks/pre-commit",
            "precommit-local-path-staged", out, "scan exact staged bytes at commit time")
    require(precommit, "sensitive_content_audit.py", "scripts/git-hooks/pre-commit", "precommit-sensitive", out,
            "reject security-finding details and private operational data before commit")
    require(precommit, '"$SENSITIVE_AUDIT" --staged', "scripts/git-hooks/pre-commit",
            "precommit-sensitive-staged", out, "scan exact staged bytes at commit time")
    prep = docs["scripts/git-hooks/pre-push"]
    if "git pull --rebase" in prep:
        out.append(finding("mutating-prepush", "scripts/git-hooks/pre-push",
                           "pre-push mutates history by rebasing during push",
                           "fail with exact recovery commands and let the operator rebase explicitly"))
    if re.search(r"git fetch[^\n]*(?:\|\||\bor\b)[^\n]*exit 0", prep):
        out.append(finding("fetch-fail-open", "scripts/git-hooks/pre-push",
                           "failed base fetch exits success and skips required gates",
                           "refuse the push when origin/main cannot be verified"))
    if re.search(r'\[ "\$REMOTE" = "origin" \][^\n]*exit 0', prep):
        out.append(finding("remote-fail-open", "scripts/git-hooks/pre-push",
                           "non-origin pushes bypass every repository gate",
                           "skip only base comparison; run deterministic gates for every remote"))
    require(prep, "cannot verify origin/main", "scripts/git-hooks/pre-push", "fetch-refusal", out,
            "fail closed when origin/main cannot be fetched")
    require(prep, "REFUSING PUSH - origin/main is", "scripts/git-hooks/pre-push", "behind-refusal", out,
            "refuse a behind branch instead of silently rewriting it")
    require(prep, "contribution_safety_audit.py", "scripts/git-hooks/pre-push", "prepush-safety", out,
            "run the contribution-boundary audit and its mutations before push")
    require(prep, "local_path_leak_audit.py", "scripts/git-hooks/pre-push", "prepush-local-path", out,
            "reject contributor workstation paths before source leaves the workstation")
    require(prep, 'RANGE="origin/main..HEAD"', "scripts/git-hooks/pre-push", "prepush-range", out,
            "define one complete proposed-history range")
    require(prep, 'python3 "$SAFETY" --commit-range "$RANGE"',
            "scripts/git-hooks/pre-push", "prepush-dco", out,
            "reject unsigned topic-branch commits before push")
    require(prep, 'python3 "$LOCAL_PATH_AUDIT" --commit-range "$RANGE"',
            "scripts/git-hooks/pre-push", "prepush-local-path-range", out,
            "reject contributor-local additions even when a later commit removes them")
    require(prep, 'python3 "$SENSITIVE_AUDIT" --commit-range "$RANGE"',
            "scripts/git-hooks/pre-push", "prepush-sensitive-range", out,
            "reject restricted details even when a later commit removes them")
    require(prep, 'python3 "$RELEASE_REMINDER" --commit-range "$RANGE"',
            "scripts/git-hooks/pre-push", "prepush-release-reminder", out,
            "show operator-owned external release follow-ups before push")
    for rel in (".github/PULL_REQUEST_TEMPLATE.md", ".gitlab/merge_request_templates/Default.md"):
        require(docs[rel], "## External release follow-up", rel, "submission-release-reminder", out,
                "retain the external release follow-up section in contribution templates")
    require(prep, 'release_gate.py', "scripts/git-hooks/pre-push", "prepush-canonical-gate", out,
            "delegate deterministic checks to the canonical release gate")
    require(prep, '--tier ship --no-write --changed-since origin/main --reuse-success',
            "scripts/git-hooks/pre-push", "prepush-canonical-gate", out,
            "run one change-aware ship gate and reuse only identical clean local success")
    for duplicate in ("LOCK_AUDIT=", "SBOM_POLICY=", "PACKAGE_RELEASE=", "validate_bundle.py"):
        if duplicate in prep:
            out.append(finding("prepush-duplicate-gate", "scripts/git-hooks/pre-push",
                               f"pre-push re-expands canonical gate work: {duplicate}",
                               "keep history checks explicit and delegate deterministic checks once to release_gate.py"))

    playbook = docs["docs/release_playbook.md"]
    for token in ("Host settings are not versioned by this repository", "gitlab_governance_audit.py",
                  "release_artifacts.md", "release_gate.py --tier ship"):
        require(playbook, token, "docs/release_playbook.md", "release-playbook", out,
                f"document {token} in the GitHub release/operator runbook")
    artifact_doc = docs["docs/release_artifacts.md"]
    for token in ("GitHub release runbook", "github-release", "draft release", "immutable"):
        require(artifact_doc, token, "docs/release_artifacts.md", "release-artifact-doc", out,
                f"document {token} in the artifact and tag contract")
    package_source = docs["scripts/build/package_release.py"]
    for token in ('mtime=0', 'format=tarfile.PAX_FORMAT', '"release-manifest.json"', '"SHA256SUMS"'):
        require(package_source, token, "scripts/build/package_release.py", "release-package-contract", out,
                f"keep deterministic release-packaging primitive: {token}")
    package_manifest = re.search(
        r'(?ms)^\s*manifest = \{.*?(?=^\s*manifest_path\.write_text)', package_source
    )
    if not package_manifest or '"malware_scan_required"' not in package_manifest.group(0):
        out.append(finding(
            "release-malware-evidence-contract", "scripts/build/package_release.py",
            "release manifest does not identify archives requiring external malware evidence",
            "make every packaged archive identify its required external malware evidence",
        ))
    require(artifact_doc, "required-before-publication", "docs/release_artifacts.md",
            "release-malware-evidence-doc", out,
            "document how the release manifest blocks publication pending authoritative evidence")
    require(docs["scripts/build/build_branch_manifest.py"], 'os.environ.get("SOURCE_DATE_EPOCH")',
            "scripts/build/build_branch_manifest.py", "release-build-epoch", out,
            "make generated branch metadata reproducible for tagged builds")
    require(release, 'echo "SOURCE_DATE_EPOCH=', ".github/workflows/release.yml",
            "release-build-epoch", out, "bind generated build metadata to the release commit time")
    require(release, '>> "$GITHUB_ENV"', ".github/workflows/release.yml",
            "release-build-epoch", out, "carry the release commit epoch through every build step")
    require(docs["scripts/validation/validate_bundle.py"], 'os.environ.get("SOURCE_DATE_EPOCH")',
            "scripts/validation/validate_bundle.py", "release-build-epoch", out,
            "make generated validation reports reproducible for tagged builds")
    for token in ("annotated", "immutable", "CycloneDX", "SHA256SUMS", "3 days"):
        require(docs["docs/release_artifacts.md"], token, "docs/release_artifacts.md",
                "release-artifact-doc", out, f"document release strategy token: {token}")
    require(docs["scripts/skills/gen_skill_hierarchy.py"], "Ideas stay easy to contribute",
            "scripts/skills/gen_skill_hierarchy.py", "tenet-source", out,
            "project the contribution trust boundary into the root SKILL tenets")
    require(docs["scripts/validation/SKILL.html"], "contribution_safety_audit.py",
            "scripts/validation/SKILL.html", "validation-beacon", out,
            "advertise the contribution boundary from the validation beacon")
    return out


SUBMISSION_SECTIONS = (
    "Summary", "Issue link", "Surfaces touched", "Blast radius checked",
    "Validation evidence", "Human ownership", "Risk and rollback", "Out of scope",
)


def audit_submission(body: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    required_headings = [f"## {section}" for section in SUBMISSION_SECTIONS]
    missing_in_window = [heading for heading in required_headings if heading not in (body or "")[:2700]]
    if missing_in_window:
        out.append(finding("submission-description-window", "submission",
                           "required headings fall outside GitLab's CI description window: "
                           + ", ".join(missing_in_window),
                           "put the compact submission contract before rationale, screenshots, or logs"))
    for section in SUBMISSION_SECTIONS:
        match = re.search(rf"(?ms)^## {re.escape(section)}\s*\n(.*?)(?=^## |\Z)", body or "")
        if not match or not match.group(1).strip():
            out.append(finding("submission-section", "submission", f"missing or empty section: {section}",
                               f"fill ## {section} with concrete evidence"))
    relationship = re.search(r"(?im)\b(?:Addresses|Closes|Fixes)\s+#[0-9]+\b", body or "")
    if not relationship:
        out.append(finding("submission-issue", "submission", "no explicit issue relationship",
                           "add Addresses #N, or Closes #N only when acceptance is fully met"))
    elif relationship.group(0).lower().startswith("addresses"):
        remaining = re.search(r"(?ms)^## Remaining issue work\s*\n(.*?)(?=^## |\Z)", body or "")
        if not remaining or not remaining.group(1).strip():
            out.append(finding(
                "submission-issue-remains", "submission",
                "Addresses #N does not say which acceptance criteria remain unmet",
                "use Closes #N when the issue is fully satisfied, or add a substantive "
                "## Remaining issue work section",
            ))
    if not re.search(r"(?im)^- \[[xX]\] `?(?:web/|i18n/|scripts/|docs/|materials)", body or ""):
        out.append(finding("submission-surface", "submission", "no changed surface is checked",
                           "check every touched surface in ## Surfaces touched"))
    if not re.search(r"(?im)\b(?:PASS|FAIL|BLOCKED)\b", body or ""):
        out.append(finding("submission-evidence", "submission", "validation has no PASS, FAIL, or BLOCKED result",
                           "record command outcomes; do not submit an unqualified checklist"))
    return out


def audit_commit_records(records: list[tuple[str, str, str, str]]) -> list[dict[str, str]]:
    """Require one DCO trailer matching each commit author's name and email."""
    out: list[dict[str, str]] = []
    for sha, author_name, author_email, message in records:
        trailers = re.findall(r"(?im)^Signed-off-by:\s*(.+?)\s*<([^>]+)>\s*$", message)
        expected = (" ".join(author_name.split()).casefold(), author_email.strip().casefold())
        normalized = {(" ".join(name.split()).casefold(), email.strip().casefold())
                      for name, email in trailers}
        if expected not in normalized:
            out.append(finding("commit-signoff", sha,
                               f"commit by {author_name} <{author_email}> lacks a matching Signed-off-by trailer",
                               "amend the commit with git commit --amend --signoff; repair every commit in the proposed range"))
    return out


def audit_language_ownership(
    changed_paths: list[str], changelog: str, commit_messages: list[str],
    learner_prose_paths: set[str] | None = None,
) -> list[dict[str, str]]:
    """Require public credit and explicit review for learner-prose localization changes."""
    out: list[dict[str, str]] = []
    prose_candidates = learner_prose_paths if learner_prose_paths is not None else set(changed_paths)
    locale_pages = [path for path in prose_candidates if re.fullmatch(
        r"i18n/[^/]+/web/nemoclaw/[0-9]{2}[a-z]-[^/]+\.html", path)]
    canonical_pages = [path for path in prose_candidates if re.fullmatch(
        r"web/nemoclaw/[0-9]{2}[a-z]-[^/]+\.html", path)]
    if not locale_pages:
        return out

    unreleased = re.search(r"(?ms)^## Unreleased\s*$\n(.*?)(?=^## |\Z)", changelog)
    has_public_credit = bool(unreleased and re.search(r"(?i)\bThanks to\b", unreleased.group(1)))
    if "CHANGELOG.md" not in changed_paths or not has_public_credit:
        out.append(finding(
            "contributor-credit", "CHANGELOG.md",
            "localized learner prose changed without an Unreleased public contributor credit",
            "add a concise 'Thanks to <public name>' entry; do not publish private contact details",
        ))
    if canonical_pages and not any(re.search(
            r"(?im)^Localization-Review:\s*[^=\s]+\s*=\s*\S.+$", message)
            for message in commit_messages):
        out.append(finding(
            "mixed-language-ownership", "git",
            "canonical and localized learner prose changed without a Localization-Review trailer",
            "split ownership by proposal or add Localization-Review: <locale>=<public reviewer name>",
        ))
    return out


class _LearnerText(HTMLParser):
    """Extract text a learner can perceive without treating URLs as prose."""

    LEARNER_ATTRIBUTES = {"alt", "aria-label", "placeholder", "title"}
    HIDDEN_ELEMENTS = {"script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in self.HIDDEN_ELEMENTS:
            self.hidden_depth += 1
            return
        if self.hidden_depth:
            return
        for name, value in attrs:
            if name.casefold() in self.LEARNER_ATTRIBUTES and value:
                self.parts.append(value)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.hidden_depth or tag.casefold() in self.HIDDEN_ELEMENTS:
            return
        for name, value in attrs:
            if name.casefold() in self.LEARNER_ATTRIBUTES and value:
                self.parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in self.HIDDEN_ELEMENTS and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def learner_text(raw: str) -> str:
    parser = _LearnerText()
    parser.feed(raw)
    parser.close()
    return " ".join(" ".join(parser.parts).split())


def changed_learner_prose_paths(
    rev_range: str, changed_paths: list[str], root: Path = ROOT,
) -> set[str]:
    """Return course pages whose rendered prose changed across a Git range.

    Ownership follows what a learner reads, including accessibility labels. A
    local URL, class, hash, or other transport-only edit is still reviewed by
    its functional gates but is not misreported as a translation rewrite.
    Missing or unreadable blobs fail closed as prose changes.
    """
    endpoints = re.fullmatch(r"(.+?)\.{2,3}(.+)", rev_range)
    candidates = [path for path in changed_paths if re.fullmatch(
        r"(?:i18n/[^/]+/)?web/nemoclaw/[0-9]{2}[a-z]-[^/]+\.html", path)]
    if not endpoints:
        return set(candidates)
    base, head = endpoints.groups()
    changed: set[str] = set()
    for path in candidates:
        blobs: list[str] = []
        for revision in (base, head):
            result = subprocess.run(
                ["git", "show", f"{revision}:{path}"], cwd=root,
                capture_output=True, text=True,
            )
            if result.returncode:
                changed.add(path)
                break
            blobs.append(result.stdout)
        if len(blobs) == 2 and learner_text(blobs[0]) != learner_text(blobs[1]):
            changed.add(path)
    return changed


def audit_commit_range(rev_range: str, root: Path = ROOT) -> list[dict[str, str]]:
    try:
        result = subprocess.run(
            ["git", "log", "--format=%H%x00%an%x00%ae%x00%B%x1e", rev_range],
            cwd=root, check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "git log failed").strip()
        return [finding("commit-range", "git", f"cannot inspect {rev_range}: {detail}",
                        "fetch the base ref and pass an explicit BASE..HEAD range")]
    records: list[tuple[str, str, str, str]] = []
    for raw in result.stdout.split("\x1e"):
        raw = raw.strip("\n")
        if not raw:
            continue
        fields = raw.split("\x00", 3)
        if len(fields) != 4:
            return [finding("commit-range", "git", f"cannot parse commit metadata for {rev_range}",
                            "retain the NUL-delimited git log contract")]
        records.append((fields[0], fields[1], fields[2], fields[3]))
    if not records:
        return [finding("commit-range", "git", f"range {rev_range} contains no commits",
                        "pass the proposed commit range as BASE..HEAD")]
    try:
        changed = subprocess.run(
            ["git", "diff", "--name-only", rev_range], cwd=root, check=True,
            capture_output=True, text=True,
        ).stdout.splitlines()
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except (subprocess.CalledProcessError, OSError) as exc:
        return [finding("commit-range", "git", f"cannot inspect changed paths: {exc}",
                        "fetch the base ref and restore CHANGELOG.md")]
    prose_paths = changed_learner_prose_paths(rev_range, changed, root)
    return audit_commit_records(records) + audit_language_ownership(
        changed, changelog, [record[3] for record in records], prose_paths)


def self_test() -> list[str]:
    failures: list[str] = []
    if audit_repo(ROOT):
        return ["baseline repository contract is not clean"]
    with tempfile.TemporaryDirectory(prefix="contribution-safety-") as td:
        fixture = Path(td)
        for rel in CONTRACT_FILES:
            src, dst = ROOT / rel, fixture / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        cases = (
            ("conduct-report-route", "CODE_OF_CONDUCT.md", "private content-reporting flow", "public Issue"),
            ("support-boundary", "SUPPORT.md", "Triage is best-effort", "Triage is guaranteed"),
            ("product-security-question-route", "SUPPORT.md", "[#ask-security](https://nvidia.slack.com/archives/CAHCG5005)", "#security-help"),
            ("dco-policy", "DCO.md", "Developer Certificate of Origin 1.1", "unversioned signoff"),
            ("dco-stacked-merge", "DCO.md", "host-generated squash or merge commit", "generated integration commit"),
            ("contributor-stacked-merge", "CONTRIBUTING.md", "stacked merge request", "nested proposal"),
            ("hook-authority", "CONTRIBUTING.md", "Required CI and protected refs remain authoritative", "Local hooks are authoritative"),
            ("contributor-credit-policy", "CONTRIBUTING.md", "Contributor credit and localization ownership", "Anonymous integration"),
            ("localization-review-policy", "CONTRIBUTING.md", "Localization-Review:", "Translation-Note:"),
            ("agent-localization-ownership", "docs/agent_process.md", "Preserve contributor and locale ownership", "Rewrite translations automatically"),
            ("course-prose-contract", "docs/course-prose-style.md", "Course prose writing contract", "English review snapshot"),
            ("prose-review-judgment", "docs/course-prose-style.md", "Automated signals identify passages", "Scores decide every rewrite"),
            ("prose-locale-ownership", "docs/course-prose-style.md", "Locale ownership", "Translation rewrite"),
            ("github-pr-trigger", ".github/workflows/pages.yml", "  pull_request:\n", "  # pull_request removed\n"),
            ("pages-fresh-validation-report", "scripts/build/build_pages.sh", 'python3 "$T1/scripts/validation/validate_bundle.py" --scope ship', 'python3 "$T1/scripts/validation/missing_bundle_gate.py" --scope ship'),
            ("pages-report-reuse-audit", "scripts/build/build_pages.sh", 'validation_report_audit.py"', 'missing_report_audit.py"'),
            ("pages-report-reuse-immutable", "scripts/build/build_pages.sh", 'if [ "$REUSE_VALIDATION" = "1" ] && [ "$PULL_MATERIALS" != "0" ]; then', 'if [ "$REUSE_VALIDATION" = "2" ] && [ "$PULL_MATERIALS" != "0" ]; then'),
            ("pages-source-mirror-prunes-generated", "scripts/build/build_pages.sh", "-path 'web/nemoclaw/standalone' -prune", "-path 'web/nemoclaw/standalone' -print"),
            ("pages-validation-fail-open", "scripts/build/build_pages.sh", 'python3 "$T1/scripts/validation/validate_bundle.py" --scope ship', 'python3 "$T1/scripts/validation/validate_bundle.py" --scope ship || true'),
            ("pages-report-reuse-fail-open", "scripts/build/build_pages.sh", 'validation_report_audit.py" \\', 'validation_report_audit.py" || true #'),
            ("mutable-action-ref", ".github/workflows/pages.yml", "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803", "actions/checkout@v6"),
            ("unpinned-workflow-install", ".github/workflows/pages.yml", "--requirement scripts/materials/requirements.lock", "requests beautifulsoup4 markdownify lxml"),
            ("github-material-lock", ".github/workflows/pages.yml", "scripts/materials/requirements.lock", "scripts/materials/requirements.txt"),
            ("github-binary-lock-install", ".github/workflows/pages.yml", "python3 -m pip install --require-hashes --no-deps --only-binary=:all:", "python3 -m pip install --require-hashes"),
            ("github-browser-runtime-lock", ".github/workflows/pages.yml", "      - name: Install the pinned host-browser API\n        working-directory: scripts/runtime\n        run: |\n          corepack enable\n          pnpm install --frozen-lockfile --ignore-scripts\n", "      - name: Install the unscoped host-browser API\n        run: |\n          corepack enable\n          pnpm install --frozen-lockfile --ignore-scripts\n"),
            ("github-browser-runtime-order", ".github/workflows/pages.yml", "      - name: Install the pinned host-browser API\n        working-directory: scripts/runtime\n        run: |\n          corepack enable\n          pnpm install --frozen-lockfile --ignore-scripts\n", "      - name: Install the pinned host-browser API too late\n        working-directory: scripts/runtime\n        run: |\n          python3 ../../scripts/validation/release_gate.py --tier ship\n          corepack enable\n          pnpm install --frozen-lockfile --ignore-scripts\n"),
            ("github-node-runtime", ".github/workflows/pages.yml", 'node-version: "24"', 'node-version: "20"'),
            ("release-browser-runtime-lock", ".github/workflows/release.yml", "      - name: Install the pinned host-browser API\n        working-directory: scripts/runtime\n        run: |\n          corepack enable\n          pnpm install --frozen-lockfile --ignore-scripts\n", "      - name: Install the unscoped host-browser API\n        run: |\n          corepack enable\n          pnpm install --frozen-lockfile --ignore-scripts\n"),
            ("release-browser-runtime-order", ".github/workflows/release.yml", "      - name: Install the pinned host-browser API\n        working-directory: scripts/runtime\n        run: |\n          corepack enable\n          pnpm install --frozen-lockfile --ignore-scripts\n", "      - name: Install the pinned host-browser API too late\n        working-directory: scripts/runtime\n        run: |\n          python3 ../../scripts/validation/release_gate.py --tier ship\n          corepack enable\n          pnpm install --frozen-lockfile --ignore-scripts\n"),
            ("release-node-runtime", ".github/workflows/release.yml", 'node-version: "24"', 'node-version: "20"'),
            ("shared-material-provenance", "scripts/validation/release_gate.py", 'py("scripts/materials/pull_materials.py", "--verify-committed")', 'py("scripts/materials/pull_materials.py", "--list")'),
            ("shared-material-selftest", "scripts/validation/release_gate.py", 'unit_test("materials")', 'py("scripts/materials/pull_materials.py", "--help")'),
            ("shared-local-path-selftest", "scripts/validation/release_gate.py", 'unit_test("local_path_leak_audit")', 'py("scripts/validation/local_path_leak_audit.py", "--help")'),
            ("shared-sensitive-content", "scripts/validation/release_gate.py", 'unit_test("sensitive_content_audit")', 'py("scripts/validation/sensitive_content_audit.py", "--help")'),
            ("shared-release-reminder", "scripts/validation/release_gate.py", 'unit_test("release_change_reminder")', 'py("scripts/validation/release_change_reminder.py", "--help")'),
            ("shared-language-ownership-test", "scripts/validation/release_gate.py", "    CONTRIBUTION_LANGUAGE_OWNERSHIP_TESTS,", '    py("scripts/validation/contribution_safety_audit.py", "--help"),'),
            ("shared-report-reuse-selftest", "scripts/validation/release_gate.py", 'unit_test("validation_report_audit")', 'py("scripts/validation/validation_report_audit.py", "--help")'),
            ("shared-pages-artifact-selftest", "scripts/validation/release_gate.py", 'unit_test("pages_artifact_integrity")', 'py("scripts/validation/pages_artifact_integrity.py", "--help")'),
            ("shared-standard-test-contract", "scripts/validation/release_gate.py", "    HARNESS_CONTRACT,\n", "    # standard contract removed\n"),
            ("shared-change-aware-gate", "scripts/validation/release_gate.py", '"--changed-since"', '"--changed-around"'),
            ("shared-gate-timing", "scripts/validation/release_gate.py", '"--timing-report"', '"--no-timing-report"'),
            ("shared-local-reuse", "scripts/validation/release_gate.py", '"--reuse-success"', '"--ignore-success"'),
            ("shared-sbom-policy-selftest", "scripts/validation/release_gate.py", 'py("scripts/security/audit_sbom_policy.py", "--self-test")', 'py("scripts/security/audit_sbom_policy.py", "--help")'),
            ("sbom-evidence-detector", "scripts/compliance/sbom_evidence.py", "nemoclaw:license-resolution:raw-sbom-sha256", "removed-raw-sbom-binding"),
            ("sbom-evidence-catalog", "scripts/compliance/docs/sbom_evidence.json", '"id": "python-material-tooling"', '"id": "removed-tooling"'),
            ("pr-deploy-boundary", ".github/workflows/pages.yml", "if: github.event_name != 'pull_request'", "if: always()"),
            ("pages-main-only", ".github/workflows/pages.yml", "github.ref == 'refs/heads/main'", "github.ref != ''"),
            ("checkout-credential", ".github/workflows/pages.yml", "persist-credentials: false", "persist-credentials: true"),
            ("dependency-review-floor", ".github/workflows/dependency-review.yml", "fail-on-severity: moderate", "fail-on-severity: critical"),
            ("codeql-baseline", ".github/workflows/codeql.yml", "javascript-typescript", "javascript-disabled"),
            ("codeql-baseline", ".github/workflows/codeql.yml", "      actions: read\n", "      actions: none\n"),
            ("dependency-update-coverage", ".github/dependabot.yml", "package-ecosystem: npm", "package-ecosystem: unsupported"),
            ("release-draft", ".github/workflows/release.yml", "--draft --verify-tag", "--verify-tag"),
            ("release-annotated-tag", ".github/workflows/release.yml", 'git cat-file -t "refs/tags/$RELEASE_TAG"', 'git cat-file -t "$RELEASE_TAG^{commit}"'),
            ("release-artifact-set", ".github/workflows/release.yml", "test -f release-assets/release-manifest.json", "test -f release-assets/manifest.json"),
            ("release-package-contract", "scripts/build/package_release.py", "mtime=0", "mtime=None"),
            ("release-malware-evidence-contract", "scripts/build/package_release.py", '"malware_scan_required"', '"scan_optional"'),
            ("release-malware-evidence-doc", "docs/release_artifacts.md", "required-before-publication", "optional-after-publication"),
            ("release-build-epoch", "scripts/build/build_branch_manifest.py", 'os.environ.get("SOURCE_DATE_EPOCH")', 'os.environ.get("BUILD_TIME")'),
            ("publication-release-guard", ".github/workflows/release.yml", "contribution_safety_audit.py --require-publication-approved", "contribution_safety_audit.py"),
            ("publication-deploy-guard", ".github/workflows/pages.yml", "contribution_safety_audit.py --require-publication-approved", "contribution_safety_audit.py"),
            ("github-reviewed-artifact-handoff", ".github/workflows/pages.yml", "needs: [build-and-verify, rebuild-for-comparison]", "needs: build-and-verify"),
            ("github-pages-browser-review", ".github/workflows/pages.yml", "runtime_integration_browser_audit.py --site-root public --timeout-ms 180000", "runtime_integration_browser_audit.py --site-root web --timeout-ms 180000"),
            ("github-pages-artifact-integrity", ".github/workflows/pages.yml", "--write-manifest public/pages-sha256.txt", "--write-manifest web/pages-sha256.txt"),
            ("artifact-full-commit-binding", ".github/workflows/pages.yml", '--expect-sha "$GITHUB_SHA"', '--expect-sha "${GITHUB_SHA::7}"'),
            ("github-pages-artifact-reverification", ".github/workflows/pages.yml", "--check-manifest reviewed-public/pages-sha256.txt", "--write-manifest reviewed-public/pages-sha256.txt"),
            ("release-material-sbom", ".github/workflows/release.yml", "pip-audit -r scripts/materials/requirements.lock", "pip-audit -r scripts/materials/requirements.txt"),
            ("github-pages-provenance", ".github/workflows/pages.yml", "subject-path: reviewed-pages/pages-sha256.txt", "subject-path: reviewed-pages/unreviewed.txt"),
            ("github-pages-provenance", ".github/workflows/pages.yml", "needs: attest-provenance", "needs: build-and-verify"),
            ("github-pages-provenance", ".github/workflows/pages.yml", "cmp reviewed-public/pages-sha256.txt", "echo comparison-skipped"),
            ("github-pages-provenance-authority", ".github/workflows/pages.yml", "      attestations: write\n      artifact-metadata: write", "      attestations: read\n      artifact-metadata: read"),
            ("github-pages-build-authority", ".github/workflows/pages.yml", "    needs: test\n    runs-on: ubuntu-latest\n    timeout-minutes: 45\n    steps:", "    needs: test\n    runs-on: ubuntu-latest\n    timeout-minutes: 45\n    permissions:\n      id-token: write\n    steps:"),
            ("github-pages-build-dependency-isolation", ".github/workflows/pages.yml", "      - name: Build the client-side static site\n", "      - name: Build the client-side static site\n        run: npm ci\n"),
            ("github-pages-signing-source-execution", ".github/workflows/pages.yml", "    needs: compare-builds\n    runs-on: ubuntu-latest\n", "    needs: compare-builds\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@bad\n"),
            ("github-pages-deploy-source-execution", ".github/workflows/pages.yml", "    steps:\n      - id: deploy\n", "    steps:\n      - run: python3 scripts/steal_token.py\n      - id: deploy\n"),
            ("github-source-resource-preflight", ".github/workflows/pages.yml", "pages_artifact_integrity.py --source-root .", "pages_artifact_integrity.py --help"),
            ("release-source-resource-preflight", ".github/workflows/release.yml", "pages_artifact_integrity.py --source-root .", "pages_artifact_integrity.py --help"),
            ("release-live-material-check", ".github/workflows/release.yml", "pull_materials.py --check --fetch-attempts", "pull_materials.py --list --fetch-attempts"),
            ("release-sca-lock", ".github/workflows/release.yml", "scripts/security/requirements-sca.lock", "pip-audit cyclonedx-bom"),
            ("release-binary-lock-install", ".github/workflows/release.yml", ".release-scan-venv/bin/python -m pip install --require-hashes --no-deps --only-binary=:all:", ".release-scan-venv/bin/python -m pip install --require-hashes"),
            ("release-sbom-policy", ".github/workflows/release.yml", "--report release-security/sbom-policy.json", "--report release-security/unchecked-policy.json"),
            ("release-sbom-evidence-generation", ".github/workflows/release.yml", "--manifest-out release-security/python-sbom-evidence.json", "--manifest-out release-security/unchecked-evidence.json"),
            ("release-provenance", ".github/workflows/release.yml", "subject-checksums: release-assets/SHA256SUMS", "subject-checksums: release-assets/unchecked"),
            ("release-provenance", ".github/workflows/release.yml", "dispatch the workflow from the exact release tag", "dispatch accepted from any ref"),
            ("release-provenance-authority", ".github/workflows/release.yml", "      attestations: write\n      artifact-metadata: write", "      attestations: read\n      artifact-metadata: read"),
            ("release-independent-rebuild", ".github/workflows/release.yml", "cmp release-evidence/pages-sha256.txt", "echo comparison-skipped"),
            ("release-build-authority", ".github/workflows/release.yml", "  build-and-package:\n    needs: validate-and-scan\n", "  build-and-package:\n    needs: validate-and-scan\n    permissions:\n      id-token: write\n"),
            ("release-assembly-dependency-isolation", ".github/workflows/release.yml", "      - name: Assemble without installed validation dependencies\n", "      - name: Assemble without installed validation dependencies\n        run: npm ci\n"),
            ("discussion-route", ".github/ISSUE_TEMPLATE/config.yml", "/discussions", "/issues"),
            ("external-repository", ".github/ISSUE_TEMPLATE/config.yml", "https://github.com/NVDLI/NemoClawDLI/discussions", "https://github.com/example/incorrect/discussions"),
            ("issue-production-scope", ".github/ISSUE_TEMPLATE/runtime-deploy.yml", "static `web/nemoclaw/` course", "CPU service stack"),
            ("retired-runtime-scope", ".github/ISSUE_TEMPLATE/runtime-deploy.yml", "External runtime integration", "Shared service stack"),
            ("submission-template", ".github/PULL_REQUEST_TEMPLATE.md", "## Blast radius checked", "## Scope notes"),
            ("stacked-submission-template", ".gitlab/merge_request_templates/Default.md", "host-generated squash", "automatic integration"),
            ("localization-ownership-template", ".github/PULL_REQUEST_TEMPLATE.md", "localized learner prose changed", "translation files changed"),
            ("gitlab-description-window", ".gitlab/merge_request_templates/Default.md", "## Validation evidence", "x" * 2700 + "\n## Validation evidence"),
            ("mutating-prepush", "scripts/git-hooks/pre-push", "REFUSING PUSH - origin/main is", "git pull --rebase origin main # REFUSING PUSH - origin/main is"),
            ("fetch-fail-open", "scripts/git-hooks/pre-push", "if ! git fetch origin main --quiet; then", "git fetch origin main --quiet || exit 0\n    if false; then"),
            ("remote-fail-open", "scripts/git-hooks/pre-push", "if [ \"$REMOTE\" = \"origin\" ]; then", "[ \"$REMOTE\" = \"origin\" ] || exit 0\nif false; then"),
            ("precommit-local-path", "scripts/git-hooks/pre-commit", "local_path_leak_audit.py", "local_path_check_removed.py"),
            ("precommit-local-path-staged", "scripts/git-hooks/pre-commit", '"$LOCAL_PATH_AUDIT" --staged', '"$LOCAL_PATH_AUDIT"'),
            ("prepush-local-path", "scripts/git-hooks/pre-push", "local_path_leak_audit.py", "local_path_check_removed.py"),
            ("precommit-sensitive", "scripts/git-hooks/pre-commit", "sensitive_content_audit.py", "sensitive_content_check_removed.py"),
            ("precommit-sensitive-staged", "scripts/git-hooks/pre-commit", '"$SENSITIVE_AUDIT" --staged', '"$SENSITIVE_AUDIT"'),
            ("prepush-range", "scripts/git-hooks/pre-push", 'RANGE="origin/main..HEAD"', 'RANGE="HEAD"'),
            ("prepush-dco", "scripts/git-hooks/pre-push", 'python3 "$SAFETY" --commit-range "$RANGE"', 'python3 "$SAFETY" --help'),
            ("prepush-local-path-range", "scripts/git-hooks/pre-push", 'python3 "$LOCAL_PATH_AUDIT" --commit-range "$RANGE"', 'python3 "$LOCAL_PATH_AUDIT" --help'),
            ("prepush-sensitive-range", "scripts/git-hooks/pre-push", 'python3 "$SENSITIVE_AUDIT" --commit-range "$RANGE"', 'python3 "$SENSITIVE_AUDIT" --help'),
            ("prepush-release-reminder", "scripts/git-hooks/pre-push", 'python3 "$RELEASE_REMINDER" --commit-range "$RANGE"', 'python3 "$RELEASE_REMINDER" --help'),
            ("prepush-canonical-gate", "scripts/git-hooks/pre-push", '--tier ship --no-write --changed-since origin/main --reuse-success', '--tier fast'),
            ("worktree-hook-dispatch", "scripts/build/install-hooks.sh", 'hook="$content_root/scripts/git-hooks/$name"', 'hook="$HERE/git-hooks/$name"'),
            ("gitlab-safety-selftest", ".gitlab/ci/core.yml", "release_gate.py --tier ship", "release_gate.py --tier fast"),
            ("gitlab-source-resource-preflight", ".gitlab/ci/core.yml", "pages_artifact_integrity.py --source-root .", "pages_artifact_integrity.py --help"),
            ("gitlab-change-aware-gate", ".gitlab/ci/core.yml", 'GATE_ARGS+=(--changed-since "$GATE_BASE")', 'GATE_ARGS=() # no change selection'),
            ("gitlab-gate-timing", ".gitlab/ci/core.yml", "--timing-report docs/validation/release-gate-timings.json", "--no-timing-report"),
            ("gitlab-report-browser-runtime", ".gitlab/ci/core.yml", 'BROWSER_TOOLS_REQUIRED: "1"', 'BROWSER_TOOLS_REQUIRED: "0"'),
            ("gitlab-immutable-report-reuse", ".gitlab/ci/core.yml", 'bash scripts/build/build_pages.sh "$CI_PROJECT_DIR/candidate"', 'bash scripts/build/build_pages.sh "$CI_PROJECT_DIR/rebuilt-candidate"'),
            ("gitlab-protected-root-worktree", ".gitlab/ci/core.yml", 'git worktree add --quiet --detach /tmp/nemoclaw-prod-root "origin/$prod_ref"', 'git archive "origin/$prod_ref" | tar -x -C /tmp/nemoclaw-prod-root'),
            ("gitlab-image-pin", ".gitlab/ci/core.yml", "node:20-bookworm-slim@sha256:25070a03f077f5860e4f2db8d147380678ed40ead415a21eaffd5a6208f61948", "node:20-bookworm-slim"),
            ("gitlab-report-browser-runtime", ".gitlab/ci/core.yml", "mcr.microsoft.com/playwright:v1.61.1-noble@sha256:5b8f294aff9041b7191c34a4bab3ac270157a28774d4b0660e9743297b697e48", "mcr.microsoft.com/playwright:v1.61.1-noble"),
            ("gitlab-runtime-sca", ".gitlab/ci/sca.yml", "npm audit --prefix .cache/runtime-npm-audit --package-lock-only --audit-level=moderate", "echo runtime-audit-skipped"),
            ("gitlab-infrastructure-retry", ".gitlab/ci/core.yml", "runner_system_failure", "runner_unsupported"),
            ("gitlab-script-retry", ".gitlab/ci/core.yml", "runner_system_failure", "script_failure"),
            ("gitlab-material-install", ".gitlab/ci/core.yml", "scripts/materials/requirements.lock", "scripts/materials/requirements.txt"),
            ("gitlab-pages-material-install", ".gitlab/ci/core.yml", '  # localization/material tooling even when live pulls are disabled.\n  variables:\n    MATERIAL_TOOLS_REQUIRED: "1"', '  # localization/material tooling even when live pulls are disabled.\n  variables:\n    MATERIAL_TOOLS_REQUIRED: "0"'),
            ("gitlab-deploy-gate", ".gitlab/ci/core.yml", '  needs: ["test"]', '  needs: ["skipped_test"]'),
            ("gitlab-preview-ref-fetch", ".gitlab/ci/core.yml", 'git fetch "$preview_remote" "+refs/heads/$branch:refs/remotes/$preview_namespace/$branch" --quiet', 'git fetch "$preview_remote" "+refs/heads/$branch:refs/remotes/$preview_namespace/$branch" --quiet || true'),
            ("gitlab-preview-ref-fetch", ".gitlab/ci/core.yml", 'preview_remote="$CI_MERGE_REQUEST_SOURCE_PROJECT_URL"', 'preview_remote="origin"'),
            ("gitlab-transient-material-policy", ".gitlab/ci/core.yml", "pull_materials.py --check --allow-transient-unreachable", "pull_materials.py --check --strict-unreachable"),
            ("gitlab-scheduled-material-policy", ".gitlab/ci/core.yml", "pull_materials.py --check --fetch-attempts", "pull_materials.py --check --allow-transient-unreachable --fetch-attempts"),
            ("gitlab-complete-history", ".gitlab/ci/core.yml", 'GIT_DEPTH: "0"', 'GIT_DEPTH: "20"'),
            ("gitlab-dco-check", ".gitlab/ci/core.yml", 'contribution_safety_audit.py --commit-range "${CI_MERGE_REQUEST_DIFF_BASE_SHA}..${CI_COMMIT_SHA}"', 'contribution_safety_audit.py --commit-range "${CI_COMMIT_SHA}"'),
            ("gitlab-local-path-range", ".gitlab/ci/core.yml", 'local_path_leak_audit.py --commit-range "${CI_MERGE_REQUEST_DIFF_BASE_SHA}..${CI_COMMIT_SHA}"', 'local_path_leak_audit.py --help'),
            ("github-local-path-range", ".github/workflows/pages.yml", 'local_path_leak_audit.py --commit-range "$PATH_RANGE"', 'local_path_leak_audit.py --help'),
            ("gitlab-sensitive-submission", ".gitlab/ci/core.yml", "sensitive_content_audit.py --submission-env CI_MERGE_REQUEST_TITLE", "sensitive_content_audit.py --help"),
            ("gitlab-sensitive-range", ".gitlab/ci/core.yml", 'sensitive_content_audit.py --commit-range "${CI_MERGE_REQUEST_DIFF_BASE_SHA}..${CI_COMMIT_SHA}"', 'sensitive_content_audit.py --help'),
            ("github-sensitive-submission", ".github/workflows/pages.yml", "sensitive_content_audit.py --submission-env SENSITIVE_TITLE", "sensitive_content_audit.py --help"),
            ("github-sensitive-range", ".github/workflows/pages.yml", 'sensitive_content_audit.py --commit-range "$SENSITIVE_RANGE"', 'sensitive_content_audit.py --help'),
            ("github-release-reminder", ".github/workflows/pages.yml", 'release_change_reminder.py --commit-range "$RELEASE_CHANGE_RANGE"', 'release_change_reminder.py --help'),
            ("github-change-aware-gate", ".github/workflows/pages.yml", '--changed-since "$GATE_BASE"', '--changed-around "$GATE_BASE"'),
            ("github-gate-timing", ".github/workflows/pages.yml", "--timing-report docs/validation/release-gate-timings.json", "--no-timing-report"),
            ("github-report-reuse", ".github/workflows/pages.yml", "BUILD_PAGES_REUSE_VALIDATION=1", "BUILD_PAGES_REUSE_VALIDATION=0"),
            ("github-immutable-report-reuse", ".github/workflows/pages.yml", "BUILD_PAGES_PULL_MATERIALS=0 BUILD_PAGES_REUSE_VALIDATION=1", "BUILD_PAGES_REUSE_VALIDATION=1"),
            ("gitlab-release-reminder", ".gitlab/ci/core.yml", 'release_change_reminder.py --commit-range "${CI_MERGE_REQUEST_DIFF_BASE_SHA}..${CI_COMMIT_SHA}"', 'release_change_reminder.py --help'),
            ("submission-release-reminder", ".github/PULL_REQUEST_TEMPLATE.md", "## External release follow-up", "## Optional follow-up"),
            ("shared-lock-selftest", "scripts/validation/release_gate.py", 'py("scripts/security/audit_dependency_locks.py", "--self-test")', 'py("scripts/security/audit_dependency_locks.py", "--version")'),
            ("gitlab-sbom-policy", ".gitlab/ci/sca.yml", "audit_sbom_policy.py --sbom", "audit_sbom_policy.py --help"),
            ("gitlab-sbom-evidence", ".gitlab/ci/sca.yml", "scripts/compliance/resolve_sbom_licenses.py --input scripts/security/reports/python-materials/python-env.raw.cdx.json", "scripts/compliance/resolve_sbom_licenses.py --help"),
            ("gitlab-sca-lock", ".gitlab/ci/sca.yml", ".sca-tools-venv/bin/python -m pip install --require-hashes --no-deps --only-binary=:all: -q -r scripts/security/requirements-sca.lock", ".sca-tools-venv/bin/python -m pip install -q pip-audit cyclonedx-bom"),
            ("github-hash-lock-install", ".github/workflows/pages.yml", "--require-hashes --no-deps --only-binary=:all:", "--no-deps --only-binary=:all:"),
            ("gitlab-human-review", ".gitlab/ci/core.yml", "human_review:", "operator_review:"),
            ("gitlab-theme-runtime", ".gitlab/ci/core.yml", "theme_runtime:", "theme_runtime_removed:"),
            ("gitlab-theme-runtime-command", ".gitlab/ci/core.yml", '--site-root "$THEME_SITE_ROOT" --scan-root "$THEME_SCAN_ROOT"', "--site-root selected"),
            ("gitlab-theme-runtime-deployed-root", ".gitlab/ci/core.yml", "THEME_SITE_ROOT=public", 'THEME_SITE_ROOT="public/$CI_COMMIT_REF_SLUG"'),
            ("gitlab-preview-manifest-projection", ".gitlab/ci/core.yml", 'project_artifact_manifests.py public --manifest-root "public/$CI_COMMIT_REF_SLUG"', "project_artifact_manifests.py public/preview"),
            ("gitlab-production-manifest-projection", ".gitlab/ci/core.yml", "        python3 scripts/build/project_artifact_manifests.py public\n", "        python3 scripts/build/project_artifact_manifests.py public-root\n"),
            ("gitlab-combined-artifact-link-audit", ".gitlab/ci/core.yml", 'artifact_link_audit.py "public/$CI_COMMIT_REF_SLUG"', "artifact_link_audit.py selected-preview"),
            ("gitlab-human-review-needs", ".gitlab/ci/core.yml", 'needs: ["test", "pages_smoke", "theme_runtime"]', 'needs: ["test", "pages_smoke"]'),
            ("gitlab-human-review-blocking", ".gitlab/ci/core.yml", '    - if: \'$CI_PIPELINE_SOURCE == "merge_request_event"\'\n      when: manual\n      allow_failure: false\n', '    - if: \'$CI_PIPELINE_SOURCE == "merge_request_event"\'\n      when: on_success\n      allow_failure: true\n'),
            ("material-transient-classification", "scripts/materials/pull_materials.py", "TRANSIENT_HTTP_STATUS = {", "RETRYABLE_STATUS_REMOVED = {"),
            ("material-redirect-boundary", "scripts/materials/pull_materials.py", "refusing source redirect", "following source redirect"),
            ("material-full-sha", "scripts/materials/pull_materials.py", 're.fullmatch(r"[0-9a-f]{64}"', 're.fullmatch(r"[0-9a-f]{16}"'),
            ("material-offline-verifier", "scripts/materials/pull_materials.py", "def verify_committed", "def verify_removed"),
            ("material-fail-closed-policy", "scripts/materials/pull_materials.py", "def check_passes", "def check_removed"),
            ("material-explicit-degradation", "scripts/materials/pull_materials.py", '"--allow-transient-unreachable"', '"--allow-all-unreachable"'),
            ("material-provenance-sha", "web/nemoclaw/mats/_materials.json", "7a583caa8f1db1e66220cfa8963b7b37dcaf5655df0e1314f8794ea1ba5c8c94", "7a583caa8f1db1e6"),
            ("approval-not-control", "README.md", "approval does not replace a missing control", "approval completes the control"),
            ("root-license", "LICENSE", NVIDIA_APACHE_COPYRIGHT, "Copyright removed"),
            ("root-license", "LICENSE", "Apache License", "Example License"),
            ("cla-applicability", "CONTRIBUTING.md", "does not require a separate contributor license agreement", "may require another agreement"),
            ("approval-not-control", "CONTRIBUTING.md", "Human review identifies accountability but is not a compensating", "Human review is a compensating"),
            ("agent-dco", "AGENTS.md", "Every proposed commit", "Every release"),
            ("release-status", "RELEASE_STATUS.json", '"approved-for-publication"', '"published"'),
            ("release-status", "RELEASE_STATUS.json", '"external_mirror": "populated"', '"external_mirror": "not-published"'),
            ("release-status", "RELEASE_STATUS.json", '"maintenance_status": "active"', '"maintenance_status": "archived"'),
            ("decision-policy", "RELEASE_STATUS.json", '"authorization_record": "external-not-repository"', '"authorization_record": "author-supplied"'),
            ("private-decision-record", "RELEASE_STATUS.json", '"notice_required": false', '"publication_decision": {},\n  "notice_required": false'),
            ("notice-state", "RELEASE_STATUS.json", '"notice_required": false', '"notice_required": true'),
            ("release-playbook", "docs/release_playbook.md", "Host settings are not versioned by this repository", "Host settings checklist"),
            ("container-boundary-detector", "scripts/validation/container_boundary_audit.py", 'FORBIDDEN_NAMES = {".dockerignore", "Dockerfile", "Containerfile"', "FORBIDDEN_NAMES = set() #"),
            ("approval-not-control", "docs/release_playbook.md", "Protected approval identifies who is accountable; it is not a compensating control", "Protected approval completes the control"),
            ("approval-not-control", "docs/agent_process.md", "A human referral is not a defense", "A human referral closes the concern"),
            ("submission-risk-decision", ".github/PULL_REQUEST_TEMPLATE.md", "review text is not a compensating control", "review text completes the control"),
            ("submission-risk-decision", ".gitlab/merge_request_templates/Default.md", "review text is not a compensating control", "review text completes the control"),
        )
        originals = {
            rel: (fixture / rel).read_text(encoding="utf-8")
            for rel in CONTRACT_FILES
        }
        for expected, rel, old, new in cases:
            raw = originals[rel]
            if old not in raw:
                failures.append(f"fixture token missing for {expected}: {rel}: {old}")
                continue
            mutated = dict(originals)
            mutated[rel] = raw.replace(old, new, 1)
            codes = {item["code"] for item in audit_repo(fixture, text_overrides=mutated)}
            if expected not in codes:
                failures.append(f"mutation escaped detector: {expected}")

        retired = fixture / "QUALITY_DIRECTIVES.md"
        retired.write_text("stale duplicate guidance\n", encoding="utf-8")
        if "retired-guidance" not in {item["code"] for item in audit_repo(fixture)}:
            failures.append("retired guidance mutation escaped detector")
        retired.unlink()

        status_path = fixture / "RELEASE_STATUS.json"
        approved = json.loads(status_path.read_text(encoding="utf-8"))
        if audit_publication_approval(fixture):
            failures.append("approved public-safe release state was rejected")
        for label, expected, mutate in (
            ("pending state", "publication-approval", lambda value: value.update(
                publication_state="pending-osrb-approval"
            )),
            ("inconsistent published state", "release-status", lambda value: value.update(
                publication_state="published"
            )),
            ("embedded private decision", "private-decision-record", lambda value: value.update(
                publication_decision={"record": "must remain external"}
            )),
            ("weakened decision policy", "decision-policy", lambda value: value["decision_policy"].update(
                protected_environment_required=False
            )),
        ):
            invalid = json.loads(json.dumps(approved))
            mutate(invalid)
            status_path.write_text(json.dumps(invalid, indent=2) + "\n", encoding="utf-8")
            if expected not in {item["code"] for item in audit_publication_approval(fixture)}:
                failures.append(f"{label} escaped the external publication guard")

    good = """## Summary\nBound the release path.\n## Issue link\nCloses #12\n## Surfaces touched\n- [x] `scripts/`\n## Blast radius checked\nHooks and CI.\n## Validation evidence\nPASS: audit.\n## Human ownership\nRelease manager reviews.\n## Risk and rollback\nRevert commit.\n## Out of scope\nHost settings.\n"""
    if audit_submission(good):
        failures.append("valid submission fixture rejected")
    localized = good.replace("- [x] `scripts/`", "- [x] `i18n/`")
    if audit_submission(localized):
        failures.append("valid localization submission fixture rejected")
    if audit_publication_approval(ROOT):
        failures.append("approved release unexpectedly failed the external publication guard")
    partial = good.replace("Closes #12", "Addresses #12").replace(
        "## Out of scope", "## Remaining issue work\nHost approval remains.\n## Out of scope", 1)
    if audit_submission(partial):
        failures.append("valid partial submission fixture rejected")
    if "submission-issue-remains" not in {
        item["code"] for item in audit_submission(good.replace("Closes #12", "Addresses #12"))
    }:
        failures.append("partial issue relationship without remaining work escaped detector")
    for needle, expected in (("## Human ownership\nRelease manager reviews.\n", "submission-section"),
                             ("Closes #12", "submission-issue"), ("PASS: audit.", "submission-evidence")):
        codes = {item["code"] for item in audit_submission(good.replace(needle, "", 1))}
        if expected not in codes:
            failures.append(f"submission mutation escaped detector: {expected}")
    long_body = good.replace("## Out of scope", "x" * 2700 + "\n## Out of scope", 1)
    if "submission-description-window" not in {item["code"] for item in audit_submission(long_body)}:
        failures.append("submission description-window mutation escaped detector")
    signed = [("abc123", "Example Contributor", "contributor@example.com",
               "Change course\n\nSigned-off-by: Example Contributor <contributor@example.com>\n")]
    if audit_commit_records(signed):
        failures.append("valid DCO signoff fixture rejected")
    for record in (
        [("abc123", "Example Contributor", "contributor@example.com", "Unsigned change\n")],
        [("abc123", "Example Contributor", "contributor@example.com",
          "Wrong signer\n\nSigned-off-by: Other Person <other@example.com>\n")],
    ):
        if "commit-signoff" not in {item["code"] for item in audit_commit_records(record)}:
            failures.append("commit signoff mutation escaped detector")
    locale_path = "i18n/es/web/nemoclaw/01a-loop.html"
    canonical_path = "web/nemoclaw/01a-loop.html"
    credited = "## Unreleased\n\n- Thanks to Example Contributor for the Spanish translation.\n"
    href_before = '<a href="../index.html" aria-label="Inicio">Volver</a>'
    href_after = '<a href="index.html" aria-label="Inicio">Volver</a>'
    if learner_text(href_before) != learner_text(href_after):
        failures.append("transport-only href change was misclassified as learner prose")
    if learner_text(href_after) == learner_text(
            '<a href="index.html" aria-label="Inicio del curso">Volver</a>'):
        failures.append("learner-facing accessibility prose change escaped classification")
    if audit_language_ownership(
            [locale_path, canonical_path], "", ["Navigation update"], set()):
        failures.append("transport-only localized HTML change required prose ownership")
    if audit_language_ownership([locale_path, "CHANGELOG.md"], credited, ["Locale update"]):
        failures.append("credited locale-only change rejected")
    ownership_cases = (
        ([locale_path], credited, ["Locale update"], "contributor-credit"),
        ([locale_path, "CHANGELOG.md"], "## Unreleased\n\n- Locale update.\n", ["Locale update"], "contributor-credit"),
        ([locale_path, canonical_path, "CHANGELOG.md"], credited, ["Mixed update"], "mixed-language-ownership"),
    )
    for paths, changelog, messages, expected in ownership_cases:
        codes = {item["code"] for item in audit_language_ownership(paths, changelog, messages)}
        if expected not in codes:
            failures.append(f"language ownership mutation escaped detector: {expected}")
    reviewed = "Mixed update\n\nLocalization-Review: es=Example Reviewer\n"
    if audit_language_ownership(
            [locale_path, canonical_path, "CHANGELOG.md"], credited, [reviewed]):
        failures.append("reviewed mixed-language change rejected")
    return failures


def emit(findings: list[dict[str, str]], label: str, report: str | None = None) -> int:
    result = {"schema": "nemoclaw-contribution-safety/1", "ok": not findings,
              "label": label, "findings": findings}
    if report:
        path = Path(report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if findings:
        print(f"contribution safety: FAIL ({len(findings)})")
        for item in findings:
            print(f"  [{item['code']}] {item['path']}: {item['message']}")
            print(f"    fix: {item['fix']}")
        return 1
    print(f"contribution safety: OK ({label})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--require-publication-approved", action="store_true")
    parser.add_argument("--submission-env", metavar="NAME")
    parser.add_argument("--commit-range", metavar="BASE..HEAD")
    parser.add_argument("--report")
    args = parser.parse_args()
    if args.require_publication_approved:
        return emit(audit_publication_approval(), "external publication approval", args.report)
    if args.self_test:
        failures = self_test()
        findings = [finding("self-test", "mutation", item, "repair the escaped detector") for item in failures]
        return emit(findings, "mutation self-test", args.report)
    if args.submission_env:
        return emit(audit_submission(os.environ.get(args.submission_env, "")), "submission", args.report)
    if args.commit_range:
        return emit(audit_commit_range(args.commit_range), "commit signoff", args.report)
    return emit(audit_repo(), "repository", args.report)


if __name__ == "__main__":
    raise SystemExit(main())
