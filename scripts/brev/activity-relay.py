#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Hold the launchable's Activity session and relay the course's progress calls to it.

On a Brev launchable the course page calls /dli/api/activity/ on its own origin, and nginx
forwards those calls here. This process keeps the Activity API session and its token on the
launchable, presents the course's registered publication origin, and replaces an expired session
by replaying the milestones it has already recorded. Progress therefore follows the learner's
launchable, not a browser tab or cookie. It uses only the standard library and the image's python3.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import urllib.error
import urllib.request
import uuid

API = os.environ.get("NEMOCLAW_DLI_ACTIVITY_API", "https://activity-api.learn.nvidia.com").rstrip("/")
ORIGIN = os.environ.get("NEMOCLAW_DLI_ACTIVITY_ORIGIN", "https://brev.nvidia.com")
# The course always names itself; the publication the launchable reports under is configurable.
COURSE_ARTIFACT = "artifact_nemoclaw_web"
ARTIFACT = {
    "artifact_id": os.environ.get("NEMOCLAW_DLI_ACTIVITY_ARTIFACT", "artifact_nemoclaw_web"),
    "artifact_version": os.environ.get("NEMOCLAW_DLI_ACTIVITY_VERSION", "main"),
}
STATE = Path(os.environ.get("STATE_DIRECTORY") or os.environ.get("NEMOCLAW_DLI_ACTIVITY_STATE", ".")) / "session.json"
LISTEN = os.environ.get("NEMOCLAW_DLI_ACTIVITY_LISTEN", "127.0.0.1:8095")
SESSIONS = "/v1/activity-sessions"
ROUTE = re.compile(r"^/v1/activity-sessions/([0-9a-f-]{36})/(state|updates|referrals)$")
MILESTONE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
MAX_BODY = 16 * 1024
RENEW_BEFORE = timedelta(minutes=5)
HEALTH = b"nemoclaw-dli-activity ok\n"

lock = threading.Lock()


class Upstream(Exception):
    """The Activity API answered with an error status or could not be reached."""

    def __init__(self, status: int, body: bytes = b""):
        super().__init__(status)
        self.status, self.body = status, body


def load() -> dict:
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict) or not isinstance(state.get("relay_token"), str):
        # One stable session for the browser, whatever Activity session currently backs it.
        state = {"session_id": str(uuid.uuid4()), "relay_token": secrets.token_urlsafe(32),
                 "upstream": None, "milestones": [], "completed": False}
        save(state)
    return state


def save(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".next")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(state, stream)
    os.replace(temporary, STATE)


