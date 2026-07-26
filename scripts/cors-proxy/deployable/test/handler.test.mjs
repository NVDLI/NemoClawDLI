// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import test from 'node:test';
import assert from 'node:assert/strict';
import { PassThrough } from 'node:stream';

import { assertCloudFrontSecret } from '../src/proxy.mjs';

// handler.mjs captures the Lambda streaming helpers at module load. Install a
// recording double first so response metadata stays observable off Lambda.
globalThis.awslambda = {
  streamifyResponse: (fn) => fn,
  HttpResponseStream: {
    from: (stream, metadata) => {
      stream.responseMetadata = metadata;
      return stream;
    },
  },
};
const { handler } = await import('../src/handler.mjs');

const ORIGIN = 'https://course.example';
const SHARED_SECRET = 'operator-supplied-edge-secret';

async function withEnv(vars, fn) {
  const saved = {};
  for (const key of Object.keys(vars)) {
    saved[key] = process.env[key];
    if (vars[key] === undefined) delete process.env[key];
    else process.env[key] = vars[key];
  }
  try {
    return await fn();
  } finally {
    for (const key of Object.keys(vars)) {
      if (saved[key] === undefined) delete process.env[key];
      else process.env[key] = saved[key];
    }
  }
}

function collector() {
  const stream = new PassThrough();
  const chunks = [];
  stream.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
  return { stream, body: () => Buffer.concat(chunks).toString('utf8') };
}

function proxyEvent(headers = {}, overrides = {}) {
  return {
    rawPath: '/v1/chat/completions',
    rawQueryString: 'stream=true',
    requestContext: { http: { method: 'GET' } },
    headers: { origin: ORIGIN, ...headers },
    ...overrides,
  };
}

function upstreamStream(chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
      controller.close();
    },
  });
}

async function runHandler(event) {
  const sink = collector();
  await handler(event, sink.stream);
  return { metadata: sink.stream.responseMetadata, body: sink.body() };
}

// ── Direct-origin protection ──────────────────────────────────────────────────

test('assertCloudFrontSecret fails closed until an operator configures the secret', async () => {
  await withEnv({ CLOUDFRONT_SHARED_SECRET: undefined }, () => {
    for (const headers of [{}, { 'x-dli-cors-proxy-secret': 'anything' }]) {
      assert.throws(
        () => assertCloudFrontSecret(headers),
        (error) => error.statusCode === 500 && /edge secret is not configured/.test(error.message),
      );
    }
  });
});

test('assertCloudFrontSecret accepts the configured edge header in any letter case', async () => {
  await withEnv({ CLOUDFRONT_SHARED_SECRET: SHARED_SECRET }, () => {
    assert.doesNotThrow(() => assertCloudFrontSecret({ 'x-dli-cors-proxy-secret': SHARED_SECRET }));
    assert.doesNotThrow(() => assertCloudFrontSecret({ 'X-DLI-Cors-Proxy-Secret': SHARED_SECRET }));
  });
});

test('assertCloudFrontSecret rejects missing, empty, and wrong edge headers with 403', async () => {
  await withEnv({ CLOUDFRONT_SHARED_SECRET: SHARED_SECRET }, () => {
    for (const headers of [{}, { 'x-dli-cors-proxy-secret': '' }, { 'x-dli-cors-proxy-secret': 'guessed' }]) {
      assert.throws(
        () => assertCloudFrontSecret(headers),
        (error) => error.statusCode === 403 && /Direct Lambda Function URL access is disabled/.test(error.message),
      );
    }
  });
});

