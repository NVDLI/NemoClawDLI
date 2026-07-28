#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit that browser model-relay routing is explicit, bounded, and documented.

This is a narrow source audit. It does not contact the hosted service; it checks
that the published course defaults are origin-bound, every other course origin
stays direct, and custom endpoints never enter the model relay. OpenClaw's
provider-selected relay is separately fixed to the operated course endpoint.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
BUILD_PROXY = "https://nvidia-api-cors-proxy.experiments.courses.nvidia.com"
OPENCLAW_PROXY = "https://openclaw-cors-proxy.experiments.courses.nvidia.com"
LEGACY_BILLING_HEADER = "X-BILLING-" + "SOURCE"
EXPECTED_MODEL_RELAY_DEFAULT_ORIGINS = [
    "https://cdn.dli.learn.nvidia.com",
    "https://nvdli.github.io",
]

CHECKS = [
    (
        "runtime supports independent chat and embedding routes",
        "web/nemoclaw/scripts/_shared.js",
        ["DEFAULT_MODEL_API_BASE_URL", "MODEL_API_BASE_URL_KEY", "EMBEDDING_API_BASE_URL_KEY", "normalizeModelApiBaseUrl", "getModelApiBaseUrl", "getEmbeddingApiBaseUrl", "export function setModelApiBaseUrl(raw)", "export function setEmbeddingApiBaseUrl(raw)"],
        [
            r"function\s+suggestedModelApiBaseUrl",
            r'\.get\("(?:base_url|model_base_url|model|embedding_base_url|embedding_model)"\)',
        ],
    ),
    (
        "runtime exports iframe opt-in controls",
        "web/nemoclaw/scripts/_shared.js",
        ["iframeProxyModeEnabled", "setIframeProxyMode", "nemoclaw_iframe_proxy_opt_in"],
        [],
    ),
    (
        "runtime binds the relay default to the published course origins and preserves explicit overrides",
        "web/nemoclaw/scripts/_shared.js",
        ["https://integrate.api.nvidia.com/v1", 'const IFRAME_PROXY_URL = "https://nvidia-api-cors-proxy.experiments.courses.nvidia.com/v1"', "MODEL_RELAY_DEFAULT_ORIGINS", "https://cdn.dli.learn.nvidia.com", "https://nvdli.github.io", "defaultIframeProxyModeForLocation", 'stored === "0"', 'localStorage.setItem(IFRAME_PROXY_OPT_IN_KEY, enabled ? "1" : "0")', "iframe_proxy", "lms_proxy", "iframeProxy: false", "iframeProxy: true"],
        [r'const\s+DIRECT_URL\s*=\s*"https://nvidia-api-cors-proxy'],
    ),
    (
        "billing header stays on NVIDIA direct and iframe-proxy paths",
        "web/nemoclaw/scripts/_shared.js",
        ['billingAttributionEnabled(url)', 'billingAttributionEnabled(cfg.url)', 'host === "integrate.api.nvidia.com"', 'host === "nvidia-api-cors-proxy.experiments.courses.nvidia.com"', "X-BILLING-INVOKE-ORIGIN"],
        [r'if\s*\(cfg\.iframeProxy\).*X-BILLING-INVOKE-ORIGIN', r'if\s*\(iframeProxyModeEnabled\(\)\).*X-BILLING-INVOKE-ORIGIN'],
    ),
    (
        "key panel exposes independent routes and relay controls",
        "web/nemoclaw/scripts/_keypanel.js",
        ['<input type="url" class="model-api-base-url"', '<input type="url" class="embedding-api-base-url"', "normalizeModelApiBaseUrl(endpointInput.value)", "normalizeModelApiBaseUrl(embeddingEndpointInput.value)", "setModelApiBaseUrl(endpoint)", "setEmbeddingApiBaseUrl(embeddingEndpoint)", "setIframeProxyMode(defaultEndpoint &&", "iframe-proxy-toggle", "Use the NVIDIA DLI browser relay"],
        [],
    ),
    (
        "landing page mounts the bounded route controls",
        "web/nemoclaw/index.html",
        [
            'id="key-panel"',
            "mountKeyPanel(document.getElementById(\"key-panel\")",
            "selected endpoint",
        ],
        [],
    ),
    (
        "relay explorer describes the contract without advertising operated endpoints",
        "scripts/cors-proxy/SKILL.html",
        ["compact teaching references", "deployable"],
        [re.escape(BUILD_PROXY), re.escape(OPENCLAW_PROXY)],
    ),
    (
        "reference implementation findings are documented",
        "scripts/security/iframe_proxy_worker_findings.md",
        ["compact teaching references", "X-BILLING-INVOKE-ORIGIN", "ALLOWED_ORIGINS", "deployment-owner review", "exact published course origins", "explicit direct override"],
        [],
    ),
    (
        "OpenClaw relay excludes model billing attribution",
        "scripts/cors-proxy/cors-proxy-worker-openclaw.js",
        ["x-openclaw-session-key", "CF-Access-Jwt-Assertion"],
        [r"X-BILLING-INVOKE-ORIGIN"],
    ),
    (
        "OpenClaw relay binds provider sessions without forwarding service tokens",
        "scripts/cors-proxy/cors-proxy-worker-openclaw.js",
        ["Neutral access sessions require an explicit access provider.", 'fwdHeaders.set("X-Pomerium-Authorization", accessSession)', 'fwdHeaders.delete("CF-Access-Client-Id")', 'fwdHeaders.delete("CF-Access-Client-Secret")'],
        [r"_pomerium=", r"env\.CF_ACCESS_CLIENT"],
    ),
    (
        "OpenClaw relay is centralized, approved, and non-bypassable",
        "web/nemoclaw/scripts/_connection.js",
        [OPENCLAW_PROXY, "DEFAULT_OPENCLAW_PROXY_BASE", "OPENCLAW_PROXY_BASE_KEY", "OPENCLAW_PROXY_ENABLED_KEY", "migrateOpenClawConnectionStorage", "OpenClaw launchables use the approved NVIDIA DLI relay", "OpenClaw launchables use the approved NVIDIA DLI relay; it cannot be disabled.", "shouldProxyOpenClaw", "new URL(DEFAULT_OPENCLAW_PROXY_BASE)", "upstream.origin === loc.origin", 'return Boolean(String(accessSession || "").trim())'],
        [
            r'\.get\("openclaw_(?:url|access_provider|proxy|proxy_base)"\)',
            r"new URL\(config\.base\)",
            r"!config\.enabled",
        ],
    ),
    (
        "OpenClaw lesson delegates transport to the provider-aware helper",
        "web/nemoclaw/03a-kickstart.html",
        ["helpers.openclawBootstrapRequest(PATH", "signal"],
        [r"\bTRANSPORT\b", r"proxyControls\s*:\s*true", r"X-OpenClaw-Access-Session", r"CF-Access-Jwt-Assertion"],
    ),
    (
        "OpenShell terminal detects direct access and retains provider-bound fallback",
        "web/nemoclaw/scripts/_openshell.js",
        [
            "getOpenClawWsRelayEnabled",
            "const resolvedProvider = accessProviderForOpenClawUrl(rawUrl, accessProvider);",
            "relayWebSocket === true",
            "relayWebSocket === null && (getOpenClawWsRelayEnabled() ||",
            'resolvedProvider === "pomerium" && Boolean(accessSession)',
            'openclawWebSocketUrl(',
            '"/ws/terminal?cmd=" + encodeURIComponent(cmd)',
            'relayEnabled ? getOpenClawProxyConfig() : { enabled: false, base: "" }',
            "const wsUrls = [routed.url]",
        ],
        # The terminal must not rebuild a socket URL from the raw launchable or
        # keep a second fallback candidate outside the shared routing helper.
        [
            r'\.replace\(\s*/\^https?[\s\S]{0,160}/ws/terminal',
            r"\bdirect\.url\b",
        ],
    ),
]

