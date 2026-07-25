#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render every HTML file with Playwright and fail on theme or SKILL UI drift.

HTML discovery is exhaustive under the selected artifact root, which must be inside the served
deployment root. Every selected page enters the desktop/narrow and dark/light matrix; SKILL pages
additionally receive their navigation, explorer, and export checks. There is no file-level opt-in
or exemption list.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[2]
MINIMUM_FULL_ARTIFACT_TIMEOUT_SECONDS = 600
sys.path.insert(0, str(ROOT / "scripts" / "skills"))
import skill_audit

def discover_html(site: Path, scan_root: Optional[Path] = None) -> list[str]:
    """Return every HTML path below one artifact root, relative to its served deployment."""
    site = site.resolve()
    scan = (scan_root or site).resolve()
    scan.relative_to(site)
    return sorted(path.relative_to(site).as_posix() for path in scan.rglob("*.html"))

RUNTIME_JS = r"""
const http = require('http');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const root = process.env.SITE_ROOT || '/site';
const htmlFiles = JSON.parse(fs.readFileSync(process.env.HTML_FILES || '/tmp/html-files.json', 'utf8'));
const pageTimeoutMs = Number(process.env.PAGE_TIMEOUT_MS || '120000');
let port = 0;
const mime = {
  '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8',
  '.mjs':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8',
  '.json':'application/json; charset=utf-8', '.svg':'image/svg+xml',
  '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.ico':'image/x-icon',
  '.md':'text/markdown; charset=utf-8', '.txt':'text/plain; charset=utf-8',
};

function safeJoin(urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]).replace(/^\/+/, '');
  const output = path.resolve(root, clean);
  const resolvedRoot = path.resolve(root);
  if (output !== resolvedRoot && !output.startsWith(resolvedRoot + path.sep)) throw new Error('path escape');
  return output;
}

const server = http.createServer((request, response) => {
  let file;
  try { file = safeJoin(request.url || '/'); }
  catch (_) { response.writeHead(403); response.end('forbidden'); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  fs.readFile(file, (error, data) => {
    if (error) { response.writeHead(404); response.end('not found'); return; }
    response.writeHead(200, { 'content-type': mime[path.extname(file).toLowerCase()] || 'application/octet-stream' });
    response.end(request.method === 'HEAD' ? undefined : data);
  });
});

// Minimal local echo server: one masked text frame in, one text frame out. This proves the
// browser worker uses a real WebSocket without adding a test package or external dependency.
server.on('upgrade', (request, socket) => {
  if (request.url !== '/pyodide-ws-test' || !request.headers['sec-websocket-key']) {
    socket.destroy();
    return;
  }
  const accept = crypto.createHash('sha1')
    .update(request.headers['sec-websocket-key'] + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11')
    .digest('base64');
  socket.write([
    'HTTP/1.1 101 Switching Protocols',
    'Upgrade: websocket',
    'Connection: Upgrade',
    `Sec-WebSocket-Accept: ${accept}`,
    '', '',
  ].join('\r\n'));
  socket.once('data', frame => {
    let length = frame[1] & 0x7f;
    let offset = 2;
    if (length === 126) { length = frame.readUInt16BE(offset); offset += 2; }
    const masked = (frame[1] & 0x80) !== 0;
    const mask = masked ? frame.subarray(offset, offset += 4) : null;
    const payload = Buffer.from(frame.subarray(offset, offset + length));
    if (mask) for (let index = 0; index < payload.length; index++) payload[index] ^= mask[index % 4];
    const header = payload.length < 126
      ? Buffer.from([0x81, payload.length])
      : Buffer.from([0x81, 126, payload.length >> 8, payload.length & 0xff]);
    socket.write(Buffer.concat([header, payload]));
  });
});

async function inspect(browser, file) {
  const startedAt = performance.now();
  let isSkill = /(?:^|\/)SKILL\.html$/.test(file);
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  let pageTimedOut = false;
  const pageTimer = setTimeout(() => {
    pageTimedOut = true;
    page.close().catch(() => {});
  }, pageTimeoutMs);
  const ownedOrigin = `http://127.0.0.1:${port}`;
  const successfulOwned = new Set();
  let closing = false;
  page.on('pageerror', error => errors.push(`pageerror: ${error.message || String(error)}`));
  page.on('response', response => {
    const url = new URL(response.url());
    if (url.origin === ownedOrigin) {
      if (response.status() < 400) successfulOwned.add(url.href);
      else errors.push(`internal response HTTP ${response.status()}: ${url.pathname}`);
    }
  });
  page.on('requestfailed', request => {
    const url = new URL(request.url());
    if (url.origin === ownedOrigin && !closing && !successfulOwned.has(url.href)
        && request.headers()['x-static-artifact-audit'] !== '1') {
      errors.push(`internal request failed: ${url.pathname}: ${request.failure()?.errorText || 'unknown error'}`);
    }
  });
  page.on('console', message => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (/^Failed to load resource:/.test(text)) {
      const locationUrl = message.location().url;
      try { if (locationUrl && new URL(locationUrl).origin !== ownedOrigin) return; }
      catch (_) {}
    }
    errors.push(`console: ${text}`);
  });
  if (file.endsWith('scripts/pyodide/SKILL.html')) {
    await page.route('https://integrate.api.nvidia.com/v1/chat/completions', async route => {
      const cors = {
        'access-control-allow-origin': '*',
        'access-control-allow-headers': 'authorization,content-type,x-billing-invoke-origin',
        'access-control-allow-methods': 'POST,OPTIONS',
      };
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status:204, headers:cors, body:'' });
        return;
      }
      const body = [
        'data: {"choices":[{"delta":{"reasoning_content":"checked "}}]}',
        '',
        'data: {"choices":[{"delta":{"content":"streamed from the NVIDIA route"},"finish_reason":"stop"}]}',
        '',
        'data: [DONE]',
        '',
      ].join('\n');
      await route.fulfill({ status:200, headers:{...cors,'content-type':'text/event-stream'}, body });
    });
  }
  try {
    const response = await page.goto(`http://127.0.0.1:${port}/${file}`, { waitUntil:'domcontentloaded', timeout:30000 });
    // Generated aliases use document-declared redirects. Playwright resolves the initial
    // document before that navigation begins, so wait on the redirect contract itself before
    // evaluating the final page. This applies to every discovered HTML file without naming or
    // exempting an alias path.
    await page.waitForFunction(() =>
      !document.querySelector('meta[http-equiv="refresh" i]'),
      null,
      { timeout:10000 }
    );
    await page.waitForLoadState('domcontentloaded');
    await page.evaluate(() => new Promise(resolve =>
      requestAnimationFrame(() => requestAnimationFrame(resolve))
    ));
    isSkill = await page.evaluate(() =>
      /(?:^|\/)SKILL\.html$/.test(location.pathname) || !!document.getElementById('skill-meta')
    );
    if (isSkill) await page.waitForFunction(() => {
      let meta;
      try { meta = JSON.parse(document.getElementById('skill-meta')?.textContent || '{}'); }
      catch (_) { return true; }
      return (meta.exports || []).every(item => {
        const mount = document.getElementById(item.preview_mount);
        return mount && (mount.dataset.exportReady === '1' || mount.dataset.exportError);
      }) && (() => {
        const evidence = document.getElementById('sbom-evidence-preview');
        return !evidence || evidence.dataset.sbomEvidenceReady === '1' || evidence.dataset.sbomEvidenceError;
      })();
    }, null, { timeout:10000 }).catch(() => {});
    if (!response || !response.ok()) errors.push(`document HTTP ${response && response.status()}`);
    await page.waitForFunction(() => Array.from(document.querySelectorAll('[data-svg-src]'))
      .every(host => host.querySelector('svg')), null, { timeout:10000 }).catch(() => {});
    if (file.endsWith('scripts/pyodide/SKILL.html')) {
      try {
        await page.waitForFunction(() => document.querySelector('#pyodide-playground')?.dataset.runtimeMounted === 'true');
        await page.locator('[data-example-id="compute"] .CodeMirror textarea').focus();
        await page.keyboard.press('Shift+Enter');
        const keyboardAdvanced = await page.waitForFunction(() => {
          const passed = document.querySelector('[data-cell-status="compute"]')?.textContent === 'Passed';
          const focusedCell = document.activeElement?.closest?.('[data-example-id]')?.dataset.exampleId;
          return passed && focusedCell === 'output-channels';
        }, null, { timeout:60000 }).then(() => true).catch(() => false);
        const runtimeContract = await page.evaluate(async () => {
          const waitFor = async (predicate, timeoutMs=60000) => {
            const started = Date.now();
            while (Date.now() - started < timeoutMs) {
              if (predicate()) return true;
              await new Promise(resolve => setTimeout(resolve, 50));
            }
            return false;
          };
          let workerSyntax = 'ok';
          try { new Function(globalThis.__pyodideWorkerSource); }
          catch (error) { workerSyntax = error.message || String(error); }
          const count = document.querySelectorAll('[data-example-id]').length;
          const editorCount = document.querySelectorAll('.CodeMirror').length;
          const syntaxTokens = document.querySelectorAll('.CodeMirror .cm-keyword, .CodeMirror .cm-string, .CodeMirror .cm-builtin').length;
          const originalTheme = document.documentElement.getAttribute('data-theme');
          const editorBackgrounds = mode => {
            document.documentElement.setAttribute('data-theme', mode);
            return [...document.querySelectorAll('.CodeMirror')].map(node => getComputedStyle(node).backgroundColor);
          };
          const editorDark = editorBackgrounds('dark');
          const editorLight = editorBackgrounds('light');
          if (originalTheme === null) document.documentElement.removeAttribute('data-theme');
          else document.documentElement.setAttribute('data-theme', originalTheme);
          const playground = globalThis.__pyodidePlayground;
          playground.replEditor.setValue('shared_value = 41\nshared_value');
          const replFirst = await playground.runRepl();
          playground.replEditor.setValue('shared_value += 1\nshared_value');
          const replSecond = await playground.runRepl();
          playground.replEditor.setValue('display_markdown("**REPL rich output** with `visible code`")');
          const replRich = await playground.runRepl();
          playground.replEditor.setValue(`display_html('<img src="https://invalid.example/pixel"><script>globalThis.__pyodideUnsafe = true</script><meta http-equiv="refresh" content="0;url=https://invalid.example"><iframe src="https://invalid.example"></iframe><svg onload="globalThis.__pyodideUnsafe = true"><circle></circle></svg><a href="javascript:globalThis.__pyodideUnsafe=true" onclick="globalThis.__pyodideUnsafe=true">unsafe link</a><strong>safe HTML</strong>')`);
          await playground.runRepl();
          document.querySelector('[data-python-helpers]').open = true;
          document.querySelector('[data-helper-row="display_json"]').click();
          const helperEditor = playground.helperEditors.get('display_json');
          const helperSourceVisible = !!helperEditor && helperEditor.getValue().includes('def display_json');
          helperEditor.setValue(`def display_json(value, indent=2):\n    display_code("OVERRIDE:" + str(value), language="text")`);
          const helperApplied = await playground.applyHelper('display_json');
          playground.replEditor.setValue('display_json({"preview": True})');
          const helperReply = await playground.runRepl();
          await playground.revertHelper('display_json');
          const replOutput = document.querySelector('[data-repl-transcript]').textContent;
          const replRichStrong = document.querySelector('[data-repl-transcript] .py-rich-output strong')?.textContent || '';
          const channel = value => {
            const match = String(value).match(/[\d.]+/g) || [];
            return match.slice(0, 3).map(Number);
          };
          const luminance = value => channel(value).map(item => {
            const normalized = item / 255;
            return normalized <= 0.03928 ? normalized / 12.92 : Math.pow((normalized + 0.055) / 1.055, 2.4);
          }).reduce((sum, item, index) => sum + item * [0.2126, 0.7152, 0.0722][index], 0);
          const contrast = (foreground, background) => {
            const lighter = Math.max(luminance(foreground), luminance(background));
            const darker = Math.min(luminance(foreground), luminance(background));
            return (lighter + 0.05) / (darker + 0.05);
          };
          const richContrast = mode => {
            document.documentElement.setAttribute('data-theme', mode);
            const root = document.querySelector('[data-repl-transcript] .py-rich-output');
            const prose = root?.querySelector('p');
            const inlineCode = root?.querySelector('code');
            return {
              prose: root && prose ? contrast(getComputedStyle(prose).color, getComputedStyle(root).backgroundColor) : 0,
              code: inlineCode ? contrast(getComputedStyle(inlineCode).color, getComputedStyle(inlineCode).backgroundColor) : 0,
            };
          };
          const richContrastDark = richContrast('dark');
          const richContrastLight = richContrast('light');
          if (originalTheme === null) document.documentElement.removeAttribute('data-theme');
          else document.documentElement.setAttribute('data-theme', originalTheme);
          const unsafeRichOutput = !!document.querySelector(
            '[data-repl-transcript] .py-rich-output script,'
            + '[data-repl-transcript] .py-rich-output img,'
            + '[data-repl-transcript] .py-rich-output meta,'
            + '[data-repl-transcript] .py-rich-output iframe,'
            + '[data-repl-transcript] .py-rich-output svg,'
            + '[data-repl-transcript] .py-rich-output [onload],'
            + '[data-repl-transcript] .py-rich-output [onclick],'
            + '[data-repl-transcript] .py-rich-output a[href^="javascript:" i]'
          ) || !!globalThis.__pyodideUnsafe;
          const passed = workerSyntax === 'ok' ? await Promise.race([
            playground.runAll(),
            new Promise(resolve => setTimeout(() => resolve(-1), 90000)),
          ]) : 0;
          const statuses = [...document.querySelectorAll('[data-cell-status]')].map(node => node.textContent);
          const notebookDisplay = document.querySelector('[data-output-for="compute"] [data-stream="display"]');
          const backgroundReply = playground.cells.get('background-job')?.lastReply;
          const artifactReply = playground.cells.get('artifact-generation')?.lastReply;
          const artifactCard = document.querySelector('[data-output-for="artifact-generation"] [data-artifact-filename]');
          const artifactDownload = artifactCard?.querySelector('a[download]');
          let artifactContent = null;
          if (artifactDownload?.href) {
            try { artifactContent = JSON.parse(await (await fetch(artifactDownload.href)).text()); }
            catch (_) { artifactContent = null; }
          }
          const artifactPreviewTokens = artifactCard?.querySelectorAll('.hljs-attr, .hljs-string, .hljs-literal').length || 0;
          const chatInput = document.querySelector('[data-example-input="chat-app"]');
          const chatButton = document.querySelector('[data-run-example="chat-app"]');
          const chatStatus = document.querySelector('[data-cell-status="chat-app"]');
          const sendChat = async message => {
            chatInput.value = message;
            chatButton.click();
            const finished = await waitFor(() => chatStatus.textContent === 'Passed');
            return finished ? playground.cells.get('chat-app').lastReply?.value : null;
          };
          const firstChat = await sendChat('How do I stop a long Python task?');
          const secondChat = await sendChat('And how do I see an error?');
          const chatMessages = document.querySelectorAll('[data-chat-transcript="chat-app"] .py-chat-message').length;
          document.querySelector('[data-live-model-enabled]').checked = true;
          document.querySelector('[data-nvidia-api-key]').value = 'nvapi-validator-placeholder';
          const liveChat = await sendChat('Please stream this test.');
          document.querySelector('[data-live-model-enabled]').checked = false;
          document.querySelector('[data-websocket-url]').value = `ws://127.0.0.1:${location.port}/pyodide-ws-test`;
          const websocketReply = await playground.cells.get('portable-request').editor
            ? await (async () => {
                document.querySelector('[data-run-example="portable-request"]').click();
                const ready = await waitFor(() => document.querySelector('[data-cell-status="portable-request"]').textContent !== 'Running…');
                return ready ? playground.cells.get('portable-request').lastReply : null;
              })()
            : null;
          const richMimes = [...document.querySelectorAll('.py-rich-output')].map(node => node.dataset.mime);
          const syntaxMimes = [...document.querySelectorAll('.py-syntax-output')].map(node => node.dataset.mime);
          const richMarkdownStrong = document.querySelector('[data-output-for="output-channels"] .py-rich-output[data-mime="text/markdown"] strong')?.textContent || '';
          const prettyText = document.querySelector('[data-output-for="compute"] [data-value-for="compute"]')?.textContent || '';
          const jsonOutput = document.querySelector('[data-output-for="compute"] .py-syntax-output[data-mime="application/json"]');
          const codeOutput = document.querySelector('[data-output-for="output-channels"] .py-syntax-output[data-mime="text/x-code"]');
          const jsonSyntaxTokens = jsonOutput?.querySelectorAll('.hljs-attr, .hljs-string, .hljs-number, .hljs-literal').length || 0;
          const codeSyntaxTokens = codeOutput?.querySelectorAll('.hljs-keyword, .hljs-title, .hljs-string, .hljs-built_in').length || 0;
          const syntaxWhiteSpace = jsonOutput ? getComputedStyle(jsonOutput).whiteSpace : '';
          const syntaxWidth = jsonOutput?.getBoundingClientRect().width || 0;
          const outputWidth = document.querySelector('[data-output-for="compute"]')?.getBoundingClientRect().width || 0;
          const tableOutput = !!document.querySelector('[data-output-for="messages"] .py-rich-output table');
          const leakedKey = document.querySelector('#pyodide-playground').textContent.includes('nvapi-validator-placeholder');
          document.querySelector('[data-action="error"]').click();
          const tracebackFinished = await waitFor(() => document.querySelector('[data-python-status]').textContent.includes('traceback surfaced'));
          const traceback = document.querySelector('[data-python-diagnostic]').textContent;
          const errorHighlight = !!document.querySelector('[data-python-repl] .py-code-error-line')
            && document.querySelector('[data-python-status]').textContent.includes('line 3');
          document.querySelector('[data-action="reset"]').click();
          const resetReady = [...document.querySelectorAll('[data-cell-status]')].every(node => node.textContent === 'Ready')
            && [...document.querySelectorAll('[data-output-for]')].every(node => node.dataset.state === 'empty'
              && node.querySelectorAll(':scope > *:not(.wb-cell-empty)').length === 0)
            && !document.querySelector('[data-repl-transcript]').textContent.trim();
          return {
            workerSyntax, count, editorCount, syntaxTokens, editorDark, editorLight, replFirst, replSecond, replRich, replOutput, replRichStrong,
            richContrastDark, richContrastLight, unsafeRichOutput,
            passed, statuses, notebookDisplay: notebookDisplay?.textContent || '', backgroundReply, artifactReply,
            artifactFilename: artifactCard?.dataset.artifactFilename || '', artifactDownloadName: artifactDownload?.download || '',
            artifactContent, artifactPreviewTokens, firstChat,
            secondChat, chatMessages, liveChat, websocketReply, richMimes, syntaxMimes, richMarkdownStrong, prettyText,
            jsonSyntaxTokens, codeSyntaxTokens, syntaxWhiteSpace, syntaxWidth, outputWidth, tableOutput,
            helperSourceVisible, helperApplied, helperReply, leakedKey,
            tracebackFinished, traceback, errorHighlight, resetReady,
          };
        });
        if (!keyboardAdvanced) errors.push('Pyodide Shift+Enter did not run the cell and focus the next editor');
        if (runtimeContract.workerSyntax !== 'ok') errors.push(`Pyodide generated worker is invalid: ${runtimeContract.workerSyntax}`);
        if (runtimeContract.editorCount !== runtimeContract.count + 1 || runtimeContract.syntaxTokens < runtimeContract.count) {
          errors.push('Pyodide notebook editors are missing live syntax highlighting');
        }
        if (new Set(runtimeContract.editorDark).size !== 1 || new Set(runtimeContract.editorLight).size !== 1
            || runtimeContract.editorDark[0] === runtimeContract.editorLight[0]
            || runtimeContract.editorDark[0] === 'rgb(255, 255, 255)') {
          errors.push('Pyodide CodeMirror surfaces are not consistently theme-aware');
        }
        if (runtimeContract.replFirst?.display !== '41' || runtimeContract.replSecond?.display !== '42'
            || runtimeContract.replSecond?.execution_count !== runtimeContract.replFirst?.execution_count + 1
            || runtimeContract.replRichStrong !== 'REPL rich output'
            || !runtimeContract.replOutput.includes('Out[')) {
          errors.push('Pyodide scratch REPL did not preserve namespace or execution order');
        }
        if (runtimeContract.unsafeRichOutput) errors.push('Pyodide rich output sanitizer admitted executable or network-active HTML');
        if (Math.min(runtimeContract.richContrastDark?.prose || 0, runtimeContract.richContrastDark?.code || 0,
            runtimeContract.richContrastLight?.prose || 0, runtimeContract.richContrastLight?.code || 0) < 4.5) {
          errors.push(`Pyodide Markdown output does not maintain readable contrast in both themes (${JSON.stringify({dark:runtimeContract.richContrastDark,light:runtimeContract.richContrastLight})})`);
        }
        if (runtimeContract.count < 8 || runtimeContract.passed !== runtimeContract.count || runtimeContract.statuses.some(item => item !== 'Passed')) {
          errors.push(`Pyodide progressive cells failed: ${runtimeContract.passed}/${runtimeContract.count}`);
        }
        if (!runtimeContract.notebookDisplay.startsWith('Out[')) errors.push('Pyodide final expression did not render as notebook output');
        if (runtimeContract.backgroundReply?.value?.registration?.name !== 'prepare-summary'
            || runtimeContract.artifactReply?.value?.job_state !== 'completed') {
          errors.push(`Pyodide background process did not register and complete across cells (${JSON.stringify(runtimeContract.backgroundReply)})`);
        }
        if (runtimeContract.artifactFilename !== 'browser-python-report.json'
            || runtimeContract.artifactDownloadName !== 'browser-python-report.json'
            || runtimeContract.artifactContent?.background_job?.state !== 'completed'
            || runtimeContract.artifactPreviewTokens < 3) {
          errors.push(`Pyodide artifact did not preserve a highlighted preview and exact downloadable bytes (${JSON.stringify(runtimeContract.artifactContent)})`);
        }
        if (runtimeContract.firstChat?.turns !== 4 || runtimeContract.secondChat?.turns !== 6 || runtimeContract.chatMessages !== 6) {
          errors.push('Pyodide chat did not preserve repeated user input');
        }
        if (runtimeContract.liveChat?.transport !== 'http-sse'
            || !runtimeContract.liveChat?.assistant?.includes('streamed from the NVIDIA route')) {
          errors.push(`Pyodide build.nvidia.com path did not consume streamed SSE tokens (${JSON.stringify(runtimeContract.liveChat)})`);
        }
        if (runtimeContract.websocketReply?.value?.websocket?.transport !== 'websocket'
            || runtimeContract.websocketReply?.value?.websocket?.message !== 'hello from browser Python') {
          errors.push(`Pyodide WebSocket round trip did not connect, send, and receive (${JSON.stringify(runtimeContract.websocketReply)})`);
        }
        if (!runtimeContract.richMimes.includes('text/markdown') || !runtimeContract.richMimes.includes('text/html')
            || !runtimeContract.syntaxMimes.includes('application/json') || !runtimeContract.syntaxMimes.includes('text/x-code')
            || runtimeContract.richMarkdownStrong !== 'Progress:' || !runtimeContract.prettyText.includes('\n')
            || runtimeContract.jsonSyntaxTokens < 3 || runtimeContract.codeSyntaxTokens < 2 || !runtimeContract.tableOutput) {
          errors.push(`Pyodide display pipeline did not render highlighted JSON/code, Markdown, HTML, and tables (rich=${runtimeContract.richMimes.join(',')}; syntax=${runtimeContract.syntaxMimes.join(',')}; jsonTokens=${runtimeContract.jsonSyntaxTokens}; codeTokens=${runtimeContract.codeSyntaxTokens})`);
        }
        if (runtimeContract.syntaxWhiteSpace !== 'pre' || runtimeContract.syntaxWidth < runtimeContract.outputWidth * 0.75) {
          errors.push(`Pyodide syntax output is hard-wrapped or artificially narrow (white-space=${runtimeContract.syntaxWhiteSpace}; width=${runtimeContract.syntaxWidth}/${runtimeContract.outputWidth})`);
        }
        if (!runtimeContract.helperSourceVisible || !runtimeContract.helperApplied?.ok
            || runtimeContract.helperReply?.displays?.[0]?.type !== 'text/x-code'
            || !runtimeContract.helperReply.displays[0].data.startsWith('OVERRIDE:')) {
          errors.push(`Pyodide helper menu did not preview, edit, and apply the live helper source (${JSON.stringify(runtimeContract.helperReply)})`);
        }
        if (runtimeContract.leakedKey) errors.push('Pyodide rendered a model credential into page output');
        if (!runtimeContract.tracebackFinished || !runtimeContract.traceback.includes('IndexError')) {
          errors.push('Pyodide intentional error did not render its traceback');
        }
        if (!runtimeContract.errorHighlight) errors.push('Pyodide traceback did not highlight the failing source line');
        if (!runtimeContract.resetReady) errors.push('Pyodide Reset did not clear cell state');
      } catch (error) {
        errors.push(`Pyodide browser contract: ${error.message || String(error)}`);
      }
    }
    const state = await page.evaluate(async ({ isSkill }) => {
      const parse = id => { try { return JSON.parse(document.getElementById(id)?.textContent || ''); } catch (_) { return null; } };
      const config = document.getElementById('explorer-config');
      const meta = parse('skill-meta');
      const sbomEvidence = document.getElementById('sbom-evidence-preview');
      const exports = (meta?.exports || []).map(item => {
        const mount = document.getElementById(item.preview_mount);
        const categoryGroup = mount?.querySelector('.filter-choice-group');
        const categoryBoxes = Array.from(categoryGroup?.querySelectorAll('input[type="checkbox"]') || []);
        const before = mount?.querySelectorAll('tbody tr').length || 0;
        const toggle = categoryBoxes.find(input => !input.checked) || categoryBoxes[categoryBoxes.length - 1];
        if (toggle) { toggle.checked = !toggle.checked; toggle.dispatchEvent(new Event('change', {bubbles:true})); }
        const after = mount?.querySelectorAll('tbody tr').length || 0;
        const sortButtons = Array.from(mount?.querySelectorAll('th button[data-sort-index]') || []);
        const sortDirections = sortButtons.map(button => {
          button.click();
          const ascending = button.closest('th')?.getAttribute('aria-sort') === 'ascending';
          button.click();
          const descending = button.closest('th')?.getAttribute('aria-sort') === 'descending';
          return ascending && descending;
        });
        return {
          id:item.id,
          present:!!mount,
          ready:mount?.dataset.exportReady === '1',
          error:mount?.dataset.exportError || '',
          rows:mount?.querySelectorAll('tbody tr').length || 0,
          choiceGroups:mount?.querySelectorAll('.filter-choice-group').length || 0,
          choiceCount:mount?.querySelectorAll('.filter-choice-group input[type="checkbox"]').length || 0,
          headerCount:mount?.querySelectorAll('thead th').length || 0,
          sortButtons:sortButtons.length,
          multiChanged:before !== after,
          allSortDirections:sortDirections.length > 0 && sortDirections.every(Boolean),
        };
      });
      const parseColor = value => {
        const match = String(value || '').match(/rgba?\(([^)]+)\)/i);
        if (!match) return null;
        const parts = match[1].split(',').map(Number);
        return { r:parts[0], g:parts[1], b:parts[2], a:parts.length > 3 ? parts[3] : 1 };
      };
      const composite = (top, bottom) => {
        const alpha = top.a + bottom.a * (1 - top.a);
        if (!alpha) return {r:255,g:255,b:255,a:1};
        return {
          r:(top.r * top.a + bottom.r * bottom.a * (1 - top.a)) / alpha,
          g:(top.g * top.a + bottom.g * bottom.a * (1 - top.a)) / alpha,
          b:(top.b * top.a + bottom.b * bottom.a * (1 - top.a)) / alpha,
          a:alpha,
        };
      };
      const background = node => {
        const layers = [];
        for (let current=node; current; current=current.parentElement) {
          const color = parseColor(getComputedStyle(current).backgroundColor);
          if (color && color.a) layers.push(color);
        }
        let result = {r:255,g:255,b:255,a:1};
        for (let index=layers.length - 1; index >= 0; index--) result = composite(layers[index], result);
        return result;
      };
      const luminance = color => {
        const channel = value => {
          const normalized = value / 255;
          return normalized <= .03928 ? normalized / 12.92 : Math.pow((normalized + .055) / 1.055, 2.4);
        };
        return .2126 * channel(color.r) + .7152 * channel(color.g) + .0722 * channel(color.b);
      };
      const ratio = (foreground, backdrop) => {
        const a = luminance(foreground), b = luminance(backdrop);
        return (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
      };
      const label = node => {
        const classes = Array.from(node.classList || []).slice(0, 2).join('.');
        const text = String(node.innerText || node.value || node.getAttribute?.('aria-label') || '').trim().replace(/\s+/g,' ').slice(0,48);
        return `${node.tagName.toLowerCase()}${node.id ? '#' + node.id : ''}${classes ? '.' + classes : ''}${text ? ' “' + text + '”' : ''}`;
      };
      const visible = node => {
        const style = getComputedStyle(node), box = node.getBoundingClientRect();
        return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) > .02 && box.width > 0 && box.height > 0;
      };
      const hasOwnText = node => Array.from(node.childNodes).some(child => child.nodeType === Node.TEXT_NODE && child.textContent.trim())
        || /^(INPUT|SELECT|TEXTAREA)$/.test(node.tagName);
      const auditStyle = document.createElement('style');
      auditStyle.textContent = 'html[data-theme] body *,html[data-theme] body *::before,html[data-theme] body *::after{transition:none!important;animation:none!important}';
      document.head.appendChild(auditStyle);
      const themeSnapshot = mode => {
        document.documentElement.setAttribute('data-theme', mode);
        void document.documentElement.offsetWidth;
        document.getAnimations().forEach(animation => { try { animation.finish(); } catch (_) {} });
        void document.documentElement.offsetWidth;
        const candidates = Array.from(document.querySelectorAll(
          'h1,h2,h3,h4,h5,h6,p,li,a,b,strong,em,small,code,pre,span,label,summary,button,th,td,input,select,textarea'
        ));
        const contrast = [];
        for (let index = 0; index < candidates.length; index++) {
          const node = candidates[index];
          if (!visible(node) || !hasOwnText(node) || node.closest('[aria-hidden="true"]')) continue;
          const style = getComputedStyle(node), foreground = parseColor(style.color);
          if (!foreground || foreground.a < .5) continue;
          const score = ratio(foreground, background(node));
          const size = parseFloat(style.fontSize) || 16;
          const weight = parseInt(style.fontWeight, 10) || 400;
          const threshold = size >= 24 || (size >= 18.66 && weight >= 700) ? 3 : 4.5;
          contrast.push({index,label:label(node),ratio:Number(score.toFixed(2)),threshold});
        }
        const viewportWidth = document.documentElement.clientWidth;
        const overflowElements = Array.from(document.body.querySelectorAll('*')).flatMap(node => {
          if (!visible(node)) return [];
          const box = node.getBoundingClientRect();
          if (box.right <= viewportWidth + 2 && box.left >= -2) return [];
          for (let parent=node.parentElement; parent && parent !== document.body; parent=parent.parentElement) {
            const parentBox = parent.getBoundingClientRect();
            const overflow = getComputedStyle(parent).overflowX;
            if (/auto|scroll|hidden|clip/.test(overflow) && parentBox.left >= -2 && parentBox.right <= viewportWidth + 2) return [];
          }
          return [`${label(node)} (left ${Math.round(box.left)}px; right ${Math.round(box.right)}px; width ${Math.round(box.width)}px)`];
        }).slice(0,5);
        const figures = Array.from(document.querySelectorAll('[data-svg-src],img[data-figure-mode="fixed-white"][src$=".svg"]'))
          .filter(node => visible(node))
          .map((host, index) => {
            const svg = host.matches('svg') ? host : host.querySelector('svg');
            const painted = svg ? [svg, ...svg.querySelectorAll('*')].slice(0,120).map(node => {
              const style = getComputedStyle(node);
              return [style.fill, style.stroke, style.color, style.backgroundColor, style.filter].join('|');
            }).join(';') : '';
            const surfaceNode = host.closest('.paper-preview') || host;
            return {
              key:`${host.getAttribute('data-svg-src') || host.getAttribute('src') || 'inline'}#${index}`,
              fixedWhite:host.getAttribute('data-figure-mode') === 'fixed-white',
              surface:getComputedStyle(surfaceNode).backgroundColor,
              painted,
            };
          });
        return {
          mode,
          viewportWidth,
          documentWidth:document.documentElement.scrollWidth,
          overflowElements,
          bodyBackground:getComputedStyle(document.body).backgroundColor,
          surfaceBackground:getComputedStyle(document.querySelector('.skill-static,main,body')).backgroundColor,
          contrast,
          figures,
        };
      };
      const contrastFailures = snapshot => snapshot.contrast
        .filter(item => item.ratio + .01 < item.threshold)
        .map(item => `${item.label} (${snapshot.mode} ${item.ratio.toFixed(2)}:1; requires ${item.threshold.toFixed(1)}:1)`)
        .slice(0,20);
      const figureThemeFailures = (dark, light) => dark.figures.flatMap((figure, index) => {
        const peer = light.figures[index];
        if (!peer || peer.key !== figure.key) return [`${figure.key} changed identity across themes`];
        if (figure.fixedWhite) {
          const darkSurface = parseColor(figure.surface), lightSurface = parseColor(peer.surface);
          if (!darkSurface || !lightSurface || luminance(darkSurface) < .85 || luminance(lightSurface) < .85) {
            return [`${figure.key} is classified fixed-white but lacks a white paper surface`];
          }
          return [];
        }
        return figure.painted && figure.painted !== peer.painted
          ? [] : [`${figure.key} has the same rendered SVG palette in dark and light mode`];
      });
      window.__nemoclawThemeSnapshot = themeSnapshot;
      window.__nemoclawContrastFailures = contrastFailures;
      window.__nemoclawFigureThemeFailures = figureThemeFailures;
      const originalTheme = document.documentElement.getAttribute('data-theme');
      const dark = themeSnapshot('dark');
      const light = themeSnapshot('light');
      if (originalTheme === null) document.documentElement.removeAttribute('data-theme');
      else document.documentElement.setAttribute('data-theme', originalTheme);
      const themeButton = document.querySelector('button[aria-label="Toggle dark or light theme"]');
      const storedTheme = (() => { try { return localStorage.getItem('theme'); } catch (_) { return null; } })();
      document.documentElement.setAttribute('data-theme', 'dark');
      const buttonDark = getComputedStyle(document.body).backgroundColor;
      themeButton?.click();
      const buttonLight = getComputedStyle(document.body).backgroundColor;
      const themeControl = {
        count:document.querySelectorAll('button[aria-label="Toggle dark or light theme"]').length,
        visible:!!themeButton && visible(themeButton),
        switched:document.documentElement.getAttribute('data-theme') === 'light',
        paletteChanged:buttonDark !== buttonLight,
      };
      if (originalTheme === null) document.documentElement.removeAttribute('data-theme');
      else document.documentElement.setAttribute('data-theme', originalTheme);
      try {
        if (storedTheme === null) localStorage.removeItem('theme');
        else localStorage.setItem('theme', storedTheme);
      } catch (_) {}
      const evidenceAnchors = Array.from(document.querySelectorAll('a[data-evidence-link]'));
      const invalidEvidenceLinks = evidenceAnchors.filter(anchor => {
        const raw = anchor.getAttribute('href') || '';
        return !raw || raw === '#' || /^javascript:/i.test(raw);
      }).map(anchor => anchor.textContent.trim());
      const unsafeNavigationLinks = Array.from(document.querySelectorAll('a[href]')).filter(anchor => {
        try {
          const url = new URL(anchor.getAttribute('href') || '', location.href);
          return !['http:', 'https:', 'file:'].includes(url.protocol);
        } catch (_) {
          return true;
        }
      }).map(anchor => anchor.getAttribute('href') || '').slice(0,20);
      const urlAttributes = ['href', 'src', 'poster', 'action', 'data-svg-src'];
      const localUrls = new Set();
      document.querySelectorAll('*').forEach(node => {
        urlAttributes.forEach(attribute => {
          if (node.hasAttribute(attribute)) localUrls.add(node.getAttribute(attribute));
        });
        String(node.getAttribute('srcset') || '').split(',').forEach(candidate => {
          const value = candidate.trim().split(/\s+/)[0];
          if (value) localUrls.add(value);
        });
      });
      const internalUrlChecks = await Promise.all(Array.from(localUrls).map(async raw => {
        try {
          if (!raw) return 'empty internal URL';
          const url = new URL(raw, location.href);
          if (url.origin !== location.origin) return '';
          const response = await fetch(url.href, {method:'HEAD', headers:{'x-static-artifact-audit':'1'}});
          return response.ok ? '' : `${raw} HTTP ${response.status}`;
        } catch (error) {
          return `${raw} ${error.message || String(error)}`;
        }
      }));
      const interactiveSelector = 'a[href],button,input:not([type="hidden"]),select,textarea,summary,[role="button"],[role="link"]';
      const interactiveNesting = Array.from(document.querySelectorAll(interactiveSelector)).flatMap(outer =>
        Array.from(outer.querySelectorAll(interactiveSelector)).map(inner => ({
          outer:`${outer.tagName.toLowerCase()}${outer.id ? `#${outer.id}` : ''}.${String(outer.className || '').trim().replace(/\s+/g, '.')}`,
          inner:`${inner.tagName.toLowerCase()}${inner.id ? `#${inner.id}` : ''}.${String(inner.className || '').trim().replace(/\s+/g, '.')}`,
          text:(inner.textContent || inner.getAttribute('aria-label') || '').trim().slice(0,80),
        }))
      ).slice(0,12);
      return {
        isSkill,
        meta: !isSkill || !!meta,
        config: !config || !!parse('explorer-config'),
        navigationHeader: !!document.querySelector('header[data-skill-header="1"] nav'),
        navigationLinks: document.querySelectorAll('header[data-skill-header="1"] nav a[href]').length,
        visibleNavigationRegions: Array.from(document.querySelectorAll('header[data-skill-header="1"], .sx-topbar')).filter(node => getComputedStyle(node).display !== 'none').length,
        duplicateExplorerHeading: !!document.querySelector('.skill-static') && !!document.querySelector('#explorer .sx-head'),
        themeControl,
        themes:{dark,light},
        themeChanged:dark.bodyBackground !== light.bodyBackground || dark.surfaceBackground !== light.surfaceBackground,
        contrastFailures:[...contrastFailures(dark),...contrastFailures(light)],
        figureThemeFailures:figureThemeFailures(dark,light),
        visibleText: (document.body?.innerText || '').trim().length,
        explorer: !!config,
        mounted: !!document.querySelector('.sx-topbar') && !!document.querySelector('.sx-main'),
        gone: document.querySelectorAll('.sx-dot.gone').length,
        exports,
        deadInternalUrls:internalUrlChecks.filter(Boolean),
        interactiveNesting,
        unsafeNavigationLinks,
        sbomEvidence: sbomEvidence ? {
          ready:sbomEvidence.dataset.sbomEvidenceReady === '1',
          error:sbomEvidence.dataset.sbomEvidenceError || '',
          cards:sbomEvidence.querySelectorAll('.sbom-card').length,
          expectedCards:Number(sbomEvidence.dataset.sbomExpectedCards ?? NaN),
          deliveryStates:sbomEvidence.querySelectorAll('.sbom-card .sbom-state[data-distribution]').length,
          evidenceCards:Array.from(sbomEvidence.querySelectorAll('.sbom-card')).filter(card => card.querySelector('details')).length,
          componentRows:sbomEvidence.querySelectorAll('.sbom-components tbody tr').length,
          subjectRows:sbomEvidence.querySelectorAll('tr[data-sbom-subject="1"]').length,
          expectedSubjectRows:Number(sbomEvidence.dataset.sbomExpectedSubjects ?? NaN),
          subjectHints:sbomEvidence.querySelectorAll('tr[data-sbom-subject="1"] [data-license-hint="1"]').length,
          subjectLinks:Array.from(sbomEvidence.querySelectorAll('tr[data-sbom-subject="1"]')).map(row => row.querySelectorAll('a[data-evidence-link]').length),
          ciLinksState:sbomEvidence.querySelector('[data-ci-links-state]')?.dataset.ciLinksState || '',
          ciArtifactLinks:sbomEvidence.querySelectorAll('a[data-evidence-link="ci-artifact"]').length,
          ciComponentRows:sbomEvidence.querySelectorAll('[data-ci-component-preview="1"] tbody tr').length,
          clarificationRows:sbomEvidence.querySelectorAll('[data-license-clarification="1"] tbody tr').length,
          clarificationCount:Number(sbomEvidence.querySelector('[data-sbom-fact="unresolved"] strong')?.textContent ?? NaN),
          invalidEvidenceLinks,
          text:sbomEvidence.innerText || '',
          visibleTechnicalTerms:['CycloneDX','SHA-256','artifact path'].filter(term =>
            (sbomEvidence.innerText || '').includes(term)
          ),
        } : null,
      };
    }, { isSkill });
    await page.setViewportSize({ width:390, height:844 });
    await page.waitForTimeout(50);
    const narrow = await page.evaluate(() => {
      const originalTheme = document.documentElement.getAttribute('data-theme');
      const dark = window.__nemoclawThemeSnapshot('dark');
      const light = window.__nemoclawThemeSnapshot('light');
      if (originalTheme === null) document.documentElement.removeAttribute('data-theme');
      else document.documentElement.setAttribute('data-theme', originalTheme);
      return {
        themes:{dark,light},
        themeChanged:dark.bodyBackground !== light.bodyBackground || dark.surfaceBackground !== light.surfaceBackground,
        contrastFailures:[...window.__nemoclawContrastFailures(dark),...window.__nemoclawContrastFailures(light)],
        figureThemeFailures:window.__nemoclawFigureThemeFailures(dark,light),
        themeButtonVisible:Array.from(document.querySelectorAll('button[aria-label="Toggle dark or light theme"]')).some(node => {
          const style=getComputedStyle(node), box=node.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
        }),
        overflows:dark.documentWidth > dark.viewportWidth + 2 || light.documentWidth > light.viewportWidth + 2,
      };
    });
    if (state.isSkill && !state.meta) errors.push('skill-meta did not parse');
    if (state.isSkill && !state.config) errors.push('explorer-config did not parse');
    if (state.isSkill && (!state.navigationHeader || state.navigationLinks < 2)) errors.push('semantic skill navigation header is incomplete');
    if (state.isSkill && state.visibleNavigationRegions !== 1) errors.push(`renderer produced ${state.visibleNavigationRegions} visible navigation headers`);
    if (state.isSkill && state.duplicateExplorerHeading) errors.push('renderer repeated the static SKILL heading');
    if (state.isSkill && (state.themeControl.count !== 1 || !state.themeControl.visible
        || !state.themeControl.switched || !state.themeControl.paletteChanged || !narrow.themeButtonVisible)) {
      errors.push(`SKILL theme control is missing or ineffective (${JSON.stringify({desktop:state.themeControl,narrowVisible:narrow.themeButtonVisible})})`);
    }
    if (!state.themeChanged || !narrow.themeChanged) errors.push('dark/light palettes do not change the page at every viewport');
    if (state.contrastFailures.length) errors.push(`desktop contrast: ${state.contrastFailures.join('; ')}`);
    if (narrow.contrastFailures.length) errors.push(`narrow contrast: ${narrow.contrastFailures.join('; ')}`);
    if (state.figureThemeFailures.length) errors.push(`desktop figure theme: ${state.figureThemeFailures.join('; ')}`);
    if (narrow.figureThemeFailures.length) errors.push(`narrow figure theme: ${narrow.figureThemeFailures.join('; ')}`);
    if (narrow.overflows) {
      const offenders = narrow.themes.dark.overflowElements.length ? narrow.themes.dark.overflowElements : narrow.themes.light.overflowElements;
      errors.push(`narrow layout overflows 390px viewport (dark ${narrow.themes.dark.documentWidth}px; light ${narrow.themes.light.documentWidth}px): ${offenders.join('; ') || 'unattributed root overflow'}`);
    }
    if (!state.visibleText) errors.push('renderer produced no visible text');
    if (state.deadInternalUrls.length) errors.push(`internal URLs failed: ${state.deadInternalUrls.join('; ')}`);
    if (state.interactiveNesting.length) errors.push(`nested interactive controls: ${JSON.stringify(state.interactiveNesting)}`);
    if (state.unsafeNavigationLinks.length) errors.push(`unsafe navigation URLs: ${state.unsafeNavigationLinks.join('; ')}`);
    if (state.isSkill && state.explorer && !state.mounted) errors.push('shared explorer did not mount');
    if (state.isSkill && state.gone) errors.push(`${state.gone} configured file(s) did not load`);
    if (state.isSkill) state.exports.forEach(item => {
      if (!item.present) errors.push(`export ${item.id} preview mount is missing`);
      else if (item.error) errors.push(`export ${item.id} preview failed: ${item.error}`);
      else if (!item.ready) errors.push(`export ${item.id} preview did not become ready`);
      else if (!item.rows) errors.push(`export ${item.id} preview rendered no component rows`);
      else if (item.choiceGroups < 3 || item.choiceCount < 3) errors.push(`export ${item.id} lacks multi-select filter groups`);
      else if (!item.multiChanged) errors.push(`export ${item.id} multi-select filters did not change the visible rows`);
      else if (item.sortButtons !== item.headerCount || !item.allSortDirections) errors.push(`export ${item.id} does not toggle every column between ascending and descending`);
    });
    if (state.sbomEvidence) {
      if (state.sbomEvidence.error) errors.push(`SBOM evidence preview failed: ${state.sbomEvidence.error}`);
      else if (!state.sbomEvidence.ready) errors.push('SBOM evidence preview did not become ready');
      else if (!Number.isInteger(state.sbomEvidence.expectedCards)
          || state.sbomEvidence.cards !== state.sbomEvidence.expectedCards) {
        errors.push(`SBOM evidence rendered ${state.sbomEvidence.cards} of ${state.sbomEvidence.expectedCards} declared records`);
      }
      else if (!state.sbomEvidence.componentRows) errors.push('linked SBOM rendered no component licenses');
      else if (state.sbomEvidence.subjectRows !== state.sbomEvidence.expectedSubjectRows
          || state.sbomEvidence.subjectHints !== state.sbomEvidence.expectedSubjectRows
          || state.sbomEvidence.subjectLinks.some(count => count < 3)) {
        errors.push('conditional SBOM rows lack declaration, upstream, or license-hint evidence');
      } else if (state.sbomEvidence.invalidEvidenceLinks.length) {
        errors.push(`SBOM evidence contains unusable links: ${state.sbomEvidence.invalidEvidenceLinks.join('; ')}`);
      } else if (state.sbomEvidence.ciLinksState === 'available' && state.sbomEvidence.ciArtifactLinks < 3) {
        errors.push('available CI evidence does not link all three generated artifacts');
      } else if (state.sbomEvidence.ciLinksState === 'available' && !state.sbomEvidence.ciComponentRows) {
        errors.push('available CI evidence does not render the linked SBOM component licenses');
      } else if (state.sbomEvidence.ciLinksState === 'available'
          && !Number.isInteger(state.sbomEvidence.clarificationCount)) {
        errors.push('available CI evidence does not state how many packages need license clarification');
      } else if (state.sbomEvidence.ciLinksState === 'available'
          && state.sbomEvidence.clarificationRows !== state.sbomEvidence.clarificationCount) {
        errors.push(`available CI evidence reports ${state.sbomEvidence.clarificationCount} package(s) needing license clarification but renders ${state.sbomEvidence.clarificationRows}`);
      } else if (!['available', 'incomplete', 'unavailable'].includes(state.sbomEvidence.ciLinksState)) {
        errors.push('CI artifact evidence lacks an explicit availability state');
      } else if (state.sbomEvidence.deliveryStates !== state.sbomEvidence.expectedCards
          || state.sbomEvidence.evidenceCards !== state.sbomEvidence.expectedCards) {
        errors.push('software review does not answer learner delivery before exposing audit detail');
      } else if (state.sbomEvidence.ciLinksState === 'available'
          && (!state.sbomEvidence.text.includes('packages checked')
            || !state.sbomEvidence.text.includes('need package-by-package review'))) {
        errors.push('available package scan does not summarize useful review outcomes');
      } else if (state.sbomEvidence.visibleTechnicalTerms.length) {
        errors.push(`software review exposes implementation jargon before disclosure: ${state.sbomEvidence.visibleTechnicalTerms.join(', ')}`);
      }
    }
  } catch (error) {
    errors.push(`navigation: ${error.message || String(error)}`);
  }
  clearTimeout(pageTimer);
  if (pageTimedOut) errors.push(`document audit exceeded ${pageTimeoutMs}ms`);
  closing = true;
  await page.close().catch(() => {});
  return { file, durationMs: Math.round(performance.now() - startedAt), errors: [...new Set(errors)] };
}

(async () => {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      server.off('error', reject);
      port = server.address().port;
      resolve();
    });
  });
  const browser = await chromium.launch({
    headless:true,
    executablePath:process.env.CHROME_BIN || undefined,
  });
  const findings = [];
  let cursor = 0;
  let completed = 0;
  let nextProgressPercent = 10;
  async function worker(workerId) {
    while (cursor < htmlFiles.length) {
      const file = htmlFiles[cursor++];
      console.error(JSON.stringify({ event:'renderer-page-start', file, worker:workerId }));
      const started = performance.now();
      const result = await inspect(browser, file);
      console.error(JSON.stringify({
        event:'renderer-page-finish',
        file,
        worker:workerId,
        durationMs:result.durationMs,
        findings:result.errors.length,
      }));
      if (result.errors.length) findings.push(result);
      completed += 1;
      const durationMs = Math.round(performance.now() - started);
      const percent = Math.floor(completed * 100 / htmlFiles.length);
      if (durationMs >= 10000 || percent >= nextProgressPercent || completed === htmlFiles.length) {
        console.error(JSON.stringify({
          event:'renderer-progress',
          completed,
          total:htmlFiles.length,
          percent,
          file,
          durationMs,
        }));
        while (nextProgressPercent <= percent) nextProgressPercent += 10;
      }
    }
  }
  await Promise.all(Array.from({ length:4 }, (_, index) => worker(index + 1)));
  await browser.close();
  server.close();
  console.log(JSON.stringify({ files:htmlFiles.length, findings }, null, 2));
  if (findings.length) process.exit(1);
})().catch(error => {
  try { server.close(); } catch (_) {}
  console.error(error.stack || String(error));
  process.exit(1);
});
"""


