# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.validation import cell_audit


class CellSignalContractTests(unittest.TestCase):
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
                for old, expected in [
                    ('bindRunSignal(helpers, ac.signal)', 'RunCell must bind'),
                    ('bindRunSignal(helpers, _sig)', 'CanvasFlow must bind'),
                    ('delay(ms, ownSignal)', 'shared invocation binding'),
                    ('signal: value.signal ?? signal', 'shared invocation binding'),
                ]:
                    changed = source.replace(old, 'removed_binding', 1)
                    self.assertNotEqual(source, changed)
                    path.write_text(changed)
                    self.assertTrue(any(expected in message for _, message in cell_audit.audit_runtime_contract()))
