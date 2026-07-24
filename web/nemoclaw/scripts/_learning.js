// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Low-fingerprint course depth control.
// Native <details> keeps optional sections independent.
// The complete course remains usable without JavaScript.

export const LEARNING_DEPTH_KEY = "nemoclaw_learning_depth_v1";

const DEPTHS = new Set(["guided", "applied", "complete"]);
const DEPTH_RANK = { guided: 0, applied: 1, complete: 2 };
const TIER_RANK = { applied: 1, deep: 2 };
const CODE_DETAILS_SELECTOR = "details.rc-code-det, details.cf-panel-code-det";
let printOpenStates = null;
let codeObserver = null;

function supportsLearningView() {
  if (document.body?.hasAttribute("data-learning-view")) return true;
  const page = location.pathname.split("/").pop() || "index.html";
  return page === "index.html" || /^0[1-4][a-c]-[^/]+\.html$/.test(page);
}

function storage() {
  try { return window.localStorage; } catch (_) { return null; }
}

export function readLearningDepth() {
  try {
    const depth = storage()?.getItem(LEARNING_DEPTH_KEY);
    return DEPTHS.has(depth) ? depth : "guided";
  } catch (_) {
    return "guided";
  }
}

export function saveLearningDepth(depth) {
  if (!DEPTHS.has(depth)) throw new Error("invalid learning depth");
  try { storage()?.setItem(LEARNING_DEPTH_KEY, depth); } catch (_) {}
  applyLearningDepth(depth);
  window.dispatchEvent(new CustomEvent("nemoclaw:learning-depth", { detail: { depth } }));
}

function codeDetails(root) {
  const found = [...(root.querySelectorAll?.(CODE_DETAILS_SELECTOR) || [])];
  if (root.matches?.(CODE_DETAILS_SELECTOR)) found.unshift(root);
  return found;
}

function applyCodeDepth(depth, root = document, onlyNew = false) {
  codeDetails(root).forEach(detail => {
    const initialized = detail.hasAttribute("data-learning-default-open");
    if (onlyNew && initialized) return;
    if (!initialized) detail.dataset.learningDefaultOpen = String(detail.open);
    detail.open = depth === "guided" ? false : detail.dataset.learningDefaultOpen === "true";
  });
}

export function applyLearningDepth(depth = readLearningDepth(), root = document) {
  if (!DEPTHS.has(depth)) depth = "guided";
  root.documentElement?.setAttribute("data-learning-depth", depth);
  root.querySelectorAll?.("details.learning-block[data-learning-tier]").forEach(block => {
    if (block.hasAttribute("data-learning-always-open")) {
      block.open = true;
      return;
    }
    const required = TIER_RANK[block.dataset.learningTier] ?? 2;
    block.open = DEPTH_RANK[depth] >= required;
  });
  applyCodeDepth(depth, root);
  root.querySelectorAll?.(".learning-depth-select").forEach(select => { select.value = depth; });
  return depth;
}

function mountCodeObserver() {
  if (codeObserver || !document.body) return;
  codeObserver = new MutationObserver(mutations => {
    const depth = readLearningDepth();
    mutations.forEach(mutation => mutation.addedNodes.forEach(node => {
      if (node.nodeType === Node.ELEMENT_NODE) applyCodeDepth(depth, node, true);
    }));
  });
  codeObserver.observe(document.body, { childList: true, subtree: true });
}

function makeDepthControl() {
  const locale = document.documentElement.lang.toLowerCase();
  const words = locale.startsWith("pt")
    ? { detail: "Detalhe", aria: "Nível de detalhe do curso", guided: "Guiado", applied: "Aplicado", complete: "Completo" }
    : locale.startsWith("es")
      ? { detail: "Detalle", aria: "Nivel de detalle del curso", guided: "Guiado", applied: "Aplicado", complete: "Completo" }
      : { detail: "Detail", aria: "Course detail level", guided: "Guided", applied: "Applied", complete: "Complete" };
  const label = document.createElement("label");
  label.className = "learning-depth-control";
  const text = document.createElement("span");
  text.textContent = words.detail;
  const select = document.createElement("select");
  select.className = "learning-depth-select";
  select.setAttribute("aria-label", words.aria);
  select.innerHTML = `
    <option value="guided">${words.guided}</option>
    <option value="applied">${words.applied}</option>
    <option value="complete">${words.complete}</option>`;
  select.addEventListener("change", () => saveLearningDepth(select.value));
  label.append(text, select);
  return label;
}

function mountPrintFallback() {
  if (document.documentElement.dataset.learningPrintReady) return;
  document.documentElement.dataset.learningPrintReady = "true";
  window.addEventListener("beforeprint", () => {
    const blocks = [...document.querySelectorAll(
      `details.learning-block[data-learning-tier], ${CODE_DETAILS_SELECTOR}`
    )];
    printOpenStates = blocks.map(block => ({ block, open: block.open }));
    blocks.forEach(block => { block.open = true; });
  });
  window.addEventListener("afterprint", () => {
    if (!printOpenStates) return;
    printOpenStates.forEach(({ block, open }) => { block.open = open; });
    printOpenStates = null;
  });
}

function revealHashTarget() {
  if (!location.hash) return;
  let id = "";
  try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; }
  const target = document.getElementById(id);
  const disclosure = target?.closest("details.learning-block[data-learning-tier]");
  if (disclosure) disclosure.open = true;
}

function mountHashReveal() {
  if (document.documentElement.dataset.learningHashReady) return;
  document.documentElement.dataset.learningHashReady = "true";
  window.addEventListener("hashchange", revealHashTarget);
  revealHashTarget();
}

export function mountLearningView() {
  if (!supportsLearningView()) return;
  const bar = document.querySelector(".topbar");
  if (!bar) return;
  if (!bar.querySelector(".learning-depth-control")) {
    const language = bar.querySelector(".language-menu");
    const pill = bar.querySelector(".key-pill");
    bar.insertBefore(makeDepthControl(), language || pill || null);
  }
  mountCodeObserver();
  mountPrintFallback();
  try { storage()?.setItem(LEARNING_DEPTH_KEY, "guided"); } catch (_) {}
  applyLearningDepth("guided");
  mountHashReveal();
}
