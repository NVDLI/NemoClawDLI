# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Execute the authored cells against bounded transport fixtures."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]

SCRIPT = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = process.cwd();
function cell(id, directory = path.join(root, 'web')) {
  const marker = 'mountRunCell("#' + id + '"';
  function sources(dir) {
    return fs.readdirSync(dir, {withFileTypes: true}).flatMap(entry => {
      const file = path.join(dir, entry.name);
      if (entry.isDirectory()) return sources(file);
      return entry.isFile() && entry.name.endsWith('.html') ? [fs.readFileSync(file, 'utf8')] : [];
    });
  }
  const matches = sources(directory).filter(source => source.includes(marker));
  assert.equal(matches.length, 1, id + ': expected one authored cell');
  const source = matches[0];
  const start = source.indexOf(marker);
  const rest = source.slice(start);
  const match = rest.match(/code:\s*(`(?:\\[\s\S]|[^`\\])*`)/);
  assert(match, id + ' code');
  return vm.runInNewContext(match[1]);
}
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const run = (code, state, helpers) => new AsyncFunction('state', 'helpers', 'log', 'chat', code)(state, helpers, helpers.log, helpers.chat);
const logs = [];
const log = (...args) => logs.push(args.join(' '));
log.h = log; log.details = log; log.json = log;
log.kv = object => Object.entries(object).forEach(([key, value]) => log(key, value));
const config = {url: 'https://course.test/api/llm/v1', model: 'course/agent', needsKey: false};
let key = '', catalog = [{id: 'course/agent'}, {id: 'provider/chat'}, {id: 'provider/vision'}];
let status = 200;
const requests = [];
const helpers = {
  log, signal: new AbortController().signal,
  getConfig: async () => config, getKey: () => key,
  isDefaultModelApiBaseUrl: () => false,
  browserChatFetch: () => async (url, init) => {
    requests.push({url, init});
    return new Response(JSON.stringify({data: catalog}), {status});
  },
};
(async () => {
  const temporary = fs.mkdtempSync(path.join(require('node:os').tmpdir(), 'cell-discovery-'));
  try {
    const nested = path.join(temporary, 'new-course', 'lessons');
    fs.mkdirSync(nested, {recursive: true});
    const original = path.join(nested, 'new-lesson.html');
    const renamed = path.join(nested, 'renamed-lesson.html');
    fs.writeFileSync(original, 'mountRunCell("#probe", {code: `return 7;`});');
    assert.equal(cell('probe', temporary), 'return 7;');
    fs.renameSync(original, renamed);
    assert.equal(cell('probe', temporary), 'return 7;');
    fs.writeFileSync(renamed, 'mountRunCell("#probe-near-match", {code: `return 7;`});');
    assert.throws(() => cell('probe', temporary), /expected one authored cell/);
    fs.unlinkSync(renamed);
    assert.throws(() => cell('probe', temporary), /expected one authored cell/);
  } finally { fs.rmSync(temporary, {recursive: true, force: true}); }
  const discovery = cell('bench-fetch-models');
  const measure = cell('bench-measure-models');
  const state = {};
  await run(discovery, state, helpers);
  assert.deepEqual(state.models, ['course/agent']);
  assert.equal(requests[0].init.headers.Authorization, undefined);
  assert.equal(requests[0].init.signal, helpers.signal);
  assert(logs.some(line => line.includes('available model IDs')));
  catalog = [{id: 'provider/novel-chat'}];
  await assert.rejects(run(discovery, state, helpers), /edit FILTER/);
  assert.deepEqual(state.models, []);
  const before = requests.length;
  await assert.rejects(run(measure, state, helpers), /Fetch matching models/);
  assert.equal(requests.length, before);
  catalog = [{id: 'course/agent'}];
  await run(discovery, state, helpers);
  status = 503;
  await assert.rejects(run(discovery, state, helpers), /HTTP 503/);
  assert.deepEqual(state.models, []);
  status = 200;
  await run(discovery, state, helpers);
  config.url = 'https://changed.test/v1';
  const beforeChange = requests.length;
  await assert.rejects(run(measure, state, helpers), /Connection changed/);
  assert.equal(requests.length, beforeChange);
  config.needsKey = true;
  await assert.rejects(run(discovery, state, helpers), /No API key saved/);
  assert.deepEqual(state.models, []);
  config.needsKey = false;
  config.url = 'https://course.test/api/llm/v1';
  await run(discovery, state, helpers);
  let wire = 'data: {"choices":[{"delta":{"reasoning_content":"fixture reasoning"}}]}\r\n\r\n' +
    'data: {"choices":[{"delta":{"content":"fixture answer"},"finish_reason":"stop"}]}\r\n\r\n' +
    'data: [DONE]\r\n\r\n';
  let cancelled = 0;
  helpers.browserChatFetch = () => async (_url, init) => {
    assert.equal(JSON.parse(init.body).model, config.model);
    return new Response(new ReadableStream({start(controller) {
      controller.enqueue(new TextEncoder().encode(wire));
    },cancel() {cancelled++;}}),{headers:{'Content-Type':'text/event-stream'}});
  };
  const measured = await run(measure, state, helpers);
  assert.deepEqual(measured.ranked, ['course/agent']);
  assert.equal(state.results[0].text, 'fixture answer');
  assert.equal(state.results[0].think, 'fixture reasoning');
  assert.equal(cancelled,1,'DONE must cancel the still-open stream');
  wire = 'data: {"error":{"message":"fixture stream failed"}}\n\n';
  await assert.rejects(run(measure, state, helpers), /fixture stream failed/);
  assert.equal(state.results[0].err, 'fixture stream failed');
  wire = 'data: [DONE]\n\n';
  await assert.rejects(run(measure, state, helpers), /complete final response/);
  const preview = cell('cell-finish-reason');
  for (const toolCalls of [[], [{id: 'call-clock', function: {name: 'get_current_time', arguments: '{}'}}]]) {
    config.model = toolCalls.length ? 'provider/switched-model' : 'course/agent';
    const sent = [];
    helpers.chat = async body => {
      sent.push(body);
      return {model: 'provider/actual-model', choices: [{finish_reason: body.tools && toolCalls.length ? 'tool_calls' : 'stop', message: {content: 'I cannot check the time here.', tool_calls: body.tools ? toolCalls : []}}]};
    };
    logs.length = 0;
    const result = await run(preview, {}, helpers);
    assert.equal(sent.length, 2);
    assert(sent.every(body => body.model === config.model));
    for (const body of sent) assert(logs.some(line => line.includes(body.messages[0].content)));
    assert(logs.some(line => line.includes('I cannot check the time here.')));
    assert(logs.some(line => line.includes('provider/actual-model')));
    assert.equal(result.call2, toolCalls.length ? 'tool_calls' : 'stop');
    assert.equal(logs.some(line => line.includes('No clock reading was taken')), !toolCalls.length);
  }
  console.log('PASS: authored preview, model identity, keyless catalog, no-match recovery, failed discovery, stale connection, missing key');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''


class CourseObservabilityTests(unittest.TestCase):
    def test_authored_cells_preserve_inputs_and_failure_state(self):
        result = subprocess.run(
            ["node", "-e", SCRIPT], cwd=ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
