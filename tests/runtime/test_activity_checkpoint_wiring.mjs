// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const COURSE_ROOTS = fs.readdirSync('web', { withFileTypes: true })
  .filter(entry => entry.isDirectory() && fs.existsSync(path.join('web', entry.name, 'activity-policy.json')))
  .map(entry => path.join('web', entry.name));
assert.equal(COURSE_ROOTS.length, 1, 'expected one discovered Activity-enabled course');
const [COURSE_ROOT] = COURSE_ROOTS;
const COURSE_ID = path.basename(COURSE_ROOT);
const runtimeModule = await import(pathToFileURL(path.resolve(COURSE_ROOT, 'scripts', '_activity_runtime.js')));
const {
  ACTIVITY_MILESTONE_ORDER,
  getInstalledCourseActivity,
  highestContiguousMilestone,
  installCourseActivityTracking,
} = runtimeModule;

const read = path => fs.readFileSync(path, 'utf8');
const source = (...parts) => path.join(COURSE_ROOT, ...parts);
const event = name => `${COURSE_ID}:${name}`;
const connectedMilestone = `03a:${COURSE_ID}-connected`;
const evidenceKey = version => `dli_activity:${COURSE_ID}:evidence:v1:${version}`;

function trackingFixture(page = '01a-loop.html', providedStorageTarget) {
  const previousLocation = globalThis.location;
  Object.defineProperty(globalThis, 'location', {
    configurable: true,
    value: { pathname: `/${COURSE_ID}/${page}` },
  });
  const windowTarget = new EventTarget();
  const documentTarget = new EventTarget();
  const values = new Map();
  const storageTarget = providedStorageTarget || {
    getItem: key => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
  };
  const milestones = [];
  const activity = {
    start: async () => true,
    recordMilestone: async milestone => { milestones.push(milestone); },
    trackReferral: async () => true,
  };
  installCourseActivityTracking({ windowTarget, documentTarget, storageTarget, activity });
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
  assert.equal(highestContiguousMilestone(new Set(ACTIVITY_MILESTONE_ORDER)), '04b:live-agent-operated');
});

test('shared runtimes publish success-only activity signals', () => {
  const canvas = read(source('scripts', '_canvas.js'));
  assert.match(canvas, new RegExp(event('run-succeeded')));
  assert.match(canvas, new RegExp(event('canvas-node-succeeded')));
  assert.doesNotMatch(canvas, /publishActivitySignal\([^;]+\bresult\s*[,}]/s);
  assert.match(read(source('scripts', '_chat.js')), new RegExp(event('chat-completed')));
  assert.match(read(source('scripts', '_openclaw.js')), new RegExp(event('connection-audit-passed')));
  assert.match(read(source('scripts', '_openclaw_cli.js')), new RegExp(event('live-agent-operated')));
});

test('checkpoint predicates require explicit successful evidence', () => {
  const runtimeSource = read(source('scripts', '_activity_runtime.js'));
  assert.match(runtimeSource, /successCount < 1/);
  assert.match(runtimeSource, /&& runObserved/);
  assert.match(runtimeSource, /&& cleanupSucceeded/);
  assert.match(runtimeSource, /&& policyAgreed/);
});

test('the activity runtime maps every approved checkpoint to evidence', () => {
  const runtimeSource = read(source('scripts', '_activity_runtime.js'));
  for (const milestone of ACTIVITY_MILESTONE_ORDER) {
    assert.match(runtimeSource, new RegExp(milestone.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  }
});

test('the shared course entrypoint installs activity tracking', () => {
  const sharedSource = read(source('scripts', '_shared.js'));
  assert.match(sharedSource, /install\w+ActivityTracking/);
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
    assert.equal(installCourseActivityTracking({ windowTarget, documentTarget, activity }), activity);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'sessionStorage', descriptor);
    else delete globalThis.sessionStorage;
  }
});

test('checkpoint prerequisites remain available in memory when session storage is denied', () => {
  const storageTarget = {
    getItem() { throw new DOMException('denied', 'SecurityError'); },
    setItem() { throw new DOMException('denied', 'SecurityError'); },
  };
  const fixture = trackingFixture('01a-loop.html', storageTarget);
  try {
    dispatch(fixture.windowTarget, event('api-key-verified'));
    dispatch(fixture.windowTarget, event('run-succeeded'), {
      cellId: 'cell-onecall', hasContent: true,
    });
    assert.deepEqual(fixture.milestones, ['01a:model-call-verified']);
  } finally {
    fixture.restore();
  }
});

