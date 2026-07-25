# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation coverage for the canonical course objective sequence."""
from __future__ import annotations

import unittest

from scripts.validation import course_contract


class CourseContractTests(unittest.TestCase):
    def test_objective_ids_follow_the_dynamic_canonical_length(self) -> None:
        expected = [
            f"learning-objective-{idx}"
            for idx in range(1, len(course_contract.CANONICAL["learning_objectives"]) + 1)
        ]
        source = "".join(f'<li id="{identifier}">Objective</li>' for identifier in expected)
        self.assertEqual(expected, course_contract.learning_objective_ids(source))

    def test_stale_extra_objective_id_is_visible(self) -> None:
        count = len(course_contract.CANONICAL["learning_objectives"])
        source = "".join(
            f'<li id="learning-objective-{idx}">Objective</li>'
            for idx in range(1, count + 2)
        )
        actual = course_contract.learning_objective_ids(source)
        expected = [f"learning-objective-{idx}" for idx in range(1, count + 1)]
        self.assertNotEqual(expected, actual)
        self.assertEqual(f"learning-objective-{count + 1}", actual[-1])

    def test_duplicate_or_gapped_objective_ids_are_visible(self) -> None:
        source = (
            '<li id="learning-objective-1">One</li>'
            '<li id="learning-objective-1">Duplicate</li>'
            '<li id="learning-objective-3">Gap</li>'
        )
        self.assertEqual(
            [
                "learning-objective-1",
                "learning-objective-1",
                "learning-objective-3",
            ],
            course_contract.learning_objective_ids(source),
        )


if __name__ == "__main__":
    unittest.main()
