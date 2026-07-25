# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation tests for the agent continuity model experiment."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validation import agent_model_experiment_audit as audit


ROOT = Path(__file__).resolve().parents[2]


class AgentModelExperimentAuditTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory(prefix="agent-model-experiment-")
        root = Path(temporary.name)
        (root / "docs").mkdir()
        for path in (
            audit.PROTOCOL,
            audit.PROMPTS,
            audit.FOLLOWUP_PROTOCOL,
            audit.FOLLOWUP_PROMPTS,
        ):
            shutil.copy2(ROOT / path, root / path)
        return temporary, root

    def protocol(self, root: Path) -> dict[str, object]:
        return json.loads((root / audit.PROTOCOL).read_text(encoding="utf-8"))

    def write_protocol(self, root: Path, value: dict[str, object]) -> None:
        (root / audit.PROTOCOL).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def complete_results(self, root: Path) -> dict[str, object]:
        protocol = self.protocol(root)
        tasks = [
            task
            for group in protocol["task_groups"]
            for task in group["tasks"]
        ]
        return {
            "schema": audit.RESULTS_SCHEMA,
            "protocol_blob": audit.protocol_blob(root),
            "runs": [
                {
                    "arm_id": arm["id"],
                    "task_id": task["id"],
                    "status": "completed",
                    "score": 80,
                    "score_components": {
                        "functional_correctness": 30,
                        "held_out_generality": 15,
                        "safety_and_governance": 15,
                        "continuity_and_exact_evidence": 15,
                        "efficiency": 5
                    },
                    "hard_violations": [],
                    "evidence": {
                        "fixture_tree": "0" * 40,
                        "resolved_model": "test-model",
                        "exit_code": 0,
                        "duration_ms": 1,
                        "tool_actions": 1,
                        "changed_files": [],
                        "grader": "pass"
                    },
                    "summary": "Sanitized deterministic test scorecard for one run.",
                }
                for arm in protocol["arms"]
                for task in tasks
            ],
        }

    def write_results(self, root: Path, value: dict[str, object]) -> None:
        (root / audit.RESULTS).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    def test_preregistered_protocol_passes_before_results(self) -> None:
        self.assertEqual([], audit.audit(ROOT), "\n".join(audit.audit(ROOT)))

    def test_novel_arm_expands_the_required_result_matrix(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        protocol = self.protocol(root)
        protocol["arms"].append({
            "id": "new-model",
            "harness": "codex-cli",
            "cli_version": "test",
            "model": "new",
        })
        self.write_protocol(root, protocol)
        results = self.complete_results(root)
        results["runs"] = [
            run for run in results["runs"] if run["arm_id"] != "new-model"
        ]
        self.write_results(root, results)
        self.assertTrue(any("missing" in item and "run(s)" in item for item in audit.audit(root)))

    def test_task_without_oracle_is_rejected(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        protocol = self.protocol(root)
        protocol["task_groups"][0]["tasks"][0]["oracle"] = []
        self.write_protocol(root, protocol)
        self.assertTrue(any("needs a concrete oracle" in item for item in audit.audit(root)))

    def test_prompt_ids_follow_the_dynamic_task_registry(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        prompts = json.loads((root / audit.PROMPTS).read_text(encoding="utf-8"))
        prompts["tasks"].pop(next(iter(prompts["tasks"])))
        (root / audit.PROMPTS).write_text(json.dumps(prompts, indent=2) + "\n", encoding="utf-8")
        self.assertTrue(any("prompt ids must match" in item for item in audit.audit(root)))

    def test_hard_violation_caps_the_score(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        results = self.complete_results(root)
        results["runs"][0]["hard_violations"] = ["host repository Python"]
        results["runs"][0]["score"] = 90
        self.write_results(root, results)
        self.assertTrue(any("exceeds the cap" in item for item in audit.audit(root)))

    def test_raw_transcript_field_is_rejected(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        results = self.complete_results(root)
        results["runs"][0]["raw_transcript"] = "not retained"
        self.write_results(root, results)
        self.assertTrue(any("raw or sensitive" in item for item in audit.audit(root)))

    def test_nested_raw_field_is_rejected(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        results = self.complete_results(root)
        results["runs"][0]["evidence"]["raw_transcript"] = "not retained"
        self.write_results(root, results)
        self.assertTrue(any("raw or sensitive" in item for item in audit.audit(root)))

    def test_score_must_equal_bounded_components(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        results = self.complete_results(root)
        results["runs"][0]["score_components"]["functional_correctness"] = 41
        self.write_results(root, results)
        findings = audit.audit(root)
        self.assertTrue(any("invalid functional_correctness" in item for item in findings))
        self.assertTrue(any("does not equal its components" in item for item in findings))

    def test_runtime_evidence_must_be_typed_and_non_negative(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        results = self.complete_results(root)
        results["runs"][0]["evidence"]["duration_ms"] = -1
        results["runs"][0]["evidence"]["tool_actions"] = "many"
        self.write_results(root, results)
        findings = audit.audit(root)
        self.assertTrue(any("duration_ms must be a non-negative integer" in item for item in findings))
        self.assertTrue(any("tool_actions must be a non-negative integer" in item for item in findings))

    def test_parent_results_require_the_blinded_followup_results(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        self.write_results(root, self.complete_results(root))
        self.assertTrue(
            any(str(audit.FOLLOWUP_RESULTS) in item and "required" in item
                for item in audit.audit(root))
        )

    def test_followup_must_bind_the_frozen_parent(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        followup = json.loads((root / audit.FOLLOWUP_PROTOCOL).read_text(encoding="utf-8"))
        followup["parent_protocol_blob"] = "0" * 40
        (root / audit.FOLLOWUP_PROTOCOL).write_text(
            json.dumps(followup, indent=2) + "\n",
            encoding="utf-8",
        )
        self.assertTrue(any("frozen parent" in item for item in audit.audit(root)))

    def test_followup_prompts_must_not_reveal_the_condition(self) -> None:
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        prompts = json.loads((root / audit.FOLLOWUP_PROMPTS).read_text(encoding="utf-8"))
        prompts["tasks"]["blind-recover-ablated"] += " The beacons were removed."
        (root / audit.FOLLOWUP_PROMPTS).write_text(
            json.dumps(prompts, indent=2) + "\n",
            encoding="utf-8",
        )
        self.assertTrue(any("must be identical" in item for item in audit.audit(root)))


if __name__ == "__main__":
    unittest.main()
