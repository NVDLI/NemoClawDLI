// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Shared launchable routing. Every OpenClaw HTTP/WebSocket consumer uses this module.

export const DEFAULT_OPENCLAW_PROXY_BASE = "https://openclaw-cors-proxy.experiments.courses.nvidia.com";
export const OPENCLAW_PROXY_BASE_KEY = "nemoclaw_openclaw_proxy_base_v1";
export const OPENCLAW_PROXY_ENABLED_KEY = "nemoclaw_openclaw_proxy_enabled_v1";
export const OPENCLAW_WS_RELAY_ENABLED_KEY = "nemoclaw_openclaw_ws_relay_enabled_v1";
export const OPENCLAW_URL_KEY = "nemoclaw_clawurl";
export const OPENCLAW_RAW_URL_KEY = "nemoclaw_clawrawurl";
export const OPENCLAW_TOKEN_KEY = "nemoclaw_clawtoken";
export const OPENCLAW_ACCESS_JWT_KEY = "nemoclaw_clawcfjwt";
export const OPENCLAW_ACCESS_PROVIDER_KEY = "nemoclaw_openclaw_access_provider_v1";
export const OPENCLAW_ACCESS_SESSION_KEY = "nemoclaw_openclaw_access_session_v1";
export const OPENCLAW_DEVICE_AUTH_KEY = "nemoclaw_gateway_device_v1";
let deviceGeneration = 0;
export const getOpenClawDeviceGeneration = () => deviceGeneration;
function clearDeviceAuth(secrets) {
  deviceGeneration++;
  secrets?.removeItem(OPENCLAW_DEVICE_AUTH_KEY);
}
const OPENCLAW_CREDENTIAL_ORIGIN_KEY = "nemoclaw_openclaw_credential_origin_v1";
const OPENCLAW_TERMINAL_GATEWAY_KEY = "nemoclaw_openclaw_terminal_gateway_v1";

function storage() {
  try { return globalThis.localStorage || null; }
  catch (_) { return null; }
}

// Gateway and access credentials are tab-scoped. The launchable URL and routing may persist,
// but another course page on the shared CDN must not inherit credentials from a prior session.
function secretStorage() {
  try { return globalThis.sessionStorage || null; }
  catch (_) { return null; }
}

function credentialOrigin(rawUrl) {
  try { return rawUrl ? new URL(rawUrl, pageBase()).origin : ""; }
  catch (_) { return ""; }
}

function boundSecretStorage(rawUrl) {
  const secrets = secretStorage();
  // Routing persists across tabs; credentials never follow another tab's host change.
  // Older credentials have no provable origin and must be entered again.
  if (secrets?.getItem(OPENCLAW_CREDENTIAL_ORIGIN_KEY) !== credentialOrigin(rawUrl)) {
    if (secrets?.getItem(OPENCLAW_DEVICE_AUTH_KEY)) clearDeviceAuth(secrets);
    for (const key of [OPENCLAW_TOKEN_KEY, OPENCLAW_ACCESS_SESSION_KEY,
      OPENCLAW_ACCESS_JWT_KEY, OPENCLAW_CREDENTIAL_ORIGIN_KEY, OPENCLAW_DEVICE_AUTH_KEY,
      OPENCLAW_TERMINAL_GATEWAY_KEY]) secrets?.removeItem(key);
  }
  return secrets;
}

function browserLocation() {
  try { return globalThis.location || null; }
  catch (_) { return null; }
}

function isPersonalWorkerHost(hostname) {
  return /(?:^|\.)workers\.dev$/i.test(String(hostname || ""));
}

function isBrevLaunchableFamily(hostname) {
  const host = String(hostname || "").toLowerCase();
  return host.endsWith(".brevlab.com") || host.endsWith(".apps.run.brev.nvidia.com") || host.endsWith(".gobrev.dev");
}

