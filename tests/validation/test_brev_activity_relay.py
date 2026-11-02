# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The Brev launchable's Activity relay against a loopback stand-in for the Activity API."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
RELAY_SOURCE = ROOT / "scripts/brev/activity-relay.py"
BROWSER_ARTIFACT = {"artifact_id": "artifact_nemoclaw_web", "artifact_version": "git-" + "a" * 40,
                    "artifact_digest": "sha256:" + "b" * 64}


class ActivityStandIn:
    """Answers the four Activity routes the relay uses, as the published contract describes them."""

    def __init__(self):
        self.sessions, self.requests, self.unavailable = {}, [], False
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, value):
                body = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def handle_any(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length)) if length else None
                stand_in.requests.append({"method": self.command, "path": self.path, "body": body,
                                          "headers": dict(self.headers)})
                if stand_in.unavailable:
                    return self.reply(503, {"detail": "unavailable"})
                if self.path == "/v1/activity-sessions" and self.command == "POST":
                    session = {"session_id": str(uuid.uuid4()), "session_token": "upstream-" + uuid.uuid4().hex,
                               "expires_at": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat().replace("+00:00", "Z")}
                    stand_in.sessions[session["session_id"]] = dict(session, milestones={}, completed=None)
                    return self.reply(201, session)
                parts = self.path.strip("/").split("/")
                session = stand_in.sessions.get(parts[2]) if len(parts) == 4 else None
                if not session or self.headers.get("Authorization") != "Bearer " + session["session_token"]:
                    return self.reply(401, {"detail": "unauthorized"})
                state = {"session_id": session["session_id"], "completed_at": session["completed"],
                         "milestones": [{"milestone_id": key, "completed_at": value}
                                        for key, value in session["milestones"].items()]}
                if parts[3] == "state":
                    return self.reply(200, state)
                if parts[3] == "updates" and body["type"] == "milestone_completed":
                    session["milestones"][body["payload"]["milestone_id"]] = "2026-11-02T00:00:00Z"
                elif parts[3] == "updates" and body["type"] == "completed":
                    session["completed"] = "2026-11-02T00:00:00Z"
                return self.reply(202, {"update_id": str(uuid.uuid4()), "received_at": "2026-11-02T00:00:00Z",
                                        "state": dict(state, session_id=session["session_id"])})

            do_GET = do_POST = handle_any

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def expire(self):
        self.sessions.clear()


