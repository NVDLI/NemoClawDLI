# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.validation import prose_variety, validate_bundle


class ProseSurfaceCoverageTests(unittest.TestCase):
    def write(self, root: Path, relative: str, body: str) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def test_component_fields_and_comments_enter_shared_prose(self) -> None:
        with tempfile.TemporaryDirectory(prefix="prose-components-") as temp:
            page = self.write(Path(temp), "lesson.html", '''<!doctype html><html lang="en"><body>
<p>Body prose remains visible to the same analysis.</p>
<button aria-label="Run the selected example">Run</button>
<script type="module">
// This explanatory comment has enough words to be read as authored code documentation.
const node = {
  title: "Inspect " + "the route",
  question: "Which route should the model choose?",
  summary: "There are several reasons this component should receive the full grammar pass.",
  code: `return state;`,
};
</script></body></html>''')
            rows = prose_variety.script_prose(page)
            fields = {row["field"] for row in rows}
            self.assertTrue({"title", "summary", "question", "comment"} <= fields)
            self.assertIn("Inspect the route", [row["text"] for row in rows])
            self.assertEqual(
                [row["text"] for row in prose_variety.html_component_prose(page)
                 if row["field"] == "aria-label"],
                ["Run the selected example"],
            )
            grammar = prose_variety.grammar_hits(prose_variety.authored_prose(page))
            self.assertTrue(any(kind == "expletive" for kind, _ in grammar))
            concatenated = [item for item in prose_variety.interface_prose_findings(page)
                            if item["kind"] == "component-prose-concatenation"]
            self.assertEqual([item["field"] for item in concatenated], ["title"])

    def test_code_documentation_and_figure_captions_do_not_distort_cadence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="prose-cadence-") as temp:
            page = self.write(Path(temp), "lesson.html", '''<!doctype html><html lang="en"><body>
<p>The learner reads this paragraph as continuous narrative copy.</p>
<p>A second paragraph varies the rhythm while preserving the technical point.</p>
<p>Short prose helps.</p>
<p>The fourth paragraph supplies enough material for a stable cadence sample.</p>
<p>This final paragraph closes the sample without repeating the figure caption.</p>
<figure><figcaption>The agent receives observations and returns bounded actions.</figcaption></figure>
<script>
// This long code comment explains a protocol contract; it is reviewed as code documentation.
const node = {summary: "Inspect the route and compare the returned state."};
</script></body></html>''')
            authored = prose_variety.authored_prose(page)
            cadence = prose_variety.cadence_prose(page)
            self.assertTrue(any("protocol contract" in item for item in authored))
            self.assertFalse(any("protocol contract" in item for item in cadence))
            self.assertFalse(any("Inspect the route" in item for item in cadence))
            self.assertFalse(any("bounded actions" in item for item in cadence))
            measured = prose_variety.metrics(
                cadence, prose_variety.graphics(page), prose_variety.graphic_prose(page))
            self.assertIsNotNone(measured)
            self.assertEqual(0, measured["redundancy"])

    def test_skill_list_prose_is_counted_once_without_inline_code(self) -> None:
        with tempfile.TemporaryDirectory(prefix="prose-skill-list-") as temp:
            page = self.write(Path(temp), "SKILL.html", '''<!doctype html><html lang="en"><body>
<ol>
  <li>Inspect the <code>private_route</code> result and record visible evidence for reviewer approval.</li>
  <li>Inspect the <code>other_route</code> result and record visible evidence for reviewer approval.</li>
</ol>
</body></html>''')
            prose = prose_variety.cadence_prose(page)
            self.assertEqual([
                "Inspect the result and record visible evidence for reviewer approval.",
                "Inspect the result and record visible evidence for reviewer approval.",
            ], prose)
            hits = prose_variety.redundancy(prose, [])
            self.assertTrue(any(kind == "sentence-restated" for kind, *_ in hits))
            self.assertNotIn("private_route", " ".join(prose))
            self.assertNotIn("other_route", " ".join(prose))

    def test_inline_commands_do_not_create_echo_aphorisms(self) -> None:
        with tempfile.TemporaryDirectory(prefix="prose-inline-command-") as temp:
            page = self.write(Path(temp), "SKILL.html", '''<!doctype html><html lang="en"><body>
<ol><li><strong>Run source checks:</strong>
<code>python3 scripts/security/audit_projection.py</code> and
<code>node --test scripts/projection/test/*.test.mjs</code>.</li></ol>
</body></html>''')
            hits = prose_variety.antithesis_hits(prose_variety.cadence_prose(page))
            self.assertFalse(any(kind == "echo-aphorism" for kind, _ in hits))

    def test_separate_component_fields_do_not_form_a_choppy_sentence_run(self) -> None:
        separate = prose_variety.grammar_hits([
            "Run the cell.",
            "Reset the cell.",
            "Open the result.",
        ])
        continuous = prose_variety.grammar_hits(
            "Run the cell. Reset the cell. Open the result."
        )
        self.assertFalse(any(kind == "choppy-run" for kind, _ in separate))
        self.assertTrue(any(kind == "choppy-run" for kind, _ in continuous))

    def test_direct_questions_are_not_weak_openers(self) -> None:
        hits = prose_variety.grammar_hits([
            "What is a vector database?",
            "What are the supported routes?",
            "What was returned by the tool?",
            "What were the visible state changes?",
            "What is written here is ambiguous.",
        ])
        weak = [sentence for kind, sentence in hits if kind == "weak-opener"]
        self.assertEqual(["What is written here is ambiguous."], weak)

    def test_component_copy_budget_rejects_a_second_lecture(self) -> None:
        with tempfile.TemporaryDirectory(prefix="prose-budget-") as temp:
            page = self.write(Path(temp), "lesson.html", '''<html lang="en"><script>
const node = {summary: "This summary keeps explaining the implementation after the learner already knows the action. It adds another sentence about internal mechanics, then continues beyond the compact interface budget with material that belongs beside the component."};
</script></html>''')
            findings = prose_variety.interface_prose_findings(page)
            self.assertEqual([item["field"] for item in findings], ["summary"])
            self.assertTrue(all(item["kind"] == "component-prose-too-long" for item in findings))

    def test_tool_description_keeps_three_complete_capability_sentences(self) -> None:
        with tempfile.TemporaryDirectory(prefix="prose-tool-description-") as temp:
            page = self.write(Path(temp), "lesson.html", '''<html><script>
const tool = {description: [
  "Run JavaScript in the live page.",
  "Use the visible browser APIs and course helpers.",
  "Return the value that supports your answer.",
].join(" ")};
</script></html>''')
            findings = prose_variety.interface_prose_findings(page)
            self.assertEqual([], findings)

    def test_titles_cover_script_fields_and_html_headings(self) -> None:
        with tempfile.TemporaryDirectory(prefix="prose-titles-") as temp:
            page = self.write(Path(temp), "lesson.html", '''<html lang="en"><body>
<h2>Plan + tool + response</h2>
<script>const node = {title: "Retrieve → rerank → synth", code: `return state;`};</script>
</body></html>''')
            findings = prose_variety.interface_prose_findings(page)
            title_findings = [item for item in findings if item["kind"] == "title-shorthand"]
            self.assertEqual({item["field"] for item in title_findings}, {"h2", "title"})

    def test_structural_component_copy_mutations_are_illegal(self) -> None:
        mutations = {
            "quoted-key-concatenation": (
                '''<html><script>const node = {"intro": "Set one value. " + "Run the cell."};</script></html>''',
                "component-prose-concatenation",
            ),
            "assigned-concatenation": (
                '''<html><script>node.summary = "Inspect the request. " + "Compare its response.";</script></html>''',
                "component-prose-concatenation",
            ),
            "array-joined-interface-copy": (
                '''<html><script>const node = {intro: ["Read one record.", "Return its fields."].join(" ")};</script></html>''',
                "component-prose-array-assembly",
            ),
            "single-arrow-title": (
                '''<html><body><h3>Request → response</h3></body></html>''',
                "title-shorthand",
            ),
            "pipe-title": (
                '''<html><script>const node = {title: "Plan | execute"};</script></html>''',
                "title-shorthand",
            ),
        }
        with tempfile.TemporaryDirectory(prefix="prose-mutations-") as temp:
            root = Path(temp)
            for name, (source, expected) in mutations.items():
                with self.subTest(name=name):
                    page = self.write(root, f"{name}.html", source)
                    findings = prose_variety.interface_prose_findings(page)
                    self.assertIn(expected, {item["kind"] for item in findings})
                    self.assertTrue(all(validate_bundle._interface_required(item)
                                        for item in findings if item["kind"] == expected))

    def test_model_prose_normalizes_meaning_but_keeps_source_and_runtime_signals(self) -> None:
        complete_units = '''<html><script>const message = {content: [
  "Inspect the live page before answering.",
  "Return one concise result.",
].join(" ")};</script></html>'''
        fragmented_units = '''<html><script>const message = {content: [
  "Inspect the live page before",
  "answering the question.",
].join(" ")};</script></html>'''
        runtime_wrap = '''<html><script>const message = {content: `Inspect the live page before
answering the question.`};</script></html>'''
        semantic_lines = '''<html><script>const message = {content: `Choose one category.
billing = payments and invoices
technical = errors and setup`};</script></html>'''
        mapping_units = '''<html><script>const message = {content: [
  "Choose one category.",
  "billing = payments and invoices",
  "technical = errors and setup",
].join("\\n")};</script></html>'''
        source_wall = ('''<html><script>const message = {content: "''' +
                       "Inspect the live page and report only evidence. " * 6 +
                       '''"};</script></html>''')
        question_wall = '''<html><script>state.question = "Review this production incident and recommend a safe next step after comparing the job identity, schedule, missing row-count guardrail, duplicated data, and recovery evidence.";</script></html>'''
        cases = {
            "complete-units": (complete_units, set()),
            "fragmented-units": (fragmented_units, {"model-prose-fragmented-array"}),
            "runtime-wrap": (runtime_wrap, {"model-prose-runtime-wrap"}),
            "semantic-lines": (semantic_lines, set()),
            "mapping-units": (mapping_units, set()),
            "source-wall": (source_wall, {"model-prose-source-wall"}),
            "question-wall": (question_wall, {"model-prose-source-wall"}),
        }
        with tempfile.TemporaryDirectory(prefix="model-prose-") as temp:
            root = Path(temp)
            for name, (source, expected) in cases.items():
                with self.subTest(name=name):
                    page = self.write(root, f"{name}.html", source)
                    rows = prose_variety.script_prose(page)
                    self.assertTrue(rows)
                    self.assertNotRegex(rows[0]["text"], r"\s{2,}")
                    kinds = {item["kind"] for item in prose_variety.interface_prose_findings(page)}
                    self.assertEqual(expected, kinds)

    def test_interface_contract_is_required_and_language_neutral(self) -> None:
        tiers = {suite_id: tier for suite_id, _, tier, *_ in validate_bundle.SUITE_META}
        self.assertEqual(tiers["interface_prose"], "required")
        self.assertNotIn("interface_prose", validate_bundle._EN_PROSE_SUITES)
        self.assertTrue(validate_bundle._interface_required(
            {"page": "i18n/es/page.html", "kind": "component-prose-concatenation"}))
        self.assertTrue(validate_bundle._interface_required(
            {"page": "web/page.html", "kind": "component-prose-too-long"}))
        self.assertFalse(validate_bundle._interface_required(
            {"page": "i18n/es/page.html", "kind": "component-prose-too-long"}))

    def test_discovery_is_default_on_and_language_aware(self) -> None:
        with tempfile.TemporaryDirectory(prefix="prose-discovery-") as temp:
            root = Path(temp)
            expected = {
                self.write(root, "new-area/guide.md", "A newly introduced guide is monitored automatically."),
                self.write(root, "new-area/page.html", '<html lang="en"><p>New page.</p></html>'),
                self.write(root, "i18n/simple/page.html", '<html lang="en"><p>English adaptation.</p></html>'),
                self.write(root, "i18n/simple/guide.md", "English adaptation guide."),
                self.write(root, "scripts/build/SKILL.html", '<html lang="en"><p>Authored build guide.</p></html>'),
            }
            self.write(root, "i18n/es/page.html", '<html lang="es-ES"><p>Página.</p></html>')
            self.write(root, "web/nemoclaw/mats/source.md", "External source snapshot.")
            self.write(root, "vendor/package/readme.md", "Vendored package.")
            with mock.patch.object(prose_variety, "TASK1", root):
                discovered = {path for path, _ in prose_variety._pages("ship")}
                interfaces = {path for path, _ in prose_variety._interface_pages("ship")}
            self.assertEqual(discovered, expected)
            self.assertIn(root / "i18n/es/page.html", interfaces)


if __name__ == "__main__":
    unittest.main()
