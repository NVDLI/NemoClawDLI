// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// OpenClaw gateway + claw widgets for 03a/03b/03c/04a.
// Holds the live WebSocket gateway client and the connect/probe widgets.
// Also openclawChat, GW_CONNECT, and the recover flow.

import { updateClawPill, escHtml, _escAttr, mountCanvasFlow } from "./_shared.js";
import { localizeCourseUiText } from "./_locale.js";
import {
  DEFAULT_OPENCLAW_PROXY_BASE, accessProviderForOpenClawUrl, getOpenClawConnection, getOpenClawProxyConfig, getOpenClawWsRelayEnabled, migrateOpenClawConnectionStorage,
  normalizeOpenClawLaunchableUrl, normalizeOpenClawProxyBase, openclawHttpUrl,
  openclawWebSocketUrl, setOpenClawConnection, setOpenClawProxyConfig, setOpenClawWsRelayEnabled,
} from "./_connection.js";
import { openclawLoopbackProbe, terminal } from "./_openshell.js";
import { filterOpenClawRuntimeNoise, filterOpenClawRuntimeValue, openclawMessageText, openclawResultText } from "./_runtime_text.js";

export {
  DEFAULT_OPENCLAW_PROXY_BASE, accessProviderForOpenClawUrl, getOpenClawConnection, getOpenClawProxyConfig, getOpenClawWsRelayEnabled, migrateOpenClawConnectionStorage,
  normalizeOpenClawLaunchableUrl, normalizeOpenClawProxyBase, openclawHttpUrl,
  openclawWebSocketUrl, setOpenClawConnection, setOpenClawProxyConfig, setOpenClawWsRelayEnabled,
};
export { filterOpenClawRuntimeNoise, filterOpenClawRuntimeValue, openclawMessageText, openclawResultText };

const accessCookieName = provider => provider === "pomerium" ? "_pomerium" : "CF_Authorization";
function _uniqueId(prefix = "") {
  if (typeof crypto.randomUUID === "function") return prefix + crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return prefix + [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
}

export function detectOpenClawBrowserSession(rawUrl, accessProvider = "auto", timeoutMs = 4000) {
  const direct = openclawWebSocketUrl(
    rawUrl,
    "/cli/gateway",
    "",
    { enabled: false, base: "" },
    accessProvider,
  );
  if (!direct.url) return Promise.resolve(false);
  return new Promise(resolve => {
    let socket = null;
    let settled = false;
    const finish = detected => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      try { socket?.close(); } catch (_) {}
      resolve(Boolean(detected));
    };
    const timer = setTimeout(() => finish(false), Math.max(250, Number(timeoutMs) || 4000));
    try {
      socket = new WebSocket(direct.url);
    } catch (_) {
      finish(false);
      return;
    }
    socket.onmessage = event => {
      try {
        const frame = JSON.parse(event.data);
        if (frame?.event === "connect.challenge") finish(true);
      } catch (_) {}
    };
    socket.onerror = () => finish(false);
    socket.onclose = () => finish(false);
  });
}

export function openclawGatewayWsUrl(rawUrl, accessSession = "", proxyBase = null, proxyEnabled = null, accessProvider = "auto") {
  let provider = "auto";
  try { provider = accessProviderForOpenClawUrl(rawUrl, accessProvider); }
  catch (_) { /* openclawWebSocketUrl below returns the authoritative error */ }
  const relayEnabled = proxyEnabled === true ||
    (proxyEnabled === null && (getOpenClawWsRelayEnabled() ||
      (provider === "pomerium" && Boolean(String(accessSession || "").trim()))));
  if (!relayEnabled) {
    return openclawWebSocketUrl(rawUrl, "/cli/gateway", "", { enabled: false, base: "" }, accessProvider);
  }
  const config = {
    base: normalizeOpenClawProxyBase(proxyBase || DEFAULT_OPENCLAW_PROXY_BASE),
    enabled: true,
  };
  return openclawWebSocketUrl(rawUrl, "/cli/gateway", accessSession, config, accessProvider);
}

