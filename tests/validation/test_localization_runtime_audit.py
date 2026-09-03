# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import tempfile
import unittest
from pathlib import Path

from scripts.validation.localization_runtime_audit import discover_learner_pages


class LocalizationRuntimeDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.site = Path(self.temp.name)
        self.course = self.site / "course"
        self.course.mkdir()
        self.manifest = {
            "default": "en",
            "languages": [{"code": "en", "url": "course/"}],
        }

    def tearDown(self):
        self.temp.cleanup()

    def write_lessons(self, *ids):
        (self.course / "learning-profile.json").write_text(
            json.dumps({"lessons": [{"id": lesson_id} for lesson_id in ids]}),
            encoding="utf-8",
        )

    def test_novel_deleted_and_renamed_lessons_follow_the_profile(self):
        self.write_lessons("first", "novel-route")
        self.assertEqual(
            discover_learner_pages(self.site, self.manifest),
            ["first.html", "index.html", "novel-route.html"],
        )
        self.write_lessons("renamed-route")
        self.assertEqual(discover_learner_pages(self.site, self.manifest), ["index.html", "renamed-route.html"])

    def test_malformed_and_duplicate_lessons_fail_closed(self):
        for ids in (("../escape",), ("duplicate", "duplicate"), ()):
            with self.subTest(ids=ids):
                self.write_lessons(*ids)
                with self.assertRaises(ValueError):
                    discover_learner_pages(self.site, self.manifest)


if __name__ == "__main__":
    unittest.main()
