#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit OpenClaw fail-fast, Brev backup, and probe-frame cleanup contracts."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
NODE_RUNNER = ROOT / "scripts" / "runtime" / "run_node.sh"

FILES = {
    "kickstart": ROOT / "web" / "nemoclaw" / "03a-kickstart.html",
    "openclaw_js": ROOT / "web" / "nemoclaw" / "scripts" / "_openclaw.js",
    "connection_js": ROOT / "web" / "nemoclaw" / "scripts" / "_connection.js",
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
    "kickstart": ["Cloudflare Access", "Pomerium", "CF_Authorization", "HttpOnly"],
    "openclaw_js": ["Cloudflare Access", "Pomerium", "X-OpenClaw-Access-Session", "${fallback}${hint}", "openclawGatewayWsUrl", "getOpenClawProxyConfig", "proxyControls", "hideHtmlFrame", ".claw-html-frame[hidden]"],
    "connection_js": ["DEFAULT_OPENCLAW_PROXY_BASE", "OPENCLAW_PROXY_BASE_KEY", "OPENCLAW_PROXY_ENABLED_KEY", "OPENCLAW_ACCESS_PROVIDER_KEY", "OPENCLAW_ACCESS_SESSION_KEY", "openclaw_access_provider", "migrateOpenClawConnectionStorage", "workers\\.dev", "openclawWebSocketUrl"],
    "cors_worker": ["CF_Authorization", "X-Pomerium-Authorization", "X-OpenClaw-Access-Provider", "access_session", "targetSearch.delete", "upstream.webSocket", "Origin", "http://localhost:8088"],
    "runtime_js": ["OPENCLAW_BACKUP_HINT", "OPENCLAW_CORS_PROXY_BASE", "preflightOpenClaw", "resolveOpenClawToken", "OPENCLAW_TOKEN: discovered", "shared.setOpenClawConnection({ rawUrl: u, token: t, accessProvider: provider, accessSession: session })", "RESULT: FAIL (OpenClaw gateway activity missing", "gatewayMissing) ? 1 : 0", "'/health'"],
    "runtime_sh": ["CLAW_ACCESS_PROVIDER", "CLAW_ACCESS_SESSION", "OPENCLAW_CORS_PROXY_BASE"],
    "runtime_skill": ["OpenClaw fallback", "Cloudflare Access", "Pomerium", "CLAW_ACCESS_SESSION", "OPENCLAW_CORS_PROXY_BASE"],
    "scripts_skill": ["validation/SKILL.html"],
    "validation_skill": ["openclaw_fallback_audit.py", "OpenClaw fallback"],
    "worker_ws_audit": ["openclaw worker ws audit", "CF_Authorization", "x-pomerium-authorization", "synthesized a Cookie header", "http://localhost:8088", "upstream WebSocket response directly"],
    "gateway_token_audit": ["gateway token audit", "gatewayTokenFromAgentMetadata", "gatewayTokenFromDashboardUrl", "--self-test"],
    "gw_transport_audit": ["gw connect transport audit", "expected direct signed-in launchable", "cf_access_jwt"],
    "gw_recover_compile_audit": ["gw recover compile audit", "private _uniqueId"],
    "connection_audit": ["openclaw connection audit", "retired relay", "same-origin vendored course", "terminal helper", "04b-modern-clis.html"],
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
            findings.append("GW_CONNECT must call the shared configurable gateway router")
        if "const openclawGatewayWsUrl" in decoded:
            findings.append("GW_CONNECT duplicates the shared gateway router")
        if "_uniqueId(" in decoded:
            findings.append("GW_CONNECT/recover cell code references private module helper _uniqueId; use local nextId")
    if not NODE_RUNNER.is_file():
        findings.append("scripts/runtime/run_node.sh is missing")
    else:
        for script_key in ("worker_ws_audit", "gateway_token_audit", "gw_transport_audit", "gw_recover_compile_audit", "connection_audit"):
            script = FILES[script_key].relative_to(ROOT)
            proc = subprocess.run([str(NODE_RUNNER), str(script)], cwd=ROOT,
                                  text=True, capture_output=True)
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