export function gatewayTokenFromAgentMetadata(payload) {
  const raw = String(payload?.agent?.dashboardUrl || "").trim();
  if (!raw) return null;
  try {
    const parsed = new URL(raw, "https://nemoclaw.invalid/");
    const fragment = new URLSearchParams(parsed.hash.replace(/^#/, ""));
    return fragment.get("token") || parsed.searchParams.get("token") || null;
  } catch (_) {
    return null;
  }
}

function redactOpenClawText(value) {
  return String(value || "")
    .replace(/([?&#](?:token|access_session|cf_access_jwt|session|password|secret)=)[^&#\s"']+/gi, "$1<redacted>")
    .replace(/((?:Bearer|Basic)\s+)[A-Za-z0-9._~+/=-]+/gi, "$1<redacted>")
    .replace(/((?:_pomerium|CF_Authorization)=)[^;\s"']+/gi, "$1<redacted>");
}

export function redactOpenClawDiagnostic(value, key = "", seen = new WeakSet()) {
  const name = String(key || "").toLowerCase();
  if (value == null || typeof value === "number" || typeof value === "boolean") return value;
  if (typeof value === "string") {
    if (/authorization|cookie|password|secret|session|token/.test(name) && name !== "status") {
      return "<redacted>";
    }
    return redactOpenClawText(value);
  }
  if (typeof value !== "object") return redactOpenClawText(value);
  if (seen.has(value)) return "<circular>";
  seen.add(value);
  if (Array.isArray(value)) return value.map(item => redactOpenClawDiagnostic(item, key, seen));
  const output = {};
  for (const [childKey, childValue] of Object.entries(value)) {
    output[childKey] = redactOpenClawDiagnostic(childValue, childKey, seen);
  }
  return output;
}

const OPENCLAW_BOOTSTRAP_PATHS = new Set(["/api/agent", "/healthz"]);

export async function openclawBootstrapRequest(path = "/api/agent", { signal = null } = {}) {
  /* @doc <code>helpers.openclawBootstrapRequest(path)</code> ::
       Read <code>/api/agent</code> or <code>/healthz</code> through the provider selected
       from the normalized Module 3a connection. Pomerium reads these fixed endpoints from
       launchable loopback over the terminal WebSocket, which tries the signed-in browser
       first and then the approved provider-bound relay. Returns response metadata plus
       parsed JSON without exposing either access credential. */
  const actionPath = String(path || "");
  if (!OPENCLAW_BOOTSTRAP_PATHS.has(actionPath)) {
    throw new Error("OpenClaw bootstrap requests are limited to /api/agent and /healthz");
  }
  const connection = getOpenClawConnection();
  const rawUrl = String(connection.rawUrl || "").replace(/\/+$/, "");
  if (!rawUrl) throw new Error("Set the launchable URL in the Module 3a probe first.");
  const provider = accessProviderForOpenClawUrl(rawUrl, connection.accessProvider);
  if (provider === "pomerium") {
    const result = await openclawLoopbackProbe(actionPath, { baseUrl: rawUrl, signal });
    return {
      ...result,
      headers: {},
      displayUrl: rawUrl + actionPath,
    };
  }

  const route = openclawHttpUrl(
    rawUrl,
    actionPath,
    getOpenClawProxyConfig(),
    provider,
    connection.accessSession,
  );
  const headers = { Accept: "application/json, text/plain, */*" };
  if (route.viaProxy && connection.accessSession) {
    if (provider === "cloudflare") headers["CF-Access-Jwt-Assertion"] = connection.accessSession;
    else {
      headers["X-OpenClaw-Access-Provider"] = provider;
      headers["X-OpenClaw-Access-Session"] = connection.accessSession;
    }
  }
  // /api/agent discovers the gateway token. A stale token from another
  // launchable must not prevent that replacement.
  if (actionPath !== "/api/agent" && connection.token) {
    headers.Authorization = "Bearer " + connection.token;
  }
  const response = await fetch(route.url, {
    headers,
    credentials: route.viaProxy ? "same-origin" : "include",
    signal,
  });
  const body = await response.text();
  let json = null;
  try { json = JSON.parse(body); } catch (_) {}
  return {
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    body,
    json,
    headers: Object.fromEntries(response.headers),
    transport: route.viaProxy ? "approved-provider-relay" : "direct-browser",
    displayUrl: route.displayUrl,
  };
}

let _verifiedGatewayToken = { rawUrl: "", token: "", verifiedAt: 0, metadataMatches: null };

// The launchable access session and OpenClaw gateway token are separate credentials.
// Fetch the token from GET /api/agent before the first gateway connection.
// Keep it only in the tab-scoped store.
export async function refreshOpenClawGatewayToken({ signal = null, maxAgeMs = 30000 } = {}) {
  const connection = getOpenClawConnection();
  const rawUrl = String(connection.rawUrl || "").replace(/\/+$/, "");
  if (!rawUrl) throw new Error("Set the launchable URL in the Module 3a probe first.");

  const now = Date.now();
  if (_verifiedGatewayToken.rawUrl === rawUrl && _verifiedGatewayToken.token &&
      now - _verifiedGatewayToken.verifiedAt < Math.max(0, Number(maxAgeMs) || 0)) {
    return { ..._verifiedGatewayToken, source: "verified-cache", changed: connection.token !== _verifiedGatewayToken.token };
  }

  let metadataToken = "";
  try {
    const probe = await openclawBootstrapRequest("/api/agent", { signal });
    if (probe.ok) metadataToken = gatewayTokenFromAgentMetadata(probe.json) || "";
  } catch (_) { /* fall back to the tab's last discovered token below */ }

  const token = metadataToken || connection.token;
  if (!token) throw new Error("GET /api/agent did not provide a gateway token. Reopen the launchable, then try again.");
  setOpenClawConnection({
    rawUrl,
    token,
    accessProvider: connection.accessProvider,
    accessSession: connection.accessSession,
  });
  _verifiedGatewayToken = {
    rawUrl,
    token,
    verifiedAt: now,
    metadataMatches: metadataToken ? true : null,
  };
  return {
    ..._verifiedGatewayToken,
    source: metadataToken ? "metadata" : "saved",
    changed: connection.token !== token,
  };
}

function accessCredentialDelivery(provider, viaProxy, accessSession) {
  if (!accessSession) {
    return viaProxy
      ? "No access session was supplied to the hosted relay."
      : "Browser credentials are sent by the browser to the launchable origin.";
  }
  if (!viaProxy) return "The saved access session is not copied into a direct browser request.";
  if (provider === "cloudflare") {
    return "The tab-scoped access session is sent to the approved relay as CF-Access-Jwt-Assertion.";
  }
  return "The tab-scoped access session is sent to the approved relay as X-OpenClaw-Access-Session.";
}

function openClawHttpDiagnostic(path, connection) {
  const provider = accessProviderForOpenClawUrl(connection.rawUrl, connection.accessProvider);
  const viaLoopback = provider === "pomerium";
  const route = openclawHttpUrl(
    connection.rawUrl,
    path,
    getOpenClawProxyConfig(),
    provider,
    connection.accessSession,
  );
  const headers = { Accept: "application/json, text/plain, */*" };
  if (route.viaProxy && connection.accessSession) {
    if (provider === "cloudflare") headers["CF-Access-Jwt-Assertion"] = "<redacted>";
    else {
      headers["X-OpenClaw-Access-Provider"] = provider;
      headers["X-OpenClaw-Access-Session"] = "<redacted>";
    }
  }
  if (path !== "/api/agent" && connection.token) headers.Authorization = "Bearer <redacted>";
  return {
    provider,
    route,
    request: {
      method: "GET",
      url: viaLoopback ? connection.rawUrl.replace(/\/+$/, "") + path : route.displayUrl,
      upstreamUrl: connection.rawUrl.replace(/\/+$/, "") + path,
      transport: viaLoopback ? "launchable terminal loopback (direct first, hosted relay fallback)" : route.viaProxy ? "hosted relay" : "direct browser",
      authSummary: viaLoopback
        ? connection.accessSession
          ? "The launchable terminal makes this request on the learner's behalf. It tries the signed-in browser first, then sends the tab-scoped session only to the approved provider-bound relay."
          : "The launchable terminal makes this request through the signed-in browser session; no browser cookie is copied."
        : accessCredentialDelivery(provider, route.viaProxy, connection.accessSession),
      headers: viaLoopback ? {} : headers,
    },
  };
}

export async function probeOpenClawGatewayConnection({ signal = null, timeoutMs = 15000, relayWebSocket = false } = {}) {
  const connection = getOpenClawConnection();
  const provider = accessProviderForOpenClawUrl(connection.rawUrl, connection.accessProvider);
  const route = openclawGatewayWsUrl(
    connection.rawUrl,
    connection.accessSession,
    null,
    relayWebSocket,
    provider,
  );
  const request = {
    method: "WEBSOCKET",
    url: route.displayUrl,
    upstreamUrl: connection.rawUrl.replace(/\/+$/, "") + "/cli/gateway",
    transport: route.viaProxy ? "hosted relay" : "direct browser",
    authSummary: accessCredentialDelivery(provider, route.viaProxy, connection.accessSession) +
      " The gateway token discovered from /api/agent is sent only in connect.auth.token.",
    connect: {
      method: "connect",
      role: "operator",
      scopes: ["operator.read", "operator.write", "operator.admin"],
      auth: { token: connection.token ? "<redacted>" : "<missing>" },
    },
  };

  return await new Promise(resolve => {
    let socket = null;
    let settled = false;
    let connectId = "";
    let challenge = null;
    const frames = [];
    const finish = result => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      try { socket?.close(); } catch (_) {}
      resolve({
        ...result,
        request,
        response: redactOpenClawDiagnostic({ challenge, frames }),
      });
    };
    const abort = () => finish({ ok: false, error: "Connection test stopped." });
    const timer = setTimeout(
      () => finish({ ok: false, error: `No gateway challenge arrived within ${Math.round(timeoutMs / 1000)} seconds.` }),
      Math.max(1000, Number(timeoutMs) || 15000),
    );
    if (signal?.aborted) return abort();
    signal?.addEventListener("abort", abort, { once: true });
    try {
      socket = new WebSocket(route.url);
    } catch (error) {
      finish({ ok: false, error: String(error?.message || error) });
      return;
    }
    socket.onmessage = event => {
      let frame;
      try { frame = JSON.parse(event.data); }
      catch (_) { frame = { raw: String(event.data || "") }; }
      frames.push(frame);
      if (frame?.event === "connect.challenge") {
        challenge = frame;
        if (!connection.token) {
          finish({
            ok: false,
            error: "Gateway challenge arrived, but GET /api/agent did not provide a gateway token.",
          });
          return;
        }
        connectId = _uniqueId("connection-audit-");
        socket.send(JSON.stringify({
          type: "req",
          id: connectId,
          method: "connect",
          params: {
            minProtocol: 4,
            maxProtocol: 4,
            client: {
              id: "openclaw-control-ui",
              version: "0.1.0",
              platform: "browser",
              mode: "webchat",
            },
            caps: ["tool-events"],
            role: "operator",
            scopes: ["operator.read", "operator.write", "operator.admin"],
            auth: { token: connection.token },
          },
        }));
        return;
      }
      if (frame?.type === "res" && frame?.id === connectId) {
        finish({
          ok: Boolean(frame.ok),
          error: frame.ok ? "" : String(frame.error?.message || "Gateway authentication failed."),
        });
      }
    };
    socket.onerror = () => finish({ ok: false, error: "Gateway WebSocket failed before authentication completed." });
    socket.onclose = () => {
      if (!settled) finish({ ok: false, error: "Gateway WebSocket closed before authentication completed." });
    };
  });
}

export async function runOpenClawConnectionAudit({
  baseUrl,
  accessSession = "",
  signal = null,
  onStep = null,
} = {}) {
  const rawUrl = normalizeOpenClawLaunchableUrl(baseUrl);
  if (!rawUrl) throw new Error("Enter the NemoClaw launchable Base URL.");
  const provider = accessProviderForOpenClawUrl(rawUrl);
  setOpenClawConnection({
    rawUrl,
    token: "",
    accessProvider: provider,
    accessSession,
  });
  setOpenClawWsRelayEnabled(false);

  const results = [];
  const notify = step => {
    try { onStep?.(redactOpenClawDiagnostic(step)); } catch (_) {}
  };
  const execute = async ({ id, title, what, purpose, request }, task) => {
    const step = { id, title, what, purpose, request: redactOpenClawDiagnostic(request), status: "running" };
    notify(step);
    const started = performance.now();
    try {
      const outcome = await task();
      Object.assign(step, outcome);
      step.status = outcome.ok ? "passed" : "failed";
    } catch (error) {
      step.status = "failed";
      step.ok = false;
      step.error = String(error?.message || error);
      step.response = redactOpenClawDiagnostic(error?.diagnostic || null);
    }
    step.elapsedMs = Math.round(performance.now() - started);
    results.push(step);
    notify(step);
    return step;
  };

  let connection = getOpenClawConnection();
  const metadataDiagnostic = openClawHttpDiagnostic("/api/agent", connection);
  const metadata = await execute({
    id: "agent-metadata",
    title: "Agent metadata",
    what: "Returns launchable agent metadata, including the dashboard URL used to discover the gateway token.",
    purpose: "Confirms launchable authentication and discovers the gateway token used by later WebSocket checks.",
    request: metadataDiagnostic.request,
  }, async () => {
    const response = await openclawBootstrapRequest("/api/agent", { signal });
    const token = response.ok ? (gatewayTokenFromAgentMetadata(response.json) || "") : "";
    if (token) {
      setOpenClawConnection({
        rawUrl,
        token,
        accessProvider: provider,
        accessSession,
      });
    }
    return {
      ok: Boolean(response.ok && token),
      error: !response.ok
        ? `GET /api/agent returned ${response.status} ${response.statusText}.`
        : token
          ? ""
          : "GET /api/agent succeeded but did not provide a gateway token.",
      response: redactOpenClawDiagnostic({
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
        body: response.json ?? response.body,
      }),
    };
  });

  connection = getOpenClawConnection();
  const directGatewayRoute = openclawGatewayWsUrl(
    rawUrl,
    connection.accessSession,
    null,
    false,
    provider,
  );
  const relayGatewayRoute = connection.accessSession
    ? openclawGatewayWsUrl(rawUrl, connection.accessSession, null, true, provider)
    : null;
  await execute({
    id: "gateway-websocket",
    title: "Gateway WebSocket",
    what: "Carries authenticated OpenClaw JSON-RPC for agent sessions, tools, models, and control operations.",
    purpose: "Confirms /cli/gateway reaches a challenge and accepts the token discovered from agent metadata.",
    request: {
      method: "WEBSOCKET",
      authSummary: accessCredentialDelivery(provider, Boolean(relayGatewayRoute), accessSession) +
        " The gateway token discovered from /api/agent is sent only in connect.auth.token.",
      attempts: [
        {
          url: directGatewayRoute.displayUrl,
          transport: "direct browser",
          authSummary: accessCredentialDelivery(provider, false, accessSession),
        },
        ...(relayGatewayRoute ? [{
          url: relayGatewayRoute.displayUrl,
          transport: "hosted relay fallback",
          authSummary: accessCredentialDelivery(provider, true, accessSession),
        }] : []),
      ],
      upstreamUrl: rawUrl + "/cli/gateway",
      gatewayAuthentication: metadata.ok ? "discovered from /api/agent and sent as connect.auth.token" : "unavailable",
    },
  }, async () => {
    const attempts = [];
    let relaySelected = false;
    let outcome = await probeOpenClawGatewayConnection({ signal, relayWebSocket: false });
    attempts.push(outcome);
    if (!outcome.ok && relayGatewayRoute) {
      relaySelected = true;
      outcome = await probeOpenClawGatewayConnection({ signal, relayWebSocket: true });
      attempts.push(outcome);
    }
    if (outcome.ok) setOpenClawWsRelayEnabled(relaySelected);
    return {
      ok: outcome.ok,
      error: outcome.error || "",
      response: {
        attempts,
        selectedTransport: relaySelected ? "hosted relay" : "direct browser",
      },
    };
  });

  const terminalMarker = "__NEMOCLAW_CONNECTION_READY__";
  const terminalCommand = `printf '${terminalMarker}\\n'`;
  const terminalPath = "/ws/terminal?cmd=" + encodeURIComponent(terminalCommand);
  const directTerminalRoute = openclawWebSocketUrl(
    rawUrl,
    terminalPath,
    "",
    { enabled: false, base: "" },
    provider,
  );
  const relayTerminalRoute = connection.accessSession
    ? openclawWebSocketUrl(
        rawUrl,
        terminalPath,
        connection.accessSession,
        getOpenClawProxyConfig(),
        provider,
      )
    : null;
  await execute({
    id: "terminal-websocket",
    title: "Terminal WebSocket",
    what: "Opens an operator PTY on the launchable host for terminal commands and OpenShell access.",
    purpose: "Confirms /ws/terminal opens an authenticated PTY and returns a harmless marker.",
    request: {
      method: "WEBSOCKET",
      authSummary: accessCredentialDelivery(provider, Boolean(relayTerminalRoute), accessSession) +
        " The terminal route uses launchable access only; it does not receive the gateway token.",
      attempts: [
        {
          url: directTerminalRoute.displayUrl,
          transport: "direct browser",
          authSummary: accessCredentialDelivery(provider, false, accessSession),
        },
        ...(relayTerminalRoute ? [{
          url: relayTerminalRoute.displayUrl,
          transport: "hosted relay fallback",
          authSummary: accessCredentialDelivery(provider, true, accessSession),
        }] : []),
      ],
      upstreamUrl: rawUrl + terminalPath,
      command: terminalCommand,
    },
  }, async () => {
    const response = await terminal(terminalCommand, {
      idleMs: 1500,
      totalMs: 20000,
      openMs: 12000,
      baseUrl: rawUrl,
      signal,
      relayWebSocket: null,
    });
    const ok = String(response.output || "").includes(terminalMarker);
    if (ok && response.transport === "approved-provider-relay-terminal") {
      setOpenClawWsRelayEnabled(true);
    }
    return {
      ok,
      error: ok ? "" : "Terminal opened but did not return the connection marker.",
      response: redactOpenClawDiagnostic({
        frames: response.frames,
        exitCode: response.exitCode,
        output: response.output,
      }),
    };
  });

  connection = getOpenClawConnection();
  const healthDiagnostic = openClawHttpDiagnostic("/healthz", connection);
  await execute({
    id: "health",
    title: "Health",
    what: "Reports whether the launchable HTTP service is alive after authenticated routes are established.",
    purpose: "Confirms the authenticated launchable health route after metadata and both WebSocket paths work.",
    request: healthDiagnostic.request,
  }, async () => {
    const response = await openclawBootstrapRequest("/healthz", { signal });
    return {
      ok: Boolean(response.ok),
      error: response.ok ? "" : `GET /healthz returned ${response.status} ${response.statusText}.`,
      response: redactOpenClawDiagnostic({
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
        body: response.json ?? response.body,
      }),
    };
  });

  const ok = results.every(step => step.ok);
  updateClawPill(document.getElementById("claw-status"));
  window.dispatchEvent(new Event("nemoclaw:prerequisites"));
  return {
    ok,
    provider,
    baseUrl: rawUrl,
    checks: results,
  };
}

// Local launches connect directly to /cli/gateway; same-origin Brev course pages do too.
// Static-hosted cross-origin connections use the OpenClaw CORS worker to carry JWT auth.
export function mountClawGateway(targetSel, opts = {}) {
  const target = typeof targetSel === "string" ? document.querySelector(targetSel) : targetSel;
  if (!target) return;

  const label      = opts.label      || "OpenClaw Gateway";
  const intro      = opts.intro      !== undefined ? opts.intro : "";
  const actions    = opts.actions    || [];
  const sessionKey = opts.sessionKey || "agent:main:main";
  const autoConnect = !!opts.autoConnect;

  // Credentials from the shared OpenClaw connection registry.
  function _creds() {
    const connection = getOpenClawConnection();
    return {
      rawUrl: connection.rawUrl,
      token: connection.token,
      accessProvider: connection.accessProvider,
      accessSession: connection.accessSession,
    };
  }

  // ── WS state ────────────────────────────────────────────────────────────────
  let _ws      = null;
  let _pending = {};    // id → {resolve, reject, timeout}
  let _chatCb  = null;  // called with each agent/chat event during a chat.send

  function _send(obj) {
    if (_ws && _ws.readyState === WebSocket.OPEN) _ws.send(JSON.stringify(obj));
  }

  function _call(method, params) {
    return new Promise((resolve, reject) => {
      const id = _uniqueId();
      const tmo = setTimeout(() => {
        delete _pending[id];
        reject(new Error(`${method} timed out`));
      }, 20000);
      _pending[id] = { resolve, reject, tmo };
      _send({ type: "req", id, method, params: params || {} });
    });
  }

  function _connectWs(wsUrl, token) {
    return new Promise((resolve, reject) => {
      if (_ws) { try { _ws.close(); } catch (_) {} }
      _ws = new WebSocket(wsUrl);
      let _connId = null;

      _ws.onopen = () => {};

      _ws.onmessage = ev => {
        let d;
        try { d = JSON.parse(ev.data); } catch (_) { return; }
        const evt = d.event || "";
        const mid = d.id    || "";
        const typ = d.type  || "";

        if (evt === "connect.challenge") {
          _connId = _uniqueId();
          // Resolve the outer promise on connect response
          _pending[_connId] = {
            resolve: r => {
              clearTimeout(_pending[_connId]?.tmo);
              delete _pending[_connId];
              const scopes  = r?.payload?.auth?.scopes  || [];
              const version = r?.payload?.server?.version || "?";
              resolve({ scopes, version });
              // auto-subscribe to the default session
              _call("sessions.messages.subscribe", { key: sessionKey }).catch(() => {});
            },
            reject: e => {
              clearTimeout(_pending[_connId]?.tmo);
              delete _pending[_connId];
              reject(e);
            },
            tmo: setTimeout(() => reject(new Error("connect timeout")), 15000),
          };
          _ws.send(JSON.stringify({
            type: "req", id: _connId, method: "connect",
            params: {
              minProtocol: 4, maxProtocol: 4,
              client: { id: "openclaw-control-ui", version: "0.1.0", platform: "browser", mode: "webchat" },
              caps: ["tool-events"], role: "operator",
              scopes: ["operator.read", "operator.write", "operator.admin"],
              auth: { token },
            },
          }));
          return;
        }

        // Resolve pending calls
        if (typ === "res" && mid && _pending[mid]) {
          const p = _pending[mid];
          clearTimeout(p.tmo);
          delete _pending[mid];
          if (d.ok) p.resolve(d); else p.reject(new Error(d.error?.message || "gateway error"));
          return;
        }

        // Route agent/chat events to active chat handler
        if (typ === "event" && _chatCb && (evt === "chat" || evt === "agent")) {
          _chatCb(d);
        }
      };

      _ws.onerror = () => reject(new Error("WebSocket error. Check that the URL is correct and the launchable is running."));
      _ws.onclose = () => {
        _setStatus("disconnected");
        _setActions(false);
        Object.values(_pending).forEach(p => { clearTimeout(p.tmo); p.reject(new Error("connection closed")); });
        _pending = {};
      };
    });
  }

  // ── DOM ─────────────────────────────────────────────────────────────────────
  target.innerHTML = `
<div class="claw-probe gw-panel">
  ${intro ? `<div class="gw-intro">${intro}</div>` : ""}
  <div class="claw-label">${label}</div>
  <div class="gw-head">
    <span class="gw-status gw-disc">● disconnected</span>
    <button type="button" class="claw-btn alt gw-connect-btn">Connect</button>
  </div>
  <div class="gw-actions" hidden>
    ${actions.map((a, i) =>
      `<button type="button" class="claw-btn${a.primary ? "" : " alt"} gw-act" data-i="${i}">${a.label}</button>`
    ).join("")}
  </div>
  <div class="gw-out" hidden></div>
</div>`;

  const statusEl  = target.querySelector(".gw-status");
  const connectBtn = target.querySelector(".gw-connect-btn");
  const actionsEl  = target.querySelector(".gw-actions");
  const outEl      = target.querySelector(".gw-out");

  function _setStatus(state, detail) {
    const map = {
      connecting:   ["● connecting…",   "gw-conn"],
      connected:    ["● connected",     "gw-live"],
      disconnected: ["● disconnected",  "gw-disc"],
      error:        ["● error",         "gw-err"],
    };
    const [txt, cls] = map[state] || map.disconnected;
    statusEl.textContent = detail ? `${txt} · ${detail}` : txt;
    statusEl.className   = `gw-status ${cls}`;
  }

  function _setActions(en) {
    actionsEl.hidden = !en;
  }

  function _showOut(html) {
    outEl.hidden  = false;
    outEl.innerHTML = html;
  }

  function _showPre(text) {
    _showOut(`<pre class="gw-pre">${text.replace(/</g,"&lt;")}</pre>`);
  }

  // ── Connect ──────────────────────────────────────────────────────────────────
  connectBtn.addEventListener("click", async () => {
    let { rawUrl, token, accessProvider, accessSession } = _creds();
    if (!rawUrl) {
      _showOut(`<span class="gw-err-txt">No launchable URL yet. Fill in the OpenClaw probe above first.</span>`);
      return;
    }
    connectBtn.disabled = true;
    outEl.hidden = true;
    try {
      const refreshed = await refreshOpenClawGatewayToken();
      ({ rawUrl, accessProvider, accessSession } = _creds());
      token = refreshed.token;
      const gateway = openclawGatewayWsUrl(rawUrl, accessSession, null, null, accessProvider);
      const wsUrl = gateway.url;
      _setStatus("connecting", gateway.viaProxy ? "via hosted relay" : "direct");
      const { scopes, version } = await _connectWs(wsUrl, token);
      _setStatus("connected", `v${version} · ${scopes.length} scopes`);
      _setActions(true);
      connectBtn.textContent = "Reconnect";
    } catch (e) {
      _setStatus("error", e.message.slice(0, 80));
      _showOut(`<span class="gw-err-txt">${e.message}</span>`);
    }
    connectBtn.disabled = false;
  });

  // ── Action buttons ────────────────────────────────────────────────────────
  actionsEl.querySelectorAll(".gw-act").forEach(btn => {
    const action = actions[parseInt(btn.dataset.i)];
    if (!action) return;

    btn.addEventListener("click", async () => {
      btn.disabled = true;
      outEl.hidden = true;

      try {
        if (action.chat) {
          // Streaming chat
          const ikey = _uniqueId();
          let fullText = "";
          outEl.hidden  = false;
          outEl.innerHTML = `<div class="gw-chat-out"></div>`;
          const chatDiv = outEl.querySelector(".gw-chat-out");

          await new Promise((resolve, reject) => {
            let endGrace, safety, finished = false;
            const finish = () => { if (finished) return; finished = true; clearTimeout(endGrace); clearTimeout(safety); _chatCb = null; resolve(); };
            _chatCb = d => {
              const evt = d.event || "";
              const pl  = d.payload || {};
              if (evt === "chat" && pl.state === "delta") {
                fullText = openclawMessageText(pl.message) || filterOpenClawRuntimeNoise(fullText + (pl.deltaText || ""));
                chatDiv.textContent = fullText;
              } else if (evt === "agent" && pl.stream === "lifecycle" && pl.data?.phase === "end") {
                clearTimeout(endGrace); endGrace = setTimeout(finish, 1500);
              } else if (evt === "chat" && pl.state === "final") {
                fullText = openclawMessageText(pl.message) || fullText;
                chatDiv.textContent = fullText;
                finish();
              }
            };
            const msg = typeof action.message === "function" ? action.message() : (action.message || "Hello");
            _call("chat.send", { sessionKey, idempotencyKey: ikey, message: msg })
              .catch(e => { finished = true; clearTimeout(endGrace); clearTimeout(safety); _chatCb = null; reject(e); });
            // Safety timeout
            safety = setTimeout(finish, 60000);
          });
        } else {
          // Standard method call
          const params = typeof action.params === "function" ? action.params() : (action.params || {});
          const res = await _call(action.method, params);
          // Pretty-print selected payload shapes
          const pl = res.payload;
          if (action.format === "models" && pl?.models) {
            _showOut(`<table class="gw-table"><thead><tr><th>id</th><th>provider</th><th>ctx</th></tr></thead><tbody>${
              pl.models.map(m => `<tr><td>${m.id}</td><td>${m.provider}</td><td>${m.contextWindow||""}</td></tr>`).join("")
            }</tbody></table>`);
          } else if (action.format === "crons" && pl) {
            const jobs = pl.jobs || [];
            if (!jobs.length) {
              _showOut(`<span class="gw-muted">No cron jobs installed.</span>`);
            } else {
              _showOut(`<table class="gw-table"><thead><tr><th>id</th><th>schedule</th><th>prompt</th></tr></thead><tbody>${
                jobs.map(j => `<tr><td>${j.id}</td><td>${j.schedule}</td><td>${(j.prompt||"").slice(0,60)}</td></tr>`).join("")
              }</tbody></table>`);
            }
          } else {
            _showPre(JSON.stringify(pl, null, 2));
          }
        }
      } catch (e) {
        _showOut(`<span class="gw-err-txt">✗ ${e.message}</span>`);
      }
      btn.disabled = false;
    });
  });

  if (autoConnect) connectBtn.click();

  return { call: _call };
}

// ── Endpoint probe widget ─────────────────────────────────────────────────────
// OpenClaw probes own launchable state. Model probes are read-only mirrors of the
// model registry configured by mountKeyPanel; they never read or write OpenClaw keys.
export function mountEndpointProbe(targetSel, opts = {}) {
  const target = typeof targetSel === "string" ? document.querySelector(targetSel) : targetSel;
  if (!target) return;

  const connectionKind = opts.connectionKind || "isolated";
  if (!["isolated", "model", "openclaw"].includes(connectionKind)) {
    throw new Error(`Unknown endpoint probe kind: ${connectionKind}`);
  }
  const isOpenClaw = connectionKind === "openclaw";
  const openClawConnection = isOpenClaw
    ? getOpenClawConnection()
    : { rawUrl: "", effectiveUrl: "", token: "", accessProvider: "auto", accessSession: "" };
  const suppliedDefault = opts.defaultUrl !== undefined ? opts.defaultUrl : (isOpenClaw ? "/lab/openclaw" : "");
  const defaultUrl = _normalizeBaseUrl(openClawConnection.rawUrl || suppliedDefault);
  // Respect an explicit empty model key: a custom public endpoint may not require one.
  // A bare `|| default` would replace that deliberate choice with the OpenClaw token.
  const defaultToken = (opts.defaultToken !== undefined) ? opts.defaultToken : "dli-openclaw-token";
  // The placeholder follows the default, so a no-bearer probe shows "(none needed)".
  // That beats showing the misleading openclaw token in a field that takes none.
  // Callers can override with opts.tokenPlaceholder.
  const tokenPlaceholder = (opts.tokenPlaceholder !== undefined)
    ? opts.tokenPlaceholder
    : (defaultToken || "(none needed in your launchable)");
  const actions      = opts.actions || [];
  const label        = opts.label || "Live OpenClaw probe";
  const intro        = opts.intro !== undefined ? opts.intro : "Paste the base URL of a running OpenClaw service, choose its access provider, and provide the matching browser session when the course is hosted separately.";
  const helpHint     = opts.helpHint || "Need a value? Select the ? beside that field for its source and fallback.";

  function _normalizeBaseUrl(raw) {
    if (isOpenClaw) return normalizeOpenClawLaunchableUrl(raw);
    const text = String(raw || "").trim();
    return text.replace(/\/+$/, "");
  }

  // Only an OpenClaw probe owns launchable persistence. Model settings remain owned by
  // _shared.js + _keypanel.js and arrive here through explicit defaults.
  const savedUrl = isOpenClaw ? _normalizeBaseUrl(openClawConnection.rawUrl || defaultUrl) : defaultUrl;
  const savedToken = isOpenClaw
    ? (openClawConnection.token || defaultToken)
    : defaultToken;
  const savedAccessProvider = isOpenClaw && opts.cfAccess
    ? openClawConnection.accessProvider
    : "auto";
  const savedAccessSession = isOpenClaw && opts.cfAccess
    ? openClawConnection.accessSession
    : "";
  // Relay routing is provider-owned. Keep these controls available only to the explicit
  // boundary fixture that proves legacy overrides are rejected.
  const proxyControls = isOpenClaw && opts.cfAccess && opts.proxyControls === true;
  const savedProxy = isOpenClaw ? getOpenClawProxyConfig() : { enabled: false, base: "" };
  const wsRelayControls = isOpenClaw && opts.cfAccess && opts.wsRelayControls === true;
  const savedWsRelayEnabled = wsRelayControls && getOpenClawWsRelayEnabled();
  const wsRelayLabel = localizeCourseUiText("Gateway recovery");
  const wsRelayText = localizeCourseUiText("Retry Cloudflare WebSockets through the hosted relay");
  const wsRelayAvailableHint = localizeCourseUiText(
    "Use only when a direct Cloudflare gateway or terminal socket fails.");
  const wsRelayUnavailableHint = localizeCourseUiText(
    "The recovery relay applies only to Cloudflare Access launchables.");

  // Label helper. A key with fieldHelp content renders a toggle button.
  // A key without it renders a plain label. Both match the .claw-lf sizing exactly.
  const _lbl = (key, text) => opts.fieldHelp?.[key]
    ? `<button type="button" class="claw-lf claw-help-trigger" data-field="${key}" aria-expanded="false">${text}<span class="claw-help-mark" aria-hidden="true">?</span></button>`
    : `<label class="claw-lf">${text}</label>`;
  // Help panel rendered immediately after its row (hidden by default).
  const _hlp = (key) => {
    const h = opts.fieldHelp?.[key];
    return h ? `<div class="claw-help-panel" data-field="${key}" hidden role="region">${h}</div>` : "";
  };

  target.innerHTML = `
    <div class="claw-probe" data-connection-kind="${connectionKind}" data-state="ready">
      <div class="claw-head">
        <div class="claw-label">${escHtml(label)}</div>
        ${intro ? `<div class="claw-intro">${escHtml(intro)}</div>` : ""}
        ${opts.fieldHelp ? `<div class="claw-help-hint">${escHtml(helpHint)}</div>` : ""}
      </div>
      <div class="claw-row">
        ${_lbl("url", "Base URL")}
        <input class="claw-input claw-url" type="text" spellcheck="false" autocapitalize="off"
               placeholder="https://nemoclaw-&lt;id&gt;.apps.run.brev.nvidia.com" value="${_escAttr(savedUrl)}"
               ${opts.readOnly ? 'readonly aria-readonly="true"' : ""}/>
      </div>
      ${_hlp("url")}
      <div class="claw-row">
        ${_lbl("token", "Bearer token")}
        <input class="claw-input claw-token" type="password" spellcheck="false" autocapitalize="off"
               placeholder="${_escAttr(tokenPlaceholder)}" value="${_escAttr(savedToken)}"
               ${opts.readOnly ? 'readonly aria-readonly="true"' : ""}/>
        <button type="button" class="claw-btn alt claw-eye" title="Show token" aria-label="Show or hide token">👁</button>
      </div>
      ${_hlp("token")}
      ${opts.cfAccess ? `
      <div class="claw-row">
        ${_lbl("accessProvider", "Access provider")}
        <select class="claw-input claw-access-provider">
          <option value="auto" ${savedAccessProvider === "auto" ? "selected" : ""}>Automatic from URL</option>
          <option value="cloudflare" ${savedAccessProvider === "cloudflare" ? "selected" : ""}>Cloudflare Access</option>
          <option value="pomerium" ${savedAccessProvider === "pomerium" ? "selected" : ""}>Pomerium</option>
        </select>
      </div>
      ${_hlp("accessProvider")}
      <div class="claw-row claw-access-session-row">
        ${_lbl("accessSession", "Access session")}
        <input class="claw-input claw-access-session" type="password" spellcheck="false" autocapitalize="off"
               value="${_escAttr(savedAccessSession)}"/>
        <button type="button" class="claw-btn alt claw-eye claw-eye-session" title="Show session" aria-label="Show or hide access session">👁</button>
      </div>
      ${_hlp("accessSession")}` : ""}
      ${wsRelayControls ? `
      <div class="claw-row claw-ws-relay-row">
        ${_lbl("wsRelay", escHtml(wsRelayLabel))}
        <label class="claw-proxy-toggle"><input class="claw-ws-relay-enabled" type="checkbox" ${savedWsRelayEnabled ? "checked" : ""}/>
          ${escHtml(wsRelayText)}</label>
      </div>
      ${_hlp("wsRelay")}` : ""}
      ${proxyControls ? `
      <div class="claw-row claw-proxy-row">
        ${_lbl("proxy", "Hosted relay")}
        <label class="claw-proxy-toggle"><input class="claw-proxy-enabled" type="checkbox" ${savedProxy.enabled ? "checked" : ""}/>
          Use for cross-origin Cloudflare connections</label>
      </div>
      ${_hlp("proxy")}
      <div class="claw-row claw-proxy-base-row">
        ${_lbl("proxyBase", "Relay URL")}
        <input class="claw-input claw-proxy-base" type="url" spellcheck="false" autocapitalize="off"
               value="${_escAttr(savedProxy.base)}" ${savedProxy.enabled ? "" : "disabled"}/>
      </div>
      ${_hlp("proxyBase")}` : ""}
      <div class="claw-actions"></div>
      <pre class="claw-out" aria-live="polite"></pre>
    </div>
  `;

  // Inject the widget CSS once (idempotent, keyed off the marker class).
  if (!document.head.querySelector('style[data-claw-probe="1"]')) {
    const s = document.createElement("style");
    s.dataset.clawProbe = "1";
    s.textContent = `
      .claw-probe{border:1px solid var(--bd,#2a2a2a);border-radius:8px;background:var(--e1,#161616);padding:14px 16px;margin:1em 0}
      .claw-head{margin-bottom:.8em}
      .claw-label{font-weight:700;font-size:.95rem;color:var(--gs,#aee23a);margin-bottom:.2em}
      .claw-intro{font-size:.86rem;color:var(--td,#b0b0b0);line-height:1.5}
      .claw-help-hint{font-size:.8rem;color:var(--td,#b0b0b0);line-height:1.45;margin-top:.35em}
      .claw-row{display:flex;align-items:center;gap:8px;margin:.4em 0}
      .claw-lf{font-family:var(--mono,monospace);font-size:.75rem;color:var(--tf,#8a8a8a);width:96px;flex:0 0 96px;text-transform:uppercase;letter-spacing:.04em}
      .claw-input{flex:1;background:var(--e2,#1e1e1e);border:1px solid var(--bd,#2a2a2a);border-radius:5px;padding:7px 10px;color:var(--tx,#f2f2f2);font-family:var(--mono,monospace);font-size:.82rem;min-width:0}
      .claw-input:focus{outline:none;border-color:var(--g,#76b900)}
      .claw-input[readonly]{opacity:.82;cursor:default}
      .claw-actions{display:flex;flex-wrap:wrap;gap:6px;margin:.7em 0 .5em}
      .claw-btn{background:var(--g,#76b900);color:#000;border:0;border-radius:5px;padding:6px 14px;font-size:.82rem;font-weight:700;cursor:pointer;font-family:inherit}
      :root[data-theme="light"] .claw-btn{color:#fff}
      .claw-btn:hover{background:var(--gs,#aee23a)}
      .claw-btn:disabled{opacity:.5;cursor:wait}
      .claw-btn.alt{background:var(--e2,#1e1e1e);color:var(--gs,#aee23a);border:1px solid var(--bd,#2a2a2a)}
      :root[data-theme="light"] .claw-btn.alt{color:var(--g,#3f6900)}
      .claw-btn.alt:hover{border-color:var(--g,#76b900)}
      .claw-eye{flex:0 0 auto;padding:5px 9px;font-size:.88rem;line-height:1}
      .claw-help-trigger{background:none;border:none;padding:0;cursor:pointer;text-align:left;width:96px;flex:0 0 96px;font-family:var(--mono,monospace);font-size:.75rem;color:var(--tf,#8a8a8a);text-transform:uppercase;letter-spacing:.04em;line-height:inherit}
      .claw-help-trigger:hover,.claw-help-trigger[aria-expanded="true"]{color:var(--gs,#aee23a);text-decoration-style:solid}
      .claw-help-mark{display:inline-grid;place-items:center;width:1.25em;height:1.25em;margin-left:.45em;border:1px solid currentColor;border-radius:50%;font-weight:800;line-height:1}
      .claw-help-panel{padding:8px 12px 8px 104px;font-size:.82rem;line-height:1.65;color:var(--td,#b0b0b0);border-left:2px solid var(--bd,#2a2a2a);margin:.1em 0 .5em}
      .claw-help-panel p{margin:.3em 0}.claw-help-panel p:first-child{margin-top:0}.claw-help-panel p:last-child{margin-bottom:0}
      .claw-help-panel code{font-size:.88em;background:var(--e2,#0d0d0d);padding:1px 5px;border-radius:3px;color:var(--gs,#aee23a)}
      .claw-help-panel strong{color:var(--tx,#f2f2f2)}
      .claw-help-panel a{color:var(--gs,#aee23a)}
      .claw-proxy-toggle{display:flex;align-items:center;gap:8px;font-size:.82rem;color:var(--td,#b0b0b0)}
      .claw-proxy-toggle input{accent-color:var(--g,#76b900)}
      .claw-out{background:var(--e2,#0d0d0d);border:1px solid var(--bd,#2a2a2a);border-radius:5px;padding:10px 12px;font-family:var(--mono,monospace);font-size:.78rem;line-height:1.5;color:var(--tx,#f2f2f2);min-height:60px;max-height:340px;overflow:auto;white-space:pre-wrap;word-break:break-word;margin:0}
      .claw-out.ok{border-color:var(--gd,#4a7a00)}
      .claw-out.err{border-color:var(--err,#a04040);color:var(--err,#ffb0b0)}
      .claw-html-frame{width:100%;height:340px;border:1px solid var(--bd,#2a2a2a);border-radius:5px;margin-top:.5em;background:#fff;display:block}
      .claw-html-frame[hidden]{display:none}
    `;
    document.head.appendChild(s);
  }

  const urlInp   = target.querySelector(".claw-url");
  const tokenInp = target.querySelector(".claw-token");
  const eyeBtn   = target.querySelector(".claw-eye");
  if (eyeBtn) {
    eyeBtn.addEventListener("click", () => {
      const showing = tokenInp.type !== "password";
      tokenInp.type = showing ? "password" : "text";
      eyeBtn.title  = showing ? "Show token" : "Hide token";
    });
  }
  // Wire help-panel toggles for any field that has a help entry.
  target.querySelectorAll(".claw-help-trigger").forEach(btn => {
    const panel = target.querySelector(`.claw-help-panel[data-field="${btn.dataset.field}"]`);
    if (!panel) return;
    btn.addEventListener("click", () => {
      const opening = panel.hidden;
      panel.hidden  = !opening;
      btn.setAttribute("aria-expanded", String(opening));
    });
  });

  const accessProviderInp = opts.cfAccess ? target.querySelector(".claw-access-provider") : null;
  const accessSessionInp = opts.cfAccess ? target.querySelector(".claw-access-session") : null;
  const accessSessionRow = opts.cfAccess ? target.querySelector(".claw-access-session-row") : null;
  const eyeSessionBtn = opts.cfAccess ? target.querySelector(".claw-eye-session") : null;
  const proxyEnabledInp = proxyControls ? target.querySelector(".claw-proxy-enabled") : null;
  const proxyBaseInp = proxyControls ? target.querySelector(".claw-proxy-base") : null;
  const wsRelayEnabledInp = wsRelayControls ? target.querySelector(".claw-ws-relay-enabled") : null;
  if (eyeSessionBtn && accessSessionInp) {
    eyeSessionBtn.addEventListener("click", () => {
      const showing = accessSessionInp.type !== "password";
      accessSessionInp.type  = showing ? "password" : "text";
      eyeSessionBtn.title = showing ? "Show session" : "Hide session";
    });
  }
  let browserSessionProbe = 0;
  let browserSessionTimer = null;
  function _setAccessSessionState(provider, state) {
    if (!accessSessionInp) return;
    const detected = provider === "pomerium" && state === "detected";
    accessSessionInp.disabled = detected;
    if (eyeSessionBtn) eyeSessionBtn.disabled = detected;
    if (accessSessionRow) {
      accessSessionRow.dataset.browserCookie = detected ? "1" : "0";
      accessSessionRow.dataset.sessionState = state;
    }
    accessSessionInp.placeholder = provider === "pomerium"
      ? detected
        ? "signed-in browser session detected; nothing to paste"
        : state === "checking"
          ? "checking for a signed-in browser session…"
          : "paste the _pomerium cookie value"
      : provider === "cloudflare"
        ? "paste the CF_Authorization cookie value"
        : "choose a provider or enter a launchable URL";
  }
  function _scheduleBrowserSessionDetection(provider) {
    browserSessionProbe += 1;
    clearTimeout(browserSessionTimer);
    if (provider !== "pomerium" || !accessSessionInp || accessSessionInp.value.trim()) return;
    const rawUrl = _normalizeBaseUrl(urlInp.value);
    if (!rawUrl) return;
    const probe = browserSessionProbe;
    _setAccessSessionState(provider, "checking");
    browserSessionTimer = setTimeout(async () => {
      const detected = await detectOpenClawBrowserSession(rawUrl, provider);
      if (probe !== browserSessionProbe ||
          _normalizeBaseUrl(urlInp.value) !== rawUrl ||
          accessSessionInp.value.trim()) return;
      _setAccessSessionState(provider, detected ? "detected" : "manual");
      if (detected) {
        _saveOpenClawConnection(
          rawUrl,
          tokenInp.value.trim(),
          accessProviderInp?.value,
          "",
        );
      }
    }, 250);
  }
  function _refreshAccessSessionPlaceholder() {
    if (!accessSessionInp) return;
    let provider = "auto";
    try {
      provider = accessProviderForOpenClawUrl(urlInp.value, accessProviderInp?.value || "auto");
      accessProviderInp?.setCustomValidity("");
    } catch (e) {
      const message = localizeCourseUiText(e.message);
      accessProviderInp?.setCustomValidity(message);
      return;
    }
    _setAccessSessionState(provider, "manual");
    _scheduleBrowserSessionDetection(provider);
    if (wsRelayEnabledInp) {
      wsRelayEnabledInp.disabled = provider !== "cloudflare";
      if (provider !== "cloudflare" && wsRelayEnabledInp.checked) {
        wsRelayEnabledInp.checked = false;
        setOpenClawWsRelayEnabled(false);
      }
      wsRelayEnabledInp.title = provider === "cloudflare"
        ? wsRelayAvailableHint
        : wsRelayUnavailableHint;
    }
  }
  if (accessSessionInp) {
    accessSessionInp.addEventListener("input", () => {
      browserSessionProbe += 1;
      clearTimeout(browserSessionTimer);
      let provider = "auto";
      try {
        provider = accessProviderForOpenClawUrl(urlInp.value, accessProviderInp?.value || "auto");
      } catch (_) {}
      _setAccessSessionState(provider, "manual");
      _saveOpenClawConnection(urlInp.value.trim(), tokenInp.value.trim(), accessProviderInp?.value, accessSessionInp.value.trim());
    });
  }
  if (accessProviderInp) {
    accessProviderInp.addEventListener("change", () => {
      _refreshAccessSessionPlaceholder();
      _saveOpenClawConnection(urlInp.value.trim(), tokenInp.value.trim(), accessProviderInp.value, accessSessionInp?.value.trim());
    });
  }
  window.addEventListener("focus", () => {
    if (!accessSessionInp?.value.trim()) _refreshAccessSessionPlaceholder();
  });
  const outEl    = target.querySelector(".claw-out");
  const actBox   = target.querySelector(".claw-actions");
  const probeEl  = target.querySelector(".claw-probe");

  function _proxyConfig() {
    if (!proxyControls) return getOpenClawProxyConfig();
    const base = normalizeOpenClawProxyBase(proxyBaseInp?.value || DEFAULT_OPENCLAW_PROXY_BASE);
    return { enabled: !!proxyEnabledInp?.checked, base };
  }

  function _saveOpenClawConnection(rawUrl, rawToken, accessProvider, accessSession) {
    if (!isOpenClaw) return;
    try {
      setOpenClawConnection({
        rawUrl,
        token: rawToken,
        accessProvider: opts.cfAccess ? accessProvider : undefined,
        accessSession: opts.cfAccess ? accessSession : undefined,
      });
      accessProviderInp?.setCustomValidity("");
    } catch (e) {
      accessProviderInp?.setCustomValidity(localizeCourseUiText(e.message));
      return;
    }
    if (!opts.syncCanvas) return;
    updateClawPill(document.getElementById("claw-status"));
    window.dispatchEvent(new Event("nemoclaw:prerequisites"));
  }

  urlInp.addEventListener("input", () => {
    const raw = _normalizeBaseUrl(urlInp.value);
    if (urlInp.value.trim() !== raw) urlInp.value = raw;
    const previous = getOpenClawConnection().rawUrl;
    if (previous && raw && raw !== previous) {
      // Access and gateway credentials belong to one launchable. Never carry
      // them silently to another origin when the learner replaces the URL.
      tokenInp.value = "";
      if (accessSessionInp) accessSessionInp.value = "";
      if (accessProviderInp) accessProviderInp.value = "auto";
    }
    _refreshAccessSessionPlaceholder();
    _saveOpenClawConnection(raw, tokenInp.value.trim(), accessProviderInp?.value, accessSessionInp?.value.trim());
  });
  tokenInp.addEventListener("input", () => {
    const tok = tokenInp.value.trim();
    _saveOpenClawConnection(_normalizeBaseUrl(urlInp.value), tok, accessProviderInp?.value, accessSessionInp?.value.trim());
  });
  if (proxyEnabledInp && proxyBaseInp) {
    const saveProxy = () => {
      try {
        const config = setOpenClawProxyConfig({
          enabled: proxyEnabledInp.checked,
          base: proxyBaseInp.value,
        });
        proxyBaseInp.value = config.base;
        proxyBaseInp.disabled = !config.enabled;
        proxyBaseInp.setCustomValidity("");
        _saveOpenClawConnection(_normalizeBaseUrl(urlInp.value), tokenInp.value.trim(), accessProviderInp?.value, accessSessionInp?.value.trim());
      } catch (e) {
        proxyBaseInp.setCustomValidity(e.message);
        proxyBaseInp.reportValidity();
      }
    };
    proxyEnabledInp.addEventListener("change", saveProxy);
    proxyBaseInp.addEventListener("change", saveProxy);
  }
  if (wsRelayEnabledInp) {
    wsRelayEnabledInp.addEventListener("change", () => {
      setOpenClawWsRelayEnabled(wsRelayEnabledInp.checked);
    });
  }
  // Initialise canvas keys on page load with whatever is already stored.
  _refreshAccessSessionPlaceholder();
  _saveOpenClawConnection(savedUrl, savedToken, savedAccessProvider, savedAccessSession);

  function hideHtmlFrame(clear = false) {
    const fr = target.querySelector(".claw-html-frame");
    if (!fr) return;
    fr.hidden = true;
    if (clear) fr.removeAttribute("srcdoc");
  }

  function setOutput(text, kind = "", state = "") {
    probeEl.dataset.state = state || (kind === "ok" ? "succeeded" : kind === "err" ? "failed" : "running");
    if (!String(text || "").includes("HTML ·")) hideHtmlFrame(true);
    outEl.classList.remove("ok", "err");
    if (kind) outEl.classList.add(kind);
    // Highlight the response with the course hljs theme when it looks like JSON.
    // Errors and non-JSON stay plain text, so a stack trace or status line reads as written.
    const t = (text || "").trim();
    const looksJson = kind !== "err" && (t.startsWith("{") || t.startsWith("["));
    if (looksJson && window.hljs) {
      try {
        outEl.innerHTML = "";
        const code = document.createElement("code");
        code.className = "language-json hljs";
        code.textContent = text;
        outEl.appendChild(code);
        window.hljs.highlightElement(code);
        return;
      } catch (_) { /* fall through to plain text */ }
    }
    outEl.textContent = text;
  }

  // Used by runAction. Keep the normalized launchable origin and API path separate. Brev launchable
  // normalization intentionally drops UI paths; combining them here would turn
  // /healthz or /api/agent into a request for the OpenClaw Control page at /.
  function _fetchUrl(baseUrl, pathAndQuery, accessProvider = "auto", accessSession = "") {
    const displayUrl = baseUrl.replace(/\/+$/, "") + (pathAndQuery.startsWith("/") ? pathAndQuery : "/" + pathAndQuery);
    if (!isOpenClaw) {
      return { url: displayUrl, displayUrl, viaProxy: false, directUrl: displayUrl, directDisplayUrl: displayUrl };
    }
    return openclawHttpUrl(
      baseUrl,
      pathAndQuery,
      _proxyConfig(),
      accessProvider,
      accessSession,
    );
  }

  async function runAction(action) {
    const base = _normalizeBaseUrl(urlInp.value);
    if (urlInp.value.trim() !== base) urlInp.value = base;
    if (!base) { setOutput("Set a base URL above first.", "err", "blocked"); return; }
    const token = (tokenInp.value || "").trim();
    const actionPath = action.path || "/";
    const method = action.method || "GET";
    let body = null;
    if (typeof action.body === "function") {
      try { body = action.body(); }
      catch (e) { setOutput("body() threw: " + (e?.message || e), "err"); return; }
    } else if (action.body) {
      body = action.body;
    }
    let accessProvider;
    try { accessProvider = accessProviderForOpenClawUrl(base, accessProviderInp?.value || "auto"); }
    catch (e) { setOutput(localizeCourseUiText(e.message), "err"); return; }
    const accessSession = accessSessionInp ? accessSessionInp.value.trim() : "";
    const displayUrl = base + (actionPath.startsWith("/") ? actionPath : "/" + actionPath);
    const route = _fetchUrl(base, actionPath, accessProvider, accessSession);
    const fetchTarget = route.url;
    const headers = { "Accept": "application/json, text/html, */*" };
    // /api/agent discovers this token. Do not let a token retained from a
    // different launchable prevent discovery of its replacement.
    const discoversToken = !!opts.autofillToken && actionPath === "/api/agent";
    if (token && !discoversToken) headers["Authorization"] = "Bearer " + token;
    if (route.viaProxy && accessSession) {
      if (accessProvider === "auto") {
        setOutput("Choose Cloudflare Access or Pomerium for this launchable.", "err", "blocked");
        return;
      }
      if (accessProvider === "cloudflare") {
        // Cloudflare's relay contract accepts this assertion header.
        headers["CF-Access-Jwt-Assertion"] = accessSession;
      } else {
        headers["X-OpenClaw-Access-Provider"] = accessProvider;
        headers["X-OpenClaw-Access-Session"] = accessSession;
      }
    }
    if (body)  headers["Content-Type"]            = "application/json";

    const showUrl = route.viaProxy ? displayUrl + "  (via hosted relay)" : displayUrl + "  (direct)";
    setOutput(`→ ${method} ${showUrl}\n   …in flight`);
    // Hide any previous HTML frame while a new request is in flight.
    hideHtmlFrame(true);
    const t0 = performance.now();
    try {
      const useLoopback = isOpenClaw && accessProvider === "pomerium" &&
        method === "GET" &&
        !body && (actionPath === "/healthz" || actionPath === "/api/agent");
      const loopback = useLoopback
        ? await openclawLoopbackProbe(actionPath, { baseUrl: base })
        : null;
      const r = loopback
        ? new Response(loopback.body, {
            status: loopback.status,
            statusText: loopback.statusText,
            headers: { "Content-Type": loopback.json === null ? "text/plain" : "application/json" },
          })
        : await fetch(fetchTarget, {
            method,
            headers,
            body: body ? JSON.stringify(body) : null,
            // A direct cross-origin launchable request relies on the browser's
            // HttpOnly access cookie. Relay requests carry the opaque session in
            // headers instead and must not forward unrelated browser cookies.
            credentials: action.credentials || opts.credentials || (route.viaProxy ? "same-origin" : "include"),
          });
      const dt = Math.round(performance.now() - t0);
      const ct = r.headers.get("content-type") || "";
      const head = `← ${r.status} ${r.statusText}   ${dt}ms` +
        (loopback
          ? "   (launchable terminal loopback; direct first, hosted relay fallback)"
          : route.viaProxy
            ? "   (via hosted relay)"
            : "   (direct)");

      if (ct.includes("text/html")) {
        const html = await r.text();
        // Access sign-in HTML looks like a successful API response. Detect both
        // supported providers and point back to the selected session cookie.
        if (/cloudflareaccess\.com|Sign in ・ Cloudflare Access|Cloudflare Access|auth\.apps\.run\.brev\.nvidia\.com|pomerium/i.test(html)) {
          const cookieName = accessCookieName(accessProvider);
          const recovery = accessProvider === "pomerium"
            ? "Open the launchable in this browser and sign in, then probe again. If this separately hosted course cannot detect that browser session, paste the complete _pomerium value into Access session."
            : "Open the launchable, sign in, then use DevTools → Application → Storage → Cookies. " +
              "Copy the full " + cookieName + " value into Access session above and probe again.";
          setOutput(head + "\n\nThe launchable needs a fresh " + cookieName + " browser session.\n\n" + recovery, "err");
          hideHtmlFrame(true);
          return;
        }
        if (action.expectJson) {
          setOutput(head + "\n\n" + (opts.unexpectedHtmlHint ||
            "Expected JSON but received an HTML page. Confirm that the request kept its API path and that the launchable relay is current."), "err");
          hideHtmlFrame(true);
          return;
        }
        setOutput(head + `   (HTML · ${html.length} bytes)`, r.ok ? "ok" : "err");
        // Render in a sandboxed iframe below the output bar.
        let fr = target.querySelector(".claw-html-frame");
        if (!fr) {
          fr = document.createElement("iframe");
          fr.className = "claw-html-frame";
          fr.setAttribute("sandbox", "allow-same-origin allow-popups");
          target.querySelector(".claw-probe").appendChild(fr);
        }
        fr.srcdoc = html;
        fr.hidden = false;
      } else {
        let j = null, printed;
        if (ct.includes("application/json")) {
          j = await r.json();
          if (action.filterModels && j && Array.isArray(j.data)) {
            const f = action.filterModels;
            const test = typeof f === "function" ? f
              : Array.isArray(f) ? (id) => f.some(s => String(id).includes(s))
              : (id) => String(id).includes(String(f));
            const before = j.data.length;
            j = { ...j, data: j.data.filter(m => test(m.id ?? m)) };
            j._filtered = `showing ${j.data.length} of ${before}`;
          }
          printed = JSON.stringify(j, null, 2);
          // Auto-fill the bearer token from agent.dashboardUrl in the /api/agent response.
          // Cloudflare metadata uses its tab-scoped relay session. Pomerium metadata
          // uses launchable loopback over the direct-first terminal transport.
          if (opts.autofillToken && r.ok && j) {
            try {
              const found = opts.autofillToken(j);
              if (found && found !== tokenInp.value.trim()) {
                tokenInp.value = found;
                _saveOpenClawConnection(_normalizeBaseUrl(urlInp.value), found, accessProviderInp?.value, accessSessionInp?.value.trim());
                printed += "\n\n↳ bearer token auto-filled from this response (" + found.slice(0, 8) + "…). Ready for the gateway steps below.";
              }
            } catch (_) { /* response shape didn't match; leave the field as-is */ }
          }
        } else {
          printed = await r.text();
        }
        if (!r.ok && r.status === 401 && accessProvider === "pomerium") {
          printed += "\n\nPomerium did not accept the access session. Reopen the current launchable and sign in. If automatic detection remains unavailable here, paste a fresh _pomerium value into Access session.";
        }
        setOutput(head + "\n\n" + printed, r.ok ? "ok" : "err");
      }
    } catch (e) {
      const dt = Math.round(performance.now() - t0);
      if (!isOpenClaw) {
        const hint = opts.failureHint || "Check the saved model route, its bearer key, and the served model ID.";
        setOutput(`✗ network error after ${dt}ms\n   ${String(e?.message || e)}\n\n${hint}`, "err");
        return;
      }
      const fallback = /EPERM|Failed to fetch|NetworkError|Load failed|ECONN|ERR_CONNECTION|timed out|502|503/i.test(e?.message || "")
        ? "\nBackup: if local OpenClaw failed to start or logs EPERM, enter a Brev launchable URL and sign in to it in this browser. Cloudflare metadata also needs the matching relay session field.\n"
        : "";
      const hint = "Possible causes:\n" +
        "• OpenClaw did not start cleanly. Local EPERM means use a Brev launchable.\n" +
        "• CORS blocked, because a header is not in the Access-Control-Allow-Headers preflight response.\n" +
        "• Wrong URL, so confirm no trailing /v1 on the base URL.\n" +
        "• Service offline. If the launchable just started, wait 30 s and try again.\n" +
        "• 502 on /v1/chat/completions, so the model backend isn't responding; check that\n" +
        "  NVIDIA_API_KEY resolved correctly in the launchable environment.\n\n" +
        "Gateway token: once the URL and launchable sign-in check out, GET /api/agent above fills it in from agent.dashboardUrl.";
      setOutput(`✗ network error after ${dt}ms\n   ${String(e?.message || e)}\n\n${fallback}${hint}`, "err");
    }
  }

  actions.forEach(action => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "claw-btn" + (action.kind === "alt" ? " alt" : "");
    b.textContent = action.label;
    b.addEventListener("click", async () => {
      b.disabled = true;
      try { await runAction(action); }
      finally { b.disabled = false; }
    });
    actBox.appendChild(b);
  });

  return {
    getUrl:   () => _normalizeBaseUrl(urlInp.value),
    getToken: () => tokenInp.value.trim(),
    getWsRelayEnabled: () => getOpenClawWsRelayEnabled(),
    run:      runAction,
  };
}

export function mountClawProbe(targetSel, opts = {}) {
  return mountEndpointProbe(targetSel, { ...opts, connectionKind: "openclaw" });
}

export function mountOpenClawConnectionAudit(targetSel, opts = {}) {
  const target = typeof targetSel === "string" ? document.querySelector(targetSel) : targetSel;
  if (!target) return null;
  const saved = getOpenClawConnection();
  const text = value => localizeCourseUiText(value);
  const steps = [
    ["agent-metadata", "Agent metadata", "/api/agent"],
    ["gateway-websocket", "Gateway WebSocket", "/cli/gateway"],
    ["terminal-websocket", "Terminal WebSocket", "/ws/terminal"],
    ["health", "Health", "/healthz"],
  ];

  target.innerHTML = `
    <div class="claw-probe claw-connection-audit" data-state="ready">
      <div class="claw-head">
        <div class="claw-label">${escHtml(text(opts.label || "Connect NemoClaw"))}</div>
        <div class="claw-intro">${escHtml(text(opts.intro || "Enter the launchable URL and its browser access session. The course discovers everything else."))}</div>
      </div>
      <div class="claw-row">
        <label class="claw-lf" for="claw-audit-url">${escHtml(text("Base URL"))}</label>
        <input id="claw-audit-url" class="claw-input claw-url" type="url" spellcheck="false" autocapitalize="off"
          placeholder="https://nemoclaw-&lt;id&gt;.apps.run.brev.nvidia.com" value="${_escAttr(saved.rawUrl)}"/>
      </div>
      <div class="claw-row">
        <label class="claw-lf" for="claw-audit-session">${escHtml(text("Access session"))}</label>
        <input id="claw-audit-session" class="claw-input claw-access-session" type="password" spellcheck="false"
          autocapitalize="off" value="${_escAttr(saved.accessSession)}"/>
        <button type="button" class="claw-btn alt claw-eye-session" title="${escHtml(text("Show session"))}"
          aria-label="${escHtml(text("Show or hide access session"))}">👁</button>
      </div>
      <div class="claw-audit-derived" aria-live="polite"></div>
      <div class="claw-actions">
        <button type="button" class="claw-btn claw-audit-run">${escHtml(text("Test connection"))}</button>
      </div>
      <div class="claw-audit-summary" aria-live="polite">${escHtml(text("Waiting to test."))}</div>
      <ol class="claw-audit-list">
        ${steps.map(([id, title, path]) => `
          <li class="claw-audit-step" data-step="${id}" data-status="pending">
            <div class="claw-audit-step-head">
              <span><strong>${escHtml(text(title))}</strong> <code>${escHtml(path)}</code></span>
              <span class="claw-audit-status">${escHtml(text("Pending"))}</span>
            </div>
            <div class="claw-audit-explain"></div>
            <details class="claw-audit-raw" hidden>
              <summary>${escHtml(text("Redacted request and response"))}</summary>
              <pre><code class="language-json"></code></pre>
            </details>
          </li>`).join("")}
      </ol>
    </div>
  `;

  if (!document.head.querySelector('style[data-openclaw-connection-audit="1"]')) {
    const style = document.createElement("style");
    style.dataset.openclawConnectionAudit = "1";
    style.textContent = `
      .claw-connection-audit{border:1px solid var(--bd,#2a2a2a);border-radius:8px;background:var(--e1,#161616);padding:14px 16px;margin:1em 0}
      .claw-connection-audit .claw-head{margin-bottom:.8em}.claw-connection-audit .claw-label{font-weight:700;color:var(--gs,#aee23a)}
      .claw-connection-audit .claw-intro,.claw-audit-derived,.claw-audit-summary{color:var(--td,#b0b0b0);font-size:.84rem;line-height:1.5}
      .claw-connection-audit .claw-row{display:flex;align-items:center;gap:8px;margin:.5em 0}
      .claw-connection-audit .claw-lf{width:104px;flex:0 0 104px;font:700 .74rem var(--mono,monospace);color:var(--tf,#8a8a8a);text-transform:uppercase;letter-spacing:.04em}
      .claw-connection-audit .claw-input{flex:1;min-width:0;background:var(--e2,#1e1e1e);border:1px solid var(--bd,#2a2a2a);border-radius:5px;padding:8px 10px;color:var(--tx,#f2f2f2);font-family:var(--mono,monospace)}
      .claw-connection-audit .claw-input:focus{outline:none;border-color:var(--g,#76b900)}
      .claw-connection-audit .claw-actions{margin:.75em 0 .55em}.claw-connection-audit .claw-btn{background:var(--g,#76b900);color:#000;border:0;border-radius:5px;padding:7px 14px;font-weight:700;cursor:pointer}
      :root[data-theme="light"] .claw-connection-audit .claw-btn{color:#fff}.claw-connection-audit .claw-btn:disabled{opacity:.55;cursor:wait}
      .claw-connection-audit .claw-btn.alt{background:var(--e2,#1e1e1e);color:var(--gs,#aee23a);border:1px solid var(--bd,#2a2a2a);padding:6px 9px}
      :root[data-theme="light"] .claw-connection-audit .claw-btn.alt{color:var(--gd,#2f5500)}
      .claw-audit-summary[data-status="passed"]{color:var(--gs,#aee23a)}.claw-audit-summary[data-status="failed"]{color:var(--err,#ff8f8f)}
      .claw-audit-list{list-style:none;padding:0;margin:.8em 0 0;display:grid;gap:8px;counter-reset:claw-audit}
      .claw-audit-step{counter-increment:claw-audit;border:1px solid var(--bd,#2a2a2a);border-radius:6px;padding:9px 11px;background:var(--e2,#111)}
      .claw-audit-step-head{display:flex;justify-content:space-between;gap:12px;align-items:baseline}.claw-audit-step-head>span:first-child:before{content:counter(claw-audit) ". ";color:var(--tf,#8a8a8a)}
      .claw-audit-step code{color:var(--gs,#aee23a)}.claw-audit-status{font:700 .72rem var(--mono,monospace);text-transform:uppercase;color:var(--tf,#8a8a8a)}
      .claw-audit-step[data-status="running"]{border-color:var(--g,#76b900)}.claw-audit-step[data-status="passed"] .claw-audit-status{color:var(--gs,#aee23a)}
      .claw-audit-step[data-status="failed"]{border-color:var(--err,#a04040)}.claw-audit-step[data-status="failed"] .claw-audit-status{color:var(--err,#ff8f8f)}
      .claw-audit-explain{display:grid;gap:3px;margin-top:6px;color:var(--td,#b0b0b0);font-size:.79rem;line-height:1.45;overflow-wrap:anywhere}
      .claw-audit-explain b{color:var(--tx,#f2f2f2)}.claw-audit-raw{margin-top:7px}.claw-audit-raw summary{cursor:pointer;color:var(--gs,#aee23a);font-size:.78rem}
      .claw-audit-raw pre{max-height:320px;overflow:auto;margin:.45em 0 0;padding:9px;border-radius:5px;background:var(--bg,#0d0d0d);white-space:pre-wrap;word-break:break-word}
      @media(max-width:620px){.claw-connection-audit .claw-row{align-items:stretch;flex-wrap:wrap}.claw-connection-audit .claw-lf{width:100%;flex-basis:100%}.claw-audit-step-head{align-items:flex-start;flex-direction:column;gap:3px}}
    `;
    document.head.appendChild(style);
  }

  const root = target.querySelector(".claw-connection-audit");
  const urlInput = target.querySelector(".claw-url");
  const sessionInput = target.querySelector(".claw-access-session");
  const eye = target.querySelector(".claw-eye-session");
  const runButton = target.querySelector(".claw-audit-run");
  const derived = target.querySelector(".claw-audit-derived");
  const summary = target.querySelector(".claw-audit-summary");
  let controller = null;
  let detectionVersion = 0;

  function setDerived() {
    const rawUrl = normalizeOpenClawLaunchableUrl(urlInput.value);
    if (!rawUrl) {
      derived.textContent = text("Provider and transport are discovered from the Base URL.");
      sessionInput.placeholder = text("Paste the launchable browser session when this page is hosted separately");
      return;
    }
    try {
      const provider = accessProviderForOpenClawUrl(rawUrl);
      const cookie = accessCookieName(provider);
      derived.textContent = `${text("Detected automatically from Base URL:")} ${provider}. ` +
        `${text("Access session:")} ${cookie}. ${text("Sensitive values stay in this tab.")}`;
      sessionInput.placeholder = provider === "pomerium"
        ? text("Paste _pomerium when this page is hosted separately")
        : text("Paste CF_Authorization when this page is hosted separately");
      urlInput.setCustomValidity("");
    } catch (error) {
      urlInput.setCustomValidity(localizeCourseUiText(error.message));
      derived.textContent = localizeCourseUiText(error.message);
    }
  }

  function saveInputs({ clearToken = false } = {}) {
    const rawUrl = normalizeOpenClawLaunchableUrl(urlInput.value);
    if (!rawUrl) return null;
    const previous = getOpenClawConnection();
    const provider = accessProviderForOpenClawUrl(rawUrl);
    return setOpenClawConnection({
      rawUrl,
      token: clearToken || previous.rawUrl !== rawUrl ? "" : previous.token,
      accessProvider: provider,
      accessSession: sessionInput.value.trim(),
    });
  }

  function resetSteps() {
    target.querySelectorAll(".claw-audit-step").forEach(step => {
      step.dataset.status = "pending";
      step.querySelector(".claw-audit-status").textContent = text("Pending");
      step.querySelector(".claw-audit-explain").textContent = "";
      const raw = step.querySelector(".claw-audit-raw");
      raw.hidden = true;
      raw.querySelector("code").textContent = "";
    });
  }

  function renderStep(step) {
    const item = target.querySelector(`.claw-audit-step[data-step="${step.id}"]`);
    if (!item) return;
    item.dataset.status = step.status;
    const status = step.status === "running"
      ? text("Testing")
      : step.status === "passed"
        ? text("Passed")
        : text("Failed");
    item.querySelector(".claw-audit-status").textContent = step.elapsedMs == null
      ? status
      : `${status} · ${step.elapsedMs} ms`;
    const request = step.request || {};
    const explain = item.querySelector(".claw-audit-explain");
    explain.innerHTML = "";
    const lines = [
      [text("Query"), request.url || request.upstreamUrl || ""],
      [text("What"), step.what || ""],
      [text("Why"), step.purpose || ""],
      [text("Credential"), request.authSummary || ""],
    ];
    if (step.error) lines.push([text("Failure"), step.error]);
    for (const [label, value] of lines) {
      if (!value) continue;
      const row = document.createElement("div");
      const strong = document.createElement("b");
      strong.textContent = label + ": ";
      row.append(strong, document.createTextNode(String(value)));
      explain.appendChild(row);
    }
    const raw = item.querySelector(".claw-audit-raw");
    const code = raw.querySelector("code");
    code.textContent = JSON.stringify(redactOpenClawDiagnostic({
      request: step.request || null,
      response: step.response || null,
      error: step.error || null,
    }), null, 2);
    raw.hidden = step.status === "running";
    if (!raw.hidden && window.hljs) {
      try { window.hljs.highlightElement(code); } catch (_) {}
    }
  }

  eye.addEventListener("click", () => {
    const showing = sessionInput.type !== "password";
    sessionInput.type = showing ? "password" : "text";
    eye.title = text(showing ? "Show session" : "Hide session");
  });
  urlInput.addEventListener("input", () => {
    detectionVersion += 1;
    setDerived();
    try { saveInputs(); } catch (_) {}
  });
  sessionInput.addEventListener("input", () => {
    detectionVersion += 1;
    try { saveInputs(); } catch (_) {}
  });
  urlInput.addEventListener("change", async () => {
    const version = ++detectionVersion;
    const rawUrl = normalizeOpenClawLaunchableUrl(urlInput.value);
    if (!rawUrl || sessionInput.value.trim()) return;
    let provider = "auto";
    try { provider = accessProviderForOpenClawUrl(rawUrl); } catch (_) { return; }
    if (provider !== "pomerium") return;
    derived.textContent = text("Checking this browser for a signed-in launchable session.");
    const detected = await detectOpenClawBrowserSession(rawUrl, provider);
    if (version !== detectionVersion || sessionInput.value.trim()) return;
    setDerived();
    if (detected) derived.textContent += " " + text("Signed-in browser session detected.");
  });

  runButton.addEventListener("click", async () => {
    controller?.abort();
    controller = new AbortController();
    resetSteps();
    root.dataset.state = "running";
    summary.dataset.status = "running";
    summary.textContent = text("Testing required routes in order.");
    runButton.disabled = true;
    try {
      const connection = saveInputs({ clearToken: true });
      if (!connection) throw new Error(text("Enter the NemoClaw launchable Base URL."));
      const result = await runOpenClawConnectionAudit({
        baseUrl: connection.rawUrl,
        accessSession: connection.accessSession,
        signal: controller.signal,
        onStep: renderStep,
      });
      root.dataset.state = result.ok ? "succeeded" : "failed";
      summary.dataset.status = result.ok ? "passed" : "failed";
      summary.textContent = result.ok
        ? text("Connection ready. Metadata, gateway, terminal, and health checks passed.")
        : text("Connection failed. Open the failed check for its redacted request and response.");
      runButton.textContent = text("Test again");
    } catch (error) {
      root.dataset.state = "failed";
      summary.dataset.status = "failed";
      summary.textContent = String(error?.message || error);
    } finally {
      runButton.disabled = false;
    }
  });

  setDerived();
  return {
    run: () => runButton.click(),
    getUrl: () => normalizeOpenClawLaunchableUrl(urlInput.value),
    stop: () => controller?.abort(),
  };
}

export function mountModelEndpointProbe(targetSel, opts = {}) {
  return mountEndpointProbe(targetSel, {
    ...opts,
    connectionKind: "model",
    readOnly: true,
    tokenPlaceholder: opts.tokenPlaceholder || "nvapi-…",
  });
}


// ── Gateway plumbing, shared by 03a/03b/03c/04a ─────────────────────────────
// GW_CONNECT opens /cli/gateway, runs the handshake, and parks state.call/state._ws.
// mountGwRecover mounts the recover flow; both honour the canvas Stop button.

// openclawChat streams one chat turn to the live agent over /cli/gateway.
// It keeps one socket per tab and reads the URL + token the probe stored.
// The gateway-page artifacts use it as their mountChatUI respond.
let _ocSock = null;
export async function openclawChat(message, { session = "main", onToken, onTool, view, signal = null, idleMs = 90000, totalMs = 240000, finalGraceMs = 1500 } = {}) {
  /* @doc <code>helpers.openclawChat(message, {session, onToken, onTool, view})</code> :: Send one
       chat turn to the live OpenClaw agent over the <code>/cli/gateway</code>
       WebSocket and stream the reply. Reads the launchable URL + token from the OpenClaw probe
       (Kickstart page). Pass a <code>view</code> (a <code>mountChatUI</code>
       <code>ctx.view</code>) and it drives the whole observable trace for you: answer text, a
       stack-ordered chip per tool/command call (with its args and full result, errors marked),
       and the gateway-reported context-token budget. (Or pass
       <code>onToken(delta)</code>/<code>onTool(name,{id,args})</code> to handle events
       yourself.) The gateway streams no reasoning channel, so none is shown. Reuse the same
       <code>session</code> for multi-turn. The gateway companion to chat()/createReactAgent.
  */
  const refreshed = await refreshOpenClawGatewayToken({ signal });
  const connection = getOpenClawConnection();
  const rawUrl = connection.rawUrl.replace(/\/+$/, "");
  const token = refreshed.token;
  const accessProvider = connection.accessProvider;
  const accessSession = connection.accessSession;
  if (!rawUrl || !token) throw new Error("Connect first on the Kickstart page (3a): enter the launchable URL and, when requested, its access session.");
  const gateway = openclawGatewayWsUrl(rawUrl, accessSession, null, null, accessProvider);
  const wsUrl = gateway.url;

  async function connect() {
    return await new Promise((resolve, reject) => {
      const pend = {}, ws = new WebSocket(wsUrl);
      let chatCb = null;
      const call = (method, params) => new Promise((res, rej) => {
        const id = _uniqueId();
        const tmo = setTimeout(() => { delete pend[id]; rej(new Error(method + " timed out")); }, 20000);
        pend[id] = { res, rej, tmo };
        ws.send(JSON.stringify({ type: "req", id, method, params: params || {} }));
      });
      ws.onmessage = ev => { let d; try { d = JSON.parse(ev.data); } catch (_) { return; }
        if (d.type === "res" && d.id && pend[d.id]) { const p = pend[d.id]; clearTimeout(p.tmo); delete pend[d.id]; d.ok ? p.res(d.payload) : p.rej(new Error(d.error?.message || "gateway error")); }
        if (d.type === "event" && chatCb) chatCb(d);
      };
      ws.onerror = () => {};
      ws.onclose = () => { if (_ocSock && _ocSock.ws === ws) _ocSock = null; };
      const sock = { ws, call, setCb: cb => { chatCb = cb; }, subs: {} };
      const base = ws.onmessage;
      ws.onmessage = ev => { let d; try { d = JSON.parse(ev.data); } catch (_) { return; }
        if (d.event !== "connect.challenge") { base(ev); return; }
        ws.onmessage = base;
        call("connect", { minProtocol: 4, maxProtocol: 4, client: { id: "openclaw-control-ui", version: "0.1.0", platform: "browser", mode: "webchat" }, caps: ["tool-events"], role: "operator", scopes: ["operator.read", "operator.write", "operator.admin"], auth: { token } })
          .then(() => resolve(sock)).catch(reject);
      };
      setTimeout(() => reject(new Error("no challenge arrived within 15s. Open the launchable, then retry with a fresh matching access session in Module 3a.")), 15000);
    });
  }

  if (!_ocSock || _ocSock.ws.readyState !== 1) _ocSock = await connect();
  const sock = _ocSock;
  if (!sock.subs[session]) { await sock.call("sessions.messages.subscribe", { key: session }); sock.subs[session] = true; }
  // Pull readable text out of a gateway tool result / partial result, in full.
  const resText = openclawResultText;
  // One-line summary of a tool's args for the chip label (command, path, query…).
  const argSummary = (a) => { if (a == null) return ""; if (typeof a === "string") return a;
    const v = a.command || a.path || a.query || a.file || Object.values(a)[0]; return v == null ? "" : String(v); };
  return await new Promise((resolve, reject) => {
    let text = "", deliveredText = "", myRun = null, idle, glob, endGrace, toolStarts = 0, usedTok = 0, winTok = 0, lastModel = "", finished = false;
    const chips = {};   // toolCallId -> chip element (stack-ordered, never reused)
    const deliverFull = (full) => {
      full = filterOpenClawRuntimeNoise(full);
      if (!full) return;
      let delta = "";
      if (!deliveredText) delta = full;
      else if (full.startsWith(deliveredText)) delta = full.slice(deliveredText.length);
      if (delta) { if (view) view.token(delta); else if (onToken) onToken(delta); }
      if (full.length >= text.length) text = full;
      if (full.length >= deliveredText.length) deliveredText = full;
    };
    const done = (stalled) => { if (finished) return; finished = true; clearTimeout(idle); clearTimeout(glob); clearTimeout(endGrace); sock.setCb(null);
      if (stalled) sock.call("chat.abort", { sessionKey: session }).catch(() => {});
      if (!text.trim()) deliverFull(toolStarts > 0
        ? "The agent completed " + toolStarts + " tool call(s) but returned no final text. Retry once; if it repeats, run Health check on Kickstart."
        : "The gateway completed the turn without a displayable reply. Retry once; if it repeats, run Health check on Kickstart.");
      if (view && usedTok) view.usage({ context: usedTok, window: winTok || undefined, model: lastModel });
      resolve(text); };
    const bump = () => { clearTimeout(idle); idle = setTimeout(() => done(true), idleMs); };
    glob = setTimeout(() => done(true), totalMs);
    // Stop button: abort the agent run (chat.abort) and resolve with what we have.
    if (signal) { if (signal.aborted) return done(true); signal.addEventListener("abort", () => done(true), { once: true }); }

    sock.setCb(d => {
      const pl = d.payload || {};
      if (pl.isHeartbeat || d.event === "health" || d.event === "tick") return;
      if (myRun && pl.runId && pl.runId !== myRun) return;
      bump();
      // The gateway carries token accounting on its frames.
      // totalTokens is what is used; contextTokens is the agent's configured window.
      // Trust both, since this deployment may size the model unlike the build endpoint.
      if (pl.totalTokens) usedTok = pl.totalTokens;
      if (pl.contextTokens) winTok = pl.contextTokens;
      if (pl.model) lastModel = pl.model;
      if (d.event === "chat" && pl.state === "final") { deliverFull(openclawMessageText(pl.message)); done(false); return; }
      if (d.event !== "agent") return;
      const sk = pl.sessionKey || ""; if (sk !== session && !sk.endsWith(":" + session)) return;
      const data = pl.data || {}, stream = pl.stream || "";
      const id = data.toolCallId;
      if (stream === "assistant" || ("delta" in data && "text" in data)) {
        deliverFull(data.text || text);
      }
      else if (stream === "tool" && data.phase === "start") {
        toolStarts++; const name = data.name || "tool"; const sum = argSummary(data.args);
        if (view) chips[id] = view.tool(name + (sum ? " · " + sum : ""), "(running…)");
        else if (onTool) onTool(name, { id, args: data.args });
      }
      else if (stream === "tool" && data.phase === "update" && view && chips[id] && data.partialResult) {
        const b = chips[id].querySelector(".chatui-tool-body"); if (b) b.textContent = resText(data.partialResult);
      }
      else if (stream === "tool" && data.phase === "result" && view && chips[id]) {
        const c = chips[id], b = c.querySelector(".chatui-tool-body"); if (b) b.textContent = resText(data.result);
        if (data.isError) { c.classList.add("err"); const s = c.querySelector("summary"); if (s) s.textContent = s.textContent.replace("🔧", "✗"); }
      }
      else if (data.phase === "end" && !data.itemId) {
        clearTimeout(endGrace);
        endGrace = setTimeout(() => done(false), finalGraceMs);
      }
    });

    bump();
    sock.call("chat.send", { sessionKey: session, idempotencyKey: _uniqueId(), message })
      .then(res => { myRun = (res && res.runId) || null; })
      .catch(e => { clearTimeout(idle); clearTimeout(glob); sock.setCb(null); reject(e); });
  });
}

export const GW_CONNECT = `
const refreshedGateway = await helpers.refreshOpenClawGatewayToken({ signal: helpers.signal });
const connection = helpers.getOpenClawConnection();
const rawUrl = connection.rawUrl;
const token = refreshedGateway.token;
const accessProvider = connection.accessProvider;
const accessSession = connection.accessSession;
if (!rawUrl || !token) {
  helpers.log("Connect in Module 3a first. Enter the launchable URL and, when requested, its matching access session.");
  return;
}
const gateway = helpers.openclawGatewayWsUrl(rawUrl, accessSession, null, null, accessProvider);
const wsUrl = gateway.url;
helpers.log("→ " + gateway.displayUrl + (gateway.viaProxy ? "  (via hosted relay)" : ""));

// Keep one live gateway socket per flow.
if (state._ws) { try { state._ws.close(); } catch (_) {} state._chatCb = null; }

const _pend = {};
const nextId = () => {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
};
const _ws = new WebSocket(wsUrl);
state._ws = _ws;
// Stop closes the socket and rejects in-flight calls.
if (typeof helpers !== "undefined" && helpers.signal) helpers.signal.addEventListener("abort", () => {
  try { _ws.close(); } catch (_) {}
  for (const _id in _pend) { try { clearTimeout(_pend[_id].tmo); _pend[_id].reject(new Error("stopped")); } catch (_) {} delete _pend[_id]; }
}, { once: true });
_ws.onmessage = ev => {
  let d; try { d = JSON.parse(ev.data); } catch (_) { return; }
  if (d.type === "res" && d.id && _pend[d.id]) {
    const p = _pend[d.id]; clearTimeout(p.tmo); delete _pend[d.id];
    if (d.ok) p.resolve(d.payload); else p.reject(new Error(d.error?.message || "gateway error"));
  }
  if (d.type === "event" && state._chatCb) state._chatCb(d);
};
_ws.onerror = () => {};
state._chatCb = null;
state.call = (method, params) => new Promise((resolve, reject) => {
  const id  = nextId();
  const tmo = setTimeout(() => { delete _pend[id]; reject(new Error(method + " timed out")); }, 20000);
  _pend[id] = { resolve, reject, tmo };
  _ws.send(JSON.stringify({ type: "req", id, method, params: params || {} }));
});
await new Promise((resolve, reject) => {
  let challenged = false;
  let challengeTimer = null;
  const base = _ws.onmessage;
  const priorClose = _ws.onclose;
  _ws.onclose = event => {
    priorClose?.(event);
    if (!challenged) {
      clearTimeout(challengeTimer);
      reject(new Error("gateway socket closed before the challenge" + (event?.code ? " (code " + event.code + ")" : "")));
    }
  };
  _ws.onerror = () => {
    if (!challenged) {
      clearTimeout(challengeTimer);
      reject(new Error("gateway WebSocket failed before the challenge; verify the launchable access session and transport"));
    }
  };
  _ws.onmessage = ev => {
    let d; try { d = JSON.parse(ev.data); } catch (_) { return; }
    if (d.event !== "connect.challenge") { base(ev); return; }
    challenged = true;
    _ws.onmessage = base;
    state.call("connect", {
      minProtocol: 4, maxProtocol: 4,
      client: { id: "openclaw-control-ui", version: "0.1.0", platform: "browser", mode: "webchat" },
      caps: ["tool-events"], role: "operator",
      scopes: ["operator.read", "operator.write", "operator.admin"],
      auth: { token },
    }).then(pl => {
      clearTimeout(challengeTimer);
      helpers.log("● connected  v" + (pl?.server?.version || "?") + "  scopes: " + (pl?.auth?.scopes || []).join(", "));
      resolve(pl);
    }).catch(error => { clearTimeout(challengeTimer); reject(error); });
  };
  challengeTimer = setTimeout(() => reject(new Error("no challenge arrived within 30s. Open the launchable, then retry with a fresh matching access session in Module 3a.")), 30000);
});
`;

// Shared recover flow, reused across 03a/03c/04a.
export function mountGwRecover(sel) {
  mountCanvasFlow(sel, {
  label: "Detect & recover · health check, then escalating reset",
  intro: "Health check, conditional repair, and logs for the shared OpenClaw harness. Health check runs a command and reads toolSearch. Recover changes toolSearch only when it is enabled; session clearing and restart are separate opt-ins. Runtime logs tails the log when a run stalls.",
  edges: [
    { from: "gw-health", to: "gw-fix" },
  ],
  nodes: [
    {
      id: "gw-health", icon: "🩺", title: "Health check", x: 0, y: 0,
      summary: "Checks env status, toolSearch, stuck approvals, and one trivial command. HEALTHY needs no repair; DEGRADED shows what to inspect next.",
      code: GW_CONNECT + `
// ── tune these ──────────────────────────────────────────────────────────────
const PROBE_TIMEOUT_S = 60;                // how long to wait for the test command (this model can be slow)
const PROBE_MARKER    = "HEALTHCHECK_OK";  // the agent must echo this for a pass
// ──────────────────────────────────────────────────────────────────────────────
helpers.log("Checking the runtime");

// 1. Is the sandbox/environment even available?
try {
  const envs = await state.call("environments.list", {});
  (envs.environments || []).forEach(e => helpers.log("  env " + e.id + ": " + e.status));
} catch (e) { helpers.log("  environments.list failed: " + e.message); }

// 2. tools.toolSearch can trap weaker models in bridge-code loops; Recover turns it off.
let toolSearch = null;
try {
  const cfg = await state.call("config.get", {});
  toolSearch = !!(cfg.parsed && cfg.parsed.tools && cfg.parsed.tools.toolSearch);
  helpers.log("  tools.toolSearch: " + toolSearch + (toolSearch ? "  ← likely the cause; the Recover cell disables it" : ""));
} catch (e) { helpers.log("  config.get failed: " + e.message); }

// 3. A command stuck waiting on an approval looks exactly like a hang.
let pending = 0;
try {
  const appr = await state.call("exec.approval.list", {});
  pending = Array.isArray(appr) ? appr.length : 0;
  helpers.log("  pending exec approvals: " + pending);
} catch (e) { helpers.log("  exec.approval.list failed: " + e.message); }

// 3. Echo probe proves exec works; finish as soon as the marker returns.
const PROBE = nextId("quick-health-").slice(0, 21);
await state.call("sessions.messages.subscribe", { key: PROBE });
let ok = false, sawTool = false, runId = null;
const trace = [], t0 = performance.now();
const secs = () => ((performance.now() - t0) / 1000).toFixed(1) + "s";
helpers.log("  · probe: asked the agent to echo a marker with its exec tool…");
const outcome = await new Promise((resolve) => {
  const timer = setTimeout(() => resolve("timed out after " + PROBE_TIMEOUT_S + "s"), PROBE_TIMEOUT_S * 1000);
  if (helpers.signal) helpers.signal.addEventListener("abort", () => resolve("stopped"), { once: true });
  state._chatCb = d => {
    const pl = d.payload || {};
    if (pl.isHeartbeat || d.event === "health" || d.event === "tick") return;
    if (runId && pl.runId && pl.runId !== runId) return;
    if (d.event !== "agent") return;
    const data = pl.data || {};
    trace.push({ t: secs(), itemId: data.itemId, phase: data.phase, name: data.name, exitCode: data.exitCode, output: (data.output || "").slice(0, 80) });
    if ((data.itemId || "").startsWith("tool:") && data.phase === "start" && !sawTool) {
      sawTool = true; helpers.log("  · " + secs() + " agent called its " + (data.name || "exec") + " tool");
    }
    if ((data.itemId || "").startsWith("command:") && data.phase === "end") {
      helpers.log("  · " + secs() + " exec returned, exit " + data.exitCode);
      if (data.exitCode === 0 && (data.output || "").includes(PROBE_MARKER)) { ok = true; clearTimeout(timer); resolve("marker echoed"); }
    }
  };
  state.call("chat.send", { sessionKey: PROBE, idempotencyKey: "h" + Date.now(), message: "Run exactly this with your exec tool and report nothing else: echo " + PROBE_MARKER })
    .then(r => { runId = r && r.runId; }).catch(() => { clearTimeout(timer); resolve("chat.send failed"); });
});
state._chatCb = null;
state.call("chat.abort", { sessionKey: PROBE }).catch(() => {});
state.call("sessions.delete", { key: PROBE }).catch(() => {});   // don't leave the probe session behind

if (ok) {
  helpers.log("✓ HEALTHY in " + secs() + ". The agent called its exec tool and the command returned. Tool calls work.");
} else {
  helpers.log("✗ DEGRADED (" + outcome + ")" + (sawTool ? ", the agent fired a tool but no exec result came back" : ", the agent never called a tool") + (pending ? "; " + pending + " exec approval(s) stuck" : "") + (toolSearch ? "; tools.toolSearch is ON" : "") + ".");
  helpers.log("  → Run the 🛠 Recover cell next" + (toolSearch ? " (it turns off toolSearch, the usual cause)" : "") + ".");
}
helpers.log.details("probe trace · " + trace.length + " agent frames in " + secs(), trace);
return { healthy: ok, outcome, pendingApprovals: pending, toolSearch };
`,
    },
    {
      id: "gw-fix", icon: "🛠", title: "Recover", x: 1, y: 0,
      summary: "Disables tools.toolSearch only when the live config has it enabled. Session clearing and restart default off, so running this cell against a healthy launchable is non-destructive.",
      code: GW_CONNECT + `
helpers.log("Repairing the runtime");

// 1. Disable toolSearch only when the live config enables it.
const cfg = await state.call("config.get", {});
let configChanged = false;
if (cfg.parsed && cfg.parsed.tools && cfg.parsed.tools.toolSearch) {
  await state.call("config.patch", { raw: JSON.stringify({ tools: { toolSearch: false } }), baseHash: cfg.hash });
  configChanged = true;
  helpers.log("  ✓ disabled tools.toolSearch (the tool_search_code loop)");
} else {
  helpers.log("  ✓ tools.toolSearch already off; no config change needed");
}

// 2. Session deletion is independent from toolSearch repair. Opt in only when
// stale session state is part of the failure you are diagnosing.
const RESET_SESSIONS = false;
if (RESET_SESSIONS) {
  await state.call("sessions.reset", { key: "agent:main:main" }).catch(() => {});
  let offset = 0, all = [];
  for (;;) { const page = await state.call("sessions.list", { limit: 100, offset }); all = all.concat(page.sessions || []); if (!page.hasMore) break; offset = page.nextOffset; }
  let removed = 0;
  for (const s of all.filter(s => !/:main$/.test(s.key))) { try { await state.call("sessions.delete", { key: s.key }); removed++; } catch (e) {} }
  helpers.log("  ✓ reset agent:main:main and deleted " + removed + " throwaway session(s)");
} else {
  helpers.log("  · session cleanup skipped (set RESET_SESSIONS = true only when needed)");
}

// 3. Restart only when a config patch was made and you want to apply it now.
const DO_RESTART = false;
if (DO_RESTART && configChanged) {
  await state.call("gateway.restart.request", { reason: "course recovery: disable toolSearch" }).catch(e => helpers.log("  restart failed: " + e.message));
  helpers.log("  ⟳ restart requested. Wait ~40s, then re-run Connect and the 🩺 Health check.");
  helpers.log("  Still failing after that? The sandbox is wedged below the gateway, so relaunch the launchable from Brev.");
} else if (configChanged) {
  helpers.log("  config patched. To apply it now: set DO_RESTART = true above and re-run this cell (the runtime restarts in about 40s).");
} else {
  helpers.log("  no restart needed because the live toolSearch setting was already healthy.");
}
`,
    },
    {
      id: "gw-logs", icon: "📜", title: "Runtime logs", x: 2, y: 0,
      summary: "Tails the gateway/agent log (logs.tail): model calls, tool dispatches, errors, hangs. The deepest view when a run stalls and Health check is green; reasoning itself is not exposed over the gateway.",
      code: GW_CONNECT + `
// ── tune these ──────────────────────────────────────────────────────────────
const LOG_LINES = 40;          // how many recent log lines to show
// ──────────────────────────────────────────────────────────────────────────────
const lg = await state.call("logs.tail", { limit: LOG_LINES + 20 });
const lines = lg.lines || [];
helpers.log("runtime log · last " + lines.length + " line(s)" + (lg.file ? " · " + lg.file : ""));
lines.slice(-LOG_LINES).forEach(raw => {
  // Each line is a JSON STRING: { "0": "{subsystem…}", "1": <message>, …, _meta }.
  // Parse it, read the level + subsystem, and join the numeric arg keys (skip "0", the subsystem tag) into one message.
  let L; try { L = typeof raw === "string" ? JSON.parse(raw) : raw; } catch (_) { return; }
  const lvl = ((L._meta && L._meta.logLevelName) || "?").padEnd(5);
  let sub = ""; try { sub = JSON.parse(L["0"] || "{}").subsystem || ""; } catch (_) {}
  const msg = Object.keys(L).filter(k => /^[0-9]+$/.test(k) && k !== "0")
    .map(k => typeof L[k] === "string" ? L[k] : JSON.stringify(L[k]))
    .join(" ").replace(/\\n/g, " ").slice(0, 180);
  if (msg) helpers.log("  " + lvl + (sub ? " [" + sub + "]" : "") + " " + msg);
});
helpers.log.details("raw logs.tail response", lg);
return { lines: lines.length };
`,
    },
  ],
  });
}
