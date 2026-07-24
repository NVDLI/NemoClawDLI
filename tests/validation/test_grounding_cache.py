# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation coverage for grounding cache dependencies."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validation import grounding


class GroundingCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="grounding-cache-")
        self.root = Path(self.temp.name)
        self.old_root = grounding.TASK1
        self.old_cache = grounding.CACHE
        self.old_index = grounding._MAT_INDEX
        self.old_hash = grounding._MAT_HASH
        grounding.TASK1 = self.root
        grounding.CACHE = self.root / "cache"
        grounding._MAT_INDEX = None
        grounding._MAT_HASH = None
        (self.root / "web/nemoclaw/mats").mkdir(parents=True)
        (self.root / "web/nemoclaw/page.html").write_text(
            '<h1>Page</h1><p><a href="https://docs.example.org/topic">source</a></p>'
        )

    def tearDown(self) -> None:
        grounding.TASK1 = self.old_root
        grounding.CACHE = self.old_cache
        grounding._MAT_INDEX = self.old_index
        grounding._MAT_HASH = self.old_hash
        self.temp.cleanup()

    def test_material_change_invalidates_page_cache(self) -> None:
        rel = "web/nemoclaw/page.html"
        first = grounding.ground_page(rel)
        self.assertFalse(first["cached"])
        self.assertFalse(first["reference"]["mat_grounded"])

        (self.root / "web/nemoclaw/mats/reference.md").write_text(
            "[Topic](https://docs.example.org/topic)"
        )
        grounding._MAT_INDEX = None
        grounding._MAT_HASH = None
        second = grounding.ground_page(rel)
        self.assertFalse(second["cached"])
        self.assertTrue(second["reference"]["mat_grounded"])


if __name__ == "__main__":
    unittest.main()
