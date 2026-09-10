#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import subprocess
import threading
import unittest
from unittest.mock import patch

from scripts.ci.github_agent_bridge import (
    BridgeError,
    GithubBotBridge,
    run_git,
    render_event,
    validate_event,
)
from scripts.validation.agent_transparency_audit import audit, self_test as audit_self_test


REPOSITORY = "NVDLI/NemoClawDLI"
HEAD = "a" * 40
TOKEN_VALUE = "github_pat_fixture_" + "x" * 32
TOKEN_DIRECTORY = tempfile.TemporaryDirectory()
TOKEN_FILE = Path(TOKEN_DIRECTORY.name) / "bot-token"
TOKEN_FILE.write_text(TOKEN_VALUE, encoding="utf-8")
TOKEN_FILE.chmod(0o600)
SIGNERS_FILE = Path(TOKEN_DIRECTORY.name) / "allowed-signers"
SIGNERS_FILE.write_text("fixture-only human signing registry\n", encoding="utf-8")
SIGNERS_FILE.chmod(0o600)


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
        self.checks: dict[int, dict] = {}

    def __call__(self, method: str, path: str, token: str, body: dict | None = None) -> object:
        self.calls.append((method, path, token, body))
        if path == "/user":
            return {"login": "nemoclaw-course-bot", "type": "User"}
        if path == "/repos/NVDLI/NemoClawDLI":
            return {
                "full_name": REPOSITORY,
                "default_branch": "main",
                "permissions": {
                    "push": True,
                    "admin": False,
                    "maintain": False,
                },
            }
        if method == "GET" and "/check-runs?" in path:
            return {"check_runs": list(self.checks.values())}
        if "/commits/" in path:
            return {"sha": path.rsplit("/", 1)[-1], "commit": {"verification": {"verified": True}}}
        if "/git/ref/heads/" in path:
            return {"object": {"sha": "b" * 40 if path.endswith("/main") else HEAD}}
        if method == "GET" and "/issues/comments/" in path:
            return next(row for row in self.comments if row["id"] == int(path.rsplit("/", 1)[-1]))
        if method == "GET" and "/check-runs/" in path:
            return self.checks[int(path.rsplit("/", 1)[-1])]
        if method == "GET" and path.endswith("/issues/61"):
            return {"number": 61, "repository_url": f"https://api.github.com/repos/{REPOSITORY}"}
        if method == "GET" and "/comments?" in path:
            return self.comments
        if method == "POST" and path.endswith("/comments"):
            response = {"id": self.next_comment, "body": body["body"],
                        "user": {"login": "nemoclaw-course-bot"},
                        "issue_url": f"https://api.github.com/repos/{REPOSITORY}/issues/61"}
            self.comments.append(response)
            self.next_comment += 1
            return response
        if method == "POST" and path.endswith("/check-runs"):
            response = {"id": self.next_check, **body}
            self.checks[self.next_check] = response
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
        if args[0] in {"init", "fetch"}:
            return ""
        if args[0] == "merge-base":
            return ""
        if args[0] == "rev-list":
            return HEAD
        if args[0] == "diff-tree":
            return "docs/agent-github-bot.md"
        if args[0] == "-c":
            return "course-maintainer@example.invalid" if "show" in args else ""
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
    def test_current_tree_transparency_contract(self) -> None:
        self.assertEqual(audit(), [])

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
            with patch.dict(os.environ, {"AGENT_GITHUB_ALLOWED_SIGNERS_FILE": str(SIGNERS_FILE)}):
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
        with patch.dict(os.environ, {"AGENT_GITHUB_ALLOWED_SIGNERS_FILE": str(SIGNERS_FILE)}), self.assertRaisesRegex(BridgeError, "cryptographic commit signature"):
            unsigned.push_feature_branch(Path("."), "agent/issue-61-agent-transparency")

    def test_evidence_links_reject_private_suffixes_and_ambiguous_routes(self) -> None:
        base = "https://github.com/NVDLI/NemoClawDLI"
        for url in (base + "/issues/61?token=fixture", base + "/issues/61#secret",
                    base + "/issues/61\n", base + "/issues/%36%31",
                    base.replace("github.com", "github.com:443") + "/issues/61",
                    base.replace("NVDLI", "unrelated") + "/issues/61",
                    base + "/issues/61)secret", base + "/new/unknown"):
            with self.subTest(url=url), self.assertRaises(BridgeError):
                validate_event(event(evidence=[{"label": "Evidence", "state": "pass", "url": url}]), REPOSITORY)

    def test_lifecycle_report_cannot_create_a_success_attestation(self) -> None:
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as directory:
            bridge(transport).publish(event(state="pass", evidence=[]), Path(directory) / "state.json")
        self.assertEqual(transport.checks[201]["conclusion"], "neutral")

    def test_lost_state_rediscovers_existing_check_and_comment(self) -> None:
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            first = bridge(transport).publish(event(), state)
            state.unlink()
            second = bridge(transport).publish(event(2), state)
        self.assertEqual(first["comment_id"], second["comment_id"])
        self.assertEqual(first["check_run_id"], second["check_run_id"])
        self.assertEqual(len(transport.checks), 1)

    def test_concurrent_older_event_cannot_replace_newer_state(self) -> None:
        transport = FakeTransport()
        candidate = bridge(transport)
        entered, release = threading.Event(), threading.Event()
        errors = []
        original = candidate.transport
        def held(method, path, token, body=None):
            if path == "/user" and not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise AssertionError("test publication was not released")
            return original(method, path, token, body)
        candidate.transport = held
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            def publish(sequence):
                try:
                    candidate.publish(event(sequence), state)
                except Exception as exc:
                    errors.append(exc)
            newer = threading.Thread(target=publish, args=(2,))
            older = threading.Thread(target=publish, args=(1,))
            newer.start()
            self.assertTrue(entered.wait(5))
            older.start()
            release.set()
            newer.join(5)
            older.join(5)
            self.assertFalse(newer.is_alive() or older.is_alive())
            self.assertEqual(json.loads(state.read_text())["last_sequence"], 2)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], BridgeError)
        self.assertEqual(len(transport.checks), 1)

    def test_real_git_isolates_signatures_and_authenticated_push(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, sink = root / "source", root / "sink"
            source.mkdir()
            sink.mkdir()
            key, registry = root / "key", root / "signers"
            subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
            registry.write_text("course-maintainer@example.invalid " + key.with_suffix(".pub").read_text())
            run_git(source, ["init", "-b", "main"])
            run_git(sink, ["init", "--bare"])
            for name, value in (("user.name", "Course Maintainer"), ("user.email", "course-maintainer@example.invalid"),
                                ("gpg.format", "ssh"), ("user.signingkey", str(key))):
                run_git(source, ["config", name, value])
            run_git(source, ["commit", "--allow-empty", "-m", "Base fixture"])
            base = run_git(source, ["rev-parse", "HEAD"])
            branch = "agent/issue-61-agent-transparency"
            run_git(source, ["switch", "-c", branch])
            for number in (1, 2):
                run_git(source, ["commit", "--allow-empty", "-S", "-s", "-m", f"Fixture change {number}"])
            head = run_git(source, ["rev-parse", "HEAD"])
            marker = root / "untrusted-command-ran"
            trap = source / ".git" / "hooks" / "pre-push"
            trap.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 1\n")
            trap.chmod(0o700)
            run_git(source, ["config", "gpg.ssh.program", str(trap)])
            transport = FakeTransport()
            candidate = bridge(transport)
            def api(method, path, token, body=None):
                if path.endswith("/git/ref/heads/main"):
                    return {"object": {"sha": base}}
                return transport(method, path, token, body)
            candidate.transport = api
            pushes = []
            def git(worktree, args, env=None):
                if args[0] == "push":
                    self.assertNotEqual(worktree, source)
                    self.assertEqual(args[-1], f"{head}:refs/heads/{branch}")
                    pushes.append(args)
                    args = [*args[:2], str(sink), args[-1]]
                return run_git(worktree, args, env)
            candidate.git_runner = git
            with patch.dict(os.environ, {"AGENT_GITHUB_ALLOWED_SIGNERS_FILE": str(registry)}):
                result = candidate.push_feature_branch(source, branch)
                self.assertEqual(result["head_sha"], head)
                self.assertEqual(run_git(sink, ["rev-parse", f"refs/heads/{branch}"]), head)
                self.assertFalse(marker.exists())
                registry.write_text("unrelated@example.invalid " + key.with_suffix(".pub").read_text())
                with self.assertRaises(BridgeError):
                    candidate.push_feature_branch(source, branch)
            self.assertEqual(len(pushes), 1)

    def test_other_authors_marker_is_not_reused(self) -> None:
        transport = FakeTransport()
        transport.comments = [{"id": 909, "body": "<!-- nemoclaw-agent-lifecycle -->",
                               "user": {"login": "another-user"},
                               "issue_url": f"https://api.github.com/repos/{REPOSITORY}/issues/61"}]
        with tempfile.TemporaryDirectory() as directory:
            result = bridge(transport).publish(event(), Path(directory) / "state.json")
        self.assertNotEqual(result["comment_id"], 909)
        self.assertFalse(any(method == "PATCH" for method, _, _, _ in transport.calls))

    def test_foreign_or_malformed_state_rejected_before_any_write(self) -> None:
        for mutation in ({"repository": "unrelated/repository"}, {"login": "another-user"},
                         {"schema": "nemoclaw-agent-github-state/1"}, {"comments": {"61": True}},
                         {"checks": {"malformed": 1}}, {"last_sequence": "1"}):
            transport = FakeTransport()
            with tempfile.TemporaryDirectory() as directory:
                state = Path(directory) / "state.json"
                bridge(transport).publish(event(), state)
                data = json.loads(state.read_text())
                data.update(mutation)
                state.write_text(json.dumps(data))
                transport.calls.clear()
                with self.subTest(mutation=mutation), self.assertRaises(BridgeError):
                    bridge(transport).publish(event(2), state)
                self.assertFalse(any(method != "GET" for method, _, _, _ in transport.calls))

    def test_cached_records_require_current_target_and_owner(self) -> None:
        for field in ("comment-owner", "comment-target", "check-head", "check-name", "check-external-id"):
            transport = FakeTransport()
            with tempfile.TemporaryDirectory() as directory:
                state = Path(directory) / "state.json"
                bridge(transport).publish(event(), state)
                if field == "comment-owner":
                    transport.comments[0]["user"] = {"login": "someone-else"}
                elif field == "comment-target":
                    transport.comments[0]["issue_url"] += "0"
                else:
                    key = {"check-head": "head_sha", "check-name": "name", "check-external-id": "external_id"}[field]
                    transport.checks[201][key] = "unrelated"
                transport.calls.clear()
                with self.subTest(field=field), self.assertRaises(BridgeError):
                    bridge(transport).publish(event(2), state)
                self.assertFalse(any(method != "GET" for method, _, _, _ in transport.calls))

    def test_stale_event_head_rejected_before_publication(self) -> None:
        transport = FakeTransport()
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(BridgeError, "current branch head"):
            bridge(transport).publish(event(head_sha="c" * 40), Path(directory) / "state.json")
        self.assertFalse(any(method != "GET" for method, _, _, _ in transport.calls))

    def test_complete_push_range_is_verified_before_write(self) -> None:
        for failure in ("earlier-unsigned", "bad-signature", "wrong-principal", "workflow-change", "unicode-workflow", "newline-workflow"):
            transport = FakeTransport()
            git = FakeGit()
            earlier = "d" * 40
            def altered(worktree, args, env=None):
                if args[0] == "rev-list":
                    return earlier + "\n" + HEAD
                if failure == "earlier-unsigned" and args == ["cat-file", "commit", earlier]:
                    return "tree " + "c" * 40
                if failure == "bad-signature" and "verify-commit" in args:
                    raise BridgeError("untrusted cryptographic commit signature")
                if failure == "wrong-principal" and "--format=%GS" in args:
                    return "another@example.invalid"
                if failure in ("workflow-change", "unicode-workflow", "newline-workflow") and args[0] == "diff-tree":
                    self.assertIn("-z", args)
                    name = {"workflow-change": "novel.yml", "unicode-workflow": "café.yml", "newline-workflow": "new\nline.yml"}[failure]
                    return ".github/workflows/" + name + "\0"
                return git(worktree, args, env)
            candidate = bridge(transport)
            candidate.git_runner = altered
            with self.subTest(failure=failure), patch.dict(os.environ, {"AGENT_GITHUB_ALLOWED_SIGNERS_FILE": str(SIGNERS_FILE)}), self.assertRaises(BridgeError):
                candidate.push_feature_branch(Path("."), "agent/issue-61-agent-transparency")
            self.assertFalse(any(args[0] == "push" for args, _ in git.calls))

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