// Supported account-specific launchables share the NemoClaw prefix. Authentication
// stays bound to the host family, including Brev's Skybridge cookie on gobrev.dev.
// Every consumer that must recognize a launchable reads this one predicate instead of
// repeating the host list.
export function isOpenClawLaunchableHost(hostname) {
  const host = String(hostname || "");
  return /^nemoclaw-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.brevlab\.com$/i.test(host) ||
    /^nemoclaw-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.apps\.run\.brev\.nvidia\.com$/i.test(host) ||
    /^nemoclaw-[a-z0-9](?:[a-z0-9-]{0,52}[a-z0-9])?\.gobrev\.dev$/i.test(host);
}

export function accessProviderForOpenClawUrl(rawUrl, selected = "auto") {
  const choice = String(selected || "auto").trim().toLowerCase();
  if (!["auto", "cloudflare", "pomerium"].includes(choice)) {
    throw new Error("Access provider must be Automatic, Cloudflare Access, or Pomerium");
  }
  let host = "";
  try { host = new URL(normalizeOpenClawLaunchableUrl(rawUrl), pageBase()).hostname; }
  catch (_) { return choice; }
  if (isBrevLaunchableFamily(host) && !isOpenClawLaunchableHost(host)) {
    throw new Error("Use the NemoClaw App URL: https://nemoclaw-<id>.brevlab.com or https://nemoclaw-<id>.apps.run.brev.nvidia.com");
  }
  const inferred = isOpenClawLaunchableHost(host)
    ? (host.toLowerCase().endsWith(".brevlab.com") ? "cloudflare" : "pomerium")
    : "auto";
  if (choice !== "auto" && inferred !== "auto" && choice !== inferred) {
    throw new Error("Selected access provider does not match the launchable URL");
  }
  return choice === "auto" ? inferred : choice;
}

export function openclawAccessCookieName(rawUrl, accessProvider = "auto") {
  const provider = accessProviderForOpenClawUrl(rawUrl, accessProvider);
  if (provider === "cloudflare") return "CF_Authorization";
  if (provider !== "pomerium") return "";
  const host = new URL(normalizeOpenClawLaunchableUrl(rawUrl), pageBase()).hostname;
  return host.toLowerCase().endsWith(".gobrev.dev") ? "__Host-skybridge-brev-prd" : "_pomerium";
}

function pageBase() {
  return browserLocation()?.href || "http://localhost/";
}

export function normalizeOpenClawProxyBase(raw) {
  const text = String(raw || "").trim();
  if (!text) return "";
  const url = new URL(text);
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("OpenClaw relay URL cannot include credentials, query parameters, or a fragment");
  }
  const normalized = url.href.replace(/\/+$/, "");
  if (normalized !== DEFAULT_OPENCLAW_PROXY_BASE) {
    throw new Error("OpenClaw launchables use the approved NVIDIA DLI relay");
  }
  return normalized;
}

export function normalizeOpenClawLaunchableUrl(raw) {
  const text = String(raw || "").trim().replace(/\/+$/, "");
  if (!text) return "";
  let outer;
  try { outer = new URL(text, pageBase()); }
  catch (_) { return text; }

  // Earlier builds stored the effective relay URL instead of the launchable URL.
  // Recover only an HTTPS Brev target; never retain an outer personal worker host.
  const match = outer.pathname.match(/^\/https\/([^/]+)(\/.*)?$/i);
  if (match && isOpenClawLaunchableHost(match[1].split(":")[0])) {
    return new URL("https://" + match[1]).origin;
  }
  if (isPersonalWorkerHost(outer.hostname)) return "";
  outer.hash = "";
  if (isOpenClawLaunchableHost(outer.hostname)) {
    outer.search = "";
    outer.pathname = "";
    return outer.origin;
  }
  return /^[a-z][a-z0-9+.-]*:/i.test(text) ? outer.href.replace(/\/+$/, "") : text;
}

export function getOpenClawProxyConfig() {
  return { enabled: true, base: DEFAULT_OPENCLAW_PROXY_BASE };
}

