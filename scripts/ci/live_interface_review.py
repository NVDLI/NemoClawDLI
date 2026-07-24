#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise fixed live model and OpenClaw transports from trusted default-branch code.

Candidate JavaScript never runs in this process. The preceding candidate-interface job proves the
exact artifact in an egress-denied browser. This process receives protected file variables, makes
only fixed requests, records only status classes/counts/durations, scans captured child output for
the exact protected values, and exits without retaining response bodies or sessions.
"""
from __future__ import annotations

import argparse
import base64
from collections.abc import Mapping
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODEL_ENDPOINTS = {
    "direct": "https://integrate.api.nvidia.com/v1/chat/completions",
    "relay": "https://nvidia-api-cors-proxy.experiments.courses.nvidia.com/v1/chat/completions",
}
MODELS = ("nvidia/nemotron-nano-12b-v2-vl", "nvidia/nemotron-3-nano-30b-a3b")
CDN_ORIGIN = "https://cdn.dli.learn.nvidia.com"
CAPABILITY_PROBES = {
    "assessment": "candidate-required-gate",
    "model-request": "trusted-live-model",
    "model-stream": "trusted-live-model",
    "openclaw-chat": "trusted-live-runtime",
    "openclaw-cron": "trusted-live-runtime",
    "openclaw-gateway": "trusted-live-runtime",
    "operator-terminal": "trusted-live-runtime",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward a learner-owned model credential through a redirect."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


MODEL_OPENER = urllib.request.build_opener(NoRedirect())


def assert_capabilities(site_root: Path) -> dict[str, list[str]]:
    """Require every candidate-declared capability to have a reviewed probe class."""
    source = site_root if (site_root / "web").is_dir() else site_root / "validated-source"
    declared: set[str] = set()
    inventories = sorted((source / "web").glob("*/interface-inventory.json"))
    if not inventories:
        raise ValueError("candidate contains no course interface inventory")
    for path in inventories:
        data = json.loads(path.read_text(encoding="utf-8"))
        values = data.get("live_capabilities")
        if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
            raise ValueError("candidate has malformed live capabilities")
        declared.update(values)
    missing = sorted(declared - CAPABILITY_PROBES.keys())
    if missing:
        raise ValueError("candidate capability has no trusted probe class: " + ",".join(missing))
    return {
        "candidate-required-gate": sorted(item for item in declared if CAPABILITY_PROBES[item] == "candidate-required-gate"),
        "trusted-live": sorted(item for item in declared if CAPABILITY_PROBES[item].startswith("trusted-live")),
    }


def pages_origin(environment: Mapping[str, str] = os.environ) -> str:
    """Return the current project's GitLab Pages origin from trusted CI metadata."""
    raw = environment.get("CI_PAGES_URL", "").strip()
    pages_domain = environment.get("CI_PAGES_DOMAIN", "").strip().lower().rstrip(".")
    parsed = urllib.parse.urlsplit(raw)
    host = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme != "https" or not host or parsed.username or parsed.password
        or parsed.port is not None or not pages_domain
        or (host != pages_domain and not host.endswith("." + pages_domain))
    ):
        raise ValueError("CI_PAGES_URL is not an HTTPS origin beneath CI_PAGES_DOMAIN")
    return f"https://{host}"


def _secret(variable: str) -> str:
    path = Path(os.environ.get(variable, ""))
    if not path.is_file() or path.stat().st_size > 65_536:
        raise ValueError(f"{variable} is missing or outside the protected file-variable size bound")
    value = path.read_text(encoding="utf-8").strip()
    if not value or any(ord(char) < 32 for char in value):
        raise ValueError(f"{variable} is empty or contains control characters")
    return value


def _scan(raw: bytes, secrets: list[str]) -> None:
    for value in secrets:
        if not value:
            continue
        encoded = value.encode()
        variants = {
            encoded,
            urllib.parse.quote(value, safe="").encode(),
            json.dumps(value).encode()[1:-1],
            base64.b64encode(encoded),
            base64.urlsafe_b64encode(encoded),
            encoded.hex().encode(),
        }
        if any(candidate and candidate in raw for candidate in variants):
            raise RuntimeError("a protected value appeared in captured output")


def _command(name: str, env_additions: dict[str, str], timeout: int, secrets: list[str]) -> dict[str, object]:
    started = time.monotonic()
    env = {
        key: os.environ[key] for key in
        ("PATH", "HOME", "TMPDIR", "NODE_PATH", "NODE_BIN", "CHROME_BIN", "PLAYWRIGHT_BROWSERS_PATH")
        if os.environ.get(key)
    }
    env.update(env_additions)
    proc = subprocess.run(
        [
            "bash", "scripts/runtime/browser_runtime_test.sh", "--gateway-only",
            "--terminal-contract", "--chat-contract", "--cron-contract",
        ],
        cwd=ROOT, env=env, capture_output=True, timeout=timeout,
    )
    raw = proc.stdout + proc.stderr
    _scan(raw, secrets)
    return {
        "id": name,
        "ok": proc.returncode == 0,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def _preflight(name: str, endpoint: str, origin: str) -> dict[str, object]:
    started = time.monotonic()
    request = urllib.request.Request(endpoint, method="OPTIONS", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type,x-billing-invoke-origin",
    })
    status = 0
    ok = False
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            allowed_origin = response.headers.get("Access-Control-Allow-Origin", "")
            allowed_headers = {
                value.strip().lower()
                for value in response.headers.get("Access-Control-Allow-Headers", "").split(",")
            }
            ok = (
                200 <= status < 300
                and allowed_origin in {"*", origin}
                and {"authorization", "content-type", "x-billing-invoke-origin"} <= allowed_headers
            )
    except urllib.error.HTTPError as exc:
        status = exc.code
    except (OSError, TimeoutError):
        status = 0
    return {
        "id": name, "ok": ok,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "status_class": status // 100,
    }


