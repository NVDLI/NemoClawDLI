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
      localStorage.setItem('nemoclaw_model_api_base_url_v1', 'https://model-test123.brevlab.com/v1');
      localStorage.setItem('nemoclaw_model_id_v1', 'model/test-123');
      sessionStorage.setItem('nvapi', 'EMPTY');
      localStorage.removeItem('nemoclaw_clawrawurl');
      localStorage.setItem('nemoclaw_clawurl', retired);
      window.__terminalUrls = [];
      window.__gatewayUrls = [];
      class FakeWebSocket {
        static OPEN = 1;
        constructor(url) {
          this.url = url; this.readyState = 0; this.onmessage = null; this.onopen = null; this.onclose = null;
          setTimeout(() => {
            this.readyState = FakeWebSocket.OPEN;
            this.onopen?.();
            if (/\/ws\/terminal/.test(url)) {
              window.__terminalUrls.push(url);
              const command = new URL(url).searchParams.get('cmd') || '';
              const body = command.endsWith('http://127.0.0.1/healthz')
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
  const result = await page.evaluate(() => {
    const approved = 'https://openclaw-cors-proxy.experiments.courses.nvidia.com';
    const modelHost = document.querySelector('#probe-llm');
    const host = document.querySelector('#probe-claw');
    const modelUrl = modelHost.querySelector('.claw-url');
    const modelToken = modelHost.querySelector('.claw-token');
    const modelKind = modelHost.querySelector('.claw-probe')?.dataset.connectionKind;
    if (modelUrl.value !== 'https://model-test123.brevlab.com/v1') throw new Error('model endpoint was contaminated by launchable state: ' + modelUrl.value);
    if (!modelUrl.readOnly || !modelToken.readOnly || modelKind !== 'model') throw new Error('model endpoint probe is not an explicit read-only model mirror');
    const visibleModelRoutes = (document.querySelector('#model-route-settings')?.textContent || '')
      .match(/https:\/\/model-test123\.brevlab\.com\/v1/g) || [];
    if (visibleModelRoutes.length !== 1 || visibleModelRoutes[0] !== modelUrl.value) throw new Error('model route source is not visible above the probe');
    if (Object.keys(localStorage).some(key => key.startsWith('nemoclaw_clawurl:https_model'))) throw new Error('model probe wrote an OpenClaw-scoped URL');

    const url = host.querySelector('.claw-url');
    const toggle = host.querySelector('.claw-proxy-enabled');
    const relay = host.querySelector('.claw-proxy-base');
    const provider = host.querySelector('.claw-access-provider');
    const session = host.querySelector('.claw-access-session');
    const state = () => ({
      model: modelUrl.value,
      input: url.value,
      raw: localStorage.getItem('nemoclaw_clawrawurl'),
      effective: localStorage.getItem('nemoclaw_clawurl'),
      enabled: toggle.checked,
      relay: relay.value,
      provider: provider.value,
      sessionPlaceholder: session.placeholder,
    });
    const migrated = state();
    if (migrated.input !== 'https://nemoclaw-test123.brevlab.com') throw new Error('visible URL was not healed');
    if (migrated.raw !== migrated.input) throw new Error('raw saved URL was not healed');
    if (!migrated.enabled || migrated.relay !== approved) throw new Error('approved relay is not the visible default');
    if (migrated.provider !== 'auto' || !/CF_Authorization/.test(migrated.sessionPlaceholder)) throw new Error('Cloudflare launchable was not inferred from the URL');
    if (migrated.effective !== approved + '/https/nemoclaw-test123.brevlab.com') throw new Error('effective URL did not migrate');
    if (migrated.effective.includes('workers.dev')) throw new Error('retired worker survived migration');

    toggle.checked = false;
    toggle.dispatchEvent(new Event('change'));
    const direct = state();
    if (direct.effective !== direct.raw || !relay.disabled) throw new Error('relay off did not select direct mode: ' + JSON.stringify(direct));

    toggle.checked = true;
    toggle.dispatchEvent(new Event('change'));
    const restored = state();
    if (restored.effective !== approved + '/https/nemoclaw-test123.brevlab.com' || relay.disabled) throw new Error('relay on did not restore approved route: ' + JSON.stringify(restored));
    session.value = 'test-access-session';
    session.dispatchEvent(new Event('input'));
    host.querySelector('.claw-token').value = 'retained-gateway-token';
    host.querySelector('.claw-token').dispatchEvent(new Event('input'));
    return { migrated, direct, restored };
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
  result.pomerium = await page.evaluate(() => {
    const host = document.querySelector('#probe-claw');
    const url = host.querySelector('.claw-url');
    const provider = host.querySelector('.claw-access-provider');
    const session = host.querySelector('.claw-access-session');
    url.value = 'https://nemoclaw-test123.apps.run.brev.nvidia.com/chat?session=main';
    url.dispatchEvent(new Event('input'));
    if (session.value || host.querySelector('.claw-token').value) throw new Error('credentials survived a launchable URL change');
    if (localStorage.getItem('nemoclaw_openclaw_access_session_v1') || localStorage.getItem('nemoclaw_clawtoken')) throw new Error('rotated credentials survived in localStorage');
    if (provider.value !== 'auto' || !/signed-in browser session/.test(session.placeholder)) throw new Error('Pomerium launchable was not inferred from the URL');
    if (!session.disabled || session.value) throw new Error('Pomerium cookie input remained writable');
    provider.value = 'cloudflare';
    provider.dispatchEvent(new Event('change'));
    if (!provider.validationMessage) throw new Error('provider mismatch was not rejected in the UI');
    provider.value = 'pomerium';
    provider.dispatchEvent(new Event('change'));
    if (provider.validationMessage) throw new Error('matching Pomerium provider remained invalid');
    return {
      raw: localStorage.getItem('nemoclaw_clawrawurl'),
      effective: localStorage.getItem('nemoclaw_clawurl'),
      provider: localStorage.getItem('nemoclaw_openclaw_access_provider_v1'),
      localSession: localStorage.getItem('nemoclaw_openclaw_access_session_v1'),
      tabSession: sessionStorage.getItem('nemoclaw_openclaw_access_session_v1'),
    };
  });
  ok(result.pomerium.raw === 'https://nemoclaw-test123.apps.run.brev.nvidia.com' &&
     result.pomerium.effective === 'https://nemoclaw-test123.apps.run.brev.nvidia.com' &&
     result.pomerium.provider === 'pomerium' && !result.pomerium.localSession && !result.pomerium.tabSession,
    `Pomerium launchable did not persist through the visible controls: ${JSON.stringify(result.pomerium)}`);
  await page.getByRole('button', { name: 'GET /healthz', exact: true }).click();
  await page.waitForFunction(() => /"status":\s*"ok"/.test(document.querySelector('#probe-claw .claw-out')?.textContent || ''));
  await page.getByRole('button', { name: 'GET /api/agent', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('#probe-claw .claw-token')?.value === 'pomerium-probe-token_456');
  result.pomeriumTransport = await page.evaluate(() => ({
    urls: window.__terminalUrls.slice(),
    token: document.querySelector('#probe-claw .claw-token')?.value,
    savedToken: sessionStorage.getItem('nemoclaw_clawtoken'),
    localToken: localStorage.getItem('nemoclaw_clawtoken'),
    output: document.querySelector('#probe-claw .claw-out')?.textContent || '',
  }));
  ok(result.pomeriumTransport.urls.length === 2 &&
     result.pomeriumTransport.urls.every(url => url.startsWith('wss://nemoclaw-test123.apps.run.brev.nvidia.com/ws/terminal?cmd=')) &&
     result.pomeriumTransport.urls.every(url => !/openclaw-cors-proxy|access_session|cf_access_jwt/.test(url)) &&
     result.pomeriumTransport.token === 'pomerium-probe-token_456' &&
     result.pomeriumTransport.savedToken === result.pomeriumTransport.token &&
     !result.pomeriumTransport.localToken &&
     /direct browser session/.test(result.pomeriumTransport.output),
    `Pomerium bootstrap did not stay on the direct terminal: ${JSON.stringify(result.pomeriumTransport)}`);
  result.chatContract = await page.evaluate(async () => {
    const mod = await import('/nemoclaw/scripts/_openclaw.js?chat-contract=' + Date.now());
    const connection = await import('/nemoclaw/scripts/_connection.js?chat-contract=' + Date.now());
    connection.setOpenClawConnection({ rawUrl: 'https://nemoclaw-test123.brevlab.com', token: 'test-token' });
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
     result.chatContract.gatewayUrls.every(url => /^wss:\/\/nemoclaw-test123(?:\.brevlab\.com|\.apps\.run\.brev\.nvidia\.com)\/cli\/gateway$/.test(url)) &&
     result.chatContract.gatewayUrls.every(url => !/openclaw-cors-proxy|cf_access_jwt|access_session/.test(url)),
    `gateway sockets did not stay direct and credential-free: ${JSON.stringify(result.chatContract.gatewayUrls)}`);
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
