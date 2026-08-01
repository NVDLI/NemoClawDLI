#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Browser runtime harness. Run through scripts/runtime/browser_runtime_test.sh.
// Set CLAW_URL and CLAW_TOKEN for gateway nodes. Full-page mode verifies only flows that use them;
// tool-specific evidence stays in --chat-contract.

const fs = require('fs');
const http = require('http');
const path = require('path');

const args = process.argv.slice(2);
const smoke = args.includes('--smoke');
const renderOnly = args.includes('--render-only');
const gatewayOnly = args.includes('--gateway-only');
const cronContract = args.includes('--cron-contract');
const terminalContract = args.includes('--terminal-contract');
const chatContract = args.includes('--chat-contract');
const assistantArtifacts = args.includes('--assistant-artifacts');
const serveStatic = args.includes('--serve-static');
const DEFAULT_LAB_URL = 'http://127.0.0.1:4173/nemoclaw/01a-loop.html';
const STATIC_SERVER_URL = 'http://127.0.0.1:4173';
const LOOPBACK_ORIGIN = 'http:' + '//127.0.0.1';
const url = args.find(a => !['--smoke', '--render-only', '--gateway-only', '--cron-contract', '--terminal-contract', '--chat-contract', '--assistant-artifacts', '--serve-static', '--self-test-redaction', '--self-test-access-boundary', '--self-test-direct-fallback'].includes(a)) || DEFAULT_LAB_URL;
const CLAW_URL = process.env.CLAW_URL || '';
let CLAW_TOKEN = process.env.CLAW_TOKEN || '';
const CLAW_ACCESS_SESSION = process.env.CLAW_ACCESS_SESSION || process.env.CLAW_CF || '';
const inferredAccessProvider = /(^|\.)apps\.run\.brev\.nvidia\.com$/i.test((() => { try { return new URL(CLAW_URL).hostname; } catch { return ''; } })())
  ? 'pomerium'
  : 'cloudflare';
const CLAW_ACCESS_PROVIDER = (process.env.CLAW_ACCESS_PROVIDER || inferredAccessProvider).toLowerCase();
const NVIDIA_API_KEY = process.env.NVIDIA_API_KEY || '';
const DIRECT_API_URL = process.env.NVIDIA_API_URL || 'https://integrate.api.nvidia.com/v1';
const CELL_TIMEOUT_MS = Number(process.env.COURSE_CELL_TIMEOUT_MS || 420000);
if (!Number.isInteger(CELL_TIMEOUT_MS) || CELL_TIMEOUT_MS < 1000 || CELL_TIMEOUT_MS > 900000) {
  throw new Error('COURSE_CELL_TIMEOUT_MS must be a whole number from 1000 to 900000');
}
const OPENCLAW_CORS_PROXY_BASE = process.env.OPENCLAW_CORS_PROXY_BASE || 'https://openclaw-cors-proxy.experiments.courses.nvidia.com';
const OPENCLAW_BACKUP_HINT = 'For a remote launchable test, set CLAW_URL and CLAW_ACCESS_PROVIDER. Set CLAW_ACCESS_SESSION only when the isolated browser cannot reuse the launchable session directly; the value is kept in tab-scoped storage and sent through the provider-bound relay. CLAW_TOKEN is optional when /api/agent can discover it.';

function redactDiagnosticText(value) {
  let text = String(value);
  for (const secret of [CLAW_ACCESS_SESSION, CLAW_TOKEN, NVIDIA_API_KEY].filter(Boolean)) {
    for (const candidate of new Set([secret, encodeURIComponent(secret)])) {
      text = text.split(candidate).join('<redacted>');
    }
  }
  return text
    .replace(/([?&](?:access_session|token)=)[^&\s"'<>]+/gi, '$1<redacted>')
    .replace(/((?:CF-Access-Jwt-Assertion|X-OpenClaw-Access-Session)\s*[:=]\s*)[^\s,;}]+/gi, '$1<redacted>')
    .replace(/(Authorization\s*[:=]\s*Bearer\s+)[^\s,;}]+/gi, '$1<redacted>');
}

function redactDiagnosticValue(value) {
  if (typeof value === 'string') return redactDiagnosticText(value);
  if (value instanceof Error) return redactDiagnosticText(value.stack || value.message);
  try {
    return JSON.parse(redactDiagnosticText(JSON.stringify(value)));
  } catch (_) {
    return redactDiagnosticText(value);
  }
}

function sameOriginCourseControl(courseUrl, launchableUrl) {
  try {
    return new URL(courseUrl).origin === new URL(launchableUrl).origin;
  } catch (_) {
    return false;
  }
}

function isExactDirectProbeRedirect(value, launchableUrl, paths) {
  const match = String(value).match(
    /^WebSocket connection to '([^']+)' failed: Error during WebSocket handshake: Unexpected response code: 302$/,
  );
  if (!match) return false;
  try {
    const candidate = new URL(match[1]);
    const launchable = new URL(launchableUrl);
    const prefix = launchable.pathname.replace(/\/+$/, '');
    return candidate.protocol === 'wss:'
      && candidate.host === launchable.host
      && paths.some(pathPart => candidate.pathname === `${prefix}${pathPart}`);
  } catch (_) {
    return false;
  }
}

function isExpectedTerminalFallbackProbeError(value, config = {}) {
  const provider = config.provider ?? CLAW_ACCESS_PROVIDER;
  const session = config.session ?? CLAW_ACCESS_SESSION;
  const launchableUrl = config.launchableUrl ?? CLAW_URL;
  if (!['cloudflare', 'pomerium'].includes(provider) || !session || !launchableUrl) return false;
  return isExactDirectProbeRedirect(value, launchableUrl, ['/ws/terminal']);
}

const diagnosticLog = console.log.bind(console);
const diagnosticError = console.error.bind(console);
console.log = (...values) => diagnosticLog(...values.map(redactDiagnosticValue));
console.error = (...values) => diagnosticError(...values.map(redactDiagnosticValue));

if (args.includes('--self-test-redaction')) {
  const sentinel = CLAW_ACCESS_SESSION || 'diagnostic-session-sentinel';
  const encoded = encodeURIComponent(sentinel);
  const probe = `wss://relay.invalid/ws?access_session=${encoded}&token=token-sentinel Authorization: Bearer bearer-sentinel`;
  const redacted = redactDiagnosticText(probe);
  if (redacted.includes(sentinel) || redacted.includes(encoded) || redacted.includes('token-sentinel') || redacted.includes('bearer-sentinel')) {
    throw new Error('diagnostic redaction self-test failed');
  }
  console.log('diagnostic redaction self-test: PASS');
  process.exit(0);
}

