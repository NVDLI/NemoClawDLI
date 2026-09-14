# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.runtime import host_browser


class HostBrowserTests(unittest.TestCase):
    def test_relative_override_uses_the_callers_working_directory(self) -> None:
        node, modules = host_browser.resolve_node(), host_browser.resolve_node_path()
        with tempfile.TemporaryDirectory() as directory:
            browser = Path(directory) / "selected-browser"
            browser.write_text("browser fixture")
            browser.chmod(0o755)
            with contextlib.chdir(directory), patch.dict(os.environ, {
                "NODE_BIN": node, "NODE_PATH": modules, "PATH": "",
                "CHROME_BIN": "./selected-browser",
            }):
                self.assertEqual(str(browser), host_browser.resolve_chrome())

    def test_python_adapter_uses_shared_owner_and_validates_its_result(self) -> None:
        for result in (
            subprocess.CompletedProcess([], 0, "/bin/sh", ""),
            subprocess.CompletedProcess([], 0, "/missing/browser", ""),
            subprocess.CompletedProcess([], 1, "/bin/sh", "discovery failed"),
            subprocess.TimeoutExpired("node", 10),
        ):
            with self.subTest(result=result), patch.object(host_browser, "resolve_node", return_value="node"), patch.object(
                host_browser, "resolve_node_path", return_value="/modules",
            ), patch.object(host_browser.subprocess, "run", **(
                {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
            )):
                if isinstance(result, subprocess.CompletedProcess) and result.returncode == 0 and result.stdout == "/bin/sh":
                    self.assertEqual(str(Path("/bin/sh").resolve()), host_browser.resolve_chrome())
                else:
                    with self.assertRaises(host_browser.BrowserRuntimeError):
                        host_browser.resolve_chrome()


class BrowserDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.node = host_browser.resolve_node()
        self.owner = self.root / "novel" / "renamed-owner.cjs"
        self.owner.parent.mkdir()
        shutil.copyfile(host_browser.ROOT / "scripts/runtime/browser_environment.cjs", self.owner)
        package = self.owner.parent / "node_modules/playwright-core"
        package.mkdir(parents=True)
        (package / "package.json").write_text('{"name":"playwright-core","main":"index.js"}')
        (package / "index.js").write_text(
            "exports.chromium = {executablePath() { if (process.env.FIXTURE_THROW) throw new Error('unavailable'); "
            "return process.env.FIXTURE_BROWSER; }};"
        )
        self.environment = {"PATH": str(self.root / "bin"), "HOME": str(self.root),
                            "PLAYWRIGHT_BROWSERS_PATH": str(self.root / "cache")}

    def browser(self, name: str) -> Path:
        browser = self.root / name
        browser.parent.mkdir(parents=True, exist_ok=True)
        browser.write_text("browser")
        browser.chmod(0o755)
        return browser

    def discover(self, **environment: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([self.node, str(self.owner), "--chrome"],
                              env={**self.environment, **environment}, capture_output=True, text=True, timeout=15)

    def test_package_metadata_accepts_novel_and_renamed_platform_layouts(self) -> None:
        for name in ("chromium-1243/chrome-linux-arm64/chrome", "future/new-platform/browser"):
            with self.subTest(name=name):
                browser = self.browser(name)
                result = self.discover(FIXTURE_BROWSER=str(browser))
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(str(browser.resolve()), result.stdout.strip())
                browser.unlink()
                self.assertNotEqual(0, self.discover(FIXTURE_BROWSER=str(browser)).returncode)

    def test_nonexecutable_directory_and_malformed_metadata_are_rejected(self) -> None:
        plain = self.browser("plain")
        plain.chmod(0o644)
        for value in (str(plain), str(self.root), "malformed\noutput", ""):
            with self.subTest(value=value):
                result = self.discover(FIXTURE_BROWSER=value)
                self.assertNotEqual(0, result.returncode)
                self.assertIn("Chromium", result.stderr)

    def test_explicit_override_and_system_browser_precede_package_metadata(self) -> None:
        metadata = self.browser("metadata/chrome")
        system = self.browser("bin/chromium")
        explicit = self.browser("explicit/chrome")
        result = self.discover(FIXTURE_BROWSER=str(metadata), CHROME_BIN=str(explicit))
        self.assertEqual(str(explicit), result.stdout.strip())
        result = self.discover(FIXTURE_BROWSER=str(metadata))
        self.assertEqual(str(system), result.stdout.strip())

    def test_legacy_cache_remains_supported_and_invalid_files_do_not_pass(self) -> None:
        browser = self.browser("cache/chromium-1/chrome-linux/chrome")
        result = self.discover(FIXTURE_THROW="1")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(str(browser), result.stdout.strip())
        browser.chmod(0o644)
        self.assertNotEqual(0, self.discover(FIXTURE_THROW="1").returncode)


if __name__ == "__main__":
    unittest.main()
