# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.validation import validator_specialization_audit as audit


class ValidatorSpecializationAuditTests(unittest.TestCase):
    def fixture(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="validator-specialization-"))
        (root / "web/sample").mkdir(parents=True)
        (root / "web/sample/interface-inventory.json").write_text("{}", encoding="utf-8")
        (root / "scripts/validation").mkdir(parents=True)
        (root / "tests/runtime").mkdir(parents=True)
        (root / "tests/validation").mkdir(parents=True)
        (root / "scripts/pyodide").mkdir(parents=True)
        (root / "scripts/validation/reacs_registry.json").write_text(json.dumps({"suites": []}), encoding="utf-8")
        policy = {
            "schema": audit.SCHEMA,
            "allowed_dimensions": ["source-fidelity"],
            "forbidden_dimensions": sorted(audit.UNIVERSAL_DIMENSIONS),
            "entries": [],
        }
        (root / "scripts/validation/reacs_specialization_exceptions.json").write_text(json.dumps(policy), encoding="utf-8")
        return root

    def commit(self, root: Path, message: str) -> str:
        if not (root / ".git").is_dir():
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "ReACS test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "reacs@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", message], check=True)
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], check=True, text=True, capture_output=True,
        ).stdout.strip()

    def add_exception(self, root: Path, specialized: Path, baseline_commit: str) -> None:
        registry_path = root / "scripts/validation/reacs_registry.json"
        registry_path.write_text(json.dumps({
            "suites": [{"id": "sample-browser", "argv": ["python", "generic_runner.py"]}],
        }), encoding="utf-8")
        policy_path = root / "scripts/validation/reacs_specialization_exceptions.json"
        policy = json.loads(policy_path.read_text())
        policy["entries"] = [{
            "id": "sample-specialized-baseline",
            "course": "sample",
            "dimension": "source-fidelity",
            "rationale": "Preserve a pre-existing source-fidelity check during generic migration.",
            "owning_contract": "web/sample/interface-inventory.json",
            "migration": "generic-form-factor-migration",
            "baseline_commit": baseline_commit,
            "files": {
                specialized.relative_to(root).as_posix(): hashlib.sha256(specialized.read_bytes()).hexdigest(),
            },
            "registry_ids": ["sample-browser"],
        }]
        policy_path.write_text(json.dumps(policy), encoding="utf-8")

    def test_generic_validator_is_accepted(self) -> None:
        root = self.fixture()
        (root / "scripts/validation/course_surface_audit.py").write_text("pass\n", encoding="utf-8")
        self.assertEqual([], audit.audit(root))

    def test_empty_exception_policy_accepts_a_commit_range(self) -> None:
        root = self.fixture()
        base = self.commit(root, "generic baseline")
        (root / "scripts/validation/course_surface_audit.py").write_text("pass\n", encoding="utf-8")
        self.commit(root, "generic validator")
        self.assertEqual([], audit.audit(root, f"{base}..HEAD"))

    def test_course_named_validator_is_rejected(self) -> None:
        root = self.fixture()
        (root / "scripts/validation/sample_course_audit.py").write_text("pass\n", encoding="utf-8")
        self.assertTrue(any("course-named" in item for item in audit.audit(root)))

    def test_course_named_registry_suite_is_rejected(self) -> None:
        root = self.fixture()
        path = root / "scripts/validation/reacs_registry.json"
        path.write_text(json.dumps({"suites": [{"id": "sample-browser", "argv": ["python", "test.py"]}]}), encoding="utf-8")
        self.assertTrue(any("course-specialized suite" in item for item in audit.audit(root)))

    def test_universal_exception_dimension_is_rejected(self) -> None:
        root = self.fixture()
        path = root / "scripts/validation/reacs_specialization_exceptions.json"
        policy = json.loads(path.read_text())
        policy["allowed_dimensions"].append("theme")
        path.write_text(json.dumps(policy), encoding="utf-8")
        self.assertTrue(any("cannot be excepted" in item for item in audit.audit(root)))

    def test_policy_cannot_hide_literals_in_extra_fields(self) -> None:
        root = self.fixture()
        path = root / "scripts/validation/reacs_specialization_exceptions.json"
        policy = json.loads(path.read_text())
        policy["sample"] = "unreviewed bypass"
        path.write_text(json.dumps(policy), encoding="utf-8")
        self.assertTrue(any("policy fields must be exact" in item for item in audit.audit(root)))

    def test_policy_can_freeze_unchanged_specialization_that_predates_proposal(self) -> None:
        root = self.fixture()
        specialized = root / "tests/runtime/test_sample_browser.py"
        specialized.write_text("pass\n", encoding="utf-8")
        registry_path = root / "scripts/validation/reacs_registry.json"
        registry_path.write_text(json.dumps({
            "suites": [{"id": "sample-browser", "argv": ["python", "generic_runner.py"]}],
        }), encoding="utf-8")
        base = self.commit(root, "existing specialized baseline")
        self.add_exception(root, specialized, base)
        self.commit(root, "document frozen baseline")
        self.assertEqual([], audit.audit(root, f"{base}..HEAD"))

    def test_policy_can_record_an_exact_earlier_baseline_in_the_same_proposal(self) -> None:
        root = self.fixture()
        base = self.commit(root, "generic baseline")
        specialized = root / "tests/runtime/test_sample_browser.py"
        specialized.write_text("COURSE = 'sample'\n", encoding="utf-8")
        (root / "scripts/validation/reacs_registry.json").write_text(json.dumps({
            "suites": [{"id": "sample-browser", "argv": ["python", "generic_runner.py"]}],
        }), encoding="utf-8")
        reviewed = self.commit(root, "owner-reviewed migration baseline")
        self.add_exception(root, specialized, reviewed)
        self.commit(root, "record exact migration baseline")
        self.assertEqual([], audit.audit(root, f"{base}..HEAD"))

    def test_policy_cannot_legalize_code_absent_from_its_baseline(self) -> None:
        root = self.fixture()
        base = self.commit(root, "generic baseline")
        specialized = root / "tests/runtime/test_sample_browser.py"
        specialized.write_text("COURSE = 'sample'\n", encoding="utf-8")
        self.add_exception(root, specialized, base)
        self.commit(root, "invalid migration baseline")
        findings = audit.audit(root, f"{base}..HEAD")
        self.assertTrue(any("proposed validator code" in item for item in findings))

    def test_policy_cannot_hide_changes_after_the_recorded_baseline(self) -> None:
        root = self.fixture()
        base = self.commit(root, "generic baseline")
        specialized = root / "tests/runtime/test_sample_browser.py"
        specialized.write_text("COURSE = 'sample'\n", encoding="utf-8")
        reviewed = self.commit(root, "owner-reviewed migration baseline")
        self.add_exception(root, specialized, reviewed)
        self.commit(root, "record exact migration baseline")
        specialized.write_text("COURSE = 'sample'\nCHANGED = True\n", encoding="utf-8")
        self.commit(root, "change frozen migration code")
        findings = audit.audit(root, f"{base}..HEAD")
        self.assertTrue(any("baseline changed" in item or "proposed validator code" in item for item in findings))


if __name__ == "__main__":
    unittest.main()
