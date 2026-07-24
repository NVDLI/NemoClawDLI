// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// _diagram.js holds the data-driven diagram grammar that used to live in _shared.js.
// Cells call helpers.viz.diagram(spec) with nodes/edges instead of hand-rolled SVG.
import { wireFigureZoom } from "./_figures.js";

const _DG_SANS = "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif";
const _dgEsc = (s) => String(s == null ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

// Emit CSS vars, not resolved colors, so diagrams re-theme without re-rendering.
// Hex fallbacks keep headless geometry checks readable.
function _dgTheme() {
  return {
    bg: "var(--bg,#0d0d0d)", e1: "var(--e1,#161616)", e2: "var(--e2,#1e1e1e)",
    bd: "var(--bd,#2a2a2a)", tx: "var(--tx,#f2f2f2)", td: "var(--td,#b0b0b0)",
    tf: "var(--tf,#6a6a6a)", arrow: "var(--dg-arrow,#8a8a8a)",
    kinds: {
      env: "var(--dg-env,#4b9fff)", agent: "var(--dg-agent,#8ecc2f)",
      tool: "var(--dg-tool,#a78bfa)", data: "var(--dg-data,#e0a83a)",
      model: "var(--dg-model,#2dd4bf)", neutral: "var(--dg-neutral,#9aa0a6)",
    },
  };
}

function _dgLayout(spec) {
  const nodes = spec.nodes || [];
  const cols = Math.max(...nodes.map((n) => n.x), 0) + 1;
  const rows = Math.max(...nodes.map((n) => n.y), 0) + 1;
  const maxLines = Math.max(...nodes.map((n) => (n.lines || []).length), 0);
  const hasSocket = nodes.some((n) => n.socket);
  const hasBottomReturn = (spec.edges || []).some((e) =>
    e.side === "bottom" || (String(e.fromPort || "").startsWith("bottom") && String(e.toPort || "").startsWith("bottom")));
  const boxW = spec.boxW || (cols >= 4 ? 280 : 268);
  const boxH = spec.boxH || Math.max(96, 54 + maxLines * 18);
  const padX = spec.padX == null ? 44 : spec.padX;
  const top = spec.top == null ? 52 : spec.top;
  const rowGap = spec.rowGap == null ? 74 : spec.rowGap;
  const gapX = spec.gapX == null ? 76 : spec.gapX;
  const overlapX = Math.max(0, Math.min(0.08, spec.overlapX || 0));
  const stepX = spec.stepX || Math.round(boxW + gapX - boxW * overlapX);
  const W = spec.width || Math.max(640, padX * 2 + boxW + (cols - 1) * stepX);
  const bottomPad = Math.max(hasSocket ? 74 : 52, hasBottomReturn ? 104 : 52);
  const H = spec.height ? spec.height - 64 : (top + rows * boxH + (rows - 1) * rowGap + bottomPad);
  const at = {};
  for (const n of nodes) {
    const x = cols > 1 ? padX + n.x * stepX : (W - boxW) / 2;
    const y = top + n.y * (boxH + rowGap);
    at[n.id] = { x, y, w: boxW, h: boxH, cx: x + boxW / 2, cy: y + boxH / 2 };
  }
  return { boxW, boxH, W, H, at, stepX, overlapX };
}

function _dgBox(n, g, t) {
  const kc = t.kinds[n.kind] || t.kinds.neutral;
  const { x, y, w } = g.at[n.id];
  const cx = x + w / 2;
  const body = n.lines || [];
  const lineGap = 18;
  const titleFs = 17;
  const bodyFs = 12;
  const titleY = y + 27;
  const ruleY = y + 39;
  const bodyY = y + 57;
  const lines = body.map((s, i) =>
    `<text x="${cx}" y="${bodyY + i * lineGap}" text-anchor="middle" font-size="${bodyFs}" ` +
    `font-family="${_DG_SANS}" fill="${t.td}">${_dgEsc(s)}</text>`).join("");
  const socket = (() => {
    if (!n.socket) return "";
    // Size the pill to the label (not a fixed inset) so it never clips, centered on the box and capped so it stays inside the card.
    const sw = Math.min(w - 12, Math.max(w - 84, n.socket.length * 7.0 + 24));
    const sx = cx - sw / 2;
    return `<rect x="${sx}" y="${y + g.boxH - 15}" width="${sw}" height="30" rx="15" ` +
      `fill="${t.bg}" stroke="${kc}" stroke-width="1.5" opacity="0.9"/>` +
      `<text x="${cx}" y="${y + g.boxH + 5}" text-anchor="middle" font-size="12" ` +
      `font-family="${_DG_SANS}" fill="${kc}" font-weight="700">${_dgEsc(n.socket)}</text>`;
  })();
  return (
    `<g filter="url(#fig-shadow)"><rect x="${x}" y="${y}" width="${w}" height="${g.boxH}" ` +
    `rx="10" fill="${t.e2}" stroke="${kc}" stroke-width="2"/></g>` +
    `<rect x="${x}" y="${y + 1}" width="8" height="${g.boxH - 2}" rx="6" fill="${kc}" opacity="0.78"/>` +
    `<path d="M ${x + 14} ${ruleY} H ${x + w - 14}" stroke="${kc}" stroke-width="1.2" opacity="0.26"/>` +
    `<text x="${cx}" y="${titleY}" text-anchor="middle" font-size="${titleFs}" font-family="${_DG_SANS}" ` +
    `fill="${kc}" font-weight="800">${_dgEsc(n.label)}</text>` + lines + socket
  );
}

// Edges render paths below boxes and label chips above them.
function _dgEdgeLabelChip(mx, my, label, kc, t) {
  if (!label) return "";
  // Size the pill to the text so long labels do not clip.
  const w = Math.max(46, label.length * 7.1 + 18);
  return `<rect x="${mx - w / 2}" y="${my - 13}" width="${w}" height="26" rx="13" fill="${t.e1}" stroke="${t.bd}"/>` +
    `<text x="${mx}" y="${my + 4}" text-anchor="middle" font-size="12" font-family="${_DG_SANS}" ` +
    `fill="${kc}" font-style="italic">${_dgEsc(label)}</text>`;
}

function _dgPort(box, port, offset = 0) {
  const p = port || "center";
  if (p === "top") return { x: box.cx + offset, y: box.y, nx: 0, ny: -1 };
  if (p === "bottom") return { x: box.cx + offset, y: box.y + box.h, nx: 0, ny: 1 };
  if (p === "left") return { x: box.x, y: box.cy + offset, nx: -1, ny: 0 };
  if (p === "right") return { x: box.x + box.w, y: box.cy + offset, nx: 1, ny: 0 };
  if (p === "top-left") return { x: box.x + box.w * 0.28, y: box.y, nx: 0, ny: -1 };
  if (p === "top-right") return { x: box.x + box.w * 0.72, y: box.y, nx: 0, ny: -1 };
  if (p === "bottom-left") return { x: box.x + box.w * 0.28, y: box.y + box.h, nx: 0, ny: 1 };
  if (p === "bottom-right") return { x: box.x + box.w * 0.72, y: box.y + box.h, nx: 0, ny: 1 };
  return { x: box.cx + offset, y: box.cy, nx: 0, ny: 0 };
}

function _dgEdge(e, g, t) {
  const a = g.at[e.from], b = g.at[e.to];
  const kc = t.kinds[e.tint] || t.arrow;
  if (e.from === e.to) {
    const rx = a.x + a.w - 4;
    return { path: `<path d="M ${rx} ${a.y + 64} C ${rx + 42} ${a.y + 70}, ${rx + 42} ${a.y + a.h - 18}, ${rx} ${a.y + a.h - 12}" ` +
      `stroke="${kc}" stroke-width="1.8" fill="none" marker-end="url(#fig-arrow)"/>`, chip: "" };
  }
  if (e.fromPort || e.toPort) {
    const start = _dgPort(a, e.fromPort, e.fromOffset || 0);
    const end = _dgPort(b, e.toPort, e.toOffset || 0);
    const bend = e.bend == null ? 58 : e.bend;
    const c1x = start.x + start.nx * bend;
    const c1y = start.y + start.ny * bend;
    const c2x = end.x + end.nx * bend;
    const c2y = end.y + end.ny * bend;
    const mx = (start.x + end.x) / 2 + (e.labelDx || 0);
    const my = (start.y + end.y) / 2 + (e.labelDy || 0);
    const path = `<path d="M ${start.x} ${start.y} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${end.x} ${end.y}" ` +
      `stroke="${t.arrow}" stroke-width="2.2" fill="none" marker-end="url(#fig-arrow)"/>`;
    return { path, chip: _dgEdgeLabelChip(mx, my, e.label, kc, t) };
  }
  if (Math.abs(a.cx - b.cx) < 1) {
    const down = a.cy <= b.cy;
    const ax = a.cx, bx = b.cx;
    const ay = down ? a.y + a.h : a.y;
    const by = down ? b.y : b.y + b.h;
    const bend = down ? 34 : -34;
    const my = (ay + by) / 2;
    const path = `<path d="M ${ax} ${ay} C ${ax} ${ay + bend}, ${bx} ${by - bend}, ${bx} ${by}" ` +
      `stroke="${t.arrow}" stroke-width="2.2" fill="none" marker-end="url(#fig-arrow)"/>`;
    return { path, chip: _dgEdgeLabelChip(ax, my, e.label, kc, t) };
  }
  const aLeftOfB = a.cx <= b.cx;
  const top = e.side !== "bottom";
  const ay = top ? a.y + 32 : a.y + a.h - 32;
  const by = top ? b.y + 32 : b.y + b.h - 32;
  const ax = aLeftOfB ? a.x + a.w : a.x;
  const bx = aLeftOfB ? b.x : b.x + b.w;
  const dir = aLeftOfB ? 1 : -1;
  const lift = top ? -34 : 34;
  const mx = (ax + bx) / 2, my = ay + lift;
  const path = `<path d="M ${ax} ${ay} C ${ax + 32 * dir} ${ay + lift}, ${bx - 32 * dir} ${by + lift}, ${bx} ${by}" ` +
    `stroke="${t.arrow}" stroke-width="2.2" fill="none" marker-end="url(#fig-arrow)"/>`;
  return { path, chip: _dgEdgeLabelChip(mx, top ? my - 12 : my + 12, e.label, kc, t) };
}

function _dgDefs(t) {
  return `<defs>` +
    `<marker id="fig-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">` +
    `<path d="M0,0 L10,5 L0,10 Z" fill="${t.arrow}"/></marker>` +
    `<filter id="fig-shadow" x="-20%" y="-20%" width="140%" height="140%">` +
    `<feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="#000000" flood-opacity="0.28"/></filter>` +
    `</defs>`;
}

export function diagramSVG(spec) {
  /* @doc <code>helpers.diagramSVG(spec)</code> ::
       Returns a themed node/edge figure as an SVG string (the string form of
       <code>helpers.viz.diagram</code>), so a live artifact can render a diagram with
       <code>view.html(...)</code>. Same <code>spec</code>: <code>{title?, nodes:[{id,
       label, kind, x, y, lines?}], edges:[{from, to, label?}]}</code>; <code>kind &isin;
       env|agent|tool|data|model|neutral</code>.
  */
  const t = _dgTheme();
  const g = _dgLayout(spec);
  const H = g.H;
  const edges = (spec.edges || []).map((e) => _dgEdge(e, g, t));
  const edgePaths = edges.map((x) => x.path).join("");
  const edgeChips = edges.map((x) => x.chip).join("");
  const boxes = spec.nodes.map((n) => _dgBox(n, g, t)).join("");
  return (
    `<svg viewBox="0 0 ${g.W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" ` +
    `aria-label="${_dgEsc(spec.aria || spec.title || "diagram")}" ` +
    `class="dg-svg" data-diagram-svg="1" style="width:100%;max-width:${spec.maxWidth || 1100}px;height:auto;display:block;margin:1.2em auto;border-radius:12px;cursor:zoom-in">` +
    _dgDefs(t) +
    // Explicit background survives SVG export and respects dark theme.
    `<rect x="0" y="0" width="${g.W}" height="${H}" rx="12" fill="${t.bg}" stroke="${t.bd}"/>` +
    // paths under boxes, boxes, then chips on top so no label hides behind a node.
    edgePaths + boxes + edgeChips + `</svg>`
  );
}

// Render a static node/edge figure into a page element on load (the canvas pages use the same API).
// Same data grammar as helpers.viz.diagram, but for a always-on page diagram rather than a cell-rendered one.
// Colors are var()-driven (see _dgTheme), so the figure follows the theme toggle on its own; no re-render.
export function mountDiagram(targetSel, spec) {
  const host = typeof targetSel === "string" ? document.querySelector(targetSel) : targetSel;
  if (!host) return;
  host.style.width = "100%";
  host.innerHTML = diagramSVG(spec);
  const svg = host.querySelector("svg.dg-svg");
  if (svg) wireFigureZoom(svg);
}
