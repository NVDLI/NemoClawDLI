// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../src/openclaw-websocket-request.js', import.meta.url), 'utf8');

function loadHandler() {
  const updates = [];
  const context = {
    __cf: { updateRequestOrigin: options => updates.push(options) },
    JSON,
  };
  vm.runInNewContext(
    source.replace("import cf from 'cloudfront';", 'var cf = __cf;') + '\nthis.__handler = handler;',
    context,
  );
  return { handler: context.__handler, updates };
}

function event(overrides = {}) {
  return {
    request: {
      method: 'GET',
      uri: '/https/nemoclaw-demo.brevlab.com/cli/gateway',
      querystring: {
        cf_access_jwt: { value: 'header.payload.signature' },
        keep: { value: '1' },
      },
      headers: {
        origin: { value: 'https://course.example' },
        upgrade: { value: 'websocket' },
        'sec-websocket-key': { value: 'key' },
        'sec-websocket-version': { value: '13' },
      },
      cookies: { untrusted: { value: 'drop-me' } },
      ...overrides,
    },
  };
}

test('routes an authenticated gateway upgrade directly to the allowlisted Brev origin', () => {
  const { handler, updates } = loadHandler();
  const request = handler(event());
  assert.equal(request.uri, '/cli/gateway');
  assert.deepEqual({ ...request.querystring }, { keep: { value: '1' } });
  assert.deepEqual(Object.keys(request.cookies), ['CF_Authorization']);
  assert.equal(request.cookies.CF_Authorization.value, 'header.payload.signature');
  assert.equal(request.headers.origin.value, 'http://localhost:8088');
  assert.equal(updates.length, 1);
  assert.equal(updates[0].domainName, 'nemoclaw-demo.brevlab.com');
  assert.equal(updates[0].hostHeader, 'nemoclaw-demo.brevlab.com');
  assert.equal(updates[0].sni, 'nemoclaw-demo.brevlab.com');
  assert.deepEqual([...updates[0].allowedCertificateNames], ['brevlab.com', '*.brevlab.com']);
});

test('allows CloudFront to omit viewer handshake headers and lets the upstream complete the upgrade', () => {
  const { handler } = loadHandler();
  const withoutViewerHandshakeHeaders = event();
  delete withoutViewerHandshakeHeaders.request.headers.upgrade;
  delete withoutViewerHandshakeHeaders.request.headers['sec-websocket-key'];
  delete withoutViewerHandshakeHeaders.request.headers['sec-websocket-version'];
  const request = handler(withoutViewerHandshakeHeaders);
  assert.equal(request.uri, '/cli/gateway');
  assert.deepEqual(Object.keys(request.cookies), ['CF_Authorization']);
});

test('routes a Pomerium-authenticated gateway with only its validated provider cookie', () => {
  const { handler, updates } = loadHandler();
  const request = handler(event({
    uri: '/https/nemoclaw-demo.apps.run.brev.nvidia.com/cli/gateway',
    querystring: {
      access_provider: { value: 'pomerium' },
      access_session: { value: 'opaque-session' },
      keep: { value: '1' },
    },
  }));
  assert.equal(request.uri, '/cli/gateway');
  assert.deepEqual({ ...request.querystring }, { keep: { value: '1' } });
  assert.deepEqual(Object.keys(request.cookies), ['_pomerium']);
  assert.equal(request.cookies._pomerium.value, 'opaque-session');
  assert.equal(request.headers['x-pomerium-authorization'], undefined);
  assert.equal(updates[0].domainName, 'nemoclaw-demo.apps.run.brev.nvidia.com');
  assert.deepEqual([...updates[0].allowedCertificateNames], [
    'apps.run.brev.nvidia.com',
    '*.apps.run.brev.nvidia.com',
  ]);
});

test('replaces caller credentials with only the validated Pomerium cookie', () => {
  const { handler } = loadHandler();
  const request = handler(event({
    uri: '/https/nemoclaw-demo.apps.run.brev.nvidia.com/cli/gateway',
    headers: {
      upgrade: { value: 'websocket' },
      'sec-websocket-key': { value: 'key' },
      'sec-websocket-version': { value: '13' },
      'x-pomerium-authorization': { value: 'caller-controlled' },
    },
    querystring: {
      access_provider: { value: 'pomerium' },
      access_session: { value: 'validated-session' },
    },
  }));
  assert.equal(request.headers['x-pomerium-authorization'], undefined);
  assert.deepEqual(Object.keys(request.cookies), ['_pomerium']);
  assert.equal(request.cookies._pomerium.value, 'validated-session');
});

test('rejects a neutral session without an explicit provider', () => {
  const { handler, updates } = loadHandler();
  const response = handler(event({
    uri: '/https/nemoclaw-demo.apps.run.brev.nvidia.com/cli/gateway',
    querystring: {
      access_session: { value: 'opaque-session' },
    },
  }));
  assert.equal(response.statusCode, 400);
  assert.match(response.body, /explicit access provider/);
  assert.equal(updates.length, 0);
});

