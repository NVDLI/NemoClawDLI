# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Visible DOM assignments retain translations without treating expressions as UI text."""
import unittest
import subprocess
import sys
from scripts.translate.translate_html_segments import DOM_TEXT_STRING_RE, extract_segments


class DOMAssignmentTranslationTests(unittest.TestCase):
    def test_multiline_assignments_preserve_interpolation_and_exclude_near_matches(self):
        source = '''<html><script>
status.innerText = ready
  ? "Ready; continue when you choose."
  : `Verified progress is ${Number(progress) || 0}%. Complete the remaining checkpoints.`;
status.textContentExtra = "Unrelated property";
const same = status.textContent === "Comparison only";
</script></html>'''
        segments = [item for item in extract_segments(source) if item.kind == 'script-ui']
        for item in segments:
            self.assertEqual(source[item.start:item.end], item.text)
        values = [item.text for item in segments]
        self.assertIn('Ready; continue when you choose.', values)
        self.assertIn('Verified progress is ${Number(progress) || 0}%. Complete the remaining checkpoints.', values)
        self.assertNotIn('Unrelated property', values)
        self.assertNotIn('Comparison only', values)

    def test_escaped_quotes_backslashes_and_line_continuations_remain_one_string(self):
        for quote in ('"', "'", '`'):
            content = 'First ' + '\\' + quote + ' quote; ' + '\\\\' + ' path; ' + '\\\n' + 'next line'
            match = DOM_TEXT_STRING_RE.fullmatch(quote + content + quote)
            self.assertIsNotNone(match)
            self.assertEqual(match.group(2), content)

    def test_unterminated_dom_text_cannot_exhaust_regex_backtracking(self):
        source = '''from scripts.translate.translate_html_segments import DOM_TEXT_STRING_RE, UI_ASSIGN_RE
assert DOM_TEXT_STRING_RE.search("'" + chr(92) * 60000) is None
assert UI_ASSIGN_RE.search("node.textContent=" + " " * 60000) is None
'''
        subprocess.run([sys.executable, '-c', source], check=True, timeout=5)
