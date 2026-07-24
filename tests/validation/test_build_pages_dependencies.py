# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Behavioral tests for Pages build dependency boundaries."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "scripts/build/build_pages.sh"


class BuildPagesDependencyTests(unittest.TestCase):
    def run_preflight(self, *, pull_materials: bool) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="pages-dependency-preflight-") as directory:
            root = Path(directory)
            binary = root / "bin"
            binary.mkdir()
            python = binary / "python3"
            python.write_text(
                "#!/bin/sh\n"
                'case " $* " in\n'
                '  *" --require-material-tools "*)\n'
                '    echo "python environment: FAIL (missing material tools: requests, bs4, markdownify, lxml)" >&2\n'
                "    exit 2\n"
                "    ;;\n"
                "  *)\n"
                '    echo "python environment: OK (test probe)"\n'
                "    exit 0\n"
                "    ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "PATH": f"{binary}{os.pathsep}{env['PATH']}",
                "BUILD_PAGES_PULL_MATERIALS": "1" if pull_materials else "0",
                "BUILD_PAGES_REUSE_VALIDATION": "0" if pull_materials else "1",
                "BUILD_PAGES_PREFLIGHT_ONLY": "1",
            })
            return subprocess.run(
                ["bash", str(BUILD), str(root / "public")],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

    def test_no_fetch_build_does_not_require_material_scrapers(self) -> None:
        result = self.run_preflight(pull_materials=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("environment preflight complete", result.stdout)

    def test_live_material_build_still_requires_scraper_lock(self) -> None:
        result = self.run_preflight(pull_materials=True)
        self.assertEqual(2, result.returncode)
        self.assertIn("missing material tools", result.stderr)


if __name__ == "__main__":
    unittest.main()
