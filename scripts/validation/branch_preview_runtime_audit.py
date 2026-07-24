#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise root and branch foyer preview filtering in host-native Chromium."""
from __future__ import annotations

import argparse
import json
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

RUNTIME_JS = r"""
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const root = process.env.SITE_ROOT;
const port = 4201;
const mime = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.json':'application/json; charset=utf-8', '.svg':'image/svg+xml', '.png':'image/png' };
const ghost = { name:'never-published', slug:'never-published', kind:'preview', url:'never-published/web/nemoclaw/', preview_ready:true, current:false };

function safeJoin(urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]).replace(/^\/+/, '');
  const out = path.resolve(root, clean);
  if (!out.startsWith(path.resolve(root))) throw new Error('path escape');
  return out;
}
const server = http.createServer((req, res) => {
  let file;
  try { file = safeJoin(req.url || '/'); } catch (_) { res.writeHead(403); res.end(); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end('not found'); return; }
    if (file.endsWith('branches.json')) {
      const parsed = JSON.parse(data.toString('utf8'));
      parsed.branches.push(ghost);
      data = Buffer.from(JSON.stringify(parsed));
    }
    res.writeHead(200, { 'content-type': mime[path.extname(file)] || 'application/octet-stream' });
    res.end(req.method === 'HEAD' ? undefined : data);
  });
});

async function inspect(browser, pagePath, expected) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message || String(error)));
  await page.goto(`http://127.0.0.1:${port}${pagePath}`, { waitUntil:'networkidle' });
  await page.locator('#branch-switcher.ready').waitFor({ state:'visible' });
  const options = await page.locator('#branch-select option').evaluateAll(nodes => nodes.map(node => ({
    name: node.dataset.name,
    kind: node.dataset.kind,
    value: node.value,
  })));
  const names = options.map(option => option.name);
  if (JSON.stringify(names) !== JSON.stringify(expected)) throw new Error(`${pagePath} options ${JSON.stringify(names)} != ${JSON.stringify(expected)}`);
  if (names.includes(ghost.name)) throw new Error(`${pagePath} exposed injected unavailable preview`);
  if (pageErrors.length) throw new Error(`${pagePath} page errors: ${JSON.stringify(pageErrors)}`);
  await page.close();
  return { pagePath, options };
}

(async () => {
  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'branches.json'), 'utf8'));
  const expected = manifest.branches.map(branch => branch.name);
  const previews = manifest.branches.filter(branch => branch.kind === 'preview');
  const browser = await chromium.launch({ headless:true, executablePath:process.env.CHROME_BIN });
  const results = [await inspect(browser, '/index.html', expected)];
  for (const preview of previews) results.push(await inspect(browser, `/${preview.slug}/index.html`, expected));
  await browser.close();
  server.close();
  console.log(JSON.stringify({ ok:true, injectedGhost:ghost.name, results }, null, 2));
})().catch(error => {
  try { server.close(); } catch (_) {}
  console.error(error.stack || String(error));
  process.exit(1);
});
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-root", default="public")
    args = ap.parse_args()
    site_arg = Path(args.site_root)
    site_root = site_arg.resolve() if site_arg.is_absolute() else (ROOT / site_arg).resolve()
    if not (site_root / "index.html").is_file() or not (site_root / "branches.json").is_file():
        print(f"branch_preview_runtime_audit: FAIL\n  - incomplete site root: {site_root}")
        return 1
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(RUNTIME_JS)
        script = Path(handle.name)
    try:
        proc = run_node(script, env=environment(SITE_ROOT=site_root), timeout=180)
    except (BrowserRuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"branch_preview_runtime_audit: FAIL\n  - {exc}")
        return 1
    finally:
        try:
            script.unlink()
        except OSError:
            pass
    print(proc.stdout.rstrip())
    print("branch_preview_runtime_audit: " + ("OK" if proc.returncode == 0 else "FAIL"))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
