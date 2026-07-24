# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation tests for the CodeQL SARIF enforcement boundary."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.security import audit_codeql_sarif as audit


class CodeqlSarifAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="codeql-sarif-audit-")
        self.root = Path(self.temp.name)
        self.vendor = self.root / "web/nemoclaw/vendor/library.js"
        self.vendor.parent.mkdir(parents=True)
        self.vendor.write_text("publisher bytes\n", encoding="utf-8")
        self.authored = self.root / "web/nemoclaw/scripts/runtime.js"
        self.authored.parent.mkdir(parents=True)
        self.authored.write_text("export const value = 1;\n", encoding="utf-8")
        self.control = self.root / "tests/validation/test_runtime_security.py"
        self.control.parent.mkdir(parents=True)
        self.control.write_text("def test_safe_reconstruction():\n    pass\n", encoding="utf-8")

        self.vendor_result = self.result(
            "js/example",
            "web/nemoclaw/vendor/library.js",
            line=7,
            column=3,
            end_column=12,
            line_hash="vendor-line:1",
        )
        self.vendor_fingerprint = audit.result_fingerprint(self.vendor_result)
        self.policy = {
            "schema": audit.POLICY_SCHEMA,
            "artifacts": [{
                "fingerprints": [self.vendor_fingerprint],
                "artifact": "web/nemoclaw/vendor/library.js",
                "artifact_sha256": hashlib.sha256(self.vendor.read_bytes()).hexdigest(),
                "component": "library",
                "version": "1.0.0",
                "decision": "not-exploitable-in-delivered-use",
                "owner": "course-maintainers",
                "expires": "2026-10-24",
                "evidence": ["web/nemoclaw/vendor/library.js"],
                "scope": "Fixture parser output is reconstructed as text.",
            }],
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def result(
        rule: str,
        path: str,
        *,
        line: int,
        column: int,
        end_column: int,
        line_hash: str,
    ) -> dict:
        return {
            "ruleId": rule,
            "level": "error",
            "message": {"text": "fixture result"},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": path},
                    "region": {
                        "startLine": line,
                        "startColumn": column,
                        "endLine": line,
                        "endColumn": end_column,
                    },
                },
            }],
            "partialFingerprints": {"primaryLocationLineHash": line_hash},
        }

    @staticmethod
    def sarif(*results: dict) -> dict:
        return {
            "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "CodeQL"}}, "results": list(results)}],
        }

    def findings(self, sarif: dict | None = None, policy: dict | None = None) -> list[str]:
        return audit.audit(
            self.root,
            self.policy if policy is None else policy,
            [] if sarif is None else [sarif],
            today=dt.date(2026, 7, 24),
        )

    def assert_rejected(self, fragment: str, *, sarif: dict, policy: dict | None = None) -> None:
        findings = self.findings(sarif, policy)
        self.assertTrue(any(fragment in item for item in findings), findings)

    def test_reviewed_vendor_result_passes(self) -> None:
        self.assertEqual([], self.findings(self.sarif(self.vendor_result)))

    def test_upload_only_fingerprint_metadata_does_not_change_identity(self) -> None:
        post_processed = json.loads(json.dumps(self.vendor_result))
        post_processed["partialFingerprints"]["githubUploadFingerprint"] = "runner-only"
        self.assertEqual(
            audit.result_fingerprint(self.vendor_result),
            audit.result_fingerprint(post_processed),
        )
        self.assertEqual([], self.findings(self.sarif(post_processed)))

    def test_end_range_normalization_does_not_change_identity(self) -> None:
        normalized = json.loads(json.dumps(self.vendor_result))
        normalized["locations"][0]["physicalLocation"]["region"]["endColumn"] = 99
        self.assertEqual(
            audit.result_fingerprint(self.vendor_result),
            audit.result_fingerprint(normalized),
        )
        self.assertEqual([], self.findings(self.sarif(normalized)))

    def test_changed_codeql_line_hash_is_rejected(self) -> None:
        changed = json.loads(json.dumps(self.vendor_result))
        changed["partialFingerprints"]["primaryLocationLineHash"] = "changed-line:1"
        self.assert_rejected("unreviewed vendor finding", sarif=self.sarif(changed))

    def test_missing_codeql_line_hash_is_rejected(self) -> None:
        changed = json.loads(json.dumps(self.vendor_result))
        changed["partialFingerprints"].clear()
        self.assert_rejected("primaryLocationLineHash", sarif=self.sarif(changed))

    def test_zero_results_passes_without_weakening_policy_validation(self) -> None:
        self.assertEqual([], self.findings(self.sarif()))

    def test_new_authored_result_is_rejected(self) -> None:
        authored = self.result(
            "js/example", "web/nemoclaw/scripts/runtime.js",
            line=1, column=1, end_column=8, line_hash="authored-line:1",
        )
        self.assert_rejected("authored finding", sarif=self.sarif(authored))

    def test_exact_authored_safe_construction_control_passes(self) -> None:
        authored = self.result(
            "js/example", "web/nemoclaw/scripts/runtime.js",
            line=1, column=1, end_column=8, line_hash="authored-line:1",
        )
        policy = json.loads(json.dumps(self.policy))
        policy["authored_controls"] = [{
            "fingerprints": [audit.result_fingerprint(authored)],
            "artifact": "web/nemoclaw/scripts/runtime.js",
            "artifact_sha256": hashlib.sha256(self.authored.read_bytes()).hexdigest(),
            "decision": "inert-parse-allowlist-reconstruction",
            "owner": "course-maintainers",
            "expires": "2026-10-24",
            "controls": [{
                "path": "tests/validation/test_runtime_security.py",
                "contains": "test_safe_reconstruction",
            }],
            "scope": "Fixture inert parser reconstructs only allowed nodes.",
        }]
        self.assertEqual([], self.findings(self.sarif(authored), policy))

    def test_exact_tab_scoped_credential_boundary_passes(self) -> None:
        self.authored.write_text(
            'sessionStorage.setItem("nvapi", learnerKey);\n',
            encoding="utf-8",
        )
        authored = self.result(
            "js/clear-text-storage-of-sensitive-data",
            "web/nemoclaw/scripts/runtime.js",
            line=1,
            column=1,
            end_column=45,
            line_hash="tab-credential-line:1",
        )
        policy = json.loads(json.dumps(self.policy))
        policy["authored_controls"] = [{
            "fingerprints": [audit.result_fingerprint(authored)],
            "artifact": "web/nemoclaw/scripts/runtime.js",
            "artifact_sha256": hashlib.sha256(self.authored.read_bytes()).hexdigest(),
            "decision": "explicit-user-tab-credential-boundary",
            "owner": "course-maintainers",
            "expires": "2026-10-24",
            "controls": [{
                "path": "tests/validation/test_runtime_security.py",
                "contains": "test_safe_reconstruction",
            }],
            "scope": "Learner-entered bearer value is tab-scoped and cleared when the tab closes.",
        }]
        self.assertEqual([], self.findings(self.sarif(authored), policy))

    def test_authored_control_requires_an_approved_safe_construction_class(self) -> None:
        authored = self.result(
            "js/example", "web/nemoclaw/scripts/runtime.js",
            line=1, column=1, end_column=8, line_hash="authored-line:1",
        )
        policy = json.loads(json.dumps(self.policy))
        policy["authored_controls"] = [{
            "fingerprints": [audit.result_fingerprint(authored)],
            "artifact": "web/nemoclaw/scripts/runtime.js",
            "artifact_sha256": hashlib.sha256(self.authored.read_bytes()).hexdigest(),
            "decision": "accepted-risk",
            "owner": "course-maintainers",
            "expires": "2026-10-24",
            "controls": [{
                "path": "tests/validation/test_runtime_security.py",
                "contains": "test_safe_reconstruction",
            }],
            "scope": "Fixture",
        }]
        self.assert_rejected("approved reviewed-boundary", sarif=self.sarif(authored), policy=policy)

    def test_authored_control_requires_live_evidence_token(self) -> None:
        authored = self.result(
            "js/example", "web/nemoclaw/scripts/runtime.js",
            line=1, column=1, end_column=8, line_hash="authored-line:1",
        )
        policy = json.loads(json.dumps(self.policy))
        policy["authored_controls"] = [{
            "fingerprints": [audit.result_fingerprint(authored)],
            "artifact": "web/nemoclaw/scripts/runtime.js",
            "artifact_sha256": hashlib.sha256(self.authored.read_bytes()).hexdigest(),
            "decision": "inert-parse-allowlist-reconstruction",
            "owner": "course-maintainers",
            "expires": "2026-10-24",
            "controls": [{
                "path": "tests/validation/test_runtime_security.py",
                "contains": "missing_test_name",
            }],
            "scope": "Fixture",
        }]
        self.assert_rejected("control evidence", sarif=self.sarif(authored), policy=policy)

    def test_authored_path_cannot_receive_a_vendor_disposition(self) -> None:
        authored = self.result(
            "js/example", "web/nemoclaw/scripts/runtime.js",
            line=1, column=1, end_column=8, line_hash="authored-line:1",
        )
        policy = json.loads(json.dumps(self.policy))
        policy["artifacts"][0].update({
            "fingerprints": [audit.result_fingerprint(authored)],
            "artifact": "web/nemoclaw/scripts/runtime.js",
            "artifact_sha256": hashlib.sha256(self.authored.read_bytes()).hexdigest(),
            "evidence": ["web/nemoclaw/scripts/runtime.js"],
        })
        self.assert_rejected("not a vendored artifact", sarif=self.sarif(authored), policy=policy)

    def test_unknown_vendor_finding_is_rejected(self) -> None:
        changed = self.result(
            "js/new-rule", "web/nemoclaw/vendor/library.js",
            line=8, column=1, end_column=5, line_hash="new-line:1",
        )
        self.assert_rejected("unreviewed vendor finding", sarif=self.sarif(changed))

    def test_vendor_byte_drift_is_rejected(self) -> None:
        self.vendor.write_text("changed bytes\n", encoding="utf-8")
        self.assert_rejected("artifact digest differs", sarif=self.sarif(self.vendor_result))

    def test_expired_disposition_is_rejected(self) -> None:
        policy = json.loads(json.dumps(self.policy))
        policy["artifacts"][0]["expires"] = "2026-07-23"
        self.assert_rejected("expired", sarif=self.sarif(self.vendor_result), policy=policy)

    def test_duplicate_fingerprint_is_rejected(self) -> None:
        policy = json.loads(json.dumps(self.policy))
        policy["artifacts"].append(json.loads(json.dumps(policy["artifacts"][0])))
        self.assert_rejected("duplicate fingerprint", sarif=self.sarif(self.vendor_result), policy=policy)

    def test_fingerprint_is_bound_to_its_artifact(self) -> None:
        policy = json.loads(json.dumps(self.policy))
        policy["artifacts"][0]["artifact"] = "web/shared/vendor/library.js"
        self.assert_rejected("does not match SARIF artifact", sarif=self.sarif(self.vendor_result), policy=policy)

    def test_malformed_sarif_is_rejected(self) -> None:
        self.assert_rejected("SARIF", sarif={"version": "2.1.0", "runs": "not-a-list"})


if __name__ == "__main__":
    unittest.main()
