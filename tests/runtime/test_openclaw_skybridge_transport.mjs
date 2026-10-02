// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';

const persistent = new Map(), tab = new Map();
const storage = map => ({getItem:key => map.get(key) ?? null,
  setItem:(key,value) => map.set(key,String(value)), removeItem:key => map.delete(key)});
globalThis.localStorage = storage(persistent);
globalThis.sessionStorage = storage(tab);
globalThis.location = new URL('https://course.example/course.html');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const course = createRequire(import.meta.url)('./course_exercise_fixture.cjs').discoverCourses(root).roots[0];
const connection = await import(pathToFileURL(path.join(course, 'scripts/_connection.js')));
const openclaw = await import(pathToFileURL(path.join(course, 'scripts/_openclaw.js')));
const launchable = 'https://nemoclaw-new-session.gobrev.dev';

test('Skybridge onboarding links normalize and use the correct host-bound cookie', () => {
  for (const suffix of ['/onboard', '/onboard?view=agent#token=sentinel', '/dashboard/']) {
    const url = launchable + suffix;
    assert.equal(connection.normalizeOpenClawLaunchableUrl(url), launchable);
    assert.equal(connection.accessProviderForOpenClawUrl(url), 'pomerium');
    assert.equal(connection.openclawAccessCookieName(url), '__Host-skybridge-brev-prd');
    assert.equal(connection.openclawHttpUrl(url, '/api/agent').url, launchable + '/api/agent');
    assert.equal(openclaw.openclawGatewayWsUrl(url).url, launchable.replace('https:', 'wss:') + '/cli/gateway');
  }
  assert.equal(connection.openclawAccessCookieName('https://nemoclaw-old.apps.run.brev.nvidia.com'), '_pomerium');
  assert.equal(connection.openclawAccessCookieName('https://nemoclaw-old.brevlab.com'), 'CF_Authorization');
});

test('Skybridge manual fallback is tab-scoped, redacted and cleared on host rotation', () => {
  connection.setOpenClawConnection({rawUrl:launchable + '/onboard', accessSession:'tab-session', token:'gateway-sentinel'});
  assert.equal(tab.get(connection.OPENCLAW_ACCESS_SESSION_KEY), 'tab-session');
  assert.equal(persistent.get(connection.OPENCLAW_ACCESS_SESSION_KEY), undefined);
  const route = openclaw.openclawGatewayWsUrl(launchable, 'tab-session');
  assert.equal(route.viaProxy, true);
  assert.match(route.url, /access_provider=pomerium/);
  assert.doesNotMatch(route.displayUrl, /tab-session/);
  const diagnostic = openclaw.redactOpenClawDiagnostic({
    text:'__Host-skybridge-brev-prd=tab-session; cf_clearance=browser-only',
    '__Host-skybridge-brev-prd':'tab-session', cf_clearance:'browser-only',
    cookies:{novelName:'nested-secret'},
    url:route.url,
  });
  assert.doesNotMatch(JSON.stringify(diagnostic), /tab-session|browser-only|nested-secret/);
  connection.setOpenClawConnection({rawUrl:'https://nemoclaw-old.apps.run.brev.nvidia.com'});
  assert.equal(connection.getOpenClawConnection().accessSession, '');
  assert.equal(connection.getOpenClawConnection().token, '');
});

test('same-origin Skybridge stays direct, and unrelated hosts cannot claim its credentials', () => {
  globalThis.location = new URL(launchable + '/course/03a-kickstart.html');
  assert.equal(connection.openclawHttpUrl(launchable, '/api/agent', undefined, 'pomerium', 'tab-session').viaProxy, false);
  assert.equal(connection.isOpenClawLaunchableHost('nemoclaw-' + 'a'.repeat(54) + '.gobrev.dev'), true);
  for (const host of ['other.gobrev.dev', 'nemoclaw-demo.gobrev.dev.evil', 'nested.nemoclaw-demo.gobrev.dev', 'nemoclaw-.gobrev.dev', 'nemoclaw-' + 'a'.repeat(55) + '.gobrev.dev']) {
    assert.equal(connection.isOpenClawLaunchableHost(host), false, host);
  }
  assert.throws(() => connection.accessProviderForOpenClawUrl(launchable, 'cloudflare'), /does not match/);
});

