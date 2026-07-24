# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation tests for the GitHub-hosted CodeQL readiness check."""
from __future__ import annotations

import unittest

from scripts.security import audit_github_code_scanning as audit


class GithubCodeScanningAuditTests(unittest.TestCase):
    @staticmethod
    def check(*, status: str = "completed", conclusion: str = "success", app: str = audit.CODEQL_APP) -> dict:
        return {
            "total_count": 1,
            "check_runs": [{
                "name": audit.CODEQL_CHECK,
                "status": status,
                "conclusion": conclusion,
                "app": {"slug": app},
                "output": {"title": "No new alerts in code changed by this pull request"},
            }],
        }

    def test_exact_green_host_state_passes(self) -> None:
        self.assertEqual([], audit.audit(self.check(), []))

    def test_repository_workflow_success_cannot_replace_host_check(self) -> None:
        snapshot = {
            "total_count": 1,
            "check_runs": [{
                "name": "analyze (javascript-typescript)",
                "status": "completed",
                "conclusion": "success",
                "app": {"slug": "github-actions"},
            }],
        }
        findings = audit.audit(snapshot, [])
        self.assertTrue(any("expected one" in item for item in findings), findings)

    def test_host_failure_is_not_hidden_by_reviewed_sarif(self) -> None:
        snapshot = self.check(conclusion="failure")
        snapshot["check_runs"][0]["output"]["title"] = "24 new alerts including 22 high severity"
        findings = audit.audit(snapshot, [])
        self.assertTrue(any("24 new alerts" in item for item in findings), findings)

    def test_pending_host_check_blocks_readiness(self) -> None:
        findings = audit.audit(self.check(status="in_progress", conclusion=None), [])
        self.assertTrue(any("in_progress/None" in item for item in findings), findings)

    def test_open_pull_request_alerts_block_readiness(self) -> None:
        findings = audit.audit(self.check(), [{"number": 27}, {"number": 41}])
        self.assertTrue(any("2 CodeQL alert(s)" in item for item in findings), findings)

    def test_unrelated_check_named_codeql_does_not_satisfy_host_gate(self) -> None:
        findings = audit.audit(self.check(app="github-actions"), [])
        self.assertTrue(any("expected one" in item for item in findings), findings)

    def test_malformed_snapshots_fail_closed(self) -> None:
        self.assertTrue(audit.audit({}, []))
        self.assertTrue(audit.audit(self.check(), {"number": 27}))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
