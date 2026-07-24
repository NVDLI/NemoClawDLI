// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Canvas viz.* builders (makeViz).
import { diagramSVG, ganttBarsSVG } from "./_shared.js";

const DEFAULT_CHART_WIDTH = 560;

// makeViz binds the per-node `log` so runNode can wire output to a node.
// The helper menu instead reads names and source from a no-op-log instance.
export function makeViz(log) {
  return {
      // A node/edge diagram from a data spec, so a cell never hand-writes SVG.
      diagram(spec) {
        /* @doc <code>helpers.viz.diagram(spec)</code> :: Auto-themed node/edge figure from a data spec. <code>spec</code> is <code>{title?, caption?, nodes:[{id, label, kind, x, y, lines?}], edges:[{from, to, label?}]}</code>; <code>kind &isin; env|agent|tool|data|model|neutral</code>; <code>x</code>/<code>y</code> are grid columns/rows. */
        log.svg(diagramSVG(spec));
      },
      lineChart(values, opts = {}) {
        /* @doc <code>helpers.viz.lineChart(values, opts)</code> :: Static line chart for a numeric sequence. <code>opts</code> is <code>{title?, xLabel?, yLabel?, min?, max?, width?}</code>. The SVG includes point values in its accessible label; return the source array separately when learners need the exact data. */
        const series = Array.from(values || [], Number);
        if (!series.length || series.some(value => !Number.isFinite(value))) {
          throw new TypeError("helpers.viz.lineChart expects one or more finite numbers");
        }
        const esc = value => String(value == null ? "" : value).replace(/[<>&\"]/g, char => ({
          "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;",
        }[char]));
        const W = Math.max(420, Number(opts.width) || 640);
        const H = 270, PAD_L = 56, PAD_R = 24, PAD_T = 46, PAD_B = 54;
        const title = opts.title || "Values by step";
        const xLabel = opts.xLabel || "step";
        const yLabel = opts.yLabel || "value";
        let low = Number.isFinite(Number(opts.min)) ? Number(opts.min) : Math.min(...series);
        let high = Number.isFinite(Number(opts.max)) ? Number(opts.max) : Math.max(...series);
        if (high < low) [low, high] = [high, low];
        if (high === low) { low -= 1; high += 1; }
        const plotW = W - PAD_L - PAD_R, plotH = H - PAD_T - PAD_B;
        const x = index => PAD_L + (series.length === 1 ? plotW / 2 : index * plotW / (series.length - 1));
        const y = value => PAD_T + (high - value) * plotH / (high - low);
        const fmt = value => Number.isInteger(value) ? String(value) : value.toFixed(2);
        const ticks = Array.from({ length: 5 }, (_, index) => high - index * (high - low) / 4);
        const xTickIndexes = [...new Set([0, ...Array.from({ length: 3 }, (_, index) =>
          Math.round((index + 1) * (series.length - 1) / 4)), series.length - 1])];

        let body = "";
        for (const tick of ticks) {
          const py = y(tick);
          body += `<line x1="${PAD_L}" y1="${py}" x2="${W - PAD_R}" y2="${py}" stroke="var(--gfx-line,#3a3a3a)" stroke-width="1"/>`;
          body += `<text x="${PAD_L - 9}" y="${py + 4}" text-anchor="end" font-size="10" font-family="ui-monospace,monospace" fill="var(--gfx-sub,#a5a5a5)">${esc(fmt(tick))}</text>`;
        }
        for (const index of xTickIndexes) {
          body += `<text x="${x(index)}" y="${H - 30}" text-anchor="middle" font-size="10" font-family="ui-monospace,monospace" fill="var(--gfx-sub,#a5a5a5)">${index + 1}</text>`;
        }
        const points = series.map((value, index) => `${x(index)},${y(value)}`).join(" ");
        body += `<polyline points="${points}" fill="none" stroke="var(--gfx-green,#76b900)" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>`;
        series.forEach((value, index) => {
          body += `<circle cx="${x(index)}" cy="${y(value)}" r="3.5" fill="var(--gfx-bg,#0d0d0d)" stroke="var(--gfx-green,#aee23a)" stroke-width="2"><title>${esc(`${xLabel} ${index + 1}: ${fmt(value)}`)}</title></circle>`;
        });
        const description = `${title}. ${series.map((value, index) => `${xLabel} ${index + 1}: ${fmt(value)}`).join("; ")}.`;
        log.svg(`<svg class="gfx-dark" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="${esc(description)}" style="max-width:100%;background:var(--gfx-bg,#0d0d0d);border:1px solid var(--gfx-line,#2a2a2a);border-radius:6px">
          <text x="${W / 2}" y="25" text-anchor="middle" font-size="13" font-family="ui-monospace,monospace" fill="var(--gfx-green,#aee23a)" font-weight="700">${esc(title)}</text>
          ${body}
          <text x="${PAD_L + plotW / 2}" y="${H - 8}" text-anchor="middle" font-size="10" font-family="ui-monospace,monospace" fill="var(--gfx-sub,#a5a5a5)">${esc(xLabel)}</text>
          <text x="15" y="${PAD_T + plotH / 2}" text-anchor="middle" font-size="10" font-family="ui-monospace,monospace" fill="var(--gfx-sub,#a5a5a5)" transform="rotate(-90 15 ${PAD_T + plotH / 2})">${esc(yLabel)}</text>
        </svg>`);
      },
      scoreBarChart(scored, opts = {}) {
        /* @doc <code>helpers.viz.scoreBarChart(scored, opts)</code> :: 1-to-5 score bar chart with threshold and mean overlay. <code>scored</code> is an array of <code>{score, label?}</code>; <code>opts</code> is <code>{threshold, title, width}</code>. */
        const { threshold = 3, title = "Score comparison", width = DEFAULT_CHART_WIDTH } = opts;
        const BAR_H = 28, GAP = 8, PAD_L = 130, PAD_T = 48, PAD_B = 40, PAD_R = 80;
        const maxBarW = width - PAD_L - PAD_R;
        const H = PAD_T + scored.length * (BAR_H + GAP) + PAD_B;
        const mean = scored.reduce((s, x) => s + (x.score || 0), 0) / (scored.length || 1);
        const colorFor = s => s >= threshold ? "#76b900" : s === 3 ? "#d49c2c" : "#d74e4e";
        const textFor  = s => s >= threshold ? "#aee23a" : s === 3 ? "#e8c87a" : "#ff9a9a";
        const esc = t => String(t || "").replace(/[<>&]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));

        let rows = "";
        scored.forEach((item, i) => {
          const y = PAD_T + i * (BAR_H + GAP);
          const sc = item.score || 0;
          const bw = Math.round((sc / 5) * maxBarW);
          const col = colorFor(sc);
          const tc  = textFor(sc);
          rows += `<text x="${PAD_L - 8}" y="${y + BAR_H / 2 + 4}" text-anchor="end" font-size="11" font-family="ui-monospace,monospace" fill="#b0b0b0">${esc(item.label || `item ${i + 1}`)}</text>`;
          rows += `<rect x="${PAD_L}" y="${y}" width="${maxBarW}" height="${BAR_H}" rx="3" fill="#161616"/>`;
          rows += `<rect x="${PAD_L}" y="${y}" width="${bw}" height="${BAR_H}" rx="3" fill="${col}" opacity="0.85"/>`;
          rows += `<text x="${PAD_L + bw + 6}" y="${y + BAR_H / 2 + 4}" font-size="12" font-family="ui-monospace,monospace" font-weight="700" fill="${tc}">${sc}/5</text>`;
          if (item.note) rows += `<text x="${PAD_L}" y="${y + BAR_H + 6}" font-size="9" font-family="ui-monospace,monospace" fill="#6a6a6a">${esc(item.note.slice(0, 70))}</text>`;
        });

        const thX = PAD_L + Math.round((threshold / 5) * maxBarW);
        rows += `<line x1="${thX}" y1="${PAD_T - 8}" x2="${thX}" y2="${PAD_T + scored.length * (BAR_H + GAP) - GAP + 4}" stroke="#d49c2c" stroke-width="1.5" stroke-dasharray="4 3"/>`;
        rows += `<text x="${thX + 3}" y="${PAD_T - 10}" font-size="9" font-family="ui-monospace,monospace" fill="#d49c2c">threshold ${threshold}</text>`;
        const meanX = PAD_L + Math.round((mean / 5) * maxBarW);
        rows += `<line x1="${meanX}" y1="${PAD_T - 8}" x2="${meanX}" y2="${PAD_T + scored.length * (BAR_H + GAP) - GAP + 4}" stroke="#76b900" stroke-width="1" stroke-dasharray="3 3" opacity="0.6"/>`;
        rows += `<text x="${meanX + 3}" y="${H - PAD_B / 2 + 4}" font-size="9" font-family="ui-monospace,monospace" fill="var(--gfx-nvgreen,#76b900)">mean ${mean.toFixed(2)}</text>`;
        log.svg(`<svg viewBox="0 0 ${width} ${H}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;background:#0d0d0d;border:1px solid #2a2a2a;border-radius:6px">
          <text x="${width / 2}" y="22" text-anchor="middle" font-size="12" font-family="ui-monospace,monospace" fill="#aee23a" font-weight="700">${esc(title)}</text>
          ${rows}</svg>`);
      },

      messageList(messages, title = "Message sequence") {
        /* @doc <code>helpers.viz.messageList(messages, title)</code> :: Color-coded message sequence (USER=blue, ASSISTANT=green, TOOL=amber). Takes an OpenAI <code>messages</code> array as-is. */
        const W = DEFAULT_CHART_WIDTH, ROW_H = 58, PAD_T = 36, PAD_L = 20;
        const H = PAD_T + messages.length * ROW_H + 28;
        const esc = t => String(t || "").replace(/[<>&]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
        const colorFor = role => {
          if (role === "user")      return { bg: "#1e1e3a", border: "#3b82f6", text: "#7eb8ff" };
          if (role === "tool")      return { bg: "#3a2e1e", border: "#d49c2c", text: "#e8c87a" };
          if (role === "assistant") return { bg: "#1e3a1e", border: "#76b900", text: "#aee23a" };
          if (role === "system")    return { bg: "#2a1e3a", border: "#a78bfa", text: "#c4b5fd" };
          return { bg: "#1e1e1e", border: "#a5a5a5", text: "#a5a5a5" };
        };

        let body = "";
        messages.forEach((m, i) => {
          const y = PAD_T + i * ROW_H;
          const c = colorFor(m.role);
          let preview = "";
          let tag = m.role.toUpperCase();
          if (m.tool_calls && m.tool_calls.length) {
            tag = "ASSISTANT · tool_calls";
            const tc = m.tool_calls[0];
            preview = "calls " + (tc.function?.name || "?") + "(" + (tc.function?.arguments || "").slice(0, 55) + ")";
          } else if (m.content) {
            preview = String(m.content).slice(0, 90).replace(/\s+/g, " ");
          }
          body += `<circle cx="${PAD_L + 16}" cy="${y + 26}" r="14" fill="${c.bg}" stroke="${c.border}" stroke-width="2"/>`;
          body += `<text x="${PAD_L + 16}" y="${y + 31}" text-anchor="middle" font-size="11" font-family="ui-monospace,monospace" fill="${c.text}" font-weight="700">${i + 1}</text>`;
          if (i > 0) body += `<line x1="${PAD_L + 16}" y1="${y - 4}" x2="${PAD_L + 16}" y2="${y + 8}" stroke="#3a3a3a" stroke-width="1.2"/>`;
          body += `<rect x="${PAD_L + 38}" y="${y + 6}" width="${W - PAD_L - 48}" height="${ROW_H - 16}" rx="5" fill="${c.bg}" stroke="${c.border}"/>`;
          body += `<text x="${PAD_L + 48}" y="${y + 21}" font-size="10" font-family="ui-monospace,monospace" fill="${c.text}" font-weight="700">${esc(tag)}</text>`;
          body += `<text x="${PAD_L + 48}" y="${y + 37}" font-size="10" font-family="ui-monospace,monospace" fill="#e8e8e8">${esc(preview)}${preview.length > 80 ? "…" : ""}</text>`;
        });
        log.svg(`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;background:#0d0d0d;border:1px solid #2a2a2a;border-radius:6px">
          <text x="${W / 2}" y="22" text-anchor="middle" font-size="11" font-family="ui-monospace,monospace" fill="#aee23a" font-weight="700">${esc(title)}</text>
          ${body}
          <text x="${W - 10}" y="${H - 8}" text-anchor="end" font-size="9" font-family="ui-monospace,monospace" fill="#6f6f6f">USER=blue · ASSISTANT=green · TOOL=amber · SYSTEM=purple</text></svg>`);
      },

      ganttBars(workers, wallSeconds, title = "Concurrency vs serial time") {
        /* @doc <code>helpers.viz.ganttBars(workers, wallSeconds, title)</code> :: Gantt-style bar chart comparing per-worker duration against total wall time. */
        log.svg(ganttBarsSVG(workers, wallSeconds, title));
      },

      retrievalBars(scored, topK = 3, title = "Retrieval scores") {
        /* @doc <code>helpers.viz.retrievalBars(scored, topK, title)</code> :: Horizontal score bars for retrieval results, with the top-k entries highlighted green and the rest dimmed. */
        const W = DEFAULT_CHART_WIDTH, BAR_H = 26, GAP = 8, PAD_L = 20, PAD_T = 48, PAD_B = 24, PAD_R = 70;
        const maxBarW = W - PAD_L - PAD_R;
        const maxScore = Math.max(...scored.map(x => x.score || 0), 1);
        const H = PAD_T + scored.length * (BAR_H + GAP) + PAD_B;
        const esc = t => String(t || "").replace(/[<>&]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
        let body = "";
        scored.forEach((item, i) => {
          const y = PAD_T + i * (BAR_H + GAP);
          const bw = Math.round((item.score / maxScore) * maxBarW);
          const isTop = i < topK;
          const col  = isTop ? "#76b900" : "#2a2a2a";
          const tCol = isTop ? "#aee23a" : "#6a6a6a";
          const preview = String(item.text || "").slice(0, 58).replace(/\s+/g, " ");
          body += `<rect x="${PAD_L}" y="${y}" width="${maxBarW}" height="${BAR_H}" rx="3" fill="#161616"/>`;
          body += `<rect x="${PAD_L}" y="${y}" width="${bw}" height="${BAR_H}" rx="3" fill="${col}" opacity="${isTop ? 0.8 : 0.4}"/>`;
          body += `<text x="${PAD_L + 6}" y="${y + BAR_H / 2 + 4}" font-size="10" font-family="ui-monospace,monospace" fill="${tCol}">${isTop ? "★ " : ""}${esc(preview)}</text>`;
          body += `<text x="${PAD_L + maxBarW + 5}" y="${y + BAR_H / 2 + 4}" font-size="11" font-family="ui-monospace,monospace" fill="${tCol}" font-weight="700">${(item.score || 0).toFixed(3)}</text>`;
        });
        log.svg(`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;background:#0d0d0d;border:1px solid #2a2a2a;border-radius:6px">
          <text x="${W / 2}" y="22" text-anchor="middle" font-size="12" font-family="ui-monospace,monospace" fill="#aee23a" font-weight="700">${esc(title)}</text>
          <text x="${PAD_L}" y="38" font-size="9" font-family="ui-monospace,monospace" fill="#6a6a6a">top-${topK} highlighted · score normalized to max=${maxScore.toFixed(3)}</text>
          ${body}</svg>`);
      },

      // helpers.viz.diffTable({ left, right, rows, notes?, verdict? }, opts?).
      // "check" rows render ✓/✗ per side; "num" rows colour the delta by betterWhen and an optional fmt.
      // opts: { title?, width? }, where width defaults to 760. See the @doc below for full row shapes.
      diffTable(spec = {}, opts = {}) {
        /* @doc <code>helpers.viz.diffTable(spec, opts)</code> :: Before/after comparison table with colour-coded deltas, check marks, footer notes, and an optional <code>verdict({rows})</code> returning <code>{ok, text}</code>. <code>spec.rows</code> entries are <code>{kind:"check", label, left, right}</code> or <code>{kind:"num", label, left, right, betterWhen:"up"|"down", fmt?}</code>. */
        const rows  = Array.isArray(spec.rows) ? spec.rows : [];
        const notes = Array.isArray(spec.notes) ? spec.notes : [];
        const verdict = typeof spec.verdict === "function" ? spec.verdict : null;
        const left   = spec.left  || "before";
        const right  = spec.right || "after";
        const title  = opts.title || "Before / after";
        const W      = opts.width || 760;
        const ROW_H  = 24;
        const PAD_T  = 60;
        const COL1   = 40, COL2 = 290, COL3 = 510, COL4 = 640;
        const escTxt = t => String(t == null ? "" : t).replace(/[<>&]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
        const fmtNum = (v, fmt) => fmt ? fmt(v) : (typeof v === "number" ? (Number.isInteger(v) ? String(v) : v.toFixed(2)) : String(v));

        // Pre-compute deltas + good/bad colour per row
        const rendered = rows.map(r => {
          const o = { ...r };
          if (r.kind === "num" && typeof r.left === "number" && typeof r.right === "number") {
            o.delta = r.right - r.left;
            const fmt = r.fmt || (v => fmtNum(v, null));
            o.deltaStr = (o.delta > 0 ? "+" : "") + fmt(o.delta);
            o.deltaCol = "#6f6f6f";
            if (r.betterWhen === "up")   o.deltaCol = o.delta >= 0 ? "#aee23a" : "#d74e4e";
            if (r.betterWhen === "down") o.deltaCol = o.delta <= 0 ? "#aee23a" : "#d74e4e";
          }
          return o;
        });

        const checksH = ROW_H * rendered.filter(r => r.kind === "check").length;
        const numsH   = ROW_H * rendered.filter(r => r.kind === "num").length;
        const notesH  = (notes.length + (verdict ? 1 : 0)) * 18 + 12;
        const H       = PAD_T + checksH + (checksH && numsH ? 12 : 0) + numsH + (notesH ? notesH + 8 : 0) + 18;

        let body = "";
        body += `<text x="20" y="22" font-size="11" font-family="ui-monospace,monospace" fill="#6f6f6f" font-weight="700">${escTxt(title)}</text>`;
        body += `<text x="${COL2}" y="48" text-anchor="middle" font-size="11" font-family="ui-monospace,monospace" fill="#a5a5a5" font-weight="700">${escTxt(left)}</text>`;
        body += `<text x="${COL3}" y="48" text-anchor="middle" font-size="11" font-family="ui-monospace,monospace" fill="#aee23a" font-weight="700">${escTxt(right)}</text>`;
        body += `<line x1="20" y1="58" x2="${W - 20}" y2="58" stroke="#2a2a2a"/>`;

        let y = PAD_T + 12;
        const checks = rendered.filter(r => r.kind === "check");
        checks.forEach(r => {
          body += `<text x="${COL1}" y="${y}" font-size="10" font-family="ui-monospace,monospace" fill="#a5a5a5">${escTxt(r.label)}</text>`;
          body += `<text x="${COL2}" y="${y}" text-anchor="middle" font-size="11" font-family="ui-monospace,monospace" fill="${r.left ? "#aee23a" : "#d74e4e"}" font-weight="700">${r.left ? "✓" : "✗"}</text>`;
          body += `<text x="${COL3}" y="${y}" text-anchor="middle" font-size="11" font-family="ui-monospace,monospace" fill="${r.right ? "#aee23a" : "#d74e4e"}" font-weight="700">${r.right ? "✓" : "✗"}</text>`;
          y += ROW_H;
        });
        if (checks.length && rendered.some(r => r.kind === "num")) {
          body += `<line x1="20" y1="${y - 8}" x2="${W - 20}" y2="${y - 8}" stroke="#2a2a2a"/>`;
          y += 4;
        }
        rendered.filter(r => r.kind === "num").forEach(r => {
          body += `<text x="${COL1}" y="${y}" font-size="10" font-family="ui-monospace,monospace" fill="#a5a5a5">${escTxt(r.label)}</text>`;
          body += `<text x="${COL2}" y="${y}" text-anchor="middle" font-size="12" font-family="ui-monospace,monospace" fill="#7eb8ff">${escTxt(fmtNum(r.left, r.fmt))}</text>`;
          body += `<text x="${COL3}" y="${y}" text-anchor="middle" font-size="12" font-family="ui-monospace,monospace" fill="#aee23a">${escTxt(fmtNum(r.right, r.fmt))}</text>`;
          if (r.deltaStr) body += `<text x="${COL4}" y="${y}" font-size="11" font-family="ui-monospace,monospace" fill="${r.deltaCol}">${escTxt(r.deltaStr)}</text>`;
          y += ROW_H;
        });

        y += 8;
        notes.forEach(n => {
          body += `<text x="20" y="${y}" font-size="10" font-family="ui-monospace,monospace" fill="#6f6f6f">${escTxt(n)}</text>`;
          y += 18;
        });
        if (verdict) {
          const v = verdict({ rows: rendered });
          const ok = v && v.ok !== false;
          const txt = (v && v.text) || (typeof v === "string" ? v : "");
          body += `<text x="20" y="${y}" font-size="10" font-family="ui-monospace,monospace" fill="${ok ? "#aee23a" : "#e8c87a"}" font-weight="700">verdict: ${escTxt(txt)}</text>`;
        }

        log.draw(W, H, body, { title: null });
      },

      // chat(turns, opts?) renders a flat chat transcript.
      // turns: array of [role, content] pairs, role ∈ {user|assistant|ai|system|tool}.
      // opts: { title?, maxChars = 240 per turn, width = 720 }.
      chat(turns = [], opts = {}) {
        /* @doc <code>helpers.viz.chat(turns, opts?)</code> :: Chat transcript as colour-coded bubbles. <code>turns</code> is an array of <code>[role, content]</code> pairs; <code>role &isin; {user, assistant|ai, system, tool}</code>. <code>opts.maxChars</code> truncates per turn. */
        const W = opts.width || 720;
        const PAD_T = 40, PAD = 18, GAP = 8;
        const maxChars = opts.maxChars || 240;
        const escTxt = t => String(t == null ? "" : t).replace(/[<>&]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
        const palette = {
          user:      { bg: "#1e1e3a", border: "#3b82f6", lbl: "#7eb8ff", txt: "#e8e8e8", tag: "USER" },
          system:    { bg: "#2a1e3a", border: "#a78bfa", lbl: "#c4b5fd", txt: "#e8e8e8", tag: "SYSTEM" },
          tool:      { bg: "#3a2e1e", border: "#d49c2c", lbl: "#e8c87a", txt: "#e8e8e8", tag: "TOOL" },
          ai:        { bg: "#1e3a1e", border: "#76b900", lbl: "#aee23a", txt: "#e8e8e8", tag: "ASSISTANT" },
          assistant: { bg: "#1e3a1e", border: "#76b900", lbl: "#aee23a", txt: "#e8e8e8", tag: "ASSISTANT" },
        };
        const linesOf = (s, perLine = 70) => {
          const t = String(s || "").replace(/\s+/g, " ").slice(0, maxChars);
          const lines = [];
          for (let i = 0; i < t.length; i += perLine) lines.push(t.slice(i, i + perLine));
          if (String(s || "").length > maxChars) lines[lines.length - 1] = (lines[lines.length - 1] || "") + "…";
          return lines.length ? lines : ["(empty)"];
        };

        let y = PAD_T;
        let body = "";
        for (const [rawRole, content] of turns) {
          const p = palette[String(rawRole || "").toLowerCase()] || palette.user;
          const lines = linesOf(content);
          const bubbleH = 22 + lines.length * 14 + 6;
          body += `<rect x="${PAD}" y="${y}" width="${W - 2 * PAD}" height="${bubbleH}" rx="6" fill="${p.bg}" stroke="${p.border}"/>`;
          body += `<text x="${PAD + 10}" y="${y + 16}" font-size="10" font-family="ui-monospace,monospace" fill="${p.lbl}" font-weight="700" letter-spacing="0.08em">${p.tag}</text>`;
          lines.forEach((l, i) => {
            body += `<text x="${PAD + 10}" y="${y + 32 + i * 14}" font-size="11" font-family="ui-monospace,monospace" fill="${p.txt}">${escTxt(l)}</text>`;
          });
          y += bubbleH + GAP;
        }
        log.draw(W, y + PAD, body, { title: opts.title || null });
      },

      // sideBySide(leftLines, rightLines, opts?) renders two columns of text.
      // opts: { leftTitle, rightTitle, footer }.
      sideBySide(leftLines = [], rightLines = [], opts = {}) {
        /* @doc <code>helpers.viz.sideBySide(leftLines, rightLines, opts?)</code> :: Two text columns. <code>opts</code> is <code>{leftTitle, rightTitle, footer}</code>. */
        const W = 760, COL_GAP = 18, colW = (W - 24 - COL_GAP) / 2;
        const esc = t => String(t == null ? "" : t).replace(/[<>&]/g, c => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]));
        const rows = Math.max(leftLines.length, rightLines.length, 1);
        const bodyH = 60 + rows * 16;
        const H = bodyH + (opts.footer ? 24 : 0) + 12;
        const col = (x, title, lines) => {
          let out = `<text x="${x + 10}" y="32" font-size="11" font-family="ui-monospace,monospace" fill="#7eb8ff" font-weight="700">${esc(title || "")}</text>`;
          out += `<rect x="${x}" y="42" width="${colW}" height="${bodyH - 42}" rx="6" fill="#0d0d0d" stroke="#3a3a3a"/>`;
          (lines || []).forEach((line, i) => {
            out += `<text x="${x + 10}" y="${62 + i * 16}" font-size="10" font-family="ui-monospace,monospace" fill="#a5a5a5">${esc(line)}</text>`;
          });
          return out;
        };
        let body = col(12, opts.leftTitle,  leftLines)
                 + col(12 + colW + COL_GAP, opts.rightTitle, rightLines);
        if (opts.footer) {
          body += `<text x="${W / 2}" y="${H - 12}" text-anchor="middle" font-size="10" font-family="ui-monospace,monospace" fill="#a5a5a5">${esc(opts.footer)}</text>`;
        }
        log.draw(W, H, body, { title: opts.title || null });
      },
  };
}
