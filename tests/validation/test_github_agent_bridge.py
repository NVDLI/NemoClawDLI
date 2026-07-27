#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.ci.github_agent_bridge import (
    BridgeError,
    GithubBotBridge,
    render_event,
    validate_event,
)
from scripts.validation.agent_transparency_audit import self_test as audit_self_test


REPOSITORY = "NVDLI/NemoClawDLI"
HEAD = "a" * 40
TOKEN_VALUE = "github_pat_fixture_" + "x" * 32
TOKEN_DIRECTORY = tempfile.TemporaryDirectory()
TOKEN_FILE = Path(TOKEN_DIRECTORY.name) / "bot-token"
TOKEN_FILE.write_text(TOKEN_VALUE, encoding="utf-8")
TOKEN_FILE.chmod(0o600)


def event(sequence: int = 1, **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "nemoclaw-agent-event/1",
        "sequence": sequence,
        "time": "2026-07-27T12:00:00Z",
        "repository": REPOSITORY,
        "issue": 61,
        "pull_request": None,
        "branch": "agent/issue-61-agent-transparency",
        "head_sha": HEAD,
        "attempt": 1,
        "phase": "fast-gate",
        "state": "in_progress",
        "summary": "Fast validation is running on the exact branch head.",
        "next": "Review the exact-diff result.",
        "blocker": None,
        "evidence": [{
            "label": "Issue",
            "state": "in_progress",
            "url": "https://github.com/NVDLI/NemoClawDLI/issues/61",
        }],
    }
    value.update(changes)
    return value


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, object]] = []
        self.next_comment = 101
        self.next_check = 201
        self.comments: list[dict[str, object]] = []

    def __call__(self, method: str, path: str, token: str, body: dict | None = None) -> object:
        self.calls.append((method, path, token, body))
        if path == "/user":
            return {"login": "nemoclaw-course-bot", "type": "User"}
        if path == "/repos/NVDLI/NemoClawDLI":
            return {
                "full_name": REPOSITORY,
                "permissions": {
                    "push": True,
                    "admin": False,
                    "maintain": False,
                },
            }
        if "/commits/" in path:
            return {"sha": HEAD, "commit": {"verification": {"verified": True}}}
        if method == "GET" and "/comments?" in path:
            return self.comments
        if method == "POST" and path.endswith("/comments"):
            response = {"id": self.next_comment, "body": body["body"]}
            self.comments.append(response)
            self.next_comment += 1
            return response
        if method == "POST" and path.endswith("/check-runs"):
            response = {"id": self.next_check}
            self.next_check += 1
            return response
        if method == "PATCH":
            return {"id": int(path.rsplit("/", 1)[-1])}
        raise AssertionError(f"unexpected fake request: {method} {path}")


def bridge(transport: FakeTransport) -> GithubBotBridge:
    return GithubBotBridge(
        login="nemoclaw-course-bot",
        token_file=TOKEN_FILE,
        repository=REPOSITORY,
        transport=transport,
    )


class FakeGit:
    def __init__(self, *, signed: bool = True) -> None:
        self.signed = signed
        self.calls: list[tuple[list[str], dict[str, str] | None]] = []

    def __call__(self, _worktree: Path, args: list[str], env: dict[str, str] | None = None) -> str:
        self.calls.append((args, env))
        if args[:3] == ["symbolic-ref", "--quiet", "--short"]:
            return "agent/issue-61-agent-transparency"
        if args[:2] == ["status", "--porcelain=v1"]:
            return ""
        if args[0] == "rev-parse":
            return HEAD
        if args[0] == "show":
            return (
                "Course Maintainer\0course-maintainer@example.invalid\0"
                "Publish bounded agent status\n\n"
                "Signed-off-by: Course Maintainer <course-maintainer@example.invalid>\0"
                + "b" * 40
            )
        if args[:2] == ["cat-file", "commit"]:
            signature = "\ngpgsig -----BEGIN SSH SIGNATURE-----\n value" if self.signed else ""
            return f"tree {'c' * 40}\nparent {'b' * 40}{signature}\n\nPublish bounded agent status"
        if args[0] == "push":
            return "ok"
        raise AssertionError(f"unexpected fake git command: {args}")


