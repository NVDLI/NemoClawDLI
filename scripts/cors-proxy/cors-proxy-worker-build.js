// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Browser proxy for the NVIDIA model API.
// Replaces duplicate upstream CORS headers and forwards caller authentication unchanged.

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
      },
    });
  }

  // Forward to NVIDIA API
  const url      = new URL(request.url);
  const upstream = NVIDIA_API_ORIGIN + url.pathname + url.search;

  const fwd = new Headers(request.headers);
  fwd.delete("host");

  let resp;
  try {
    resp = await fetch(upstream, { method: request.method, headers: fwd, body: request.body });
  } catch (e) {
    console.error("NVIDIA API upstream request failed", e && e.name ? e.name : "Error");
    return new Response(JSON.stringify({ error: "upstream request failed" }), {
      status: 502,
      headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": origin },
    });
  }

  // Replace the upstream ACAO header instead of adding a second value.
  // The proxy carries bearer authentication, so credentialed CORS stays disabled.
  const out = new Headers(resp.headers);
  out.set("Access-Control-Allow-Origin", origin);

  return new Response(resp.body, { status: resp.status, statusText: resp.statusText, headers: out });
}
