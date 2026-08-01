# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from scripts.validation.cell_audit import duplicate_object_keys


class CellDuplicateKeyTests(unittest.TestCase):
    def test_duplicate_direct_key_is_rejected(self) -> None:
        source = '''const request = {
  role: "system",
  content: ["First sentence.", "Second sentence."].join(" "),
  content: "This silently overrides the readable prompt.",
};'''
        self.assertEqual([("content", 4)], duplicate_object_keys(source))

    def test_nested_objects_keep_independent_key_scopes(self) -> None:
        source = '''const request = {
  content: "outer",
  metadata: { content: "nested", enabled: true },
  options: { content: "sibling", enabled: false },
};'''
        self.assertEqual([], duplicate_object_keys(source))

    def test_strings_comments_and_ternaries_do_not_create_keys(self) -> None:
        source = '''const request = {
  content: condition ? "a:b" : "c:d",
  // content: "disabled",
  note: `content: not a property`,
};'''
        self.assertEqual([], duplicate_object_keys(source))

    def test_quoted_literal_keys_are_also_rejected(self) -> None:
        source = '''const request = {
  "content": "first",
  'content': "second",
};'''
        self.assertEqual([("content", 3)], duplicate_object_keys(source))


if __name__ == "__main__":
    unittest.main()
