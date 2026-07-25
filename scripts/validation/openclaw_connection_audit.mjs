#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import fs from 'node:fs';
import path from 'node:path';

const storage = new Map();
const secretStorage = new Map();
globalThis.localStorage = {
  getItem: key => storage.get(key) || null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: key => storage.delete(key),
};
globalThis.sessionStorage = {
  getItem: key => secretStorage.get(key) || null,
  setItem: (key, value) => secretStorage.set(key, String(value)),
  removeItem: key => secretStorage.delete(key),
};
globalThis.location = new URL('https://course.example.test/nemoclaw/03a-kickstart.html');

const source = fs.readFileSync('web/nemoclaw/scripts/_connection.js', 'utf8');
const mod = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const approved = 'https://openclaw-cors-proxy.experiments.courses.nvidia.com';
const launchable = 'https://nemoclaw-test123.brevlab.com';
const pomeriumLaunchable = 'https://nemoclaw-test123.apps.run.brev.nvidia.com';
const retired = 'https://retired-personal-relay.' + 'workers.dev/https/nemoclaw-test123.brevlab.com';

function ok(condition, message) {
  if (!condition) throw new Error(message);
}
function clearStorage() { storage.clear(); secretStorage.clear(); }

ok(mod.getOpenClawProxyConfig().enabled, 'hosted relay must default enabled');
ok(mod.getOpenClawProxyConfig().base === approved, 'hosted relay default drifted');

let rejected = false;
try { mod.normalizeOpenClawProxyBase('https://personal.' + 'workers.dev'); }
catch (_) { rejected = true; }
ok(rejected, 'personal worker relay was accepted');

storage.delete('nemoclaw_clawrawurl');
storage.set('nemoclaw_clawurl', retired);
const migration = mod.migrateOpenClawConnectionStorage();
ok(migration.rawUrl === launchable, `retired relay did not unwrap: ${migration.rawUrl}`);
ok(storage.get('nemoclaw_clawrawurl') === launchable, 'raw launchable URL was not healed');
ok(storage.get('nemoclaw_clawurl') === approved + '/https/nemoclaw-test123.brevlab.com',
  'healed effective URL does not use approved relay');
ok(!storage.get('nemoclaw_clawurl').includes('workers.dev'), 'retired relay survived migration');

const registered = mod.setOpenClawConnection({
  rawUrl: launchable,
  token: 'test-token',
  accessProvider: 'cloudflare',
  accessSession: 'test.jwt',
});
const reread = mod.getOpenClawConnection();
ok(registered.rawUrl === launchable && reread.rawUrl === launchable,
  'OpenClaw registry did not preserve the launchable URL');
ok(reread.effectiveUrl === approved + '/https/nemoclaw-test123.brevlab.com',
  'OpenClaw registry did not derive the approved relay URL');
ok(reread.token === 'test-token' && reread.accessSession === 'test.jwt' && reread.resolvedAccessProvider === 'cloudflare',
  'OpenClaw registry did not preserve credentials');
ok(!storage.get('nemoclaw_clawtoken') && !storage.get('nemoclaw_openclaw_access_session_v1') &&
   secretStorage.get('nemoclaw_clawtoken') === 'test-token' && secretStorage.get('nemoclaw_openclaw_access_session_v1') === 'test.jwt',
  'OpenClaw credentials were not restricted to tab-scoped storage');

const http = mod.openclawHttpUrl(launchable, '/api/agent');
ok(http.viaProxy && http.url === approved + '/https/nemoclaw-test123.brevlab.com/api/agent',
  `cross-origin HTTP route bypassed relay: ${http.url}`);
const ws = mod.openclawWebSocketUrl(launchable, '/cli/gateway', 'test.jwt', undefined, 'cloudflare');
ok(ws.viaProxy && ws.url === 'wss://openclaw-cors-proxy.experiments.courses.nvidia.com/https/nemoclaw-test123.brevlab.com/cli/gateway?cf_access_jwt=test.jwt',
  `cross-origin WebSocket route bypassed relay: ${ws.url}`);
