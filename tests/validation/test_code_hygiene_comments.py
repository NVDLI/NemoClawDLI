# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Code hygiene handles readable comments and URL-shaped source safely."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.validation import code_hygiene


class CommentHygieneTests(unittest.TestCase):
    @staticmethod
    def findings(source: str) -> list[dict]:
        unit = [("fixture.js", "js", source, 0)]
        with patch.object(code_hygiene, "units", return_value=unit):
            code_hygiene._ANALYZE_CACHE.clear()
            return code_hygiene.comment_findings("ship")

    def test_short_wrapped_comment_is_readable(self) -> None:
        rows = self.findings(
            "// The first line introduces a constraint that continues naturally\n"
            "// on the next line without forcing an excessively wide source line.\n"
            "const value = 1;\n"
        )
        self.assertEqual([], rows)

    def test_long_comment_block_still_requires_compression(self) -> None:
        rows = self.findings("// one\n// two\n// three\n// four\nconst value = 1;\n")
        self.assertEqual(["comment-block-too-long"], [row["kind"] for row in rows])


class ConstantHygieneTests(unittest.TestCase):
    @staticmethod
    def findings(source: str) -> list[dict]:
        unit = [("fixture.py", ".py", source, 0)]
        with patch.object(code_hygiene, "units", return_value=unit):
            code_hygiene._ANALYZE_CACHE.clear()
            return code_hygiene.constant_findings("ship")

    def test_named_https_regex_is_configuration_not_a_url_parse_error(self) -> None:
        rows = self.findings('VIDEO_URL_RE = re.compile(r"^https://[^/?#]+/video\\.mp4$")\n')
        self.assertEqual([], rows)

    def test_malformed_url_like_literal_becomes_a_finding(self) -> None:
        rows = self.findings('pattern = r"https://[^"\n')
        self.assertEqual(["embedded-url"], [row["kind"] for row in rows])


if __name__ == "__main__":
    unittest.main()
