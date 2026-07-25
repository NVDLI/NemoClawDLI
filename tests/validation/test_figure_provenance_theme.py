# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Contracts for exhaustive, provenance-derived figure theme validation."""
from __future__ import annotations

import unittest
from pathlib import Path
from urllib.parse import urlparse

from scripts.validation import color_theme, figure_audit
from scripts.validation.figure_provenance import (
    fixed_white_figures,
    remote_figure_rows,
    svg_modes,
    svg_semantic_contracts,
)


ROOT = Path(__file__).resolve().parents[2]


class FigureProvenanceThemeTests(unittest.TestCase):
    def test_every_canonical_svg_is_classified(self) -> None:
        actual = {
            f"figures/{path.name}"
            for path in (ROOT / "web/nemoclaw/assets/figures").glob("*.svg")
        }
        self.assertEqual(actual, set(svg_modes()))

    def test_fixed_white_set_is_derived_without_filename_allowlist(self) -> None:
        source = (ROOT / "scripts/validation/color_theme.py").read_text(encoding="utf-8")
        self.assertEqual(
            fixed_white_figures(),
            frozenset(name for name, mode in svg_modes().items() if mode == "fixed-white"),
        )
        self.assertNotIn("PAPER_ONLY_FIGURES", source)
        self.assertNotIn('{"fig2_react.svg", "fig2_rewoo.svg"}', source)

    def test_theme_contract_rejects_bypass_attempts(self) -> None:
        safe = '<svg class="gfx-dark"><rect fill="var(--gfx-bg)"/></svg>'
        cases = [
            (
                {"figures/probe.svg": "theme-aware"},
                {"figures/probe.svg": '<svg class="other"></svg>'},
                {"probe.html": '<div data-svg-src="assets/figures/probe.svg"></div>'},
                "gfx-dark",
            ),
            (
                {"figures/probe.svg": "theme-aware"},
                {"figures/probe.svg": safe},
                {"probe.html": '<div data-figure-mode="fixed-white" data-svg-src="assets/figures/probe.svg"></div>'},
                "cannot be relabeled",
            ),
            (
                {"figures/probe.svg": "fixed-white"},
                {"figures/probe.svg": "<svg></svg>"},
                {"probe.html": '<div data-svg-src="assets/figures/probe.svg"></div>'},
                "data-figure-mode",
            ),
        ]
        for modes, figures, pages, expected in cases:
            with self.subTest(expected=expected):
                findings = figure_audit._provenance_theme_findings(modes, figures, pages)
                self.assertTrue(any(expected in message for _path, message in findings), findings)

    def test_current_tree_satisfies_required_figure_contract(self) -> None:
        self.assertEqual([], figure_audit._provenance_theme_contract())
        self.assertEqual([], figure_audit._semantic_contract())

    def test_semantic_contract_rejects_bypass_attempts(self) -> None:
        contract = {"figures/probe.svg": {"type": "directed-flow", "flows": [
            {"from": "source", "to": "target", "label": "signal"},
        ]}}
        safe = ('<svg aria-label="Signal flows from source to target.">'
                '<path data-flow-from="source" data-flow-to="target" data-flow-label="signal"/>'
                '<text data-flow-label="signal">signal</text></svg>')
        self.assertEqual([], figure_audit._semantic_contract_findings(
            contract, {"figures/probe.svg": safe},
        ))
        cases = (
            (safe.replace('data-flow-from="source"', 'data-form="source"', 1),
             "expected one marked path"),
            (safe.replace(">signal</text>", ">value</text>", 1),
             "matching visible text label"),
            (safe.replace('aria-label="Signal flows from source to target."',
                          'aria-label="Connected boxes."', 1),
             "SVG aria-label"),
        )
        for source, expected in cases:
            with self.subTest(expected=expected):
                findings = figure_audit._semantic_contract_findings(
                    contract, {"figures/probe.svg": source},
                )
                self.assertTrue(any(expected in message for _path, message in findings), findings)

    def test_marked_directed_flow_cannot_skip_provenance_contract(self) -> None:
        marked = '<svg><path data-flow-from="source" data-flow-to="target" data-flow-label="signal"/></svg>'
        findings = figure_audit._semantic_contract_findings({}, {"figures/new.svg": marked})
        self.assertTrue(any("lacks an image-provenance semantic contract" in message
                            for _path, message in findings), findings)

    def test_semantic_registry_is_provenance_derived(self) -> None:
        contracts = svg_semantic_contracts()
        self.assertIn("figures/01a-agent-environment.svg", contracts)
        source = (ROOT / "scripts/validation/figure_provenance.py").read_text(encoding="utf-8")
        self.assertNotIn("01a-agent-environment.svg", source)

    def test_remote_images_share_the_common_provenance_contract(self) -> None:
        rows = remote_figure_rows()
        self.assertTrue(rows)
        for row in rows:
            with self.subTest(image_url=row.get("image_url")):
                self.assertNotIn("file", row)
                self.assertTrue(str(row.get("image_url", "")).startswith("https://"))
                self.assertEqual("not copied into this repository", row.get("distribution"))
                self.assertTrue(row.get("license"))
                self.assertTrue(row.get("source_authors"))

    def test_remote_images_are_not_copied_into_language_trees(self) -> None:
        for row in remote_figure_rows():
            source_name = Path(urlparse(str(row["image_url"])).path).name
            with self.subTest(source_name=source_name):
                self.assertFalse(list(ROOT.glob(f"web/nemoclaw/assets/figures/{source_name}")))
                self.assertFalse(list(ROOT.glob(f"i18n/*/web/nemoclaw/assets/figures/{source_name}")))


if __name__ == "__main__":
    unittest.main()
