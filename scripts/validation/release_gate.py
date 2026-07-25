#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run the canonical deterministic repository validation ladder.

Host-specific submission, commit-range, live-source, and deployment checks remain in
their workflows. This script owns the deterministic checks shared by local contributors,
GitLab, GitHub Pages, and the protected release workflow.

Use ``--changed-since`` on proposal branches. Current-tree audits still run, while expensive
mutation suites run only when their validator or protected contract changed. Omit the option
for a full release execution. Successful clean local runs record untracked cache evidence under
the worktree's Git directory, including ``--no-write`` runs that suppress repository reports.
``--reuse-success`` may reuse only the identical commit, base, mode, and gate definition. A truly
read-only mount simply cannot record the optional cache and remains a valid execution environment.
CI never depends on that local optimization.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

try:
    from scripts.validation import reacs_registry
except ModuleNotFoundError:  # direct ``python scripts/validation/release_gate.py`` entry point
    import reacs_registry


ROOT = Path(__file__).resolve().parents[2]
PYTHON = sys.executable
CACHE_SCHEMA = "release-gate-success/2"
TIMING_SCHEMA = "release-gate-timing/2"
REGISTRY = reacs_registry.load_registry()


def py(path: str, *args: str) -> tuple[str, ...]:
    return (PYTHON, path, *args)


def unit_test(name: str) -> tuple[str, ...]:
    return py(
        "-m", "unittest", "-v",
        f"tests.validation.test_embedded_validator_suites.ValidatorSelfTests.test_{name}",
    )


def cli_unit_test(name: str) -> tuple[str, ...]:
    return py(
        "-m", "unittest", "-v",
        f"tests.validation.test_embedded_validator_suites.ValidatorCliTests.test_{name}",
    )


HARNESS_CONTRACT = py("-m", "unittest", "-v", "tests.validation.test_test_harness_contract")
NODE_VALIDATOR_TESTS = ("bash", "scripts/runtime/run_node.sh", "tests/runtime/test_embedded_validator_suites.mjs")
COLOR_THEME_TESTS = py("-m", "unittest", "-v", "tests.validation.test_color_theme")
THEME_RUNTIME_CONTRACT_TESTS = py("-m", "unittest", "-v", "tests.validation.test_theme_runtime_contract")
ARTIFACT_NAVIGATION_TESTS = py("-m", "unittest", "-v", "tests.validation.test_artifact_navigation_projection")
CONTRIBUTION_LANGUAGE_OWNERSHIP_TESTS = py(
    "-m", "unittest", "-v", "tests.validation.test_contribution_language_ownership",
)
FOYER_BRANCH_PATH_TESTS = py("-m", "unittest", "-v", "tests.validation.test_foyer_branch_paths")
SOURCE_LICENSE_CONTRACT_TESTS = py(
    "-m", "unittest", "-v", "tests.validation.test_source_license_contract",
)
PYODIDE_RUNTIME_SMOKE = ("bash", "scripts/runtime/run_node.sh", "scripts/pyodide/runtime_smoke.mjs", "--cdn")
REACS_REGISTRY_TESTS = py("-m", "unittest", "-v", "tests.validation.test_reacs_registry")
PRIVILEGED_COURSE_OPS_TESTS = py("-m", "unittest", "-v", "tests.validation.test_privileged_course_ops")
STANDARD_TEST_DISCOVERY = py("-m", "unittest", "discover", "-v", "-s", "tests/validation")


FAST_COMMANDS: tuple[tuple[str, ...], ...] = (
    REACS_REGISTRY_TESTS,
    py("scripts/validation/container_boundary_audit.py", "--self-test"),
    py("scripts/validation/container_boundary_audit.py"),
    py("scripts/build/bundle_standalone.py", "--self-test"),
    unit_test("artifact_link_audit"),
    ARTIFACT_NAVIGATION_TESTS,
    py("scripts/build/build_security_review_package.py", "--self-test"),
    py("scripts/materials/pull_materials.py", "--verify-committed"),
    unit_test("local_path_leak_audit"),
    py("scripts/validation/local_path_leak_audit.py"),
    unit_test("external_link_attribution_audit"),
    py("scripts/validation/external_link_attribution_audit.py"),
    unit_test("sensitive_content_audit"),
    unit_test("release_change_reminder"),
    unit_test("validation_report_audit"),
    unit_test("pages_artifact_integrity"),
    unit_test("threat_control_audit"),
    unit_test("repository_sync_audit"),
    unit_test("gitlab_ci_policy"),
    py("scripts/validation/gitlab_ci_policy.py"),
    py("scripts/skills/skill_consistency.py"),
    py("scripts/skills/gen_directory_beacons.py", "--check"),
    py("scripts/skills/normalize_skill_headers.py", "--self-test"),
    py("scripts/skills/normalize_skill_headers.py", "--check"),
    py("scripts/skills/test_skill_contract.py"),
    py("scripts/skills/skill_contract.py"),
    unit_test("project_docs_explorer"),
    HARNESS_CONTRACT,
    py("scripts/build/project_docs_explorer.py", "--audit"),
    py("scripts/build/project_source_tree.py", "--self-test"),
    py("scripts/build/project_source_tree.py", "--check-generated"),
    py("scripts/security/audit_iframe_proxy_opt_in.py"),
    py("scripts/validation/endpoint_registration_audit.py"),
    ("bash", "scripts/runtime/run_node.sh", "scripts/validation/openclaw_connection_audit.mjs"),
    py("scripts/compliance/source_gate.py"),
    SOURCE_LICENSE_CONTRACT_TESTS,
    py("scripts/compliance/source_document_audit.py"),
    unit_test("source_document_audit"),
    py("scripts/pyodide/integration_audit.py"),
    unit_test("pyodide_integration_audit"),
    PYODIDE_RUNTIME_SMOKE,
    py("scripts/compliance/third_party_inventory_audit.py"),
    unit_test("third_party_inventory_audit"),
    unit_test("export_third_party_csv"),
    unit_test("export_legal_scope_csv"),
    unit_test("render_sbom_license_inventory"),
    unit_test("resolve_sbom_licenses"),
    unit_test("sbom_evidence"),
    py("scripts/compliance/sbom_evidence.py", "--check"),
    py("scripts/validation/tenets.py", "--check"),
    py("scripts/runtime/module_check.py"),
    py("scripts/validation/interface_inventory_audit.py"),
    COLOR_THEME_TESTS,
    THEME_RUNTIME_CONTRACT_TESTS,
    py("scripts/validation/color_theme.py"),
    STANDARD_TEST_DISCOVERY,
    py("scripts/validation/validator_specialization_audit.py"),
    PRIVILEGED_COURSE_OPS_TESTS,
    py("-m", "unittest", "-v", "tests.validation.test_codeql_sarif_audit"),
    py("scripts/security/audit_codeql_sarif.py"),
    py("scripts/validation/browser_security_boundary_audit.py", "--self-test"),
    py("scripts/validation/browser_security_boundary_audit.py"),
    py("scripts/materials/build_rag_index.py", "--check"),
    py("scripts/validation/validate_bundle.py", "--scope", "ship", "--no-write"),
)


