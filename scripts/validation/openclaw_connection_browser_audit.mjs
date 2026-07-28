#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let chromium;
try { ({ chromium } = require('/opt/nemoclaw-runtime/node_modules/playwright-core')); }
catch (_) { ({ chromium } = require('playwright-core')); }

const root = path.resolve(process.env.SITE_ROOT || 'web');
const port = Number(process.env.SITE_PORT || 4198);
const screenshot = process.env.SCREENSHOT_PATH || '';
const APPROVED_RELAY = 'https://openclaw-cors-proxy.experiments.courses.nvidia.com';
const mime = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png',
};

const server = http.createServer((req, res) => {
  const rel = decodeURIComponent(new URL(req.url, 'http://localhost').pathname).replace(/^\/+/, '');
  let file = path.resolve(root, rel || 'index.html');
  if (!file.startsWith(root + path.sep) && file !== root) {
    res.writeHead(403).end('forbidden'); return;
  }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  fs.readFile(file, (error, body) => {
    if (error) { res.writeHead(404).end('not found'); return; }
    res.writeHead(200, { 'content-type': mime[path.extname(file)] || 'application/octet-stream' });
    res.end(body);
  });
});

function listen() { return new Promise(resolve => server.listen(port, '127.0.0.1', resolve)); }
function ok(condition, message) { if (!condition) throw new Error(message); }

