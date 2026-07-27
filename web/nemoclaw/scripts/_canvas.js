// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Interactive-cell runtime: mountCanvasFlow, mountRunCell, the helper-menu builders, error/log.
// Leaf module: it imports the registries and primitives from _shared.js but references them only inside function bodies, so the import cycle stays load-safe.
import { HELPER_FNS, REASONING_MODEL, SPECIALS, VIZ_BUILDERS, _labOnlyService, _stepLabOnly, browserChatFetch, chat, chatStream, contextWindow, cosineSim, coursePage, coursePages, diagramSVG, embed, estimateTokens, evalSandboxFs, evalSandboxNetwork, fetchRetry, formatSearchResults, ganttBarsSVG, getConfig, getKey, instantAnswer, mountAgentChat, mountChatUI, mountKeyPanel, openclawChat, sandboxExec, terminal, webSearch, wireFigureZoom } from "./_shared.js";
import { makeViz } from "./_viz.js";

// ── Cmd-/ · Ctrl-/ : toggle `// ` line comments on the selection ─────────────────
// The page loads CodeMirror core and the javascript mode but not the comment addon, so this fills in the toggle: comment the selected lines unless all are already commented, else uncomment.
function _cmCommentToggle(cm) {
  cm.operation(() => {
    for (const r of cm.listSelections()) {
      const from = Math.min(r.anchor.line, r.head.line);
      const to = Math.max(r.anchor.line, r.head.line);
      let allCommented = true;
      for (let l = from; l <= to; l++) {
        const t = cm.getLine(l);
        if (t.trim() && !/^\s*\/\//.test(t)) { allCommented = false; break; }
      }
      for (let l = from; l <= to; l++) {
        const t = cm.getLine(l);
        if (!t.trim()) continue;
        if (allCommented) {
          const m = t.match(/^(\s*)\/\/ ?/);
          if (m) cm.replaceRange(m[1], { line: l, ch: 0 }, { line: l, ch: m[0].length });
        } else {
          const indent = t.match(/^\s*/)[0];
          cm.replaceRange(indent + "// ", { line: l, ch: 0 }, { line: l, ch: indent.length });
        }
      }
    }
  });
}

// ── Error-line helpers (used by mountCanvasFlow + mountRunCell) ──────────────────
// V8 splits the new Function header across two lines, so user code starts at stack line 4 (2 header, 1 body-wrapper, user line 1).
// CodeMirror is 0-indexed, hence cmLine = stackLine - 4.
function _parseErrLine(e) {
  if (!e || !e.stack) return null;
  for (const row of e.stack.split("\n")) {
    let m = row.match(/<anonymous>:(\d+):(\d+)/);
    if (!m) m = row.match(/@[^@\n]*:(\d+):(\d+)\s*$/);
    if (m) {
      return { cmLine: Math.max(0, parseInt(m[1]) - 4), cmCol: Math.max(0, parseInt(m[2]) - 1) };
    }
  }
  return null;
}

function _markCMErr(cm, ep) {
  const safeL = Math.min(ep.cmLine, Math.max(0, cm.lineCount() - 1));
  const marker = cm.getWrapperElement().ownerDocument.createElement("span");
  marker.className = "cm-err-gutter";
  marker.title = "Error at line " + (safeL + 1);
  cm.setGutterMarker(safeL, "CodeMirror-linenumbers", marker);
  cm.addLineClass(safeL, "background", "cm-err-line");
  cm.addLineClass(safeL, "wrap", "cm-err-wrap");
  if (!cm._errLines) cm._errLines = [];
  cm._errLines.push(safeL);
  cm.scrollIntoView({ line: safeL, ch: 0 }, 100);
}

function _clearCMErrs(cm) {
  if (!cm || !cm._errLines) return;
  for (const ln of cm._errLines) {
    try {
      cm.setGutterMarker(ln, "CodeMirror-linenumbers", null);
      cm.removeLineClass(ln, "background", "cm-err-line");
      cm.removeLineClass(ln, "wrap", "cm-err-wrap");
    } catch (_) { /**/ }
  }
  cm._errLines = [];
}

function _buildDebugDet(e, code, ep) {
  const _e = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const det = document.createElement("details");
  det.className = "cf-debug-det";
  const sum = document.createElement("summary");
  sum.className = "cf-debug-sum";
  sum.textContent = "Debug info";
  det.appendChild(sum);
  const msg = document.createElement("div");
  msg.className = "cf-debug-type";
  msg.textContent = (e.name || "Error") + ": " + e.message;
  det.appendChild(msg);

  if (ep !== null && code) {
    const lines = code.split("\n");
    const li = ep.cmLine;
    const from = Math.max(0, li - 1);
    const to   = Math.min(lines.length - 1, li + 1);
    const snip = document.createElement("div");
    snip.className = "cf-debug-snippet";
    for (let i = from; i <= to; i++) {
      const row = document.createElement("div");
      row.className = "cf-debug-codeline" + (i === li ? " cf-debug-codeline-err" : "");
      const num = document.createElement("span");
      num.className = "cf-debug-lineno";
      num.textContent = String(i + 1);
      const src = document.createElement("code");
      src.textContent = lines[i] || "";
      row.appendChild(num); row.appendChild(src);
      snip.appendChild(row);
    }
    det.appendChild(snip);
  }

  if (e.stack) {
    const filtered = e.stack.split("\n")
      .filter(l => l.trim() && !l.includes("_shared.js") && !l.includes("at async Function."))
      .slice(0, 6).join("\n");
    const st = document.createElement("pre");
    st.className = "cf-debug-stack";
    st.textContent = filtered || e.stack.split("\n").slice(0, 5).join("\n");
    det.appendChild(st);
  }
  return det;
}


// ── Shared cell shell/rendering primitives (CanvasFlow + RunCell) ─────────────
// Retain rc/cf selectors for tests and Studio automation.
// Route learner controls, labels, and output through one renderer.
const CELL_CANVAS_VISIBLE_LINES = 39;

function _cellBtnHTML(kind, text, extraClass = "", title = "") {
  const tone = kind === "run" ? " cell-btn-run"
             : kind === "reset" ? " cell-btn-reset"
             : "";
  const safeTitle = title ? ` title="${escapeHtml(title)}"` : "";
  return `<button type="button" class="cell-btn${tone}${extraClass ? " " + extraClass : ""}"${safeTitle}>${escapeHtml(text)}</button>`;
}

function _cellLangSummaryHTML({ chip = "JS", sig = "", meta = "", metaAttr = "" } = {}) {
  return `<summary>
    <span class="cf-det-chip cell-lang-chip" data-lang-chip>${escapeHtml(chip)}</span>
    ${sig ? `<span class="cf-det-sig">${sig}</span>` : ""}
    ${meta ? `<span class="cf-det-meta" ${metaAttr}>${escapeHtml(meta)}</span>` : ""}
  </summary>`;
}

function _cellCodeOpen(opts = {}, code = "", kind = "run") {
  if (opts.openCode === true || opts.showCode === true) return true;
  if (opts.openCode === false || opts.showCode === false) return false;
  if (kind !== "canvas") return false;
  const lines = Math.max(1, String(code || "").split("\n").length);
  return lines <= CELL_CANVAS_VISIBLE_LINES;
}

function _cellHighlight(codeEl) {
  if (typeof window !== "undefined" && typeof window.hljs !== "undefined") {
    try { window.hljs.highlightElement(codeEl); } catch (_) {}
  }
}

function _appendCellJson(host, value, label = null, cls = "cell-log-json") {
  if (label) _appendCellHeading(host, label);
  const pre = document.createElement("pre");
  pre.className = cls;
  const code = document.createElement("code");
  code.className = "language-json hljs";
  code.textContent = JSON.stringify(value, null, 2);
  pre.appendChild(code);
  host.appendChild(pre);
  _cellHighlight(code);
  return pre;
}

function _appendCellText(host, text, cls = "cell-log-line", color = "") {
  const div = document.createElement("div");
  div.className = cls;
  if (color) div.style.color = color;
  div.textContent = String(text);
  host.appendChild(div);
  return div;
}

function _appendCellHeading(host, title) {
  const div = document.createElement("div");
  div.className = "cell-log-heading";
  div.textContent = String(title);
  host.appendChild(div);
  return div;
}

function _appendCellDetails(host, summary, body, cls = "cell-log-details") {
  const det = document.createElement("details");
  det.className = cls;
  const sum = document.createElement("summary");
  sum.textContent = String(summary);
  det.appendChild(sum);
  const inner = document.createElement("div");
  inner.className = "cell-log-details-body";
  if (body && typeof body === "object") {
    const pre = document.createElement("pre");
    pre.className = "cell-log-json";
    const code = document.createElement("code");
    code.className = "language-json hljs";
    code.textContent = JSON.stringify(body, null, 2);
    pre.appendChild(code);
    inner.appendChild(pre);
    det.appendChild(inner);
    host.appendChild(det);
    _cellHighlight(code);
  } else {
    inner.textContent = String(body);
    det.appendChild(inner);
    host.appendChild(det);
  }
  return det;
}

function _appendCellKv(host, obj) {
  const div = document.createElement("div");
  div.className = "cell-log-kv";
  for (const [k, v] of Object.entries(obj || {})) {
    const pair = document.createElement("span");
    const key = document.createElement("span");
    key.className = "cell-log-kv-key";
    key.textContent = k + ":";
    const val = document.createElement("span");
    val.className = "cell-log-kv-val";
    val.textContent = typeof v === "object" ? JSON.stringify(v) : String(v);
    pair.appendChild(key);
    pair.appendChild(document.createTextNode(" "));
    pair.appendChild(val);
    div.appendChild(pair);
  }
  host.appendChild(div);
  return div;
}

function _appendCellHtml(host, html, cls = "cell-log-html") {
  const div = document.createElement("div");
  div.className = cls;
  div.innerHTML = String(html);
  div.querySelectorAll("svg.dg-svg").forEach(svg => wireFigureZoom(svg));
  host.appendChild(div);
  return div;
}

function _appendCellReturn(host, val, cls = "cf-panel-output-pre") {
  if (val !== null && (typeof val === "object" || typeof val === "boolean" || typeof val === "number")) {
    return _appendCellJson(host, val, null, cls);
  }
  return _appendCellText(host, String(val), cls);
}

function _installStructuredLog(log, host, onAppend = () => {}, svgFn = null) {
  log.h = (title) => { const el = _appendCellHeading(host, title); onAppend(el); return el; };
  log.json = (a, b) => { const el = b === undefined ? _appendCellJson(host, a) : _appendCellJson(host, b, a); onAppend(el); return el; };
  log.details = (summary, body) => { const el = _appendCellDetails(host, summary, body); onAppend(el); return el; };
  log.kv = (obj) => { const el = _appendCellKv(host, obj); onAppend(el); return el; };
  log.html = (htmlString) => { const el = _appendCellHtml(host, htmlString); onAppend(el); return el; };
  log.svg = svgFn || ((htmlString) => log.html(htmlString));
  log.draw = (W, H, body, opts = {}) => {
    const title  = opts.title || null;
    const bg     = opts.bg     || "#0d0d0d";
    const border = opts.border || "#2a2a2a";
    const radius = opts.radius != null ? opts.radius : 6;
    const titleEl = title
      ? `<text x="${W / 2}" y="22" text-anchor="middle" font-size="11" font-family="ui-monospace,monospace" fill="#6f6f6f" letter-spacing="0.08em">${String(title)
          .replace(/[<>&]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]))}</text>`
      : "";
    return log.svg(`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;background:${bg};border:1px solid ${border};border-radius:${radius}px">${titleEl}${body}</svg>`);
  };
  log.clear = () => { host.innerHTML = ""; };
  return log;
}

// ── mountCanvasFlow: a 2D graph view of an exercise ─────────────────────────────
// Renders the nodes as icon-and-title cards on a grid joined by curved SVG edges, each node's editable CodeMirror cell stacked below in declared (= run) order.

// Call: mountCanvasFlow("#cell", { label, intro, nodes, edges }), where:
//   - nodes: [{ id, icon, title, x, y, summary, code }] (code editable, run in declared order)
//   - edges: [{ from, to }] (drawn as curved SVG arrows between node cards)

// Each node runs as async (state, helpers) => { … } and nodes share `state`, so a later node reads earlier results.
// helpers.log appends a line and the return value renders as the node result. With no callback, helpers.chatStream(opts) streams into the results view; pass null second to suppress.
export function mountCanvasFlow(targetSel, opts) {
  const target = typeof targetSel === "string" ? document.querySelector(targetSel) : targetSel;
  if (!target) return;
  const { label, intro, nodes, edges = [], minHeight = 320 } = opts;

  const ns = {};
  for (const n of nodes) ns[n.id] = { code: n.code || "", status: "idle", output: null, logs: [], cm: null };
  const shared = {};

  const maxX = Math.max(0, ...nodes.map(n => n.x ?? 0));
  const maxY = Math.max(0, ...nodes.map(n => n.y ?? 0));
  const cols = maxX + 1, rows = maxY + 1;
  const markerId = "cf-arr-" + Math.random().toString(36).slice(2, 8);

  // Scope the helper menu to the helpers this canvas's nodes actually use, derived from the node code (helpers.X references plus any `{ … } = helpers` destructure); opts.helpers overrides it.
  // Display-only: every helper stays injected into each node, so a cell can still call an off-menu one.
  let _menuAllow = opts.helpers ? new Set(opts.helpers) : null;
  if (!_menuAllow) {
    const _src = nodes.map(n => n.code || "").join("\n");
    const _used = new Set();
    // helpers.X covers the domain helpers AND the platform primitives (fetch / trace / log / signal).
    for (const k of Object.keys(HELPER_FNS)) if (_src.indexOf("helpers." + k) >= 0) _used.add(k);
    for (const k of ["fetch", "trace", "log", "signal"]) if (_src.indexOf("helpers." + k) >= 0) _used.add(k);
    // helpers.viz.X covers only the visualization builders this canvas actually draws with.
    if (typeof VIZ_BUILDERS !== "undefined") for (const k of Object.keys(VIZ_BUILDERS)) if (_src.indexOf("viz." + k) >= 0) _used.add("viz." + k);
    // `state` is a bare in-scope object (not helpers.state); include it when a node touches it.
    if (/\bstate\b/.test(_src)) _used.add("state");
    // `{ x, y } = helpers` destructures.
    let _m; const _re = /\{([^}]*)\}\s*=\s*helpers\b/g;
    while ((_m = _re.exec(_src))) _m[1].split(",").forEach(s => { const nm = s.trim().split(":")[0].trim(); if (nm) _used.add(nm); });
    _menuAllow = _used;
  }
  // Build the rows once. The section's helpers show; the rest are flagged extra and hidden behind a "show all" toggle so every helper stays reachable without cluttering the menu.
  const _helperRows = _buildHelperRows(_menuAllow);
  const _extraN = _helperRows.filter(r => r.extra && !r.sectionHead).length;

  const wrap = document.createElement("div");
  wrap.className = "cf-wrap";
  wrap.innerHTML = `
    <div class="cf-header">
      <span class="cf-label">${label || ""}</span>
      <div class="cf-actions cell-actions">
        ${_cellBtnHTML("reset", "↺ Reset code", "cf-btn cf-btn-reset", "Restore every node's code to its original")}
        ${_cellBtnHTML("run", "▶ Run all", "cf-btn cf-btn-run", "Run every node in order")}
      </div>
    </div>
    ${intro ? `<div class="cf-intro">${intro}</div>` : ""}
    <details class="cf-helpers">
      <summary>
        <span class="cf-helpers-chip">helpers</span>
        <span class="cf-helpers-sig">in scope inside every node: <code>state</code>, <code>helpers</code></span>
        <span class="cf-helpers-meta">click a row to inspect &amp; edit its source</span>
      </summary>
      <div class="cf-helpers-scroll">
      ${_extraN ? `<button type="button" class="cf-helpers-showall" aria-expanded="false" style="margin:6px 0;background:transparent;border:1px solid var(--bd);color:var(--td);border-radius:5px;padding:3px 10px;font-family:var(--mono);font-size:.74rem;cursor:pointer;">+ show all ${_extraN} more helpers</button>` : ""}
      <table class="cf-helpers-table">
        <tbody>
          ${_helperRows.map(r => {
            if (r.sectionHead) return `<tr class="cf-helpers-section-head"${r.extra ? ' data-x="1" style="display:none"' : ''}><td colspan="2">${r.sectionHead}</td></tr>`;
            const editable = r.editable !== false;
            // Prefer the helper's own @doc comment; fall back to the curated text only where none.
            const _d = _docFor(r.row);
            const _s = SPECIALS[r.row] || {};
            const sig = _d.sig || _s.sig || `<code>helpers.${r.row}(…)</code>`;
            const desc = _d.desc || _s.desc || "";
            return `<tr data-helper="${r.row}"${r.extra ? ' data-x="1" style="display:none"' : ''}><td>${sig}</td><td>${desc}</td></tr>
              <tr class="cf-helpers-source-row" data-helper-source="${r.row}" hidden>
                <td colspan="2">
                  <div class="cf-helpers-src-head">
                    source · <code>${r.row}</code>
                    ${editable ? `<button type="button" class="cf-helpers-apply" data-apply="${r.row}" title="Compile your edits and override the helper for this canvas">apply override</button>
                    <button type="button" class="cf-helpers-revert" data-revert="${r.row}" title="Restore the original source">revert</button>` : ""}
                    <span class="cf-helpers-status" data-status-of="${r.row}"></span>
                  </div>
                  <textarea class="cf-helpers-src-editor" data-src-for="${r.row}" spellcheck="false" ${editable ? "" : "readonly"}></textarea>
                </td>
              </tr>`;
          }).join("")}
        </tbody>
      </table>
      </div>
    </details>
    <div class="cf-stage">
      <svg class="cf-svg" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <defs>
          <marker id="${markerId}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L10,5 L0,10 Z" fill="var(--gfx-nvgreen,#76b900)"/>
          </marker>
        </defs>
      </svg>
      <div class="cf-canvas" style="min-height:${minHeight}px;grid-template-columns:repeat(${cols},minmax(170px,1fr));grid-template-rows:repeat(${rows},auto);"></div>
    </div>
    <div class="cf-status-bar" role="status" aria-live="polite" aria-atomic="true"></div>
    <div class="cf-panels"></div>
  `;
  target.appendChild(wrap);

  const setFlowState = (state) => {
    wrap.dataset.state = state;
    wrap.setAttribute("aria-busy", state === "running" ? "true" : "false");
  };
  setFlowState("ready");

  const stage     = wrap.querySelector(".cf-stage");
  const svg       = wrap.querySelector(".cf-svg");
  const canvas    = wrap.querySelector(".cf-canvas");
  const statusBar = wrap.querySelector(".cf-status-bar");
  const panelsHost = wrap.querySelector(".cf-panels");

  // Click a helpers-table row to reveal that helper's source.
  // Live functions use toString; values and closures use inline examples.
  const HELPER_SRC = {
    state: `// Shared object for this Run-all.
// Write in one node, read in later nodes.
state.question = "What is the capital of France?";
// Later: use state.question in a chat call.`,
    chat:                chat.toString(),
    chatStream:          chatStream.toString(),
    webSearch:           webSearch.toString(),
    instantAnswer:       instantAnswer.toString(),
    formatSearchResults: formatSearchResults.toString(),
    embed:               embed.toString(),
    cosineSim:           cosineSim.toString(),
    trace: `// Add a lightweight span to state.__trace.
// Later nodes can inspect or render the full trace.
helpers.trace("llm.chat", { model, tokens: usage.total_tokens });`,
    log: `// Write to this node's log area.
// Objects render as JSON; extra values join as text.
helpers.log("step 1 done", { count: 42 });`,
    "viz.scoreBarChart": `// Draw rubric scores as an SVG bar chart.
// Green meets threshold; amber is borderline; red is below.
helpers.viz.scoreBarChart(
  [{ score: 5, label: "accuracy" }, { score: 3, label: "relevance" }, { score: 2, label: "concision" }],
  { threshold: 3, title: "Rubric scores" }
);`,
    "viz.lineChart": `// Draw a numeric sequence while keeping the source data available.
const values = [3, 4, 5, 6, 7, 8, 9, 8, 7];
helpers.viz.lineChart(values, {
  title: "Position by tick", xLabel: "tick", yLabel: "position", min: 0, max: 9,
});
return values;`,
    "viz.messageList": `// Render LLM messages as color-coded cards.
// Pass the same message objects you send to the LLM API.
helpers.viz.messageList(state.messages, "Memory grows with each turn");`,
    "viz.ganttBars": `// Draw worker time, serial total, and wall time.
// Use seconds for each worker duration and for wallSeconds.
const t0 = performance.now();
const results = await Promise.all(tasks.map(doWork));
helpers.viz.ganttBars(
  results.map((r, i) => ({ label: \`worker \${i+1}\`, dt: r.elapsed })),
  (performance.now() - t0) / 1000,
  "Parallel vs serial"
);`,
    "viz.retrievalBars": `// Draw retrieval scores in sorted order.
// Top-k bars are green; the rest stay muted.
helpers.viz.retrievalBars(
  results.map(r => ({ text: r.chunk.slice(0, 80), score: r.similarity })),
  3, "Cosine similarity · top-3 retrieved"
);`,
    fetchRetry:          fetchRetry.toString(),
    getConfig:           getConfig.toString(),
    getKey:              getKey.toString(),
    "viz.diagram": `// Render a node/edge figure from data, not hand-written SVG.
// Use x/y grid coordinates and kind-based styling.
helpers.viz.diagram({
  title: "One agent call",
  nodes: [{ id: "you", label: "your code", kind: "data",  x: 0, y: 0 },
          { id: "gw",  label: "gateway",   kind: "agent", x: 1, y: 0 }],
  edges: [{ from: "you", to: "gw", label: "POST" }],
});`,
    "viz.diffTable": `// Render a before/after table.
// Rows can be boolean checks or numeric deltas.
helpers.viz.diffTable({ rows: [
  { kind: "num",   label: "latency (s)", left: 4.1,   right: 1.2,  betterWhen: "down" },
  { kind: "check", label: "schema ok",   left: false, right: true },
]}, { leftTitle: "before", rightTitle: "after" });`,
    "viz.chat": `// helpers.viz.chat(turns, opts?)
// Render a transcript as colour-coded bubbles.
// turns: array of [role, content] pairs; role ∈ { user, assistant|ai, system, tool }.
// opts:  { maxChars? }  (truncate each turn). Example:
helpers.viz.chat([
  ["system", "You are terse."],
  ["user", "Hi"],
  ["assistant", "Hello."],
], { maxChars: 200 });`,
    "viz.sideBySide": `// helpers.viz.sideBySide(leftLines, rightLines, opts?)
// Two text columns side by side.
// leftLines / rightLines: arrays of strings (one per row).
// opts: { leftTitle?, rightTitle?, footer? }. Example:
helpers.viz.sideBySide(
  ["plan: search", "plan: summarize"],
  ["ran: search ✓", "ran: summarize ✓"],
  { leftTitle: "planned", rightTitle: "executed" }
);`,
  };
  // Per-canvas helper overrides: { [helperName]: compiledFunction }.
  // Empty by default; populated when the student clicks "apply override" on an editable helper source.
  // Read by runNode below before calling the user's code.
  const helperOverrides = {};
  const helperEditors   = {};  // { [helperName]: CodeMirror instance }
  let _liveHelpers = null, _liveViz = null;  // the live helper set, captured per run (see runNode)

  // Resolve a helper's source live from the code so the menu can never drift.
  // Top-level helpers come from HELPER_FNS via Function.toString(), viz.* from VIZ_BUILDERS (or the live viz once a node has run), and the value/native/closure ones (state, fetch, trace, log) from SPECIALS.src.
  function _resolveHelperSrc(name) {
    if (HELPER_FNS[name]) return HELPER_FNS[name].toString();
    if (name.startsWith("viz.")) {
      const k = name.slice(4);
      if (typeof VIZ_BUILDERS !== "undefined" && typeof VIZ_BUILDERS[k] === "function") return VIZ_BUILDERS[k].toString();
      if (_liveViz && typeof _liveViz[k] === "function") return _liveViz[k].toString();
    }
    if (SPECIALS[name]) return SPECIALS[name].src;
    return "// (source unavailable)";
  }

  // Structural self-check: the menu rows must match what the live helpers object exposes.
  // It warns once on drift, so a helper added to baseHelpers without a row, or a stale row, surfaces in the console instead of silently showing "source not available".
  let _menuAudited = false;
  function _auditHelperMenu(live) {
    if (_menuAudited || !helpersTable) return;
    _menuAudited = true;
    const rows = new Set([...helpersTable.querySelectorAll("tr[data-helper]")].map(r => r.dataset.helper));
    const callable = [...Object.keys(live).filter(k => k !== "viz"),
                      ...Object.keys(live.viz || {}).map(k => "viz." + k), "state"];
    const undocumented = callable.filter(n => !rows.has(n));
    const phantom = [...rows].filter(n => n !== "state" && !callable.includes(n));
    if (undocumented.length) console.warn("[helpers menu] callable but no row:", undocumented);
    if (phantom.length)      console.warn("[helpers menu] row but not callable:", phantom);
  }

  const helpersTable = wrap.querySelector(".cf-helpers-table");
  if (helpersTable) {
    // "show all" toggle reveals or hides the extras (helpers this section does not use).
    // The default menu stays scoped to the section, but every helper is one click away to read and edit.
    const _showAll = wrap.querySelector(".cf-helpers-showall");
    if (_showAll) _showAll.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const on = _showAll.getAttribute("aria-expanded") !== "true";
      _showAll.setAttribute("aria-expanded", on ? "true" : "false");
      helpersTable.querySelectorAll("[data-x]").forEach(el => { el.style.display = on ? "" : "none"; });
      _showAll.textContent = on ? "− show only this section's helpers" : `+ show all ${_extraN} more helpers`;
    });
    // Click a helper row → toggle its inline source row directly below.
    // Only one source row open at a time keeps the menu compact.
    helpersTable.addEventListener("click", (ev) => {
      const tr = ev.target.closest("tr[data-helper]");
      if (!tr) return;
      // ignore clicks on the source row's controls (handled separately)
      if (ev.target.closest("tr.cf-helpers-source-row")) return;
      const name = tr.dataset.helper;
      const srcRow = helpersTable.querySelector(`tr[data-helper-source="${name}"]`);
      const wasOpen = srcRow && !srcRow.hidden;
      // Collapse any currently-open row.
      helpersTable.querySelectorAll("tr.cf-helpers-source-row").forEach(r => r.hidden = true);
      helpersTable.querySelectorAll("tr[data-helper]").forEach(r => r.classList.remove("selected"));
      if (wasOpen || !srcRow) return;
      srcRow.hidden = false;
      tr.classList.add("selected");
      _initHelperEditor(name);
    });

    // Apply / revert buttons inside source rows.
    helpersTable.addEventListener("click", (ev) => {
      const apply = ev.target.closest("[data-apply]");
      if (apply) {
        ev.stopPropagation();
        _applyHelperOverride(apply.dataset.apply);
        return;
      }
      const revert = ev.target.closest("[data-revert]");
      if (revert) {
        ev.stopPropagation();
        _revertHelperOverride(revert.dataset.revert);
      }
    });
  }


  function _initHelperEditor(name) {
    const ta = helpersTable.querySelector(`textarea[data-src-for="${name}"]`);
    if (!ta) return;
    // Seed with current value (override if present, otherwise the live source).
    const original = _resolveHelperSrc(name);
    if (helperEditors[name]) {
      setTimeout(() => helperEditors[name].refresh(), 30);
      return;
    }
    ta.value = (helperOverrides[name]?.src) || original;
    if (window.CodeMirror) {
      helperEditors[name] = window.CodeMirror.fromTextArea(ta, {
        mode: "javascript",
        theme: "monokai",
        lineNumbers: true,
        lineWrapping: true,
        tabSize: 2,
        indentUnit: 2,
        readOnly: ta.hasAttribute("readonly"),
        viewportMargin: Infinity,
        extraKeys: {
          "Cmd-/":     _cmCommentToggle,
          "Ctrl-/":    _cmCommentToggle,
          "Tab":       e => e.execCommand("indentMore"),
          "Shift-Tab": e => e.execCommand("indentLess"),
        },
      });
      helperEditors[name].setSize("100%", "auto");
      setTimeout(() => helperEditors[name].refresh(), 30);
    }
  }

  function _applyHelperOverride(name) {
    const editor = helperEditors[name];
    if (!editor) return;
    const src = editor.getValue();
    const status = helpersTable.querySelector(`[data-status-of="${name}"]`);
    try {
      // Compile the edited source as an expression, wrapped in parens.
      // It must evaluate to a function: a plain function, an async function, or an arrow function.
      const fn = new Function(`"use strict"; return (${src});`)();
      if (typeof fn !== "function") {
        throw new Error("source must evaluate to a function");
      }
      helperOverrides[name] = { fn, src };
      if (status) {
        status.textContent = "✓ override active";
        status.className = "cf-helpers-status ok";
      }
    } catch (e) {
      if (status) {
        status.textContent = `✗ ${e.message}`;
        status.className = "cf-helpers-status err";
      }
    }
  }

  function _revertHelperOverride(name) {
    delete helperOverrides[name];
    const editor = helperEditors[name];
    const original = _resolveHelperSrc(name);
    if (editor) editor.setValue(original);
    const status = helpersTable.querySelector(`[data-status-of="${name}"]`);
    if (status) { status.textContent = ""; status.className = "cf-helpers-status"; }
  }

  // Compact node cards on the canvas.
  for (const node of nodes) {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "cf-node";
    card.dataset.id = node.id;
    card.style.gridColumn = (node.x ?? 0) + 1;
    card.style.gridRow    = (node.y ?? 0) + 1;
    card.innerHTML = `
      <span class="cf-node-icon">${node.icon || "●"}</span>
      <span class="cf-node-title">${node.title || ""}</span>
      <span class="cf-node-status-dot" data-status></span>
    `;
    card.addEventListener("click", () => focusPanel(node.id));
    canvas.appendChild(card);
  }

  // One <details> for the (editable JS) code and one for results. Both collapsed by default.
  for (const node of nodes) {
    const panel = document.createElement("div");
    panel.className = "cf-panel";
    panel.dataset.id = node.id;
    // Short teaching snippets open by default; longer/plumbing snippets stay one click away.
    // node.showCode forces it: true = always open, false = always collapsed.
    const _showCode = _cellCodeOpen(node, node.code, "canvas");
    panel.innerHTML = `
      <div class="cf-panel-head cell-head">
        <span class="cf-panel-icon">${node.icon || "●"}</span>
        <span class="cf-panel-title">${node.title || ""}</span>
        ${node.summary ? `<span class="cf-panel-summary">${node.summary}</span>` : ""}
        <span class="cell-actions">
          <span class="cf-panel-status-dot" data-status></span>
          ${_cellBtnHTML("reset", "↺ Reset", "cf-panel-reset", "Restore this node's original code and clear its output")}
          ${_cellBtnHTML("run", "▶ Run", "cf-panel-runone", "Run this node")}
        </span>
      </div>
      <div class="cf-panel-overview"></div>
      <details class="cf-panel-det cf-panel-code-det"${_showCode ? " open" : ""}>
        ${_cellLangSummaryHTML({ sig: "async (state, helpers) =&gt; { … }", meta: _showCode ? "click to collapse" : "click to expand", metaAttr: "data-code-meta" })}
        <div class="cf-panel-code-body cell-code-body">
          <div class="cf-code-view cell-code-view" data-lang="js">
            <textarea class="cf-panel-code" spellcheck="false">${escapeHtml(node.code || "")}</textarea>
          </div>
          <button type="button" class="cf-code-copy cell-code-copy" title="Copy code to clipboard" aria-label="Copy code">⎘</button>
        </div>
      </details>
      <details class="cf-panel-det cf-panel-results-det">
        <summary>
          <span class="cf-det-chip cf-det-chip-alt">results</span>
          <span class="cf-det-sig">stream · log · return value</span>
          <span class="cf-det-meta" data-results-meta>not yet run</span>
        </summary>
        <div class="cf-panel-stream"></div>
        <div class="cf-panel-log cell-log"></div>
        <div class="cf-panel-output cell-output-panel"></div>
      </details>
    `;
    panelsHost.appendChild(panel);

    // Floating copy button that copies the currently-active source.
    const copyBtn = panel.querySelector(".cf-code-copy");
    if (copyBtn) {
      copyBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        const src = ns[node.id].cm ? ns[node.id].cm.getValue() : node.code;
        navigator.clipboard.writeText(src || "").then(() => {
          const orig = copyBtn.textContent;
          copyBtn.textContent = "✓";
          copyBtn.classList.add("ok");
          setTimeout(() => { copyBtn.textContent = orig; copyBtn.classList.remove("ok"); }, 1500);
        });
      });
    }

    panel.querySelector(".cf-panel-runone").addEventListener("click", async (e) => {
      e.stopPropagation();
      if (running) { stopRun(); return; }   // a run is in flight: this click stops it
      // Run this one node under the shared cancellation.
      // The Run-all button flips to "⏹ Stop" so it can abort even a single-node run.
      const epoch = beginRun();
      try { await runNode(node.id); } catch (_) {} finally { if (epoch === runEpoch) endRun(); }
    });

    panel.querySelector(".cf-panel-reset").addEventListener("click", (e) => {
      e.stopPropagation();
      if (running) { runEpoch++; stopRun(); endRun(); }
      resetNode(node.id);
    });

    // Initialize CodeMirror lazily on the first open of the code dropdown, then refresh it so wrapped lines render correctly.
    const codeDet = panel.querySelector(".cf-panel-code-det");
    codeDet.addEventListener("toggle", () => {
      if (!codeDet.open) return;
      ensureCM(node.id);
      if (ns[node.id].cm) setTimeout(() => ns[node.id].cm.refresh(), 30);
    });
    // A default-open panel never fires the toggle event, so initialize its editor at mount.
    if (codeDet.open) setTimeout(() => { ensureCM(node.id); if (ns[node.id] && ns[node.id].cm) ns[node.id].cm.refresh(); }, 60);
  }

  // ── Lab-only gating ──────────────────────────────────────────────────────
  // When the lab is unreachable (getConfig resolves to "direct" mode, as in the edX iframe), steps that talk to lab-only services are badged 🔒 and explained rather than run.
  let _labReachable = true;
  function _labBadgeCard(node) {
    const card = canvas.querySelector(`.cf-node[data-id="${node.id}"]`);
    if (card && !card.querySelector(".cf-node-lab")) {
      const b = document.createElement("span");
      b.className = "cf-node-lab"; b.textContent = "🔒";
      b.title = "Runs in your launchable only"; b.style.cssText = "margin-left:3px;font-size:.7em;opacity:.85";
      (card.querySelector(".cf-node-title") || card).appendChild(b);
    }
  }

  function _labOnlyNotice(node, panel) {
    if (!panel) return;
    _labBadgeCard(node);
    const det = panel.querySelector(".cf-panel-results-det"); if (det) det.open = true;
    const streamEl = panel.querySelector(".cf-panel-stream"); if (streamEl) streamEl.textContent = "";
    const logEl = panel.querySelector(".cf-panel-log"); if (logEl) logEl.innerHTML = "";
    const outEl = panel.querySelector(".cf-panel-output");
    if (outEl) {
      outEl.innerHTML = "";
      const div = document.createElement("div");
      div.className = "cf-panel-error";
      div.style.cssText = "border-left:3px solid var(--warn);background:rgba(212,156,44,.10);color:var(--tx)";
      div.innerHTML = "🔒 <strong>This step runs in your launchable.</strong> It uses " + escapeHtml(_labOnlyService(node)) +
        ", which is gated on your launchable's token and can't be reached from this edX page. Open this page from inside your " +
        "NemoClaw launchable to run it, or run the step in your launchable's OpenClaw chat. The model steps on this page work here once you set your <code>nvapi-</code> key.";
      outEl.appendChild(div);
    }
    const meta = panel.querySelector("[data-results-meta]");
    if (meta) { meta.textContent = "lab only"; meta.className = "cf-det-meta err"; }
    setStatus(node.id, "idle");
  }

  function _applyLabBadges() {
    let any = false;
    for (const node of nodes) {
      if (!_stepLabOnly(node)) continue;
      any = true;
      _labBadgeCard(node);
      const panel = panelsHost.querySelector(`.cf-panel[data-id="${node.id}"]`);
      const ov = panel && panel.querySelector(".cf-panel-overview");
      if (ov && !ov.querySelector(".cf-lab-note")) {
        const n = document.createElement("div");
        n.className = "cf-lab-note";
        n.style.cssText = "font-size:.78rem;color:var(--tx);border-left:3px solid var(--warn);background:rgba(212,156,44,.08);padding:6px 10px;border-radius:0 4px 4px 0;margin:.3em 0";
        n.innerHTML = "🔒 Runs in your launchable. Uses " + escapeHtml(_labOnlyService(node)) + ". Open this page from your launchable to run it.";
        ov.appendChild(n);
      }
    }
    if (any && !document.querySelector(".cf-lab-banner")) {
      const banner = document.createElement("div");
      banner.className = "cf-lab-banner";
      banner.style.cssText = "font-size:.82rem;color:var(--tx);border:1px solid var(--warn);background:rgba(212,156,44,.08);padding:8px 12px;border-radius:6px;margin:0 0 .8em";
      banner.innerHTML = "🔒 Some steps here run <strong>only inside your launchable</strong> (marked 🔒): they use services gated on your launchable's token. Open this page from your launchable to run those; the model steps work here with your <code>nvapi-</code> key.";
      target.insertBefore(banner, wrap);
    }
  }
  getConfig().then(cfg => { _labReachable = !!(cfg && cfg.mode === "proxy"); if (!_labReachable) _applyLabBadges(); }).catch(() => {});

  // Helper: sync status dots from ns[nodeId].status ("idle"|"running"|"ok"|"error")
  function _updateStatus(panel, nodeId) {
    const s = ns[nodeId];
    const dots = panel.querySelectorAll("[data-status]");
    dots.forEach(d => { d.dataset.status = s.status || "idle"; });
    const card = canvas.querySelector(`.cf-node[data-id="${nodeId}"] [data-status]`);
    if (card) card.dataset.status = s.status || "idle";
  }

  function resetNode(nodeId) {
    const node = nodes.find(n => n.id === nodeId);
    const s = ns[nodeId];
    const panel = panelsHost.querySelector(`.cf-panel[data-id="${nodeId}"]`);
    if (!node || !s || !panel) return;

    s.code = node.code || "";
    s.output = null;
    s.logs = [];
    if (s.cm) { s.cm.setValue(s.code); _clearCMErrs(s.cm); }
    else {
      const ta = panel.querySelector('.cf-code-view[data-lang="js"] .cf-panel-code');
      if (ta) ta.value = s.code;
    }

    const overview = panel.querySelector(".cf-panel-overview");
    const stream = panel.querySelector(".cf-panel-stream");
    const logEl = panel.querySelector(".cf-panel-log");
    const outEl = panel.querySelector(".cf-panel-output");
    if (overview) overview.innerHTML = "";
    if (stream) stream.textContent = "";
    if (logEl) logEl.innerHTML = "";
    if (outEl) outEl.innerHTML = "";

    const meta = panel.querySelector("[data-results-meta]");
    if (meta) { meta.textContent = "reset"; meta.className = "cf-det-meta"; }
    setStatus(nodeId, "idle");
    flowEdgesInto(nodeId, false);
  }

  function ensureCM(nodeId) {
    const s = ns[nodeId];
    if (s.cm) return s.cm;
    const panel = panelsHost.querySelector(`.cf-panel[data-id="${nodeId}"]`);
    const ta    = panel.querySelector('.cf-code-view[data-lang="js"] .cf-panel-code');
    if (window.CodeMirror && ta) {
      s.cm = window.CodeMirror.fromTextArea(ta, {
        mode: "javascript",
        theme: "monokai",
        lineNumbers: true,
        lineWrapping: true,
        viewportMargin: Infinity,
        tabSize: 2,
        indentUnit: 2,
        extraKeys: {
          "Cmd-/":     _cmCommentToggle,
          "Ctrl-/":    _cmCommentToggle,
          "Tab":       e => e.execCommand("indentMore"),
          "Shift-Tab": e => e.execCommand("indentLess"),
        },
      });
      s.cm.setSize("100%", "auto");
      s.cm.on("change", () => { s.code = s.cm.getValue(); });
    }
    return s.cm;
  }

  function focusPanel(nodeId) {
    canvas.querySelectorAll(".cf-node").forEach(c => c.classList.toggle("active", c.dataset.id === nodeId));
    panelsHost.querySelectorAll(".cf-panel").forEach(p => p.classList.toggle("focus", p.dataset.id === nodeId));
    const p = panelsHost.querySelector(`.cf-panel[data-id="${nodeId}"]`);
    if (p) p.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // Edge geometry: route vertically whenever the target is on a different row (dy != 0), exiting the source bottom (dy>0) or top (dy<0) and entering the opposite side of the target.
  // Bezier control points pull straight off each port, giving an S-curve when the nodes are diagonal.
  function relayoutEdges() {
    [...svg.querySelectorAll("path.cf-edge")].forEach(p => p.remove());
    const stageBox = stage.getBoundingClientRect();
    if (stageBox.width < 2 || stageBox.height < 2) {
      requestAnimationFrame(relayoutEdges);
      return;
    }
    svg.setAttribute("viewBox", `0 0 ${stageBox.width} ${stageBox.height}`);
    svg.setAttribute("width",  stageBox.width);
    svg.setAttribute("height", stageBox.height);

    for (const edge of edges) {
      const a = canvas.querySelector(`[data-id="${edge.from}"]`);
      const b = canvas.querySelector(`[data-id="${edge.to}"]`);
      if (!a || !b) continue;
      const ra = a.getBoundingClientRect();
      const rb = b.getBoundingClientRect();
      const cAy = ra.top + ra.height/2, cBy = rb.top + rb.height/2;
      const cAx = ra.left + ra.width/2, cBx = rb.left + rb.width/2;
      const dy = cBy - cAy;
      const dx = cBx - cAx;

      let p1x, p1y, p2x, p2y, vertical;
      if (Math.abs(dy) >= 8) {
        // Different rows → vertical-leaning routing (top/bottom ports).
        vertical = true;
        if (dy > 0) { p1x = cAx; p1y = ra.bottom; p2x = cBx; p2y = rb.top; }
        else        { p1x = cAx; p1y = ra.top;    p2x = cBx; p2y = rb.bottom; }
      } else {
        // Same row → horizontal-leaning routing (left/right ports).
        vertical = false;
        if (dx > 0) { p1x = ra.right; p1y = cAy; p2x = rb.left;  p2y = cBy; }
        else        { p1x = ra.left;  p1y = cAy; p2x = rb.right; p2y = cBy; }
      }
      p1x -= stageBox.left; p1y -= stageBox.top;
      p2x -= stageBox.left; p2y -= stageBox.top;

      let d;
      if (vertical) {
        const cdy = Math.max(28, Math.abs(p2y - p1y) * 0.5);
        // Control points pull straight off each port; the p1.x-to-p2.x offset makes the S-curve.
        d = `M ${p1x} ${p1y} C ${p1x} ${p1y + (p2y > p1y ? cdy : -cdy)}, ${p2x} ${p2y - (p2y > p1y ? cdy : -cdy)}, ${p2x} ${p2y}`;
      } else {
        const cdx = Math.max(40, Math.abs(p2x - p1x) * 0.5);
        d = `M ${p1x} ${p1y} C ${p1x + (p2x > p1x ? cdx : -cdx)} ${p1y}, ${p2x - (p2x > p1x ? cdx : -cdx)} ${p2y}, ${p2x} ${p2y}`;
      }
      const el = document.createElementNS("http://www.w3.org/2000/svg", "path");
      el.setAttribute("d", d);
      el.setAttribute("class", "cf-edge");
      el.setAttribute("data-from", edge.from);
      el.setAttribute("data-to",   edge.to);
      el.setAttribute("marker-end", `url(#${markerId})`);
      svg.appendChild(el);
    }
  }

  const ro = new ResizeObserver(() => relayoutEdges());
  ro.observe(stage);
  window.addEventListener("resize", relayoutEdges, { passive: true });
  setTimeout(relayoutEdges, 0);
  setTimeout(relayoutEdges, 100);

  // Cancellation: one AbortController per run.
  // While running, the Run-all button shows "⏹ Stop"; clicking it aborts in-flight helpers (chat, chatStream, terminal all honour the signal) and closes any gateway/terminal socket the cell parked on state._ws.
  let runAC = null, running = false, runEpoch = 0;
  const _runBtn = () => wrap.querySelector(".cf-btn-run");
  function beginRun() {
    runEpoch++;
    running = true; runAC = new AbortController();
    setFlowState("running");
    const b = _runBtn();
    if (b) { b.textContent = "⏹ Stop"; b.disabled = false; b.style.background = "var(--err)"; b.style.color = "#fff"; }
    return runEpoch;
  }
  function endRun() {
    running = false; runAC = null;
    const b = _runBtn();
    if (b) { b.textContent = "▶ Run all"; b.disabled = false; b.style.background = ""; b.style.color = ""; }
  }
  function stopRun() {
    if (!running || !runAC) return;
    try { runAC.abort(); } catch (_) {}
    try { if (shared._ws) shared._ws.close(); } catch (_) {}
    const b = _runBtn(); if (b) b.textContent = "⏹ stopping…";
  }

  async function runNode(nodeId) {
    const node = nodes.find(n => n.id === nodeId);
    if (!node) return;
    const epoch = runEpoch;
    const s = ns[nodeId];
    const panel = panelsHost.querySelector(`.cf-panel[data-id="${nodeId}"]`);
    // Lab-only steps can't run outside the lab; explain instead of failing.
    const _cfg = await getConfig();
    if (epoch !== runEpoch) return;
    if (_cfg.mode !== "proxy" && _stepLabOnly(node)) { _labReachable = false; _labOnlyNotice(node, panel); return; }
    setStatus(nodeId, "running");
    flowEdgesInto(nodeId, true);
    const t0 = performance.now();

    // Update the meta badge on the results dropdown so the run state shows even while collapsed.
    const metaEl = panel.querySelector("[data-results-meta]");
    if (metaEl) { metaEl.textContent = "streaming…"; metaEl.className = "cf-det-meta running"; }

    // Auto-open results so streaming output is visible while the node runs.
    const resultsDet = panel.querySelector(".cf-panel-results-det");
    if (resultsDet) resultsDet.open = true;

    const streamEl = panel.querySelector(".cf-panel-stream"); streamEl.textContent = "";
    const logEl    = panel.querySelector(".cf-panel-log");    logEl.innerHTML = ""; s.logs = [];
    const outEl    = panel.querySelector(".cf-panel-output"); outEl.innerHTML = "";

    const log = (...args) => {
      // Dicts and lists are pretty-printed + syntax-highlighted; plain values stay text.
      const el = appendLogLine(logEl, args);
      s.logs.push(el);
      return el;
    };
    // Capture a cell's console.{log,warn,error,info} into the panel log (warn/error tinted) and mirror to the real console, so console statements show in the panel, not just devtools.
    // Injected as a `console` parameter that shadows the global only inside the cell, never leaking.
    const _capLine = (kind, args) => {
      // Same object-aware formatting as helpers.log, with warn/error tinting + a prefix glyph.
      const opts = kind === "warn"  ? { prefix: "⚠ ", color: "var(--warn)" }
                 : kind === "error" ? { prefix: "✗ ", color: "var(--err)" }
                 : {};
      s.logs.push(appendLogLine(logEl, args, opts));
      try { (console[kind] || console.log).apply(console, args); } catch (_) {}
    };
    const cellConsole = {
      log:   (...a) => _capLine("log", a),
      info:  (...a) => _capLine("log", a),
      debug: (...a) => _capLine("log", a),
      warn:  (...a) => _capLine("warn", a),
      error: (...a) => _capLine("error", a),
    };
    // log.html/svg/draw need the lite SVG color pass, so install them after the pass is defined.
    const _LITE_VIZ_SUBS = (typeof window !== "undefined" && window.parent !== window) ? [
      // Backgrounds / panel surfaces
      ['#161616', '#eef1f4'], ['#1e1e1e', '#f6f8fa'], ['#0d0d0d', '#f6f8fa'],
      ['#0a0a0a', '#f6f8fa'], ['#1c1c1c', '#eef1f4'], ['#262626', '#e1e6eb'],
      ['#131313', '#eef1f4'], ['#1a1a2e', '#dfeaf5'], ['#0d2a0d', '#e6f3d4'],
      ['#1a3a2a', '#daeec1'], ['#1e3a1e', '#daeec1'], ['#141f04', '#e6f3d4'],
      ['#111a11', '#e6f3d4'], ['#1a2820', '#daeec1'], ['#1e1e3a', '#dfeaf5'],
      ['#3a2e1e', '#f7e3c5'], ['#3a1e1e', '#fadcdc'], ['#1f1a2e', '#eadfff'],
      ['#0d1828', '#dfeaf5'], ['#0d2b40', '#dfeaf5'], ['#141f3a', '#cad7e8'],
      ['#1a2850', '#b5c6db'], ['#211b12', '#f7e3c5'], ['#0f1a22', '#dfeaf5'],
      // Light-on-dark token colors → readable on light
      ['#aee23a', '#4a7a00'], ['#7eb8ff', '#0969da'], ['#7eb6ff', '#0969da'],
      ['#e8c87a', '#8b6914'], ['#f2cc60', '#8b6914'], ['#d2b9ff', '#6f42c1'],
      ['#c4b5fd', '#6f42c1'], ['#a78bfa', '#6f42c1'], ['#c084fc', '#6f42c1'],
      ['#ff9a9a', '#d1242f'], ['#ff6b6b', '#d1242f'],
      ['#e0eec8', '#3b6500'], ['#c8d8f0', '#0969da'], ['#88aacc', '#0969da'],
      ['#f8f8f2', '#1f2328'], ['#f2f2f2', '#1a1a1a'], ['#e8e8e8', '#1a1a1a'],
      // Mid-grays that read OK on dark but vanish on light
      ['#a5a5a5', '#57606a'], ['#b0b0b0', '#3b3b3b'], ['#6a6a6a', '#57606a'],
      ['#6f6f6f', '#57606a'],
      // Serial-total amber (gantt bars + the scoreBar threshold line): darken for light
      ['#d49c2c', '#8b6914'],
      // Strokes
      ['stroke="#2a2a2a"', 'stroke="#d0d7de"'], ['stroke="#3a3a3a"', 'stroke="#b0b8c0"'],
      ['stroke="#4a4a4a"', 'stroke="#a5a5a5"'], ['stroke="#3a6080"', 'stroke="#0969da"'],
      ['stroke="#58a6ff"', 'stroke="#0969da"'], ['stroke="#76b900"', 'stroke="#4a7a00"'],
    ] : null;
    function _flipDarkSvg(s) {
      if (!_LITE_VIZ_SUBS) return s;
      for (const [from, to] of _LITE_VIZ_SUBS) {
        // Plain string replace is fine because we're targeting concrete hex literals.
        s = s.split(from).join(to);
      }
      return s;
    }
    _installStructuredLog(log, logEl, (el) => s.logs.push(el), (html) => {
      const el = _appendCellHtml(logEl, _flipDarkSvg(String(html)));
      s.logs.push(el);
      return el;
    });
    log.clear = () => { logEl.innerHTML = ""; s.logs = []; };

    // ── helpers.viz: per-run viz utilities (capture the per-run log) ───────────
    const viz = makeViz(log);

    // chatStream wrapper. With no callback, route tokens into the panel's streaming view (pass null to suppress); the full content is still returned for the next node.
    // Multiple chatStream calls in one cell each get a labeled section in the stream pane, so tokens are not run together.
    let streamCallIdx = 0;
    const streamingChatStream = (opts, onChunk, extra) => {
      if (onChunk === undefined) {
        streamCallIdx++;
        const hdr = document.createElement("div");
        hdr.className = "cf-panel-stream-head";
        hdr.textContent = "── call " + streamCallIdx + " ──";
        streamEl.appendChild(hdr);
        const span = document.createElement("span");
        span.className = "cf-panel-stream-tokens";
        streamEl.appendChild(span);
        onChunk = (text) => {
          span.textContent += text;
          streamEl.scrollTop = streamEl.scrollHeight;
        };
      } else if (onChunk === null) {
        onChunk = null;
      }
      return chatStream(opts, onChunk, extra);
    };

    // The overview row (between the panel header and the dropdowns) surfaces the state.X values the run wrote, so inputs and computed values are visible without expanding the results dropdown.
    // Cleared each run, populated after the code finishes.
    const overviewEl = panel.querySelector(".cf-panel-overview");
    if (overviewEl) overviewEl.innerHTML = "";

    try {
      const codeText = (s.cm ? s.cm.getValue() : s.code) || "";
      // Snapshot keys the cell adds to `state` so we can highlight them.
      const stateKeysBefore = new Set(Object.keys(shared));
      // The user's code runs as `async (state, helpers) => { ... }`.
      // The older one-letter `h` alias stays exposed for back-compat, but every node template uses `helpers.foo()` so newcomers discover what is available without reading the runtime.
      const fn = new Function("state", "helpers", "h", "console",
        `"use strict"; return (async () => {\n${codeText}\n})();`);
      // helpers.trace emits an OTel-shaped span into a shared in-page trace store any node can read. Module 5 surfaces this.
      const trace = (name, attrs = {}) => {
        if (!shared.__trace) shared.__trace = [];
        shared.__trace.push({ ts: Date.now(), name, attrs });
      };
      // Wrap each network helper so an error is logged into the panel's per-run log before bubbling, so a student's empty `catch (_) {}` cannot silently swallow 524s, JSON errors, or bad tool calls.
      // Sync stays sync, async keeps its promise, the wrapper rethrows; _raw is the unwrapped fn.
      function withErrLog(label, fn) {
        const markLogged = (e) => {
          if (e && (typeof e === "object" || typeof e === "function")) {
            try { Object.defineProperty(e, "__courseHelperErrorLogged", { value: true, configurable: true }); } catch (_) {}
          }
          return e;
        };
        const wrapped = function (...args) {
          let r;
          try { r = fn.apply(this, args); }
          catch (e) { try { log(`✗ ${label} error: ${e.message || e}`); } catch (_) {} throw markLogged(e); }
          if (r && typeof r.then === "function")
            return r.catch(e => { try { log(`✗ ${label} error: ${e.message || e}`); } catch (_) {} throw markLogged(e); });
          return r;
        };
        wrapped._raw = fn;
        return wrapped;
      }
      // baseHelpers is built from the same HELPER_FNS registry the menu enumerates.
      // The menu therefore lists exactly the helpers the runtime exposes, never more or fewer.
      // chatStream is the one per-node variant (its streaming target is this node), overriding the fn.
      const baseHelpers = {};
      for (const [k, fn] of Object.entries(HELPER_FNS)) baseHelpers[k] = withErrLog(k, fn);
      baseHelpers.chatStream = withErrLog("chatStream", streamingChatStream);
      baseHelpers.trace = trace;
      baseHelpers.log   = log;
      baseHelpers.viz   = viz;
      baseHelpers.fetch = (...a) => fetch(...a);   // the platform fetch; see fetchRetry for auto-retry
      // Apply any per-canvas overrides the student set via the helpers menu (row, edit, "apply override").
      // An override entry can replace a top-level helper or a nested viz.*.
      const helpers = { ...baseHelpers, viz: { ...viz } };
      // Cancellation wiring: expose the run's signal and auto-inject it into the network helpers, so a cell aborts on Stop without the student threading `signal` by hand.
      // A cell that passes its own signal keeps it; we only fill when absent.
      const _sig = runAC ? runAC.signal : null;
      helpers.signal = _sig || undefined;
      if (_sig) {
        const _delay = helpers.delay;
        helpers.delay = (ms, signal = _sig) => _delay(ms, signal);
        const _withSig = (o) => (o && typeof o === "object" && o.signal == null) ? { ...o, signal: _sig } : o;
        const _chat = helpers.chat, _stream = helpers.chatStream, _term = helpers.terminal;
        if (_chat)   helpers.chat       = (o, ...r) => _chat(_withSig(o), ...r);
        if (_stream) helpers.chatStream = (o, ...r) => _stream(_withSig(o), ...r);
        if (_term)   helpers.terminal   = (cmd, o = {}, ...r) => _term(cmd, _withSig(o), ...r);
      }
      _liveHelpers = helpers; _liveViz = helpers.viz;   // expose to the self-deriving helper menu
      _auditHelperMenu(helpers);
      for (const [name, { fn: override }] of Object.entries(helperOverrides)) {
        if (name.startsWith("viz.")) {
          helpers.viz[name.slice(4)] = override;
        } else if (name in helpers) {
          helpers[name] = override;
        }
      }
      const result = await fn(shared, helpers, helpers, cellConsole);
      if (epoch !== runEpoch) return;
      s.output = result;

      // Render the return value, de-duplicated against the stream view: when the return is a string already most of what streamed, the redundant pre is omitted (no "same content shown twice" after a cell streams a reply then returns it).
      // Objects and arrays go through highlight.js.
      const renderResultPre = (val) => _appendCellReturn(outEl, val, "cf-panel-output-pre");
      if (result !== undefined) {
        const streamedText = (streamEl.textContent || "")
          .replace(/── call \d+ ──/g, "")
          .trim();
        const resultText = typeof result === "string" ? result.trim() : "";
        const isRedundant = streamedText.length > 60 && resultText.length > 60 &&
                            (streamedText === resultText
                             || streamedText.includes(resultText)
                             || resultText.includes(streamedText));
        if (!isRedundant) renderResultPre(result);
      }

      // Surface fresh state keys the cell just wrote, so inputs and computed values stay visible without expanding the results details. Shows the first ~80 chars per key.
      if (overviewEl) {
        const freshKeys = Object.keys(shared).filter(k =>
          !k.startsWith("__") && !stateKeysBefore.has(k));
        if (freshKeys.length) {
          const rows = freshKeys.slice(0, 6).map(k => {
            const v = shared[k];
            let preview;
            if (typeof v === "string") preview = v.slice(0, 120) + (v.length > 120 ? "…" : "");
            else if (typeof v === "number" || typeof v === "boolean") preview = String(v);
            else if (Array.isArray(v))  preview = "[" + v.length + " items]";
            else if (v && typeof v === "object") {
              const keys = Object.keys(v);
              preview = "{ " + keys.slice(0, 5).join(", ") + (keys.length > 5 ? ", …" : "") + " }";
            } else preview = String(v);
            return `<div class="cf-overview-row"><span class="cf-overview-key">state.${k}</span><span class="cf-overview-val">${escapeHtml(preview)}</span></div>`;
          }).join("");
          overviewEl.innerHTML = `<div class="cf-overview-label">wrote into state</div>${rows}`;
        }
      }

      // A clean run wipes the error marks a previous failed run left, so a fixed cell stops showing the old red line instead of accumulating marks.
      if (s.cm) _clearCMErrs(s.cm);
      setStatus(nodeId, "complete");
      if (metaEl) {
        const dt = ((performance.now() - t0) / 1000).toFixed(2);
        metaEl.textContent = "done in " + dt + "s";
        metaEl.className = "cf-det-meta ok";
      }
    } catch (e) {
      if (epoch !== runEpoch) return;
      // A Stop press aborts the run; show it as stopped, not a red code error.
      if (runAC && runAC.signal.aborted) {
        setStatus(nodeId, "idle");
        if (metaEl) { metaEl.textContent = "stopped"; metaEl.className = "cf-det-meta"; }
        flowEdgesInto(nodeId, false);
        throw e;
      }
      if (!e.__courseHelperErrorLogged) {
        const err = document.createElement("div");
        err.className = "cf-panel-error";
        err.textContent = "✗ " + (e.name || "Error") + ": " + e.message;
        outEl.appendChild(err);
      }
      // Surface where it failed: map the stack to a CodeMirror line, mark it, open the code dropdown, and append a Debug-info panel (snippet plus stack).
      const _ep = _parseErrLine(e);
      const _codeForErr = (s.cm ? s.cm.getValue() : s.code) || "";
      if (_ep !== null) {
        const _cm = ensureCM(nodeId);
        if (_cm) {
          _clearCMErrs(_cm); _markCMErr(_cm, _ep);
          const _cd = panel.querySelector(".cf-panel-code-det");
          if (_cd && !_cd.open) _cd.open = true;
          setTimeout(() => { try { _cm.refresh(); _cm.scrollIntoView({ line: _ep.cmLine, ch: 0 }, 100); } catch (_) {} }, 60);
        }
      }
      outEl.appendChild(_buildDebugDet(e, _codeForErr, _ep));
      setStatus(nodeId, "error");
      if (metaEl) { metaEl.textContent = "error"; metaEl.className = "cf-det-meta err"; }
      flowEdgesInto(nodeId, false);
      throw e;
    } finally {
      flowEdgesInto(nodeId, false);
    }
  }

  function setStatus(nodeId, status) {
    ns[nodeId].status = status;
    const card  = canvas.querySelector(`.cf-node[data-id="${nodeId}"]`);
    const panel = panelsHost.querySelector(`.cf-panel[data-id="${nodeId}"]`);
    [card, panel].forEach(el => {
      if (!el) return;
      el.classList.remove("running", "complete", "error");
      if (status !== "idle") el.classList.add(status);
      el.querySelectorAll("[data-status]").forEach(d => {
        d.className = (el === card ? "cf-node-status-dot " : "cf-panel-status-dot ") + status;
      });
    });
  }

  function flowEdgesInto(nodeId, on) {
    svg.querySelectorAll(`path.cf-edge[data-to="${nodeId}"], path.cf-edge[data-from="${nodeId}"]`).forEach(p => {
      if (on) p.classList.add("flowing"); else p.classList.remove("flowing");
    });
  }

  wrap.querySelector(".cf-btn-run").addEventListener("click", async () => {
    if (running) { stopRun(); return; }   // the button is "⏹ Stop" mid-run
    const epoch = beginRun();
    statusBar.textContent = ""; statusBar.className = "cf-status-bar";
    for (const n of nodes) setStatus(n.id, "idle");
    for (const k of Object.keys(shared)) delete shared[k];
    let ran = 0;

    try {
      for (const node of nodes) {
        if (runAC.signal.aborted) break;
        await runNode(node.id);
        if (epoch !== runEpoch) return;
        ran++;
      }
      if (runAC && runAC.signal.aborted) {
        setFlowState("stopped");
        statusBar.textContent = "⏹ stopped after " + ran + " of " + nodes.length + " nodes";
        statusBar.className = "cf-status-bar";
      } else {
        setFlowState("succeeded");
        statusBar.textContent = "✓ ran " + nodes.length + " nodes";
        statusBar.className = "cf-status-bar ok";
      }
    } catch (e) {
      if (epoch !== runEpoch) return;
      if (runAC && runAC.signal.aborted) {
        setFlowState("stopped");
        statusBar.textContent = "⏹ stopped after " + ran + " of " + nodes.length + " nodes";
        statusBar.className = "cf-status-bar";
      } else {
        setFlowState("failed");
        const failedNode = nodes[ran];
        statusBar.textContent = "✗ stopped at " + (failedNode?.title || failedNode?.id || "failed step");
        statusBar.className = "cf-status-bar err";
      }
    } finally {
      if (epoch === runEpoch) endRun();
    }
  });

  wrap.querySelector(".cf-btn-reset").addEventListener("click", () => {
    if (running) { runEpoch++; stopRun(); endRun(); }
    for (const node of nodes) {
      ns[node.id].code = node.code || "";
      if (ns[node.id].cm) ns[node.id].cm.setValue(node.code || "");
      setStatus(node.id, "idle");
      const panel = panelsHost.querySelector(`.cf-panel[data-id="${node.id}"]`);
      panel.querySelector(".cf-panel-stream").textContent = "";
      panel.querySelector(".cf-panel-log").innerHTML = "";
      panel.querySelector(".cf-panel-output").innerHTML = "";
    }
    for (const k of Object.keys(shared)) delete shared[k];
    setFlowState("reset");
    statusBar.textContent = "reset";
    statusBar.className = "cf-status-bar";
  });

}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}