SHIP_COMMANDS: tuple[tuple[str, ...], ...] = (
    REACS_REGISTRY_TESTS,
    py("scripts/validation/container_boundary_audit.py", "--self-test"),
    py("scripts/validation/container_boundary_audit.py"),
    py("scripts/build/bundle_standalone.py", "--self-test"),
    unit_test("artifact_link_audit"),
    ARTIFACT_NAVIGATION_TESTS,
    py("scripts/build/build_security_review_package.py", "--self-test"),
    unit_test("materials"),
    py("scripts/materials/pull_materials.py", "--verify-committed"),
    unit_test("local_path_leak_audit"),
    py("scripts/validation/local_path_leak_audit.py"),
    unit_test("external_link_attribution_audit"),
    py("scripts/validation/external_link_attribution_audit.py"),
    # validate_bundle owns the current-tree sensitive, layout, architecture, release-evidence,
    # repository-work-product, localization, contribution, browser-dependency, and cell audits.
    # Keep only their mutation suites here so one shared gate never scans the same tree twice.
    unit_test("sensitive_content_audit"),
    unit_test("release_change_reminder"),
    unit_test("validation_report_audit"),
    unit_test("pages_artifact_integrity"),
    unit_test("threat_control_audit"),
    unit_test("repository_sync_audit"),
    unit_test("gitlab_ci_policy"),
    py("scripts/validation/gitlab_ci_policy.py"),
    py("scripts/skills/skill_consistency.py"),
    py("scripts/skills/gen_directory_beacons.py", "--check"),
    py("scripts/skills/normalize_skill_headers.py", "--self-test"),
    py("scripts/skills/normalize_skill_headers.py", "--check"),
    py("scripts/skills/test_skill_contract.py"),
    py("scripts/skills/skill_contract.py"),
    py("scripts/validation/ci_storage_audit.py"),
    py("scripts/validation/branch_preview_manifest_audit.py", "--self-test"),
    py("scripts/validation/learner_flow_audit.py", "--self-test"),
    py("scripts/validation/html_structure_audit.py", "--self-test"),
    py("scripts/validation/code_hygiene.py", "--self-test"),
    py("scripts/figures/render_security_architecture.py", "--check"),
    unit_test("security_architecture_audit"),
    unit_test("project_docs_explorer"),
    HARNESS_CONTRACT,
    py("scripts/build/project_docs_explorer.py", "--audit"),
    py("scripts/build/project_source_tree.py", "--self-test"),
    py("scripts/build/project_source_tree.py", "--check-generated"),
    unit_test("release_evidence_audit"),
    unit_test("repository_work_products_audit"),
    NODE_VALIDATOR_TESTS,
    py("scripts/build/assemble_locale_overlay.py", "--self-test"),
    py("scripts/validation/localization_audit.py", "--self-test"),
    FOYER_BRANCH_PATH_TESTS,
    CONTRIBUTION_LANGUAGE_OWNERSHIP_TESTS,
    py("scripts/validation/contribution_safety_audit.py", "--self-test"),
    py(
        "scripts/validation/contribution_safety_audit.py",
        "--report",
        "docs/validation/contribution-safety.json",
    ),
    py("scripts/security/audit_iframe_proxy_opt_in.py", "--self-test"),
    py("scripts/security/audit_iframe_proxy_opt_in.py"),
    py("scripts/validation/endpoint_registration_audit.py", "--self-test"),
    py("scripts/validation/endpoint_registration_audit.py"),
    ("bash", "scripts/runtime/run_node.sh", "scripts/validation/openclaw_connection_audit.mjs"),
    py("scripts/compliance/source_gate.py"),
    SOURCE_LICENSE_CONTRACT_TESTS,
    py("scripts/compliance/source_document_audit.py"),
    unit_test("source_document_audit"),
    py("scripts/pyodide/integration_audit.py"),
    unit_test("pyodide_integration_audit"),
    PYODIDE_RUNTIME_SMOKE,
    py("scripts/compliance/third_party_inventory_audit.py"),
    unit_test("third_party_inventory_audit"),
    unit_test("export_third_party_csv"),
    unit_test("export_legal_scope_csv"),
    unit_test("render_sbom_license_inventory"),
    unit_test("resolve_sbom_licenses"),
    unit_test("course_dependency_integrity"),
    cli_unit_test("cell_audit"),
    py("scripts/security/audit_python_dependencies.py"),
    py("scripts/security/audit_vulnerability_waivers.py"),
    py("scripts/security/audit_dependency_locks.py", "--self-test"),
    py("scripts/security/audit_dependency_locks.py"),
    py("scripts/security/audit_sbom_policy.py", "--self-test"),
    py("scripts/build/package_release.py", "--self-test"),
    py("scripts/validation/tenets.py", "--check"),
    py("scripts/runtime/module_check.py"),
    py("scripts/validation/interface_inventory_audit.py"),
    COLOR_THEME_TESTS,
    THEME_RUNTIME_CONTRACT_TESTS,
    py("scripts/validation/color_theme.py"),
    STANDARD_TEST_DISCOVERY,
    py("scripts/validation/interface_inventory_browser_audit.py", "--site-root", "."),
    py("scripts/validation/validator_specialization_audit.py"),
    PRIVILEGED_COURSE_OPS_TESTS,
    py("-m", "unittest", "-v", "tests.validation.test_codeql_sarif_audit"),
    py("scripts/security/audit_codeql_sarif.py"),
    py("scripts/validation/browser_security_boundary_audit.py", "--self-test"),
    py("scripts/validation/browser_security_boundary_audit.py"),
    py("scripts/materials/build_rag_index.py", "--check"),
    py("scripts/validation/validate_bundle.py", "--scope", "ship"),
)


