#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation tests for the exhaustive CORS relay projection contract."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.security import audit_cors_proxy_projection as audit


class CorsProxyProjectionAuditTests(unittest.TestCase):
    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "deployable"
        shutil.copytree(audit.PROJECTION, root)
        return temporary, root

    def assert_fails(self, root: Path, phrase: str) -> None:
        self.assertTrue(
            any(phrase in finding for finding in audit.audit(root)),
            msg=f"missing detector for {phrase}: {audit.audit(root)}",
        )

    def test_current_projection_passes(self) -> None:
        self.assertEqual([], audit.audit())

    def test_node_request_and_websocket_suites_pass(self) -> None:
        tests = sorted(
            str(path.relative_to(audit.ROOT))
            for path in (audit.PROJECTION / "test").glob("*.test.mjs")
        )
        result = subprocess.run(
            ["node", "--test", *tests],
            cwd=audit.ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, msg=result.stdout + result.stderr)

    def test_new_and_removed_files_are_discovered_without_registration(self) -> None:
        temporary, root = self.fixture()
        with temporary:
            (root / "new-source.mjs").write_text(
                "// SPDX-License-Identifier: Apache-2.0\nexport default true;\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "unrecorded file new-source.mjs")
            (root / "new-source.mjs").unlink()
            manifest = json.loads((root / audit.MANIFEST_NAME).read_text(encoding="utf-8"))
            removed = next(iter(manifest["files"]))
            (root / removed).unlink()
            self.assert_fails(root, f"missing recorded file {removed}")

    def test_changed_bytes_and_missing_spdx_fail(self) -> None:
        temporary, root = self.fixture()
        with temporary:
            target = root / "src" / "proxy.mjs"
            target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            self.assert_fails(root, "SHA-256 differs")
            text = target.read_text(encoding="utf-8").replace(audit.SPDX, "license omitted")
            target.write_text(text, encoding="utf-8")
            self.assert_fails(root, "missing Apache-2.0 SPDX header")

    def test_environment_identifiers_fail(self) -> None:
        mutations = {
            "bucket": "s3" + "://operator-prod-state/key",
            "account": "arn:aws:iam::" + "123456789012" + ":role/example",
            "zone": "Z" + "1234567890ABC",
            "distribution": "d" + "1234567890.cloudfront" + ".net",
            "operated host": "relay" + ".experiments.courses.nvidia.com",
            "private source": "https://gitlab" + ".com/nvidia/dli/platform/example",
        }
        for label, value in mutations.items():
            with self.subTest(label=label):
                temporary, root = self.fixture()
                with temporary:
                    target = root / "README.md"
                    target.write_text(target.read_text(encoding="utf-8") + f"\n{value}\n", encoding="utf-8")
                    self.assertNotEqual([], audit.audit(root))

    def test_local_state_and_symlinks_fail(self) -> None:
        temporary, root = self.fixture()
        with temporary:
            (root / "operator-values.json").write_text(
                '{"bucket":"' + "s3" + '://operator-private-name/key"}\n',
                encoding="utf-8",
            )
            self.assert_fails(root, "concrete object-store bucket")
            (root / "linked").symlink_to(root / "README.md")
            self.assert_fails(root, "symlinks are not allowed")


if __name__ == "__main__":
    unittest.main()
