#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Keep model, embedding, and OpenClaw endpoint registrations distinct."""
from __future__ import annotations

import argparse
import functools
import re
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from translate.locale_catalog import discover_locales
from translate.locale_pages import course_pages

ROOT = Path(__file__).resolve().parents[2]
SHARED = "web/nemoclaw/scripts/_shared.js"
OPENCLAW = "web/nemoclaw/scripts/_openclaw.js"
CONNECTION = "web/nemoclaw/scripts/_connection.js"
KEYPANEL = "web/nemoclaw/scripts/_keypanel.js"
RUNTIME_HARNESS = "scripts/runtime/test_page_runtime.js"
EXPLORER = "web/_skill_explorer.js"
BROWSER_INTEGRATION = "scripts/validation/runtime_integration_browser_audit.py"

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
    "nemoclaw_openclaw_ws_relay_enabled_v1": {CONNECTION},
}

RETIRED_PRESENTER_QUERY_KEYS = (
    "base_url",
    "model_base_url",
    "model",
    "embedding_base_url",
    "embedding_model",
    "openclaw_url",
    "openclaw_access_provider",
    "openclaw_proxy_base",
    "openclaw_proxy",
)

ENDPOINT_PAGE = "web/nemoclaw/03a-kickstart.html"
UNOWNED_PARTS = {"vendor", "mats", "assets", "standalone"}


@functools.lru_cache(maxsize=1)
def published_locale_pages() -> dict[str, str]:
    """Return the localized course pages the build publishes, keyed by repository-relative path.

    A locale page ships either from a reviewed HTML overlay or from a key-based resource, so the
    locale tree alone no longer holds every page. Resolving publication the way the assembler does
    keeps a migrated page under the same registration contract as one that still has an HTML file.
    """
    return course_pages(ROOT, "nemoclaw")


def source_files() -> list[str]:
    """Return the repository-relative sources whose endpoint registrations this audit owns."""
    files = {RUNTIME_HARNESS, EXPLORER}
    bases = [ROOT / "web/nemoclaw", *(spec.course_root for spec in discover_locales(ROOT))]
    for base in bases:
        for path in base.rglob("*"):
            if path.suffix in {".js", ".mjs", ".html"}:
                files.add(path.relative_to(ROOT).as_posix())
    files.update(published_locale_pages())
    return sorted(rel for rel in files if not UNOWNED_PARTS.intersection(Path(rel).parts))


def endpoint_pages() -> list[str]:
    return [
        ENDPOINT_PAGE,
        *(f"i18n/{spec.url_code}/{ENDPOINT_PAGE}" for spec in discover_locales(ROOT)),
    ]


def text(rel: str, overrides: dict[str, str]) -> str:
    if rel in overrides:
        return overrides[rel]
    published = published_locale_pages()
    if rel in published:
        return published[rel]
    return (ROOT / rel).read_text(encoding="utf-8")