WORKER_FINDINGS = [
    (
        "build worker reflects page origins; review exact origin allowlist before deployment changes",
        "scripts/cors-proxy/cors-proxy-worker-build.js",
        ["Access-Control-Allow-Origin", "origin"],
    ),
    (
        "launchable worker keeps upstream host allowlist but still reflects page origins",
        "scripts/cors-proxy/cors-proxy-worker-openclaw.js",
        ["brevlab.com", "Access-Control-Allow-Origin"],
    ),
]


def request(request: Request) -> tuple[int, dict[str, str], str]:
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as exc:
        response = exc
    status = response.status
    headers = {key.lower(): value for key, value in response.headers.items()}
    body = response.read(500).decode("utf-8", errors="replace")
    return status, headers, body


def live_findings() -> list[str]:
    """Probe public, unauthenticated relay boundaries without sending credentials."""
    origin = "https://relay-validator.invalid"
    findings: list[str] = []
    probes = (
        (
            "model relay preflight",
            Request(
                BUILD_PROXY + "/v1/chat/completions",
                method="OPTIONS",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "authorization,content-type,x-billing-invoke-origin",
                },
            ),
            ("authorization", "content-type", "x-billing-invoke-origin"),
        ),
        (
            "OpenClaw relay preflight",
            Request(
                OPENCLAW_PROXY + "/https/example.com/health",
                method="OPTIONS",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "authorization,x-openclaw-session-key",
                },
            ),
            ("authorization", "x-openclaw-session-key"),
        ),
    )
    for label, probe, required_headers in probes:
        try:
            status, headers, _ = request(probe)
        except (OSError, URLError) as exc:
            findings.append(f"{label} unreachable: {exc}")
            continue
        allow_headers = headers.get("access-control-allow-headers", "").lower()
        if not 200 <= status < 300:
            findings.append(f"{label} returned HTTP {status}")
        if headers.get("access-control-allow-origin") != origin:
            findings.append(f"{label} did not echo the requesting Origin")
        for header in required_headers:
            if header not in allow_headers:
                findings.append(f"{label} does not allow {header}")

    try:
        status, _, body = request(Request(OPENCLAW_PROXY + "/https/example.com/health"))
        if status != 403 or "allowlist" not in body.lower():
            findings.append("OpenClaw relay did not reject an arbitrary upstream host")
    except (OSError, URLError) as exc:
        findings.append(f"OpenClaw upstream-boundary probe unreachable: {exc}")
    return findings


