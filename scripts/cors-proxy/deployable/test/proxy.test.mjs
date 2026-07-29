// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  bodyFromEvent,
  buildTargetUrl,
  corsHeaders,
  fetchWithSameOriginRedirects,
  filteredRequestHeaders,
  filteredResponseHeaders,
  isHostAllowed,
  normalizePath,
  preflightResponse,
  responseForProxyError,
  stripSensitiveQuery,
} from '../src/proxy.mjs';

const RETIRED_BILLING_HEADER = ['X-BILLING', 'SOURCE'].join('-');

function withEnv(vars, fn) {
  const saved = {};
  for (const key of Object.keys(vars)) {
    saved[key] = process.env[key];
    if (vars[key] === undefined) delete process.env[key];
    else process.env[key] = vars[key];
  }
  try {
    return fn();
  } finally {
    for (const key of Object.keys(vars)) {
      if (saved[key] === undefined) delete process.env[key];
      else process.env[key] = saved[key];
    }
  }
}

test('buildTargetUrl always uses the hardcoded upstream origin', () => {
  const target = buildTargetUrl('/v1/chat/completions', 'stream=true');
  assert.equal(target.toString(), 'https://build.nvidia.com/v1/chat/completions?stream=true');
});

test('normalizePath strips absolute proxy URL tricks', () => {
  assert.equal(normalizePath('/https/evil.example/path'), '/evil.example/path');
  assert.equal(normalizePath('https://evil.example/path'), '/evil.example/path');
});

test('corsHeaders allow arbitrary origins but do not allow credentials', () => {
  const headers = corsHeaders('https://course.example');
  assert.equal(headers['access-control-allow-origin'], 'https://course.example');
  assert.equal(headers['access-control-allow-credentials'], undefined);
  assert.match(headers['access-control-allow-headers'], /x-openclaw-session-key/);
  assert.match(headers['access-control-allow-headers'], /CF-Access-Jwt-Assertion/);
  assert.match(headers['access-control-allow-headers'], /X-BILLING-INVOKE-ORIGIN/i);
  assert.doesNotMatch(
    headers['access-control-allow-headers'],
    new RegExp(RETIRED_BILLING_HEADER, 'i'),
  );
});

test('the deployed NVIDIA API endpoint preflights the invoke-origin header', () => {
  const template = JSON.parse(
    readFileSync(new URL('../infrastructure/template.json', import.meta.url), 'utf8'),
  );
  const headers = template.Resources.ModelFunction.Properties.Environment
    .Variables.CORS_ALLOWED_HEADERS;
  assert.match(headers, /X-BILLING-INVOKE-ORIGIN/i);
  assert.doesNotMatch(headers, new RegExp(RETIRED_BILLING_HEADER, 'i'));
});

test('X-BILLING-INVOKE-ORIGIN is bounded and forwarded by the NVIDIA API relay', () => {
  const fwd = filteredRequestHeaders({
    'Content-Type': 'application/json',
    'X-BILLING-INVOKE-ORIGIN': 'dli-cfx11-web',
    [RETIRED_BILLING_HEADER]: 'retired-value',
  }, 'integrate.api.nvidia.com');
  assert.equal(fwd.get('X-BILLING-INVOKE-ORIGIN'), 'dli-cfx11-web');
  assert.equal(fwd.get(RETIRED_BILLING_HEADER), null);
});

test('billing attribution rejects malformed and multihost values', () => {
  assert.throws(
    () => filteredRequestHeaders({ 'X-BILLING-INVOKE-ORIGIN': 'https://spoofed.example' }, 'integrate.api.nvidia.com'),
    /Invalid billing invoke origin/,
  );
  withEnv({ PROXY_MODE: 'multihost-allowlist' }, () => {
    assert.throws(
      () => filteredRequestHeaders({ 'X-BILLING-INVOKE-ORIGIN': 'dli-cfx11-web' }, 'nemoclaw-demo.brevlab.com'),
      /Invalid billing invoke origin/,
    );
  });
});

test('preflightResponse returns 200 and CORS headers', () => {
  const response = preflightResponse('https://course.example');
  assert.equal(response.statusCode, 200);
  assert.equal(response.headers['access-control-allow-origin'], 'https://course.example');
  assert.equal(response.body, 'OK\n');
});

test('filteredRequestHeaders strips browser cookies and hop-by-hop headers', () => {
  const headers = filteredRequestHeaders({
    Host: 'proxy.example',
    Cookie: 'session=bad',
    Connection: 'keep-alive',
    Authorization: 'Bearer ok',
    'x-openclaw-session-key': 'session-key',
    'X-Pomerium-Authorization': 'caller-controlled',
    'CF-Access-Client-Id': 'caller-id',
    'CF-Access-Client-Secret': 'caller-secret',
  });
  assert.equal(headers.get('host'), null);
  assert.equal(headers.get('cookie'), null);
  assert.equal(headers.get('connection'), null);
  assert.equal(headers.get('authorization'), 'Bearer ok');
  assert.equal(headers.get('x-openclaw-session-key'), 'session-key');
  assert.equal(headers.get('x-pomerium-authorization'), null);
  assert.equal(headers.get('cf-access-client-id'), null);
  assert.equal(headers.get('cf-access-client-secret'), null);
});