if (args.includes('--self-test-access-boundary')) {
  const sameOrigin = sameOriginCourseControl(
    'https://nemoclaw.example.test/nemoclaw/03a-kickstart.html',
    'https://nemoclaw.example.test',
  );
  const crossOrigin = sameOriginCourseControl(
    'https://course.example.test/nemoclaw/03a-kickstart.html',
    'https://nemoclaw.example.test',
  );
  const lookalike = sameOriginCourseControl(
    'https://nemoclaw.example.test.attacker.invalid/nemoclaw/03a-kickstart.html',
    'https://nemoclaw.example.test',
  );
  if (!sameOrigin || crossOrigin || lookalike) {
    throw new Error('access boundary self-test failed');
  }
  console.log('access boundary self-test: PASS');
  process.exit(0);
}

if (args.includes('--self-test-direct-fallback')) {
  const expected = "WebSocket connection to 'wss://nemoclaw.example.test/ws/terminal?cmd=probe' failed: Error during WebSocket handshake: Unexpected response code: 302";
  const config = {
    provider: 'pomerium',
    session: 'session-sentinel',
    launchableUrl: 'https://nemoclaw.example.test',
  };
  const mutations = [
    expected.replace('nemoclaw.example.test/', 'nemoclaw.example.test.attacker.invalid/'),
    expected.replace('/ws/terminal', '/cli/gateway'),
    expected.replace('code: 302', 'code: 401'),
  ];
  if (!isExpectedTerminalFallbackProbeError(expected, config)
      || !isExpectedTerminalFallbackProbeError(expected, { ...config, provider: 'cloudflare' })
      || mutations.some(value => isExpectedTerminalFallbackProbeError(value, config))
      || isExpectedTerminalFallbackProbeError(expected, { ...config, provider: 'auto' })
      || isExpectedTerminalFallbackProbeError(expected, { ...config, session: '' })) {
    throw new Error('direct fallback self-test failed');
  }
  console.log('direct fallback self-test: PASS');
  process.exit(0);
}

let pw;
try {
  pw = require('/usr/lib/node_modules/openclaw/node_modules/playwright-core');
} catch (_) {
  pw = require('playwright-core');
}

// Locate the chromium-headless-shell binary.
// The install path moves between playwright versions, so glob the known roots instead of hardcoding one.
function contentType(file) {
  if (/\.html?$/.test(file)) return 'text/html; charset=utf-8';
  if (/\.m?js$/.test(file)) return 'text/javascript; charset=utf-8';
  if (/\.css$/.test(file)) return 'text/css; charset=utf-8';
  if (/\.json$/.test(file)) return 'application/json; charset=utf-8';
  if (/\.svg$/.test(file)) return 'image/svg+xml';
  if (/\.png$/.test(file)) return 'image/png';
  if (/\.jpe?g$/.test(file)) return 'image/jpeg';
  if (/\.webp$/.test(file)) return 'image/webp';
  return 'application/octet-stream';
}

function startStaticServer() {
  const courseRoot = path.resolve(process.env.COURSE_ROOT || path.join(__dirname, '..', '..'));
  const roots = [path.join(courseRoot, 'web'), courseRoot];
  const server = http.createServer((req, res) => {
    try {
      const parsed = new URL(req.url, LOOPBACK_ORIGIN);
      let rel = decodeURIComponent(parsed.pathname);
      if (rel.startsWith('/lab/static/')) rel = rel.slice('/lab/static/'.length);
      else rel = rel.replace(/^\/+/, '');
      if (!rel || rel.endsWith('/')) rel += 'index.html';
      for (const root of roots) {
        const candidate = path.resolve(root, rel);
        if (!candidate.startsWith(root + path.sep) && candidate !== root) continue;
        if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
          res.writeHead(200, { 'Content-Type': contentType(candidate) });
          fs.createReadStream(candidate).pipe(res);
          return;
        }
      }
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      res.end('not found');
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'text/plain' });
      res.end(e.message);
    }
  });
  return new Promise(resolve => {
    server.listen(4173, '127.0.0.1', () => resolve(server));
  });
}


function withTimeout(ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error(`timeout after ${ms}ms`)), ms);
  return { signal: controller.signal, done: () => clearTimeout(timer) };
}

function joinUrl(base, pathPart) {
  return base.replace(/\/+$/, '') + pathPart;
}

function openClawHttpUrl(pathPart) {
  const direct = joinUrl(CLAW_URL, pathPart);
  if (!CLAW_ACCESS_SESSION) return direct;
  try {
    const upstream = new URL(CLAW_URL);
    if (!/(^|\.)brevlab\.com$/i.test(upstream.hostname) && !/(^|\.)apps\.run\.brev\.nvidia\.com$/i.test(upstream.hostname)) return direct;
    const proxy = new URL(OPENCLAW_CORS_PROXY_BASE);
    const upstreamPath = upstream.pathname.replace(/\/+$/, '');
    proxy.pathname = `/https/${upstream.host}${upstreamPath}${pathPart}`;
    return proxy.href;
  } catch (_) {
    return direct;
  }
}

function openClawAccessHeaders() {
  if (!CLAW_ACCESS_SESSION) return {};
  if (CLAW_ACCESS_PROVIDER === 'pomerium') {
    return {
      'X-OpenClaw-Access-Provider': 'pomerium',
      'X-OpenClaw-Access-Session': CLAW_ACCESS_SESSION,
    };
  }
  return { 'CF-Access-Jwt-Assertion': CLAW_ACCESS_SESSION };
}