test('a direct Function URL request is refused before any upstream call', async () => {
  const realFetch = globalThis.fetch;
  let upstreamCalls = 0;
  globalThis.fetch = async () => { upstreamCalls += 1; throw new Error('upstream must not be reached'); };
  try {
    const result = await withEnv(
      { CLOUDFRONT_SHARED_SECRET: SHARED_SECRET },
      () => runHandler(proxyEvent()),
    );
    assert.equal(upstreamCalls, 0);
    assert.equal(result.metadata.statusCode, 403);
    assert.equal(result.metadata.headers['access-control-allow-origin'], ORIGIN);
    assert.equal(result.metadata.headers['access-control-allow-credentials'], undefined);
    assert.deepEqual(JSON.parse(result.body), { error: 'Direct Lambda Function URL access is disabled' });
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('a missing edge-secret configuration fails closed before any upstream call', async () => {
  const realFetch = globalThis.fetch;
  let upstreamCalls = 0;
  globalThis.fetch = async () => { upstreamCalls += 1; throw new Error('upstream must not be reached'); };
  try {
    const result = await withEnv(
      { CLOUDFRONT_SHARED_SECRET: undefined },
      () => runHandler(proxyEvent({ 'x-dli-cors-proxy-secret': SHARED_SECRET })),
    );
    assert.equal(upstreamCalls, 0);
    assert.equal(result.metadata.statusCode, 500);
    assert.equal(result.metadata.headers['access-control-allow-origin'], ORIGIN);
    assert.deepEqual(JSON.parse(result.body), {
      error: 'Proxy request failed',
      details: 'Relay edge secret is not configured',
    });
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('a CloudFront-signed request reaches the upstream and forwards no edge secret', async () => {
  const realFetch = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (url, init) => {
    seen.push({ url: String(url), headers: init.headers });
    return new Response('ok', { status: 200, headers: { 'content-type': 'text/plain' } });
  };
  try {
    const result = await withEnv(
      { CLOUDFRONT_SHARED_SECRET: SHARED_SECRET },
      () => runHandler(proxyEvent({ 'x-dli-cors-proxy-secret': SHARED_SECRET })),
    );
    assert.equal(seen.length, 1);
    assert.equal(seen[0].url, 'https://build.nvidia.com/v1/chat/completions?stream=true');
    // The edge secret authenticates CloudFront to this relay. Forwarding it
    // would hand an operator credential to the upstream origin.
    assert.equal(seen[0].headers.get('x-dli-cors-proxy-secret'), null);
    assert.equal(result.metadata.statusCode, 200);
    assert.equal(result.body, 'ok');
  } finally {
    globalThis.fetch = realFetch;
  }
});

// ── Response streaming ────────────────────────────────────────────────────────

test('the handler streams an upstream body through with filtered CORS metadata', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(
    upstreamStream(['data: one\n\n', 'data: two\n\n', 'data: [DONE]\n\n']),
    {
      status: 200,
      headers: {
        'content-type': 'text/event-stream',
        'access-control-allow-origin': 'https://wrong.example',
        'access-control-allow-credentials': 'true',
        'set-cookie': 'upstream=leak',
      },
    },
  );
  try {
    const result = await withEnv(
      { CLOUDFRONT_SHARED_SECRET: SHARED_SECRET },
      () => runHandler(proxyEvent({ 'x-dli-cors-proxy-secret': SHARED_SECRET })),
    );
    assert.equal(result.metadata.statusCode, 200);
    assert.equal(result.metadata.headers['content-type'], 'text/event-stream');
    assert.equal(result.metadata.headers['access-control-allow-origin'], ORIGIN);
    assert.equal(result.metadata.headers['access-control-allow-credentials'], undefined);
    assert.equal(result.metadata.headers['set-cookie'], undefined);
    assert.equal(result.metadata.headers.vary, 'Origin');
    assert.equal(result.body, 'data: one\n\ndata: two\n\ndata: [DONE]\n\n');
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('a preflight answers from the relay without contacting the upstream', async () => {
  const realFetch = globalThis.fetch;
  let upstreamCalls = 0;
  globalThis.fetch = async () => { upstreamCalls += 1; throw new Error('upstream must not be reached'); };
  try {
    const result = await withEnv(
      { CLOUDFRONT_SHARED_SECRET: SHARED_SECRET },
      () => runHandler(proxyEvent(
        { 'x-dli-cors-proxy-secret': SHARED_SECRET },
        { requestContext: { http: { method: 'OPTIONS' } } },
      )),
    );
    assert.equal(upstreamCalls, 0);
    assert.equal(result.metadata.statusCode, 200);
    assert.equal(result.metadata.headers['access-control-allow-origin'], ORIGIN);
    assert.equal(result.body, 'OK\n');
  } finally {
    globalThis.fetch = realFetch;
  }
});

test('a caller-facing upstream failure keeps its status and CORS metadata', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('upstream timeout'); };
  try {
    const result = await withEnv(
      { CLOUDFRONT_SHARED_SECRET: SHARED_SECRET },
      () => runHandler(proxyEvent({ 'x-dli-cors-proxy-secret': SHARED_SECRET })),
    );
    assert.equal(result.metadata.statusCode, 502);
    assert.equal(result.metadata.headers['access-control-allow-origin'], ORIGIN);
    assert.deepEqual(JSON.parse(result.body), {
      error: 'Proxy request failed',
      details: 'upstream timeout',
    });
  } finally {
    globalThis.fetch = realFetch;
  }
});
