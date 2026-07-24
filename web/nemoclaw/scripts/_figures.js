// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Course-specific inline figure builders kept out of the shared diagram engine.

export function ganttBarsSVG(workers, wallSeconds, title = "Concurrency vs serial time") {
  /* @doc <code>helpers.ganttBarsSVG(workers, wallSeconds, title)</code> ::
       Returns a Gantt-style concurrency chart as an SVG string (the string form of
       <code>helpers.viz.ganttBars</code>), for rendering in a live artifact with
       <code>view.html(...)</code>. <code>workers</code>: array of <code>{label, dt}</code>
       (seconds); compares the per-worker bars and their serial sum against the real
       <code>wallSeconds</code>.
  */
  const W = 560, BAR_H = 26, GAP = 8, PAD_L = 130, PAD_T = 52, PAD_B = 44, PAD_R = 60;
  const maxBarW = W - PAD_L - PAD_R;
  const serialTotal = workers.reduce((s, w) => s + (w.dt || 0), 0);
  const scale = dt => Math.round((dt / Math.max(serialTotal, 0.001)) * maxBarW);
  const H = PAD_T + (workers.length + 2) * (BAR_H + GAP) + PAD_B;
  const esc = t => String(t || "").replace(/[<>&]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
  let body = "";
  workers.forEach((w, i) => {
    const y = PAD_T + i * (BAR_H + GAP);
    const bw = scale(w.dt || 0);
    body += `<text x="${PAD_L - 6}" y="${y + BAR_H / 2 + 4}" text-anchor="end" font-size="11" font-family="ui-monospace,monospace" fill="#b0b0b0">${esc(w.label || `worker ${i + 1}`)}</text>`;
    body += `<rect x="${PAD_L}" y="${y}" width="${maxBarW}" height="${BAR_H}" rx="3" fill="#161616"/>`;
    body += `<rect x="${PAD_L}" y="${y}" width="${bw}" height="${BAR_H}" rx="3" fill="var(--gfx-blue,#3b82f6)" opacity="0.75"/>`;
    body += `<text x="${PAD_L + bw + 5}" y="${y + BAR_H / 2 + 4}" font-size="11" font-family="ui-monospace,monospace" fill="#7eb8ff">${(w.dt || 0).toFixed(2)}s</text>`;
  });
  const serY = PAD_T + workers.length * (BAR_H + GAP) + GAP;
  body += `<text x="${PAD_L - 6}" y="${serY + BAR_H / 2 + 4}" text-anchor="end" font-size="11" font-family="ui-monospace,monospace" fill="#d49c2c" font-weight="700">serial total</text>`;
  body += `<rect x="${PAD_L}" y="${serY}" width="${maxBarW}" height="${BAR_H}" rx="3" fill="#161616"/>`;
  body += `<rect x="${PAD_L}" y="${serY}" width="${maxBarW}" height="${BAR_H}" rx="3" fill="#d49c2c" opacity="0.35"/>`;
  body += `<text x="${PAD_L + maxBarW + 5}" y="${serY + BAR_H / 2 + 4}" font-size="11" font-family="ui-monospace,monospace" fill="#e8c87a">${serialTotal.toFixed(2)}s</text>`;
  const wallY = serY + BAR_H + GAP;
  const wallW = scale(wallSeconds);
  body += `<text x="${PAD_L - 6}" y="${wallY + BAR_H / 2 + 4}" text-anchor="end" font-size="11" font-family="ui-monospace,monospace" fill="var(--gfx-nvgreen,#76b900)" font-weight="700">wall time</text>`;
  body += `<rect x="${PAD_L}" y="${wallY}" width="${maxBarW}" height="${BAR_H}" rx="3" fill="#161616"/>`;
  body += `<rect x="${PAD_L}" y="${wallY}" width="${wallW}" height="${BAR_H}" rx="3" fill="var(--gfx-nvgreen,#76b900)" opacity="0.75"/>`;
  body += `<text x="${PAD_L + wallW + 5}" y="${wallY + BAR_H / 2 + 4}" font-size="11" font-family="ui-monospace,monospace" fill="#aee23a">${wallSeconds.toFixed(2)}s</text>`;
  const speedup = serialTotal / Math.max(wallSeconds, 0.001);
  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;background:#0d0d0d;border:1px solid #2a2a2a;border-radius:6px">
    <text x="${W / 2}" y="22" text-anchor="middle" font-size="12" font-family="ui-monospace,monospace" fill="#aee23a" font-weight="700">${esc(title)}</text>
    <text x="${W / 2}" y="38" text-anchor="middle" font-size="10" font-family="ui-monospace,monospace" fill="#6a6a6a">parallel speedup: ${speedup.toFixed(2)}x  (serial ${serialTotal.toFixed(2)}s / wall ${wallSeconds.toFixed(2)}s)</text>
    ${body}</svg>`;
}

// Inject SVG figures inline and wire the fit-to-screen lightbox.
const _figCache = {};
function _fetchSvg(src) {
  if (!_figCache[src]) {
    _figCache[src] = fetch(src).then(r => { if (!r.ok) throw new Error(r.status + " " + src); return r.text(); });
  }
  return _figCache[src];
}

function _safeSvgDocument(source) {
  const parsed = new DOMParser().parseFromString(String(source), "image/svg+xml");
  const svg = parsed.documentElement;
  if (!svg || svg.localName !== "svg" || parsed.querySelector("parsererror")) {
    throw new Error("response is not a valid SVG document");
  }
  svg.querySelectorAll("script,foreignObject,iframe,object,embed").forEach(node => node.remove());
  svg.querySelectorAll("*").forEach(node => {
    [...node.attributes].forEach(attribute => {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();
      if (name.startsWith("on")) node.removeAttribute(attribute.name);
      if ((name === "href" || name === "xlink:href") &&
          !/^(?:#|data:image\/(?:png|gif|jpeg|webp);base64,)/i.test(value)) {
        node.removeAttribute(attribute.name);
      }
    });
  });
  return document.importNode(svg, true);
}

let _lb = null;
const MOBILE_FIGURE_BREAKPOINT = 600;
const MOBILE_FIGURE_MIN_WIDTH = 720;
function _lightbox() {
  if (_lb) return _lb;
  let source = null;
  const root = document.createElement("div");
  root.className = "fig-lightbox";
  root.hidden = true;
  root.innerHTML = '<button class="fig-lightbox-x" type="button" aria-label="Close (Esc)">✕</button>'
                 + '<p class="fig-lightbox-hint">Swipe to pan</p>'
                 + '<div class="fig-lightbox-stage" role="dialog" aria-modal="true" aria-label="Enlarged figure"></div>';
  const stage = root.querySelector(".fig-lightbox-stage");
  const close = () => {
    root.hidden = true;
    stage.innerHTML = "";
    document.body.style.overflow = "";
    if (source) {
      source.dataset.state = "ready";
      source.setAttribute("aria-expanded", "false");
      source.focus();
      source = null;
    }
  };
  root.addEventListener("click", e => { if (e.target === root || e.target === stage) close(); });
  root.querySelector(".fig-lightbox-x").addEventListener("click", close);
  document.addEventListener("keydown", e => { if (e.key === "Escape" && !root.hidden) close(); });
  document.body.appendChild(root);
  _lb = {
    open(svg, trigger = null) {
      source = trigger;
      if (source) {
        source.dataset.state = "selected";
        source.setAttribute("aria-expanded", "true");
      }
      stage.innerHTML = "";
      svg.removeAttribute("style");
      svg.style.display = "block";
      svg.style.background = "var(--gfx-bg, var(--bg, #0d0d0d))";
      svg.style.borderRadius = "8px";
      const vb = (svg.getAttribute("viewBox") || "").split(/[\s,]+/).map(Number);
      if (vb.length === 4 && vb[2] > 0 && vb[3] > 0) {
        const fit = Math.min(window.innerWidth * 0.92 / vb[2], window.innerHeight * 0.9 / vb[3]);
        const readable = window.innerWidth <= MOBILE_FIGURE_BREAKPOINT
          ? MOBILE_FIGURE_MIN_WIDTH / vb[2]
          : 0;
        const s = Math.max(fit, readable);
        svg.style.width = Math.round(vb[2] * s) + "px";
        svg.style.height = Math.round(vb[3] * s) + "px";
      } else {
        svg.style.maxWidth = "92vw"; svg.style.maxHeight = "90vh";
      }
      stage.appendChild(svg);
      root.hidden = false;
      document.body.style.overflow = "hidden";
      root.querySelector(".fig-lightbox-x").focus();
    }
  };
  return _lb;
}

export function openFigureLightbox(svg, trigger = null) {
  if (!svg) return;
  _lightbox().open(svg.cloneNode(true), trigger);
}

export function wireFigureZoom(host, svg = null) {
  if (!host) return;
  const targetSvg = svg || (host.matches && host.matches("svg") ? host : host.querySelector("svg"));
  if (!targetSvg || targetSvg.dataset.figZoomDone === "1") return;
  targetSvg.dataset.figZoomDone = "1";
  const clickHost = host.matches && host.matches("svg") ? targetSvg : host;
  clickHost.classList.add("fig-zoom-host");
  clickHost.setAttribute("role", "button");
  clickHost.setAttribute("tabindex", "0");
  clickHost.dataset.state = "ready";
  clickHost.setAttribute("aria-expanded", "false");
  clickHost.setAttribute("aria-label", (targetSvg.getAttribute("aria-label") || "Figure") + ", click to enlarge");
  const open = () => openFigureLightbox(targetSvg, clickHost);
  clickHost.addEventListener("click", open);
  clickHost.addEventListener("keydown", e => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); }
  });
}

export function mountFigures(rootSel) {
  /* @doc <code>helpers.mountFigures(rootSel?)</code> ::
       Replace each <code>[data-svg-src]</code> placeholder under <code>rootSel</code> (default the whole
       document) with the SVG fetched from that path, injected inline so <code>var(--gfx-*)</code> theming
       applies, and made click/Enter to open a fit-to-screen lightbox. Auto-mounted on page load.
  */
  if (typeof document === "undefined") return;
  const scope = (rootSel && document.querySelector(rootSel)) || document;
  scope.querySelectorAll("[data-svg-src]:not([data-fig-done])").forEach(host => {
    host.dataset.figDone = "1";
    const src = host.getAttribute("data-svg-src");
    _fetchSvg(src).then(txt => {
      const svg = _safeSvgDocument(txt);
      host.replaceChildren(svg);
      host.style.aspectRatio = "";   // the injected SVG now sets its own height
      wireFigureZoom(host, svg);
    }).catch(() => {
      const link = document.createElement("a");
      link.href = src;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "Open figure in a new tab";
      host.replaceChildren(link);
    });
  });
}
