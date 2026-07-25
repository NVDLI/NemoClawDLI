// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// LangChain.js loader and helpers for 01b/02c.
// Holds the COURSE_PAGES registry, coursePage/coursePages, and the context + token estimators.

// ── Course content as a tool ─────────────────────────────────────────────────
// The short course's own pages, keyed by file id.
// Single source of truth for the 01b module dropdown and the read_course_page tool's enum.
export const COURSE_PAGES = [
  { id: "overview",          title: "0 · Course overview (home)" },
  { id: "01a-loop",          title: "1a · The Agent (the loop)" },
  { id: "01b-react",         title: "1b · The ReAct Loop" },
  { id: "01c-tools",         title: "1c · Tools at Scale" },
  { id: "02a-routing",       title: "2a · Workflows & routing" },
  { id: "02b-rag",           title: "2b · The Index Agent (RAG)" },
  { id: "02c-deep",          title: "2c · Deep Agents" },
  { id: "03a-kickstart",     title: "3a · Kickstart" },
  { id: "03b-openclaw",      title: "3b · The OpenClaw Agent" },
  { id: "03c-always-on",     title: "3c · The Always-On Agent" },
  { id: "04a-safety",        title: "4a · The OpenShell Sandbox" },
  { id: "04b-modern-clis",   title: "4b · Modern CLI Agents" },
  { id: "04c-going-further", title: "4c · Going Further" },
];

// Public browser modules learners can inspect through the Course Assistant.
// Keep this allowlist explicit.
// Source access can explain the course without becoming a same-origin file reader.
const COURSE_RUNTIME_FILES = [
  ["_shared.js", "course API surface and browser model helpers"],
  ["_canvas.js", "RunCell and CanvasFlow rendering/runtime"],
  ["_chat.js", "chat, ReAct, streaming, and compaction UI"],
  ["_course_assistant.js", "Course Assistant sessions and course-reading tools"],
  ["_langchain.js", "course-page, source, and token helpers"],
  ["_learning.js", "Guided disclosure behavior"],
  ["_openclaw.js", "OpenClaw gateway and probe controls"],
  ["_openclaw_cli.js", "OpenClaw CLI gateway, branches, and command discovery"],
  ["_openshell.js", "OpenShell policy and terminal helpers"],
  ["_rag.js", "retrieval helpers"],
  ["_glossary.js", "curated-material search"],
  ["_diagram.js", "diagram grammar"],
  ["_figures.js", "course figures and lightbox behavior"],
  ["_viz.js", "cell visualization builders"],
  ["_keypanel.js", "API-key setup UI"],
  ["_locale.js", "language menu and locale routing"],
];

function _courseId(pageId) {
  return String(pageId || "").trim().replace(/\.html$/, "");
}

export function resolveCoursePageUrl(pageId, pageHref = globalThis.location?.href) {
  if (!pageHref) throw new Error("course page URL requires a browser location");
  const id = _courseId(pageId);
  const courseDirectory = new URL("./", pageHref);
  return new URL(id === "overview" ? "../index.html" : id + ".html", courseDirectory).href;
}

const COURSE_HTML_CACHE = new Map();
async function _courseHtml(pageId) {
  const id = _courseId(pageId);
  if (!COURSE_PAGES.some(page => page.id === id)) return { id, html: "", error: `(unknown page "${id}")` };
  if (!COURSE_HTML_CACHE.has(id)) COURSE_HTML_CACHE.set(id, (async () => {
    const response = await fetch(resolveCoursePageUrl(id), { credentials: "same-origin" });
    if (!response.ok) throw new Error(`course source "${id}" → ${response.status}`);
    return { id, html: await response.text(), error: "" };
  })());
  try { return await COURSE_HTML_CACHE.get(id); }
  catch (error) { COURSE_HTML_CACHE.delete(id); throw error; }
}

