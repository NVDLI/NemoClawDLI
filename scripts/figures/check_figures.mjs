#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Browser-rendered figure gate. Detects overlap, bounds, connector, and no-edge diagram issues.
// Self-tests each detector before reporting clean.
import fs from "fs"; import http from "http"; import path from "path"; import { fileURLToPath } from "url";
import { createRequire } from "module";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const NEMO = process.env.FIG_NEMO || path.resolve(HERE, "..", "..", "web", "nemoclaw");
const COURSE_SCRIPTS = path.join(NEMO, "scripts");
// Stage an ESM shim beside course modules so relative imports resolve under Node.
const tmp = path.join(COURSE_SCRIPTS, `.figcheck_shared-${process.pid}.mjs`);
fs.writeFileSync(tmp, fs.readFileSync(path.join(COURSE_SCRIPTS, "_shared.js")));
let shared;
try { shared = await import("file://" + tmp); }
finally { try { fs.unlinkSync(tmp); } catch { /* best-effort cleanup */ } }
const { diagramSVG } = shared;

const { chromium } = require("playwright-core");

async function renderedPolicyMap() {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, "http://127.0.0.1").pathname).replace(/^\/+/, "") || "index.html";
    if (rel === "index.html") { res.writeHead(200, { "content-type": "text/html" }); res.end('<div id="pm"></div>'); return; }
    const file = path.resolve(NEMO, rel);
    if ((!file.startsWith(NEMO + path.sep) && file !== NEMO) || !fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { "content-type": file.endsWith(".js") ? "text/javascript" : "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_BIN });
  try {
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${port}/index.html`);
    return await page.evaluate(async () => {
      const shared = await import("/scripts/_shared.js");
      shared.mountPolicyMap("#pm");
      return document.querySelector("#pm .pmap-svg")?.innerHTML || "";
    });
  } finally { await browser.close(); server.close(); }
}

const MONO = 0.6, SANS = 0.52;       // em-width per char; monospace is wider
function attrs(s) {
  return Object.fromEntries([...s.matchAll(/([:\w-]+)="([^"]*)"/g)].map((m) => [m[1], m[2]]));
}
function numAttr(a, k, d = 0) {
  const v = a[k];
  return v == null ? d : +String(v).replace(/[^\d.-].*$/, "");
}
function viewBox(svg) {
  const m = svg.match(/viewBox="\s*([\d.-]+)\s+([\d.-]+)\s+([\d.]+)\s+([\d.]+)/);
  return m ? { x: +m[1], y: +m[2], w: +m[3], h: +m[4] } : null;
}
function translate(a) {
  const m = String(a.transform || "").match(/translate\(\s*([\d.-]+)(?:[,\s]+([\d.-]+))?/);
  return m ? { x: +m[1], y: +(m[2] || 0) } : { x: 0, y: 0 };
}
function svgElementWalk(svg, visit) {
  const stack = [{ x: 0, y: 0 }];
  const re = /<\/g>|<g\b([^>]*)>|<rect\b([^>]*)\/?>|<text\b([^>]*)>([\s\S]*?)<\/text>/g;
  for (const m of svg.matchAll(re)) {
    const tok = m[0];
    if (tok === "</g>") { if (stack.length > 1) stack.pop(); continue; }
    const cur = stack[stack.length - 1];
    if (tok.startsWith("<g")) {
      const tr = translate(attrs(m[1] || ""));
      stack.push({ x: cur.x + tr.x, y: cur.y + tr.y });
      continue;
    }
    visit(tok.startsWith("<rect") ? "rect" : "text", m, cur);
  }
}
function textWithoutTags(markup) {
  let output = "", insideTag = false;
  for (const character of String(markup || "")) {
    if (character === "<") { insideTag = true; continue; }
    if (character === ">") { insideTag = false; continue; }
    if (!insideTag) output += character;
  }
  return output;
}
// Estimate text boxes from SVG anchors, font size, character count, and simple translate() groups.
function textBoxes(svg) {
  const out = [];
  svgElementWalk(svg, (kind, m, tr) => {
    if (kind !== "text") return;
    const a = attrs(m[3] || "");
    const txt = textWithoutTags(m[4]).replace(/&[a-z]+;|&#\d+;/g, "x").trim();
    if (!txt) return;
    const fs2 = numAttr(a, "font-size", 12);
    const x = tr.x + numAttr(a, "x");
    const y = tr.y + numAttr(a, "y");
    const anc = a["text-anchor"] === "middle" ? "middle" : a["text-anchor"] === "end" ? "end" : "start";
    const w = txt.length * fs2 * (/mono/i.test(a["font-family"] || "") ? MONO : SANS);   // estimated text width
    const l = anc === "middle" ? x - w / 2 : anc === "end" ? x - w : x;   // left edge depends on the anchor
    out.push({ l, r: l + w, t: y - fs2 * 0.8, b: y + fs2 * 0.25, y, anc, txt });   // box: y is the baseline, so t is above it
  });
  return out;
}
// The node boxes of a relational diagram: the rounded rects inside the shadow group.
// Used to test whether connector curves pass through unrelated boxes and whether overlap is excessive.
function nodeBoxes(svg) {
  return [...svg.matchAll(/<g filter="url\(#fig-shadow\)"><rect[^>]*\bx="([\d.]+)"[^>]*\by="([\d.]+)"[^>]*\bwidth="([\d.]+)"[^>]*\bheight="([\d.]+)"[^>]*rx="([\d.]+)"/g)]
    .map((m) => ({ x: +m[1], y: +m[2], w: +m[3], h: +m[4], rx: +m[5] }));
}
function staticCardBoxes(svg) {
  const vb = viewBox(svg);
  const out = [];
  svgElementWalk(svg, (kind, m, tr) => {
    if (kind !== "rect") return;
    const a = attrs(m[2] || "");
    const b = { x: tr.x + numAttr(a, "x"), y: tr.y + numAttr(a, "y"), w: numAttr(a, "width"), h: numAttr(a, "height"), rx: numAttr(a, "rx") };
    if (b.w < 150 || b.h < 64 || b.rx < 6) return;
    if (vb && b.w > vb.w * 0.72 && b.h > vb.h * 0.62) return;
    out.push(b);
  });
  return out;
}
// Cubic bezier point at parameter t, given the 4 control points P.
// Used to sample a connector curve so we can test whether it runs through an unrelated box.
function bez(P, t) { const m = 1 - t; return [
  m*m*m*P[0][0] + 3*m*m*t*P[1][0] + 3*m*t*t*P[2][0] + t*t*t*P[3][0],
  m*m*m*P[0][1] + 3*m*m*t*P[1][1] + 3*m*t*t*P[2][1] + t*t*t*P[3][1]]; }

// Visual geometry checks static text scans cannot see.
function svgProblems(svg, { checkEdges = false } = {}) {
  const out = [], T = textBoxes(svg), E = 1.5;   // erode 1.5px so merely-touching text is fine
  // every pair of text boxes: report if their eroded rectangles intersect (a label collision)
  for (let i = 0; i < T.length; i++) for (let j = i + 1; j < T.length; j++) {
    const A = T[i], B = T[j];
    if (A.l < B.r - E && B.l < A.r - E && A.t < B.b - E && B.t < A.b - E)
      out.push(`text overlaps text: "${A.txt.slice(0, 26)}" / "${B.txt.slice(0, 26)}"`);
  }
  const vb = svg.match(/viewBox="\s*([\d.-]+)\s+([\d.-]+)\s+([\d.]+)\s+([\d.]+)/);
  if (vb) {
    const minx = +vb[1], miny = +vb[2], W = +vb[3], H = +vb[4];   // the figure's own coordinate bounds
    // any text box reaching outside the viewBox (with a 2px tolerance) is clipped on screen
    for (const t of T) if (t.l < minx - 2 || t.r > minx + W + 2 || t.t < miny - 2 || t.b > miny + H + 2)
      out.push(`text past figure bounds: "${t.txt.slice(0, 26)}"`);
  }
  if (checkEdges) {
    const B = nodeBoxes(svg);                     // the diagram's node boxes
    // Ignore decimal-rounding noise; report any visible box overlap.
    for (let a = 0; a < B.length; a++) for (let b = a + 1; b < B.length; b++) {
      const A = B[a], C = B[b];
      const ow = Math.max(0, Math.min(A.x + A.w, C.x + C.w) - Math.max(A.x, C.x));
      const oh = Math.max(0, Math.min(A.y + A.h, C.y + C.h) - Math.max(A.y, C.y));
      const frac = (ow * oh) / Math.max(1, Math.min(A.w * A.h, C.w * C.h));
      if (frac > 0.01) out.push("node boxes overlap");
    }
    // each connector path: sample the curve and flag if it passes through a box that is not its endpoint
    for (const m of svg.matchAll(/<path d="M ([\d.]+) ([\d.]+) C ([\d.]+) ([\d.]+), ([\d.]+) ([\d.]+), ([\d.]+) ([\d.]+)"/g)) {
      const P = [[+m[1],+m[2]], [+m[3],+m[4]], [+m[5],+m[6]], [+m[7],+m[8]]];   // the 4 bezier control points
      // the boxes this connector actually links (its start/end land on or near them)
      const ends = B.filter((bx) => { const near = (p) => p[0] >= bx.x-3 && p[0] <= bx.x+bx.w+3 && p[1] >= bx.y-3 && p[1] <= bx.y+bx.h+3; return near(P[0]) || near(P[3]); });
      for (let t = 0.1; t <= 0.9; t += 0.1) { const [x, y] = bez(P, t);   // walk along the curve
        for (const bx of B) { if (ends.includes(bx)) continue;            // skip the boxes it legitimately links
          if (x > bx.x && x < bx.x+bx.w && y > bx.y && y < bx.y+bx.h) { out.push("a connector crosses a box it does not link"); t = 9; break; } } }
    }
  }
  return out;
}

const FLOW = /\b(path|paths|trajector\w*|flow|pipeline|sequence|steps?|then|leads?|chain|into|through|cycle|loop|stages?)\b/i;
// Flag framed lists that claim to be relationship diagrams but draw no edges.
function uselessSpec(spec) {
  const nodes = spec.nodes || [], edges = spec.edges || [];
  if (nodes.length >= 3 && edges.length === 0) {                 // enough boxes to imply structure, but no connections
    const framing = [spec.kicker, spec.title, spec.caption, spec.aria].filter(Boolean).join(" ");
    const m = framing.match(FLOW);                              // does the framing language promise a relationship?
    if (m) return `${nodes.length} boxes, no edges, but the framing implies a relationship ("${m[0]}") and draws none -- a bordered list, not a diagram`;
  }
  return null;
}

function flowOrderProblems(spec) {
  const out = [];
  const at = Object.fromEntries((spec.nodes || []).map((n) => [n.id, n]));
  for (const e of spec.edges || []) {
    const bottomReturn = String(e.fromPort || "").startsWith("bottom") && String(e.toPort || "").startsWith("bottom");
    if (e.from === e.to || e.return === true || e.side === "bottom" || bottomReturn) continue;
    const a = at[e.from], b = at[e.to];
    if (!a || !b) continue;
    if (a.x > b.x) out.push(`forward edge runs backward: ${e.from} -> ${e.to}`);
  }
  return out;
}

function renderedBoxWidth(svg) {
  const vb = svg.match(/viewBox="\s*[\d.-]+\s+[\d.-]+\s+([\d.]+)\s+([\d.]+)/);
  if (!vb) return null;
  const viewW = +vb[1];
  const mw = (svg.match(/max-width:([\d.]+)px/) || [])[1];
  const renderW = Math.min(mw ? +mw : 1076, 1076, viewW);
  const boxes = nodeBoxes(svg);
  if (!boxes.length) return null;
  return Math.min(...boxes.map((b) => b.w * renderW / viewW));
}

function compositionProblems(svg, { includeStaticCards = false, checkInterBox = true, checkDensity = true, checkBalance = true, checkCenter = false, minBorderPad = 8 } = {}) {
  const out = [];
  const B = includeStaticCards ? staticCardBoxes(svg) : nodeBoxes(svg);
  if (!B.length) return out;
  const T = textBoxes(svg);
  if (checkInterBox) {
    for (let a = 0; a < B.length; a++) for (let b = a + 1; b < B.length; b++) {
      const A = B[a], C = B[b];
      const vOverlap = Math.max(0, Math.min(A.y + A.h, C.y + C.h) - Math.max(A.y, C.y));
      const hOverlap = Math.max(0, Math.min(A.x + A.w, C.x + C.w) - Math.max(A.x, C.x));
      const hGap = Math.max(0, Math.max(A.x, C.x) - Math.min(A.x + A.w, C.x + C.w));
      const vGap = Math.max(0, Math.max(A.y, C.y) - Math.min(A.y + A.h, C.y + C.h));
      if (vOverlap > Math.min(A.h, C.h) * 0.35 && hGap > 0 && hGap < 58) out.push(`box gap too tight: ${hGap.toFixed(1)}px`);
      if (hOverlap > Math.min(A.w, C.w) * 0.35 && vGap > 0 && vGap < 58) out.push(`row gap too tight: ${vGap.toFixed(1)}px`);
    }
  }
  for (const b of B) {
    const inside = T.filter((t) => (t.l + t.r) / 2 >= b.x && (t.l + t.r) / 2 <= b.x + b.w && t.y >= b.y && t.y <= b.y + b.h);
    if (!inside.length) continue;
    const top = Math.min(...inside.map((t) => t.t));
    const bottom = Math.max(...inside.map((t) => t.b));
    const topPad = top - b.y;
    const bottomPad = b.y + b.h - bottom;
    const density = (bottom - top) / b.h;
    const centerDelta = ((top + bottom) / 2) - (b.y + b.h / 2);
    if (checkDensity && density < 0.34) out.push(`box content too sparse: ${(density * 100).toFixed(0)}% vertical use`);
    if (topPad < minBorderPad || bottomPad < minBorderPad) out.push("box text too close to border");
    const centerEligible = !includeStaticCards || (b.h <= 130 && inside.length <= 5 && inside.every((t) => t.anc === "middle"));
    if (checkCenter && centerEligible && Math.abs(centerDelta) > Math.max(7, b.h * 0.08)) out.push(`box text off-center: ${centerDelta.toFixed(1)}px`);
    if (checkBalance && Math.abs(topPad - bottomPad) > b.h * 0.34) out.push(`box text vertically imbalanced: top ${topPad.toFixed(1)}px bottom ${bottomPad.toFixed(1)}px`);
  }
  return out;
}

function fidelityProblems(svg) {
  const out = [];
  if (!/class="[^"]*\bdg-svg\b/.test(svg) || !/data-diagram-svg="1"/.test(svg)) {
    out.push("generated diagram is not marked as a zoomable dg-svg");
  }
  if (nodeBoxes(svg).length && !/width="8"[^>]*opacity="0\.78"/.test(svg)) {
    out.push("generated boxed diagram lacks node accent rail");
  }
  const bw = renderedBoxWidth(svg);
  if (bw != null && bw < 230) out.push(`rendered node box too narrow: ${bw.toFixed(1)}px`);
  const monoText = [...svg.matchAll(/<text\b[^>]*font-family="[^"]*mono[^"]*"/gi)].length;
  if (monoText > 0) out.push(`boxed diagram forces monospace text in ${monoText} label(s)`);
  return out;
}

function inFigureCaptionProblems(svg) {
  const out = [];
  const vb = svg.match(/viewBox="\s*([\d.-]+)\s+([\d.-]+)\s+([\d.]+)\s+([\d.]+)/);
  if (!vb) return out;
  const bottom = +vb[2] + +vb[4];
  for (const t of textBoxes(svg)) {
    if (t.y > bottom - 42 && /[.!?]$/.test(t.txt) && t.txt.length >= 58) {
      out.push(`in-figure caption text; move to page figcaption: "${t.txt.slice(0, 42)}"`);
    }
  }
  return out;
}

// ---- self-tests: each detector MUST fire on a known-bad input ----
const stOverlap = svgProblems('<svg viewBox="0 0 200 50"><text x="10" y="20" font-size="14" font-family="monospace">overlapping aaa</text><text x="40" y="22" font-size="14" font-family="monospace">overlapping bbb</text></svg>');
const CROSS_BOX_SVG = '<svg viewBox="0 0 520 180">' +
  '<g filter="url(#fig-shadow)"><rect x="24" y="44" width="120" height="80" rx="10"/></g>' +
  '<g filter="url(#fig-shadow)"><rect x="200" y="44" width="120" height="80" rx="10"/></g>' +
  '<g filter="url(#fig-shadow)"><rect x="376" y="44" width="120" height="80" rx="10"/></g>' +
  '<path d="M 144 84 C 210 84, 310 84, 376 84"/>' +
  '</svg>';
const stEdge = svgProblems(CROSS_BOX_SVG, { checkEdges: true });
const OLD_TRAJ = { kicker: "A GRANTED CAPABILITY BECOMES A BREACH ALONG A PATH", title: "Three action trajectories",
  nodes: [{ id: "a", label: "a", x: 0, y: 0 }, { id: "b", label: "b", x: 1, y: 0 }, { id: "c", label: "c", x: 2, y: 0 }], edges: [] };
const TINY_BOX = diagramSVG({ maxWidth: 560, boxW: 220, nodes: [0,1,2].map((i) => ({ id: "n"+i, label: "node"+i, x: i, y: 0 })), edges: [{ from: "n0", to: "n1" }, { from: "n1", to: "n2" }] });
const BAD_CAPTION = '<svg viewBox="0 0 500 200"><text x="250" y="176" text-anchor="middle" font-size="12">This explanatory sentence belongs in the page caption, not inside the figure.</text></svg>';
const BAD_GAP = '<svg viewBox="0 0 360 120"><g filter="url(#fig-shadow)"><rect x="20" y="20" width="150" height="80" rx="10"/></g><text x="95" y="50">label</text><text x="95" y="72">line</text><g filter="url(#fig-shadow)"><rect x="184" y="20" width="150" height="80" rx="10"/></g><text x="259" y="50">label</text><text x="259" y="72">line</text></svg>';
const BAD_SPARSE = '<svg viewBox="0 0 240 140"><g filter="url(#fig-shadow)"><rect x="20" y="20" width="200" height="100" rx="10"/></g><text x="120" y="52" text-anchor="middle" font-size="14">label only</text></svg>';
const BAD_STATIC_CARD = '<svg viewBox="0 0 360 160"><rect x="90" y="28" width="180" height="90" rx="10"/><text x="180" y="105" text-anchor="middle" font-size="14">nearly clipped</text></svg>';
const BAD_OFFCENTER = '<svg viewBox="0 0 260 140"><g filter="url(#fig-shadow)"><rect x="30" y="20" width="200" height="100" rx="10"/></g><text x="130" y="48" text-anchor="middle" font-size="14">too high</text></svg>';
const selftests = [
  ["text-overlap", stOverlap.some((p) => /text overlaps text/.test(p))],
  ["edge-cross-box", stEdge.some((p) => /crosses a box/.test(p))],
  ["useless-diagram", !!uselessSpec(OLD_TRAJ)],
  ["tiny-runtime-box", fidelityProblems(TINY_BOX).some((p) => /too narrow/.test(p))],
  ["in-figure-caption", inFigureCaptionProblems(BAD_CAPTION).some((p) => /in-figure caption/.test(p))],
  ["tight-box-gap", compositionProblems(BAD_GAP).some((p) => /gap too tight/.test(p))],
  ["sparse-box", compositionProblems(BAD_SPARSE).some((p) => /too sparse/.test(p))],
  ["static-card-bottom-padding", compositionProblems(BAD_STATIC_CARD, { includeStaticCards: true }).some((p) => /too close to border|imbalanced/.test(p))],
  ["off-center-card-text", compositionProblems(BAD_OFFCENTER, { checkCenter: true }).some((p) => /off-center/.test(p))],
];
const broken = selftests.filter(([, ok]) => !ok);
if (broken.length) { console.error("check_figures: SELF-TEST FAILED for " + broken.map((b) => b[0]).join(", ") + "; refusing to report clean."); process.exit(2); }

function extract(src) {
  const out = []; let i = 0;
  while ((i = src.indexOf("mountDiagram(", i)) >= 0) {
    let j = src.indexOf("{", i); if (j < 0) break; let d = 0, k = j, s = null;
    for (; k < src.length; k++) { const c = src[k];
      if (s) { if (c === "\\") { k++; continue; } if (c === s) s = null; continue; }
      if (c === '"' || c === "'" || c === "`") { s = c; continue; }
      if (c === "{") d++; else if (c === "}") { d--; if (d === 0) { k++; break; } } }
    const sel = (src.slice(i, j).match(/["'`](#[^"'`]+)/) || [])[1] || "?";
    try { out.push({ sel, spec: (0, eval)("(" + src.slice(j, k) + ")") }); }
    catch (e) { out.push({ sel, err: String(e.message || e).slice(0, 80) }); }
    i = k;
  }
  return out;
}

const findings = []; let checked = 0;
for (const f of fs.readdirSync(NEMO).filter((f) => /\.html$/.test(f)).sort()) {
  const pageSrc = fs.readFileSync(path.join(NEMO, f), "utf8");
  for (const { sel, spec, err } of extract(pageSrc)) {
    checked++; const page = "web/nemoclaw/" + f;
    if (err) { findings.push({ page, sel, detail: "spec did not parse: " + err }); continue; }
    // a mount whose target div is absent renders nothing -- a dead call, or a leftover after the figure was replaced (e.g. by a table).
    // Flag it and do not "validate" a phantom.
    if (sel.startsWith("#") && !pageSrc.includes(`id="${sel.slice(1)}"`)) {
      findings.push({ page, sel, detail: `mount target ${sel} has no element on the page; this figure never renders (dead mount or leftover after a replacement)` });
      continue;
    }
    if (spec.caption) findings.push({ page, sel, detail: "mountDiagram spec uses caption; move caption text to page prose or <figcaption>, never inside generated SVG" });
    const u = uselessSpec(spec); if (u) findings.push({ page, sel, detail: u });
    for (const p of flowOrderProblems(spec)) findings.push({ page, sel, detail: p });
    const svg = diagramSVG(spec);
    for (const p of svgProblems(svg, { checkEdges: true })) findings.push({ page, sel, detail: p });
    for (const p of compositionProblems(svg)) findings.push({ page, sel, detail: p });
    for (const p of fidelityProblems(svg)) findings.push({ page, sel, detail: p });
  }
}

for (const f of fs.readdirSync(path.join(NEMO, "assets", "figures")).filter((f) => /\.svg$/.test(f)).sort()) {
  checked++;
  const svg = fs.readFileSync(path.join(NEMO, "assets", "figures", f), "utf8");
  for (const p of inFigureCaptionProblems(svg)) findings.push({ page: "web/nemoclaw/assets/figures/" + f, sel: "svg", detail: p });
  for (const p of compositionProblems(svg, { includeStaticCards: true, checkInterBox: false, checkDensity: false, checkCenter: false })) findings.push({ page: "web/nemoclaw/assets/figures/" + f, sel: "svg", detail: p });
}

// mountPolicyMap is built from the DOM, so render it in the same host Chromium used by other checks.
const PM = { page: "web/nemoclaw/scripts/_shared.js", sel: "mountPolicyMap" };
try {
  const svg = await renderedPolicyMap();
  if (!svg) findings.push({ ...PM, detail: "produced no SVG" });
  else { checked++; for (const p of svgProblems(svg)) findings.push({ ...PM, detail: p }); }
} catch (e) { findings.push({ ...PM, detail: "render error: " + String(e.message || e).slice(0, 120) }); }

if (process.argv.includes("--json")) process.stdout.write(JSON.stringify({ checked, findings }) + "\n");
else { for (const x of findings) console.log(`  ${x.page} ${x.sel}: ${x.detail}`); console.log(`\ncheck_figures: ${checked} figure(s), ${findings.length} problem(s)`); }
process.exit(findings.length ? 1 : 0);
