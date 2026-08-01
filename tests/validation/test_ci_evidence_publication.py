# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contracts for publishing generated CI evidence without private host links."""
from __future__ import annotations

import unittest
from pathlib import Path

from scripts.skills import skill_renderer_runtime_audit


ROOT = Path(__file__).resolve().parents[2]


class CiEvidencePublicationTests(unittest.TestCase):
    def test_secure_same_origin_artifact_copies_remain_auditable(self) -> None:
        ui = (ROOT / "scripts/compliance/third_party_export_ui.js").read_text(
            encoding="utf-8",
        )
        secure_fallback = (
            'kind:artifact.href ? "ci-artifact" : "ci-artifact-preview"'
        )
        self.assertEqual(2, ui.count(secure_fallback))
        self.assertNotIn(
            'kind:artifact.href ? "ci-artifact" : "local"',
            ui,
        )

        runtime = skill_renderer_runtime_audit.RUNTIME_JS
        self.assertIn(
            'a[data-evidence-link="ci-artifact-preview"]',
            runtime,
        )
        direct_only = runtime.replace(
            ', a[data-evidence-link="ci-artifact-preview"]',
            "",
            1,
        )
        self.assertNotEqual(runtime, direct_only)
        self.assertNotIn(
            'a[data-evidence-link="ci-artifact-preview"]',
            direct_only,
        )


if __name__ == "__main__":
    unittest.main()