test('accepts the HTTP assertion header and removes it before origin forwarding', () => {
  const { handler } = loadHandler();
  const input = event({
    querystring: {},
    headers: {
      upgrade: { value: 'websocket' },
      'sec-websocket-key': { value: 'key' },
      'sec-websocket-version': { value: '13' },
      'cf-access-jwt-assertion': { value: 'header.jwt' },
      'cf-access-client-id': { value: 'viewer-must-not-set-this' },
      'cf-access-client-secret': { value: 'viewer-must-not-set-this' },
    },
  });
  const request = handler(input);
  assert.equal(request.headers['cf-access-jwt-assertion'], undefined);
  assert.equal(request.headers['cf-access-client-id'], undefined);
  assert.equal(request.headers['cf-access-client-secret'], undefined);
  assert.equal(request.cookies.CF_Authorization.value, 'header.jwt');
});

test('preserves an allowlisted launchable path prefix', () => {
  const { handler, updates } = loadHandler();
  const request = handler(event({ uri: '/https/nemoclaw-demo.brevlab.com/kickstart/openclaw/cli/gateway' }));
  assert.equal(request.uri, '/kickstart/openclaw/cli/gateway');
  assert.equal(updates[0].domainName, 'nemoclaw-demo.brevlab.com');
});

test('routes the operator terminal upgrade and preserves its command query', () => {
  const { handler, updates } = loadHandler();
  const input = event({
    uri: '/https/nemoclaw-demo.brevlab.com/ws/terminal',
    querystring: {
      cmd: { value: 'openshell sandbox connect my-assistant' },
      cf_access_jwt: { value: 'terminal.jwt' },
    },
  });
  const request = handler(input);
  assert.equal(request.uri, '/ws/terminal');
  assert.deepEqual({ ...request.querystring }, {
    cmd: { value: 'openshell sandbox connect my-assistant' },
  });
  assert.equal(request.cookies.CF_Authorization.value, 'terminal.jwt');
  assert.equal(request.headers.origin.value, 'http://localhost:8088');
  assert.equal(updates.length, 1);
  assert.equal(updates[0].domainName, 'nemoclaw-demo.brevlab.com');
});

for (const [label, uri, statusCode] of [
  ['off-allowlist host', '/https/evil.example/cli/gateway', 403],
  ['suffix lookalike', '/https/brevlab.com.evil.example/cli/gateway', 403],
  ['malformed DNS labels', '/https/nemoclaw..brevlab.com/cli/gateway', 403],
  ['userinfo host', '/https/a@b.brevlab.com/cli/gateway', 403],
  ['wrong path', '/https/nemoclaw-demo.brevlab.com/api/agent', 400],
]) {
  test(`rejects ${label}`, () => {
    const { handler, updates } = loadHandler();
    const response = handler(event({ uri }));
    assert.equal(response.statusCode, statusCode);
    assert.equal(updates.length, 0);
  });
}

test('rejects non-GET and explicitly contradictory upgrade requests', () => {
  const { handler, updates } = loadHandler();
  assert.equal(handler(event({ method: 'POST' })).statusCode, 400);

  const contradictoryUpgrade = event();
  contradictoryUpgrade.request.headers.upgrade.value = 'h2c';
  assert.equal(handler(contradictoryUpgrade).statusCode, 400);
  assert.equal(updates.length, 0);
});

test('rejects ambiguous and oversized assertions', () => {
  const { handler } = loadHandler();
  const duplicate = event();
  duplicate.request.querystring.cf_access_jwt.multiValue = [{ value: 'a' }, { value: 'b' }];
  assert.equal(handler(duplicate).statusCode, 400);
  const large = event();
  large.request.querystring.cf_access_jwt.value = 'x'.repeat(8193);
  assert.equal(handler(large).statusCode, 400);

  const conflicting = event();
  conflicting.request.headers['cf-access-jwt-assertion'] = { value: 'different.jwt' };
  assert.equal(handler(conflicting).statusCode, 400);

  const invalidCookie = event();
  invalidCookie.request.querystring.cf_access_jwt.value = 'valid; injected=true';
  assert.equal(handler(invalidCookie).statusCode, 400);
});

test('rejects provider mismatches and legacy assertions on Pomerium hosts', () => {
  const { handler } = loadHandler();
  const mismatch = event({
    uri: '/https/nemoclaw-demo.apps.run.brev.nvidia.com/cli/gateway',
    querystring: {
      access_provider: { value: 'cloudflare' },
      access_session: { value: 'must-not-forward' },
    },
  });
  assert.equal(handler(mismatch).statusCode, 400);

  const legacy = event({
    uri: '/https/nemoclaw-demo.apps.run.brev.nvidia.com/cli/gateway',
  });
  assert.equal(handler(legacy).statusCode, 400);
});

test('rejects conflicting provider declarations', () => {
  const { handler } = loadHandler();
  const conflicting = event({
    querystring: {
      access_provider: { value: 'cloudflare' },
      access_session: { value: 'must-not-forward' },
    },
    headers: {
      origin: { value: 'https://course.example' },
      upgrade: { value: 'websocket' },
      'sec-websocket-key': { value: 'key' },
      'sec-websocket-version': { value: '13' },
      'x-openclaw-access-provider': { value: 'pomerium' },
    },
  });
  assert.equal(handler(conflicting).statusCode, 400);
});
