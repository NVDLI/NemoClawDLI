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

function storage() {
  try { return globalThis.localStorage || null; }
  catch (_) { return null; }
}

// Gateway and access credentials are tab-scoped. The launchable URL and routing may persist,
// but another course page on the shared CDN must not inherit credentials from a prior session.
function secretStorage() {
  try { return globalThis.sessionStorage || storage(); }
  catch (_) { return storage(); }
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
  return host.endsWith(".brevlab.com") || host.endsWith(".apps.run.brev.nvidia.com");
}

// The two supported account-specific launchable hostname families:
// https://nemoclaw-<id>.apps.run.brev.nvidia.com and https://nemoclaw-<id>.brevlab.com.
// Every consumer that must recognize a launchable reads this one predicate instead of
// repeating the host list.
export function isOpenClawLaunchableHost(hostname) {
  const host = String(hostname || "");
  return /^nemoclaw-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.brevlab\.com$/i.test(host) ||
    /^nemoclaw-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.apps\.run\.brev\.nvidia\.com$/i.test(host);
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
    ? (host.toLowerCase().endsWith(".apps.run.brev.nvidia.com") ? "pomerium" : "cloudflare")
    : "auto";
  if (choice !== "auto" && inferred !== "auto" && choice !== inferred) {
    throw new Error("Selected access provider does not match the launchable URL");
  }
  return choice === "auto" ? inferred : choice;
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
  const routed = openclawHttpUrl(rawUrl, pathAndQuery, config, provider, accessSession);
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
  return { ...routed, url: url.href, displayUrl: display.href };
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
  const secrets = secretStorage();
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
  const target = storage();
  const secrets = secretStorage();
  const migrated = migrateOpenClawConnectionStorage();
  const accessProvider = target?.getItem(OPENCLAW_ACCESS_PROVIDER_KEY) || "auto";
  const resolvedAccessProvider = accessProviderForOpenClawUrl(migrated.rawUrl, accessProvider);
  // One-time migration from older builds that persisted credentials in localStorage.
  const legacyToken = target?.getItem(OPENCLAW_TOKEN_KEY) || "";
  const legacySession = target?.getItem(OPENCLAW_ACCESS_SESSION_KEY) || target?.getItem(OPENCLAW_ACCESS_JWT_KEY) || "";
  if (legacyToken && !secrets?.getItem(OPENCLAW_TOKEN_KEY)) secrets?.setItem(OPENCLAW_TOKEN_KEY, legacyToken);
  if (legacySession && !secrets?.getItem(OPENCLAW_ACCESS_SESSION_KEY)) {
    secrets?.setItem(OPENCLAW_ACCESS_SESSION_KEY, legacySession);
  }
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