// JSON.stringify replacer that survives what a live cell logs (circular references, bigints, functions).
// Without it a single such value would throw and the whole log line would silently fall back to text.
function _logReplacer() {
  const seen = new WeakSet();
  return function (k, v) {
    if (typeof v === "bigint") return v.toString();
    if (typeof v === "function") return "[Function]";
    if (v && typeof v === "object") { if (seen.has(v)) return "[Circular]"; seen.add(v); }
    return v;
  };
}

// Append one log line to `logEl`. A dict or list is pretty-printed and syntax-highlighted (highlight.js when present, indented JSON as fallback), while plain values stay text.
// Shared by every log surface (canvas nodes, captured console, run cells); returns the created
// element so learner code can update an in-place status line consistently in both cell types.
function appendLogLine(logEl, args, opts) {
  opts = opts || {};
  const div = document.createElement("div");
  div.className = opts.cls || "cf-panel-log-line";
  if (opts.color) div.style.color = opts.color;
  const plain = [];
  if (opts.prefix) { const p = document.createElement("span"); p.textContent = opts.prefix; div.appendChild(p); plain.push(opts.prefix.trim()); }

  args.forEach((a, i) => {
    if (a && typeof a === "object") {
      let json = null;
      try { json = JSON.stringify(a, _logReplacer(), 2); } catch (_) { json = null; }
      if (json != null) {
        const pre = document.createElement("pre");
        pre.className = "cf-log-json";
        const code = document.createElement("code");
        code.className = "language-json hljs";
        code.textContent = json;
        pre.appendChild(code);
        div.appendChild(pre);
        if (typeof window.hljs !== "undefined") { try { window.hljs.highlightElement(code); } catch (_) {} }
        plain.push(json);
        return;
      }
    }
    const span = document.createElement("span");
    span.textContent = (i ? " " : "") + String(a);
    div.appendChild(span);
    plain.push(String(a));
  });
  logEl.appendChild(div);
  div.dataset.logText = plain.join(" ");
  return div;
}