class GithubAgentBridgeTests(unittest.TestCase):
    def test_transparency_audit_mutations(self) -> None:
        self.assertEqual(audit_self_test(), [])

    def test_verify_requires_dedicated_non_administrative_identity(self) -> None:
        transport = FakeTransport()
        result = bridge(transport).verify()
        self.assertEqual(result["login"], "nemoclaw-course-bot")
        self.assertEqual(result["repository"], REPOSITORY)

        original = transport.__call__

        def excessive(method: str, path: str, token: str, body: dict | None = None) -> object:
            response = original(method, path, token, body)
            if path == "/repos/NVDLI/NemoClawDLI":
                response = {**response, "permissions": {**response["permissions"], "admin": True}}
            return response

        candidate = bridge(transport)
        candidate.transport = excessive
        with self.assertRaisesRegex(BridgeError, "administrative or maintainer"):
            candidate.verify()

    def test_explicit_empty_environment_does_not_fall_back_to_process_state(self) -> None:
        with self.assertRaisesRegex(BridgeError, "missing GitHub bot configuration"):
            GithubBotBridge.from_env({})
        with self.assertRaisesRegex(BridgeError, "login is invalid"):
            GithubBotBridge.from_env({
                "AGENT_GITHUB_LOGIN": "not/a/login",
                "AGENT_GITHUB_TOKEN_FILE": str(TOKEN_FILE),
                "AGENT_GITHUB_REPOSITORY": REPOSITORY,
            })
        with self.assertRaisesRegex(BridgeError, "owner/name"):
            GithubBotBridge.from_env({
                "AGENT_GITHUB_LOGIN": "nemoclaw-course-bot",
                "AGENT_GITHUB_TOKEN_FILE": str(TOKEN_FILE),
                "AGENT_GITHUB_REPOSITORY": "not-a-repository",
            })

    def test_token_must_be_fine_grained_and_private(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            token_file = Path(directory) / "token"
            token_file.write_text(TOKEN_VALUE, encoding="utf-8")
            token_file.chmod(0o644)
            candidate = GithubBotBridge(
                login="nemoclaw-course-bot",
                token_file=token_file,
                repository=REPOSITORY,
            )
            with self.assertRaisesRegex(BridgeError, "group or others"):
                candidate.access_token()
            token_file.chmod(0o600)
            token_file.write_text("ghp_classic-token-is-not-accepted", encoding="utf-8")
            with self.assertRaisesRegex(BridgeError, "fine-grained token"):
                candidate.access_token()
            token_file.write_text(TOKEN_VALUE, encoding="utf-8")
            linked = Path(directory) / "linked-token"
            linked.symlink_to(token_file)
            candidate.token_file = linked
            with self.assertRaisesRegex(BridgeError, "unavailable or unsafe"):
                candidate.access_token()

    def test_publish_reuses_comment_and_exact_head_check(self) -> None:
        transport = FakeTransport()
        candidate = bridge(transport)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "github-state.json"
            first = candidate.publish(event(), state)
            second = candidate.publish(
                event(2, state="pass", summary="Fast validation passed on the exact branch head."),
                state,
            )
            written = json.loads(state.read_text(encoding="utf-8"))
            state_text = state.read_text(encoding="utf-8")

        self.assertEqual(first["comment_id"], second["comment_id"])
        self.assertEqual(first["check_run_id"], second["check_run_id"])
        self.assertEqual(written["last_sequence"], 2)
        created_comments = [call for call in transport.calls if call[0] == "POST" and call[1].endswith("/comments")]
        updated_comments = [call for call in transport.calls if call[0] == "PATCH" and "/issues/comments/" in call[1]]
        created_checks = [call for call in transport.calls if call[0] == "POST" and call[1].endswith("/check-runs")]
        updated_checks = [call for call in transport.calls if call[0] == "PATCH" and "/check-runs/" in call[1]]
        self.assertEqual(len(created_comments), 1)
        self.assertEqual(len(updated_comments), 1)
        self.assertEqual(len(created_checks), 1)
        self.assertEqual(len(updated_checks), 1)
        self.assertNotIn(TOKEN_VALUE, state_text)

    def test_precommit_event_updates_comment_without_fabricating_check(self) -> None:
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as directory:
            result = bridge(transport).publish(
                event(head_sha=None, phase="implementation", summary="The scoped implementation is in progress."),
                Path(directory) / "state.json",
            )
        self.assertIsNone(result["check_run_id"])
        self.assertFalse(any(path.endswith("/check-runs") for _, path, _, _ in transport.calls))

    def test_push_uses_ephemeral_bot_auth_and_requires_signed_human_dco(self) -> None:
        transport = FakeTransport()
        git = FakeGit()
        candidate = bridge(transport)
        candidate.git_runner = git
        previous_trace = os.environ.get("GIT_TRACE_CURL")
        os.environ["GIT_TRACE_CURL"] = "1"
        try:
            result = candidate.push_feature_branch(
                Path("."), "agent/issue-61-agent-transparency",
            )
        finally:
            if previous_trace is None:
                os.environ.pop("GIT_TRACE_CURL", None)
            else:
                os.environ["GIT_TRACE_CURL"] = previous_trace
        self.assertEqual(result["head_sha"], HEAD)
        push_args, push_env = next((args, env) for args, env in git.calls if args[0] == "push")
        self.assertNotIn("--force", push_args)
        self.assertNotIn("--force-with-lease", push_args)
        self.assertNotIn(TOKEN_VALUE, " ".join(push_args))
        self.assertNotIn("GIT_TRACE_CURL", push_env)
        self.assertIn("Authorization: Basic ", push_env["GIT_CONFIG_VALUE_0"])

        unsigned = bridge(FakeTransport())
        unsigned.git_runner = FakeGit(signed=False)
        with self.assertRaisesRegex(BridgeError, "cryptographic commit signature"):
            unsigned.push_feature_branch(Path("."), "agent/issue-61-agent-transparency")

    def test_sequence_cannot_move_backwards(self) -> None:
        transport = FakeTransport()
        candidate = bridge(transport)
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            candidate.publish(event(3), state)
            with self.assertRaisesRegex(BridgeError, "sequence must increase"):
                candidate.publish(event(2), state)

    def test_event_rejects_protected_refs_unknown_fields_and_private_data(self) -> None:
        mutations = [
            event(branch="main"),
            {**event(), "raw_tool_output": "hidden"},
            event(summary="Authorization: github_pat_" + "x" * 30),
            event(evidence=[{
                "label": "Private log",
                "state": "pass",
                "url": "https://example.invalid/log",
            }]),
        ]
        for mutated in mutations:
            with self.subTest(mutated=mutated):
                with self.assertRaises(BridgeError):
                    validate_event(mutated, REPOSITORY)

    def test_rendered_status_is_bounded_and_explains_omitted_data(self) -> None:
        body, output = render_event(validate_event(event(), REPOSITORY))
        self.assertIn("Agent contribution status", body)
        self.assertIn("omits prompts, tool transcripts, credentials, costs", body)
        self.assertIn("fast-gate", output["title"])
        self.assertNotIn(TOKEN_VALUE, body)


if __name__ == "__main__":
    unittest.main()
