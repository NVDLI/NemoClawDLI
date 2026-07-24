# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for Markdown narrative extraction."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "validation"))

import prose_variety  # noqa: E402


class MarkdownNarrativeTests(unittest.TestCase):
    def test_wrapped_list_item_stays_whole(self) -> None:
        body = """# Contract

- Update the architecture source and regenerate its SVG. Production nodes remain source-backed.
  Local-only services remain explicit.
- Run the audit.

Closing guidance remains a paragraph.
"""
        self.assertEqual(
            [
                "Update the architecture source and regenerate its SVG. Production nodes remain source-backed. Local-only services remain explicit.",
                "Run the audit.",
                "Closing guidance remains a paragraph.",
            ],
            prose_variety._markdown_chunks(body),
        )

    def test_wrapped_line_is_not_scored_without_its_bullet_start(self) -> None:
        chunks = prose_variety._markdown_chunks(
            "- Local hooks provide early feedback\n  and can be bypassed.\n"
        )
        self.assertEqual(["Local hooks provide early feedback and can be bypassed."], chunks)

    def test_markdown_link_target_is_not_treated_as_prose(self) -> None:
        chunks = prose_variety._markdown_chunks(
            "Read [the guide](docs/guide.md) and [the plan](docs/plan.md).\n"
        )
        self.assertEqual(["Read the guide and the plan."], chunks)


if __name__ == "__main__":
    unittest.main()
