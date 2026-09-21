/* Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0 */
'use strict';
const {discoverCourses,courseLanguage}=require('./course_exercise_fixture.cjs');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const assert = require('node:assert/strict');
const { test } = require('node:test');

const root = process.env.COURSE_SOURCE_ROOT;
assert(root, 'COURSE_SOURCE_ROOT is required');
for(const course of discoverCourses(root).roots) {
const language=courseLanguage(root,course,['04a-safety.html','04b-modern-clis.html']);
const t=language.text;
const safety = fs.readFileSync(path.join(course, '04a-safety.html'), 'utf8');
const clis = fs.readFileSync(path.join(course, '04b-modern-clis.html'), 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

// Decode the actual learner-visible template; do not keep a test copy of its code.
function cell(html, anchor) {
  assert.equal(html.split(anchor).length, 2, `one code anchor: ${anchor}`);
  const start = html.indexOf('code: `', html.indexOf(anchor));
  assert(start >= 0);
  const first = start + 'code: `'.length;
  let last = first;
  for (; last < html.length; last++) {
    if (html[last] === '\\') { last++; continue; }
    if (html[last] === '`') break;
  }
  assert.equal(html.slice(last, last + 2), '`,');
  return vm.runInNewContext('`' + html.slice(first, last) + '`');
}
const displayed = {
  layers: cell(safety, 'mountRunCell("#cell-layers",'),
  trajectory: cell(safety, 'mountRunCell("#trajectory-cell",'),
  predict: cell(safety, 'id: "predict", icon:'),
  policy: cell(safety, 'mountRunCell("#cell-live-policy",'),
  confirm: cell(safety, 'id: "confirm", icon:'),
  compare: cell(safety, 'id: "compare", icon:'),
  survey: cell(safety, 'id: "tok-survey", icon:'),
  browser: cell(clis, 'mountRunCell("#cell-jsagent",'),
  terminal: cell(clis, 'mountRunCell("#cell-deepagents",'),
  agentChat: cell(clis, 'mountRunCell("#cell-agentchat",'),
};
function recorder() {
  const entries = [];
  const log = (...args) => entries.push(args);
  log.details = (...args) => entries.push(args);
  log.html = (...args) => entries.push(args);
  return { log, entries };
}
async function execute(code, helpers, state = {}, window = {}, signal = new AbortController().signal) {
  helpers = {signal, getOpenClawConnection:() => ({rawUrl:'https://runtime.example.test'}), ...helpers};
  return new AsyncFunction('helpers', 'state', 'window', 'AbortSignal', code)(helpers, state, window, signal);
}
function model(content, finish = 'stop') {
  return { model: 'fixture-lightning', choices: [{ finish_reason: finish, message: { role: 'assistant', content } }] };
}
function calls(code, id = 'call-1') {
  return { model: 'fixture-lightning', choices: [{ finish_reason: 'tool_calls', message: {
    role: 'assistant', content: null,
    tool_calls: [{ id, type: 'function', function: { name: 'js', arguments: JSON.stringify({ code }) } }],
  } }] };
}
async function widget(kind, overrides = {}, globals = {}) {
  const capture = recorder();
  const tools = [], errors = [], answers = [];
  const listeners = new Map();
  const reviewButton = {disabled:false, addEventListener:(name,fn)=>listeners.set(name,fn), removeEventListener:(name,fn)=>{if(listeners.get(name)===fn)listeners.delete(name);}};
  let spec;
  const helpers = {
    log: capture.log,
    getConfig: async () => ({ model: 'fixture-lightning' }),
    mountChatUI(_selector, options) { spec = options; },
    ...overrides,
  };
  if (kind === 'browser') {
    await vm.runInNewContext('(async helpers => {\n' + displayed[kind] + '\n})', globals)(helpers);
  } else await execute(displayed[kind], helpers);
  assert(spec?.respond);
  const controller = new AbortController();
  const ctx = { signal: controller.signal, view: {
    html() { return {querySelector:()=>reviewButton}; },
    tool(...args) { tools.push(args); },
    error(text) { errors.push(text); },
    token(text) { answers.push(text); }, usage() {},
  } };
  return { helpers, spec, ctx, controller, tools, errors, answers, reviewButton, accept:()=>listeners.get("click")?.() };
}

test(language.label + ': terminal preserves the agent command boundary and handles a bare prefix without execution', async () => {
  let spec;
  const commands=[], entries=[];
  await execute(displayed.terminal, {
    log:()=>{}, mountConsole:(_id,value)=>{spec=value;},
    sandboxExec:async command=>{commands.push(['sandbox',command]);return {output:'fixture output'};},
    terminal:async command=>{commands.push(['host',command]);return {};},
  });
  const con={write:value=>entries.push(value),clear:()=>{},raw:()=>{}};
  const ctx={signal:new AbortController().signal};
  await spec.onSubmit(' agent ',con,ctx);
  assert.deepEqual(commands,[], 'a bare agent prefix must not reach either shell');
  assert.equal(entries[0],t('usage: agent <command>   runs <command> inside your agent sandbox, for example: agent ls'));
  await spec.onSubmit('agent pwd',con,ctx);
  assert.deepEqual(commands,[['sandbox','pwd']]);
  await spec.onSubmit('openshell status',con,ctx);
  assert.deepEqual(commands,[['sandbox','pwd'],['host','openshell status']]);
});

test(language.label + ': terminal console reports Ready only after sandbox and host exit zero', async () => {
  for (const target of ['sandbox', 'host']) {
    for (const scenario of [
      { name: 'success', result: { exitCode: 0, completion: 'exit', output: target + ' output' }, error: false },
      { name: 'nonzero', result: { exitCode: 1, completion: 'exit', output: target + ' diagnostic' }, error: true },
      { name: 'disconnect', result: { exitCode: null, completion: 'disconnect', output: target + ' partial output' }, error: true },
    ]) {
      const entries = [], calls = [];
      let spec;
      await execute(displayed.terminal, {
        log: () => {}, mountConsole: (_id, value) => { spec = value; },
        sandboxExec: async command => { calls.push(['sandbox', command]); return scenario.result; },
        terminal: async (command, options) => { calls.push(['host', command, options]); if (scenario.result.output) options.onChunk?.(scenario.result.output); return scenario.result; },
      });
      const con = { write: (value, kind) => entries.push([value, kind]), clear: () => {}, raw: value => entries.push([value, 'raw']) };
      const ctx = { signal: new AbortController().signal };
      const reply = await spec.onSubmit(target === 'sandbox' ? 'agent false' : 'false', con, ctx);
      assert.deepEqual(calls.map(call => call[0]), [target], target + ' ' + scenario.name);
      if (target === 'host') assert.equal(calls[0][2].stdio, 'pipe', 'host one-shot uses labelled streams');
      assert(entries.some(([value]) => value === scenario.result.output), target + ' output remains visible for ' + scenario.name);
      if (scenario.error) {
        assert(entries.some(([value]) => value === 'completion=' + scenario.result.completion + ' exitCode=' + (scenario.result.exitCode ?? 'unknown')),
          target + ' completion remains inspectable for ' + scenario.name);
        assert.deepEqual(reply, { status: 'error', message: t('Command failed. Read the message, then retry.') });
      } else assert.equal(reply, undefined);
    }
  }
});

test(language.label + ': agent chat cell awaits the gateway bootstrap result', async () => {
  const logs = [];
  await execute(displayed.agentChat, {
    log: value => logs.push(value),
    mountOpenClawCli: async () => ({ mounted: true, connected: true, session: 'main', reason: '' }),
  });
  assert.deepEqual(logs, [t('agent chat mounted below')]);

  logs.length = 0;
  await assert.rejects(execute(displayed.agentChat, {
    log: value => logs.push(value),
    mountOpenClawCli: async () => ({ mounted: true, connected: false, reason: 'metadata unavailable' }),
  }), /metadata unavailable/);
  assert.deepEqual(logs, []);
});

test(language.label + ': commands distinguish denial evidence, ordinary failure and unknown completion', async () => {
  const cases = [
    [{ exitCode: 0, output: 'uid=1000' }, 'completed'],
    [{ exitCode: 127, output: 'sudo: command not found' }, 'command failed'],
    [{ exitCode: 1, output: 'cat: missing: No such file or directory' }, 'command failed'],
    [{ exitCode: 6, output: 'Could not resolve host' }, 'command failed'],
    [{ exitCode: 28, output: 'Operation timed out' }, 'command failed'],
    [{ exitCode: 1, output: 'Permission denied' }, 'access-denial evidence'],
    [{ exitCode: 56, output: 'CONNECT tunnel failed, response 403' }, 'access-denial evidence'],
    [{ exitCode: 0, output: 'code=403' }, 'completed'],
    [{ exitCode: null, output: '' }, 'incomplete'],
    [{ exitCode: null, output: 'partial output' }, 'incomplete'],
  ];
  for (const [result, outcome] of cases) {
    const { log } = recorder();
    const value = await execute(displayed.layers, { log, sandboxExec: async () => result });
    assert(value.results.length > 0);
    assert(value.results.every(item => item.outcome === t(outcome)), outcome);
    if (outcome === 'incomplete') assert.equal(value.results.length, 1);
  }
});

test(language.label + ': permission experiment cleans its own file on completion, command failure and termination', async () => {
  for (const mode of ['success', 'failure', 'termination']) {
    const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'module4-permissions-test-'));
    const scratch = path.join(fixture, 'scratch');
    const bin = path.join(fixture, 'bin');
    fs.mkdirSync(scratch);
    fs.mkdirSync(bin);
    if (mode !== 'success') {
      fs.writeFileSync(path.join(bin, 'chmod'), mode === 'failure'
        ? '#!/bin/sh\nexit 23\n'
        : '#!/bin/sh\nkill -TERM "$PPID"\nexit 0\n', { mode: 0o755 });
    }
    const commands = [];
    let permissionResult;
    try {
      const { log } = recorder();
      await execute(displayed.layers, { log, sandboxExec: async command => {
        commands.push(command);
        if (!command.includes('mktemp')) return { exitCode: 0, output: '' };
        // Execute only the displayed exercise-owned permission command. All
        // network, package and authority probes remain external-service fixtures.
        permissionResult = spawnSync('sh', ['-c', command], {
          encoding: 'utf8', timeout: 5000,
          env: { ...process.env, TMPDIR: scratch, PATH: bin + path.delimiter + process.env.PATH },
        });
        assert.ifError(permissionResult.error);
        return { exitCode: permissionResult.status, output: permissionResult.stdout + permissionResult.stderr };
      } });
      assert(permissionResult, 'displayed permission experiment ran');
      assert.equal(permissionResult.status, mode === 'success' ? 0 : mode === 'failure' ? 23 : 130);
      assert.deepEqual(fs.readdirSync(scratch), [], 'exercise directory removed');
      assert.deepEqual(commands.filter(command => command.includes('SOUL.md')),
        ['ls -la /sandbox/.openclaw/workspace/SOUL.md'], 'persona metadata is observed only');
      assert(!commands.some(command => /\bchattr\b/.test(command)), 'no immutable state can survive cleanup');
      assert(commands.includes('dd if=/proc/1/environ of=/dev/null status=none'), 'environment access probe discards all contents');
    } finally {
      fs.rmSync(fixture, { recursive: true, force: true });
    }
  }
});

