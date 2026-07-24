#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Browser-check the shared runnable-cell UI contract.

This is intentionally stricter than a page render smoke. It verifies the
consolidated CanvasFlow/RunCell abstraction across source or built pages,
multiple viewport/theme configurations, CodeMirror highlighting, hidden-code
heuristics, paired initial/expanded screenshots, unified controls, live-artifact
cues, and actual run output on the helper notebook.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
sys.path.insert(0, str(ROOT))
from scripts.runtime.host_browser import BrowserRuntimeError, environment, run_node
DEFAULT_EXTRA_PAGES = ("scripts/SKILL.html",)
INTERACTIVE_MARKERS = ("mountCanvasFlow(", "mountRunCell(", "mountDiagram(")

RUNTIME_JS = r"""
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const root = process.env.SITE_ROOT || '/site';
const pages = JSON.parse(process.env.CELL_UI_PAGES || '[]');
const screenshots = process.env.SCREENSHOT_DIR || '';
const port = Number(process.env.SITE_PORT || 4196);
const timeoutMs = Number(process.env.AUDIT_TIMEOUT_MS || 120000);
const mime = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.json':'application/json; charset=utf-8', '.svg':'image/svg+xml', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.woff2':'font/woff2' };
const viewports = [
  { name: 'desktop', width: 1440, height: 1000 },
  { name: 'narrow', width: 390, height: 900 },
];
const themes = ['dark', 'light'];

function safeJoin(base, urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]).replace(/^\/+/, '');
  const out = path.resolve(base, clean);
  if (!out.startsWith(path.resolve(base))) throw new Error('path escape');
  return out;
}
const server = http.createServer((req, res) => {
  let file;
  try { file = safeJoin(root, req.url || '/'); } catch (e) { res.writeHead(403); res.end('forbidden'); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found'); return; }
    res.writeHead(200, { 'content-type': mime[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
});
function listen() { return new Promise(resolve => server.listen(port, '127.0.0.1', resolve)); }
function wait(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function inspectPage(page, pagePath, vp, theme) {
  const url = `http://127.0.0.1:${port}${pagePath}`;
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', err => pageErrors.push(err.message || String(err)));
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
  await page.setViewportSize({ width: vp.width, height: vp.height });
  await page.addInitScript((themeName) => {
    try { document.documentElement.setAttribute('data-theme', themeName); } catch (_) {}
  }, theme);
  await page.goto(url, { waitUntil: 'networkidle', timeout: timeoutMs });
  await page.evaluate((themeName) => document.documentElement.setAttribute('data-theme', themeName), theme);
  await wait(600);
  // Shared chrome may restore its saved theme after page scripts finish mounting.
  // Disable visual transitions during measurement, then re-assert the requested state so
  // the matrix checks final colors instead of sampling a reset button mid-fade.
  await page.addStyleTag({ content: '*,*::before,*::after{transition:none!important;animation:none!important}' });
  await page.evaluate((themeName) => document.documentElement.setAttribute('data-theme', themeName), theme);
  await wait(50);

  const visibility = await page.evaluate(() => ({
    canvasLongOpen: Array.from(document.querySelectorAll('.cf-panel-code-det[open] .cf-panel-code')).filter(ta => (ta.value || '').split('\n').length >= 40).length,
    runCellOpenDefault: document.querySelectorAll('.rc-code-det[open]').length,
  }));
  const initial = await page.evaluate((visibility) => {
    const wrongToneSurfaces = () => Array.from(document.querySelectorAll(
      '.cell-btn-reset,.cf-btn-reset,.cf-panel-reset,.cf-wrap,.cf-stage,.cf-node,.cf-panel,.cf-panel-det,.rc-code-det,.CodeMirror,.CodeMirror-gutters,.cell-code-body,.rc-code-body,.cf-panel-code-body,.cell-output-panel,.rc-out,.cf-panel-stream,.cf-panel-log,.cf-panel-output-pre,svg.dg-svg,svg.dg-svg rect,svg.gfx-dark,svg.gfx-dark rect,svg.gfx-dark circle,svg.gfx-dark ellipse,svg.gfx-dark polygon,svg.os-architecture,svg.os-architecture rect,svg.os-architecture .os-panel'
    )).filter(el => {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return false;
      const cs = getComputedStyle(el);
      let color = cs.backgroundColor;
      if (el instanceof SVGElement) {
        const tag = el.tagName.toLowerCase();
        if (tag !== 'svg') {
          if (r.width * r.height < 900) return false;
          if (tag === 'path' && !String(el.getAttribute('class') || '').includes('os-panel')) return false;
          color = cs.fill;
          if (!color || color === 'none') return false;
        }
      }
      const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?/);
      if (!m) return false;
      if (m[4] != null && Number(m[4]) === 0) return false;
      const rgb = m.slice(1, 4).map(Number);
      if (el instanceof SVGElement && el.tagName.toLowerCase() !== 'svg') {
        if (Math.max(...rgb) - Math.min(...rgb) >= 45) return false;
      }
      const [rr, gg, bb] = rgb.map(v => v / 255);
      const lin = [rr, gg, bb].map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
      const lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
      const lightTheme = document.documentElement.getAttribute('data-theme') === 'light';
      return lightTheme ? lum < 0.45 : lum > 0.82;
    }).slice(0, 12).map(el => ({ tag: el.tagName, cls: String(el.className || '').slice(0, 80), bg: getComputedStyle(el).backgroundColor, fill: getComputedStyle(el).fill }));
    const codeDetails = Array.from(document.querySelectorAll('.cf-panel-code-det,.rc-code-det'));
    const codeSummaries = codeDetails.map(det => (det.querySelector('summary')?.textContent || '').trim());
    const canvasLongOpen = Array.from(document.querySelectorAll('.cf-panel-code-det[open] .cf-panel-code')).filter(ta => (ta.value || '').split('\n').length >= 40).length;
    const runCellOpenDefault = document.querySelectorAll('.rc-code-det[open]').length;
    const cms = Array.from(document.querySelectorAll('.CodeMirror'));
    const artifacts = Array.from(document.querySelectorAll('[id$="-artifact"]')).map(el => {
      const surface = el.querySelector('.chatui-log,.da-out');
      const surfaceStyle = surface ? getComputedStyle(surface) : null;
      return {
        id: el.id,
        marked: el.classList.contains('course-artifact'),
        label: el.dataset.artifactLabel || '',
        cue: getComputedStyle(el, '::before').content,
        rail: getComputedStyle(el).borderLeftColor,
        railWidth: parseFloat(getComputedStyle(el).borderLeftWidth) || 0,
        surface: !!surface,
        maxHeight: surfaceStyle?.maxHeight || '',
        overflowY: surfaceStyle?.overflowY || '',
      };
    });
    const output = {
      title: document.title,
      main: !!document.querySelector('main'),
      flows: document.querySelectorAll('.cf-btn-run').length,
      panels: document.querySelectorAll('.cf-panel').length,
      runCells: document.querySelectorAll('.rc-card').length,
      unifiedButtons: document.querySelectorAll('.cell-btn').length,
      unifiedLangChips: document.querySelectorAll('.cell-lang-chip').length,
      uglyCellButtons: document.querySelectorAll('.rc-run:not(.cell-btn),.rc-reset:not(.cell-btn),.cf-panel-runone:not(.cell-btn),.cf-panel-reset:not(.cell-btn)').length,
      plainCodeLabels: codeSummaries.filter(t => /^code\b/i.test(t)).length,
      canvasLongOpen: visibility.canvasLongOpen,
      runCellOpenDefault: visibility.runCellOpenDefault,
      codeMirrorCount: cms.length,
      cmTokenCount: document.querySelectorAll('.CodeMirror .cm-keyword,.CodeMirror .cm-string,.CodeMirror .cm-property,.CodeMirror .cm-def').length,
      pageOverflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      badOverflow: Array.from(document.querySelectorAll('body *')).filter(el => {
        const r = el.getBoundingClientRect();
        if (el instanceof SVGElement || el.closest('svg')) return false;
        if (r.right <= document.documentElement.clientWidth + 2) return false;
        if (el.tagName === 'CODE') return false;
        if (el.closest('.topbar nav,.cf-stage,.CodeMirror,.CodeMirror-scroll,.cf-helpers-scroll,.cell-log-json,.cf-panel-log-json,.cf-log-json,.cell-code-body,.rc-code-body,.cf-panel-code-body,pre')) return false;
        // Wide tables and similar content are valid when a parent deliberately owns horizontal
        // scrolling. Judge page overflow, not the width of descendants inside a contained scroller.
        for (let parent = el.parentElement; parent && parent !== document.body; parent = parent.parentElement) {
          if (/auto|scroll/.test(getComputedStyle(parent).overflowX)) return false;
        }
        return true;
      }).slice(0, 8).map(el => ({ tag: el.tagName, cls: String(el.className || '').slice(0, 80), text: (el.textContent || '').trim().slice(0, 80) })),
      themeMismatchSurfaces: wrongToneSurfaces(),
      minCellButton: Math.min(...Array.from(document.querySelectorAll('.cell-btn')).map(b => Math.min(b.getBoundingClientRect().width, b.getBoundingClientRect().height)).filter(Number.isFinite), 999),
      cellActionLayout: Array.from(document.querySelectorAll('.cell-actions')).map(group => {
        const buttons = Array.from(group.querySelectorAll('.cell-btn'));
        const buttonRows = new Set(buttons.map(button => Math.round(button.getBoundingClientRect().top)));
        const wrappedLabels = buttons.filter(button => {
          const range = document.createRange();
          range.selectNodeContents(button);
          const lines = new Set(Array.from(range.getClientRects()).map(rect => Math.round(rect.top)));
          return getComputedStyle(button).whiteSpace !== 'nowrap' || lines.size > 1;
        });
        return {
          buttons: buttons.length,
          rows: buttonRows.size,
          wrappedLabels: wrappedLabels.map(button => button.textContent.trim()),
        };
      }),
      artifacts,
    };
    return output;
  }, visibility);

  const runSelectors = await page.evaluate(() => {
    if (!document.querySelector('.helper-notebook')) return [];
    return ['#helper-map-cell .cf-btn-run', '#helper-retrieval-cell .cf-btn-run', '#helper-live-cell .cf-btn-run', '#helper-ui-cell .rc-run'];
  });
  if (runSelectors.length) {
    await page.evaluate(() => document.querySelectorAll('.cf-panel-code-det,.rc-code-det').forEach(det => { det.open = false; }));
    await wait(150);
  }
  const runResults = [];
  for (const sel of runSelectors) {
    const loc = page.locator(sel).first();
    if (!await loc.count()) throw new Error(`missing helper run selector ${sel}`);
    await loc.click();
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const txt = await loc.innerText().catch(() => '');
      if (!/stop|running|⏹/i.test(txt)) break;
      await wait(250);
    }
    const rootSel = sel.replace(/ .*/, '');
    const text = await page.locator(rootSel).innerText().catch(() => '');
    runResults.push({ sel, hasOutput: /(returned value|wrote into state|helper|mounted|liveSkipped|labSkipped|traceEvents)/i.test(text), badText: /TypeError|ReferenceError|helpers\.log\.[a-z]+ is not a function|✗ stopped:/i.test(text) });
  }
  if (screenshots) {
    fs.mkdirSync(screenshots, { recursive: true });
    const safe = pagePath.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').slice(0, 80);
    await page.screenshot({ path: path.join(screenshots, `${safe}_${vp.name}_${theme}_initial.png`), fullPage: true });
  }
  await page.evaluate(() => document.querySelectorAll('.cf-panel-code-det,.rc-code-det').forEach(det => { det.open = true; }));
  await wait(250);
  if (screenshots) {
    fs.mkdirSync(screenshots, { recursive: true });
    const safe = pagePath.replace(/[^a-z0-9]+/gi, '_').replace(/^_+|_+$/g, '').slice(0, 80);
    await page.screenshot({ path: path.join(screenshots, `${safe}_${vp.name}_${theme}_expanded.png`), fullPage: true });
  }
  const finalInfo = await page.evaluate(() => ({
    codeMirrorCount: document.querySelectorAll('.CodeMirror').length,
    cmTokenCount: document.querySelectorAll('.CodeMirror .cm-keyword,.CodeMirror .cm-string,.CodeMirror .cm-property,.CodeMirror .cm-def').length,
    outputs: document.querySelectorAll('.cf-panel-output:not(:empty),.rc-out:not(:empty)').length,
    logHeadings: document.querySelectorAll('.cell-log-heading').length,
    jsonBlocks: document.querySelectorAll('.cell-log-json,.cf-panel-output-pre code.language-json').length,
    detailsBlocks: document.querySelectorAll('.cell-log-details, .cf-panel-log-details').length,
    htmlBlocks: document.querySelectorAll('.cell-log-html,.cf-panel-log-html').length,
    themeMismatchSurfaces: Array.from(document.querySelectorAll(
      '.cell-btn-reset,.cf-btn-reset,.cf-panel-reset,.cf-wrap,.cf-stage,.cf-node,.cf-panel,.cf-panel-det,.rc-code-det,.CodeMirror,.CodeMirror-gutters,.cell-code-body,.rc-code-body,.cf-panel-code-body,.cell-output-panel,.rc-out,.cf-panel-stream,.cf-panel-log,.cf-panel-output-pre,svg.dg-svg,svg.dg-svg rect,svg.gfx-dark,svg.gfx-dark rect,svg.gfx-dark circle,svg.gfx-dark ellipse,svg.gfx-dark polygon,svg.os-architecture,svg.os-architecture rect,svg.os-architecture .os-panel'
    )).filter(el => {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return false;
      const cs = getComputedStyle(el);
      let color = cs.backgroundColor;
      if (el instanceof SVGElement) {
        const tag = el.tagName.toLowerCase();
        if (tag !== 'svg') {
          if (r.width * r.height < 900) return false;
          if (tag === 'path' && !String(el.getAttribute('class') || '').includes('os-panel')) return false;
          color = cs.fill;
          if (!color || color === 'none') return false;
        }
      }
      const m = color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?/);
      if (!m) return false;
      if (m[4] != null && Number(m[4]) === 0) return false;
      const rgb = m.slice(1, 4).map(Number);
      if (el instanceof SVGElement && el.tagName.toLowerCase() !== 'svg') {
        if (Math.max(...rgb) - Math.min(...rgb) >= 45) return false;
      }
      const [rr, gg, bb] = rgb.map(v => v / 255);
      const lin = [rr, gg, bb].map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4));
      const lum = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
      const lightTheme = document.documentElement.getAttribute('data-theme') === 'light';
      return lightTheme ? lum < 0.45 : lum > 0.82;
    }).slice(0, 12).map(el => ({ tag: el.tagName, cls: String(el.className || '').slice(0, 80), bg: getComputedStyle(el).backgroundColor, fill: getComputedStyle(el).fill })),
  }));

  let figureZoom = null;
  // Learner-depth settings can intentionally hide an early reference figure. Exercise the first
  // rendered figure rather than timing out on a valid hidden disclosure.
  const firstFigure = page.locator('.fig-embed:visible').first();
  if (await firstFigure.count()) {
    await firstFigure.scrollIntoViewIfNeeded();
    const badge = await firstFigure.evaluate(el => ({
      content: getComputedStyle(el, '::after').content,
      opacity: Number(getComputedStyle(el, '::after').opacity),
    }));
    await firstFigure.click();
    await page.locator('.fig-lightbox:not([hidden])').waitFor({ state: 'visible', timeout: timeoutMs });
    figureZoom = await page.evaluate((badgeState) => {
      const overlay = document.querySelector('.fig-lightbox:not([hidden])');
      const svg = overlay && overlay.querySelector('.fig-lightbox-stage svg');
      const close = overlay && overlay.querySelector('.fig-lightbox-x');
      const hint = overlay && overlay.querySelector('.fig-lightbox-hint');
      const svgBox = svg && svg.getBoundingClientRect();
      const closeBox = close && close.getBoundingClientRect();
      return {
        badge: badgeState,
        svgWidth: svgBox ? Math.round(svgBox.width) : 0,
        svgHeight: svgBox ? Math.round(svgBox.height) : 0,
        overlayClientWidth: overlay ? overlay.clientWidth : 0,
        overlayScrollWidth: overlay ? overlay.scrollWidth : 0,
        closeVisible: !!closeBox && closeBox.width >= 36 && closeBox.height >= 36,
        hintVisible: !!hint && getComputedStyle(hint).display !== 'none' && /swipe to pan/i.test(hint.textContent || ''),
      };
    }, badge);
    await page.keyboard.press('Escape');
    figureZoom.closed = await page.locator('.fig-lightbox[hidden]').count() === 1;
  }

  const failures = [];
  if (!initial.main) failures.push('missing <main>');
  if (initial.flows + initial.runCells > 0 && initial.unifiedButtons < (initial.flows * 2 + initial.panels * 2 + initial.runCells * 2)) failures.push('too few unified .cell-btn controls');
  if (initial.flows + initial.runCells > 0 && initial.unifiedLangChips < initial.panels + initial.runCells) failures.push('too few unified JS chips');
  if (initial.uglyCellButtons) failures.push(`ugly legacy buttons ${initial.uglyCellButtons}`);
  if (initial.plainCodeLabels) failures.push(`plain code labels ${initial.plainCodeLabels}`);
  if (initial.canvasLongOpen) failures.push(`long CanvasFlow code open by default ${initial.canvasLongOpen}`);
  if (initial.flows + initial.runCells > 0 && finalInfo.codeMirrorCount < initial.panels + initial.runCells) failures.push('CodeMirror did not mount for every opened editor');
  if (initial.flows + initial.runCells > 0 && finalInfo.cmTokenCount < finalInfo.codeMirrorCount) failures.push('CodeMirror syntax tokens missing');
  if (initial.badOverflow.length) failures.push(`uncontained horizontal overflow ${JSON.stringify(initial.badOverflow)}`);
  if (initial.themeMismatchSurfaces.length) failures.push(`${theme} theme wrong-tone cell/graph surfaces ${JSON.stringify(initial.themeMismatchSurfaces)}`);
  if (finalInfo.themeMismatchSurfaces.length) failures.push(`${theme} theme wrong-tone expanded surfaces ${JSON.stringify(finalInfo.themeMismatchSurfaces)}`);
  if (initial.minCellButton < 28) failures.push(`tiny cell button dimension ${initial.minCellButton}`);
  const badActionLayout = initial.cellActionLayout.filter(group => group.rows > 1 || group.wrappedLabels.length);
  if (badActionLayout.length) failures.push(`cell actions split or wrapped ${JSON.stringify(badActionLayout)}`);
  const badArtifacts = initial.artifacts.filter(a => !a.marked || !a.label || !a.cue.includes(a.label) || a.railWidth < 2 || /rgba?\(0,\s*0,\s*0,\s*0\)/.test(a.rail) || (a.surface && (a.maxHeight === 'none' || !/auto|scroll/.test(a.overflowY))));
  if (badArtifacts.length) failures.push(`live artifact cue missing ${JSON.stringify(badArtifacts)}`);
  const badRuns = runResults.filter(r => !r.hasOutput || r.badText);
  if (badRuns.length) failures.push(`helper run output failed ${JSON.stringify(badRuns)}`);
  if (figureZoom && !figureZoom.closed) failures.push('figure lightbox did not close on Escape');
  if (figureZoom && !figureZoom.closeVisible) failures.push('figure lightbox close control is not visible');
  if (figureZoom && vp.name === 'narrow' && figureZoom.svgWidth < 680) failures.push(`mobile figure zoom remains unreadably narrow ${JSON.stringify(figureZoom)}`);
  if (figureZoom && vp.name === 'narrow' && figureZoom.overlayScrollWidth <= figureZoom.overlayClientWidth) failures.push(`mobile figure zoom is not horizontally pannable ${JSON.stringify(figureZoom)}`);
  if (figureZoom && vp.name === 'narrow' && (!figureZoom.badge.content.includes('tap to enlarge') || figureZoom.badge.opacity < 0.8)) failures.push(`mobile figure zoom affordance is hidden ${JSON.stringify(figureZoom.badge)}`);
  if (figureZoom && vp.name === 'narrow' && !figureZoom.hintVisible) failures.push(`mobile figure pan hint is hidden ${JSON.stringify(figureZoom)}`);
  if (pageErrors.length) failures.push(`page errors ${JSON.stringify(pageErrors)}`);
  return { pagePath, viewport: vp.name, theme, initial, runResults, finalInfo, figureZoom, consoleErrors, failures };
}

(async () => {
  await listen();
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_BIN || undefined,
    args: process.env.CHROME_BIN ? ['--no-sandbox'] : [],
  });
  const results = [];
  for (const pagePath of pages) {
    for (const vp of viewports) {
      for (const theme of themes) {
        const page = await browser.newPage();
        try { results.push(await inspectPage(page, pagePath, vp, theme)); }
        finally { await page.close().catch(() => {}); }
      }
    }
  }
  await browser.close();
  server.close();
  const failed = results.filter(r => r.failures.length);
  const verbose = process.env.AUDIT_VERBOSE === '1';
  console.log(JSON.stringify({
    ok: failed.length === 0,
    root,
    screenshots: screenshots || null,
    checked: results.length,
    failures: failed,
    ...(verbose ? { results } : {}),
  }, null, 2));
  process.exit(failed.length ? 1 : 0);
})().catch(err => {
  try { server.close(); } catch (_) {}
  console.error(err && err.stack || String(err));
  process.exit(1);
});
"""


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validate shared CanvasFlow/RunCell UI in host-native Chromium")
    ap.add_argument("--site-root", default="web", help="site root to serve, usually web or public")
    ap.add_argument("--page", action="append", dest="pages", help="page path under site root; repeatable")
    ap.add_argument("--screenshots", default="", help="directory for full-page PNG screenshots")
    ap.add_argument("--timeout-ms", type=int, default=120000, help="browser timeout")
    return ap.parse_args()