function _courseCodeArtifacts(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const artifacts = [{
    id: "page-html",
    kind: "page document",
    summary: "complete course-page HTML",
    lines: html.split("\n").length,
    source: html,
  }];
  doc.querySelectorAll('script[type="text/plain"][id]').forEach(script => {
    const source = script.textContent.trim();
    if (source) artifacts.push({
      id: script.id,
      kind: "lesson artifact",
      summary: `script#${script.id}`,
      lines: source.split("\n").length,
      source,
    });
  });
  let moduleNumber = 0;
  doc.querySelectorAll('script[type="module"]:not([src])').forEach(script => {
    const source = script.textContent.trim();
    if (!source) return;
    moduleNumber += 1;
    const mounts = [...source.matchAll(/\b(mount[A-Z][A-Za-z0-9_]*)\s*\(/g)].map(match => match[1]);
    const imports = [...source.matchAll(/from\s+["']([^"']+)["']/g)].map(match => match[1]);
    const signals = [...new Set([...mounts, ...imports])].slice(0, 6);
    artifacts.push({
      id: `module-${moduleNumber}`,
      kind: "page module",
      summary: signals.join(", ") || `inline module ${moduleNumber}`,
      lines: source.split("\n").length,
      source,
    });
  });
  return artifacts;
}

export async function courseCodeArtifacts(pageId) {
  const page = await _courseHtml(pageId);
  if (page.error) return [];
  return _courseCodeArtifacts(page.html).map(({ source: _source, ...metadata }) => metadata);
}

export async function courseCode(pageId, artifactId) {
  const page = await _courseHtml(pageId);
  if (page.error) return page.error;
  const artifacts = _courseCodeArtifacts(page.html);
  const artifact = artifacts.find(item => item.id === String(artifactId || "").trim());
  if (!artifact) {
    return `(unknown code artifact "${artifactId}" on ${page.id}. Choose one of: ${artifacts.map(item => item.id).join(", ") || "none"})`;
  }
  return `// Course source: ${page.id} · ${artifact.id} · ${artifact.summary}\n\n${artifact.source}`;
}

export function courseRuntimeFiles() {
  return COURSE_RUNTIME_FILES.map(([file, summary]) => ({ file, summary }));
}

export async function courseRuntimeSource(file) {
  const safe = String(file || "").trim().replace(/^scripts\//, "");
  const entry = COURSE_RUNTIME_FILES.find(([name]) => name === safe);
  if (!entry) return `(unknown runtime file "${file}". Choose one of: ${COURSE_RUNTIME_FILES.map(([name]) => name).join(", ")})`;
  const response = await fetch("scripts/" + safe, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`course runtime source "${safe}" → ${response.status}`);
  return `// Course runtime source: scripts/${safe} · ${entry[1]}\n\n${await response.text()}`;
}

// Convert a course page's HTML to markdown a model can ingest.
// Keep the prose (headings, paragraphs, lists, code, callouts).
// Drop the chrome (nav, scripts, SVGs, interactive canvas widgets).
function _htmlToMarkdown(html) {
  const doc = new DOMParser().parseFromString(html, "text/html");
  const root = doc.querySelector("main") || doc.body;
  if (!root) return "";
  root.querySelectorAll(
    "script,style,noscript,svg,.topbar,#nav,#journey-map,.key-pill,.foot-nav," +
    ".references,.claw-probe,.gw-panel,[id^='cell-'],[id^='gw-'],[id^='bench-']," +
    "[id^='probe-'],[id^='fig-'],[id$='-recover']"
  ).forEach(e => e.remove());

  const inline = (el) => {
    let s = "";
    el.childNodes.forEach(n => {
      if (n.nodeType === 3) { s += n.textContent; return; }
      if (n.nodeType !== 1) return;
      const t = n.tagName.toLowerCase();
      if (t === "code") s += "`" + n.textContent + "`";
      else if (t === "strong" || t === "b") s += "**" + inline(n) + "**";
      else if (t === "em" || t === "i") s += "*" + inline(n) + "*";
      else if (t === "br") s += "\n";
      else s += inline(n);
    });
    return s;
  };
  const clean = (s) => s.replace(/[ \t]+/g, " ").replace(/ *\n */g, "\n").trim();

  const out = [];
  const walk = (el) => {
    el.childNodes.forEach(n => {
      if (n.nodeType !== 1) return;
      const t = n.tagName.toLowerCase();
      if (/^h[1-6]$/.test(t)) out.push("\n" + "#".repeat(+t[1]) + " " + clean(inline(n)));
      else if (t === "p") { const x = clean(inline(n)); if (x) out.push(x); }
      else if (t === "ul" || t === "ol") {
        n.querySelectorAll(":scope > li").forEach(li => { const x = clean(inline(li)); if (x) out.push("- " + x); });
      }
      else if (t === "pre") out.push("```\n" + n.textContent.trim() + "\n```");
      else if (t === "blockquote" || (n.classList && n.classList.contains("callout"))) {
        const x = clean(inline(n)); if (x) out.push("> " + x.replace(/\n/g, "\n> "));
      }
      else walk(n);
    });
  };
  walk(root);
  // No truncation: the agent reads the whole page.
  // Length is surfaced as a context-budget readout in the artifact, not silently clipped here.
  return out.join("\n\n").replace(/\n{3,}/g, "\n\n").trim();
}

export async function coursePage(pageId) {
  /* @doc <code>helpers.coursePage(id)</code> returns one course page's prose as markdown.
       <code>id</code> is a file id like <code>"01b-react"</code> (list them with <code>helpers.coursePages()</code>); same-origin fetch, no key.
       Wire it as the body of a <code>read_course_page</code> tool to ground answers in real content. */
  const id = _courseId(pageId);
  if (!COURSE_PAGES.some(p => p.id === id)) {
    return `(unknown page "${id}". Choose one of: ${COURSE_PAGES.map(p => p.id).join(", ")})`;
  }
  // "overview" is the course home, one level up from the page directory.
  // It carries the global map, what-you'll-build, and what-it-runs-on.
  // Read it for course-wide questions rather than guessing at a single module page.
  const page = await _courseHtml(id);
  const html = page.html;
  const doc = new DOMParser().parseFromString(html, "text/html");
  const md = _htmlToMarkdown(html);
  const title = doc.querySelector("h1")?.textContent.replace(/\s+/g, " ").trim()
    || (COURSE_PAGES.find(p => p.id === id) || {}).title || id;
  return `# ${title}  (course page: ${id})\n\n${md}`;
}

// Advertised context windows for the models the artifacts expose.
// The chat uses these to show how full the window is and warn before it overflows.
// Both Nemotron-3 models ship a 256K window.
export const CONTEXT_WINDOWS = {
  "nvidia/nemotron-3-nano-30b-a3b":    262144,
  "nvidia/nemotron-3-super-120b-a12b": 262144,
};
export function contextWindow(model) {
  /* @doc <code>helpers.contextWindow(model)</code> returns a model's advertised context-window size in tokens.
       It drives the artifact's context-budget readout, and falls back to 131072 for unknown models. */
  return CONTEXT_WINDOWS[model] || 131072;
}
// Cheap pre-flight token estimate (about 4 chars/token) before a turn is sent.
// The authoritative count comes back in usage_metadata afterward.
export function estimateTokens(textOrMessages) {
  /* @doc <code>helpers.estimateTokens(textOrMessages)</code> roughly estimates tokens (about 4 chars/token) for a string or an array of <code>{content}</code> messages.
       Use it for a pre-flight check; the authoritative count is the model's <code>usage_metadata</code>. */
  const s = Array.isArray(textOrMessages)
    ? textOrMessages.map(m => (typeof m === "string" ? m : (m && m.content) || "")).join("\n")
    : String(textOrMessages || "");
  return Math.ceil(s.length / 4);
}

export function coursePages() {
  /* @doc <code>helpers.coursePages()</code> returns the page list as <code>[{ id, title }]</code>.
       It is the single source for a module menu or a <code>read_course_page</code> tool's <code>enum</code>. */
  return COURSE_PAGES.map(p => ({ ...p }));
}