function _docFor(name) {
  let fn = HELPER_FNS[name];
  if (!fn && name.startsWith("viz.") && typeof VIZ_BUILDERS !== "undefined") fn = VIZ_BUILDERS[name.slice(4)];
  if (typeof fn !== "function") return {};
  const m = fn.toString().match(/\/\*\s*@doc\b([\s\S]*?)\*\//);
  if (!m) return {};
  const body = m[1].trim();
  const i = body.indexOf("::");
  return i >= 0 ? { sig: body.slice(0, i).trim(), desc: body.slice(i + 2).trim() } : { desc: body };
}

// A helper's source, read live from the code so the menu can never drift.
// Top-level helpers come from Function.toString(), viz.* from VIZ_BUILDERS, and the value/native/closure ones from SPECIALS.
function _helperSource(name) {
  if (HELPER_FNS[name]) return HELPER_FNS[name].toString();
  if (name.startsWith("viz.")) {
    const k = name.slice(4);
    if (typeof VIZ_BUILDERS !== "undefined" && typeof VIZ_BUILDERS[k] === "function") return VIZ_BUILDERS[k].toString();
  }
  if (SPECIALS[name]) return SPECIALS[name].src;
  return "// (source unavailable)";
}

// The helpers a snippet of cell/node code actually uses, so a menu can scope to them.
// It scans for helpers.X (and the bare names run-cells inject, e.g. chat()), helpers.viz.X, `state`, and any `{ x } = helpers` destructure. Shared by mountCanvasFlow and mountRunCell.
function _deriveHelperAllow(code) {
  const src = String(code || ""), used = new Set();
  for (const k of Object.keys(HELPER_FNS)) {
    if (src.indexOf("helpers." + k) >= 0 || new RegExp("\\b" + k + "\\s*\\(").test(src)) used.add(k);
  }
  for (const k of ["fetch", "trace", "log", "signal"]) if (src.indexOf("helpers." + k) >= 0) used.add(k);
  if (typeof VIZ_BUILDERS !== "undefined") for (const k of Object.keys(VIZ_BUILDERS)) if (src.indexOf("viz." + k) >= 0) used.add("viz." + k);
  if (/\bstate\b/.test(src)) used.add("state");
  let m; const re = /\{([^}]*)\}\s*=\s*helpers\b/g;
  while ((m = re.exec(src))) m[1].split(",").forEach(s => { const nm = s.trim().split(":")[0].trim(); if (nm) used.add(nm); });
  return used;
}