def source_findings(
    root: Path = ROOT,
    replacements: dict[str, tuple[str, str]] | None = None,
    *,
    scan_retired: bool = True,
) -> list[str]:
    replacements = replacements or {}
    failures: list[str] = []
    for label, rel, required, forbidden in CHECKS:
        text = (root / rel).read_text(encoding="utf-8")
        if rel in replacements:
            old, new = replacements[rel]
            text = text.replace(old, new, 1)
        missing = [needle for needle in required if needle not in text]
        bad = [pat for pat in forbidden if re.search(pat, text)]
        if missing or bad:
            parts = []
            if missing:
                parts.append("missing " + ", ".join(missing))
            if bad:
                parts.append("forbidden " + ", ".join(bad))
            failures.append(f"FAIL {label} ({rel}): " + "; ".join(parts))
    shared = (root / "web/nemoclaw/scripts/_shared.js").read_text(encoding="utf-8")
    if "web/nemoclaw/scripts/_shared.js" in replacements:
        old, new = replacements["web/nemoclaw/scripts/_shared.js"]
        shared = shared.replace(old, new, 1)
    match = re.search(r"MODEL_RELAY_DEFAULT_ORIGINS\s*=\s*new Set\(\[([^]]*)\]\)", shared)
    origins = re.findall(r'["\'](https?://[^"\']+)["\']', match.group(1)) if match else []
    if origins != EXPECTED_MODEL_RELAY_DEFAULT_ORIGINS:
        failures.append(
            "FAIL model relay default origin allowlist must contain only "
            + ", ".join(EXPECTED_MODEL_RELAY_DEFAULT_ORIGINS)
        )
    if scan_retired:
        tracked = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8").split("\0")
        for rel in filter(None, tracked):
            try:
                text = (root / rel).read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if rel in replacements:
                old, new = replacements[rel]
                text = text.replace(old, new, 1)
            if LEGACY_BILLING_HEADER.casefold() in text.casefold():
                failures.append(f"FAIL retired billing header remains in {rel}")
    return failures


