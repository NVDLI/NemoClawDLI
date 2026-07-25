// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { languageManifestUrl } from "./_locale.js";

const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
let drift, languages, activeStatus = "all", activeKind = "pages", selected;
const localeSelect = $("#loc-locale");

async function languageManifest() {
  const url = languageManifestUrl();
  try {
    const response = await fetch(url, {cache:"no-store"});
    if (!response.ok) return null;
    const data = await response.json();
    return data?.schema === "nemoclaw-languages/1" ? {data, url} : null;
  } catch (_) { return null; }
}

function courseRows() {
  return drift.pages.filter(row => row.path.startsWith("web/nemoclaw/") && row.file !== "SKILL.html");
}

function activeRows() { return activeKind === "assets" ? (drift.assets || []) : courseRows(); }

function counts() {
  const out = {};
  activeRows().forEach(row => { out[row.status] = (out[row.status] || 0) + 1; });
  return out;
}

function renderFilters() {
  const found = counts();
  const statuses = ["all", "current", "stale", "blocked", "needs-review", "missing"];
  $("#loc-filters").innerHTML = statuses.map(status => {
    const n = status === "all" ? activeRows().length : (found[status] || 0);
    return `<button class="loc-filter${activeStatus===status?' active':''}" data-status="${status}">${status} ${n}</button>`;
  }).join("");
  document.querySelectorAll(".loc-filter").forEach(button => button.addEventListener("click", () => {
    activeStatus = button.dataset.status; renderFilters(); renderPages();
  }));
}

function renderPages() {
  const rows = activeRows().filter(row => activeStatus === "all" || row.status === activeStatus);
  $("#loc-pages").innerHTML = rows.map(row => `<button class="loc-page${selected?.path===row.path?' active':''}" data-path="${esc(row.path)}"><span class="loc-dot ${esc(row.status)}"></span><span><b>${esc(row.file)}</b><small>${esc(row.status)}</small></span></button>`).join("") || '<div class="loc-empty">No pages in this state.</div>';
  document.querySelectorAll(".loc-page").forEach(button => button.addEventListener("click", () => selectPage(button.dataset.path)));
}

function baseFor(code) {
  const entry = languages?.data.languages.find(item => item.code === code);
  return entry ? new URL(entry.url, languages.url) : null;
}

function shortHash(value) { return value ? value.slice(0, 12) : "none"; }