export function setOpenClawProxyConfig({ enabled, base } = {}) {
  // Retained only so boundary tests and older integrations fail closed. It is
  // deliberately absent from the learner helper registry.
  const target = storage();
  if (enabled === false) throw new Error("OpenClaw launchables use the approved NVIDIA DLI relay; it cannot be disabled.");
  if (base !== undefined && String(base || "").trim()) normalizeOpenClawProxyBase(base);
  try {
    target?.removeItem(OPENCLAW_PROXY_BASE_KEY);
    target?.removeItem(OPENCLAW_PROXY_ENABLED_KEY);
  } catch (_) {}
  return { enabled: true, base: DEFAULT_OPENCLAW_PROXY_BASE };
}

export function getOpenClawWsRelayEnabled() {
  try { return storage()?.getItem(OPENCLAW_WS_RELAY_ENABLED_KEY) === "1"; }
  catch (_) { return false; }
}

export function setOpenClawWsRelayEnabled(enabled = false) {
  const target = storage();
  try {
    if (enabled) target?.setItem(OPENCLAW_WS_RELAY_ENABLED_KEY, "1");
    else target?.removeItem(OPENCLAW_WS_RELAY_ENABLED_KEY);
  } catch (_) {}
  return Boolean(enabled);
}

export function shouldProxyOpenClaw(rawUrl, config = getOpenClawProxyConfig(), accessSession = "") {
  const clean = normalizeOpenClawLaunchableUrl(rawUrl);
  if (!clean) return false;
  let upstream;
  try { upstream = new URL(clean, pageBase()); }
  catch (_) { return false; }
  if (!isOpenClawLaunchableHost(upstream.hostname)) return false;
  if (config?.enabled === false) return false;
  // A course served by the same launchable origin already has the browser's
  // authenticated session and does not send that session through an external relay.
  // Public course origins use a manually supplied, tab-scoped access session through
  // the approved relay. Pomerium stays direct until that fallback is actually supplied.
  const loc = browserLocation();
  if (loc && upstream.origin === loc.origin) return false;
  if (accessProviderForOpenClawUrl(clean) === "pomerium") {
    return Boolean(String(accessSession || "").trim());
  }
  return true;
}

function appendPath(rawUrl, pathAndQuery) {
  const clean = normalizeOpenClawLaunchableUrl(rawUrl);
  if (!clean) return "";
  const suffix = String(pathAndQuery || "");
  if (!suffix) return clean;
  return clean.replace(/\/+$/, "") + (suffix.startsWith("/") ? suffix : "/" + suffix);
}

export function openclawHttpUrl(
  rawUrl,
  pathAndQuery = "",
  config = getOpenClawProxyConfig(),
  accessProvider = "auto",
  accessSession = "",
) {
  const clean = normalizeOpenClawLaunchableUrl(rawUrl);
  accessProviderForOpenClawUrl(clean, accessProvider);
  const direct = appendPath(clean, pathAndQuery);
  if (!direct || !shouldProxyOpenClaw(clean, config, accessSession)) {
    return { url: direct, displayUrl: direct, viaProxy: false, directUrl: direct, directDisplayUrl: direct };
  }
  const upstream = new URL(direct, pageBase());
  // When a caller explicitly selects relay transport, only the repository-approved
  // origin is allowed. A disabled config selects a direct, credential-free browser route.
  const proxied = new URL(DEFAULT_OPENCLAW_PROXY_BASE);
  const proxyPath = proxied.pathname.replace(/\/+$/, "");
  const upstreamPath = String(pathAndQuery || "") ? upstream.pathname : "";
  proxied.pathname = proxyPath + "/https/" + upstream.host + upstreamPath;
  proxied.search = upstream.search;
  return {
    url: proxied.href,
    displayUrl: proxied.href,
    viaProxy: true,
    directUrl: direct,
    directDisplayUrl: direct,
  };
}

