# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.validation import cell_audit


class CellSignalContractTests(unittest.TestCase):
    def test_default_visibility_matches_the_bounded_shared_runtime_rule(self):
        short = "\n".join(["line"] * cell_audit.CANVAS_DEFAULT_VISIBLE_MAX_LINES)
        long = short + "\nline"
        for flag in ("showCode: true", "openCode: true"):
            with self.subTest(flag=flag):
                block = f'mountCanvasFlow("#example", {{ {flag}, code: `{long}` }});'
                start = block.index("`", block.index("code:")) + 1
                self.assertFalse(cell_audit._is_visible_cell(block, start, long.count("\n") + 1, True))
        short_block = f'mountCanvasFlow("#example", {{ showCode: true, code: `{short}` }});'
        short_start = short_block.index("`", short_block.index("code:")) + 1
        self.assertTrue(cell_audit._is_visible_cell(short_block, short_start, short.count("\n") + 1, True))
        hidden_block = f'mountCanvasFlow("#example", {{ showCode: false, code: `{short}` }});'
        hidden_start = hidden_block.index("`", hidden_block.index("code:")) + 1
        self.assertFalse(cell_audit._is_visible_cell(hidden_block, hidden_start, short.count("\n") + 1, True))

    def test_shared_binding_and_each_current_invocation_are_required(self):
        original = cell_audit.WEB / 'nemoclaw/scripts'
        source = (original / '_canvas.js').read_text()
        with tempfile.TemporaryDirectory() as folder:
            web = Path(folder)
            scripts = web / 'nemoclaw/scripts'
            scripts.mkdir(parents=True)
            (scripts / '_shared.js').write_text((original / '_shared.js').read_text())
            path = scripts / '_canvas.js'
            path.write_text(source)
            with patch.object(cell_audit, 'WEB', web):
                self.assertEqual(cell_audit.audit_runtime_contract(), [])
                unbounded = source.replace(
                    'const codeOpenAttr = _cellCodeOpen(opts, code) ? " open" : "";',
                    'const codeOpenAttr = opts.openCode === true ? " open" : "";',
                    1,
                )
                path.write_text(unbounded)
                self.assertTrue(any('former unbounded openCode expression' in message
                                    for _, message in cell_audit.audit_runtime_contract()))
                for old, expected in [
                    ('const codeOpenAttr = _cellCodeOpen(opts, code) ? " open" : "";', 'shared bounded visibility helper'),
                    ('if (lines > CELL_CANVAS_VISIBLE_LINES) return false;', 'line cap'),
                    ('const _showCode = _cellCodeOpen(node, node.code, "canvas");', 'same bounded visibility rule'),
                    ('bindRunSignal(helpers, ac.signal)', 'RunCell must bind'),
                    ('bindRunSignal(helpers, _sig)', 'CanvasFlow must bind'),
                    ('delay(ms, ownSignal)', 'shared invocation binding'),
                    ('signal: value.signal ?? signal', 'shared invocation binding'),
                ]:
                    changed = source.replace(old, 'removed_binding', 1)
                    self.assertNotEqual(source, changed)
                    path.write_text(changed)
                    self.assertTrue(any(expected in message for _, message in cell_audit.audit_runtime_contract()))