// Categories group the live helper registry; they never define or filter the registry itself.
// Exporting the map lets the browser validator prove that a newly exposed helper cannot silently
// fall into an unreviewed bucket.
export const HELPER_CATEGORIES = Object.freeze([
    ["Shared state",            ["state"]],
    ["Model calls",             ["chat", "chatStream", "browserChatFetch"]],
    ["Model configuration",     [
      "getConfig", "getKey", "getModelApiBaseUrl", "setModelApiBaseUrl",
      "isDefaultModelApiBaseUrl", "mountModelEndpointProbe",
    ]],
    ["Web search",              ["webSearch", "instantAnswer", "formatSearchResults"]],
    ["Embeddings & similarity", ["embed", "cosineSim"]],
    ["Tokens & context",        ["contextWindow", "estimateTokens"]],
    ["Raw HTTP",                ["fetch", "fetchRetry"]],
    ["Launchable terminal",     ["terminal"]],
    ["OpenShell policy",        [
      "evalSandboxNetwork", "evalSandboxFs", "sandboxExec", "policyGet", "mountPolicyMap",
    ]],
    ["Course content",          [
      "coursePage", "coursePages", "mountFigures", "openFigureLightbox", "wireFigureZoom",
    ]],
    ["Live artifacts",          [
      "mountChatUI", "mountAgentChat", "mountConsole", "mountOpenClawCli", "mountKeyPanel",
    ]],
    ["Diagram strings",         ["diagramSVG", "ganttBarsSVG"]],
    ["OpenClaw gateway",        [
      "openclawBootstrapRequest", "openclawChat", "openclawLoopbackProbe",
      "openclawGatewayWsUrl",
      "refreshOpenClawGatewayToken", "getOpenClawConnection", "setOpenClawConnection",
      "filterOpenClawRuntimeNoise", "filterOpenClawRuntimeValue", "openclawMessageText",
      "openclawResultText",
    ]],
    ["Run control",             ["signal", "delay"]],
    ["Instrumentation",         ["trace", "log"]],
]);

