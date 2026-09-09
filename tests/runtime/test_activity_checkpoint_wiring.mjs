// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

import {
  getInstalledNemoClawActivity,
  highestContiguousMilestone,
  installNemoClawActivityTracking,
} from '../../web/nemoclaw/scripts/_activity_runtime.js';

const read = path => fs.readFileSync(path, 'utf8');

function trackingFixture(page = '01a-loop.html') {
  const previousLocation = globalThis.location;
  Object.defineProperty(globalThis, 'location', {
    configurable: true,
    value: { pathname: `/nemoclaw/${page}` },
  });
  const windowTarget = new EventTarget();
  const documentTarget = new EventTarget();
  const values = new Map();
  const storageTarget = {
    getItem: key => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
  };
  const milestones = [];
  const activity = {
    start: async () => true,
    recordMilestone: async milestone => { milestones.push(milestone); },
    trackReferral: async () => true,
  };
  installNemoClawActivityTracking({ windowTarget, documentTarget, storageTarget, activity });
  return {
    milestones,
    storageTarget,
    windowTarget,
    restore() {
      if (previousLocation === undefined) delete globalThis.location;
      else Object.defineProperty(globalThis, 'location', { configurable: true, value: previousLocation });
    },
  };
}

function dispatch(target, type, detail) {
  const event = new Event(type);
  event.detail = detail;
  target.dispatchEvent(event);
}

test('out-of-order outcomes advance only through contiguous checkpoints', () => {
  assert.equal(highestContiguousMilestone(new Set(['04b:live-agent-operated'])), null);
  assert.equal(highestContiguousMilestone(new Set([
    '01a:model-call-verified', '01b:react-loop-complete', '01c:tool-roundtrip-complete',
  ])), '01c:tool-roundtrip-complete');
  assert.equal(highestContiguousMilestone(new Set([
    '01a:model-call-verified', '01b:react-loop-complete', '01c:tool-roundtrip-complete',
    '02a:routed-workflow-complete', '02b:grounded-answer-complete',
    '02c:deep-research-complete', '03a:nemoclaw-connected',
    '03b:workspace-inspected', '03c:scheduled-run-complete',
    '04a:policy-boundary-verified', '04b:live-agent-operated',
  ])), '04b:live-agent-operated');
});

test('shared runtimes publish success-only activity signals', () => {
  const canvas = read('web/nemoclaw/scripts/_canvas.js');
  assert.match(canvas, /nemoclaw:run-succeeded/);
  assert.match(canvas, /nemoclaw:canvas-node-succeeded/);
  assert.doesNotMatch(canvas, /publishActivitySignal\([^;]+\bresult\s*[,}]/s);
  assert.match(read('web/nemoclaw/scripts/_chat.js'), /nemoclaw:chat-completed/);
  assert.match(read('web/nemoclaw/scripts/_openclaw.js'), /nemoclaw:connection-audit-passed/);
  assert.match(read('web/nemoclaw/scripts/_openclaw_cli.js'), /nemoclaw:live-agent-operated/);
});

test('checkpoint predicates require explicit successful evidence', () => {
  const source = read('web/nemoclaw/scripts/_activity_runtime.js');
  assert.match(source, /successCount < 1/);
  assert.match(source, /&& runObserved/);
  assert.match(source, /&& cleanupSucceeded/);
  assert.match(source, /&& policyAgreed/);
});

