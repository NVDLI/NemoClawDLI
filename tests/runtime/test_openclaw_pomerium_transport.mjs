// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';

const persistent = new Map();
const tab = new Map();
const storage = map => ({
  getItem: key => map.get(key) ?? null,
  setItem: (key, value) => map.set(key, String(value)),
  removeItem: key => map.delete(key),
});

globalThis.localStorage = storage(persistent);
globalThis.sessionStorage = storage(tab);
globalThis.location = new URL('https://cdn.dli.learn.nvidia.com/course-static/test/web/nemoclaw/03a-kickstart.html');

const terminalUrls = [];
class FakeWebSocket {
  static OPEN = 1;
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    terminalUrls.push(url);
    setTimeout(() => {
      this.readyState = FakeWebSocket.OPEN;
      this.onopen?.();
      const command = new URL(url).searchParams.get('cmd') || '';
      const body = command.endsWith('http://127.0.0.1/api/agent')
        ? JSON.stringify({ agent: { dashboardUrl: '/#token=test-gateway-token' } })
        : JSON.stringify({ status: 'ok' });
      this.onmessage?.({ data: JSON.stringify({ type: 'data', data: body }) });
      this.onmessage?.({ data: JSON.stringify({ type: 'exit', code: 0 }) });
      this.close();
    }, 0);
  }
  send() {}
  close() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.();
  }
}
globalThis.WebSocket = FakeWebSocket;

const connection = await import('../../web/nemoclaw/scripts/_connection.js');
const openshell = await import('../../web/nemoclaw/scripts/_openshell.js');
const shared = await import('../../web/nemoclaw/scripts/_shared.js');
const launchable = 'https://nemoclaw-test.apps.run.brev.nvidia.com';

test('Pomerium loopback probe is registered for learner cells', () => {
  assert.equal(shared.HELPER_FNS.openclawLoopbackProbe, openshell.openclawLoopbackProbe);
});

test('Pomerium stays browser-direct and exposes only fixed loopback bootstrap reads', async () => {
  const saved = connection.setOpenClawConnection({
    rawUrl: launchable,
    token: 'tab-token',
    accessProvider: 'pomerium',
    accessSession: 'must-not-be-retained',
  });

  assert.equal(saved.accessSession, '');
  assert.equal(connection.getOpenClawConnection().accessSession, '');
  assert.equal(persistent.get(connection.OPENCLAW_TOKEN_KEY), undefined);
  assert.equal(persistent.get(connection.OPENCLAW_ACCESS_SESSION_KEY), undefined);
  assert.equal(tab.get(connection.OPENCLAW_TOKEN_KEY), 'tab-token');
  assert.equal(tab.get(connection.OPENCLAW_ACCESS_SESSION_KEY), undefined);

  const http = connection.openclawHttpUrl(launchable, '/api/agent');
  const gateway = connection.openclawWebSocketUrl(
    launchable,
    '/cli/gateway',
    'must-not-enter-url',
    undefined,
    'pomerium',
  );
  assert.equal(http.url, launchable + '/api/agent');
  assert.equal(http.viaProxy, false);
  assert.equal(gateway.url, 'wss://nemoclaw-test.apps.run.brev.nvidia.com/cli/gateway');
  assert.equal(gateway.viaProxy, false);
  assert.doesNotMatch(gateway.url, /openclaw-cors-proxy|access_session|cf_access_jwt|must-not-enter-url/);

  const metadata = await openshell.openclawLoopbackProbe('/api/agent', { baseUrl: launchable });
  assert.equal(metadata.transport, 'direct-terminal-loopback');
  assert.equal(metadata.json.agent.dashboardUrl, '/#token=test-gateway-token');
  assert.equal(terminalUrls.length, 1);
  const terminal = new URL(terminalUrls[0]);
  assert.equal(terminal.origin, 'wss://nemoclaw-test.apps.run.brev.nvidia.com');
  assert.equal(terminal.pathname, '/ws/terminal');
  assert.equal(terminal.searchParams.get('cmd'), 'curl -fsS --max-time 10 http://127.0.0.1/api/agent');
  assert.doesNotMatch(terminal.href, /openclaw-cors-proxy|access_session|cf_access_jwt|must-not-be-retained/);

  await assert.rejects(
    openshell.openclawLoopbackProbe('/arbitrary', { baseUrl: launchable }),
    /Unsupported loopback bootstrap path/,
  );
  assert.equal(terminalUrls.length, 1, 'unsupported path opened a terminal socket');
});