def audit(overrides: dict[str, str] | None = None) -> list[str]:
    overrides = overrides or {}
    findings: list[str] = []
    shared = text(SHARED, overrides)
    openclaw = text(OPENCLAW, overrides)
    connection = text(CONNECTION, overrides)
    runtime = text(RUNTIME_HARNESS, overrides)
    explorer = text(EXPLORER, overrides)
    browser_integration = text(BROWSER_INTEGRATION, overrides)

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

    for key in RETIRED_PRESENTER_QUERY_KEYS:
        getter = re.compile(rf"\.get\(\s*(['\"]){re.escape(key)}\1\s*\)")
        if getter.search(shared):
            findings.append(f"model registry still accepts retired presenter query parameter: {key}")
        if getter.search(connection):
            findings.append(f"OpenClaw registry still accepts retired presenter query parameter: {key}")
        for rel in endpoint_pages():
            if re.search(rf"[?&]\s*{re.escape(key)}\s*=", text(rel, overrides), re.I):
                findings.append(f"{rel}: advertises retired presenter query parameter: {key}")

    if 'sessionStorage.setItem("__nv_slim_cfg_v1"' in runtime:
        findings.append("runtime harness bypasses the model registry with a private config cache write")
    if "shared.setOpenClawConnection({ rawUrl: u, token: t, accessProvider: provider, accessSession: session })" not in runtime:
        findings.append("runtime harness bypasses the OpenClaw connection registry")
    if "courseRuntime().then(function (shared)" not in explorer or "return shared.chat({" not in explorer:
        findings.append("SKILL explorer bypasses the canonical course model registry")
    if "nemoclaw_claw" in explorer or "App.prototype.proxy" in explorer:
        findings.append("SKILL explorer redeclares endpoint or OpenClaw state")
    if "SKILL explorer model registry handoff failed" not in browser_integration:
        findings.append("browser integration audit does not execute the SKILL explorer model handoff")
    browser_connection_contract = (
        "#probe-claw .claw-connection-audit",
        "results.probe.editableFields !== 2",
        "results.probe.advancedFields !== 0",
        "['/api/agent', '/cli/gateway', '/ws/terminal', '/healthz']",
        "connectionPattern",
    )
    for token in browser_connection_contract:
        if token not in browser_integration:
            findings.append(f"browser connection audit is stale or incomplete: {token}")
    if "#probe-claw .claw-help-hint" in browser_integration:
        findings.append("browser connection audit still waits for the retired multi-field help UI")

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
        "OpenClaw launchables use the approved NVIDIA DLI relay",
        "new URL(DEFAULT_OPENCLAW_PROXY_BASE)",
    )
    for token in connection_contract:
        if token not in connection:
            findings.append(f"OpenClaw registry contract missing: {token}")
    if "nemoclaw_claw" in openclaw:
        findings.append("OpenClaw widget redeclares a connection storage key outside _connection.js")
    probe_path_contract = (
        'function _fetchUrl(baseUrl, pathAndQuery, accessProvider = "auto", accessSession = "")',
        "pathAndQuery,\n      _proxyConfig(),\n      accessProvider,\n      accessSession,",
        "const route = _fetchUrl(base, actionPath, accessProvider, accessSession)",
        "if (action.expectJson)",
    )
    for token in probe_path_contract:
        if token not in openclaw:
            findings.append(f"OpenClaw probe path contract missing: {token}")
    if 'openclawHttpUrl(displayUrl, ""' in openclaw:
        findings.append("OpenClaw probe normalizes a combined URL and drops /healthz or /api/agent")
    audit_steps = (
        'id: "agent-metadata"',
        'id: "gateway-websocket"',
        'id: "terminal-websocket"',
        'id: "health"',
    )
    positions = [openclaw.find(token) for token in audit_steps]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        findings.append("OpenClaw connection audit must run metadata, gateway, terminal, and health in order")
    for token in (
        'const response = await openclawBootstrapRequest("/api/agent"',
        "gatewayTokenFromAgentMetadata(response.json)",
        "probeOpenClawGatewayConnection({ signal, relayWebSocket: false })",
        "const response = await terminal(terminalCommand",
        'openclawBootstrapRequest("/healthz"',
        "response.json ?? response.body",
        "redactOpenClawDiagnostic",
        'if (provider === "pomerium")',
        'transport: viaLoopback ? "launchable terminal loopback (direct first, hosted relay fallback)"',
        '[text("What"), step.what || ""]',
        '[text("Credential"), request.authSummary || ""]',
        'what: "Returns launchable agent metadata',
        'what: "Carries authenticated OpenClaw JSON-RPC',
        'what: "Opens an operator PTY',
        'what: "Reports whether the launchable HTTP service is alive',
        "authSummary: accessCredentialDelivery(",
    ):
        if token not in openclaw:
            findings.append(f"OpenClaw connection audit lost required route or redaction: {token}")

    for rel in endpoint_pages():
        if rel not in overrides and rel not in published_locale_pages() and not (ROOT / rel).is_file():
            findings.append(f"{rel}: no endpoint registration page is published for this locale")
            continue
        page = text(rel, overrides)
        if 'mountModelEndpointProbe("#probe-llm"' not in page:
            findings.append(f"{rel}: model endpoint is not mounted through its typed probe")
        if 'mountClawProbe("#probe-llm"' in page:
            findings.append(f"{rel}: model endpoint is mounted as OpenClaw")
        if 'mountOpenClawConnectionAudit("#probe-claw"' not in page:
            findings.append(f"{rel}: OpenClaw endpoint lost its typed probe")
        if 'mountClawProbe("#probe-claw"' in page:
            findings.append(f"{rel}: legacy multi-field OpenClaw probe returned")
        for token in ('id="model-route-settings"', 'mountKeyPanel(document.getElementById("model-route-settings")', "await renderModelEndpointProbe()"):
            if token not in page:
                findings.append(f"{rel}: model route source is not visible or refreshable: {token}")
        audit_start = page.find('mountOpenClawConnectionAudit("#probe-claw"')
        audit_end = page.find("\n    });", audit_start)
        audit_mount = page[audit_start:audit_end + len("\n    });")] if audit_start >= 0 and audit_end >= 0 else ""
        for token in ("wsRelayControls:", "defaultToken:", "accessProvider:", "fieldHelp:"):
            if token in audit_mount:
                findings.append(f"{rel}: legacy learner-facing OpenClaw control returned: {token}")

    direct_write = re.compile(
        r"(?:localStorage|sessionStorage)\.(?:setItem|removeItem)\(\s*(['\"])([^'\"]+)\1"
    )
    for rel in source_files():
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
    pages = endpoint_pages()
    en = text(pages[0], {})
    localized = text(pages[1], {})
    openclaw = (ROOT / OPENCLAW).read_text(encoding="utf-8")
    connection = (ROOT / CONNECTION).read_text(encoding="utf-8")
    shared = (ROOT / SHARED).read_text(encoding="utf-8")
    explorer = (ROOT / EXPLORER).read_text(encoding="utf-8")
    browser_integration = (ROOT / BROWSER_INTEGRATION).read_text(encoding="utf-8")
    cases = (
        ("model mounted as OpenClaw", {pages[0]: en.replace('mountModelEndpointProbe("#probe-llm"', 'mountClawProbe("#probe-llm"', 1)}, "mounted as OpenClaw"),
        ("OpenClaw audit replaced by legacy probe", {pages[0]: en.replace('mountOpenClawConnectionAudit("#probe-claw"', 'mountClawProbe("#probe-claw"', 1)}, "legacy multi-field"),
        ("conditional registration removed", {OPENCLAW: openclaw.replace("const openClawConnection = isOpenClaw", "const openClawConnection = true", 1)}, "typed endpoint probe"),
        ("probe path folded into launchable", {OPENCLAW: openclaw.replace("baseUrl,\n      pathAndQuery,", 'displayUrl,\n      "",', 1)}, "probe path contract"),
        ("probe provider dropped", {OPENCLAW: openclaw.replace("accessProvider,\n      accessSession,", '"auto",\n      accessSession,', 1)}, "probe path contract"),
        ("probe session dropped", {OPENCLAW: openclaw.replace("accessProvider,\n      accessSession,", 'accessProvider,\n      "",', 1)}, "probe path contract"),
        ("connection metadata route removed", {OPENCLAW: openclaw.replace('const response = await openclawBootstrapRequest("/api/agent"', 'const response = await openclawBootstrapRequest("/api/agents-broken"', 1)}, "required route or redaction"),
        ("connection route order changed", {OPENCLAW: openclaw.replace('id: "agent-metadata"', 'id: "terminal-websocket"', 1)}, "must run metadata"),
        ("connection endpoint explanation removed", {OPENCLAW: openclaw.replace('[text("What"), step.what || ""]', '[text("Endpoint"), step.title || ""]', 1)}, "required route or redaction"),
        ("connection credential explanation redacted away", {OPENCLAW: openclaw.replace('[text("Credential"), request.authSummary || ""]', '[text("Credential"), request.gatewayToken || ""]', 1)}, "required route or redaction"),
        ("Pomerium manual-session loopback removed", {OPENCLAW: openclaw.replace('if (provider === "pomerium")', 'if (provider === "pomerium" && !connection.accessSession)', 1)}, "required route or redaction"),
        ("gateway silently selects the relay", {OPENCLAW: openclaw.replace("probeOpenClawGatewayConnection({ signal, relayWebSocket: false })", "probeOpenClawGatewayConnection({ signal, relayWebSocket: true })", 1)}, "required route or redaction"),
        ("model route panel removed", {pages[1]: localized.replace('id="model-route-settings"', 'id="removed-model-route-settings"', 1)}, "model route source"),
        ("page writes launchable registration", {pages[0]: en + '\n<script>localStorage.setItem("nemoclaw_clawrawurl", "bad")</script>\n'}, "writes protected endpoint"),
        ("page writes WebSocket relay preference", {pages[0]: en + '\n<script>localStorage.setItem("nemoclaw_openclaw_ws_relay_enabled_v1", "1")</script>\n'}, "writes protected endpoint"),
        ("embedding conflated with chat", {SHARED: shared.replace('const EMBEDDING_API_BASE_URL_KEY = "nemoclaw_embedding_api_base_url_v1"', 'const EMBEDDING_API_BASE_URL_KEY = "nemoclaw_model_api_base_url_v1"', 1)}, "registry contract"),
        ("explorer bypasses course model registry", {EXPLORER: explorer.replace("return shared.chat({", "return fetch(self.cfg.proxy, {", 1)}, "SKILL explorer bypasses"),
        ("explorer browser handoff removed", {BROWSER_INTEGRATION: browser_integration.replace("SKILL explorer model registry handoff failed", "browser handoff removed", 1)}, "browser integration audit"),
        ("browser audit restores retired probe selector", {BROWSER_INTEGRATION: browser_integration.replace("#probe-claw .claw-connection-audit", "#probe-claw .claw-help-hint", 1)}, "browser connection audit"),
        ("browser audit stops enforcing two fields", {BROWSER_INTEGRATION: browser_integration.replace("results.probe.editableFields !== 2", "results.probe.editableFields !== 5", 1)}, "browser connection audit"),
        ("retired model query restored", {SHARED: shared.replace("export function getModelApiBaseUrl()", 'const legacyModel = new URLSearchParams(location.search).get("base_url");\n\nexport function getModelApiBaseUrl()', 1)}, "retired presenter query parameter"),
        ("retired OpenClaw query restored", {CONNECTION: connection.replace("export function getOpenClawProxyConfig()", 'const legacyLaunchable = new URLSearchParams(location.search).get("openclaw_url");\n\nexport function getOpenClawProxyConfig()', 1)}, "retired presenter query parameter"),
        ("learner advertises retired model query", {pages[0]: en + "\n<p>?model=provider/model</p>\n"}, "advertises retired presenter query parameter"),
        ("learner advertises retired relay query", {pages[0]: en + "\n<p>?openclaw_proxy_base=https://relay.example</p>\n"}, "advertises retired presenter query parameter"),
        ("arbitrary OpenClaw relay restored", {CONNECTION: connection.replace("new URL(DEFAULT_OPENCLAW_PROXY_BASE)", "new URL(config.base)", 1)}, "registry contract"),
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
