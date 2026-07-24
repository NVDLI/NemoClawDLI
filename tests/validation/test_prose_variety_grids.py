# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Grid checks distinguish promotional cards from evidence previews."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.validation import prose_variety


class GridStructureTests(unittest.TestCase):
    @staticmethod
    def findings(body: str) -> list[tuple[str, str]]:
        with tempfile.TemporaryDirectory(prefix="prose-grid-") as temp:
            page = Path(temp) / "page.html"
            page.write_text(body)
            return prose_variety._grid_findings(page)

    def test_responsive_evidence_gallery_is_not_a_card_wall(self) -> None:
        card = (
            '<article class="pv-card"><div class="pv-prev">preview</div>'
            '<div class="pv-meta">Source</div><a href="source.html">evidence</a></article>'
        )
        html = (
            '<style>.pv-grid{display:grid;grid-template-columns:'
            'repeat(auto-fill,minmax(270px,1fr))}</style><body>'
            '<div class="pv-grid">' + card * 11 + '</div></body>'
        )
        self.assertEqual([], self.findings(html))

    def test_generic_card_wall_remains_visible(self) -> None:
        card = '<article class="promo-card"><a href="item.html">item</a></article>'
        html = '<style>.tile-grid{display:grid}</style><body>' + card * 10 + '</body>'
        kinds = [kind for kind, _ in self.findings(html)]
        self.assertIn("flashy-page", kinds)


if __name__ == "__main__":
    unittest.main()
