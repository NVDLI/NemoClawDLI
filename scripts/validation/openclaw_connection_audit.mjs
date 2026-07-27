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
ok(!mod.getOpenClawWsRelayEnabled(), 'WebSocket relay must be an explicit opt-in');
ok(mod.setOpenClawWsRelayEnabled(true) && mod.getOpenClawWsRelayEnabled(),
  'WebSocket relay opt-in was not retained');
ok(!mod.setOpenClawWsRelayEnabled(false) && !mod.getOpenClawWsRelayEnabled(),
  'WebSocket relay opt-in could not be cleared');

let rejected = false;
try { mod.normalizeOpenClawProxyBase('https://personal.' + 'workers.dev'); }
catch (_) { rejected = true; }
ok(rejected, 'personal worker relay was accepted');

// Both account-specific launchable families are recognized by one predicate, and a lookalike
// suffix is not. Normalization must reduce either family to its origin before routing.
ok(mod.isOpenClawLaunchableHost('nemoclaw-test123.apps.run.brev.nvidia.com') &&
   mod.isOpenClawLaunchableHost('nemoclaw-test123.brevlab.com'),
  'launchable host predicate does not cover both supported families');
ok(!mod.isOpenClawLaunchableHost('nemoclaw-test123.apps.run.brev.nvidia.com.evil') &&
   !mod.isOpenClawLaunchableHost('brevlab.com.evil') &&
   !mod.isOpenClawLaunchableHost('other-test123.brevlab.com') &&
   !mod.isOpenClawLaunchableHost('apps.run.brev.nvidia.com'),
  'launchable host predicate accepted a lookalike or unsupported Brev host');
let unsupportedBrevRejected = false;
try { mod.accessProviderForOpenClawUrl('https://other-test123.brevlab.com'); }
catch (error) { unsupportedBrevRejected = /NemoClaw App URL/.test(error.message); }
ok(unsupportedBrevRejected, 'unsupported Brev host did not produce actionable NemoClaw URL guidance');
ok(mod.normalizeOpenClawLaunchableUrl(pomeriumLaunchable + '/dashboard?tab=agents#card') === pomeriumLaunchable,
  'Pomerium launchable URL did not normalize to its origin');
ok(mod.normalizeOpenClawLaunchableUrl(launchable + '/dashboard?tab=agents#card') === launchable,
  'Cloudflare launchable URL did not normalize to its origin');

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

let relayDisableRejected = false;
try { mod.setOpenClawProxyConfig({ enabled: false }); }
catch (_) { relayDisableRejected = true; }
ok(relayDisableRejected, 'cross-origin Cloudflare relay could be disabled');
let arbitraryRelayRejected = false;
try { mod.normalizeOpenClawProxyBase('https://relay.example.test'); }
catch (_) { arbitraryRelayRejected = true; }
ok(arbitraryRelayRejected, 'arbitrary OpenClaw relay origin was accepted');
const forcedConfig = mod.openclawWebSocketUrl(
  launchable,
  '/cli/gateway',
  'test.jwt',
  { enabled: false, base: 'https://relay.example.test' },
  'cloudflare',
);
ok(!forcedConfig.viaProxy &&
   forcedConfig.url === 'wss://nemoclaw-test123.brevlab.com/cli/gateway' &&
   !forcedConfig.url.includes('test.jwt'),
  `explicit direct WebSocket route exposed or relayed the Cloudflare assertion: ${forcedConfig.url}`);

globalThis.location = new URL(launchable + '/course/03a-kickstart.html');
const sameOrigin = mod.openclawWebSocketUrl(launchable, '/cli/gateway', 'test.jwt', undefined, 'cloudflare');
ok(!sameOrigin.viaProxy &&
   sameOrigin.url === 'wss://nemoclaw-test123.brevlab.com/cli/gateway',
  'same-origin co-located launchable did not use its authenticated direct route');

// Terminal WebSocket selection mirrors _openshell.js: both providers are direct by default,
// while the approved Cloudflare relay remains available only through an explicit opt-in.
globalThis.location = new URL('https://course.example.test/nemoclaw/04b-modern-clis.html');
const terminalPath = '/ws/terminal?cmd=' + encodeURIComponent('bash');
function terminalRoutes(rawUrl, accessSession, accessProvider) {
  const relayEnabled = mod.getOpenClawWsRelayEnabled();
  const routed = mod.openclawWebSocketUrl(
    rawUrl,
    terminalPath,
    relayEnabled ? accessSession : '',
    relayEnabled ? mod.getOpenClawProxyConfig() : { enabled: false, base: '' },
    accessProvider,
  );
  return [routed.url];
}
const cfTerminal = terminalRoutes(launchable, 'test.jwt', 'cloudflare');
ok(cfTerminal.length === 1 &&
   cfTerminal[0] === 'wss://nemoclaw-test123.brevlab.com/ws/terminal?cmd=bash',
  `Cloudflare terminal did not keep its browser-bound direct session: ${cfTerminal.join(' , ')}`);
