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
function cell(page, id) {
  const source = fs.readFileSync(path.join(root, 'web/nemoclaw', page), 'utf8');
  const start = source.indexOf('mountRunCell("#' + id + '"');
  assert(start >= 0, id);
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
  const discovery = cell('03a-kickstart.html', 'bench-fetch-models');
  const measure = cell('03a-kickstart.html', 'bench-measure-models');
  const state = {};
  await run(discovery, state, helpers);
  assert.deepEqual(state.models, ['course/agent']);
  assert.equal(requests[0].init.headers.Authorization, undefined);
  assert.equal(requests[0].init.signal, helpers.signal);
  assert(logs.some(line => line.includes('available model IDs')));
  catalog = [{id: 'provider/novel-chat'}];
  await run(discovery, state, helpers);
  assert.deepEqual(state.models, []);
  assert(logs.some(line => line.includes('edit FILTER')));
  const before = requests.length;
  await run(measure, state, helpers);
  assert.equal(requests.length, before);
  catalog = [{id: 'course/agent'}];
  await run(discovery, state, helpers);
  status = 503;
  await run(discovery, state, helpers);
  assert.deepEqual(state.models, []);
  status = 200;
  await run(discovery, state, helpers);
  config.url = 'https://changed.test/v1';
  const beforeChange = requests.length;
  await run(measure, state, helpers);
  assert.equal(requests.length, beforeChange);
  assert(logs.some(line => line.includes('Connection changed')));
  config.needsKey = true;
  await run(discovery, state, helpers);
  assert.deepEqual(state.models, []);
  config.needsKey = false;
  const preview = cell('01b-react.html', 'cell-finish-reason');
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
