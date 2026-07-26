#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import fs from 'node:fs';

const src = fs.readFileSync('web/nemoclaw/scripts/_openclaw.js', 'utf8');
const m = src.match(/export const GW_CONNECT = `([\s\S]*?)`;\n/);
if (!m) throw new Error('GW_CONNECT not found');
const quoteTemplate = value => value.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$\{/g, '\\${');
const code = Function('return `' + quoteTemplate(m[1]) + '`')();

const logs = [];
const storage = new Map([
  ['nemoclaw_clawrawurl', 'https://nemoclaw-demo.brevlab.com'],
  ['nemoclaw_clawtoken', 'test-token'],
  ['nemoclaw_openclaw_access_provider_v1', 'cloudflare'],
  ['nemoclaw_openclaw_access_session_v1', 'test.jwt'],
]);

const tabStorage = new Map();
const storageApi = values => ({
  getItem: key => values.get(key) || '',
  setItem: (key, value) => values.set(key, String(value)),
  removeItem: key => values.delete(key),
});
globalThis.localStorage = storageApi(storage);
globalThis.sessionStorage = storageApi(tabStorage);
globalThis.location = new URL('https://course.example.test/nemoclaw/03a-kickstart.html');
const connectionSource = fs.readFileSync('web/nemoclaw/scripts/_connection.js', 'utf8');
const connection = await import('data:text/javascript;base64,' + Buffer.from(connectionSource).toString('base64'));
const opened = [];
let tokenRefreshes = 0;
class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = 1;
    opened.push(url);
    setTimeout(() => this.onmessage && this.onmessage({ data: JSON.stringify({ event: 'connect.challenge' }) }), 0);
  }
  send(raw) {
    const msg = JSON.parse(raw);
    if (msg.method === 'connect') {
      setTimeout(() => this.onmessage && this.onmessage({ data: JSON.stringify({
        type: 'res', id: msg.id, ok: true,
        payload: { server: { version: 'test' }, auth: { scopes: ['operator.admin'] } },
      }) }), 0);
    }
  }
  close() { this.readyState = 3; }
}
globalThis.WebSocket = FakeWebSocket;

const helpers = {
  log: msg => logs.push(String(msg)),
  fetch: async () => { throw new Error('GW_CONNECT must not probe a retired metadata route'); },
  refreshOpenClawGatewayToken: async () => { tokenRefreshes++; return { token: 'test-token', source: 'metadata' }; },
  getOpenClawConnection: () => connection.getOpenClawConnection(),
  openclawGatewayWsUrl: (raw, session, proxyBase, proxyEnabled, provider) =>
    connection.openclawWebSocketUrl(raw, '/cli/gateway', '', { enabled: false, base: '' }, provider),
  signal: null,
};
const state = {};
const fn = new Function('state', 'helpers', 'h', 'console', '"use strict"; return (async () => {\n' + code + '\n})();');
await fn(state, helpers, helpers, console);

if (opened.length !== 1) throw new Error(`expected one WebSocket, saw ${opened.length}`);
if (tokenRefreshes !== 1) throw new Error(`expected one gateway-token bootstrap, saw ${tokenRefreshes}`);
const expected = 'wss://nemoclaw-demo.brevlab.com/cli/gateway';
if (opened[0] !== expected) throw new Error(`expected direct signed-in launchable ${expected}, got ${opened[0]}`);
if (opened[0].includes('cf_access_jwt') || logs.some(x => x.includes('via hosted relay'))) {
  throw new Error('gateway connection exposed the access session through the hosted relay');
}
console.log('gw connect transport audit: ok');
