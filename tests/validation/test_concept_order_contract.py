# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import unittest

from scripts.validation import concept_order_audit


class ConceptOrderContractTests(unittest.TestCase):
    def test_runtime_profile_is_linked_for_standalone_projection(self) -> None:
        skill = (concept_order_audit.COURSE / "SKILL.html").read_text(encoding="utf-8")
        self.assertIn('href="lesson-map.json"', skill)

    def profile(self) -> dict[str, object]:
        return json.loads(concept_order_audit.LESSON_MAP.read_text(encoding="utf-8"))

    def test_research_artifact_order_does_not_depend_on_heading_punctuation(self) -> None:
        source = concept_order_audit.read("02c-deep.html")
        changed_heading = source.replace(
            "Try it · plan, investigate, and synthesize",
            "Try the complete research workflow",
        )
        findings = concept_order_audit.audit({"02c-deep.html": changed_heading})
        self.assertFalse(any("runnable research artifact" in item for item in findings))

    def test_research_artifact_after_implementation_is_rejected(self) -> None:
        source = concept_order_audit.read("02c-deep.html")
        marker = '<div id="deep-cell"></div>'
        moved = source.replace(marker, "", 1).replace(
            "<h2>Inspect the implementation</h2>",
            "<h2>Inspect the implementation</h2>\n" + marker,
            1,
        )
        findings = concept_order_audit.audit({"02c-deep.html": moved})
        self.assertTrue(any("concept appears after first use: runnable research artifact" in item
                            for item in findings))

    def test_new_lesson_is_discovered_without_an_allowlist(self) -> None:
        pages = concept_order_audit._lesson_pages()
        findings = concept_order_audit.audit(discovered_pages=pages | {"04d-novel"})
        self.assertIn(
            "lesson-map.json: discovered lesson 04d-novel.html is not mapped",
            findings,
        )

    def test_deleted_or_renamed_lesson_mapping_is_rejected(self) -> None:
        pages = concept_order_audit._lesson_pages() - {"02b-rag"}
        findings = concept_order_audit.audit(discovered_pages=pages)
        self.assertIn(
            "lesson-map.json: mapped lesson 02b-rag.html does not exist",
            findings,
        )

    def test_unknown_objective_is_rejected(self) -> None:
        profile = self.profile()
        profile["lessons"][0]["objective"] = "learning-objective-99"
        findings = concept_order_audit.audit(profile_override=profile)
        self.assertTrue(any("maps unknown objective" in item for item in findings))

    def test_duplicate_lesson_id_is_rejected(self) -> None:
        profile = self.profile()
        profile["lessons"][1]["id"] = profile["lessons"][0]["id"]
        findings = concept_order_audit.audit(profile_override=profile)
        self.assertTrue(any("duplicate lesson id" in item for item in findings))

    def test_synthetic_checkpoint_fields_are_rejected(self) -> None:
        profile = self.profile()
        profile["lessons"][0]["action"] = {"en": "Prompt"}
        profile["lessons"][0]["recap"] = {"en": "Claim"}
        profile["lessons"][0]["transition"] = {"en": "Next"}
        profile["lessons"][0]["interaction"] = "cell"
        profile["lessons"][0]["evidence"] = "A self-reported success criterion."
        profile["lessons"][0]["evidence_target"] = "#cell-reflex"
        findings = concept_order_audit.audit(profile_override=profile)
        self.assertTrue(any(
            "retired synthetic-checkpoint fields: action, evidence, evidence_target, interaction, recap, transition"
            in item
                            for item in findings))

    def test_modes_and_copied_trees_are_rejected(self) -> None:
        for field in ("profiles", "source_root", "content_root", "copied_tree", "lesson_tree"):
            with self.subTest(field=field):
                profile = self.profile()
                profile[field] = {"alternate": {"query": "mode=alternate"}}
                findings = concept_order_audit.audit(profile_override=profile)
                self.assertTrue(any("mode profiles and copied lesson trees are retired" in item for item in findings))

    def test_required_concept_spine_cannot_move_into_optional_copy(self) -> None:
        cases = {
            "01c-tools.html": 'data-learning-spine="tool-boundaries"',
            "02a-routing.html": 'data-learning-spine="support-loop-workflow"',
            "02b-rag.html": 'data-learning-spine="retrieval-ladder"',
        }
        for page, marker in cases.items():
            with self.subTest(page=page):
                source = concept_order_audit.read(page)
                findings = concept_order_audit.audit({page: source.replace(marker, "", 1)})
                self.assertTrue(any("missing required concept framing" in item for item in findings))


