// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';
import os from 'node:os';
import './test_helper_registry.mjs';
import './test_model_routing.mjs';
import './test_course_exercises.mjs';
import './test_course_gateway.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
// Start independent runners even when this aggregate is itself run with --test.
const childEnvironment = {...process.env};
delete childEnvironment.NODE_TEST_CONTEXT;
const discoverContracts = (directory, pattern) => fs.readdirSync(directory, {withFileTypes:true}).flatMap(entry => {
  const file = path.join(directory, entry.name);
  if (entry.isDirectory()) return discoverContracts(file, pattern);
  return entry.isFile() && pattern.test(entry.name) ? [file] : [];
}).sort();

const contractFamilies = [
  {name:'launchable transport', pattern:/^test_openclaw_.+_transport\.mjs$/, prefix:'test_openclaw_', suffix:'_transport.mjs', timeout:40000},
  {name:'Activity', pattern:/^test_activity_.+\.mjs$/, prefix:'test_activity_', suffix:'.mjs', timeout:80000},
];
for (const {name, pattern, prefix, suffix, timeout} of contractFamilies) {
  test(name + ' discovery follows added, renamed, deleted and malformed entries', () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'contract-discovery-'));
    try {
      const nested = path.join(directory, 'nested');
      fs.mkdirSync(nested);
      const novel = path.join(directory, prefix + 'novel' + suffix);
      const moved = path.join(nested, prefix + 'renamed' + suffix);
      fs.writeFileSync(novel, 'import test from "node:test"; test("novel", () => {});');
      assert.deepEqual(discoverContracts(directory, pattern), [novel]);
      fs.renameSync(novel, moved);
      fs.writeFileSync(moved, 'import test from "node:test"; test("nested", () => { throw Error("discovery-sentinel"); });');
      for (const filename of [prefix + suffix, 'test_other_contract.mjs', prefix + 'near' + suffix + '.bak']) {
        fs.writeFileSync(path.join(directory, filename), 'throw Error("malformed near-match must not execute");');
      }
      assert.deepEqual(discoverContracts(directory, pattern), [moved]);
      const result = spawnSync(process.execPath, ['--test', ...discoverContracts(directory, pattern)], {env:childEnvironment, encoding:'utf8', timeout:10000});
      assert.equal(result.status, 1, String(result.error || '') + result.stdout + result.stderr);
      assert.match(result.stdout, /discovery-sentinel/);
      fs.unlinkSync(moved);
      assert.deepEqual(discoverContracts(directory, pattern), []);
    } finally {fs.rmSync(directory, {recursive:true, force:true});}
  });

  test('discovered ' + name + ' contracts', {timeout:timeout + 5000}, () => {
    const files = discoverContracts(path.join(ROOT, 'tests/runtime'), pattern);
    assert(files.length, 'No ' + name + ' contracts discovered');
    const result = spawnSync(process.execPath, ['--test', ...files], {cwd:ROOT, env:childEnvironment, encoding:'utf8', timeout});
    assert.equal(result.status, 0, String(result.error || '') + result.stdout + result.stderr);
    console.log(name + ' contracts: PASS (' + files.length + ' discovered files)');
  });
}

function runFixture(script) {
  return spawnSync(process.execPath, [script, '--self-test'], {
    cwd: ROOT,
    env: childEnvironment,
    encoding: 'utf8',
  });
}

for (const [name, script] of [
  ['gateway token detector', 'scripts/validation/gateway_token_audit.mjs'],
  ['course link engine', 'scripts/runtime/engine.js'],
]) {
  test(name, () => {
    const result = runFixture(script);
    assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
  });
}

test('native invocation and reference attachment contracts', {timeout:120000}, () => {
  const result = spawnSync(process.execPath, ['--test', path.join(ROOT, 'tests/runtime/test_course_runtime_contract.mjs')], {
    cwd:ROOT, env:childEnvironment, encoding:'utf8', timeout:110000,
  });
  assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
});
