#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation coverage for browser-tolerant validator HTML parsing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _bootstrap import add_script_paths  # noqa: E402

add_script_paths(ROOT / "scripts")
from html_document import raw_text_blocks, script_body_by_id, without_elements  # noqa: E402


class HtmlDocumentTests(unittest.TestCase):
    def test_malformed_browser_script_end_tags_cannot_hide_following_content(self) -> None:
        for ending in ("</script foo=\"bar\">", "</script\t\n bar>"):
            with self.subTest(ending=ending):
                raw = f"<script>danger(){ending}<p>visible</p>"
                blocks = raw_text_blocks(raw, "script")
                self.assertEqual([block.body for block in blocks], ["danger()"])
                projection = without_elements(raw, {"script"})
                self.assertNotIn("danger()", projection)
                self.assertIn("visible", projection)

    def test_script_metadata_and_source_position_follow_the_parsed_document(self) -> None:
        raw = '<p>before</p><script type="module">\nrun();\n</script><p>after</p>'
        block = raw_text_blocks(raw, "script")[0]
        self.assertEqual(block.attributes, {"type": "module"})
        self.assertEqual(block.body, "\nrun();\n")
        self.assertEqual(raw[block.body_start:block.body_start + len(block.body)], block.body)

    def test_comments_and_longer_element_names_are_not_script_boundaries(self) -> None:
        raw = (
            "<!-- <script>commented()</script> -->"
            "<scripture>ordinary element</scripture>"
            '<script id="real">run()</script>'
        )
        block = raw_text_blocks(raw, "script")[0]
        self.assertEqual(block.attributes, {"id": "real"})
        self.assertEqual(block.body, "run()")
        self.assertEqual(
            without_elements(raw, {"script"}),
            "<!-- <script>commented()</script> -->"
            "<scripture>ordinary element</scripture>",
        )

    def test_script_body_by_id_uses_structural_selection(self) -> None:
        raw = (
            '<script id="other" type="application/json">{"wrong": true}</script>'
            '<script id="skill-meta" type="application/json">{"right": true}</script>'
        )
        self.assertEqual(script_body_by_id(raw, "skill-meta"), '{"right": true}')
        self.assertIsNone(script_body_by_id(raw, "missing"))

    def test_removal_preserves_untouched_authored_entities(self) -> None:
        raw = "<p>left&mdash;right</p><script>hidden()</script>"
        self.assertEqual(
            without_elements(raw, {"script"}),
            "<p>left&mdash;right</p>",
        )


if __name__ == "__main__":
    unittest.main()
