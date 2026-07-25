// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Page-aware ReAct assistant. Shared chrome mounts it lazily in the page language.
import { mountAgentChat } from "./_chat.js";
import {
  courseCode, courseCodeArtifacts, coursePage, coursePages,
  courseRuntimeFiles, courseRuntimeSource,
} from "./_langchain.js";

const MODELS = [
  { id: "nvidia/nemotron-3-super-120b-a12b", label: "Nemotron Super 120B · recommended" },
  { id: "nvidia/nemotron-3-nano-30b-a3b", label: "Nemotron Nano 30B · fast" },
];
const ASSISTANT_WIDTH_KEY = "nemoclaw_course_assistant_width_v1";
const ASSISTANT_SESSIONS_KEY = "nemoclaw_course_assistant_sessions_v1";
const MAX_ASSISTANT_SESSIONS = 12;
const MAX_SESSION_HISTORY_CHARS = 100000;
const MAX_SESSION_ACTIVITY_CHARS = 20000;
const MAX_ARTIFACT_FIELD_CHARS = 40000;

function randomId(prefix = "") {
  if (typeof crypto.randomUUID === "function") return prefix + crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return prefix + [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
}

function newSession(page = null) {
  const now = Date.now();
  return {
    id: randomId("session-"),
    title: "New session", manualTitle: false,
    pageId: page?.id || "", pageTitle: page?.title || "",
    createdAt: now, updatedAt: now, history: [], activity: "", artifact: null,
  };
}

function cleanHistory(items) {
  const normalized = (Array.isArray(items) ? items : [])
    .filter(item => item && ["system", "user", "assistant"].includes(item.role) && typeof item.content === "string")
    .slice(-40)
    .map(item => ({ role: item.role, content: item.content.slice(0, 60000) }));
  const summary = normalized.filter(item => item.role === "system").at(-1);
  const kept = [], summaryChars = summary ? Math.min(20000, summary.content.length) : 0;
  let remaining = MAX_SESSION_HISTORY_CHARS - summaryChars;
  for (let index = normalized.length - 1; index >= 0 && remaining > 0; index -= 1) {
    const item = normalized[index];
    if (item === summary) continue;
    const content = item.content.slice(0, remaining);
    if (content) { kept.push({ role: item.role, content }); remaining -= content.length; }
  }
  kept.reverse();
  if (summary) kept.unshift({ role: "system", content: summary.content.slice(0, summaryChars) });
  return kept;
}

function cleanArtifact(value) {
  if (!value || typeof value !== "object") return null;
  return {
    title: String(value.title || "Browser artifact").slice(0, 96),
    html: String(value.html || "").slice(0, MAX_ARTIFACT_FIELD_CHARS),
    javascript: String(value.javascript || "").slice(0, MAX_ARTIFACT_FIELD_CHARS),
    updatedAt: Number(value.updatedAt || Date.now()),
  };
}

function cleanActivity(value) {
  return String(value || "").slice(-MAX_SESSION_ACTIVITY_CHARS);
}

export function loadCourseAssistantStore(storage = localStorage) {
  let parsed = null;
  try { parsed = JSON.parse(storage.getItem(ASSISTANT_SESSIONS_KEY) || "null"); } catch (_) {}
  const sessions = (parsed && Array.isArray(parsed.sessions) ? parsed.sessions : []).map(item => ({
    id: String(item.id || ""), title: String(item.title || "New session").slice(0, 72),
    manualTitle: item.manualTitle === true,
    pageId: String(item.pageId || "").slice(0, 80), pageTitle: String(item.pageTitle || "").slice(0, 160),
    createdAt: Number(item.createdAt || Date.now()), updatedAt: Number(item.updatedAt || Date.now()), history: cleanHistory(item.history), activity: cleanActivity(item.activity), artifact: cleanArtifact(item.artifact),
  })).filter(item => item.id).sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_ASSISTANT_SESSIONS);
  if (!sessions.length) sessions.push(newSession());
  const activeId = sessions.some(item => item.id === parsed?.activeId) ? parsed.activeId : sessions[0].id;
  return { version: 1, activeId, sessions };
}

export function saveCourseAssistantStore(store, storage = localStorage) {
  store.sessions = store.sessions.map(session => ({
    ...session, history: cleanHistory(session.history), activity: cleanActivity(session.activity), artifact: cleanArtifact(session.artifact),
  })).sort((a, b) => b.updatedAt - a.updatedAt).slice(0, MAX_ASSISTANT_SESSIONS);
  if (!store.sessions.some(item => item.id === store.activeId)) store.activeId = store.sessions[0]?.id || "";
  const serialized = JSON.stringify({ version: 3, activeId: store.activeId, sessions: store.sessions });
  storage.setItem(ASSISTANT_SESSIONS_KEY, serialized);
  return { chars: serialized.length, sessions: store.sessions.length };
}

function currentPage() {
  const id = (location.pathname.split("/").pop() || "index.html").replace(/\.html$/, "");
  return coursePages().find(page => page.id === id) || coursePages()[0];
}

function currentTitle(page) {
  return (document.querySelector("h1")?.textContent || page.title).replace(/\s+/g, " ").trim();
}

export function questionTargetsCurrentPage(value) {
  const text = String(value || "").normalize("NFC").toLowerCase();
  return /\b(?:this|current|open) page\b/.test(text)
    || /\besta página\b/.test(text)
    || /\bpágina (?:actual|abierta|atual)\b/.test(text);
}

export async function searchCoursePages(query, readPage = coursePage, catalog = coursePages()) {
  const terms = (String(query || "").toLowerCase().match(/[\p{L}\p{N}-]{3,}/gu) || []).slice(0, 8);
  if (!terms.length) return [];
  const docs = await Promise.all(catalog.map(async item => ({ item, body: await readPage(item.id) })));
  return docs.map(({ item, body }) => {
    const lower = body.toLowerCase();
    const score = terms.reduce((sum, term) => sum + lower.split(term).length - 1, 0);
    const hits = terms.map(term => lower.indexOf(term)).filter(index => index >= 0);
    const start = Math.max(0, (hits.length ? Math.min(...hits) : 0) - 180);
    return { id: item.id, title: item.title, score, excerpt: body.slice(start, start + 900) };
  }).filter(result => result.score > 0).sort((a, b) => b.score - a.score).slice(0, 4);
}

