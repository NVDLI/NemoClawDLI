// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from "node:assert/strict";
import test from "node:test";
import { pathToFileURL } from "node:url";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
await import(pathToFileURL(path.join(root, "scripts/pyodide/examples/execution-contract.js")));
const contract = globalThis.PYODIDE_EXECUTION_CONTRACT;

test("every injected browser-Python helper is discoverable exactly once", () => {
  const documented = contract.helpers.map(item => item.name);
  assert.equal(new Set(documented).size, documented.length);
  assert.deepEqual(
    [...documented].sort(),
    [...contract.injectedHelpers].sort(),
  );
});

test("a missing helper document is rejected", () => {
  assert.throws(
    () => contract.validateHelperDocs(contract.helpers.slice(1)),
    /missing:/,
  );
});

test("a duplicate helper document is rejected", () => {
  assert.throws(
    () => contract.validateHelperDocs([...contract.helpers, contract.helpers[0]]),
    /duplicate:/,
  );
});

test("an undocumented injected helper is rejected", () => {
  const mutated = contract.source.replace(
    '\nhelper_defaults = {',
    '\ndef newly_injected_helper():\n    return None\n\nhelper_defaults = {\n    "newly_injected_helper": newly_injected_helper,',
  );
  assert.throws(
    () => contract.validateHelperDocs(contract.helpers, mutated),
    /missing: newly_injected_helper/,
  );
});

test("a helper document without its own source is rejected", () => {
  const changed = contract.helpers.map((item, index) => index ? item : { ...item, source: "" });
  assert.throws(
    () => contract.validateHelperDocs(changed),
    /source missing:/,
  );
});
