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
const LESSON_PAGE_RE = /^(0[1-4][a-c]-[^/]+)\.html$/;
const PROFILE_URL = new URL("../learning-profile.json", import.meta.url);
let printOpenStates = null;
let codeObserver = null;
let profilePromise = null;

function supportsLearningView() {
  if (document.body?.hasAttribute("data-learning-view")) return true;
  const page = location.pathname.split("/").pop() || "index.html";
  return page === "index.html" || /^0[1-4][a-c]-[^/]+\.html$/.test(page);
}

function storage() {
  try { return window.localStorage; } catch (_) { return null; }
}

function localeKey() {
  const lang = document.documentElement.lang.toLowerCase();
  if (lang.startsWith("pt")) return "pt";
  if (lang.startsWith("es")) return "es";
  return "en";
}

function lessonId() {
  const page = location.pathname.split("/").pop() || "";
  return page.match(LESSON_PAGE_RE)?.[1] || "";
}

async function loadLearningProfile() {
  if (!profilePromise) {
    profilePromise = fetch(PROFILE_URL)
      .then(response => {
        if (!response.ok) throw new Error(`learning profile returned ${response.status}`);
        return response.json();
      })
      .then(profile => {
        if (profile?.schema !== "nemoclaw-learning-profile/1" || !Array.isArray(profile.lessons)) {
          throw new Error("invalid learning profile");
        }
        return profile;
      });
  }
  return profilePromise;
}

function profileWords() {
  const locale = localeKey();
  if (locale === "pt") {
    return {
      lesson: "Lição", of: "de",
      transparencySummary: "Conteúdo com assistência de IA · revisão humana",
      transparencyBody: "Este curso inclui edições com assistência de IA e passa por revisão editorial humana. A publicação permanece sujeita aos controles de conteúdo da NVIDIA. Diagramas técnicos e mídias externas têm registros de procedência e licença em",
      imageProvenance: "Procedência das imagens",
      materialProvenance: "Procedência dos materiais",
    };
  }
  if (locale === "es") {
    return {
      lesson: "Lección", of: "de",
      transparencySummary: "Contenido con asistencia de IA · revisión humana",
      transparencyBody: "Este curso incluye ediciones asistidas por IA y pasa por revisión editorial humana. La publicación sigue sujeta a los controles de contenido de NVIDIA. Los diagramas técnicos y los recursos externos tienen registros de procedencia y licencia en",
      imageProvenance: "Procedencia de las imágenes",
      materialProvenance: "Procedencia de los materiales",
    };
  }
  return {
    lesson: "Lesson", of: "of",
    transparencySummary: "AI-assisted content · human reviewed",
    transparencyBody: "This course includes AI-assisted edits and undergoes human editorial review. Publication remains subject to NVIDIA content controls. Technical diagrams and external media have source and licensing records in",
    imageProvenance: "Image provenance",
    materialProvenance: "Material provenance",
  };
}

function mountLessonPosition(profile) {
  const id = lessonId();
  const lesson = profile.lessons.find(item => item.id === id);
  if (!lesson) return;
  const words = profileWords();
  const eyebrow = document.querySelector(".hero .eyebrow");
  const moduleLessons = profile.lessons.filter(item => item.module === lesson.module);
  const position = moduleLessons.findIndex(item => item.id === lesson.id) + 1;
  if (eyebrow) {
    eyebrow.textContent = `Module ${lesson.module} · ${words.lesson} ${position} ${words.of} ${moduleLessons.length}`;
  }
  document.documentElement.dataset.learningProfile = "guided";
}

async function mountLearningProfile() {
  try {
    const profile = await loadLearningProfile();
    if (lessonId()) mountLessonPosition(profile);
  } catch (error) {
    console.warn("Learning profile unavailable:", error);
  }
}

function mountContentTransparency() {
  if (document.querySelector("[data-content-transparency]")) return;
  const main = document.querySelector("main");
  if (!main) return;
  const words = profileWords();
  const disclosure = document.createElement("details");
  disclosure.className = "publication-disclosure";
  disclosure.dataset.contentTransparency = "ai-assisted-human-reviewed";

  const summary = document.createElement("summary");
  summary.textContent = words.transparencySummary;
  const body = document.createElement("p");
  body.append(document.createTextNode(`${words.transparencyBody} `));
  const imageLink = document.createElement("a");
  imageLink.href = "assets/SKILL.html";
  imageLink.textContent = words.imageProvenance;
  const materialLink = document.createElement("a");
  materialLink.href = "mats/SKILL.html";
  materialLink.textContent = words.materialProvenance;
  body.append(imageLink, document.createTextNode(" · "), materialLink, document.createTextNode("."));
  disclosure.append(summary, body);
  main.insertBefore(disclosure, main.querySelector(":scope > footer"));
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
  mountContentTransparency();
  void mountLearningProfile();
}