test(language.label + ': trajectory rejects incomplete, malformed and invalid plans before any command', async () => {
  const invalid = [
    model('{', 'length'), model('{'), model(''), model(null), model('null'),
    model('{"steps":[{"intent":"list","command":"ls"}]}', null),
    { model: 'fixture-lightning', choices: [{ finish_reason: 'stop', message: { refusal: 'declined', content: null } }] },
    model('{"steps":"ls"}'), model('{"steps":[]}'),
    model(JSON.stringify({ steps: Array(6).fill({ intent: 'list', command: 'ls' }) })),
    model('{"steps":[{"intent":"list","command":7}]}'),
    model('{"steps":[{"intent":"list","command":"ls\\nid"}]}'),
  ];
  for (const response of invalid) {
    let commands = 0;
    const w = await widget('trajectory', {
      chat: async request => { assert(request.signal); return response; },
      sandboxExec: async () => { commands++; throw Error('unexpected command'); },
    });
    await w.spec.respond('inspect files', w.ctx);
    assert.equal(commands, 0);
    assert.equal(w.errors.length, 1);
    if(response.choices[0].finish_reason === 'length')
      assert.equal(w.errors[0],t('The model reached its output limit before completing the plan. Inspect the response before changing the goal or token budget.'));
    assert(w.tools.some(([label, value]) => label === t('Model response') && value.raw === response));
  }
});

