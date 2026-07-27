# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise the shared foyer branch resolver across root and localized paths."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _bootstrap import add_script_paths  # noqa: E402

add_script_paths(ROOT / "scripts")
from translate.locale_catalog import discover_locales  # noqa: E402
from translate.locale_pages import published_pages  # noqa: E402

FOYER = "web/index.html"


def foyer_pages() -> dict[str, str]:
    """Return the canonical foyer and every discovered locale's published foyer.

    A locale foyer is the bytes the build publishes, whether they come from a reviewed HTML
    overlay or a key-based resource. Reading the locale tree directly would drop coverage of
    every migrated locale instead of failing.
    """
    published = published_pages(ROOT)
    pages = {FOYER: (ROOT / FOYER).read_text(encoding="utf-8")}
    for spec in discover_locales(ROOT):
        relative = (spec.locale_root / FOYER).relative_to(ROOT).as_posix()
        if relative not in published:
            raise AssertionError(f"{spec.locale} publishes no foyer at {relative}")
        pages[relative] = published[relative]
    return pages


def resolver_source(page: str, raw: str) -> str:
    match = re.search(
        r"(function sameOriginUrl\(raw, base\) \{.*?\n  \})\n"
        r"  (function targetUrl\(branch, manifestUrl\) \{.*?\n  \})",
        raw,
        re.DOTALL,
    )
    if not match:
        raise AssertionError(f"branch resolver missing from {page}")
    return "\n".join(match.groups())


class FoyerBranchPathTests(unittest.TestCase):
    def test_localized_foyers_share_the_canonical_resolver(self) -> None:
        sources = {page: resolver_source(page, raw) for page, raw in foyer_pages().items()}
        self.assertGreater(len(sources), 1)
        for page, source in sources.items():
            self.assertEqual(sources[FOYER], source, page)

    def test_resolver_uses_each_manifest_as_its_navigation_authority(self) -> None:
        source = resolver_source(FOYER, (ROOT / FOYER).read_text(encoding="utf-8"))
        cases = (
            ("https://example.test/project/branches.json", "nemoclaw/", "https://example.test/project/nemoclaw/"),
            ("https://example.test/project/topic/branches.json", "web/nemoclaw/", "https://example.test/project/topic/web/nemoclaw/"),
            ("https://example.test/project/i18n/es/branches.json", "../../nemoclaw/", "https://example.test/project/nemoclaw/"),
            ("https://example.test/project/validated-source/branches.json", "../web/nemoclaw/", "https://example.test/project/web/nemoclaw/"),
        )
        script = source + """
const cases = JSON.parse(process.argv[2]);
globalThis.window = { location: new URL('https://example.test/project/index.html') };
const results = cases.map(([manifestUrl, url]) => {
  return targetUrl({ url }, new URL(manifestUrl));
});
process.stdout.write(JSON.stringify(results));
"""
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / "foyer-branch-paths.mjs"
            runner.write_text(script, encoding="utf-8")
            result = subprocess.run(
                [
                    "bash",
                    "scripts/runtime/run_node.sh",
                    str(runner),
                    json.dumps([case[:2] for case in cases]),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual([case[2] for case in cases], json.loads(result.stdout))

    def test_resolver_rejects_cross_origin_manifest_entries(self) -> None:
        source = resolver_source(FOYER, (ROOT / FOYER).read_text(encoding="utf-8"))
        script = source + """
globalThis.window = { location: new URL('https://example.test/project/index.html') };
process.stdout.write(JSON.stringify(targetUrl({url:'https://evil.example/course/'}, new URL('https://example.test/project/branches.json'))));
"""
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / "foyer-cross-origin.mjs"
            runner.write_text(script, encoding="utf-8")
            result = subprocess.run(
                ["bash", "scripts/runtime/run_node.sh", str(runner)],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIsNone(json.loads(result.stdout))


if __name__ == "__main__":
    unittest.main()
