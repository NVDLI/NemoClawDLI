# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation tests for repository-local Codex continuity contracts."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from scripts.validation import codex_continuity_audit as audit
from scripts.skills import skill_consistency


ROOT = Path(__file__).resolve().parents[2]


class CodexContinuityAuditTests(unittest.TestCase):
    @staticmethod
    def write_skill(
        root: Path,
        paths: list[Path],
        package: Path,
        *,
        name: str | None = None,
        manifest_name: str = "SKILL.md",
        metadata: bool = True,
    ) -> tuple[Path, Path]:
        skill = package / manifest_name
        metadata_path = package / "agents/openai.yaml"
        (root / skill).parent.mkdir(parents=True, exist_ok=True)
        (root / skill).write_text(
            textwrap.dedent(
                f"""\
                ---
                name: {name or package.name}
                description: Discover and execute a newly introduced repository capability safely.
                ---
                """
            ),
            encoding="utf-8",
        )
        paths.append(skill)
        if metadata:
            (root / metadata_path).parent.mkdir(parents=True, exist_ok=True)
            (root / metadata_path).write_text(
                textwrap.dedent(
                    f"""\
                    interface:
                      display_name: "New capability"
                      short_description: "Execute a repository capability safely"
                      default_prompt: "Use ${name or package.name} to execute this capability safely."
                    """
                ),
                encoding="utf-8",
            )
            paths.append(metadata_path)
        return skill, metadata_path

    def fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, list[Path]]:
        temporary = tempfile.TemporaryDirectory(prefix="codex-continuity-")
        root = Path(temporary.name)
        paths = [
            Path("AGENTS.md"),
            Path("CLAUDE.md"),
            Path(".codex/config.toml"),
            Path(".codex/continuity-contract.json"),
            Path(".codex/hooks/continuity.sh"),
            Path(".agents/skills/nemoclaw-contribution/SKILL.md"),
            Path(".agents/skills/nemoclaw-contribution/agents/openai.yaml"),
        ]
        for path in paths:
            (root / path).parent.mkdir(parents=True, exist_ok=True)

        contract = json.loads((ROOT / ".codex/continuity-contract.json").read_text(encoding="utf-8"))
        (root / ".codex/continuity-contract.json").write_text(
            json.dumps(contract, indent=2) + "\n", encoding="utf-8"
        )
        for path in (
            Path(".codex/config.toml"),
            Path(".codex/hooks/continuity.sh"),
            Path(".agents/skills/nemoclaw-contribution/SKILL.md"),
            Path(".agents/skills/nemoclaw-contribution/agents/openai.yaml"),
        ):
            (root / path).write_text((ROOT / path).read_text(encoding="utf-8"), encoding="utf-8")
        (root / "AGENTS.md").write_text(
            "Read .codex/continuity-contract.json and "
            ".agents/skills/nemoclaw-contribution/SKILL.md.\n",
            encoding="utf-8",
        )
        (root / "CLAUDE.md").write_text("# Claude Code entry point\n\n@AGENTS.md\n", encoding="utf-8")
        return temporary, root, paths

    def test_repository_contract_passes(self) -> None:
        self.assertEqual([], audit.audit(ROOT), "\n".join(audit.audit(ROOT)))

    def test_deleted_hook_is_rejected(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        hook = Path(".codex/hooks/continuity.sh")
        (root / hook).unlink()
        paths.remove(hook)
        findings = audit.audit(root, paths)
        self.assertTrue(any("referenced hook is missing" in item for item in findings))
        self.assertFalse(
            any("missing declared hook phase" in item for item in findings),
            "content checks must not obscure a missing-file finding",
        )
        self.assertFalse(
            any("hook output does not route back" in item for item in findings),
            "content checks must not obscure a missing-file finding",
        )

    def test_renamed_skill_is_rejected(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        skill = Path(".agents/skills/nemoclaw-contribution/SKILL.md")
        renamed = Path(".agents/skills/renamed/SKILL.md")
        (root / renamed).parent.mkdir(parents=True)
        (root / skill).rename(root / renamed)
        paths.remove(skill)
        paths.append(renamed)
        findings = audit.audit(root, paths)
        self.assertTrue(any("referenced contribution skill is missing" in item for item in findings))

    def test_claude_beacon_cannot_duplicate_or_replace_canonical_rules(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        (root / "CLAUDE.md").write_text("# Local rules\n\nSkip expensive checks.\n", encoding="utf-8")
        self.assertTrue(any("must import AGENTS.md" in item for item in audit.audit(root, paths)))

    def test_malformed_near_match_event_is_rejected(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        config = root / ".codex/config.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "[[hooks.PostCompact]]", "[[hooks.PostCompaction]]"
            ).replace(
                "[[hooks.PostCompact.hooks]]", "[[hooks.PostCompaction.hooks]]"
            ),
            encoding="utf-8",
        )
        self.assertTrue(
            any("PostCompact must have one continuity hook group" in item
                for item in audit.audit(root, paths))
        )

    def test_novel_nested_skill_is_discovered(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        self.write_skill(
            root,
            paths,
            Path("module/.agents/skills/category/expected-name"),
            name="different-name",
        )
        self.assertTrue(any("must match directory" in item for item in audit.audit(root, paths)))

    def test_novel_nested_skill_with_native_metadata_passes(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        self.write_skill(root, paths, Path("module/.agents/skills/category/new-capability"))
        self.assertEqual([], audit.audit(root, paths))

    def test_novel_valid_skill_still_requires_ui_metadata(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        self.write_skill(
            root,
            paths,
            Path("module/.agents/skills/new-capability"),
            metadata=False,
        )
        self.assertTrue(any("new-capability/agents/openai.yaml" in item for item in audit.audit(root, paths)))

    def test_deleted_skill_payload_is_discovered_from_metadata(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        package = Path("module/.agents/skills/deleted-payload")
        skill, _ = self.write_skill(root, paths, package)
        (root / skill).unlink()
        paths.remove(skill)
        self.assertTrue(
            any("deleted-payload/SKILL.md: native skill payload is missing" in item
                for item in audit.audit(root, paths))
        )

    def test_renamed_package_is_discovered_without_a_name_allowlist(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        original = Path("module/.agents/skills/original-name")
        skill, metadata = self.write_skill(root, paths, original)
        renamed = original.with_name("renamed-package")
        (root / original).rename(root / renamed)
        paths.remove(skill)
        paths.remove(metadata)
        paths.extend((renamed / "SKILL.md", renamed / "agents/openai.yaml"))
        findings = audit.audit(root, paths)
        self.assertTrue(any("must match directory 'renamed-package'" in item for item in findings))
        self.assertTrue(any("default_prompt must invoke $renamed-package" in item
                            for item in findings))

    def test_manifest_near_match_is_rejected_even_beside_valid_manifest(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        package = Path("module/.agents/skills/near-match")
        self.write_skill(root, paths, package)
        near_match = package / "SKILL.mdx"
        (root / near_match).write_text("# Not a native manifest\n", encoding="utf-8")
        paths.append(near_match)
        self.assertTrue(
            any("SKILL.mdx: skill manifest must be named SKILL.md" in item
                for item in audit.audit(root, paths))
        )

    def test_host_python_hook_command_is_rejected(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        config = root / ".codex/config.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                'sh "$(git rev-parse --show-toplevel)/.codex/hooks/continuity.sh" session-start',
                'python3 "$(git rev-parse --show-toplevel)/.codex/hooks/continuity.py"',
                1,
            ),
            encoding="utf-8",
        )
        self.assertTrue(any("handler differs from the reviewed command" in item
                            for item in audit.audit(root, paths)))

    def test_indirect_hook_side_effect_is_rejected(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        hook = root / ".codex/hooks/continuity.sh"
        hook.write_text(hook.read_text(encoding="utf-8") + "\nenv\n", encoding="utf-8")
        findings = audit.audit(root, paths)
        self.assertTrue(any("differs from the reviewed canonical body" in item
                            for item in findings))
        self.assertTrue(any("outside the reviewed hook grammar" in item
                            for item in findings))

    def test_synchronized_hook_and_digest_edit_is_rejected_structurally(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        hook = root / ".codex/hooks/continuity.sh"
        tampered = hook.read_text(encoding="utf-8").replace(
            audit.HOOK_EMITTER,
            'printf "%s\\n" "$phase" >"${TMPDIR:-/tmp}/last-phase"\n\n'
            + audit.HOOK_EMITTER,
        )
        hook.write_text(tampered, encoding="utf-8")
        digest = hashlib.sha256(tampered.encode("utf-8")).hexdigest()
        with mock.patch.object(audit, "EXPECTED_HOOK_SHA256", digest):
            findings = audit.audit(root, paths)
        self.assertFalse(
            any("differs from the reviewed canonical body" in item for item in findings)
        )
        self.assertTrue(any("outside the reviewed hook grammar" in item
                            for item in findings))

    def test_contract_cannot_redirect_validation_to_a_decoy_hook(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        decoy = Path(".codex/hooks/decoy.sh")
        (root / decoy).write_text(
            (root / ".codex/hooks/continuity.sh").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        paths.append(decoy)
        contract_path = root / ".codex/continuity-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["hook"] = "hooks/decoy.sh"
        contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        self.assertTrue(
            any("is not the hook the config executes" in item
                for item in audit.audit(root, paths))
        )

    def test_hook_grammar_covers_every_lifecycle_phase(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        hook = root / ".codex/hooks/continuity.sh"
        tampered = hook.read_text(encoding="utf-8").replace(
            "  post-compact)", "  post-compaction)"
        )
        hook.write_text(tampered, encoding="utf-8")
        digest = hashlib.sha256(tampered.encode("utf-8")).hexdigest()
        with mock.patch.object(audit, "EXPECTED_HOOK_SHA256", digest):
            findings = audit.audit(root, paths)
        self.assertTrue(any("hook phase branches" in item for item in findings))

    def test_symlinked_hook_is_rejected_even_when_target_bytes_match(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        hook = root / ".codex/hooks/continuity.sh"
        hook.unlink()
        hook.symlink_to(ROOT / ".codex/hooks/continuity.sh")
        self.assertTrue(
            any("regular repository file without symlink components" in item
                for item in audit.audit(root, paths))
        )

    def test_contract_and_config_cannot_tamper_with_the_oracle_together(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        contract_path = root / ".codex/continuity-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["events"]["PreCompact"]["phase"] = "post-compact"
        contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        config = root / ".codex/config.toml"
        config.write_text(
            config.read_text(encoding="utf-8").replace(
                "continuity.sh\" pre-compact", "continuity.sh\" post-compact"
            ),
            encoding="utf-8",
        )
        self.assertTrue(any("independent lifecycle oracle" in item for item in audit.audit(root, paths)))

    def test_malformed_contract_collection_fails_without_crashing(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        contract_path = root / ".codex/continuity-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["checkpoint_fields"] = "objective"
        contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        self.assertTrue(any("checkpoint_fields must be a list of strings" in item
                            for item in audit.audit(root, paths)))

    def test_changed_surface_preflight_cannot_be_removed_from_contract_or_skill(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        contract_path = root / ".codex/continuity-contract.json"
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        contract["invariants"].remove("changed-surface-preflight")
        contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
        skill_path = root / ".agents/skills/nemoclaw-contribution/SKILL.md"
        skill_path.write_text(
            skill_path.read_text(encoding="utf-8").replace(
                "`changed-surface-preflight`", "`focused-preflight`"
            ),
            encoding="utf-8",
        )
        findings = audit.audit(root, paths)
        self.assertTrue(
            any("missing invariants: changed-surface-preflight" in item for item in findings)
        )
        self.assertTrue(
            any("missing continuity invariant changed-surface-preflight" in item
                for item in findings)
        )

    def test_hook_trust_instructions_are_required(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        skill = root / ".agents/skills/nemoclaw-contribution/SKILL.md"
        skill.write_text(
            skill.read_text(encoding="utf-8").replace("trusted checkout", "recognized project"),
            encoding="utf-8",
        )
        self.assertTrue(any("missing hook trust boundary" in item for item in audit.audit(root, paths)))

    def test_malformed_skill_metadata_is_rejected(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        metadata = root / ".agents/skills/nemoclaw-contribution/agents/openai.yaml"
        metadata.write_text(
            metadata.read_text(encoding="utf-8").replace("default_prompt:", "default-prompt:"),
            encoding="utf-8",
        )
        self.assertTrue(
            any("interface metadata is malformed" in item for item in audit.audit(root, paths))
        )

    def test_duplicate_native_metadata_field_is_rejected(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        metadata = root / ".agents/skills/nemoclaw-contribution/agents/openai.yaml"
        metadata.write_text(
            metadata.read_text(encoding="utf-8").replace(
                '  display_name: "NemoClaw contribution"',
                '  display_name: "NemoClaw contribution"\n  display_name: "Duplicate"',
            ),
            encoding="utf-8",
        )
        self.assertTrue(
            any("interface metadata is malformed" in item for item in audit.audit(root, paths))
        )

    def test_non_utf8_git_path_does_not_abort_source_discovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="codex-continuity-path-") as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            path_bytes = os.fsencode(root) + b"/malformed-\xff-path.txt"
            descriptor = os.open(path_bytes, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(descriptor)
            self.assertIn(
                Path(os.fsdecode(b"malformed-\xff-path.txt")),
                audit._source_files(root),
            )

    def test_non_utf8_skill_content_fails_without_crashing(self) -> None:
        temporary, root, paths = self.fixture()
        self.addCleanup(temporary.cleanup)
        skill = root / ".agents/skills/nemoclaw-contribution/SKILL.md"
        skill.write_bytes(b"---\nname: nemoclaw-contribution\ndescription: \xff\n---\n")
        self.assertTrue(
            any("must be a readable UTF-8 file" in item for item in audit.audit(root, paths))
        )

    def test_novel_hidden_root_is_resolved_without_a_prefix_allowlist(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-root-") as temporary:
            root = Path(temporary)
            hidden = root / ".future-capability"
            hidden.mkdir()
            resolved = skill_consistency._resolve(
                ".future-capability/",
                root / "nested",
                task_root=root,
                repo_root=root,
                root_prefixes={".future-capability"},
            )
            self.assertEqual(hidden, resolved)

    def test_ignored_live_directory_does_not_become_a_root_prefix(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-root-") as temporary:
            root = Path(temporary)
            base = root / "nested"
            (root / "build-cache").mkdir()
            resolved = skill_consistency._resolve(
                "build-cache/file.md",
                base,
                task_root=root,
                repo_root=root,
                root_prefixes=set(),
            )
            self.assertEqual(base / "build-cache/file.md", resolved)

    def test_non_utf8_source_root_does_not_abort_prefix_discovery(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-root-") as temporary:
            root = Path(temporary)
            with mock.patch(
                "scripts.skills.skill_consistency.subprocess.check_output",
                return_value=b"normal/file.md\0malformed-\xff/file.md\0",
            ):
                roots = skill_consistency.source_top_level_directories(root)
            self.assertIn("normal", roots)
            self.assertIn(os.fsdecode(b"malformed-\xff"), roots)

    def test_hook_phases_emit_valid_json(self) -> None:
        raw = (ROOT / audit.HOOK_PATH).read_text(encoding="utf-8")
        self.assertEqual(
            audit.EXPECTED_HOOK_SHA256,
            hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            [],
            audit._hook_effect_findings(
                audit.HOOK_PATH,
                raw,
                ["session-start", "pre-compact", "post-compact"],
            ),
        )
        hook = ROOT / ".codex/hooks/continuity.sh"
        expected = {
            "session-start": "Reconstruct the active plan",
            "pre-compact": "before compaction",
            "post-compact": "after compaction",
        }
        for phase, phrase in expected.items():
            with self.subTest(phase=phase):
                result = subprocess.run(
                    ["sh", str(hook), phase],
                    input='{"hook_event_name":"test"}',
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                payload = json.loads(result.stdout)
                self.assertIn("systemMessage", payload)
                self.assertIn("NemoClawDLI continuity", payload["systemMessage"])
                self.assertIn(phrase, payload["systemMessage"])


if __name__ == "__main__":
    unittest.main()
