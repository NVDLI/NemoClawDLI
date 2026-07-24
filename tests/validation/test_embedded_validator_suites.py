# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run detector fixtures under standard unittest discovery."""
from __future__ import annotations

import importlib
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
for _path in (
    ROOT / "scripts" / "validation",
    ROOT / "scripts" / "build",
    ROOT / "scripts" / "materials",
    ROOT / "scripts" / "compliance",
):
    sys.path.insert(0, str(_path))


SUITES = {
    "artifact_link_audit": "scripts.validation.artifact_link_audit",
    "course_dependency_integrity": "scripts.validation.course_dependency_integrity",
    "external_link_attribution_audit": "scripts.validation.external_link_attribution_audit",
    "export_legal_scope_csv": "scripts.compliance.export_legal_scope_csv",
    "export_third_party_csv": "scripts.compliance.export_third_party_csv",
    "gitlab_ci_policy": "scripts.validation.gitlab_ci_policy",
    "local_path_leak_audit": "scripts.validation.local_path_leak_audit",
    "materials": "scripts.materials.pull_materials",
    "pages_artifact_integrity": "scripts.validation.pages_artifact_integrity",
    "project_docs_explorer": "scripts.build.project_docs_explorer",
    "pyodide_integration_audit": "scripts.pyodide.integration_audit",
    "release_change_reminder": "scripts.validation.release_change_reminder",
    "release_evidence_audit": "scripts.validation.release_evidence_audit",
    "release_gate": "scripts.validation.release_gate",
    "repository_sync_audit": "scripts.validation.repository_sync_audit",
    "repository_work_products_audit": "scripts.validation.repository_work_products_audit",
    "security_architecture_audit": "scripts.validation.security_architecture_audit",
    "sensitive_content_audit": "scripts.validation.sensitive_content_audit",
    "source_document_audit": "scripts.compliance.source_document_audit",
    "threat_control_audit": "scripts.validation.threat_control_audit",
    "third_party_inventory_audit": "scripts.compliance.third_party_inventory_audit",
    "render_sbom_license_inventory": "scripts.compliance.render_sbom_license_inventory",
    "resolve_sbom_licenses": "scripts.compliance.resolve_sbom_licenses",
    "sbom_evidence": "scripts.compliance.sbom_evidence",
    "validation_report_audit": "scripts.validation.validation_report_audit",
}


class ValidatorSelfTests(unittest.TestCase):
    """One framework-visible test per embedded detector suite."""


def _suite_test(module_name: str):
    def test(self: unittest.TestCase) -> None:
        module = importlib.import_module(module_name)
        failures = module.self_test()
        self.assertIsInstance(failures, list, f"unsupported self_test() result from {module_name}")
        self.assertEqual([], failures, "\n".join(str(item) for item in failures))

    return test


for _name, _module in SUITES.items():
    _test = _suite_test(_module)
    _test.__name__ = f"test_{_name}"
    _test.__qualname__ = f"ValidatorSelfTests.test_{_name}"
    setattr(ValidatorSelfTests, _test.__name__, _test)


class ValidatorCliTests(unittest.TestCase):
    """Framework-owned adapters for validators that still expose only a CLI fixture."""

    def test_cell_audit(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/validation/cell_audit.py", "--self-test"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