const pomTerminal = terminalRoutes(pomeriumLaunchable, 'opaque-session', 'pomerium');
ok(pomTerminal.length === 1 && pomTerminal[0] === 'wss://nemoclaw-test123.apps.run.brev.nvidia.com/ws/terminal?cmd=bash',
  `Pomerium terminal did not stay on one direct route: ${pomTerminal.join(' , ')}`);
ok(!/access_session|cf_access_jwt|_pomerium/.test(pomTerminal.join(' ')),
  'Pomerium terminal exposed or relayed its browser session');
mod.setOpenClawWsRelayEnabled(true);
const cfRelayTerminal = terminalRoutes(launchable, 'test.jwt', 'cloudflare');
ok(cfRelayTerminal[0] ===
   'wss://openclaw-cors-proxy.experiments.courses.nvidia.com/https/nemoclaw-test123.brevlab.com/ws/terminal?cmd=bash&cf_access_jwt=test.jwt',
  `explicit Cloudflare terminal relay opt-in was not retained: ${cfRelayTerminal.join(' , ')}`);
mod.setOpenClawWsRelayEnabled(false);
let terminalMismatchRejected = false;
try { terminalRoutes(pomeriumLaunchable, 'opaque-session', 'cloudflare'); }
catch (_) { terminalMismatchRejected = true; }
ok(terminalMismatchRejected, 'terminal route accepted a provider that does not match its launchable');

// Gateway and terminal must agree on transport for the same saved launchable, or a learner can
// reach one surface and not the other.
for (const [rawUrl, provider, session] of [
  [launchable, 'cloudflare', 'test.jwt'],
  [pomeriumLaunchable, 'pomerium', ''],
]) {
  const gateway = mod.openclawWebSocketUrl(
    rawUrl, '/cli/gateway', '', { enabled: false, base: '' }, provider);
  const terminal = terminalRoutes(rawUrl, session, provider)[0];
  ok(new URL(gateway.url).origin === new URL(terminal).origin &&
     gateway.viaProxy === /openclaw-cors-proxy/.test(terminal),
    `${provider} gateway and terminal disagree on their shared transport`);
  ok(mod.accessProviderForOpenClawUrl(rawUrl) === provider,
    `${provider} launchable no longer infers its own access provider`);
}

const openshell = fs.readFileSync('web/nemoclaw/scripts/_openshell.js', 'utf8');
ok(openshell.includes('openclawWebSocketUrl(') &&
   openshell.includes('"/ws/terminal?cmd=" + encodeURIComponent(cmd)'),
  'terminal helper bypasses shared launchable routing');
ok(openshell.includes('const wsUrls = [routed.url]') &&
   openshell.includes('getOpenClawWsRelayEnabled()') &&
   openshell.includes('{ enabled: false, base: "" }') &&
   !openshell.includes('[direct.url, routed.url]'),
  'terminal helper does not use the one provider-selected route');
ok(openshell.includes('POMERIUM_LOOPBACK_PROBES') &&
   openshell.includes('"/healthz": "http://127.0.0.1/healthz"') &&
   openshell.includes('"/api/agent": "http://127.0.0.1/api/agent"') &&
   openshell.includes('export async function openclawLoopbackProbe') &&
   !openshell.includes('curl -fsS --max-time 10 " + path'),
  'Pomerium loopback bootstrap is missing or accepts a caller-controlled shell path');
const openclaw = fs.readFileSync('web/nemoclaw/scripts/_openclaw.js', 'utf8');
ok(openclaw.includes('opts.proxyControls === true') &&
   openclaw.includes('setOpenClawProxyConfig({') &&
   openclaw.includes('proxyBaseInp.setCustomValidity(e.message)') &&
   openclaw.includes('proxyBaseInp.reportValidity()'),
  'explicit relay-override fixture no longer surfaces rejected configuration');
ok(openclaw.includes('getOpenClawWsRelayEnabled()') &&
   openclaw.includes('proxyEnabled === true') &&
   openclaw.includes('{ enabled: false, base: "" }'),
  'gateway WebSocket does not default direct while retaining explicit relay opt-in');