# Mutation suites prove their detectors. Current-tree behavior remains in validate_bundle.
# Proposal runs may skip a mutation suite only when none of its implementation or contract
# inputs changed. Full release runs omit --changed-since and execute every suite.
MUTATION_IMPACTS: dict[tuple[str, ...], tuple[str, ...]] = {
    STANDARD_TEST_DISCOVERY: (
        "tests/validation/*.py", "tests/validation/**/*.py",
    ),
    REACS_REGISTRY_TESTS: (
        "scripts/validation/reacs_registry.json", "scripts/validation/reacs_registry.py",
        "scripts/validation/release_gate.py", "tests/validation/test_reacs_registry.py",
        ".gitlab-ci.yml", ".gitlab/ci/*", ".github/workflows/*",
    ),
    py("scripts/validation/container_boundary_audit.py", "--self-test"): (
        "scripts/validation/container_boundary_audit.py", "scripts/validation/release_gate.py",
        "**/Dockerfile", "**/Containerfile", "**/docker-compose*.yml",
    ),
    unit_test("artifact_link_audit"): (
        "scripts/validation/artifact_link_audit.py", "scripts/build/bundle_standalone.py",
        "scripts/build/build_pages.sh", "tests/validation/test_embedded_validator_suites.py",
        "**/*.html",
    ),
    ARTIFACT_NAVIGATION_TESTS: (
        "scripts/build/bundle_standalone.py", "scripts/build/project_artifact_navigation.py",
        "scripts/build/project_artifact_manifests.py", "scripts/build/build_branch_manifest.py",
        "scripts/validation/artifact_link_audit.py",
        "tests/validation/test_artifact_navigation_projection.py", "**/*.html",
    ),
    COLOR_THEME_TESTS: (
        "scripts/validation/color_theme.py", "tests/validation/test_color_theme.py",
        "web/**/*.html", "web/**/*.css", "web/**/*.js", "web/**/*.mjs", "web/**/*.svg",
    ),
    THEME_RUNTIME_CONTRACT_TESTS: (
        "scripts/skills/skill_renderer_runtime_audit.py",
        "tests/validation/test_theme_runtime_contract.py", ".gitlab/ci/core.yml", "**/*.html",
    ),
    SOURCE_LICENSE_CONTRACT_TESTS: (
        "LICENSE", "DCO.md", "THIRD-PARTY-NOTICES.md", "CONTRIBUTING.md",
        "scripts/compliance/source_gate.py", "scripts/compliance/source_license_contract.py",
        "tests/validation/test_source_license_contract.py",
        "scripts/build/vendor_browser_dependencies.mjs",
        "web/nemoclaw/vendor/browser-dependencies.json",
        "scripts/**/*.py", "scripts/**/*.js", "scripts/**/*.mjs",
        "web/**/*.py", "web/**/*.js", "web/**/*.mjs",
        "tests/**/*.py", "tests/**/*.js", "tests/**/*.mjs",
    ),
    unit_test("source_document_audit"): (
        "scripts/compliance/source_document_audit.py", "scripts/compliance/docs/document_sources.json",
        "THIRD_PARTY_LICENSES.md", "web/nemoclaw/*.html", "web/nemoclaw/mats/*",
        "web/nemoclaw/assets/SKILL.html",
    ),
    unit_test("pyodide_integration_audit"): (
        "scripts/pyodide/*", "tests/validation/test_embedded_validator_suites.py",
        "scripts/validation/release_gate.py", "scripts/validation/release_change_reminder.py",
        "web/**/*", "i18n/**/*",
    ),
    PYODIDE_RUNTIME_SMOKE: (
        "scripts/pyodide/*", "scripts/pyodide/examples/*",
        "scripts/validation/release_gate.py",
    ),
    py("scripts/skills/normalize_skill_headers.py", "--self-test"): (
        "scripts/skills/normalize_skill_headers.py", "scripts/skills/gen_directory_beacons.py",
        "SKILL_CONTRACT.md", "**/SKILL.html",
    ),
    unit_test("third_party_inventory_audit"): (
        "THIRD_PARTY_LICENSES.md", "scripts/compliance/third_party_inventory_audit.py",
        "scripts/browser-vendor/package-lock.json", "web/nemoclaw/vendor/*",
        "scripts/materials/requirements*", "scripts/security/requirements*",
        "scripts/runtime/package.json", "scripts/runtime/pnpm-lock.yaml", "web/nemoclaw/assets/SKILL.html",
        "web/nemoclaw/mats/SKILL.html", "scripts/build/build_pages.sh",
    ),
    unit_test("render_sbom_license_inventory"): (
        "THIRD_PARTY_LICENSES.md", "scripts/compliance/render_sbom_license_inventory.py",
        "scripts/compliance/third_party_inventory_audit.py",
    ),
    unit_test("resolve_sbom_licenses"): (
        "THIRD_PARTY_LICENSES.md", "scripts/compliance/resolve_sbom_licenses.py",
        "scripts/compliance/render_sbom_license_inventory.py", ".gitlab/ci/sca.yml",
    ),
    unit_test("sbom_evidence"): (
        "THIRD_PARTY_LICENSES.md", "scripts/compliance/sbom_evidence.py",
        "scripts/compliance/render_sbom_license_inventory.py",
        "scripts/compliance/docs/sbom_evidence.json", "web/nemoclaw/vendor/browser-sbom.cdx.json",
        ".gitlab/ci/sca.yml", ".github/workflows/release.yml",
    ),
    unit_test("export_third_party_csv"): (
        "THIRD_PARTY_LICENSES.md", "scripts/compliance/export_third_party_csv.py",
        "scripts/compliance/third_party_inventory_audit.py", "scripts/compliance/SKILL.html",
        "scripts/compliance/third_party_export_ui.js", "web/nemoclaw/vendor/browser-dependencies.json",
    ),
    unit_test("export_legal_scope_csv"): (
        "THIRD_PARTY_LICENSES.md", "scripts/compliance/export_legal_scope_csv.py",
        "scripts/compliance/export_third_party_csv.py", "scripts/compliance/SKILL.html",
        "scripts/compliance/third_party_export_ui.js", "web/nemoclaw/vendor/browser-dependencies.json",
    ),
    py("scripts/build/build_security_review_package.py", "--self-test"): (
        "scripts/build/build_security_review_package.py", "docs/product-design.md",
        "docs/security-design.md", "docs/security-control-disposition.md", "docs/release-test-plan.md",
        "docs/SKILL.html", "scripts/build/SKILL.html",
    ),
    py("scripts/build/project_source_tree.py", "--self-test"): (
        "scripts/build/project_source_tree.py", "scripts/build/build_pages.sh",
        "scripts/build/SKILL.html", "scripts/skills/skill_audit.py",
    ),
    py("scripts/build/project_source_tree.py", "--check-generated"): (
        "scripts/build/project_source_tree.py", "web/nemoclaw/standalone/*",
    ),
    py("scripts/build/bundle_standalone.py", "--self-test"): (
        "scripts/build/bundle_standalone.py", "scripts/build/build_pages.sh",
        "web/nemoclaw/*.html", "web/nemoclaw/assets/figures/*",
        "i18n/*/web/nemoclaw/*.html",
    ),
    unit_test("materials"): (
        "scripts/materials/pull_materials.py", "scripts/materials/requirements*",
    ),
    unit_test("local_path_leak_audit"): (
        "scripts/validation/local_path_leak_audit.py",
    ),
    unit_test("external_link_attribution_audit"): (
        "scripts/validation/external_link_attribution_audit.py", "scripts/build/bundle_standalone.py",
        "web/*.html", "web/*.js", "web/nemoclaw/*.html", "web/nemoclaw/scripts/*.js",
        "web/nemoclaw/standalone/*.html", "web/nemoclaw/standalone/scripts/*.js",
        "i18n/*/web/*.html", "i18n/*/web/nemoclaw/*.html",
    ),
    unit_test("sensitive_content_audit"): (
        "scripts/validation/sensitive_content_audit.py", "scripts/validation/sensitive-content-policy.json",
    ),
    unit_test("release_change_reminder"): (
        "scripts/validation/release_change_reminder.py",
    ),
    unit_test("validation_report_audit"): (
        "scripts/validation/validation_report_audit.py", "scripts/validation/validate_bundle.py",
        "scripts/build/build_pages.sh", ".gitlab-ci.yml", ".gitlab/ci/*", ".github/workflows/*",
    ),
    unit_test("pages_artifact_integrity"): (
        "scripts/validation/pages_artifact_integrity.py", "scripts/build/build_pages.sh",
        ".github/workflows/pages.yml", "docs/pages_deploy.md", "docs/release-test-plan.md",
    ),
    unit_test("threat_control_audit"): (
        "scripts/validation/threat_control_audit.py", "scripts/validation/pages_artifact_integrity.py",
        "scripts/validation/repository_sync_audit.py", ".github/workflows/pages.yml",
        ".github/workflows/release.yml", ".gitlab-ci.yml", ".gitlab/ci/*", "docs/release_playbook.md",
        "docs/security-control-disposition.md",
    ),
    unit_test("repository_sync_audit"): (
        "scripts/validation/repository_sync_audit.py", ".gitlab-ci.yml", ".gitlab/ci/*",
        "docs/release_playbook.md",
    ),
    unit_test("gitlab_ci_policy"): (
        ".gitlab-ci.yml", ".gitlab/ci/*", ".gitlab/CODEOWNERS",
        "scripts/validation/gitlab_ci_policy.py", "scripts/validation/release_gate.py",
    ),
    PRIVILEGED_COURSE_OPS_TESTS: (
        "scripts/ci/*", "tests/validation/test_privileged_course_ops.py",
        ".gitlab-ci.yml", ".gitlab/ci/privileged.yml", "docs/pages_deploy.md",
    ),
    py("scripts/validation/branch_preview_manifest_audit.py", "--self-test"): (
        "scripts/validation/branch_preview_manifest_audit.py", "scripts/build/build_branch_manifest.py",
        "web/index.html", ".gitlab-ci.yml", ".gitlab/ci/core.yml",
    ),
    py("scripts/validation/learner_flow_audit.py", "--self-test"): (
        "scripts/validation/learner_flow_audit.py", "web/nemoclaw/scripts/*", "web/nemoclaw/styles/*",
        "web/nemoclaw/0*.html", "i18n/*/web/nemoclaw/0*.html", "scripts/browser-vendor/*",
        ".gitlab/ci/core.yml",
    ),
    py("scripts/validation/html_structure_audit.py", "--self-test"): (
        "scripts/validation/html_structure_audit.py",
    ),
    py("scripts/validation/code_hygiene.py", "--self-test"): (
        "scripts/validation/code_hygiene.py",
    ),
    unit_test("security_architecture_audit"): (
        "scripts/validation/security_architecture_audit.py", "scripts/figures/render_security_architecture.py",
        "docs/security-architecture*", ".gitlab-ci.yml", ".gitlab/ci/*", ".github/workflows/*",
    ),
    unit_test("project_docs_explorer"): (
        "scripts/build/project_docs_explorer.py", "docs/SKILL.html",
    ),
    unit_test("release_evidence_audit"): (
        "scripts/validation/release_evidence_audit.py", "docs/product-design.md",
        "docs/release-test-plan.md", "docs/release-evidence.json", "RELEASE_STATUS*",
        ".gitlab/ci/core.yml",
    ),
    unit_test("repository_work_products_audit"): (
        "scripts/validation/repository_work_products_audit.py", "docs/release-evidence.json",
        "README.md", "LICENSE", "SECURITY.md", "CHANGELOG.md", "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md", "docs/release_playbook.md", "docs/release-test-plan.md",
        "docs/agent_process.md", ".gitattributes", ".github/ISSUE_TEMPLATE/*",
        ".github/PULL_REQUEST_TEMPLATE.md", ".gitlab/issue_templates/*",
        "scripts/validation/SKILL.html", "scripts/validation/release_gate.py",
        "scripts/validation/validate_bundle.py", "scripts/git-hooks/pre-commit",
    ),
    NODE_VALIDATOR_TESTS: (
        "scripts/validation/gateway_token_audit.mjs", "scripts/validation/openclaw_fallback_audit.py",
        "scripts/validation/openclaw_connection_audit.mjs", "scripts/runtime/test_page_runtime.js",
        "scripts/runtime/browser_runtime_test.sh", "scripts/runtime/host_browser.py", "web/nemoclaw/scripts/_connection.js",
        "web/nemoclaw/scripts/_openclaw.js", "web/nemoclaw/scripts/_openshell.js",
        "web/nemoclaw/scripts/_shared.js", "web/nemoclaw/03a-kickstart.html", "web/nemoclaw/04b-modern-clis.html",
        "i18n/pt/web/nemoclaw/03a-kickstart.html", "i18n/es/web/nemoclaw/03a-kickstart.html",
        "i18n/pt/web/nemoclaw/04b-modern-clis.html", "i18n/es/web/nemoclaw/04b-modern-clis.html",
        "scripts/runtime/engine.js", "scripts/runtime/link_projection.py", "scripts/runtime/run_engine.sh",
        "scripts/runtime/run_node.sh",
    ),
    py("scripts/build/assemble_locale_overlay.py", "--self-test"): (
        "scripts/build/assemble_locale_overlay.py", "scripts/translate/code_localization.py",
        "scripts/translate/locale_projection.py", "i18n/*/locale.json",
    ),
    py("scripts/validation/localization_audit.py", "--self-test"): (
        "scripts/validation/localization_audit.py", "scripts/translate/locales/*",
        "scripts/translate/code_localization.py", "scripts/translate/locale_projection.py",
        "scripts/build/assemble_locale_overlay.py", "i18n/*/locale.json",
        "web/nemoclaw/scripts/_keypanel.js", "web/nemoclaw/scripts/_locale.js",
        "web/nemoclaw/scripts/_shared.js",
    ),
    py("scripts/validation/contribution_safety_audit.py", "--self-test"): (
        ".github/*", ".github/**/*", ".gitlab-ci.yml", ".gitlab/*", ".gitlab/**/*",
        "AGENTS.md", "CONTRIBUTING.md", "DCO.md", "LICENSE", "RELEASE_STATUS.json",
        "CODE_OF_CONDUCT.md", "SUPPORT.md", "RELEASE_STATUS*",
        "docs/agent_process.md", "docs/release*", "docs/pages_deploy.md",
        "scripts/git-hooks/*", "scripts/build/install-hooks.sh", "scripts/build/build_pages.sh",
        "scripts/build/package_release.py", "scripts/validation/release_gate.py",
        "scripts/validation/contribution_safety_audit.py", "scripts/security/*", "workspace/*",
    ),
    CONTRIBUTION_LANGUAGE_OWNERSHIP_TESTS: (
        "scripts/validation/contribution_safety_audit.py",
        "tests/validation/test_contribution_language_ownership.py",
        "web/nemoclaw/*", "i18n/*/web/nemoclaw/*",
    ),
    FOYER_BRANCH_PATH_TESTS: (
        "tests/validation/test_foyer_branch_paths.py",
        "web/index.html", "i18n/*/web/index.html",
    ),
    py("scripts/security/audit_iframe_proxy_opt_in.py", "--self-test"): (
        "scripts/security/audit_iframe_proxy_opt_in.py", "scripts/cors-proxy/*",
        "web/nemoclaw/index.html", "web/nemoclaw/scripts/_keypanel.js",
        "web/nemoclaw/scripts/_shared.js",
    ),
    py("scripts/validation/endpoint_registration_audit.py", "--self-test"): (
        "scripts/validation/endpoint_registration_audit.py", "web/nemoclaw/scripts/_shared.js",
        "web/nemoclaw/scripts/_keypanel.js", "web/nemoclaw/scripts/_connection.js",
        "web/nemoclaw/scripts/_openclaw.js", "web/nemoclaw/03a-kickstart.html",
        "web/_skill_explorer.js", "scripts/cors-proxy/SKILL.html",
        "scripts/runtime/test_page_runtime.js", "scripts/validation/runtime_integration_browser_audit.py",
        "i18n/pt/web/nemoclaw/03a-kickstart.html", "i18n/es/web/nemoclaw/03a-kickstart.html",
    ),
    unit_test("course_dependency_integrity"): (
        "scripts/validation/course_dependency_integrity.py", "scripts/browser-vendor/*",
        "scripts/build/vendor_browser_dependencies.mjs", "web/nemoclaw/vendor/*", ".gitlab/ci/sca.yml",
        ".github/workflows/pages.yml", ".github/workflows/release.yml",
    ),
    cli_unit_test("cell_audit"): (
        "scripts/validation/cell_audit.py", "web/nemoclaw/scripts/*", "web/nemoclaw/vendor/*",
    ),
    py("scripts/security/audit_dependency_locks.py", "--self-test"): (
        "scripts/security/audit_dependency_locks.py", "scripts/materials/requirements*",
        "scripts/security/requirements-sca*", "scripts/runtime/pnpm-lock.yaml",
    ),
    py("scripts/security/audit_sbom_policy.py", "--self-test"): (
        "scripts/security/audit_sbom_policy.py",
    ),
    py("scripts/build/package_release.py", "--self-test"): (
        "scripts/build/package_release.py", "docs/release_artifacts.md", ".github/workflows/release.yml",
    ),
    py("scripts/validation/browser_security_boundary_audit.py", "--self-test"): (
        "scripts/validation/browser_security_boundary_audit.py",
        "scripts/validation/learner_flow_runtime_audit.py",
        "scripts/validation/studio_responsive_audit.py",
        "scripts/skills/skill_renderer_runtime_audit.py",
        "scripts/edx/*", "scripts/pyodide/*", "scripts/runtime/*",
        "web/**/*", "i18n/**/*", "docs/security-design.md", "docs/product-design.md",
    ),
    py("-m", "unittest", "-v", "tests.validation.test_codeql_sarif_audit"): (
        ".github/workflows/codeql.yml",
        "scripts/security/audit_codeql_sarif.py",
        "scripts/security/codeql-vendor-dispositions.json",
        "tests/validation/test_codeql_sarif_audit.py",
        "web/nemoclaw/vendor/*",
        "web/shared/vendor/*",
    ),
    HARNESS_CONTRACT: (
        "tests/validation/test_test_harness_contract.py", "scripts/**/*.py",
        "scripts/**/*.js", "scripts/**/*.mjs", "scripts/**/*.sh",
    ),
}