function _helperUniverse(helperFns = HELPER_FNS, vizBuilders = VIZ_BUILDERS) {
  const vizNames = vizBuilders ? Object.keys(vizBuilders).map(k => "viz." + k) : [];
  return new Set(["state", "signal", ...Object.keys(helperFns), "fetch", "trace", "log", ...vizNames]);
}

export function helperMenuOrphans({ helperFns = HELPER_FNS, vizBuilders = VIZ_BUILDERS, categories = HELPER_CATEGORIES } = {}) {
  const universe = _helperUniverse(helperFns, vizBuilders);
  const categorized = new Set(categories.flatMap(([, names]) => names));
  for (const name of universe) if (name.startsWith("viz.")) categorized.add(name);
  return [...universe].filter(name => !categorized.has(name));
}

// Build the helper-menu rows by enumerating everything the runtime exposes, in a fixed order.
// The category map only groups; anything exposed but uncategorized remains visible under "Other"
// while the runtime validator fails the contribution that introduced it.
function _buildHelperRows(allow) {
  // `allow` (a Set of names) scopes the menu to the helpers a section uses; null or omitted shows everything.
  // The in-scope primitives (state, signal, fetch, trace, log) and viz.* builders always show; scoping is display-only, every helper stays injected, so a cell can call off-menu.
  const inScope = (n) => !allow || allow.has(n);
  const vizNames = typeof VIZ_BUILDERS !== "undefined" ? Object.keys(VIZ_BUILDERS).map(k => "viz." + k) : [];
  const universe = _helperUniverse();
  const out = [];
  const rowFor = (name) => ({ row: name, editable: name !== "state" && name !== "signal", extra: !inScope(name) });
  // Every row is emitted. Rows the section does not use are flagged extra (hidden until "show all"), and a section head is extra when all of its rows are.
  for (const [head, names] of HELPER_CATEGORIES) {
    const inU = names.filter(n => universe.has(n));
    if (!inU.length) continue;
    out.push({ sectionHead: head, extra: inU.every(n => !inScope(n)) });
    inU.forEach(n => out.push(rowFor(n)));
  }
  if (vizNames.length) {
    out.push({ sectionHead: "Visualization · <code>helpers.viz.*</code>", extra: vizNames.every(n => !inScope(n)) });
    vizNames.forEach(n => out.push(rowFor(n)));
  }
  const orphans = helperMenuOrphans();
  if (orphans.length) {
    console.warn("[helpers menu] uncategorized helpers (add to HELPER_CATEGORIES):", orphans);
    out.push({ sectionHead: "Other", extra: orphans.every(n => !inScope(n)) });
    orphans.forEach(n => out.push(rowFor(n)));
  }
  return out;
}