def call(method: str, path: str, body: dict | None = None, token: str | None = None,
         key: str | None = None) -> tuple[int, bytes]:
    headers = {"Accept": "application/json", "Origin": ORIGIN}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if key:
        headers["Idempotency-Key"] = key
    request = urllib.request.Request(API + path, method=method, headers=headers,
                                     data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read(MAX_BODY * 8)
    except urllib.error.HTTPError as error:
        raise Upstream(error.code, error.read(MAX_BODY)) from None
    except (OSError, ValueError):
        raise Upstream(502) from None


def expiring(upstream: dict | None) -> bool:
    try:
        expires = datetime.fromisoformat(upstream["expires_at"].replace("Z", "+00:00"))
    except (TypeError, KeyError, ValueError, AttributeError):
        return True
    return expires - datetime.now(timezone.utc) < RENEW_BEFORE


def renew(state: dict) -> dict:
    """Open a new Activity session and replay this launchable's recorded progress into it."""
    _, raw = call("POST", SESSIONS, ARTIFACT)
    created = json.loads(raw)
    upstream = {name: created[name] for name in ("session_id", "session_token", "expires_at")}
    updates = f"{SESSIONS}/{upstream['session_id']}/updates"
    for milestone in state["milestones"]:
        call("POST", updates, {"type": "milestone_completed", "payload": {"milestone_id": milestone}},
             upstream["session_token"], f"replay:{milestone}")
    if state["completed"]:
        call("POST", updates, {"type": "completed", "payload": {}}, upstream["session_token"], "replay:completed")
    state["upstream"] = upstream
    save(state)
    return upstream


def current(state: dict) -> dict:
    return renew(state) if expiring(state.get("upstream")) else state["upstream"]


def relabel(raw: bytes, upstream_id: str, session_id: str) -> bytes:
    """Answer with the launchable's stable session ID in place of the current Activity session's."""
    try:
        value = json.loads(raw)
    except ValueError:
        return raw
    for item in (value, value.get("state") if isinstance(value, dict) else None):
        if isinstance(item, dict) and item.get("session_id") == upstream_id:
            item["session_id"] = session_id
    return json.dumps(value).encode()


class Relay(BaseHTTPRequestHandler):
    server_version = "nemoclaw-dli-activity"
    sys_version = ""

    def log_message(self, format: str, *args) -> None:
        # Paths and statuses only; tokens travel in headers and are never logged.
        sys.stderr.write(f"{self.command} {self.path.split('?', 1)[0]} {args[1] if len(args) > 1 else ''}\n")

    def answer(self, status: int, body: bytes = b"{}", kind: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def payload(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY or self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            return None
        try:
            value = json.loads(self.rfile.read(length) or b"null")
        except ValueError:
            return None
        return value if isinstance(value, dict) else None

    def do_GET(self) -> None:
        if self.path == "/healthz":
            return self.answer(200, HEALTH, "text/plain")
        self.route("GET")

    def do_POST(self) -> None:
        self.route("POST")

    def route(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        try:
            with lock:
                state = load()
                if method == "POST" and path == SESSIONS:
                    body = self.payload()
                    if not body or body.get("artifact_id") != COURSE_ARTIFACT:
                        return self.answer(422)
                    upstream = current(state)
                    return self.answer(201, json.dumps({"session_id": state["session_id"],
                        "session_token": state["relay_token"], "expires_at": upstream["expires_at"]}).encode())
                match = ROUTE.match(path)
                if not match or (match[2] == "state") != (method == "GET"):
                    return self.answer(404)
                expected = f"Bearer {state['relay_token']}"
                presented = self.headers.get("X-Activity-Authorization", "")
                if match[1] != state["session_id"] or not hmac.compare_digest(presented, expected):
                    return self.answer(401)
                body = None if method == "GET" else self.payload()
                if method == "POST" and body is None:
                    return self.answer(422)
                key = self.headers.get("Idempotency-Key")
                upstream = current(state)
                for attempt in (1, 2):
                    try:
                        status, raw = call(method, f"{SESSIONS}/{upstream['session_id']}/{match[2]}",
                                           body, upstream["session_token"], key)
                        break
                    except Upstream as error:
                        # An Activity session that ended early is replaced once, with progress replayed.
                        if error.status != 401 or attempt == 2:
                            raise
                        upstream = renew(state)
                if match[2] == "updates" and body.get("type") == "milestone_completed":
                    milestone = (body.get("payload") or {}).get("milestone_id")
                    if isinstance(milestone, str) and MILESTONE.match(milestone) and milestone not in state["milestones"]:
                        state["milestones"].append(milestone)
                        save(state)
                elif match[2] == "updates" and body.get("type") == "completed" and not state["completed"]:
                    state["completed"] = True
                    save(state)
                return self.answer(status, relabel(raw, upstream["session_id"], state["session_id"]))
        except Upstream as error:
            status = error.status if 400 <= error.status < 500 and error.status != 401 else 502
            return self.answer(status, error.body if status != 502 else b'{"message":"Activity service unavailable"}')
        except (ValueError, KeyError, TypeError):
            return self.answer(502, b'{"message":"Activity service returned an invalid response"}')


def main() -> None:
    host, _, port = LISTEN.rpartition(":")
    if not API.startswith("https://") and not API.startswith(("http://127.0.0.1", "http://localhost")):
        raise SystemExit("NEMOCLAW_DLI_ACTIVITY_API must use HTTPS")
    server = ThreadingHTTPServer((host or "127.0.0.1", int(port)), Relay)
    load()
    server.serve_forever()


if __name__ == "__main__":
    main()
