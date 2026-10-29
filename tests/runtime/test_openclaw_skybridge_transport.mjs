// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import vm from 'node:vm';
import {randomUUID} from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';

const persistent = new Map(), tab = new Map();
const vault = new Map();
let vaultReadBarrier = null, vaultReadStarted = null, vaultFailure = false;
// Browser API fixture for Node units; signed-artifact acceptance uses real IndexedDB.
globalThis.indexedDB = {open() {
  const request = {};
  setTimeout(() => {
    request.result = {createObjectStore() {}, close() {}, transaction() {
      const transaction = {}; let pending = 0, failed = false;
      const schedule = callback => {
        pending++;
        setTimeout(async () => {
          try { await callback(); } catch (_) { failed = true; transaction.onabort?.(); }
          finally { if (--pending === 0 && !failed) queueMicrotask(() => transaction.oncomplete?.()); }
        },0);
      };
      const operation = callback => {
        const result = {};
        schedule(async () => { result.result = await callback(); result.onsuccess?.(); });
        return result;
      };
      transaction.objectStore = () => ({
        get:handle => operation(async () => {vaultReadStarted?.();if(vaultReadBarrier)await vaultReadBarrier;if(vaultFailure)throw Error();return structuredClone(vault.get(handle));}),
        put:(value,handle) => operation(() => {if(vaultFailure)throw Error();vault.set(handle,structuredClone(value));return handle;}),
        delete:handle => operation(() => vault.delete(handle)),
        openCursor() {
          const result = {}, entries = [...vault.keys()]; let index = 0;
          const next = () => schedule(() => {
            const key = entries[index++];
            result.result = key === undefined ? null : {value:vault.get(key),delete:() => vault.delete(key),continue:next};
            result.onsuccess?.();
          });
          next();return result;
        },
      });
      return transaction;
    }};
    request.onupgradeneeded?.();request.onsuccess?.();
  },0);
  return request;
}};
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

async function executeApproval(program, listed) {
  const calls = []; let output = '';
  class OwnerGateway {
    handlers = {};
    constructor() { queueMicrotask(() => this.handlers.message?.(JSON.stringify({event:'connect.challenge'}))); }
    on(name, callback) { this.handlers[name] = callback; }
    send(text) {
      const frame = JSON.parse(text);
      if (frame.method === 'device.pair.approve') calls.push(frame.params);
      const payload = frame.method === 'device.pair.list' ? listed : {};
      queueMicrotask(() => this.handlers.message?.(JSON.stringify({type:'res',id:frame.id,ok:true,payload})));
    }
    close() {}
  }
  const dependencies = {
    'node:child_process':{execFileSync:binary => binary === 'which' ? '/fixture/openclaw' :
      JSON.stringify({url:'http://127.0.0.1/#token=synthetic-owner-credential',wsUrl:'ws://127.0.0.1:18789'})},
    'node:fs':{realpathSync:value => value},
    'node:crypto':{randomUUID},
    'node:module':{createRequire:() => name => {assert.equal(name,'ws');return OwnerGateway;}},
  };
  await vm.runInNewContext(program, {require:name => {
    assert(Object.hasOwn(dependencies,name),'Unexpected dependency in approval program');return dependencies[name];
  },URL,URLSearchParams,Map,setTimeout,clearTimeout,process:{stdout:{write:value => {output += value;}}}});
  assert.doesNotMatch(output,/synthetic-owner-credential/);
  return {ok:JSON.parse(output).ok,calls};
}

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

