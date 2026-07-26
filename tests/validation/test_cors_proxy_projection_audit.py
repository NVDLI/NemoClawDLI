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
            example = root / "infrastructure" / "terraform.tfvars.example"
            example.write_text(
                example.read_text(encoding="utf-8").replace(audit.SPDX, "license omitted"),
                encoding="utf-8",
            )
            self.assert_fails(root, "missing Apache-2.0 SPDX header")

    def test_terraform_contract_mutations_fail(self) -> None:
        mutations = {
            "backend": (
                "infrastructure/terraform.tf",
                'backend "s3" {}',
                'backend "local" {}',
                "operator-configured backend",
            ),
            "direct-origin header": (
                "infrastructure/main.tf",
                'name  = "x-dli-cors-proxy-secret"',
                'name  = "x-unreviewed-header"',
                "direct-origin shared header",
            ),
            "websocket route": (
                "infrastructure/main.tf",
                'path_pattern             = "/https/*/ws/terminal"',
                'path_pattern             = "/unreviewed/*"',
                "terminal WebSocket route",
            ),
            "operator region": (
                "infrastructure/variables.tf",
                'variable "aws_region" {\n',
                'variable "aws_region" {\n  default = "operator-picked-later"\n',
                "aws_region must be operator-supplied",
            ),
        }
        for label, (relative, before, after, finding) in mutations.items():
            with self.subTest(label=label):
                temporary, root = self.fixture()
                with temporary:
                    target = root / relative
                    text = target.read_text(encoding="utf-8")
                    self.assertIn(before, text)
                    target.write_text(text.replace(before, after, 1), encoding="utf-8")
                    self.assert_fails(root, finding)

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

    def test_manifest_cannot_hide_source_location_or_drop_reviewed_corrections(self) -> None:
        temporary, root = self.fixture()
        with temporary:
            path = root / audit.MANIFEST_NAME
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest["source_location"] = "https://gitlab.com/nvidia/dli/platform/private-relay"
            manifest["projection_transformations"] = [
                "combine source",
                "add headers",
                "replace values",
                "generic template",
            ]
            path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assert_fails(root, "private source location")
            self.assert_fails(root, "required projection corrections")
            self.assert_fails(root, "source location must remain public-safe")

    def test_documented_build_and_packaging_output_is_not_projected_source(self) -> None:
        temporary, root = self.fixture()
        with temporary:
            for relative in (
                "build/infrastructure.json",
                "build/cors-proxy-build-nvidia.zip",
                "build/lambda/src/proxy.mjs",
                "node_modules/left-pad/index.js",
                "deployment-state/notes.txt",
            ):
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("generated\n", encoding="utf-8")
            archive = root / "build" / "cors-proxy-build-nvidia.zip"
            archive.write_bytes(b"PK\x03\x04\xff\xfe\x00\x80packaged")
            self.assertEqual([], audit.audit(root))

    def test_a_committed_binary_outside_the_build_path_still_fails(self) -> None:
        temporary, root = self.fixture()
        with temporary:
            (root / "src" / "vendored.bin").write_bytes(b"\xff\xfe\x00\x80")
            self.assert_fails(root, "unexpected binary file")
            (root / "archive.zip").write_bytes(b"PK\x03\x04\xff\xfe\x00\x80")
            self.assert_fails(root, "unrecorded file archive.zip")

    def test_generated_directory_names_cannot_hide_nested_source(self) -> None:
        temporary, root = self.fixture()
        with temporary:
            target = root / "src" / "build" / "hidden.mjs"
            target.parent.mkdir()
            target.write_text(
                "// SPDX-License-Identifier: Apache-2.0\nexport default true;\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "unrecorded file src/build/hidden.mjs")

    def test_ignored_output_is_still_scanned_for_environment_identifiers(self) -> None:
        temporary, root = self.fixture()
        with temporary:
            target = root / "build" / "infrastructure.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                '{"bucket":"' + "s3" + '://operator-private-name/key"}\n', encoding="utf-8",
            )
            self.assert_fails(root, "concrete object-store bucket")

    def test_an_ignore_entry_cannot_hide_a_projected_file_even_after_refresh(self) -> None:
        temporary, root = self.fixture()
        with temporary:
            (root / ".gitignore").write_text(
                "build/\nsrc/\nnew-source.mjs\n", encoding="utf-8",
            )
            (root / "new-source.mjs").write_text(
                "// SPDX-License-Identifier: Apache-2.0\nexport default true;\n",
                encoding="utf-8",
            )
            self.assert_fails(root, "entries must exactly match")
            with self.assertRaisesRegex(ValueError, "entries must exactly match"):
                audit.refresh_manifest(root)
            self.assert_fails(root, "unrecorded file new-source.mjs")
            # Every recorded src/ file must still be verified.
            (root / "src" / "proxy.mjs").unlink()
            self.assert_fails(root, "missing recorded file src/proxy.mjs")

    def test_ignore_contract_drift_fails_closed(self) -> None:
        for label, pattern in {
            "added source directory": "src/",
            "added file": "new-source.mjs",
            "removed build directory": "",
            "wildcard": "operator-*.json",
        }.items():
            with self.subTest(label=label):
                temporary, root = self.fixture()
                with temporary:
                    entries = sorted(audit.EXPECTED_IGNORE_ENTRIES)
                    if label == "removed build directory":
                        entries.remove("build/")
                    else:
                        entries.append(pattern)
                    (root / ".gitignore").write_text("\n".join(entries) + "\n", encoding="utf-8")
                    self.assert_fails(root, "entries must exactly match")

    def test_environment_identifier_variants_fail_without_file_opt_ins(self) -> None:
        mutations = {
            "account field": 'account_id = "' + "123456789012" + '"',
            "bucket field": 'backend_bucket = "' + "operator-prod-state" + '"',
            "region": 'region = "' + "us-east-2" + '"',
            "function URL": "https://example.lambda-url.us-west-2.on.aws/",
        }
        for label, value in mutations.items():
            with self.subTest(label=label):
                temporary, root = self.fixture()
                with temporary:
                    target = root / "novel" / "settings.tf"
                    target.parent.mkdir()
                    target.write_text(
                        "# SPDX-License-Identifier: Apache-2.0\n" + value + "\n",
                        encoding="utf-8",
                    )
                    findings = audit.audit(root)
                    self.assertTrue(
                        any("unrecorded file novel/settings.tf" in item for item in findings),
                        findings,
                    )
                    self.assertTrue(
                        any("concrete " in item or "cloud account" in item or "generated function" in item
                            for item in findings),
                        findings,
                    )

    def test_committed_deployment_state_still_fails(self) -> None:
        for label, relative in {
            "backend": "backend.hcl",
            "variables": "local.tfvars",
            "state": "infrastructure/example.tfstate",
        }.items():
            with self.subTest(label=label):
                temporary, root = self.fixture()
                with temporary:
                    (root / relative).write_text("operator = true\n", encoding="utf-8")
                    self.assert_fails(root, "local or generated deployment state is committed")

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
