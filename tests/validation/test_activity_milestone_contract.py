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
        self.course = Path(self.directory.name) / "novel-course"
        self.course.mkdir()
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
        rows = [f"| `{marker['id']}` | [{marker['label']}]({marker['href']}) | {marker['description']} |"
                for marker in self.config["milestones"]]
        (self.course / "ACTIVITY_MILESTONES.md").write_text(
            "# Activity Milestones\n\n| ID | Exercise | Criteria |\n| --- | --- | --- |\n" + "\n".join(rows) + "\n")

    def write(self, config):
        (self.course / "activity_milestones.json").write_text(json.dumps(config))

    def test_current_courses_have_required_home_contracts(self):
        self.assertEqual(audit(ROOT), [])

    def test_novel_course_uses_same_parity_gate(self):
        self.assertEqual(audit_course(self.course), [])

    def test_missing_or_renamed_required_files_fail(self):
        for filename in ("ACTIVITY_MILESTONES.md", "activity_milestones.json"):
            path = self.course / filename
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

    def test_bundler_copies_required_root_files_through_existing_discovery(self):
        (self.course / "SKILL.html").write_text('<a href="ACTIVITY_MILESTONES.md">Activity Milestones</a>')
        destination = Path(self.directory.name) / "bundle"
        destination.mkdir()
        copied = bundle_standalone._copy_linked_course_files(self.course, destination)
        self.assertIn("ACTIVITY_MILESTONES.md", copied)
        self.assertIn("activity_milestones.json", copied)

    def test_bundler_refuses_missing_required_contract_before_assembly(self):
        (self.course / "activity-policy.json").write_text("{}")
        (self.course / "activity_milestones.json").unlink()
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
