# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import unittest

from scripts.validation import concept_order_audit


class ConceptOrderContractTests(unittest.TestCase):
    def test_runtime_profile_is_linked_for_standalone_projection(self) -> None:
        skill = (concept_order_audit.COURSE / "SKILL.html").read_text(encoding="utf-8")
        self.assertIn('href="learning-profile.json"', skill)

    def profile(self) -> dict[str, object]:
        return json.loads(concept_order_audit.LEARNING_PROFILE.read_text(encoding="utf-8"))

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
            "learning-profile.json: discovered lesson 04d-novel.html is not mapped",
            findings,
        )

    def test_deleted_or_renamed_lesson_mapping_is_rejected(self) -> None:
        pages = concept_order_audit._lesson_pages() - {"02b-rag"}
        findings = concept_order_audit.audit(discovered_pages=pages)
        self.assertIn(
            "learning-profile.json: mapped lesson 02b-rag.html does not exist",
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

    def test_guided_cannot_define_a_copied_tree(self) -> None:
        profile = self.profile()
        profile["profiles"]["guided"]["copied_tree"] = "web/guided"
        findings = concept_order_audit.audit(profile_override=profile)
        self.assertTrue(any("must not define a copied lesson tree" in item for item in findings))

    def test_query_only_duplicate_profile_is_rejected(self) -> None:
        profile = self.profile()
        profile["profiles"]["compact"] = {"query": "profile=compact", "detail": "guided"}
        findings = concept_order_audit.audit(profile_override=profile)
        self.assertTrue(any("Guided must be the only default profile" in item for item in findings))

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