test('filteredRequestHeaders maps Cloudflare Access JWT header to its upstream-only cookie', () => {
  const headers = filteredRequestHeaders({
    'CF-Access-Jwt-Assertion': 'jwt-value',
  }, 'nemoclaw-demo.brevlab.com');
  assert.equal(headers.get('CF-Access-Jwt-Assertion'), null);
  assert.equal(headers.get('cookie'), 'CF_Authorization=jwt-value');
});

test('filteredRequestHeaders maps a Pomerium session only for the Pomerium host family', () => {
  const headers = filteredRequestHeaders({
    'X-OpenClaw-Access-Provider': 'pomerium',
    'X-OpenClaw-Access-Session': 'opaque-session',
  }, 'nemoclaw-demo.apps.run.brev.nvidia.com');
  assert.equal(headers.get('X-OpenClaw-Access-Provider'), null);
  assert.equal(headers.get('X-OpenClaw-Access-Session'), null);
  assert.equal(headers.get('cookie'), '_pomerium=opaque-session');
  assert.equal(headers.get('X-Pomerium-Authorization'), null);
});

test('filteredRequestHeaders requires an explicit provider for neutral sessions', () => {
  assert.throws(() => filteredRequestHeaders({
    'X-OpenClaw-Access-Session': 'opaque-session',
  }, 'nemoclaw-demo.apps.run.brev.nvidia.com'), /require an explicit access provider/);
});

test('filteredRequestHeaders rejects provider and host mismatches', () => {
  assert.throws(() => filteredRequestHeaders({
    'X-OpenClaw-Access-Provider': 'cloudflare',
    'X-OpenClaw-Access-Session': 'must-not-forward',
  }, 'nemoclaw-demo.apps.run.brev.nvidia.com'), /does not match/);
  assert.throws(() => filteredRequestHeaders({
    'CF-Access-Jwt-Assertion': 'must-not-forward',
  }, 'nemoclaw-demo.apps.run.brev.nvidia.com'), /Cloudflare access assertions/);
});

test('Cloudflare service-token headers are always stripped', () => {
  const cloudflare = filteredRequestHeaders({
    'CF-Access-Client-Id': 'caller-id',
    'CF-Access-Client-Secret': 'caller-secret',
  }, 'nemoclaw-demo.brevlab.com');
  assert.equal(cloudflare.get('cf-access-client-id'), null);
  assert.equal(cloudflare.get('cf-access-client-secret'), null);

  const pomerium = filteredRequestHeaders({
    'CF-Access-Client-Id': 'caller-id',
    'CF-Access-Client-Secret': 'caller-secret',
    'X-OpenClaw-Access-Provider': 'pomerium',
    'X-OpenClaw-Access-Session': 'opaque-session',
  }, 'nemoclaw-demo.apps.run.brev.nvidia.com');
  assert.equal(pomerium.get('cf-access-client-id'), null);
  assert.equal(pomerium.get('cf-access-client-secret'), null);
  assert.equal(pomerium.get('cookie'), '_pomerium=opaque-session');
  assert.equal(pomerium.get('x-pomerium-authorization'), null);

  const unrelated = filteredRequestHeaders({
    'CF-Access-Client-Id': 'caller-id',
    'CF-Access-Client-Secret': 'caller-secret',
  }, 'integrate.api.nvidia.com');
  assert.equal(unrelated.get('cf-access-client-id'), null);
  assert.equal(unrelated.get('cf-access-client-secret'), null);
});

test('filteredRequestHeaders rejects cookie-delimiter injection in access sessions', () => {
  for (const session of ['valid; injected=true', 'line\nbreak', 'comma,value', 'back\\slash']) {
    assert.throws(() => filteredRequestHeaders({
      'X-OpenClaw-Access-Provider': 'pomerium',
      'X-OpenClaw-Access-Session': session,
    }, 'nemoclaw-demo.apps.run.brev.nvidia.com'), /invalid cookie characters/);
  }
});