test('the activity runtime maps every approved checkpoint to evidence', () => {
  const source = read('web/nemoclaw/scripts/_activity_runtime.js');
  for (const milestone of [
    '01a:model-call-verified', '01b:react-loop-complete',
    '01c:tool-roundtrip-complete', '02a:routed-workflow-complete',
    '02b:grounded-answer-complete', '02c:deep-research-complete',
    '03a:nemoclaw-connected', '03b:workspace-inspected',
    '03c:scheduled-run-complete', '04a:policy-boundary-verified',
    '04b:live-agent-operated',
  ]) assert.match(source, new RegExp(milestone.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
});

test('the shared course entrypoint installs activity tracking', () => {
  const source = read('web/nemoclaw/scripts/_shared.js');
  assert.match(source, /installNemoClawActivityTracking/);
});

test('installing activity tracking on a page does not advance progress', () => {
  const fixture = trackingFixture();
  try {
    assert.deepEqual(fixture.milestones, []);
  } finally {
    fixture.restore();
  }
});

test('course bootstrap survives browsers that deny sessionStorage access', () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'sessionStorage');
  Object.defineProperty(globalThis, 'sessionStorage', {
    configurable: true,
    get() { throw new DOMException('denied', 'SecurityError'); },
  });
  const windowTarget = new EventTarget();
  const documentTarget = new EventTarget();
  const activity = { start: async () => true, recordMilestone: async () => true };
  try {
    assert.equal(installNemoClawActivityTracking({ windowTarget, documentTarget, activity }), activity);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'sessionStorage', descriptor);
    else delete globalThis.sessionStorage;
  }
});

test('checkpoint evidence from an older release cannot advance the current release', () => {
  const fixture = trackingFixture('01b-react.html');
  try {
    fixture.storageTarget.setItem('dli_activity:nemoclaw:evidence:v1:0', JSON.stringify({
      'milestone:01a:model-call-verified': true,
    }));
    dispatch(fixture.windowTarget, 'nemoclaw:chat-completed', {
      containerId: 'react-artifact', successCount: 1, hasAnswer: true,
    });
    assert.deepEqual(fixture.milestones, []);
  } finally {
    fixture.restore();
  }
});

test('Module 1a advances only after key verification and successful model content', () => {
  const fixture = trackingFixture();
  try {
    dispatch(fixture.windowTarget, 'nemoclaw:run-succeeded', {
      cellId: 'cell-onecall', hasContent: true,
    });
    assert.deepEqual(fixture.milestones, []);

    dispatch(fixture.windowTarget, 'nemoclaw:api-key-verified');
    dispatch(fixture.windowTarget, 'nemoclaw:run-succeeded', {
      cellId: 'cell-onecall', hasContent: false,
    });
    assert.deepEqual(fixture.milestones, []);

    dispatch(fixture.windowTarget, 'nemoclaw:run-succeeded', {
      cellId: 'cell-onecall', hasContent: true,
    });
    assert.deepEqual(fixture.milestones, ['01a:model-call-verified']);
  } finally {
    fixture.restore();
  }
});

