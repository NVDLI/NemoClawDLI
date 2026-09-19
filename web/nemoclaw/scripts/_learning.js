// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Optional sections start collapsed; links and printing can reveal their contents.
const CODE_DETAILS_SELECTOR = "details.rc-code-det, details.cf-panel-code-det";
const LESSON_PAGE_RE = /^(0[1-4][a-c]-[^/]+)\.html$/;
const LESSON_MAP_URL = new URL("../lesson-map.json", import.meta.url);
let printOpenStates = null;
let lessonMapPromise = null;

function supportsLearningView() {
  if (document.body?.hasAttribute("data-learning-view")) return true;
  const page = location.pathname.split("/").pop() || "index.html";
  return page === "index.html" || /^0[1-4][a-c]-[^/]+\.html$/.test(page);
}

function localeKey() {
  const lang = document.documentElement.lang.toLowerCase();
  if (lang.startsWith("zh")) return "zh";
  if (lang.startsWith("pt")) return "pt";
  if (lang.startsWith("es")) return "es";
  return "en";
}

function lessonId() {
  const page = location.pathname.split("/").pop() || "";
  return page.match(LESSON_PAGE_RE)?.[1] || "";
}

async function loadLessonMap() {
  if (!lessonMapPromise) {
    lessonMapPromise = fetch(LESSON_MAP_URL)
      .then(response => {
        if (!response.ok) throw new Error(`lesson map returned ${response.status}`);
        return response.json();
      })
      .then(lessonMap => {
        if (lessonMap?.schema !== "nemoclaw-lesson-map/1" || !Array.isArray(lessonMap.lessons)) {
          throw new Error("invalid lesson map");
        }
        return lessonMap;
      });
  }
  return lessonMapPromise;
}

function lessonWords() {
  const locale = localeKey();
  if (locale === "zh") {
    return {
      module: document.documentElement.lang.toLowerCase() === "zh-tw" ? "模組" : "模块",
      lesson: document.documentElement.lang.toLowerCase() === "zh-tw" ? "課時" : "课时", of: "/",
      transparencySummary: "AI 辅助内容 · 人工审核",
      transparencyBody: "本课程包含 AI 辅助编辑，并经过人工编辑审核。发布内容仍须遵守 NVIDIA 内容管控要求。技术图表和外部媒体的来源及许可记录见",
      imageProvenance: "图片来源",
      materialProvenance: "资料来源",
    };
  }
  if (locale === "pt") {
    return {
      module: "Módulo", lesson: "Lição", of: "de",
      transparencySummary: "Conteúdo com assistência de IA · revisão humana",
      transparencyBody: "Este curso inclui edições com assistência de IA e passa por revisão editorial humana. A publicação permanece sujeita aos controles de conteúdo da NVIDIA. Diagramas técnicos e mídias externas têm registros de procedência e licença em",
      imageProvenance: "Procedência das imagens",
      materialProvenance: "Procedência dos materiais",
    };
  }
  if (locale === "es") {
    return {
      module: "Módulo", lesson: "Lección", of: "de",
      transparencySummary: "Contenido con asistencia de IA · revisión humana",
      transparencyBody: "Este curso incluye ediciones asistidas por IA y pasa por revisión editorial humana. La publicación sigue sujeta a los controles de contenido de NVIDIA. Los diagramas técnicos y los recursos externos tienen registros de procedencia y licencia en",
      imageProvenance: "Procedencia de las imágenes",
      materialProvenance: "Procedencia de los materiales",
    };
  }
  return {
    module: "Module", lesson: "Lesson", of: "of",
    transparencySummary: "AI-assisted content · human reviewed",
    transparencyBody: "This course includes AI-assisted edits and undergoes human editorial review. Publication remains subject to NVIDIA content controls. Technical diagrams and external media have source and licensing records in",
    imageProvenance: "Image provenance",
    materialProvenance: "Material provenance",
  };
}

function mountLessonPosition(lessonMap) {
  const id = lessonId();
  const lesson = lessonMap.lessons.find(item => item.id === id);
  if (!lesson) return;
  const words = lessonWords();
  const eyebrow = document.querySelector(".hero .eyebrow");
  const moduleLessons = lessonMap.lessons.filter(item => item.module === lesson.module);
  const position = moduleLessons.findIndex(item => item.id === lesson.id) + 1;
  if (eyebrow) {
    eyebrow.textContent = `${words.module} ${lesson.module} · ${words.lesson} ${position} ${words.of} ${moduleLessons.length}`;
  }
}

async function mountLessonMap() {
  try {
    const lessonMap = await loadLessonMap();
    if (lessonId()) mountLessonPosition(lessonMap);
  } catch (error) {
    console.warn("Lesson map unavailable:", error);
  }
}

function mountContentTransparency() {
  if (document.querySelector("[data-content-transparency]")) return;
  const main = document.querySelector("main");
  if (!main) return;
  const words = lessonWords();
  const disclosure = document.createElement("details");
  disclosure.className = "course-disclosure publication-disclosure";
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

function mountHoverNoteDisclosures(root = document) {
  root.querySelectorAll("[data-hover-note]").forEach(host => {
    const anchor = host.closest(".sys-grid") || host;
    if (anchor.nextElementSibling?.hasAttribute("data-hover-note-disclosure")) return;
    const title = host.querySelector(".sys-name")?.textContent.trim();
    const copy = host.dataset.hoverNote?.trim();
    if (!title || !copy) return;
    const disclosure = root.createElement("details");
    disclosure.className = "course-disclosure hover-note-disclosure";
    disclosure.dataset.hoverNoteDisclosure = "";
    const summary = root.createElement("summary");
    summary.textContent = title.endsWith("*") ? title : `${title}*`;
    const body = root.createElement("p");
    body.textContent = copy;
    disclosure.append(summary, body);
    anchor.insertAdjacentElement("afterend", disclosure);
  });
}

function mountPrintFallback() {
  if (document.documentElement.dataset.learningPrintReady) return;
  document.documentElement.dataset.learningPrintReady = "true";
  window.addEventListener("beforeprint", () => {
    const blocks = [...document.querySelectorAll(
      `details.learning-block, ${CODE_DETAILS_SELECTOR}`
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

function mountOptionalDisclosures() {
  if (document.documentElement.dataset.learningDisclosuresReady) return;
  document.documentElement.dataset.learningDisclosuresReady = "true";
  document.querySelectorAll("details.learning-block").forEach(block => { block.open = false; });
}

export function revealHashTarget() {
  if (!location.hash) return;
  let id = "";
  try { id = decodeURIComponent(location.hash.slice(1)); } catch (_) { return; }
  const target = document.getElementById(id);
  let disclosure = target?.closest("details");
  while (disclosure) {
    disclosure.open = true;
    disclosure = disclosure.parentElement?.closest("details");
  }
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
  mountOptionalDisclosures();
  mountPrintFallback();
  mountHashReveal();
  mountContentTransparency();
  mountHoverNoteDisclosures();
  void mountLessonMap();
}
