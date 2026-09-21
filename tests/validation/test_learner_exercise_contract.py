# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Focused production-detector mutations; external runtime behavior has Node tests."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.validation import learner_flow_audit as audit


class LearnerExerciseContractTests(unittest.TestCase):
    def test_retired_modes_follow_new_nested_renamed_and_deleted_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = self.inventory_fixture(root)
            nested = course / 'nested/new.html'
            nested.parent.mkdir()
            for suffix, content in [
                ('.html', '<select class="learning-depth-select"><option>Guided</option></select>'),
                ('.htm', '<select class="learning-depth-select"><option>Guided</option></select>'),
                ('.js', 'localStorage.setItem("nemoclaw_learning_depth_v1", "applied");'),
                ('.mjs', 'export const storageKey = "nemoclaw_learning_depth_v1";'),
                ('.ts', 'export const storageKey: string = "nemoclaw_learning_depth_v1";'),
                ('.css', '.learning-depth-control { display: none; }'),
            ]:
                path = nested.with_suffix(suffix)
                path.write_text(content, encoding='utf-8')
                for candidate in (path, path.with_name('renamed' + suffix)):
                    if candidate != path:
                        path.rename(candidate)
                    surfaces = {p.relative_to(root).as_posix(): p.read_text()
                                for p in audit.learner_surface_files(root)}
                    findings = audit.audit_retired_course_modes(surfaces)
                    self.assertEqual(len(findings), 1)
                    self.assertIn(candidate.relative_to(root).as_posix(), findings[0])
                candidate.unlink()
                surfaces = {p.relative_to(root).as_posix(): p.read_text()
                            for p in audit.learner_surface_files(root)}
                self.assertEqual(audit.audit_retired_course_modes(surfaces), [])

    def test_retired_mode_near_matches_cannot_hide_in_translated_markup(self) -> None:
        for markup in ['<select class="learning&#45;depth-select">',
                       '<details DATA-LEARNING-TIER="deep">',
                       '<div class="learning-depth-contrl">',
                       'applyLearningDepth("complete");']:
            with self.subTest(markup=markup):
                self.assertTrue(audit.audit_retired_course_modes({'i18n/novel/nested/page.json': markup}))
        self.assertEqual(audit.audit_retired_course_modes({
            'new.html': '<p>Complete the guided exercise and inspect the applied policy.</p>',
            'new.js': 'const status = "complete";',
        }), [])

    @classmethod
    def setUpClass(cls) -> None:
        course = dict(audit.locale_course_roots(audit.ROOT))['en']
        profile = json.loads((course / 'lesson-map.json').read_text(encoding='utf-8'))
        def lesson(module, number):
            matches = [entry for entry in profile['lessons']
                       if entry['module'] == module and entry['lesson'] == number]
            assert len(matches) == 1, 'one declared lesson for each exercised role'
            return course / (matches[0]['id'] + '.html')
        cls.cron_html = lesson(3, 3).read_text(encoding='utf-8')
        sources = [source for _, source in audit.displayed_code_sources('lesson.html', cls.cron_html)
                   if 'cron.add' in source]
        assert len(sources) == 1, 'one actual scheduling cell'
        cls.cron = sources[0]
        cls.openclaw = (course / 'scripts/_openclaw.js').read_text(encoding='utf-8')
        cls.canvas = (course / 'scripts/_canvas.js').read_text(encoding='utf-8')
        cls.deep = lesson(2, 3).read_text(encoding='utf-8')
        cls.cli_html = lesson(4, 2).read_text(encoding='utf-8')

    def mutate(self, source: str, old: str, new: str) -> str:
        self.assertIn(old, source, 'mutation target must exist')
        changed = source.replace(old, new, 1)
        self.assertNotEqual(changed, source, 'mutation must change bytes')
        return changed

    def test_actual_one_shot_contract_is_a_clean_focused_baseline(self) -> None:
        self.assertEqual(audit.audit_owned_cron(self.cron, 'fixture'), [])

    def test_old_cron_failure_classes_still_fail_with_new_owned_workflow(self) -> None:
        self.assertEqual(audit.audit_owned_cron(self.cron, 'fixture'), [])
        cases = [
            ('schedule:{kind:"at", at:new Date(Date.now() + 15000).toISOString()}', 'schedule:"* * * * *"', 'cron-schema'),
            ('payload:{kind:"agentTurn", message:', 'prompt:"legacy", payload:{kind:"agentTurn", message:', 'cron-schema'),
            ('payload:{kind:"agentTurn", message:', 'payload:{kind:"wrong", message:', 'cron-schema'),
            ('deleteAfterRun:true', 'deleteAfterRun:false', 'cron-schema'),
            ('state.demoCronId = added.id', 'state.demoCronId = name', 'cron-owner'),
            ('"cron.remove", {id:state.demoCronId}', '"cron.remove", {id:job.id}', 'cron-owner'),
            ('job.id === state.demoCronId', 'job.name === name', 'cron-cleanup'),
            ('while (Date.now() < deadline)', 'while (true)', 'cron-poll'),
            ('await helpers.delay(5000, helpers.signal)', 'await helpers.delay(70000)', 'cron-poll'),
            ('delete state._ws;', '', 'cron-cleanup'),
            ('observed.trim() !== state.cronReference', 'false', 'cron-readback'),
        ]
        for old, new, expected in cases:
            with self.subTest(expected=expected, old=old):
                changed = self.mutate(self.cron, old, new)
                self.assertTrue(any(expected in finding for finding in audit.audit_owned_cron(changed, 'novel/path.html')))

    def test_payload_parser_tolerates_formatting_quoting_and_local_variable_rename(self) -> None:
        changed = self.cron.replace('added', 'created').replace('"cron.add"', "'cron.add'")
        changed = changed.replace('schedule:{', 'schedule : {\n').replace('kind:"at"', "kind : 'at'")
        self.assertNotEqual(changed, self.cron)
        self.assertEqual(audit.audit_owned_cron(changed, 'renamed.html'), [])

    def test_comment_and_duplicate_field_near_matches_cannot_supply_schema(self) -> None:
        for old, new in [
            ('kind:"at"', '/* kind:"at" */ kind:"unknown"'),
            ('deleteAfterRun:true', 'deleteAfterRun:true, deleteAfterRun:false'),
            ('schedule:{kind:', 'schedule:broken({kind:'),
        ]:
            changed = self.mutate(self.cron, old, new)
            self.assertTrue(any('cron-schema' in item for item in audit.audit_owned_cron(changed, 'malformed.js')))

    def test_turn_connection_check_belongs_to_shared_owner(self) -> None:
        consumer = {'novel.html':'mountRunCell("#x", {code: `await courseTurn(state, helpers, "new", "question");`});'}
        self.assertEqual(audit.audit_exercise_consumers(consumer, self.openclaw, self.canvas), [])
        changed = self.mutate(self.openclaw, 'if (typeof state.call !== "function")', 'if (false)')
        self.assertTrue(any('turn-prerequisite' in item for item in audit.audit_exercise_consumers(consumer, changed, self.canvas)))
        changed_consumer = {'novel.html':self.mutate(consumer['novel.html'], 'state, helpers,', 'state, {},')}
        self.assertTrue(any('turn-prerequisite' in item for item in audit.audit_exercise_consumers(changed_consumer, self.openclaw, self.canvas)))

    def test_actual_canvas_log_not_an_unrelated_live_region_owns_poll_announcements(self) -> None:
        self.assertEqual(audit.audit_exercise_consumers({'renamed.html':self.cron_html}, self.openclaw, self.canvas), [])
        changed = self.mutate(self.canvas, 'class="cf-panel-log cell-log" role="log" aria-live="polite"', 'class="cf-panel-log cell-log"')
        self.assertIn('aria-live="polite"', changed, 'unrelated live regions remain as a negative control')
        self.assertTrue(any('cron-progress' in item for item in audit.audit_exercise_consumers({'renamed.html':self.cron_html}, self.openclaw, changed)))

    def test_unextractable_or_misspelled_consumer_is_an_error(self) -> None:
        malformed = self.mutate(self.cron_html, '"cron.add"', '"cron.ad"')
        self.assertTrue(any('cron-discovery' in item for item in audit.audit_exercise_consumers({'nested/new.html':malformed}, self.openclaw, self.canvas)))
        hidden = {'nested/new.html':'<script>const schedule = "cron.add"; mountRunCell("#x", {code: missing});</script>'}
        self.assertTrue(any('discovery' in item for item in audit.audit_exercise_consumers(hidden, self.openclaw, self.canvas)))
        prose = {'lesson.html':'<p><code>cron.add</code> schedules work without a new message.</p>'}
        self.assertEqual(audit.audit_exercise_consumers(prose, self.openclaw, self.canvas), [])

    def test_timing_keeps_measured_values_without_fabricating_serial_execution(self) -> None:
        self.assertFalse(any('deep-timing' in item for item in audit.audit_deep_research_artifact(self.deep)))
        for old, new in [('summed concurrent durations', 'serial baseline'),
                         ('performance.now() - t0', '0'),
                         ('sum + r.dt', 'sum')]:
            changed = self.mutate(self.deep, old, new)
            self.assertTrue(any('deep-timing' in item for item in audit.audit_deep_research_artifact(changed)))

    def inventory_fixture(self, root: Path) -> Path:
        course = dict(audit.locale_course_roots(root))['en']
        course.mkdir(parents=True)
        (course / 'scripts').mkdir()
        (course / 'scripts/_shared.js').write_text('// shared owner', encoding='utf-8')
        lessons = [{'id':f'lesson-{module}-{lesson}', 'module':module, 'lesson':lesson}
                   for module, lesson in [(1,1),(1,2),(1,3),(2,3),(3,1),(3,2),(3,3),(4,1),(4,2)]]
        (course / 'lesson-map.json').write_text(json.dumps({'lessons':lessons}), encoding='utf-8')
        for item in lessons:
            (course / (item['id'] + '.html')).write_text('<h1>Lesson</h1>', encoding='utf-8')
        return course

    def inventory(self, root: Path):
        with patch('translate.locale_pages.published_pages', return_value={}):
            return audit.load_runtime_pages(root)

    def test_real_tree_novel_nested_and_renamed_consumers_remain_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = self.inventory_fixture(root)
            self.assertEqual(self.inventory(root).findings, [])
            nested = course / 'nested/new-work.html'
            nested.parent.mkdir()
            nested.write_text(self.cron_html, encoding='utf-8')
            pages = self.inventory(root)
            name = nested.relative_to(root).as_posix()
            self.assertIn(name, pages.surfaces)
            self.assertTrue(any('absent from course/lesson metadata' in item for item in pages.findings))
            broken = self.mutate(self.cron_html, 'deleteAfterRun:true', 'deleteAfterRun:false')
            nested.write_text(broken, encoding='utf-8')
            renamed = nested.with_name('entirely-renamed.html')
            nested.rename(renamed)
            pages = self.inventory(root)
            self.assertIn(renamed.relative_to(root).as_posix(), pages.surfaces)
            self.assertTrue(any('cron-schema' in item for item in audit.audit_exercise_consumers(pages.surfaces, self.openclaw, self.canvas)))
            self.assertIn(renamed, audit.learner_surface_files(root))

    def test_real_delete_rename_and_missing_declaration_cannot_silently_drop_role(self) -> None:
        for mode in ['delete','rename','remove-declaration','valid-rename']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                course = self.inventory_fixture(root)
                profile = course / 'lesson-map.json'
                data = json.loads(profile.read_text(encoding='utf-8'))
                target = course / 'lesson-3-3.html'
                if mode == 'delete': target.unlink()
                elif mode in ['rename','valid-rename']: target.rename(course / 'scheduled-work.html')
                else: data['lessons'] = [item for item in data['lessons'] if item['id'] != 'lesson-3-3']
                if mode == 'valid-rename':
                    for item in data['lessons']:
                        if item['id'] == 'lesson-3-3': item['id'] = 'scheduled-work'
                profile.write_text(json.dumps(data), encoding='utf-8')
                pages = self.inventory(root)
                if mode == 'valid-rename':
                    self.assertEqual(pages.findings, [])
                    self.assertEqual(pages['en-03c'],'<h1>Lesson</h1>')
                else:
                    self.assertTrue(any('missing' in item for item in pages.findings))
                    self.assertIn('en-03c',pages, 'missing role stays visible to downstream contracts')

    def test_module4b_terminal_contract_uses_discovered_metadata_path(self) -> None:
        for mode in ['novel-nested', 'renamed', 'deleted', 'malformed', 'stale-ready']:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                course = self.inventory_fixture(root)
                profile = course / 'lesson-map.json'
                data = json.loads(profile.read_text(encoding='utf-8'))
                original = course / 'lesson-4-2.html'
                original.write_text(self.cli_html, encoding='utf-8')
                target = original
                if mode in ['novel-nested', 'renamed']:
                    target = course / ('novel/nested/operator.html' if mode == 'novel-nested' else 'renamed/operator.html')
                    target.parent.mkdir(parents=True)
                    original.rename(target)
                    for item in data['lessons']:
                        if item['id'] == 'lesson-4-2': item['id'] = target.relative_to(course).with_suffix('').as_posix()
                elif mode == 'deleted':
                    original.unlink()
                elif mode == 'malformed':
                    original.write_text(self.mutate(self.cli_html, 'result?.completion === "exit"', 'result?.completion === "done"'), encoding='utf-8')
                else:
                    original.write_text(self.mutate(self.cli_html, 'return { status: "error", message:', 'return con.write('), encoding='utf-8')
                profile.write_text(json.dumps(data), encoding='utf-8')
                pages = self.inventory(root)
                if mode in ['novel-nested', 'renamed']:
                    self.assertEqual(pages.findings, [])
                    self.assertEqual(audit.audit_module4b_terminal(pages['en-04b'], mode), [])
                elif mode == 'deleted':
                    self.assertTrue(any('declared consumer is missing' in item for item in pages.findings))
                    self.assertTrue(audit.audit_module4b_terminal(pages['en-04b'], mode))
                else:
                    expected = 'explicit zero exit completion' if mode == 'malformed' else 'preserve an error state'
                    self.assertTrue(any(expected in item for item in audit.audit_module4b_terminal(pages['en-04b'], mode)))

    def test_malformed_profile_and_unknown_locale_fail_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = self.inventory_fixture(root)
            (course / 'lesson-map.json').write_text('{broken', encoding='utf-8')
            self.assertTrue(any('invalid lesson metadata' in item for item in self.inventory(root).findings))
            (root / 'i18n/unrecognized').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'missing locale metadata'):
                self.inventory(root)

    def test_nested_script_consumer_is_discovered_without_filename_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = self.inventory_fixture(root)
            script = course / 'scripts/nested/novel.js'
            script.parent.mkdir()
            script.write_text(self.mutate(self.cron, 'deleteAfterRun:true', 'deleteAfterRun:false'), encoding='utf-8')
            pages = self.inventory(root)
            self.assertIn(script.relative_to(root).as_posix(), pages.surfaces)
            self.assertTrue(any('cron-schema' in item for item in audit.audit_exercise_consumers(pages.surfaces, self.openclaw, self.canvas)))

    def test_integration_reads_cli_and_canvas_from_supplied_owner_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = dict(audit.locale_course_roots(root))['en'] / 'scripts'
            scripts.mkdir(parents=True)
            (scripts / '_openclaw_cli.js').write_text('// no error result', encoding='utf-8')
            (scripts / '_canvas.js').write_text('', encoding='utf-8')
            findings = audit.audit_runtime_integrations('', '', '', {}, root=root)
            self.assertTrue(any('shared OpenClaw CLI failures' in item for item in findings))


if __name__ == '__main__':
    unittest.main()