def commands_for(tier: str, *, no_write: bool) -> list[tuple[str, ...]]:
    return [command for _, command in REGISTRY.for_tier(tier, no_reports=no_write)]


def suites_for(tier: str, *, no_write: bool) -> list[tuple[reacs_registry.Suite, tuple[str, ...]]]:
    return REGISTRY.for_tier(tier, no_reports=no_write)


def display(command: Iterable[str]) -> str:
    return " ".join(command)


def _run_captured(command: tuple[str, ...], *, env: dict[str, str]) -> dict[str, object]:
    started = time.monotonic()
    completed = subprocess.run(
        command, cwd=ROOT, env=env, check=False, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return {
        "returncode": completed.returncode,
        "seconds": time.monotonic() - started,
        "output": completed.stdout or "",
    }


def run_parallel_group(
    commands: list[tuple[str, ...]], *, jobs: int, env: dict[str, str],
) -> list[dict[str, object]]:
    """Execute one declared-safe group concurrently and retain registry-order results."""
    if jobs < 1:
        raise ValueError("jobs must be positive")
    with ThreadPoolExecutor(max_workers=min(jobs, len(commands))) as executor:
        futures = [executor.submit(_run_captured, command, env=env) for command in commands]
        return [future.result() for future in futures]


def _git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=ROOT, check=False, text=True, capture_output=True,
    )
    if check and proc.returncode:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip()