function gatewayTokenFromDashboardUrl(raw) {
  if (!raw) return '';
  try {
    const parsed = new URL(String(raw), 'https://nemoclaw.invalid/');
    const fragment = new URLSearchParams(parsed.hash.replace(/^#/, ''));
    return fragment.get('token') || parsed.searchParams.get('token') || '';
  } catch (_) {
    return '';
  }
}

async function resolveOpenClawToken() {
  // A detected Pomerium browser session stays direct. A manually supplied
  // session follows the same provider-bound fallback as the course runtime.
  if (CLAW_ACCESS_PROVIDER === 'pomerium' && !CLAW_ACCESS_SESSION) return;
  if (CLAW_TOKEN || !(CLAW_URL && CLAW_ACCESS_SESSION)) return;
  const timeout = withTimeout(8000);
  try {
    const resp = await fetch(openClawHttpUrl('/api/agent'), {
      headers: {
        Accept: 'application/json, text/plain, */*',
        ...openClawAccessHeaders(),
      },
      signal: timeout.signal,
    });
    const body = await resp.text();
    let discovered = '';
    try { discovered = gatewayTokenFromDashboardUrl(JSON.parse(body)?.agent?.dashboardUrl); } catch (_) {}
    if (resp.ok && discovered) {
      CLAW_TOKEN = discovered;
      console.log('OPENCLAW_TOKEN: discovered from /api/agent');
    } else {
      console.log('OPENCLAW_TOKEN: not discovered from /api/agent (' + resp.status + ')');
    }
  } catch (e) {
    console.log('OPENCLAW_TOKEN: discovery failed (' + (e && e.message ? e.message : String(e)) + ')');
  } finally {
    timeout.done();
  }
}

async function preflightOpenClaw() {
  if (CLAW_ACCESS_PROVIDER === 'pomerium' && !CLAW_ACCESS_SESSION) return;
  await resolveOpenClawToken();
  if (!(CLAW_URL && CLAW_TOKEN)) return;
  const headers = {
    Accept: 'application/json, text/plain, */*',
    Authorization: `Bearer ${CLAW_TOKEN}`,
    ...openClawAccessHeaders(),
  };
  const targets = ['/health', '/healthz', '/api/agent'];
  const attempts = [];
  for (const pathPart of targets) {
    const timeout = withTimeout(6000);
    const target = openClawHttpUrl(pathPart);
    try {
      const resp = await fetch(target, { headers, signal: timeout.signal });
      attempts.push(`${resp.status} ${target}`);
      if (resp.ok || [401, 403].includes(resp.status)) {
        console.log('OPENCLAW_PREFLIGHT:', attempts.join(' | '));
        return;
      }
    } catch (e) {
      attempts.push(`${target} -> ${e && e.message ? e.message : String(e)}`);
    } finally {
      timeout.done();
    }
  }
  throw new Error(`OpenClaw preflight failed. ${attempts.join(' | ')}. ${OPENCLAW_BACKUP_HINT}`);
}

function findChrome() {
  if (process.env.CHROME_BIN && fs.existsSync(process.env.CHROME_BIN)) return process.env.CHROME_BIN;
  const roots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH || '/tmp/pw-browsers',
    '/sandbox/.cache/ms-playwright',
    `${process.env.HOME || '/root'}/.cache/ms-playwright`,
  ];
  for (const root of roots) {
    let dirs = [];
    try { dirs = fs.readdirSync(root); } catch { continue; }
    for (const d of dirs) {
      const candidates = [
        `${root}/${d}/chrome-headless-shell-linux64/chrome-headless-shell`,
        `${root}/${d}/chrome-linux/chrome`,
        `${root}/${d}/chrome-linux64/chrome`,
      ];
      for (const bin of candidates) if (fs.existsSync(bin)) return bin;
    }
  }
  for (const bin of ['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome']) {
    if (fs.existsSync(bin)) return bin;
  }
  for (const bin of [
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ]) if (fs.existsSync(bin)) return bin;
  return null;
}

(async () => {
  let staticServer = null;
  if (serveStatic) {
    staticServer = await startStaticServer();
    console.log('STATIC_SERVER: ' + STATIC_SERVER_URL);
  }

  const executablePath = findChrome();
  if (!executablePath) {
    console.error('FATAL: Chromium/Chrome not found. Install it for your OS or set CHROME_BIN.');
    process.exit(1);
  }
  console.log('CHROME:', executablePath || 'playwright default');

  const launchOptions = { headless: true, args: ['--no-sandbox'] };
  if (executablePath) launchOptions.executablePath = executablePath;
  const browser = await pw.chromium.launch(launchOptions);
  const page = await browser.newPage();

  await page.route('**/*', route => {
    const reqUrl = route.request().url();
    try {
      const host = new URL(reqUrl).hostname;
      if (/^(cdnjs\.cloudflare\.com|cdn\.jsdelivr\.net|unpkg\.com)$/.test(host)) {
        if (/\.css(?:$|\?)/.test(reqUrl)) {
          return route.fulfill({ status: 200, contentType: 'text/css', body: '' });
        }
        if (/highlight\.min\.js/.test(reqUrl)) {
          return route.fulfill({ status: 200, contentType: 'text/javascript', body: 'window.hljs={highlightAll(){},highlightElement(){},highlight(){return {value:""}}};' });
        }
        if (/codemirror\.min\.js/.test(reqUrl)) {
          return route.fulfill({ status: 200, contentType: 'text/javascript', body: 'window.CodeMirror={fromTextArea(){return {setValue(){},getValue(){return ""},on(){},refresh(){},setSize(){}}}};' });
        }
        return route.fulfill({ status: 200, contentType: 'text/javascript', body: '' });
      }
    } catch (_) {}
    return route.continue();
  });

  if (!smoke && !renderOnly) await preflightOpenClaw();

  if (smoke) {
    await page.goto('data:text/html,<main id="ok">lab runtime smoke</main>');
    const ok = await page.textContent('#ok');
    console.log('SMOKE_TEXT:', ok);
    console.log('RESULT: PASS (node + playwright + chromium runtime)');
    await browser.close();
    if (staticServer) staticServer.close();
    process.exit(0);
  }

  // Local harness may need an allowlisted Origin for gateway WS handshakes.
  if (process.env.CLAW_ORIGIN) {
    await page.setExtraHTTPHeaders({ Origin: process.env.CLAW_ORIGIN });
    console.log('ORIGIN: overridden ->', process.env.CLAW_ORIGIN);
  }

  const errors = [];
  const resourceErrors = [];
  const resourceEvents = [];
  let resourceEventOrder = 0;
  let activeCell = null;
  function requestMetadata(req) {
    const raw = req.postData() || '';
    let body = null;
    try { body = raw ? JSON.parse(raw) : null; } catch (_) {}
    return {
      cellIndex: activeCell?.index ?? null,
      cellKind: activeCell?.kind ?? null,
      requestBytes: Buffer.byteLength(raw),
      model: body && typeof body.model === 'string' ? body.model : null,
      messageCount: body && Array.isArray(body.messages) ? body.messages.length : null,
      maxTokens: body && (body.max_tokens ?? body.maxTokens ?? null),
      stream: body ? body.stream === true : null,
    };
  }
  page.on('console', msg => {
    if (msg.type() !== 'error') return;
    const text = msg.text();
    if (/^Failed to load resource:/.test(text)) return;
    if (/integrate\.api\.nvidia\.com\/v1\/models/.test(text)) return;
    errors.push(text);
  });
  page.on('pageerror', err => errors.push('PAGE_ERROR: ' + err.message));
  page.on('requestfailed', req => {
    const failure = req.failure();
    // Chromium may mark a completed HEAD probe as aborted because no response body follows.
    // HTTP error responses remain visible through the response listener below.
    if (req.method() === 'HEAD' && failure && failure.errorText === 'net::ERR_ABORTED') return;
    resourceErrors.push(`FAILED ${req.url()} ${failure ? failure.errorText : ''}`.trim());
    resourceEvents.push({
      order: resourceEventOrder++, kind:'failed', method:req.method(), url:req.url(),
      errorText:failure?.errorText || '', ...requestMetadata(req),
    });
  });
  page.on('response', resp => {
    const req = resp.request();
    resourceEvents.push({
      order:resourceEventOrder++, kind:'response', method:req.method(), url:resp.url(),
      status:resp.status(), ...requestMetadata(req),
    });
    if (resp.status() >= 400) resourceErrors.push(`${resp.status()} ${resp.url()}`);
  });
  if (process.env.DEBUG_WS) {
    page.on('console', msg => console.log('  [console.' + msg.type() + ']', msg.text()));
    page.on('websocket', s => console.log('  [ws.open]', s.url()));
  }

  // Gateway frame counts prove the connection and any agent loop actually ran.
  const ws = { sockets: 0, allFrames: 0, challenges: 0, resOk: 0, evtKinds: {}, resErr: [], agentFrames: 0, toolStarts: [], cmdEnds: [], chatFinals: 0, errors: 0 };
  page.on('websocket', sock => {
    if (!/\/cli\/gateway/.test(sock.url())) return;
    ws.sockets++;
    sock.on('framereceived', f => {
      ws.allFrames++;
      let d; try { d = JSON.parse(typeof f.payload === 'string' ? f.payload : f.payload.toString()); } catch { return; }
      if (d.type === 'res' && d.ok === true) ws.resOk++;
      if (d.type === 'res' && d.ok === false) { ws.errors++; ws.resErr.push((d.error && d.error.message) || '?'); }
      if (d.event) ws.evtKinds[d.event] = (ws.evtKinds[d.event] || 0) + 1;
      if (d.event === 'connect.challenge') ws.challenges++;
      if (d.type !== 'event') return;
      if (d.event === 'chat' && d.payload && d.payload.state === 'final') ws.chatFinals++;
      if (d.event !== 'agent') return;
      ws.agentFrames++;
      const data = (d.payload && d.payload.data) || {};
      const iid = data.itemId || '';
      if (iid.startsWith('tool:') && data.phase === 'start') ws.toolStarts.push(data.name || 'tool');
      else if (iid.startsWith('command:') && data.phase === 'end' && 'exitCode' in data)
        ws.cmdEnds.push({ exit: data.exitCode, ms: data.durationMs });
    });
  });

  // A same-origin launchable control may reuse its Cloudflare browser cookie.
  // Cross-origin course tests must exercise the learner's tab-scoped relay path.
  if (CLAW_ACCESS_SESSION && CLAW_URL && CLAW_ACCESS_PROVIDER === 'cloudflare' && sameOriginCourseControl(url, CLAW_URL)) {
    try {
      const host = new URL(CLAW_URL).hostname;
      await page.context().addCookies([{ name: 'CF_Authorization', value: CLAW_ACCESS_SESSION, domain: host, path: '/', secure: true, sameSite: 'None' }]);
      console.log('ACCESS_COOKIE: set provider=' + CLAW_ACCESS_PROVIDER + ' host=' + host);
    } catch (e) { console.log('ACCESS_COOKIE: skipped (' + e.message + ')'); }
  }

  // The web course is remote-service-only. Published course origins and local previews use the
  // bounded browser relay for the default endpoint; custom endpoints remain direct.
  await page.addInitScript(({ apiUrl, useIframeProxy }) => {
    try {
      const defaultUrl = "https://integrate.api.nvidia.com/v1";
      if (apiUrl === defaultUrl) {
        localStorage.removeItem("nemoclaw_model_api_base_url_v1");
        localStorage.removeItem("nemoclaw_embedding_api_base_url_v1");
      } else {
        localStorage.setItem("nemoclaw_model_api_base_url_v1", apiUrl);
        localStorage.setItem("nemoclaw_embedding_api_base_url_v1", apiUrl);
      }
      localStorage.removeItem("nemoclaw_model_id_v1");
      sessionStorage.removeItem("__nv_slim_cfg_v1");
      if (useIframeProxy) localStorage.setItem("nemoclaw_iframe_proxy_opt_in", "1");
    } catch (_) {}
  }, {
    apiUrl: DIRECT_API_URL,
    useIframeProxy: !renderOnly && !gatewayOnly &&
      ['127.0.0.1', 'localhost'].includes(new URL(url).hostname) &&
      DIRECT_API_URL === 'https://integrate.api.nvidia.com/v1',
  });

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
  if (NVIDIA_API_KEY) {
    await page.evaluate(async apiKey => {
      const runtime = await import(new URL("./scripts/_shared.js", document.baseURI).href);
      runtime.setKey(apiKey);
    }, NVIDIA_API_KEY);
  }
  await page.waitForTimeout(2000);
  // Render checks include foyer manifest probes. Let those finite HEAD requests settle before
  // closing Chromium; otherwise Playwright reports the close itself as net::ERR_ABORTED.
  if (renderOnly) await page.waitForLoadState('networkidle', { timeout: 5000 }).catch(() => {});

  if (assistantArtifacts) {
    if (!NVIDIA_API_KEY) throw new Error('--assistant-artifacts requires NVIDIA_API_KEY');
    const prompts = [
      'Build a runnable interactive agent-loop diagram with Observe, Reason, Act, and Update. Include Next and Reset buttons that visibly advance and reset the active step.',
      'Build a runnable context-budget dashboard for four agents. Include Normal load and Overloaded controls that update bar widths, values, and warning state.',
      'Build a runnable three-question quiz about the main ideas from this page. Use button elements for every selectable answer, with immediate feedback, a score, and Restart.',
    ];
    const results = [];
    for (let index = 0; index < prompts.length; index++) {
      if (index) {
        await page.evaluate(() => localStorage.removeItem('nemoclaw_course_assistant_sessions_v1'));
        await page.reload({ waitUntil:'domcontentloaded', timeout:20000 });
      }
      await page.locator('.course-assistant-launcher').click();
      const panel = page.locator('.course-assistant-panel');
      await panel.waitFor({ state:'visible' });
      const chat = panel.locator('.course-assistant-body');
      const model = await chat.locator('.chatui-model').inputValue();
      if (!/nemotron-3-super-120b/i.test(model)) throw new Error(`Course Assistant artifact default is not the validated model: ${model}`);
      await chat.locator('.chatui-text').fill(prompts[index]);
      const send = chat.locator('.chatui-send');
      await send.click();
      await page.waitForFunction(() => document.querySelector('.course-assistant-body .chatui-send')?.textContent.trim() !== 'Send', null, { timeout:5000 });
      await page.waitForFunction(() => document.querySelector('.course-assistant-body .chatui-send')?.textContent.trim() === 'Send', null, { timeout:180000 });
      const toolBodies = await chat.locator('.chatui-tool-body').allInnerTexts();
      const validated = toolBodies.some(text => /Validated and queued browser artifact/.test(text));
      const rejections = toolBodies.filter(text => /Artifact rejected (?:before execution|at runtime)/.test(text));
      const chatErrors = await chat.locator('.chatui-msg.err,.chatui-warn').allInnerTexts();
      const lastAnswer = (await chat.locator('.chatui-msg.chatui-bot').last().innerText().catch(() => '')).slice(0, 600);
      await panel.locator('[data-course-assistant-view="artifact"]').click();
      const sourceChars = await panel.evaluate(node => {
        const html = node.querySelector('[data-course-artifact-html]');
        const javascript = node.querySelector('[data-course-artifact-js]');
        return (html.__courseAssistantEditor?.getValue() || html.value || '').length +
          (javascript.__courseAssistantEditor?.getValue() || javascript.value || '').length;
      });
      const frame = panel.frameLocator('.course-assistant-artifact iframe');
      await frame.locator('body').waitFor({ state:'attached', timeout:10000 });
      const snapshot = () => frame.locator('body').evaluate(body => JSON.stringify({
        text:body.innerText,
        controls:[...body.querySelectorAll('button,input,select,textarea')].map(control => ({
          tag:control.tagName, type:control.type, value:control.value, checked:control.checked,
          disabled:control.disabled, hidden:control.hidden, className:control.className,
          style:control.getAttribute('style') || '',
        })),
        states:[...body.querySelectorAll('[class],[style]')].slice(0,80).map(node => [node.className, node.getAttribute('style') || '']),
      }));
      const before = await snapshot();
      const controls = frame.locator('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled])');
      const controlCount = await controls.count();
      let changed = false;
      for (let controlIndex = 0; controlIndex < Math.min(controlCount, 12) && !changed; controlIndex++) {
        const control = controls.nth(controlIndex);
        if (!await control.isVisible().catch(() => false)) continue;
        const tag = await control.evaluate(node => node.tagName);
        const type = await control.getAttribute('type') || '';
        try {
          if (tag === 'SELECT') await control.selectOption({ index:0 });
          else if (tag === 'TEXTAREA' || (tag === 'INPUT' && !['button','submit','radio','checkbox'].includes(type))) await control.fill('probe');
          else await control.click({ timeout:3000 });
          await page.waitForTimeout(180);
          changed = await snapshot() !== before;
        } catch (_) {}
      }
      const status = await panel.locator('.course-artifact-actions [role="status"]').innerText();
      const result = {
        prompt:index + 1,
        model,
        validated,
        rejections:rejections.length,
        chatErrors,
        pageErrors:[...errors],
        resourceErrors:[...resourceErrors],
        sourceChars,
        controlCount,
        changed,
        status,
        lastAnswer,
      };
      results.push(result);
      if (!validated || !sourceChars || !controlCount || !changed || chatErrors.length || /error|rejected|erro/i.test(status)) {
        console.log('COURSE_ASSISTANT_ARTIFACTS:', JSON.stringify(results, null, 2));
        throw new Error(`Course Assistant artifact ${index + 1} failed validation: ${JSON.stringify(result)}`);
      }
    }
    console.log('COURSE_ASSISTANT_ARTIFACTS:', JSON.stringify(results, null, 2));
    console.log('RESULT: PASS (live Course Assistant artifact generation)');
    await browser.close();
    if (staticServer) staticServer.close();
    process.exit(0);
  }

  if (renderOnly) {
    const pageInfo = await page.evaluate(() => {
      const main = document.querySelector('main');
      const title = document.title || '';
      const heading = (document.querySelector('h1') || document.querySelector('h2') || {}).textContent || '';
      const textStartsCode = el => /^code\b/i.test((el.textContent || '').trim());
      return {
        title: title.trim(),
        heading: heading.trim(),
        hasMain: !!main,
        flows: document.querySelectorAll('.cf-btn-run').length,
        panels: document.querySelectorAll('.cf-panel').length,
        runCells: document.querySelectorAll('.rc-card').length,
        unifiedButtons: document.querySelectorAll('.cell-btn').length,
        unifiedLangChips: document.querySelectorAll('.cell-lang-chip').length,
        uglyCellButtons: document.querySelectorAll('.rc-run:not(.cell-btn),.rc-reset:not(.cell-btn),.cf-panel-runone:not(.cell-btn),.cf-panel-reset:not(.cell-btn)').length,
        plainCodeLabels: Array.from(document.querySelectorAll('.rc-code-det > summary,.cf-panel-code-det > summary')).filter(textStartsCode).length,
        codeBlocks: document.querySelectorAll('pre code, pre').length,
      };
    });
    console.log('PAGE_INFO:', JSON.stringify(pageInfo, null, 2));
    console.log('PAGE_ERRORS:', JSON.stringify(errors));
    console.log('RESOURCE_ERRORS:', JSON.stringify(resourceErrors));
    const significantResourceErrors = resourceErrors.filter(x => !/favicon\.ico/.test(x) && !/integrate\.api\.nvidia\.com\/v1\/models/.test(x));
    const fail = errors.length > 0 || significantResourceErrors.length > 0 || !pageInfo.hasMain
      || pageInfo.uglyCellButtons > 0 || pageInfo.plainCodeLabels > 0;
    console.log(fail ? 'RESULT: FAIL (render errors)' : 'RESULT: PASS (static render)');
    await browser.close();
    if (staticServer) staticServer.close();
    process.exit(fail ? 1 : 0);
  }

  if (gatewayOnly) {
    if (!(CLAW_URL && CLAW_ACCESS_SESSION)) {
      throw new Error('--gateway-only requires CLAW_URL and CLAW_ACCESS_SESSION');
    }
    const result = await page.evaluate(async ({ clawUrl, accessProvider, accessSession, proxyBase, cronContract, terminalContract, chatContract }) => {
      const output = {
        httpStatus: 0,
        token: false,
        viaProxy: false,
        challenge: false,
        connect: false,
        rpc: false,
        cronAdd: false,
        cronRuns: false,
        cronRemove: false,
        cleanupId: '',
        terminalOpen: false,
        terminalFrames: 0,
        chatText: false,
        chatRendered: false,
        chatTools: 0,
        chatToolNames: [],
        chatToolErrors: 0,
        chatNoise: false,
        error: '',
      };
      try {
        const mod = await import(new URL('./scripts/_shared.js', location.href).href);
        mod.setOpenClawConnection({ rawUrl: clawUrl, accessProvider, accessSession });
        const gateway = mod.openclawGatewayWsUrl(clawUrl, accessSession, proxyBase, null, accessProvider);
        output.viaProxy = gateway.viaProxy;
        const response = await mod.openclawBootstrapRequest('/api/agent');
        output.httpStatus = response.status;
        if (!response.ok) throw new Error(`agent metadata returned HTTP ${response.status}`);
        const metadata = response.json;
        const token = mod.gatewayTokenFromAgentMetadata(metadata);
        output.token = !!token;
        if (!token) throw new Error('agent metadata omitted a gateway token');
        mod.setOpenClawConnection({ rawUrl: clawUrl, token, accessProvider, accessSession });

        await new Promise((resolve, reject) => {
          const socket = new WebSocket(gateway.url);
          const timer = setTimeout(() => reject(new Error('gateway check timed out')), 20000);
          const finish = error => {
            clearTimeout(timer);
            try { socket.close(); } catch (_) {}
            error ? reject(error) : resolve();
          };
          socket.onerror = () => finish(new Error('gateway WebSocket error'));
          socket.onmessage = event => {
            let data;
            try { data = JSON.parse(event.data); } catch (_) { return; }
            if (data.event === 'connect.challenge') {
              output.challenge = true;
              socket.send(JSON.stringify({
                type: 'req', id: 'browser-connect', method: 'connect',
                params: {
                  minProtocol: 4, maxProtocol: 4,
                  client: { id: 'openclaw-control-ui', version: '0.1.0', platform: 'browser', mode: 'webchat' },
                  caps: ['tool-events'], role: 'operator',
                  scopes: ['operator.read', 'operator.write', 'operator.admin'],
                  auth: { token },
                },
              }));
              return;
            }
            if (data.type !== 'res') return;
            if (data.id === 'browser-connect') {
              if (!data.ok) return finish(new Error(data.error?.message || 'gateway connect rejected'));
              output.connect = true;
              socket.send(JSON.stringify({ type: 'req', id: 'browser-rpc', method: 'models.list', params: {} }));
              return;
            }
            if (data.id === 'browser-rpc') {
              if (!data.ok) return finish(new Error(data.error?.message || 'gateway RPC rejected'));
              output.rpc = true;
              if (!cronContract) return finish();
              socket.send(JSON.stringify({
                type: 'req', id: 'browser-cron-add', method: 'cron.add',
                params: {
                  name: `course-runtime-audit-${Date.now()}`,
                  schedule: { kind: 'cron', expr: '0 0 1 1 *', tz: 'UTC' },
                  sessionTarget: 'isolated', wakeMode: 'now',
                  payload: { kind: 'agentTurn', message: 'Runtime contract audit. No action is required.' },
                },
              }));
              return;
            }
            if (data.id === 'browser-cron-add') {
              if (!data.ok) return finish(new Error(data.error?.message || 'cron.add rejected'));
              const id = data.payload?.id;
              if (!id) return finish(new Error('cron.add returned no job id'));
              output.cronAdd = true;
              output.cleanupId = id;
              socket.send(JSON.stringify({ type: 'req', id: 'browser-cron-runs', method: 'cron.runs', params: { id, limit: 20 } }));
              return;
            }
            if (data.id === 'browser-cron-runs') {
              if (!data.ok || !Array.isArray(data.payload?.entries)) return finish(new Error(data.error?.message || 'cron.runs rejected'));
              output.cronRuns = true;
              socket.send(JSON.stringify({ type: 'req', id: 'browser-cron-remove', method: 'cron.remove', params: { id: output.cleanupId } }));
              return;
            }
            if (data.id === 'browser-cron-remove') {
              if (!data.ok) return finish(new Error(data.error?.message || `cron.remove rejected for ${output.cleanupId}`));
              output.cronRemove = true;
              output.cleanupId = '';
              finish();
            }
          };
        });
        if (terminalContract) {
          mod.setOpenClawConnection({ rawUrl: clawUrl, token, accessProvider, accessSession });
          const transcript = await mod.terminal('openshell sandbox list', {
            idleMs: 4000,
            totalMs: 20000,
            openMs: 12000,
          });
          output.terminalFrames = transcript.frames;
          output.terminalOpen = transcript.frames > 0 && !!String(transcript.output || '').trim();
        }
        if (chatContract) {
          mod.setOpenClawConnection({ rawUrl: clawUrl, token, accessProvider, accessSession });
          const rendered = [], tools = [];
          const view = {
            token: value => rendered.push(String(value || '')),
            tool: (label, body) => {
              const node = document.createElement('details');
              const summary = document.createElement('summary'); summary.textContent = '🔧 ' + label;
              const result = document.createElement('div'); result.className = 'chatui-tool-body'; result.textContent = body || '';
              node.append(summary, result); tools.push(node); return node;
            },
            usage: () => {},
          };
          const text = await mod.openclawChat(
            'Use your exec tool to run whoami and pwd, then report both results.',
            { session: 'course-live-chat-audit-' + Date.now(), view, idleMs: 90000, totalMs: 180000, finalGraceMs: 3000 },
          );
          const transcript = [text, rendered.join(''), ...tools.map(node => node.textContent || '')].join('\n');
          output.chatText = !!String(text || '').trim();
          output.chatRendered = !!rendered.join('').trim();
          output.chatTools = tools.length;
          output.chatToolNames = tools.map(node => (node.querySelector('summary')?.textContent || '').replace(/^🔧\s*/, '').split(' · ')[0]);
          output.chatToolErrors = tools.filter(node => node.classList.contains('err')).length;
          output.chatNoise = /oom_score_adj/.test(transcript);
        }
      } catch (error) {
        output.error = error?.message || String(error);
      }
      return output;
    }, { clawUrl: CLAW_URL, accessProvider: CLAW_ACCESS_PROVIDER, accessSession: CLAW_ACCESS_SESSION, proxyBase: OPENCLAW_CORS_PROXY_BASE, cronContract, terminalContract, chatContract });
    console.log('GATEWAY_CHECK:', JSON.stringify(result));
    const expectedProxy = CLAW_ACCESS_PROVIDER === 'pomerium' && !!CLAW_ACCESS_SESSION;
    const passed = result.httpStatus === 200 && result.token && result.viaProxy === expectedProxy
      && result.challenge && result.connect && result.rpc && !result.error
      && (!cronContract || (result.cronAdd && result.cronRuns && result.cronRemove && !result.cleanupId))
      && (!terminalContract || (result.terminalOpen && result.terminalFrames > 0))
      && (!chatContract || (result.chatText && result.chatRendered && result.chatTools > 0
        && result.chatToolNames.includes('exec') && result.chatToolErrors === 0 && !result.chatNoise));
    console.log(passed ? 'RESULT: PASS (live OpenClaw transport)' : 'RESULT: FAIL (live OpenClaw transport)');
    await browser.close();
    if (staticServer) staticServer.close();
    process.exit(passed ? 0 : 1);
  }

  // Drive Module 3a's visible four-route connection audit when present. Other
  // lessons retain direct registry setup because they depend on Module 3a.
  const acceptedAuditErrors = new Set();
  if (CLAW_URL && (CLAW_TOKEN || CLAW_ACCESS_PROVIDER === 'pomerium' || CLAW_ACCESS_SESSION)) {
    const audit = page.locator('.claw-connection-audit');
    if (await audit.count()) {
      const beforeAuditErrors = errors.length;
      await audit.locator('.claw-url').fill(CLAW_URL);
      await audit.locator('.claw-access-session').fill(CLAW_ACCESS_SESSION);
      await audit.locator('.claw-audit-run').click();
      await page.waitForFunction(() => {
        const root = document.querySelector('.claw-connection-audit');
        return root && ['succeeded', 'failed'].includes(root.dataset.state);
      }, null, { timeout: 90000 });
      const auditResult = await audit.evaluate(root => ({
        state: root.dataset.state,
        summary: root.querySelector('.claw-audit-summary')?.textContent?.trim() || '',
        checks: [...root.querySelectorAll('.claw-audit-step')].map(step => ({
          id: step.dataset.step,
          status: step.dataset.status,
        })),
      }));
      if (auditResult.state !== 'succeeded') {
        throw new Error(`visible connection audit failed: ${JSON.stringify(auditResult)}`);
      }
      for (const error of errors.slice(beforeAuditErrors)) {
        if (isExactDirectProbeRedirect(error, CLAW_URL, ['/cli/gateway', '/ws/terminal'])) {
          acceptedAuditErrors.add(error);
        }
      }
      console.log('CONNECTION_AUDIT:', JSON.stringify(auditResult));
    } else {
      const injected = await page.evaluate(async ([u, t, provider, session]) => {
        const shared = await import(new URL('./scripts/_shared.js', location.href).href);
        if (!t && provider === 'pomerium' && !session) {
          shared.setOpenClawConnection({ rawUrl: u, accessProvider: provider, accessSession: '' });
          const metadata = await shared.openclawLoopbackProbe('/api/agent', { baseUrl: u });
          t = shared.gatewayTokenFromAgentMetadata(metadata.json);
          if (!t) throw new Error('agent metadata omitted a gateway token');
        }
        shared.setOpenClawConnection({ rawUrl: u, token: t, accessProvider: provider, accessSession: session });
        return { token: !!t, accessSessionStored: !!shared.getOpenClawConnection().accessSession };
      }, [CLAW_URL, CLAW_TOKEN, CLAW_ACCESS_PROVIDER, CLAW_ACCESS_SESSION]);
      console.log('CREDS: injected', CLAW_URL,
        CLAW_ACCESS_PROVIDER === 'pomerium'
          ? (injected.accessSessionStored
            ? '(Pomerium fallback session is tab-scoped)'
            : '(Pomerium browser session will be detected directly)')
          : (injected.accessSessionStored ? '(Cloudflare relay session is tab-scoped)' : ''));
    }
  } else {
    console.log('CREDS: none (gateway nodes will short-circuit on the probe guard)');
  }

  // Run every learner cell in document order. A RunCell may prepare state for a
  // later CanvasFlow, so grouping by widget type changes the authored exercise.
  const runnableSelector = '.cf-btn-run,.rc-run';
  const runnableCount = await page.locator(runnableSelector).count();
  const cellRuns = [];
  console.log('RUNNABLE_CELLS:', runnableCount);
  let settled = true;
  for (let index = 0; index < runnableCount; index++) {
    const metadata = await page.evaluate(i => {
      const button = document.querySelectorAll('.cf-btn-run,.rc-run')[i];
      const flow = button?.closest('.cf-wrap');
      const runCell = button?.closest('.rc-card');
      const source = flow
        ? [...flow.querySelectorAll('textarea.cf-panel-code')]
            .map(textarea => textarea.value || textarea.textContent || '').join('\n')
        : (runCell?.querySelector('textarea.rc-code')?.value || '');
      return {
        kind: flow ? 'canvas-flow' : 'run-cell',
        label: (flow?.querySelector('.cf-label')?.textContent ||
          runCell?.querySelector('.rc-label')?.textContent || `cell ${i + 1}`).trim(),
        disabled: !!button?.disabled,
        expectsGateway: /\bopenclawGatewayWsUrl\b|\bopenclawChat\b|\/cli\/gateway/.test(source),
      };
    }, index);
    const before = {
      sockets: ws.sockets, allFrames: ws.allFrames, challenges: ws.challenges,
      resOk: ws.resOk, errors: ws.errors, agentFrames: ws.agentFrames,
      toolStarts: ws.toolStarts.length, cmdEnds: ws.cmdEnds.length, chatFinals: ws.chatFinals,
    };
    if (metadata.disabled) {
      cellRuns.push({ index, ...metadata, settled:false, status:'disabled before execution', runtimeError:'', gatewayOk:false, ws:{} });
      settled = false;
      continue;
    }
    // Some flows live inside collapsed Guided-mode sections. Programmatic click keeps
    // full-course auditing independent of the learner's current disclosure preference.
    activeCell = { index, kind:metadata.kind };
    await page.evaluate(i => document.querySelectorAll('.cf-btn-run,.rc-run')[i]?.click(), index);
    let runSettled = true;
    try {
      await page.waitForFunction(({ i, selector }) => {
        const button = document.querySelectorAll(selector)[i];
        const flow = button?.closest('.cf-wrap');
        if (flow) {
          const status = (flow.querySelector('.cf-status-bar')?.textContent || '').trim();
          return !flow?.querySelector('.cf-panel.running') && !!status;
        }
        return !!button && !/stop/i.test(button.textContent || '');
      }, { i:index, selector:runnableSelector }, { timeout:CELL_TIMEOUT_MS });
    } catch (_) {
      runSettled = false;
      settled = false;
    }
    const status = await page.evaluate(i => {
      const button = document.querySelectorAll('.cf-btn-run,.rc-run')[i];
      const flow = button?.closest('.cf-wrap');
      const runCell = button?.closest('.rc-card');
      return (flow?.querySelector('.cf-status-bar')?.textContent ||
        runCell?.querySelector('.rc-out')?.textContent || '').trim().slice(0, 500);
    }, index);
    const runtimeError = await page.evaluate(i => {
      const button = document.querySelectorAll('.cf-btn-run,.rc-run')[i];
      const owner = button?.closest('.cf-wrap,.rc-card');
      return (owner?.querySelector('.cell-runtime-error,.cf-panel-error')?.textContent || '').trim().slice(0, 500);
    }, index);
    const activity = {
      sockets: ws.sockets - before.sockets,
      allFrames: ws.allFrames - before.allFrames,
      challenges: ws.challenges - before.challenges,
      resOk: ws.resOk - before.resOk,
      errors: ws.errors - before.errors,
      agentFrames: ws.agentFrames - before.agentFrames,
      toolStarts: ws.toolStarts.length - before.toolStarts,
      cmdEnds: ws.cmdEnds.length - before.cmdEnds,
      chatFinals: ws.chatFinals - before.chatFinals,
    };
    const gatewayOk = !metadata.expectsGateway || (
      activity.allFrames > 0 && activity.resOk > 0 && activity.errors === 0
    );
    cellRuns.push({ index, ...metadata, settled:runSettled, status, runtimeError, gatewayOk, ws:activity });
    activeCell = null;
  }
  console.log('CELL_RUNS:', JSON.stringify(cellRuns, null, 2));
  console.log('SETTLED:', settled);

  // Per-node status: error text + how many <details> blocks rendered (tool trace).
  const nodeStatus = await page.evaluate(() => {
    const result = {};
    document.querySelectorAll('[data-id].cf-panel').forEach(p => {
      const errEl = p.querySelector('.cf-panel-error');
      const outEl = p.querySelector('.cf-panel-log');
      result[p.dataset.id] = {
        error: errEl ? errEl.textContent.trim().slice(0, 200) : null,
        details: p.querySelectorAll('details').length,
        log: outEl ? outEl.textContent.trim().slice(0, 300) : null,
      };
    });
    return result;
  });

  console.log('PAGE_ERRORS:', JSON.stringify(errors));
  console.log('RESOURCE_ERRORS:', JSON.stringify(resourceErrors));
  console.log('NODE_STATUS:', JSON.stringify(nodeStatus, null, 2));
  console.log('WS_STATS:', JSON.stringify(ws, null, 2));

  const failedResourceEvents = resourceEvents.filter(event => {
    if (serveStatic && event.kind === 'response' && event.status === 404 &&
        new URL(event.url).pathname === '/languages.json') return false;
    return event.kind === 'failed' || (event.kind === 'response' && event.status >= 400);
  });
  const recoveredResourceEvents = failedResourceEvents.filter(event => {
    if (event.kind === 'response' && event.status < 500 && event.status !== 429) return false;
    return resourceEvents.some(candidate =>
      candidate.order > event.order && candidate.kind === 'response' &&
      candidate.method === event.method && candidate.url === event.url &&
      candidate.status >= 200 && candidate.status < 400);
  });
  const recoveredOrders = new Set(recoveredResourceEvents.map(event => event.order));
  const recoveredUrls = new Set(recoveredResourceEvents.map(event => event.url));
  const unrecoveredResourceErrors = failedResourceEvents.filter(event => !recoveredOrders.has(event.order));
  console.log('RECOVERED_TRANSIENTS:', JSON.stringify(recoveredResourceEvents));
  console.log('UNRECOVERED_RESOURCE_ERRORS:', JSON.stringify(unrecoveredResourceErrors));

  const nodeErr = Object.values(nodeStatus).some(v => v.error);
  const cellErr = cellRuns.some(cell => cell.runtimeError);
  const noRunnableCells = runnableCount === 0;
  const expectedProbeErrors = errors.filter(error =>
    acceptedAuditErrors.has(error) || isExpectedTerminalFallbackProbeError(error));
  const unexpectedErrors = errors.filter(error =>
    !acceptedAuditErrors.has(error) && !isExpectedTerminalFallbackProbeError(error));
  const actionableErrors = unexpectedErrors.filter(text => {
    const cors = text.match(/Access to fetch at '([^']+)'[^]*blocked by CORS policy:[^]*No 'Access-Control-Allow-Origin'/);
    return !(cors && recoveredUrls.has(cors[1]));
  });
  console.log('EXPECTED_ACCESS_PROBE_ERRORS:', expectedProbeErrors.length);
  console.log('ACTIONABLE_PAGE_ERRORS:', JSON.stringify(actionableErrors));
  const hardFail = actionableErrors.length > 0 || unrecoveredResourceErrors.length > 0 ||
    nodeErr || cellErr || !settled || noRunnableCells;
  // Supplying a launchable makes gateway evidence mandatory even when
  // /api/agent fails to discover a token. Otherwise an authentication or relay
  // regression can erase the token and silently disable the live assertion.
  const gatewayExpected = !!CLAW_URL
    && cellRuns.some(cell => cell.expectsGateway);
  const gatewayMissing = gatewayExpected
    && cellRuns.some(cell => cell.expectsGateway && !cell.gatewayOk);

  if (hardFail) console.log('RESULT: FAIL (errors / unsettled or disabled cells / no runnable cells)');
  else if (gatewayMissing) console.log('RESULT: FAIL (OpenClaw gateway activity missing for a gateway-backed cell). ' + OPENCLAW_BACKUP_HINT);
  else console.log('RESULT: PASS' + (cellRuns.some(cell => cell.expectsGateway)
    ? ` (${ws.allFrames} gateway frames, ${ws.chatFinals} chat finals, ${ws.toolStarts.length} tool starts)` : ''));

  await browser.close();
  if (staticServer) staticServer.close();
  process.exit((hardFail || gatewayMissing) ? 1 : 0);
})().catch(e => { console.error('FATAL:', e.message); process.exit(1); });