test('fetchWithSameOriginRedirects follows bounded same-origin redirects', async () => {
  const calls = [];
  const fakeFetch = async (url, init) => {
    calls.push({ url: String(url), init });
    if (calls.length === 1) {
      return new Response(null, { status: 302, headers: { location: '/next' } });
    }
    return new Response('ok', { status: 200 });
  };
  const response = await fetchWithSameOriginRedirects(
    'https://nemoclaw-demo.brevlab.com/start',
    { method: 'GET', headers: { Authorization: 'Bearer trusted' } },
    fakeFetch,
  );
  assert.equal(response.status, 200);
  assert.deepEqual(calls.map(call => call.url), [
    'https://nemoclaw-demo.brevlab.com/start',
    'https://nemoclaw-demo.brevlab.com/next',
  ]);
  assert.equal(calls[1].init.headers.get('authorization'), 'Bearer trusted');
  assert.equal(calls[1].init.redirect, 'manual');
});

for (const [status, method] of [[302, 'POST'], [303, 'PUT']]) {
  test(`fetchWithSameOriginRedirects applies bodyless GET semantics for ${status}`, async () => {
    const calls = [];
    const fakeFetch = async (url, init) => {
      calls.push({ url: String(url), init });
      if (calls.length === 1) {
        return new Response('redirect', { status, headers: { location: '/result' } });
      }
      return new Response('ok', { status: 200 });
    };
    await fetchWithSameOriginRedirects(
      'https://nemoclaw-demo.brevlab.com/submit',
      {
        method,
        body: 'request-body',
        headers: {
          'Content-Type': 'application/json',
          'Content-Length': '12',
          Authorization: 'Bearer trusted',
        },
      },
      fakeFetch,
    );
    assert.equal(calls[1].init.method, 'GET');
    assert.equal(calls[1].init.body, undefined);
    assert.equal(calls[1].init.headers.get('content-type'), null);
    assert.equal(calls[1].init.headers.get('content-length'), null);
    assert.equal(calls[1].init.headers.get('authorization'), 'Bearer trusted');
  });
}

test('fetchWithSameOriginRedirects replays a buffered body across a 307 redirect', async () => {
  const bodies = [];
  const fakeFetch = async (_url, init) => {
    bodies.push(Buffer.isBuffer(init.body) ? init.body.toString('utf8') : String(init.body));
    if (bodies.length === 1) {
      return new Response(null, { status: 307, headers: { location: '/next' } });
    }
    return new Response('ok', { status: 200 });
  };
  await fetchWithSameOriginRedirects(
    'https://nemoclaw-demo.brevlab.com/start',
    {
      method: 'POST',
      body: Buffer.from('request-body'),
      headers: { 'Content-Type': 'application/json' },
    },
    fakeFetch,
  );
  assert.deepEqual(bodies, ['request-body', 'request-body']);
});

test('fetchWithSameOriginRedirects blocks cross-origin credential replay', async () => {
  const calls = [];
  const fakeFetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response(null, {
      status: 302,
      headers: { location: 'https://credential-sink.example/collect' },
    });
  };
  await assert.rejects(() => fetchWithSameOriginRedirects(
    'https://nemoclaw-demo.brevlab.com/start',
    {
      method: 'GET',
      headers: {
        Authorization: 'Bearer trusted',
      },
    },
    fakeFetch,
  ), /Cross-origin upstream redirect blocked/);
  assert.equal(calls.length, 1);
});

test('fetchWithSameOriginRedirects enforces its redirect limit', async () => {
  let calls = 0;
  const fakeFetch = async () => {
    calls += 1;
    return new Response(null, { status: 307, headers: { location: `/hop-${calls}` } });
  };
  await assert.rejects(() => fetchWithSameOriginRedirects(
    'https://nemoclaw-demo.brevlab.com/start',
    { method: 'GET' },
    fakeFetch,
    2,
  ), /redirect limit exceeded/);
  assert.equal(calls, 3);
});

test('filteredResponseHeaders strips upstream CORS and Set-Cookie', () => {
  const upstreamHeaders = new Headers({
    'content-type': 'text/event-stream',
    'access-control-allow-origin': 'https://wrong.example',
    'access-control-allow-credentials': 'true',
    'set-cookie': 'secret=bad',
  });
  const headers = filteredResponseHeaders(upstreamHeaders, 'https://course.example');
  assert.equal(headers.get('content-type'), 'text/event-stream');
  assert.equal(headers.get('access-control-allow-origin'), 'https://course.example');
  assert.equal(headers.get('access-control-allow-credentials'), null);
  assert.equal(headers.get('set-cookie'), null);
});

test('bodyFromEvent produces reusable string or Buffer request bodies', async () => {
  const text = await bodyFromEvent({
    requestContext: { http: { method: 'POST' } },
    body: 'plain text',
    isBase64Encoded: false,
  });
  assert.equal(text, 'plain text');

  const binary = await bodyFromEvent({
    requestContext: { http: { method: 'POST' } },
    body: Buffer.from('binary data').toString('base64'),
    isBase64Encoded: true,
  });
  assert.equal(Buffer.isBuffer(binary), true);
  assert.equal(binary.toString('utf8'), 'binary data');
});