def _parse_name_status(raw: bytes, source: str) -> dict[str, set[str]]:
    """Parse Git's NUL-delimited status stream, retaining both sides of renames/copies."""
    tokens = [os.fsdecode(item) for item in raw.split(b"\0") if item]
    rows: dict[str, set[str]] = {}
    index = 0
    while index < len(tokens):
        status = tokens[index]
        index += 1
        width = 2 if status[:1] in {"R", "C"} else 1
        if index + width > len(tokens):
            raise RuntimeError("malformed git name-status output; refusing selective execution")
        paths = tokens[index:index + width]
        index += width
        labels = (
            (f"{source}:{status}:from", f"{source}:{status}:to")
            if width == 2 else (f"{source}:{status}",)
        )
        for path, label in zip(paths, labels):
            rows.setdefault(path, set()).add(label)
    return rows


def _merge_statuses(target: dict[str, set[str]], source: dict[str, set[str]]) -> None:
    for path, labels in source.items():
        target.setdefault(path, set()).update(labels)


def changed_paths(revision: str) -> tuple[str, set[str], dict[str, set[str]]]:
    resolved = _git("rev-parse", f"{revision}^{{commit}}")
    statuses: dict[str, set[str]] = {}
    for source, args in (
        ("commit", ("diff", "--name-status", "-z", f"{resolved}..HEAD")),
        ("worktree", ("diff", "--name-status", "-z")),
        ("index", ("diff", "--cached", "--name-status", "-z")),
    ):
        raw = subprocess.run(["git", *args], cwd=ROOT, check=False, capture_output=True)
        if raw.returncode:
            raise RuntimeError(f"git {' '.join(args)} failed; refusing change-aware skips")
        _merge_statuses(statuses, _parse_name_status(raw.stdout, source))
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=ROOT, check=False, capture_output=True,
    )
    if untracked.returncode:
        raise RuntimeError("git ls-files --others failed; refusing change-aware skips")
    for item in untracked.stdout.split(b"\0"):
        if item:
            statuses.setdefault(os.fsdecode(item), set()).add("worktree:A:untracked")
    return resolved, set(statuses), statuses