test(language.label + ': valid trajectory retains output and avoids invented network verdict', async () => {
  const response = model(JSON.stringify({ steps: [{ intent: 'read missing file', command: 'cat missing' }] }));
  const w = await widget('trajectory', {
    chat: async request => { assert.equal(request.model, 'fixture-lightning'); return response; },
    sandboxExec: async command => { assert.equal(command, 'cat missing'); return { exitCode: 1, output: 'No such file' }; },
  });
  const pending = w.spec.respond('read a file', w.ctx);
  await new Promise(resolve => setImmediate(resolve));
  assert(!w.tools.some(([label])=>label.startsWith(t('Step '))), 'nothing executes before review');
  w.accept(); await pending;
  assert.equal(w.errors.length, 0);
  assert(w.tools.some(([label, value]) => label.includes(t('command failed')) && value.output === 'No such file'));
  assert(w.answers.join('').includes(t('command failed')), 'summary retains the observed command outcome');
});

// Use the materialized policy evaluator with external runtime responses only mocked.
const policySource = fs.readFileSync(path.join(root, 'web', path.basename(course), 'scripts/_openshell.js'), 'utf8');
const evaluatorStart = policySource.indexOf('function _globMatch(');
const evaluatorEnd = policySource.indexOf('// Filesystem decision', evaluatorStart);
assert(evaluatorStart >= 0 && evaluatorEnd > evaluatorStart);
const evalSandboxNetwork = vm.runInNewContext(
  policySource.slice(evaluatorStart, evaluatorEnd).replace(/^export /gm, '') + '\nevalSandboxNetwork;',
);
function policyWindow(action = {}) {
  return {
    __SBX_POLICY_OWNER: 'https://runtime.example.test',
    __sbxAction: { binary: '/usr/bin/curl', host: 'service.example', port: 8443, scheme: 'https:', method: 'POST', path: '/v1/chat/completions', ...action },
    __SBX_POLICY: { network_policies: { fixture: {
      binaries: [{ path: '/usr/bin/curl' }],
      endpoints: [{ host: 'service.example', port: 8443, rules: [{ allow: { method: 'POST', path: '/v1/chat/completions' } }] }],
    } } },
  };
}
test(language.label + ': Confirm executes selected method and custom port; Predict invalidates prior observations', async () => {
  const state = {}, window = policyWindow(), { log } = recorder();
  const helpers = { log, evalSandboxNetwork, sandboxExec: async command => {
    assert.match(command, /-X 'POST'/);
    assert.match(command, /'https:\/\/service\.example:8443\/v1\/chat\/completions'/);
    return { exitCode: 0, output: 'code=200' };
  } };
  await execute(displayed.predict, helpers, state, window);
  assert.equal(state.predicted, 'allow');
  await execute(displayed.confirm, helpers, state, window);
  assert.equal((await execute(displayed.compare, helpers, state, window)).agree, true);
  window.__sbxAction.method = 'GET';
  await execute(displayed.predict, helpers, state, window);
  assert.equal(state.predicted, 'deny');
  assert.equal(state.observed, null);
  assert.equal(await execute(displayed.compare, helpers, state), undefined);
});
test(language.label + ': Confirm reads labelled stdout without swallowing transport diagnostics', async () => {
  const state = {}, window = policyWindow(), {log} = recorder();
  const helpers = {log, evalSandboxNetwork, sandboxExec:async command => {
    assert(command.includes("-w '\\ncode=%{http_code}\\n'"), 'status is bounded by newlines on legacy PTYs');
    return {exitCode:0, completion:'exit', stdout:'code=200', stderr:'Connection to sandbox closed.', output:'code=200Connection to sandbox closed.'};
  }};
  await execute(displayed.predict, helpers, state, window);
  await execute(displayed.confirm, helpers, state, window);
  assert.equal(state.observed, 'allow');
  assert.equal((await execute(displayed.compare, helpers, state, window)).agree, true);
});

