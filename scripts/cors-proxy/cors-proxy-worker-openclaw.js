// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Browser proxy contract for allowlisted NemoClaw launchables.
const WORKER_VERSION = "openclaw-cors-proxy/2026-07-09-access-providers";
const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);
const REDIRECT_BODY_HEADERS = ["content-encoding", "content-language", "content-location", "content-type"];
const COOKIE_VALUE = /^[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*$/;

async function fetchWithSameOriginRedirects(target, init, maxRedirects = 3) {
  let currentUrl = new URL(target);
  let currentInit = { ...init, headers: new Headers(init.headers || {}), redirect: "manual" };
  for (let redirects = 0; ; redirects += 1) {
    const response = await fetch(currentUrl, currentInit);
    if (!REDIRECT_STATUSES.has(response.status)) return response;
    const location = response.headers.get("location");
    if (!location) return response;
    try { await response.body?.cancel(); } catch { /* redirect body is intentionally discarded */ }
    if (redirects >= maxRedirects) throw new Error("Upstream redirect limit exceeded.");
    const nextUrl = new URL(location, currentUrl);
    if (nextUrl.origin !== currentUrl.origin) throw new Error("Cross-origin upstream redirect blocked.");
    const method = String(currentInit.method || "GET").toUpperCase();
    if ((response.status === 303 && method !== "HEAD") ||
        ((response.status === 301 || response.status === 302) && method === "POST")) {
      const headers = new Headers(currentInit.headers);
      for (const name of REDIRECT_BODY_HEADERS) headers.delete(name);
      currentInit = { ...currentInit, method: "GET", headers };
      delete currentInit.body;
    }
    currentUrl = nextUrl;
  }
}
export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "*";
    const cors = {
      "Access-Control-Allow-Origin":  origin,
      "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
      "Access-Control-Allow-Headers": "Authorization, Content-Type, x-openclaw-session-key, Accept, CF-Access-Jwt-Assertion, X-OpenClaw-Access-Provider, X-OpenClaw-Access-Session",
      "Access-Control-Max-Age":       "86400",
    };
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors });
    }
    const url  = new URL(request.url);
    const path = url.pathname.slice(1);
    if (!path.startsWith("https/")) {
      return new Response('Use /https/<host>/<path> (drop the ://).', { status: 400, headers: { "Content-Type": "text/plain", ...cors } });
    }
    const rest = path.slice("https/".length);
    const host = (rest.split("/")[0] || "").toLowerCase();
    // Restrict targets because requests carry an access session. Without this
    // allowlist, a caller could redirect that session to another host.
    const cloudflareHost = /^[a-z0-9.-]+$/.test(host) && (host === "brevlab.com" || host.endsWith(".brevlab.com"));
    const pomeriumHost = /^[a-z0-9.-]+$/.test(host) &&
      (host === "apps.run.brev.nvidia.com" || host.endsWith(".apps.run.brev.nvidia.com"));
    const hostOk = cloudflareHost || pomeriumHost;
    if (!hostOk) {
      return new Response('Upstream host not allowed (NemoClaw launchables only).', { status: 403, headers: { "Content-Type": "text/plain", ...cors } });
    }
    const targetSearch = new URLSearchParams(url.search);
    const fwdHeaders = new Headers(request.headers);
    const expectedProvider = pomeriumHost ? "pomerium" : "cloudflare";
    const headerProvider = (fwdHeaders.get("X-OpenClaw-Access-Provider") || "").toLowerCase();
    const queryProvider = (targetSearch.get("access_provider") || "").toLowerCase();
    if (headerProvider && queryProvider && headerProvider !== queryProvider) {
      return new Response("Conflicting access providers.", { status: 400, headers: { "Content-Type": "text/plain", ...cors } });
    }
    const requestedProvider = headerProvider || queryProvider;
    const headerSession = fwdHeaders.get("X-OpenClaw-Access-Session") || "";
    const querySession = targetSearch.get("access_session") || "";
    const legacyHeaderSession = fwdHeaders.get("CF-Access-Jwt-Assertion") || "";
    const legacyQuerySession = targetSearch.get("cf_access_jwt") || "";
    if ((headerSession && querySession && headerSession !== querySession) ||
        (legacyHeaderSession && legacyQuerySession && legacyHeaderSession !== legacyQuerySession)) {
      return new Response("Conflicting access sessions.", { status: 400, headers: { "Content-Type": "text/plain", ...cors } });
    }
    const neutralSession = headerSession || querySession;
    const legacySession = legacyHeaderSession || legacyQuerySession;
    if (requestedProvider && requestedProvider !== expectedProvider) {
      return new Response("Access provider does not match the upstream host.", { status: 400, headers: { "Content-Type": "text/plain", ...cors } });
    }
    if (legacySession && expectedProvider !== "cloudflare") {
      return new Response("Cloudflare access assertions are valid only for Cloudflare launchables.", { status: 400, headers: { "Content-Type": "text/plain", ...cors } });
    }
    if (neutralSession && legacySession && neutralSession !== legacySession) {
      return new Response("Conflicting access sessions.", { status: 400, headers: { "Content-Type": "text/plain", ...cors } });
    }
    const accessSession = neutralSession || legacySession;
    if (accessSession.length > 8192) {
      return new Response("Access session is too large.", { status: 400, headers: { "Content-Type": "text/plain", ...cors } });
    }
    if (accessSession && !COOKIE_VALUE.test(accessSession)) {
      return new Response("Access session contains invalid cookie characters.", { status: 400, headers: { "Content-Type": "text/plain", ...cors } });
    }
    targetSearch.delete("cf_access_jwt");
    targetSearch.delete("access_provider");
    targetSearch.delete("access_session");
    const target = "https://" + rest + (targetSearch.toString() ? "?" + targetSearch.toString() : "");
    fwdHeaders.delete("CF-Access-Jwt-Assertion");
    fwdHeaders.delete("X-OpenClaw-Access-Provider");
    fwdHeaders.delete("X-OpenClaw-Access-Session");
    fwdHeaders.delete("CF-Access-Client-Id");
    fwdHeaders.delete("CF-Access-Client-Secret");
    fwdHeaders.delete("Cookie");
    if (accessSession) {
      fwdHeaders.set("Cookie", expectedProvider === "pomerium"
        ? "_pomerium=" + accessSession
        : "CF_Authorization=" + accessSession);
    }
    if (cloudflareHost && env.CF_ACCESS_CLIENT_ID && env.CF_ACCESS_CLIENT_SECRET) {
      fwdHeaders.set("CF-Access-Client-Id",     env.CF_ACCESS_CLIENT_ID);
      fwdHeaders.set("CF-Access-Client-Secret", env.CF_ACCESS_CLIENT_SECRET);
    }

    const isWebSocket = (request.headers.get("Upgrade") || "").toLowerCase() === "websocket";
    if (isWebSocket) {
      // OpenClaw validates Origin during the WebSocket handshake.
      // nginx uses the same trusted origin; the Worker terminates CF/JWT authentication.
      fwdHeaders.set("Origin", "http://localhost:8088");
      const upstream = await fetch(target, { method: request.method, headers: fwdHeaders, redirect: "manual" });
      if (upstream.webSocket) return upstream;
      return new Response("Upstream did not accept WebSocket upgrade", { status: 502, headers: { "Content-Type": "text/plain", ...cors } });
    }

    let upstream;
    try {
      const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
      upstream = await fetchWithSameOriginRedirects(target, { method: request.method, headers: fwdHeaders, body });
    } catch (error) {
      return new Response(error.message || "Upstream redirect blocked.", { status: 502, headers: { "Content-Type": "text/plain", ...cors } });
    }
    const out = new Response(upstream.body, upstream);
    for (const [k, v] of Object.entries(cors)) out.headers.set(k, v);
    return out;
  },
};
