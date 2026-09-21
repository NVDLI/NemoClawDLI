// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import {fileURLToPath, pathToFileURL} from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import {createRequire} from 'node:module';
import {discoverGatewayInventory, gatewayConsumerFindings, gatewayLifecycleFindings} from '../../scripts/validation/gateway_token_audit.mjs';
const {discoverCourses} = createRequire(import.meta.url)('./course_exercise_fixture.cjs');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const course = discoverCourses(root).roots[0];
await import(pathToFileURL(path.join(course,'scripts/_shared.js')));
const {courseTurn, openclawMessageText, filterOpenClawRuntimeValue} =
  await import(pathToFileURL(path.join(course,'scripts/_openclaw.js')));

const frame = (state, runId, sessionKey, text, event = 'chat', extra = {}) => state._chatCb?.({
  event, payload:{runId, sessionKey, state:'final', message:{content:text}, ...extra},
});
const tick = () => new Promise(resolve => setImmediate(resolve));
function fixture(call) {
  const controller = new AbortController(), entries = [];
  const log = (...args) => entries.push(args);
  log.details = log;
  const state = {call, courseEvents:['old result']};
  const helpers = {signal:controller.signal, log, openclawMessageText, filterOpenClawRuntimeValue};
  return {state, helpers, controller, entries};
}

test('course turn accepts pre-ack final only for acknowledged run and canonical session alias', async () => {
  const f = fixture(async method => {
    if (method === 'chat.send') {
      frame(f.state, 'other-run', 'task', 'wrong run');
      frame(f.state, 'owned', 'other:task', 'wrong session');
      frame(f.state, 'owned', 'agent:research:task', 'authoritative');
      return {runId:'owned'};
    }
  });
  const answer = await courseTurn(f.state, f.helpers, 'task', 'question');
  assert.equal(answer, 'authoritative');
  assert.equal(f.state.courseEvents.length, 1);
  assert.equal(f.state._chatCb, null);
  assert.equal(f.state._courseTurn, null);
});

test('Stop cancels pending subscription, releases the lock and never sends the turn', async () => {
  let release; const methods=[];
  const f=fixture(method => {methods.push(method);return new Promise(resolve => {release=resolve;});});
  const pending=courseTurn(f.state,f.helpers,'task','question');
  await tick();
  await assert.rejects(courseTurn(f.state,f.helpers,'other','question'),/Another turn/);
  f.controller.abort();
  await assert.rejects(pending,{name:'AbortError'});
  release({});await tick();
  assert.deepEqual(methods,['sessions.messages.subscribe']);
  assert.deepEqual(f.state.courseEvents,[]);
  assert.equal(f.state._courseTurn,null);
});

test('a late send acknowledgement is aborted on its original connection with its run ID', async () => {
  let acknowledge; const aborted=[];
  const f=fixture(async (method,args) => {
    if(method==='chat.send')return new Promise(resolve=>{acknowledge=resolve;});
    if(method==='chat.abort')aborted.push(args);
  });
  const pending=courseTurn(f.state,f.helpers,'task','question');await tick();
  f.controller.abort();await assert.rejects(pending,{name:'AbortError'});
  f.state.call=()=>{throw Error('wrong connection');};
  acknowledge({runId:'late-owned'});await tick();
  assert.deepEqual(aborted,[{sessionKey:'task',runId:'late-owned'}]);
});

test('tool and lifecycle frames alone cannot complete a turn; socket closure rejects it', async () => {
  const f=fixture(async method=>method==='chat.send'?{runId:'owned'}:{});
  const pending=courseTurn(f.state,f.helpers,'task','question');await tick();
  frame(f.state,'owned','task','partial','agent',{stream:'assistant',data:{text:'partial'}});
  frame(f.state,'owned','task','','agent',{stream:'lifecycle',data:{phase:'end'}});
  let settled=false;pending.then(()=>{settled=true;},()=>{settled=true;});await tick();assert.equal(settled,false);
  f.state._onGatewayClose(new Error('socket closed'));
  await assert.rejects(pending,/socket closed/);
  assert.deepEqual(f.state.courseEvents,[]);
});

test('missing final times out and an explicit canonical request rejects another agent alias', async () => {
  const f=fixture(async method=>method==='chat.send'?{runId:'owned'}:{});
  const pending=courseTurn(f.state,f.helpers,'agent:research:task','question',{idleMs:25,totalMs:100});
  await tick();frame(f.state,'owned','agent:main:task','foreign final');
  await assert.rejects(pending,/idle deadline/);
});