test(language.label + ': Confirm preserves IPv6 URL brackets', async () => {
  const state = {}, window = policyWindow({host:'2001:db8::1'}), {log} = recorder();
  let command;
  const helpers={log,evalSandboxNetwork,sandboxExec:async value=>{command=value;return {exitCode:0,output:'code=200'};}};
  await execute(displayed.predict,helpers,state,window);
  await execute(displayed.confirm,helpers,state,window);
  assert(command.includes("'https://[2001:db8::1]:8443/v1/chat/completions'"));
  assert.equal(state.observed,'allow');
});
test(language.label + ': plain HTTP denial, missing exit and ordinary command errors remain unresolved', async () => {
  for (const result of [{ exitCode: 0, output: 'code=403' }, { exitCode: null, output: '' }, { exitCode: 6, output: 'Could not resolve host' }]) {
    const state = {}, window = policyWindow(), { log } = recorder();
    const helpers = { log, evalSandboxNetwork, sandboxExec: async () => result };
    await execute(displayed.predict, helpers, state, window);
    await execute(displayed.confirm, helpers, state, window);
    assert.equal(state.observed, 'unknown');
    assert.equal((await execute(displayed.compare, helpers, state, window)).agree, null);
  }
});
test(language.label + ': an older in-flight Confirm cannot replace a newer prediction, even for the same action', async () => {
  const state = {}, window = policyWindow(), { log } = recorder();
  let release;
  const helpers = { log, evalSandboxNetwork, sandboxExec: () => new Promise(resolve => { release = resolve; }) };
  await execute(displayed.predict, helpers, state, window);
  const pending = execute(displayed.confirm, helpers, state, window);
  await execute(displayed.predict, helpers, state, window);
  release({ exitCode: 0, output: 'code=200' });
  await pending;
  assert.equal(state.observed, null);
});
test(language.label + ': missing policy and a changed picker cannot reuse an earlier observation', async () => {
  const state = {}, window = policyWindow(), { log } = recorder();
  const helpers = { log, evalSandboxNetwork, sandboxExec: async () => ({ exitCode: 0, output: 'code=200' }) };
  await execute(displayed.predict, helpers, state, window);
  await execute(displayed.confirm, helpers, state, window);
  window.__sbxAction.method = 'GET';
  assert.equal(await execute(displayed.compare, helpers, state, window), undefined);
  window.__SBX_POLICY = null;
  await execute(displayed.predict, helpers, state, window);
  assert.equal(state.predicted, null);
  assert.equal(state.observed, null);
});

