#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Keep model, embedding, and OpenClaw endpoint registrations distinct."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SHARED = "web/nemoclaw/scripts/_shared.js"
OPENCLAW = "web/nemoclaw/scripts/_openclaw.js"
CONNECTION = "web/nemoclaw/scripts/_connection.js"
KEYPANEL = "web/nemoclaw/scripts/_keypanel.js"
RUNTIME_HARNESS = "scripts/runtime/test_page_runtime.js"
EXPLORER = "web/_skill_explorer.js"
BROWSER_INTEGRATION = "scripts/validation/runtime_integration_browser_audit.py"
PAGES = (
    "web/nemoclaw/03a-kickstart.html",
    "i18n/pt/web/nemoclaw/03a-kickstart.html",
    "i18n/es/web/nemoclaw/03a-kickstart.html",
)

PROTECTED_WRITERS = {
    "nemoclaw_model_api_base_url_v1": {SHARED, RUNTIME_HARNESS},
    "nemoclaw_model_id_v1": {SHARED, RUNTIME_HARNESS},
    "nemoclaw_embedding_api_base_url_v1": {SHARED, RUNTIME_HARNESS},
    "nemoclaw_embedding_model_id_v1": {SHARED},
    "nemoclaw_embedding_api_key_v1": {SHARED},
    "nvapi": {SHARED, KEYPANEL, RUNTIME_HARNESS, EXPLORER},
    "nemoclaw_clawurl": {CONNECTION},
    "nemoclaw_clawrawurl": {CONNECTION},
    "nemoclaw_clawtoken": {CONNECTION},
    "nemoclaw_clawcfjwt": {CONNECTION},
    "nemoclaw_openclaw_access_provider_v1": {CONNECTION},
    "nemoclaw_openclaw_access_session_v1": {CONNECTION},
    "nemoclaw_openclaw_proxy_base_v1": {CONNECTION},
    "nemoclaw_openclaw_proxy_enabled_v1": {CONNECTION},
}

MODEL_QUERY_KEYS = ("base_url", "model_base_url", "model", "embedding_base_url", "embedding_model")
OPENCLAW_QUERY_KEYS = ("openclaw_url", "openclaw_proxy_base", "openclaw_proxy", "openclaw_access_provider")


def source_files() -> list[Path]:
    files: list[Path] = []
    for base in (ROOT / "web/nemoclaw", ROOT / "i18n/pt/web/nemoclaw", ROOT / "i18n/es/web/nemoclaw"):
        for path in base.rglob("*"):
            if path.suffix not in {".js", ".mjs", ".html"}:
                continue
            if {"vendor", "mats", "assets", "standalone"}.intersection(path.parts):
                continue
            files.append(path)
    files.append(ROOT / RUNTIME_HARNESS)
    files.append(ROOT / EXPLORER)
    return sorted(set(files))


def text(rel: str, overrides: dict[str, str]) -> str:
    return overrides.get(rel, (ROOT / rel).read_text(encoding="utf-8"))


