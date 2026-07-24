#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.cwd();
const sourcePath = path.join(root, 'scripts/cors-proxy/cors-proxy-worker-openclaw.js');
const source = fs.readFileSync(sourcePath, 'utf8');
const tmpPath = path.join(os.tmpdir(), `openclaw-worker-${process.pid}.mjs`);
fs.writeFileSync(tmpPath, source, 'utf8');

function fail(message) {
  console.error(message);
  process.exit(1);
}

try {
  const worker = (await import(pathToFileURL(tmpPath).href)).default;
  const calls = [];
  const wsMarker = { accepted: true };
  globalThis.fetch = async (target, init = {}) => {
    const headers = Object.fromEntries(new Headers(init.headers).entries());
    calls.push({ target, method: init.method, headers, redirect: init.redirect });
    const upstream = new Response(null, { status: 200 });
    Object.defineProperty(upstream, 'webSocket', { value: wsMarker });
    return upstream;
  };

  const req = new Request('https://openclaw-cors-proxy.test/https/nemoclaw-v6paslvp5.brevlab.com/cli/gateway?cf_access_jwt=test.jwt&keep=1', {
    method: 'GET',
    headers: { Upgrade: 'websocket', Origin: 'https://course.example.test' },
  });
  const res = await worker.fetch(req, {});
  if (res.webSocket !== wsMarker) fail('worker did not return upstream WebSocket response directly');
  if (calls.length !== 1) fail(`expected one upstream fetch, saw ${calls.length}`);
  const call = calls[0];
  if (call.target !== 'https://nemoclaw-v6paslvp5.brevlab.com/cli/gateway?keep=1') fail(`bad upstream target: ${call.target}`);
  if (call.headers.cookie !== 'CF_Authorization=test.jwt') fail(`missing CF_Authorization cookie: ${JSON.stringify(call.headers)}`);
  if (call.headers.origin !== 'http://localhost:8088') fail(`bad pinned Origin: ${call.headers.origin}`);
  if (call.redirect !== 'manual') fail(`WS fetch should use manual redirect, got ${call.redirect}`);

  calls.length = 0;
  const pomeriumReq = new Request('https://openclaw-cors-proxy.test/https/nemoclaw-demo.apps.run.brev.nvidia.com/ws/terminal?cmd=openshell+sandbox+list&access_provider=pomerium&access_session=opaque.session&keep=1', {
    method: 'GET',
    headers: { Upgrade: 'websocket', Origin: 'https://course.example.test' },
  });
  const pomeriumRes = await worker.fetch(pomeriumReq, {
    CF_ACCESS_CLIENT_ID: 'must-not-forward',
    CF_ACCESS_CLIENT_SECRET: 'must-not-forward',
  });
  if (pomeriumRes.webSocket !== wsMarker) fail('worker did not return Pomerium upstream WebSocket directly');
  if (calls.length !== 1) fail(`expected one Pomerium upstream fetch, saw ${calls.length}`);
  const pomeriumCall = calls[0];
  if (pomeriumCall.target !== 'https://nemoclaw-demo.apps.run.brev.nvidia.com/ws/terminal?cmd=openshell+sandbox+list&keep=1') fail(`bad Pomerium upstream target: ${pomeriumCall.target}`);
  if (pomeriumCall.headers.cookie !== '_pomerium=opaque.session') fail(`missing _pomerium cookie: ${JSON.stringify(pomeriumCall.headers)}`);
  if (pomeriumCall.headers['cf-access-client-id'] || pomeriumCall.headers['cf-access-client-secret']) fail('Cloudflare service-token headers reached a Pomerium host');

  const mismatch = await worker.fetch(new Request('https://openclaw-cors-proxy.test/https/nemoclaw-demo.apps.run.brev.nvidia.com/cli/gateway?access_provider=cloudflare&access_session=must-not-forward', {
    method: 'GET',
    headers: { Upgrade: 'websocket', Origin: 'https://course.example.test' },
  }), {});
  if (mismatch.status !== 400) fail(`provider mismatch returned ${mismatch.status}, expected 400`);

  const conflict = await worker.fetch(new Request('https://openclaw-cors-proxy.test/https/nemoclaw-demo.brevlab.com/cli/gateway?access_provider=cloudflare&access_session=query-value', {
    method: 'GET',
    headers: {
      Upgrade: 'websocket',
      Origin: 'https://course.example.test',
      'X-OpenClaw-Access-Provider': 'pomerium',
      'X-OpenClaw-Access-Session': 'header-value',
    },
  }), {});
  if (conflict.status !== 400) fail(`conflicting provider/session declarations returned ${conflict.status}, expected 400`);

  const invalidCookie = await worker.fetch(new Request('https://openclaw-cors-proxy.test/https/nemoclaw-demo.apps.run.brev.nvidia.com/api/agent?access_provider=pomerium&access_session=valid%3Binjected%3Dtrue', {
    method: 'GET',
    headers: { Origin: 'https://course.example.test' },
  }), {});
  if (invalidCookie.status !== 400) fail(`invalid cookie delimiter returned ${invalidCookie.status}, expected 400`);

  calls.length = 0;
  globalThis.fetch = async (target, init = {}) => {
    const headers = Object.fromEntries(new Headers(init.headers).entries());
    calls.push({ target: String(target), method: init.method, headers, redirect: init.redirect });
    return new Response(null, { status: 302, headers: { location: 'https://credential-sink.example/collect' } });
  };
  const blockedRedirect = await worker.fetch(new Request('https://openclaw-cors-proxy.test/https/nemoclaw-demo.brevlab.com/api/agent', {
    method: 'GET',
    headers: {
      Origin: 'https://course.example.test',
      'CF-Access-Client-Id': 'caller-id',
      'CF-Access-Client-Secret': 'caller-secret',
    },
  }), { CF_ACCESS_CLIENT_ID: 'trusted-id', CF_ACCESS_CLIENT_SECRET: 'trusted-secret' });
  if (blockedRedirect.status !== 502) fail(`cross-origin redirect returned ${blockedRedirect.status}, expected 502`);
  if (calls.length !== 1) fail(`cross-origin redirect made ${calls.length} upstream calls, expected one`);
  if (calls[0].headers['cf-access-client-id'] !== 'trusted-id' || calls[0].headers['cf-access-client-secret'] !== 'trusted-secret') {
    fail('trusted Cloudflare headers did not replace caller-supplied values on the initial request');
  }

  calls.length = 0;
  globalThis.fetch = async (target, init = {}) => {
    const headers = Object.fromEntries(new Headers(init.headers).entries());
    calls.push({ target: String(target), method: init.method, headers, redirect: init.redirect });
    if (calls.length === 1) return new Response(null, { status: 302, headers: { location: '/next' } });
    return new Response('ok', { status: 200 });
  };
  const sameOriginRedirect = await worker.fetch(new Request('https://openclaw-cors-proxy.test/https/nemoclaw-demo.brevlab.com/api/agent', {
    method: 'GET', headers: { Origin: 'https://course.example.test' },
  }), {});
  if (sameOriginRedirect.status !== 200 || calls.length !== 2) fail('same-origin redirect did not complete in two requests');
  if (calls[1].target !== 'https://nemoclaw-demo.brevlab.com/next') fail(`bad same-origin redirect target: ${calls[1].target}`);
  if (calls.some(item => item.redirect !== 'manual')) fail('HTTP redirect fetch did not use manual mode');

  console.log('openclaw worker ws audit: ok');
} finally {
  try { fs.unlinkSync(tmpPath); } catch {}
}