test(language.label + ': a failed policy reload clears the old policy and rendered map', async () => {
  const window = policyWindow(), {log} = recorder();
  let cleared = 0;
  window.document = {getElementById:() => ({replaceChildren() { cleared++; }})};
  await assert.rejects(execute(displayed.policy, {
    log, policyGet:async () => { throw new Error('route unavailable'); },
  }, {}, window), /route unavailable/);
  assert.equal(window.__SBX_POLICY, null);
  assert.equal(window.__SBX_POLICY_OWNER, null);
  assert.equal(cleared, 1);
});

test(language.label + ': Confirm cannot publish an observation for a policy replaced during the request', async () => {
  const state = {}, window = policyWindow(), {log} = recorder();
  let release;
  const helpers = {log, evalSandboxNetwork, sandboxExec:() => new Promise(resolve => { release = resolve; })};
  await execute(displayed.predict, helpers, state, window);
  const pending = execute(displayed.confirm, helpers, state, window);
  window.__SBX_POLICY = {network_policies:{}};
  release({exitCode:0, output:'code=200'});
  await pending;
  assert.equal(state.observed, null);
  assert.equal(await execute(displayed.compare, helpers, state, window), undefined);
});
test(language.label + ': read-only survey uses the returned persona field', async () => {
  const { log, entries } = recorder();
  const methods = [];
  const result = await execute(displayed.survey, { log }, { call: async method => { methods.push(method); return ({
    'agents.files.get': { file: { content: 'persona' } }, 'cron.list': { jobs: [] },
    'sessions.list': { sessions: [] }, 'models.list': { models: [] }, 'config.get': {},
  })[method]; } });
  assert.equal(result.soulBytes, 7);
  assert.deepEqual(methods.sort(), ['agents.files.get','config.get','cron.list','models.list','sessions.list'].sort());
});
test(language.label + ': browser agent completes a tool round and passes the current turn signal', async () => {
  let count = 0;
  const w = await widget('browser', { chat: async request => {
    assert.equal(request.signal, w.ctx.signal);
    return ++count === 1 ? calls('return 144;') : model('144');
  } });
  await w.spec.respond('calculate', w.ctx);
  assert.equal(count, 2);
  assert.deepEqual(w.answers, ['144']);
  assert(w.tools.some(([label, value]) => label === t('Returned') && value === '144'));
});
test(language.label + ': Stop during a model response prevents its tool from executing', async () => {
  const w = await widget('browser', { marker: 0, chat: async request => {
    assert.equal(request.signal, w.ctx.signal);
    w.controller.abort();
    return calls('helpers.marker++; return helpers.marker;');
  } });
  await assert.rejects(w.spec.respond('change marker', w.ctx), { name: 'AbortError' });
  assert.equal(w.helpers.marker, 0);
});
test(language.label + ': Stop after an asynchronous tool prevents further calls and the fallback request', async () => {
  let requests = 0;
  const w = await widget('browser', {
    stopDuringTool: async () => { w.controller.abort(); return 'finished'; },
    chat: async () => { requests++; return calls('return await helpers.stopDuringTool();'); },
  });
  await assert.rejects(w.spec.respond('inspect', w.ctx), { name: 'AbortError' });
  assert.equal(requests, 1);
  assert.equal(w.answers.length, 0);
});
test(language.label + ': invalid tool arguments and cyclic results become tool errors, not unhandled serialization failures', async () => {
  for (const response of [calls('const a = {}; a.self = a; return a;'), calls(7)]) {
    let count = 0;
    const w = await widget('browser', { chat: async request => {
      if (++count === 1) return response;
      assert(request.messages.at(-1).content.startsWith(t('Error: ')));
      return model('The tool could not return that result.');
    } });
    await w.spec.respond('inspect', w.ctx);
    assert.equal(count, 2);
  }
});