def audit(overrides: dict[str, str] | None = None) -> list[str]:
    overrides = overrides or {}
    findings: list[str] = []
    shared = text(SHARED, overrides)
    openclaw = text(OPENCLAW, overrides)
    connection = text(CONNECTION, overrides)
    runtime = text(RUNTIME_HARNESS, overrides)
    explorer = text(EXPLORER, overrides)

    storage_contract = (
        'const MODEL_API_BASE_URL_KEY = "nemoclaw_model_api_base_url_v1"',
        'const MODEL_ID_KEY = "nemoclaw_model_id_v1"',
        'const EMBEDDING_API_BASE_URL_KEY = "nemoclaw_embedding_api_base_url_v1"',
        'const EMBEDDING_MODEL_ID_KEY = "nemoclaw_embedding_model_id_v1"',
        'const EMBEDDING_API_KEY = "nemoclaw_embedding_api_key_v1"',
    )
    for token in storage_contract:
        if token not in shared:
            findings.append(f"model registry contract missing: {token}")
    if len({re.search(r'"([^"\n]+)"', token).group(1) for token in storage_contract}) != len(storage_contract):
        findings.append("model and embedding storage registrations are not distinct")

    for key in MODEL_QUERY_KEYS:
        if f'.get("{key}")' not in shared:
            findings.append(f"model registry does not own query parameter: {key}")
        if f'.get("{key}")' in connection:
            findings.append(f"OpenClaw registry reads model query parameter: {key}")
    for key in OPENCLAW_QUERY_KEYS:
        if f'params.get("{key}")' not in connection:
            findings.append(f"OpenClaw registry does not own query parameter: {key}")
        if f'.get("{key}")' in shared:
            findings.append(f"model registry reads OpenClaw query parameter: {key}")

    if 'sessionStorage.setItem("__nv_slim_cfg_v1"' in runtime:
        findings.append("runtime harness bypasses the model registry with a private config cache write")
    if "shared.setOpenClawConnection({ rawUrl: u, token: t, accessProvider: provider, accessSession: session })" not in runtime:
        findings.append("runtime harness bypasses the OpenClaw connection registry")
    if "courseRuntime().then(function (shared)" not in explorer or "return shared.chat({" not in explorer:
        findings.append("SKILL explorer bypasses the canonical course model registry")
    if "nemoclaw_claw" in explorer or "App.prototype.proxy" in explorer:
        findings.append("SKILL explorer redeclares endpoint or OpenClaw state")
    if "SKILL explorer model registry handoff failed" not in text("scripts/validation/runtime_integration_browser_audit.py", overrides):
        findings.append("browser integration audit does not execute the SKILL explorer model handoff")

    openclaw_contract = (
        'const isOpenClaw = connectionKind === "openclaw"',
        "const openClawConnection = isOpenClaw",
        "? getOpenClawConnection()",
        "const savedUrl = isOpenClaw",
        "if (!isOpenClaw)",
        'connectionKind: "openclaw"',
        'connectionKind: "model"',
        "readOnly: true",
    )
    for token in openclaw_contract:
        if token not in openclaw:
            findings.append(f"typed endpoint probe contract missing: {token}")
    connection_contract = (
        'export const OPENCLAW_URL_KEY = "nemoclaw_clawurl"',
        'export const OPENCLAW_RAW_URL_KEY = "nemoclaw_clawrawurl"',
        'export const OPENCLAW_TOKEN_KEY = "nemoclaw_clawtoken"',
        'export const OPENCLAW_ACCESS_JWT_KEY = "nemoclaw_clawcfjwt"',
        'export const OPENCLAW_ACCESS_PROVIDER_KEY = "nemoclaw_openclaw_access_provider_v1"',
        'export const OPENCLAW_ACCESS_SESSION_KEY = "nemoclaw_openclaw_access_session_v1"',
        "export function getOpenClawConnection()",
        "export function setOpenClawConnection({ rawUrl, token, accessProvider, accessSession, accessJwt } = {})",
    )
    for token in connection_contract:
        if token not in connection:
            findings.append(f"OpenClaw registry contract missing: {token}")
    if "nemoclaw_claw" in openclaw:
        findings.append("OpenClaw widget redeclares a connection storage key outside _connection.js")
    probe_path_contract = (
        "function _fetchUrl(baseUrl, pathAndQuery)",
        "return openclawHttpUrl(baseUrl, pathAndQuery, _proxyConfig())",
        "const route = _fetchUrl(base, actionPath)",
        "if (action.expectJson)",
    )
    for token in probe_path_contract:
        if token not in openclaw:
            findings.append(f"OpenClaw probe path contract missing: {token}")
    if 'openclawHttpUrl(displayUrl, ""' in openclaw:
        findings.append("OpenClaw probe normalizes a combined URL and drops /healthz or /api/agent")

    for rel in PAGES:
        page = text(rel, overrides)
        if 'mountModelEndpointProbe("#probe-llm"' not in page:
            findings.append(f"{rel}: model endpoint is not mounted through its typed probe")
        if 'mountClawProbe("#probe-llm"' in page:
            findings.append(f"{rel}: model endpoint is mounted as OpenClaw")
        if 'mountClawProbe("#probe-claw"' not in page:
            findings.append(f"{rel}: OpenClaw endpoint lost its typed probe")
        for token in ('id="model-route-settings"', 'mountKeyPanel(document.getElementById("model-route-settings")', "await renderModelEndpointProbe()"):
            if token not in page:
                findings.append(f"{rel}: model route source is not visible or refreshable: {token}")
        for token in ("unexpectedHtmlHint:", 'path: "/healthz", method: "GET", expectJson: true', 'path: "/api/agent", method: "GET", expectJson: true'):
            if token not in page:
                findings.append(f"{rel}: OpenClaw API probe lost its JSON/path guard: {token}")

    direct_write = re.compile(
        r"(?:localStorage|sessionStorage)\.(?:setItem|removeItem)\(\s*(['\"])([^'\"]+)\1"
    )
    for path in source_files():
        rel = path.relative_to(ROOT).as_posix()
        body = text(rel, overrides)
        if rel != CONNECTION:
            for key in ("nemoclaw_clawurl", "nemoclaw_clawrawurl", "nemoclaw_clawtoken", "nemoclaw_clawcfjwt"):
                if key in body:
                    findings.append(f"{rel}: bypasses getOpenClawConnection()/setOpenClawConnection() with {key}")
        for match in direct_write.finditer(body):
            key = match.group(2)
            owners = PROTECTED_WRITERS.get(key)
            if owners is not None and rel not in owners:
                findings.append(f"{rel}: writes protected endpoint registration {key}; owner is {', '.join(sorted(owners))}")

    return findings