// ── runCell: editable in-page code sandbox with syntax highlighting ─────────
// Mounts an editable JS textarea. On Run, its contents execute in an async sandbox with chat, chatStream, log, clear, MODEL, ui, and schemas in scope (same semantics as the edx-track runner).
// Uses CodeMirror 5 when loaded, falling back to a plain textarea (offline lab).

// Call: mountRunCell("#cell-1", { code, schemas }). Each `schemas` entry becomes an editable JSON block passed to the sandboxed code as a named variable (e.g. CALC_SCHEMA); a parse error shows in place instead of running, so the student sees the actual message.
const _runCellAborts = new Map();
const _runCellState = {};

export function mountRunCell(targetSel, opts) {
  const target = typeof targetSel === "string" ? document.querySelector(targetSel) : targetSel;
  if (!target) return null;
  const cellId = target.id || `cell-${Math.random().toString(36).slice(2, 8)}`;
  target.id = cellId;
  const code = opts.code || "";
  let jsBuffer = code;
  const runLabel = () => "▶ Run";
  const schemas = opts.schemas || {};
  const label = opts.label || "editable cell";
  const showSchemas = Object.keys(schemas).length > 0;
  const codeLines = Math.max(1, String(code).split("\n").length);
  const codeOpenAttr = opts.openCode === true ? " open" : "";
  const autoCollapseCode = opts.autoCollapseCode !== false && opts.openCode !== true;

  // Helpers tab, shown whenever a cell has helpers. Scoped to the helpers this cell's code uses, with a "show all" toggle and click-to-read-source.
  // It is the run-cell twin of the canvas menu, so a Try-it cell's helpers are as discoverable as a canvas node's.
  const _rcAllow = opts.helpers ? new Set(opts.helpers) : _deriveHelperAllow(code);
  const _rcRows = _buildHelperRows(_rcAllow);
  const _rcHasHelpers = _rcRows.some(r => !r.sectionHead && !r.extra);
  const _rcExtraN = _rcRows.filter(r => r.extra && !r.sectionHead).length;
  const _rcHelpersHTML = !_rcHasHelpers ? "" : `
      <details class="cf-helpers rc-helpers" style="border-top:1px solid var(--bd);border-bottom:1px solid var(--bd);">
        <summary>
          <span class="cf-helpers-chip">helpers</span>
          <span class="cf-helpers-sig">in scope for this cell. Click a row to read its source</span>
          <span class="cf-helpers-meta"></span>
        </summary>
        <div class="cf-helpers-scroll">
        ${_rcExtraN ? `<button type="button" class="cf-helpers-showall" aria-expanded="false" style="margin:6px 0;background:transparent;border:1px solid var(--bd);color:var(--td);border-radius:5px;padding:3px 10px;font-family:var(--mono);font-size:.74rem;cursor:pointer;">+ show all ${_rcExtraN} more helpers</button>` : ""}
        <table class="cf-helpers-table"><tbody>
          ${_rcRows.map(r => {
            if (r.sectionHead) return `<tr class="cf-helpers-section-head"${r.extra ? ' data-x="1" style="display:none"' : ''}><td colspan="2">${r.sectionHead}</td></tr>`;
            const _d = _docFor(r.row), _s = SPECIALS[r.row] || {};
            const sig = _d.sig || _s.sig || `<code>helpers.${r.row}(…)</code>`;
            const desc = _d.desc || _s.desc || "";
            return `<tr data-helper="${r.row}"${r.extra ? ' data-x="1" style="display:none"' : ''}><td>${sig}</td><td>${desc}</td></tr>
              <tr class="cf-helpers-source-row" data-helper-source="${r.row}" hidden><td colspan="2"><textarea class="cf-helpers-src-editor" data-src-for="${r.row}" spellcheck="false" readonly style="width:100%;min-height:120px;max-height:320px;font-family:ui-monospace,monospace;font-size:.78rem;"></textarea></td></tr>`;
          }).join("")}
        </tbody></table>
        </div>
      </details>`;

  // Outer card
  target.innerHTML = `
    <div class="rc-card cell-card">
      <div class="rc-head cell-head">
        <span class="rc-label">${label}</span>
        <span class="cf-det-chip cell-lang-chip rc-lang" data-lang-chip>JS</span>
        <span class="rc-lang-sub">javascript · editable · re-run</span>
        <span class="cell-spacer"></span>
        <span class="cell-actions">
          ${_cellBtnHTML("reset", "↺ Reset", "rc-reset", "Restore this cell's original code and clear its output")}
          ${_cellBtnHTML("run", runLabel(), "rc-run", "Run this cell")}
        </span>
      </div>
      ${opts.intro ? `<div class="cf-intro rc-intro">${escapeHtml(opts.intro)}</div>` : ""}
      ${_rcHelpersHTML}
      ${showSchemas ? `<details class="rc-schemas-det cell-schema-det"><summary><span class="cf-det-chip cf-det-chip-alt">schemas</span><span class="cf-det-sig">JSON · editable</span></summary><div class="rc-schemas"></div></details>` : ""}
      <details class="rc-code-det"${codeOpenAttr}>
        ${_cellLangSummaryHTML({ sig: "javascript · editable · " + codeLines + " lines", meta: codeOpenAttr ? "click to collapse" : "click to expand", metaAttr: "data-code-meta" })}
        <div class="rc-code-body cell-code-body">
          <button type="button" class="cf-code-copy rc-code-copy cell-code-copy" title="Copy current code" aria-label="Copy current code">⎘</button>
          <textarea class="rc-code" spellcheck="false"></textarea>
        </div>
      </details>
      <div class="rc-out cell-output-panel" role="status" aria-live="polite" aria-atomic="true">empty until you Run</div>
    </div>`;
  const setCellState = (state) => {
    target.dataset.state = state;
    target.setAttribute("aria-busy", state === "running" ? "true" : "false");
    const card = target.querySelector(".rc-card");
    if (card) card.dataset.state = state;
  };
  setCellState("ready");
  // Wire the helpers tab: "show all" toggle + click-a-row-to-read-its-source (read-only, highlighted).
  const _rcHelpers = target.querySelector(".rc-helpers .cf-helpers-table");
  if (_rcHelpers) {
    const _sa = target.querySelector(".rc-helpers .cf-helpers-showall");
    if (_sa) _sa.addEventListener("click", (e) => {
      e.stopPropagation();
      const on = _sa.getAttribute("aria-expanded") !== "true";
      _sa.setAttribute("aria-expanded", on ? "true" : "false");
      _rcHelpers.querySelectorAll("[data-x]").forEach(el => { el.style.display = on ? "" : "none"; });
      _sa.textContent = on ? "− show only this cell's helpers" : `+ show all ${_rcExtraN} more helpers`;
    });
    const rcHelpCM = {};   // read-only CodeMirror per helper source, created lazily on first open
    _rcHelpers.addEventListener("click", (ev) => {
      const tr = ev.target.closest("tr[data-helper]");
      if (!tr || ev.target.closest("tr.cf-helpers-source-row")) return;
      const name = tr.dataset.helper;
      const srcRow = _rcHelpers.querySelector(`tr[data-helper-source="${name}"]`);
      const wasOpen = srcRow && !srcRow.hidden;
      _rcHelpers.querySelectorAll("tr.cf-helpers-source-row").forEach(r => r.hidden = true);
      _rcHelpers.querySelectorAll("tr[data-helper]").forEach(r => r.classList.remove("selected"));
      if (wasOpen || !srcRow) return;
      const ta = srcRow.querySelector("textarea[data-src-for]");
      if (ta && !ta.dataset.filled) {
        ta.value = _helperSource(name); ta.dataset.filled = "1";
        // Use CodeMirror for large helpers; plain text remains readable if unavailable.
        if (typeof window.CodeMirror === "function") {
          rcHelpCM[name] = window.CodeMirror.fromTextArea(ta, {
            mode: "javascript", theme: "monokai", lineNumbers: true, lineWrapping: true,
            readOnly: true, viewportMargin: Infinity, tabSize: 2, indentUnit: 2,
          });
          rcHelpCM[name].setSize("100%", "auto");
        }
      }
      srcRow.hidden = false; tr.classList.add("selected");
      if (rcHelpCM[name]) setTimeout(() => rcHelpCM[name].refresh(), 30);   // re-layout after un-hide
    });
  }

  const ta = target.querySelector(".rc-code");
  ta.value = jsBuffer;
  // Auto-grow the textarea to fit its initial content height (fallback path).
  ta.style.height = "auto";
  ta.style.height = (Math.max(140, ta.scrollHeight + 6)) + "px";

  // CodeMirror upgrade: when the CDN script is loaded, turn the JS textarea into a syntax-highlighted editor that auto-grows with content.
  let cm = null;
  function attachCM(textarea, mode, opts = {}) {
    if (typeof window.CodeMirror !== "function") return null;
    const editor = window.CodeMirror.fromTextArea(textarea, {
      mode,
      theme: "monokai",
      lineNumbers: true,
      indentUnit: 2,
      tabSize: 2,
      indentWithTabs: false,
      lineWrapping: true,                 // wrap long lines instead of per-cell horizontal scroll
      viewportMargin: Infinity,           // render full content; no inner scrollbar
      extraKeys: {
        "Ctrl-Enter": () => run(),
        "Cmd-Enter":  () => run(),
        "Cmd-/":      _cmCommentToggle,
        "Ctrl-/":     _cmCommentToggle,
        "Tab":         e => e.execCommand("indentMore"),
        "Shift-Tab":   e => e.execCommand("indentLess"),
      },
      ...opts,
    });
    editor.setSize("100%", "auto");
    // Refresh once shortly after mount so layout settles even if the cell first renders in a hidden tab.
    setTimeout(() => editor.refresh(), 0);
    return editor;
  }
  cm = attachCM(ta, "javascript");

  // Optional schemas section: one editable JSON textarea per schema name.
  // Also upgraded to CodeMirror with json mode when available.
  const schemaTAs = {};
  const schemaEditors = {};
  if (showSchemas) {
    const wrap = target.querySelector(".rc-schemas");
    for (const [name, value] of Object.entries(schemas)) {
      const block = document.createElement("div");
      block.style.cssText = "padding:8px 14px;border-bottom:1px solid var(--bd);background:var(--e1);";
      block.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;font-family:ui-monospace,monospace;font-size:.74rem;color:var(--gs);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px;">
          <span>${name}</span>
          <span style="color:var(--tf);">json · editable · referenced as <code style="color:var(--gs);">${name}</code> inside the code below</span>
        </div>
        <textarea class="rc-schema" spellcheck="false"
          style="width:100%;min-height:80px;background:var(--e2,#0d0d0d);color:var(--tx,#e6edf3);border:1px solid var(--bd,#2a2a2a);border-radius:4px;outline:none;padding:8px 10px;
                 font-family:ui-monospace,monospace;font-size:.78rem;line-height:1.5;resize:vertical;"></textarea>`;
      wrap.appendChild(block);
      const sta = block.querySelector(".rc-schema");
      sta.value = JSON.stringify(value, null, 2);
      sta.style.height = "auto";
      sta.style.height = (Math.max(80, sta.scrollHeight + 6)) + "px";
      schemaTAs[name] = sta;
      schemaEditors[name] = attachCM(sta, { name: "javascript", json: true });
    }
    wrap.lastElementChild.style.borderBottom = "none";
  }

  const out = target.querySelector(".rc-out");
  // Reset out to a flex container that can hold structured blocks.
  out.innerHTML = "";
  out.style.padding = "0";
  out.style.cssText += "display:flex;flex-direction:column;gap:0;";
  function _emptyState(msg) {
    out.innerHTML = `<div style="padding:10px 14px;color:var(--tf);font-family:ui-monospace,monospace;font-size:.82rem;">${msg}</div>`;
  }
  _emptyState("empty until you Run");
  const btn = target.querySelector(".rc-run");
  const resetBtn = target.querySelector(".rc-reset");
  const copyBtn = target.querySelector(".rc-code-copy");
  const codeDet = target.querySelector(".rc-code-det");
  const schemaDet = target.querySelector(".rc-schemas-det");
  let runEpoch = 0;
  if (codeDet) codeDet.addEventListener("toggle", () => {
    if (codeDet.open && cm) setTimeout(() => cm.refresh(), 30);
  });
  if (schemaDet) schemaDet.addEventListener("toggle", () => {
    if (!schemaDet.open) return;
    setTimeout(() => Object.values(schemaEditors).forEach(ed => { try { ed && ed.refresh(); } catch (_) {} }), 30);
  });
  if (copyBtn) copyBtn.addEventListener("click", async () => {
    const text = cm ? cm.getValue() : ta.value;
    try {
      await navigator.clipboard.writeText(text);
      copyBtn.textContent = "✓";
      setTimeout(() => { copyBtn.textContent = "⎘"; }, 900);
    } catch (_) {
      copyBtn.textContent = "select";
      if (codeDet && !codeDet.open) codeDet.open = true;
      setTimeout(() => ta.focus(), 40);
    }
  });
  function resetCell() {
    runEpoch++;
    const live = _runCellAborts.get(cellId);
    if (live) live.abort();
    jsBuffer = code;
    if (cm) { cm.setValue(code); _clearCMErrs(cm); }
    else ta.value = code;
    ta.style.height = "auto";
    ta.style.height = (Math.max(140, ta.scrollHeight + 6)) + "px";

    for (const [name, value] of Object.entries(schemas)) {
      const next = JSON.stringify(value, null, 2);
      if (schemaEditors[name]) schemaEditors[name].setValue(next);
      if (schemaTAs[name]) schemaTAs[name].value = next;
    }

    _emptyState("reset. empty until you Run");
    setCellState("reset");
    btn.textContent = runLabel();
    btn.onclick = run;
  }
  if (resetBtn) resetBtn.addEventListener("click", resetCell);

  async function run() {
    if (_runCellAborts.get(cellId)) { _runCellAborts.get(cellId).abort(); }
    const ac = new AbortController();
    const epoch = ++runEpoch;
    _runCellAborts.set(cellId, ac);
    setCellState("running");
    btn.textContent = "⏹ Stop";
    btn.onclick = () => ac.abort();
    out.innerHTML = "";
    if (autoCollapseCode && codeDet && codeDet.open) codeDet.open = false;

    // Parse schemas first; if any fails, show the parse error and bail.
    const schemaVars = {};
    for (const [name, sta] of Object.entries(schemaTAs)) {
      // Read from CodeMirror if present; otherwise from the textarea.
      const text = schemaEditors[name] ? schemaEditors[name].getValue() : sta.value;
      try { schemaVars[name] = JSON.parse(text); }
      catch (e) {
        const err = document.createElement("div");
        err.style.cssText = "padding:10px 14px;color:var(--err);font-family:ui-monospace,monospace;font-size:.82rem;white-space:pre-wrap;";
        err.textContent = `schema parse error in ${name}: ${e.message}\n\nFix the JSON in the schema block above, then Run again.`;
        out.appendChild(err);
        setCellState("failed");
        btn.textContent = runLabel(); btn.onclick = run;
        return;
      }
    }

    // Structured log API.
    // CanvasFlow and RunCell share text, JSON, details, HTML, SVG, drawing, and clear operations.
    // Strings stay plain; objects render as highlighted JSON.
    let outputCount = 0;
    const counted = (el) => { outputCount++; return el; };
    const _appendText = (text, color = "") => counted(_appendCellText(out, text, "cell-log-line", color));
    const _appendJson = (obj, label = null) => counted(_appendCellJson(out, obj, label));
    const log = (...args) => {
      let last = null;
      const texts = [];
      const flush = () => { if (texts.length) { last = _appendText(texts.join(" ")); texts.length = 0; } };
      args.forEach(a => {
        if (a && typeof a === "object") { flush(); last = _appendJson(a); }
        else texts.push(String(a));
      });
      flush();
      return last;
    };
    _installStructuredLog(log, out, counted);
    const clear = () => { out.innerHTML = ""; outputCount = 0; };
    log.clear = clear;


    if (cm) _clearCMErrs(cm);
    try {
      // `helpers` mirrors the canvas-cell convention (helpers.embed, helpers.log, helpers.mountChatUI) so a run-cell can mount a full artifact, not only call chat().
      // The bare names below stay for back-compat with older cells.
      const helpers = Object.assign({}, HELPER_FNS, { log, clear, fetch: (...a) => window.fetch(...a) });
      helpers.signal = ac.signal;
      const runDelay = helpers.delay;
      helpers.delay = (ms, signal = ac.signal) => runDelay(ms, signal);
      const argNames = ["chat", "chatStream", "webSearch", "instantAnswer", "formatSearchResults", "log", "clear", "MODEL", "REASONING_MODEL", "AbortSignal", "helpers", "state",       ...Object.keys(schemaVars)];
      const argVals  = [chat,    chatStream,   webSearch,   instantAnswer,   formatSearchResults,   log,   clear,   null,    REASONING_MODEL,  ac.signal,    helpers,   _runCellState, ...Object.values(schemaVars)];
      // Read from CodeMirror if present; otherwise from the textarea.
      const codeText = cm ? cm.getValue() : ta.value;
      jsBuffer = codeText;  // preserve the student's edits across re-runs/toggles
      const fn = new Function(...argNames,
        `"use strict"; return (async () => {\n${codeText}\n})();`);
      const result = await fn(...argVals);
      if (!ac.signal.aborted) {
        if (result === undefined && outputCount === 0) {
          _emptyState("(completed; no log output and no returned value)");
        } else if (result !== undefined && typeof result === "object" && result !== null) {
          _appendJson(result, "returned value");
        } else if (result !== undefined) {
          counted(_appendCellHeading(out, "returned value"));
          _appendText(String(result));
        }
        setCellState("succeeded");
      }
    } catch (e) {
      if (epoch !== runEpoch) {
        return;
      } else if (ac.signal.aborted) {
        _emptyState("⏹ stopped");
        setCellState("stopped");
      } else {
        const err = document.createElement("div");
        err.className = "cell-runtime-error";
        err.style.cssText = "padding:10px 14px;color:var(--err);font-family:ui-monospace,monospace;font-size:.82rem;white-space:pre-wrap;";
        err.textContent = "✗ " + (e.name || "Error") + ": " + e.message;
        out.appendChild(err);
        // Mark the failing line in the editor and show a Debug-info panel (code snippet plus filtered stack), mirroring the canvas-cell behaviour.
        const _ep = _parseErrLine(e);
        const _rcCode = cm ? cm.getValue() : ta.value;
        if (codeDet && !codeDet.open) codeDet.open = true;
        if (_ep !== null && cm) {
          _clearCMErrs(cm); _markCMErr(cm, _ep);
          setTimeout(() => { try { cm.refresh(); cm.scrollIntoView({ line: _ep.cmLine, ch: 0 }, 100); } catch (_) {} }, 60);
        }
        const dbg = _buildDebugDet(e, _rcCode, _ep);
        dbg.style.cssText = "margin:0 14px 8px;border-radius:0 0 5px 5px;";
        out.appendChild(dbg);
        setCellState("failed");
      }
    } finally {
      if (_runCellAborts.get(cellId) === ac) _runCellAborts.delete(cellId);
      if (epoch === runEpoch) {
        btn.textContent = runLabel();
        btn.onclick = run;
      }
    }
  }
  btn.onclick = run;

  // autorun: run once on mount so a cell that renders an artifact shows it without a click.
  // The student still sees and can edit the code, then Run to re-render.
  if (opts.autorun) run();
  return { run, ta, out, schemaTAs };
}
