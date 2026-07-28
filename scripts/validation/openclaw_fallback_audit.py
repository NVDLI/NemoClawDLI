#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit OpenClaw fail-fast, provider routing, and probe-frame cleanup contracts."""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import add_script_paths, find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
add_script_paths(ROOT / "scripts")
NODE_RUNNER = ROOT / "scripts" / "runtime" / "run_node.sh"

FILES = {
    "kickstart": ROOT / "web" / "nemoclaw" / "03a-kickstart.html",
    "openclaw_js": ROOT / "web" / "nemoclaw" / "scripts" / "_openclaw.js",
    "connection_js": ROOT / "web" / "nemoclaw" / "scripts" / "_connection.js",
    "openshell_js": ROOT / "web" / "nemoclaw" / "scripts" / "_openshell.js",
    "cors_worker": ROOT / "scripts" / "cors-proxy" / "cors-proxy-worker-openclaw.js",
    "runtime_js": ROOT / "scripts" / "runtime" / "test_page_runtime.js",
    "runtime_sh": ROOT / "scripts" / "runtime" / "browser_runtime_test.sh",
    "runtime_skill": ROOT / "scripts" / "runtime" / "SKILL.html",
    "scripts_skill": ROOT / "scripts" / "SKILL.html",
    "validation_skill": ROOT / "scripts" / "validation" / "SKILL.html",
    "worker_ws_audit": ROOT / "scripts" / "validation" / "openclaw_worker_ws_audit.mjs",
    "gateway_token_audit": ROOT / "scripts" / "validation" / "gateway_token_audit.mjs",
    "gw_transport_audit": ROOT / "scripts" / "validation" / "gw_connect_transport_audit.mjs",
    "gw_recover_compile_audit": ROOT / "scripts" / "validation" / "gw_recover_compile_audit.mjs",
    "connection_audit": ROOT / "scripts" / "validation" / "openclaw_connection_audit.mjs",
}

