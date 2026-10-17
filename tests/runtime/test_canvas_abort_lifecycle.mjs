// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

// Execute the production node runner. DOM stubs record only its publication boundary;
// the asynchronous cell and cancellation signal are real, not a copied runner.
const source = await readFile(new URL('../../web/nemoclaw/scripts/_canvas.js', import.meta.url), 'utf8');
const start = source.indexOf('  async function runNode(nodeId) {');
const end = source.indexOf('\n  function setStatus(', start);
assert(start >= 0 && end > start, 'production canvas runner must be discoverable');
const runner = source.slice(start, end);

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

function fixture({ waitForConfig = false } = {}) {
  const pending = deferred();
  const entered = deferred();
  const elements = new Map();
  const statuses = [];
  const publications = [];
  const returns = [];
  const element = () => ({ textContent: '', innerHTML: '', appendChild() {}, style: {} });
  const panel = { querySelector(selector) {
    if (!elements.has(selector)) elements.set(selector, element());
    return elements.get(selector);
  } };
  const ac = new AbortController();
  let calls = 0;
  const context = vm.createContext({
    console, performance, AbortController, DOMException,
    nodes: [{ id: 'novel-node', code: 'return await helpers.delayed();' }],
    ns: { 'novel-node': { code: 'return await helpers.delayed();', output: 'previous output' } },
    runEpoch: 1, runAC: ac, shared: {}, helperOverrides: {},
    _liveHelpers: null, _liveViz: null,
    target: { id: 'novel-canvas' },
    panelsHost: { querySelector: () => panel },
    document: { createElement: element },
    getConfig: async () => {
      if (waitForConfig) { entered.resolve(); await pending.promise; }
      return { mode: 'proxy' };
    },
    HELPER_FNS: { delayed: async () => {
      calls++;
      entered.resolve();
      await pending.promise; // Deliberately ignores the injected AbortSignal.
      return { run_status: 'ok', removed: true };
    } },
    bindRunSignal: (helpers, signal) => { helpers.signal = signal; },
    setStatus: (_id, status) => statuses.push(status),
    publishActivitySignal: (...args) => publications.push(args),
    _appendCellReturn: (_el, value) => returns.push(value),
    flowEdgesInto() {}, _installStructuredLog() {}, _auditHelperMenu() {},
    makeViz: () => ({}), _parseErrLine: () => null,
    _buildDebugDet: element, appendLogLine: element,
    escapeHtml: String,
  });
  vm.runInContext(`${runner}\nglobalThis.runNode = runNode;`, context);
  return { context, ac, pending, entered, elements, statuses, publications, returns, calls: () => calls };
}

for (const replaceController of [false, true]) {
  const f = fixture();
  const running = f.context.runNode('novel-node');
  await f.entered.promise;
  f.ac.abort(new DOMException('Stopped by learner', 'AbortError'));
  // Classification must use the captured signal, even if outer lifecycle state changes.
  if (replaceController) f.context.runAC = new AbortController();
  f.pending.resolve();
  await assert.rejects(running, error => error.name === 'AbortError');
  assert.deepEqual(f.statuses, ['running', 'idle']);
  assert.equal(f.context.ns['novel-node'].output, 'previous output');
  assert.equal(f.elements.get('[data-results-meta]').textContent, 'stopped');
  assert.equal(f.elements.get('.cf-panel-overview').innerHTML, '');
  assert.deepEqual(f.publications, []);
  assert.deepEqual(f.returns, []);
}

{
  const f = fixture({ waitForConfig: true });
  const running = f.context.runNode('novel-node');
  await f.entered.promise;
  f.ac.abort(new DOMException('Stopped during configuration', 'AbortError'));
  f.pending.resolve();
  await assert.rejects(running, error => error.name === 'AbortError');
  assert.equal(f.calls(), 0, 'Stop before setup completes must prevent cell execution');
  assert.deepEqual(f.statuses, []);
  assert.deepEqual(f.publications, []);
}

{
  const f = fixture();
  const running = f.context.runNode('novel-node');
  await f.entered.promise;
  f.pending.resolve();
  await running;
  assert.deepEqual(f.statuses, ['running', 'complete']);
  assert.equal(f.publications.length, 1, 'ordinary completion must still publish evidence');
  assert.equal(f.publications[0][1].runObserved, true);
  assert.equal(f.returns.length, 1);
}

console.log('PASS canvas cancellation: late helper results, captured signal, setup cancellation, ordinary completion');
