// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const COURSE_ROOTS = fs.readdirSync('web', {withFileTypes:true})
  .filter(entry => entry.isDirectory() && fs.existsSync(path.join('web', entry.name, 'COURSE_CANON.md')))
  .map(entry => path.join('web', entry.name));
assert.ok(COURSE_ROOTS.length, 'expected courses with milestone contracts');
for (const COURSE_ROOT of COURSE_ROOTS) {
const nativeFetch = globalThis.fetch;
globalThis.fetch = async url => url instanceof URL && url.protocol === 'file:'
  ? new Response(fs.readFileSync(url, 'utf8')) : nativeFetch(url);
const { installCourseActivityTracking, getInstalledCourseActivity, ACTIVITY_MILESTONE_ORDER } = await import(pathToFileURL(path.resolve('web/activity', '_activity_runtime.js')));
globalThis.fetch = nativeFetch;

const read = file => fs.readFileSync(path.join(COURSE_ROOT, file), 'utf8');

test('Activity Milestones documentation matches every course definition and exercise', async () => {
  const { ACTIVITY_MILESTONES } = await import(pathToFileURL(path.resolve('web/activity', '_activity.js')));
  const doc = fs.readFileSync('docs/ACTIVITY_MILESTONES.md', 'utf8');
  assert.match(doc, /^# Activity Milestones\n/);
  const blocks = [...doc.matchAll(/^```json[ \t]*\n([\s\S]*?)^```[ \t]*$/gm)];
  assert.equal(blocks.length, 1);
  const { validateActivityMilestoneConfig } = await import('../../web/activity/activity-sdk.js');
  const config = validateActivityMilestoneConfig(JSON.parse(blocks[0][1]));
  assert.deepEqual(config.milestones.map(marker => marker.id), Object.keys(ACTIVITY_MILESTONES));
  for (const milestone of config.milestones) {
    assert.deepEqual(milestone, ACTIVITY_MILESTONES[milestone.id]);
    const [file, fragment] = milestone.href.split('#');
    assert.ok(read(file).includes('id="' + fragment + '"'), milestone.id + ' exercise anchor');
  }
});
const flush = () => new Promise(resolve => setImmediate(resolve));
function dispatch(target, type, detail = {}) {
  const event = new Event(`nemoclaw:${type}`); event.detail = detail; target.dispatchEvent(event);
}
function fixture(page = '01a-loop.html', { sessionId = 'session-a', storageTarget, write = async () => true } = {}) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'location');
  Object.defineProperty(globalThis, 'location', { configurable: true, value: { pathname: `/${COURSE_ROOT}/${page}` } });
  const windowTarget = new EventTarget(); const documentTarget = new EventTarget();
  documentTarget.getElementById = id => read(page).includes('id="' + id + '"') ? {} : null;
  windowTarget.OneTrust = { IsAlertBoxClosed: () => true, OnConsentChanged: () => {} };
  windowTarget.OnetrustActiveGroups = ',C0001,C0002,';
  const values = new Map();
  const storage = storageTarget || { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
  const listeners = new Set(); const milestones = [];
  let state = { enabled: Boolean(sessionId), sessionId };
  const activity = {
    snapshot: () => state,
    resume: async () => false,
    enable: async () => state.enabled,
    subscribe(listener) { listeners.add(listener); listener(state); return () => listeners.delete(listener); },
    getCourseActivityState: async () => state,
    recordMilestone: async id => { milestones.push(id); return write(id); },
    trackReferral: async () => true,
  };
  installCourseActivityTracking({ windowTarget, documentTarget, activity, storageTarget: storage });
  return { windowTarget, documentTarget, activity, milestones, storage,
    session(sessionId) { state = { enabled: Boolean(sessionId), sessionId }; listeners.forEach(listener => listener(state)); },
    restore() { if (previous) Object.defineProperty(globalThis, 'location', previous); else delete globalThis.location; },
  };
}

const pairs = [
  ['03b-openclaw.html', ['run-succeeded', { cellId: 'cell-introspect' }], ['run-succeeded', { cellId: 'cell-workspace-term' }], '03b:workspace-inspected'],
  ['03c-always-on.html', ['canvas-node-succeeded', { canvasId: 'probe-cron', nodeId: 'cr-run', runObserved: true }], ['canvas-node-succeeded', { canvasId: 'probe-cron', nodeId: 'cr-rm', cleanupSucceeded: true }], '03c:scheduled-run-complete'],
  ['04a-safety.html', ['run-succeeded', { cellId: 'cell-live-policy', hasAgent: true }], ['canvas-node-succeeded', { canvasId: 'cell-predict-confirm', nodeId: 'compare', policyAgreed: true }], '04a:policy-boundary-verified'],
];

test('course bootstrap and reinstall do not award a milestone', () => {
  const f = fixture(); try {
    assert.deepEqual(f.milestones, []);
    assert.equal(installCourseActivityTracking({ windowTarget: f.windowTarget, documentTarget: f.documentTarget }), f.activity);
    assert.equal(getInstalledCourseActivity(f.windowTarget), f.activity);
  } finally { f.restore(); }
});

test('later successful exercises save independently of earlier exercises', async () => {
  const f = fixture('01b-react.html'); try {
    dispatch(f.windowTarget, 'chat-completed', { containerId: 'react-artifact', successCount: 0, hasAnswer: true }); await flush();
    assert.deepEqual(f.milestones, []);
    dispatch(f.windowTarget, 'chat-completed', { containerId: 'react-artifact', successCount: 1, hasAnswer: true }); await flush();
    assert.deepEqual(f.milestones, ['01b:react-loop-complete']);
  } finally { f.restore(); }
});

test('paired live success predicates work in either order, without trusting stored flags', async () => {
  for (const [page, left, right, milestone] of pairs) {
    for (const [first, second] of [[left, right], [right, left]]) {
      const f = fixture(page); try {
        f.storage.setItem('dli_activity:nemoclaw:evidence:v1:1', JSON.stringify({ '03b:introspect': true, '03b:workspace': true, '03c:run': true, '03c:removed': true, '04a:policy': true, '04a:agreement': true }));
        dispatch(f.windowTarget, ...first); await flush(); assert.deepEqual(f.milestones, []);
        dispatch(f.windowTarget, ...second); await flush(); assert.deepEqual(f.milestones, [milestone]);
      } finally { f.restore(); }
    }
  }
});

test('paired success halves cannot cross sessions, including disconnect and replacement', async () => {
  for (const [page, first, second] of pairs) {
    const f = fixture(page); try {
      dispatch(f.windowTarget, ...first); f.session(null); f.session('session-b');
      dispatch(f.windowTarget, ...second); await flush(); assert.deepEqual(f.milestones, []);
    } finally { f.restore(); }
  }
});

test('fresh work before enabling may bind once; stale saved evidence cannot bind', async () => {
  const f = fixture('03b-openclaw.html', { sessionId: null }); try {
    dispatch(f.windowTarget, 'run-succeeded', { cellId: 'cell-introspect' });
    f.session('session-a');
    dispatch(f.windowTarget, 'run-succeeded', { cellId: 'cell-workspace-term' }); await flush();
    assert.deepEqual(f.milestones, ['03b:workspace-inspected']);
  } finally { f.restore(); }
});

test('failed milestone evidence cannot transfer to a replacement session', async () => {
  const f = fixture('01b-react.html', { write: async () => false }); try {
    dispatch(f.windowTarget, 'chat-completed', { containerId: 'react-artifact', successCount: 1, hasAnswer: true }); await flush();
    assert.equal(f.milestones.length, 1);
    f.session('session-b');
    dispatch(f.windowTarget, 'chat-completed', { containerId: 'react-artifact', successCount: 1, hasAnswer: true }); await flush();
    assert.deepEqual(f.milestones, ['01b:react-loop-complete', '01b:react-loop-complete']);
  } finally { f.restore(); }
});

test('model-call milestone requires a live key verification and nonempty successful content', async () => {
  const f = fixture(); try {
    f.storage.setItem('dli_activity:nemoclaw:evidence:v1:1', JSON.stringify({ '01a:key': true }));
    dispatch(f.windowTarget, 'run-succeeded', { cellId: 'cell-onecall', hasContent: true }); await flush(); assert.deepEqual(f.milestones, []);
    dispatch(f.windowTarget, 'api-key-verified');
    dispatch(f.windowTarget, 'run-succeeded', { cellId: 'cell-onecall', hasContent: false }); await flush(); assert.deepEqual(f.milestones, []);
    dispatch(f.windowTarget, 'run-succeeded', { cellId: 'cell-onecall', hasContent: true }); await flush(); assert.deepEqual(f.milestones, ['01a:model-call-verified']);
  } finally { f.restore(); }
});

test('success predicates survive denied sessionStorage', async () => {
  const denied = { getItem() { throw new DOMException('denied', 'SecurityError'); }, setItem() { throw new DOMException('denied', 'SecurityError'); } };
  const f = fixture('01a-loop.html', { storageTarget: denied }); try {
    dispatch(f.windowTarget, 'api-key-verified'); dispatch(f.windowTarget, 'run-succeeded', { cellId: 'cell-onecall', hasContent: true }); await flush();
    assert.deepEqual(f.milestones, ['01a:model-call-verified']);
  } finally { f.restore(); }
});

test('every configured milestone retains success-only runtime evidence and the shared entrypoint installs tracking', () => {
  const runtime = fs.readFileSync('web/activity/_activity_runtime.js', 'utf8');
  const config = JSON.parse(fs.readFileSync('web/activity/activity_milestones.json', 'utf8'));
  assert.deepEqual(config.milestones.map(({id}) => id), ACTIVITY_MILESTONE_ORDER);
  assert.match(runtime, /bindActivityMilestones/);
  for (const id of ACTIVITY_MILESTONE_ORDER) assert.equal(runtime.includes(id), false);
  assert.match(read('scripts/_shared.js'), /install\w+ActivityTracking/);
  for (const [file, signal] of [['scripts/_canvas.js', 'run-succeeded'], ['scripts/_chat.js', 'chat-completed'], ['scripts/_openclaw.js', 'connection-audit-passed'], ['scripts/_openclaw_cli.js', 'live-agent-operated']]) assert.ok(read(file).includes(`nemoclaw:${signal}`));
  assert.equal(config.milestones.find(({id}) => id === '01b:react-loop-complete').evidence[0].minimum.successCount, 1);
  for (const key of ['runObserved', 'cleanupSucceeded', 'policyAgreed']) assert.ok(config.milestones.some(marker => marker.evidence.some(rule => rule.matches?.[key] === true)));
  assert.match(read('03c-always-on.html'), /state\.demoCronVerified = true/);
});

test('Going Further uses the installed facade and requires every configured ID before explicit Finish Course', () => {
  const page = read('04c-going-further.html');
  assert.match(page, /getInstalled\w+Activity/); assert.match(page, /recordCompletion/);
  assert.doesNotMatch(page, /progressPercent|progress_percent/);
  assert.match(page, /ACTIVITY_MILESTONE_ORDER/);
  assert.match(page, /completedAt/);
});

test('each independent checkpoint requires its full success predicate', async () => {
  const cases = [
    ['react-artifact', '01b:react-loop-complete'], ['tools-artifact', '01c:tool-roundtrip-complete'],
    ['router-artifact', '02a:routed-workflow-complete'], ['rag-artifact', '02b:grounded-answer-complete'], ['deep-artifact', '02c:deep-research-complete'],
  ];
  for (const [containerId, id] of cases) {
    const milestone = JSON.parse(fs.readFileSync('web/activity/activity_milestones.json', 'utf8')).milestones.find(marker => marker.id === id);
    const f = fixture(milestone.href.split('#')[0]); try {
      for (const detail of [{ containerId, successCount: 0, hasAnswer: true }, { containerId, successCount: 1, hasAnswer: false }]) {
        dispatch(f.windowTarget, 'chat-completed', detail); await flush(); assert.deepEqual(f.milestones, []);
      }
      dispatch(f.windowTarget, 'chat-completed', { containerId, successCount: 1, hasAnswer: true }); await flush(); assert.deepEqual(f.milestones, [id]);
    } finally { f.restore(); }
  }
  for (const [signal, id] of [['connection-audit-passed', '03a:nemoclaw-connected'], ['live-agent-operated', '04b:live-agent-operated']]) {
    const milestone = JSON.parse(fs.readFileSync('web/activity/activity_milestones.json', 'utf8')).milestones.find(marker => marker.id === id);
    const f = fixture(milestone.href.split('#')[0]); try { dispatch(f.windowTarget, signal); await flush(); assert.deepEqual(f.milestones, [id]); } finally { f.restore(); }
  }
});

test('combined cron result requires both run and cleanup evidence', async () => {
  for (const [runObserved, cleanupSucceeded, expected] of [[true, false, []], [false, true, []], [true, true, ['03c:scheduled-run-complete']]]) {
    const f = fixture('03c-always-on.html'); try {
      dispatch(f.windowTarget, 'canvas-node-succeeded', { canvasId: 'probe-cron', nodeId: 'cr-run', runObserved, cleanupSucceeded }); await flush();
      assert.deepEqual(f.milestones, expected);
    } finally { f.restore(); }
  }
});

}
