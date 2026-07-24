// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { loadRuntime } from "./runtime-loader.js";
import "./execution-contract.js";
import "./notebook-syntax.js";

const PACKAGE_PROFILES = Object.freeze({
  core: [],
  network: ["requests", "pyodide-http", "openai"],
});

const EXECUTE_CELL = globalThis.PYODIDE_EXECUTION_CONTRACT.source;

let loadedProfile;
let kernelReady = false;
let executionCount = 0;

async function prepareRuntime(profile = "core") {
  const packages = PACKAGE_PROFILES[profile];
  if (!packages) throw new Error(`Unknown Pyodide profile: ${profile}`);

  const pyodide = await loadRuntime();
  if (!kernelReady) {
    pyodide.runPython('__course_scope = {"__name__": "__main__"}');
    kernelReady = true;
  }
  if (loadedProfile !== profile && packages.length) {
    await pyodide.loadPackage(packages);
    if (packages.includes("pyodide-http")) {
      await pyodide.runPythonAsync("import pyodide_http; pyodide_http.patch_all()\n");
    }
  }
  loadedProfile = profile;
  return pyodide;
}

async function runCell({ source, inputs = {}, profile = "core" }) {
  const pyodide = await prepareRuntime(profile);
  executionCount += 1;
  const normalized = globalThis.PYODIDE_NOTEBOOK_SYNTAX.normalize(source);
  pyodide.globals.set("__cell_source", normalized.source);
  pyodide.globals.set("__cell_inputs", inputs);
  pyodide.globals.set("__execution_count", executionCount);
  const reply = JSON.parse(String(await pyodide.runPythonAsync(EXECUTE_CELL)));
  if (reply.error_line && normalized.lineOffset) reply.error_line = Math.max(1, reply.error_line - normalized.lineOffset);
  return reply;
}

self.addEventListener("message", async ({ data }) => {
  const { id, type = "run" } = data;
  try {
    const result = type === "preload"
      ? (await prepareRuntime(data.profile), { ok: true, stdout: "", stderr: "", value: null })
      : await runCell(data);
    self.postMessage({ id, ...result });
  } catch (error) {
    self.postMessage({
      id,
      ok: false,
      stdout: "",
      stderr: error instanceof Error ? error.message : String(error),
      value: null,
      display: "",
      has_value: false,
      execution_count: executionCount || null,
    });
  }
});