def self_test() -> list[str]:
    failures: list[str] = []
    cases = (
        ("saved chat endpoint", "web/nemoclaw/scripts/_shared.js", "export function setModelApiBaseUrl(raw)", "function removedModelSetter(raw)"),
        ("saved embedding endpoint", "web/nemoclaw/scripts/_shared.js", "export function setEmbeddingApiBaseUrl(raw)", "function removedEmbeddingSetter(raw)"),
        ("retired model query prefill", "web/nemoclaw/scripts/_shared.js", "export function getModelApiBaseUrl()", 'const legacyModel = new URLSearchParams(location.search).get("base_url");\n\nexport function getModelApiBaseUrl()'),
        ("explicit setup field", "web/nemoclaw/scripts/_keypanel.js", '<input type="url" class="model-api-base-url"', '<input type="url" class="removed-endpoint-field"'),
        ("custom endpoint bypasses iframe relay", "web/nemoclaw/scripts/_keypanel.js", "setIframeProxyMode(defaultEndpoint &&", "setIframeProxyMode(true &&"),
        ("bounded CDN relay default", "web/nemoclaw/scripts/_shared.js", '"https://cdn.dli.learn.nvidia.com"', '"https://example.com"'),
        ("bounded Pages relay default", "web/nemoclaw/scripts/_shared.js", '"https://nvdli.github.io"', '"https://nvdli.github.io.example.invalid"'),
        ("explicit direct override", "web/nemoclaw/scripts/_shared.js", 'stored === "0"', 'stored === "disabled"'),
        ("custom endpoint omits NVIDIA attribution", "web/nemoclaw/scripts/_shared.js", "if (billingAttributionEnabled(cfg.url))", "if (true)"),
        ("credential destination warning", "web/nemoclaw/index.html", "selected endpoint", "configured service"),
        ("OpenClaw excludes model billing attribution", "scripts/cors-proxy/cors-proxy-worker-openclaw.js", "x-openclaw-session-key, Accept", "x-openclaw-session-key, X-BILLING-INVOKE-ORIGIN, Accept"),
        ("OpenClaw Pomerium header", "scripts/cors-proxy/cors-proxy-worker-openclaw.js", 'fwdHeaders.set("X-Pomerium-Authorization", accessSession)', 'fwdHeaders.set("Cookie", "_pomerium=" + accessSession)'),
        ("OpenClaw provider declaration", "scripts/cors-proxy/cors-proxy-worker-openclaw.js", "Neutral access sessions require an explicit access provider.", "Neutral access sessions may omit a provider."),
        ("OpenClaw approved relay allowlist", "web/nemoclaw/scripts/_connection.js", "new URL(DEFAULT_OPENCLAW_PROXY_BASE)", "new URL(config.base)"),
        ("OpenClaw relay cannot be disabled", "web/nemoclaw/scripts/_connection.js", 'throw new Error("OpenClaw launchables use the approved NVIDIA DLI relay; it cannot be disabled.");', "return { enabled: false, base: DEFAULT_OPENCLAW_PROXY_BASE };"),
        ("OpenClaw retired presenter query", "web/nemoclaw/scripts/_connection.js", "export function getOpenClawProxyConfig()", 'const legacyProxy = new URLSearchParams(location.search).get("openclaw_proxy");\n\nexport function getOpenClawProxyConfig()'),
        ("OpenClaw same-origin exception", "web/nemoclaw/scripts/_connection.js", "if (loc && upstream.origin === loc.origin) return false;", "if (loc && upstream.origin !== loc.origin) return false;"),
        ("OpenClaw manual-session relay", "web/nemoclaw/scripts/_connection.js", 'return Boolean(String(accessSession || "").trim());', "return false;"),
        ("OpenClaw lesson helper", "web/nemoclaw/03a-kickstart.html", "helpers.openclawBootstrapRequest(PATH", "helpers.fetchOpenClawDirect(PATH"),
        ("OpenClaw lesson restores transport branch", "web/nemoclaw/03a-kickstart.html", "const PATH = '/api/agent';", "const TRANSPORT = 'direct';\nconst PATH = '/api/agent';"),
        ("OpenShell shared routing", "web/nemoclaw/scripts/_openshell.js", "openclawWebSocketUrl(", "removedWebSocketRouter("),
        ("OpenShell drops the shared provider decision", "web/nemoclaw/scripts/_openshell.js", "const resolvedProvider = accessProviderForOpenClawUrl(rawUrl, accessProvider);", "const resolvedProvider = guessTerminalProvider(rawUrl, accessProvider);"),
        ("OpenShell drops the saved relay opt-in", "web/nemoclaw/scripts/_openshell.js", "relayWebSocket === null && (getOpenClawWsRelayEnabled() ||", "relayWebSocket === null && (false ||"),
        ("OpenShell forces the relay", "web/nemoclaw/scripts/_openshell.js", 'relayEnabled ? getOpenClawProxyConfig() : { enabled: false, base: "" }', "getOpenClawProxyConfig()"),
        ("OpenShell disables explicit relay selection", "web/nemoclaw/scripts/_openshell.js", "relayWebSocket === true", "relayWebSocket === false"),
        ("OpenShell deletes its single terminal route", "web/nemoclaw/scripts/_openshell.js", "const wsUrls = [routed.url];", ""),
        ("OpenShell renames its single terminal route", "web/nemoclaw/scripts/_openshell.js", "const wsUrls = [routed.url]", "const terminalRoutes = [routed.url]"),
        ("OpenShell restores the direct-first fallback", "web/nemoclaw/scripts/_openshell.js", "const wsUrls = [routed.url]", "const wsUrls = [direct.url, routed.url]"),
        ("OpenShell appends a direct fallback candidate", "web/nemoclaw/scripts/_openshell.js", "const wsUrls = [routed.url]", "const wsUrls = [routed.url, direct.url]"),
        ("OpenShell rebuilds a socket URL from the raw launchable", "web/nemoclaw/scripts/_openshell.js", "let launchableOrigin = rawUrl;", 'const bypass = rawUrl.replace(/^https/, "wss") + "/ws/terminal?cmd=" + encodeURIComponent(cmd);\n  let launchableOrigin = rawUrl;'),
    )
    # Every mutation must produce a finding the unmutated tree does not already have. A stale
    # mutation string then fails as an escape instead of riding an unrelated failure, and a
    # detector that no longer matches its own source cannot report PASS.
    baseline = source_findings(scan_retired=False)
    failures.extend(f"unmutated source already fails: {item}" for item in baseline)
    for label, rel, old, new in cases:
        mutated = source_findings(replacements={rel: (old, new)}, scan_retired=False)
        if not [item for item in mutated if item not in baseline]:
            failures.append(f"mutation escaped: {label}")
    legacy_mutation = {
        "web/nemoclaw/scripts/_shared.js": ("X-BILLING-INVOKE-ORIGIN", LEGACY_BILLING_HEADER),
    }
    tracked_baseline = source_findings()
    if not [item for item in source_findings(replacements=legacy_mutation) if item not in tracked_baseline]:
        failures.append("mutation escaped: retired billing header")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="probe both public relay contracts without credentials")
    parser.add_argument("--self-test", action="store_true", help="prove endpoint and relay mutation detectors")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        if failures:
            print("\n".join(f"FAIL {item}" for item in failures), file=sys.stderr)
            return 1
        print("iframe/model endpoint audit self-test: PASS")
        return 0
    failures = source_findings()
    for label, _, _, _ in CHECKS:
        if not any(label in item for item in failures):
            print(f"PASS {label}")
    for label, rel, required in WORKER_FINDINGS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        missing = [needle for needle in required if needle not in text]
        if missing:
            failures.append(f"FAIL worker finding source changed unexpectedly ({rel}): missing " + ", ".join(missing))
        else:
            print(f"NOTE {label} ({rel})")
    if args.live:
        failures.extend(f"FAIL {item}" for item in live_findings())
        if not any(item.startswith("FAIL ") for item in failures):
            print("PASS live hosted relay contracts")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