ok(ws.displayUrl.includes('cf_access_jwt=...') && !ws.displayUrl.includes('test.jwt'),
  'display URL exposes access assertion');

const rotated = mod.setOpenClawConnection({ rawUrl: pomeriumLaunchable });
ok(!rotated.token && !rotated.accessSession,
  'programmatic launchable rotation retained credentials from another origin');

const pomeriumRegistered = mod.setOpenClawConnection({
  rawUrl: pomeriumLaunchable,
  accessProvider: 'pomerium',
  accessSession: 'opaque-session',
});
ok(pomeriumRegistered.resolvedAccessProvider === 'pomerium', 'Pomerium launchable was not selectable');
ok(!pomeriumRegistered.accessSession && !storage.get('nemoclaw_openclaw_access_session_v1') &&
   !secretStorage.get('nemoclaw_openclaw_access_session_v1'),
  'Pomerium browser cookie entered course-accessible storage');
const pomeriumHttp = mod.openclawHttpUrl(pomeriumLaunchable, '/api/agent');
ok(!pomeriumHttp.viaProxy && pomeriumHttp.url === 'https://nemoclaw-test123.apps.run.brev.nvidia.com/api/agent',
  `Pomerium HTTP route did not stay direct: ${pomeriumHttp.url}`);
const pomeriumWs = mod.openclawWebSocketUrl(pomeriumLaunchable, '/cli/gateway', 'opaque-session', undefined, 'pomerium');
ok(!pomeriumWs.viaProxy && pomeriumWs.url === 'wss://nemoclaw-test123.apps.run.brev.nvidia.com/cli/gateway' &&
   !/access_session|cf_access_jwt/.test(pomeriumWs.url),
  `Pomerium WebSocket route exposed or relayed its browser session: ${pomeriumWs.url}`);
let mismatchRejected = false;
try { mod.openclawWebSocketUrl(pomeriumLaunchable, '/cli/gateway', 'opaque-session', undefined, 'cloudflare'); }
catch (_) { mismatchRejected = true; }
ok(mismatchRejected, 'provider and launchable host mismatch was accepted');

mod.setOpenClawProxyConfig({ enabled: false });
const direct = mod.openclawWebSocketUrl(launchable, '/cli/gateway', 'test.jwt', undefined, 'cloudflare');
ok(!direct.viaProxy && direct.url === 'wss://nemoclaw-test123.brevlab.com/cli/gateway',
  `relay toggle did not select direct route: ${direct.url}`);

mod.setOpenClawProxyConfig({ enabled: true });
globalThis.location = new URL(launchable + '/course/03a-kickstart.html');
const sameOrigin = mod.openclawWebSocketUrl(launchable, '/cli/gateway', 'test.jwt', undefined, 'cloudflare');
ok(!sameOrigin.viaProxy, 'same-origin vendored course must bypass relay');

const openshell = fs.readFileSync('web/nemoclaw/scripts/_openshell.js', 'utf8');
ok(openshell.includes('openclawWebSocketUrl(rawUrl, "/ws/terminal?cmd="'),
  'terminal helper bypasses shared launchable routing');
ok(openshell.includes('[direct.url, routed.url]') && openshell.includes('{ enabled: false, base: "" }'),
  'terminal helper lost authenticated direct-first routing with relay fallback');
ok(openshell.includes('POMERIUM_LOOPBACK_PROBES') &&
   openshell.includes('"/healthz": "http://127.0.0.1/healthz"') &&
   openshell.includes('"/api/agent": "http://127.0.0.1/api/agent"') &&
   openshell.includes('export async function openclawLoopbackProbe') &&
   !openshell.includes('curl -fsS --max-time 10 " + path'),
  'Pomerium loopback bootstrap is missing or accepts a caller-controlled shell path');
