# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise discovered browser linkage using the release compiler, without source mocks."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/runtime'))
from module_check import check_root, discover_roots


class ModuleLinkageTests(unittest.TestCase):
    def check(self, files):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, source in files.items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding='utf-8')
            return check_root(root)[0]

    def test_missing_import_forms_and_broken_export_chains_fail(self):
        invalid = [
            "import missing from './leaf.mjs'; console.log(missing)",
            "import {missing} from './leaf.mjs'; console.log(missing)",
            "import * as leaf from './leaf.mjs'; console.log(leaf.missing)",
            "import './absent.mjs'",
            "export {missing} from './leaf.mjs'",
            "export * from './absent.mjs'",
            "import('./absent.mjs')",
            "export { neverDefined }",
        ]
        for source in invalid:
            with self.subTest(source=source):
                self.assertTrue(self.check({'entry.js': source, 'leaf.mjs': 'export const present = 1;'}))

    def test_novel_nested_module_rename_and_deletion_enter_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            course = root / 'new-course/deep'
            course.mkdir(parents=True)
            (course.parent / 'interface-inventory.json').write_text('{}')
            self.assertEqual(discover_roots(root), [root])
            entry = course / 'entry.mjs'
            leaf = course / 'leaf.mjs'
            entry.write_text("import value from './leaf.mjs'; console.log(value)")
            leaf.write_text('export default 42')
            self.assertEqual(check_root(root)[0], [])
            renamed = leaf.with_name('renamed.mjs')
            leaf.rename(renamed)
            self.assertTrue(check_root(root)[0])
            entry.write_text("import value from './renamed.mjs'; console.log(value)")
            self.assertEqual(check_root(root)[0], [])
            renamed.unlink()
            self.assertTrue(check_root(root)[0])
            entry.unlink()
            self.assertEqual(check_root(root)[0], [])

    def test_real_html_module_boundaries_and_relative_paths(self):
        self.assertEqual(self.check({
            'course/page.html': '<script type="module">import {value} from "../shared/bridge.js"; console.log(value)</script>',
            'shared/bridge.js': "export {default as value} from './leaf.mjs'",
            'shared/leaf.mjs': 'export default 42',
        }), [])
        self.assertTrue(self.check({'page.html': '<script type="module" src="./missing.mjs"></script>'}))
        self.assertTrue(self.check({'page.html': '<script type="module">import "./missing.mjs"</script >'}))
        self.assertEqual(self.check({'page.html': '<p>import {missing} from "./none.js"</p><script>const example = "import {missing} from \'./none.js\'";</script>'}), [])

    def test_script_urls_resolve_browser_query_fragment_and_encoded_path(self):
        self.assertEqual(self.check({
            'course/page.html': '<script type="module" src="./runtime%20module.mjs?v=1#entry"></script>',
            'course/runtime module.mjs': 'export const value = 1;',
        }), [])

    def test_known_node_runtime_dependencies_are_explicit_and_unknown_imports_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = root / 'universal.mjs'
            entry.write_text("export async function init() { await import('node:fs'); require('path'); }")
            findings, _, obligations = check_root(root)
            self.assertEqual(findings, [])
            self.assertTrue(any('dynamic-import node:fs (Node runtime required)' in row for row in obligations))
            self.assertTrue(any('require-call path (Node runtime required)' in row for row in obligations))
            for source in ("import fs from 'node:fs'; console.log(fs)",
                           "import('node:nonexistent-module')", "import('missing-package')",
                           "require('missing-package')", "import('./missing.mjs')"):
                entry.write_text(source)
                self.assertTrue(check_root(root)[0], source)
            entry.rename(entry.with_suffix('.js'))
            self.assertTrue(check_root(root)[0])
            entry.with_suffix('.js').unlink()
            self.assertEqual(check_root(root)[0], [])

    def test_runtime_package_resolution_requires_the_nearest_valid_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'nested/universal'
            package.mkdir(parents=True)
            metadata = package / 'package.json'
            metadata.write_text('{"name":"fixture-runtime","version":"1.0.0","dependencies":{"fixture-host-backend":"^1.0.0"}}')
            entry = package / 'novel.mjs'
            entry.write_text("export async function init() { return import('fixture-host-backend'); }")
            findings, _, obligations = check_root(root)
            self.assertEqual(findings, [])
            self.assertTrue(any('declared by' in row and 'package.json' in row for row in obligations))
            outside = root / 'new-course.mjs'
            outside.write_text(entry.read_text())
            self.assertTrue(check_root(root)[0], 'a new course outside the package must not inherit its declarations')
            outside.unlink()
            renamed = metadata.with_name('renamed-package.json')
            metadata.rename(renamed)
            self.assertTrue(check_root(root)[0], 'renamed metadata cannot establish package ownership')
            renamed.rename(metadata)
            saved = metadata.read_text()
            for malformed in ('{', '{"dependencies":null}', '{"dependencies":[]}',
                              '{"dependencies":{"fixture-host-backend":false}}'):
                metadata.write_text(malformed)
                self.assertTrue(check_root(root)[0], malformed)
            metadata.write_text(saved)
            for code in ("import('fixture-host-backend/nonexistent')", "import('unknown-backend')",
                         "import value from 'fixture-host-backend'; console.log(value)"):
                entry.write_text(code)
                self.assertTrue(check_root(root)[0], code)
            entry.write_text("require('fixture-host-backend')")
            self.assertEqual(check_root(root)[0], [])
            metadata.unlink()
            self.assertTrue(check_root(root)[0], 'deleted metadata must expose an unresolved dependency')
            entry.unlink()
            self.assertEqual(check_root(root)[0], [])

    def test_duplicate_values_and_malformed_javascript_fail(self):
        for source in ('export const values = {value: 1, value: 2}', 'export const = ;'):
            self.assertTrue(self.check({'novel.js': source}))

    def test_public_html_does_not_exempt_unresolved_template_paths(self):
        self.assertTrue(self.check({'shared/page.template.html': '<script src="{{script}}"></script>'}))
        self.assertTrue(self.check({'shared/page.template.htm': '<script src="missing.js"></script>'}))


if __name__ == '__main__':
    unittest.main()