test('shared routing changes cannot pair another tab host with this tab credentials', () => {
  persistent.clear(); tab.clear();
  globalThis.location = new URL('https://course.example/course.html');
  const otherTab = new Map();
  connection.setOpenClawConnection({rawUrl:'https://nemoclaw-old.apps.run.brev.nvidia.com',
    accessSession:'old-tab-session',token:'old-tab-token'});
  globalThis.sessionStorage = storage(otherTab);
  connection.setOpenClawConnection({rawUrl:launchable,accessSession:'new-tab-session',token:'new-tab-token'});
  globalThis.sessionStorage = storage(tab);
  assert.equal(connection.getOpenClawConnection().rawUrl,launchable);
  assert.equal(connection.getOpenClawConnection().accessSession,'');
  assert.equal(connection.getOpenClawConnection().token,'');
  globalThis.sessionStorage = storage(otherTab);
  assert.equal(connection.getOpenClawConnection().accessSession,'new-tab-session');
  assert.equal(connection.getOpenClawConnection().token,'new-tab-token');
  globalThis.sessionStorage = storage(tab);
});

test('unbound legacy secrets and unavailable tab storage do not become persistent credentials', () => {
  persistent.clear(); tab.clear();
  persistent.set(connection.OPENCLAW_RAW_URL_KEY,launchable);
  persistent.set(connection.OPENCLAW_TOKEN_KEY,'legacy-persistent-token');
  tab.set(connection.OPENCLAW_ACCESS_SESSION_KEY,'legacy-unbound-session');
  assert.equal(connection.getOpenClawConnection().token,'');
  assert.equal(connection.getOpenClawConnection().accessSession,'');
  assert.equal(persistent.has(connection.OPENCLAW_TOKEN_KEY),false);
  globalThis.sessionStorage = null;
  connection.setOpenClawConnection({rawUrl:launchable,accessSession:'unstored-session',token:'unstored-token'});
  assert.equal(persistent.has(connection.OPENCLAW_ACCESS_SESSION_KEY),false);
  assert.equal(persistent.has(connection.OPENCLAW_TOKEN_KEY),false);
  assert.equal(connection.getOpenClawConnection().accessSession,'');
  globalThis.sessionStorage = storage(tab);
});

test('late metadata cannot restore credentials after cancellation or connection edits', async () => {
  const originalUrl = 'https://nemoclaw-original.brevlab.com';
  const originalFetch = globalThis.fetch;
  try {
    for (const change of ['cancel', 'host', 'session']) {
      persistent.clear(); tab.clear();
      let release, started;
      const pending = new Promise(resolve => {release = resolve;});
      const entered = new Promise(resolve => {started = resolve;});
      // Deliberately ignore AbortSignal to test the persistence boundary too.
      globalThis.fetch = async () => {started(); return pending;};
      const controller = new AbortController();
      const audit = openclaw.runOpenClawConnectionAudit({
        baseUrl:originalUrl,accessSession:'original-session',signal:controller.signal,
      });
      await entered;
      if (change === 'cancel') controller.abort();
      else connection.setOpenClawConnection({
        rawUrl:change === 'host' ? 'https://nemoclaw-next.gobrev.dev' : originalUrl,
        accessSession:'replacement-session',token:'replacement-token',
      });
      const expected = connection.getOpenClawConnection();
      release(new Response(JSON.stringify({agent:{dashboardUrl:'/#token=late-token'}}),
        {headers:{'Content-Type':'application/json'}}));
      await assert.rejects(audit,/Connection test stopped/);
      assert.deepEqual(connection.getOpenClawConnection(),expected,change);
    }
    const controller = new AbortController();
    controller.abort();
    const expected = connection.getOpenClawConnection();
    await assert.rejects(openclaw.runOpenClawConnectionAudit({
      baseUrl:launchable,signal:controller.signal,
    }),/Connection test stopped/);
    assert.deepEqual(connection.getOpenClawConnection(),expected);
  } finally {globalThis.fetch = originalFetch;}
});