const openclaw = fs.readFileSync('web/nemoclaw/scripts/_openclaw.js', 'utf8');
ok(openclaw.includes('if (route.viaProxy && accessSession)') &&
   openclaw.includes('headers["CF-Access-Jwt-Assertion"] = accessSession;') &&
   openclaw.includes('headers["X-OpenClaw-Access-Provider"] = accessProvider;') &&
   openclaw.includes('headers["X-OpenClaw-Access-Session"] = accessSession;'),
  'HTTP probe bypasses provider-aware relay headers');
ok(openclaw.includes('(route.viaProxy ? "same-origin" : "include")'),
  'direct HTTP probe does not send the browser-held launchable cookie');
ok(openclaw.includes('getOpenClawConnection()') && openclaw.includes('setOpenClawConnection({'),
  'OpenClaw widgets bypass the shared connection registry');
const openclawCli = fs.readFileSync('web/nemoclaw/scripts/_openclaw_cli.js', 'utf8');
ok(openclawCli.includes('runtime.openclawGatewayWsUrl(connection.rawUrl, connection.accessSession, null, null, connection.accessProvider).url'),
  'OpenClaw CLI runtime bypasses shared gateway routing');
ok(!openclawCli.includes('return u + "/cli/gateway"'),
  'OpenClaw CLI runtime rebuilt a direct gateway URL');
const cliPages = ['web/nemoclaw/04b-modern-clis.html'];
for (const entry of fs.readdirSync('i18n', { withFileTypes: true })) {
  if (!entry.isDirectory()) continue;
  const metadataPath = path.join('i18n', entry.name, 'locale.json');
  ok(fs.existsSync(metadataPath), `${metadataPath}: every locale directory must declare locale.json`);
  const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
  ok(metadata.url_code === entry.name, `${metadataPath}: url_code must match its directory`);
  cliPages.push(path.join('i18n', entry.name, 'web/nemoclaw/04b-modern-clis.html'));
}
for (const pagePath of cliPages) {
  const page = fs.readFileSync(pagePath, 'utf8');
  ok(page.includes('helpers.mountOpenClawCli("#agent-chat")'), `${pagePath} bypasses the shared CLI runtime`);
  ok(!page.includes('return u + "/cli/gateway"'), `${pagePath} rebuilt a direct gateway URL`);
}

clearStorage();
storage.set('nemoclaw_clawrawurl', launchable);
storage.set('nemoclaw_clawtoken', 'query-stale-token');
storage.set('nemoclaw_openclaw_access_session_v1', 'query-stale-session');
globalThis.location = new URL('https://course.example.test/nemoclaw/03a-kickstart.html?openclaw_url=' + encodeURIComponent(pomeriumLaunchable));
const queryRotationMod = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64') + '#query-rotation');
const queryRotated = queryRotationMod.getOpenClawConnection();
ok(queryRotated.rawUrl === pomeriumLaunchable && !queryRotated.token && !queryRotated.accessSession,
  'presenter URL rotation retained credentials from another launchable');

clearStorage();
globalThis.location = new URL('https://course.example.test/nemoclaw/03a-kickstart.html?' + new URLSearchParams({
  openclaw_url: launchable,
  openclaw_proxy: '0',
  openclaw_proxy_base: 'https://relay.example.test',
  openclaw_access_provider: 'cloudflare',
}));
const queryMod = await import('data:text/javascript;base64,' + Buffer.from(source + '\n// query-prefill-fixture').toString('base64'));
ok(storage.get('nemoclaw_clawrawurl') === launchable, 'openclaw_url query prefill was ignored');
ok(queryMod.getOpenClawProxyConfig().enabled === false, 'openclaw_proxy=0 query prefill was ignored');
ok(queryMod.getOpenClawProxyConfig().base === 'https://relay.example.test',
  'openclaw_proxy_base query prefill was ignored');
ok(storage.get('nemoclaw_openclaw_access_provider_v1') === 'cloudflare',
  'openclaw_access_provider query prefill was ignored');

console.log('openclaw connection audit: ok');
