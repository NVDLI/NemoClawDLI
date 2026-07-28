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
let failDirectTerminal = false;
class FakeWebSocket {
  static OPEN = 1;
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    terminalUrls.push(url);
    setTimeout(() => {
      if (failDirectTerminal && new URL(url).hostname.endsWith('.brevlab.com')) {
        this.onerror?.(new Error('direct route unavailable'));
        this.close();
        return;
      }
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

test('Pomerium keeps a supplied session tab-scoped and uses the provider-bound relay', async () => {
  const saved = connection.setOpenClawConnection({
    rawUrl: launchable,
    token: 'tab-token',
    accessProvider: 'pomerium',
    accessSession: 'manual-pomerium-session',
  });

  assert.equal(saved.accessSession, 'manual-pomerium-session');
  const restored = connection.getOpenClawConnection();
  assert.equal(restored.accessSession, 'manual-pomerium-session');
  assert.equal(
    restored.effectiveUrl,
    'https://openclaw-cors-proxy.experiments.courses.nvidia.com/https/nemoclaw-test.apps.run.brev.nvidia.com',
  );
  assert.equal(persistent.get(connection.OPENCLAW_TOKEN_KEY), undefined);
  assert.equal(persistent.get(connection.OPENCLAW_ACCESS_SESSION_KEY), undefined);
  assert.equal(tab.get(connection.OPENCLAW_TOKEN_KEY), 'tab-token');
  assert.equal(tab.get(connection.OPENCLAW_ACCESS_SESSION_KEY), 'manual-pomerium-session');

  const gateway = shared.openclawGatewayWsUrl(
    launchable,
    saved.accessSession,
    null,
    null,
    'pomerium',
  );
  assert.equal(
    gateway.url,
    'wss://openclaw-cors-proxy.experiments.courses.nvidia.com/https/nemoclaw-test.apps.run.brev.nvidia.com/cli/gateway?access_provider=pomerium&access_session=manual-pomerium-session',
  );
  assert.equal(gateway.viaProxy, true);
  assert.doesNotMatch(gateway.displayUrl, /manual-pomerium-session/);

  const metadata = await openshell.openclawLoopbackProbe('/api/agent', { baseUrl: launchable });
  assert.equal(metadata.transport, 'direct-terminal-loopback');
  assert.equal(metadata.json.agent.dashboardUrl, '/#token=test-gateway-token');
  assert.equal(terminalUrls.length, 1);
  const terminal = new URL(terminalUrls[0]);
  assert.equal(terminal.origin, 'wss://nemoclaw-test.apps.run.brev.nvidia.com');
  assert.equal(terminal.pathname, '/ws/terminal');
  assert.equal(terminal.searchParams.get('cmd'), 'curl -fsS --max-time 10 http://127.0.0.1/api/agent');
  assert.equal(terminal.searchParams.get('access_provider'), null);
  assert.equal(terminal.searchParams.get('access_session'), null);

  await assert.rejects(
    openshell.openclawLoopbackProbe('/arbitrary', { baseUrl: launchable }),
    /Unsupported loopback bootstrap path/,
  );
  assert.equal(terminalUrls.length, 1, 'unsupported path opened a terminal socket');
});

test('Pomerium remains direct when no manual access session is supplied', () => {
  connection.setOpenClawConnection({
    rawUrl: launchable,
    token: 'tab-token',
    accessProvider: 'pomerium',
    accessSession: '',
  });
  const gateway = connection.openclawWebSocketUrl(
    launchable,
    '/cli/gateway',
    '',
    undefined,
    'pomerium',
  );
  assert.equal(gateway.url, 'wss://nemoclaw-test.apps.run.brev.nvidia.com/cli/gateway');
  assert.equal(gateway.viaProxy, false);
});

test('Cloudflare terminal retries through relay only after direct failure', async () => {
  const launchable = 'https://nemoclaw-test.brevlab.com';
  connection.setOpenClawConnection({
    rawUrl: launchable,
    token: 'tab-token',
    accessProvider: 'cloudflare',
    accessSession: 'cloudflare-session',
  });
  terminalUrls.length = 0;
  failDirectTerminal = true;
  try {
    await openshell.terminal('printf ready', {
      baseUrl: launchable,
      openMs: 20,
      idleMs: 20,
      totalMs: 2000,
    });
  } finally {
    failDirectTerminal = false;
  }

  assert.equal(terminalUrls.length, 2);
  assert.equal(new URL(terminalUrls[0]).origin, 'wss://nemoclaw-test.brevlab.com');
  const fallback = new URL(terminalUrls[1]);
  assert.equal(fallback.origin, 'wss://openclaw-cors-proxy.experiments.courses.nvidia.com');
  assert.equal(fallback.searchParams.get('cf_access_jwt'), 'cloudflare-session');
});