test('responseForProxyError preserves caller status and visible 502 diagnostics', () => {
  const callerError = new Error('Unsupported access provider.');
  callerError.statusCode = 400;
  const callerResponse = responseForProxyError(callerError, 'https://course.example');
  assert.equal(callerResponse.statusCode, 400);
  assert.deepEqual(JSON.parse(callerResponse.body), { error: 'Unsupported access provider.' });

  const upstreamError = new Error('upstream timeout');
  upstreamError.statusCode = 502;
  const upstreamResponse = responseForProxyError(upstreamError, 'https://course.example');
  assert.equal(upstreamResponse.statusCode, 502);
  assert.deepEqual(JSON.parse(upstreamResponse.body), {
    error: 'Proxy request failed',
    details: 'upstream timeout',
  });
});

// ── Dual-endpoint behavior ────────────────────────────────────────────────────

test('single-host mode honors an UPSTREAM_ORIGIN override (nvidia-api endpoint)', () => {
  withEnv({ PROXY_MODE: undefined, UPSTREAM_ORIGIN: 'https://integrate.api.nvidia.com' }, () => {
    const target = buildTargetUrl('/v1/chat/completions', 'stream=true');
    assert.equal(target.toString(), 'https://integrate.api.nvidia.com/v1/chat/completions?stream=true');
  });
});

test('isHostAllowed: suffix and exact match, rejects off-list and malformed hosts', () => {
  const list = ['.brevlab.com', '.apps.run.brev.nvidia.com', 'gateway.example.com'];
  assert.equal(isHostAllowed('nemoclaw-abc.brevlab.com', list), true);
  assert.equal(isHostAllowed('brevlab.com', list), true);
  assert.equal(isHostAllowed('gateway.example.com', list), true);
  assert.equal(isHostAllowed('nemoclaw-abc.apps.run.brev.nvidia.com', list), true);
  assert.equal(isHostAllowed('evil.example', list), false);
  assert.equal(isHostAllowed('brevlab.com.evil.com', list), false); // suffix spoof
  assert.equal(isHostAllowed('host:8080', list), false);            // port junk
  assert.equal(isHostAllowed('a@b.brevlab.com', list), false);      // userinfo junk
});

test('multihost-allowlist mode proxies an allowlisted /https/<host>/ target', () => {
  withEnv({ PROXY_MODE: 'multihost-allowlist', UPSTREAM_HOST_ALLOWLIST: '.brevlab.com,.apps.run.brev.nvidia.com' }, () => {
    const target = buildTargetUrl('/https/nemoclaw-abc.brevlab.com/api/agent', '');
    assert.equal(target.toString(), 'https://nemoclaw-abc.brevlab.com/api/agent');
  });
});

test('multihost-allowlist mode proxies an allowlisted Pomerium launchable target', () => {
  withEnv({ PROXY_MODE: 'multihost-allowlist', UPSTREAM_HOST_ALLOWLIST: '.brevlab.com,.apps.run.brev.nvidia.com' }, () => {
    const target = buildTargetUrl('/https/nemoclaw-abc.apps.run.brev.nvidia.com/api/agent', '');
    assert.equal(target.toString(), 'https://nemoclaw-abc.apps.run.brev.nvidia.com/api/agent');
  });
});

test('access sessions never reach an upstream query string', () => {
  assert.equal(stripSensitiveQuery('keep=1&cf_access_jwt=secret&access_provider=pomerium&access_session=opaque&after=2'), 'keep=1&after=2');
  withEnv({ PROXY_MODE: 'multihost-allowlist', UPSTREAM_HOST_ALLOWLIST: '.brevlab.com' }, () => {
    const target = buildTargetUrl(
      '/https/nemoclaw-abc.brevlab.com/api/agent',
      'cf_access_jwt=secret&keep=1',
    );
    assert.equal(target.toString(), 'https://nemoclaw-abc.brevlab.com/api/agent?keep=1');
  });
});

test('multihost-allowlist mode rejects an off-allowlist host with 403 (not an open relay)', () => {
  withEnv({ PROXY_MODE: 'multihost-allowlist', UPSTREAM_HOST_ALLOWLIST: '.brevlab.com' }, () => {
    assert.throws(() => buildTargetUrl('/https/evil.example/api/agent', ''), (err) => err.statusCode === 403);
  });
});

test('multihost-allowlist mode rejects a malformed (non-/https/) path with 400', () => {
  withEnv({ PROXY_MODE: 'multihost-allowlist', UPSTREAM_HOST_ALLOWLIST: '.brevlab.com' }, () => {
    assert.throws(() => buildTargetUrl('/v1/chat/completions', ''), (err) => err.statusCode === 400);
  });
});
