# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Framework-visible coverage for key-based locale resources and the pages they render."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.validation import locale_resource_audit as audit
from scripts.validation import locale_resource_mutations as fixtures
from scripts.validation import localization_audit
from scripts.translate import locale_pages
from scripts.translate.locale_catalog import discover_locales
from scripts.translate.locale_projection import project_locale_html
from scripts.translate.locale_resource_render import extract_resource, render_overlay, render_page
from scripts.translate.locale_resources import (
    code_copy_segments,
    derive_key,
    LocaleResourceError,
    base_key,
    consumer_map,
    expected_resource_path,
    has_english_shell,
    json_resources,
    load_resource,
    template_units,
)
from scripts.translate.code_localization import code_templates, js_shape
from scripts.translate.migrate_locale_resource import build as build_resource
from scripts.translate.migrate_locale_resource import review_provenance
from scripts.translate.translate_html_segments import (
    code_value_ranges,
    extract_segments,
    normalize_zh_spacing,
)

ROOT = Path(__file__).resolve().parents[2]


def tracked_resources():
    for spec in discover_locales(ROOT):
        for path in json_resources(spec.locale_root):
            yield spec, load_resource(path)


class LocaleResourceMutationTests(unittest.TestCase):
    def test_code_key_identity_preserves_semantic_whitespace(self) -> None:
        self.assertEqual(
            derive_key("text", "Agent   loop"),
            derive_key("text", "Agent loop"),
        )
        self.assertNotEqual(
            derive_key("code-double-string", "agent  loop"),
            derive_key("code-double-string", "agent loop"),
        )

    def test_every_mutation_is_detected(self) -> None:
        self.assertEqual(fixtures.run_mutations(), [])

    def test_new_page_and_locale_need_no_validator_edit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-resource-growth-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.add_template_and_resource(root)
            fixtures.add_locale(root)
            self.assertEqual(audit.audit(root), [])

    def test_template_discovery_reads_the_tree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-resource-discovery-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            before = set(audit.discover_templates(root))
            fixtures.add_template_and_resource(root)
            after = set(audit.discover_templates(root))
            self.assertEqual(after - before, {fixtures.SECOND_TEMPLATE})

    def test_deleting_a_reviewed_resource_is_not_silent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-resource-deletion-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.delete_resource(root)
            finding = next(item for item in audit.audit(root)
                           if item["code"] == "resource-missing")
            self.assertIn(f"locale={fixtures.LOCALE}", finding["detail"])
            self.assertIn(fixtures.TEMPLATE, finding["detail"])
            self.assertIn("correction=", finding["detail"])

    def test_template_discovery_does_not_skip_named_directories(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-resource-nested-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.add_formerly_skipped_template(root)
            self.assertIn(fixtures.NESTED_TEMPLATE, audit.discover_templates(root))
            self.assertEqual(audit.audit(root), [])

    def test_derived_key_collision_is_rejected(self) -> None:
        digest = mock.Mock()
        digest.hexdigest.return_value = "0" * 64
        with mock.patch("translate.locale_resources.hashlib.sha256", return_value=digest):
            with self.assertRaisesRegex(LocaleResourceError, "derived key collision"):
                consumer_map({
                    "web/course/first.html": "<html><body><p>First value</p></body></html>",
                    "web/course/second.html": "<html><body><p>Second value</p></body></html>",
                })

    def test_shared_key_diagnostic_names_complete_context(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-resource-diagnostic-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.shared_key_conflict(root)
            finding = next(item for item in audit.audit(root)
                           if item["code"] == "resource-shared-key-unrecorded")
            for token in (
                f"locale={fixtures.LOCALE}",
                "key=",
                "values=",
                "consuming_templates=",
                "correction=",
            ):
                self.assertIn(token, finding["detail"])
            self.assertIn(fixtures.TEMPLATE, finding["detail"])
            self.assertIn(fixtures.SECOND_TEMPLATE, finding["detail"])

    def test_repeated_source_is_addressed_once_per_occurrence(self) -> None:
        units = template_units(fixtures.REPEAT_HTML)
        repeated = [unit for unit in units
                    if unit.source.strip() == "The loop repeats until the budget runs out."]
        self.assertEqual(len(repeated), 2)
        self.assertNotEqual(repeated[0].key, repeated[1].key)
        self.assertEqual(base_key(repeated[1].key), repeated[0].key)
        self.assertEqual(len({unit.key for unit in units}), len(units))

    def test_moving_a_unit_does_not_rename_its_key(self) -> None:
        moved = fixtures.SECOND_HTML.replace(
            "<h1>The second loop</h1>\n<p>The loop repeats until the budget runs out.</p>",
            "<p>The loop repeats until the budget runs out.</p>\n<h1>The second loop</h1>",
        )
        self.assertNotEqual(moved, fixtures.SECOND_HTML)
        self.assertEqual({unit.key for unit in template_units(fixtures.SECOND_HTML)},
                         {unit.key for unit in template_units(moved)})

    def test_script_ui_discovery_has_no_field_name_allowlist(self) -> None:
        raw = """<html><script>
const panel = {
  futureHint: "Visible quoted hint",
  arbitraryHelp: `<p>Visible template help</p>`,
};
status.textContent = "Visible assigned " + "status";
</script></html>"""
        values = [item.text for item in extract_segments(raw) if item.kind == "script-ui"]
        self.assertIn("Visible quoted hint", values)
        self.assertIn("<p>Visible template help</p>", values)
        self.assertIn("Visible assigned ", values)
        self.assertIn("status", values)

    def test_runnable_code_span_hides_nested_strings_from_ui_discovery(self) -> None:
        raw = """<html><script>
const cell = {
  code: makeCell({message: "Executable detail", nested: {hint: "Still executable"}}),
  failureHint: "Visible failure hint",
};
</script></html>"""
        body = raw[raw.index("<script>") + len("<script>"):raw.index("</script>")]
        ranges = code_value_ranges(body)
        self.assertEqual(len(ranges), 1)
        self.assertIn("Executable detail", body[ranges[0][0]:ranges[0][1]])
        values = [item.text for item in extract_segments(raw) if item.kind == "script-ui"]
        self.assertEqual(values, ["Visible failure hint"])

    def test_runnable_copy_discovery_ignores_regex_syntax(self) -> None:
        body = r"""const match = raw.match(/choose\s*\(\s*['"]([^'"]*)['"]\s*\)/);
helpers.log("Visible result");"""
        segments = code_copy_segments(body)
        self.assertEqual(
            [(item.kind, item.text) for item in segments],
            [("code-double-string", "Visible result")],
        )

    def test_javascript_shape_ignores_quotes_inside_regex_literals(self) -> None:
        source = 'const esc = value => value.replace(/[&<>\"]/g, "English copy");'
        target = 'const esc = value => value.replace(/[&<>\"]/g, "中文文案");'
        self.assertEqual(js_shape(source), js_shape(target))

    def test_runnable_ui_scan_ignores_strings_inside_comments(self) -> None:
        raw = '<html><script>const cell = {code: `// log.details("raw response", reply);\nhelpers.log("Visible result");`};</script></html>'
        self.assertEqual(localization_audit.runnable_code_ui_strings(raw), ["Visible result"])

    def test_zh_spacing_removes_only_chinese_inline_boundary_whitespace(self) -> None:
        self.assertEqual(
            normalize_zh_spacing(
                "当前的 \n<a href=\"/guide\">安全指南</a> \n记录了 <code>pairing code</code> 的行为"
            ),
            "当前的<a href=\"/guide\">安全指南</a>记录了 <code>pairing code</code> 的行为",
        )
        self.assertEqual(
            normalize_zh_spacing("<strong>工作流\n智能体</strong>并行运行的\n子任务"),
            "<strong>工作流智能体</strong>并行运行的子任务",
        )

    def test_zh_resource_extraction_restores_english_runnable_comments(self) -> None:
        source = '<html lang="en"><script>const cell = {code: `// Keep this comment\\nrun();`};</script></html>'
        target = source.replace('lang="en"', 'lang="zh-CN"').replace(
            "// Keep this comment", "// 保留这条注释")
        resource = extract_resource(source, target, "zh-CN", "web/course/page.html")
        unit = next(item for item in template_units(source) if item.kind == "code-line-comment")
        self.assertEqual(resource["values"][unit.key]["value"], unit.source)


class TrackedResourceTests(unittest.TestCase):
    def test_repository_resources_pass_the_gate(self) -> None:
        self.assertEqual(audit.audit(ROOT), [])

    def test_resources_supply_every_key_their_template_consumes(self) -> None:
        for _, resource in tracked_resources():
            with self.subTest(resource=resource.path.name):
                template = (ROOT / resource.template).read_text(encoding="utf-8")
                self.assertEqual(
                    sorted({unit.key for unit in template_units(template)}),
                    sorted(resource.values),
                )

    def test_resources_never_duplicate_complete_runnable_bodies(self) -> None:
        for _, resource in tracked_resources():
            template = (ROOT / resource.template).read_text(encoding="utf-8")
            complete_bodies = set(code_templates(template))
            with self.subTest(resource=resource.path.name):
                self.assertNotIn("code", {entry["type"] for entry in resource.values.values()})
                self.assertFalse(
                    complete_bodies
                    & {
                        entry[field]
                        for entry in resource.values.values()
                        for field in ("source", "value")
                    }
                )

    def test_zh_resources_keep_comments_in_english_and_use_chinese_spacing(self) -> None:
        for spec, resource in tracked_resources():
            if not spec.locale.casefold().startswith("zh"):
                continue
            template = (ROOT / resource.template).read_text(encoding="utf-8")
            units = {item.key: item for item in template_units(template)}
            for key, entry in resource.values.items():
                unit = units[key]
                with self.subTest(resource=resource.path.name, key=key):
                    if unit.kind in {"code-line-comment", "code-block-comment"}:
                        self.assertEqual(entry["value"], unit.source)
                    else:
                        self.assertEqual(entry["value"], normalize_zh_spacing(entry["value"]))

    def test_zh_glossary_runtime_covers_only_canonical_material_terms(self) -> None:
        raw = (ROOT / "web/nemoclaw/scripts/_glossary_zh.js").read_text(encoding="utf-8")
        match = re.search(
            r"const ZH_BLURBS = Object\.freeze\((\{[\s\S]*?\})\);",
            raw,
        )
        self.assertIsNotNone(match)
        blurbs = json.loads(match.group(1))
        materials = json.loads(
            (ROOT / "web/nemoclaw/assets/materials_index.json").read_text(encoding="utf-8")
        )
        canonical_terms = {entry["term"] for entry in materials["entries"]}
        self.assertEqual(set(blurbs), canonical_terms)
        self.assertTrue(all(isinstance(value, str) and value.strip() for value in blurbs.values()))

    def test_migration_left_no_replaced_localized_html(self) -> None:
        for spec in discover_locales(ROOT):
            with self.subTest(locale=spec.locale):
                self.assertEqual(spec.state.get("overlay_files", []), [])
                stray = [path.relative_to(ROOT).as_posix()
                         for path in sorted(spec.overlay_root.rglob("*.html"))
                         if path.name != "SKILL.html"]
                self.assertEqual(stray, [])

    def test_every_reviewed_template_publishes_from_a_resource(self) -> None:
        for spec in discover_locales(ROOT):
            resources = {resource.template for resource in
                         (load_resource(path) for path in json_resources(spec.locale_root))}
            with self.subTest(locale=spec.locale):
                self.assertEqual(sorted(spec.state.get("reviews", {})), sorted(resources))
                for template in resources:
                    self.assertTrue(
                        expected_resource_path(spec.locale_root, template).is_file())

    def test_recorded_shared_key_variants_describe_a_real_divergence(self) -> None:
        for spec in discover_locales(ROOT):
            recorded = spec.state.get("shared_key_variants", {})
            with self.subTest(locale=spec.locale):
                self.assertIsInstance(recorded, dict)
                for key, reason in recorded.items():
                    self.assertEqual(key, base_key(key))
                    self.assertGreater(len(reason.strip()), 40)
                findings = audit.shared_key_findings(
                    ROOT, spec, json_resources(spec.locale_root),
                    consumer_map(audit.discover_templates(ROOT)))
                self.assertEqual(findings, [])

    def test_migrator_rejects_an_undeclared_or_stale_overlay(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-resource-migrator-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.add_overlay(root)
            state_path = root / "i18n" / fixtures.URL_CODE / "localization_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["overlay_files"] = []
            state_path.write_text(json.dumps(state), encoding="utf-8")
            # The CLI-loaded migration module and package-loaded test module can hold the same
            # ValueError subclass under different module names.
            with self.assertRaisesRegex(ValueError, "not declared"):
                build_resource(root, fixtures.LOCALE, fixtures.TEMPLATE)

            state["overlay_files"] = [fixtures.TEMPLATE]
            state["reviews"][fixtures.TEMPLATE]["translation_sha256"] = "0" * 64
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not reviewed"):
                build_resource(root, fixtures.LOCALE, fixtures.TEMPLATE)

            profile_path = (
                root / "scripts" / "translate" / "locales" / fixtures.LOCALE / "profile.json")
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["reviewed_target_hashes"] = True
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            from scripts.translate.localization_scope import translation_sha
            state["reviews"][fixtures.TEMPLATE] = {
                "translation_sha256": translation_sha(fixtures.TEMPLATE_HTML),
                "target_sha256": "0" * 64,
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "accepted locale target hash"):
                build_resource(root, fixtures.LOCALE, fixtures.TEMPLATE)

    def test_rendered_page_follows_the_assembler_publication_path(self) -> None:
        for spec, resource in tracked_resources():
            with self.subTest(resource=resource.path.name):
                template = (ROOT / resource.template).read_text(encoding="utf-8")
                shell = audit._locale_quality(ROOT, spec)["_shell_translations"]
                overlay = render_overlay(template, resource.values, spec.html_lang)
                rendered = render_page(template, resource.values, shell, spec.html_lang)
                if has_english_shell(template):
                    self.assertEqual(project_locale_html(template, overlay, shell), rendered)
                else:
                    # The assembler copies a page with no English shell verbatim, so the rendered
                    # overlay is the published page. Projecting it would reserialize shipped HTML.
                    self.assertEqual(overlay, rendered)
                self.assertIn(f'lang="{spec.html_lang}"', rendered)

    def test_untranslated_reasons_carry_review_provenance(self) -> None:
        for spec, resource in tracked_resources():
            expected = review_provenance(spec.locale, resource.template)
            for key, entry in resource.values.items():
                reason = entry.get("untranslated")
                if reason is None or reason == expected:
                    continue
                with self.subTest(resource=resource.path.name, key=key):
                    self.assertGreater(len(reason.strip()), 20)

    def test_provenance_reason_needs_an_accepted_overlay(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-resource-provenance-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.add_overlay(root)
            _, document = build_resource(root, fixtures.LOCALE, fixtures.TEMPLATE)
            reason = review_provenance(fixtures.LOCALE, fixtures.TEMPLATE)
            self.assertIn(fixtures.LOCALE, reason)
            self.assertIn(fixtures.TEMPLATE, reason)
            # Without the reviewed overlay there is nothing to derive a decision from, so a value
            # repeating English stays a hidden fallback rather than gaining an invented reason.
            (root / "i18n" / fixtures.URL_CODE / fixtures.TEMPLATE).unlink()
            with self.assertRaises(ValueError):
                build_resource(root, fixtures.LOCALE, fixtures.TEMPLATE)
            self.assertIsInstance(document, str)

class PublishedLocalePageTests(unittest.TestCase):
    """A runtime audit must see a locale page whichever representation currently holds it."""

    def test_published_pages_cover_every_migrated_page(self) -> None:
        pages = locale_pages.published_pages(ROOT)
        for spec, resource in tracked_resources():
            rel = (spec.locale_root / resource.template).relative_to(ROOT).as_posix()
            with self.subTest(page=rel):
                self.assertIn(rel, pages)
                self.assertIn(f'lang="{spec.html_lang}"', pages[rel])

    def test_a_reviewed_overlay_still_wins_over_its_resource(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-pages-overlay-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            resource_only = locale_pages.published_pages(root)
            rel = f"i18n/{fixtures.URL_CODE}/{fixtures.TEMPLATE}"
            self.assertIn(rel, resource_only)

            fixtures.add_overlay(root)
            overlay_path = root / rel
            overlay_path.write_text(
                overlay_path.read_text(encoding="utf-8").replace(
                    "Xx ciclo xx", "Xx ciclo revisado xx"),
                encoding="utf-8")
            published = locale_pages.published_pages(root)
            self.assertIn("Xx ciclo revisado xx", published[rel])
            self.assertNotIn("Xx ciclo revisado xx", resource_only[rel])

    def test_materialize_mirrors_a_walkable_locale_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-pages-mirror-") as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            fixtures.build_fixture(root)
            out = Path(directory) / "staged"
            mirrored = locale_pages.materialize(root, out)
            self.assertEqual(mirrored.name, "i18n")
            self.assertTrue((mirrored / fixtures.URL_CODE / "locale.json").is_file())
            self.assertTrue((mirrored / fixtures.URL_CODE / fixtures.TEMPLATE).is_file())

    def test_locale_page_discovery_is_not_a_path_allowlist(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-pages-growth-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            before = set(locale_pages.published_pages(root))
            fixtures.add_template_and_resource(root)
            fixtures.add_locale(root)
            after = set(locale_pages.published_pages(root))
            self.assertEqual(after - before, {
                f"i18n/{fixtures.URL_CODE}/{fixtures.SECOND_TEMPLATE}",
                f"i18n/zz/{fixtures.TEMPLATE}",
            })

    def test_published_pages_share_the_assembler_resource_fallback_authority(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        mutations = (
            fixtures.missing_review_authority,
            fixtures.stale_review_authority,
            fixtures.stale_target_authority,
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate.__name__), tempfile.TemporaryDirectory(
                    prefix="locale-pages-authority-") as directory:
                root = Path(directory)
                fixtures.build_fixture(root)
                mutate(root)
                rel = f"i18n/{fixtures.URL_CODE}/{fixtures.TEMPLATE}"
                resolved = locale_pages.published_pages(root)[rel]
                out = root / "out"
                assemble(root / "i18n" / fixtures.URL_CODE, out, root)
                assembled = (out / fixtures.TEMPLATE).read_text(encoding="utf-8")
                self.assertEqual(resolved, assembled)
                self.assertEqual(resolved, fixtures.TEMPLATE_HTML)


class ResourceMediaTests(unittest.TestCase):
    def test_localized_media_survives_migration(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-resource-media-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.declare_media(root)
            self.assertEqual(audit.audit(root), [])
            state_path = root / "i18n" / fixtures.URL_CODE / "localization_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["asset_files"] = []
            state_path.write_text(json.dumps(state), encoding="utf-8")
            codes = [item["code"] for item in audit.audit(root)]
            self.assertIn("resource-media-undeclared", codes)


class ResourceBuildTests(unittest.TestCase):
    def test_resource_only_page_renders_into_the_build(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        with tempfile.TemporaryDirectory(prefix="locale-resource-build-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            out = root / "out"
            (root / "web" / "shared").mkdir(parents=True, exist_ok=True)
            applied = assemble(root / "i18n" / fixtures.URL_CODE, out, root)
            self.assertIn(fixtures.TEMPLATE, applied)
            rendered = (out / fixtures.TEMPLATE).read_text(encoding="utf-8")
            self.assertIn(f'lang="{fixtures.LOCALE}"', rendered)
            self.assertIn(fixtures.SHELL_TARGET, rendered)
            shutil.rmtree(out)

    def test_existing_stale_overlay_keeps_resource_shadow_only(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        with tempfile.TemporaryDirectory(prefix="locale-resource-shadow-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.add_overlay(root)
            state_path = root / "i18n" / fixtures.URL_CODE / "localization_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["reviews"] = {}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            out = root / "out"
            applied = assemble(root / "i18n" / fixtures.URL_CODE, out, root)
            rendered = (out / fixtures.TEMPLATE).read_text(encoding="utf-8")
            self.assertNotIn(fixtures.TEMPLATE, applied)
            self.assertEqual(rendered, fixtures.TEMPLATE_HTML)

    def test_unreviewed_resource_falls_back_to_canonical(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        with tempfile.TemporaryDirectory(prefix="locale-resource-unreviewed-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            state_path = root / "i18n" / fixtures.URL_CODE / "localization_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["reviews"] = {}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            out = root / "out"
            applied = assemble(root / "i18n" / fixtures.URL_CODE, out, root)
            self.assertNotIn(fixtures.TEMPLATE, applied)
            self.assertEqual((out / fixtures.TEMPLATE).read_text(encoding="utf-8"),
                             fixtures.TEMPLATE_HTML)

    def test_unaccepted_resource_value_falls_back_to_canonical(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        with tempfile.TemporaryDirectory(prefix="locale-resource-unaccepted-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            profile_path = (
                root / "scripts" / "translate" / "locales" / fixtures.LOCALE / "profile.json")
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["reviewed_target_hashes"] = True
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            state_path = root / "i18n" / fixtures.URL_CODE / "localization_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["reviews"][fixtures.TEMPLATE]["target_sha256"] = "0" * 64
            state_path.write_text(json.dumps(state), encoding="utf-8")
            out = root / "out"
            applied = assemble(root / "i18n" / fixtures.URL_CODE, out, root)
            self.assertNotIn(fixtures.TEMPLATE, applied)
            self.assertEqual((out / fixtures.TEMPLATE).read_text(encoding="utf-8"),
                             fixtures.TEMPLATE_HTML)

    def test_unaccepted_html_overlay_falls_back_to_canonical(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        with tempfile.TemporaryDirectory(prefix="locale-overlay-unaccepted-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.add_overlay(root)
            profile_path = (
                root / "scripts" / "translate" / "locales" / fixtures.LOCALE / "profile.json")
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["reviewed_target_hashes"] = True
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            state_path = root / "i18n" / fixtures.URL_CODE / "localization_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["reviews"][fixtures.TEMPLATE]["target_sha256"] = "0" * 64
            state_path.write_text(json.dumps(state), encoding="utf-8")

            rel = f"i18n/{fixtures.URL_CODE}/{fixtures.TEMPLATE}"
            resolved = locale_pages.published_pages(root)[rel]
            out = root / "out"
            applied = assemble(root / "i18n" / fixtures.URL_CODE, out, root)
            assembled = (out / fixtures.TEMPLATE).read_text(encoding="utf-8")
            self.assertNotIn(fixtures.TEMPLATE, applied)
            self.assertEqual(resolved, assembled)
            self.assertEqual(assembled, fixtures.TEMPLATE_HTML)

    def test_direct_assembly_rejects_unsafe_values(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        mutations = (
            lambda root: fixtures.edit_value(
                root, "text", lambda value: f'<em onmouseover="steal()">{value}</em>'),
            fixtures.script_ui_injection,
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory(
                    prefix="locale-resource-unsafe-build-") as directory:
                root = Path(directory)
                fixtures.build_fixture(root)
                mutate(root)
                # The CLI-loaded assembler and package-loaded test module can hold the same
                # ValueError subclass under different module names. The built-in contract is stable.
                with self.assertRaises(ValueError):
                    assemble(root / "i18n" / fixtures.URL_CODE, root / "out", root)

    def test_direct_assembly_rejects_resource_identity_drift(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        for mutate in (fixtures.foreign_locale, fixtures.misplaced_resource):
            with self.subTest(mutation=mutate.__name__), tempfile.TemporaryDirectory(
                    prefix="locale-resource-identity-build-") as directory:
                root = Path(directory)
                fixtures.build_fixture(root)
                mutate(root)
                with self.assertRaises(ValueError):
                    assemble(root / "i18n" / fixtures.URL_CODE, root / "out", root)

    def test_localized_media_is_copied_for_resource_only_page(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble, source_sha

        with tempfile.TemporaryDirectory(prefix="locale-resource-media-build-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            fixtures.declare_media(root)
            state_path = root / "i18n" / fixtures.URL_CODE / "localization_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["asset_reviews"] = {
                fixtures.FIGURE: {
                    "source_sha256": source_sha(root / fixtures.FIGURE),
                }
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            out = root / "out"
            applied = assemble(root / "i18n" / fixtures.URL_CODE, out, root)
            self.assertIn(fixtures.FIGURE, applied)
            self.assertEqual(
                (out / fixtures.FIGURE).read_text(encoding="utf-8"),
                (root / "i18n" / fixtures.URL_CODE / fixtures.FIGURE).read_text(
                    encoding="utf-8"),
            )

    def test_direct_assembly_rejects_symlinked_media_inputs(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        for mutate in (
                fixtures.symlink_localized_media,
                fixtures.symlink_localized_media_parent,
                fixtures.symlink_canonical_media,
        ):
            with self.subTest(mutation=mutate.__name__), tempfile.TemporaryDirectory(
                    prefix="locale-resource-media-symlink-build-") as directory:
                root = Path(directory)
                fixtures.build_fixture(root)
                mutate(root)
                with self.assertRaises(ValueError):
                    assemble(root / "i18n" / fixtures.URL_CODE, root / "out", root)

    def test_direct_assembly_rejects_stale_localized_media_reviews(self) -> None:
        from scripts.build.assemble_locale_overlay import assemble

        for mutate in (fixtures.stale_media_source_review, fixtures.stale_media_target_review):
            with self.subTest(mutation=mutate.__name__), tempfile.TemporaryDirectory(
                    prefix="locale-resource-media-review-build-") as directory:
                root = Path(directory)
                fixtures.build_fixture(root)
                mutate(root)
                with self.assertRaises(ValueError):
                    assemble(root / "i18n" / fixtures.URL_CODE, root / "out", root)


class ResourceLocalizationContinuityTests(unittest.TestCase):
    def test_accept_reuses_reviewed_untranslated_resource_reasons(self) -> None:
        with tempfile.TemporaryDirectory(prefix="locale-resource-acceptance-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            resource_path = fixtures.resource_path(root)
            resource = json.loads(resource_path.read_text(encoding="utf-8"))
            entry = next(
                item for item in resource["values"].values()
                if item["source"].strip() == "The agent loop"
            )
            entry["value"] = entry["source"]
            entry["untranslated"] = "Exact interface label retained after rendered locale review"
            resource_path.write_text(
                json.dumps(resource, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            profile_path = (
                root / "scripts" / "translate" / "locales" / fixtures.LOCALE / "profile.json"
            )
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["reviewed_target_hashes"] = True
            profile["english_sentence_markers"] = ["The agent loop"]
            profile_path.write_text(json.dumps(profile), encoding="utf-8")

            self.assertEqual(
                localization_audit.accept(root, fixtures.LOCALE, [fixtures.TEMPLATE]),
                [],
            )

            del entry["untranslated"]
            resource_path.write_text(
                json.dumps(resource, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            self.assertTrue(
                localization_audit.accept(root, fixtures.LOCALE, [fixtures.TEMPLATE])
            )

    def test_resource_style_reference_keeps_its_editorial_pin(self) -> None:
        from scripts.translate.localization_scope import editorial_sha
        from scripts.validation import localization_audit

        with tempfile.TemporaryDirectory(prefix="locale-resource-style-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            resource = load_resource(fixtures.resource_path(root))
            target = render_overlay(fixtures.TEMPLATE_HTML, resource.values, fixtures.LOCALE)
            profile_path = (
                root / "scripts" / "translate" / "locales" / fixtures.LOCALE / "profile.json")
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["review_protocol"] = {
                "style_reference": fixtures.TEMPLATE,
                "style_reference_origin_commit": "a" * 40,
                "style_reference_editorial_sha256": editorial_sha(target),
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            state_path = root / "i18n" / fixtures.URL_CODE / "localization_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["reviews"][fixtures.TEMPLATE]["target_sha256"] = audit._sha(target)
            state_path.write_text(json.dumps(state), encoding="utf-8")

            findings, _ = localization_audit.scan(root, fixtures.LOCALE)
            self.assertNotIn("style-reference-drift", {item["code"] for item in findings})

            fixtures.edit_value(root, "text", lambda value: value + " cambiado")
            findings, _ = localization_audit.scan(root, fixtures.LOCALE)
            self.assertIn("style-reference-drift", {item["code"] for item in findings})

    def test_explicit_editorial_pin_ignores_plumbing_but_not_style_prose(self) -> None:
        from scripts.translate.localization_scope import editorial_sha

        source = (
            '<html><p data-editorial-pin="1">Pinned editorial voice.</p>'
            '<p>Runtime-facing exercise copy.</p><script>const model = "old";</script></html>'
        )
        plumbing = source.replace("Runtime-facing exercise copy.", "Updated exercise copy.") \
            .replace('"old"', '"current"')
        editorial = source.replace("Pinned editorial voice.", "Changed editorial voice.")
        missing_beacon = source.replace(' data-editorial-pin="1"', "")

        self.assertEqual(editorial_sha(source), editorial_sha(plumbing))
        self.assertNotEqual(editorial_sha(source), editorial_sha(editorial))
        self.assertNotEqual(editorial_sha(source), editorial_sha(missing_beacon))

    def test_resource_only_page_rebinds_review_and_manifest_availability(self) -> None:
        from scripts.translate.localization_scope import translation_sha
        from scripts.validation import localization_audit

        rel = "web/nemoclaw/index.html"
        with tempfile.TemporaryDirectory(prefix="locale-resource-continuity-") as directory:
            root = Path(directory)
            fixtures.build_fixture(root)
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(fixtures.TEMPLATE_HTML, encoding="utf-8")
            fixtures._resource(root, fixtures.URL_CODE, fixtures.LOCALE,
                               rel, fixtures.TEMPLATE_HTML)
            profile_path = (
                root / "scripts" / "translate" / "locales" / fixtures.LOCALE / "profile.json")
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["reviewed_target_hashes"] = True
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            resource = load_resource(fixtures.resource_path(root, rel))
            target = render_overlay(fixtures.TEMPLATE_HTML, resource.values, fixtures.LOCALE)
            state_path = root / "i18n" / fixtures.URL_CODE / "localization_state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["reviews"] = {
                rel: {
                    "translation_sha256": translation_sha(fixtures.TEMPLATE_HTML),
                    # The former HTML representation can have different ignorable whitespace.
                    "target_sha256": "0" * 64,
                }
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            findings, manifest = localization_audit.scan(root, fixtures.LOCALE)
            self.assertIn("target-drift", {item["code"] for item in findings})
            row = next(item for item in manifest["pages"] if item["path"] == rel)
            self.assertEqual(row["status"], "needs-review")
            self.assertEqual(localization_audit.accept(root, fixtures.LOCALE, [rel]), [])

            findings, manifest = localization_audit.scan(root, fixtures.LOCALE)
            self.assertEqual(findings, [])
            row = next(item for item in manifest["pages"] if item["path"] == rel)
            self.assertEqual(row["status"], "current")
            self.assertEqual(row["target_representation"], "locale-resource")
            self.assertIn("index.html", manifest["available_pages"])
            accepted = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(
                accepted["reviews"][rel]["target_sha256"],
                localization_audit.sha(target),
            )


class TrackedManifestProjectionTests(unittest.TestCase):
    """The drift manifest each locale publishes is generated, so a stale copy must fail early."""

    def projections(self):
        from scripts.validation import localization_audit

        for spec in discover_locales(ROOT):
            _, manifest = localization_audit.scan(ROOT, spec.locale)
            yield spec, manifest

    def test_tracked_manifest_matches_a_fresh_scan(self) -> None:
        from scripts.validation import localization_audit

        for spec, manifest in self.projections():
            with self.subTest(locale=spec.locale):
                self.assertEqual(
                    [], localization_audit.manifest_drift(ROOT, spec.profile, manifest))

    def test_every_structural_manifest_mutation_is_detected(self) -> None:
        from scripts.validation import localization_audit

        for spec, manifest in self.projections():
            path = localization_audit.manifest_path(ROOT, spec.profile)
            with tempfile.TemporaryDirectory(prefix="locale-manifest-projection-") as directory:
                mirror = Path(directory) / path.relative_to(ROOT)
                mirror.parent.mkdir(parents=True, exist_ok=True)
                for name, mutated in localization_audit.manifest_projection_mutations(manifest):
                    mirror.write_text(
                        localization_audit.manifest_bytes(mutated), encoding="utf-8")
                    with self.subTest(locale=spec.locale, mutation=name):
                        self.assertIn(
                            "manifest-projection-stale",
                            {item["code"] for item in localization_audit.manifest_drift(
                                Path(directory), spec.profile, manifest)})


class ChineseRuntimeLocalizationTests(unittest.TestCase):
    def test_helper_prose_is_localized_without_translating_code_or_partial_buttons(self) -> None:
        script = r'''
globalThis.document = { documentElement: { lang: "zh-CN" } };
const locale = await import("./web/nemoclaw/scripts/_locale.js");
const fail = message => { throw new Error(message); };

const runAll = locale.localizeCourseUiText(
  "Reset when you click <strong>▶ Run all</strong>."
);
if (!runAll.includes("▶ 全部运行") || runAll.includes("运行 all")) {
  fail("Run all was translated as a shorter mixed-language label: " + runAll);
}

const protectedCode = locale.localizeCourseUiText(
  "Use <code>log.clear()</code>, then clear the panel."
);
if (!protectedCode.includes("<code>log.clear()</code>") || protectedCode.includes("log.清除")) {
  fail("inline code was translated: " + protectedCode);
}

if (locale.localizeCourseUiText("Instrumentation") !== "追踪与日志") {
  fail("the trace/log helper category uses an unnatural literal translation");
}
if (locale.localizeCourseUiText("Visualization") !== "可视化") {
  fail("the visualization helper category was not localized");
}

const documentedHelpers = [
  "chat", "chatStream", "webSearch", "instantAnswer", "formatSearchResults",
  "embed", "cosineSim", "fetchRetry", "delay", "getConfig", "getKey",
  "terminal", "coursePage", "coursePages", "contextWindow", "estimateTokens",
  "browserChatFetch", "diagramSVG", "ganttBarsSVG", "mountFigures", "mountChatUI",
  "mountAgentChat", "mountOpenClawCli", "mountKeyPanel", "openclawBootstrapRequest",
  "openclawChat", "evalSandboxNetwork", "evalSandboxFs", "sandboxExec", "policyGet",
  "viz.diagram", "viz.lineChart", "viz.scoreBarChart", "viz.messageList",
  "viz.ganttBars", "viz.retrievalBars", "viz.diffTable", "viz.chat", "viz.sideBySide",
  "state", "fetch", "trace", "log", "signal",
];
for (const name of documentedHelpers) {
  const value = locale.localizeCourseHelperDescription(name, "English helper description");
  if (value === "English helper description" || !/[\u3400-\u9fff]/.test(value)) {
    fail("missing Chinese helper description: " + name);
  }
}
const logDescription = locale.localizeCourseHelperDescription("log", "unused");
if (!logDescription.includes("<code>log.clear()</code>") || logDescription.includes("log.清除")) {
  fail("localized log helper description changed executable code");
}
'''
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_taiwan_runtime_ui_uses_traditional_script_and_regional_terms(self) -> None:
        script = r'''
globalThis.document = { documentElement: { lang: "zh-TW" } };
const locale = await import("./web/nemoclaw/scripts/_locale.js");
const fail = message => { throw new Error(message); };

const runAll = locale.localizeCourseUiText(
  "Reset when you click <strong>▶ Run all</strong>."
);
if (!runAll.includes("▶ 全部執行") || /运行|運行/.test(runAll)) {
  fail("Run all does not use the Taiwan runtime term: " + runAll);
}
if (locale.localizeCourseUiText("Instrumentation") !== "追蹤與日誌") {
  fail("the trace/log helper category is not localized for Taiwan");
}
if (locale.localizeCourseUiText("+ show all 3 more helpers") !== "+ 顯示其餘 3 個輔助函式") {
  fail("dynamic helper text is not localized for Taiwan");
}
const description = locale.localizeCourseHelperDescription("mountAgentChat", "English helper description");
if (!/[\u3400-\u9fff]/.test(description) || /智能體|智慧體|運行時/.test(description)) {
  fail("helper description does not use Taiwan terminology: " + description);
}
const protectedCode = locale.localizeCourseUiText(
  "Use <code>log.clear()</code>, then clear the panel."
);
if (!protectedCode.includes("<code>log.clear()</code>") || protectedCode.includes("log.清除")) {
  fail("inline code was translated: " + protectedCode);
}
'''
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_chinese_resources_preserve_code_and_use_exact_button_and_brand_labels(self) -> None:
        resource_root = ROOT / "i18n/zh/resources/web/nemoclaw"
        values = []
        for path in resource_root.glob("*.json"):
            document = json.loads(path.read_text(encoding="utf-8"))
            values.extend(item.get("value", "") for item in document.get("values", {}).values())
        localized = "\n".join(values)
        for unwanted in ("log.清除()", "运行 all", "点击 Run", "按下 Run", "单击 Run", "NVIDIA · 智能体安全"):
            self.assertNotIn(unwanted, localized)
        self.assertIn("点击“全部运行”", localized)
        self.assertIn("NVIDIA · 安全智能体", localized)


if __name__ == "__main__":
    unittest.main()
