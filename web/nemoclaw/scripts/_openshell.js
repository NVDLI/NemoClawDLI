// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// OpenShell teaching surface for 04a (policy lab) and 04b (modern CLIs).
// Holds the launchable PTY terminal, the sandbox-policy.rego port, the exec bridge, and the policy map.
// Browser globals only; _shared.js re-exports these so a page can import from either module.

import {
  accessProviderForOpenClawUrl, getOpenClawConnection, getOpenClawProxyConfig,
  getOpenClawWsRelayEnabled, openclawWebSocketUrl,
} from "./_connection.js";
import { filterOpenClawRuntimeNoise } from "./_runtime_text.js";

const POLICY_YAML_MODULE_URL = "../vendor/js-yaml-5.2.2.esm.min.js";
const POMERIUM_LOOPBACK_PROBES = Object.freeze({
  "/healthz": "http://127.0.0.1/healthz",
  "/api/agent": "http://127.0.0.1/api/agent",
});

// PTY helper: `bash` opens the host; `openshell sandbox connect <agent>` enters the agent.
// A detected browser session uses the direct PTY. A manually supplied access
// session uses the approved relay; Cloudflare also retains an explicit recovery toggle.
export async function terminal(cmd, { send = [], idleMs = 5000, totalMs = 25000, openMs = 12000, onChunk = null, baseUrl = null, signal = null, relayWebSocket = null } = {}) {
  /* @doc <code>helpers.terminal(cmd, {send, idleMs, totalMs, openMs, onChunk})</code> ::
       Open a PTY over your launchable's <code>/ws/terminal</code> WebSocket and run
       <code>cmd</code>. Use <code>"bash"</code> for the VM shell, or <code>"openshell sandbox
       connect &lt;agent&gt;"</code> to drop inside the kernel-sandboxed agent.
       <code>send</code> is an array of shell lines typed into the PTY in order (each gets
       Enter). A detected browser session stays direct. A manually supplied access session
       uses the approved relay; <code>relayWebSocket: true</code> explicitly selects that
       recovery route too.
       Returns <code>{ output, raw, frames, exitCode }</code> (<code>output</code>
       is ANSI-stripped; <code>exitCode</code> is the command's PTY exit status, or null if none
       arrived). Reads the launchable URL from the OpenClaw probe. Launchable only.
  */
  const connection = getOpenClawConnection();
  const rawUrl = (baseUrl || connection.rawUrl).replace(/\/+$/, "");
  if (!rawUrl) throw new Error("No launchable URL set. Connect on the Kickstart page (Module 3a) first, or pass { baseUrl }.");
  const accessProvider = connection.accessProvider;
  const accessSession = connection.accessSession;
  const resolvedProvider = accessProviderForOpenClawUrl(rawUrl, accessProvider);
  const relayEnabled = relayWebSocket === true ||
    (relayWebSocket === null && (getOpenClawWsRelayEnabled() ||
      (resolvedProvider === "pomerium" && Boolean(accessSession))));
  const routed = openclawWebSocketUrl(
    rawUrl,
    "/ws/terminal?cmd=" + encodeURIComponent(cmd),
    relayEnabled ? accessSession : "",
    relayEnabled ? getOpenClawProxyConfig() : { enabled: false, base: "" },
    accessProvider,
  );
  const wsUrls = [routed.url];
  let launchableOrigin = rawUrl;
  try { launchableOrigin = new URL(rawUrl).origin; } catch (_) {}
  // Drop xterm control sequences so the returned text reads like a transcript.
  const strip = s => String(s)
    .replace(/\x1b\[[0-9;?]*[A-Za-z]/g, "").replace(/\x1b\][^\x07]*\x07/g, "")
    .replace(/\x1b[()][AB0]/g, "").replace(/[\r\x07]/g, "");
  const clean = s => filterOpenClawRuntimeNoise(strip(s));
  const terminalOpenError = () => {
    const accessHint = routed.viaProxy
      ? (accessSession
          ? "The hosted relay failed. Open the launchable, then paste a fresh matching access session in Module 3a."
          : "The hosted relay has no matching access session. Open the launchable, then paste a fresh provider credential in Module 3a.")
      : "Reopen the launchable and verify that its terminal route is running.";
    const error = new Error(
      `Terminal did not open for ${launchableOrigin}. ` + accessHint
    );
    error.name = "TerminalConnectionError";
    error.code = "TERMINAL_OPEN_TIMEOUT";
    return error;
  };
  return await new Promise((resolve, reject) => {
    let raw = "", frames = 0, opened = false, idleT = null, exitCode = null;
    let ws = null, candidate = 0, openT = null;
    let finished = false, abortHandler = null;
    const totalT = setTimeout(() => opened ? finish() : fail(terminalOpenError()), totalMs);
    function settle() {
      if (finished) return false;
      finished = true;
      clearTimeout(idleT); clearTimeout(totalT); clearTimeout(openT);
      if (signal && abortHandler) signal.removeEventListener("abort", abortHandler);
      try { ws.close(); } catch (_) {}
      return true;
    }
    function finish() {
      if (!settle()) return;
      resolve({ output: clean(raw), raw: filterOpenClawRuntimeNoise(raw), frames, exitCode });
    }
    function fail(error) {
      if (!settle()) return;
      reject(error);
    }
    const bump = () => { if (!finished) { clearTimeout(idleT); idleT = setTimeout(finish, idleMs); } };

    function openNext() {
      if (finished) return;
      clearTimeout(openT);
      if (candidate >= wsUrls.length) return fail(terminalOpenError());
      const routeIndex = candidate++;
      let socket;
      try { socket = new WebSocket(wsUrls[routeIndex]); }
      catch (_) { return openNext(); }
      ws = socket;
      const budget = openMs;
      openT = setTimeout(() => {
        if (finished || opened || socket !== ws) return;
        try { socket.close(); } catch (_) {}
        ws = null;
        openNext();
      }, budget);
      socket.onopen = () => {
        if (finished || socket !== ws) return;
        opened = true; clearTimeout(openT); bump();
        let i = 0;
        (function pump() {
          if (finished || i >= send.length) return;
          setTimeout(() => { if (finished) return; try { socket.send(send[i] + "\n"); } catch (_) {} i++; pump(); }, 1500);
        })();
      };
      socket.onmessage = ev => {
        if (finished || socket !== ws) return;
        frames++;
        let t = "";
        try {
          const j = JSON.parse(ev.data);
          if (j.type === "exit" && typeof j.code === "number") exitCode = j.code;
          t = (j.data != null ? j.data : "");
        } catch (_) { t = String(ev.data || ""); }
        raw += t; if (onChunk) { const chunk = clean(t); if (chunk) try { onChunk(chunk); } catch (_) {} }
        bump();
      };
      socket.onerror = () => {};
      socket.onclose = () => {
        if (finished || socket !== ws) return;
        if (opened) finish();
        else { ws = null; openNext(); }
      };
    }

    // External cancellation (the cell's Stop button) closes the socket and resolves with whatever arrived so far.
    if (signal) {
      if (signal.aborted) return finish();
      abortHandler = () => finish();
      signal.addEventListener("abort", abortHandler, { once: true });
    }
    openNext();
  });
}