export function openclawWebSocketUrl(rawUrl, pathAndQuery = "/cli/gateway", accessSession = "", config = getOpenClawProxyConfig(), accessProvider = "auto") {
  // Validate an explicit provider even on direct routes. Routing must not make
  // a mismatched provider/host pair silently acceptable.
  const provider = accessProviderForOpenClawUrl(rawUrl, accessProvider);
  const native = pathAndQuery === "/cli/gateway" &&
    openclawAccessCookieName(rawUrl, provider) === "__Host-skybridge-brev-prd" &&
    secretStorage()?.getItem(OPENCLAW_CREDENTIAL_ORIGIN_KEY) === credentialOrigin(rawUrl) &&
    secretStorage()?.getItem(OPENCLAW_TERMINAL_GATEWAY_KEY) === "1";
  const routed = openclawHttpUrl(rawUrl, native ? gatewayTerminalPath() : pathAndQuery, config, provider, accessSession);
  if (!routed.url) return routed;
  const url = new URL(routed.url, pageBase());
  url.protocol = url.protocol === "http:" ? "ws:" : "wss:";
  if (routed.viaProxy && String(accessSession || "").trim()) {
    if (provider === "auto") throw new Error("Choose Cloudflare Access or Pomerium for this launchable");
    if (provider === "cloudflare") {
      // Cloudflare's relay contract uses this query name.
      url.searchParams.set("cf_access_jwt", String(accessSession).trim());
    } else {
      // A manually supplied Pomerium session uses the provider-bound relay.
      // Directly detected browser sessions never reach this branch.
      url.searchParams.set("access_provider", provider);
      url.searchParams.set("access_session", String(accessSession).trim());
    }
  }
  const display = new URL(url.href);
  if (display.searchParams.has("access_session")) display.searchParams.set("access_session", "...");
  if (display.searchParams.has("cf_access_jwt")) display.searchParams.set("cf_access_jwt", "...");
  if (native) display.searchParams.set("cmd", "<gateway adapter>");
  return { ...routed, url: url.href, displayUrl: display.href, gatewayViaTerminal: native,
    transport: native ? (routed.viaProxy ? "hosted relay terminal gateway" : "direct terminal gateway")
      : routed.viaProxy ? "hosted relay" : "direct browser",
    openSocket: () => native ? new GatewayTerminalSocket(url.href) : new WebSocket(url.href) };
}

// Transport helpers construct sockets through the same provider-bound router.
export function setOpenClawTerminalGateway(enabled, expected = getOpenClawConnection()) {
  const connection = getOpenClawConnection();
  if (["rawUrl", "accessProvider", "accessSession", "token"].some(key => connection[key] !== expected[key]))
    throw new Error("The connected gateway changed; run Connect again.");
  const secrets = secretStorage();
  if (enabled && openclawAccessCookieName(connection.rawUrl, connection.accessProvider) === "__Host-skybridge-brev-prd")
    secrets?.setItem(OPENCLAW_TERMINAL_GATEWAY_KEY, "1");
  else {
    secrets?.removeItem(OPENCLAW_TERMINAL_GATEWAY_KEY);
    if (!enabled) clearDeviceAuth(secrets);
  }
}

export function openclawGatewaySocketRoute(rawUrl, accessSession, config, accessProvider) {
  return openclawWebSocketUrl(rawUrl, "/cli/gateway", accessSession, config, accessProvider);
}

export function openOpenClawWebSocket(rawUrl, pathAndQuery, accessSession, config, accessProvider) {
  if (pathAndQuery === "/cli/gateway")
    return openclawGatewaySocketRoute(rawUrl, accessSession, config, accessProvider).openSocket();
  return new WebSocket(openclawWebSocketUrl(rawUrl, pathAndQuery, accessSession, config, accessProvider).url);
}

