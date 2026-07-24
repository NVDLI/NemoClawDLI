# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standard-framework tests for deployment-root navigation projection."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build.bundle_standalone import _copy_pyodide_review, project_artifact_navigation
from scripts.build.project_artifact_navigation import project_generated_output_aliases, project_lab_static_urls
from scripts.build.project_artifact_manifests import project_artifact_manifests
from scripts.validation.artifact_link_audit import audit


class ArtifactNavigationProjectionTests(unittest.TestCase):
    def test_source_projection_runs_after_docs_projection(self):
        """A docs link must not restore repository-only routes after public projection."""
        root = Path(__file__).resolve().parents[2]
        build = (root / "scripts/build/build_pages.sh").read_text(encoding="utf-8")
        docs = build.index('python3 "$T1/scripts/build/project_docs_explorer.py"')
        source = build.index('python3 "$T1/scripts/build/project_source_tree.py"')
        self.assertLess(docs, source)

    def test_nested_preview_manifest_describes_real_combined_tree_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "topic" / "branches.json"
            output.parent.mkdir()
            subprocess.run(
                [
                    sys.executable,
                    "scripts/build/build_branch_manifest.py",
                    "--out", str(output),
                    "--current-ref", "feature/topic",
                    "--current-slug", "topic",
                    "--site-root-prefix", "../",
                ],
                cwd=Path(__file__).resolve().parents[2],
                check=True,
                capture_output=True,
                text=True,
            )
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("../nemoclaw/", data["production_url"])
            self.assertEqual(
                ["../nemoclaw/", "web/nemoclaw/"],
                [item["url"] for item in data["branches"]],
            )

    def test_manifests_follow_every_discovered_mirror_after_ci_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            deployment = Path(directory)
            (deployment / "nemoclaw").mkdir()
            preview = deployment / "topic"
            for course in (
                preview / "web/nemoclaw",
                preview / "validated-source/web/nemoclaw",
                preview / "i18n/es/web/nemoclaw",
            ):
                course.mkdir(parents=True)
            (preview / "LICENSE").write_text("license", encoding="utf-8")
            (preview / "languages.json").write_text(
                json.dumps({"languages": [{"url": "web/nemoclaw/"}]}), encoding="utf-8"
            )
            (preview / "branches.json").write_text(
                json.dumps({"branches": [
                    {"url": "../nemoclaw/"},
                    {"url": "web/nemoclaw/"},
                ]}),
                encoding="utf-8",
            )

            project_artifact_manifests(deployment, preview)

            validated = preview / "validated-source"
            branches = json.loads((validated / "branches.json").read_text(encoding="utf-8"))
            self.assertEqual(["../../nemoclaw/", "../web/nemoclaw/"], [
                item["url"] for item in branches["branches"]
            ])
            self.assertEqual("license", (validated / "LICENSE").read_text(encoding="utf-8"))

    def test_lab_static_urls_resolve_root_and_relocated_course_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("home", encoding="utf-8")
            (root / "scripts").mkdir()
            (root / "scripts" / "SKILL.html").write_text("toolchain", encoding="utf-8")
            course = root / "web" / "nemoclaw"
            (course / "assets").mkdir(parents=True)
            (course / "index.html").write_text('<main id="start">course</main>', encoding="utf-8")
            (course / "assets" / "favicon.ico").write_bytes(b"icon")
            foyer = root / "web" / "index.html"
            foyer.write_text(
                '<link href="/lab/static/nemoclaw/assets/favicon.ico">'
                '<a href="/lab/static/nemoclaw/index.html?from=lab#start">course</a>'
                '<a href="/lab/static/scripts/SKILL.html">tools</a>',
                encoding="utf-8",
            )

            self.assertEqual(1, project_lab_static_urls(root, "web"))

            source = foyer.read_text(encoding="utf-8")
            self.assertIn('href="nemoclaw/assets/favicon.ico"', source)
            self.assertIn('href="nemoclaw/index.html?from=lab#start"', source)
            self.assertIn('href="../scripts/SKILL.html"', source)
            self.assertEqual([], [str(item) for item in audit(root)])

    def test_source_mirror_standalone_route_targets_the_fresh_course_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / "web/nemoclaw"
            course.mkdir(parents=True)
            (course / "SKILL.html").write_text("built course", encoding="utf-8")
            mirror = root / "validated-source/web/nemoclaw"
            mirror.mkdir(parents=True)
            (mirror / "SKILL.html").write_text(
                '<a href="standalone/SKILL.html">Standalone export</a>', encoding="utf-8"
            )

            self.assertEqual(1, project_generated_output_aliases(root, "web"))

            alias = mirror / "standalone/SKILL.html"
            self.assertTrue(alias.is_file())
            self.assertIn('../../../../web/nemoclaw/SKILL.html', alias.read_text(encoding="utf-8"))
            self.assertEqual([], [str(item) for item in audit(root)])

    def test_every_explorer_is_rebased_without_a_surface_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text('<a href="SKILL.html">map</a>', encoding="utf-8")
            (root / "SKILL.html").write_text(self.fixture("../index.html", "../SKILL.html"), encoding="utf-8")
            nested = root / "nested" / "SKILL.html"
            nested.parent.mkdir()
            nested.write_text(self.fixture("../../index.html", "../../SKILL.html"), encoding="utf-8")
            report = root / "report.html"
            report.write_text(self.fixture("../../index.html", "../../SKILL.html"), encoding="utf-8")
            static_topbar = root / "graph.html"
            static_topbar.write_text(
                '<!doctype html><body><div class="sx-topbar">'
                '<a class="sx-logo" href="../../index.html">Home</a>'
                '<a class="sx-up" href="../SKILL.html">Up</a>'
                '</div></body>',
                encoding="utf-8",
            )

            project_artifact_navigation(root)

            self.assertEqual([], [str(item) for item in audit(root)])
            nested_index = nested.parent / "index.html"
            self.assertTrue(nested_index.is_file())
            self.assertIn('id="explorer-config"', nested_index.read_text(encoding="utf-8"))
            self.assertNotIn('http-equiv="refresh"', nested_index.read_text(encoding="utf-8"))
            for page in (root / "SKILL.html", nested, report, static_topbar):
                source = page.read_text(encoding="utf-8")
                if page == static_topbar:
                    self.assertIn('href="index.html"', source)
                    self.assertIn('href="SKILL.html"', source)
                    self.assertNotIn('../', source)
                    continue
                self.assertIn('data-skill-nav="home"', source)
                self.assertIn('data-skill-nav="map"', source)
                config = source.split('id="explorer-config">', 1)[1].split("</script>", 1)[0]
                self.assertIn("map", json.loads(config)["nav"])

    def test_navigation_projection_never_hides_a_missing_local_link(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("home", encoding="utf-8")
            page = root / "SKILL.html"
            page.write_text(
                self.fixture("index.html", "SKILL.html").replace(
                    "</body>", '<a class="skill-card" href="missing/SKILL.html">Missing</a></body>'
                ),
                encoding="utf-8",
            )

            project_artifact_navigation(root)

            self.assertIn('href="missing/SKILL.html"', page.read_text(encoding="utf-8"))
            self.assertTrue(any("does not exist" in str(item) for item in audit(root)))

    def test_pyodide_review_projection_ships_its_contract_and_rebases_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _copy_pyodide_review(root)

            page = root / "pyodide/SKILL.html"
            self.assertTrue(page.is_file())
            self.assertTrue((root / "pyodide/candidate-components.json").is_file())
            self.assertTrue((root / "pyodide/shared/runtime-workbench.css").is_file())
            self.assertTrue((root / "pyodide/shared/runtime-workbench.js").is_file())
            source = page.read_text(encoding="utf-8")
            self.assertIn('href="../styles/_style.css"', source)
            self.assertIn('src="../vendor/codemirror-5.65.21.js"', source)
            self.assertIn('src="../vendor/codemirror-mode-python-5.65.21.js"', source)
            self.assertIn('href="./shared/runtime-workbench.css"', source)
            self.assertIn('from "./shared/runtime-workbench.js"', source)
            self.assertNotIn('from "shared/runtime-workbench.js"', source)
            self.assertNotIn("../../web/nemoclaw/", source)
            self.assertNotIn("../../web/shared/", source)

    @staticmethod
    def fixture(home: str, map_href: str) -> str:
        return (
            '<!doctype html><body><header data-skill-header="1"><nav>'
            f'<a href="{home}">Home</a><a href="{map_href}">Map</a>'
            '</nav></header><script type="application/json" id="explorer-config">'
            f'{{"title":"fixture","nav":{{"home":"{home}"}},"files":[]}}'
            '</script></body>'
        )


if __name__ == "__main__":
    unittest.main()