// Pomerium keeps its HttpOnly session between the browser and launchable.
// The direct terminal reads two loopback bootstrap endpoints without exposing the cookie.
// A fixed map selects the command; no learner-controlled shell fragment is interpolated.
export async function openclawLoopbackProbe(path, { baseUrl = null, signal = null } = {}) {
  const connection = getOpenClawConnection();
  const rawUrl = (baseUrl || connection.rawUrl || "").replace(/\/+$/, "");
  if (!rawUrl) throw new Error("No launchable URL set. Connect on Module 3a first.");
  if (accessProviderForOpenClawUrl(rawUrl, connection.accessProvider) !== "pomerium") {
    throw new Error("The loopback bootstrap is only for Pomerium launchables.");
  }
  const endpoint = POMERIUM_LOOPBACK_PROBES[String(path || "")];
  if (!endpoint) throw new Error("Unsupported loopback bootstrap path.");
  const command = "curl -fsS --max-time 10 " + endpoint;
  const result = await terminal(command, {
    baseUrl: rawUrl,
    idleMs: 1500,
    totalMs: 18000,
    openMs: 10000,
    signal,
  });
  if (result.exitCode !== 0) {
    throw new Error(`Launchable loopback probe failed with exit code ${result.exitCode ?? "unknown"}.`);
  }
  const body = String(result.output || "").trim();
  if (!body) throw new Error("Launchable loopback probe returned an empty response.");
  let json = null;
  try { json = JSON.parse(body); } catch (_) { /* health responses may be plain text */ }
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    body,
    json,
    frames: result.frames,
    transport: "direct-terminal-loopback",
  };
}

// ── OpenShell policy engine (JS port of sandbox-policy.rego) ─────────────────
// Computes a static allow/deny verdict (with the kernel proxy's deny-reason) for any candidate network or filesystem action, so a page can predict offline then confirm against the LIVE sandbox via `sandboxExec`.
// Verdicts matched the live launchable on 2026-06-17, including binary-identity and L7 method/path denials.

// glob.match(pattern, [delim], str): "*" spans one segment, "**" spans across.
function _globMatch(pattern, delim, str) {
  let re = "^";
  for (let i = 0; i < pattern.length; i++) {
    const c = pattern[i];
    if (c === "*") {
      if (pattern[i + 1] === "*") { re += ".*"; i++; }
      else re += "[^" + (delim === "." ? "." : "/") + "]*";
    } else if ("\\^$.|?+()[]{}".includes(c)) re += "\\" + c;
    else re += c;
  }
  return new RegExp(re + "$").test(str);
}
const _epPorts = ep => Array.isArray(ep.ports) ? ep.ports : (ep.port != null ? [ep.port] : []);
function _endpointAllowed(policy, net) {
  return (policy.endpoints || []).some(ep => {
    if (ep.host && !ep.host.includes("*")) return ep.host.toLowerCase() === String(net.host).toLowerCase() && _epPorts(ep).includes(net.port);
    if (ep.host && ep.host.includes("*")) return _globMatch(ep.host.toLowerCase(), ".", String(net.host).toLowerCase()) && _epPorts(ep).includes(net.port);
    if ((!ep.host || ep.host === "") && (ep.allowed_ips || []).length > 0) return _epPorts(ep).includes(net.port);
    return false;
  });
}
// Binary identity matches the exact exe path, any ancestor (claude spawns node), or a glob over exe and ancestors.
// argv[0]/cmdline are NOT trusted (spoofable).
function _binaryAllowed(policy, exec) {
  const all = [exec.path, ...(exec.ancestors || [])];
  return (policy.binaries || []).some(b =>
    b.path.includes("*") ? all.some(p => _globMatch(b.path, "/", p))
                         : (b.path === exec.path || (exec.ancestors || []).includes(b.path)));
}
function _l7Allowed(ep, req) {
  if (!ep.rules) return true;                       // no L7 rules -> the L4 match suffices
  return ep.rules.some(rule => {
    const a = rule.allow; if (!a || !a.method) return false;
    const mOk = a.method === "*" || a.method.toLowerCase() === String(req.method).toLowerCase();
    const pOk = a.path === "**" || _globMatch(a.path, "/", req.path);
    return mOk && pOk;
  });
}
function _matchedEndpoint(policy, net) {
  return (policy.endpoints || []).find(ep =>
    (ep.host && !ep.host.includes("*") && ep.host.toLowerCase() === String(net.host).toLowerCase() && _epPorts(ep).includes(net.port)) ||
    (ep.host && ep.host.includes("*") && _globMatch(ep.host.toLowerCase(), ".", String(net.host).toLowerCase()) && _epPorts(ep).includes(net.port)) ||
    ((!ep.host || ep.host === "") && (ep.allowed_ips || []).length > 0 && _epPorts(ep).includes(net.port)));
}