test('shared turn preserves every final block and filters only known tool diagnostic noise', async () => {
  const noise = '/bin/bash: 1: cannot create /proc/self/oom_score_adj: Permission denied';
  const f = fixture(async method => {
    if (method !== 'chat.send') return {};
    frame(f.state, 'owned', 'task', '', 'agent', {stream:'tool', data:{phase:'result', name:'exec',
      result:{content:[{text:noise + '\nPermission denied: keep this'}]}}});
    frame(f.state, 'owned', 'task', '', 'agent', {stream:'lifecycle', data:{phase:'end'}});
    frame(f.state, 'owned', 'task', '', 'chat', {message:{content:[{text:noise + '\nfirst'}, {text:'second'}]}});
    return {runId:'owned'};
  });
  assert.equal(await courseTurn(f.state, f.helpers, 'task', 'question'), 'first\nsecond');
  const displayed = JSON.stringify(f.entries);
  assert(!displayed.includes('oom_score_adj'));
  assert(displayed.includes('Permission denied: keep this'));
  assert(displayed.includes('first\\nsecond'));
});

test('streamed snapshots update one text row and final content replaces the draft', async t => {
  const f = fixture(async method => method === 'chat.send' ? {runId:'owned'} : {});
  const rows = [], details = [];
  f.helpers.log = (...args) => {
    const row = {nodeType:1, textContent:args.join(' '), dataset:{}};
    rows.push(row);
    return row;
  };
  f.helpers.log.details = (...args) => details.push(args);
  const pending = courseTurn(f.state, f.helpers, 'task', 'question');
  t.after(() => f.controller.abort());
  pending.catch(() => {});
  await tick();
  const before = rows.length;
  for (const text of ['Read c', 'Read config', 'Read config.md', 'Read config.md\n\n- 中文']) {
    frame(f.state, 'owned', 'task', '', 'agent', {stream:'assistant', data:{text}});
    assert.equal(rows.length, before + 1, 'chunks must not become separate block rows');
    assert.equal(rows.at(-1).textContent, text);
  }
  const row = rows.at(-1);
  frame(f.state, 'owned', 'task', '', 'agent', {stream:'tool', data:{phase:'result', name:'read', isError:true}});
  const final = 'Read config.md\n\n- 中文\n- <script>literal text</script>';
  frame(f.state, 'owned', 'task', final);
  assert.equal(await pending, final);
  assert.equal(rows.length, before + 1, 'final answer must replace the draft, not repeat it');
  assert.equal(row.textContent, final);
  assert.equal(row.dataset.logText, final);
  assert(details.some(([label]) => label.startsWith('✗ read')));
  assert(details.some(([label]) => label === 'final event'));
  const next = courseTurn(f.state, f.helpers, 'another-task', 'question');
  await tick();
  frame(f.state, 'owned', 'another-task', '');
  assert.equal(await next, '', 'empty final is authoritative even without streamed text');
  assert.equal(rows.at(-1).textContent, '');
  assert.notEqual(rows.at(-1), row, 'each turn owns its response row');
  assert.equal(row.textContent, final, 'later turns cannot overwrite earlier output');
});

test('stopped streams retain partial text and ignore late frames', async () => {
  const f = fixture(async method => method === 'chat.send' ? {runId:'owned'} : {});
  const rows = [];
  f.helpers.log = (...args) => {
    const row = {nodeType:1, textContent:args.join(' '), dataset:{}};
    rows.push(row); return row;
  };
  f.helpers.log.details = () => {};
  const pending = courseTurn(f.state, f.helpers, 'task', 'question');
  await tick();
  frame(f.state, 'owned', 'task', '', 'agent', {stream:'assistant', data:{text:'Partial\nanswer'}});
  const receive = f.state._chatCb, row = rows.at(-1);
  f.controller.abort();
  await assert.rejects(pending, {name:'AbortError'});
  receive({event:'chat', payload:{runId:'owned', sessionKey:'task', state:'final', message:{content:'late'}}});
  assert.equal(row.textContent, 'Partial\nanswer');
});

test('gateway lifecycle detector rejects final, ownership and filtering regressions in each actual owner', () => {
  const source = fs.readFileSync(path.join(course, 'scripts/_openclaw.js'), 'utf8');
  assert.deepEqual(gatewayLifecycleFindings(source), []);
  for (const [before, after, expected] of [
    ['text = finalText; done(); return;', 'done(); return;', 'openclawChat: gateway-final'],
    ['// Lifecycle end is not authoritative chat completion. Wait for chat.final.', 'if (stream === "lifecycle") done();', 'openclawChat: gateway-final'],
    ['view.replaceAnswer(finalText)', 'view.token(finalText)', 'openclawChat: gateway-final'],
    ['resText(data.partialResult)', 'data.partialResult', 'openclawChat: gateway-noise'],
    ['resText(data.result)', 'data.result', 'openclawChat: gateway-noise'],
    ['if (!myRun || pl.runId !== myRun) return;', '', 'openclawChat: gateway-owner'],
    ['settle(null, helpers.openclawMessageText(p.message))', 'settle(null, p.message.content[0].text)', 'courseTurn: gateway-final'],
    ['helpers.log.details(label, helpers.filterOpenClawRuntimeValue(event))', 'helpers.log.details(label, event)', 'courseTurn: gateway-noise'],
    ['helpers.log.details("final event", helpers.filterOpenClawRuntimeValue(event))', 'helpers.log.details("final event", event)', 'courseTurn: gateway-noise'],
    ['if (!runId || p.runId !== runId) return;', '', 'courseTurn: gateway-owner'],
    ['bump(); events.push(event);', 'bump(); events.push(event); if (p.stream === "lifecycle") settle(null, "");', 'courseTurn: gateway-final'],
  ]) {
    assert(source.includes(before), 'mutation must have an existing target');
    const mutated = source.replace(before, after);
    assert.notEqual(mutated, source);
    assert(gatewayLifecycleFindings(mutated).some(finding => finding.includes(expected)), expected);
  }
});