test(language.label + ': actual console-only and console-plus-true snippets retain headings without mutating global console', async () => {
  const headings = ['Permissions and tools', 'Inspect the current page', 'Operator terminal'];
  for (const suffix of ['', '\nreturn true;']) {
    const globalConsole = { log() { throw Error('global console must not be used'); } };
    let count = 0, toolEvidence;
    const w = await widget('browser', { chat: async request => {
      if (++count === 1) return calls("document.querySelectorAll('h2').forEach(h => console.log(h.innerText.trim()));" + suffix);
      toolEvidence = request.messages.at(-1).content;
      headings.forEach(heading => assert(toolEvidence.includes(heading)));
      assert(toolEvidence.startsWith(suffix ? 'true\n' : t('undefined (return the requested data or inspect the captured console output)')));
      assert.equal(w.tools.find(([label]) => label === t('Returned'))[1], toolEvidence);
      return model(headings.join('\n'));
    } }, { document: { querySelectorAll(selector) {
      assert.equal(selector, 'h2'); return headings.map(innerText => ({ innerText }));
    } }, console: globalConsole });
    const originalLog = globalConsole.log;
    await w.spec.respond('Use JavaScript to list the H2 section headings on this page.', w.ctx);
    assert.equal(globalConsole.log, originalLog);
    assert.equal(count, 2);
    assert.deepEqual(w.answers, [headings.join('\n')]);
  }
});