try {
  await listen();
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {}),
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  const probeRequests = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    try {
      if (window.top !== window) return;
      const retired = 'https://retired-personal-relay.' + 'workers.dev/https/nemoclaw-test123.brevlab.com';
      // A launchable host is not a valid model route, so the independence fixture uses a
      // neutral custom endpoint.
      localStorage.setItem('nemoclaw_model_api_base_url_v1', 'https://model-test123.example.test/v1');
      localStorage.setItem('nemoclaw_model_id_v1', 'model/test-123');
      sessionStorage.setItem('nvapi', 'test-model-key');
      localStorage.removeItem('nemoclaw_clawrawurl');
      localStorage.setItem('nemoclaw_clawurl', retired);
      window.__terminalUrls = [];
      window.__gatewayUrls = [];
      window.__pomeriumDirectSession = false;
      class FakeWebSocket {
        static OPEN = 1;
        constructor(url) {
          this.url = url; this.readyState = 0; this.onmessage = null; this.onopen = null; this.onclose = null;
          setTimeout(() => {
            const parsed = new URL(url);
            const directPomeriumGateway =
              parsed.hostname.endsWith('.apps.run.brev.nvidia.com') &&
              parsed.pathname === '/cli/gateway';
            if (directPomeriumGateway && !window.__pomeriumDirectSession) {
              this.onerror?.(new Event('error'));
              this.close();
              return;
            }
            this.readyState = FakeWebSocket.OPEN;
            this.onopen?.();
            if (/\/ws\/terminal/.test(url)) {
              window.__terminalUrls.push(url);
              const command = new URL(url).searchParams.get('cmd') || '';
              const body = command.includes('__NEMOCLAW_CONNECTION_READY__')
                ? '__NEMOCLAW_CONNECTION_READY__\n'
                : command.endsWith('http://127.0.0.1/healthz')
                ? JSON.stringify({ status: 'ok' })
                : JSON.stringify({ agent: { dashboardUrl: '/#token=pomerium-probe-token_456' } });
              this.emit({ type: 'data', data: body }, 1);
              this.emit({ type: 'exit', code: 0 }, 2);
              setTimeout(() => this.close(), 3);
              return;
            }
            window.__gatewayUrls.push(url);
            this.emit({ type: 'event', event: 'connect.challenge', payload: {} });
          }, 0);
        }
        emit(frame, delay = 0) { setTimeout(() => this.onmessage?.({ data: JSON.stringify(frame) }), delay); }
        response(id, payload = {}) { this.emit({ type: 'res', id, ok: true, payload }); }
        send(raw) {
          const request = JSON.parse(raw);
          if (request.method === 'connect' || request.method === 'sessions.messages.subscribe') {
            this.response(request.id, {}); return;
          }
          if (request.method === 'chat.abort') { this.response(request.id, {}); return; }
          if (request.method !== 'chat.send') return;
          const runId = 'run-' + request.id;
          const sessionKey = request.params.sessionKey;
          const frame = (stream, data) => ({
            type: 'event', event: 'agent',
            payload: { runId, sessionKey, stream, data },
          });
          this.response(request.id, { runId });
          if (request.params.message === 'empty-turn') {
            this.emit(frame('lifecycle', { phase: 'end' }), 5); return;
          }
          if (request.params.message === 'final-only') {
            this.emit({ type: 'event', event: 'chat', payload: {
              runId, state: 'final', message: { content: [{ text: 'final-only answer' }] },
            } }, 5); return;
          }
          const noise = '/bin/bash: 1: cannot create /proc/self/oom_score_adj: Permission denied';
          this.emit(frame('tool', { phase: 'start', toolCallId: 'tool-1', name: 'dir_list', args: {} }), 5);
          this.emit(frame('tool', { phase: 'result', toolCallId: 'tool-1', name: 'dir_list', isError: true,
            result: { content: [{ text: `Validation failed for tool "dir_list": required properties node, path\n${noise}\nretry with exec` }] } }), 10);
          this.emit(frame('assistant', { text: 'final answer' }), 12);
          this.emit(frame('lifecycle', { phase: 'end' }), 15);
          this.emit({ type: 'event', event: 'chat', payload: {
            runId, state: 'final', message: { content: [{ text: 'final answer after tools' }] },
          } }, 25);
        }
        close() { this.readyState = 3; this.onclose?.(); }
      }
      Object.defineProperty(window, 'WebSocket', { configurable: true, value: FakeWebSocket });
    } catch (_) {}
  });
  await page.route('https://openclaw-cors-proxy.experiments.courses.nvidia.com/**', async route => {
    const url = route.request().url();
    const headers = route.request().headers();
    const legacyCloudflare = headers['cf-access-jwt-assertion'] || '';
    probeRequests.push({
      url,
      provider: headers['x-openclaw-access-provider'] || (legacyCloudflare ? 'cloudflare' : ''),
      session: headers['x-openclaw-access-session'] || legacyCloudflare,
      authorization: headers.authorization || '',
    });
    if (url.endsWith('/healthz')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'ok' }) });
      return;
    }
    if (url.endsWith('/api/agent')) {
      if (headers['x-openclaw-access-session'] === 'rejected-session') {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Unauthenticated', request_id: 'request-test' }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ agent: { dashboardUrl: '/#token=probe-token_123' } }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'text/html', body: '<html><title>OpenClaw Control</title><body><openclaw-app></openclaw-app></body></html>' });
  });
  await page.goto(`http://127.0.0.1:${port}/nemoclaw/03a-kickstart.html`, { waitUntil: 'networkidle' });
  await page.waitForSelector('#probe-llm .claw-url');
  await page.waitForSelector('#probe-claw .claw-url');
  await page.evaluate(() => {
    const host = document.querySelector('#probe-claw');
    if (!host.querySelector('.claw-access-session') || !host.querySelector('.claw-audit-run')) {
      throw new Error('connection audit did not expose Base URL, Access session, and one run control');
    }
    if (host.querySelector('.claw-token') || host.querySelector('.claw-access-provider') ||
        host.querySelector('.claw-ws-relay-enabled') || host.querySelector('.claw-proxy-enabled')) {
      throw new Error('connection audit exposed a derived credential or transport control');
    }
    const url = host.querySelector('.claw-url');
    const session = host.querySelector('.claw-access-session');
    url.value = 'https://nemoclaw-test123.brevlab.com/chat?session=main';
    url.dispatchEvent(new Event('input'));
    session.value = 'test-access-session';
    session.dispatchEvent(new Event('input'));
    host.querySelector('.claw-audit-run').click();
  });
  await page.waitForFunction(() => {
    const state = document.querySelector('#probe-claw .claw-connection-audit')?.dataset.state;
    return state === 'succeeded' || state === 'failed';
  }, null, { timeout: 65000 });
  const connectionAudit = await page.evaluate(() => {
    const host = document.querySelector('#probe-claw');
    const raw = [...host.querySelectorAll('.claw-audit-raw code')].map(node => node.textContent || '').join('\n');
    return {
      statuses: [...host.querySelectorAll('.claw-audit-step')].map(node => node.dataset.status),
      summary: host.querySelector('.claw-audit-summary')?.textContent || '',
      raw,
    };
  });
  ok(connectionAudit.statuses.length === 4 &&
     connectionAudit.statuses.every(status => status === 'passed') &&
     /Connection ready/.test(connectionAudit.summary) &&
     !connectionAudit.raw.includes('test-access-session'),
    `guided connection audit did not pass and redact all required routes: ${JSON.stringify(connectionAudit)}`);

  // Keep the older endpoint-probe fixture as a lower-level transport regression test.
  // Learners see only the guided audit verified above.
  probeRequests.length = 0;
  await page.evaluate(async () => {
    window.__terminalUrls = [];
    window.__gatewayUrls = [];
    const host = document.querySelector('#probe-claw');
    const mod = await import('/nemoclaw/scripts/_openclaw.js?endpoint-fixture=' + Date.now());
    const shared = await import('/nemoclaw/scripts/_shared.js?endpoint-fixture=' + Date.now());
    shared.setOpenClawConnection({
      rawUrl: 'https://nemoclaw-test123.brevlab.com',
      token: '',
      accessProvider: 'auto',
      accessSession: '',
    });
    mod.mountClawProbe(host, {
      label: 'Transport fixture',
      defaultUrl: '',
      defaultToken: '',
      syncCanvas: true,
      cfAccess: true,
      wsRelayControls: true,
      autofillToken: mod.gatewayTokenFromAgentMetadata,
      actions: [
        { label: 'GET /healthz', path: '/healthz', method: 'GET', expectJson: true },
        { label: 'GET /api/agent', path: '/api/agent', method: 'GET', expectJson: true },
      ],
    });
  });
  const result = await page.evaluate(async () => {
    const approved = 'https://openclaw-cors-proxy.experiments.courses.nvidia.com';
    const modelHost = document.querySelector('#probe-llm');
    const host = document.querySelector('#probe-claw');
    const modelUrl = modelHost.querySelector('.claw-url');
    const modelToken = modelHost.querySelector('.claw-token');
    const modelKind = modelHost.querySelector('.claw-probe')?.dataset.connectionKind;
    if (modelUrl.value !== 'https://model-test123.example.test/v1') throw new Error('model endpoint was contaminated by launchable state: ' + modelUrl.value);
    if (!modelUrl.readOnly || !modelToken.readOnly || modelKind !== 'model') throw new Error('model endpoint probe is not an explicit read-only model mirror');
    const visibleModelRoutes = (document.querySelector('#model-route-settings')?.textContent || '')
      .match(/https:\/\/model-test123\.example\.test\/v1/g) || [];
    if (visibleModelRoutes.length !== 1 || visibleModelRoutes[0] !== modelUrl.value) throw new Error('model route source is not visible above the probe');
    if (Object.keys(localStorage).some(key => key.startsWith('nemoclaw_clawurl:https_model'))) throw new Error('model probe wrote an OpenClaw-scoped URL');

    const url = host.querySelector('.claw-url');
    const provider = host.querySelector('.claw-access-provider');
    const session = host.querySelector('.claw-access-session');
    if (host.querySelector('.claw-proxy-enabled') || host.querySelector('.claw-proxy-base')) {
      throw new Error('learner probe exposed a relay override');
    }
    const wsRelay = host.querySelector('.claw-ws-relay-enabled');
    if (!wsRelay || wsRelay.checked) {
      throw new Error('transport fixture lacks an off-by-default WebSocket recovery control');
    }
    const state = () => ({
      model: modelUrl.value,
      input: url.value,
      raw: localStorage.getItem('nemoclaw_clawrawurl'),
      effective: localStorage.getItem('nemoclaw_clawurl'),
      provider: provider.value,
      sessionPlaceholder: session.placeholder,
    });
    const migrated = state();
    if (migrated.input !== 'https://nemoclaw-test123.brevlab.com') throw new Error('visible URL was not healed');
    if (migrated.raw !== migrated.input) throw new Error('raw saved URL was not healed');
    if (migrated.provider !== 'auto' || !/CF_Authorization/.test(migrated.sessionPlaceholder)) throw new Error('Cloudflare launchable was not inferred from the URL');
    if (migrated.effective !== approved + '/https/nemoclaw-test123.brevlab.com') throw new Error('effective URL did not migrate');
    if (migrated.effective.includes('workers.dev')) throw new Error('retired worker survived migration');

    const connection = await import('/nemoclaw/scripts/_connection.js?relay-boundary=' + Date.now());
    let disableRejected = false;
    try { connection.setOpenClawProxyConfig({ enabled: false }); }
    catch (_) { disableRejected = true; }
    let overrideRejected = false;
    try { connection.setOpenClawProxyConfig({ base: 'https://relay.example.test' }); }
    catch (_) { overrideRejected = true; }
    const protectedState = state();
    if (!disableRejected || !overrideRejected ||
        protectedState.effective !== approved + '/https/nemoclaw-test123.brevlab.com') {
      throw new Error('approved relay boundary was bypassed: ' + JSON.stringify({ disableRejected, overrideRejected, protectedState }));
    }
    if (connection.getOpenClawWsRelayEnabled()) {
      throw new Error('WebSocket relay did not default off');
    }
    connection.setOpenClawWsRelayEnabled(true);
    if (!connection.getOpenClawWsRelayEnabled()) {
      throw new Error('operator WebSocket relay opt-in was not retained');
    }
    const relayedGateway = (await import('/nemoclaw/scripts/_openclaw.js?relay-ui=' + Date.now()))
      .openclawGatewayWsUrl(url.value, 'test-access-session', null, null, 'cloudflare');
    if (!relayedGateway.viaProxy || !relayedGateway.url.includes('cf_access_jwt=')) {
      throw new Error('operator recovery control did not select the approved Cloudflare relay');
    }
    connection.setOpenClawWsRelayEnabled(false);
    session.value = 'test-access-session';
    session.dispatchEvent(new Event('input'));
    host.querySelector('.claw-token').value = 'retained-gateway-token';
    host.querySelector('.claw-token').dispatchEvent(new Event('input'));
    return { migrated, disableRejected, overrideRejected, protectedState };
  });
  result.autoBootstrap = await page.evaluate(async () => {
    const mod = await import('/nemoclaw/scripts/_openclaw.js?auto-bootstrap=' + Date.now());
    const before = sessionStorage.getItem('nemoclaw_clawtoken');
    const refreshed = await mod.refreshOpenClawGatewayToken({ maxAgeMs: 0 });
    return {
      before,
      token: refreshed.token,
      source: refreshed.source,
      changed: refreshed.changed,
      saved: sessionStorage.getItem('nemoclaw_clawtoken'),
      local: localStorage.getItem('nemoclaw_clawtoken'),
    };
  });
  ok(result.autoBootstrap.before === 'retained-gateway-token' &&
     result.autoBootstrap.token === 'probe-token_123' &&
     result.autoBootstrap.saved === result.autoBootstrap.token &&
     result.autoBootstrap.source === 'metadata' && result.autoBootstrap.changed &&
     !result.autoBootstrap.local,
    `gateway bootstrap did not replace stale tab state from /api/agent: ${JSON.stringify(result.autoBootstrap)}`);
  await page.getByRole('button', { name: 'GET /healthz', exact: true }).click();
  await page.waitForFunction(() => /"status":\s*"ok"/.test(document.querySelector('#probe-claw .claw-out')?.textContent || ''));
  await page.getByRole('button', { name: 'GET /api/agent', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#probe-claw .claw-token')?.value === 'probe-token_123');
  result.probeActions = await page.evaluate(() => ({
    token: document.querySelector('#probe-claw .claw-token')?.value,
    savedToken: sessionStorage.getItem('nemoclaw_clawtoken'),
    leakedToken: localStorage.getItem('nemoclaw_clawtoken'),
    output: document.querySelector('#probe-claw .claw-out')?.textContent || '',
    visibleHtmlFrame: !!document.querySelector('#probe-claw .claw-html-frame:not([hidden])'),
  }));
  const expectedProbeRequests = [
    'https://openclaw-cors-proxy.experiments.courses.nvidia.com/https/nemoclaw-test123.brevlab.com/api/agent',
    'https://openclaw-cors-proxy.experiments.courses.nvidia.com/https/nemoclaw-test123.brevlab.com/healthz',
    'https://openclaw-cors-proxy.experiments.courses.nvidia.com/https/nemoclaw-test123.brevlab.com/api/agent',
  ];
  ok(JSON.stringify(probeRequests.map(item => item.url)) === JSON.stringify(expectedProbeRequests),
    `probe dropped or changed its API path: ${JSON.stringify(probeRequests)}`);
  ok(probeRequests.every(item => item.provider === 'cloudflare' && item.session === 'test-access-session'),
    `Cloudflare probe did not use neutral access headers: ${JSON.stringify(probeRequests)}`);
  ok(!probeRequests[0].authorization && probeRequests[1].authorization && !probeRequests[2].authorization,
    `token discovery forwarded a retained bearer token: ${JSON.stringify(probeRequests)}`);
  ok(result.probeActions.token === 'probe-token_123' &&
     result.probeActions.savedToken === result.probeActions.token && !result.probeActions.leakedToken,
    `GET /api/agent did not update the bearer token: ${JSON.stringify(result.probeActions)}`);
  ok(!result.probeActions.visibleHtmlFrame && /dashboardUrl/.test(result.probeActions.output),
    `API probe rendered HTML instead of JSON status: ${JSON.stringify(result.probeActions)}`);
  // Gateway sockets accumulate across the whole page session, and each provider phase
  // has its own correct route. Close one phase before opening the next so a later
  // assertion cannot be satisfied by an earlier phase's socket, or fail because of it.
  result.cloudflareGatewayUrls = await page.evaluate(() => {
    const seen = window.__gatewayUrls.slice();
    window.__gatewayUrls = [];
    return seen;
  });
  ok(result.cloudflareGatewayUrls.length > 0 &&
     result.cloudflareGatewayUrls.every(url =>
       /^wss:\/\/nemoclaw-test123\.brevlab\.com\/cli\/gateway$/.test(url)) &&
     result.cloudflareGatewayUrls.every(url => !/access_session|cf_access_jwt|_pomerium/.test(url)),
    `Cloudflare gateway sockets did not keep authentication sender-bound: ${JSON.stringify(result.cloudflareGatewayUrls)}`);
  await page.evaluate(() => {
    const host = document.querySelector('#probe-claw');
    const url = host.querySelector('.claw-url');
    url.value = 'https://nemoclaw-test123.apps.run.brev.nvidia.com/chat?session=main';
    url.dispatchEvent(new Event('input'));
  });
  await page.waitForFunction(() => {
    const session = document.querySelector('#probe-claw .claw-access-session');
    return session?.closest('.claw-access-session-row')?.dataset.sessionState === 'manual';
  });
  result.pomerium = await page.evaluate(async () => {
    const host = document.querySelector('#probe-claw');
    const provider = host.querySelector('.claw-access-provider');
    const session = host.querySelector('.claw-access-session');
    if (session.value || host.querySelector('.claw-token').value) throw new Error('credentials survived a launchable URL change');
    if (localStorage.getItem('nemoclaw_openclaw_access_session_v1') || localStorage.getItem('nemoclaw_clawtoken')) throw new Error('rotated credentials survived in localStorage');
    if (provider.value !== 'auto' || !/paste the _pomerium cookie value/.test(session.placeholder)) throw new Error('Pomerium manual fallback was not exposed after detection failed');
    if (session.disabled || session.value) throw new Error('Pomerium manual fallback was not writable');
    provider.value = 'cloudflare';
    provider.dispatchEvent(new Event('change'));
    if (!provider.validationMessage) throw new Error('provider mismatch was not rejected in the UI');
    provider.value = 'pomerium';
    provider.dispatchEvent(new Event('change'));
    if (provider.validationMessage) throw new Error('matching Pomerium provider remained invalid');
    session.value = 'test-pomerium-session';
    session.dispatchEvent(new Event('input'));
    const shared = await import('/nemoclaw/scripts/_shared.js?pomerium-manual=' + Date.now());
    const routing = await import('/nemoclaw/scripts/_connection.js?pomerium-manual=' + Date.now());
    const connection = shared.getOpenClawConnection();
    return {
      raw: localStorage.getItem('nemoclaw_clawrawurl'),
      effective: localStorage.getItem('nemoclaw_clawurl'),
      provider: localStorage.getItem('nemoclaw_openclaw_access_provider_v1'),
      localSession: localStorage.getItem('nemoclaw_openclaw_access_session_v1'),
      tabSession: sessionStorage.getItem('nemoclaw_openclaw_access_session_v1'),
      routed: routing.openclawHttpUrl(
        connection.rawUrl,
        '',
        connection.proxy,
        connection.accessProvider,
        connection.accessSession,
      ),
    };
  });
  ok(result.pomerium.raw === 'https://nemoclaw-test123.apps.run.brev.nvidia.com' &&
     result.pomerium.effective === APPROVED_RELAY + '/https/nemoclaw-test123.apps.run.brev.nvidia.com' &&
     result.pomerium.provider === 'pomerium' && !result.pomerium.localSession &&
     result.pomerium.tabSession === 'test-pomerium-session',
    `Pomerium launchable did not persist through the visible controls: ${JSON.stringify(result.pomerium)}`);
  await page.getByRole('button', { name: 'GET /healthz', exact: true }).click();
  await page.waitForFunction(() => /"status":\s*"ok"/.test(document.querySelector('#probe-claw .claw-out')?.textContent || ''));
  await page.getByRole('button', { name: 'GET /api/agent', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#probe-claw .claw-token')?.value === 'probe-token_123');
  const pomeriumRequests = probeRequests.filter(item =>
    item.url.includes('/https/nemoclaw-test123.apps.run.brev.nvidia.com/'));
  ok(pomeriumRequests.length === 2 &&
     pomeriumRequests.every(item =>
       item.provider === 'pomerium' && item.session === 'test-pomerium-session'),
    `Pomerium manual session did not reach the relay through neutral headers: ${JSON.stringify(pomeriumRequests)}`);
  result.pomeriumTransport = await page.evaluate(() => {
    const gatewayUrls = window.__gatewayUrls.slice();
    window.__gatewayUrls = [];
    return {
      urls: window.__terminalUrls.slice(),
      gatewayUrls,
      token: document.querySelector('#probe-claw .claw-token')?.value,
      savedToken: sessionStorage.getItem('nemoclaw_clawtoken'),
      localToken: localStorage.getItem('nemoclaw_clawtoken'),
      output: document.querySelector('#probe-claw .claw-out')?.textContent || '',
    };
  });
  ok(result.pomeriumTransport.gatewayUrls.length > 0 &&
     result.pomeriumTransport.gatewayUrls.every(url =>
       /^wss:\/\/openclaw-cors-proxy\.experiments\.courses\.nvidia\.com\/https\/nemoclaw-test123\.apps\.run\.brev\.nvidia\.com\/cli\/gateway\?access_provider=pomerium&access_session=test-pomerium-session$/.test(url)),
    `Pomerium manual-session gateway did not use the provider-bound relay: ${JSON.stringify(result.pomeriumTransport.gatewayUrls)}`);
  ok(result.pomeriumTransport.urls.length === 0 &&
     result.pomeriumTransport.token === 'probe-token_123' &&
     result.pomeriumTransport.savedToken === result.pomeriumTransport.token &&
     !result.pomeriumTransport.localToken &&
     /via hosted relay/.test(result.pomeriumTransport.output) &&
     !/test-pomerium-session/.test(result.pomeriumTransport.output),
    `Pomerium manual-session bootstrap did not use the redacted relay route: ${JSON.stringify(result.pomeriumTransport)}`);
  result.detectedPomerium = await page.evaluate(() => {
    const host = document.querySelector('#probe-claw');
    const session = host.querySelector('.claw-access-session');
    window.__pomeriumDirectSession = true;
    session.value = '';
    session.dispatchEvent(new Event('input'));
    window.dispatchEvent(new Event('focus'));
    return true;
  });
  await page.waitForFunction(() => {
    const session = document.querySelector('#probe-claw .claw-access-session');
    return session?.disabled && /session detected/.test(session.placeholder);
  });
  result.detectedPomerium = await page.evaluate(() => {
    const session = document.querySelector('#probe-claw .claw-access-session');
    return {
      state: session.closest('.claw-access-session-row')?.dataset.sessionState,
      disabled: session.disabled,
      placeholder: session.placeholder,
      tabSession: sessionStorage.getItem('nemoclaw_openclaw_access_session_v1'),
    };
  });
  ok(result.detectedPomerium.state === 'detected' &&
     result.detectedPomerium.disabled &&
     /signed-in browser session detected; nothing to paste/.test(result.detectedPomerium.placeholder) &&
     !result.detectedPomerium.tabSession,
    `Pomerium direct-session success was not bound to a live challenge: ${JSON.stringify(result.detectedPomerium)}`);
  // The model route and the launchable route stay separate registrations: a launchable host
  // is not an OpenAI-compatible model API, so the model normalizer must refuse both families.
  result.modelRouteBoundary = await page.evaluate(async () => {
    const shared = await import('/nemoclaw/scripts/_shared.js?model-boundary=' + Date.now());
    const attempt = value => {
      try { return { url: shared.normalizeModelApiBaseUrl(value), error: '' }; }
      catch (error) { return { url: '', error: String(error.message || error) }; }
    };
    return {
      pomerium: attempt('https://nemoclaw-test123.apps.run.brev.nvidia.com/v1'),
      cloudflare: attempt('https://nemoclaw-test123.brevlab.com/v1'),
      supported: attempt('https://integrate.api.nvidia.com/v1'),
      custom: attempt('https://model-test123.example.test/v1'),
    };
  });
  ok(/launchable is not a model API/.test(result.modelRouteBoundary.pomerium.error) &&
     /launchable is not a model API/.test(result.modelRouteBoundary.cloudflare.error) &&
     !/port|tunnel|EMPTY/i.test(result.modelRouteBoundary.cloudflare.error) &&
     result.modelRouteBoundary.supported.url === 'https://integrate.api.nvidia.com/v1' &&
     result.modelRouteBoundary.custom.url === 'https://model-test123.example.test/v1',
    `model route did not reject launchable hosts cleanly: ${JSON.stringify(result.modelRouteBoundary)}`);
  result.chatContract = await page.evaluate(async () => {
    const mod = await import('/nemoclaw/scripts/_openclaw.js?chat-contract=' + Date.now());
    const connection = await import('/nemoclaw/scripts/_connection.js?chat-contract=' + Date.now());
    connection.setOpenClawConnection({
      rawUrl: 'https://nemoclaw-test123.brevlab.com',
      token: 'test-token',
      accessProvider: 'cloudflare',
      accessSession: 'chat-test-cf-session',
    });
    window.__gatewayUrls = [];
    const run = async (message, session) => {
      const tokens = [], tools = [];
      const view = {
        token: value => tokens.push(value),
        tool: (label, body) => {
          const node = document.createElement('details');
          const summary = document.createElement('summary'); summary.textContent = '🔧 ' + label;
          const output = document.createElement('div'); output.className = 'chatui-tool-body'; output.textContent = body;
          node.append(summary, output); tools.push(node); return node;
        },
        usage: () => {},
      };
      const text = await mod.openclawChat(message, { session, view, finalGraceMs: 50, idleMs: 1000, totalMs: 2000 });
      return { text, tokens: tokens.join(''), tools: tools.map(node => ({
        label: node.querySelector('summary')?.textContent || '',
        body: node.querySelector('.chatui-tool-body')?.textContent || '',
        error: node.classList.contains('err'),
      })) };
    };
    const result = {
      afterTools: await run('final-after-end', 'chat-contract-tools'),
      finalOnly: await run('final-only', 'chat-contract-final'),
      empty: await run('empty-turn', 'chat-contract-empty'),
    };
    result.gatewayUrls = window.__gatewayUrls.slice();
    return result;
  });
  const toolResult = result.chatContract.afterTools.tools[0] || {};
  ok(result.chatContract.afterTools.text === 'final answer after tools' &&
     result.chatContract.afterTools.tokens === 'final answer after tools',
    `chat.final was lost after lifecycle end: ${JSON.stringify(result.chatContract.afterTools)}`);
  ok(toolResult.error && /Validation failed/.test(toolResult.body) && /retry with exec/.test(toolResult.body),
    `actionable dir_list validation evidence was hidden: ${JSON.stringify(toolResult)}`);
  ok(!/oom_score_adj/.test(toolResult.body), `sandbox bootstrap noise remained in tool output: ${JSON.stringify(toolResult)}`);
  ok(result.chatContract.finalOnly.text === 'final-only answer' && result.chatContract.finalOnly.tokens === 'final-only answer',
    `final-only gateway text did not reach the UI: ${JSON.stringify(result.chatContract.finalOnly)}`);
  ok(/without a displayable reply/.test(result.chatContract.empty.text) &&
     !/\(no answer\)/.test(result.chatContract.empty.tokens),
    `empty gateway turn retained the no-answer dead end: ${JSON.stringify(result.chatContract.empty)}`);
  ok(result.chatContract.gatewayUrls.length > 0 &&
     result.chatContract.gatewayUrls.every(url =>
       /^wss:\/\/nemoclaw-test123\.brevlab\.com\/cli\/gateway$/.test(url)) &&
     result.chatContract.gatewayUrls.every(url => !/access_session|cf_access_jwt|_pomerium/.test(url)),
    `Cloudflare chat sockets did not keep authentication sender-bound: ${JSON.stringify(result.chatContract.gatewayUrls)}`);
  ok(!errors.length, `page errors: ${JSON.stringify(errors)}`);
  if (screenshot) {
    await page.locator('#model-route-settings').scrollIntoViewIfNeeded();
    await page.screenshot({ path: screenshot, fullPage: false });
  }
  console.log(JSON.stringify({ ok: true, result }, null, 2));
  await browser.close();
} finally {
  server.close();
}
