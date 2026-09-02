#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise high-risk course runtime handoffs in host-native Chromium."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.runtime.host_browser import BrowserRuntimeError, environment, run_node

RUNTIME_JS = r"""
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const root = process.env.SITE_ROOT || '/site';
const port = Number(process.env.SITE_PORT || 4198);
const timeoutMs = Number(process.env.AUDIT_TIMEOUT_MS || 120000);
const retiredBillingHeader = 'x-billing-' + 'source';
const mime = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.json':'application/json; charset=utf-8', '.svg':'image/svg+xml', '.png':'image/png', '.woff2':'font/woff2' };

function safeJoin(base, urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]).replace(/^\/+/, '');
  const out = path.resolve(base, clean);
  if (!out.startsWith(path.resolve(base))) throw new Error('path escape');
  return out;
}
const server = http.createServer((req, res) => {
  let file;
  try { file = safeJoin(root, req.url || '/'); } catch (_) { res.writeHead(403); res.end('forbidden'); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found'); return; }
    res.writeHead(200, { 'content-type': mime[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
});
const listen = () => new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
const url = page => `http://127.0.0.1:${port}${page.startsWith('/') ? page : '/nemoclaw/' + page}`;
const fail = message => { throw new Error(message); };

async function open(browser, pageName, init) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message || String(error)));
  if (init) await page.addInitScript(init);
  await page.goto(url(pageName), { waitUntil: 'domcontentloaded', timeout: timeoutMs });
  return { page, errors };
}

(async () => {
  await listen();
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_BIN || undefined,
  });
  const results = {};

  // Shared terminal/console: a failed socket settles once and leaves visible error state.
  {
    const { page, errors } = await open(browser, '01b-react.html');
    results.terminalFailure = await page.evaluate(async () => {
      const connection = await import('./scripts/_connection.js?terminal-audit=' + Date.now());
      const openshell = await import('./scripts/_openshell.js?terminal-audit=' + Date.now());
      const chat = await import('./scripts/_chat.js?terminal-audit=' + Date.now());
      connection.setOpenClawConnection({ rawUrl: 'https://terminal-audit.example.test', token: '', accessJwt: '' });
      const RealWebSocket = window.WebSocket;
      let closeCount = 0;
      class NeverOpeningSocket {
        close() { closeCount++; }
      }
      window.WebSocket = NeverOpeningSocket;
      let terminalError = null;
      const started = performance.now();
      try {
        await openshell.terminal('bash', { openMs: 20, totalMs: 80, idleMs: 10 });
      } catch (error) {
        terminalError = { name: error.name, code: error.code, message: error.message };
      }
      await new Promise(resolve => setTimeout(resolve, 100));
      window.WebSocket = RealWebSocket;

      const host = document.createElement('div');
      document.body.appendChild(host);
      chat.mountConsole(host, {
        onSubmit: async () => ({ status: 'error', message: 'synthetic command failure' }),
      });
      const input = host.querySelector('.da-in');
      input.value = 'fail';
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
      await new Promise(resolve => setTimeout(resolve, 30));
      const state = host.querySelector('.da-console-state');
      return {
        terminalError,
        closeCount,
        elapsedMs: Math.round(performance.now() - started),
        consoleState: state.textContent,
        consoleClass: state.className,
      };
    });
    if (results.terminalFailure.terminalError?.code !== 'TERMINAL_OPEN_TIMEOUT' ||
        results.terminalFailure.terminalError?.name !== 'TerminalConnectionError' ||
        results.terminalFailure.closeCount !== 1 ||
        results.terminalFailure.consoleState !== 'synthetic command failure' ||
        !results.terminalFailure.consoleClass.includes('error')) {
      fail('terminal fail-once/error-state contract failed: ' + JSON.stringify(results.terminalFailure));
    }
    if (errors.length) fail('shared terminal browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // A cross-origin Cloudflare terminal opens one sender-bound direct route and gives it
  // the whole configured open window. The copied relay session is not placed in its URL.
  {
    const { page, errors } = await open(browser, '01b-react.html');
    results.terminalDirectRoute = await page.evaluate(async () => {
      const connection = await import('./scripts/_connection.js?terminal-relay-audit=' + Date.now());
      const openshell = await import('./scripts/_openshell.js?terminal-relay-audit=' + Date.now());
      connection.setOpenClawConnection({
        rawUrl: 'https://nemoclaw-terminal-audit.brevlab.com', token: 'test-token',
        accessProvider: 'cloudflare', accessSession: 'test-cf-session',
      });
      const RealWebSocket = window.WebSocket;
      const urls = [];
      // Open late in the configured window: a route that only receives a shortened
      // budget cannot settle in time, so the full-budget contract is observable.
      class LateOpeningSocket {
        constructor(url) {
          urls.push(url);
          setTimeout(() => this.onopen?.(), 60);
        }
        close() {}
        send() {}
      }
      window.WebSocket = LateOpeningSocket;
      let result = null, error = null;
      try {
        result = await openshell.terminal('bash', { openMs: 400, totalMs: 900, idleMs: 5 });
      } catch (caught) {
        error = caught.message;
      }
      window.WebSocket = RealWebSocket;
      return { urls, result, error };
    });
    if (results.terminalDirectRoute.urls.length !== 1 ||
        results.terminalDirectRoute.urls[0] !==
          'wss://nemoclaw-terminal-audit.brevlab.com/ws/terminal?cmd=bash' ||
        results.terminalDirectRoute.error || !results.terminalDirectRoute.result) {
      fail('terminal sender-bound direct route failed: ' + JSON.stringify(results.terminalDirectRoute));
    }
    if (errors.length) fail('terminal direct-route browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // 1b/1c: execute the shipped same-origin ESM boundary, not only a source grep.
  {
    const { page, errors } = await open(browser, '01b-react.html');
    results.agentBundle = await page.evaluate(async () => {
      const mod = await import('./vendor/langchain-1.4.7.esm.js?runtime-audit=' + Date.now());
      const chat = await import('./scripts/_chat.js?runtime-audit=' + Date.now());
      return {
        exports: ['ChatOpenAI', 'tool', 'createReactAgent', 'MemorySaver', 'z'].filter(name => typeof mod[name] !== 'undefined'),
        mountAgentChat: typeof chat.mountAgentChat,
        origin: location.origin,
      };
    });
    if (results.agentBundle.exports.length !== 5 || results.agentBundle.mountAgentChat !== 'function') {
      fail('same-origin agent bundle contract failed: ' + JSON.stringify(results.agentBundle));
    }
    await page.evaluate(() => {
      sessionStorage.setItem('nvapi', 'nvapi-runtime-audit');
      document.querySelectorAll('details.learning-block').forEach(item => { item.open = true; });
    });
    const artifactCards = page.locator('.rc-card');
    let artifactCard = null;
    for (let index = 0; index < await artifactCards.count(); index++) {
      const card = artifactCards.nth(index);
      const code = await card.locator('.rc-code').inputValue();
      if (code.includes('import(new URL("./vendor/langchain-1.4.7.esm.js", location.href).href)')) {
        artifactCard = card;
        break;
      }
    }
    if (!artifactCard) fail('1b authored LangChain artifact cell was not found');
    await artifactCard.locator('.rc-run').click();
    await page.waitForFunction(() => !/stop/i.test(document.querySelector('#cell-react-lab .rc-run')?.textContent || ''), null, { timeout: timeoutMs });
    const artifactOutput = await artifactCard.locator('.rc-out').innerText();
    if (/TypeError|ReferenceError|Failed to fetch dynamically imported module|^✗/m.test(artifactOutput) ||
        !await page.locator('#react-artifact .chatui').count()) {
      fail('1b authored LangChain artifact cell failed: ' + artifactOutput);
    }
    results.agentBundle.authoredArtifactCell = 'complete';
    if (errors.length) fail('1b browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // Course-wide model routes: one custom chat setup must persist its discovered model while
  // embeddings keep their independent hosted route.
  {
    const { page, errors } = await open(browser, '01a-loop.html');
    await page.locator('#key-panel .model-api-base-url').waitFor({ state: 'visible', timeout: timeoutMs });
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.setItem('nemoclaw_embedding_api_key_v1', 'nvapi-embedding-audit');
      window.__modelRequests = [];
      window.fetch = async (url, init = {}) => {
        const headers = Object.fromEntries(new Headers(init.headers || {}).entries());
        const record = { url: String(url), method: init.method || 'GET', credentials: init.credentials || '', headers, body: init.body || '' };
        window.__modelRequests.push(record);
        if (String(url).endsWith('/models')) return new Response(JSON.stringify({ data: [
          { id: 'nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8' },
        ] }), { status: 200, headers: { 'content-type': 'application/json' } });
        if (String(url).endsWith('/chat/completions')) return new Response(JSON.stringify({
          choices: [{ message: { content: 'ready' }, finish_reason: 'stop' }],
          usage: { prompt_tokens: 1, completion_tokens: 1 },
        }), { status: 200, headers: { 'content-type': 'application/json' } });
        if (String(url).endsWith('/embeddings')) return new Response(JSON.stringify({
          data: [{ embedding: [1, 0, 0] }],
        }), { status: 200, headers: { 'content-type': 'application/json' } });
        return new Response('unexpected ' + url, { status: 500 });
      };
    });
    await page.locator('#key-panel .model-api-base-url').fill('https://sglang.example.test/v1');
    await page.locator('#key-panel .model-api-key').fill('test-model-key');
    await page.locator('#key-panel .btn').click();
    await page.locator('#key-panel .key-panel-saved').waitFor({ state: 'visible', timeout: timeoutMs });
    results.modelRoutes = await page.evaluate(async () => {
      const shared = await import('./scripts/_shared.js?route-audit=' + Date.now());
      const rag = await import('./scripts/_rag.js?route-audit=' + Date.now());
      await shared.chat({
        model: 'nvidia/nemotron-3.5-lightning-30b-a3b',
        messages: [{ role: 'user', content: 'route check' }],
        max_tokens: 8,
      });
      await rag.embed('route check');
      const defaultEmbedding = await shared.getEmbeddingConfig();
      shared.setEmbeddingApiBaseUrl('https://embedding.example.test/v1');
      shared.setEmbeddingModelId('embedding/provider-model');
      shared.setEmbeddingKey('test-embedding-key');
      await rag.embed('custom embedding route', { model: 'nvidia/llama-nemotron-embed-vl-1b-v2' });
      let jupyterError = '';
      try { shared.normalizeModelApiBaseUrl('https://jupyter-example.brevlab.com/lab'); }
      catch (error) { jupyterError = error.message; }
      return {
        chat: await shared.getConfig(),
        embedding: defaultEmbedding,
        customEmbedding: await shared.getEmbeddingConfig(),
        jupyterError,
        requests: window.__modelRequests,
        saved: Object.fromEntries([
          'nemoclaw_model_api_base_url_v1', 'nemoclaw_model_id_v1',
          'nemoclaw_embedding_api_base_url_v1', 'nemoclaw_embedding_model_id_v1',
          'nemoclaw_embedding_api_key_v1', 'nvapi',
        ].map(key => [key, localStorage.getItem(key)])),
      };
    });
    const custom = results.modelRoutes.requests.filter(item => item.url.startsWith('https://sglang.example.test/v1'));
    const chats = custom.filter(item => item.url.endsWith('/chat/completions'));
    const embedding = results.modelRoutes.requests.find(item => item.url === 'https://integrate.api.nvidia.com/v1/embeddings');
    const customEmbedding = results.modelRoutes.requests.find(item => item.url === 'https://embedding.example.test/v1/embeddings');
    if (results.modelRoutes.chat.model !== 'nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8' ||
        results.modelRoutes.embedding.model !== 'nvidia/llama-nemotron-embed-vl-1b-v2' ||
        results.modelRoutes.customEmbedding.model !== 'embedding/provider-model' ||
        !/Jupyter \/lab URL is not a model API/.test(results.modelRoutes.jupyterError) ||
        custom.some(item => item.credentials !== 'include' ||
          'x-billing-invoke-origin' in item.headers || retiredBillingHeader in item.headers) ||
        chats.some(item => JSON.parse(item.body).model !== 'nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8') ||
        !embedding || embedding.credentials !== 'same-origin' ||
        embedding.headers.authorization !== 'Bearer nvapi-embedding-audit' ||
        embedding.headers['x-billing-invoke-origin'] !== 'dli-nemoclaw-web' ||
        retiredBillingHeader in embedding.headers ||
        !customEmbedding || customEmbedding.credentials !== 'include' ||
        customEmbedding.headers.authorization !== 'Bearer test-embedding-key' ||
        JSON.parse(customEmbedding.body).model !== 'embedding/provider-model' ||
        'x-billing-invoke-origin' in customEmbedding.headers ||
        retiredBillingHeader in customEmbedding.headers) {
      fail('persistent model route handoff failed: ' + JSON.stringify(results.modelRoutes));
    }
    if (errors.length) fail('model route browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // Original 2b RAG route: exact model pin, vector shape, and semantic anchor.
  {
    const { page, errors } = await open(browser, '02b-rag.html');
    results.prebuiltRagIndex = await page.evaluate(async () => {
      const rag = await import('./scripts/_rag.js?prebuilt-index-audit=' + Date.now());
      const response = await fetch('./assets/rag_index.json');
      const index = await response.json();
      const query = index.queries.find(row => row.text === 'What is retrieval-augmented generation?');
      const ranked = index.docs
        .map(row => ({ text:row.text, score:rag.cosineSim(query.vec, row.vec) }))
        .sort((left, right) => right.score - left.score);
      return {
        status: response.status,
        model: index.model,
        dim: index.dim,
        docs: index.docs.length,
        queries: index.queries.length,
        shapesValid: [...index.docs, ...index.queries].every(row => row.vec.length === index.dim),
        topText: ranked[0]?.text || '',
        topScore: ranked[0]?.score ?? null,
      };
    });
    if (results.prebuiltRagIndex.status !== 200 ||
        results.prebuiltRagIndex.model !== 'nvidia/llama-nemotron-embed-vl-1b-v2' ||
        results.prebuiltRagIndex.dim !== 2048 ||
        results.prebuiltRagIndex.docs !== 8 || results.prebuiltRagIndex.queries !== 6 ||
        !results.prebuiltRagIndex.shapesValid ||
        !results.prebuiltRagIndex.topText.startsWith('Retrieval-augmented generation embeds')) {
      fail('prebuilt RAG index browser contract failed: ' + JSON.stringify(results.prebuiltRagIndex));
    }
    if (errors.length) fail('prebuilt RAG index browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // Repeated invalid choices must fail visibly. The controller may constrain and explain the
  // next choice, but it must never replace the model with a hidden maze solver.
  {
    const init = () => {
      if (window.top !== window) return;
      localStorage.removeItem('nemoclaw_model_api_base_url_v1');
      localStorage.removeItem('nemoclaw_model_id_v1');
      sessionStorage.setItem('nvapi', 'nvapi-maze-audit');
      window.__mazeRequests = [];
      const originalFetch = window.fetch.bind(window);
      window.fetch = async (input, init = {}) => {
        if (!String(input).endsWith('/chat/completions')) return originalFetch(input, init);
        const body = JSON.parse(String(init.body || '{}'));
        window.__mazeRequests.push(body);
        const id = 'maze-' + window.__mazeRequests.length;
        const frame = JSON.stringify({ choices: [{
          delta: { tool_calls: [{ index: 0, id, type: 'function', function: {
            name: 'choose_direction', arguments: '{"direction":"N"}',
          } }] },
          finish_reason: 'tool_calls',
        }] });
        return new Response('data: ' + frame + '\n\ndata: [DONE]\n\n', {
          status: 200,
          headers: { 'content-type': 'text/event-stream' },
        });
      };
    };
    const { page, errors } = await open(browser, '01a-loop.html', init);
    await page.evaluate(() => {
      const section = document.querySelector('#cell-llm-maze')?.closest('details.learning-block');
      if (section) section.open = true;
    });
    const run = page.locator('#cell-llm-maze .cf-btn-run');
    await run.waitFor({ state: 'visible', timeout: timeoutMs });
    await run.click();
    await page.waitForFunction(() => /Run all/i.test(document.querySelector('#cell-llm-maze .cf-btn-run')?.textContent || ''), null, { timeout: timeoutMs });
    results.mazeLoopBoundary = await page.evaluate(() => {
      const root = document.querySelector('#cell-llm-maze');
      const raw = root?.querySelector('.cf-panel[data-id="run"] .cf-panel-output')?.innerText || '';
      const log = root?.querySelector('.cf-panel[data-id="run"] .cf-panel-log')?.innerText || '';
      const text = root?.innerText || '';
      let result = null;
      try { result = JSON.parse(raw); } catch (_) {}
      return {
        result,
        rejectedChoiceVisible: /No move was executed\. Choose exactly one of:/i.test(log),
        failureVisible: /maze stopped after 20 decisions without reaching the goal/i.test(text),
        falseSuccessVisible: /goal reached by the loop guard|solved with loop guard|shortest-path recovery/i.test(text),
        requestCount: window.__mazeRequests.length,
        allowed: window.__mazeRequests.map(request => request.tools?.[0]?.function?.parameters?.properties?.direction?.enum || []),
      };
    });
    if (results.mazeLoopBoundary.result?.won || results.mazeLoopBoundary.requestCount !== 20 ||
        !results.mazeLoopBoundary.allowed.some(letters => letters.length && !letters.includes('N')) ||
        !results.mazeLoopBoundary.rejectedChoiceVisible || !results.mazeLoopBoundary.failureVisible ||
        results.mazeLoopBoundary.falseSuccessVisible) {
      fail('maze repeated-choice boundary failed: ' + JSON.stringify(results.mazeLoopBoundary));
    }
    if (errors.length) fail('maze repeated-choice browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // SKILL explorer: the explainer must reuse the course model registry instead of a private endpoint.
  {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message || String(error)));
    await page.addInitScript(() => {
      localStorage.setItem('nemoclaw_model_api_base_url_v1', 'https://skill-model.example.test/v1');
      localStorage.setItem('nemoclaw_model_id_v1', 'model/skill-registry');
      sessionStorage.setItem('nvapi', 'test-model-key');
    });
    const fixtureUrl = `http://127.0.0.1:${port}/endpoint-registry-fixture.html`;
    const skillExplorerPath = fs.existsSync(path.join(root, '_skill_explorer.js'))
      ? '/_skill_explorer.js'
      : '/web/_skill_explorer.js';
    await page.route(fixtureUrl, route => route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: `<!doctype html><html><head><meta charset="utf-8"><title>Registry fixture</title></head><body>
        <div id="explorer"></div>
        <script type="application/json" id="explorer-config">{"title":"Registry fixture","files":[{"path":"nemoclaw/scripts/_shared.js","role":"fixture"}]}</script>
        <script src="${skillExplorerPath}"></script>
      </body></html>`,
    }));
    let request = null;
    await page.route('https://skill-model.example.test/**', async route => {
      const body = JSON.parse(route.request().postData() || '{}');
      request = {
        url: route.request().url(),
        headers: route.request().headers(),
        model: body.model,
        messageCount: Array.isArray(body.messages) ? body.messages.length : 0,
      };
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ choices: [{ message: { content: 'registry-ok' } }] }),
      });
    });
    await page.goto(fixtureUrl, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
    await page.locator('.sx-file').waitFor({ state: 'visible', timeout: timeoutMs });
    await page.locator('.sx-file').first().click();
    await page.locator('.sx-ask textarea').fill('Which registry is active?');
    await page.locator('.sx-ask .sx-send').click();
    await page.waitForFunction(() => {
      const text = document.querySelector('.sx-answer')?.textContent || '';
      return text && text !== 'thinking...';
    }, null, { timeout: 10000 }).catch(() => {});
    results.skillExplorer = { request, answer: await page.locator('.sx-answer').innerText(), errors };
    if (!request || request.url !== 'https://skill-model.example.test/v1/chat/completions' ||
        request.model !== 'model/skill-registry' || request.messageCount !== 2 ||
        request.headers.authorization !== 'Bearer test-model-key' ||
        'x-billing-invoke-origin' in request.headers || retiredBillingHeader in request.headers ||
        results.skillExplorer.answer !== 'registry-ok') {
      fail('SKILL explorer model registry handoff failed: ' + JSON.stringify(results.skillExplorer));
    }
    if (errors.length) fail('SKILL explorer browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // 2c: every authored vendor-import node must resolve from the lesson URL, not scripts/_canvas.js.
  {
    const { page, errors } = await open(browser, '02c-deep.html');
    await page.evaluate(() => document.querySelectorAll('details.learning-block').forEach(item => { item.open = true; }));
    const panels = page.locator('.cf-panel');
    let imports = 0;
    for (let index = 0; index < await panels.count(); index++) {
      const panel = panels.nth(index);
      const code = await panel.locator('.cf-panel-code').inputValue();
      if (!code.includes('import(new URL("./vendor/langchain-1.4.7.esm.js", location.href).href)')) continue;
      imports++;
      await panel.locator('.cf-panel-runone').click();
      await panel.locator('[data-results-meta].ok').waitFor({ state: 'attached', timeout: timeoutMs });
      const output = await panel.innerText();
      if (/TypeError|ReferenceError|Failed to fetch dynamically imported module|✗ stopped:/m.test(output)) {
        fail('2c authored LangChain import cell failed: ' + output);
      }
    }
    if (imports !== 3) fail('2c authored LangChain import coverage expected 3 cells, found ' + imports);
    results.agentBundle.deepImportCells = imports;
    if (errors.length) fail('2c browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // 3a: model and OpenClaw registrations stay distinct. The learner-facing connection
  // audit owns exactly Base URL and Access session; provider, token, and transport stay derived.
  {
    const { page, errors } = await open(browser, '03a-kickstart.html', () => {
      try {
        if (window.top !== window) return;
        localStorage.setItem('nemoclaw_model_api_base_url_v1', 'https://model-runtime-audit.brevlab.com/v1');
        localStorage.setItem('nemoclaw_model_id_v1', 'model/runtime-audit');
        sessionStorage.setItem('nvapi', 'test-model-key');
        localStorage.setItem('nemoclaw_clawrawurl', 'https://nemoclaw-runtime-audit.brevlab.com');
      } catch (_) {}
    });
    await page.locator('#probe-claw .claw-connection-audit').waitFor({ state: 'visible', timeout: timeoutMs });
    results.probe = await page.evaluate(() => {
      const root = document.querySelector('#probe-claw .claw-connection-audit');
      const modelUrl = document.querySelector('#probe-llm .claw-url');
      const launchableUrl = root?.querySelector('.claw-url');
      const accessSession = root?.querySelector('.claw-access-session');
      const registered = {
        model: modelUrl?.value,
        launchable: launchableUrl?.value,
        modelReadOnly: !!modelUrl?.readOnly,
        modelSourceVisible: (document.querySelector('#model-route-settings')?.textContent || '').includes('https://model-runtime-audit.brevlab.com/v1'),
      };
      launchableUrl.value = 'https://nemoclaw-launchable.brevlab.com/chat?session=main#ignored';
      launchableUrl.dispatchEvent(new Event('input', { bubbles: true }));
      accessSession.value = 'synthetic-access-value';
      accessSession.dispatchEvent(new Event('input', { bubbles: true }));
      return {
        visible: !!root,
        registered,
        editableFields: root?.querySelectorAll('input').length || 0,
        advancedFields: root?.querySelectorAll(
          '.claw-token,.claw-access-provider,.claw-ws-relay-enabled,.claw-help-mark'
        ).length || 0,
        steps: Array.from(root?.querySelectorAll('.claw-audit-step') || [])
          .map(step => step.querySelector('code')?.textContent || ''),
        url: localStorage.getItem('nemoclaw_clawrawurl'),
        token: sessionStorage.getItem('nemoclaw_clawtoken'),
        access: sessionStorage.getItem('nemoclaw_openclaw_access_session_v1'),
        persistentAccess: localStorage.getItem('nemoclaw_openclaw_access_session_v1'),
      };
    });
    if (!results.probe.visible || results.probe.editableFields !== 2 ||
        results.probe.advancedFields !== 0 ||
        JSON.stringify(results.probe.steps) !== JSON.stringify(['/api/agent', '/cli/gateway', '/ws/terminal', '/healthz']) ||
        results.probe.registered.model !== 'https://model-runtime-audit.brevlab.com/v1' ||
        results.probe.registered.launchable !== 'https://nemoclaw-runtime-audit.brevlab.com' ||
        !results.probe.registered.modelReadOnly || !results.probe.registered.modelSourceVisible ||
        results.probe.url !== 'https://nemoclaw-launchable.brevlab.com' ||
        results.probe.token !== null ||
        results.probe.access !== 'synthetic-access-value' ||
        results.probe.persistentAccess !== null) {
      fail('probe handoff failed: ' + JSON.stringify(results.probe));
    }
    if (errors.length) fail('3a browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // 3c: run add/watch/remove against a schema-checking fake Gateway. The watcher
  // must poll run history and exit immediately when a completed run appears.
  {
    const { page, errors } = await open(browser, '03c-always-on.html');
    await page.locator('#probe-cron .cf-panel-code').first().waitFor({ state: 'attached', timeout: timeoutMs });
    results.cron = await page.evaluate(async () => {
      const codes = Array.from(document.querySelectorAll('.cf-panel-code')).map(el => el.value || el.textContent || '');
      const addCode = codes.find(code => code.includes('state.call("cron.add"'));
      const watchCode = codes.find(code => code.includes('const POLL_MS = 5000'));
      const removeCode = codes.find(code => code.includes('state.call("cron.remove"'));
      if (!addCode || !watchCode || !removeCode) throw new Error('cron add/watch/remove code cells were not mounted');
      const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
      const calls = [];
      let jobs = [];
      let runHistoryReads = 0;
      let terminalCalls = 0;
      const state = {
        call: async (method, params = {}) => {
          calls.push({ method, params });
          if (method === 'cron.list') return { jobs };
          if (method === 'cron.runs') {
            runHistoryReads++;
            return runHistoryReads === 1
              ? { entries: [] }
              : { entries: [{ ts: Date.now() + 1, runAtMs: Date.now(), status: 'ok', jobId: 'job-runtime-audit' }] };
          }
          if (method === 'cron.add') {
            const valid = params.name === 'quick-3c-demo' && !('id' in params) &&
              params.schedule?.kind === 'cron' && params.schedule.expr === '* * * * *' &&
              params.sessionTarget === 'isolated' && params.wakeMode === 'now' &&
              params.payload?.kind === 'agentTurn' && typeof params.payload.message === 'string';
            if (!valid) throw new Error('invalid authored cron.add payload: ' + JSON.stringify(params));
            const job = { ...params, id: 'job-runtime-audit', state: { lastRunAtMs: 0 } };
            jobs = [job];
            return job;
          }
          if (method === 'cron.remove') {
            if (params.id !== 'job-runtime-audit') throw new Error('remove did not use server id');
            jobs = jobs.filter(job => job.id !== params.id);
            return { removed: true };
          }
          throw new Error('unexpected method ' + method);
        },
      };
      const log = () => ({ textContent: '', setAttribute() {} });
      log.details = () => {};
      const helpers = {
        log,
        signal: new AbortController().signal,
        terminal: async () => {
          terminalCalls++;
          const output = terminalCalls === 1
            ? '=== MEMORY.md (tail) ===\nbefore'
            : '=== MEMORY.md (tail) ===\nbefore\nafter';
          return { output, raw: output, frames: 1 };
        },
      };
      await new AsyncFunction('helpers', 'state', 'ctx', addCode)(helpers, state, {});
      const watch = await new AsyncFunction('helpers', 'state', 'ctx', watchCode)(helpers, state, {});
      await new AsyncFunction('helpers', 'state', 'ctx', removeCode)(helpers, state, {});
      return { calls, remaining: jobs.length, stateId: state.demoCronId, watch, terminalCalls, runHistoryReads };
    });
    const add = results.cron.calls.find(call => call.method === 'cron.add');
    const remove = results.cron.calls.find(call => call.method === 'cron.remove');
    const runs = results.cron.calls.filter(call => call.method === 'cron.runs');
    if (!add || !remove || runs.length < 2 || results.cron.stateId !== 'job-runtime-audit' ||
        results.cron.remaining !== 0 || results.cron.terminalCalls !== 1 ||
        results.cron.runHistoryReads !== 2 || results.cron.watch?.polls !== 1 ||
        results.cron.watch?.run_status !== 'ok' || results.cron.watch?.auto_watch !== false) {
      fail('cron lifecycle failed: ' + JSON.stringify(results.cron));
    }
    if (errors.length) fail('3c browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // 4a: fake only the terminal transport; run the real cell, vendored parser, and Predict node.
  {
    const init = () => {
      try {
        if (window.top !== window) return;
        localStorage.setItem('nemoclaw_clawrawurl', 'https://launchable.example.test');
      } catch (_) { return; }
      const transcript = [
        'Version: 2',
        'Status: Effective',
        'Source: sandbox',
        '---',
        'version: 1',
        'filesystem_policy:',
        '  include_workdir: true',
        '  read_only: ["/usr"]',
        '  read_write: ["/tmp"]',
        'landlock:',
        '  compatibility: best_effort',
        'process:',
        '  run_as_user: sandbox',
        '  run_as_group: sandbox',
        'network_policies:',
        '  nvidia:',
        '    endpoints:',
        '      - host: integrate.api.nvidia.com',
        '        port: 443',
        '        rules:',
        '          - allow: { method: GET, path: /v1/models }',
        '    binaries:',
        '      - path: /usr/local/bin/openclaw',
      ].join('\n');
      class FakeWebSocket {
        static OPEN = 1;
        constructor() {
          this.readyState = 0;
          setTimeout(() => {
            this.readyState = 1;
            this.onopen?.();
            setTimeout(() => {
              this.onmessage?.({ data: JSON.stringify({ data: transcript }) });
              this.onmessage?.({ data: JSON.stringify({ type: 'exit', code: 0 }) });
              this.readyState = 3;
              this.onclose?.();
            }, 10);
          }, 0);
        }
        send() {}
        close() { this.readyState = 3; }
      }
      window.WebSocket = FakeWebSocket;
    };
    const { page, errors } = await open(browser, '04a-safety.html', init);
    await page.locator('#cell-live-policy .rc-run').waitFor({ state: 'visible', timeout: timeoutMs });
    await page.locator('#cell-live-policy .rc-run').click();
    await page.waitForFunction(() => !!window.__SBX_POLICY, null, { timeout: timeoutMs });
    await page.locator('#cell-predict-confirm .cf-panel[data-id="predict"] .cf-panel-runone').click();
    await page.waitForFunction(() => /predicted:/i.test(document.querySelector('#cell-predict-confirm .cf-panel[data-id="predict"]')?.textContent || ''), null, { timeout: timeoutMs });
    results.policy = await page.evaluate(() => ({
      networks: Object.keys(window.__SBX_POLICY?.network_policies || {}),
      liveText: document.querySelector('#cell-live-policy .rc-out')?.textContent || '',
      predictText: document.querySelector('#cell-predict-confirm .cf-panel[data-id="predict"] .cf-panel-log')?.textContent || '',
    }));
    if (!results.policy.networks.includes('nvidia') || !/predicted:/i.test(results.policy.predictText) ||
        /Run the .*live policy.*first/i.test(results.policy.predictText) ||
        /Could not parse the live policy/i.test(results.policy.liveText)) {
      fail('policy state handoff failed: ' + JSON.stringify(results.policy));
    }
    if (errors.length) fail('4a browser errors: ' + JSON.stringify(errors));
    await page.close();
  }

  // Built Pages roots contain locale overlays. Prove runtime guidance stayed translated.
  results.locales = {};
  for (const [locale, connectionPattern, cronPattern, policyPattern] of [
    ['pt', /URL base[\s\S]*Sessão de acesso[\s\S]*Testar conexão/i, /Adicione uma linha curta[\s\S]*aguardando uma execução cron concluída/i, /Não foi possível interpretar/],
    ['es', /URL base[\s\S]*Sesión de acceso[\s\S]*Probar conexión/i, /Añade una línea breve[\s\S]*esperando una ejecución cron terminada/i, /No se pudo interpretar/],
  ]) {
    const kickstartPath = `/${locale}/nemoclaw/03a-kickstart.html`;
    if (!fs.existsSync(safeJoin(root, kickstartPath))) continue;
    const kickstart = await open(browser, kickstartPath);
    await kickstart.page.locator('#probe-claw .claw-connection-audit').waitFor({ state: 'visible', timeout: timeoutMs });
    const connectionText = await kickstart.page.locator('#probe-claw .claw-connection-audit').innerText();
    if (!connectionPattern.test(connectionText)) {
      fail(`${locale} connection audit was de-localized: ${connectionText}`);
    }
    if (kickstart.errors.length) fail(`${locale} 3a browser errors: ${JSON.stringify(kickstart.errors)}`);
    await kickstart.page.close();

    const cron = await open(browser, `/${locale}/nemoclaw/03c-always-on.html`);
    await cron.page.locator('#probe-cron .cf-panel-code').first().waitFor({ state: 'attached', timeout: timeoutMs });
    const cronCode = await cron.page.locator('#probe-cron .cf-panel-code').evaluateAll(items => items.map(item => item.value || '').join('\n'));
    if (!cronPattern.test(cronCode) || !cronCode.includes('state.call("cron.add"') ||
        !cronCode.includes('sessionTarget: "isolated"') ||
        !cronCode.includes('state.call("cron.runs"') ||
        !cronCode.includes('const POLL_MS = 5000') || cronCode.includes('const WAIT_S = 70')) {
      fail(`${locale} cron code lost translation or protocol structure`);
    }
    if (cron.errors.length) fail(`${locale} 3c browser errors: ${JSON.stringify(cron.errors)}`);
    await cron.page.close();

    const safety = await open(browser, `/${locale}/nemoclaw/04a-safety.html`);
    await safety.page.locator('#cell-live-policy .rc-code').waitFor({ state: 'attached', timeout: timeoutMs });
    const policyCode = await safety.page.locator('#cell-live-policy .rc-code').inputValue();
    if (!policyPattern.test(policyCode) || !policyCode.includes('p.parseError')) {
      fail(`${locale} policy failure guidance lost translation or parser detail`);
    }
    if (safety.errors.length) fail(`${locale} 4a browser errors: ${JSON.stringify(safety.errors)}`);
    await safety.page.close();
    results.locales[locale] = { connectionLocalized: true, cronLocalized: true, policyLocalized: true };
  }

  await browser.close();
  server.close();
  console.log(JSON.stringify({ ok: true, root, results }, null, 2));
})().catch(error => {
  try { server.close(); } catch (_) {}
  console.error(error && error.stack || String(error));
  process.exit(1);
});
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate course runtime integration handoffs in Chromium")
    parser.add_argument("--site-root", default="web", help="source or built site root")
    parser.add_argument("--timeout-ms", type=int, default=120000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    site_arg = Path(args.site_root)
    site_root = site_arg.resolve() if site_arg.is_absolute() else (ROOT / site_arg).resolve()
    if not site_root.exists():
        print(f"runtime_integration_browser_audit: FAIL\n  - site root missing: {site_root}")
        return 1
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(RUNTIME_JS)
        script = Path(handle.name)
    try:
        proc = run_node(
            script,
            env=environment(SITE_ROOT=site_root, AUDIT_TIMEOUT_MS=str(args.timeout_ms)),
            timeout=args.timeout_ms / 1000 + 60,
        )
    except BrowserRuntimeError as error:
        print(f"runtime_integration_browser_audit: FAIL\n  - {error}")
        return 1
    except subprocess.TimeoutExpired as error:
        print(f"runtime_integration_browser_audit: FAIL\n  - timed out after {error.timeout}s")
        if error.stdout:
            print(error.stdout)
        return 1
    finally:
        script.unlink(missing_ok=True)
    print(proc.stdout.rstrip())
    print("runtime_integration_browser_audit: " + ("OK" if proc.returncode == 0 else "FAIL"))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
