// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Browser proxy for the NVIDIA model API.
// Replaces duplicate upstream CORS headers and forwards caller bearer authentication.
//
// Teaching reference. It shows the browser contract and the response-header
// rules a deployment must keep. It is not the deployed relay: it has no edge
// authentication, no request logging, and no operator configuration surface.
// scripts/cors-proxy/deployable/src/proxy.mjs is the complete implementation.

// Upstream CORS decisions belong to this relay, not to the origin. Dropping
// these before the reflected origin is reattached keeps a single ACAO value and
// prevents an upstream credential grant from pairing with an arbitrary origin.
const UPSTREAM_CORS_HEADERS = [
  "access-control-allow-origin",
  "access-control-allow-methods",
  "access-control-allow-headers",
  "access-control-allow-credentials",
  "access-control-expose-headers",
  "access-control-max-age",
  "set-cookie",
  "set-cookie2",
];
const BILLING_INVOKE_ORIGIN = /^dli-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;

addEventListener("fetch", event => {
  event.respondWith(handle(event.request));
});

const NVIDIA_API_ORIGIN = "https://integrate.api.nvidia.com";

async function handle(request) {
  const origin = request.headers.get("Origin") || "*";

  // Handle CORS preflight
  if (request.method === "OPTIONS") {
    return new Response(null, {
      status: 204,
      headers: {
        "Access-Control-Allow-Origin":  origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        // X-BILLING-INVOKE-ORIGIN attributes usage to the course.
        // The browser requires preflight approval; the worker forwards the value unchanged.
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-BILLING-INVOKE-ORIGIN",
        "Access-Control-Max-Age":       "86400",
        "Vary":                         "Origin",
      },
    });
  }

  // Forward to NVIDIA API
  const url      = new URL(request.url);
  const upstream = NVIDIA_API_ORIGIN + url.pathname + url.search;

  const fwd = new Headers(request.headers);
  fwd.delete("host");
  fwd.delete("content-length");
  // The caller authenticates with a bearer token. A browser cookie would only
  // reach the upstream by accident, so drop it before forwarding.
  fwd.delete("cookie");
  fwd.delete("x-dli-cors-proxy-secret");
  fwd.delete("x-forwarded-for");
  fwd.delete("x-forwarded-host");
  fwd.delete("x-forwarded-proto");
  const billingOrigin = (fwd.get("X-BILLING-INVOKE-ORIGIN") || "").trim();
  if (billingOrigin && (billingOrigin.length > 64 || !BILLING_INVOKE_ORIGIN.test(billingOrigin))) {
    return new Response(JSON.stringify({ error: "invalid billing invoke origin" }), {
      status: 400,
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": origin, "Vary": "Origin" },
    });
  }

  let resp;
  try {
    const body = ["GET", "HEAD"].includes(request.method) ? undefined : request.body;
    resp = await fetch(upstream, { method: request.method, headers: fwd, body });
  } catch (e) {
    console.error("NVIDIA API upstream request failed", e && e.name ? e.name : "Error");
    return new Response(JSON.stringify({ error: "upstream request failed" }), {
      status: 502,
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": origin, "Vary": "Origin" },
    });
  }

  // Replace the upstream CORS headers instead of adding second values.
  // The proxy carries bearer authentication, so credentialed CORS stays disabled.
  const out = new Headers(resp.headers);
  for (const name of UPSTREAM_CORS_HEADERS) out.delete(name);
  out.set("Access-Control-Allow-Origin", origin);
  out.set("Vary", "Origin");

  return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers: out });
}
