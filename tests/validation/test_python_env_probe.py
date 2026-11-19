# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The shared Python probe enforces the tooling floor and the stricter material-tool floor."""
import contextlib
import io
import types
import unittest
from unittest import mock

from scripts.runtime import python_env_probe as probe


def run_probe(version, *args, installed=True):
    """Run the probe as if under Python `version`; return (exit code, stdout, stderr)."""
    fake_sys = types.SimpleNamespace(
        version_info=version, prefix="/venv", base_prefix="/usr", stderr=io.StringIO()
    )
    stdout = io.StringIO()
    find_spec = (lambda name: object()) if installed else (lambda name: None)
    with mock.patch.object(probe, "sys", fake_sys), \
            mock.patch("sys.argv", ["python_env_probe.py", *args]), \
            mock.patch.object(probe.importlib.util, "find_spec", find_spec), \
            contextlib.redirect_stdout(stdout):
        code = probe.main()
    return code, stdout.getvalue(), fake_sys.stderr.getvalue()


class PythonEnvProbeTests(unittest.TestCase):
    def test_material_tools_require_the_material_floor(self):
        code, _, err = run_probe((3, 11, 4, "final", 0), "--require-material-tools")
        self.assertEqual(code, 2)
        self.assertIn("found 3.11.4; material tools require Python 3.11.5+", err)

    def test_material_floor_accepts_its_exact_release(self):
        code, out, _ = run_probe((3, 11, 5, "final", 0), "--require-material-tools")
        self.assertEqual(code, 0)
        self.assertIn("python environment: OK (3.11", out)

    def test_material_floor_runs_before_the_import_check(self):
        code, _, err = run_probe((3, 11, 0, "final", 0), "--require-material-tools", installed=False)
        self.assertEqual(code, 2)
        self.assertIn("material tools require Python 3.11.5+", err)
        self.assertNotIn("missing material tools", err)

    def test_other_tooling_keeps_the_general_floor(self):
        self.assertEqual(run_probe((3, 11, 0, "final", 0))[0], 0)
        code, _, err = run_probe((3, 10, 14, "final", 0))
        self.assertEqual(code, 2)
        self.assertIn("Python 3.11+ is required", err)


if __name__ == "__main__":
    unittest.main()
