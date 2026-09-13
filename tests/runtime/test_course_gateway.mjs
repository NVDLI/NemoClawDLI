// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import {fileURLToPath, pathToFileURL} from 'node:url';
import path from 'node:path';
import {createRequire} from 'node:module';
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
