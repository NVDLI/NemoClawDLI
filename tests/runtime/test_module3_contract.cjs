/* Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {pathToFileURL} = require('node:url');
const {webcrypto} = require('node:crypto');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const {discoverCourses} = require('./course_exercise_fixture.cjs');

const root = process.env.COURSE_SOURCE_ROOT;
assert(root, 'COURSE_SOURCE_ROOT is required');
const {roots} = discoverCourses(root);
const runtime = import(pathToFileURL(path.join(roots[0], 'scripts/_shared.js')));

function htmlFiles(directory) {
  return fs.readdirSync(directory, {withFileTypes:true}).flatMap(entry => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? htmlFiles(file) : entry.name.endsWith('.html') ? [file] : [];
  });
}

// Evaluate actual module registrations, including their shared snippet expansion.
// Navigation and diagram rendering are inert; no displayed cell runs at capture time.
async function displayed(directory) {
  const shared = await runtime;
  const flows = new Map();
  for (const file of htmlFiles(directory)) {
    const html = fs.readFileSync(file, 'utf8');
    for (const match of html.matchAll(/<script\b[^>]*type=["']module["'][^>]*>([\s\S]*?)<\/script>/g)) {
      if (!/mountCanvasFlow\(["']#(?:cell-personas|cell-memory|cell-skill|probe-cron)["']/.test(match[1])) continue;
      const register = (selector, options) => {
        assert(!flows.has(selector), `duplicate flow ${selector} in ${file}`);
        flows.set(selector, options.nodes);
      };
      const element = {innerHTML:'', textContent:'', classList:{add(){},remove(){}}, addEventListener(){}};
      const scope = {
        GW_CONNECT:shared.GW_CONNECT, mountCanvasFlow:register, mountRunCell(){},
        buildNav(){return '';}, updateKeyPill(){}, updateClawPill(){}, mountJourneyMap(){}, mountGwRecover(){}, mountDiagram(){},
        document:{getElementById(){return element;}}, hljs:{highlightAll(){}},
      };
      const source = match[1].replace(/^\s*import\s+[\s\S]*?\s+from\s+["'][^"']+["'];?/gm, '');
      vm.runInNewContext(source, scope, {filename:file, timeout:1000});
    }
  }
  const cell = (selector, id) => {
    const nodes = flows.get(selector);
    assert(nodes, `missing displayed flow ${selector} in ${directory}`);
    const matches = nodes.filter(node => node.id === id);
    assert.equal(matches.length, 1, `one displayed ${selector}/${id}`);
    assert.equal(typeof matches[0].code, 'string');
    return matches[0].code;
  };
  return {
    general:cell('#cell-personas','ask-a'), review:cell('#cell-personas','ask-b'),
    write:cell('#cell-memory','write'), recall:cell('#cell-memory','recall'),
    install:cell('#cell-skill','sk-install'), trigger:cell('#cell-skill','sk-trigger'),
    cron:cell('#probe-cron','cr-run'), remove:cell('#probe-cron','cr-rm'),
  };
}

async function fixture(options = {}) {
  const shared = await runtime;
  const controller = new AbortController();
  const state = {...options.state};
  const owner = options.owner || 'https://gateway.example.test';
  const storage = new Map(options.storage || []);
  const entries = [], calls = [], sockets = [], commands = [], files = new Map();
  let time = Date.parse('2026-01-01T00:00:00Z'), histories = 0, job = null;
  const ownedId = 'server-owned-opaque-id';
  const log = (...args) => { entries.push(args); return {textContent:'', setAttribute(){}}; };
  log.details = log;
  log.html = log;
  const f = {state, controller, storage, entries, calls, sockets, commands, files, owner, ownedId};
  const key = 'module3-owned-cron:' + owner;
  f.key = key;
  const gateway = async (method, params) => {
    if (options.gateway) {
      const override = await options.gateway(method, params, f);
      if (override !== undefined) return override;
    }
    if (method === 'connect') return {server:{version:'fixture'},auth:{scopes:['operator.read','operator.write']}};
    if (method === 'sessions.messages.subscribe' || method === 'chat.abort') return {};
    if (method === 'chat.send') return {runId:'model-run-' + calls.length};
    if (method === 'cron.add') {
      assert.equal(params.schedule.kind, 'at');
      assert(Number.isFinite(Date.parse(params.schedule.at)), 'valid scheduled timestamp');
      assert(Date.parse(params.schedule.at) > time, 'one-shot scheduled in the future');
      assert.equal(params.deleteAfterRun, true);
      assert.equal(params.sessionTarget, 'isolated');
      assert.equal(params.wakeMode, 'now');
      assert.equal(params.payload.kind, 'agentTurn');
      assert.equal(typeof params.payload.message, 'string');
      assert(!Object.hasOwn(params, 'id'), 'server owns the job ID');
      assert(!Object.hasOwn(params, 'prompt'), 'agent prompt belongs inside payload');
      assert(params.payload.message.includes(state.cronFile));
      assert(params.payload.message.includes(state.cronReference));
      assert.notEqual(params.name, ownedId);
      assert(!state._ws, 'Canvas Stop cannot close the connection reserved for cleanup');
      if (options.noId) return {};
      job = {id:ownedId, name:params.name};
      return {id:ownedId};
    }
    if (method === 'cron.runs') {
      assert.equal(params.id, ownedId, 'poll the server-returned ID');
      histories++;
      if (options.runFailure) return {entries:[{status:'error',error:'fixture run failure'}]};
      if (options.neverComplete || histories === 1) return {entries:[]};
      files.set(state.cronFile, options.mismatch ? 'wrong file reference' : state.cronReference + '\n');
      return {entries:[{status:'ok',runId:'scheduled-run'}]};
    }
    if (method === 'cron.remove') {
      assert.equal(params.id, ownedId, 'remove only the server-returned owned ID');
      assert.equal(sockets.at(-1).readyState, 1, 'cleanup transport remains open');
      if (options.removeFailure) throw new Error('fixture removal unavailable');
      if (!options.stillPresent) job = null;
      return {removed:true};
    }
    if (method === 'cron.list') return {jobs:job ? [job, {id:'foreign-id',name:'unrelated'}] : [{id:'foreign-id',name:'unrelated'}]};
    throw new Error('Unexpected gateway method: ' + method);
  };
  class GatewaySocket {
    constructor() {
      this.readyState = 1;
      sockets.push(this);
      queueMicrotask(() => this.deliver({type:'event',event:'connect.challenge',payload:{nonce:'fixture'}}));
    }
    deliver(data) { this.onmessage?.({data:JSON.stringify(data)}); }
    send(text) {
      assert.equal(this.readyState, 1);
      const request = JSON.parse(text);
      calls.push({method:request.method, params:request.params});
      Promise.resolve().then(() => gateway(request.method, request.params)).then(payload => {
        this.deliver({type:'res',id:request.id,ok:true,payload});
        if (request.method === 'chat.send') {
          const content = options.answer ? options.answer(request.params, f) : (state.memoryReference || state.runbookReference || 'fixture answer');
          this.deliver({type:'event',event:'chat',payload:{runId:payload.runId,sessionKey:request.params.sessionKey,state:'final',message:{content}}});
        }
      }, error => this.deliver({type:'res',id:request.id,ok:false,error:{message:error.message}}));
    }
    close() { if (this.readyState === 3) return; this.readyState = 3; this.onclose?.({code:1000}); }
  }
  class Clock extends Date { static now() { return time; } }
  const helpers = {
    ...shared, signal:controller.signal, log,
    refreshOpenClawGatewayToken:async () => ({token:'fixture-only-token'}),
    getOpenClawConnection:() => ({rawUrl:owner}),
    openclawGatewayWsUrl:() => ({url:'wss://gateway.example.test',displayUrl:'fixture gateway'}),
    delay:async (_ms, signal) => {
      assert.equal(signal, controller.signal, 'poll waiting observes this cell Stop');
      if (options.stop) controller.abort();
      signal.throwIfAborted();
      time += options.neverComplete ? 180000 : 5000;
    },
    sandboxExec:async (command, {signal} = {}) => {
      assert.equal(signal, controller.signal, 'file verification observes this cell Stop');
      signal.throwIfAborted();
      commands.push(command);
      if (options.shellFailure) return {exitCode:1,output:'fixture command failure'};
      const read = command.match(/base64 < '([^']+)'/);
      if (read) {
        let content = files.get(read[1]);
        if (options.read) content = options.read(read[1], f);
        if (content === undefined) return {exitCode:1,output:'fixture file missing'};
        return {exitCode:0,output:'\x1e' + Buffer.from(content).toString('base64') + '\x1f'};
      }
      for (const write of command.matchAll(/printf '%s' '([^']+)' \| base64 -d > '([^']+)'/g))
        files.set(write[2], Buffer.from(write[1], 'base64').toString());
      return {exitCode:0,output:''};
    },
  };
  const globals = {
    crypto:webcrypto, Date:Clock, WebSocket:GatewaySocket, AbortController, DOMException,
    setTimeout, clearTimeout, TextEncoder, TextDecoder, btoa, atob,
    sessionStorage:{getItem:k => storage.get(k) ?? null,setItem:(k,v) => storage.set(k,v),removeItem:k => storage.delete(k)},
  };
  f.helpers = helpers;
  f.execute = code => vm.runInNewContext('(async (helpers, state) => {\n' + code + '\n})', globals)(helpers,state);
  f.close = () => { for (const socket of sockets) socket.close(); };
  return f;
}

for (const directory of roots) {
  const label = path.relative(root, directory);
  const cells = displayed(directory);
  test(`${label}: dependent review, recall and skill cells fail before issuing a request`, async () => {
    const d = await cells;
    for (const code of [d.review,d.recall,d.trigger]) {
      const f = await fixture();
      try { await assert.rejects(f.execute(code), error => Boolean(error.message)); assert.equal(f.calls.length,0); }
      finally { f.close(); }
    }
  });

  test(`${label}: review prerequisites cannot bypass the shared connection guard`, async () => {
    const d = await cells;
    const f = await fixture({state:{question:'fixture question'}});
    try { await assert.rejects(f.execute(d.review), /Connect/); assert.equal(f.calls.length,0); }
    finally { f.close(); }
  });

  test(`${label}: independent reviews use distinct sessions and retain the same question`, async () => {
    const d = await cells, f = await fixture();
    try {
      await f.execute(d.general); await f.execute(d.review);
      const turns = f.calls.filter(call => call.method === 'chat.send');
      assert.equal(turns.length,2);
      assert.notEqual(turns[0].params.sessionKey,turns[1].params.sessionKey);
      assert(turns.every(call => call.params.message.includes(f.state.question)));
      assert.notEqual(turns[0].params.message,turns[1].params.message);
      assert.equal(f.commands.length,0, 'comparison does not rewrite workspace files');
    } finally { f.close(); }
  });

  test(`${label}: memory success requires disk evidence and a fresh-session reference`, async () => {
    const d = await cells;
    for (const mode of ['success','missing-file','missing-reference','wrong-recall']) {
      const f = await fixture({
        read:(_path, fixture) => mode === 'missing-file' ? undefined : fixture.state.memoryLabel + (mode === 'missing-reference' ? '' : ' ' + fixture.state.memoryReference),
        answer:(_params, fixture) => mode === 'wrong-recall' ? 'I remember everything.' : fixture.state.memoryReference,
      });
      try {
        if (mode === 'missing-file' || mode === 'missing-reference') {
          await assert.rejects(f.execute(d.write)); assert.equal(f.state.memoryVerified,false);
        } else {
          await f.execute(d.write); assert.equal(f.state.memoryVerified,true);
          if (mode === 'wrong-recall') await assert.rejects(f.execute(d.recall)); else await f.execute(d.recall);
          const turns = f.calls.filter(call => call.method === 'chat.send');
          assert.equal(turns.length,2); assert.notEqual(turns[0].params.sessionKey,turns[1].params.sessionKey);
        }
      } finally { f.close(); }
    }
  });

  test(`${label}: skill fixture verifies both files before a fresh-session request`, async () => {
    const d = await cells;
    for (const mode of ['success','wrong-skill','wrong-runbook','shell-failure','wrong-answer']) {
      const f = await fixture({shellFailure:mode === 'shell-failure',
        read:(file, fixture) => (mode === 'wrong-skill' && file.endsWith('/SKILL.md')) || (mode === 'wrong-runbook' && file.endsWith('/runbook.md')) ? 'corrupt fixture' : fixture.files.get(file),
        answer:(_params, fixture) => mode === 'wrong-answer' ? 'I used a skill.' : fixture.state.runbookReference,
      });
      try {
        if (['wrong-skill','wrong-runbook','shell-failure'].includes(mode)) {
          await assert.rejects(f.execute(d.install)); assert.equal(f.state.skillVerified,false);
          assert(!f.calls.some(call => call.method === 'chat.send'));
        } else {
          await f.execute(d.install); assert.equal(f.state.skillVerified,true);
          if (mode === 'wrong-answer') await assert.rejects(f.execute(d.trigger)); else await f.execute(d.trigger);
          const turn = f.calls.find(call => call.method === 'chat.send');
          assert(turn.params.message.includes(f.state.skillDirectory + '/SKILL.md'));
          assert(!turn.params.message.includes(f.state.runbookReference), 'answer must retrieve the hidden runbook reference');
        }
      } finally { f.close(); }
    }
  });

  test(`${label}: one-shot cron verifies disk evidence and removes only its owned ID`, async () => {
    const d = await cells, f = await fixture();
    try {
      await f.execute(d.cron);
      assert.equal(f.calls.filter(call => call.method === 'cron.runs').length,2);
      assert.equal(f.calls.filter(call => call.method === 'cron.remove').length,1);
      assert(!f.calls.some(call => call.method === 'chat.send'), 'no chat message triggers the scheduled run');
      assert.equal(f.state.demoCronId,null); assert(!f.storage.has(f.key));
      assert.equal(f.sockets.at(-1).readyState,3);
      assert(f.commands.some(command => command.includes(f.state.cronFile)), 'independent framed readback executed');
      const firstName = f.calls.find(call => call.method === 'cron.add').params.name;
      await f.execute(d.cron);
      assert.notEqual(f.calls.filter(call => call.method === 'cron.add')[1].params.name,firstName);
    } finally { f.close(); }
  });

  test(`${label}: Stop, deadline, run failure and wrong file all fail and still clean up`, async () => {
    const d = await cells;
    for (const mode of ['stop','neverComplete','runFailure','mismatch']) {
      const f = await fixture({[mode]:true});
      try {
        await assert.rejects(f.execute(d.cron), error => mode === 'stop' ? error.name === 'AbortError' : Boolean(error.message));
        assert.equal(f.calls.filter(call => call.method === 'cron.remove').length,1,mode);
        assert.equal(f.state.demoCronId,null,mode); assert(!f.storage.has(f.key),mode);
        assert.equal(f.sockets.at(-1).readyState,3,mode);
      } finally { f.close(); }
    }
  });

  test(`${label}: incomplete cleanup retains ownership and retry clears it only after absence`, async () => {
    const d = await cells;
    for (const mode of ['removeFailure','stillPresent']) {
      const options = {[mode]:true};
      const f = await fixture(options);
      try {
        await assert.rejects(f.execute(d.cron));
        assert.equal(f.state.demoCronId,f.ownedId);
        assert.equal(JSON.parse(f.storage.get(f.key)).id,f.ownedId);
        assert.equal(f.sockets.at(-1).readyState,3);
        const adds = f.calls.filter(call => call.method === 'cron.add').length;
        await assert.rejects(f.execute(d.cron));
        assert.equal(f.calls.filter(call => call.method === 'cron.add').length,adds,'no second job while cleanup is unconfirmed');
        options[mode] = false;
        await f.execute(d.remove);
        assert.equal(f.state.demoCronId,null); assert(!f.storage.has(f.key));
      } finally { f.close(); }
    }
  });

  test(`${label}: original run error survives cleanup failure with recovery evidence`, async () => {
    const d = await cells, f = await fixture({runFailure:true,removeFailure:true});
    try {
      await assert.rejects(f.execute(d.cron), /fixture run failure/);
      assert.equal(f.state.demoCronId,f.ownedId); assert(f.storage.has(f.key));
      assert(f.entries.some(args => args.some(value => typeof value === 'string' && value.includes(f.ownedId))));
      assert.equal(f.sockets.at(-1).readyState,3);
    } finally { f.close(); }
  });

  test(`${label}: lost creation acknowledgement retains inspection context and never guesses an ID`, async () => {
    const d = await cells, f = await fixture({noId:true});
    try {
      await assert.rejects(f.execute(d.cron));
      const saved = JSON.parse(f.storage.get(f.key)); assert(saved.name); assert(!saved.id);
      await assert.rejects(f.execute(d.remove));
      assert(f.calls.some(call => call.method === 'cron.list'));
      assert(!f.calls.some(call => call.method === 'cron.remove'));
      assert.deepEqual(JSON.parse(f.storage.get(f.key)),saved);
      assert.equal(f.sockets.at(-1).readyState,3);
    } finally { f.close(); }
  });

  test(`${label}: changing gateways cannot remove or replace a retained owned job`, async () => {
    const d = await cells;
    for (const code of [d.cron,d.remove]) {
      const f = await fixture({state:{demoCronId:'other-owned-id',demoCronOwner:'https://other.example.test'}});
      try {
        await assert.rejects(f.execute(code));
        assert(!f.calls.some(call => call.method.startsWith('cron.')));
        assert.equal(f.state.demoCronId,'other-owned-id');
        assert.equal(f.state.demoCronOwner,'https://other.example.test');
        assert.equal(f.sockets.at(-1).readyState,3);
      } finally { f.close(); }
    }
  });
}