// Network decision for a candidate { binary, host, port, method?, path? }.
// Returns { action:"allow"|"deny", matched?, reason? }, denying by default.
// The reason carries the Rego's endpoint-miss / binary-miss / L7-miss diagnostics.
export function evalSandboxNetwork(candidate, policy = OPENSHELL_POLICY_HARDENED) {
  /* @doc <code>helpers.evalSandboxNetwork({binary,host,port,method,path}, policy?)</code> ::
       Static port of the OpenShell network Rego. Returns <code>{action, matched, reason}</code>
       (deny-by-default; binary-identity + L7 method/path enforced) for a candidate connection,
       without touching the network. Defaults to the live launchable's hardened policy. Pair
       with <code>helpers.sandboxExec</code> to confirm the prediction live.
  */
  const policies = policy.network_policies || {};
  const net = { host: candidate.host, port: candidate.port };
  const exec = { path: candidate.binary, ancestors: candidate.ancestors || [] };
  const req = (candidate.method || candidate.path) ? { method: candidate.method || "GET", path: candidate.path || "/" } : null;
  const matches = [], epMiss = [], binMiss = [];
  for (const [name, p] of Object.entries(policies)) {
    const epOk = _endpointAllowed(p, net), binOk = _binaryAllowed(p, exec);
    if (epOk && binOk) matches.push(name);
    else if (!epOk) epMiss.push(`endpoint ${net.host}:${net.port} not in policy '${name}'`);
    else binMiss.push(`binary '${exec.path}' not allowed in policy '${name}'`);
  }
  if (matches.length === 0) return { action: "deny", reason: [...epMiss, ...binMiss].join("; ") || "no network policy matches (deny by default)" };
  if (req) {
    const name = matches.sort()[0];
    const ep = _matchedEndpoint(policies[name], net);
    if (ep && !_l7Allowed(ep, req)) return { action: "deny", matched: name, reason: `${req.method} ${req.path} not permitted by policy '${name}'` };
  }
  return { action: "allow", matched: matches.sort()[0] };
}

// Filesystem decision for { path, mode:"read"|"write" }, longest matching prefix wins.
// read_write allows; read_only allows read and denies write; anything else denies.
// include_workdir treats the /sandbox workdir as writable.
export function evalSandboxFs(path, mode = "write", policy = OPENSHELL_POLICY_HARDENED) {
  /* @doc <code>helpers.evalSandboxFs(path, mode, policy?)</code> ::
       Static port of the OpenShell filesystem (Landlock) policy. Returns
       <code>"allow"</code>/<code>"deny"</code> for reading or writing <code>path</code>.
       Defaults to the live launchable's hardened policy.
  */
  const fp = policy.filesystem_policy || policy;
  const under = (p, base) => p === base || p.startsWith(base.replace(/\/$/, "") + "/");
  const rw = (fp.read_write || []).filter(b => under(path, b)).sort((a, b) => b.length - a.length)[0];
  const ro = (fp.read_only || []).filter(b => under(path, b)).sort((a, b) => b.length - a.length)[0];
  const best = [rw, ro].filter(Boolean).sort((a, b) => b.length - a.length)[0];
  if (best === undefined) return (fp.include_workdir && under(path, "/sandbox")) ? "allow" : "deny";
  return best === rw ? "allow" : (mode === "read" ? "allow" : "deny");
}

// Offline default for the static evaluator: a "shields up" policy read off the live launchable on 2026-06-17.
// The live sandbox stays the source of truth.
// The schema has no tool_policy or per-file read-only, so SOUL.md is guarded by DAC + chattr, not here.
export const OPENSHELL_POLICY_HARDENED = {
  filesystem_policy: {
    include_workdir: true,
    read_only: ["/usr", "/lib", "/proc", "/dev/urandom", "/app", "/etc", "/var/log"],
    read_write: ["/tmp", "/dev/null", "/sandbox/.openclaw", "/sandbox/.nemoclaw", "/home/linuxbrew"],
  },
  landlock: { compatibility: "best_effort" },
  process: { run_as_user: "sandbox", run_as_group: "sandbox" },
  network_policies: {
    nvidia: { endpoints: [
      { host: "integrate.api.nvidia.com", port: 443, rules: [
        { allow: { method: "POST", path: "/v1/chat/completions" } },
        { allow: { method: "POST", path: "/v1/completions" } },
        { allow: { method: "POST", path: "/v1/embeddings" } },
        { allow: { method: "GET", path: "/v1/models" } },
        { allow: { method: "GET", path: "/v1/models/**" } }] },
      { host: "inference-api.nvidia.com", port: 443, rules: [
        { allow: { method: "GET", path: "/v1/models" } }] }],
      binaries: [{ path: "/usr/local/bin/openclaw" }] },
    managed_inference: { endpoints: [{ host: "inference.local", port: 443, rules: [
        { allow: { method: "GET", path: "/**" } }, { allow: { method: "POST", path: "/**" } }] }],
      binaries: [{ path: "/usr/local/bin/openclaw" }, { path: "/usr/local/bin/node" }, { path: "/usr/bin/node" }, { path: "/usr/bin/curl" }, { path: "/usr/bin/python3" }] },
    clawhub: { endpoints: [{ host: "clawhub.ai", port: 443, rules: [{ allow: { method: "GET", path: "/**" } }, { allow: { method: "POST", path: "/**" } }] }],
      binaries: [{ path: "/usr/local/bin/openclaw" }, { path: "/usr/local/bin/node" }] },
    openclaw_docs: { endpoints: [{ host: "docs.openclaw.ai", port: 443, rules: [{ allow: { method: "GET", path: "/**" } }] }],
      binaries: [{ path: "/usr/local/bin/openclaw" }] },
    npm_registry: { endpoints: [{ host: "registry.npmjs.org", port: 443, rules: [{ allow: { method: "GET", path: "/**" } }] }],
      binaries: [{ path: "/usr/local/bin/openclaw" }] },
  },
  // Opt-in presets are deliberately ABSENT from this baseline.
  // The `github` preset (github.com, api.github.com) and the messaging presets (telegram/discord/slack) are the Hermes-style exfil surface.
  // They are granted by explicit onboard choice only.
};