export function migrateOpenClawConnectionStorage() {
  const target = storage();
  if (!target) return { rawUrl: "", migrated: false };
  // Retired relay overrides are cleaned once during state migration. Route
  // construction remains a pure read and cannot write storage as a side effect.
  target.removeItem(OPENCLAW_PROXY_BASE_KEY);
  target.removeItem(OPENCLAW_PROXY_ENABLED_KEY);
  const beforeRaw = target.getItem(OPENCLAW_RAW_URL_KEY) || "";
  const beforeEffective = target.getItem(OPENCLAW_URL_KEY) || "";
  const clean = normalizeOpenClawLaunchableUrl(beforeRaw) || normalizeOpenClawLaunchableUrl(beforeEffective);
  if (!clean) {
    if (beforeRaw || beforeEffective) {
      target.removeItem(OPENCLAW_RAW_URL_KEY);
      target.removeItem(OPENCLAW_URL_KEY);
    }
    return { rawUrl: "", migrated: !!(beforeRaw || beforeEffective) };
  }
  let accessProvider = target.getItem(OPENCLAW_ACCESS_PROVIDER_KEY) || "auto";
  try {
    accessProviderForOpenClawUrl(clean, accessProvider);
  } catch (error) {
    // Older or interrupted writes can leave the previous host family's explicit
    // provider beside a newly entered launchable URL. The allowlisted hostname
    // is authoritative, so heal only this exact mismatch back to automatic.
    if (error?.message !== "Selected access provider does not match the launchable URL") throw error;
    accessProvider = "auto";
    target.setItem(OPENCLAW_ACCESS_PROVIDER_KEY, accessProvider);
  }
  const secrets = boundSecretStorage(clean);
  const accessSession = secrets?.getItem(OPENCLAW_ACCESS_SESSION_KEY) ||
    secrets?.getItem(OPENCLAW_ACCESS_JWT_KEY) || "";
  const effective = openclawHttpUrl(
    clean,
    "",
    getOpenClawProxyConfig(),
    accessProvider,
    accessSession,
  ).url || clean;
  target.setItem(OPENCLAW_RAW_URL_KEY, clean);
  target.setItem(OPENCLAW_URL_KEY, effective);
  return { rawUrl: clean, migrated: clean !== beforeRaw || effective !== beforeEffective };
}

export function setOpenClawConnection({ rawUrl, token, accessProvider, accessSession, accessJwt } = {}) {
  /* @doc <code>helpers.setOpenClawConnection(connection)</code> :: Validates and saves launchable routing while keeping credentials in tab-scoped storage. */
  const target = storage();
  const secrets = secretStorage();
  const current = migrateOpenClawConnectionStorage();
  const clean = rawUrl === undefined
    ? current.rawUrl
    : normalizeOpenClawLaunchableUrl(rawUrl);
  const originChanged = rawUrl !== undefined && clean !== current.rawUrl;
  const nextToken = token === undefined
    ? (originChanged ? "" : (secrets?.getItem(OPENCLAW_TOKEN_KEY) || ""))
    : String(token || "").trim();
  const savedProvider = target?.getItem(OPENCLAW_ACCESS_PROVIDER_KEY) || "auto";
  const nextAccessProvider = accessProvider === undefined
    ? (rawUrl === undefined ? savedProvider : "auto")
    : String(accessProvider || "auto").trim().toLowerCase();
  accessProviderForOpenClawUrl(clean, nextAccessProvider);
  const suppliedSession = accessSession === undefined ? accessJwt : accessSession;
  const legacySession = secrets?.getItem(OPENCLAW_ACCESS_SESSION_KEY) || secrets?.getItem(OPENCLAW_ACCESS_JWT_KEY) || "";
  let nextAccessSession = suppliedSession === undefined
    ? (originChanged ? "" : legacySession)
    : String(suppliedSession || "").trim();
  const resolvedAccessProvider = accessProviderForOpenClawUrl(clean, nextAccessProvider);
  if (originChanged || nextAccessSession !== legacySession || nextAccessProvider !== savedProvider) {
    clearDeviceAuth(secrets);
    secrets?.removeItem(OPENCLAW_TERMINAL_GATEWAY_KEY);
  }
  target?.removeItem(OPENCLAW_DEVICE_AUTH_KEY);
  if (!target) return {
    rawUrl: clean,
    effectiveUrl: openclawHttpUrl(
      clean, "", getOpenClawProxyConfig(), nextAccessProvider, nextAccessSession,
    ).url || clean,
    token: nextToken,
    accessProvider: nextAccessProvider,
    resolvedAccessProvider,
    accessSession: nextAccessSession,
    accessJwt: nextAccessSession,
  };
  const effectiveUrl = clean
    ? (openclawHttpUrl(
        clean, "", getOpenClawProxyConfig(), nextAccessProvider, nextAccessSession,
      ).url || clean)
    : "";
  if (clean) {
    // Compute and validate first, then persist the provider before its URL.
    // Readers never observe a cross-family host/provider pair.
    target.setItem(OPENCLAW_ACCESS_PROVIDER_KEY, nextAccessProvider);
    target.setItem(OPENCLAW_RAW_URL_KEY, clean);
    target.setItem(OPENCLAW_URL_KEY, effectiveUrl);
  } else {
    target.setItem(OPENCLAW_ACCESS_PROVIDER_KEY, nextAccessProvider);
    target.removeItem(OPENCLAW_RAW_URL_KEY);
    target.removeItem(OPENCLAW_URL_KEY);
  }
  if (nextToken) secrets?.setItem(OPENCLAW_TOKEN_KEY, nextToken);
  else secrets?.removeItem(OPENCLAW_TOKEN_KEY);
  target.removeItem(OPENCLAW_TOKEN_KEY);
  if (nextAccessSession) secrets?.setItem(OPENCLAW_ACCESS_SESSION_KEY, nextAccessSession);
  else secrets?.removeItem(OPENCLAW_ACCESS_SESSION_KEY);
  if (clean) secrets?.setItem(OPENCLAW_CREDENTIAL_ORIGIN_KEY, credentialOrigin(clean));
  else secrets?.removeItem(OPENCLAW_CREDENTIAL_ORIGIN_KEY);
  target.removeItem(OPENCLAW_ACCESS_SESSION_KEY);
  secrets?.removeItem(OPENCLAW_ACCESS_JWT_KEY);
  target.removeItem(OPENCLAW_ACCESS_JWT_KEY);
  return {
    rawUrl: clean,
    effectiveUrl: clean ? (target.getItem(OPENCLAW_URL_KEY) || clean) : "",
    token: nextToken,
    accessProvider: nextAccessProvider,
    resolvedAccessProvider,
    accessSession: nextAccessSession,
    accessJwt: nextAccessSession,
  };
}

