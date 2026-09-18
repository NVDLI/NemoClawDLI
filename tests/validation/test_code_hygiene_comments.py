# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Code hygiene handles readable comments and URL-shaped source safely."""
from __future__ import annotations

import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from scripts.validation import code_hygiene
from scripts.validation import learner_flow_audit
from scripts.validation import locale_resource_mutations as locale_fixtures
from translate.locale_resources import LocaleResourceError, derive_key


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


class AuthoredPunctuationTests(unittest.TestCase):
    def test_owned_module_suffixes_follow_rename_and_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / 'web/new-course/nested'
            parent.mkdir(parents=True)
            with patch.object(code_hygiene, 'TASK1', root):
                for suffix in ('.ts', '.mts', '.cts', '.tsx', '.jsx', '.mjs', '.cjs', '.css'):
                    with self.subTest(suffix=suffix):
                        path = parent / ('new' + suffix)
                        path.write_text('/* Read ' + chr(0x2014) + ' inspect. */', encoding='utf-8')
                        self.assertEqual(len(code_hygiene.prose_findings('ship')), 1)
                        renamed = path.with_name('renamed' + suffix)
                        path.rename(renamed)
                        rows = code_hygiene.prose_findings('ship')
                        self.assertEqual(rows[0]['path'], renamed.relative_to(root).as_posix())
                        renamed.unlink()
                        self.assertEqual(code_hygiene.prose_findings('ship'), [])

    def test_real_locale_discovery_values_history_rename_delete_and_malformed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            locale_fixtures.build_fixture(root)
            original = locale_fixtures.resource_path(root)
            data = json.loads(original.read_text())
            source = 'Earlier wording ' + chr(0x2014) + ' retained for provenance'
            key = derive_key('text', source)
            data['values'][key] = {'type':'text', 'source':source, 'value':'Reviewed current wording'}
            original.write_text(json.dumps(data), encoding='utf-8')
            with patch.object(code_hygiene, 'TASK1', root):
                self.assertEqual(code_hygiene.prose_findings('ship'), [])
                data['values'][key]['value'] = 'Read &mdash; inspect'
                original.write_text(json.dumps(data), encoding='utf-8')
                rows = code_hygiene.prose_findings('ship')
                self.assertTrue(any(row['path'] == original.relative_to(root).as_posix() for row in rows))
                nested = original.parent / 'new/nested.html.json'
                nested.parent.mkdir()
                original.rename(nested)
                rows = code_hygiene.prose_findings('ship')
                self.assertTrue(any(row['path'] == nested.relative_to(root).as_posix() for row in rows))
                self.assertFalse(any(row['path'] == original.relative_to(root).as_posix() for row in rows))
                data['values'][key]['value'] = '<select class="learning-depth-select">Depth</select>'
                nested.write_text(json.dumps(data), encoding='utf-8')
                self.assertTrue(learner_flow_audit.audit_retired_course_modes(
                    learner_flow_audit.locale_resource_surfaces(root)))
                nested.unlink()
                self.assertEqual(code_hygiene.prose_findings('ship'), [])
                self.assertEqual(learner_flow_audit.audit_retired_course_modes(
                    learner_flow_audit.locale_resource_surfaces(root)), [])
                nested.write_text('{"values": null}', encoding='utf-8')
                with self.assertRaises(LocaleResourceError):
                    code_hygiene.prose_findings('ship')
                with self.assertRaises(LocaleResourceError):
                    learner_flow_audit.locale_resource_surfaces(root)

    def test_rendered_forms_and_near_matches(self) -> None:
        dash = chr(0x2014)
        for value in (dash, '&mdash;', '&#8212;', '&#x2014;', '&#x02014;',
                      r'\u2014', r'\u{2014}', r'\u{02014}'):
            with self.subTest(value=value):
                self.assertEqual(code_hygiene.normalize_prose_punctuation(value), dash)
        for value in ('&mdashx;', r'\u201g', r'\\u2014', '課程與練習'):
            with self.subTest(value=value):
                self.assertEqual(code_hygiene.normalize_prose_punctuation(value), value)
        self.assertNotIn(dash, code_hygiene.normalize_prose_punctuation('&#x201g;'))

    def test_new_nested_renamed_deleted_markup_and_attributes_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'web/new-course/nested/new.html'
            path.parent.mkdir(parents=True)
            with patch.object(code_hygiene, 'TASK1', root):
                path.write_text('<h1 title="Read &mdash; inspect">Course</h1>', encoding='utf-8')
                rows = code_hygiene.prose_findings('ship')
                self.assertTrue(any(row['path'] == 'web/new-course/nested/new.html' for row in rows))
                renamed = path.with_name('renamed.html')
                path.rename(renamed)
                rows = code_hygiene.prose_findings('ship')
                self.assertFalse(any(row['path'].endswith('/new.html') for row in rows))
                self.assertTrue(any(row['path'].endswith('/renamed.html') for row in rows))
                renamed.unlink()
                self.assertEqual(code_hygiene.prose_findings('ship'), [])


if __name__ == "__main__":
    unittest.main()
