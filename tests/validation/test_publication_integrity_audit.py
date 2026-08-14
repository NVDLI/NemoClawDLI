# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.build import project_publication_metadata as projector
from scripts.validation import publication_integrity_audit as audit
from scripts.validation import release_gate


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = tuple(sorted((ROOT / "web").glob("*/publication-integrity.json")))
if len(CONTRACTS) != 1:
    raise RuntimeError(f"expected one publication contract, found {len(CONTRACTS)}")
COURSE = CONTRACTS[0].parent


class PublicationIntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        audit.figure_rows.cache_clear()

    def contract(self) -> dict:
        return json.loads((COURSE / "publication-integrity.json").read_text(encoding="utf-8"))

    def copy_course(self, root: Path) -> Path:
        course = root / COURSE.name
        course.mkdir(parents=True)
        for path in COURSE.glob("*.html"):
            shutil.copy2(path, course / path.name)
        (course / "scripts").mkdir()
        shutil.copy2(COURSE / "scripts" / "_learning.js", course / "scripts" / "_learning.js")
        (course / "styles").mkdir()
        shutil.copy2(COURSE / "styles" / "_style.css", course / "styles" / "_style.css")
        return course

    def codes(self, findings: list[dict[str, str]]) -> set[str]:
        return {item["code"] for item in findings}

    def test_current_contract_is_complete_and_grounded(self) -> None:
        self.assertEqual([], audit.audit_contract(self.contract()))

    def test_visible_text_uses_html_parsing_not_tag_filtering(self) -> None:
        raw = '<p title="1 > 0">Visible <em>course</em></p><script>Hidden product</script>'
        self.assertEqual("Visible course", audit.visible_text(raw))

    def test_build_and_public_workflows_enforce_the_generic_contract(self) -> None:
        build = (ROOT / "scripts" / "build" / "build_pages.sh").read_text(encoding="utf-8")
        self.assertIn('PUBLICATION_MODE="${BUILD_PAGES_PUBLICATION_MODE:-preview}"', build)
        projector_call = build.index("project_publication_metadata.py")
        navigation_call = build.index("project_artifact_navigation.py", projector_call)
        artifact_audit = build.index("publication_integrity_audit.py", navigation_call)
        self.assertLess(projector_call, navigation_call)
        self.assertLess(navigation_call, artifact_audit)
        self.assertIn(release_gate.STANDARD_TEST_DISCOVERY, release_gate.FAST_COMMANDS)
        self.assertIn(release_gate.STANDARD_TEST_DISCOVERY, release_gate.SHIP_COMMANDS)
        for workflow in ("pages.yml", "release.yml"):
            text = (ROOT / ".github" / "workflows" / workflow).read_text(encoding="utf-8")
            self.assertIn("BUILD_PAGES_PUBLICATION_MODE: public", text)

    def test_novel_deleted_and_renamed_pages_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course = self.copy_course(Path(tmp))
            data = self.contract()
            (course / "05a-new.html").write_text("<!doctype html><title>New</title>", encoding="utf-8")
            self.assertIn("page-unclassified", self.codes(audit.audit_contract(data, course=course, provenance=())))

            (course / "05a-new.html").unlink()
            (course / "01a-loop.html").unlink()
            self.assertIn("page-stale", self.codes(audit.audit_contract(data, course=course, provenance=())))

            source = course / "01b-react.html"
            source.rename(course / "01b-renamed.html")
            codes = self.codes(audit.audit_contract(data, course=course, provenance=()))
            self.assertTrue({"page-unclassified", "page-stale"}.issubset(codes))

    def test_metadata_only_entity_and_invented_product_name_are_rejected(self) -> None:
        data = self.contract()
        data["pages"]["01a-loop.html"]["entities"].append("Hermes Agent")
        self.assertIn("entity-hidden", self.codes(audit.audit_contract(data, provenance=())))

        data = self.contract()
        data["pages"]["01a-loop.html"]["description"] += " DeepAgent."
        self.assertIn("entity-name", self.codes(audit.audit_contract(data, provenance=())))

    def test_unknown_media_and_missing_deepfake_label_are_rejected(self) -> None:
        base = {
            "file": "figures/01a-agent-environment.svg",
            "used_by": "01a-loop.html",
            "content_origin": "unknown",
            "transparency_class": "technical-diagram",
            "visible_disclosure_required": False,
            "transparency_basis": "fixture",
        }
        self.assertIn("media-origin", self.codes(audit.audit_contract(self.contract(), provenance=(base,))))

        deepfake = {**base, "content_origin": "course-authored", "transparency_class": "deepfake", "visible_disclosure_required": True}
        self.assertIn("media-label", self.codes(audit.audit_contract(self.contract(), provenance=(deepfake,))))

    def test_learner_disclosure_contract_and_runtime_fail_closed(self) -> None:
        data = self.contract()
        del data["text_transparency"]["learner_disclosure"]
        self.assertIn("text-disclosure-contract", self.codes(audit.audit_contract(data, provenance=())))

        with tempfile.TemporaryDirectory() as tmp:
            course = self.copy_course(Path(tmp))
            runtime = course / "scripts" / "_learning.js"
            raw = runtime.read_text(encoding="utf-8")
            runtime.write_text(raw.replace('imageLink.href = "assets/SKILL.html"', 'imageLink.href = "missing.html"', 1), encoding="utf-8")
            self.assertIn("text-disclosure-runtime", self.codes(audit.audit_contract(self.contract(), course=course, provenance=())))

            style = course / "styles" / "_style.css"
            raw = style.read_text(encoding="utf-8")
            style.write_text(raw.replace("justify-self: end", "justify-self: start", 1), encoding="utf-8")
            self.assertIn("assistant-overview-layout", self.codes(audit.audit_contract(self.contract(), course=course, provenance=())))

    def test_novel_static_and_runtime_media_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            course = self.copy_course(Path(tmp))
            data = self.contract()
            page = course / "01b-react.html"
            raw = page.read_text(encoding="utf-8")
            page.write_text(raw.replace("</body>", '<img src="assets/figures/new.svg" alt="new"/></body>'), encoding="utf-8")
            self.assertIn("media-unclassified", self.codes(audit.audit_contract(data, course=course, provenance=())))

            page.write_text(raw.replace("</body>", '<script>document.createElement("canvas").toDataURL()</script></body>'), encoding="utf-8")
            self.assertIn("runtime-media-unclassified", self.codes(audit.audit_contract(data, course=course, provenance=())))

    def test_runtime_media_source_and_classification_are_enforced(self) -> None:
        data = self.contract()
        data["runtime_media"][0]["source_token"] = "missing-render-token"
        self.assertIn("runtime-media-source", self.codes(audit.audit_contract(data, provenance=())))

        data = self.contract()
        data["runtime_media"][0]["transparency_class"] = "unknown"
        self.assertIn("runtime-media-class", self.codes(audit.audit_contract(data, provenance=())))

    def test_dynamic_and_material_media_are_discovered_without_filename_allowlists(self) -> None:
        data = self.contract()
        data["script_media"] = data["script_media"][1:]
        self.assertIn("script-media-unclassified", self.codes(audit.audit_contract(data, provenance=())))

        with tempfile.TemporaryDirectory() as tmp:
            course = Path(tmp) / COURSE.name
            shutil.copytree(COURSE, course)
            (course / "mats" / "glossary_raw" / "images" / "novel.png").write_bytes(b"not-an-image")
            self.assertIn(
                "material-media-unclassified",
                self.codes(audit.audit_contract(self.contract(), course=course, provenance=())),
            )

    def test_public_projection_indexes_only_primary_course_and_builds_exact_sitemap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            course = self.copy_course(site)
            mirror = site / "validated-source" / "web" / COURSE.name
            shutil.copytree(course, mirror)
            data = self.contract()
            projector.project(site, course, data, projector.PUBLIC_MODE)
            self.assertEqual([], audit.audit_artifact(site, data, projector.PUBLIC_MODE))
            self.assertIn('content="noindex,follow"', (mirror / "index.html").read_text(encoding="utf-8"))

            raw = (mirror / "index.html").read_text(encoding="utf-8")
            (mirror / "index.html").write_text(raw.replace("noindex,follow", "index,follow", 1), encoding="utf-8")
            self.assertIn("artifact-index", self.codes(audit.audit_artifact(site, data, projector.PUBLIC_MODE)))

    def test_preview_projection_has_no_sitemap_and_disallows_crawling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            course = self.copy_course(site)
            data = self.contract()
            projector.project(site, course, data, projector.PREVIEW_MODE)
            self.assertEqual([], audit.audit_artifact(site, data, projector.PREVIEW_MODE))
            self.assertFalse((site / "sitemap.xml").exists())
            self.assertEqual("User-agent: *\nDisallow: /\n", (site / "robots.txt").read_text(encoding="utf-8"))

    def test_prefixed_primary_course_is_explicit_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            course = self.copy_course(site / "branch-preview")
            data = self.contract()
            projector.project(site, course, data, projector.PREVIEW_MODE)
            self.assertEqual(
                [],
                audit.audit_artifact(
                    site,
                    data,
                    projector.PREVIEW_MODE,
                    primary_course_root=course,
                ),
            )
            (course / "01a-loop.html").unlink()
            self.assertIn(
                "artifact-page",
                self.codes(
                    audit.audit_artifact(
                        site,
                        data,
                        projector.PREVIEW_MODE,
                        primary_course_root=course,
                    )
                ),
            )

    def test_malformed_metadata_and_stale_sitemap_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            course = self.copy_course(site)
            data = copy.deepcopy(self.contract())
            projector.project(site, course, data, projector.PUBLIC_MODE)
            page = course / "01a-loop.html"
            page.write_text(page.read_text(encoding="utf-8").replace('name="description"', 'name="descriptio"', 1), encoding="utf-8")
            (site / "sitemap.xml").write_text('<urlset><url><loc>https://example.invalid/extra</loc></url></urlset>', encoding="utf-8")
            codes = self.codes(audit.audit_artifact(site, data, projector.PUBLIC_MODE))
            self.assertTrue({"artifact-metadata", "sitemap"}.issubset(codes))


if __name__ == "__main__":
    unittest.main()
