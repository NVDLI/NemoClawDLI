# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.runtime import host_browser


class HostBrowserTests(unittest.TestCase):
    def test_resolver_finds_a_full_playwright_chromium_install(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            browser = Path(directory) / "chromium-1" / "chrome-linux" / "chrome"
            browser.parent.mkdir(parents=True)
            browser.write_text("browser")
            browser.chmod(0o755)
            environment = {
                "PLAYWRIGHT_BROWSERS_PATH": directory,
                "HOME": str(Path(directory) / "home"),
            }
            original = host_browser.executable

            def fixture_executable(value: str | None) -> str | None:
                if value in {"chromium", "chromium-browser", "google-chrome", "google-chrome-stable"}:
                    return None
                return original(value)

            with patch.dict(os.environ, environment, clear=True), patch.object(
                host_browser, "executable", side_effect=fixture_executable,
            ):
                self.assertEqual(str(browser.resolve()), host_browser.resolve_chrome())


if __name__ == "__main__":
    unittest.main()
