// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// OpenClaw gateway + claw widgets for 03a/03b/03c/04a.
// Holds the live WebSocket gateway client and the connect/probe widgets.
// Also openclawChat, GW_CONNECT, and the recover flow.

import { updateClawPill, escHtml, _escAttr, mountCanvasFlow } from "./_shared.js";
import {
  DEFAULT_OPENCLAW_PROXY_BASE, accessProviderForOpenClawUrl, getOpenClawConnection, getOpenClawProxyConfig, migrateOpenClawConnectionStorage,
  normalizeOpenClawLaunchableUrl, normalizeOpenClawProxyBase, openclawHttpUrl,
  openclawWebSocketUrl, setOpenClawConnection, setOpenClawProxyConfig,
} from "./_connection.js";
import { openclawLoopbackProbe } from "./_openshell.js";
import { filterOpenClawRuntimeNoise, filterOpenClawRuntimeValue, openclawMessageText, openclawResultText } from "./_runtime_text.js";

export {
  DEFAULT_OPENCLAW_PROXY_BASE, accessProviderForOpenClawUrl, getOpenClawConnection, getOpenClawProxyConfig, migrateOpenClawConnectionStorage,
  normalizeOpenClawLaunchableUrl, normalizeOpenClawProxyBase, openclawHttpUrl,
  openclawWebSocketUrl, setOpenClawConnection, setOpenClawProxyConfig,
};
export { filterOpenClawRuntimeNoise, filterOpenClawRuntimeValue, openclawMessageText, openclawResultText };

