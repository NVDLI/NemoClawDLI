# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation and compatibility tests for the declarative ReACS suite registry."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validation import reacs_registry
from scripts.validation import release_gate


class ReacsRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(reacs_registry.REGISTRY_PATH.read_text(encoding="utf-8"))

    def load(self, mutate=None) -> reacs_registry.Registry:
        document = json.loads(json.dumps(self.document))
        if mutate:
            mutate(document)
        with tempfile.TemporaryDirectory(prefix="reacs-registry-") as directory:
            path = Path(directory) / "registry.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return reacs_registry.load_registry(path)

    def test_registry_preserves_current_fast_and_ship_commands(self) -> None:
        registry = self.load()
        for tier, expected in (("fast", release_gate.FAST_COMMANDS), ("ship", release_gate.SHIP_COMMANDS)):
            actual = [command for _, command in registry.for_tier(tier, no_reports=False)]
            self.assertEqual(list(expected), actual)

    def test_no_report_projection_matches_existing_gate_behavior(self) -> None:
        registry = self.load()
        for tier in ("fast", "ship"):
            actual = [command for _, command in registry.for_tier(tier, no_reports=True)]
            self.assertEqual(release_gate.commands_for(tier, no_write=True), actual)

    def test_duplicate_suite_identifier_is_rejected(self) -> None:
        def mutate(document):
            document["suites"][1]["id"] = document["suites"][0]["id"]
        with self.assertRaisesRegex(reacs_registry.RegistryError, "identifiers must be unique"):
            self.load(mutate)

    def test_mutation_suite_without_impacts_is_rejected(self) -> None:
        def mutate(document):
            suite = next(item for item in document["suites"] if item["mode"] == "mutation")
            suite.pop("impacts")
        with self.assertRaisesRegex(reacs_registry.RegistryError, "must declare impacts"):
            self.load(mutate)

    def test_unsafe_impact_path_is_rejected(self) -> None:
        def mutate(document):
            suite = next(item for item in document["suites"] if item["mode"] == "mutation")
            suite["impacts"] = ["../outside"]
        with self.assertRaisesRegex(reacs_registry.RegistryError, "unsafe path pattern"):
            self.load(mutate)

    def test_invalid_tier_order_is_rejected(self) -> None:
        def mutate(document):
            suite = next(item for item in document["suites"] if "fast" in item["tiers"])
            suite["order"]["fast"] = 999
        with self.assertRaisesRegex(reacs_registry.RegistryError, "contiguous and unique"):
            self.load(mutate)

    def test_registry_or_ci_policy_change_selects_every_mutation(self) -> None:
        registry = self.load()
        expected = {suite.id for suite in registry.suites if suite.mode == "mutation"}
        for path in ("scripts/validation/reacs_registry.json", ".gitlab/ci/core.yml"):
            selected, reason = registry.selected_mutations({path})
            self.assertEqual(expected, selected)
            self.assertEqual("policy-change-full-matrix", reason)

    def test_unclaimed_path_selects_every_mutation_regardless_of_location_or_type(self) -> None:
        registry = self.load()
        expected = {suite.id for suite in registry.suites if suite.mode == "mutation"}
        paths = (
            "new-surface/file.txt",
            "docs/new-policy-without-extension",
            "scripts/new_unregistered_gate.py",
            "README.next",
        )
        for path in paths:
            with self.subTest(path=path):
                selected, reason = registry.selected_mutations({path})
                self.assertEqual(expected, selected)
                self.assertEqual("unclaimed-path-full-matrix", reason)

    def test_add_delete_rename_and_copy_always_select_every_mutation(self) -> None:
        registry = self.load()
        expected = {suite.id for suite in registry.suites if suite.mode == "mutation"}
        signals = ("commit:A", "commit:D", "commit:R100:to", "index:C087:from")
        for signal in signals:
            with self.subTest(signal=signal):
                path = "web/nemoclaw/assets/claimed-by-broad-pattern.bin"
                selected, reason = registry.selected_mutations({path}, {path: {signal}})
                self.assertEqual(expected, selected)
                self.assertEqual("structural-change-full-matrix", reason)

    def test_default_impact_cannot_be_weakened(self) -> None:
        def mutate(document):
            document["default_impact"] = "ignore"
        with self.assertRaisesRegex(reacs_registry.RegistryError, "must remain full-matrix"):
            self.load(mutate)

    def test_known_document_uses_declared_change_impacts(self) -> None:
        registry = self.load()
        path = "docs/agent_process.md"
        selected, reason = registry.selected_mutations({path}, {path: {"commit:M"}})
        self.assertEqual("change-aware", reason)
        self.assertTrue(selected)
        self.assertNotEqual(
            {suite.id for suite in registry.suites if suite.mode == "mutation"}, selected,
        )

    def test_release_without_changed_paths_selects_every_mutation(self) -> None:
        registry = self.load()
        selected, reason = registry.selected_mutations(None)
        self.assertEqual(
            {suite.id for suite in registry.suites if suite.mode == "mutation"}, selected,
        )
        self.assertEqual("full-matrix", reason)

    def test_parallel_safe_suites_are_mutation_only_and_have_no_resource_collision(self) -> None:
        registry = self.load()
        parallel = [suite for suite in registry.suites if suite.parallel_safe]
        self.assertTrue(parallel)
        self.assertTrue(all(suite.mode == "mutation" for suite in parallel))
        self.assertTrue(all(not suite.exclusive_resources for suite in parallel))


if __name__ == "__main__":
    unittest.main()