// Run a command INSIDE the live sandbox via `openshell sandbox exec` over the /ws/terminal PTY, so the result is the real kernel verdict, not the model's.
// The command rides the cmd= query string rather than being retyped into the PTY.
export async function sandboxExec(command, { agent = null, idleMs = 8000, totalMs = 30000, signal = null } = {}) {
  /* @doc <code>helpers.sandboxExec(command, {agent})</code> ::
       Run <code>command</code> inside your live OpenShell sandbox via <code>openshell sandbox
       exec</code> and return its real output (the kernel's actual allow/deny). Discovers the
       sandbox name if <code>agent</code> is omitted. Use it to confirm a
       <code>helpers.evalSandboxNetwork</code> / <code>evalSandboxFs</code> prediction against
       the running sandbox. Launchable only.
  */
  let name = agent || localStorage.getItem("nemoclaw_sandbox_name");
  if (!name) {
    const list = await terminal("openshell sandbox list", { idleMs: 6000, totalMs: 18000, signal });
    const m = (list.output || "").match(/^\s*([A-Za-z0-9._-]+)\s+\d{4}-\d\d-\d\d.*?Ready/m);
    name = m ? m[1] : "my-assistant";
    try { localStorage.setItem("nemoclaw_sandbox_name", name); } catch (_) {}
  }
  const res = await terminal("openshell sandbox exec -n " + name + " -- " + command, { idleMs, totalMs, signal });
  return { ...res, sandbox: name, command };
}

// Read and parse the launchable's live OpenShell policy, so a cell predicts from the SAME policy the kernel enforces rather than a baked copy.
// Returns the exact command run and the raw response alongside the parsed object.
export async function policyGet(agent = null, { idleMs = 8000, totalMs = 30000, signal = null } = {}) {
  /* @doc <code>helpers.policyGet(agent?)</code> ::
       Read your launchable's live OpenShell policy. Runs <code>openshell policy get &lt;agent&gt;
       --full</code> over the operator terminal and parses the YAML body. Returns
       <code>{ agent, command, raw, status, policy, parseError }</code>: the exact command run, the raw
       text it returned, the status header, the parsed policy object, and an explicit parser error
       when no policy is available (the shape
       <code>evalSandboxNetwork</code> / <code>evalSandboxFs</code> read). Launchable only.
  */
  const name = agent || localStorage.getItem("nemoclaw_sandbox_name") || "my-assistant";
  const command = "openshell policy get " + name + " --full";
  const res = await terminal(command, { idleMs, totalMs, signal });
  const raw = (res.output || "").trim();
  const sep = raw.indexOf("---");
  const status = sep >= 0 ? raw.slice(0, sep).trim() : raw;
  const body = sep >= 0 ? raw.slice(sep + 3) : "";
  let policy = null;
  let parseError = "";
  if (body.trim()) {
    try {
      const yaml = await import(POLICY_YAML_MODULE_URL);
      if (typeof yaml.load !== "function") throw new Error("vendored YAML parser does not export load()");
      policy = yaml.load(body);
      if (!policy || typeof policy !== "object" || Array.isArray(policy)) {
        throw new Error("policy YAML did not produce an object");
      }
    } catch (error) {
      parseError = error instanceof Error ? error.message : String(error);
      policy = null;
    }
  }
  else parseError = "openshell policy get returned no YAML body after the status header";
  return { agent: name, command, raw, status, policy, parseError };
}

// Render a policy object back to the OpenShell YAML it mirrors, so the map can show the exact source every edge is computed from.
// This is the real file shape a student would `cat` on the launchable, not an opaque in-page object.
export function policyToYaml(p) {
  /* @doc <code>helpers.policyToYaml(policy)</code> ::
       Render a sandbox-policy object as the OpenShell YAML it mirrors (the same shape
       <code>openshell policy get</code> prints), for showing the source a map or check is
       computed from.
  */
  const L = [];
  const fp = p.filesystem_policy || {};
  L.push("version: 1", "filesystem_policy:");
  if ("include_workdir" in fp) L.push(`  include_workdir: ${fp.include_workdir}`);
  for (const k of ["read_only", "read_write"])
    if (fp[k]) { L.push(`  ${k}:`); fp[k].forEach(x => L.push(`    - ${x}`)); }
  if (p.landlock) L.push("landlock:", `  compatibility: ${p.landlock.compatibility}`);
  if (p.process) L.push("process:", `  run_as_user: ${p.process.run_as_user}`, `  run_as_group: ${p.process.run_as_group}`);
  L.push("network_policies:");
  for (const [name, np] of Object.entries(p.network_policies || {})) {
    L.push(`  ${name}:`, "    endpoints:");
    (np.endpoints || []).forEach(ep => {
      L.push(`      - host: ${ep.host}`, `        port: ${ep.port}`);
      if (ep.rules) { L.push("        rules:"); ep.rules.forEach(r => L.push(`          - allow: { method: ${r.allow.method}, path: ${r.allow.path} }`)); }
    });
    L.push("    binaries:");
    (np.binaries || []).forEach(b => L.push(`      - ${b.path}`));
  }
  return L.join("\n");
}

