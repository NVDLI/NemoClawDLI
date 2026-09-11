# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise the published assistant interface with a real browser."""
from pathlib import Path
import unittest
from scripts.runtime.host_browser import run_node


class AssistantDialogTests(unittest.TestCase):
    def test_modal_keyboard_and_service_links(self):
        result = run_node(
            Path(__file__).resolve().parents[1] / 'runtime/check_assistant_dialog.mjs',
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