export function artifactFromMarkdown(markdown, title = "Generated browser artifact") {
  const raw = String(markdown || "");
  let html = "", javascript = "", css = "";
  const fences = raw.matchAll(/```([^\n`]*)\n([\s\S]*?)```/g);
  for (const match of fences) {
    const language = match[1].trim().toLowerCase();
    if (["html", "htm"].includes(language)) html += (html ? "\n" : "") + match[2].trim();
    else if (["javascript", "js"].includes(language)) javascript += (javascript ? "\n" : "") + match[2].trim();
    else if (language === "css") css += (css ? "\n" : "") + match[2].trim();
  }
  if (!html && !javascript) {
    const documentStart = raw.search(/(?:<!doctype\s+html[^>]*>\s*)?<html[\s>]/i);
    if (documentStart >= 0) {
      const documentEnd = raw.toLowerCase().lastIndexOf("</html>");
      html = raw.slice(documentStart, documentEnd >= documentStart ? documentEnd + 7 : raw.length).trim();
    }
  }
  if (css) html = `<style>\n${css}\n</style>\n` + html;
  return html || javascript ? cleanArtifact({ title, html, javascript, updatedAt: Date.now() }) : null;
}

export function artifactJavaScriptIssue(source) {
  const javascript = String(source || "");
  const issues = [];
  if (/\bimport\s*\(|\bimport\s+[\s\S]*?\bfrom\s*["']|\bfrom\s*["']\.\.?\//.test(javascript)) {
    issues.push("Imports are unavailable in the artifact sandbox. Use the injected course API.");
  }
  const badInputType = javascript.match(/\binputType\s*:\s*["']([^"']+)["']/);
  if (badInputType && !["query", "passage"].includes(badInputType[1])) {
    issues.push(`Artifact embed inputType must be "query" or "passage", not "${badInputType[1]}".`);
  }
  const helperNames = [...javascript.matchAll(/\bhelpers\.([A-Za-z_$][\w$]*)/g)].map(match => match[1]);
  const unsupportedHelpers = [...new Set(helperNames.filter(name => !["embed", "cosineSim"].includes(name)))];
  if (unsupportedHelpers.length) {
    issues.push(`Unsupported artifact helper(s): ${unsupportedHelpers.map(name => `helpers.${name}`).join(", ")}. Supported: helpers.embed, helpers.cosineSim.`);
  }
  if (/(?:^|[;\n])\s*(?:(?:const|let|var)\s+)?[A-Za-z_$][\w$]*\s*=\s*(?:course|helpers)\.embed\s*\(/m.test(javascript)) {
    issues.push("Artifact embedding is asynchronous. Assign its result with await course.embed(...) or await helpers.embed(...).");
  }
  return issues.join(" ");
}

function artifactTagEnd(source, start) {
  let quote = "";
  for (let index = start; index < source.length; index += 1) {
    const character = source[index];
    if (quote) {
      if (character === quote) quote = "";
    } else if (character === '"' || character === "'") quote = character;
    else if (character === ">") return index;
  }
  return -1;
}

function artifactTagAttributes(source, start, end) {
  const attributes = [];
  let cursor = start;
  while (cursor < end) {
    while (cursor < end && /[\s/]/.test(source[cursor])) cursor += 1;
    if (cursor >= end) break;
    const nameStart = cursor;
    while (cursor < end && !/[\s"'/>=]/.test(source[cursor])) cursor += 1;
    if (cursor === nameStart) return { attributes, malformed: true };
    const name = source.slice(nameStart, cursor).toLowerCase();
    while (cursor < end && /\s/.test(source[cursor])) cursor += 1;
    let value = "";
    if (source[cursor] === "=") {
      cursor += 1;
      while (cursor < end && /\s/.test(source[cursor])) cursor += 1;
      const quote = source[cursor] === '"' || source[cursor] === "'" ? source[cursor++] : "";
      const valueStart = cursor;
      if (quote) {
        while (cursor < end && source[cursor] !== quote) cursor += 1;
        if (cursor >= end) return { attributes, malformed: true };
        value = source.slice(valueStart, cursor);
        cursor += 1;
      } else {
        while (cursor < end && !/[\s>]/.test(source[cursor])) cursor += 1;
        value = source.slice(valueStart, cursor);
      }
    }
    attributes.push({ name, value });
  }
  return { attributes, malformed: false };
}

function artifactTagAt(source, start) {
  if (source[start] !== "<") return null;
  let cursor = start + 1;
  const closing = source[cursor] === "/";
  if (closing) cursor += 1;
  while (cursor < source.length && /\s/.test(source[cursor])) cursor += 1;
  const nameStart = cursor;
  if (!/[A-Za-z]/.test(source[cursor] || "")) return null;
  while (cursor < source.length && /[A-Za-z0-9:-]/.test(source[cursor])) cursor += 1;
  const name = source.slice(nameStart, cursor).toLowerCase();
  const boundary = source[cursor];
  if (boundary && !/[\s/>]/.test(boundary)) return null;
  const end = artifactTagEnd(source, cursor);
  if (end < 0) return { name, closing, end, attributes: [], malformed: true };
  const parsed = closing
    ? { attributes: [], malformed: false }
    : artifactTagAttributes(source, cursor, end);
  return { name, closing, end, ...parsed };
}

function artifactCommentEnd(source, start) {
  const standard = source.indexOf("-->", start);
  const permissive = source.indexOf("--!>", start);
  if (standard < 0) return permissive < 0 ? null : { start: permissive, length: 4 };
  if (permissive < 0 || standard < permissive) return { start: standard, length: 3 };
  return { start: permissive, length: 4 };
}

export function inspectArtifactHtmlSource(value) {
  const source = String(value || "");
  const inlineJavaScript = [];
  let externalScripts = 0;
  let navigationElements = false;
  let malformed = source.includes("\0");
  let cursor = 0;
  while (!malformed && cursor < source.length) {
    const next = source.indexOf("<", cursor);
    if (next < 0) break;
    if (source.slice(next, next + 4) === "<!--") {
      const end = artifactCommentEnd(source, next + 4);
      if (!end) { malformed = true; break; }
      cursor = end.start + end.length;
      continue;
    }
    const tag = artifactTagAt(source, next);
    if (!tag) { cursor = next + 1; continue; }
    if (tag.malformed) { malformed = true; break; }
    cursor = tag.end + 1;
    if (tag.closing) continue;
    const attributeNames = new Set(tag.attributes.map(attribute => attribute.name));
    if (["base", "iframe", "object", "embed"].includes(tag.name)
        || (tag.name === "meta" && attributeNames.has("http-equiv"))) {
      navigationElements = true;
    }
    for (const attribute of tag.attributes) {
      if (attribute.name.startsWith("on")) inlineJavaScript.push(attribute.value);
      if (/^\s*javascript\s*:/i.test(attribute.value)) navigationElements = true;
    }
    if (tag.name !== "script") continue;
    if (attributeNames.has("src")) externalScripts += 1;
    let closeStart = -1, closeTag = null, search = cursor;
    while (search < source.length) {
      const candidate = source.indexOf("<", search);
      if (candidate < 0) break;
      const parsed = artifactTagAt(source, candidate);
      if (parsed?.malformed) { malformed = true; break; }
      if (parsed?.closing && parsed.name === "script") {
        closeStart = candidate; closeTag = parsed; break;
      }
      search = candidate + 1;
    }
    if (malformed || closeStart < 0 || !closeTag) { malformed = true; break; }
    inlineJavaScript.push(source.slice(cursor, closeStart));
    cursor = closeTag.end + 1;
  }
  return { inlineJavaScript, externalScripts, navigationElements, malformed };
}

export function artifactCodeIssue(artifact) {
  const html = String(artifact?.html || "");
  const inspection = inspectArtifactHtmlSource(html);
  const javascript = [...inspection.inlineJavaScript, String(artifact?.javascript || "")].filter(Boolean).join("\n");
  const issues = [];
  if (inspection.malformed) issues.push("Malformed artifact HTML cannot be validated safely.");
  if (inspection.externalScripts) issues.push("External scripts are unavailable in the artifact sandbox. Use self-contained browser JavaScript.");
  if (inspection.navigationElements) {
    issues.push("Navigation and embedded browsing elements are unavailable in the artifact sandbox.");
  }
  if (/(?:\bfetch\s*\(|\bXMLHttpRequest\b|\bWebSocket\s*\(|\blocalStorage\b|\bsessionStorage\b|\bindexedDB\b|\bwindow\.open\s*\(|\b(?:window\.)?location\s*=)/.test(javascript)) {
    issues.push("Network and browser storage APIs are unavailable in the artifact sandbox. Keep the artifact self-contained; use course.embed for embeddings.");
  }
  const javascriptIssue = artifactJavaScriptIssue(javascript);
  if (javascriptIssue) issues.push(javascriptIssue);
  return issues.join(" ");
}

export function parseInlineCourseSourceIntent(text) {
  const raw = String(text || "").trim();
  if (!/^\{[\s\S]*\}$/.test(raw) || raw.length > 500) return null;
  try {
    const value = JSON.parse(raw);
    return value && typeof value === "object" && typeof value.uri === "string" && value.uri.trim()
      ? { uri: value.uri.trim() } : null;
  } catch (_) { return null; }
}

export async function resolveCourseSourceUri(uri, pageId = "") {
  const value = String(uri || "").trim().replace(/^course:\/\//, "");
  if (!value || value.includes("..") || value.length > 160) return null;
  const runtimeFile = value.replace(/^scripts\//, "");
  if (courseRuntimeFiles().some(item => item.file === runtimeFile)) {
    return { label: `read_course_runtime_source · ${runtimeFile}`, content: await courseRuntimeSource(runtimeFile) };
  }
  let page = String(pageId || "").trim(), artifact = value;
  const pageIds = new Set(coursePages().map(item => item.id));
  const hash = value.indexOf("#");
  if (hash > 0) { page = value.slice(0, hash); artifact = value.slice(hash + 1); }
  else {
    const slash = value.indexOf("/");
    if (slash > 0 && pageIds.has(value.slice(0, slash))) { page = value.slice(0, slash); artifact = value.slice(slash + 1); }
  }
  if (!pageIds.has(page) || !artifact) return null;
  const available = await courseCodeArtifacts(page);
  if (!available.some(item => item.id === artifact)) return null;
  return { label: `read_course_source · ${page}#${artifact}`, content: await courseCode(page, artifact) };
}

