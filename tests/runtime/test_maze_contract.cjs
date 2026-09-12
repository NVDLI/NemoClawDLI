/* Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {discoverCourses} = require('./course_exercise_fixture.cjs');

const root = process.env.COURSE_SOURCE_ROOT;
assert(root, 'COURSE_SOURCE_ROOT is required');
const {roots} = discoverCourses(root);

function engine(html) {
  const marker = html.indexOf('id: "helpers"', html.indexOf('mountCanvasFlow("#cell-llm-maze"'));
  const first = html.indexOf('code: `', marker) + 'code: `'.length;
  let last = first;
  for (; last < html.length; last++) {
    if (html[last] !== '`') continue;
    let slashes=0; for(let i=last-1;html[i]==='\\';i--)slashes++;
    if(slashes%2===0)break;
  }
  assert(marker > 0 && last > first, 'maze engine must remain inspectable');
  return vm.runInNewContext('`' + html.slice(first, last) + '`');
}

let body = engine(fs.readFileSync(path.join(roots[0], '01a-loop.html'), 'utf8'));
for (const directory of roots) {
  assert.match(fs.readFileSync(path.join(directory, '01b-react.html'), 'utf8'),
    /const QUESTION_2 = "[^"\n]*get_current_time[^"\n]*";/);
}

function create() {
  const state = {}, elements = new Map();
  const log = Object.assign(() => {}, { html() {}, details() {} });
  const document = {getElementById(id) {
    if (!id.startsWith('sw')) return null;
    if (!elements.has(id)) elements.set(id, {firstChild: {}, style: {}});
    return elements.get(id);
  }};
  vm.runInNewContext(body, {state, helpers: {log}, document, AbortController, DOMException, console});
  return {state, log, elements};
}

const trap = ['###########','###.###.###','###.###.###','###S......#','###.#######',
  '###.#######','###.#######','#...#######','###.#######','###G#######','###########'];

function tool(id, direction, name = 'choose_direction') {
  return {id, type: 'function', function: {name, arguments: JSON.stringify({direction})}};
}

function validateHistory(messages) {
  const pending = new Set();
  for (const message of messages) {
    if (message.role === 'tool') { assert(pending.delete(message.tool_call_id)); continue; }
    assert.equal(pending.size, 0, 'all tool calls require results before the next turn');
    for (const call of message.tool_calls || []) pending.add(call.id);
  }
  assert.equal(pending.size, 0);
}

// Match the owning executable condition, then evaluate its localized message.
// A missing or duplicated condition must fail rather than accept any rejection.
function visibleError(code, kind, context = {}) {
  const anchors = {
    budget: /throw new Error\(([^\n]*\bcfg\.max\b[^\n]*)\);/g,
    incomplete: /if \(summary\.finish_reason !== 'tool_calls' && summary\.finish_reason !== 'stop'\)\s*throw new Error\(([^\n]*)\);/g,
    malformed: /new Set\(tcs\.map\(function\(tc\) \{ return tc\.id; \}\)\)\.size !== tcs\.length\)\s*throw new Error\(([^\n]*)\);/g,
  };
  const matches = [...code.matchAll(anchors[kind])];
  assert.equal(matches.length, 1, 'expected one displayed '+kind+' error condition');
  const message = vm.runInNewContext('(' + matches[0][1] + ')', context);
  assert.equal(typeof message, 'string');
  assert(message.length > 0, 'displayed error must explain the failure');
  return {name:'Error', message};
}

async function run({grid, choose, signal, stop, finish = 'tool_calls', advanced = false, custom = false} = {}) {
  const {state, log, elements} = create();
  if (grid) state.generateMaze = () => grid;
  const requests = [], positions = [];
  const helpers = {log, signal, getConfig:async()=>({url:"https://integrate.api.nvidia.com/v1",model:custom?"custom-maze-model":"nvidia/nemotron-3.5-lightning-30b-a3b"}), isDefaultModelApiBaseUrl:()=>!custom, delay: async () => {}, async chatStream(req) {
    validateHistory(req.messages);
    assert.equal(req.tool_choice, 'required');
    assert(req.signal, 'Stop must reach the model request');
    requests.push(req);
    const user = req.messages.at(-1).content;
    positions.push(typeof user === 'string' ? user.match(/\((\d+),(\d+)\)/)?.[0] : user);
    assert(positions.at(-1), 'request must expose the current position');
    if (stop) {
      return new Promise((resolve, reject) => {
        req.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), {once:true});
        setTimeout(() => stop(elements), 0);
      });
    }
    const allowed = [...req.tools[0].function.parameters.properties.direction.enum];
    const calls = choose ? choose(requests.length, allowed, req) : [tool('call-'+requests.length, allowed[0])];
    return {content:'', tool_calls:calls, model:req.model, finish_reason:finish};
  }};
  const result = await state.runMaze(helpers, state, {model:'direct', advanced});
  return {result, requests, positions};
}

(async () => {
  for (const directory of roots) {
  body=engine(fs.readFileSync(path.join(directory,'01a-loop.html'),'utf8'));
  const {state} = create();
  for (const finish of ['length', null]) await assert.rejects(run({finish}), visibleError(body, 'incomplete'));
  const grid = state.generateMaze(5,4,42,.3), tree = state.generateMaze(5,4,42,0);
  assert.equal(grid.length, 9); assert.equal(grid[0].length, 11);
  assert.notDeepEqual(grid, tree, 'loop setting must change openings');
  const baseline = await run(); assert(baseline.result.won);
  const advancedPriority = await run({advanced:true, choose(n, allowed) {
    return [tool('priority-'+n, [...'NWSE'].find(direction => allowed.includes(direction)))];
  }});
  assert(advancedPriority.result.won, 'valid advanced branch order must outlast the former 40-call cap');
  assert.equal(advancedPriority.result.decisions, 42);
  assert.equal(advancedPriority.result.guardrails, 0);
  function permutations(letters) {
    if (!letters.length) return [''];
    return letters.flatMap((letter,i) => permutations(letters.filter((_,j) => i!==j)).map(tail => letter+tail));
  }
  for (const order of permutations([...'NSEW'])) {
    const sample = await run({advanced:true, choose(n, allowed) {
      return [tool('order-'+n, [...order].find(direction => allowed.includes(direction)))];
    }});
    assert(sample.result.won, 'valid branch order '+order+' must complete');
    assert.equal(sample.result.guardrails, 0);
  }
  const formerCycle = await run({grid:trap, choose(n,allowed) {
    const preferred = ['S','N','N','E','N','E','W'][n-1];
    return [tool('cycle-'+n, allowed.includes(preferred) ? preferred : allowed[0])];
  }});
  assert(formerCycle.result.won, 'valid choices must not be trapped between exhausted junctions');
  const customBudget = 2 * trap.reduce((total,row) => total + [...row].filter(cell => cell !== '#').length, 0);
  let rejectedTurns = 0;
  const budgetError = visibleError(body, 'budget', {cfg:{max:customBudget}});
  assert(budgetError.message.includes(String(customBudget)), 'visible budget failure must report the derived count');
  assert.throws(()=>visibleError('', 'budget', {cfg:{max:customBudget}}), /expected one displayed budget/);
  assert.throws(()=>visibleError(body+'\n'+body, 'budget', {cfg:{max:customBudget}}), /expected one displayed budget/);
  await assert.rejects(run({grid:trap, choose(n) {
    rejectedTurns++;
    return [tool('invalid-'+n, 'not-a-direction')];
  }}), budgetError);
  assert.equal(rejectedTurns, customBudget, 'custom grids derive the same finite budget; invalid replies consume turns');
  for (const mode of ['multiple','wrong-name','wrong-type','multi-move','left','true']) {
    const sample = await run({choose(n,allowed) {
      if (n > 1) return [tool('good-'+n, allowed[0])];
      if (mode === 'multiple') return [tool('a',allowed[0]),tool('b',allowed[0])];
      if (mode === 'wrong-name') return [tool('a',allowed[0],'other_tool')];
      return [tool('a',mode === 'wrong-type' ? true : mode === 'multi-move' ? allowed[0]+allowed[0] : mode)];
    }});
    assert(sample.result.won); assert.equal(sample.result.guardrails, 1, mode);
    assert.equal(sample.positions[0], sample.positions[1], 'invalid tool output must not move the agent');
  }
  const configured = await run({custom:true});
  assert(configured.requests.every(request=>request.model==="custom-maze-model" && !request.extra_body));
  const parent = new AbortController();
  assert((await run({signal:parent.signal,stop:()=>parent.abort()})).result.stopped);
  assert((await run({stop:elements=>[...elements.values()][0].firstChild.onclick()})).result.stopped);
  await assert.rejects(run({choose:()=>[tool('', 'N')]}), visibleError(body, 'malformed'));
  console.log(JSON.stringify({result:'PASS',directory:path.relative(root,directory),locales:roots.length,
    customBudget,rejectedTurns,defaultDecisions:baseline.result.decisions,
    formerCycleDecisions:formerCycle.result.decisions,advancedPriorityDecisions:advancedPriority.result.decisions,checks:['loop openings','rendered dimensions','default goal',
      'advanced 42-decision goal','24 valid advanced branch orders','custom-grid finite budget',
      'exhausted-junction recovery','multiple and invalid tools','paired tool history','both stop controls','malformed response']}));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
