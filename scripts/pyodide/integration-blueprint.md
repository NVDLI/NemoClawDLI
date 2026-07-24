# Pyodide integration notes

The executable guide is [`SKILL.html`](SKILL.html). It downloads the pinned core runtime after the
reader selects Run and executes a scratch REPL plus twelve editable Python cells in a Web Worker.
The REPL and cells share one namespace, use execution counters, highlight Python as it is edited,
render dictionaries and lists as syntax-highlighted JSON without requiring `print()`, render
full-width highlighted code plus sanitized Markdown, HTML, and tables, and mark the source line
reported by Python. An expandable helper menu shows the exact runtime source and lets a student
apply a kernel-local override. The progression covers stdout and stderr, learner
input, chat messages, a local assistant, function calling, MCP descriptors, an agent loop,
named background-task registration, generated-file preview and download, NVIDIA-hosted model
streaming, an optional secure WebSocket round trip, and a stateful chat application.

Its implementation lives under [`examples/`](examples/):

1. [`runtime-loader.js`](examples/runtime-loader.js) loads versioned same-origin assets.
2. [`python-worker.js`](examples/python-worker.js) runs cells off the page thread and returns
   `stdout`, `stderr`, and the final expression as separate fields.
3. [`worker-client.js`](examples/worker-client.js) provides request IDs, timeout, Stop, and Reset.
4. [`network-fetch.js`](examples/network-fetch.js) adds a destination allowlist and optional injected relay.
5. [`learner-cell.py`](examples/learner-cell.py) demonstrates notebook-style returned output.
6. [`cell-examples.js`](examples/cell-examples.js) defines the progressive Python source and coverage labels.
7. [`notebook-editor.js`](examples/notebook-editor.js) owns Python highlighting and keyboard behavior.
8. [`live-playground.js`](examples/live-playground.js) mounts the persistent REPL, CodeMirror editors,
   Jupyter-style prompts and rich display output, NVIDIA SSE and WebSocket transports, keyboard
   execution, Stop, Reset, and run-all behavior.
9. [`execution-contract.js`](examples/execution-contract.js) is the single source for Python execution,
   MIME selection, display helpers, and the editable helper-source registry used by both workers.
10. [`notebook-syntax.js`](examples/notebook-syntax.js) normalizes inspection, timing, namespace,
    virtual-filesystem, package, and bounded browser-shell syntax before Python execution.

[`runtime_smoke.mjs`](runtime_smoke.mjs) verifies exact asset hashes, executes every progressive cell
with real Pyodide, proves persistent state, JSON/code/Markdown/HTML/table/artifact display output,
helper overrides, background task completion and cancellation, captures stdout, and
requires an `IndexError` traceback with its source line through the stderr result.

The repository does not copy Pyodide core, CPython WebAssembly, or Python wheels. This scripts page
fetches its pinned 0.27.7 core runtime only when a reader runs a cell.

## Integration order

Start with the browser-only runtime. Add the HTTP/API package set only when a named lesson requires
outbound requests or an OpenAI-compatible Python client.

| Evaluated use | Includes | Use it for |
|---|---|---|
| Browser-only runtime (`core`) | Pyodide 0.27.7 and CPython 3.12.7 standard library | Python exercises that do not make network requests |
| HTTP/API support (`network`) | Browser-only runtime plus the exact reviewed wheel closure | Optional cookbook HTTP/API examples |

Keep the interpreter in a module worker. The page sends plain source and inputs, then receives a
plain result. Stop terminates the worker. Reset starts a new worker and clears Python globals,
loaded packages, environment values, and pending work.

Do not use unrestricted `micropip.install()` in a shipped lesson. Put every required package in
the reviewed same-origin asset set, component inventory, notices, SBOM, and browser test matrix.