ok(openclaw.includes('if (route.viaProxy && accessSession)') &&
   openclaw.includes('headers["CF-Access-Jwt-Assertion"] = accessSession;') &&
   openclaw.includes('headers["X-OpenClaw-Access-Provider"] = accessProvider;') &&
   openclaw.includes('headers["X-OpenClaw-Access-Session"] = accessSession;'),
  'HTTP probe bypasses provider-aware relay headers');
ok(openclaw.includes('(route.viaProxy ? "same-origin" : "include")'),
  'direct HTTP probe does not send the browser-held launchable cookie');
ok(openclaw.includes('getOpenClawConnection()') && openclaw.includes('setOpenClawConnection({'),
  'OpenClaw widgets bypass the shared connection registry');
ok(openclaw.includes('export async function openclawBootstrapRequest') &&
   openclaw.includes('await openclawBootstrapRequest("/api/agent"') &&
   openclaw.includes('OPENCLAW_BOOTSTRAP_PATHS'),
  'bootstrap discovery does not use the shared provider-aware request helper');
// A locale page is the bytes the build publishes. When it ships from a key-based resource there is
// no HTML file to read, so the caller renders the published pages and names their root here.
const localeRoot = process.env.NEMOCLAW_LOCALE_PAGES || 'i18n';
const courseRoots = ['web/nemoclaw'];
for (const entry of fs.readdirSync(localeRoot, { withFileTypes: true })) {
  if (!entry.isDirectory()) continue;
  const metadataPath = path.join(localeRoot, entry.name, 'locale.json');
  ok(fs.existsSync(metadataPath), `${metadataPath}: every locale directory must declare locale.json`);
  const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
  ok(metadata.url_code === entry.name, `${metadataPath}: url_code must match its directory`);
  courseRoots.push(path.join(localeRoot, entry.name, 'web/nemoclaw'));
}
for (const courseRoot of courseRoots) {
  const pagePath = path.join(courseRoot, '03a-kickstart.html');
  const page = fs.readFileSync(pagePath, 'utf8');
  ok(page.includes('helpers.openclawBootstrapRequest(PATH') &&
     !page.includes("const TRANSPORT =") &&
     !page.includes('X-OpenClaw-Access-Session') &&
     !page.includes('CF-Access-Jwt-Assertion'),
    `${pagePath}: learner probe duplicated or bypassed the shared provider decision`);
}
const openclawCli = fs.readFileSync('web/nemoclaw/scripts/_openclaw_cli.js', 'utf8');
ok(openclawCli.includes('runtime.openclawGatewayWsUrl(connection.rawUrl, connection.accessSession, null, null, connection.accessProvider).url'),
  'OpenClaw CLI runtime bypasses shared gateway routing');
ok(!openclawCli.includes('return u + "/cli/gateway"'),
  'OpenClaw CLI runtime rebuilt a direct gateway URL');
for (const pagePath of courseRoots.map(root => path.join(root, '04b-modern-clis.html'))) {
  const page = fs.readFileSync(pagePath, 'utf8');
  ok(page.includes('helpers.mountOpenClawCli("#agent-chat")'), `${pagePath} bypasses the shared CLI runtime`);
  ok(!page.includes('return u + "/cli/gateway"'), `${pagePath} rebuilt a direct gateway URL`);
}

// Presenter query prefills are retired. A crafted course link must not select a launchable,
// provider, relay, or route on the learner's behalf.
clearStorage();
storage.set('nemoclaw_clawrawurl', launchable);
globalThis.location = new URL('https://course.example.test/nemoclaw/03a-kickstart.html?' + new URLSearchParams({
  openclaw_url: pomeriumLaunchable,
  openclaw_proxy: '0',
  openclaw_proxy_base: 'https://relay.example.test',
  openclaw_access_provider: 'pomerium',
}));
const queryMod = await import('data:text/javascript;base64,' + Buffer.from(source + '\n// retired-query-fixture').toString('base64'));
const queryState = queryMod.getOpenClawConnection();
ok(queryState.rawUrl === launchable &&
   queryState.accessProvider === 'auto' &&
   queryState.resolvedAccessProvider === 'cloudflare',
  'retired presenter query parameters changed normalized connection state');
ok(queryMod.getOpenClawProxyConfig().enabled === true &&
   queryMod.getOpenClawProxyConfig().base === approved,
  'retired relay query parameters changed the approved route');
ok(!storage.has('nemoclaw_openclaw_proxy_enabled_v1') &&
   !storage.has('nemoclaw_openclaw_proxy_base_v1'),
  'retired relay query parameters were persisted');
ok(!/\.get\("openclaw_(?:url|access_provider|proxy|proxy_base)"\)/.test(source),
  'OpenClaw connection runtime still reads a retired presenter query parameter');

console.log('openclaw connection audit: ok');
