// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import './test_openclaw_pomerium_transport.mjs';
import './test_helper_registry.mjs';
import './test_model_routing.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

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