// Per-line annotation for the policy YAML, naming what each line is FOR so a reader can hover any line and learn its purpose.
// The binary lines carry the answer to "why do curl and openclaw differ" right where it lives.
const _POLICY_NOTES = [
  [/^\s*#/, "comment / provenance, not part of the policy"],
  [/^version:/, "policy schema version"],
  [/^filesystem_policy:/, "Landlock rules: which paths the agent may read or write"],
  [/^\s*include_workdir:/, "the agent's working directory (/sandbox) is writable"],
  [/^\s*read_only:/, "readable but NOT writable; a write here is refused with EACCES"],
  [/^\s*read_write:/, "the only paths the agent is allowed to write to"],
  [/^landlock:/, "kernel-level filesystem enforcement"],
  [/^\s*compatibility:/, "best_effort: applied where the kernel supports Landlock (not strict enforce)"],
  [/^process:/, "the unprivileged identity the agent runs as"],
  [/^\s*run_as_/, "non-root user/group; setuid and similar are blocked by seccomp"],
  [/^network_policies:/, "egress is DENY by default; each named block below grants one set of destinations"],
  [/^\s*endpoints:/, "the destinations (host, port, and HTTP method/path) this block permits"],
  [/^\s*-?\s*host:/, "an allowed destination host (exact or glob match)"],
  [/^\s*port:/, "the allowed port on that host"],
  [/^\s*rules:/, "L7 filter: only these HTTP method + path combinations are allowed through"],
  [/^\s*-?\s*allow:/, "one permitted HTTP method + path"],
  [/^\s*binaries:/, "ONLY these executables may use this block. This is why curl and openclaw differ: same host, but the kernel checks WHICH binary is connecting."],
  [/^\s{6,}-\s*\//, "an executable allowed to use the block above; any other binary is denied even to the same host"],
  [/^\s{2,4}[A-Za-z0-9_]+:\s*$/, "the name of one allow-rule block"],
];

// Render each YAML line with theme-var coloring so it flips light/dark, unlike the dark-only hljs theme, and return its annotation.
// Keys, list dashes, and comments each get a variable color; the note comes from _POLICY_NOTES.
export function annotatePolicyYaml(yaml) {
  /* @doc <code>helpers.annotatePolicyYaml(yaml)</code> ::
       Split a policy YAML into <code>{html, note}</code> lines (theme-var syntax coloring + a
       plain-English purpose for each line), for an annotated, hover-explained policy view.
  */
  const e = s => String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  return yaml.split("\n").map(line => {
    let html;
    if (/^\s*#/.test(line)) {
      html = `<span style="color:var(--tf,#8a8a8a)">${e(line)}</span>`;
    } else {
      const kv = line.match(/^(\s*-?\s*)([A-Za-z0-9_.]+)(:)(.*)$/);
      if (kv) html = e(kv[1]) + `<span style="color:var(--gs,#aee23a)">${e(kv[2])}</span>${kv[3]}<span style="color:var(--td,#b0b0b0)">${e(kv[4])}</span>`;
      else {
        const li = line.match(/^(\s*-\s*)(.*)$/);
        html = li ? `<span style="color:var(--g,#76b900)">${e(li[1])}</span><span style="color:var(--td,#b0b0b0)">${e(li[2])}</span>` : e(line);
      }
    }
    let note = "";
    for (const [re, n] of _POLICY_NOTES) if (re.test(line)) { note = n; break; }
    return { html, note };
  });
}

// Interactive trust-boundary map driven by the policy object.
// Switching the calling binary recomputes every egress edge through evalSandboxNetwork, and clicking a target shows its rules and verdict reason.
// The operator token sits ABOVE the checkpoint to mark the escalation axis the sandbox never sees. Returns { setBinary }.
export function mountPolicyMap(sel, { policy = OPENSHELL_POLICY_HARDENED, binaries, snapshotDate = "2026-06-17" } = {}) {
  const root = typeof sel === "string" ? document.querySelector(sel) : sel;
  if (!root) return;
  root.dataset.state = "ready";
  const BINS = binaries || [
    { path: "/usr/bin/curl", label: "curl" },
    { path: "/usr/local/bin/openclaw", label: "openclaw" },
    { path: "/usr/local/bin/node", label: "node" },
    { path: "/usr/bin/python3", label: "python3" },
  ];
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  // Targets: every endpoint in the policy, plus three denied-by-default contrasts.
  const seen = new Set(); const targets = [];
  for (const [name, p] of Object.entries(policy.network_policies || {}))
    for (const ep of (p.endpoints || [])) {
      const host = ep.host || "(any host)"; const key = host + ":" + (ep.port || "");
      if (seen.has(key)) continue; seen.add(key);
      const rule = ((ep.rules || [])[0] || {}).allow || { method: "GET", path: "/" };
      targets.push({ host, port: ep.port || 443, policy: name,
        method: rule.method === "*" ? "GET" : rule.method, path: rule.path === "**" ? "/v1/models" : rule.path });
    }
  [["example.com", 443, "/"], ["169.254.169.254", 80, "/latest/meta-data/"], ["discord.com", 443, "/"]]
    .forEach(([host, port, path]) => { if (!seen.has(host + ":" + port)) targets.push({ host, port, method: "GET", path, policy: null, contrast: true }); });

  // Geometry.
  const W = 940, TB = 104, RH = 44, COLX = 560, AX0 = 46, AX1 = 250, CHK = 300;
  const top = TB + 46, H = top + targets.length * RH + 30, ay = top + (targets.length * RH) / 2 - RH / 2;
  const GREEN = "var(--g,#76b900)", RED = "#d1242f", AMBER = "#d9a441",
        TXT = "var(--td,#b0b0b0)", HEAD = "var(--gs,#aee23a)", BD = "var(--bd,#2a2a2a)", PANEL = "var(--e1,#161616)";

  root.innerHTML =
    `<div class="pmap-controls" style="display:flex;flex-wrap:wrap;gap:14px;align-items:center;margin:.4em 0 .6em;font-size:.85rem;color:${TXT}">
       <label style="font-family:var(--mono)">Calling binary:
         <select class="pmap-bin" style="margin-left:6px;background:var(--e2,#1c1c1c);color:${HEAD};border:1px solid ${BD};border-radius:4px;padding:3px 8px;font-family:var(--mono);font-size:.85rem">
           ${BINS.map((b, i) => `<option value="${esc(b.path)}"${i === 0 ? " selected" : ""}>${esc(b.label)} &mdash; ${esc(b.path)}</option>`).join("")}
         </select>
       </label>
       <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:22px;height:0;border-top:2px solid ${GREEN}"></span>allowed</span>
       <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:22px;height:0;border-top:2px dashed ${RED}"></span>denied</span>
       <span style="display:inline-flex;align-items:center;gap:6px"><span style="width:12px;height:12px;background:${AMBER};border-radius:2px"></span>above the checkpoint</span>
       <span style="margin-left:auto">
         <button class="pmap-src" type="button" style="background:none;border:none;color:${HEAD};cursor:pointer;font:inherit;text-decoration:underline">hide policy source</button>
       </span>
     </div>
     <div class="pmap-prov" style="font-size:.78rem;color:${TXT};margin:0 0 .5em">Every edge in this diagram is computed from the OpenShell policy shown below, a snapshot read off the live NemoClaw launchable on ${esc(snapshotDate)}. Nothing here is hand-drawn. Click any destination on the right and the source jumps to the exact rule that decides it; run the <em>Read your launchable's live policy</em> cell below to fetch your own box's policy and confirm it matches.</div>
     <div class="pmap-svg"></div>
     <div class="pmap-detail" style="margin-top:.5em;padding:10px 14px;background:${PANEL};border:1px solid ${BD};border-left:3px solid ${HEAD};border-radius:6px;font-size:.84rem;color:${TXT};line-height:1.5">Click any destination on the right. This panel names its rule and the binaries allowed to use it, the policy below scrolls to that rule and highlights it, and you get the live verdict for the binary you picked.</div>
     <div style="margin:.8em 0 .3em;font-size:.78rem;color:${TXT}">The policy this map reads, line by line <span style="opacity:.7">&middot; click a destination above to jump to its rule, or hover any line for what it does</span></div>
     <pre class="pmap-source-pre" style="margin:0;padding:10px 12px;background:var(--e2,#0d0d0d);border:1px solid ${BD};border-top-left-radius:6px;border-top-right-radius:6px;font-family:var(--mono),monospace;font-size:.78rem;line-height:1.5;color:${TXT};max-height:340px;overflow:auto;white-space:pre"></pre>
     <div class="pmap-note" style="margin:0 0 .6em;padding:7px 12px;background:var(--e1,#161616);border:1px solid ${BD};border-top:none;border-bottom-left-radius:6px;border-bottom-right-radius:6px;font-size:.8rem;color:${TXT};line-height:1.4;min-height:1.4em">Hover any line to see what it does.</div>`;

  const sb = root.querySelector(".pmap-svg"), bin = root.querySelector(".pmap-bin"), detail = root.querySelector(".pmap-detail");

  function verdictFor(t, binPath) {
    return evalSandboxNetwork({ binary: binPath, host: t.host, port: t.port, method: t.method, path: t.path }, policy);
  }
  function render(binPath) {
    const edges = targets.map((t, i) => {
      const ty = top + i * RH + RH / 2;
      const v = verdictFor(t, binPath);
      const col = v.action === "allow" ? GREEN : RED;
      const dash = v.action === "allow" ? "" : ` stroke-dasharray="5 4"`;
      return `<line x1="${AX1}" y1="${ay}" x2="${COLX}" y2="${ty}" stroke="${col}" stroke-width="2"${dash} opacity="${v.action === "allow" ? 0.95 : 0.6}"/>`;
    }).join("");
    const nodes = targets.map((t, i) => {
      const ty = top + i * RH + RH / 2;
      const v = verdictFor(t, binPath);
      const col = v.action === "allow" ? GREEN : RED;
      return `<g class="pmap-t" data-i="${i}" style="cursor:pointer">
        <rect x="${COLX}" y="${ty - 16}" width="${W - COLX - 14}" height="32" rx="6" fill="${PANEL}" stroke="${col}" stroke-width="1.6"/>
        <circle cx="${COLX + 14}" cy="${ty}" r="5" fill="${col}"/>
        <text x="${COLX + 28}" y="${ty - 1}" font-family="var(--mono),monospace" font-size="11.5" fill="${HEAD}">${esc(t.host)}${t.port === 443 ? "" : ":" + t.port}</text>
        <text x="${COLX + 28}" y="${ty + 11}" font-family="Arial,sans-serif" font-size="9.5" fill="${TXT}">${t.contrast ? "not in any policy" : esc(t.policy)} &middot; ${esc(t.method)} ${esc(t.path)}</text>
      </g>`;
    }).join("");
    const binLabel = (BINS.find(b => b.path === binPath) || {}).label || binPath;
    sb.innerHTML =
`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Interactive trust-boundary map of the sandbox policy" preserveAspectRatio="xMidYMid meet" style="width:100%;height:auto;display:block">
  <!-- operator plane (above the checkpoint) -->
  <rect x="14" y="12" width="${W - 28}" height="${TB - 24}" rx="8" fill="none" stroke="${AMBER}" stroke-width="1.4" stroke-dasharray="3 4"/>
  <text x="26" y="32" font-family="var(--mono),monospace" font-size="11" fill="${AMBER}" font-weight="700">OPERATOR PLANE &middot; above the sandbox, the kernel never sees it</text>
  <rect x="26" y="44" width="180" height="40" rx="6" fill="${PANEL}" stroke="${AMBER}" stroke-width="1.6"/>
  <text x="116" y="61" text-anchor="middle" font-family="var(--mono),monospace" font-size="11" fill="${AMBER}" font-weight="700">gateway token</text>
  <text x="116" y="75" text-anchor="middle" font-family="Arial,sans-serif" font-size="9.5" fill="${TXT}">operator.admin</text>
  <text x="228" y="60" font-family="Arial,sans-serif" font-size="10.5" fill="${TXT}">reads SOUL.md, plants cron, patches config, injects a turn.</text>
  <text x="228" y="74" font-family="Arial,sans-serif" font-size="10.5" fill="${TXT}">None of it crosses the egress checkpoint.</text>
  <!-- arrow from token down into the sandbox internals -->
  <line x1="116" y1="84" x2="116" y2="110" stroke="${AMBER}" stroke-width="2" marker-end="url(#pmap-arrow-amber)"/>
  <!-- the sandbox box -->
  <rect x="${AX0 - 22}" y="${TB + 8}" width="${CHK - AX0 + 22}" height="${H - TB - 24}" rx="10" fill="none" stroke="${BD}" stroke-width="1.6"/>
  <text x="${AX0 - 8}" y="${TB + 22}" font-family="var(--mono),monospace" font-size="10.5" fill="${TXT}">OpenShell sandbox &middot; non-root</text>
  <text x="${AX0 - 8}" y="${TB + 37}" font-family="var(--mono),monospace" font-size="10.5" fill="${TXT}">Landlock + seccomp + netns</text>
  <!-- agent + selected binary -->
  <rect x="${AX0}" y="${ay - 20}" width="${AX1 - AX0}" height="40" rx="8" fill="${PANEL}" stroke="${HEAD}" stroke-width="1.8"/>
  <text x="${(AX0 + AX1) / 2}" y="${ay - 3}" text-anchor="middle" font-family="Arial,sans-serif" font-size="11.5" fill="${HEAD}" font-weight="700">the agent</text>
  <text x="${(AX0 + AX1) / 2}" y="${ay + 12}" text-anchor="middle" font-family="var(--mono),monospace" font-size="10.5" fill="${TXT}">${esc(binLabel)}</text>
  <!-- the policy checkpoint (sandbox egress wall) -->
  <line x1="${CHK}" y1="${TB + 12}" x2="${CHK}" y2="${H - 18}" stroke="${BD}" stroke-width="1.4" stroke-dasharray="2 4"/>
  <text x="${CHK + 6}" y="${TB + 26}" font-family="var(--mono),monospace" font-size="9.5" fill="${TXT}">policy checkpoint:</text>
  <text x="${CHK + 6}" y="${TB + 38}" font-family="var(--mono),monospace" font-size="9.5" fill="${TXT}">binary + host + port + method/path</text>
  <defs>
    <marker id="pmap-arrow-amber" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="${AMBER}"/></marker>
  </defs>
  ${edges}
  ${nodes}
</svg>`;
    detail.dataset.bin = binPath;
  }
  function showDetail(i) {
    root.dataset.state = "selected";
    const t = targets[i], binPath = detail.dataset.bin, v = verdictFor(t, binPath);
    const binLabel = (BINS.find(b => b.path === binPath) || {}).label || binPath;
    const allowedBins = t.policy ? ((policy.network_policies[t.policy] || {}).binaries || []).map(b => b.path) : [];
    const binListed = allowedBins.includes(binPath);
    // Why does the verdict change when you switch the binary?
    // The kernel checks the calling executable's identity, not just the host.
    // Spell that out for the selected binary so the edge flipping is understandable, not magic.
    let why;
    if (!t.policy) why = `No policy names <code>${esc(t.host)}</code>, so every binary is denied (egress is deny-by-default).`;
    else if (binListed) why = `<code>${esc(binLabel)}</code> is on this endpoint's binary list, so it is allowed (if the method and path also match).`;
    else why = `<code>${esc(binLabel)}</code> is NOT on this endpoint's binary list, so the kernel refuses it even though the host is allow-listed. Switch the binary to one of the listed ones and this edge turns green: that is binary-bound egress.`;
    detail.innerHTML =
      `<div style="font-family:var(--mono);color:${HEAD};font-size:.9rem">${esc(t.host)}:${t.port}</div>
       <div style="margin-top:.3em">policy: <code>${t.policy ? esc(t.policy) : "none (denied by default)"}</code> &middot; rule: <code>${esc(t.method)} ${esc(t.path)}</code></div>
       <div style="margin-top:.2em">binaries this endpoint allows: ${allowedBins.length ? allowedBins.map(b => `<code>${esc(b)}</code>`).join(", ") : "<em>none</em>"}</div>
       <div style="margin-top:.4em;color:${v.action === "allow" ? GREEN : RED};font-weight:700">verdict for ${esc(binLabel)}: ${v.action.toUpperCase()}</div>
       ${v.reason ? `<div style="margin-top:.2em;font-size:.8rem">reason: ${esc(v.reason)}</div>` : ""}
       <div style="margin-top:.4em;font-size:.8rem">${why}</div>`;
    focusSource(t);   // scroll the policy source to this rule and highlight it
  }
  bin.addEventListener("change", () => { root.dataset.state = "selected"; render(bin.value); });
  sb.addEventListener("click", e => { const g = e.target.closest(".pmap-t"); if (g) showDetail(+g.dataset.i); });

  // ── Observability: show the exact policy every edge is computed from ─────────
  // This button makes NO request; it prints the embedded snapshot as the YAML the map mirrors.
  // Reading the LIVE policy is a separate, inspectable cell (helpers.terminal openshell policy get) with visible source and a raw response, like every other launchable call.
  const srcBtn = root.querySelector(".pmap-src"), srcPre = root.querySelector(".pmap-source-pre"),
        noteBar = root.querySelector(".pmap-note");
  const snapshotYaml = "# The OpenShell policy this map computes every edge from.\n"
    + "# Snapshot of the live NemoClaw launchable, read " + snapshotDate + " via `openshell policy get`.\n"
    + "# Read your own launchable's live policy with the cell below and compare.\n\n"
    + policyToYaml(policy);
  const NOTE_DEFAULT = "Hover any line to see what it does.";
  // Per-line metadata, built from the same YAML, so a click on a destination can jump to and highlight the rule that decides it.
  // It records which network-policy block each line belongs to, and whether it is the host line or a binary line (the two that flip the verdict).
  let META = [], hot = [];
  function computeLineMeta(raw) {
    let inNet = false, cur = null;
    return raw.map(line => {
      if (/^network_policies:/.test(line)) { inNet = true; return { netHdr: true }; }
      if (!inNet) return {};
      const blk = line.match(/^  ([A-Za-z0-9_.-]+):\s*$/);
      if (blk) { cur = blk[1]; return { pol: cur, blockHdr: true }; }
      const h = line.match(/^\s+-?\s*host:\s*(\S+)/);
      if (h) return { pol: cur, host: h[1] };
      if (/^\s+binaries:/.test(line)) return { pol: cur, binsHdr: true };
      if (/^\s{6,}-\s*\//.test(line)) return { pol: cur, binPath: true };
      return cur ? { pol: cur } : {};
    });
  }
  function clearHot() { hot.forEach(el => { el.style.background = ""; el.style.borderLeft = ""; el.style.paddingLeft = ""; }); hot = []; }
  // Scroll the source to the rule deciding target t, highlight its whole block, and put a left bar on the host + binaries lines.
  // That makes "why this verdict" visible in the policy text itself.
  function focusSource(t) {
    if (srcPre.style.display === "none") return;
    clearHot();
    const spans = [...srcPre.querySelectorAll(".pmap-ln")];
    let anchor = null;
    if (t.policy) {
      spans.forEach(el => {
        const m = META[+el.dataset.i] || {};
        if (m.pol !== t.policy) return;
        el.style.background = "var(--e3)";
        if (m.host === t.host || m.binsHdr || m.binPath || m.blockHdr) { el.style.borderLeft = "3px solid var(--g)"; el.style.paddingLeft = "5px"; }
        hot.push(el);
        if (m.host === t.host && !anchor) anchor = el;
      });
      if (!anchor) anchor = spans.find(el => { const m = META[+el.dataset.i] || {}; return m.pol === t.policy && m.blockHdr; });
    } else {
      anchor = spans.find(el => (META[+el.dataset.i] || {}).netHdr);
      if (anchor) { anchor.style.background = "var(--e3)"; anchor.style.borderLeft = "3px solid " + RED; anchor.style.paddingLeft = "5px"; hot.push(anchor); }
    }
    if (anchor) srcPre.scrollTop += anchor.getBoundingClientRect().top - srcPre.getBoundingClientRect().top - 10;
  }
  // Render the policy as theme-coloured, hover-annotated lines so a reader learns what each line is FOR rather than facing a flat dump.
  // The binary lines explain why curl and openclaw differ; lines with a note get an underline cue and update the note bar on hover.
  function renderSource() {
    const lines = annotatePolicyYaml(snapshotYaml);
    META = computeLineMeta(snapshotYaml.split("\n"));
    srcPre.innerHTML = lines.map((ln, i) =>
      `<span class="pmap-ln" data-i="${i}"${ln.note ? ` title="${esc(ln.note)}" style="display:block;cursor:help;border-radius:3px"` : ` style="display:block"`}>${ln.html || "&nbsp;"}</span>`
    ).join("");
    noteBar.textContent = NOTE_DEFAULT;
    srcPre.querySelectorAll(".pmap-ln").forEach(el => {
      const note = lines[+el.dataset.i].note;
      if (!note) return;
      el.addEventListener("mouseenter", () => { noteBar.textContent = note; });
      el.addEventListener("mouseleave", () => { noteBar.textContent = NOTE_DEFAULT; });
    });
  }
  srcBtn.addEventListener("click", () => {
    const open = srcPre.style.display !== "none";
    srcPre.style.display = open ? "none" : "block";
    noteBar.style.display = open ? "none" : "block";
    srcBtn.textContent = open ? "view policy source" : "hide policy source";
    if (open) clearHot(); else renderSource();
  });

  render(BINS[0].path);
  renderSource();   // the policy source is shown by default, so the map is visibly policy-derived
  return { setBinary: p => { bin.value = p; render(p); } };
}
