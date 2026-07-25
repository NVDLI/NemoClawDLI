// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const MANIFEST = JSON.parse(await readFile(path.join(HERE, "candidate-components.json"), "utf8"));
await import(pathToFileURL(path.join(HERE, "examples/cell-examples.js")));
await import(pathToFileURL(path.join(HERE, "examples/execution-contract.js")));
await import(pathToFileURL(path.join(HERE, "examples/notebook-syntax.js")));
const EXAMPLES = globalThis.PYODIDE_CELL_EXAMPLES;
const EXECUTE_CELL = globalThis.PYODIDE_EXECUTION_CONTRACT.source;
const CDN_BASE = `https://cdn.jsdelivr.net/pyodide/v${MANIFEST.runtime.pyodide}/full/`;
const args = process.argv.slice(2);

function argument(name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : null;
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function downloadCoreAssets() {
  const target = path.join(os.tmpdir(), `nemoclaw-pyodide-${MANIFEST.runtime.pyodide}`);
  await mkdir(target, { recursive: true });
  for (const asset of MANIFEST.live_core_assets) {
    const destination = path.join(target, asset.file);
    try {
      const cached = await readFile(destination);
      if (sha256(cached) === asset.sha256) continue;
    } catch {
      // A missing or unreadable cache entry is downloaded below.
    }
    const response = await fetch(new URL(asset.file, CDN_BASE));
    if (!response.ok) throw new Error(`Download failed for ${asset.file}: ${response.status}`);
    const bytes = new Uint8Array(await response.arrayBuffer());
    if (sha256(bytes) !== asset.sha256) {
      throw new Error(`SHA-256 mismatch for ${asset.file}`);
    }
    await writeFile(destination, bytes);
  }
  return target;
}

async function verifyLocalAssets(directory) {
  for (const asset of MANIFEST.core_assets) {
    const bytes = await readFile(path.join(directory, asset.file));
    if (sha256(bytes) !== asset.sha256) throw new Error(`SHA-256 mismatch for ${asset.file}`);
  }
  return directory;
}

const assetDirectory = args.includes("--cdn")
  ? await downloadCoreAssets()
  : await verifyLocalAssets(argument("--asset-dir") || process.env.PYODIDE_ASSET_DIR || "");

const modulePath = path.join(assetDirectory, "pyodide.mjs");
const { loadPyodide } = await import(pathToFileURL(modulePath));
const pyodide = await loadPyodide({ indexURL: `${assetDirectory}${path.sep}` });
pyodide.runPython('__course_scope = {"__name__": "__main__"}');
let executionCount = 0;

async function execute(source, inputs) {
  executionCount += 1;
  const normalized = globalThis.PYODIDE_NOTEBOOK_SYNTAX.normalize(source);
  pyodide.globals.set("__cell_source", normalized.source);
  pyodide.globals.set("__cell_inputs", inputs);
  pyodide.globals.set("__execution_count", executionCount);
  const reply = JSON.parse(String(await pyodide.runPythonAsync(EXECUTE_CELL)));
  if (reply.error_line && normalized.lineOffset) reply.error_line = Math.max(1, reply.error_line - normalized.lineOffset);
  return reply;
}

if (!Array.isArray(EXAMPLES) || EXAMPLES.length < 8) {
  throw new Error("At least eight progressive Python examples are required");
}

const coverage = new Set();
const results = [];
const exampleReplies = new Map();
for (const example of EXAMPLES) {
  for (const useCase of example.coverage) coverage.add(useCase);
  const reply = await execute(example.source, {
    user_input: example.input,
    history: [],
    base_url: "https://integrate.api.nvidia.com/v1",
    model: "nvidia/nemotron-3-nano-30b-a3b",
  });
  if (!reply.ok || reply.value?.example !== example.id) {
    throw new Error(`Progressive cell failed: ${example.id}: ${reply.stderr || JSON.stringify(reply.value)}`);
  }
  results.push(example.id);
  exampleReplies.set(example.id, reply);
}

const backgroundReply = exampleReplies.get("background-job");
const artifactReply = exampleReplies.get("artifact-generation");
const artifactDisplay = artifactReply?.displays?.find(item => item.type === "application/x-course-artifact+json");
const artifactPayload = artifactDisplay ? JSON.parse(artifactDisplay.data) : null;
if (backgroundReply?.value?.registration?.name !== "prepare-summary"
    || artifactReply?.value?.job_state !== "completed"
    || artifactPayload?.filename !== "browser-python-report.json"
    || JSON.parse(artifactPayload.content).background_job.state !== "completed") {
  throw new Error("Background registration did not produce the downloadable JSON artifact");
}
const cancelledReply = await execute(`import asyncio
async def linger():
    await asyncio.sleep(30)
register_background("cancel-me", linger())
await cancel_background("cancel-me")
background_status("cancel-me")`, {});
if (cancelledReply.value?.state !== "cancelled") {
  throw new Error("Background cancellation did not settle the registered task");
}

if (!results.includes("output-channels")) throw new Error("stdout example is missing");
const outputReply = await execute(EXAMPLES.find((item) => item.id === "output-channels").source, {
  user_input: "4, 9, 16",
});
if (!outputReply.stdout.includes("calculating square roots")) throw new Error("stdout was not captured");

const errorReply = await execute("values = [1]\nvalues[9]", {});
if (errorReply.ok || !errorReply.stderr.includes("IndexError") || errorReply.error_line !== 2) {
  throw new Error("Python exception was not surfaced through stderr");
}

const expressionReply = await execute("2 + 3", {});
if (expressionReply.stdout || expressionReply.display !== "5" || !expressionReply.has_value) {
  throw new Error("Final expression did not produce a Jupyter-style display value");
}
const stateStart = await execute("repl_value = 41\nrepl_value", {});
const stateNext = await execute("repl_value += 1\nrepl_value", {});
if (stateStart.display !== "41" || stateNext.display !== "42" || stateNext.execution_count !== stateStart.execution_count + 1) {
  throw new Error("Python namespace or execution counter did not persist between runs");
}
const inspectReply = await execute("??repl_value", {});
if (!inspectReply.ok || !inspectReply.display.includes("builtins.int") || !inspectReply.display.includes('"value": "42"')) {
  throw new Error("Notebook ?? inspection did not resolve a persistent value");
}
const shellReply = await execute("!echo hello pipes | rev | tr 'a-z' 'A-Z'", {});
if (!shellReply.ok || !shellReply.stdout.includes("SEPIP OLLEH")) {
  throw new Error(`Bounded browser-shell pipeline did not execute: ${JSON.stringify(shellReply)}`);
}
const magicReply = await execute("%magic", {});
// Assert the magics a learner actually types, not the prose that describes them, so the
// help text stays free to satisfy the prose gates.
const magicTokens = ["value?", "%%bash", "%%time", "%who", "%pwd", "%pip list", "%timeit", "%magic"];
const missingMagics = magicTokens.filter((token) => !magicReply.display.includes(token));
if (!magicReply.ok || missingMagics.length) {
  throw new Error(`Notebook magic help did not render: ${JSON.stringify(missingMagics)}`);
}
const prettyReply = await execute("{'outer': {'numbers': list(range(12)), 'ready': True}}", {});
if (prettyReply.display_type !== "application/json" || prettyReply.display_language !== "json"
    || JSON.parse(prettyReply.display).outer.ready !== true || !prettyReply.display.includes("\n")) {
  throw new Error("Container output was not emitted as indented JSON");
}
const structuredObjectReply = await execute(`from dataclasses import dataclass
@dataclass
class Usage:
    input_tokens: int
    output_tokens: int
class Message:
    def model_dump(self, mode="python"):
        if mode != "json":
            raise ValueError("JSON mode is required")
        return {
            "type": "ai",
            "content": "Structured response",
            "usage": Usage(18, 23),
        }
[Message(), {"nested": Message()}]`, {});
const structuredObjects = JSON.parse(structuredObjectReply.display);
if (structuredObjectReply.display_type !== "application/json"
    || structuredObjects[0].type !== "ai"
    || structuredObjects[0].usage.input_tokens !== 18
    || structuredObjects[1].nested.content !== "Structured response"
    || structuredObjectReply.display.includes("Message object at")) {
  throw new Error("Explicit structured Python objects were not recursively emitted as JSON");
}
const ordinaryObjectReply = await execute(`class Ordinary:
    def __repr__(self):
        return "Ordinary(display-only)"
Ordinary()`, {});
if (ordinaryObjectReply.display_type !== "text/plain" || ordinaryObjectReply.display !== "Ordinary(display-only)") {
  throw new Error("Ordinary Python objects no longer retain their plain repr fallback");
}
const richReply = await execute(`display_markdown("**Markdown works**")
display_html("<strong>HTML works</strong>")
display_json({"ready": True, "count": 3})
display_code("def greet(name):\\n    return f'Hello, {name}'", language="python")
display_table([{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}])
Code("answer = 6 * 7", language="python")`, {});
if (richReply.displays?.map(item => item.type).join(",") !== "text/markdown,text/html,application/json,text/x-code,text/html"
    || richReply.display_type !== "text/x-code" || richReply.display_language !== "python") {
  throw new Error("Display helpers did not preserve Markdown, HTML, JSON, code, and table MIME types");
}
const overrideReply = await execute(`def display_json(value, indent=2):
    display_code("OVERRIDE:" + str(value), language="text")
__course_helper_overrides["display_json"] = display_json`, {});
const overriddenDisplay = await execute('display_json({"active": True})', {});
if (!overrideReply.ok || overriddenDisplay.displays?.[0]?.type !== "text/x-code"
    || !overriddenDisplay.displays[0].data.startsWith("OVERRIDE:")) {
  throw new Error("Editable helper override did not persist in the Python kernel");
}

console.log(JSON.stringify({
  runtime: `Pyodide ${MANIFEST.runtime.pyodide} / Python ${pyodide.runPython("import platform; platform.python_version()")}`,
  examples: results,
  coverage: [...coverage].sort(),
  stdout: "captured",
  display: "highlight-ready structured objects, JSON, code, Markdown, HTML, and table MIME output",
  helpers: "editable display override persisted",
  background: "registered, completed, inspected, and cancelled named asyncio tasks",
  artifact: "generated JSON preview retained exact downloadable content",
  repl: "namespace and execution counter persisted",
  error: "IndexError surfaced through stderr with source line 2",
}));
