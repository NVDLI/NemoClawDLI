#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mount every discovered course interface in an egress-denied Chromium context.

The candidate is untrusted. This harness supplies no credential, blocks service workers, aborts
every non-loopback request and WebSocket, and adds a restrictive response CSP. It proves that each
inventory instance resolves, mounts, exposes the semantics required by its form factor, and keeps
the page palette readable in both themes. Live remote transports run later in trusted code.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.runtime.host_browser import BrowserRuntimeError, environment, run_node
from scripts.validation.interface_inventory_audit import audit as audit_inventory


RUNTIME = r"""
const fs = require('fs');
const http = require('http');
const path = require('path');
const { chromium } = require('playwright-core');

const site = path.resolve(process.env.SITE_ROOT);
const inventory = JSON.parse(fs.readFileSync(process.env.INTERFACE_REPORT, 'utf8'));
const sourceMode = process.env.SOURCE_MODE === '1';
const port = Number(process.env.SITE_PORT || 4238);
const timeout = Number(process.env.AUDIT_TIMEOUT_MS || 600000);
const origin = `http://127.0.0.1:${port}`;
const csp = [
  "default-src 'self' data: blob:",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval' blob:",
  "style-src 'self' 'unsafe-inline'",
  "connect-src 'self' data: blob:",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "media-src 'none'", "frame-src 'self' blob:", "worker-src 'none'",
  "form-action 'self'", "base-uri 'none'", "object-src 'none'",
].join('; ');
const mime = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.mjs':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.json':'application/json; charset=utf-8', '.svg':'image/svg+xml', '.png':'image/png', '.jpg':'image/jpeg', '.woff2':'font/woff2', '.whl':'application/zip', '.wasm':'application/wasm' };

function safeFile(raw) {
  let rel = decodeURIComponent(new URL(raw, origin).pathname).replace(/^\/+/, '');
  if (!rel || rel.endsWith('/')) rel += 'index.html';
  const file = path.resolve(site, rel);
  if (file !== site && !file.startsWith(site + path.sep)) throw new Error('path escape');
  return file;
}
const server = http.createServer((request, response) => {
  let file;
  try { file = safeFile(request.url || '/'); } catch (_) { response.writeHead(403).end('forbidden'); return; }
  fs.readFile(file, (error, body) => {
    if (error && sourceMode && path.basename(file) === 'languages.json') {
      response.writeHead(200, { 'content-type':'application/json', 'content-security-policy':csp });
      response.end('{"schema":"nemoclaw-languages/1","default":"en","languages":[]}');
      return;
    }
    if (error) { response.writeHead(404, { 'content-type':'text/plain', 'content-security-policy':csp }).end('not found'); return; }
    response.writeHead(200, { 'content-type':mime[path.extname(file)] || 'application/octet-stream', 'content-security-policy':csp, 'x-content-type-options':'nosniff' });
    response.end(body);
  });
});
const listen = () => new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
const fail = message => { throw new Error(message); };

async function waitAttached(locator, timeoutMs, instance, label) {
  try {
    await locator.waitFor({ state:'attached', timeout:timeoutMs });
  } catch (error) {
    fail(`${instance.id}: ${label} did not attach at ${instance.entry} ${instance.selector}: ${error.message}`);
  }
}

async function exercise(locator, profile, id) {
  return locator.evaluate(async (root, data) => {
    const ENTRY_STATES = new Set(['ready','blocked','empty','loading','preview','idle']);
    const ACTION_WORDS = /\b(run|start|send|test|save|apply|connect|open|play|preview|select|continue|get|request)\b/i;
    const failLocal = message => { throw new Error(message); };
    const stateWords = () => {
      const declared = new Set(data.profile.states || []);
      const observed = new Set();
      for (const node of [root, ...root.querySelectorAll('[data-state],[aria-busy],[aria-current],[aria-selected],[role="status"]')]) {
        const values = [node.dataset?.state, node.getAttribute?.('aria-current'), node.getAttribute?.('aria-selected')];
        if (node.getAttribute?.('aria-busy') === 'true') values.push('running');
        const text = node.getAttribute?.('role') === 'status' ? String(node.textContent || '').toLowerCase() : '';
        for (const state of declared) if (text && new RegExp(`\\b${state.replaceAll('-', '[ -]')}\\b`, 'i').test(text)) values.push(state);
        for (const value of values) if (declared.has(String(value).toLowerCase())) observed.add(String(value).toLowerCase());
      }
      return [...observed].sort();
    };
    const states = new Set(data.profile.states || []);
    const strategy = data.profile.authority === 'learner-secret' ? 'credential'
      : states.has('playing') || [...states].some(state => ['running','queued','stopped','succeeded','reset'].includes(state)) ? 'action'
      : [...states].some(state => ['selected','current','complete'].includes(state)) ? 'selection'
      : 'passive';
    let beforeStates = stateWords();
    const entryDeadline = Date.now() + 5000;
    while (Date.now() < entryDeadline && !beforeStates.some(state => ENTRY_STATES.has(state))) {
      await new Promise(resolve => setTimeout(resolve, 50));
      beforeStates = stateWords();
    }
    if (!beforeStates.some(state => ENTRY_STATES.has(state))) {
      failLocal(`${data.id}: declared entry state is not observable (${beforeStates.join(',') || 'none'})`);
    }
    if (beforeStates.includes('blocked')) {
      return { strategy:'blocked', beforeStates, afterStates:beforeStates };
    }
    if (strategy === 'passive') return { strategy, beforeStates, afterStates:beforeStates };
    if (strategy === 'credential') {
      const input = root.querySelector('input:not([type="hidden"]),textarea');
      if (!input || input.disabled || input.readOnly) failLocal(`${data.id}: credential state has no editable control`);
      input.focus(); input.value = 'invalid-browser-audit-value';
      input.dispatchEvent(new Event('input', { bubbles:true }));
      input.dispatchEvent(new Event('change', { bubbles:true }));
    }
    const controls = [...root.querySelectorAll('button:not([disabled]):not([hidden]),[role="button"]:not([aria-disabled="true"]):not([hidden]),a[href],summary')]
      .filter(node => node.getClientRects().length > 0);
    const localControls = controls.filter(node => !node.matches('a[href]'));
    const semanticAction = localControls.find(node => ACTION_WORDS.test(`${node.getAttribute('aria-label') || ''} ${node.textContent || ''}`))
      || controls.find(node => ACTION_WORDS.test(`${node.getAttribute('aria-label') || ''} ${node.textContent || ''}`));
    const commandInputs = [...root.querySelectorAll('input:not([type="hidden"]):not([disabled]),textarea:not([disabled])')]
      .filter(node => !node.readOnly && node.getClientRects().length > 0);
    const commandInput = commandInputs[0];
    const explicitAction = localControls.find(node => {
      const identity = `${node.getAttribute('type') || ''} ${node.id || ''} ${node.className || ''} ${node.getAttribute('aria-label') || ''}`;
      return /\b(submit|send|run|execute|connect|test|play)\b/i.test(identity);
    });
    const keyboardSubmit = strategy === 'action' && commandInputs.length === 1 && !explicitAction && commandInput;
    const action = keyboardSubmit || explicitAction || semanticAction || localControls[0] || controls[0];
    if (!action) failLocal(`${data.id}: dynamic form factor has no enabled action`);
    const setupControls = semanticAction && strategy === 'action'
      ? [...root.querySelectorAll('input:not([type="hidden"]):not([disabled]),textarea:not([disabled]),select:not([disabled])')]
      : [];
    for (const control of setupControls) {
      if (control.readOnly || ['checkbox','radio','file'].includes(control.type)) continue;
      if (control instanceof HTMLSelectElement) {
        if (!control.value) {
          const option = [...control.options].find(item => !item.disabled && item.value);
          if (option) control.value = option.value;
        }
      } else if (!control.value) {
        const descriptor = `${control.type || ''} ${control.name || ''} ${control.id || ''} ${control.className || ''} ${control.placeholder || ''} ${control.getAttribute('aria-label') || ''}`;
        control.value = /\b(url|endpoint|host)\b/i.test(descriptor)
          ? 'http://127.0.0.1:9'
          : 'invalid-browser-audit-value';
      }
      control.dispatchEvent(new Event('input', { bubbles:true }));
      control.dispatchEvent(new Event('change', { bubbles:true }));
    }
    const requiredControls = [...root.querySelectorAll('input[required],textarea[required],select[required]')];
    for (const control of requiredControls) {
      if (control instanceof HTMLSelectElement) {
        if (!control.value) {
          const option = [...control.options].find(item => !item.disabled && item.value);
          if (option) control.value = option.value;
        }
      } else if (!control.value) {
        control.value = 'browser interface audit';
      }
      control.dispatchEvent(new Event('input', { bubbles:true }));
      control.dispatchEvent(new Event('change', { bubbles:true }));
    }
    const before = root.innerHTML;
    let changed = false;
    const observer = new MutationObserver(() => { changed = true; });
    observer.observe(root, { subtree:true, childList:true, characterData:true, attributes:true });
    if (keyboardSubmit) {
      action.value = 'browser interface audit';
      action.dispatchEvent(new Event('input', { bubbles:true }));
      action.dispatchEvent(new KeyboardEvent('keydown', { key:'Enter', code:'Enter', bubbles:true, cancelable:true }));
    } else {
      if (action.matches('a[href]')) action.addEventListener('click', event => event.preventDefault(), { once:true, capture:true });
      if (typeof action.click === 'function') action.click();
      else action.dispatchEvent(new MouseEvent('click', { bubbles:true, cancelable:true }));
    }
    const deadline = Date.now() + 5000;
    let afterStates = stateWords();
    while (Date.now() < deadline && !changed && afterStates.join() === beforeStates.join()) {
      await new Promise(resolve => setTimeout(resolve, 50));
      afterStates = stateWords();
    }
    observer.disconnect();
    const transitioned = changed || root.innerHTML !== before || afterStates.join() !== beforeStates.join();
    if (!transitioned) {
      const actionLabel = `${action.tagName} ${action.getAttribute('aria-label') || ''} ${action.textContent || ''}`.trim().replace(/\s+/g, ' ').slice(0, 160);
      failLocal(`${data.id}: action produced no observable state transition (${actionLabel})`);
    }
    if (!afterStates.length) failLocal(`${data.id}: action left no declared state observable`);
    return { strategy, beforeStates, afterStates };
  }, { profile, id });
}
async function activateDeferred(locator, mountedSelector, id) {
  return locator.evaluate(async (root, data) => {
    const controls = [...root.querySelectorAll('button:not([disabled]),[role="button"]:not([aria-disabled="true"])')];
    const trigger = controls.find(node => /\brun\b/i.test(`${node.getAttribute('aria-label') || ''} ${node.textContent || ''}`));
    if (!trigger) throw new Error(`${data.id}: deferred interface trigger has no enabled Run action`);
    const before = root.innerHTML;
    let changed = false;
    const observer = new MutationObserver(() => { changed = true; });
    observer.observe(root, { subtree:true, childList:true, characterData:true, attributes:true });
    trigger.click();
    const deadline = Date.now() + 5000;
    while (Date.now() < deadline && !changed && root.innerHTML === before) {
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    observer.disconnect();
    if (!changed && root.innerHTML === before) throw new Error(`${data.id}: deferred trigger produced no observable state transition`);
  }, { mountedSelector, id });
}
async function mountProbe(page, target, probe, id) {
  await target.evaluate(async (root, data) => {
    const moduleUrl = new URL(data.probe.module, location.href).href;
    const runtime = await import(moduleUrl);
    const render = runtime[data.probe.export];
    if (typeof render !== 'function') throw new Error(`${data.id}: mount_probe export is not callable`);
    if (data.probe.mode === 'mount-target') {
      await render(root, structuredClone(data.probe.argument));
    } else {
      const view = await render(structuredClone(data.probe.argument));
      if (!(view instanceof Node)) throw new Error(`${data.id}: mount_probe did not return a DOM node`);
      const output = root.querySelector('.cell-output') || root;
      const hidden = output.closest('[hidden]');
      if (hidden) hidden.hidden = false;
      output.append(view);
    }
  }, { probe, id });
}

(async () => {
  await listen();
  const browser = await chromium.launch({ headless:true, executablePath:process.env.CHROME_BIN || undefined, args:['--no-sandbox'] });
  const context = await browser.newContext({ serviceWorkers:'block', acceptDownloads:false, viewport:{ width:1440, height:900 } });
  await context.route('**/*', route => {
    try { if (new URL(route.request().url()).origin === origin) return route.continue(); } catch (_) {}
    return route.abort('blockedbyclient');
  });
  if (typeof context.routeWebSocket === 'function') await context.routeWebSocket('**/*', socket => socket.close());
  const grouped = new Map();
  for (const instance of inventory.instances) {
    if (!grouped.has(instance.entry)) grouped.set(instance.entry, []);
    grouped.get(instance.entry).push(instance);
  }
  const checked = [];
  const exercised = new Set();
  const page = await context.newPage();
  // One tab follows the learner journey. This preserves intentionally tab-scoped sessionStorage
  // while each navigation still creates a fresh document and remains under the egress-denied context.
  await page.addInitScript(() => {
    if (window.top !== window) return;
    window.__dliTopErrors = [];
    addEventListener('error', event => window.__dliTopErrors.push(String(event.error?.message || event.message || 'error')));
    addEventListener('unhandledrejection', event => window.__dliTopErrors.push(String(event.reason?.message || event.reason || 'rejection')));
  });
  for (const [entry, instances] of grouped) {
    const localFailures = [];
    let exercisedOnEntry = false;
    const onRequestFailed = request => {
      try { if (new URL(request.url()).origin === origin) localFailures.push(request.url()); } catch (_) {}
    };
    page.on('requestfailed', onRequestFailed);
    const target = new URL(entry, origin + '/');
    await page.goto(target.href, { waitUntil:'domcontentloaded', timeout:Math.min(timeout, 60000) });
    await page.evaluate(() => document.querySelectorAll('details').forEach(item => { item.open = true; }));
    for (const instance of instances) {
      const mounted = page.locator(instance.selector).first();
      const target = instance.trigger_selector ? page.locator(instance.trigger_selector).first() : mounted;
      await waitAttached(target, 30000, instance, 'trigger');
      const effectiveDeferred = !!instance.trigger_selector || (instance.deferred && (
        !!instance.mount_probe || await page.locator('.rc-card,.cf-wrap,.xblock').count() > 0
      ));
      const result = await target.evaluate((root, data) => {
        const detail = root.closest('details'); if (detail) detail.open = true;
        const content = root.childElementCount + (root.textContent || '').trim().length;
        const interactive = root.querySelectorAll('button,input,select,textarea,a[href],summary,[role="button"],[tabindex]').length;
        const inputs = root.querySelectorAll('input,select,textarea,.CodeMirror').length;
        const buttons = root.querySelectorAll('button,[role="button"],summary').length;
        const links = root.querySelectorAll('a[href]').length;
        let semanticError = '';
        if (content) {
          if (data.authority !== 'none' && interactive === 0) semanticError = 'authority-bearing interface has no operable control';
          if (data.factor === 'editable-code-cell' && (!inputs || !buttons)) semanticError = 'editable code cell lacks editor or run control';
          if (data.factor === 'credential-controls' && (!inputs || !buttons)) semanticError = 'credential controls lack input or action';
          if (data.factor === 'video-supplement' && (!root.querySelector('video') || !buttons)) semanticError = 'video supplement lacks preview and player';
          if (['course-navigation','course-progress'].includes(data.factor) && !links) semanticError = 'navigation has no destination';
        }
        return {
          count: document.querySelectorAll(data.targetSelector).length,
          content,
          semanticError,
        };
      }, {
        selector:instance.selector, targetSelector:instance.trigger_selector || instance.selector,
        factor:effectiveDeferred ? (instance.trigger_selector ? 'editable-code-cell' : '') : instance.form_factor,
        authority:effectiveDeferred && !instance.trigger_selector ? 'none' : inventory.form_factors[instance.form_factor].authority,
      });
      if (result.count !== 1 || (!effectiveDeferred && !result.content) || result.semanticError) {
        fail(`${instance.id}: count=${result.count} content=${result.content} ${result.semanticError}`);
      }
      if (!exercised.has(instance.form_factor)) {
        if (exercisedOnEntry) {
          await page.reload({ waitUntil:'domcontentloaded', timeout:Math.min(timeout, 60000) });
          await page.evaluate(() => document.querySelectorAll('details').forEach(item => { item.open = true; }));
          await waitAttached(target, 30000, instance, 'fresh exercise target');
        }
        if (instance.trigger_selector) {
          await activateDeferred(target, instance.selector, instance.id);
          try {
            await mounted.waitFor({ state:'attached', timeout:5000 });
          } catch (error) {
            if (!instance.mount_probe) {
              fail(`${instance.id}: deferred interface did not mount at ${instance.entry} ${instance.selector}: ${error.message}`);
            }
            await mountProbe(page, target, instance.mount_probe, instance.id);
            await waitAttached(mounted, 30000, instance, 'mount probe');
          }
        } else if (effectiveDeferred && instance.mount_probe) {
          await mountProbe(page, mounted, instance.mount_probe, instance.id);
        }
        try {
          await exercise(mounted, inventory.form_factors[instance.form_factor], instance.id);
        } catch (error) {
          const diagnostic = await page.evaluate(selector => ({
            errors: window.__dliTopErrors || [],
            html: String(document.querySelector(selector)?.innerHTML || '').slice(0, 1200),
          }), instance.selector);
          fail(`${instance.id}: exercise failed at ${instance.entry} ${instance.selector}: ${error.message}; diagnostic=${JSON.stringify(diagnostic)}`);
        }
        exercised.add(instance.form_factor);
        exercisedOnEntry = true;
      }
      checked.push(instance.id);
    }
    for (const theme of ['light','dark']) {
      const palette = await page.evaluate(value => {
        document.documentElement.dataset.theme = value;
        const style = getComputedStyle(document.body);
        return { color:style.color, background:style.backgroundColor };
      }, theme);
      if (!palette.color || !palette.background || palette.color === palette.background || palette.background === 'rgba(0, 0, 0, 0)') {
        fail(`${entry}: unreadable ${theme} page palette ${JSON.stringify(palette)}`);
      }
    }
    const errors = await page.evaluate(() => window.__dliTopErrors || []);
    if (errors.length || localFailures.length) fail(`${entry}: browser errors=${JSON.stringify(errors)} local failures=${JSON.stringify(localFailures)}`);
    page.off('requestfailed', onRequestFailed);
  }
  if (checked.length !== inventory.instances.length || new Set(checked).size !== checked.length) fail('expanded interface coverage is incomplete or repeated');
  const factors = Object.keys(inventory.form_factors);
  if (exercised.size !== factors.length || factors.some(factor => !exercised.has(factor))) fail('not every discovered form factor was exercised');
  console.log(JSON.stringify({ ok:true, instances:checked.length, routes:grouped.size, form_factors:factors.length, exercised:exercised.size }));
  await page.close();
  await context.close(); await browser.close(); server.close();
})().catch(error => { try { server.close(); } catch (_) {} console.error(error?.stack || String(error)); process.exit(1); });
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-root", required=True)
    parser.add_argument("--timeout-ms", type=int, default=600_000)
    return parser.parse_args()


def run(site: Path, timeout_ms: int) -> int:
    site = site.resolve()
    source_site = site if (site / "web").is_dir() else site / "validated-source"
    findings, instances = audit_inventory(source_site)
    if findings:
        print(f"interface inventory browser audit: FAIL inventory={len(findings)}")
        return 1
    factors: dict[str, dict[str, str]] = {}
    for contract in sorted((source_site / "web").glob("*/interface-inventory.json")):
        data = json.loads(contract.read_text(encoding="utf-8"))
        for name, profile in data.get("form_factors", {}).items():
            previous = factors.get(name)
            if previous is not None:
                if previous.get("authority") != profile.get("authority"):
                    print(f"interface inventory browser audit: FAIL conflicting authority for form factor={name}")
                    return 1
                previous["states"] = sorted(set(previous.get("states", [])) | set(profile.get("states", [])))
            else:
                factors[name] = profile
    with tempfile.TemporaryDirectory(prefix="dli-interface-browser-") as directory:
        temp = Path(directory)
        report = temp / "interfaces.json"
        script = temp / "audit.js"
        report.write_text(json.dumps({"instances": instances, "form_factors": factors}), encoding="utf-8")
        script.write_text(RUNTIME, encoding="utf-8")
        try:
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                site_port = reservation.getsockname()[1]
            resolved = environment(
                SITE_ROOT=source_site, INTERFACE_REPORT=report,
                AUDIT_TIMEOUT_MS=str(timeout_ms), SITE_PORT=str(site_port), SOURCE_MODE="1",
            )
            browser_env = {
                key: resolved[key] for key in (
                    "PATH", "HOME", "TMPDIR", "NODE_PATH", "CHROME_BIN", "COURSE_ROOT",
                    "SITE_ROOT", "INTERFACE_REPORT", "AUDIT_TIMEOUT_MS", "SITE_PORT",
                    "SOURCE_MODE",
                ) if resolved.get(key)
            }
            proc = run_node(
                script,
                env=browser_env,
                timeout=timeout_ms / 1000 + 60,
            )
        except BrowserRuntimeError as exc:
            print(f"interface inventory browser audit: FAIL BrowserRuntimeError: {exc}")
            return 1
        except subprocess.TimeoutExpired:
            print(f"interface inventory browser audit: FAIL timeout after {timeout_ms} ms")
            return 1
    if proc.returncode:
        print("interface inventory browser audit: FAIL")
        print(proc.stdout.rstrip())
        return proc.returncode
    print(proc.stdout.rstrip())
    print("interface inventory browser audit: OK")
    return 0


def main() -> int:
    args = parse_args()
    return run(Path(args.site_root), args.timeout_ms)


if __name__ == "__main__":
    raise SystemExit(main())