REQUIRED = {
    "kickstart": ["Cloudflare Access", "Pomerium", "HttpOnly", "CF_Authorization", "helpers.openclawBootstrapRequest(PATH"],
    "openclaw_js": ["Cloudflare Access", "Pomerium", "detectOpenClawBrowserSession", "X-OpenClaw-Access-Session", "CF-Access-Jwt-Assertion", "${fallback}${hint}", "openclawGatewayWsUrl", "openclawBootstrapRequest", "getOpenClawProxyConfig", "getOpenClawWsRelayEnabled", "proxyControls", "hideHtmlFrame", ".claw-html-frame[hidden]"],
    "connection_js": ["DEFAULT_OPENCLAW_PROXY_BASE", "OPENCLAW_PROXY_BASE_KEY", "OPENCLAW_PROXY_ENABLED_KEY", "OPENCLAW_WS_RELAY_ENABLED_KEY", "OPENCLAW_ACCESS_PROVIDER_KEY", "OPENCLAW_ACCESS_SESSION_KEY", "openclaw_access_provider", "migrateOpenClawConnectionStorage", "workers\\.dev", "new URL(DEFAULT_OPENCLAW_PROXY_BASE)", "openclawWebSocketUrl"],
    "cors_worker": ["CF_Authorization", "X-Pomerium-Authorization", "X-OpenClaw-Access-Provider", "access_session", "targetSearch.delete", "upstream.webSocket", "Origin", "http://localhost:8088"],
    "runtime_js": ["OPENCLAW_BACKUP_HINT", "OPENCLAW_CORS_PROXY_BASE", "preflightOpenClaw", "resolveOpenClawToken", "OPENCLAW_TOKEN: discovered", "shared.setOpenClawConnection({ rawUrl: u, token: t, accessProvider: provider, accessSession: session })", "RESULT: FAIL (OpenClaw gateway activity missing", "gatewayMissing) ? 1 : 0", "'/health'"],
    "runtime_sh": ["CLAW_ACCESS_PROVIDER", "CLAW_ACCESS_SESSION", "OPENCLAW_CORS_PROXY_BASE"],
    "runtime_skill": ["OpenClaw access", "Cloudflare", "Pomerium", "CLAW_ACCESS_SESSION", "OPENCLAW_CORS_PROXY_BASE"],
    "scripts_skill": ["validation/SKILL.html"],
    "validation_skill": ["openclaw_fallback_audit.py", "OpenClaw fallback"],
    "worker_ws_audit": ["openclaw worker ws audit", "CF_Authorization", "x-pomerium-authorization", "synthesized a Cookie header", "http://localhost:8088", "upstream WebSocket response directly"],
    "gateway_token_audit": ["gateway token audit", "gatewayTokenFromAgentMetadata", "gatewayTokenFromDashboardUrl", "--self-test"],
    # Bind to the transport facts the audit must still assert (relay route, gateway path,
    # direct sender-bound gateway route, not to its failure prose, so rewording a
    # message cannot block the ship while dropping the contract still does.
    "gw_transport_audit": ["gw connect transport audit", "/cli/gateway", "sender-bound Cloudflare route", "direct browser credential boundary"],
    "gw_recover_compile_audit": ["gw recover compile audit", "private _uniqueId"],
    "connection_audit": ["openclaw connection audit", "retired relay", "same-origin co-located launchable", "terminal helper", "04b-modern-clis.html"],
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def probe_frame_findings(openclaw: str) -> list[str]:
    """Return static contract failures for the learner-visible probe iframe lifecycle."""
    findings: list[str] = []
    if not re.search(r"\.claw-html-frame\[hidden\]\s*\{\s*display\s*:\s*none\s*\}", openclaw):
        findings.append("web/nemoclaw/scripts/_openclaw.js lets .claw-html-frame display:block override the hidden lifecycle")
    hide_fn = re.search(r"function hideHtmlFrame\(clear = false\) \{([\s\S]*?)\n  \}", openclaw)
    if not hide_fn or "fr.hidden = true" not in hide_fn.group(1) or 'fr.removeAttribute("srcdoc")' not in hide_fn.group(1):
        findings.append("web/nemoclaw/scripts/_openclaw.js must hide the probe frame and clear srcdoc when requested")
    output_fn = re.search(
        r"function setOutput\(text, kind = \"\"(?:, [^)]*)?\) \{([\s\S]*?)\n  \}\n\n  // Used by runAction",
        openclaw,
    )
    if not output_fn or 'includes("HTML ·")' not in output_fn.group(1) or "hideHtmlFrame(true)" not in output_fn.group(1):
        findings.append("web/nemoclaw/scripts/_openclaw.js must clear the HTML frame before every non-HTML output")
    run_action = re.search(r"async function runAction\(action\) \{([\s\S]*?)\n  \}\n\n  actions\.forEach", openclaw)
    if not run_action:
        findings.append("web/nemoclaw/scripts/_openclaw.js missing probe runAction lifecycle")
    else:
        body = run_action.group(1)
        start = body.find("…in flight")
        clear = body.find("hideHtmlFrame(true)", start)
        fetch = body.find("await fetch", start)
        if min(start, clear, fetch) < 0 or not start < clear < fetch:
            findings.append("web/nemoclaw/scripts/_openclaw.js must clear stale HTML before the next probe request starts")
        access = re.search(r"if \(/cloudflareaccess[\s\S]*?\n\s*return;", body)
        if not access or "hideHtmlFrame(true)" not in access.group(0):
            findings.append("web/nemoclaw/scripts/_openclaw.js must clear stale HTML when Cloudflare Access returns a login page")
    return findings


def probe_frame_contract(openclaw: str) -> list[str]:
    """Mutate each protected edge and prove the static detector rejects it."""
    cases: list[tuple[str, str, str]] = [
        ("hidden CSS", openclaw.replace(".claw-html-frame[hidden]{display:none}", "", 1), "display:block override"),
        ("hidden flag", openclaw.replace("fr.hidden = true", "fr.hidden = false", 1), "must hide the probe frame"),
        ("srcdoc cleanup", openclaw.replace('fr.removeAttribute("srcdoc")', "void fr.srcdoc", 1), "must hide the probe frame"),
        ("non-HTML output", openclaw.replace('if (!String(text || "").includes("HTML ·")) hideHtmlFrame(true);', "", 1), "before every non-HTML output"),
    ]
    request_clear = "// Hide any previous HTML frame while a new request is in flight.\n    hideHtmlFrame(true);"
    cases.append(("request-start cleanup", openclaw.replace(request_clear, "// cleanup removed", 1), "before the next probe request"))
    access_start = openclaw.find("if (/cloudflareaccess")
    access_end = openclaw.find("return;", access_start)
    if access_start >= 0 and access_end >= 0:
        prefix, block, suffix = openclaw[:access_start], openclaw[access_start:access_end], openclaw[access_end:]
        cases.append(("access-warning cleanup", prefix + block.replace("hideHtmlFrame(true);", "", 1) + suffix, "Cloudflare Access"))
    misses = []
    for label, mutated, expected in cases:
        if not any(expected in finding for finding in probe_frame_findings(mutated)):
            misses.append(f"probe-frame detector missed {label}")
    return misses


def worker_provider_findings(worker: str) -> list[str]:
    """Return failures for the provider-specific upstream credential boundary."""
    findings: list[str] = []
    if "_pomerium=" in worker:
        findings.append("OpenClaw relay must use the provider-native Pomerium header, not synthesize a Pomerium cookie")
    if 'fwdHeaders.delete("X-Pomerium-Authorization")' not in worker:
        findings.append("OpenClaw relay must strip caller-supplied Pomerium authorization before provider binding")
    if 'fwdHeaders.set("X-Pomerium-Authorization", accessSession)' not in worker:
        findings.append("OpenClaw relay must bind Pomerium sessions to the upstream-only provider header")
    return findings


def browser_session_findings(openclaw: str, connection: str) -> list[str]:
    """Enforce sender-bound Pomerium auth while retaining live session detection."""
    findings: list[str] = []
    detector = re.search(
        r"export function detectOpenClawBrowserSession\([^)]*\) \{([\s\S]*?)\n\}",
        openclaw,
    )
    if not detector or 'frame?.event === "connect.challenge"' not in detector.group(1):
        findings.append("Pomerium auto-detection must require a live connect.challenge from the exact launchable")
    if "uses the signed-in browser session; nothing to paste" in openclaw:
        findings.append("Pomerium hostname inference must not claim that a browser session was detected")
    if not re.search(
        r'detected\s*\?\s*"signed-in browser session detected; nothing to paste"',
        openclaw,
    ):
        findings.append("Pomerium detected copy must be limited to the verified detected state")
    if '"open the launchable, sign in, then retry"' not in openclaw:
        findings.append("Pomerium detection failure must direct the learner back to launchable sign-in")
    if '"paste the _pomerium cookie value"' in openclaw:
        findings.append("Pomerium recovery must not ask the learner to copy an HttpOnly session")
    if "accessSessionInp.disabled = pomerium;" not in openclaw:
        findings.append("Pomerium access-session input must remain disabled")
    if 'if (pomerium) accessSessionInp.value = "";' not in openclaw:
        findings.append("Pomerium access-session input must clear stale values")
    if 'if (resolvedAccessProvider === "pomerium") nextAccessSession = "";' not in connection:
        findings.append("Pomerium connection storage must reject supplied sessions")
    if not re.search(
        r'if \(accessProviderForOpenClawUrl\(clean\) === "pomerium"\)\s+return false;',
        connection,
    ):
        findings.append("Pomerium HTTP routing must stay direct regardless of stale session state")
    if not re.search(
        r'if \(provider === "pomerium"\) \{\s*'
        r'return openclawWebSocketUrl\([^;]*\{ enabled: false, base: "" \}',
        openclaw,
    ):
        findings.append("Pomerium gateway routing must stay direct")
    if not re.search(
        r'if \(provider === "pomerium"\) \{\s*'
        r'const result = await openclawLoopbackProbe\(actionPath',
        openclaw,
    ):
        findings.append("Pomerium bootstrap reads must use the direct terminal loopback")
    if re.search(r'provider === "pomerium"\s*&&\s*!connection\.accessSession', openclaw):
        findings.append("Pomerium bootstrap must not depend on a stored access session")
    if re.search(r'accessProvider === "pomerium"\s*&&\s*!accessSession', openclaw):
        findings.append("Pomerium probe actions must not fall back to relay when stale session state exists")
    return findings


def browser_session_contract(openclaw: str, connection: str) -> list[str]:
    """Mutate every sender-bound Pomerium edge and prove the detector rejects it."""
    cases = (
        ("challenge proof", openclaw.replace('frame?.event === "connect.challenge"', 'frame?.event === "message"', 1),
         connection, "live connect.challenge"),
        ("hostname-only claim", openclaw.replace("uses the signed-in browser session; nothing to paste",
                                                  "uses the signed-in browser session; nothing to paste", 1) +
         "\n// uses the signed-in browser session; nothing to paste", connection, "hostname inference"),
        ("sign-in recovery", openclaw.replace('"open the launchable, sign in, then retry"',
                                               '"session unavailable"', 1),
         connection, "launchable sign-in"),
        ("cookie-paste regression", openclaw + '\nconst unsafe = "paste the _pomerium cookie value";',
         connection, "must not ask"),
        ("input remains editable", openclaw.replace("accessSessionInp.disabled = pomerium;",
                                                     "accessSessionInp.disabled = detected;", 1),
         connection, "remain disabled"),
        ("stale input retained", openclaw.replace('if (pomerium) accessSessionInp.value = "";',
                                                   "// stale value retained", 1),
         connection, "clear stale"),
        ("stored session accepted", openclaw,
         connection.replace('if (resolvedAccessProvider === "pomerium") nextAccessSession = "";',
                            "// supplied session accepted", 1), "reject supplied"),
        ("HTTP relay selected", openclaw,
         connection.replace('if (accessProviderForOpenClawUrl(clean) === "pomerium") return false;',
                            'if (accessProviderForOpenClawUrl(clean) === "pomerium") return Boolean(accessSession);',
                            1), "HTTP routing"),
        ("gateway relay selected", openclaw.replace('if (provider === "pomerium") {',
                                                     'if (provider === "cloudflare") {', 1),
         connection, "gateway routing"),
        ("bootstrap loopback removed", openclaw.replace('if (provider === "pomerium") {\n    const result = await openclawLoopbackProbe(actionPath',
                                                 'if (provider === "cloudflare") {\n    const result = await openclawLoopbackProbe(actionPath',
                                                 1),
         connection, "bootstrap reads"),
        ("bootstrap session branch", openclaw.replace('if (provider === "pomerium") {\n    const result = await openclawLoopbackProbe(actionPath',
                                                'if (provider === "pomerium" && !connection.accessSession) {\n    const result = await openclawLoopbackProbe(actionPath',
                                                1),
         connection, "must not depend"),
        ("probe session branch", openclaw.replace('isOpenClaw && accessProvider === "pomerium" && method === "GET"',
                                                  'isOpenClaw && accessProvider === "pomerium" && !accessSession && method === "GET"',
                                                  1),
         connection, "must not fall back"),
    )
    misses = []
    for label, mutated_openclaw, mutated_connection, expected in cases:
        if not any(expected in item for item in browser_session_findings(mutated_openclaw, mutated_connection)):
            misses.append(f"browser-session detector missed {label}")
    return misses


def terminal_routing_findings(openshell: str) -> list[str]:
    """Reject any terminal route that can move Pomerium auth onto the relay."""
    findings: list[str] = []
    if not re.search(
        r'const relayEnabled = resolvedProvider === "cloudflare"\s*&&',
        openshell,
    ):
        findings.append("Pomerium terminal routing must stay direct")
    if re.search(r'resolvedProvider === "pomerium"[\s\S]{0,100}accessSession', openshell):
        findings.append("Pomerium terminal routing must not branch on stored session state")
    return findings


def terminal_routing_contract(openshell: str) -> list[str]:
    """Prove a provider-guard regression is rejected."""
    cases = (
        (
            "provider guard",
            openshell.replace(
                'const relayEnabled = resolvedProvider === "cloudflare" &&',
                "const relayEnabled =",
                1,
            ),
            "must stay direct",
        ),
        (
            "session-selected relay",
            openshell.replace(
                "const relayEnabled = resolvedProvider === \"cloudflare\" &&",
                'const relayEnabled = resolvedProvider === "pomerium" && accessSession &&',
                1,
            ),
            "must stay direct",
        ),
    )
    misses = []
    for label, mutated, expected in cases:
        if not any(expected in item for item in terminal_routing_findings(mutated)):
            misses.append(f"terminal-routing detector missed {label}")
    return misses


def audit() -> list[str]:
    findings: list[str] = []
    for key, tokens in REQUIRED.items():
        path = FILES[key]
        if not path.is_file():
            findings.append(f"missing {path.relative_to(ROOT)}")
            continue
        raw = read(path)
        for token in tokens:
            if token not in raw:
                findings.append(f"{path.relative_to(ROOT)} missing {token}")

    openclaw = read(FILES["openclaw_js"])
    connection = read(FILES["connection_js"])
    openshell = read(FILES["openshell_js"])
    kickstart = read(FILES["kickstart"])
    if "try { await runAction(action); }\n      try { await runAction(action); }" in openclaw:
        findings.append("web/nemoclaw/scripts/_openclaw.js runs each probe action twice")
    if "?cf_access_jwt=" in openclaw and "?cf_access_jwt=..." not in openclaw:
        findings.append("web/nemoclaw/scripts/_openclaw.js may log the raw CF Access JWT in gateway output")
    if "__nemoclaw_proxy_meta" in openclaw:
        findings.append("GW_CONNECT depends on the retired worker metadata route instead of the hosted relay contract")
    if "setOutput(head + `   (HTML" in openclaw and "hideHtmlFrame(true);" not in openclaw:
        findings.append("web/nemoclaw/scripts/_openclaw.js does not clear stale HTML iframe before non-HTML output")
    findings.extend(probe_frame_findings(openclaw))
    findings.extend(probe_frame_contract(openclaw))
    findings.extend(browser_session_findings(openclaw, connection))
    findings.extend(browser_session_contract(openclaw, connection))
    findings.extend(terminal_routing_findings(openshell))
    findings.extend(terminal_routing_contract(openshell))
    if re.search(r"(?:paste|copy)[^<\n]{0,80}<code>_pomerium</code>", kickstart, re.I):
        findings.append("web/nemoclaw/03a-kickstart.html must not ask learners to copy a Pomerium session")

    findings.extend(worker_provider_findings(read(FILES["cors_worker"])))

    m = re.search(r"export const GW_CONNECT = `([\s\S]*?)`;", openclaw)
    if not m:
        findings.append("web/nemoclaw/scripts/_openclaw.js missing GW_CONNECT template")
    else:
        # This is not a full JS parser. It catches the exact class of regression where
        # regex slash escapes inside the template literal decode into invalid cell code
        # such as replace(//+$/, ""), which module-level node --check cannot see.
        decoded = m.group(1).replace(r"\/", "/")
        if "replace(//" in decoded:
            findings.append("GW_CONNECT template decodes to invalid regex/comment syntax; avoid slash regex literals inside stringified cells")
        if "helpers.openclawGatewayWsUrl(rawUrl, accessSession, null, null, accessProvider)" not in decoded:
            findings.append("GW_CONNECT must call the shared provider-aware gateway router")
        if "const openclawGatewayWsUrl" in decoded:
            findings.append("GW_CONNECT duplicates the shared gateway router")
        if "_uniqueId(" in decoded:
            findings.append("GW_CONNECT/recover cell code references private module helper _uniqueId; use local nextId")
    if not NODE_RUNNER.is_file():
        findings.append("scripts/runtime/run_node.sh is missing")
    else:
        # A Node audit cannot render a key-based locale resource, so hand it the published bytes.
        with tempfile.TemporaryDirectory(prefix="locale-pages-") as staged:
            environment = dict(os.environ)
            try:
                from translate.locale_pages import materialize

                environment["NEMOCLAW_LOCALE_PAGES"] = str(materialize(ROOT, Path(staged)))
            except Exception as error:  # noqa: BLE001 - reported, not raised, like every finding
                findings.append(f"locale page rendering failed: {error}")
            for script_key in ("worker_ws_audit", "gateway_token_audit", "gw_transport_audit", "gw_recover_compile_audit", "connection_audit"):
                script = FILES[script_key].relative_to(ROOT)
                proc = subprocess.run([str(NODE_RUNNER), str(script)], cwd=ROOT,
                                      text=True, capture_output=True, env=environment)
                if proc.returncode != 0:
                    detail = (proc.stdout + proc.stderr).strip().replace("\n", " | ")
                    findings.append(f"{FILES[script_key].name} failed: {detail}")
    return findings


def main() -> int:
    findings = audit()
    if findings:
        for item in findings:
            print(item)
        return 1
    print("openclaw fallback audit: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