def _matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern)


def mutation_affected(command: tuple[str, ...], paths: set[str]) -> bool:
    for suite in REGISTRY.suites:
        if suite.command(no_reports=False) == command or suite.command(no_reports=True) == command:
            return suite.mode != "mutation" or REGISTRY.impact_matches(suite, paths)
    return True


def _head() -> str | None:
    try:
        return _git("rev-parse", "HEAD")
    except RuntimeError:
        return None


def _clean() -> bool:
    try:
        return not _git("status", "--porcelain", "--untracked-files=all")
    except RuntimeError:
        return False


def _cache_path() -> Path | None:
    try:
        git_dir = Path(_git("rev-parse", "--git-dir"))
    except RuntimeError:
        return None
    if not git_dir.is_absolute():
        git_dir = ROOT / git_dir
    return git_dir / "release-gate-success.json"


def _signature(tier: str, no_write: bool, commands: list[tuple[str, ...]]) -> str:
    payload = json.dumps({
        "tier": tier,
        "no_write": no_write,
        "commands": commands,
        "registry": REGISTRY.signature,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def reusable_success(
    *, tier: str, no_write: bool, commands: list[tuple[str, ...]], changed_base: str | None,
) -> dict | None:
    path = _cache_path()
    if path is None or not path.is_file() or not _clean():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("schema") != CACHE_SCHEMA or data.get("head") != _head():
        return None
    if data.get("tier") != tier or data.get("signature") != _signature(tier, no_write, commands):
        return None
    cached_base = data.get("changed_base")
    if cached_base is not None and cached_base != changed_base:
        return None
    return data


def record_success(
    *, tier: str, no_write: bool, commands: list[tuple[str, ...]], changed_base: str | None,
    duration: float, executed: int, skipped: int,
) -> None:
    # ``--no-write`` suppresses repository reports. The cache lives under Git metadata and is
    # neither tracked output nor release evidence. Read-only mounts remain supported: failure to
    # write this optional optimization never changes a successful validation result.
    if os.environ.get("CI") or not _clean():
        return
    path = _cache_path()
    head = _head()
    if path is None or head is None:
        return
    data = {
        "schema": CACHE_SCHEMA,
        "head": head,
        "tier": tier,
        "no_write": no_write,
        "signature": _signature(tier, no_write, commands),
        "registry_signature": REGISTRY.signature,
        "changed_base": changed_base,
        "duration_seconds": round(duration, 3),
        "executed": executed,
        "skipped": skipped,
    }
    try:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def write_timing_report(path: str | None, report: dict) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def self_test() -> list[str]:
    failures: list[str] = []
    fast = commands_for("fast", no_write=True)
    ship = commands_for("ship", no_write=False)
    mutation_commands = {
        command for command in ship
        if "--self-test" in command
        or ("-m" in command and "unittest" in command)
        or command == NODE_VALIDATOR_TESTS
    }
    checks = [
        (REGISTRY.signature == hashlib.sha256(REGISTRY.path.read_bytes()).hexdigest(),
         "registry signature covers the exact policy bytes"),
        (fast == [command for _, command in REGISTRY.for_tier("fast", no_reports=True)],
         "fast tier is projected from the declarative registry"),
        (ship == [command for _, command in REGISTRY.for_tier("ship", no_reports=False)],
         "ship tier is projected from the declarative registry"),
        (len(fast) < len(ship), "fast tier is smaller than ship tier"),
        (py("scripts/materials/pull_materials.py", "--verify-committed") in fast,
         "fast tier verifies committed material provenance"),
        (py("scripts/materials/build_rag_index.py", "--check") in fast
         and py("scripts/materials/build_rag_index.py", "--check") in ship,
         "shared tiers reject stale generated retrieval indexes"),
        (py("scripts/validation/sensitive_content_audit.py") not in ship,
         "ship tier delegates the sensitive tree scan to validate_bundle"),
        (py("scripts/validation/validate_layout.py", "--quiet") not in ship,
         "ship tier delegates layout to validate_bundle"),
        (py("scripts/validation/course_dependency_integrity.py") not in ship,
         "ship tier delegates browser dependency audit to validate_bundle"),
        (py("scripts/validation/localization_audit.py", "--locale", "pt-BR") not in ship,
         "ship tier delegates locale current-tree audits to validate_bundle"),
        (mutation_commands <= set(MUTATION_IMPACTS),
         "every mutation command declares change-impact inputs"),
        (py("scripts/validation/tenets.py", "--check") in fast and py("scripts/validation/tenets.py", "--check") in ship,
         "shared tiers include the tenets projection"),
        (ship[-1] == py("scripts/validation/validate_bundle.py", "--scope", "ship"),
         "ship tier ends with report-producing bundle gate"),
        (commands_for("ship", no_write=True)[-1]
         == py("scripts/validation/validate_bundle.py", "--scope", "ship", "--no-write"),
         "no-write mode reaches final bundle gate"),
        (not any("--report" in command for command in commands_for("ship", no_write=True)),
         "no-write mode suppresses durable contribution report"),
    ]
    failures.extend(label for passed, label in checks if not passed)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=("fast", "ship"), default="fast")
    parser.add_argument("--no-write", action="store_true", help="avoid durable validator reports")
    parser.add_argument("--changed-since", metavar="REV", help="skip unaffected mutation suites")
    parser.add_argument("--reuse-success", action="store_true", help="reuse an identical clean local success")
    parser.add_argument("--timing-report", metavar="PATH", help="write per-command JSON timing evidence")
    parser.add_argument("--list", action="store_true", help="print commands without running them")
    parser.add_argument("--plan-json", metavar="PATH", help="write the selected suite plan without running it")
    parser.add_argument(
        "--jobs", type=int, default=int(os.environ.get("REACS_JOBS", "1")),
        help="maximum workers for registry-declared parallel-safe suites (default: REACS_JOBS or 1)",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        parser.error("--jobs must be between 1 and 8")

    if args.self_test:
        failures = self_test()
        print("release gate self-test: " + ("FAIL" if failures else "PASS"))
        for failure in failures:
            print(f"  FAIL {failure}")
        return 1 if failures else 0

    suite_commands = suites_for(args.tier, no_write=args.no_write)
    commands = [command for _, command in suite_commands]
    changed_base: str | None = None
    paths: set[str] | None = None
    path_statuses: dict[str, set[str]] = {}
    if args.changed_since:
        try:
            changed_base, paths, path_statuses = changed_paths(args.changed_since)
        except RuntimeError as exc:
            print(f"release gate: FAIL: {exc}", file=sys.stderr)
            return 1

    selected_mutations, selection_reason = REGISTRY.selected_mutations(paths, path_statuses)
    defaulted_paths = REGISTRY.unclaimed_paths(paths or ()) if paths is not None else []
    structural_paths = sorted(
        path for path, signals in path_statuses.items()
        if REGISTRY.structural_change({path: signals})
    )
    plan = []
    for index, (suite, command) in enumerate(suite_commands, 1):
        selected = suite.mode != "mutation" or suite.id in selected_mutations
        plan.append({
            "index": index,
            "suite_id": suite.id,
            "mode": suite.mode,
            "selected": selected,
            "reason": "required-current-tree" if suite.mode != "mutation" else (
                selection_reason if selected else "unaffected-mutation"
            ),
            "parallel_safe": suite.parallel_safe,
            "command": display(command),
        })

    if args.plan_json:
        write_timing_report(args.plan_json, {
            "schema": "reacs-execution-plan/1",
            "tier": args.tier,
            "head": _head(),
            "changed_since": changed_base,
            "changed_paths": sorted(paths or ()),
            "changed_files": [
                {"path": path, "signals": sorted(path_statuses[path])}
                for path in sorted(path_statuses)
            ],
            "selection_reason": selection_reason,
            "defaulted_paths": defaulted_paths,
            "structural_paths": structural_paths,
            "registry_signature": REGISTRY.signature,
            "suites": plan,
        })

    if args.list:
        if paths is not None:
            print(
                f"# selection={selection_reason} changed={len(paths)} "
                f"structural={len(structural_paths)} defaulted={len(defaulted_paths)}"
            )
        for row in plan:
            marker = "" if row["selected"] else "  # SKIP unaffected mutation suite"
            print(f"[{row['suite_id']}] {row['command']}{marker}")
        return 0

    if args.reuse_success:
        cached = reusable_success(
            tier=args.tier, no_write=args.no_write, commands=commands, changed_base=changed_base,
        )
        if cached is not None:
            print(
                "release gate: REUSED clean local success "
                f"tier={args.tier} head={cached['head'][:12]} "
                f"duration={cached.get('duration_seconds', '?')}s"
            )
            return 0

    env = os.environ.copy()
    if paths is not None:
        print(
            f"release gate selection: {selection_reason} changed={len(paths)} "
            f"structural={len(structural_paths)} defaulted={len(defaulted_paths)}",
            flush=True,
        )
    rows: list[dict[str, object]] = []
    started_gate = time.monotonic()
    executed = 0
    skipped = 0
    execution_group = 0
    pointer = 0
    failure: tuple[int, reacs_registry.Suite, tuple[str, ...], int] | None = None
    while pointer < len(suite_commands):
        index = pointer + 1
        suite, command = suite_commands[pointer]
        if suite.mode == "mutation" and suite.id not in selected_mutations:
            print(f"[release_gate {index}/{len(commands)} {suite.id}] SKIP unaffected mutation", flush=True)
            rows.append({"index": index, "suite_id": suite.id, "mode": suite.mode,
                         "status": "skipped-unaffected", "selection_reason": "unaffected-mutation",
                         "seconds": 0.0, "parallel": False, "execution_group": None,
                         "command": display(command)})
            skipped += 1
            pointer += 1
            continue
        if args.jobs > 1 and suite.parallel_safe:
            group: list[tuple[int, reacs_registry.Suite, tuple[str, ...]]] = []
            while pointer < len(suite_commands):
                group_suite, group_command = suite_commands[pointer]
                if (
                    not group_suite.parallel_safe
                    or (group_suite.mode == "mutation" and group_suite.id not in selected_mutations)
                ):
                    break
                group.append((pointer + 1, group_suite, group_command))
                pointer += 1
            execution_group += 1
            print(
                f"[release_gate group {execution_group}] parallel suites="
                + ",".join(item[1].id for item in group),
                flush=True,
            )
            results = run_parallel_group(
                [item[2] for item in group], jobs=args.jobs, env=env,
            )
            for (group_index, group_suite, group_command), result in zip(group, results):
                output = str(result["output"])
                if output:
                    print(output, end="" if output.endswith("\n") else "\n")
                returncode = int(result["returncode"])
                elapsed = float(result["seconds"])
                rows.append({
                    "index": group_index, "suite_id": group_suite.id, "mode": group_suite.mode,
                    "status": "passed" if returncode == 0 else "failed",
                    "selection_reason": selection_reason,
                    "seconds": round(elapsed, 3), "parallel": True,
                    "execution_group": execution_group, "command": display(group_command),
                })
                executed += 1
                print(
                    f"[release_gate {group_index}/{len(commands)} {group_suite.id}] {elapsed:.3f}s",
                    flush=True,
                )
                if returncode and failure is None:
                    failure = (group_index, group_suite, group_command, returncode)
            if failure is not None:
                break
            continue
        execution_group += 1
        print(f"[release_gate {index}/{len(commands)} {suite.id}] {display(command)}", flush=True)
        started = time.monotonic()
        completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
        elapsed = time.monotonic() - started
        rows.append({"index": index, "suite_id": suite.id, "mode": suite.mode,
                     "status": "passed" if completed.returncode == 0 else "failed",
                     "selection_reason": "required-current-tree" if suite.mode != "mutation" else selection_reason,
                     "seconds": round(elapsed, 3), "parallel": False,
                     "execution_group": execution_group, "command": display(command)})
        executed += 1
        print(f"[release_gate {index}/{len(commands)} {suite.id}] {elapsed:.3f}s", flush=True)
        if completed.returncode:
            failure = (index, suite, command, completed.returncode)
            break
        pointer += 1

    if failure is not None:
        total = time.monotonic() - started_gate
        report = {"schema": TIMING_SCHEMA, "ok": False, "tier": args.tier,
                  "head": _head(), "changed_since": changed_base,
                  "selection_reason": selection_reason, "registry_signature": REGISTRY.signature,
                  "structural_paths": len(structural_paths), "defaulted_paths": len(defaulted_paths),
                  "changed_paths": len(paths or ()), "duration_seconds": round(total, 3),
                  "suite_seconds": round(sum(float(row["seconds"]) for row in rows), 3),
                  "jobs": args.jobs, "executed": executed, "skipped": skipped, "commands": rows}
        write_timing_report(args.timing_report, report)
        _, _, failed_command, returncode = failure
        print(f"release gate: FAIL ({returncode}) {display(failed_command)}", file=sys.stderr)
        return returncode

    total = time.monotonic() - started_gate
    report = {"schema": TIMING_SCHEMA, "ok": True, "tier": args.tier,
              "head": _head(), "changed_since": changed_base,
              "selection_reason": selection_reason, "registry_signature": REGISTRY.signature,
              "structural_paths": len(structural_paths), "defaulted_paths": len(defaulted_paths),
              "changed_paths": len(paths or ()), "duration_seconds": round(total, 3),
              "suite_seconds": round(sum(float(row["seconds"]) for row in rows), 3),
              "jobs": args.jobs,
              "executed": executed, "skipped": skipped, "commands": rows}
    write_timing_report(args.timing_report, report)
    record_success(tier=args.tier, no_write=args.no_write, commands=commands,
                   changed_base=changed_base, duration=total, executed=executed, skipped=skipped)
    print(
        f"release gate: PASS tier={args.tier} executed={executed} skipped={skipped} "
        f"duration={total:.3f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