class BrevActivityRelayTests(unittest.TestCase):
    def setUp(self):
        self.upstream = ActivityStandIn()
        self.addCleanup(self.upstream.server.server_close)
        self.addCleanup(self.upstream.server.shutdown)
        self.state = Path(tempfile.mkdtemp())
        self.start_relay()

    def start_relay(self, **overrides):
        environment = {"NEMOCLAW_DLI_ACTIVITY_API": self.upstream.url, "STATE_DIRECTORY": str(self.state), **overrides}
        with patch.dict(os.environ, environment):
            spec = importlib.util.spec_from_file_location(f"activity_relay_{uuid.uuid4().hex}", RELAY_SOURCE)
            self.relay = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.relay)
        server = ThreadingHTTPServer(("127.0.0.1", 0), self.relay.Relay)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.url = f"http://127.0.0.1:{server.server_address[1]}"

    def request(self, method, path, body=None, token=None, key=None, raw=None):
        headers = {"Content-Type": "application/json"} if body is not None or raw is not None else {}
        if token:
            headers["X-Activity-Authorization"] = f"Bearer {token}"
        if key:
            headers["Idempotency-Key"] = key
        data = raw if raw is not None else (None if body is None else json.dumps(body).encode())
        try:
            with urllib.request.urlopen(urllib.request.Request(self.url + path, data=data, method=method,
                                                               headers=headers), timeout=10) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"null")

    def open_session(self):
        status, session = self.request("POST", "/v1/activity-sessions", BROWSER_ARTIFACT)
        self.assertEqual(status, 201)
        return session

    def milestone(self, session, milestone, key="key-1"):
        return self.request("POST", f"/v1/activity-sessions/{session['session_id']}/updates",
                            {"type": "milestone_completed", "payload": {"milestone_id": milestone}},
                            session["session_token"], key)

    def test_session_uses_the_brev_publication_and_keeps_the_activity_token_on_the_launchable(self):
        session = self.open_session()
        created = self.upstream.requests[0]
        self.assertEqual(created["headers"]["Origin"], "https://brev.nvidia.com")
        self.assertEqual(created["body"], {"artifact_id": "artifact_nemoclaw_web", "artifact_version": "main"})
        upstream_session = next(iter(self.upstream.sessions.values()))
        self.assertNotEqual(session["session_id"], upstream_session["session_id"])
        self.assertNotIn("upstream-", json.dumps(session))
        self.assertEqual(stat.S_IMODE((self.state / "session.json").stat().st_mode), 0o600)

        status, state = self.request("GET", f"/v1/activity-sessions/{session['session_id']}/state",
                                     token=session["session_token"])
        self.assertEqual((status, state["session_id"]), (200, session["session_id"]))
        self.assertEqual(self.upstream.requests[-1]["headers"]["Origin"], "https://brev.nvidia.com")
        self.assertNotIn("Cookie", self.upstream.requests[-1]["headers"])

    def test_the_course_can_report_under_another_configured_publication(self):
        # A stage test publication names a different artifact; the course still names itself.
        self.start_relay(NEMOCLAW_DLI_ACTIVITY_ARTIFACT="s-fx-43", NEMOCLAW_DLI_ACTIVITY_VERSION="v1",
                         NEMOCLAW_DLI_ACTIVITY_ORIGIN="http://localhost:3000")
        self.open_session()
        created = self.upstream.requests[0]
        self.assertEqual(created["body"], {"artifact_id": "s-fx-43", "artifact_version": "v1"})
        self.assertEqual(created["headers"]["Origin"], "http://localhost:3000")
        self.assertEqual(self.request("POST", "/v1/activity-sessions", dict(BROWSER_ARTIFACT, artifact_id="s-fx-43"))[0], 422)

    def test_another_artifact_or_a_malformed_request_reaches_nothing_upstream(self):
        for body in ({"artifact_id": "artifact_other"}, {}):
            self.assertEqual(self.request("POST", "/v1/activity-sessions", body)[0], 422)
        self.assertEqual(self.request("POST", "/v1/activity-sessions", raw=b"x" * (17 * 1024))[0], 422)
        self.assertEqual(self.upstream.requests, [])

    def test_only_the_launchable_session_and_its_relay_token_are_accepted(self):
        session = self.open_session()
        state = f"/v1/activity-sessions/{session['session_id']}/state"
        self.assertEqual(self.request("GET", state)[0], 401)
        self.assertEqual(self.request("GET", state, token=session["session_token"] + "x")[0], 401)
        self.assertEqual(self.request("GET", f"/v1/activity-sessions/{uuid.uuid4()}/state",
                                      token=session["session_token"])[0], 401)
        self.assertEqual(self.request("POST", state, {}, session["session_token"])[0], 404)
        self.assertEqual(self.request("GET", f"/v1/activity-sessions/{session['session_id']}/updates",
                                      token=session["session_token"])[0], 404)

    def test_milestones_are_forwarded_once_recorded_and_relabelled(self):
        session = self.open_session()
        status, reply = self.milestone(session, "01a:model-call-verified")
        self.assertEqual((status, reply["state"]["session_id"]), (202, session["session_id"]))
        forwarded = self.upstream.requests[-1]
        self.assertEqual(forwarded["headers"]["Idempotency-Key"], "key-1")
        self.assertEqual(json.loads((self.state / "session.json").read_text())["milestones"],
                         ["01a:model-call-verified"])

    def test_an_ended_activity_session_is_replaced_once_with_progress_replayed(self):
        session = self.open_session()
        self.milestone(session, "01a:model-call-verified")
        self.request("POST", f"/v1/activity-sessions/{session['session_id']}/updates",
                     {"type": "completed", "payload": {}}, session["session_token"], "key-done")
        self.upstream.expire()
        status, reply = self.milestone(session, "01b:react-loop-complete", "key-2")
        self.assertEqual(status, 202)
        replacement = next(iter(self.upstream.sessions.values()))
        self.assertEqual(set(replacement["milestones"]), {"01a:model-call-verified", "01b:react-loop-complete"})
        self.assertIsNotNone(replacement["completed"])
        keys = [item["headers"].get("Idempotency-Key") for item in self.upstream.requests]
        self.assertIn("replay:01a:model-call-verified", keys)
        self.assertEqual(reply["state"]["session_id"], session["session_id"])

    def test_a_session_close_to_expiry_is_renewed_before_use(self):
        session = self.open_session()
        saved = json.loads((self.state / "session.json").read_text())
        saved["upstream"]["expires_at"] = "2026-01-01T00:00:00Z"
        (self.state / "session.json").write_text(json.dumps(saved))
        status, _ = self.request("GET", f"/v1/activity-sessions/{session['session_id']}/state",
                                 token=session["session_token"])
        self.assertEqual(status, 200)
        self.assertEqual(sum(item["path"] == "/v1/activity-sessions" for item in self.upstream.requests), 2)

    def test_a_restarted_relay_keeps_the_launchable_session(self):
        session = self.open_session()
        self.milestone(session, "01a:model-call-verified")
        self.start_relay()
        reopened = self.open_session()
        self.assertEqual((reopened["session_id"], reopened["session_token"]),
                         (session["session_id"], session["session_token"]))
        status, state = self.request("GET", f"/v1/activity-sessions/{session['session_id']}/state",
                                     token=session["session_token"])
        self.assertEqual((status, state["milestones"][0]["milestone_id"]), (200, "01a:model-call-verified"))

    def test_an_unavailable_service_answers_without_detail_or_credentials(self):
        session = self.open_session()
        self.upstream.unavailable = True
        stderr = io.StringIO()
        with patch("sys.stderr", stderr):
            status, reply = self.milestone(session, "01a:model-call-verified")
        self.assertEqual((status, reply), (502, {"message": "Activity service unavailable"}))
        self.assertNotIn(session["session_token"], stderr.getvalue())
        self.assertNotIn("upstream-", stderr.getvalue())

    def test_health_identifies_the_relay(self):
        with urllib.request.urlopen(self.url + "/healthz", timeout=5) as response:
            self.assertEqual(response.read(), b"nemoclaw-dli-activity ok\n")


if __name__ == "__main__":
    unittest.main()
