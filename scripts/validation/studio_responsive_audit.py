#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Browser-check Studio responsive floors and scroll containers."""
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
DEFAULT_PATH = "/nemoclaw/studio.html?page=01a-loop.html"

RUNTIME_JS = r"""
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const root = process.env.SITE_ROOT || '/site';
const pagePath = process.env.PAGE_PATH || '/nemoclaw/studio.html?page=01a-loop.html';
const port = Number(process.env.SITE_PORT || 4192);
const timeoutMs = Number(process.env.AUDIT_TIMEOUT_MS || 120000);
const mime = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.json':'application/json; charset=utf-8', '.svg':'image/svg+xml', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.woff2':'font/woff2' };
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

async function checkViewport(page, width, height) {
  await page.setViewportSize({ width, height });
  await page.goto(`http://127.0.0.1:${port}${pagePath}`, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
  await page.waitForSelector('#studio-frame', { timeout: timeoutMs });
  await wait(350);
  const result = await page.evaluate(() => {
    const fillList = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return;
      el.innerHTML = Array.from({length: 18}, (_, i) => `<div class="ref-item"><span class="ref-kind">item</span><a href="#">Long reference row ${i + 1} / ${'x'.repeat(48)}</a><div class="ref-meta"><span>left</span><span>right</span></div></div>`).join('');
    };
    ['#ref-list', '#cmt-list', '#test-list', '#chg-list'].forEach(fillList);
    const top = document.querySelector('.studio-topbar');
    const topStyle = getComputedStyle(top);
    top.scrollLeft = 24;
    const btns = Array.from(document.querySelectorAll('.studio-topbar .tb-btn'));
    const tinyBtns = btns.map(btn => ({ id: btn.id, w: btn.getBoundingClientRect().width, h: btn.getBoundingClientRect().height })).filter(b => b.w < 48 || b.h < 30);
    const lists = ['#ref-list', '#cmt-list', '#test-list', '#chg-list'].map(sel => {
      const el = document.querySelector(sel);
      const cs = getComputedStyle(el);
      return { sel, overflowY: cs.overflowY, h: el.getBoundingClientRect().height, clientHeight: el.clientHeight, scrollHeight: el.scrollHeight, canScroll: el.scrollHeight > el.clientHeight + 4 };
    });
    const badLists = lists.filter(x => x.overflowY !== 'auto' || x.h < 96 || !x.canScroll);
    return {
      topOverflowX: topStyle.overflowX,
      topCanScroll: top.scrollWidth > top.clientWidth + 4 && top.scrollLeft > 0,
      topScrollWidth: top.scrollWidth,
      topClientWidth: top.clientWidth,
      tinyBtns,
      lists,
      badLists,
      bodyOverflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      sidebarWidth: document.querySelector('#sidebar')?.getBoundingClientRect().width || 0,
    };
  });
  const errors = [];
  if (!['auto', 'scroll'].includes(result.topOverflowX)) errors.push(`topbar overflow-x is ${result.topOverflowX}`);
  if (!result.topCanScroll) errors.push(`topbar cannot scroll internally: ${JSON.stringify(result)}`);
  if (result.tinyBtns.length) errors.push(`topbar controls collapsed below usable size: ${JSON.stringify(result.tinyBtns)}`);
  if (result.badLists.length) errors.push(`sidebar lists lack scroll floor: ${JSON.stringify(result.badLists)}`);
  if (result.sidebarWidth < 220) errors.push(`sidebar width collapsed: ${result.sidebarWidth}`);
  if (result.bodyOverflowX > 2) errors.push(`body-level horizontal overflow: ${result.bodyOverflowX}px`);
  if (errors.length) throw new Error(`${width}x${height}: ${errors.join('; ')}`);
  return { width, height, ...result };
}

(async () => {
  await listen();
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_BIN });
  const page = await browser.newPage();
  const sizes = [[360, 360], [520, 420], [900, 360]];
  const results = [];
  for (const [w, h] of sizes) results.push(await checkViewport(page, w, h));
  await browser.close();
  server.close();
  console.log(JSON.stringify({ ok: true, results: results.map(r => ({ width: r.width, height: r.height, topClientWidth: r.topClientWidth, topScrollWidth: r.topScrollWidth, sidebarWidth: r.sidebarWidth })) }, null, 2));
})().catch(err => {
  try { server.close(); } catch (_) {}
  console.error(err && err.stack || String(err));
  process.exit(1);
});
"""


def run_browser(args: argparse.Namespace) -> int:
    site_root = (ROOT / args.site_root).resolve() if not Path(args.site_root).is_absolute() else Path(args.site_root).resolve()
    if not site_root.exists():
        print(f"studio_responsive_audit: FAIL\n  - site root missing: {site_root}", file=sys.stderr)
        return 1
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(RUNTIME_JS)
        script = Path(fh.name)
    try:
        proc = run_node(script, env=environment(SITE_ROOT=site_root, PAGE_PATH=args.page_path, AUDIT_TIMEOUT_MS=str(args.timeout_ms)), timeout=(args.timeout_ms / 1000) + 30)
    except BrowserRuntimeError as exc:
        print(f"studio_responsive_audit: FAIL\n  - {exc}")
        return 1
    except subprocess.TimeoutExpired as exc:
        print("studio_responsive_audit: FAIL")
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
    if proc.returncode == 0:
        print("studio_responsive_audit: OK")
    else:
        print("studio_responsive_audit: FAIL")
    return proc.returncode


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Browser-check Studio responsive floors")
    ap.add_argument("--site-root", default="web", help="site root to serve in host Chromium")
    ap.add_argument("--page-path", default=DEFAULT_PATH, help="studio URL path under served site root")
    ap.add_argument("--timeout-ms", type=int, default=120000, help="browser timeout")
    return ap.parse_args()


def main() -> int:
    return run_browser(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
