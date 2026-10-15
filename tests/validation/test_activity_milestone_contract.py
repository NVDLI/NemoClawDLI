# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Course-home JSON, Markdown and real exercise targets must agree."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from scripts.build import bundle_standalone

from scripts.validation.activity_milestone_contract import audit_course, audit

ROOT = Path(__file__).resolve().parents[2]

class ActivityMilestoneContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.course = self.root / "web" / "novel-course"
        self.course.mkdir(parents=True)
        self.activity = self.course.parent / "activity"
        self.activity.mkdir()
        (self.course / "COURSE_CANON.md").write_text("fixture course")
        (self.root / "docs").mkdir()
        self.document = self.root / "docs/ACTIVITY_MILESTONES.md"
        self.config = {"schemaVersion": 1, "milestones": [
            {"id": "fixture:first", "label": "First exercise", "description": "Complete the first exercise.",
             "href": "lesson.html#exercise", "evidence": [
                 {"event": "fixture:succeeded", "page": "lesson.html", "target": "exercise"}]},
            {"id": "fixture:second", "label": "Follow-up exercise", "description": "Complete the follow-up and cleanup.",
             "href": "followup.html#result", "evidence": [
                 {"event": "fixture:result", "page": "followup.html", "target": "result"},
                 {"event": "fixture:cleanup", "page": "followup.html", "target": "cleanup"}]},
        ]}
        self.write(self.config)
        (self.course / "lesson.html").write_text('<html><body><div id="exercise"></div></body></html>')
        (self.course / "followup.html").write_text('<html><body><div id="result"></div><div id="cleanup"></div></body></html>')
        self.write_source(self.config)

    def write_source(self, config):
        self.document.write_text("# Activity Milestones\n\n```json\n" + json.dumps(config, indent=2) + "\n```\n")

    def write(self, config):
        (self.activity / "activity_milestones.json").write_text(json.dumps(config, indent=2) + "\n")

    def test_current_courses_have_required_home_contracts(self):
        self.assertEqual(audit(ROOT), [])

    def test_novel_course_uses_same_parity_gate(self):
        self.assertEqual(audit_course(self.course), [])

    def test_missing_or_renamed_required_files_fail(self):
        for path in (self.document, self.activity / "activity_milestones.json"):
            filename = path.name
            path.rename(path.with_suffix(".old"))
            self.assertTrue(audit_course(self.course), filename)
            path.with_suffix(".old").rename(path)

    def test_duplicate_ids_and_changed_labels_fail(self):
        mutated = copy.deepcopy(self.config)
        mutated["milestones"].append(mutated["milestones"][0])
        self.write(mutated)
        self.assertTrue(audit_course(self.course))
        mutated = copy.deepcopy(self.config)
        mutated["milestones"][0]["label"] = "A different label"
        self.write(mutated)
        self.assertTrue(audit_course(self.course))

    def test_changed_exercise_and_evidence_targets_fail(self):
        for key in ("href", "target", "page"):
            mutated = copy.deepcopy(self.config)
            if key == "href":
                mutated["milestones"][0][key] = "lesson.html#missing-exercise"
            else:
                mutated["milestones"][0]["evidence"][0][key] = "missing.html" if key == "page" else "missing-exercise"
            self.write(mutated)
            self.assertTrue(audit_course(self.course), key)

    def test_removing_real_html_target_fails(self):
        page = self.course / "lesson.html"
        page.write_text(page.read_text().replace('id="exercise"', 'id="removed-exercise"'))
        self.assertTrue(audit_course(self.course))

    def test_parallel_javascript_definition_source_fails(self):
        (self.course / "scripts").mkdir()
        (self.course / "scripts/_activity_config.js").write_text("export const ACTIVITY_MILESTONES = {};\n")
        self.assertTrue(audit_course(self.course))

    def test_write_generates_projection_and_refuses_invalid_targets(self):
        from scripts.validation.activity_milestone_contract import audit
        projection = self.activity / "activity_milestones.json"
        projection.unlink()
        self.assertEqual(audit(self.root, write=True), [])
        self.assertEqual(json.loads(projection.read_text()), self.config)
        before = projection.read_bytes()
        changed = copy.deepcopy(self.config)
        changed["milestones"][0]["href"] = "../escape.html#exercise"
        self.write_source(changed)
        self.assertTrue(audit(self.root, write=True))
        self.assertEqual(projection.read_bytes(), before)

    def test_missing_duplicate_and_malformed_json_blocks_fail(self):
        for source in ("# Activity Milestones\n", self.document.read_text() * 2,
                       "# Activity Milestones\n```json\n{broken}\n```\n"):
            self.document.write_text(source)
            self.assertTrue(audit_course(self.course))

    def test_source_change_requires_regeneration(self):
        changed = copy.deepcopy(self.config)
        changed["milestones"][0]["label"] = "Updated exercise"
        self.write_source(changed)
        self.assertTrue(audit_course(self.course))
        self.assertEqual(audit(self.root, write=True), [])
        self.assertEqual(audit_course(self.course), [])

    def test_malformed_evidence_refuses_generation(self):
        for evidence in (None, {}, [{"page": "lesson.html", "target": "exercise"}],
                         [{"event": 7, "page": "lesson.html", "target": "exercise"}]):
            changed = copy.deepcopy(self.config)
            changed["milestones"][0]["evidence"] = evidence
            self.write_source(changed)
            self.assertTrue(audit(self.root, write=True))

    def test_sdk_invalid_evidence_never_replaces_projection(self):
        projection = self.activity / "activity_milestones.json"
        before = projection.read_bytes()
        mutations = [
            {"event": "click"}, {"requires": [0]}, {"requires": [True]},
            {"matches": {"unsafe": {"nested": True}}}, {"matches": {"constructor": True}},
            {"matches": {"hasAnswer": []}}, {"minimum": {"count": -1}},
            {"minimum": {"count": True}}, {"minimum": {"count": 1.5}},
            {"unknown": "field"},
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(self.config)
                changed["milestones"][0]["evidence"][0].update(mutation)
                self.write_source(changed)
                self.assertTrue(audit(self.root, write=True))
                self.assertEqual(projection.read_bytes(), before)

    def test_matching_unsafe_source_and_projection_fail(self):
        changed = copy.deepcopy(self.config)
        changed["milestones"][0]["evidence"][0]["page"] = "../escape.html"
        self.write_source(changed)
        self.write(changed)
        self.assertTrue(audit_course(self.course))

    def test_bundler_copies_complete_activity_as_sibling(self):
        from scripts.build.bundle_standalone import _copy_activity_assets
        (self.activity / "activity-sdk.js").write_text("export const fixture = true;")
        nested = self.activity / "nested"
        nested.mkdir()
        (nested / "asset.txt").write_text("preserve all assets")
        renderer = self.course.parent / "_skill_explorer.js"
        renderer.write_text("fixture renderer")
        destination = self.root / "bundle/course"
        destination.mkdir(parents=True)
        _copy_activity_assets(self.course, destination)
        self.assertEqual((destination.parent / "activity/nested/asset.txt").read_text(), "preserve all assets")
        self.assertEqual((destination.parent / "_skill_explorer.js").read_bytes(), renderer.read_bytes())

    def test_link_audit_uses_deployment_boundary_for_scoped_course(self):
        from scripts.validation import artifact_link_audit
        delivered = self.root / "delivery"
        course = delivered / "course"
        course.mkdir(parents=True)
        (delivered / "activity").mkdir()
        (delivered / "activity/config.json").write_text("{}")
        (course / "index.html").write_text('<a href="../activity/config.json">configuration</a>')
        (delivered / "unrelated.html").write_text('<a href="missing.html">unrelated</a>')
        self.assertEqual(artifact_link_audit.audit(delivered, source_roots=[course]), [])
        (course / "index.html").write_text('<a href="../../escape.html">escape</a>')
        self.assertTrue(artifact_link_audit.audit(delivered, source_roots=[course]))
        self.assertTrue(artifact_link_audit.audit(delivered, source_roots=[self.root]))

    def test_bundler_refuses_missing_required_contract_before_assembly(self):
        (self.activity / "activity_milestones.json").unlink()
        with patch("sys.argv", ["bundle_standalone.py", "--src", str(self.course), "--out", str(self.course / "output")]):
            self.assertEqual(bundle_standalone.main(), 1)
        self.assertFalse((self.course / "output").exists())

    def test_novel_inline_javascript_definitions_fail(self):
        (self.course / "scripts").mkdir()
        (self.course / "scripts/renamed_config.js").write_text(
            "export const copied = " + json.dumps([self.config["milestones"][0]]) + ";\n")
        self.assertTrue(audit_course(self.course))

    def test_regenerating_course_hub_retains_lesson_map_metadata_and_links(self):
        from scripts.skills import gen_skill_hierarchy
        root = Path(self.directory.name) / "root"
        web = root / "web"
        web.mkdir(parents=True)
        course = web / "novel"
        shutil.copytree(self.course, course)
        (course / "SKILL.html").write_text("<!-- generated by scripts/gen_skill_hierarchy.py -->")
        (course / "lesson-map.json").write_text('{"schema":"fixture-lesson-map/1"}')
        with patch.object(gen_skill_hierarchy, "TASK1", root):
            gen_skill_hierarchy.gen_web_course_hubs()
        source = (course / "SKILL.html").read_text()
        self.assertIn('"source": "lesson-map.json"', source)
        self.assertIn('href="lesson-map.json"', source)

    def test_activity_beacon_is_infrastructure_not_a_course(self):
        from scripts.skills import gen_skill_hierarchy
        root = Path(self.directory.name) / "graph"
        activity = root / "web/activity"
        activity.mkdir(parents=True)
        (activity / "SKILL.html").write_text("activity")
        with patch.object(gen_skill_hierarchy, "TASK1", root):
            self.assertEqual(gen_skill_hierarchy.courses_in("web"), [])
            gen_skill_hierarchy.gen_surface("web")
        source = (root / "web/SKILL.html").read_text()
        self.assertIn('"path": "web/activity/SKILL.html"', source)
        self.assertIn('href="activity/SKILL.html"', source)