if __name__ == "__main__":
    unittest.main()

class VisibleConceptBridgeTests(unittest.TestCase):
    def test_current_visible_bridges_and_paraphrases(self):
        cases = [
            ('workflow-scope', 'Index workflow.', '<p>The outer workflow controls scope and data flow.</p><p>Index workflow.</p>'),
            ('persistent-authority', 'Product roles', '<p>In the previous module, files supplied context and scheduled jobs did work. Those operations rely on process authority.</p><h2>Product roles</h2>'),
        ]
        for kind, after, source in cases:
            with self.subTest(kind=kind):
                self.assertTrue(concept_order_audit.semantic_order(source, kind, after))
                for changed in [source.replace('<p>', '<p hidden>', 1),
                                '<script>' + source + '</script>',
                                source.replace('controls scope', 'does not control scope').replace('rely on', 'never rely on'),
                                source.replace('data flow', 'flowchart').replace('authority', 'popularity'),
                                '<h2>' + after + '</h2>' + source]:
                    self.assertNotEqual(source, changed)
                    self.assertFalse(concept_order_audit.semantic_order(changed, kind, after))

    def test_real_tree_discovery_rename_deletion_and_malformed_metadata(self):
        import tempfile
        import shutil
        from pathlib import Path
        from unittest.mock import patch
        original = concept_order_audit.COURSE
        with tempfile.TemporaryDirectory() as folder:
            course = Path(folder)
            for item in original.glob('*.html'):
                shutil.copy(item, course / item.name)
            for name in ['lesson-map.json', 'course_contract.json']:
                shutil.copy(original / name, course / name)
            with patch.object(concept_order_audit, 'COURSE', course), \
                 patch.object(concept_order_audit, 'LESSON_MAP', course / 'lesson-map.json'), \
                 patch.object(concept_order_audit, 'COURSE_CONTRACT', course / 'course_contract.json'):
                self.assertEqual(concept_order_audit.audit(), [])
                profile = json.loads((course / 'lesson-map.json').read_text())
                source = course / '02c-deep.html'
                novel = course / 'nested' / 'research.html'
                novel.parent.mkdir()
                shutil.copy(source, novel)
                self.assertTrue(any('discovered lesson nested/research.html is not mapped' in x for x in concept_order_audit.audit()))
                novel.unlink()
                source.rename(novel)
                findings = concept_order_audit.audit()
                self.assertTrue(any('mapped lesson 02c-deep.html does not exist' in x for x in findings))
                self.assertTrue(any('required concept source is missing' in x for x in findings))
                for lesson in profile['lessons']:
                    if lesson['id'] == '02c-deep':
                        lesson['id'] = 'nested/research'
                (course / 'lesson-map.json').write_text(json.dumps(profile))
                self.assertEqual(concept_order_audit.audit(), [])
                source_text = novel.read_text()
                changed = source_text.replace('owns scope and data flow', 'contains a flowchart')
                self.assertNotEqual(source_text, changed)
                novel.write_text(changed)
                self.assertTrue(any('missing or misplaced visible concept bridge' in x for x in concept_order_audit.audit()))
                novel.unlink()
                self.assertTrue(any('mapped lesson nested/research.html does not exist' in x for x in concept_order_audit.audit()))
