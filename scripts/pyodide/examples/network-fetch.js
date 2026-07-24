// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const BLOCKED_HEADERS = new Set([
  "connection", "content-length", "cookie", "host", "origin", "referer",
]);

function requestHeaders(headers) {
  return Object.fromEntries(
    [...headers.entries()].filter(([name]) => !BLOCKED_HEADERS.has(name.toLowerCase())),
  );
}

export function createCourseFetch({ fetchImpl = fetch, relayUrl, allowedOrigins = [] }) {
  const allowlist = new Set(allowedOrigins);

  return async function courseFetch(input, init) {
    const request = new Request(input, init);
    const target = new URL(request.url, self.location.href);

    if (target.origin === self.location.origin || allowlist.has(target.origin)) {
      return fetchImpl(request);
    }
    if (!relayUrl) {
      throw new Error(`This lesson does not allow requests to ${target.origin}.`);
    }

    const body = ["GET", "HEAD"].includes(request.method)
      ? null
      : Array.from(new Uint8Array(await request.arrayBuffer()));
    return fetchImpl(relayUrl, {
      method: "POST",
      credentials: "omit",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: target.href,
        method: request.method,
        headers: requestHeaders(request.headers),
        body,
      }),
      signal: request.signal,
    });
  };
}