test('a course hosted on a Brev link reads an unset launchable as unset, not as its own host', () => {
  const previous = globalThis.location;
  try {
    for (const page of ['https://course-example.gobrev.dev/dli/nemoclaw/03a-kickstart.html',
      'https://dli-example.brevlab.com/dli/nemoclaw/03a-kickstart.html',
      'https://course-example.apps.run.brev.nvidia.com/dli/nemoclaw/',
      'http://nemoclaw-new-session.gobrev.dev/dli/nemoclaw/03a-kickstart.html']) {
      globalThis.location = new URL(page);
      connection.setOpenClawConnection({rawUrl:''});
      for (const provider of ['auto', 'cloudflare', 'pomerium'])
        assert.equal(connection.accessProviderForOpenClawUrl('', provider), provider, page);
      assert.equal(connection.openclawAccessCookieName(''), '', page);
      assert.equal(connection.openclawHttpUrl('', '/api/agent').url, '', page);
      const state = connection.getOpenClawConnection();
      assert.equal(state.rawUrl, '', page);
      assert.equal(state.resolvedAccessProvider, 'auto', page);
      // An entered launchable keeps its own provider and naming rule on these pages.
      assert.equal(connection.accessProviderForOpenClawUrl(launchable), 'pomerium', page);
      assert.throws(() => connection.accessProviderForOpenClawUrl('https://other.gobrev.dev'), /NemoClaw App URL/, page);
    }
  } finally {
    globalThis.location = previous;
    connection.setOpenClawConnection({rawUrl:''});
  }
});

test('the DLI launchable serving the course is the launchable until the learner saves another', () => {
  const previous = globalThis.location;
  const other = 'https://nemoclaw-other-session.apps.run.brev.nvidia.com';
  try {
    for (const [page, provider] of [[launchable + '/dli/nemoclaw/03a-kickstart.html', 'pomerium'],
      ['https://nemoclaw-demo.brevlab.com/dli/nemoclaw/', 'cloudflare'],
      ['https://nemoclaw-demo.apps.run.brev.nvidia.com/dli/', 'pomerium']]) {
      globalThis.location = new URL(page);
      const origin = new URL(page).origin;
      connection.setOpenClawConnection({rawUrl:''});
      let state = connection.getOpenClawConnection();
      assert.equal(state.rawUrl, origin, page);
      assert.equal(state.effectiveUrl, origin, page);
      assert.equal(state.resolvedAccessProvider, provider, page);
      assert.equal(connection.openclawHttpUrl(state.rawUrl, '/api/agent').viaProxy, false, page);
      // Reading the default writes nothing; the first save binds the token to this origin.
      assert.equal(localStorage.getItem(connection.OPENCLAW_RAW_URL_KEY), null, page);
      connection.setOpenClawConnection({token:'gateway-token'});
      state = connection.getOpenClawConnection();
      assert.equal(localStorage.getItem(connection.OPENCLAW_RAW_URL_KEY), origin, page);
      assert.equal(state.token, 'gateway-token', page);
      // A launchable the learner saves still wins on this page.
      connection.setOpenClawConnection({rawUrl:other});
      state = connection.getOpenClawConnection();
      assert.equal(state.rawUrl, other, page);
      assert.equal(state.token, '', page);
    }
    // A provider left from a cleared launchable of another family never breaks the page default.
    globalThis.location = new URL(launchable + '/dli/');
    connection.setOpenClawConnection({rawUrl:''});
    localStorage.setItem(connection.OPENCLAW_ACCESS_PROVIDER_KEY, 'cloudflare');
    assert.equal(connection.getOpenClawConnection().resolvedAccessProvider, 'pomerium');
  } finally {
    globalThis.location = previous;
    connection.setOpenClawConnection({rawUrl:''});
  }
});

test('native empty-credential setup retains its device when metadata later supplies a token', () => {
  persistent.clear(); tab.clear();
  connection.setOpenClawConnection({rawUrl:launchable,accessProvider:'pomerium',accessSession:'',token:''});
  tab.set(connection.OPENCLAW_DEVICE_AUTH_KEY,'synthetic-device');
  assert.equal(connection.getOpenClawConnection().token,'');
  assert.equal(tab.get(connection.OPENCLAW_DEVICE_AUTH_KEY),'synthetic-device');
  connection.setOpenClawConnection({token:'new-gateway-credential'});
  assert.equal(tab.get(connection.OPENCLAW_DEVICE_AUTH_KEY),'synthetic-device');
  connection.setOpenClawConnection({rawUrl:'https://nemoclaw-other.gobrev.dev'});
  assert.equal(tab.has(connection.OPENCLAW_DEVICE_AUTH_KEY),false);
});