def discover_default_pages(site_root: Path) -> list[str]:
    """Cover every shipped page that authors a runnable cell or generated graph.

    The old hand-picked list exercised shared CSS but missed page-local interactions between injected
    figures and later diagrams. Discovering from the built/source HTML is what makes a future graph
    page enter the dark/light matrix without a validator edit.
    """
    course_roots = [site_root / "nemoclaw", *sorted(site_root.glob("*/nemoclaw"))]
    pages: list[str] = []
    for course in course_roots:
        if not course.is_dir():
            continue
        prefix = "/" + course.relative_to(site_root).as_posix()
        pages.extend(f"{prefix}/{extra}" for extra in DEFAULT_EXTRA_PAGES if (course / extra).is_file())
        for html in sorted(course.glob("*.html")):
            text = html.read_text(errors="ignore")
            if any(marker in text for marker in INTERACTIVE_MARKERS):
                pages.append(f"{prefix}/{html.name}")
    return list(dict.fromkeys(pages))


def main() -> int:
    args = parse_args()
    site_root = (ROOT / args.site_root).resolve() if not Path(args.site_root).is_absolute() else Path(args.site_root).resolve()
    if not site_root.exists():
        print(f"cell_ui_runtime_audit: FAIL\n  - site root missing: {site_root}")
        return 1
    pages = args.pages or discover_default_pages(site_root)
    screenshot_dir = ""
    if args.screenshots:
        out = Path(args.screenshots)
        if not out.is_absolute():
            out = ROOT / out
        out.mkdir(parents=True, exist_ok=True)
        screenshot_dir = str(out.resolve())
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(RUNTIME_JS)
        script = Path(fh.name)
    try:
        proc = run_node(
            script,
            env=environment(
                SITE_ROOT=site_root,
                CELL_UI_PAGES=__import__('json').dumps(pages),
                AUDIT_TIMEOUT_MS=str(args.timeout_ms),
                SCREENSHOT_DIR=screenshot_dir or None,
            ),
            timeout=(args.timeout_ms / 1000) * max(1, len(pages)) * 4 + 60,
        )
    except BrowserRuntimeError as exc:
        print(f"cell_ui_runtime_audit: FAIL\n  - {exc}")
        return 1
    except subprocess.TimeoutExpired as exc:
        print("cell_ui_runtime_audit: FAIL")
        print(f"  - timed out after {exc.timeout}s")
        if exc.stdout:
            print(exc.stdout)
        return 1
    finally:
        try:
            script.unlink()
        except OSError:
            pass
    print(proc.stdout.rstrip())
    print("cell_ui_runtime_audit: " + ("OK" if proc.returncode == 0 else "FAIL"))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