export function mountCourseAssistant(runtime = {}) {
  if (!location.pathname.includes("/nemoclaw/")) return;
  if (document.querySelector(".course-assistant-launcher")) return;
  const language = document.documentElement.lang.toLowerCase();
  const pt = language.startsWith("pt");
  const es = language.startsWith("es");
  const copy = pt ? {
    open: "Abrir Assistente do Curso", assistant: "ASSISTENTE DO CURSO", dialog: "Assistente do Curso",
    resize: "Redimensionar o Assistente do Curso", resizeTitle: "Arraste para redimensionar · clique duas vezes para restaurar",
    close: "Fechar Assistente do Curso", session: "Sessão", newSession: "+ Nova", deleteSession: "Excluir",
    deleteLabel: "Excluir a sessão atual do Assistente do Curso",
    renameLabel: "Renomear a sessão atual", renamePlaceholder: "Nome da sessão",
    attached: "Página vinculada", noPage: "Nenhuma página vinculada", usePage: id => `Usar ${id}`, refreshPage: "Atualizar página",
    tools: "mapa, prosa, código e fontes do runtime disponíveis",
    chatView: "Conversa", artifactView: "Artefato", historyView: "Histórico", historyTitle: "Atividade salva da sessão", copyHistory: "Copiar histórico", noHistory: "Ainda não há atividade salva nesta sessão.", artifactTitle: "Título do artefato", htmlLabel: "HTML", javascriptLabel: "JavaScript",
    runArtifact: "▶ Executar", clearArtifact: "Limpar prévia", deleteArtifact: "Excluir artefato", artifactPreview: "Prévia do artefato do curso", generatedReady: "Código gerado pronto",
    previewCleared: "Prévia limpa; código preservado", artifactDeleted: "Artefato excluído", syntaxError: "Erro de sintaxe", runtimeError: "Erro de execução", runtimeReady: "Prévia pronta",
    artifactApi: 'API: await course.embed(...) ou await helpers.embed(...); helpers.cosineSim(a, b).',
    saved: "Salvo localmente", saving: "Salvando resposta", full: "Não salvo: armazenamento local cheio", selected: "Sessão selecionada",
    created: "Nova sessão criada", deleted: "Sessão excluída", renamed: "Sessão renomeada", attachedNow: "Página vinculada à sessão", compacted: "Contexto condensado e salvo localmente",
    emptyTitle: "Nova sessão", clear: "↺ Limpar sessão",
    intro: "As sessões ficam neste navegador. Turnos antigos são condensados automaticamente.",
    greeting: (liveId, sessionId) => sessionId && sessionId !== liveId
      ? `Você está em ${liveId}. Esta sessão começou em ${sessionId}; “esta página” sempre significa ${liveId}.`
      : liveId ? `Você está em ${liveId}. A prosa, o documento HTML e o índice de código desta página estão disponíveis.` : "Nenhuma página está vinculada. Pesquise ou leia qualquer parte do curso.",
    examples: ["Resuma esta página", "Mostre o código desta página", "Crie um artefato HTML/JavaScript executável", "Como _shared.js apoia esta página?"],
  } : es ? {
    open: "Abrir el Asistente del curso", assistant: "ASISTENTE DEL CURSO", dialog: "Asistente del curso",
    resize: "Cambiar el tamaño del Asistente del curso", resizeTitle: "Arrastre para cambiar el tamaño · haga doble clic para restablecerlo",
    close: "Cerrar el Asistente del curso", session: "Sesión", newSession: "+ Nueva", deleteSession: "Eliminar",
    deleteLabel: "Eliminar la sesión actual del Asistente del curso",
    renameLabel: "Cambiar el nombre de la sesión actual", renamePlaceholder: "Nombre de la sesión",
    attached: "Página vinculada", noPage: "Ninguna página vinculada", usePage: id => `Usar ${id}`, refreshPage: "Actualizar página",
    tools: "mapa, prosa, código y fuentes del runtime disponibles",
    chatView: "Conversación", artifactView: "Artefacto", historyView: "Historial", historyTitle: "Actividad guardada de la sesión", copyHistory: "Copiar historial", noHistory: "Esta sesión aún no tiene actividad guardada.", artifactTitle: "Título del artefacto", htmlLabel: "HTML", javascriptLabel: "JavaScript",
    runArtifact: "▶ Ejecutar", clearArtifact: "Borrar vista previa", deleteArtifact: "Eliminar artefacto", artifactPreview: "Vista previa del artefacto del curso", generatedReady: "Código generado listo",
    previewCleared: "Vista previa borrada; se conservó el código", artifactDeleted: "Artefacto eliminado", syntaxError: "Error de sintaxis", runtimeError: "Error de ejecución", runtimeReady: "Vista previa lista",
    artifactApi: 'API: await course.embed(...) o await helpers.embed(...); helpers.cosineSim(a, b).',
    saved: "Guardado localmente", saving: "Guardando respuesta", full: "No se guardó: el almacenamiento del navegador está lleno", selected: "Sesión seleccionada",
    created: "Nueva sesión creada", deleted: "Sesión eliminada", renamed: "Sesión renombrada", attachedNow: "Página vinculada a la sesión", compacted: "Contexto condensado y guardado localmente",
    emptyTitle: "Nueva sesión", clear: "↺ Borrar sesión",
    intro: "Las sesiones permanecen en este navegador. Los turnos antiguos se condensan automáticamente.",
    greeting: (liveId, sessionId) => sessionId && sessionId !== liveId
      ? `Está en ${liveId}. Esta sesión comenzó en ${sessionId}; «esta página» siempre significa ${liveId}.`
      : liveId ? `Está en ${liveId}. La prosa, el documento HTML y el índice de código de esta página están disponibles.` : "No hay ninguna página vinculada. Busque o lea cualquier parte del curso.",
    examples: ["Resuma esta página", "Muéstreme el código de esta página", "Cree un artefacto HTML/JavaScript ejecutable", "¿Cómo ayuda _shared.js a esta página?"],
  } : {
    open: "Open Course Assistant", assistant: "COURSE ASSISTANT", dialog: "Course Assistant",
    resize: "Resize Course Assistant", resizeTitle: "Drag to resize · double-click to reset",
    close: "Close Course Assistant", session: "Session", newSession: "+ New", deleteSession: "Delete",
    deleteLabel: "Delete current Course Assistant session",
    renameLabel: "Rename current Course Assistant session", renamePlaceholder: "Session name",
    attached: "Attached page", noPage: "No page attached", usePage: id => `Use ${id}`, refreshPage: "Refresh page",
    tools: "course map, prose, code, and runtime-source tools available",
    chatView: "Chat", artifactView: "Artifact", historyView: "History", historyTitle: "Saved session activity", copyHistory: "Copy history", noHistory: "No saved activity in this session yet.", artifactTitle: "Artifact title", htmlLabel: "HTML", javascriptLabel: "JavaScript",
    runArtifact: "▶ Run", clearArtifact: "Clear preview", deleteArtifact: "Delete artifact", artifactPreview: "Course artifact preview", generatedReady: "Generated code ready",
    previewCleared: "Preview cleared; code preserved", artifactDeleted: "Artifact deleted", syntaxError: "Syntax error", runtimeError: "Runtime error", runtimeReady: "Preview ready",
    artifactApi: 'API: await course.embed(...) or await helpers.embed(...); helpers.cosineSim(a, b).',
    saved: "Saved locally", saving: "Saving response", full: "Not saved: browser storage is full", selected: "Session selected",
    created: "New session created", deleted: "Session deleted", renamed: "Session renamed", attachedNow: "Page attached to session", compacted: "Compacted and saved locally",
    emptyTitle: "New session", clear: "↺ Clear session",
    intro: "Sessions stay in this browser. Older turns compact automatically.",
    greeting: (liveId, sessionId) => sessionId && sessionId !== liveId
      ? `You are on ${liveId}. This session began on ${sessionId}; “this page” always means ${liveId}.`
      : liveId ? `You are on ${liveId}. This page's prose, HTML document, and code index are available.` : "No page is attached. Search or read any part of the course.",
    examples: ["Summarize this page", "Show me this page's code", "Build a runnable HTML/JavaScript artifact", "How does _shared.js support this page?"],
  };
  const page = currentPage();
  const localized = (ptText, esText, enText) => pt ? ptText : es ? esText : enText;
  const title = currentTitle(page);
  const launcher = document.createElement("button");
  launcher.type = "button";
  launcher.className = "course-assistant-launcher";
  launcher.setAttribute("aria-label", copy.open);
  launcher.setAttribute("aria-controls", "course-assistant-panel");
  launcher.setAttribute("aria-expanded", "false");
  launcher.title = copy.open;
  launcher.textContent = "✦";

  const shell = document.createElement("section");
  shell.className = "course-assistant-shell";
  shell.innerHTML = `<div class="course-assistant-backdrop" data-course-assistant-close></div>
    <aside id="course-assistant-panel" class="course-assistant-panel" role="dialog" aria-modal="true" aria-label="${copy.dialog}" aria-hidden="true">
      <div class="course-assistant-resizer" role="separator" aria-label="${copy.resize}" aria-orientation="vertical" aria-valuemin="320" tabindex="0" title="${copy.resizeTitle}"></div>
      <header><div><span>${copy.assistant}</span><h2 data-course-assistant-title>${copy.emptyTitle}</h2></div><button type="button" data-course-assistant-close aria-label="${copy.close}">×</button></header>
      <div class="course-assistant-sessions"><label for="course-assistant-session">${copy.session}</label><select id="course-assistant-session" aria-label="${copy.session}"></select><button type="button" data-course-assistant-new>${copy.newSession}</button><button type="button" data-course-assistant-delete aria-label="${copy.deleteLabel}">${copy.deleteSession}</button><input type="text" maxlength="72" aria-label="${copy.renameLabel}" placeholder="${copy.renamePlaceholder}"><span role="status" aria-live="polite"></span></div>
      <p class="course-assistant-context"><span></span><button type="button" data-course-assistant-use-page></button></p>
      <div class="course-assistant-tabs" role="tablist"><button type="button" role="tab" aria-selected="true" data-course-assistant-view="chat">${copy.chatView}</button><button type="button" role="tab" aria-selected="false" data-course-assistant-view="artifact">${copy.artifactView}</button><button type="button" role="tab" aria-selected="false" data-course-assistant-view="history">${copy.historyView}</button></div>
      <div class="course-assistant-body"></div>
      <section class="course-assistant-artifact" hidden>
        <label>${copy.artifactTitle}<input type="text" maxlength="96" data-course-artifact-title></label>
        <p class="course-artifact-api">${copy.artifactApi}</p>
        <div class="course-artifact-editors"><label>${copy.htmlLabel}<textarea data-course-artifact-html spellcheck="false"></textarea></label><label>${copy.javascriptLabel}<textarea data-course-artifact-js spellcheck="false"></textarea></label></div>
        <div class="course-artifact-actions"><button type="button" data-course-artifact-run>${copy.runArtifact}</button><button type="button" data-course-artifact-clear>${copy.clearArtifact}</button><button type="button" data-course-artifact-delete>${copy.deleteArtifact}</button><span role="status" aria-live="polite"></span></div>
        <iframe sandbox="allow-scripts" referrerpolicy="no-referrer" title="${copy.artifactPreview}"></iframe>
      </section>
      <section class="course-assistant-history" hidden><header><strong>${copy.historyTitle}</strong><button type="button" data-course-history-copy>${copy.copyHistory}</button></header><pre tabindex="0"></pre></section>
    </aside>`;
  document.body.append(launcher, shell);
  const panel = shell.querySelector(".course-assistant-panel");
  const body = shell.querySelector(".course-assistant-body");
  const artifactPanel = shell.querySelector(".course-assistant-artifact");
  const historyPanel = shell.querySelector(".course-assistant-history");
  const historyText = historyPanel.querySelector("pre");
  const artifactTitle = shell.querySelector("[data-course-artifact-title]");
  const artifactHtml = shell.querySelector("[data-course-artifact-html]");
  const artifactJs = shell.querySelector("[data-course-artifact-js]");
  const artifactFrame = artifactPanel.querySelector("iframe");
  const artifactStatus = artifactPanel.querySelector('[role="status"]');
  const viewButtons = [...shell.querySelectorAll("[data-course-assistant-view]")];
  const artifactViewButton = shell.querySelector('[data-course-assistant-view="artifact"]');
  const resizer = shell.querySelector(".course-assistant-resizer");
  const sessionSelect = shell.querySelector("#course-assistant-session");
  const sessionName = shell.querySelector('.course-assistant-sessions input[type="text"]');
  const sessionStatus = shell.querySelector(".course-assistant-sessions [role=status]");
  const sessionTitle = shell.querySelector("[data-course-assistant-title]");
  const contextText = shell.querySelector(".course-assistant-context span");
  const usePageButton = shell.querySelector("[data-course-assistant-use-page]");
  const newSessionButton = shell.querySelector("[data-course-assistant-new]");
  let store = loadCourseAssistantStore();
  const initial = store.sessions.find(item => item.id === store.activeId) || store.sessions[0];
  if (initial && !initial.pageId && !initial.history.length) {
    initial.pageId = page.id; initial.pageTitle = title;
  }
  let chatApi = null;
  let mountedSessionId = null;
  let artifactBlobUrl = "";
  const artifactBridgeId = randomId("artifact-");
  const artifactEditors = { html: null, javascript: null };
  let syncingArtifactEditors = false;
  const editorValue = (kind, textarea) => artifactEditors[kind]?.getValue() ?? textarea.value;
  const setEditorValue = (kind, textarea, value) => {
    if (artifactEditors[kind] && artifactEditors[kind].getValue() !== value) {
      syncingArtifactEditors = true; artifactEditors[kind].setValue(value); syncingArtifactEditors = false;
    }
    else textarea.value = value;
  };
  const clearArtifactPreview = message => {
    if (artifactBlobUrl) { URL.revokeObjectURL(artifactBlobUrl); artifactBlobUrl = ""; }
    artifactFrame.src = "about:blank";
    if (message) artifactStatus.textContent = message;
  };
  const activeSession = () => store.sessions.find(item => item.id === store.activeId) || store.sessions[0];
  let activeView = "chat";
  const activateView = view => {
    activeView = ["artifact", "history"].includes(view) ? view : "chat";
    body.hidden = activeView !== "chat";
    artifactPanel.hidden = activeView !== "artifact";
    historyPanel.hidden = activeView !== "history";
    viewButtons.forEach(button => button.setAttribute("aria-selected", String(button.dataset.courseAssistantView === activeView)));
    if (activeView === "artifact") setTimeout(() => Object.values(artifactEditors).forEach(editor => editor?.refresh()), 0);
  };
  const artifactDocument = (artifact, channel = artifactBridgeId) => {
    const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; img-src data: blob:; font-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline' 'unsafe-eval'; base-uri 'none'; form-action 'none'">`;
    const bridge = `<script>
(() => {
  const channel = ${JSON.stringify(channel)};
  const pending = new Map();
  let sequence = 0;
  let sourceStarted = false;
  const emit = (type, payload = {}) => parent.postMessage({ channel, type, ...payload }, "*");
  const report = value => emit("artifact-error", {
    message: String(value?.message || value),
    line: value?.lineno || 0,
    column: value?.colno || 0,
  });
  const embed = (input, options = {}) => new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    emit("request", { id, method: "embed", args: [input, options] });
    setTimeout(() => {
      if (pending.delete(id)) reject(new Error("course.embed timed out"));
    }, 65000);
  });
  const cosineSim = (a, b) => {
    if (!Array.isArray(a) || !Array.isArray(b) || !a.length || a.length !== b.length) {
      throw new Error("helpers.cosineSim expects two non-empty vectors of equal length");
    }
    let dot = 0, aa = 0, bb = 0;
    for (let index = 0; index < a.length; index += 1) {
      const x = Number(a[index]), y = Number(b[index]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) {
        throw new Error("helpers.cosineSim expects finite numbers");
      }
      dot += x * y; aa += x * x; bb += y * y;
    }
    return aa && bb ? dot / Math.sqrt(aa * bb) : 0;
  };
  const api = Object.freeze({ embed, cosineSim });
  window.course = api;
  window.helpers = new Proxy(api, {
    get(target, key) {
      if (key in target) return target[key];
      throw new Error("Artifact helper helpers." + String(key)
        + " is unavailable. Supported: helpers.embed, helpers.cosineSim.");
    },
  });
  const runSource = async source => {
    const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
    const run = new AsyncFunction("course", "helpers", '"use strict";\\n' + source);
    await run(api, window.helpers);
  };
  const probe = async () => {
    const original = { alert: window.alert, confirm: window.confirm, prompt: window.prompt };
    window.alert = () => {};
    window.confirm = () => true;
    window.prompt = () => "";
    try {
      for (const input of [...document.querySelectorAll("input,select,textarea")].slice(0, 12)) {
        if (input.disabled) continue;
        if (input.type === "radio" || input.type === "checkbox") input.checked = true;
        else if (input.tagName === "SELECT" && input.options.length) input.selectedIndex = 0;
        else if (!input.value) input.value = "probe";
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      }
      for (const button of [...document.querySelectorAll("button,input[type=button],input[type=submit]")].slice(0, 12)) {
        if (button.disabled) continue;
        try { button.click(); } catch (error) { report(error); }
        await Promise.resolve();
      }
      await new Promise(resolve => setTimeout(resolve, 120));
    } finally {
      window.alert = original.alert;
      window.confirm = original.confirm;
      window.prompt = original.prompt;
    }
    emit("artifact-probe-complete");
  };
  addEventListener("message", event => {
    if (event.source !== parent) return;
    const data = event.data || {};
    if (data.channel !== channel) return;
    if (data.type === "response" && pending.has(data.id)) {
      const item = pending.get(data.id);
      pending.delete(data.id);
      data.error ? item.reject(new Error(data.error)) : item.resolve(data.result);
    } else if (data.type === "artifact-source" && !sourceStarted) {
      sourceStarted = true;
      const source = typeof data.javascript === "string" ? data.javascript : "";
      if (source.length > ${MAX_ARTIFACT_FIELD_CHARS}) {
        report(new Error("Artifact JavaScript exceeds the course limit."));
        emit("artifact-ready");
      } else {
        runSource(source)
          .catch(report)
          .finally(() => emit("artifact-ready"));
      }
    } else if (data.type === "artifact-probe") {
      probe().catch(error => {
        report(error);
        emit("artifact-probe-complete");
      });
    }
  });
  addEventListener("error", event => report(event));
  addEventListener("unhandledrejection", event => report(event.reason));
})();
<\/script>`;
    const html = String(artifact?.html || "").trim();
    if (/<html[\s>]/i.test(html)) {
      let documentText = /<head[\s>]/i.test(html)
        ? html.replace(/<head([^>]*)>/i, `<head$1>${csp}${bridge}`)
        : html.replace(/<html([^>]*)>/i, `<html$1><head>${csp}${bridge}</head>`);
      return documentText;
    }
    return `<!doctype html><html><head><meta charset="utf-8">${csp}${bridge}<style>:root{color-scheme:light}body{font:16px/1.5 system-ui;margin:1rem;color:var(--tx,#161616)}*{box-sizing:border-box}</style></head><body>${html}</body></html>`;
  };
  const sendArtifactSource = (frame, artifact, channel) => {
    frame.contentWindow?.postMessage({
      channel,
      type: "artifact-source",
      javascript: String(artifact?.javascript || ""),
    }, "*");
  };
  const validateArtifactRuntime = artifact => new Promise(resolve => {
    const channel = randomId("artifact-check-");
    const frame = document.createElement("iframe");
    frame.setAttribute("sandbox", "allow-scripts"); frame.referrerPolicy = "no-referrer"; frame.hidden = true;
    const blobUrl = URL.createObjectURL(new Blob([artifactDocument(artifact, channel)], { type: "text/html" }));
    const errors = [];
    let settled = false;
    const finish = issue => {
      if (settled) return;
      settled = true; clearTimeout(timer); window.removeEventListener("message", onMessage);
      frame.remove(); URL.revokeObjectURL(blobUrl); resolve(issue || errors[0] || "");
    };
    const onMessage = event => {
      const data = event.data || {};
      if (event.source !== frame.contentWindow || data.channel !== channel) return;
      if (data.type === "artifact-error") {
        const locationText = data.line ? ` at line ${data.line}${data.column ? ":" + data.column : ""}` : "";
        errors.push(String(data.message || "unknown error").slice(0, 500) + locationText); return;
      }
      if (data.type === "request" && data.method === "embed") {
        const raw = data.args?.[0], input = (Array.isArray(raw) ? raw : [raw]).map(value => String(value || ""));
        const requestedType = data.args?.[1]?.inputType;
        let error = "", result = null;
        if (!input.length || input.length > 16 || input.some(value => !value || value.length > 2000) || input.join("").length > 12000) error = "course.embed accepts 1-16 non-empty strings, up to 12,000 characters total";
        else if (requestedType != null && !["query", "passage"].includes(requestedType)) error = 'course.embed inputType must be "query" or "passage"';
        else result = input.map((value, index) => [1, (value.length % 17) / 17, index / 16]);
        frame.contentWindow?.postMessage({ channel, type: "response", id: data.id, ...(error ? { error } : { result }) }, "*");
      } else if (data.type === "artifact-ready") frame.contentWindow?.postMessage({ channel, type: "artifact-probe" }, "*");
      else if (data.type === "artifact-probe-complete") setTimeout(() => finish(), 80);
    };
    window.addEventListener("message", onMessage);
    const timer = setTimeout(() => finish("Artifact runtime validation timed out before its controls became ready."), 5000);
    frame.addEventListener("load", () => sendArtifactSource(frame, artifact, channel), { once: true });
    frame.src = blobUrl;
    document.body.appendChild(frame);
  });
  const renderArtifact = (run = false) => {
    const artifact = activeSession()?.artifact;
    artifactTitle.value = artifact?.title || "Browser artifact";
    setEditorValue("html", artifactHtml, artifact?.html || "");
    setEditorValue("javascript", artifactJs, artifact?.javascript || "");
    artifactViewButton.textContent = copy.artifactView + (artifact ? " •" : "");
    artifactStatus.classList.remove("error");
    artifactStatus.textContent = artifact ? new Date(artifact.updatedAt).toLocaleString() : "";
    if (run && artifact) {
      const previousBlobUrl = artifactBlobUrl;
      artifactBlobUrl = URL.createObjectURL(new Blob([artifactDocument(artifact)], { type: "text/html" }));
      artifactFrame.addEventListener("load", () => sendArtifactSource(artifactFrame, artifact, artifactBridgeId), { once: true });
      artifactFrame.src = artifactBlobUrl;
      if (previousBlobUrl) URL.revokeObjectURL(previousBlobUrl);
    } else if (!artifact) clearArtifactPreview();
  };
  const renderSessions = () => {
    sessionSelect.replaceChildren(...store.sessions.map(session => {
      const option = document.createElement("option"); option.value = session.id;
      const label = session.title === "New session" ? copy.emptyTitle : session.title;
      option.textContent = label + (session.pageId ? " · " + session.pageId : ""); return option;
    }));
    sessionSelect.value = store.activeId;
    const session = activeSession();
    const label = session?.title === "New session" ? copy.emptyTitle : session?.title || copy.emptyTitle;
    sessionName.value = label;
    sessionTitle.textContent = label;
    const attached = session?.pageId ? `${copy.attached}: ${session.pageId}${session.pageTitle ? " · " + session.pageTitle : ""}` : copy.noPage;
    const livePage = session?.pageId && session.pageId !== page.id
      ? ` · ${localized("Página atual", "Página actual", "Current page")}: ${page.id}`
      : "";
    contextText.textContent = attached + livePage + " · " + copy.tools;
    usePageButton.textContent = session?.pageId === page.id ? copy.refreshPage : copy.usePage(page.id);
    newSessionButton.disabled = store.sessions.length >= MAX_ASSISTANT_SESSIONS;
  };
  const renderHistory = () => {
    historyText.textContent = activeSession()?.activity || copy.noHistory;
  };
  const persistStore = (message = copy.saved) => {
    try {
      const saved = saveCourseAssistantStore(store); renderSessions(); renderHistory();
      sessionStatus.textContent = `${message} · ${saved.sessions}/${MAX_ASSISTANT_SESSIONS} · ${Math.ceil(saved.chars / 1024)} KB`;
    }
    catch (error) { sessionStatus.textContent = `${copy.full} · ${error?.name || "storage error"}`; }
  };
  persistStore(copy.saved);
  renderArtifact(true);
  viewButtons.forEach(button => button.addEventListener("click", () => activateView(button.dataset.courseAssistantView)));
  shell.querySelector("[data-course-history-copy]").addEventListener("click", event => {
    navigator.clipboard.writeText(activeSession()?.activity || "").then(() => {
      const button = event.currentTarget, before = button.textContent; button.textContent = "✓";
      setTimeout(() => { button.textContent = before; }, 1000);
    }).catch(() => {});
  });
  let artifactSaveTimer = 0;
  let runArtifact = () => {};
  const saveArtifact = (message = copy.saved, run = false) => {
    if (artifactSaveTimer) { clearTimeout(artifactSaveTimer); artifactSaveTimer = 0; }
    const session = activeSession();
    if (!session) return;
    session.artifact = cleanArtifact({
      title: artifactTitle.value,
      html: editorValue("html", artifactHtml),
      javascript: editorValue("javascript", artifactJs),
      updatedAt: Date.now(),
    });
    session.updatedAt = Date.now();
    persistStore(message);
    renderArtifact(run);
  };
  const scheduleArtifactSave = () => {
    clearTimeout(artifactSaveTimer);
    artifactSaveTimer = setTimeout(() => saveArtifact(copy.saved, false), 300);
  };
  const flushArtifactSave = () => {
    if (!artifactSaveTimer) return;
    clearTimeout(artifactSaveTimer); artifactSaveTimer = 0; saveArtifact(copy.saved, false);
  };
  artifactTitle.addEventListener("input", scheduleArtifactSave);
  const ensureArtifactHtmlMode = () => {
    if (typeof window.CodeMirror?.defineMode !== "function" || window.CodeMirror.modes["course-html"]) return;
    window.CodeMirror.defineMode("course-html", () => ({
      startState: () => ({ inTag: false }),
      token: (stream, state) => {
        if (!state.inTag) {
          if (stream.match("<!--")) { if (!stream.skipTo("-->")) stream.skipToEnd(); else stream.match("-->"); return "comment"; }
          if (stream.peek() === "<") { stream.next(); stream.eat("/"); state.inTag = true; return "tag"; }
          stream.next(); stream.eatWhile(/[^<]/); return null;
        }
        if (stream.peek() === ">") { stream.next(); state.inTag = false; return "tag"; }
        if (stream.peek() === "/") { stream.next(); return "tag"; }
        if (/["']/.test(stream.peek())) { const quote = stream.next(); while (!stream.eol()) { if (stream.next() === quote) break; } return "string"; }
        if (stream.match(/^[A-Za-z_:][\w:.-]*(?=\s*=)/)) return "attribute";
        if (stream.match(/^[A-Za-z_:][\w:.-]*/)) return "tag";
        stream.next(); return null;
      },
    }));
  };
  ensureArtifactHtmlMode();
  const attachArtifactEditor = (textarea, kind, mode) => {
    if (typeof window.CodeMirror !== "function") {
      textarea.addEventListener("input", scheduleArtifactSave);
      textarea.addEventListener("keydown", event => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); runArtifact(); }
      });
      return null;
    }
    const editor = window.CodeMirror.fromTextArea(textarea, {
      mode, theme: "monokai", lineNumbers: true, lineWrapping: false,
      indentUnit: 2, tabSize: 2, indentWithTabs: false, viewportMargin: 20,
      extraKeys: {
        "Ctrl-Enter": () => runArtifact(), "Cmd-Enter": () => runArtifact(),
        "Tab": item => item.execCommand("indentMore"), "Shift-Tab": item => item.execCommand("indentLess"),
      },
    });
    editor.setSize("100%", "100%");
    textarea.__courseAssistantEditor = editor;
    editor.on("change", () => { if (!syncingArtifactEditors) scheduleArtifactSave(); });
    return editor;
  };
  artifactEditors.html = attachArtifactEditor(artifactHtml, "html", window.CodeMirror?.modes?.htmlmixed ? "htmlmixed" : "course-html");
  artifactEditors.javascript = attachArtifactEditor(artifactJs, "javascript", "javascript");
  runArtifact = () => {
    saveArtifact(copy.saved, false);
    const issue = artifactCodeIssue({
      html: editorValue("html", artifactHtml),
      javascript: editorValue("javascript", artifactJs),
    });
    if (issue) { artifactStatus.textContent = issue; artifactStatus.classList.add("error"); return; }
    artifactStatus.classList.remove("error"); renderArtifact(true);
  };
  shell.querySelector("[data-course-artifact-run]").addEventListener("click", runArtifact);
  shell.querySelector("[data-course-artifact-clear]").addEventListener("click", () => {
    flushArtifactSave(); clearArtifactPreview(copy.previewCleared);
  });
  shell.querySelector("[data-course-artifact-delete]").addEventListener("click", () => {
    if (artifactSaveTimer) { clearTimeout(artifactSaveTimer); artifactSaveTimer = 0; }
    const session = activeSession();
    if (!session) return;
    session.artifact = null; session.updatedAt = Date.now();
    persistStore(copy.saved); renderArtifact(false); artifactStatus.textContent = copy.artifactDeleted;
  });
  window.addEventListener("message", async event => {
    const data = event.data || {};
    if (event.source !== artifactFrame.contentWindow || data.channel !== artifactBridgeId) return;
    if (data.type === "artifact-error") {
      const locationText = data.line ? ` · line ${data.line}${data.column ? ":" + data.column : ""}` : "";
      artifactStatus.textContent = `${copy.runtimeError}: ${String(data.message || "unknown error").slice(0, 500)}${locationText}`;
      artifactStatus.classList.add("error"); return;
    }
    if (data.type === "artifact-ready") {
      if (!artifactStatus.classList.contains("error")) artifactStatus.textContent = copy.runtimeReady;
      return;
    }
    if (data.type !== "request" || data.method !== "embed") return;
    const respond = payload => artifactFrame.contentWindow?.postMessage({ channel: artifactBridgeId, type: "response", id: data.id, ...payload }, "*");
    try {
      if (typeof runtime.embed !== "function") throw new Error("course.embed is unavailable on this page");
      const rawInput = data.args?.[0];
      const input = (Array.isArray(rawInput) ? rawInput : [rawInput]).map(value => String(value || ""));
      if (!input.length || input.length > 16 || input.some(value => !value || value.length > 2000) || input.join("").length > 12000) {
        throw new Error("course.embed accepts 1-16 non-empty strings, up to 12,000 characters total");
      }
      const requestedType = data.args?.[1]?.inputType;
      if (requestedType != null && !["query", "passage"].includes(requestedType)) throw new Error('course.embed inputType must be "query" or "passage"');
      const inputType = requestedType || "query";
      respond({ result: await runtime.embed(input, { inputType }) });
    } catch (error) { respond({ error: String(error?.message || error).slice(0, 500) }); }
  });
  window.addEventListener("pagehide", () => {
    flushArtifactSave();
  });
  const maxPanelWidth = () => Math.floor(window.innerWidth * 0.9);
  const minPanelWidth = () => Math.min(320, maxPanelWidth());
  const setPanelWidth = (width, persist = true) => {
    if (window.innerWidth <= 640) {
      panel.style.removeProperty("width");
      return;
    }
    const next = Math.max(minPanelWidth(), Math.min(maxPanelWidth(), Math.round(width)));
    panel.style.width = next + "px";
    resizer.setAttribute("aria-valuenow", String(next));
    resizer.setAttribute("aria-valuemax", String(maxPanelWidth()));
    if (persist) try { localStorage.setItem(ASSISTANT_WIDTH_KEY, String(next)); } catch (_) {}
  };
  const resetPanelWidth = () => {
    try { localStorage.removeItem(ASSISTANT_WIDTH_KEY); } catch (_) {}
    setPanelWidth(Math.min(480, maxPanelWidth()), false);
  };
  try {
    const saved = Number(localStorage.getItem(ASSISTANT_WIDTH_KEY));
    if (Number.isFinite(saved) && saved > 0) setPanelWidth(saved, false);
    else resetPanelWidth();
  } catch (_) { resetPanelWidth(); }
  resizer.addEventListener("pointerdown", event => {
    if (window.innerWidth <= 640) return;
    event.preventDefault();
    resizer.setPointerCapture(event.pointerId);
    shell.classList.add("resizing");
  });
  resizer.addEventListener("pointermove", event => {
    if (resizer.hasPointerCapture(event.pointerId)) setPanelWidth(window.innerWidth - event.clientX);
  });
  const endResize = event => {
    if (resizer.hasPointerCapture(event.pointerId)) resizer.releasePointerCapture(event.pointerId);
    shell.classList.remove("resizing");
  };
  resizer.addEventListener("pointerup", endResize);
  resizer.addEventListener("pointercancel", endResize);
  resizer.addEventListener("dblclick", resetPanelWidth);
  resizer.addEventListener("keydown", event => {
    const width = panel.getBoundingClientRect().width;
    if (event.key === "ArrowLeft") setPanelWidth(width + 48);
    else if (event.key === "ArrowRight") setPanelWidth(width - 48);
    else if (event.key === "Home") resetPanelWidth();
    else if (event.key === "End") setPanelWidth(maxPanelWidth());
    else return;
    event.preventDefault();
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth <= 640) panel.style.removeProperty("width");
    else setPanelWidth(panel.getBoundingClientRect().width, false);
  });
  let priorFocus = null;
  const mountSession = async (session = activeSession()) => {
    if (!session || mountedSessionId === session.id) return;
    if (chatApi?.stop) chatApi.stop();
    body.replaceChildren();
    mountedSessionId = session.id;
    const attachedPage = coursePages().find(item => item.id === session.pageId) || null;
    const attachedTitle = session.pageTitle || attachedPage?.title || "";
    let turnQuestion = "";
    const targetPageId = requested => questionTargetsCurrentPage(turnQuestion) ? page.id : requested;
    const pageContext = async id => {
      const [prose, artifacts] = await Promise.all([coursePage(id), courseCodeArtifacts(id)]);
      const codeIndex = artifacts.length
        ? artifacts.map(item => `- ${id}#${item.id} · ${item.kind} · ${item.lines} lines · ${item.summary}`).join("\n")
        : "(no lesson code artifacts on this page)";
      return `${prose}\n\n## Available implementation source\n${codeIndex}\n\nUse the code-reading tools for exact source. Course-authored source is public and Apache-2.0; never claim it is private or inaccessible.`;
    };
    const position = localized(
      `O navegador está em ${page.id}, “${title}”. ${attachedPage && attachedPage.id !== page.id ? `A sessão salva começou em ${attachedPage.id}, “${attachedTitle}”, mas “esta página” e “página atual” sempre significam ${page.id}.` : "A sessão está vinculada à página atual."}`,
      `El navegador está en ${page.id}, «${title}». ${attachedPage && attachedPage.id !== page.id ? `La sesión guardada comenzó en ${attachedPage.id}, «${attachedTitle}», pero «esta página» y «página actual» siempre significan ${page.id}.` : "La sesión está vinculada a la página actual."}`,
      `The browser is currently on ${page.id}, “${title}”. ${attachedPage && attachedPage.id !== page.id ? `The saved session began on ${attachedPage.id}, “${attachedTitle}”, but “this page” and “current page” always mean ${page.id}.` : "This session is attached to the current page."}`,
    );
    chatApi = await mountAgentChat(body, {
      models: MODELS,
      memory: true,
      initialHistory: session.history,
      initialActivity: session.activity,
      resetLabel: copy.clear,
      compactAtTokens: 12000,
      compactKeepMessages: 6,
      onUserMessage: question => {
        turnQuestion = String(question || "");
        const current = store.sessions.find(item => item.id === mountedSessionId);
        if (!current) return;
        if (!current.manualTitle) current.title = question.replace(/\s+/g, " ").trim().slice(0, 48) || "New session";
        current.updatedAt = Date.now();
        persistStore(copy.saved);
      },
      onTurnSnapshot: (history, meta) => {
        const current = store.sessions.find(item => item.id === mountedSessionId);
        if (!current) return;
        current.history = cleanHistory(history); current.activity = cleanActivity(meta?.activity); current.updatedAt = Date.now();
        persistStore(meta?.state === "running" ? copy.saving : copy.saved);
      },
      onHistoryChange: history => {
        const current = store.sessions.find(item => item.id === mountedSessionId);
        if (!current) return;
        current.history = cleanHistory(history);
        const firstUser = current.history.find(item => item.role === "user");
        if (!current.manualTitle) current.title = firstUser ? firstUser.content.replace(/\s+/g, " ").trim().slice(0, 48) || "New session" : "New session";
        current.updatedAt = Date.now();
        persistStore(current.history.some(item => item.role === "system") ? copy.compacted : copy.saved);
      },
      onAssistantMessage: async answer => {
        const sessionId = mountedSessionId;
        const current = store.sessions.find(item => item.id === sessionId);
        if (!current) return;
        const artifact = artifactFromMarkdown(answer, `${current.title || "Course Assistant"} artifact`);
        if (!artifact) return;
        const issue = artifactCodeIssue(artifact) || await validateArtifactRuntime(artifact);
        if (mountedSessionId !== sessionId) return;
        current.artifact = artifact; current.updatedAt = Date.now();
        persistStore(copy.saved); renderArtifact(!issue); activateView("artifact");
        artifactStatus.textContent = issue ? `Generated artifact rejected: ${issue}` : copy.generatedReady;
        artifactStatus.classList.toggle("error", !!issue);
      },
      intro: copy.intro,
      greeting: copy.greeting(page.id, attachedPage?.id || ""),
      showGreetingWithHistory: true,
      examples: copy.examples,
      system: pt
        ? `Você é o Assistente do Curso Securing Agents. ${position} Para perguntas sobre o curso, use list_course_pages, search_course_pages e read_course_page. Para código, use list_course_code e depois read_course_source com o URI retornado; para módulos compartilhados, use list_course_runtime_files e read_course_runtime_source. Invoque as ferramentas pela API: nunca imprima os argumentos JSON como resposta. O runtime do curso é JavaScript no navegador: use HTML/JavaScript por padrão. O sandbox fornece a API assíncrona course.embed e os aliases helpers.embed e helpers.cosineSim; sempre use await course.embed(textos, { inputType: "query" ou "passage" }) ou await helpers.embed(...). Nenhum outro helpers.* está disponível. O executor aceita await no nível superior. Não use import, fetch, localStorage nem pacotes externos. O curso não oferece uma célula genérica para colar código. Para qualquer artefato, diagrama, painel, questionário ou simulação solicitada, chame queue_course_artifact; coloque marcação e CSS em html e código executável em javascript. Use elementos button, input ou select nativos para ações do estudante. Não responda com HTML bruto nem blocos de código. Defina cada função e alvo DOM usado. Se a ferramenta rejeitar o artefato, corrija o erro e chame-a novamente. Só diga que está pronto após a aceitação da ferramenta. Leia o código antes de explicar e nunca invente uma implementação nem alegue que o código é privado ou inacessível. Cite os IDs das páginas e os arquivos usados.`
        : es
          ? `Es el Asistente del curso Securing Agents. ${position} Para preguntas sobre el curso, use list_course_pages, search_course_pages y read_course_page. Para código, use list_course_code y luego read_course_source con el URI devuelto; para módulos compartidos, use list_course_runtime_files y read_course_runtime_source. Invoque las herramientas mediante la API: nunca imprima los argumentos JSON como respuesta. El runtime del curso es JavaScript en el navegador; use HTML/JavaScript de forma predeterminada. El sandbox proporciona la API asíncrona course.embed y los alias helpers.embed y helpers.cosineSim; use siempre await course.embed(textos, { inputType: "query" o "passage" }) o await helpers.embed(...). Ningún otro helpers.* está disponible. El ejecutor admite await en el nivel superior. No use import, fetch, localStorage ni paquetes externos. El curso no ofrece una celda genérica para pegar código. Para cualquier artefacto, diagrama, panel, cuestionario o simulación solicitada, llame a queue_course_artifact; coloque el marcado y CSS en html y el código ejecutable en javascript. Use elementos button, input o select nativos para las acciones del estudiante. No responda con HTML sin procesar ni bloques de código. Defina cada función y destino DOM utilizado. Si la herramienta rechaza el artefacto, corrija el error y vuelva a llamarla. Diga que está listo solo después de que la herramienta lo acepte. Lea el código antes de explicarlo; nunca invente una implementación ni afirme que el código es privado o inaccesible. Cite los ID de página y los archivos utilizados.`
          : `You are the Course Assistant for Securing Agents. ${position} For course questions, use list_course_pages, search_course_pages, and read_course_page. For code, use list_course_code then read_course_source with the returned URI; for shared modules use list_course_runtime_files and read_course_runtime_source. Invoke tools through the API: never print tool arguments as JSON. The course runtime is browser JavaScript: default to HTML/JavaScript. The sandbox provides the asynchronous course.embed API plus helpers.embed and helpers.cosineSim compatibility aliases; always use await course.embed(texts, { inputType: "query" or "passage" }) or await helpers.embed(...). No other helpers.* API is available. Top-level await is supported by the artifact runner. Do not use import, fetch, localStorage, or external packages. The course has no generic pasteable code cell. For every requested artifact, diagram, dashboard, quiz, or simulation, call queue_course_artifact; put markup and CSS in html and executable code in javascript. Use native button, input, or select elements for learner actions. Do not answer with raw HTML or code fences. Define every function and DOM target you use. If the tool rejects the artifact, correct the reported error and call it again. Claim it is ready only after the tool accepts it. Inspect source before explaining code, and never invent an implementation or claim source is private or inaccessible. Cite course page ids and source files used.`,
      artifactCorrectionLimit: 2,
      recoverInlineToolIntent: async answer => {
        const intent = parseInlineCourseSourceIntent(answer);
        return intent ? resolveCourseSourceUri(intent.uri, targetPageId(attachedPage?.id || page.id)) : null;
      },
      recoverInlineArtifact: async answer => {
        const current = store.sessions.find(item => item.id === mountedSessionId);
        if (!current) return null;
        const artifact = artifactFromMarkdown(answer, `${current.title || "Course Assistant"} artifact`);
        if (!artifact) return null;
        const issue = artifactCodeIssue(artifact) || await validateArtifactRuntime(artifact);
        if (issue) {
          current.artifact = artifact;
          current.updatedAt = Date.now();
          persistStore(copy.saved);
          renderArtifact(false);
          activateView("artifact");
          artifactStatus.textContent = `Generated artifact rejected: ${issue}`;
          artifactStatus.classList.add("error");
          return {
            label: "queue_course_artifact",
            content: `Artifact rejected at runtime: ${issue}`,
            rejected: true,
            retryPrompt: `The browser rejected that artifact: ${issue} Inspect the exact source near the failing operation, then return one simpler corrected artifact using only fenced HTML and JavaScript. Initialize every value before reading or indexing it. Keep the requested controls and behavior. Do not explain the correction.`,
            answer: localized(
              `O artefato gerado está aberto para edição, mas não passou nas verificações do navegador: ${issue}`,
              `El artefacto generado está abierto para editar, pero no superó las comprobaciones del navegador: ${issue}`,
              `The generated artifact is open for editing, but it did not pass its browser checks: ${issue}`,
            ),
          };
        }
        current.artifact = artifact;
        current.updatedAt = Date.now();
        persistStore(copy.saved);
        renderArtifact(true);
        activateView("artifact");
        artifactStatus.textContent = copy.generatedReady;
        artifactStatus.classList.remove("error");
        return {
          label: "queue_course_artifact",
          content: `Validated and queued browser artifact “${artifact.title}” with ${artifact.html.length} HTML chars and ${artifact.javascript.length} JavaScript chars.`,
          answer: localized(
            "O artefato passou nas verificações do navegador e está aberto na visualização Artefato.",
            "El artefacto superó las comprobaciones del navegador y está abierto en la vista Artefacto.",
            "The artifact passed its browser checks and is open in the Artifact view.",
          ),
        };
      },
      initialContext: async () => ({ label: localized("página + índice de código · ", "página + índice de código · ", "page + code index · ") + page.id, content: await pageContext(page.id) }),
      buildTools: ({ tool, z, coursePage: readPage, coursePages: pages }) => {
        const catalog = pages();
        return [
          tool(async () => catalog.map(item => `${item.id} · ${item.title}`).join("\n"), {
            name: "list_course_pages",
            description: localized("Liste os IDs e títulos das páginas antes de escolher o que consultar.", "Enumere los ID y títulos de las páginas antes de elegir qué consultar.", "List every Securing Agents course page id and title before choosing what to inspect."),
            schema: z.object({}),
          }),
          tool(async ({ query }) => {
            return JSON.stringify(await searchCoursePages(query, readPage, catalog), null, 2);
          }, {
            name: "search_course_pages",
            description: localized("Busque no texto do curso e retorne as páginas mais relevantes com trechos curtos.", "Busque en el texto del curso y devuelva las páginas más relevantes con fragmentos breves.", "Search all course prose and return the most relevant page ids with short excerpts."),
            schema: z.object({ query: z.string().min(2).describe(localized("conceito ou frase a localizar no curso", "concepto o frase que debe localizarse en el curso", "concept or phrase to find across the course")) }),
          }),
          tool(async ({ page: id }) => readPage(targetPageId(id)), {
            name: "read_course_page",
            description: localized("Leia uma página completa depois que o mapa ou a busca a identificar.", "Lea una página completa después de identificarla mediante el mapa o la búsqueda.", "Read one complete Securing Agents page after the map or search identifies it."),
            schema: z.object({ page: z.enum(catalog.map(item => item.id)).describe("course page id") }),
          }),
          tool(async ({ page: id }) => {
            const target = targetPageId(id);
            return JSON.stringify((await courseCodeArtifacts(target)).map(item => ({ ...item, uri: `${target}#${item.id}` })), null, 2);
          }, {
            name: "list_course_code",
            description: localized("Liste o documento HTML, as células e os módulos JavaScript disponíveis em uma página.", "Enumere el documento HTML, los artefactos y los módulos JavaScript disponibles en una página.", "List the HTML document, exact JavaScript lesson artifacts, and page modules available on one course page."),
            schema: z.object({ page: z.enum(catalog.map(item => item.id)).describe("course page id") }),
          }),
          tool(async ({ uri }) => {
            const resolved = await resolveCourseSourceUri(uri, attachedPage?.id || "");
            return resolved?.content || `(unknown course source URI "${uri}")`;
          }, {
            name: "read_course_source",
            description: localized("Leia o código-fonte exato usando o URI retornado por list_course_code.", "Lea el código fuente exacto mediante el URI devuelto por list_course_code.", "Read exact lesson source using the single URI returned by list_course_code, for example 02c-deep#deep-src."),
            schema: z.object({ uri: z.string().min(1).describe("source URI returned by list_course_code") }),
          }),
          tool(async () => courseRuntimeFiles().map(item => `${item.file} · ${item.summary}`).join("\n"), {
            name: "list_course_runtime_files",
            description: localized("Liste os módulos JavaScript compartilhados e públicos do curso.", "Enumere los módulos JavaScript públicos y compartidos del curso.", "List public shared JavaScript modules such as _shared.js and _canvas.js."),
            schema: z.object({}),
          }),
          tool(async ({ file }) => courseRuntimeSource(file), {
            name: "read_course_runtime_source",
            description: localized("Leia o código-fonte exato de um módulo compartilhado listado.", "Lea el código fuente exacto de uno de los módulos compartidos enumerados.", "Read the exact public source of one shared course runtime module."),
            schema: z.object({ file: z.enum(courseRuntimeFiles().map(item => item.file)).describe("runtime filename") }),
          }),
          tool(async ({ title: artifactName, html, javascript }) => {
            const current = store.sessions.find(item => item.id === mountedSessionId);
            if (!current) return "No active Course Assistant session.";
            const candidate = cleanArtifact({ title: artifactName, html, javascript, updatedAt: Date.now() });
            const issue = artifactCodeIssue(candidate);
            if (issue) return `Artifact rejected before execution: ${issue} Correct the artifact, then call queue_course_artifact again.`;
            const runtimeIssue = await validateArtifactRuntime(candidate);
            if (runtimeIssue) return `Artifact rejected at runtime: ${runtimeIssue} Correct the artifact, then call queue_course_artifact again.`;
            current.artifact = candidate;
            current.updatedAt = Date.now(); persistStore(copy.saved); renderArtifact(true); activateView("artifact");
            return `Validated and queued browser artifact “${current.artifact.title}” with ${current.artifact.html.length} HTML chars and ${current.artifact.javascript.length} JavaScript chars.`;
          }, {
            name: "queue_course_artifact",
            description: localized("Valide e crie HTML/JavaScript editável e executável. Coloque marcação e CSS em html e código executável em javascript. Defina cada função e alvo DOM. Corrija qualquer rejeição e chame novamente. Para embeddings, use await course.embed ou await helpers.embed com inputType query ou passage; somente helpers.cosineSim também está disponível. Não use import, fetch, localStorage ou pacotes externos.", "Valide y cree HTML/JavaScript editable y ejecutable. Coloque el marcado y CSS en html y el código ejecutable en javascript. Defina cada función y destino DOM. Corrija cualquier rechazo y vuelva a llamar. Para embeddings, use await course.embed o await helpers.embed con inputType query o passage; también está disponible helpers.cosineSim. No use import, fetch, localStorage ni paquetes externos.", "Validate and queue editable HTML/JavaScript. Put markup and CSS in html and executable code in javascript. Define every function and DOM target. Correct any rejection and call again. For embeddings use await course.embed or await helpers.embed with inputType query or passage; only helpers.cosineSim is also available. Top-level await works. Do not use import, fetch, localStorage, external packages, or a nonexistent course cell."),
            schema: z.object({
              title: z.string().min(1).describe("short artifact title"),
              html: z.string().describe("HTML body or complete document; use an empty string when not needed"),
              javascript: z.string().describe("browser JavaScript; use an empty string when not needed"),
            }),
          }),
        ];
      },
      recursionLimit: 24,
    });
  };
  sessionSelect.addEventListener("change", async () => {
    flushArtifactSave(); store.activeId = sessionSelect.value; mountedSessionId = null;
    persistStore(copy.selected); renderArtifact(true); await mountSession();
  });
  const renameSession = () => {
    const session = activeSession();
    if (!session) return;
    const name = sessionName.value.replace(/\s+/g, " ").trim().slice(0, 72);
    if (!name) { renderSessions(); return; }
    session.title = name; session.manualTitle = true; session.updatedAt = Date.now();
    persistStore(copy.renamed);
  };
  sessionName.addEventListener("change", renameSession);
  sessionName.addEventListener("keydown", event => {
    if (event.key === "Enter") { event.preventDefault(); renameSession(); sessionName.blur(); }
  });
  usePageButton.addEventListener("click", async () => {
    const session = activeSession();
    if (!session) return;
    session.pageId = page.id; session.pageTitle = title; session.updatedAt = Date.now();
    mountedSessionId = null; persistStore(copy.attachedNow); await mountSession(session);
  });
  newSessionButton.addEventListener("click", async () => {
    flushArtifactSave();
    const current = activeSession();
    if (current && !current.history.length && !current.activity && !current.artifact && current.title === "New session") {
      sessionName.focus(); sessionName.select(); return;
    }
    if (store.sessions.length >= MAX_ASSISTANT_SESSIONS) { sessionStatus.textContent = `${copy.full} · ${MAX_ASSISTANT_SESSIONS}/${MAX_ASSISTANT_SESSIONS}`; return; }
    const session = newSession({ id: page.id, title }); store.sessions.unshift(session); store.activeId = session.id; mountedSessionId = null;
    persistStore(copy.created); renderArtifact(true); await mountSession(session);
  });
  shell.querySelector("[data-course-assistant-delete]").addEventListener("click", async () => {
    flushArtifactSave();
    if (chatApi?.stop) chatApi.stop();
    store.sessions = store.sessions.filter(item => item.id !== store.activeId);
    if (!store.sessions.length) store.sessions.push(newSession({ id: page.id, title }));
    store.activeId = store.sessions[0].id; mountedSessionId = null; persistStore(copy.deleted); renderArtifact(true); await mountSession();
  });
  const close = () => {
    shell.classList.remove("open");
    panel.setAttribute("aria-hidden", "true");
    launcher.setAttribute("aria-expanded", "false");
    if (priorFocus) priorFocus.focus();
  };
  const open = async () => {
    priorFocus = document.activeElement;
    shell.classList.add("open");
    panel.setAttribute("aria-hidden", "false");
    launcher.setAttribute("aria-expanded", "true");
    await mountSession();
    panel.querySelector("button[data-course-assistant-close]").focus();
  };
  launcher.addEventListener("click", () => shell.classList.contains("open") ? close() : open());
  shell.querySelectorAll("[data-course-assistant-close]").forEach(el => el.addEventListener("click", close));
  window.addEventListener("keydown", event => { if (event.key === "Escape" && shell.classList.contains("open")) close(); });
}

export function mountCourseLicenseNote() {
  if (document.querySelector(".course-license-note")) return;
  const main = document.querySelector("main");
  if (!main || !document.querySelector(".topbar")) return;
  const note = document.createElement("footer");
  note.className = "course-license-note";
  const language = document.documentElement.lang.toLowerCase();
  note.innerHTML = language.startsWith("pt")
    ? 'Material do curso, código de exemplo e diagramas originais: <a href="../../LICENSE">Apache-2.0</a>. Material externo citado mantém seus próprios termos; veja a <a href="assets/SKILL.html">proveniência</a>.'
    : language.startsWith("es")
      ? 'Prosa del curso, código de ejemplo y diagramas originales: <a href="../../LICENSE">Apache-2.0</a>. El material externo citado conserva sus propios términos; consulte la <a href="assets/SKILL.html">procedencia</a>.'
      : 'Course-authored prose, example code, and original diagrams: <a href="../../LICENSE">Apache-2.0</a>. Named external material keeps its own terms; see <a href="assets/SKILL.html">provenance</a>.';
  main.appendChild(note);
}
