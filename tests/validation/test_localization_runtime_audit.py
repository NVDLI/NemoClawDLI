# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import os
import subprocess
import sys
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
        (self.course / "lesson-map.json").write_text(
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

    def test_compound_metadata_deletion_cannot_hide_a_delivered_course(self):
        row = {"code": "ja", "locale": "ja-JP", "url": "preview/ja/nemoclaw/"}
        self.add_locale(row)
        course = self.site / row["url"]
        (course / "assets/locale.json").unlink()
        self.languages.pop()
        self.write_manifest()
        for name in ("lesson-map.json", "interface-inventory.json"):
            with self.subTest(name=name):
                marker = course / name
                marker.write_text('{"schema":"novel or malformed consumer"}')
                with self.assertRaisesRegex(ValueError, "missing from languages.json"):
                    discover_artifact_locales(self.site)
                marker.unlink()
        (course / "scripts").mkdir()
        (course / "scripts/_shared.js").write_text("// native runtime")
        page = course / "novel-lesson.html"
        page.write_text('<main data-learning-id="novel"><h1>Lesson</h1></main>')
        with self.assertRaisesRegex(ValueError, "missing from languages.json"):
            discover_artifact_locales(self.site)
        page.rename(course / "renamed-lesson.html")
        renamed = course.with_name("renamed-course")
        course.rename(renamed)
        with self.assertRaisesRegex(ValueError, "renamed-course"):
            discover_artifact_locales(self.site)

    def test_novel_undeclared_profile_is_discovered_without_locale_metadata(self):
        course = self.site / "novel/nemoclaw"
        course.mkdir(parents=True)
        (course / "lesson-map.json").write_text('{')
        with self.assertRaisesRegex(ValueError, "novel/nemoclaw"):
            discover_artifact_locales(self.site)

    def test_source_mirror_requires_independent_directory_and_manifest_provenance(self):
        from scripts.build.project_artifact_manifests import project_artifact_manifests
        (self.site / "branches.json").write_text('{"branches":[]}')
        (self.site / "LICENSE").write_text("fixture")
        course = self.site / "novel/authoring/web/nemoclaw"
        course.mkdir(parents=True)
        (course / "lesson-map.json").write_text('{"schema":"nemoclaw-lesson-map/1"}')
        metadata = {"schema":"dir-skill/1.0", "node_type":"directory-explorer",
                    "source_dir":"novel/authoring/web/nemoclaw/"}
        skill = course / "SKILL.html"
        def write_metadata(value):
            skill.write_text('<script type="application/json" id="skill-meta">' + json.dumps(value) + '</script>')
        write_metadata(metadata)
        project_artifact_manifests(self.site, self.site)
        self.assertEqual(discover_artifact_locales(self.site), self.languages)
        original_metadata = skill.read_text()
        for malformed in (
            original_metadata + original_metadata,
            original_metadata.replace('id="skill-meta"', 'id="other" ID="skill-meta"'),
            '<!-- ' + original_metadata + ' -->',
            original_metadata.replace("<script ", "<scripture ").replace("</script>", "</scripture>"),
            original_metadata.replace("</script>", ""),
        ):
            with self.subTest(metadata=malformed):
                skill.write_text(malformed)
                with self.assertRaises(ValueError):
                    discover_artifact_locales(self.site)
        skill.write_text(original_metadata)
        for mutate in (lambda value: value.update(source_dir="renamed/web/nemoclaw/"),
                       lambda value: value.update(node_type="directory-explorer-near-match"),
                       lambda value: value.update(schema="dir-skill/1.0-broken")):
            value = dict(metadata)
            mutate(value)
            write_metadata(value)
            with self.assertRaisesRegex(ValueError, "directory provenance"):
                discover_artifact_locales(self.site)
        write_metadata([])
        with self.assertRaisesRegex(ValueError, "malformed directory provenance"):
            discover_artifact_locales(self.site)
        skill.unlink()
        with self.assertRaisesRegex(ValueError, "directory provenance"):
            discover_artifact_locales(self.site)
        hub = {"node_type":"hub", "level":"course", "surface":"web", "course":"nemoclaw",
               "self_path":"web/nemoclaw/SKILL.html"}
        write_metadata(hub)
        self.assertEqual(discover_artifact_locales(self.site), self.languages)
        for change in ({"level":"course-near-match"}, {"surface":"renamed-web"},
                       {"self_path":"../web/nemoclaw/SKILL.html"}, {"course":"other-course"}):
            write_metadata({**hub, **change})
            with self.assertRaisesRegex(ValueError, "directory provenance"):
                discover_artifact_locales(self.site)
        write_metadata(metadata)
        projected = course.parent / "languages.json"
        original = projected.read_text()
        value = json.loads(original)
        value["languages"][0]["url"] = "../wrong-course/"
        projected.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "language provenance differs"):
            discover_artifact_locales(self.site)
        projected.write_text(original)
        self.assertEqual(discover_artifact_locales(self.site), self.languages)
        projected.unlink()
        with self.assertRaisesRegex(ValueError, "missing language provenance"):
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
    def test_policy_transport_fixture_preserves_generated_stream_boundaries(self):
        fixture = "class FakeWebSocket {" + RUNTIME_JS.split("class FakeWebSocket {", 1)[1].split(
            "window.WebSocket = FakeWebSocket;", 1)[0]
        checks = r"""
const assert = require('assert/strict');
const queue = [], frames = [], window = {__policyCommands:[]};
const transcript = '---\nversion: 1\n';
const Socket = new Function('window', 'setTimeout', 'transcript',
  FIXTURE + '\nreturn FakeWebSocket;')(window, callback => queue.push(callback), transcript);
const command = 'openshell policy get policy-audit-agent --full';
for (const seed of ['novel9', 'renamed17']) {
  const stdout = '__DLI_OPENSHELL_POLICY_STDOUT_END_' + seed + '__';
  const stderr = '__DLI_OPENSHELL_POLICY_STDERR_END_' + seed + '__';
  const wrapped = 'sh -c ' + command + '; printf ' + stdout + '; printf ' + stderr;
  const url = value => 'wss://fixture.invalid/ws/terminal?cmd=' + encodeURIComponent(value);
  const socket = new Socket(url(wrapped));
  frames.length = 0;
  socket.onmessage = frame => frames.push(JSON.parse(frame.data));
  while (queue.length) queue.shift()();
  assert.equal(frames[0].data, transcript + '\n' + stdout +
    '\nConnection to 172.18.0.1 closed.\n' + stderr + '\n');
  assert.deepEqual(frames[1], {type:'exit', code:0});
  for (const invalid of [command, wrapped.replace(stdout, ''), wrapped.replace(stderr, ''),
    wrapped.replace('STDOUT_END', 'RENAMED_END'), wrapped.replace(seed + '__', '?__'),
    wrapped.replace('policy-audit-agent', 'unrelated-agent')]) {
    assert.throws(() => new Socket(url(invalid)), /unframed transport command/);
  }
}
assert.deepEqual(window.__policyCommands, [command, command]);
"""
        result = subprocess.run(["node", "-e", "const FIXTURE = " + json.dumps(fixture) + ";\n" + checks],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_artifact_discovery_needs_no_site_packages(self):
        result = subprocess.run(
            [sys.executable, "-S", "-m", "unittest",
             "tests.validation.test_localization_runtime_audit.RuntimeArtifactLocaleTests"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_owned_cron_evidence_rejects_partial_or_foreign_cleanup(self):
        prefix = RUNTIME_JS.split("(async () => {", 1)[0]
        checks = r"""
const assert = require('assert/strict');
const good = {calls:[{method:'cron.add',params:{}},{method:'cron.remove',params:{id:'owned-cron-id'}}],
  historyReads:2,reads:['new-file'],delays:[5000],ownedJob:null,foreign:{id:'foreign-job'},
  stateId:null,retained:null,socketsClosed:true,clearedAfterRun:true};
assert.equal(checkCronLifecycle(good),good);
for (const change of [value=>value.calls.pop(),value=>value.calls[1].params.id='foreign-job',
  value=>value.calls.push({method:'chat.send'}),value=>value.historyReads=1,value=>value.reads=[],
  value=>value.delays=[0],value=>value.ownedJob={id:'owned-cron-id'},value=>value.foreign=null,
  value=>value.stateId='owned-cron-id',value=>value.retained='retained-job',value=>value.socketsClosed=false,
  value=>value.clearedAfterRun=false]) {
  const value=structuredClone(good);change(value);assert.throws(()=>checkCronLifecycle(value));
}
"""
        result = subprocess.run(["node", "-e", prefix + checks], capture_output=True, text=True,
                                env={**os.environ, "NODE_PATH": resolve_node_path(),
                                     "ARTIFACT_LOCALES": '[{"code":"en","url":"nemoclaw/"}]'},
                                check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_research_fixture_obeys_delivered_planner_schema(self):
        prefix = RUNTIME_JS.split("(async () => {", 1)[0]
        checks = r"""
const assert = require('assert/strict');
const request = {response_format:{json_schema:{name:'research_plan',schema:{properties:{branches:{
  minItems:3,maxItems:4,items:{properties:{target:{enum:['overview','AI Agents','Retrieval-Augmented Generation (RAG)']}}},
}}}}}};
assert.equal(researchPlan(request).length,3);
const changed = mutate => { const value = structuredClone(request); mutate(value); assert.throws(()=>researchPlan(value)); };
changed(value=>value.response_format.json_schema.schema.properties.branches.minItems=4);
changed(value=>value.response_format.json_schema.schema.properties.branches.maxItems=2);
changed(value=>value.response_format.json_schema.schema.properties.branches.items.properties.target.enum.pop());
changed(value=>value.response_format.json_schema.schema.properties.branches.items.properties.target.enum[0]='renamed-overview');
changed(value=>delete value.response_format.json_schema.schema.properties.branches);
changed(value=>value.response_format.json_schema.name='research_plan_near_match');
changed(value=>value.response_format.json_schema.schema.properties.branches.minItems='3');
changed(value=>delete value.response_format);
changed(value=>value.response_format.json_schema.schema.properties.branches.items.properties.target.enum='overview');
request.response_format.json_schema.schema.properties.branches.items.properties.target.enum.push('novel-section');
assert.equal(researchPlan(request).length,3);
request.response_format.json_schema.schema.properties.branches.minItems=2;
request.response_format.json_schema.schema.properties.branches.maxItems=5;
assert.equal(researchPlan(request).length,3);
"""
        result = subprocess.run(["node", "-e", prefix + checks], capture_output=True, text=True,
                                env={**os.environ, "NODE_PATH": resolve_node_path(),
                                     "ARTIFACT_LOCALES": '[{"code":"en","url":"nemoclaw/"}]'},
                                check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_maze_budget_and_rejected_moves_follow_delivered_grid(self):
        prefix = RUNTIME_JS.split("(async () => {", 1)[0]
        checks = r"""
const assert = require('assert/strict');
function observation(map) {
  const budget = 2 * [...map].filter(cell => cell !== '#' && cell !== '\n').length;
  const request = {
    messages:[{role:'user',content:'Maze:\n'+map+'\nPath travelled (move into each cell): (1,1)'}],
    tools:[{function:{parameters:{properties:{direction:{enum:['S','E']}}}}}],
  };
  return {requests:Array.from({length:budget},()=>structuredClone(request)),
    choices:Array(budget).fill('N'),initialGrid:'visible position and path',finalGrid:'visible position and path',
    raw:'',log:'No move was executed. Choose exactly one of: S, E.',
    text:'The maze stopped after '+budget+' decisions without reaching the goal.'};
}
const maps = ['#####\n#@.G#\n#####', '#######\n#@....#\n#...G.#\n#######'];
for (const map of maps) {
  const good = observation(map);
  assert.equal(checkMazeBoundary(good).expectedBudget,good.requests.length);
  const changed = mutate => { const value = structuredClone(good); mutate(value); assert.throws(()=>checkMazeBoundary(value)); };
  // Exact finite bound: even a plausible matching error cannot excuse early/late termination.
  for (const delta of [-1,1]) changed(value => {
    if (delta < 0) { value.requests.pop(); value.choices.pop(); }
    else { value.requests.push(structuredClone(value.requests[0])); value.choices.push('N'); }
    value.text = 'The maze stopped after '+value.requests.length+' decisions without reaching the goal.';
  });
  changed(value => value.requests[1].messages[0].content = value.requests[1].messages[0].content.replace('@.','.@'));
  changed(value => value.requests[1].messages[0].content += '\nPath travelled (move into each cell): (2,1)');
  changed(value => value.requests[1].messages[0].content = value.requests[1].messages[0].content.replace('(1,1)','(2,1)'));
  changed(value => value.finalGrid = 'moved after the last rejected request');
  changed(value => value.initialGrid = '');
  changed(value => value.choices[0] = 'S');
  changed(value => value.log = '');
  changed(value => value.text = 'gave up');
  changed(value => value.text += ' goal reached by recovery');
  changed(value => value.raw = '{"won":true}');
  changed(value => value.requests[0].messages[0].content = 'map deleted');
  changed(value => value.requests[0].messages[0].content = value.requests[0].messages[0].content.replace('@','?'));
  changed(value => value.requests[0].messages[0].content = value.requests[0].messages[0].content.replace('G','GG'));
  changed(value => value.requests[0].messages[0].content = value.requests[0].messages[0].content.replace('Path travelled','Renamed path'));
  changed(value => value.requests[0].tools[0].function.parameters.properties.direction.enum = ['north']);
}
assert.notEqual(checkMazeBoundary(observation(maps[0])).expectedBudget,
                checkMazeBoundary(observation(maps[1])).expectedBudget);
"""
        result = subprocess.run(["node", "-e", prefix + checks], capture_output=True, text=True,
                                env={**os.environ, "NODE_PATH": resolve_node_path(),
                                     "ARTIFACT_LOCALES": '[{"code":"en","url":"nemoclaw/"}]'},
                                check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