def self_test() -> list[str]:
    misses: list[str] = []
    if audit():
        return ["baseline endpoint registration audit does not pass"]
    en = (ROOT / PAGES[0]).read_text(encoding="utf-8")
    pt = (ROOT / PAGES[1]).read_text(encoding="utf-8")
    openclaw = (ROOT / OPENCLAW).read_text(encoding="utf-8")
    shared = (ROOT / SHARED).read_text(encoding="utf-8")
    explorer = (ROOT / EXPLORER).read_text(encoding="utf-8")
    browser_integration = (ROOT / BROWSER_INTEGRATION).read_text(encoding="utf-8")
    cases = (
        ("model mounted as OpenClaw", {PAGES[0]: en.replace('mountModelEndpointProbe("#probe-llm"', 'mountClawProbe("#probe-llm"', 1)}, "mounted as OpenClaw"),
        ("conditional registration removed", {OPENCLAW: openclaw.replace("const openClawConnection = isOpenClaw", "const openClawConnection = true", 1)}, "typed endpoint probe"),
        ("probe path folded into launchable", {OPENCLAW: openclaw.replace("openclawHttpUrl(baseUrl, pathAndQuery, _proxyConfig())", 'openclawHttpUrl(displayUrl, "", _proxyConfig())', 1)}, "drops /healthz"),
        ("probe JSON guard removed", {PAGES[0]: en.replace(', expectJson: true', '', 1)}, "JSON/path guard"),
        ("model route panel removed", {PAGES[1]: pt.replace('id="model-route-settings"', 'id="removed-model-route-settings"', 1)}, "model route source"),
        ("page writes launchable registration", {PAGES[0]: en + '\n<script>localStorage.setItem("nemoclaw_clawrawurl", "bad")</script>\n'}, "writes protected endpoint"),
        ("embedding conflated with chat", {SHARED: shared.replace('const EMBEDDING_API_BASE_URL_KEY = "nemoclaw_embedding_api_base_url_v1"', 'const EMBEDDING_API_BASE_URL_KEY = "nemoclaw_model_api_base_url_v1"', 1)}, "registry contract"),
        ("explorer bypasses course model registry", {EXPLORER: explorer.replace("return shared.chat({", "return fetch(self.cfg.proxy, {", 1)}, "SKILL explorer bypasses"),
        ("explorer browser handoff removed", {BROWSER_INTEGRATION: browser_integration.replace("SKILL explorer model registry handoff failed", "browser handoff removed", 1)}, "browser integration audit"),
    )
    for label, overrides, expected in cases:
        if not any(expected in finding for finding in audit(overrides)):
            misses.append(f"detector missed {label}")
    return misses


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    findings = self_test() if args.self_test else audit()
    if findings:
        print("endpoint_registration_audit: FAIL")
        for finding in findings:
            print("  - " + finding)
        return 1
    print("endpoint_registration_audit: OK" + (" (mutation self-test)" if args.self_test else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