test('new handoff transport is opt-in by metadata and old gateway routes remain available', () => {
  persistent.clear(); tab.clear();
  globalThis.location = new URL('https://course.example/course.html');
  connection.setOpenClawConnection({rawUrl:launchable,accessSession:'tab-session'});
  assert.equal(new URL(openclaw.openclawGatewayWsUrl(launchable,'tab-session').url).pathname,
    '/https/nemoclaw-new-session.gobrev.dev/cli/gateway');
  connection.setOpenClawTerminalGateway(true);
  const gateway = openclaw.openclawGatewayWsUrl(launchable,'tab-session');
  assert.equal(new URL(gateway.url).pathname,'/https/nemoclaw-new-session.gobrev.dev/ws/terminal');
  assert.equal(gateway.gatewayViaTerminal,true);
  assert.equal(typeof gateway.openSocket,'function');
  assert.doesNotMatch(gateway.displayUrl,/tab-session|Buffer/);
  connection.setOpenClawTerminalGateway(false);
  assert.match(openclaw.openclawGatewayWsUrl(launchable,'tab-session').url,/\/cli\/gateway\?/);
  connection.setOpenClawTerminalGateway(true);
  connection.setOpenClawConnection({accessSession:'different-session'});
  assert.equal(openclaw.openclawGatewayWsUrl(launchable,'different-session').gatewayViaTerminal,false);
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

test('Skybridge health selects the runtime over the authenticated terminal without copying access or gateway tokens', async () => {
  const originalFetch = globalThis.fetch, originalSocket = globalThis.WebSocket;
  try {
    globalThis.fetch = async () => {throw new Error('Health must not depend on the cross-origin HTTP relay');};
    globalThis.WebSocket = class {
      constructor(url) {
        const command = new URL(url).searchParams.get('cmd');
        assert.equal(command, 'curl -fsS --max-time 10 --cookie nemoclaw_dashboard=openclaw http://127.0.0.1/healthz');
        assert.doesNotMatch(command, /gateway-sentinel|tab-session/);
        setTimeout(() => {
          this.onopen?.();
          this.onmessage?.({data:JSON.stringify({type:'data',data:'{"ok":true}'})});
          this.onmessage?.({data:JSON.stringify({type:'exit',code:0})});
        },0);
      }
      close() {}
    };
    for (const sameOrigin of [true, false]) {
      globalThis.location = new URL(sameOrigin ? launchable + '/course.html' : 'https://course.example/course.html');
      connection.setOpenClawConnection({rawUrl:launchable, token:'gateway-sentinel', accessSession:sameOrigin ? '' : 'tab-session'});
      const response = await openclaw.openclawBootstrapRequest('/healthz');
      assert.equal(response.ok,true);
      assert.equal(response.json.ok,true);
      assert.match(response.transport,/terminal-loopback$/);
    }
  } finally {globalThis.fetch = originalFetch; globalThis.WebSocket = originalSocket;}
});

test('native metadata and legacy health preserve terminal loopback discovery', async () => {
  const originalFetch = globalThis.fetch, originalSocket = globalThis.WebSocket;
  try {
    globalThis.fetch = async () => {throw new Error('Loopback reads must not use cross-origin HTTP');};
    globalThis.WebSocket = class {
      constructor(url) {
        assert.equal(new URL(url).pathname, '/ws/terminal');
        assert.match(new URL(url).searchParams.get('cmd'), /^curl -fsS --max-time 10 http:\/\/127\.0\.0\.1\/(api\/agent|healthz)$/);
        setTimeout(() => {
          this.onopen?.();
          this.onmessage?.({data:JSON.stringify({type:'data',data:JSON.stringify({agent:{dashboardUrl:'/#token=discovered-sentinel'}})})});
          this.onmessage?.({data:JSON.stringify({type:'exit',code:0})});
        },0);
      }
      close() {}
    };
    for (const [url, path] of [[launchable, '/api/agent'], ['https://nemoclaw-old.apps.run.brev.nvidia.com', '/healthz']]) {
      connection.setOpenClawConnection({rawUrl:url,accessSession:'',token:''});
      const response = await openclaw.openclawBootstrapRequest(path);
      assert.equal(response.transport,'direct-terminal-loopback');
      assert.equal(response.ok,true);
    }
  } finally {globalThis.fetch = originalFetch; globalThis.WebSocket = originalSocket;}
});

test('current launch handoff discovers a gateway credential through the terminal and uses the generic client', async () => {
  const originalSocket = globalThis.WebSocket;
  const commands = [];
  let paired = false, device, approvalProgram, legacyMetadata = false, connectCount = 0;
  try {
    globalThis.location = new URL('https://course.example/course.html');
    connection.setOpenClawConnection({rawUrl:launchable, accessSession:'tab-session', token:''});
    globalThis.WebSocket = class {
      constructor(url) {
        const parsed = new URL(url);
        this.gatewayTunnel = (parsed.searchParams.get('cmd') || '').startsWith('node -e ');
        setTimeout(async () => {
          this.onopen?.();
          if (this.gatewayTunnel) {
            this.deliver({type:'open'});
            this.deliver({type:'message',data:JSON.stringify({type:'event',event:'connect.challenge',payload:{nonce:'challenge',ts:Date.now()}})});
            return;
          }
          const command = parsed.searchParams.get('cmd');
          commands.push(command);
          let value = {agent:{agent:'openclaw',name:'my-assistant',dashboardUrl:legacyMetadata ? '/agent#token=legacy-gateway' : '/api/agent/launch'}};
          if (command.startsWith('openshell sandbox exec')) {
            assert.match(command,/^openshell sandbox exec --name my-assistant -- node -e /);
            assert.doesNotMatch(command,/tab-session/);
            const source = Buffer.from(command.match(/Buffer\.from\("([^"]+)","base64"\)/)[1],'base64').toString();
            assert.match(source,/\['dashboard','--json'\]/);
            assert.doesNotMatch(source,/bootstrapToken|\.config|process\.env/);
            value = {token:'discovered-gateway'};
            if(source.includes('device.pair.list')) {
              approvalProgram = source;
              const result = await executeApproval(source,{pending:[{
                requestId:'11111111-1111-4111-8111-111111111111',deviceId:device.id,
                publicKey:device.publicKey,scopes:['operator.read','operator.write','operator.admin'],
              }],paired:[]});
              assert.equal(result.calls.length,1);
              paired=result.ok;value={ok:paired};
            }
          }
          this.onmessage?.({data:JSON.stringify({type:'data',data:JSON.stringify(value)})});
          this.onmessage?.({data:JSON.stringify({type:'exit',code:0})});
        },0);
      }
      deliver(value) {
        this.onmessage?.({data:JSON.stringify({type:'data',data:'__DLI_GATEWAY__'+Buffer.from(JSON.stringify(value)).toString('base64')+'\n'})});
      }
      async send(data) {
        const terminalFrame = JSON.parse(data);
        assert.equal(terminalFrame.type,'input');
        const frame = JSON.parse(Buffer.from(terminalFrame.data.trim(),'base64').toString()), p = frame.params;
        assert.equal(frame.method,'connect');
        connectCount++;
        assert.equal(p.client.id,'gateway-client');
        assert.equal(p.client.mode,'ui');
        assert.deepEqual(p.scopes,['operator.read','operator.write','operator.admin']);
        assert(p.device, 'a token-only connect would silently lose every scope');
        device = p.device;
        const credential=p.auth.token||p.auth.deviceToken;
        assert(['discovered-gateway','device-gateway'].includes(credential));
        const key=await crypto.subtle.importKey('raw',Buffer.from(p.device.publicKey,'base64url'),'Ed25519',false,['verify']);
        const body=['v2',p.device.id,p.client.id,p.client.mode,'operator',p.scopes.join(','),String(p.device.signedAt),credential,p.device.nonce].join('|');
        assert(await crypto.subtle.verify('Ed25519',key,Buffer.from(p.device.signature,'base64url'),new TextEncoder().encode(body)));
        const reply=paired ? {ok:true,payload:{auth:{scopes:p.scopes,deviceToken:'device-gateway'}}}
          : {ok:false,error:{details:{code:'PAIRING_REQUIRED',requestId:'11111111-1111-4111-8111-111111111111'}}};
        setTimeout(() => this.deliver({type:'message',data:JSON.stringify({type:'res',id:frame.id,...reply})}),0);
      }
      close() {}
    };
    const refreshed = await openclaw.refreshOpenClawGatewayToken({maxAgeMs:0});
    const handle = tab.get(connection.OPENCLAW_DEVICE_AUTH_KEY);
    assert.match(handle,/^[a-f0-9-]{36}$/);
    assert.equal(refreshed.token,handle,'the existing token slot holds only an opaque locator');
    assert.equal(persistent.get(connection.OPENCLAW_TOKEN_KEY),undefined);
    assert.equal(commands.length,3);
    assert.equal((await openclaw.probeOpenClawGatewayConnection({relayWebSocket:true})).ok,true);
    await openclaw.refreshOpenClawGatewayToken();
    assert.equal(commands.length,3,'verified credential avoids another issuer invocation');
    const saved = vault.get(handle);
    assert.equal(saved.key.extractable,false);
    assert.equal(saved.encryptionKey.extractable,false);
    assert(!Object.hasOwn(saved,'deviceToken'));
    assert(!Object.hasOwn(saved,'privateKey'));
    assert.doesNotMatch(JSON.stringify([...tab]),/device-gateway|discovered-gateway|privateKey/);
    assert.doesNotMatch(JSON.stringify([...vault]),/device-gateway|discovered-gateway|privateKey/);
    await assert.rejects(crypto.subtle.exportKey('pkcs8',saved.key));
    await assert.rejects(crypto.subtle.exportKey('raw',saved.encryptionKey));
    assert.equal(persistent.has(connection.OPENCLAW_DEVICE_AUTH_KEY),false);
    const freshModule = await import(pathToFileURL(path.join(course,'scripts/_gateway_auth.js')).href + '?navigation');
    const restored = await freshModule.openclawGatewayConnectParams(handle,{nonce:'new-challenge',ts:Date.now()});
    assert.equal(restored.auth.deviceToken,'device-gateway');
    assert.equal(restored.device.id,device.id,'page navigation must retain the same tab identity');
    assert.equal(commands.length,3,'navigation must not enqueue another approval');
    await openclaw.refreshOpenClawGatewayToken({maxAgeMs:0});
    assert.equal(commands.length,4,'metadata refresh must reuse the signed device without another CLI issuer or approval');
    assert.equal(commands.filter(command=>command.startsWith('openshell')).length,2);
    assert.equal(saved.iv.length,12);
    const corrupted=structuredClone(saved);
    new Uint8Array(corrupted.ciphertext)[0] ^= 1;
    vault.set(handle,corrupted);
    const corruptModule=await import(pathToFileURL(path.join(course,'scripts/_gateway_auth.js')).href+'?corrupt');
    await assert.rejects(corruptModule.openclawGatewayConnectParams(handle,{nonce:'corrupt',ts:Date.now()}),/run Connect again/);
    vault.set(handle,saved);
    vault.set('expired-orphan',{expiresAt:Date.now()-1});
    const cleanupModule=await import(pathToFileURL(path.join(course,'scripts/_gateway_auth.js')).href+'?cleanup');
    assert.equal((await cleanupModule.openclawGatewayConnectParams(handle,{nonce:'cleanup',ts:Date.now()})).device.id,device.id);
    assert.equal(vault.has('expired-orphan'),false);
    vault.delete(handle);
    const evictedModule=await import(pathToFileURL(path.join(course,'scripts/_gateway_auth.js')).href+'?evicted');
    await assert.rejects(evictedModule.openclawGatewayConnectParams(handle,{nonce:'evicted',ts:Date.now()}),/run Connect again/);
    vault.set(handle,saved);
    vaultFailure=true;
    const unavailableModule=await import(pathToFileURL(path.join(course,'scripts/_gateway_auth.js')).href+'?unavailable');
    await assert.rejects(unavailableModule.openclawGatewayConnectParams(handle,{nonce:'unavailable',ts:Date.now()}),/storage failed/);
    vaultFailure=false;
    const raceSigner=await import(pathToFileURL(path.join(course,'scripts/_gateway_auth.js')).href+'?sign-race');
    const originalSign=crypto.subtle.sign;
    let releaseSign, signingStarted;
    const signing=new Promise(resolve=>{signingStarted=resolve;});
    const signingBarrier=new Promise(resolve=>{releaseSign=resolve;});
    crypto.subtle.sign=async function(...args) {signingStarted();await signingBarrier;return originalSign.apply(this,args);};
    try {
      const signedConnection=connection.getOpenClawConnection(), beforeSigning=connectCount;
      const lateHandshake=raceSigner.reuseOpenClawGatewayAuth(signedConnection);
      await signing;
      connection.setOpenClawConnection({rawUrl:'',accessSession:'',token:''});
      connection.setOpenClawConnection(signedConnection);
      releaseSign();
      await assert.rejects(lateHandshake,/gateway changed/);
      assert.equal(connectCount,beforeSigning,'cleared enrollment cannot send stale signed credentials');
      assert.equal(tab.has(connection.OPENCLAW_DEVICE_AUTH_KEY),false);
    } finally {releaseSign();crypto.subtle.sign=originalSign;}
    tab.set(connection.OPENCLAW_DEVICE_AUTH_KEY,handle);
    const owned={requestId:'11111111-1111-4111-8111-111111111111',deviceId:device.id,
      publicKey:device.publicKey,scopes:['operator.read','operator.write','operator.admin']};
    for (const [label, mutation] of [
      ['request ID',{requestId:'22222222-2222-4222-8222-222222222222'}],
      ['device ID',{deviceId:'another-device'}],
      ['public key',{publicKey:'another-key'}],
      ['excess scope',{scopes:[...owned.scopes,'operator.pairing']}],
    ]) {
      const rejected=await executeApproval(approvalProgram,{pending:[{...owned,...mutation}],paired:[]});
      assert.equal(rejected.ok,false,label);
      assert.equal(rejected.calls.length,0,label);
    }
    const missing=await executeApproval(approvalProgram,{pending:[],paired:[]});
    assert.equal(missing.ok,false);
    assert.equal(missing.calls.length,0);
    const unrelated={...owned,requestId:'33333333-3333-4333-8333-333333333333',publicKey:'unrelated-key'};
    const selected=await executeApproval(approvalProgram,{pending:[unrelated,owned],paired:[]});
    assert.equal(selected.ok,true);
    assert.equal(selected.calls.length,1);
    assert.equal(selected.calls[0].requestId,owned.requestId);
    const removedRequestGuard=approvalProgram.replace('item.requestId===input.requestId&&','');
    assert.notEqual(removedRequestGuard,approvalProgram);
    const weakened=await executeApproval(removedRequestGuard,{pending:[{...owned,requestId:'44444444-4444-4444-8444-444444444444'}],paired:[]});
    assert.equal(weakened.ok,true,'negative control must expose the removed request guard');
    const originalConnection=connection.getOpenClawConnection();
    connection.setOpenClawConnection({accessSession:'different-binding'});
    tab.set(connection.OPENCLAW_DEVICE_AUTH_KEY,handle);
    const wrongBinding=await import(pathToFileURL(path.join(course,'scripts/_gateway_auth.js')).href+'?wrong-binding');
    await assert.rejects(wrongBinding.openclawGatewayConnectParams(handle,{nonce:'wrong-binding',ts:Date.now()}),/run Connect again/);
    connection.setOpenClawConnection(originalConnection);
    tab.set(connection.OPENCLAW_DEVICE_AUTH_KEY,handle);
    legacyMetadata = true;
    const legacy = await openclaw.refreshOpenClawGatewayToken({maxAgeMs:0});
    assert.equal(legacy.token,'legacy-gateway');
    assert.equal(tab.has(connection.OPENCLAW_DEVICE_AUTH_KEY),false);
    assert.equal(openclaw.openclawGatewayWsUrl(launchable,'tab-session').gatewayViaTerminal,false);
    const legacyParams = await openclaw.openclawGatewayConnectParams(legacy.token,{nonce:'legacy-challenge',ts:Date.now()});
    assert.deepEqual(legacyParams.auth,{token:'legacy-gateway'});
    assert.equal(legacyParams.device,undefined,'same-host legacy metadata must discard stale device authentication');
    const previous = connection.getOpenClawConnection();
    connection.setOpenClawConnection({rawUrl:'',token:'',accessSession:''});
    connection.setOpenClawConnection({...previous,token:'reentered-gateway'});
    const cleared = await freshModule.openclawGatewayConnectParams('reentered-gateway',{nonce:'after-clear',ts:Date.now()});
    assert.deepEqual(cleared.auth,{token:'reentered-gateway'},'explicit clear must not resurrect a cached device credential');
    assert.equal(cleared.device,undefined,'re-entering the same host and session cannot restore the cleared identity');
    const captured = connection.getOpenClawConnection();
    connection.setOpenClawConnection({rawUrl:launchable,accessSession:'replacement-session'});
    assert.equal(tab.has(connection.OPENCLAW_DEVICE_AUTH_KEY),false,'credential changes clear the device record');
    await assert.rejects(freshModule.openclawGatewayConnectParams('discovered-gateway',
      {nonce:'late-challenge',ts:Date.now()},null,captured),/gateway changed/);
    connection.setOpenClawConnection({rawUrl:launchable,accessSession:'tab-session',token:handle});
    tab.set(connection.OPENCLAW_DEVICE_AUTH_KEY,handle);
    let release;
    vaultReadBarrier=new Promise(resolve=>{release=resolve;});
    const started=new Promise(resolve=>{vaultReadStarted=resolve;});
    const raceModule=await import(pathToFileURL(path.join(course,'scripts/_gateway_auth.js')).href+'?clear-race');
    const pending=raceModule.openclawGatewayConnectParams(handle,{nonce:'late-restore',ts:Date.now()});
    await started;
    const beforeClear=connection.getOpenClawConnection();
    connection.setOpenClawConnection({rawUrl:'',accessSession:'',token:''});
    connection.setOpenClawConnection(beforeClear);
    release();
    await assert.rejects(pending,/gateway changed/);
    assert.equal(tab.has(connection.OPENCLAW_DEVICE_AUTH_KEY),false,'late decryption cannot resurrect a cleared identity');
    vaultReadBarrier=null;vaultReadStarted=null;
    connection.setOpenClawTerminalGateway(true);
    vaultFailure=true;
    const failedWrite=await import(pathToFileURL(path.join(course,'scripts/_gateway_auth.js')).href+'?failed-write');
    const beforeWrite=vault.size;
    await assert.rejects(failedWrite.prepareOpenClawGatewayAuth('my-assistant','discovered-gateway',connection.getOpenClawConnection()),/storage failed/);
    assert.equal(vault.size,beforeWrite,'failed retention leaves no credential record');
    assert.equal(tab.has(connection.OPENCLAW_DEVICE_AUTH_KEY),false);
    const unretained=await failedWrite.openclawGatewayConnectParams('legacy-sentinel',{nonce:'after-failed-write',ts:Date.now()});
    assert.equal(unretained.device,undefined,'failed persistence must not leave an active signed device');
    vaultFailure=false;
  } finally {globalThis.WebSocket = originalSocket;vaultReadBarrier=null;vaultReadStarted=null;vaultFailure=false;}
});

test('a successful gateway hello without the course scopes cannot pass the connection audit', async () => {
  const originalSocket = globalThis.WebSocket;
  try {
    for (const scopes of [[],['operator.read'],['operator.read','operator.write','operator.admin']]) {
      connection.setOpenClawConnection({rawUrl:'https://nemoclaw-grant-check.apps.run.brev.nvidia.com',token:'gateway-sentinel',accessSession:''});
      globalThis.WebSocket = class {
        constructor() {
          setTimeout(() => this.onmessage?.({data:JSON.stringify({type:'event',event:'connect.challenge',payload:{nonce:'challenge',ts:Date.now()}})}),0);
        }
        send(data) {
          const frame = JSON.parse(data);
          assert.deepEqual(frame.params.client,{id:'openclaw-control-ui',version:'0.1.0',platform:'browser',mode:'webchat'},
            'legacy token metadata must preserve the established client identity');
          assert.equal(frame.params.device,undefined,'legacy metadata must not silently enroll a device');
          setTimeout(() => this.onmessage?.({data:JSON.stringify({type:'res',id:frame.id,ok:true,payload:{auth:{scopes}}})}),0);
        }
        close() {}
      };
      const result = await openclaw.probeOpenClawGatewayConnection();
      assert.equal(result.ok,scopes.length === 3);
      if (!result.ok) assert.match(result.error,/required course permissions/);
    }
  } finally {globalThis.WebSocket = originalSocket;}
});

test('untrusted or malformed dashboard handoffs cannot enqueue credential discovery', async () => {
  const originalSocket = globalThis.WebSocket;
  try {
    for (const agent of [
      {agent:'openclaw',name:'my-assistant',dashboardUrl:'https://evil.example/api/agent/launch'},
      {agent:'openclaw',name:'my-assistant',dashboardUrl:'/api/agent/launch?untrusted=1'},
      {agent:'openclaw',name:'my-assistant;whoami',dashboardUrl:'/api/agent/launch'},
      {agent:'hermes',name:'my-assistant',dashboardUrl:'/api/agent/launch'},
    ]) {
      connection.setOpenClawConnection({rawUrl:launchable,token:'',accessSession:''});
      globalThis.WebSocket = class {
        constructor(url) {
          assert.match(new URL(url).searchParams.get('cmd'),/^curl /);
          setTimeout(() => {
            this.onopen?.();
            this.onmessage?.({data:JSON.stringify({type:'data',data:JSON.stringify({agent})})});
            this.onmessage?.({data:JSON.stringify({type:'exit',code:0})});
          },0);
        }
        close() {}
      };
      await assert.rejects(openclaw.refreshOpenClawGatewayToken({maxAgeMs:0}),/did not provide a gateway token/);
      assert.equal(connection.getOpenClawConnection().token,'');
    }
  } finally {globalThis.WebSocket = originalSocket;}
});

test('diagnostics redact browser and device bootstrap URL credentials', () => {
  const value = openclaw.redactOpenClawDiagnostic({url:'https://native.example/agent#bootstrapToken=sentinel&deviceToken=other'});
  assert.doesNotMatch(JSON.stringify(value),/sentinel|=other/);
});

test('late handoff credentials cannot overwrite a stopped or replaced connection', async () => {
  const originalSocket = globalThis.WebSocket;
  try {
    for (const change of ['cancel','host','session']) {
      connection.setOpenClawConnection({rawUrl:launchable,token:'',accessSession:'original-session'});
      let issuer, started;
      const entered = new Promise(resolve => {started=resolve;});
      globalThis.WebSocket = class {
        constructor(url) {
          if (new URL(url).searchParams.get('cmd').startsWith('openshell')) {
            issuer=this; started(); return;
          }
          setTimeout(() => {
            this.onopen?.();
            this.onmessage?.({data:JSON.stringify({type:'data',data:JSON.stringify({agent:{agent:'openclaw',name:'my-assistant',dashboardUrl:'/api/agent/launch'}})})});
            this.onmessage?.({data:JSON.stringify({type:'exit',code:0})});
          },0);
        }
        close() {}
      };
      const controller = new AbortController();
      const pending = openclaw.refreshOpenClawGatewayToken({maxAgeMs:0,signal:controller.signal});
      await entered;
      if (change === 'cancel') controller.abort();
      else connection.setOpenClawConnection({rawUrl:change === 'host' ? 'https://nemoclaw-replacement.gobrev.dev' : launchable,
        accessSession:'replacement-session',token:'replacement-gateway'});
      const expected = connection.getOpenClawConnection();
      issuer.onopen?.();
      issuer.onmessage?.({data:JSON.stringify({type:'data',data:'{"token":"late-gateway"}'})});
      issuer.onmessage?.({data:JSON.stringify({type:'exit',code:0})});
      await assert.rejects(pending);
      assert.deepEqual(connection.getOpenClawConnection(),expected,change);
    }
  } finally {globalThis.WebSocket = originalSocket;}
});