test('every 01b through 04b checkpoint requires its full success predicate', () => {
  const cases = [
    ['01b-react.html', 'nemoclaw:chat-completed',
      { containerId: 'react-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'react-artifact', successCount: 0, hasAnswer: true }, '01b:react-loop-complete'],
    ['01c-tools.html', 'nemoclaw:chat-completed',
      { containerId: 'tools-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'tools-artifact', successCount: 1, hasAnswer: false }, '01c:tool-roundtrip-complete'],
    ['02a-routing.html', 'nemoclaw:chat-completed',
      { containerId: 'router-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'wrong-artifact', successCount: 1, hasAnswer: true }, '02a:routed-workflow-complete'],
    ['02b-rag.html', 'nemoclaw:chat-completed',
      { containerId: 'rag-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'rag-artifact', successCount: 0, hasAnswer: false }, '02b:grounded-answer-complete'],
    ['02c-deep.html', 'nemoclaw:chat-completed',
      { containerId: 'deep-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'deep-artifact', successCount: 0, hasAnswer: true }, '02c:deep-research-complete'],
    ['03a-connect.html', 'nemoclaw:connection-audit-passed', {}, null, '03a:nemoclaw-connected'],
    ['04b-operate.html', 'nemoclaw:live-agent-operated', {}, null, '04b:live-agent-operated'],
  ];
  const order = [
    '01a:model-call-verified', '01b:react-loop-complete', '01c:tool-roundtrip-complete',
    '02a:routed-workflow-complete', '02b:grounded-answer-complete', '02c:deep-research-complete',
    '03a:nemoclaw-connected', '03b:workspace-inspected', '03c:scheduled-run-complete',
    '04a:policy-boundary-verified', '04b:live-agent-operated',
  ];
  for (const [page, type, positive, negative, milestone] of cases) {
    const fixture = trackingFixture(page);
    try {
      const position = order.indexOf(milestone);
      fixture.storageTarget.setItem('dli_activity:nemoclaw:evidence:v1:1',
        JSON.stringify(Object.fromEntries(order.slice(0, position)
          .map(item => [`milestone:${item}`, true]))));
      if (negative) {
        dispatch(fixture.windowTarget, type, negative);
        assert.deepEqual(fixture.milestones, [], `${milestone} accepted partial evidence`);
      }
      dispatch(fixture.windowTarget, type, positive);
      assert.deepEqual(fixture.milestones, [milestone], `${milestone} did not advance contiguously`);
    } finally { fixture.restore(); }
  }
});

test('paired checkpoints reject partial evidence and advance after both halves', () => {
  const cases = [
    ['03b-openclaw.html',
      ['nemoclaw:run-succeeded', { cellId: 'cell-introspect' }],
      ['nemoclaw:run-succeeded', { cellId: 'cell-workspace-term' }],
      '03b:workspace-inspected', 7],
    ['03c-always-on.html',
      ['nemoclaw:canvas-node-succeeded', { canvasId: 'probe-cron', nodeId: 'cr-watch', runObserved: true }],
      ['nemoclaw:canvas-node-succeeded', { canvasId: 'probe-cron', nodeId: 'cr-rm', cleanupSucceeded: true }],
      '03c:scheduled-run-complete', 8],
    ['04a-safety.html',
      ['nemoclaw:run-succeeded', { cellId: 'cell-live-policy', hasAgent: true }],
      ['nemoclaw:canvas-node-succeeded', { canvasId: 'cell-predict-confirm', nodeId: 'compare', policyAgreed: true }],
      '04a:policy-boundary-verified', 9],
  ];
  const order = [
    '01a:model-call-verified', '01b:react-loop-complete', '01c:tool-roundtrip-complete',
    '02a:routed-workflow-complete', '02b:grounded-answer-complete', '02c:deep-research-complete',
    '03a:nemoclaw-connected', '03b:workspace-inspected', '03c:scheduled-run-complete',
  ];
  for (const [page, first, second, milestone, priorCount] of cases) {
    const fixture = trackingFixture(page);
    try {
      fixture.storageTarget.setItem('dli_activity:nemoclaw:evidence:v1:1',
        JSON.stringify(Object.fromEntries(order.slice(0, priorCount).map(item => [`milestone:${item}`, true]))));
      dispatch(fixture.windowTarget, first[0], first[1]);
      assert.deepEqual(fixture.milestones, [], `${milestone} accepted partial evidence`);
      dispatch(fixture.windowTarget, second[0], second[1]);
      assert.deepEqual(fixture.milestones, [milestone]);
    } finally { fixture.restore(); }
  }
});

test('reinstalling the tracker returns the existing page activity client', () => {
  const listeners = new Map();
  const windowTarget = {
    addEventListener: (name, listener) => listeners.set(name, listener),
  };
  const documentTarget = { addEventListener() {} };
  const activity = { start() {}, recordMilestone() {} };

  assert.equal(installNemoClawActivityTracking({ windowTarget, documentTarget, activity }), activity);
  assert.equal(installNemoClawActivityTracking({ windowTarget, documentTarget }), activity);
  assert.equal(getInstalledNemoClawActivity(windowTarget), activity);
});

test('Going Further exposes an explicit gated Finish Course action', () => {
  const page = read('web/nemoclaw/04c-going-further.html');
  assert.match(page, /id="finish-course"/);
  assert.match(page, /getInstalledNemoClawActivity/);
  assert.doesNotMatch(page, /createNemoClawActivity/);
  assert.match(page, /getCourseActivityState/);
  assert.match(page, /recordCompletion/);
  assert.match(page, /Course completed/);
  assert.match(page, /state\.progressPercent/);
  assert.match(page, /Number\.isInteger\(state\.progressPercent\)\s*&&\s*state\.progressPercent\s*===\s*100/);
  assert.match(page, /state\.completedAt/);
  assert.doesNotMatch(page, /state\.(?:progress_percent|completed_at)/);
});
