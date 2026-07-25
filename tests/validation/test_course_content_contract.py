# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation coverage for retired course-runtime terminology."""
from __future__ import annotations

import unittest

from scripts.validation import course_content_contract


class CourseContentContractTests(unittest.TestCase):
    def test_retired_runtime_patterns_are_detected(self) -> None:
        for source in (
            "No lab proxy is required.",
            "Route through llm_client.",
            "POST http://localhost:9000/v1/chat/completions",
            "Connect to the service at :9000.",
        ):
            with self.subTest(source=source):
                self.assertIsNotNone(course_content_contract.OBSOLETE_RUNTIME_RE.search(source))

    def test_current_authored_tree_has_no_retired_runtime_references(self) -> None:
        self.assertEqual([], course_content_contract.obsolete_runtime_references())


if __name__ == "__main__":
    unittest.main()