export function getOpenClawConnection() {
  /* @doc <code>helpers.getOpenClawConnection()</code> :: Returns the normalized launchable route, provider, and tab-scoped credentials after migrating legacy storage. */
  const target = storage();
  const secrets = secretStorage();
  const migrated = migrateOpenClawConnectionStorage();
  const accessProvider = target?.getItem(OPENCLAW_ACCESS_PROVIDER_KEY) || "auto";
  const resolvedAccessProvider = accessProviderForOpenClawUrl(migrated.rawUrl, accessProvider);
  // Legacy persistent credentials lack an origin binding; discard instead of replaying.
  target?.removeItem(OPENCLAW_TOKEN_KEY);
  target?.removeItem(OPENCLAW_ACCESS_SESSION_KEY);
  target?.removeItem(OPENCLAW_ACCESS_JWT_KEY);
  const accessSession = secrets?.getItem(OPENCLAW_ACCESS_SESSION_KEY) ||
    secrets?.getItem(OPENCLAW_ACCESS_JWT_KEY) || "";
  return {
    rawUrl: migrated.rawUrl,
    effectiveUrl: target?.getItem(OPENCLAW_URL_KEY) || "",
    token: secrets?.getItem(OPENCLAW_TOKEN_KEY) || "",
    accessProvider,
    resolvedAccessProvider,
    accessSession,
    accessJwt: accessSession,
    proxy: getOpenClawProxyConfig(),
  };
}

migrateOpenClawConnectionStorage();