def _terminate_process(process: subprocess.Popen[str]) -> None:
    """Stop the browser process tree after the whole-run deadline."""
    if process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        process.wait()


def stream_command(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
    write: Callable[[str], object] = sys.stdout.write,
) -> tuple[int, bool, list[str]]:
    """Stream renderer evidence and retain active documents if the run stalls."""
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=os.name == "posix",
    )
    assert process.stdout is not None
    active: set[str] = set()
    active_lock = threading.Lock()

    def pump() -> None:
        for line in process.stdout:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {}
            if isinstance(event, dict):
                file = event.get("file")
                if isinstance(file, str):
                    with active_lock:
                        if event.get("event") == "renderer-page-start":
                            active.add(file)
                        elif event.get("event") == "renderer-page-finish":
                            active.discard(file)
            write(line)

    reader = threading.Thread(target=pump, name="renderer-output", daemon=True)
    reader.start()
    timed_out = False
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process(process)
        returncode = process.returncode if process.returncode is not None else 1
    reader.join(timeout=5)
    process.stdout.close()
    with active_lock:
        stalled = sorted(active)
    return returncode, timed_out, stalled


def run(args: argparse.Namespace) -> int:
    site = Path(args.site_root).resolve()
    if not site.is_dir():
        print(f"skill_renderer_runtime_audit: FAIL\n  - site root missing: {site}")
        return 1
    scan_root = Path(args.scan_root).resolve() if args.scan_root else site
    try:
        scan_root.relative_to(site)
    except ValueError:
        print(f"skill_renderer_runtime_audit: FAIL\n  - scan root escapes served tree: {scan_root}")
        return 1
    if not scan_root.is_dir():
        print(f"skill_renderer_runtime_audit: FAIL\n  - scan root missing: {scan_root}")
        return 1
    # Every HTML file below the artifact boundary is included. Serving may use a parent deployment
    # root so intentional links to a separately validated sibling artifact resolve realistically.
    files = discover_html(site, scan_root)
    if not files:
        print(f"skill_renderer_runtime_audit: FAIL\n  - no HTML files under {site}")
        return 1
    if args.timeout_seconds <= 0 or args.page_timeout_seconds <= 0:
        print("skill_renderer_runtime_audit: FAIL\n  - timeout values must be positive")
        return 1
    with tempfile.TemporaryDirectory(prefix="skill-renderer-audit-") as temp:
        temp_path = Path(temp)
        script = temp_path / "audit.js"
        manifest = temp_path / "html-files.json"
        script.write_text(RUNTIME_JS, encoding="utf-8")
        manifest.write_text(json.dumps(files), encoding="utf-8")
        command = [os.environ.get("NODE_BIN") or "node", str(script)]
        try:
            environment = os.environ.copy()
            environment.update({
                "NODE_PATH": args.node_path,
                "CHROME_BIN": "" if args.chrome_bin == "auto" else args.chrome_bin,
                "SITE_ROOT": str(site),
                "HTML_FILES": str(manifest),
                "PAGE_TIMEOUT_MS": str(args.page_timeout_seconds * 1000),
            })
            returncode, timed_out, stalled = stream_command(
                command,
                cwd=ROOT,
                environment=environment,
                timeout_seconds=args.timeout_seconds,
            )
        except FileNotFoundError as exc:
            print(
                "skill_renderer_runtime_audit: FAIL\n"
                f"  - {exc}\n"
                f"  - attempted {len(files)} exhaustive HTML render(s) with a "
                f"{args.timeout_seconds}-second process budget"
            )
            return 1
        if timed_out:
            active = ", ".join(stalled) if stalled else "(no document reported active)"
            print(
                "skill_renderer_runtime_audit: FAIL\n"
                f"  - renderer exceeded {args.timeout_seconds}s; active documents: {active}"
            )
            return 1
    print("skill_renderer_runtime_audit: " + ("OK" if returncode == 0 else "FAIL"))
    return returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", default=str(ROOT))
    parser.add_argument("--scan-root", help="artifact subtree to discover exhaustively; must be inside --site-root")
    parser.add_argument("--node-path", default=os.environ.get("NODE_PATH") or str(ROOT / "scripts/runtime/node_modules"))
    parser.add_argument("--chrome-bin", default=os.environ.get("CHROME_BIN") or "auto")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=MINIMUM_FULL_ARTIFACT_TIMEOUT_SECONDS,
        help="whole-audit process budget; CI must not set less than the full-artifact minimum",
    )
    parser.add_argument(
        "--page-timeout-seconds",
        type=int,
        default=120,
        help="maximum time for one document before it is closed and reported",
    )
    return parser


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
