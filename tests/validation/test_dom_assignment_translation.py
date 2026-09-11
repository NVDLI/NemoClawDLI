# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Visible DOM assignments retain translations without treating expressions as UI text."""
import unittest
from scripts.translate.translate_html_segments import extract_segments


class DOMAssignmentTranslationTests(unittest.TestCase):
    def test_multiline_assignments_preserve_interpolation_and_exclude_near_matches(self):
        source = '''<html><script>
status.innerText = ready
  ? "Ready; continue when you choose."
  : `Verified progress is ${Number(progress) || 0}%. Complete the remaining checkpoints.`;
status.textContentExtra = "Unrelated property";
const same = status.textContent === "Comparison only";
</script></html>'''
        values = [item.text for item in extract_segments(source) if item.kind == 'script-ui']
        self.assertIn('Ready; continue when you choose.', values)
        self.assertIn('Verified progress is ${Number(progress) || 0}%. Complete the remaining checkpoints.', values)
        self.assertNotIn('Unrelated property', values)
        self.assertNotIn('Comparison only', values)