async function selectPage(path) {
  selected = activeRows().find(row => row.path === path);
  if (!selected) return;
  const sourceBase = baseFor(languages?.data.default || "en") || new URL("./", location.href);
  const targetBase = baseFor(drift.url_code) || new URL(`../../i18n/${drift.url_code}/web/nemoclaw/`, location.href);
  const relative = activeKind === "assets" ? selected.path.replace(/^web\/nemoclaw\//, "") : selected.file;
  const sourceUrl = new URL(relative, sourceBase);
  const targetUrl = new URL(relative, targetBase);
  if (activeKind === "assets") {
    const [sourceSvg, targetSvg] = await Promise.all([
      fetch(sourceUrl).then(response => response.text()), fetch(targetUrl).then(response => response.text()),
    ]);
    const documentFor = svg => `<!doctype html><link rel="stylesheet" href="styles/_style.css"><style>html,body{margin:0;min-height:100%;display:grid;place-items:center;background:var(--bg);overflow:auto}svg{max-width:96%;height:auto}</style>${svg}`;
    $("#loc-source").removeAttribute("src"); $("#loc-target").removeAttribute("src");
    $("#loc-source").srcdoc = documentFor(sourceSvg); $("#loc-target").srcdoc = documentFor(targetSvg);
  } else {
    $("#loc-source").removeAttribute("srcdoc"); $("#loc-target").removeAttribute("srcdoc");
    $("#loc-source").src = sourceUrl; $("#loc-target").src = targetUrl;
  }
  $("#loc-source-label").textContent = shortHash(selected.source_sha256);
  $("#loc-target-label").textContent = selected.status;
  $("#loc-evidence").innerHTML = `<strong>${esc(selected.file)}</strong><span>source <code>${shortHash(selected.source_sha256)}</code></span><span>reviewed <code>${shortHash(selected.reviewed_source_sha256)}</code></span><span>target <code>${shortHash(selected.target_sha256)}</code></span>`;
  const findings = selected.quality || [];
  $("#loc-findings").innerHTML = `<strong>${esc(selected.status)}</strong>${findings.length ? `<ul>${findings.map(item => `<li><code>${esc(item.code)}</code> ${esc(item.detail)}</li>`).join("")}</ul>` : '<span> · no static language/structure findings</span>'}<div>After reviewing the complete page: <code>python3 scripts/validation/localization_audit.py --locale ${esc(drift.locale)} --accept ${esc(selected.path)}</code></div>`;
  renderPages();
}

async function boot() {
  const lang = await languageManifest();
  const localized = (lang?.data.languages || []).filter(item => item.code !== (lang?.data.default || "en"));
  if (lang && !localized.length) {
    languages = lang;
    if (localeSelect) {
      localeSelect.innerHTML = '<option value="en">English only</option>';
      localeSelect.hidden = true;
      document.querySelector('label[for="loc-locale"]')?.setAttribute("hidden", "");
    }
    $("#loc-target-name").textContent = "No localized target";
    $("#loc-summary").textContent = "This build contains English only.";
    $("#loc-pages").innerHTML = '<div class="loc-empty">No localized course was published in this build.</div>';
    $("#loc-findings").textContent = "Use a multilingual build to review translation drift.";
    return;
  }
  if (localeSelect) {
    localeSelect.replaceChildren(...localized.map(item => {
      const option = document.createElement("option");
      option.value = item.code;
      option.textContent = item.native_label || item.label || item.locale;
      return option;
    }));
  }
  const requestedValue = new URLSearchParams(location.search).get("locale")
    || localeSelect?.value
    || localized[0]?.code;
  const requested = localized.some(item => item.code === requestedValue) ? requestedValue : (localized[0]?.code || requestedValue);
  if (localeSelect) localeSelect.value = requested;
  const driftResponse = await fetch(`assets/localization-${requested}.json`, {cache:"no-store"});
  if (!driftResponse.ok) throw new Error(`drift manifest unavailable (${driftResponse.status})`);
  drift = await driftResponse.json(); languages = lang;
  $("#loc-target-name").textContent = drift.native_label || drift.label || drift.locale;
  const c = counts();
  const assets = drift.asset_counts || {};
  $("#loc-summary").textContent = `${c.current || 0} pages current · ${assets.current || 0} SVGs current · ${(c.stale || 0) + (c.blocked || 0) + (c['needs-review'] || 0) + (c.missing || 0) + (assets.stale || 0) + (assets.blocked || 0) + (assets['needs-review'] || 0) + (assets.missing || 0)} pending`;
  document.querySelectorAll("#loc-kinds button").forEach(button => button.addEventListener("click", () => {
    activeKind = button.dataset.kind; activeStatus = "all"; selected = null;
    document.querySelectorAll("#loc-kinds button").forEach(item => item.classList.toggle("active", item === button));
    renderFilters(); renderPages(); const first = activeRows()[0]; if (first) selectPage(first.path);
  }));
  renderFilters(); renderPages();
  const first = courseRows().find(row => row.status !== "missing") || courseRows()[0];
  if (first) selectPage(first.path);
}

localeSelect?.addEventListener("change", () => {
  const url = new URL(location.href); url.searchParams.set("locale", localeSelect.value); location.href = url;
});

boot().catch(error => {
  $("#loc-summary").textContent = "Localization data unavailable";
  $("#loc-pages").innerHTML = `<div class="loc-empty">${esc(error.message)}</div>`;
});