Pyodide follows browser networking rules. Python HTTP adapters do not bypass CORS. The live guide
allows the NVIDIA API and the DLI course relay; its reusable fetch adapter still requires injected
origins and must not contain a deployment URL. NVIDIA model streaming uses HTTP Server-Sent Events.
The separate WebSocket helper accepts only a learner-supplied `wss://` URL and never receives the
NVIDIA API key.

## Runtime acquisition

Acquire assets in a clean directory from the exact version selected for the lesson. Record the npm
lock entry, Pyodide lockfile, selected filenames, hashes, and license files before proposing the
binary assets to the course tree.

```bash
npm install --save-exact pyodide@0.27.7
npm view pyodide@0.27.7 version license dist.integrity repository --json
shasum -a 256 pyodide.mjs pyodide.asm.js pyodide.asm.wasm python_stdlib.zip pyodide-lock.json
unzip -p package.whl '*/METADATA' | sed -n '/^Name:/p;/^Version:/p;/^License/p'
```

For each selected package, verify the filename and SHA-256 from `pyodide-lock.json`, inspect its
wheel metadata and bundled license files, and corroborate the exact upstream version. The candidate
inventory records the evaluated set. OpenSSL 1.1.1w remains a named review item because the Pyodide
recipe label and the exact upstream license do not agree.

## Required implementation checks

- Versioned same-origin assets match the checked manifest hashes.
- License and notice files ship beside the applicable artifacts.
- The generated CycloneDX SBOM matches the built artifact.
- The scratch REPL and notebook cells share a namespace until Stop or Reset replaces the worker.
- CodeMirror highlights Python, wraps long lines, exposes line numbers and a visible theme-aware caret,
  and supports run, comment, and indentation shortcuts in both themes.
- Notebook inspection and magic syntax is shared by the canonical worker and course integrations.
  Browser-shell commands operate only on the Pyodide virtual filesystem; they do not start a host process.
- Shift+Enter runs and advances; Ctrl/Cmd+Enter runs in place.
- Execution counters, automatic final-expression display, stdout, and tracebacks render with notebook prompts.
- Dictionaries and lists render as indented, highlighted JSON; code output keeps its full width and scrolls instead of hard-wrapping.
- `display`, `display_text`, `display_json`, `display_code`, `display_table`, `display_markdown`, `display_html`, and `clear_output` expose an IPython-like display surface.
- The helper dropdown derives source from the execution contract, previews it in CodeMirror, and applies and reverts kernel-local edits.
- Named asyncio tasks can be registered, inspected, awaited, and cancelled across cell executions; Stop and Reset terminate the worker that owns them.
- Generated text artifacts render through a non-executing preview and a Blob download whose bytes are checked against the Python payload.
- Markdown, HTML, tables, and `_repr_*_` output are sanitized before rendering.
- Runtime and syntax exceptions identify and highlight the failing CodeMirror line.
- The NVIDIA route consumes boundary-safe SSE frames incrementally without rendering the key.
- The WebSocket example exposes connecting, open, message, timeout, close, and error behavior.
- Run, Stop, Reset, timeout, output limits, and error rendering work in a real browser.
- `stdout`, `stderr`, and the final expression remain distinct.
- The package profile rejects undeclared packages.
- Network tests cover allowed and rejected destinations, missing configuration, timeout, and cancellation.
- Light and dark modes pass at desktop and narrow widths.
- Chromium, Firefox, and Safari pass the supported course behavior.
- Removing the runtime leaves the existing JavaScript cells working.

The machine-readable state is `human-approval-required`; this document does not approve the
candidate. Changed packages, versions, patches, network destinations, credential flows, or
distribution require refreshed evidence and the applicable human decision.

## Reference scope

The examples synthesize behavior from the task-supplied local reference files
`scripts/vendor-pyodide.mjs`, `src/components/interactive-code/python-worker.ts`,
`src/components/interactive-code/client.ts`, `src/components/interactive-code/proxy-fetch.ts`, and
`src/components/coding-harness-chat.ts`.
No reference source file, runtime binary, wheel, or deployment URL is included here.