def _valid_model_body(data: bytes, stream: bool) -> bool:
    """Validate the bounded response contract without persisting model output."""

    try:
        if not stream:
            payload = json.loads(data)
            choices = payload.get("choices") if isinstance(payload, dict) else None
            return bool(
                isinstance(choices, list)
                and any(
                    isinstance(choice, dict)
                    and isinstance(choice.get("message"), dict)
                    and choice["message"].get("role") == "assistant"
                    and isinstance(choice["message"].get("content"), str)
                    and choice["message"]["content"].strip()
                    for choice in choices
                )
            )

        content = False
        terminal = False
        for line in data.decode("utf-8", errors="strict").splitlines():
            line = line.strip()
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data:"):
                return False
            value = line[5:].strip()
            if value == "[DONE]":
                terminal = True
                continue
            if terminal:
                return False
            payload = json.loads(value)
            choices = payload.get("choices") if isinstance(payload, dict) else None
            if not isinstance(choices, list):
                return False
            for choice in choices:
                delta = choice.get("delta") if isinstance(choice, dict) else None
                if (
                    isinstance(delta, dict) and isinstance(delta.get("content"), str)
                    and delta["content"].strip()
                ):
                    content = True
        return content and terminal
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return False


def _model(
    name: str, endpoint: str, key: str, browser_origin: str,
    attribution: str, stream: bool,
) -> dict[str, object]:
    started = time.monotonic()
    last_status = 0
    for model in MODELS:
        body = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": "Reply OK."}],
            "temperature": 0,
            "max_tokens": 2,
            "stream": stream,
        }).encode()
        request = urllib.request.Request(endpoint, data=body, method="POST", headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if stream else "application/json",
            "Origin": browser_origin,
            "X-BILLING-INVOKE-ORIGIN": attribution,
        })
        try:
            with MODEL_OPENER.open(request, timeout=60) as response:
                last_status = response.status
                data = response.read(1_048_577)
                allowed_origin = response.headers.get("Access-Control-Allow-Origin", "")
                if (
                    len(data) <= 1_048_576 and response.status == 200
                    and allowed_origin in {"*", browser_origin}
                    and _valid_model_body(data, stream)
                ):
                    return {
                        "id": name, "ok": True,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "status_class": 2,
                    }
        except urllib.error.HTTPError as exc:
            last_status = exc.code
        except (OSError, TimeoutError):
            last_status = 0
    return {
        "id": name, "ok": False,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "status_class": last_status // 100,
    }


def review(request: dict[str, object], retain: Path | None = None) -> list[dict[str, object]]:
    api_key = _secret("LIVE_NVIDIA_API_KEY_FILE")
    secrets = [api_key]
    project_pages_origin = pages_origin()
    results = [
        _preflight("model-direct-cdn-cors", MODEL_ENDPOINTS["direct"], CDN_ORIGIN),
        _preflight("model-relay-pages-cors", MODEL_ENDPOINTS["relay"], project_pages_origin),
    ]
    for route, endpoint in MODEL_ENDPOINTS.items():
        browser_origin = CDN_ORIGIN if route == "direct" else project_pages_origin
        for stream in (False, True):
            results.append(_model(
                f"nemoclaw-model-{route}-{'stream' if stream else 'request'}",
                endpoint, api_key, browser_origin, "dli-nemoclaw-web", stream,
            ))

    targets = request.get("targets")
    if not isinstance(targets, list) or not targets:
        raise ValueError("live request has no validated launchable target")
    for target in targets:
        slot = int(target["slot"])
        session = _secret(f"LIVE_CLAW_SESSION_{slot}_FILE")
        secrets.append(session)
        results.append(_command(
            f"openclaw-{target['provider']}-gateway-terminal-chat-cron",
            {
                "CLAW_URL": str(target["url"]),
                "CLAW_ACCESS_PROVIDER": str(target["provider"]),
                "CLAW_ACCESS_SESSION": session,
                "CLAW_ORIGIN": CDN_ORIGIN,
                "OPENCLAW_CORS_PROXY_BASE": "https://openclaw-cors-proxy.experiments.courses.nvidia.com",
            },
            600,
            secrets,
        ))

    report = {
        "schema": "dli-live-interface-review/1",
        "candidate_sha": request["source_sha"],
        "candidate_job_id": request["job_id"],
        "results": results,
    }
    if retain is not None:
        retain.parent.mkdir(parents=True, exist_ok=True)
        retain.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        _scan(retain.read_bytes(), secrets)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--request")
    group.add_argument("--assert-capabilities")
    parser.add_argument("--retain")
    args = parser.parse_args()
    try:
        if args.assert_capabilities:
            coverage = assert_capabilities(Path(args.assert_capabilities))
            print(
                "live capability coverage: OK candidate-gate="
                f"{len(coverage['candidate-required-gate'])} trusted-live={len(coverage['trusted-live'])}"
            )
            return 0
        results = review(
            json.loads(Path(args.request).read_text(encoding="utf-8")),
            Path(args.retain) if args.retain else None,
        )
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"live interface review: FAIL: {type(exc).__name__}")
        return 1
    failed = [str(item["id"]) for item in results if not item["ok"]]
    if failed:
        print("live interface review: FAIL components=" + ",".join(failed))
        return 1
    print(f"live interface review: OK components={len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