const accessCookieName = provider => provider === "pomerium" ? "_pomerium" : "CF_Authorization";
function _uniqueId(prefix = "") {
  if (typeof crypto.randomUUID === "function") return prefix + crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return prefix + [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
}

export function openclawGatewayWsUrl(rawUrl, accessSession = "", proxyBase = null, proxyEnabled = null, accessProvider = "auto") {
  const config = proxyBase === null
    ? getOpenClawProxyConfig()
    : { base: normalizeOpenClawProxyBase(proxyBase), enabled: proxyEnabled !== false };
  // Brev establishes its access cookie when the learner opens the launchable.
  // Connect WebSockets directly so that signed-in session authenticates the socket.
  // Keep the relay for HTTP bootstrap reads such as /api/agent.
  let provider = "auto";
  try { provider = accessProviderForOpenClawUrl(rawUrl, accessProvider); }
  catch (_) { /* openclawWebSocketUrl below returns the authoritative error */ }
  if (provider === "cloudflare" || provider === "pomerium") {
    return openclawWebSocketUrl(rawUrl, "/cli/gateway", "", { enabled: false, base: "" }, accessProvider);
  }
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
    if (connection.resolvedAccessProvider === "pomerium") {
      const probe = await openclawLoopbackProbe("/api/agent", { baseUrl: rawUrl, signal });
      metadataToken = gatewayTokenFromAgentMetadata(probe.json) || "";
    } else {
      const route = openclawHttpUrl(rawUrl, "/api/agent");
      const headers = { Accept: "application/json" };
      if (route.viaProxy && connection.accessSession) {
        headers["CF-Access-Jwt-Assertion"] = connection.accessSession;
      }
      const response = await fetch(route.url, {
        headers,
        credentials: route.viaProxy ? "same-origin" : "include",
        signal,
      });
      if (response.ok) metadataToken = gatewayTokenFromAgentMetadata(await response.json()) || "";
    }
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
  const proxyControls = isOpenClaw && opts.cfAccess && opts.proxyControls !== false;
  const savedProxy = isOpenClaw ? getOpenClawProxyConfig() : { enabled: false, base: "" };

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
               placeholder="https://your-tunnel.example.com" value="${_escAttr(savedUrl)}"
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
  if (eyeSessionBtn && accessSessionInp) {
    eyeSessionBtn.addEventListener("click", () => {
      const showing = accessSessionInp.type !== "password";
      accessSessionInp.type  = showing ? "password" : "text";
      eyeSessionBtn.title = showing ? "Show session" : "Hide session";
    });
  }
  function _refreshAccessSessionPlaceholder() {
    if (!accessSessionInp) return;
    let provider = "auto";
    try {
      provider = accessProviderForOpenClawUrl(urlInp.value, accessProviderInp?.value || "auto");
      accessProviderInp?.setCustomValidity("");
    } catch (e) {
      accessProviderInp?.setCustomValidity(e.message);
      accessSessionInp.placeholder = "provider does not match this launchable URL";
      return;
    }
    const pomerium = provider === "pomerium";
    if (pomerium) accessSessionInp.value = "";
    accessSessionInp.disabled = pomerium;
    if (eyeSessionBtn) eyeSessionBtn.disabled = pomerium;
    if (accessSessionRow) accessSessionRow.dataset.browserCookie = pomerium ? "1" : "0";
    accessSessionInp.placeholder = pomerium
      ? "uses the signed-in browser session; nothing to paste"
      : provider === "cloudflare"
        ? "paste the CF_Authorization cookie value"
        : "choose a provider or enter a launchable URL";
  }
  if (accessSessionInp) {
    accessSessionInp.addEventListener("input", () => {
      _saveOpenClawConnection(urlInp.value.trim(), tokenInp.value.trim(), accessProviderInp?.value, accessSessionInp.value.trim());
    });
  }
  if (accessProviderInp) {
    accessProviderInp.addEventListener("change", () => {
      _refreshAccessSessionPlaceholder();
      _saveOpenClawConnection(urlInp.value.trim(), tokenInp.value.trim(), accessProviderInp.value, accessSessionInp?.value.trim());
    });
  }
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
      accessProviderInp?.setCustomValidity(e.message);
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
  function _fetchUrl(baseUrl, pathAndQuery) {
    const displayUrl = baseUrl.replace(/\/+$/, "") + (pathAndQuery.startsWith("/") ? pathAndQuery : "/" + pathAndQuery);
    if (!isOpenClaw) {
      return { url: displayUrl, displayUrl, viaProxy: false, directUrl: displayUrl, directDisplayUrl: displayUrl };
    }
    return openclawHttpUrl(baseUrl, pathAndQuery, _proxyConfig());
  }

  async function runAction(action) {
    const base = _normalizeBaseUrl(urlInp.value);
    if (urlInp.value.trim() !== base) urlInp.value = base;
    if (!base) { setOutput("Set a base URL above first.", "err", "blocked"); return; }
    const token = (tokenInp.value || "").trim();
    const actionPath = action.path || "/";
    const displayUrl = base + (actionPath.startsWith("/") ? actionPath : "/" + actionPath);
    const route = _fetchUrl(base, actionPath);
    const fetchTarget = route.url;
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
    catch (e) { setOutput(e.message, "err"); return; }
    const accessSession = accessSessionInp ? accessSessionInp.value.trim() : "";
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
        // Explicit relay deployments may use the provider-neutral pair below;
        // the course keeps Pomerium direct and never enters this branch.
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
      const useLoopback = isOpenClaw && accessProvider === "pomerium" && method === "GET" &&
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
        (loopback ? "   (direct browser session → launchable loopback)" : "");

      if (ct.includes("text/html")) {
        const html = await r.text();
        // Access sign-in HTML looks like a successful API response. Detect both
        // supported providers and point back to the selected session cookie.
        if (/cloudflareaccess\.com|Sign in ・ Cloudflare Access|Cloudflare Access|auth\.apps\.run\.brev\.nvidia\.com|pomerium/i.test(html)) {
          const cookieName = accessCookieName(accessProvider);
          const recovery = accessProvider === "pomerium"
            ? "Open the launchable in this browser and sign in, then probe again. The HttpOnly Pomerium session stays in the browser and is never pasted into the course."
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
          // Cloudflare uses its tab-scoped relay session; Pomerium uses the authenticated
          // direct terminal socket.
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
          printed += "\n\nPomerium did not accept the browser session. Open the current launchable in this browser, sign in, and try again. Do not copy the _pomerium cookie into the course.";
        }
        setOutput(head + "\n\n" + printed, r.ok ? "ok" : "err");
      }
    } catch (e) {
      const dt = Math.round(performance.now() - t0);
      if (!isOpenClaw) {
        const hint = opts.failureHint || "Check the saved model route, bearer key, served model ID, and public HTTPS tunnel.";
        setOutput(`✗ network error after ${dt}ms\n   ${String(e?.message || e)}\n\n${hint}`, "err");
        return;
      }
      const fallback = /EPERM|Failed to fetch|NetworkError|Load failed|ECONN|ERR_CONNECTION|timed out|502|503/i.test(e?.message || "")
        ? "\nBackup: if local OpenClaw failed to start or logs EPERM, enter a Brev launchable URL. For Pomerium, open that launchable and sign in in this browser. Cloudflare launchables still use the relay session field.\n"
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
    run:      runAction,
  };
}

export function mountClawProbe(targetSel, opts = {}) {
  return mountEndpointProbe(targetSel, { ...opts, connectionKind: "openclaw" });
}

export function mountModelEndpointProbe(targetSel, opts = {}) {
  return mountEndpointProbe(targetSel, {
    ...opts,
    connectionKind: "model",
    readOnly: true,
    tokenPlaceholder: opts.tokenPlaceholder || "nvapi-… or EMPTY",
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
  if (!rawUrl || !token) throw new Error("Connect first on the Kickstart page (3a): set your launchable URL + token in the probe.");
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
      setTimeout(() => reject(new Error("no challenge arrived within 15s. For a Brev URL, open the launchable, select its access provider, and paste a fresh matching browser session in Module 3a.")), 15000);
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
  helpers.log("Fill in the OpenClaw probe above first. For a Brev launchable, select its access provider and paste the matching browser session.");
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
  challengeTimer = setTimeout(() => reject(new Error("no challenge arrived within 30s. For a Brev URL, open the launchable, select its access provider, and refresh its session in Module 3a.")), 30000);
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
