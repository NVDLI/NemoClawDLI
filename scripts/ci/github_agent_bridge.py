#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Publish bounded agent lifecycle state through a dedicated GitHub bot user."""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


AGENT_TRANSPARENCY_BRIDGE = True
API = "https://api.github.com"
API_VERSION = "2022-11-28"
SCHEMA = "nemoclaw-agent-event/1"
CHECK_NAME = "Agent contribution / lifecycle"
COMMENT_MARKER = "<!-- nemoclaw-agent-lifecycle -->"
REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
BRANCH = re.compile(r"^(?![-/])(?!.*(?:\.\.|//))[A-Za-z0-9][A-Za-z0-9._/-]{0,126}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
PUBLIC_STATES = {"queued", "in_progress", "pass", "fail", "blocked", "cancelled"}
PHASES = {
    "implementation", "focused-preflight", "fast-gate", "exact-diff-review", "ship-gate",
    "browser", "pages-artifact", "signed-pr", "pr-checks", "merge", "production",
}
REQUIRED_PERMISSIONS = {
    "checks": "write",
    "contents": "write",
    "issues": "write",
}
FORBIDDEN_PUBLIC_TEXT = (
    re.compile(r"(?i)(?:token|password|secret|cookie|authorization)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(?:gh[oprsu]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
    re.compile(r"(?i)\b(?:_pomerium|CF_Authorization|NEMOCLAW_DLI_PAT)\b"),
    re.compile(r"(?i)\b(?:localhost|127\.0\.0\.1|development\.dli-infra\.nvidia\.com)\b"),
)
EVENT_FIELDS = {
    "schema", "sequence", "time", "repository", "issue", "pull_request", "branch", "head_sha",
    "attempt", "phase", "state", "summary", "next", "blocker", "evidence",
}
TRACE_ENV = {
    "GIT_TRACE", "GIT_TRACE_CURL", "GIT_TRACE_CURL_NO_DATA", "GIT_CURL_VERBOSE",
    "GIT_TRACE_PACKET", "GIT_TRACE2", "GIT_TRACE2_EVENT",
}


class BridgeError(RuntimeError):
    """A safe, user-facing bridge failure."""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_time(value: object) -> str:
    if not isinstance(value, str):
        raise BridgeError("event time must be an ISO-8601 UTC string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BridgeError("event time must be an ISO-8601 UTC string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise BridgeError("event time must use UTC")
    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _public_line(value: object, field: str, limit: int, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise BridgeError(f"{field} must be a non-empty string")
    text = " ".join(value.split())
    if len(text) > limit:
        raise BridgeError(f"{field} exceeds {limit} characters")
    if any(pattern.search(text) for pattern in FORBIDDEN_PUBLIC_TEXT):
        raise BridgeError(f"{field} contains data that cannot be published")
    return text


def _positive_number(value: object, field: str, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise BridgeError(f"{field} must be a positive integer")
    return value


def validate_event(raw: object, expected_repository: str) -> dict[str, Any]:
    """Validate and normalize one public lifecycle event."""

    if not isinstance(raw, dict) or set(raw) != EVENT_FIELDS:
        missing = sorted(EVENT_FIELDS - set(raw if isinstance(raw, dict) else {}))
        extra = sorted(set(raw if isinstance(raw, dict) else {}) - EVENT_FIELDS)
        raise BridgeError(f"event fields do not match the schema; missing={missing} extra={extra}")
    if raw["schema"] != SCHEMA:
        raise BridgeError(f"unsupported event schema: {raw['schema']!r}")
    if raw["repository"] != expected_repository:
        raise BridgeError("event repository does not match the configured repository")
    if not REPOSITORY.fullmatch(expected_repository):
        raise BridgeError("configured repository must use owner/name form")
    branch = raw["branch"]
    if not isinstance(branch, str) or not BRANCH.fullmatch(branch):
        raise BridgeError("branch is outside the allowed ref vocabulary")
    if branch in {"main", "master"} or branch.startswith(("release/", "refs/", "tags/")):
        raise BridgeError("the agent bridge cannot publish a protected or release ref")
    head = raw["head_sha"]
    if head is not None and (not isinstance(head, str) or not SHA.fullmatch(head)):
        raise BridgeError("head_sha must be null or one full lowercase Git commit SHA")
    phase = raw["phase"]
    state = raw["state"]
    if phase not in PHASES:
        raise BridgeError(f"unsupported lifecycle phase: {phase!r}")
    if state not in PUBLIC_STATES:
        raise BridgeError(f"unsupported lifecycle state: {state!r}")
    evidence = raw["evidence"]
    if not isinstance(evidence, list) or len(evidence) > 12:
        raise BridgeError("evidence must be a list with at most 12 entries")
    clean_evidence = []
    for index, item in enumerate(evidence):
        if not isinstance(item, dict) or set(item) != {"label", "state", "url"}:
            raise BridgeError(f"evidence[{index}] must contain label, state, and url")
        label = _public_line(item["label"], f"evidence[{index}].label", 80)
        evidence_state = item["state"]
        if evidence_state not in PUBLIC_STATES:
            raise BridgeError(f"evidence[{index}].state is invalid")
        url = item["url"]
        parsed = urlsplit(url) if isinstance(url, str) else None
        if (
            parsed is None or parsed.scheme != "https" or parsed.hostname != "github.com"
            or parsed.username or parsed.password or not parsed.path.startswith("/")
        ):
            raise BridgeError(f"evidence[{index}].url must be an https://github.com link")
        clean_evidence.append({"label": label, "state": evidence_state, "url": url})
    return {
        "schema": SCHEMA,
        "sequence": _positive_number(raw["sequence"], "sequence"),
        "time": _parse_time(raw["time"]),
        "repository": expected_repository,
        "issue": _positive_number(raw["issue"], "issue"),
        "pull_request": _positive_number(raw["pull_request"], "pull_request", optional=True),
        "branch": branch,
        "head_sha": head,
        "attempt": _positive_number(raw["attempt"], "attempt"),
        "phase": phase,
        "state": state,
        "summary": _public_line(raw["summary"], "summary", 240),
        "next": _public_line(raw["next"], "next", 240, optional=True),
        "blocker": _public_line(raw["blocker"], "blocker", 400, optional=True),
        "evidence": clean_evidence,
    }


class HttpTransport:
    """Small injectable GitHub JSON transport."""

    def __call__(
        self, method: str, path: str, token: str, body: dict[str, Any] | None = None,
    ) -> Any:
        encoded = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        request = Request(
            API + path,
            data=encoded,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "nemoclaw-agent-transparency",
                **({"Content-Type": "application/json"} if encoded is not None else {}),
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read()
        except HTTPError as exc:
            raise BridgeError(f"GitHub API {method} {path} returned HTTP {exc.code}") from exc
        except OSError as exc:
            raise BridgeError(f"GitHub API {method} {path} could not be reached") from exc
        return json.loads(data) if data else {}


def run_git(worktree: Path, arguments: list[str], env: dict[str, str] | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(worktree), *arguments],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BridgeError("Git feature-branch publication failed") from exc
    return result.stdout.strip()


@dataclass
class GithubBotBridge:
    login: str
    token_file: Path
    repository: str
    transport: Callable[[str, str, str, dict[str, Any] | None], Any] = HttpTransport()
    git_runner: Callable[[Path, list[str], dict[str, str] | None], str] = run_git

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "GithubBotBridge":
        values = dict(os.environ) if env is None else env
        names = {
            "login": "AGENT_GITHUB_LOGIN",
            "token_file": "AGENT_GITHUB_TOKEN_FILE",
            "repository": "AGENT_GITHUB_REPOSITORY",
        }
        missing = [source for source in names.values() if not values.get(source)]
        if missing:
            raise BridgeError("missing GitHub bot configuration: " + ", ".join(missing))
        repository = values[names["repository"]]
        login = values[names["login"]]
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", login):
            raise BridgeError("GitHub bot login is invalid")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise BridgeError("GitHub repository must be an owner/name pair")
        return cls(
            login=login,
            token_file=Path(values[names["token_file"]]),
            repository=repository,
        )

    def access_token(self) -> str:
        """Read one fine-grained token from a private file without persisting a copy."""

        try:
            descriptor = os.open(self.token_file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise BridgeError("GitHub bot token file is unavailable or unsafe") from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise BridgeError("GitHub bot token path must be a regular file")
            if metadata.st_mode & 0o077:
                raise BridgeError("GitHub bot token file must not be accessible by group or others")
            with os.fdopen(descriptor, encoding="utf-8") as handle:
                descriptor = -1
                token = handle.read().strip()
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if (
            not token.startswith("github_pat_")
            or len(token) < 30
            or any(character.isspace() for character in token)
        ):
            raise BridgeError("GitHub bot credential must be one fine-grained token")
        return token

    def verify(self) -> dict[str, Any]:
        """Verify the dedicated identity and its non-administrative repository role."""

        token = self.access_token()
        account = self.transport("GET", "/user", token, None)
        owner, repo = self.repository.split("/", 1)
        repository = self.transport(
            "GET", f"/repos/{owner}/{repo}", token, None,
        )
        if str(account.get("login", "")).casefold() != self.login.casefold():
            raise BridgeError("GitHub token belongs to a different account")
        if account.get("type") != "User":
            raise BridgeError("GitHub bot credential must belong to a dedicated user account")
        if repository.get("full_name") != self.repository:
            raise BridgeError("GitHub token is not bound to the configured repository")
        permissions = repository.get("permissions")
        if not isinstance(permissions, dict):
            raise BridgeError("GitHub did not return repository role evidence")
        if permissions.get("push") is not True:
            raise BridgeError("GitHub bot requires repository write access")
        if permissions.get("admin") is True or permissions.get("maintain") is True:
            raise BridgeError("GitHub bot must not hold administrative or maintainer authority")
        return {
            "login": account.get("login"),
            "repository": self.repository,
            "repository_role": permissions,
            "token_permissions": REQUIRED_PERMISSIONS,
        }

    def push_feature_branch(self, worktree: Path, expected_branch: str) -> dict[str, str]:
        """Push one clean, signed, DCO-complete feature head as the bot actor."""

        worktree = worktree.resolve()
        if not worktree.is_dir() or not BRANCH.fullmatch(expected_branch):
            raise BridgeError("worktree or feature branch is invalid")
        if expected_branch in {"main", "master"} or expected_branch.startswith(("release/", "refs/", "tags/")):
            raise BridgeError("the agent bridge cannot publish a protected or release ref")
        current = self.git_runner(worktree, ["symbolic-ref", "--quiet", "--short", "HEAD"], None)
        if current != expected_branch:
            raise BridgeError("checked-out branch does not match the requested feature branch")
        if self.git_runner(worktree, ["status", "--porcelain=v1", "--untracked-files=all"], None):
            raise BridgeError("feature branch worktree must be clean before publication")
        head = self.git_runner(worktree, ["rev-parse", "HEAD"], None)
        if not SHA.fullmatch(head):
            raise BridgeError("feature branch head is not a full Git commit SHA")
        record = self.git_runner(
            worktree, ["show", "-s", "--format=%an%x00%ae%x00%B%x00%P", head], None,
        ).split("\0")
        if len(record) != 4:
            raise BridgeError("could not read commit author, message, and parent")
        author, email, message, parents = record
        trailer = re.compile(
            rf"(?im)^Signed-off-by:\s*{re.escape(author)}\s*<{re.escape(email)}>\s*$",
        )
        if not trailer.search(message):
            raise BridgeError("feature branch head lacks a Signed-off-by trailer matching its author")
        if len(parents.split()) != 1:
            raise BridgeError("feature branch head must have exactly one parent")
        raw_commit = self.git_runner(worktree, ["cat-file", "commit", head], None)
        if "\ngpgsig " not in "\n" + raw_commit and "\ngpgsig-sha256 " not in "\n" + raw_commit:
            raise BridgeError("feature branch head must carry a cryptographic commit signature")
        self.verify()
        token = self.access_token()
        basic = base64.b64encode(f"{self.login}:{token}".encode()).decode("ascii")
        environment = {key: value for key, value in os.environ.items() if key not in TRACE_ENV}
        environment.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
            "GIT_TERMINAL_PROMPT": "0",
        })
        remote = f"https://github.com/{self.repository}.git"
        self.git_runner(
            worktree,
            ["push", "--porcelain", remote, f"HEAD:refs/heads/{expected_branch}"],
            environment,
        )
        remote_commit = self.transport(
            "GET", f"/repos/{self.repository}/commits/{head}", token, None,
        )
        verification = remote_commit.get("commit", {}).get("verification", {})
        if remote_commit.get("sha") != head or verification.get("verified") is not True:
            raise BridgeError("GitHub did not verify the published commit signature")
        return {"branch": expected_branch, "head_sha": head}

    def _upsert_comment(
        self, event: dict[str, Any], token: str, state: dict[str, Any], body: str,
    ) -> int:
        target = event["pull_request"] or event["issue"]
        key = str(target)
        comments = state.setdefault("comments", {})
        comment_id = comments.get(key)
        if not isinstance(comment_id, int):
            rows = self.transport(
                "GET", f"/repos/{self.repository}/issues/{target}/comments?per_page=100", token, None,
            )
            match = next(
                (row.get("id") for row in rows if isinstance(row, dict)
                 and COMMENT_MARKER in str(row.get("body", ""))),
                None,
            )
            comment_id = match if isinstance(match, int) else None
        if comment_id is None:
            response = self.transport(
                "POST", f"/repos/{self.repository}/issues/{target}/comments", token, {"body": body},
            )
            comment_id = response.get("id")
        else:
            self.transport(
                "PATCH", f"/repos/{self.repository}/issues/comments/{comment_id}", token, {"body": body},
            )
        if not isinstance(comment_id, int):
            raise BridgeError("GitHub did not return the lifecycle comment ID")
        comments[key] = comment_id
        return comment_id

    def _upsert_check(
        self, event: dict[str, Any], token: str, state: dict[str, Any], output: dict[str, str],
    ) -> int | None:
        head = event["head_sha"]
        if head is None:
            return None
        checks = state.setdefault("checks", {})
        check_id = checks.get(head)
        status, conclusion = check_status(event["state"])
        payload: dict[str, Any] = {
            "name": CHECK_NAME,
            "head_sha": head,
            "status": status,
            "output": output,
        }
        if status == "completed":
            payload["conclusion"] = conclusion
            payload["completed_at"] = _utc_now()
        elif status == "in_progress":
            payload["started_at"] = event["time"]
        if isinstance(check_id, int):
            response = self.transport(
                "PATCH", f"/repos/{self.repository}/check-runs/{check_id}", token, payload,
            )
        else:
            response = self.transport(
                "POST", f"/repos/{self.repository}/check-runs", token, payload,
            )
            check_id = response.get("id")
        if not isinstance(check_id, int):
            raise BridgeError("GitHub did not return the lifecycle check ID")
        checks[head] = check_id
        return check_id

    def publish(self, raw_event: object, state_path: Path) -> dict[str, Any]:
        event = validate_event(raw_event, self.repository)
        state = read_state(state_path)
        if event["sequence"] <= state.get("last_sequence", 0):
            raise BridgeError("event sequence must increase")
        body, output = render_event(event)
        self.verify()
        token = self.access_token()
        comment_id = self._upsert_comment(event, token, state, body)
        check_id = self._upsert_check(event, token, state, output)
        state.update({
            "schema": "nemoclaw-agent-github-state/1",
            "repository": self.repository,
            "last_sequence": event["sequence"],
            "last_event_time": event["time"],
        })
        write_state(state_path, state)
        return {"comment_id": comment_id, "check_run_id": check_id, "sequence": event["sequence"]}


def check_status(state: str) -> tuple[str, str | None]:
    return {
        "queued": ("queued", None),
        "in_progress": ("in_progress", None),
        "pass": ("completed", "success"),
        "fail": ("completed", "failure"),
        "blocked": ("completed", "action_required"),
        "cancelled": ("completed", "cancelled"),
    }[state]


def render_event(event: dict[str, Any]) -> tuple[str, dict[str, str]]:
    target = f"#{event['pull_request'] or event['issue']}"
    sha = event["head_sha"][:12] if event["head_sha"] else "not committed"
    rows = [
        COMMENT_MARKER,
        "### Agent contribution status",
        "",
        f"**{event['phase']} · {event['state']}**",
        "",
        f"| Scope | Current value |",
        f"| --- | --- |",
        f"| Target | {target} |",
        f"| Branch | `{event['branch']}` |",
        f"| Exact head | `{sha}` |",
        f"| Attempt | {event['attempt']} |",
        f"| Updated | {event['time']} |",
        "",
        event["summary"],
    ]
    if event["next"]:
        rows += ["", f"**Next:** {event['next']}"]
    if event["blocker"]:
        rows += ["", f"**Blocker:** {event['blocker']}"]
    if event["evidence"]:
        rows += ["", "**Evidence**", ""]
        rows += [f"- [{item['label']}]({item['url']}) · {item['state']}" for item in event["evidence"]]
    rows += [
        "",
        "_This bounded update omits prompts, tool transcripts, credentials, costs, private reasoning, and internal infrastructure._",
    ]
    body = "\n".join(rows) + "\n"
    summary = event["summary"]
    if event["blocker"]:
        summary += f" Blocker: {event['blocker']}"
    output = {
        "title": f"{event['phase']} · {event['state']}",
        "summary": summary,
        "text": body,
    }
    return body, output


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeError("agent GitHub state file is unreadable") from exc
    if not isinstance(state, dict):
        raise BridgeError("agent GitHub state file must contain an object")
    return state


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(state, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify", help="verify the bot identity and permission boundary")
    publish = subparsers.add_parser("publish", help="publish one validated lifecycle event")
    publish.add_argument("--event", type=Path, required=True)
    publish.add_argument("--state", type=Path, required=True)
    push = subparsers.add_parser("push", help="push one signed feature branch as the bot actor")
    push.add_argument("--worktree", type=Path, default=Path.cwd())
    push.add_argument("--branch", required=True)
    args = parser.parse_args()
    try:
        bridge = GithubBotBridge.from_env()
        if args.command == "verify":
            result = bridge.verify()
            print(
                f"GitHub bot verified: {result['login']} on {result['repository']}"
            )
        elif args.command == "publish":
            event = json.loads(args.event.read_text(encoding="utf-8"))
            result = bridge.publish(event, args.state)
            print(
                f"GitHub agent status published: sequence={result['sequence']} "
                f"comment={result['comment_id']} check={result['check_run_id'] or 'pending-head'}"
            )
        else:
            result = bridge.push_feature_branch(args.worktree, args.branch)
            print(f"GitHub bot feature branch published: {result['branch']} at {result['head_sha']}")
    except (BridgeError, OSError, json.JSONDecodeError) as exc:
        print(f"GitHub agent bridge: FAIL: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
