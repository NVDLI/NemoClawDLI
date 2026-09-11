# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.runtime.host_browser import resolve_node_path
from scripts.validation.localization_runtime_audit import discover_learner_pages
from scripts.validation.runtime_integration_browser_audit import (
    LOCALE_PAGES, RUNTIME_JS, discover_artifact_locales,
)


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


class RuntimeArtifactLocaleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        self.languages = [{"code": "en", "locale": "en", "url": "nemoclaw/"}]
        self.add_locale(self.languages[0])

    def add_locale(self, row):
        course = self.site / row["url"]
        course.mkdir(parents=True, exist_ok=True)
        for filename in LOCALE_PAGES:
            (course / filename).write_text(f'<html lang="{row["locale"]}"></html>')
        if row["code"] != "en":
            (course / "assets").mkdir(exist_ok=True)
            (course / "assets/locale.json").write_text(json.dumps({
                "schema": "nemoclaw-locale/1", "url_code": row["code"], "locale": row["locale"],
            }))
        if row not in self.languages:
            self.languages.append(row)
        self.write_manifest()

    def write_manifest(self):
        (self.site / "languages.json").write_text(json.dumps({
            "schema": "nemoclaw-languages/1", "default": "en", "languages": self.languages,
        }))

    def test_novel_and_renamed_locale_routes_are_discovered(self):
        row = {"code": "ja", "locale": "ja-JP", "url": "ja/nemoclaw/"}
        self.add_locale(row)
        self.assertEqual(discover_artifact_locales(self.site), self.languages)
        (self.site / "ja").rename(self.site / "jp")
        row.update(code="jp", url="jp/nemoclaw/")
        self.add_locale(row)
        self.assertEqual(discover_artifact_locales(self.site), self.languages)

    def test_deleted_and_renamed_declared_pages_fail(self):
        row = {"code": "ja", "locale": "ja-JP", "url": "ja/nemoclaw/"}
        self.add_locale(row)
        page = self.site / row["url"] / "03c-always-on.html"
        renamed = page.with_name("renamed-cron.html")
        page.rename(renamed)
        with self.assertRaisesRegex(ValueError, "missing a required route"):
            discover_artifact_locales(self.site)
        renamed.unlink()
        with self.assertRaisesRegex(ValueError, "missing a required route"):
            discover_artifact_locales(self.site)

    def test_deleting_a_declaration_does_not_hide_its_delivered_locale(self):
        self.add_locale({"code": "ja", "locale": "ja-JP", "url": "ja/nemoclaw/"})
        self.languages.pop()
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "missing from languages.json"):
            discover_artifact_locales(self.site)

    def test_nested_locale_declaration_removal_is_rejected(self):
        self.add_locale({"code": "ja", "locale": "ja-JP", "url": "preview/ja/nemoclaw/"})
        self.assertEqual(discover_artifact_locales(self.site), self.languages)
        self.languages.pop()
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "missing from languages.json"):
            discover_artifact_locales(self.site)

    def test_missing_published_manifest_fails_instead_of_falling_back_to_source(self):
        (self.site / "languages.json").unlink()
        with self.assertRaises(FileNotFoundError):
            discover_artifact_locales(self.site)

    def test_malformed_duplicate_and_escaping_declarations_fail(self):
        for change in ({"locale": "unknown??"}, {"code": "../ja"}, {"url": "../ja/nemoclaw/"},
                       {"url": "https://example.test/nemoclaw/"}, {"url": "ja/nemoclaw/?query"}):
            with self.subTest(change=change):
                self.languages = [{"code": "en", "locale": "en", "url": "nemoclaw/"},
                                  {"code": "ja", "locale": "ja-JP", "url": "ja/nemoclaw/", **change}]
                self.write_manifest()
                with self.assertRaises(ValueError):
                    discover_artifact_locales(self.site)
        self.languages = [self.languages[0], dict(self.languages[0])]
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            discover_artifact_locales(self.site)

    def test_locale_metadata_mismatch_is_rejected(self):
        row = {"code": "ja", "locale": "ja-JP", "url": "ja/nemoclaw/"}
        self.add_locale(row)
        metadata = self.site / row["url"] / "assets/locale.json"
        metadata.write_text(json.dumps({"schema": "nemoclaw-locale/1", "url_code": "ja", "locale": "en"}))
        with self.assertRaisesRegex(ValueError, "delivered locale metadata"):
            discover_artifact_locales(self.site)


class RuntimeBrowserFixtureTests(unittest.TestCase):
    def test_explorer_follows_course_local_and_nested_source_layouts(self):
        prefix = RUNTIME_JS.split("(async () => {", 1)[0]
        with tempfile.TemporaryDirectory() as temporary:
            site = Path(temporary)
            for course, explorer in (("novel-course/", "novel-course/_skill_explorer.js"),
                                     ("preview/source/renamed-course/", "preview/source/_skill_explorer.js")):
                with self.subTest(course=course):
                    script = site / explorer
                    script.parent.mkdir(parents=True, exist_ok=True)
                    script.write_text("// course-owned explorer")
                    env = {**os.environ, "NODE_PATH": resolve_node_path(), "SITE_ROOT": str(site), "ARTIFACT_LOCALES": json.dumps([
                        {"code": "en", "url": course},
                    ])}
                    result = subprocess.run(["node", "-e", prefix + "console.log(courseExplorerPath());"],
                                            capture_output=True, text=True, env=env, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), "/" + explorer)
                    script.unlink()
                    result = subprocess.run(["node", "-e", prefix + "courseExplorerPath();"],
                                            capture_output=True, text=True, env=env, check=False)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("missing course explorer script", result.stderr)

    def test_top_level_fixture_does_not_access_sandbox_storage(self):
        prefix = RUNTIME_JS.split("(async () => {", 1)[0]
        checks = r"""
const assert = require('assert/strict');
const vm = require('vm');
const script = topLevelInitScript(() => window.sessionStorage.setItem('fixture', 'ready'));
const top = {}; top.top = top;
let stored;
top.sessionStorage = {setItem:(key,value) => stored = [key,value]};
vm.runInNewContext(script, {window:top});
assert.deepEqual(stored, ['fixture','ready']);
let accesses = 0;
const frame = {top, get sessionStorage() {accesses++; throw new Error('opaque sandbox storage');}};
const sandbox = {window:frame};
vm.runInNewContext(script, sandbox);
assert.equal(accesses, 0);
assert.throws(() => vm.runInNewContext(script.replace('window === window.top', 'true'), sandbox), /opaque sandbox storage/);
assert.equal(accesses, 1);
"""
        result = subprocess.run(["node", "-e", prefix + checks], capture_output=True, text=True,
                                env={**os.environ, "NODE_PATH": resolve_node_path(),
                                     "ARTIFACT_LOCALES": '[{"code":"en","url":"nemoclaw/"}]'},
                                check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