test('checkpoint evidence from an older release cannot advance the current release', () => {
  const fixture = trackingFixture('01b-react.html');
  try {
    fixture.storageTarget.setItem(evidenceKey(0), JSON.stringify({
      'milestone:01a:model-call-verified': true,
    }));
    dispatch(fixture.windowTarget, event('chat-completed'), {
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
    dispatch(fixture.windowTarget, event('run-succeeded'), {
      cellId: 'cell-onecall', hasContent: true,
    });
    assert.deepEqual(fixture.milestones, []);

    dispatch(fixture.windowTarget, event('api-key-verified'));
    dispatch(fixture.windowTarget, event('run-succeeded'), {
      cellId: 'cell-onecall', hasContent: false,
    });
    assert.deepEqual(fixture.milestones, []);

    dispatch(fixture.windowTarget, event('run-succeeded'), {
      cellId: 'cell-onecall', hasContent: true,
    });
    assert.deepEqual(fixture.milestones, ['01a:model-call-verified']);
  } finally {
    fixture.restore();
  }
});

test('every 01b through 04b checkpoint requires its full success predicate', () => {
  const cases = [
    ['01b-react.html', event('chat-completed'),
      { containerId: 'react-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'react-artifact', successCount: 0, hasAnswer: true }, '01b:react-loop-complete'],
    ['01c-tools.html', event('chat-completed'),
      { containerId: 'tools-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'tools-artifact', successCount: 1, hasAnswer: false }, '01c:tool-roundtrip-complete'],
    ['02a-routing.html', event('chat-completed'),
      { containerId: 'router-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'wrong-artifact', successCount: 1, hasAnswer: true }, '02a:routed-workflow-complete'],
    ['02b-rag.html', event('chat-completed'),
      { containerId: 'rag-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'rag-artifact', successCount: 0, hasAnswer: false }, '02b:grounded-answer-complete'],
    ['02c-deep.html', event('chat-completed'),
      { containerId: 'deep-artifact', successCount: 1, hasAnswer: true },
      { containerId: 'deep-artifact', successCount: 0, hasAnswer: true }, '02c:deep-research-complete'],
    ['03a-connect.html', event('connection-audit-passed'), {}, null, connectedMilestone],
    ['04b-operate.html', event('live-agent-operated'), {}, null, '04b:live-agent-operated'],
  ];
  const order = [
    '01a:model-call-verified', '01b:react-loop-complete', '01c:tool-roundtrip-complete',
    '02a:routed-workflow-complete', '02b:grounded-answer-complete', '02c:deep-research-complete',
    connectedMilestone, '03b:workspace-inspected', '03c:scheduled-run-complete',
    '04a:policy-boundary-verified', '04b:live-agent-operated',
  ];
  for (const [page, type, positive, negative, milestone] of cases) {
    const fixture = trackingFixture(page);
    try {
      const position = order.indexOf(milestone);
      fixture.storageTarget.setItem(evidenceKey(1),
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

test('paired checkpoints reject partial evidence in either order', async t => {
  const cases = [
    ['03b-openclaw.html',
      [event('run-succeeded'), { cellId: 'cell-introspect' }],
      [event('run-succeeded'), { cellId: 'cell-workspace-term' }],
      '03b:workspace-inspected', 7],
    ['03c-always-on.html',
      [event('canvas-node-succeeded'), { canvasId: 'probe-cron', nodeId: 'cr-watch', runObserved: true }],
      [event('canvas-node-succeeded'), { canvasId: 'probe-cron', nodeId: 'cr-rm', cleanupSucceeded: true }],
      '03c:scheduled-run-complete', 8],
    ['04a-safety.html',
      [event('run-succeeded'), { cellId: 'cell-live-policy', hasAgent: true }],
      [event('canvas-node-succeeded'), { canvasId: 'cell-predict-confirm', nodeId: 'compare', policyAgreed: true }],
      '04a:policy-boundary-verified', 9],
  ];
  const order = [
    '01a:model-call-verified', '01b:react-loop-complete', '01c:tool-roundtrip-complete',
    '02a:routed-workflow-complete', '02b:grounded-answer-complete', '02c:deep-research-complete',
    connectedMilestone, '03b:workspace-inspected', '03c:scheduled-run-complete',
  ];
  for (const [page, left, right, milestone, priorCount] of cases) {
    for (const [first, second] of [[left, right], [right, left]]) {
      await t.test(`${milestone}: ${first[1].cellId || first[1].nodeId} first`, () => {
        const fixture = trackingFixture(page);
        try {
          fixture.storageTarget.setItem(evidenceKey(1),
            JSON.stringify(Object.fromEntries(order.slice(0, priorCount).map(item => [`milestone:${item}`, true]))));
          dispatch(fixture.windowTarget, first[0], first[1]);
          assert.deepEqual(fixture.milestones, [], `${milestone} accepted partial evidence`);
          dispatch(fixture.windowTarget, second[0], second[1]);
          assert.deepEqual(fixture.milestones, [milestone]);
        } finally { fixture.restore(); }
      });
    }
  }
});

test('reinstalling the tracker returns the existing page activity client', () => {
  const listeners = new Map();
  const windowTarget = {
    addEventListener: (name, listener) => listeners.set(name, listener),
  };
  const documentTarget = { addEventListener() {} };
  const activity = { start() {}, recordMilestone() {} };

  assert.equal(installCourseActivityTracking({ windowTarget, documentTarget, activity }), activity);
  assert.equal(installCourseActivityTracking({ windowTarget, documentTarget }), activity);
  assert.equal(getInstalledCourseActivity(windowTarget), activity);
});

test('Going Further exposes an explicit gated Finish Course action', () => {
  const page = read(source('04c-going-further.html'));
  assert.match(page, /id="finish-course"/);
  assert.match(page, /getInstalled\w+Activity/);
  assert.doesNotMatch(page, /create\w+Activity/);
  assert.match(page, /getCourseActivityState/);
  assert.match(page, /recordCompletion/);
  assert.match(page, /Course completed/);
  assert.match(page, /state\.progressPercent/);
  assert.match(page, /Number\.isInteger\(state\.progressPercent\)\s*&&\s*state\.progressPercent\s*===\s*100/);
  assert.match(page, /state\.completedAt/);
  assert.doesNotMatch(page, /state\.(?:progress_percent|completed_at)/);
});
