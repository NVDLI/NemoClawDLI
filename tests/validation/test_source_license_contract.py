# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation tests for repository legal files and authored-source headers."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.compliance import source_license_contract as contract


class SourceLicenseContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="source-license-contract-")
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        (self.root / "web/nemoclaw/vendor").mkdir(parents=True)
        (self.root / "scripts/browser-vendor/node_modules/library").mkdir(parents=True)
        (self.root / "scripts/compliance/docs").mkdir(parents=True)
        (self.root / "tests").mkdir()
        (self.root / "LICENSE").write_text(
            contract.COPYRIGHT + "\n\nApache License\nVersion 2.0\n", encoding="utf-8",
        )
        (self.root / "DCO.md").write_text(contract.DCO_1_1 + "\n", encoding="utf-8")
        (self.root / "THIRD-PARTY-NOTICES.md").write_text(
            "\n".join(contract.NOTICE_LINKS) + "\nmodified_from_upstream\n", encoding="utf-8",
        )
        (self.root / "scripts/check.py").write_text(
            "# " + contract.COPYRIGHT + "\n# " + contract.SPDX + "\n\nprint('ok')\n",
            encoding="utf-8",
        )
        (self.root / "tests/check.mjs").write_text(
            "#!/usr/bin/env node\n// " + contract.COPYRIGHT + "\n// " + contract.SPDX + "\n\nexport {};\n",
            encoding="utf-8",
        )
        self.exception_policy = self.root / contract.BROWSER_EXCEPTION_POLICY_PATH
        self.exception_policy.write_text(json.dumps({
            "schema": contract.BROWSER_EXCEPTION_POLICY_SCHEMA,
            "exceptions": [contract.LANGCHAIN_BROWSER_EXCEPTION],
        }, indent=2) + "\n", encoding="utf-8")
        self.embedded_evidence = self.root / "scripts/browser-vendor/embedded-component-evidence.json"
        self.embedded_evidence.write_text(json.dumps({
            "schema": "nemoclaw-embedded-browser-components/1",
            "parent": {"package": "@langchain/core", "version": "1.1.48"},
            "explanation": "Fixture evidence for source copied into the upstream package.",
            "components": [{"id": "fixture-embedded-utility"}],
        }, indent=2) + "\n", encoding="utf-8")
        self.upstream_file = self.root / "scripts/browser-vendor/node_modules/library/library.js"
        self.upstream_file.write_bytes(b"publisher bytes\n")
        self.library_file = self.root / "web/nemoclaw/vendor/library.js"
        self.library_file.write_bytes(self.upstream_file.read_bytes())
        self.langchain_file = self.root / "web/nemoclaw/vendor/langchain-1.4.7.esm.js"
        self.langchain_file.write_bytes(b"generated interoperability bundle\n")
        library_hash = hashlib.sha256(self.library_file.read_bytes()).hexdigest()
        langchain_hash = hashlib.sha256(self.langchain_file.read_bytes()).hexdigest()
        self.manifest = self.root / "web/nemoclaw/vendor/browser-dependencies.json"
        self.manifest.write_text(json.dumps({
            "modification_exception_policy": {
                "file": contract.BROWSER_EXCEPTION_POLICY_PATH,
                "sha256": hashlib.sha256(self.exception_policy.read_bytes()).hexdigest(),
                "exception_ids": [contract.LANGCHAIN_BROWSER_EXCEPTION["id"]],
            },
            "embedded_component_evidence": {
                "file": "scripts/browser-vendor/embedded-component-evidence.json",
                "sha256": hashlib.sha256(self.embedded_evidence.read_bytes()).hexdigest(),
                "parent": {"package": "@langchain/core", "version": "1.1.48"},
                "explanation": "Fixture evidence for source copied into the upstream package.",
            },
            "embedded_components": [{"id": "fixture-embedded-utility"}],
            "assets": [
                {
                    "file": "library.js",
                    "bytes": self.library_file.stat().st_size,
                    "sha256": library_hash,
                    "upstream_sha256": library_hash,
                    "distribution_form": "upstream-file-copy",
                    "modified_from_upstream": False,
                    "publisher_provided_minified": False,
                    "transformation": "Publisher-provided source copied byte-for-byte",
                    "source_files": ["scripts/browser-vendor/node_modules/library/library.js"],
                },
                {
                    "file": contract.LANGCHAIN_BROWSER_EXCEPTION["asset"],
                    "bytes": self.langchain_file.stat().st_size,
                    "sha256": langchain_hash,
                    "distribution_form": "transformed-bundle",
                    "modified_from_upstream": True,
                    "publisher_provided_minified": False,
                    "modification_exception_id": contract.LANGCHAIN_BROWSER_EXCEPTION["id"],
                    "transformation": contract.LANGCHAIN_BROWSER_EXCEPTION["transformation"],
                    "source_files": [contract.LANGCHAIN_BROWSER_EXCEPTION["entrypoint"]],
                },
            ],
        }), encoding="utf-8")
        shared_vendor = self.root / "web/shared/vendor"
        (shared_vendor / "licenses").mkdir(parents=True)
        self.shared_file = shared_vendor / "library.js"
        self.shared_file.write_bytes(self.library_file.read_bytes())
        (shared_vendor / "licenses/library--1.0.0.txt").write_text("MIT License\n", encoding="utf-8")
        self.shared_manifest = shared_vendor / "browser-dependencies.json"
        self.shared_manifest.write_text(json.dumps({
            "schema": "dli-shared-browser-dependencies/1",
            "packages": [{
                "name": "library", "version": "1.0.0", "license": "MIT",
                "license_file": "licenses/library--1.0.0.txt",
            }],
            "assets": [{
                "file": "library.js", "package": "library@1.0.0",
                "sha256": hashlib.sha256(self.shared_file.read_bytes()).hexdigest(),
                "bytes": self.shared_file.stat().st_size,
                "reviewed_copy": "web/nemoclaw/vendor/library.js",
            }],
        }), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def audit(self, *, verify_browser_upstream: bool = False) -> list[str]:
        files = [path for path in self.root.rglob("*") if path.is_file()]
        failures, _ = contract.audit(
            self.root,
            files,
            verify_browser_upstream=verify_browser_upstream,
        )
        return failures

    def assert_rejected(self, fragment: str) -> None:
        self.assertTrue(any(fragment in item for item in self.audit()), self.audit())

    def test_complete_fixture_passes(self) -> None:
        self.assertEqual([], self.audit())

    def test_publisher_inputs_are_byte_identical(self) -> None:
        self.assertEqual([], self.audit(verify_browser_upstream=True))

    def test_license_copyright_mutation_is_rejected(self) -> None:
        (self.root / "LICENSE").write_text("Apache License\nVersion 2.0\n", encoding="utf-8")
        self.assert_rejected("root license")

    def test_dco_mutation_is_rejected(self) -> None:
        (self.root / "DCO.md").write_text(contract.DCO_1_1.replace("indefinitely", "temporarily"), encoding="utf-8")
        self.assert_rejected("DCO")

    def test_notice_link_mutation_is_rejected(self) -> None:
        path = self.root / "THIRD-PARTY-NOTICES.md"
        path.write_text(path.read_text(encoding="utf-8").replace(contract.NOTICE_LINKS[0], ""), encoding="utf-8")
        self.assert_rejected("third-party notices")

    def test_python_header_mutation_is_rejected(self) -> None:
        path = self.root / "scripts/check.py"
        path.write_text(path.read_text(encoding="utf-8").replace("# " + contract.SPDX + "\n", ""), encoding="utf-8")
        self.assert_rejected("scripts/check.py")

    def test_shebang_javascript_header_mutation_is_rejected(self) -> None:
        path = self.root / "tests/check.mjs"
        path.write_text(path.read_text(encoding="utf-8").replace("// " + contract.COPYRIGHT + "\n", ""), encoding="utf-8")
        self.assert_rejected("tests/check.mjs")

    def test_vendor_classification_mutation_is_rejected(self) -> None:
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["assets"][0].pop("modified_from_upstream")
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("browser vendor")

    def test_vendor_form_and_modification_boolean_must_agree(self) -> None:
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["assets"][0]["modified_from_upstream"] = True
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("browser vendor")

    def test_repository_minified_vendor_output_is_rejected(self) -> None:
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["assets"][0]["file"] = "library.min.js"
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("browser vendor")

    def test_publisher_minified_upstream_copy_is_accepted(self) -> None:
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.library_file.rename(self.library_file.with_name("library.min.js"))
        shared = json.loads(self.shared_manifest.read_text(encoding="utf-8"))
        shared["assets"][0]["reviewed_copy"] = "web/nemoclaw/vendor/library.min.js"
        self.shared_manifest.write_text(json.dumps(shared), encoding="utf-8")
        data["assets"][0].update({
            "file": "library.min.js",
            "distribution_form": "upstream-file-copy",
            "modified_from_upstream": False,
            "publisher_provided_minified": True,
            "transformation": "Publisher-provided file copied byte-for-byte",
        })
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual([], self.audit())

    def test_only_documented_langchain_exception_turns_failure_into_pass(self) -> None:
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["assets"][1].pop("modification_exception_id")
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("exact documented LangChain exception")
        data["assets"][1]["modification_exception_id"] = contract.LANGCHAIN_BROWSER_EXCEPTION["id"]
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual([], self.audit())

    def test_non_langchain_transformation_is_rejected_even_beside_langchain(self) -> None:
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["assets"][0].update({
            "distribution_form": "transformed-bundle",
            "modified_from_upstream": True,
            "publisher_provided_minified": False,
            "modification_exception_id": contract.LANGCHAIN_BROWSER_EXCEPTION["id"],
            "transformation": contract.LANGCHAIN_BROWSER_EXCEPTION["transformation"],
            "source_files": [contract.LANGCHAIN_BROWSER_EXCEPTION["entrypoint"]],
        })
        data["assets"][0].pop("upstream_sha256")
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("modified asset set must be exactly")

    def test_langchain_must_remain_the_one_modified_asset(self) -> None:
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        langchain = data["assets"][1]
        langchain.update({
            "distribution_form": "upstream-file-copy",
            "modified_from_upstream": False,
            "upstream_sha256": langchain["sha256"],
        })
        langchain.pop("modification_exception_id")
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("modified asset set must be exactly")

    def test_langchain_exception_rationale_is_immutable(self) -> None:
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["assets"][1]["transformation"] = "bundled"
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("exact documented LangChain exception")

    def test_exception_policy_mutation_is_rejected(self) -> None:
        data = json.loads(self.exception_policy.read_text(encoding="utf-8"))
        data["exceptions"][0]["constraints"] = []
        self.exception_policy.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("exact, sole LangChain exception")

    def test_embedded_component_evidence_mutation_is_rejected(self) -> None:
        data = json.loads(self.embedded_evidence.read_text(encoding="utf-8"))
        data["components"].append({"id": "unrecorded-embedded-utility"})
        self.embedded_evidence.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("embedded component")

    def test_embedded_component_manifest_omission_is_rejected(self) -> None:
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["embedded_components"] = []
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        self.assert_rejected("embedded component manifest differs")

    def test_manual_langchain_output_change_is_rejected(self) -> None:
        self.langchain_file.write_bytes(b"manual edit\n")
        self.assert_rejected("delivered asset hash or size differs")

    def test_publisher_source_change_is_rejected_by_ci_verification(self) -> None:
        self.upstream_file.write_bytes(b"different publisher bytes\n")
        failures = self.audit(verify_browser_upstream=True)
        self.assertTrue(any("publisher byte identity failed" in item for item in failures), failures)

    def test_shared_vendor_byte_mutation_is_rejected(self) -> None:
        self.shared_file.write_bytes(b"changed shared bytes\n")
        self.assert_rejected("shared browser vendor: delivered asset hash or size differs")

    def test_shared_vendor_unmanifested_asset_is_rejected(self) -> None:
        (self.shared_file.parent / "extra.js").write_text("extra\n", encoding="utf-8")
        self.assert_rejected("manifest must exhaustively describe every delivered asset")

    def test_shared_vendor_reviewed_copy_drift_is_rejected(self) -> None:
        self.library_file.write_bytes(b"reviewed source changed\n")
        self.assert_rejected("differs from its reviewed publisher copy")

    def test_shared_vendor_license_evidence_is_required(self) -> None:
        (self.shared_file.parent / "licenses/library--1.0.0.txt").unlink()
        self.assert_rejected("missing license evidence")

    def test_header_fixer_preserves_shebang(self) -> None:
        target = self.root / "tests/unlicensed.js"
        target.write_text("#!/usr/bin/env node\nconsole.log('ok');\n", encoding="utf-8")
        changed = contract.apply_headers(self.root, [target])
        self.assertEqual(["tests/unlicensed.js"], changed)
        lines = target.read_text(encoding="utf-8").splitlines()
        self.assertEqual("#!/usr/bin/env node", lines[0])
        self.assertEqual("// " + contract.COPYRIGHT, lines[1])
        self.assertEqual("// " + contract.SPDX, lines[2])


if __name__ == "__main__":
    unittest.main()
