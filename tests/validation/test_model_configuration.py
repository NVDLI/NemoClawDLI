#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Keep repository explorer model selection delegated to one course default."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = re.compile(
    r'<script type="application/json" id="explorer-config">(.*?)</script>',
    re.DOTALL,
)
DEFAULT = "nvidia/nemotron-3-nano-30b-a3b"


class ModelConfigurationTests(unittest.TestCase):
    def test_explorers_do_not_pin_independent_models(self) -> None:
        offenders: list[str] = []
        for path in ROOT.rglob("SKILL.html"):
            source = path.read_text(encoding="utf-8")
            match = CONFIG.search(source)
            if match and "model" in json.loads(match.group(1)):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], offenders)

    def test_course_runtime_declares_the_default_once(self) -> None:
        source = (ROOT / "web/nemoclaw/scripts/_shared.js").read_text(encoding="utf-8")
        self.assertEqual(1, source.count(DEFAULT))
        self.assertIn("export const REASONING_MODEL = DEFAULT_MODEL;", source)
        self.assertIn("const LAB_MODEL     = DEFAULT_MODEL;", source)

    def test_generators_do_not_reintroduce_a_model_pin(self) -> None:
        for relative in (
            "scripts/skills/gen_skill_hierarchy.py",
            "scripts/skills/gen_directory_beacons.py",
        ):
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn(DEFAULT, source)


if __name__ == "__main__":
    unittest.main()
