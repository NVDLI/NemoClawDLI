#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standard-library tests for exhaustive SKILL coverage and renderer contracts."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import skill_audit
import skill_contract


def page(script: str = "../web/_skill_explorer.js", file_name: str = "item.txt") -> str:
    meta = {
        "schema": "dir-skill/1.0",
        "node_type": "directory-explorer",
        "title": "fixture",
        "source_dir": "fixture/",
        "summary": "A renderer fixture with enough human-readable detail.",
        "explorer": script,
    }
    config = {
        "title": "fixture",
        "summary": meta["summary"],
        "files": [{"path": file_name, "role": "fixture", "desc": "fixture source"}],
    }
    return f'''<!DOCTYPE html><html><head>
<script type="application/json" id="skill-meta">{json.dumps(meta)}</script>
<script type="application/json" id="explorer-config">{json.dumps(config)}</script>
</head><body><header data-skill-header="1"><nav aria-label="Skill navigation"><a href="../SKILL.html">Up</a><a href="../index.html">Home</a></nav></header><main><h1>Fixture directory</h1><p>{meta["summary"]}</p></main>
<div id="explorer"></div><script src="{script}"></script></body></html>'''


class DirectoryCoverageTests(unittest.TestCase):
    def test_every_ancestor_directory_is_discovered(self) -> None:
        files = [Path(".github/workflows/pages.yml"), Path("web/course/assets/figure.svg")]
        self.assertEqual(
            skill_audit.directories_for_files(files),
            [
                Path("."),
                Path(".github"),
                Path("web"),
                Path(".github/workflows"),
                Path("web/course"),
                Path("web/course/assets"),
            ],
        )


class SkillGraphTests(unittest.TestCase):
    def test_disconnected_beacon_fails_until_root_path_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "scripts" / "compliance"
            child.mkdir(parents=True)
            root_skill = root / "SKILL.html"
            scripts_skill = root / "scripts" / "SKILL.html"
            compliance_skill = child / "SKILL.html"
            root_skill.write_text('<html><body><a href="scripts/SKILL.html">scripts</a></body></html>', encoding="utf-8")
            scripts_skill.write_text('<html><body><p>Scripts without a child link.</p></body></html>', encoding="utf-8")
            compliance_skill.write_text('<html><body><p>Compliance evidence.</p></body></html>', encoding="utf-8")
            skills = [root_skill, scripts_skill, compliance_skill]
            findings = skill_contract.skill_graph_findings(root, skills)
            self.assertIn(
                ("scripts/compliance/SKILL.html", "beacon is disconnected from the root SKILL graph"),
                findings,
            )
            scripts_skill.write_text(
                '<html><body><a href="compliance/SKILL.html">compliance</a></body></html>', encoding="utf-8"
            )
            self.assertEqual(skill_contract.skill_graph_findings(root, skills), [])


class RendererContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "SKILL.html").write_text("fixture root", encoding="utf-8")
        (self.root / "index.html").write_text("fixture home", encoding="utf-8")
        (self.root / "web").mkdir()
        (self.root / "web" / "_skill_explorer.js").write_text("/* fixture */", encoding="utf-8")
        (self.root / "fixture").mkdir()
        (self.root / "fixture" / "item.txt").write_text("fixture", encoding="utf-8")
        self.skill = self.root / "fixture" / "SKILL.html"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def findings(self, text: str) -> list[str]:
        self.skill.write_text(text, encoding="utf-8")
        return skill_contract.renderer_findings_for(self.skill, self.root)

    def test_valid_shared_renderer(self) -> None:
        self.assertEqual(self.findings(page()), [])

    def test_missing_shared_renderer_fails(self) -> None:
        text = page().replace('<script src="../web/_skill_explorer.js"></script>', "")
        self.assertTrue(any("every SKILL page requires exactly one shared" in finding for finding in self.findings(text)))

    def test_leaf_without_explorer_config_still_requires_shared_shell(self) -> None:
        text = '<!DOCTYPE html><html><head><script type="application/json" id="skill-meta">{"node_type":"leaf","source_dir":"fixture/","summary":"fixture","self_path":"fixture/SKILL.html","title":"fixture"}</script></head><body><header data-skill-header="1"><nav><a href="../SKILL.html">Up</a><a href="../index.html">Home</a></nav></header><main>fixture body text that is long enough to inspect</main><script src="../web/_skill_explorer.js"></script></body></html>'
        self.assertEqual(self.findings(text), [])

    def test_root_absolute_renderer_fails(self) -> None:
        self.assertTrue(any("root-absolute" in finding for finding in self.findings(page("/web/_skill_explorer.js"))))

    def test_missing_configured_file_fails(self) -> None:
        self.assertTrue(any("explorer-config file is missing" in finding for finding in self.findings(page(file_name="gone.txt"))))

    def test_missing_visible_link_fails(self) -> None:
        text = page().replace("</main>", '<a href="gone.py">Missing source</a></main>')
        self.assertTrue(any("local link target is missing" in finding for finding in self.findings(text)))

    def test_missing_navigation_header_fails(self) -> None:
        text = page().replace('<header data-skill-header="1"><nav aria-label="Skill navigation"><a href="../SKILL.html">Up</a><a href="../index.html">Home</a></nav></header>', "")
        self.assertTrue(any("missing semantic skill navigation header" in finding for finding in self.findings(text)))

    def test_navigation_header_needs_two_destinations(self) -> None:
        text = page().replace('<a href="../index.html">Home</a>', '<a href="../SKILL.html">Home</a>')
        self.assertTrue(any("at least two distinct links" in finding for finding in self.findings(text)))

    def test_custom_renderer_needs_semantic_human_view(self) -> None:
        text = '<!DOCTYPE html><html><head><script type="application/json" id="skill-meta">{"node_type":"leaf","source_dir":"fixture/","summary":"fixture","self_path":"fixture/SKILL.html","title":"fixture"}</script></head><body><header data-skill-header="1"><nav><a href="../SKILL.html">Up</a><a href="../index.html">Home</a></nav></header><div>fixture body text that is long enough to inspect</div></body></html>'
        self.assertTrue(any("semantic <main> or <section>" in finding for finding in self.findings(text)))

    def test_parameterized_export_needs_preview_mount(self) -> None:
        text = page().replace(
            '"explorer": "../web/_skill_explorer.js"',
            '"explorer": "../web/_skill_explorer.js", "exports": [{"id":"review-csv","label":"Review CSV","format":"csv","preview_mount":"review-preview","command":"python3 fixture/export.py","parameters":["--output <path>"]}]',
        )
        self.assertTrue(any("preview mount #review-preview is missing" in finding for finding in self.findings(text)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