test(language.label + ': console objects are snapshotted, cycles marked, and logs survive execution errors', async () => {
  let count = 0;
  const w = await widget('browser', { chat: async request => {
    if (++count === 1) return calls('const item = { count: 3 }; item.self = item; console.log(item); item.count = 9; console.warn(12n, undefined); throw new Error("fixture failure");');
    const evidence = request.messages.at(-1).content;
    assert(evidence.startsWith(t('Error: ')+'fixture failure'));
    assert(evidence.includes('"count":3'));
    assert(!evidence.includes('"count":9'));
    assert(evidence.includes(t('[Circular]')));
    assert(evidence.includes('12n'));
    assert.equal(w.tools.find(([label]) => label === t('Returned'))[1], evidence);
    return model('The snippet failed after logging count 3.');
  } });
  await w.spec.respond('inspect failure', w.ctx);
});

test(language.label + ': returned and logged evidence is bounded identically for learner and model with explicit truncation', async () => {
  const markers = [...displayed.browser.matchAll(/const marker = ("(?:[^"\\]|\\.)*");/g)];
  assert.equal(markers.length, 1, 'one localized truncation marker in displayed code');
  const marker = t(String.raw`\\n[truncated]`).replace(/^\\+n/, '').trim();
  assert.equal(JSON.parse(markers[0][1]).trim(), marker);
  for (const code of ['return "r".repeat(10000);', 'for (let i = 0; i < 100; i++) console.log("entry" + i + "x".repeat(100)); return true;']) {
    let count = 0;
    const w = await widget('browser', { chat: async request => {
      if (++count === 1) return calls(code);
      const evidence = request.messages.at(-1).content;
      assert(evidence.length <= 1500);
      assert(evidence.endsWith(marker));
      assert.equal(w.tools.find(([label]) => label === t('Returned'))[1], evidence);
      return model('The output was truncated.');
    } });
    await w.spec.respond('large result', w.ctx);
  }
});

test(language.label + ': alternate DOM task returns actual data and console capture resets between invocations', async () => {
  let count = 0;
  const w = await widget('browser', { chat: async request => {
    if (++count === 1) return calls('console.info("first invocation"); return document.querySelectorAll("a[target=\\\"_blank\\\"]").length;');
    if (count === 2) {
      assert(request.messages.at(-1).content.startsWith('7\n'));
      return calls('return 7;', 'call-2');
    }
    assert.equal(request.messages.at(-1).content, '7');
    return model('7 links open in a new tab.');
  } }, { document: { querySelectorAll(selector) {
    assert.equal(selector, 'a[target="_blank"]'); return Array(7).fill({});
  } } });
  await w.spec.respond('How many links open in a new tab?', w.ctx);
  assert.equal(count, 3);
});

test(language.label + ': Stop while reviewing a trajectory disables execution and runs no command', async () => {
  let commands=0;
  const w=await widget('trajectory',{chat:async()=>model(JSON.stringify({steps:[{intent:'identity',command:'id'}]})),sandboxExec:async()=>{commands++;}});
  const pending=w.spec.respond('inspect identity',w.ctx);
  await new Promise(resolve=>setImmediate(resolve));
  w.controller.abort();await assert.rejects(pending,{name:'AbortError'});
  w.accept();assert.equal(commands,0);assert.equal(w.reviewButton.disabled,true);
});

test(language.label + ': Confirm runs under native flow bindings without a RunCell AbortSignal alias', async () => {
  const state={},window=policyWindow(),{log}=recorder();let count=0;
  const helpers={log,signal:new AbortController().signal,getOpenClawConnection:()=>({rawUrl:'https://runtime.example.test'}),evalSandboxNetwork,sandboxExec:async()=>{count++;return {exitCode:0,output:'code=200'};}};
  await execute(displayed.predict,helpers,state,window);
  await new AsyncFunction('helpers','state','window',displayed.confirm)(helpers,state,window);
  assert.equal(count,1);assert.equal(state.observed,'allow');
});

}
