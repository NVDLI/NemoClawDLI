#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate the runnable helper notebook in web/nemoclaw/scripts/SKILL.html.

Default mode runs two checks:
- static API-surface audit for the notebook source
- host-native Playwright smoke that clicks every notebook Run control

Use --static-only to run the deterministic source audit without a browser.
"""
from __future__ import annotations

import argparse
import json
import re
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
SKILL = ROOT / "web" / "nemoclaw" / "scripts" / "SKILL.html"
DEFAULT_PATH = "/nemoclaw/scripts/SKILL.html"

CANVAS_UNSUPPORTED = ()
RUN_CELL_UNSUPPORTED = (
    "helpers.viz.",
)
REQUIRED_IDS = (
    "helper-map-cell",
    "helper-retrieval-cell",
    "helper-live-cell",
    "helper-ui-cell",
)
RUNTIME_JS = r"""
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const root = process.env.SITE_ROOT || '/site';
const pagePath = process.env.PAGE_PATH || '/nemoclaw/scripts/SKILL.html';
const port = Number(process.env.SITE_PORT || 4188);
const timeoutMs = Number(process.env.AUDIT_TIMEOUT_MS || 120000);
const mime = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
  '.woff2': 'font/woff2'
};

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

function waitForListen(srv) {
  return new Promise(resolve => srv.listen(port, '127.0.0.1', resolve));
}
function wait(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

(async () => {
  await waitForListen(server);
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_BIN });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', err => pageErrors.push(err.message || String(err)));
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  const url = `http://127.0.0.1:${port}${pagePath}`;
  await page.goto(url, { waitUntil: 'networkidle', timeout: timeoutMs });
  await page.waitForSelector('.helper-notebook', { timeout: timeoutMs });
  await page.waitForFunction(() => typeof window.CodeMirror === 'function', null, { timeout: timeoutMs });
  await page.waitForFunction(() => {
    const expected = document.querySelectorAll('.helper-notebook .cf-panel-code, .helper-notebook .rc-code').length;
    return expected > 0 && document.querySelectorAll('.helper-notebook .CodeMirror').length >= expected;
  }, null, { timeout: timeoutMs });
  const surface = await page.evaluate(() => {
    const table = document.querySelector('#validation-table');
    const rows = table ? Array.from(table.querySelectorAll('tbody tr')) : [];
    const tb = table && table.getBoundingClientRect();
    const validationRows = rows.map((tr, idx) => {
      const first = tr.querySelector('td:first-child');
      const second = tr.querySelector('td:nth-child(2)');
      const code = first && first.querySelector('code');
      const fb = first && first.getBoundingClientRect();
      const sb = second && second.getBoundingClientRect();
      const cs = code && getComputedStyle(code);
      return {
        idx,
        command: code ? code.textContent.trim() : '',
        commandRatio: tb && fb ? fb.width / tb.width : 1,
        descRatio: tb && sb ? sb.width / tb.width : 0,
        commandWhiteSpace: cs && cs.whiteSpace,
        commandOverflowWrap: cs && cs.overflowWrap,
        commandScrolls: code ? code.scrollWidth > code.clientWidth + 2 : false,
      };
    });
    const unupgradedEditors = Array.from(document.querySelectorAll('.helper-notebook .cf-code-view > textarea, .helper-notebook .rc-code-body > textarea')).filter(ta => {
      const host = ta.closest('.cf-code-view,.rc-code-body');
      return host && !host.querySelector('.CodeMirror');
    }).map(ta => ta.className || ta.getAttribute('data-src-for') || 'textarea');
    return {
      codeMirrorCount: document.querySelectorAll('.helper-notebook .CodeMirror').length,
      expectedEditors: document.querySelectorAll('.helper-notebook .cf-panel-code, .helper-notebook .rc-code').length,
      cmTokenCount: document.querySelectorAll('.helper-notebook .CodeMirror .cm-keyword, .helper-notebook .CodeMirror .cm-string, .helper-notebook .CodeMirror .cm-property').length,
      hasHljs: typeof window.hljs !== 'undefined',
      validationTable: !!table,
      validationRows,
      unupgradedEditors,
      unifiedButtons: document.querySelectorAll('.helper-notebook .cell-btn').length,
      unifiedLangChips: document.querySelectorAll('.helper-notebook .cell-lang-chip').length,
      uglyCellButtons: document.querySelectorAll('.helper-notebook .rc-run:not(.cell-btn),.helper-notebook .rc-reset:not(.cell-btn),.helper-notebook .cf-panel-runone:not(.cell-btn),.helper-notebook .cf-panel-reset:not(.cell-btn)').length,
      plainCodeLabels: Array.from(document.querySelectorAll('.helper-notebook .rc-code-det > summary,.helper-notebook .cf-panel-code-det > summary')).filter(el => /^code\b/i.test((el.textContent || '').trim())).length,
      pageOverflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      badOverflow: Array.from(document.querySelectorAll('body *')).filter(el => {
        const r = el.getBoundingClientRect();
        if (r.right <= document.documentElement.clientWidth + 2) return false;
        if (el.closest('.topbar nav,.cf-stage,.CodeMirror,.CodeMirror-scroll,.cf-helpers-scroll,.cell-log-json,.cf-panel-log-json,.cf-log-json,pre')) return false;
        return true;
      }).slice(0, 8).map(el => ({ tag: el.tagName, cls: String(el.className || '').slice(0, 80), text: (el.textContent || '').trim().slice(0, 80) })),
    };
  });
  if (!surface.hasHljs) throw new Error('highlight.js not loaded on helper notebook page');
  if (!surface.validationTable) throw new Error('validation table missing #validation-table');
  if (surface.codeMirrorCount < surface.expectedEditors) throw new Error(`not every helper notebook editor upgraded to CodeMirror: ${JSON.stringify(surface)}`);
  if (surface.cmTokenCount < surface.expectedEditors) throw new Error(`CodeMirror mounted without visible syntax tokens: ${JSON.stringify(surface)}`);
  if (surface.unupgradedEditors.length) throw new Error(`raw editors did not upgrade to CodeMirror: ${JSON.stringify(surface.unupgradedEditors)}`);
  const badRows = surface.validationRows.filter(r => r.commandRatio > 0.46 || r.descRatio < 0.50 || r.commandWhiteSpace !== 'pre-wrap' || !['anywhere', 'break-word'].includes(r.commandOverflowWrap) || r.commandScrolls);
  if (badRows.length) throw new Error(`validation table rows fail wrapping/proportion checks: ${JSON.stringify(badRows)}`);
  if (surface.uglyCellButtons > 0) throw new Error(`helper notebook has ugly legacy cell buttons: ${surface.uglyCellButtons}`);
  if (surface.plainCodeLabels > 0) throw new Error(`helper notebook has old plain code labels: ${surface.plainCodeLabels}`);
  if (surface.unifiedButtons < 12) throw new Error(`helper notebook missing unified buttons: ${JSON.stringify(surface)}`);
  if (surface.unifiedLangChips < surface.expectedEditors) throw new Error(`helper notebook missing unified JS chips: ${JSON.stringify(surface)}`);
  if (surface.badOverflow.length) throw new Error(`page has uncontained horizontal overflow: ${JSON.stringify(surface.badOverflow)}`);
  const selectors = [
    '#helper-map-cell .cf-btn-run',
    '#helper-retrieval-cell .cf-btn-run',
    '#helper-live-cell .cf-btn-run',
    '#helper-ui-cell .rc-run'
  ];
  const results = [];
  for (const sel of selectors) {
    const count = await page.locator(sel).count();
    if (!count) throw new Error(`missing run control: ${sel}`);
    const button = page.locator(sel).first();
    const before = await button.innerText().catch(() => '');
    await button.click();
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const text = await button.innerText().catch(() => '');
      if (!/stop|running|⏹/i.test(text)) break;
      await wait(250);
    }
    const after = await button.innerText().catch(() => '');
    if (/stop|running|⏹/i.test(after)) throw new Error(`run did not finish: ${sel}`);
    const cellText = await page.locator(sel.replace(/ .*/, '')).innerText().catch(() => '');
    results.push({ selector: sel, before, after, failed: /✗ stopped:|TypeError|ReferenceError|helpers\.log\.h is not a function/.test(cellText) });
  }
  const body = await page.locator('body').innerText();
  const runtimeFailures = results.filter(r => r.failed);
  const textFailure = body.match(/✗ stopped:[^\n]*|TypeError[^\n]*|ReferenceError[^\n]*/g) || [];
  const lightVisuals = await page.evaluate(() => {
    document.documentElement.dataset.theme = 'light';
    return Array.from(document.querySelectorAll('.helper-notebook svg.gfx-dark[role="img"]')).map(svg => {
      const stroke = svg.querySelector('polyline, line, path');
      const label = svg.querySelector('text');
      return {
        label: svg.getAttribute('aria-label') || '',
        background: getComputedStyle(svg).backgroundColor,
        stroke: stroke ? getComputedStyle(stroke).stroke : '',
        text: label ? getComputedStyle(label).fill : '',
      };
    });
  });
  const badVisuals = lightVisuals.filter(visual =>
    !visual.label || visual.background !== 'rgb(255, 255, 255)' ||
    !visual.stroke || visual.stroke === visual.background ||
    !visual.text || visual.text === visual.background);
  if (!lightVisuals.length || badVisuals.length) {
    throw new Error(`helper SVG output is not visible in light theme: ${JSON.stringify({ lightVisuals, badVisuals })}`);
  }
  await browser.close();
  server.close();
  if (runtimeFailures.length || pageErrors.length || textFailure.length) {
    console.error(JSON.stringify({ ok: false, url, results, pageErrors, consoleErrors, textFailure }, null, 2));
    process.exit(1);
  }
  console.log(JSON.stringify({ ok: true, url, ran: results.map(r => r.selector), consoleErrors }, null, 2));
})().catch(async (err) => {
  try { server.close(); } catch (_) {}
  console.error(err && err.stack || String(err));
  process.exit(1);
});
"""



def _skill_meta(raw: str) -> dict:
    m = re.search(r'<script[^>]+id=["\']skill-meta["\'][^>]*>(.*?)</script>', raw, re.S | re.I)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return {}


def _table_commands(raw: str) -> list[str]:
    m = re.search(r'<table[^>]+id=["\']validation-table["\'][^>]*>(.*?)</table>', raw, re.S | re.I)
    if not m:
        return []
    return [re.sub(r"\s+", " ", x).strip() for x in re.findall(r'<td>\s*<code>(.*?)</code>\s*</td>', m.group(1), re.S | re.I)]


def _mount_targets(raw: str, marker: str) -> list[str]:
    return re.findall(rf'{marker}\(\s*["\']#([^"\']+)["\']', raw)

def _line_for(raw: str, token: str, start: int = 0) -> int:
    idx = raw.find(token, start)
    return raw.count("\n", 0, idx) + 1 if idx >= 0 else 0


def _regions(raw: str, marker: str) -> list[tuple[int, str]]:
    starts = [m.start() for m in re.finditer(re.escape(marker), raw)]
    all_starts = sorted(starts + [m.start() for m in re.finditer(r"mount(?:CanvasFlow|RunCell)\(", raw)])
    out: list[tuple[int, str]] = []
    for start in starts:
        end_candidates = [x for x in all_starts if x > start]
        end = end_candidates[0] if end_candidates else len(raw)
        out.append((start, raw[start:end]))
    return out


def static_audit(skill_path: Path = SKILL) -> list[str]:
    raw = skill_path.read_text(encoding="utf-8")
    findings: list[str] = []
    for item in REQUIRED_IDS:
        if item not in raw:
            findings.append(f"missing helper notebook cell #{item}")

    meta_tests = _skill_meta(raw).get("tests", [])
    table_cmds = _table_commands(raw)
    for cmd in meta_tests:
        if cmd not in table_cmds:
            findings.append(f"skill-meta test missing from Validation table: {cmd}")
    for cmd in table_cmds:
        if cmd not in meta_tests:
            findings.append(f"Validation table command missing from skill-meta tests: {cmd}")

    ids = set(re.findall(r"id=[\"\']([^\"\']+)[\"\']", raw))
    for target in _mount_targets(raw, "mountCanvasFlow") + _mount_targets(raw, "mountRunCell"):
        if target not in ids:
            findings.append(f"runtime mount target #{target} has no matching DOM id")
    if len(_mount_targets(raw, "mountCanvasFlow")) < 3:
        findings.append("helper notebook should keep at least three CanvasFlow examples")
    if len(_mount_targets(raw, "mountRunCell")) < 1:
        findings.append("helper notebook should keep at least one RunCell example")
    for required in (
        "python3 scripts/validation/helper_notebook_runtime_audit.py --static-only",
        "python3 scripts/validation/helper_notebook_runtime_audit.py",
        "python3 scripts/validation/cell_ui_runtime_audit.py --screenshots tmp/cell-ui-audit-source",
        "python3 scripts/validation/cell_ui_runtime_audit.py --site-root public --screenshots tmp/cell-ui-audit-public",
        "scripts/runtime/browser_env_probe.sh",
        "scripts/runtime/browser_runtime_test.sh --smoke",
        "../vendor/highlight-11.10.0.min.js",
        "../vendor/codemirror-5.65.21.js",
        "../vendor/codemirror-mode-javascript-5.65.21.js",
        "../vendor/codemirror-mode-python-5.65.21.js",
        "../vendor/codemirror-5.65.21.css",
        'id="validation-table"',
        "validation-command-col",
        "overflow-wrap: anywhere",
        "table-layout: fixed",
        "white-space: pre-wrap",
        "hljs.highlightAll",
    ):
        if required not in raw:
            findings.append(f"web/nemoclaw/scripts/SKILL.html missing validation token: {required}")
    for start, block in _regions(raw, "mountCanvasFlow("):
        for token in CANVAS_UNSUPPORTED:
            if token in block:
                findings.append(f"CanvasFlow block uses RunCell-only API {token} at line {_line_for(raw, token, start)}")
    for start, block in _regions(raw, "mountRunCell("):
        for token in RUN_CELL_UNSUPPORTED:
            if token in block:
                findings.append(f"RunCell block uses CanvasFlow-only API {token} at line {_line_for(raw, token, start)}")
    shared_log_tokens = (
        "helpers.log(",
        "helpers.log.h(",
        "helpers.log.json(",
        "helpers.log.kv(",
        "helpers.log.details(",
        "helpers.log.html(",
        "helpers.log.svg(",
        "helpers.log.draw(",
        "helpers.log.clear(",
    )
    for token in shared_log_tokens:
        if token not in raw:
            findings.append(f"helper notebook must retain shared log API coverage: {token}")
    for token in ("helpers.log.svg(", "helpers.log.draw("):
        if raw.count(token) < 2:
            findings.append(f"helper notebook must show {token} in both CanvasFlow and RunCell examples")
    if "helpers.log.h(\"UI helper dry run\")" not in raw or "helpers.log.h(\"shared log surfaces\")" not in raw:
        findings.append("helper notebook must retain log heading examples in both RunCell and CanvasFlow")
    if any(token not in raw for token in (
        "helpers.viz.lineChart(", "helpers.viz.scoreBarChart(", "helpers.viz.diffTable(",
    )):
        findings.append("CanvasFlow visualization examples must retain trace, chart, and diff coverage")
    if "helpers.coursePages()" not in raw or "helpers.formatSearchResults(" not in raw:
        findings.append("retrieval/context examples must retain coursePages and formatSearchResults coverage")
    if "helpers.fetchRetry(" not in raw or "helpers.browserChatFetch()" not in raw:
        findings.append("network examples must retain fetchRetry and browserChatFetch coverage")
    return findings


def run_browser(args: argparse.Namespace) -> int:
    site_root = (ROOT / args.site_root).resolve() if not Path(args.site_root).is_absolute() else Path(args.site_root).resolve()
    if not site_root.exists():
        print(f"helper_notebook_runtime_audit: FAIL\n  - site root missing: {site_root}", file=sys.stderr)
        return 1
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(RUNTIME_JS)
        script = Path(fh.name)
    try:
        proc = run_node(script, env=environment(SITE_ROOT=site_root, PAGE_PATH=args.page_path, AUDIT_TIMEOUT_MS=str(args.timeout_ms)), timeout=(args.timeout_ms / 1000) + 30)
    except BrowserRuntimeError as exc:
        print(f"helper_notebook_runtime_audit: FAIL\n  - {exc}")
        return 1
    except subprocess.TimeoutExpired as exc:
        print("helper_notebook_runtime_audit: FAIL")
        print(f"  - browser audit timed out after {exc.timeout}s")
        if exc.stdout:
            print(exc.stdout)
        return 1
    finally:
        try:
            script.unlink()
        except OSError:
            pass
    print(proc.stdout.rstrip())
    return proc.returncode


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Validate web/nemoclaw/scripts/SKILL.html helper notebook")
    ap.add_argument("--static-only", action="store_true", help="run deterministic source audit without Chromium")
    ap.add_argument("--site-root", default="web", help="site root to serve in host Chromium")
    ap.add_argument("--page-path", default=DEFAULT_PATH, help="page path under served site root")
    ap.add_argument("--timeout-ms", type=int, default=120000, help="per-run browser timeout")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    findings = static_audit()
    if findings:
        print("helper_notebook_runtime_audit: FAIL")
        for row in findings:
            print(f"  - {row}")
        return 1
    if args.static_only:
        print("helper_notebook_runtime_audit: OK (static)")
        return 0
    rc = run_browser(args)
    if rc == 0:
        print("helper_notebook_runtime_audit: OK (runtime)")
    else:
        print("helper_notebook_runtime_audit: FAIL (runtime)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