test('gateway discovery follows actual metadata through new, nested, deleted and renamed consumers', () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'gateway-discovery-'));
  const directory = path.join(temporary, 'web', 'example');
  fs.mkdirSync(path.join(directory, 'scripts'), {recursive:true});
  fs.writeFileSync(path.join(directory, 'scripts/_openclaw.js'), '// owner');
  const profile = {lessons:[
    {id:'connection', module:3, lesson:1}, {id:'memory', module:3, lesson:2},
    {id:'scheduled', module:3, lesson:3}, {id:'cli', module:4, lesson:2},
  ]};
  const profilePath = path.join(directory, 'lesson-map.json');
  const save = () => fs.writeFileSync(profilePath, JSON.stringify(profile));
  save();
  for (const lesson of profile.lessons) fs.writeFileSync(path.join(directory, lesson.id + '.html'), '<h1>Lesson</h1>');
  const owner = path.join(directory, 'scripts/_openclaw.js');
  const good = '<script>await helpers.courseTurn(state, helpers, "session", "question");</script>';
  try {
    assert.deepEqual(discoverGatewayInventory(temporary).findings, []);
    const added = path.join(directory, 'nested', 'new.html');
    fs.mkdirSync(path.dirname(added)); fs.writeFileSync(added, good);
    let inventory = discoverGatewayInventory(temporary);
    assert(inventory.surfaces[added]);
    assert(inventory.findings.some(item => item.includes('absent from lesson metadata')));
    profile.lessons.push({id:'nested/new', module:5, lesson:1}); save();
    assert.deepEqual(discoverGatewayInventory(temporary).findings, []);
    assert.deepEqual(gatewayConsumerFindings(discoverGatewayInventory(temporary).surfaces, [owner]), []);
    const renamed = path.join(directory, 'nested', 'renamed.html');
    fs.renameSync(added, renamed);
    inventory = discoverGatewayInventory(temporary);
    assert(inventory.findings.some(item => item.includes('declared lesson is missing')));
    profile.lessons.at(-1).id = 'nested/renamed'; save();
    assert.deepEqual(discoverGatewayInventory(temporary).findings, []);
    fs.writeFileSync(renamed, good.replace('helpers.courseTurn', 'helpers.courseTur'));
    assert(gatewayConsumerFindings(discoverGatewayInventory(temporary).surfaces, [owner])
      .some(item => item.includes('malformed shared turn helper')));
    fs.unlinkSync(renamed);
    assert(discoverGatewayInventory(temporary).findings.some(item => item.includes('declared lesson is missing')));
    profile.lessons.pop(); save();
    const script = path.join(directory, 'scripts/nested/new.js');
    fs.mkdirSync(path.dirname(script)); fs.writeFileSync(script, 'await state.call("chat.send", {});');
    assert(gatewayConsumerFindings(discoverGatewayInventory(temporary).surfaces, [owner])
      .some(item => item.includes('inline gateway lifecycle')));
    profile.lessons.pop(); save();
    assert.throws(() => discoverGatewayInventory(temporary), /missing gateway curriculum role/);
    fs.writeFileSync(profilePath, '{bad');
    assert.throws(() => discoverGatewayInventory(temporary));
    save(); fs.mkdirSync(path.join(temporary, 'i18n', 'unknown'), {recursive:true});
    assert.throws(() => discoverGatewayInventory(temporary), /locale.json/);
  } finally { fs.rmSync(temporary, {recursive:true, force:true}); }
});

test('gateway consumers cannot bypass the shared owner or use stale invocation helpers', () => {
  const valid = 'const courseTurn = helpers.courseTurn; await courseTurn(state, helpers, "session", "question");';
  assert.deepEqual(gatewayConsumerFindings({'nested/new.js':valid}, []), []);
  for (const changed of [valid.replace('helpers.courseTurn', 'other.turn'),
    valid.replace('state, helpers,', 'state, {},'),
    'state._chatCb = frame => resolve(frame.payload.message);',
    'await state.call("chat.send", {});']) {
    assert.notEqual(changed, valid);
    assert(gatewayConsumerFindings({'nested/renamed.js':changed}, []).some(item => item.includes('gateway-owner')));
  }
  assert.deepEqual(gatewayConsumerFindings({'notes.html':'<p>Call <code>chat.send</code> through the shared helper.</p>'}, []), []);
});
