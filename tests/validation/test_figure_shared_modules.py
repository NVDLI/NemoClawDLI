# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise figure rendering through course-relative shared module imports."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'scripts/figures/check_figures.mjs'


class FigureSharedModuleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='figure-shared-modules-')
        self.addCleanup(self.temporary.cleanup)
        self.web = Path(self.temporary.name) / 'nested' / 'web'
        self.course = self.web / 'new course'
        (self.course / 'scripts').mkdir(parents=True)
        self.module = self.web / 'shared' / 'novel' / 'drawing.js'
        self.module.parent.mkdir(parents=True)
        self.module.write_text('export const label = "shared module rendered";')
        self.write_import(self.module.name)

    def write_import(self, name):
        (self.course / 'scripts/_shared.js').write_text(
            f'import {{ label }} from "../../shared/novel/{name}";\n'
            'export function mountPolicyMap(selector) {\n'
            '  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");\n'
            '  svg.classList.add("pmap-svg");\n'
            '  svg.innerHTML = "<text>" + label + "</text>";\n'
            '  document.querySelector(selector).append(svg);\n'
            '}\n'
        )

    def render(self):
        source = SOURCE.read_text()
        function = 'async function renderedPolicyMap()' + source.split(
            'async function renderedPolicyMap()', 1)[1].split('const MONO', 1)[0]
        program = (
            'import fs from "fs"; import http from "http"; import path from "path";\n'
            'import { createRequire } from "module";\n'
            'const require = createRequire(process.cwd() + "/figure-harness.cjs");\n'
            'const { chromium } = require("playwright-core");\n'
            'const NEMO = process.env.FIG_NEMO;\n' + function +
            '\nconsole.log(await renderedPolicyMap());\n'
        )
        return subprocess.run(
            ['node', '--input-type=module', '-e', program], cwd=ROOT,
            env={**os.environ, 'FIG_NEMO': str(self.course)}, capture_output=True,
            text=True, timeout=45, check=False,
        )

    def test_new_course_and_shared_module_render_in_browser(self):
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('shared module rendered', result.stdout)

    def test_deleted_and_renamed_module_keep_real_import_failures(self):
        renamed = self.module.with_name('renamed.mjs')
        self.module.rename(renamed)
        self.assertNotEqual(self.render().returncode, 0)
        self.write_import(renamed.name)
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        renamed.unlink()
        self.assertNotEqual(self.render().returncode, 0)

    def test_directory_and_malformed_module_do_not_pass(self):
        self.module.unlink()
        self.module.mkdir()
        self.assertNotEqual(self.render().returncode, 0)
        self.module.rmdir()
        self.module.write_text('export const label = ;')
        self.assertNotEqual(self.render().returncode, 0)


if __name__ == '__main__':
    unittest.main()
