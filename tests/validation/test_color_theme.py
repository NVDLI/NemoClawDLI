# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standard-library tests for exhaustive color-theme source coverage."""
from __future__ import annotations

import unittest

from scripts.validation import color_theme


class ColorThemeTests(unittest.TestCase):
    def test_page_discovery_has_no_named_opt_outs(self) -> None:
        names = {path.name for path in color_theme.page_html()}
        self.assertTrue({"SKILL.html", "courses.html", "studio.html"}.issubset(names))

    def test_chrome_discovery_includes_studio(self) -> None:
        names = {path.name for path in color_theme.chrome_js()}
        self.assertIn("studio_main.js", names)

    def test_stylesheet_discovery_includes_every_web_course(self) -> None:
        paths = {path.relative_to(color_theme.WEB).as_posix() for path in color_theme.style_files()}
        self.assertIn("nemoclaw/styles/_style.css", paths)

    def test_os_only_palette_is_rejected(self) -> None:
        source = '@media (prefers-color-scheme: light) { :root { --bg: #fff; } }'
        self.assertTrue(color_theme.scan_palette_contract(source))
        source += ':root[data-theme="light"] { --bg: #fff; }'
        self.assertFalse(color_theme.scan_palette_contract(source))

    def test_inline_literal_is_rejected(self) -> None:
        self.assertTrue(color_theme.scan_inline('<div style="color:#f2f2f2">text</div>'))

    def test_injected_stylesheet_literal_is_rejected(self) -> None:
        source = "const style=document.createElement('style');style.textContent=`.panel{background:#161616}`;"
        self.assertTrue(color_theme.scan_style_blocks(source))

    def test_render_time_color_bake_is_rejected(self) -> None:
        source = "const c=getComputedStyle(node).color; return `<path fill=\"${c}\"/>`;"
        self.assertTrue(color_theme.scan_js_theme_bake(source))

    def test_skill_row_theme_projection_covers_text_and_layout(self) -> None:
        explorer = (color_theme.WEB / "_skill_explorer.js").read_text()
        for selector in (".skill-link span", ".skill-link b", ".skill-list", ".skill-link{"):
            self.assertIn(selector, explorer)


if __name__ == "__main__":
    unittest.main()
