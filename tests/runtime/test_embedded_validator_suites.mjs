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
import './test_activity_sdk.mjs';
import './test_activity_course_integration.mjs';
import './test_activity_checkpoint_wiring.mjs';
import './test_course_exercises.mjs';
import './test_course_gateway.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const transportContracts = directory => fs.readdirSync(directory, {withFileTypes:true}).flatMap(entry => {
  const file = path.join(directory, entry.name);
  if (entry.isDirectory()) return transportContracts(file);
  return entry.isFile() && /^test_openclaw_.+_transport\.mjs$/.test(entry.name) ? [file] : [];
}).sort();

test('transport discovery follows added, renamed, deleted and malformed entries', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'transport-discovery-'));
  try {
    const nested = path.join(directory, 'nested');
    fs.mkdirSync(nested);
    const novel = path.join(directory, 'test_openclaw_novel_transport.mjs');
    const moved = path.join(nested, 'test_openclaw_renamed_transport.mjs');
    fs.writeFileSync(novel, 'import test from "node:test"; test("novel", () => {});');
    assert.deepEqual(transportContracts(directory), [novel]);
    fs.renameSync(novel, moved);
    fs.writeFileSync(moved, 'import test from "node:test"; test("nested", () => { throw Error("discovery-sentinel"); });');
    for (const name of ['test_openclaw__transport.mjs', 'test_other_transport.mjs', 'test_openclaw_near_transport.mjs.bak']) {
      fs.writeFileSync(path.join(directory, name), 'throw Error("malformed near-match must not execute");');
    }
    assert.deepEqual(transportContracts(directory), [moved]);
    const result = spawnSync(process.execPath, ['--test', ...transportContracts(directory)], {encoding:'utf8', timeout:10000});
    assert.equal(result.status, 1);
    assert.match(result.stdout, /discovery-sentinel/);
    fs.unlinkSync(moved);
    assert.deepEqual(transportContracts(directory), []);
  } finally {fs.rmSync(directory, {recursive:true, force:true});}
});

test('discovered launchable transport contracts', {timeout:45000}, () => {
  const files = transportContracts(path.join(ROOT, 'tests/runtime'));
  assert(files.length, 'No launchable transport contracts discovered');
  const result = spawnSync(process.execPath, ['--test', ...files], {cwd:ROOT, encoding:'utf8', timeout:40000});
  assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
});

function runFixture(script) {
  return spawnSync(process.execPath, [script, '--self-test'], {
    cwd: ROOT,
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
    cwd:ROOT, encoding:'utf8', timeout:110000,
  });
  assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
});
