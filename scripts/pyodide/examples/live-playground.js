// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

(function () {
  "use strict";

  const PYODIDE_VERSION = "0.27.7";
  const CDN_BASE = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
  const ERROR_SOURCE = `values = [2, 4, 6]
print("about to read an item that does not exist")
values[99]`;

  const EXECUTE_CELL = globalThis.PYODIDE_EXECUTION_CONTRACT?.source;
  if (!EXECUTE_CELL) throw new Error("Pyodide execution contract failed to load.");

  const WORKER_SOURCE = String.raw`
const BASE_URL = ${JSON.stringify(CDN_BASE)};
let runtimePromise;
let executionCount = 0;
const EXECUTE_CELL = ${JSON.stringify(EXECUTE_CELL)};

async function runtime() {
  if (!runtimePromise) {
    runtimePromise = fetch(BASE_URL + "pyodide.js")
      .then((response) => {
        if (!response.ok) throw new Error("Pyodide loader download failed: " + response.status);
        return response.text();
      })
      .then((source) => {
        (0, eval)(source);
        return self.loadPyodide({ indexURL: BASE_URL });
      })
      .then((pyodide) => {
        pyodide.runPython('__course_scope = {"__name__": "__main__"}');
        return pyodide;
      });
  }
  return runtimePromise;
}

function emitCourseEvent(id, channel, text, detail = {}) {
  self.postMessage({ type: "stream", id, channel, text: String(text || ""), ...detail });
}

self.courseStreamChat = async (requestJson, apiKey, requestId) => {
  const request = JSON.parse(String(requestJson));
  const baseUrl = String(request.base_url || "https://integrate.api.nvidia.com/v1").replace(/\/+$/, "");
  const endpoint = new URL(baseUrl + "/chat/completions");
  const allowedHosts = new Set([
    "integrate.api.nvidia.com",
    "nvidia-api-cors-proxy.experiments.courses.nvidia.com",
  ]);
  if (endpoint.protocol !== "https:" || !allowedHosts.has(endpoint.hostname)) {
    throw new Error("Model streaming is limited to the NVIDIA API and the course relay.");
  }
  emitCourseEvent(requestId, "state", "connecting", { transport: "http-sse" });
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + String(apiKey),
      "Content-Type": "application/json",
      "X-BILLING-INVOKE-ORIGIN": "dli-pyodide-reference",
    },
    body: JSON.stringify({
      model: request.model,
      messages: request.messages,
      temperature: request.temperature ?? 0.1,
      max_tokens: request.max_tokens ?? 512,
      stream: true,
    }),
    credentials: "omit",
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(response.status + ": " + body.slice(0, 400));
  }
  emitCourseEvent(requestId, "state", "streaming", { transport: "http-sse" });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let content = "";
  let reasoning = "";
  let finishReason = null;
  outer: while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data:")) continue;
        const payload = line.slice(5).trim();
        if (payload === "[DONE]") break outer;
        if (!payload) continue;
        const event = JSON.parse(payload);
        const choice = event?.choices?.[0] || {};
        const delta = choice.delta || {};
        if (delta.reasoning_content) {
          reasoning += delta.reasoning_content;
          emitCourseEvent(requestId, "reasoning", delta.reasoning_content, { transport: "http-sse" });
        }
        if (delta.content) {
          content += delta.content;
          emitCourseEvent(requestId, "content", delta.content, { transport: "http-sse" });
        }
        if (choice.finish_reason) finishReason = choice.finish_reason;
      }
    }
  }
  emitCourseEvent(requestId, "state", "complete", { transport: "http-sse" });
  return JSON.stringify({ content, reasoning, finish_reason: finishReason, transport: "http-sse" });
};

self.courseWebSocketRoundTrip = (url, message, requestId, timeoutMs = 8000) => new Promise((resolve, reject) => {
  let endpoint;
  try { endpoint = new URL(String(url)); }
  catch (_) { reject(new Error("WebSocket URL is invalid.")); return; }
  const localAuthoringSocket = endpoint.protocol === "ws:"
    && ["127.0.0.1", "localhost", "::1"].includes(endpoint.hostname);
  if (endpoint.protocol !== "wss:" && !localAuthoringSocket) {
    reject(new Error("WebSocket examples require wss:// (ws:// is accepted only on localhost)."));
    return;
  }
  emitCourseEvent(requestId, "state", "connecting", { transport: "websocket" });
  let settled = false;
  const socket = new WebSocket(endpoint.href);
  const timer = setTimeout(() => finish(new Error("WebSocket timed out before a message arrived.")), Number(timeoutMs));
  const finish = (error, result = null) => {
    if (settled) return;
    settled = true;
    clearTimeout(timer);
    try { socket.close(1000, "course example complete"); } catch (_) {}
    if (error) reject(error);
    else resolve(JSON.stringify(result));
  };
  socket.addEventListener("open", () => {
    emitCourseEvent(requestId, "state", "open", { transport: "websocket" });
    socket.send(String(message));
  });
  socket.addEventListener("message", event => {
    const text = typeof event.data === "string" ? event.data : "[binary message]";
    emitCourseEvent(requestId, "content", text, { transport: "websocket" });
    finish(null, { message: text, transport: "websocket", url: endpoint.href });
  });
  socket.addEventListener("error", () => finish(new Error("WebSocket connection failed.")));
  socket.addEventListener("close", event => {
    if (!settled) finish(new Error("WebSocket closed before a reply (" + event.code + ")."));
  });
});

self.addEventListener("message", async ({ data }) => {
  const { id, source, inputs = {} } = data;
  try {
    const pyodide = await runtime();
    executionCount += 1;
    pyodide.globals.set("__cell_source", source);
    pyodide.globals.set("__cell_inputs", inputs);
    pyodide.globals.set("__execution_count", executionCount);
    pyodide.globals.set("__request_id", id);
    const reply = JSON.parse(String(await pyodide.runPythonAsync(EXECUTE_CELL)));
    self.postMessage({ id, ...reply });
  } catch (error) {
    self.postMessage({
      id,
      ok: false,
      stdout: "",
      stderr: error instanceof Error ? (error.stack || error.message) : String(error),
      value: null,
      display: "",
      has_value: false,
      execution_count: executionCount || null,
      error_line: null,
      error_column: null,
    });
  }
});
`;

  // Exposed for the browser contract test; it contains no credentials or deployment state.
  globalThis.__pyodideWorkerSource = WORKER_SOURCE;

  class BrowserPythonRunner {
    constructor() {
      this.nextId = 1;
      this.pending = new Map();
      this.reset();
    }

    reset() {
      this.worker?.terminate();
      this.rejectAll("Python runtime reset.");
      this.workerUrl && URL.revokeObjectURL(this.workerUrl);
      this.workerUrl = URL.createObjectURL(new Blob([WORKER_SOURCE], { type: "text/javascript" }));
      this.worker = new Worker(this.workerUrl);
      this.worker.addEventListener("message", ({ data }) => this.finish(data));
      this.worker.addEventListener("error", (event) => this.rejectAll(event.message));
    }

    run(source, inputs, onEvent = null) {
      const id = this.nextId++;
      return new Promise((resolve, reject) => {
        this.pending.set(id, { resolve, reject, onEvent });
        this.worker.postMessage({ id, source, inputs });
      });
    }

    stop() {
      this.worker.terminate();
      this.rejectAll("Python execution stopped.");
      this.reset();
    }

    finish(reply) {
      const request = this.pending.get(reply.id);
      if (!request) return;
      if (reply.type === "stream") {
        request.onEvent?.(reply);
        return;
      }
      this.pending.delete(reply.id);
      request.resolve(reply);
    }

    rejectAll(message) {
      for (const request of this.pending.values()) request.reject(new Error(message));
      this.pending.clear();
    }
  }

  const attachPythonEditor = globalThis.PYODIDE_NOTEBOOK_EDITOR?.attach;
  if (typeof attachPythonEditor !== "function") throw new Error("Pyodide notebook editor failed to load.");

  const RICH_TAGS = new Set([
    "A", "BLOCKQUOTE", "BR", "CODE", "DEL", "DIV", "EM", "H1", "H2", "H3", "H4",
    "HR", "KBD", "LI", "OL", "P", "PRE", "S", "SPAN", "STRONG", "TABLE", "TBODY",
    "TD", "TH", "THEAD", "TR", "UL",
  ]);
  const BLOCKED_RICH_TAGS = new Set(["BASE", "EMBED", "IFRAME", "IMG", "LINK", "META", "OBJECT", "SCRIPT", "STYLE"]);

  function safeHref(raw) {
    try {
      const url = new URL(raw, location.href);
      return ["http:", "https:", "mailto:"].includes(url.protocol) ? url.href : null;
    } catch (_) {
      return null;
    }
  }

  function fallbackMarkdown(source) {
    const escape = text => String(text)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    const inline = text => escape(text)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>");
    return String(source).trim().split(/\n{2,}/).map(block => {
      const heading = block.match(/^(#{1,4})\s+([\s\S]+)$/);
      if (heading) return `<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`;
      return `<p>${inline(block).replace(/\n/g, "<br>")}</p>`;
    }).join("");
  }

  function sanitizeRichOutput(source, type) {
    const markdownParser = globalThis.marked?.parse || globalThis.marked;
    const html = type === "text/markdown" && typeof markdownParser === "function"
      ? markdownParser(String(source), { gfm: true, breaks: false })
      : type === "text/markdown" ? fallbackMarkdown(source) : String(source);
    const inert = document.createElement("template");
    inert.innerHTML = html;
    const fragment = document.createDocumentFragment();
    const copy = (node, parent) => {
      if (node.nodeType === Node.TEXT_NODE) {
        parent.append(document.createTextNode(node.textContent || ""));
        return;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return;
      if (!RICH_TAGS.has(node.tagName)) {
        if (BLOCKED_RICH_TAGS.has(node.tagName)) return;
        for (const child of node.childNodes) copy(child, parent);
        return;
      }
      const clean = document.createElement(node.tagName.toLowerCase());
      if (node.tagName === "A") {
        const href = safeHref(node.getAttribute("href") || "");
        if (href) {
          clean.href = href;
          clean.target = "_blank";
          clean.rel = "noopener noreferrer";
        }
      }
      for (const child of node.childNodes) copy(child, clean);
      parent.append(clean);
    };
    for (const child of inert.content.childNodes) copy(child, fragment);
    return fragment;
  }

  function mount() {
    const root = document.getElementById("pyodide-playground");
    if (!root) return;
    const examples = globalThis.PYODIDE_CELL_EXAMPLES || [];
    const list = root.querySelector("[data-python-cells]");
    const status = root.querySelector("[data-python-status]");
    const diagnostic = root.querySelector("[data-python-diagnostic]");
    const replSource = root.querySelector("[data-repl-source]");
    const replPrompt = root.querySelector("[data-repl-prompt]");
    const replTranscript = root.querySelector("[data-repl-transcript]");
    const helperRows = root.querySelector("[data-helper-rows]");
    const apiKey = root.querySelector("[data-nvidia-api-key]");
    const baseUrl = root.querySelector("[data-model-base-url]");
    const model = root.querySelector("[data-model-id]");
    const websocketUrl = root.querySelector("[data-websocket-url]");
    const liveEnabled = root.querySelector("[data-live-model-enabled]");
    let runner = new BrowserPythonRunner();
    let replEditor;
    const cells = new Map();
    const artifactUrls = new Set();
    const helperEditors = new Map();
    const helperDocs = new Map((globalThis.PYODIDE_EXECUTION_CONTRACT?.helpers || []).map(item => [item.name, item]));

    const setStatus = (text, state = "") => {
      status.textContent = text;
      status.dataset.state = state;
      root.dispatchEvent(new CustomEvent("pyodide:status", { detail: { text, state } }));
    };
    const setBusy = (busy) => {
      root.querySelectorAll("button").forEach((button) => {
        if (button.dataset.action === "stop" || button.matches("[data-workbench-view], [data-workbench-close]")) return;
        button.disabled = busy;
      });
    };

    function clearCell(cell) {
      cell.editor?.clearError();
      cell.inputPrompt.textContent = "In [ ]:";
      cell.output.querySelectorAll("[data-artifact-url]").forEach(node => {
        URL.revokeObjectURL(node.dataset.artifactUrl);
        artifactUrls.delete(node.dataset.artifactUrl);
      });
      cell.output.replaceChildren();
      cell.output.dataset.state = "empty";
      const empty = document.createElement("p");
      empty.className = "wb-cell-empty";
      empty.textContent = "Run this cell to see its value, streams, generated artifact, or traceback.";
      cell.output.append(empty);
      cell.lastReply = null;
      cell.status.textContent = "Ready";
      cell.status.dataset.state = "ready";
      cell.section.dataset.state = "ready";
      cell.section.setAttribute("aria-busy", "false");
    }

    function makeDisplayNode(text, displayType = "text/plain", language = "") {
      if (displayType === "text/plain") {
        const output = document.createElement("pre");
        output.textContent = text;
        return output;
      }
      if (displayType === "application/x-course-artifact+json") {
        const payload = JSON.parse(text);
        const card = document.createElement("article");
        card.className = "py-artifact-output";
        card.dataset.artifactFilename = payload.filename;
        const header = document.createElement("header");
        const filename = document.createElement("code");
        filename.textContent = payload.filename;
        const mime = document.createElement("span");
        mime.textContent = payload.mime_type;
        const download = document.createElement("a");
        const url = URL.createObjectURL(new Blob([payload.content], { type: payload.mime_type }));
        artifactUrls.add(url);
        download.href = url;
        download.download = payload.filename;
        download.textContent = "Download artifact";
        download.dataset.artifactUrl = url;
        header.append(filename, mime, download);
        let previewType = "text/plain";
        let previewLanguage = payload.language || "";
        if (payload.mime_type === "application/json") previewType = "application/json";
        else if (payload.mime_type === "text/markdown" || payload.mime_type === "text/html") previewType = payload.mime_type;
        else if (payload.language || /(?:javascript|python|css|shell|x-sh)$/i.test(payload.mime_type)) previewType = "text/x-code";
        const preview = makeDisplayNode(payload.content, previewType, previewLanguage);
        preview.classList.add("py-artifact-preview");
        card.append(header, preview);
        return card;
      }
      if (displayType === "application/json" || displayType === "text/x-code") {
        const output = document.createElement("pre");
        output.className = "py-syntax-output";
        output.dataset.mime = displayType;
        const code = document.createElement("code");
        const selectedLanguage = /^[a-z0-9_+-]{1,32}$/i.test(language)
          ? language.toLowerCase()
          : displayType === "application/json" ? "json" : "plaintext";
        code.className = `language-${selectedLanguage}`;
        code.textContent = text;
        output.append(code);
        if (globalThis.hljs?.getLanguage(selectedLanguage)) globalThis.hljs.highlightElement(code);
        return output;
      }
      const output = document.createElement("div");
      output.className = "py-rich-output";
      output.dataset.mime = displayType;
      output.append(sanitizeRichOutput(text, displayType));
      return output;
    }

    function appendOutput(container, { prompt = "", text = "", stream = "display", displayType = "text/plain", language = "" }) {
      if (!text) return;
      const row = document.createElement("div");
      row.className = "py-output-row";
      row.dataset.stream = stream;
      const label = document.createElement("span");
      label.className = "py-cell-prompt";
      label.textContent = prompt;
      const output = makeDisplayNode(text, displayType, language);
      if (stream === "stdout") output.dataset.stdoutFor = container.dataset.outputFor;
      if (stream === "display") output.dataset.valueFor = container.dataset.outputFor;
      if (stream === "stderr") output.dataset.stderrFor = container.dataset.outputFor;
      row.append(label, output);
      container.append(row);
    }

    function renderReply(cell, reply) {
      const count = reply.execution_count ?? " ";
      cell.inputPrompt.textContent = `In [${count}]:`;
      cell.output.querySelectorAll("[data-artifact-url]").forEach(node => {
        URL.revokeObjectURL(node.dataset.artifactUrl);
        artifactUrls.delete(node.dataset.artifactUrl);
      });
      cell.output.replaceChildren();
      cell.output.dataset.state = "rendered";
      cell.editor.clearError();
      appendOutput(cell.output, { text: reply.stdout, stream: "stdout" });
      for (const display of reply.displays || []) {
        appendOutput(cell.output, { text: display.data, stream: "display", displayType: display.type, language: display.language });
      }
      if (reply.has_value) {
        appendOutput(cell.output, {
          prompt: `Out[${count}]:`, text: reply.display || String(reply.value), stream: "display",
          displayType: reply.display_type || "text/plain", language: reply.display_language,
        });
      }
      appendOutput(cell.output, { prompt: reply.ok ? "" : "Error:", text: reply.stderr, stream: "stderr" });
      if (!reply.ok) cell.editor.showError(reply.error_line, reply.error_column);
    }

    function renderStreamEvent(cell, event) {
      let row = cell.output.querySelector(`[data-live-channel="${event.channel}"]`);
      if (!row) {
        cell.output.dataset.state = "streaming";
        row = document.createElement("div");
        row.className = "py-output-row py-live-stream";
        row.dataset.liveChannel = event.channel;
        const label = document.createElement("span");
        label.className = "py-cell-prompt";
        label.textContent = event.channel === "reasoning" ? "Think:" : event.channel === "state" ? "Net:" : "Live:";
        const pre = document.createElement("pre");
        row.append(label, pre);
        cell.output.append(row);
      }
      const pre = row.querySelector("pre");
      if (event.channel === "state") pre.textContent = `${event.transport || "network"}: ${event.text}`;
      else pre.textContent += event.text;
    }

    function appendReplEntry(prompt, text, stream, displayType = "text/plain", language = "") {
      if (!text) return;
      const entry = document.createElement("div");
      entry.className = "py-repl-entry";
      entry.dataset.stream = stream;
      const label = document.createElement("span");
      label.className = "py-cell-prompt";
      label.textContent = prompt;
      const output = makeDisplayNode(text, displayType, language);
      entry.append(label, output);
      replTranscript.append(entry);
    }

    function mountHelperMenu() {
      for (const helper of helperDocs.values()) {
        const row = document.createElement("tr");
        row.className = "py-helper-row";
        row.dataset.helperRow = helper.name;
        const signature = document.createElement("td");
        const code = document.createElement("code");
        code.textContent = helper.signature;
        signature.append(code);
        const description = document.createElement("td");
        description.textContent = helper.description;
        row.append(signature, description);

        const sourceRow = document.createElement("tr");
        sourceRow.className = "py-helper-source";
        sourceRow.dataset.helperSource = helper.name;
        sourceRow.hidden = true;
        const sourceCell = document.createElement("td");
        sourceCell.colSpan = 2;
        const sourceHead = document.createElement("div");
        sourceHead.className = "py-helper-source-head";
        sourceHead.append("source · ");
        const name = document.createElement("code");
        name.textContent = helper.name;
        sourceHead.append(name);
        for (const [label, action] of [["apply override", "helperApply"], ["load in REPL", "helperLoad"], ["copy", "helperCopy"], ["revert", "helperRevert"]]) {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = label;
          button.dataset[action] = helper.name;
          sourceHead.append(button);
        }
        const helperStatus = document.createElement("span");
        helperStatus.className = "py-helper-status";
        helperStatus.dataset.helperStatus = helper.name;
        sourceHead.append(helperStatus);
        const textarea = document.createElement("textarea");
        textarea.className = "py-helper-editor";
        textarea.dataset.helperEditor = helper.name;
        textarea.spellcheck = false;
        textarea.value = helper.source;
        sourceCell.append(sourceHead, textarea);
        sourceRow.append(sourceCell);
        helperRows.append(row, sourceRow);
      }

      helperRows.addEventListener("click", event => {
        if (event.target.closest("button")) return;
        const row = event.target.closest("[data-helper-row]");
        if (!row) return;
        const selected = row.dataset.helperRow;
        const sourceRow = helperRows.querySelector(`[data-helper-source="${selected}"]`);
        const wasOpen = !sourceRow.hidden;
        helperRows.querySelectorAll("[data-helper-source]").forEach(item => { item.hidden = true; });
        helperRows.querySelectorAll("[data-helper-row]").forEach(item => item.classList.remove("selected"));
        if (wasOpen) return;
        sourceRow.hidden = false;
        row.classList.add("selected");
        if (!helperEditors.has(selected)) {
          const textarea = sourceRow.querySelector("textarea");
          const editor = globalThis.CodeMirror?.fromTextArea
            ? globalThis.CodeMirror.fromTextArea(textarea, {
                mode: "course-python", lineNumbers: true, lineWrapping: false,
                indentUnit: 4, tabSize: 4, indentWithTabs: false,
              })
            : { getValue: () => textarea.value, setValue: value => { textarea.value = value; }, focus: () => textarea.focus() };
          helperEditors.set(selected, editor);
        }
      });
    }

    const helperSource = name => helperEditors.get(name)?.getValue() || helperDocs.get(name)?.source || "";
    const setHelperStatus = (name, text, state = "") => {
      const node = root.querySelector(`[data-helper-status="${name}"]`);
      if (node) { node.textContent = text; node.dataset.state = state; }
    };
    async function applyHelper(name) {
      setBusy(true);
      setHelperStatus(name, "applying…");
      const source = helperSource(name);
      const registration = `\n__course_helper_overrides[${JSON.stringify(name)}] = ${name}`;
      const reply = await runner.run(source + registration, {});
      setHelperStatus(name, reply.ok ? "active for this kernel" : `error on line ${reply.error_line || "?"}`, reply.ok ? "ok" : "error");
      if (!reply.ok) {
        appendReplEntry("Helper:", reply.stderr, "error");
        replEditor.setValue(source);
        replEditor.showError(reply.error_line, reply.error_column);
      }
      setBusy(false);
      return reply;
    }

    async function revertHelper(name) {
      setBusy(true);
      const reply = await runner.run(`__course_helper_overrides.pop(${JSON.stringify(name)}, None)\nNone`, {});
      helperEditors.get(name)?.setValue(helperDocs.get(name).source);
      setHelperStatus(name, reply.ok ? "restored default" : "revert failed", reply.ok ? "ok" : "error");
      setBusy(false);
    }

    async function runRepl() {
      const source = replEditor.getValue();
      if (!source.trim()) return null;
      setBusy(true);
      replPrompt.textContent = "In [*]:";
      setStatus("Running the scratch REPL…", "running");
      try {
        replEditor.clearError();
        const reply = await runner.run(source, {
          api_key: "", base_url: baseUrl.value, model: model.value,
          websocket_url: websocketUrl.value.trim(),
        }, event => appendReplEntry(event.channel === "state" ? "Net:" : "Live:", event.text, event.channel));
        const count = reply.execution_count ?? " ";
        replPrompt.textContent = `In [${count}]:`;
        appendReplEntry(`In [${count}]:`, source, "input");
        appendReplEntry("", reply.stdout, "stdout");
        for (const display of reply.displays || []) {
          appendReplEntry("Display:", display.data, "display", display.type, display.language);
        }
        if (reply.has_value) {
          appendReplEntry(`Out[${count}]:`, reply.display || String(reply.value), "display", reply.display_type || "text/plain", reply.display_language);
        }
        appendReplEntry(reply.ok ? "" : "Error:", reply.stderr, "error");
        if (!reply.ok) replEditor.showError(reply.error_line, reply.error_column);
        setStatus(reply.ok ? "Scratch REPL finished; kernel state was preserved." : "Scratch REPL raised an exception.", reply.ok ? "ok" : "error");
        return reply;
      } catch (error) {
        appendReplEntry("Error:", error instanceof Error ? error.message : String(error), "error");
        setStatus("Scratch REPL did not finish.", "error");
        return { ok: false };
      } finally {
        setBusy(false);
      }
    }

    function renderChat(cell) {
      if (!cell.transcript) return;
      cell.transcript.replaceChildren();
      if (!cell.history.length) {
        const empty = document.createElement("p");
        empty.className = "py-chat-empty";
        empty.textContent = "No messages yet. Write a message below and send it to Python.";
        cell.transcript.append(empty);
        return;
      }
      for (const message of cell.history) {
        const bubble = document.createElement("article");
        bubble.className = "py-chat-message";
        bubble.dataset.role = message.role;
        const role = document.createElement("strong");
        role.textContent = message.role;
        const content = document.createElement("p");
        content.textContent = message.content;
        bubble.append(role, content);
        cell.transcript.append(bubble);
      }
    }

    function createCell(example) {
      const section = document.createElement("section");
      section.className = "py-example wb-cell";
      section.dataset.exampleId = example.id;

      const heading = document.createElement("header");
      heading.className = "py-example-heading";
      const headingCopy = document.createElement("div");
      headingCopy.className = "wb-cell-heading";
      const title = document.createElement("h3");
      title.textContent = example.title;
      const purpose = document.createElement("p");
      purpose.textContent = example.purpose;
      const tags = document.createElement("div");
      tags.className = "py-coverage-tags";
      for (const item of example.coverage) {
        const tag = document.createElement("span");
        tag.textContent = item;
        tags.append(tag);
      }
      headingCopy.append(title, purpose, tags);
      heading.append(headingCopy);

      let transcript = null;
      if (example.chat) {
        transcript = document.createElement("div");
        transcript.className = "py-chat-transcript";
        transcript.dataset.chatTranscript = example.id;
        transcript.setAttribute("aria-live", "polite");
      }

      const inputLabel = document.createElement("label");
      inputLabel.className = "py-input-label";
      inputLabel.textContent = example.chat ? "Your next chat message" : "Input passed to Python";
      const input = document.createElement("input");
      input.type = "text";
      input.value = example.input;
      input.dataset.exampleInput = example.id;
      inputLabel.append(input);

      const editorLabel = document.createElement("label");
      editorLabel.className = "py-editor-label";
      editorLabel.setAttribute("aria-label", `Editable Python for ${example.title}`);
      const editor = document.createElement("textarea");
      editor.value = example.source;
      editor.spellcheck = false;
      editor.setAttribute("aria-label", `Editable Python for ${example.title}`);
      editor.dataset.exampleSource = example.id;
      editorLabel.append(editor);
      const editorShell = document.createElement("div");
      editorShell.className = "py-editor-shell";
      const inputPrompt = document.createElement("span");
      inputPrompt.className = "py-cell-prompt";
      inputPrompt.textContent = "In [ ]:";
      editorShell.append(inputPrompt, editorLabel);

      const actions = document.createElement("div");
      actions.className = "py-example-actions";
      const run = document.createElement("button");
      run.type = "button";
      run.dataset.runExample = example.id;
      run.textContent = example.chat ? "Send to Python" : "Run cell";
      if (example.chat) {
        input.addEventListener("keydown", (event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
            event.preventDefault();
            run.click();
          }
        });
      }
      const reset = document.createElement("button");
      reset.type = "button";
      reset.dataset.resetExample = example.id;
      reset.textContent = "Restore code";
      const cellStatus = document.createElement("span");
      cellStatus.className = "py-cell-status";
      cellStatus.dataset.cellStatus = example.id;
      actions.append(run, reset, cellStatus);

      const output = document.createElement("div");
      output.className = "py-notebook-output";
      output.dataset.outputFor = example.id;
      output.setAttribute("aria-live", "polite");

      const workspace = document.createElement("div");
      workspace.className = "wb-cell-workspace";
      const sourcePane = document.createElement("section");
      sourcePane.className = "wb-cell-source";
      const sourceLabel = document.createElement("div");
      sourceLabel.className = "wb-cell-pane-label";
      sourceLabel.textContent = "Editable Python";
      sourcePane.append(sourceLabel, inputLabel, editorShell, actions);
      const artifactPane = document.createElement("section");
      artifactPane.className = "wb-cell-artifact";
      const artifactLabel = document.createElement("div");
      artifactLabel.className = "wb-cell-pane-label";
      artifactLabel.textContent = "Result and evidence";
      artifactPane.append(artifactLabel);
      if (transcript) artifactPane.append(transcript);
      artifactPane.append(output);
      workspace.append(sourcePane, artifactPane);
      section.append(heading, workspace);
      list.append(section);
      const cell = { example, section, input, editor: null, inputPrompt, output, status: cellStatus, transcript, history: [] };
      cells.set(example.id, cell);
      cell.editor = attachPythonEditor(editor, {
        run: () => execute(cell),
        runNext: async () => {
          await execute(cell);
          const index = examples.findIndex((item) => item.id === example.id);
          const next = cells.get(examples[index + 1]?.id);
          (next?.editor || cell.editor).focus();
        },
      });
      clearCell(cell);
      renderChat(cell);
    }

    async function execute(cell, manageBusy = true) {
      clearCell(cell);
      if (manageBusy) setBusy(true);
      cell.inputPrompt.textContent = "In [*]:";
      cell.status.textContent = "Running…";
      cell.status.dataset.state = "running";
      cell.section.dataset.state = "running";
      cell.section.setAttribute("aria-busy", "true");
      setStatus(`Running ${cell.example.title} with Pyodide ${PYODIDE_VERSION}…`, "running");
      try {
        const reply = await runner.run(cell.editor.getValue(), {
          user_input: cell.input.value,
          history: cell.history,
          base_url: baseUrl.value,
          model: model.value,
          api_key: cell.example.id === "chat-app" && liveEnabled.checked ? apiKey.value.trim() : "",
          websocket_url: websocketUrl.value.trim(),
        }, event => renderStreamEvent(cell, event));
        cell.lastReply = reply;
        renderReply(cell, reply);
        if (reply.ok && cell.example.chat && Array.isArray(reply.value?.history)) {
          cell.history = reply.value.history;
          cell.input.value = "";
          renderChat(cell);
        }
        cell.status.textContent = reply.ok ? "Passed" : "Python error";
        cell.status.dataset.state = reply.ok ? "ok" : "error";
        cell.section.dataset.state = reply.ok ? "passed" : "failed";
        setStatus(reply.ok ? `${cell.example.title} finished.` : `${cell.example.title} raised an exception.`, reply.ok ? "ok" : "error");
        return reply;
      } catch (error) {
        renderReply(cell, {
          ok: false,
          stdout: "",
          stderr: error instanceof Error ? error.message : String(error),
          has_value: false,
          execution_count: null,
        });
        cell.status.textContent = "Runtime error";
        cell.status.dataset.state = "error";
        cell.section.dataset.state = "failed";
        setStatus("Python did not finish.", "error");
        return { ok: false };
      } finally {
        cell.section.setAttribute("aria-busy", "false");
        if (manageBusy) setBusy(false);
      }
    }

    async function runAll() {
      setBusy(true);
      let passed = 0;
      for (const cell of cells.values()) {
        const reply = await execute(cell, false);
        if (reply.ok) passed += 1;
      }
      setBusy(false);
      diagnostic.textContent = `${passed}/${cells.size} progressive Python cells completed.`;
      setStatus(passed === cells.size ? "Every progressive cell passed." : "One or more cells failed.", passed === cells.size ? "ok" : "error");
      return passed;
    }

    root.addEventListener("click", async ({ target }) => {
      const button = target.closest("button");
      const action = button?.dataset.action;
      const runId = button?.dataset.runExample;
      const resetId = button?.dataset.resetExample;
      const applyName = button?.dataset.helperApply;
      const loadName = button?.dataset.helperLoad;
      const copyName = button?.dataset.helperCopy;
      const revertName = button?.dataset.helperRevert;
      if (applyName) await applyHelper(applyName);
      if (loadName) {
        replEditor.setValue(helperSource(loadName));
        replEditor.focus();
        setHelperStatus(loadName, "copied to scratch REPL", "ok");
      }
      if (copyName) {
        try {
          await copyText(helperSource(copyName));
          setHelperStatus(copyName, "copied", "ok");
        } catch (error) {
          setHelperStatus(copyName, "copy failed", "error");
        }
      }
      if (revertName) await revertHelper(revertName);
      if (runId) await execute(cells.get(runId));
      if (resetId) {
        const cell = cells.get(resetId);
        cell.editor.setValue(cell.example.source);
        cell.input.value = cell.example.input;
        cell.history = [];
        clearCell(cell);
        renderChat(cell);
      }
      if (action === "run-all") await runAll();
      if (action === "run-repl") await runRepl();
      if (action === "clear-repl") {
        replTranscript.replaceChildren();
        replPrompt.textContent = "In [ ]:";
        replEditor.clearError();
        replEditor.focus();
      }
      if (action === "error") {
        replEditor.setValue(ERROR_SOURCE);
        const reply = await runRepl();
        diagnostic.textContent = reply?.stderr || "Expected an error, but stderr was empty.";
        setStatus(reply?.ok ? "The intentional error did not fail." : `Python traceback surfaced; line ${reply?.error_line || "?"} is highlighted.`, reply?.ok ? "error" : "ok");
      }
      if (action === "stop") {
        runner.stop();
        setBusy(false);
        replEditor.clearError();
        replPrompt.textContent = "In [ ]:";
        appendReplEntry("Kernel:", "Execution stopped. The replacement kernel has an empty namespace.", "error");
        setStatus("Python stopped. The next run starts a clean interpreter.", "stopped");
      }
      if (action === "reset") {
        runner.reset();
        replTranscript.replaceChildren();
        replPrompt.textContent = "In [ ]:";
        replEditor.clearError();
        replEditor.setValue('course_topic = "browser Python"\ncourse_topic.upper()');
        for (const cell of cells.values()) {
          cell.editor.setValue(cell.example.source);
          cell.input.value = cell.example.input;
          cell.history = [];
          clearCell(cell);
          renderChat(cell);
        }
        for (const url of artifactUrls) URL.revokeObjectURL(url);
        artifactUrls.clear();
        diagnostic.textContent = "Runtime and all cell state cleared.";
        root.querySelectorAll("[data-helper-status]").forEach(node => { node.textContent = ""; node.dataset.state = ""; });
        setStatus("Runtime reset. Ready to run.", "ready");
      }
    });

    replEditor = attachPythonEditor(replSource, {
      run: () => runRepl(),
      runNext: async () => {
        await runRepl();
        replEditor.setValue("");
        replEditor.focus();
      },
    });
    try { apiKey.value = sessionStorage.getItem("nvapi") || ""; } catch (_) {}
    mountHelperMenu();
    for (const example of examples) createCell(example);
    diagnostic.textContent = `${examples.length} cells loaded; none have run yet.`;
    setStatus("Ready. The first run downloads the pinned Pyodide runtime.", "ready");
    root.dataset.runtimeMounted = "true";
    root.dataset.exampleCount = String(examples.length);
    globalThis.__pyodidePlayground = { runAll, runRepl, applyHelper, revertHelper, cells, replEditor, helperEditors, runtime: PYODIDE_VERSION };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else {
    mount();
  }
})();
