// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import {
  assertCloudFrontSecret,
  bodyFromEvent,
  buildTargetUrl,
  fetchWithSameOriginRedirects,
  filteredRequestHeaders,
  filteredResponseHeaders,
  logSafeRequest,
  preflightResponse,
  responseForProxyError,
  shouldSendBody,
} from './proxy.mjs';

const streamifyResponse = globalThis.awslambda?.streamifyResponse ?? ((handler) => handler);
const httpResponseFrom = globalThis.awslambda?.HttpResponseStream?.from ?? ((stream) => stream);

export const handler = streamifyResponse(async (event, responseStream) => {
  const startedAt = Date.now();
  const origin = event.headers?.origin || event.headers?.Origin || '*';
  const method = event.requestContext?.http?.method || event.httpMethod || 'GET';
  let targetUrl;

  try {
    assertCloudFrontSecret(event.headers);

    if (method === 'OPTIONS') {
      const response = preflightResponse(origin);
      const out = httpResponseFrom(responseStream, {
        statusCode: response.statusCode,
        headers: response.headers,
      });
      await pipeline(Readable.from([response.body]), out);
      logSafeRequest(event, targetUrl, response.statusCode, startedAt);
      return;
    }

    // Resolve the upstream AFTER the preflight and INSIDE the try. In
    // multihost-allowlist mode this rejects off-allowlist hosts with 400/403, which
    // must surface as a CORS error response, not an unhandled Lambda fault.
    targetUrl = buildTargetUrl(event.rawPath || '/', event.rawQueryString || '');

    const requestInit = {
      method,
      headers: filteredRequestHeaders(event.headers, targetUrl.hostname),
      ...(shouldSendBody(method) ? { body: await bodyFromEvent(event) } : {}),
    };

    const upstream = await fetchWithSameOriginRedirects(targetUrl, requestInit);
    const responseHeaders = filteredResponseHeaders(upstream.headers, origin);

    const out = httpResponseFrom(responseStream, {
      statusCode: upstream.status,
      headers: Object.fromEntries(responseHeaders.entries()),
    });

    if (method === 'HEAD' || !upstream.body) {
      out.end();
      await waitForEnd(out);
      logSafeRequest(event, targetUrl, upstream.status, startedAt);
      return;
    }

    await pipeline(Readable.fromWeb(upstream.body), out);
    logSafeRequest(event, targetUrl, upstream.status, startedAt);
  } catch (error) {
    const response = responseForProxyError(error, origin);
    const statusCode = response.statusCode;
    const out = httpResponseFrom(responseStream, {
      statusCode: response.statusCode,
      headers: response.headers,
    });
    await pipeline(Readable.from([response.body]), out);
    console.error(JSON.stringify({ error: error.message, statusCode }));
  }
});

async function waitForEnd(stream) {
  if (typeof stream.finished === 'function') {
    await stream.finished();
  }
}