// Forward gateway frames through Skybridge's existing authenticated terminal.
// The browser still signs the gateway challenge and retains its scoped device.
const PREFIX = "__DLI_GATEWAY__";
const LIMIT = 8 * 1024 * 1024;
const PROGRAM = `
const prefix='${PREFIX}',limit=${LIMIT};
if(process.stdin.isTTY)process.stdin.setRawMode(true);
process.stdin.setEncoding('utf8');
const socket=new WebSocket('ws://127.0.0.1:18789');
let input='',done=false;
const emit=value=>process.stdout.write(prefix+Buffer.from(JSON.stringify(value)).toString('base64')+'\\n');
const finish=code=>{if(done)return;done=true;emit({type:'close',code});socket.close();setTimeout(()=>process.exit(0),20)};
socket.addEventListener('open',()=>emit({type:'open'}));
socket.addEventListener('message',event=>{if(typeof event.data!=='string'||event.data.length>limit)return finish(1009);emit({type:'message',data:event.data})});
socket.addEventListener('error',()=>finish(1011));
socket.addEventListener('close',event=>finish(event.code));
process.stdin.on('data',chunk=>{input+=chunk;if(input.length>limit*2)return finish(1009);let end;while((end=input.indexOf('\\n'))>=0){const line=input.slice(0,end).trim();input=input.slice(end+1);if(!line)continue;if(socket.readyState!==1)return finish(1011);socket.send(Buffer.from(line,'base64').toString('utf8'))}});
process.stdin.on('end',()=>finish(1000));
`;

function encode(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 16384)
    binary += String.fromCharCode(...bytes.subarray(i, i + 16384));
  return btoa(binary);
}

export function gatewayTerminalPath() {
  // This command contains public code only. Credentials travel in input frames.
  return "/ws/terminal?cmd=" + encodeURIComponent(
    'node -e eval(Buffer.from("' + encode(PROGRAM) + '","base64").toString())');
}

export class GatewayTerminalSocket extends EventTarget {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  readyState = 0;
  onopen = null;
  onmessage = null;
  onerror = null;
  onclose = null;
  #terminal;
  #buffer = "";

  constructor(url) {
    super();
    this.url = url;
    this.#terminal = new WebSocket(url);
    this.#terminal.onmessage = event => {
      if (this.readyState >= 2) return;
      let frame;
      try { frame = JSON.parse(event.data); } catch (_) { return this.#fail(); }
      if (frame.type === "exit") return this.#finish(1006);
      if (typeof frame.data !== "string") return;
      this.#buffer += frame.data;
      if (this.#buffer.length > LIMIT * 2) return this.#fail();
      let end;
      while ((end = this.#buffer.indexOf("\n")) >= 0) {
        const line = this.#buffer.slice(0, end).replace(/\r$/, "");
        this.#buffer = this.#buffer.slice(end + 1);
        if (!line.startsWith(PREFIX)) continue;
        let value;
        try {
          const bytes = Uint8Array.from(atob(line.slice(PREFIX.length)), c => c.charCodeAt(0));
          value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
        } catch (_) { return this.#fail(); }
        if (value.type === "open" && this.readyState === 0) {
          this.readyState = 1;
          this.#emit(new Event("open"));
        } else if (value.type === "message" && this.readyState === 1 && typeof value.data === "string") {
          this.#emit(new MessageEvent("message", { data: value.data }));
        } else if (value.type === "close") this.#finish(value.code);
        else return this.#fail();
      }
    };
    this.#terminal.onerror = () => this.#fail();
    this.#terminal.onclose = () => this.#finish(1006);
  }

  #emit(event) {
    this.dispatchEvent(event);
    this["on" + event.type]?.call(this, event);
  }

  #finish(code) {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.#buffer = "";
    this.#terminal.close();
    const event = new Event("close");
    Object.assign(event, { code: Number.isInteger(code) ? code : 1006, reason: "", wasClean: code === 1000 });
    this.#emit(event);
  }

  #fail() {
    if (this.readyState >= 2) return;
    this.readyState = 2;
    try { this.#emit(new Event("error")); }
    finally { this.#finish(1011); }
  }

  send(data) {
    if (this.readyState !== 1) throw new DOMException("Gateway is not open.", "InvalidStateError");
    if (typeof data !== "string" || data.length > LIMIT) throw new TypeError("Gateway requires a bounded text frame.");
    this.#terminal.send(JSON.stringify({ type: "input", data: encode(data) + "\n" }));
  }

  close() {
    if (this.readyState >= 2) return;
    this.readyState = 2;
    this.#terminal.close();
    this.#finish(1000);
  }
}
