#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Exercise prerequisite, run, stop, reset, error, and disclosure states in Chromium."""
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

RUNTIME_JS = r"""
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright-core');

const root = process.env.SITE_ROOT || '/site';
const port = 4203;
const mime = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.json':'application/json' };
const fixture = `<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="/nemoclaw/styles/_style.css"></head><body data-learning-view>
<div class="topbar"><a class="logo" href="#">Fixture</a><div class="spacer"></div><span class="key-pill">No API key</span></div><main>
  <div id="journey-map"></div>
  <details id="learning-applied" class="learning-block" open data-learning-id="fixture-applied" data-learning-tier="applied"><summary><span class="learning-scope">Applied · Build</span><span class="learning-question">Inspect the implementation detail?</span></summary><div class="learning-block-body"><h2>Applied detail</h2><p>Applied implementation detail stays available in the source and can be revealed without changing the canonical page.</p></div></details>
  <details id="learning-deep" class="learning-block" open data-learning-id="fixture-deep" data-learning-tier="deep"><summary><span class="learning-scope">Deep · Sources</span><span class="learning-question">Read the deeper reference?</span></summary><div class="learning-block-body"><h2>Deep detail</h2><p>Deep reference detail stays available in the source while guided and applied views keep the main path short.</p></div></details>
  <details id="learning-reference" class="references learning-block" open data-learning-always-open data-learning-id="fixture-references" data-learning-tier="deep"><summary><span class="learning-scope">Deep · Sources</span><span class="learning-question">Read the primary paper sources?</span></summary><div class="learning-block-body"><h2>Primary sources</h2><p>Paper references stay visible on first load while the native disclosure still lets a learner collapse this list.</p></div></details>
  <div id="run-cell"></div><div id="canvas"></div><div id="chat"></div><div id="console"></div>
</main><script type="module">
import { mountRunCell, mountCanvasFlow, mountChatUI, mountConsole } from "/nemoclaw/scripts/_shared.js";
window.fixtureReady = false;
window.runApi = mountRunCell("#run-cell", {
  openCode: true,
  label: "fixture run cell",
  intro: "Read the outcome first. Open code only to change the wait.",
  code: \`helpers.log("process started");\nawait helpers.delay(5000);\nreturn { finished: true };\`,
});
window.canvasApi = mountCanvasFlow("#canvas", {
  label: "fixture flow", intro: "A cancellable wait followed by a visible result.", edges:[{from:"wait",to:"finish"}], nodes: [{ id:"wait", title:"Wait", x:0, y:0,
    code: \`await new Promise((resolve, reject) => {\n  const timer = setTimeout(resolve, 5000);\n  helpers.signal.addEventListener("abort", () => { clearTimeout(timer); reject(new DOMException("stopped", "AbortError")); }, { once: true });\n});\nhelpers.log("finished");\` },
    { id:"finish", title:"Result", x:1, y:0, code: \`return "done";\` }],
});
window.chatApi = mountChatUI("#chat", {
  disabled: () => !window.fixtureReady,
  disabledMsg: "Complete fixture setup.",
  greeting: "Fixture chat",
  respond: async (_text, ctx) => { await new Promise((resolve, reject) => { const timer = setTimeout(resolve, 5000); ctx.signal.addEventListener("abort", () => { clearTimeout(timer); reject(new DOMException("stopped", "AbortError")); }, { once:true }); }); },
});
window.consoleApi = mountConsole("#console", {
  greeting: "Fixture console",
  onSubmit: async (_line, _con, ctx) => { await new Promise((resolve, reject) => { const timer = setTimeout(resolve, 5000); ctx.signal.addEventListener("abort", () => { clearTimeout(timer); reject(new DOMException("stopped", "AbortError")); }, { once:true }); }); },
});
window.fixtureMounted = true;
</script></body></html>`;
const supportFixture = `<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="/nemoclaw/styles/_style.css"></head><body>
<div class="topbar"><a class="logo" href="#">Support tool</a><div class="spacer"></div><span class="key-pill">No API key</span></div><main><h1>Support tool</h1></main>
<script type="module">import "/nemoclaw/scripts/_shared.js"; window.supportMounted=true;</script></body></html>`;
const localizedFixture = `<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><link rel="stylesheet" href="/nemoclaw/styles/_style.css"></head><body data-learning-view>
<div class="topbar"><a class="logo" href="#">Curso</a><div class="spacer"></div><span class="key-pill">Sem chave</span></div><main><details id="localized-detail" open><summary>Detalhe</summary><p>Conteúdo localizado.</p></details></main>
<script type="module">import "/nemoclaw/scripts/_shared.js"; window.localizedMounted=true;</script></body></html>`;
const historyFixture = `<!doctype html><html lang="en"><head><meta charset="utf-8"><link rel="stylesheet" href="/nemoclaw/styles/_style.css"></head><body><main><div id="history-chat"></div></main>
<script type="module">
import { mountChatUI } from "/nemoclaw/scripts/_shared.js";
import { loadCourseAssistantStore, saveCourseAssistantStore } from "/nemoclaw/scripts/_course_assistant.js";
const store = loadCourseAssistantStore();
const session = store.sessions.find(item => item.id === store.activeId) || store.sessions[0];
const persist = (history, meta={}) => { const current = store.sessions.find(item => item.id === store.activeId) || store.sessions[0]; current.history = history; if (Object.hasOwn(meta, "activity")) current.activity = meta.activity; current.updatedAt = Date.now(); saveCourseAssistantStore(store); };
mountChatUI("#history-chat", { memory:true, initialHistory:session.history, initialActivity:session.activity, onHistoryChange:persist, onTurnSnapshot:persist,
  respond:async(text,ctx) => { if (text.includes("slow")) { ctx.view.token("partial reply before navigation"); await new Promise(resolve => setTimeout(resolve, 5000)); } ctx.view.token("completed reply: " + text); } });
window.historyMounted = true;
</script></body></html>`;

function safeJoin(urlPath) {
  const clean = decodeURIComponent(urlPath.split('?')[0]).replace(/^\/+/, '');
  const out = path.resolve(root, clean);
  if (!out.startsWith(path.resolve(root))) throw new Error('path escape');
  return out;
}
const server = http.createServer((req, res) => {
  if ((req.url || '').split('?')[0] === '/fixture.html') { res.writeHead(200, { 'content-type':'text/html; charset=utf-8' }); res.end(fixture); return; }
  if ((req.url || '').split('?')[0] === '/support.html') { res.writeHead(200, { 'content-type':'text/html; charset=utf-8' }); res.end(supportFixture); return; }
  if ((req.url || '').split('?')[0] === '/localized.html') { res.writeHead(200, { 'content-type':'text/html; charset=utf-8' }); res.end(localizedFixture); return; }
  if ((req.url || '').split('?')[0] === '/history.html') { res.writeHead(200, { 'content-type':'text/html; charset=utf-8' }); res.end(historyFixture); return; }
  let file;
  try { file = safeJoin(req.url || '/'); } catch (_) { res.writeHead(403); res.end(); return; }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  fs.readFile(file, (err, data) => { if (err) { res.writeHead(404); res.end('not found'); return; } res.writeHead(200, { 'content-type':mime[path.extname(file)] || 'application/octet-stream' }); res.end(data); });
});

async function waitText(locator, pattern) {
  await locator.waitFor({ state:'visible' });
  await locator.evaluate((el, source) => new Promise((resolve, reject) => {
    const re = new RegExp(source, 'i');
    if (re.test(el.textContent || '')) return resolve();
    const observer = new MutationObserver(() => { if (re.test(el.textContent || '')) { observer.disconnect(); resolve(); } });
    observer.observe(el, { subtree:true, childList:true, characterData:true, attributes:true });
    setTimeout(() => { observer.disconnect(); reject(new Error(`timed out waiting for ${source}: ${el.textContent}`)); }, 10000);
  }), pattern.source);
}

(async () => {
  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
  const browser = await chromium.launch({
    headless:true,
    executablePath:process.env.CHROME_BIN || undefined,
  });
  const page = await browser.newPage({ viewport:{ width:1100, height:900 } });
  const pageErrors = [];
  const helperRegistryWarnings = [];
  page.on('pageerror', error => pageErrors.push(error.message || String(error)));
  page.on('console', message => {
    if (message.type() === 'warning' && message.text().includes('[helpers menu] uncategorized helpers')) {
      helperRegistryWarnings.push(message.text());
    }
  });
  await page.goto(`http://127.0.0.1:${port}/fixture.html`, { waitUntil:'networkidle' });
  await page.waitForFunction(() => window.fixtureMounted === true);

  const runtimeRegistryContract = await page.evaluate(async () => {
    const shared = await import('/nemoclaw/scripts/_shared.js');
    const canvas = await import('/nemoclaw/scripts/_canvas.js');
    localStorage.removeItem('nemoclaw_iframe_proxy_opt_in');
    const localDefault = shared.iframeProxyModeEnabled();
    shared.setIframeProxyMode(true);
    const explicitRelay = shared.iframeProxyModeEnabled();
    shared.setIframeProxyMode(false);
    const explicitDirect = shared.iframeProxyModeEnabled();
    return {
      orphans:canvas.helperMenuOrphans(),
      cdnDefault:shared.defaultIframeProxyModeForLocation('https://cdn.dli.learn.nvidia.com/course-static/nemoclaw/'),
      localFile:shared.defaultIframeProxyModeForLocation('file:course-preview.html'),
      cdnHttp:shared.defaultIframeProxyModeForLocation('http://cdn.dli.learn.nvidia.com/course-static/nemoclaw/'),
      siblingHost:shared.defaultIframeProxyModeForLocation('https://cdn.dli.learn.nvidia.com.example.invalid/'),
      unrelatedHost:shared.defaultIframeProxyModeForLocation('https://example.com/'),
      localDefault,
      explicitRelay,
      explicitDirect,
    };
  });
  if (runtimeRegistryContract.orphans.length) throw new Error(`helper registry has uncategorized entries: ${JSON.stringify(runtimeRegistryContract.orphans)}`);
  if (!runtimeRegistryContract.cdnDefault || !runtimeRegistryContract.localFile || runtimeRegistryContract.cdnHttp || runtimeRegistryContract.siblingHost || runtimeRegistryContract.unrelatedHost) throw new Error(`model relay default escaped the CDN and local-preview boundary: ${JSON.stringify(runtimeRegistryContract)}`);
  if (runtimeRegistryContract.localDefault || !runtimeRegistryContract.explicitRelay || runtimeRegistryContract.explicitDirect) throw new Error(`model relay override is not deterministic: ${JSON.stringify(runtimeRegistryContract)}`);

  const depthSelect = page.locator('.learning-depth-select');
  await depthSelect.waitFor({ state:'attached' });
  if (await depthSelect.isVisible()) throw new Error('global depth selector should stay hidden during the Guided pilot');
  const setDepth = async (value) => depthSelect.evaluate((el, next) => {
    el.value = next;
    el.dispatchEvent(new Event('change', { bubbles:true }));
  }, value);
  if (await depthSelect.inputValue() !== 'guided') throw new Error('first visit did not default to Guided');
  if (await page.locator('#learning-applied .learning-block-body').isVisible() || await page.locator('#learning-deep .learning-block-body').isVisible()) throw new Error('first visit did not collapse optional Guided sections');
  const referenceBody = page.locator('#learning-reference .learning-block-body');
  if (!await referenceBody.isVisible()) throw new Error('Guided hid the primary paper references');
  await page.locator('#learning-reference > summary').click();
  if (await referenceBody.isVisible()) throw new Error('always-open reference disclosure could not be collapsed locally');
  await page.locator('#learning-reference > summary').click();
  if (!/Inspect the implementation detail\?/.test(await page.locator('#learning-applied > summary').innerText())) throw new Error('applied section did not ask its local question inline');
  const runCode = page.locator('#run-cell .rc-code-det');
  const canvasCodes = page.locator('#canvas .cf-panel-code-det');
  const canvasCode = canvasCodes.first();
  if (await runCode.getAttribute('open') !== null || await page.locator('#canvas .cf-panel-code-det[open]').count()) throw new Error('Guided did not collapse interactive code');
  await canvasCode.locator('summary').click();
  if (await canvasCode.getAttribute('open') === null || await runCode.getAttribute('open') !== null) throw new Error('local code reveal changed the wrong cell');

  if (!await page.locator('#learning-applied > summary').isVisible() || !await page.locator('#learning-deep > summary').isVisible()) throw new Error('Guided view hid inline section questions');
  await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
  await page.emulateMedia({ media:'print' });
  if (!await page.locator('#learning-applied .learning-block-body').isVisible() || !await page.locator('#learning-deep .learning-block-body').isVisible()) {
    const printState = await page.evaluate(() => [...document.querySelectorAll('.learning-block')].map(el => ({ open:el.open, display:getComputedStyle(el.querySelector('.learning-block-body')).display, height:el.querySelector('.learning-block-body').getBoundingClientRect().height })));
    throw new Error(`print did not restore complete authored content: ${JSON.stringify(printState)}`);
  }
  if (!await runCode.isVisible() || !await canvasCode.isVisible()) throw new Error('print did not restore interactive code');
  await page.emulateMedia({ media:'screen' });
  await page.evaluate(() => window.dispatchEvent(new Event('afterprint')));
  if (await page.locator('#learning-applied .learning-block-body').isVisible() || await page.locator('#learning-deep .learning-block-body').isVisible()) throw new Error('screen view did not restore Guided disclosure state after print');
  if (await runCode.getAttribute('open') !== null || await canvasCode.getAttribute('open') === null) throw new Error('screen view did not restore per-cell code disclosure state after print');
  await setDepth('applied');
  if (await runCode.getAttribute('open') === null || await page.locator('#canvas .cf-panel-code-det[open]').count() !== await canvasCodes.count()) throw new Error('Applied did not restore authored code defaults');
  await setDepth('guided');
  if (await runCode.getAttribute('open') !== null || await page.locator('#canvas .cf-panel-code-det[open]').count()) throw new Error('returning to Guided did not collapse code');
  await page.locator('#learning-applied > summary').click();
  if (!await page.locator('#learning-applied .learning-block-body').isVisible() || await page.locator('#learning-deep .learning-block-body').isVisible()) throw new Error('local section override changed the wrong disclosure');
  const stored = await page.evaluate(() => localStorage.getItem('nemoclaw_learning_depth_v1'));
  if (stored !== 'guided') throw new Error(`learning depth stored unexpected data: ${stored}`);

  await page.reload({ waitUntil:'networkidle' });
  await page.waitForFunction(() => window.fixtureMounted === true);
  if (await page.locator('#learning-applied .learning-block-body').isVisible() || await page.locator('#learning-deep .learning-block-body').isVisible()) throw new Error('reload did not restore Guided default');
  if (!await page.locator('#learning-reference .learning-block-body').isVisible()) throw new Error('reload hid the primary paper references');
  await page.evaluate(() => { location.hash = 'learning-deep'; });
  if (!await page.locator('#learning-deep .learning-block-body').isVisible()) throw new Error('deep link did not reveal its collapsed disclosure');
  await page.locator('#learning-deep > summary').click();
  await page.locator('.learning-depth-select').evaluate(el => { el.value='applied'; el.dispatchEvent(new Event('change', { bubbles:true })); });
  if (!await page.locator('#learning-applied .learning-block-body').isVisible() || await page.locator('#learning-deep .learning-block-body').isVisible()) throw new Error('Applied view did not show applied detail and collapse deep detail');
  await page.locator('.learning-depth-select').evaluate(el => { el.value='complete'; el.dispatchEvent(new Event('change', { bubbles:true })); });
  if (!await page.locator('#learning-applied .learning-block-body').isVisible() || !await page.locator('#learning-deep .learning-block-body').isVisible()) throw new Error('Complete did not restore all optional content');

  await page.setViewportSize({ width:390, height:844 });
  await page.locator('#learning-deep > summary').focus();
  await page.keyboard.press('Enter');
  if (await page.locator('#learning-deep .learning-block-body').isVisible()) throw new Error('narrow keyboard activation did not close the local disclosure');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (overflow > 1) throw new Error(`learning fixture overflowed narrow viewport by ${overflow}px`);
  await page.setViewportSize({ width:1100, height:900 });

  const intro = await page.locator('#run-cell .rc-intro').innerText();
  if (!/Read the outcome first/.test(intro)) throw new Error('RunCell intro did not render');
  if (await page.locator('#run-cell .rc-code-det').getAttribute('open') === null) throw new Error('Complete did not restore the authored open RunCell');

  const chatState = page.locator('#chat .chatui-state');
  await waitText(chatState, /Prerequisite:/);
  if (!await page.locator('#chat .chatui-send').isDisabled()) throw new Error('chat Send enabled before prerequisite');
  await page.evaluate(() => { window.fixtureReady = true; window.dispatchEvent(new Event('nemoclaw:prerequisites')); });
  await waitText(chatState, /^Ready$/);
  if (await page.locator('#chat .chatui-send').isDisabled()) throw new Error('chat Send stayed disabled after prerequisite');

  await page.locator('#chat .chatui-text').fill('reset this run');
  await page.locator('#chat .chatui-send').click();
  await waitText(chatState, /Running/);
  await page.locator('#chat .chatui-reset').click();
  await waitText(chatState, /^Ready$/);
  if (/reset this run/.test(await page.locator('#chat .chatui-log').innerText())) throw new Error('chat Reset left the in-flight turn');
  await page.locator('#chat .chatui-text').fill('stop this run');
  await page.locator('#chat .chatui-send').click();
  await waitText(chatState, /Running/);
  await page.locator('#chat .chatui-send').click();
  await waitText(chatState, /Stopped.*Ready/);
  await page.locator('#chat .chatui-reset').click();
  await waitText(chatState, /^Ready$/);

  const runButton = page.locator('#run-cell .rc-run');
  await runButton.click();
  await waitText(runButton, /Stop/);
  await page.locator('#run-cell .rc-reset').click();
  await waitText(page.locator('#run-cell .rc-out'), /reset.*empty/i);
  await waitText(runButton, /Run$/);
  await page.waitForTimeout(100);
  if (!/reset.*empty/i.test(await page.locator('#run-cell .rc-out').innerText())) throw new Error('RunCell stale completion overwrote Reset');
  await runButton.click();
  await waitText(runButton, /Stop/);
  await runButton.click();
  await waitText(page.locator('#run-cell .rc-out'), /stopped/);
  await waitText(runButton, /Run$/);
  await page.locator('#run-cell .rc-code').evaluate(el => {
    el.value = 'helpers.log("process detail"); return { useful: 42, status: "complete" };';
  });
  await runButton.click();
  await waitText(page.locator('#run-cell .rc-out'), /process detail/);
  await waitText(page.locator('#run-cell .rc-out'), /returned value/);
  const returnText = await page.locator('#run-cell .rc-out').innerText();
  if (!/useful/.test(returnText) || !/42/.test(returnText)) throw new Error('RunCell log suppressed its structured returned value');
  await page.locator('#run-cell .rc-code').evaluate(el => { el.value = 'throw new Error("fixture boom")'; });
  await runButton.click();
  await waitText(page.locator('#run-cell .rc-out'), /fixture boom/);
  if (await page.locator('#run-cell .rc-code-det').getAttribute('open') === null) throw new Error('RunCell error did not reveal code');
  await page.locator('#run-cell .rc-reset').click();
  await waitText(page.locator('#run-cell .rc-out'), /reset.*empty/i);

  const flowButton = page.locator('#canvas .cf-btn-run');
  await flowButton.click();
  await waitText(flowButton, /Stop/);
  await page.locator('#canvas .cf-btn-reset').click();
  await waitText(page.locator('#canvas .cf-status-bar'), /^reset$/);
  await waitText(flowButton, /Run all$/);
  await page.waitForTimeout(100);
  if ((await page.locator('#canvas .cf-status-bar').innerText()).trim() !== 'reset') throw new Error('CanvasFlow stale completion overwrote Reset');
  await flowButton.click();
  await waitText(flowButton, /Stop/);
  await flowButton.click();
  await waitText(page.locator('#canvas .cf-status-bar'), /stopped/);
  await page.locator('#canvas .cf-btn-reset').click();
  await waitText(page.locator('#canvas .cf-status-bar'), /^reset$/);

  const consoleInput = page.locator('#console .da-in');
  await consoleInput.scrollIntoViewIfNeeded();
  const scrollBeforeConsoleRun = await page.evaluate(() => window.scrollY);
  await consoleInput.fill('wait');
  await consoleInput.press('Enter');
  await waitText(page.locator('#console .da-console-state'), /Running/);
  await page.locator('#console .da-stop').click();
  await waitText(page.locator('#console .da-console-state'), /Stopped.*Ready/);
  await waitText(page.locator('#console .da-out'), /stopped/);
  const scrollAfterConsoleRun = await page.evaluate(() => window.scrollY);
  if (Math.abs(scrollAfterConsoleRun - scrollBeforeConsoleRun) > 2) throw new Error(`console run moved viewport: ${scrollBeforeConsoleRun} -> ${scrollAfterConsoleRun}`);
  await page.locator('#console .da-clear').click();
  if ((await page.locator('#console .da-out').innerText()).trim()) throw new Error('console Clear left output');

  if (pageErrors.length) throw new Error(`page errors: ${JSON.stringify(pageErrors)}`);
  if (helperRegistryWarnings.length) throw new Error(`helper registry warnings: ${JSON.stringify(helperRegistryWarnings)}`);
  const noJsContext = await browser.newContext({ javaScriptEnabled:false, viewport:{ width:800, height:700 } });
  const noJsPage = await noJsContext.newPage();
  await noJsPage.goto(`http://127.0.0.1:${port}/fixture.html`, { waitUntil:'domcontentloaded' });
  if (!await noJsPage.locator('#learning-applied .learning-block-body').isVisible() || !await noJsPage.locator('#learning-deep .learning-block-body').isVisible() || !await noJsPage.locator('#learning-reference .learning-block-body').isVisible()) throw new Error('no-JavaScript view hid authored content');
  await noJsContext.close();
  const supportPage = await browser.newPage({ viewport:{ width:800, height:700 } });
  await supportPage.goto(`http://127.0.0.1:${port}/support.html`, { waitUntil:'networkidle' });
  await supportPage.waitForFunction(() => window.supportMounted === true);
  if (await supportPage.locator('.learning-depth-control').count()) throw new Error('learning controls mounted on a non-course support tool');
  await supportPage.close();
  const localizedPage = await browser.newPage({ viewport:{ width:390, height:700 } });
  await localizedPage.goto(`http://127.0.0.1:${port}/localized.html`, { waitUntil:'networkidle' });
  await localizedPage.waitForFunction(() => window.localizedMounted === true);
  const localizedControl = localizedPage.locator('.learning-depth-control');
  if (await localizedControl.count() !== 1 || !/^Detalhe/.test(await localizedControl.innerText())) throw new Error('localized course page lost its Portuguese depth control');
  const localizedOptions = await localizedControl.locator('option').allInnerTexts();
  if (localizedOptions.join('|') !== 'Guiado|Aplicado|Completo') throw new Error(`localized depth options are not Portuguese: ${JSON.stringify(localizedOptions)}`);
  if (!await localizedPage.locator('#localized-detail p').isVisible()) throw new Error('localized depth control changed authored content visibility');
  await localizedPage.close();

  const historyContext = await browser.newContext({ viewport:{ width:800, height:700 } });
  const historyPage = await historyContext.newPage();
  await historyPage.goto(`http://127.0.0.1:${port}/history.html`, { waitUntil:'domcontentloaded' });
  await historyPage.waitForFunction(() => window.historyMounted === true);
  await historyPage.locator('.chatui-text').fill('slow turn survives navigation');
  await historyPage.locator('.chatui-send').click();
  await historyPage.waitForFunction(() => JSON.parse(localStorage.getItem('nemoclaw_course_assistant_sessions_v1')).sessions[0].history.some(item => item.content === 'slow turn survives navigation'));
  await historyPage.reload({ waitUntil:'domcontentloaded' });
  await historyPage.waitForFunction(() => window.historyMounted === true);
  const inFlightHistory = await historyPage.locator('.chatui-log').innerText();
  if (!/slow turn survives navigation/.test(inFlightHistory) || !/partial reply before navigation/.test(inFlightHistory)) throw new Error('in-flight Course Assistant turn or streamed tail vanished across navigation');
  await historyPage.locator('.chatui-text').fill('completed turn survives navigation');
  await historyPage.locator('.chatui-send').click();
  await waitText(historyPage.locator('.chatui-state'), /^Ready$/);
  await historyPage.reload({ waitUntil:'domcontentloaded' });
  await historyPage.waitForFunction(() => window.historyMounted === true);
  const restoredHistory = await historyPage.locator('.chatui-log').innerText();
  if (!/completed turn survives navigation/.test(restoredHistory) || !/completed reply: completed turn survives navigation/.test(restoredHistory)) throw new Error('completed Course Assistant transcript vanished across navigation');
  const restoredActivity = await historyPage.evaluate(() => JSON.parse(localStorage.getItem('nemoclaw_course_assistant_sessions_v1')).sessions[0].activity);
  if (!/completed turn survives navigation/.test(restoredActivity) || !/completed reply: completed turn survives navigation/.test(restoredActivity)) throw new Error('visible Course Assistant agent activity vanished across navigation');
  await historyContext.close();

  const courseContext = await browser.newContext({ viewport:{ width:1100, height:900 } });
  await courseContext.addInitScript(() => {
    localStorage.setItem('nemoclaw_learning_depth_v1', 'guided');
    const key = 'nemoclaw_course_assistant_sessions_v1';
    if (!localStorage.getItem(key)) localStorage.setItem(key, JSON.stringify({ version:1, activeId:'saved-session', sessions:[{
      id:'saved-session', title:'Saved session', pageId:'01a-loop', pageTitle:'The agent loop', createdAt:1, updatedAt:1,
      history:[{ role:'user', content:'Persisted learner question' }, { role:'assistant', content:'Persisted course answer' }],
      activity:'USER\\nPersisted learner question\\n\\nAGENT ACTIVITY\\nread_course_page · 01a-loop\\nPersisted course answer',
    }] }));
  });
  const coursePage = await courseContext.newPage();
  await coursePage.goto(`http://127.0.0.1:${port}/nemoclaw/02b-rag.html`, { waitUntil:'domcontentloaded' });
  const courseSearch = await coursePage.evaluate(async () => {
    const { searchCoursePages } = await import('./scripts/_course_assistant.js');
    return searchCoursePages('sandbox policy tools');
  });
  if (!courseSearch.length || courseSearch.length > 4 || courseSearch.some(result => !result.id || !result.excerpt || result.excerpt.length > 900)) throw new Error(`page assistant course search is not bounded/useful: ${JSON.stringify(courseSearch)}`);
  const sourceAccess = await coursePage.evaluate(async () => {
    const { courseCode, courseCodeArtifacts, courseRuntimeFiles, courseRuntimeSource, resolveCoursePageUrl } = await import('./scripts/_langchain.js');
    const { artifactFromMarkdown, artifactCodeIssue, artifactJavaScriptIssue, parseInlineCourseSourceIntent, resolveCourseSourceUri } = await import('./scripts/_course_assistant.js');
    const artifacts = await courseCodeArtifacts('02c-deep');
    const deep = await courseCode('02c-deep', 'deep-src');
    const runtimeFiles = courseRuntimeFiles();
    const shared = await courseRuntimeSource('_shared.js');
    const rejected = await courseRuntimeSource('../index.html');
    const captured = artifactFromMarkdown('```html\n<button id="captured">Captured</button>\n```\n```javascript\ndocument.querySelector("#captured").dataset.ready = "yes";\n```', 'Captured artifact');
    const rawCaptured = artifactFromMarkdown('Here is the artifact.\n<!doctype html><html><body><button id="raw">Raw</button><script>document.querySelector("#raw").dataset.ready="yes";</script></body></html>\nReady.', 'Raw artifact');
    const recoveredIntent = parseInlineCourseSourceIntent('{"uri":"deep-src"}');
    const recoveredSource = await resolveCourseSourceUri(recoveredIntent?.uri, '02c-deep');
    return {
      artifactIds:artifacts.map(item => item.id),
      indexHasBodies:artifacts.some(item => Object.hasOwn(item, 'source')),
      deepIsJavaScript:/helpers\.mountChatUI\("#deep-artifact"/.test(deep) && /Promise\.all\(branches\.map\(runBranch\)\)/.test(deep),
      runtimeFiles:runtimeFiles.map(item => item.file),
      sharedIsExact:/The web course runs JavaScript only\./.test(shared) && /mountCourseAssistant/.test(shared),
      traversalRejected:/unknown runtime file/.test(rejected),
      fencedArtifactCaptured:captured?.title === 'Captured artifact' && /captured/.test(captured.html) && /dataset\.ready/.test(captured.javascript),
      rawArtifactCaptured:rawCaptured?.title === 'Raw artifact' && /^<!doctype html>/i.test(rawCaptured.html) && !/Here is the artifact/.test(rawCaptured.html) && !/Ready\.$/.test(rawCaptured.html),
      inlineScriptGuard:/browser storage APIs/.test(artifactCodeIssue({ html:'<script>localStorage.setItem("x", "y")</script>', javascript:'' })),
      externalScriptGuard:/External scripts/.test(artifactCodeIssue({ html:'<script src="https://example.com/demo.js"></script>', javascript:'' })),
      inlineHelperGuard:/helpers\.mountChatUI/.test(artifactCodeIssue({ html:'<script>helpers.mountChatUI("#app")</script>', javascript:'' })),
      inlineSourceRecovered:recoveredIntent?.uri === 'deep-src' && /Course source: 02c-deep · deep-src/.test(recoveredSource?.content || ''),
      artifactAsyncGuard:/asynchronous/.test(artifactJavaScriptIssue('const embeddings = course.embed(["hello"], { inputType: "query" });')),
      artifactInputGuard:/inputType/.test(artifactJavaScriptIssue('const embeddings = await course.embed(["hello"], { inputType: "text" });')),
      artifactTopLevelAwait:artifactJavaScriptIssue('const embeddings = await course.embed(["hello"], { inputType: "query" });') === '',
      artifactCombinedGuard:(issue => /inputType/.test(issue) && /asynchronous/.test(issue))(artifactJavaScriptIssue('const embeddings = course.embed(["hello"], { inputType: "text" });')),
      helperAliasAllowed:artifactJavaScriptIssue('const embeddings = await helpers.embed(["hello"], { inputType: "query" }); const score = helpers.cosineSim(embeddings[0], embeddings[0]);') === '',
      helperAsyncGuard:/asynchronous/.test(artifactJavaScriptIssue('const embeddings = helpers.embed(["hello"], { inputType: "query" });')),
      helperAllowlistGuard:/helpers\.mountChatUI/.test(artifactJavaScriptIssue('helpers.mountChatUI("#app");')),
      deployedOverviewUrl:resolveCoursePageUrl('overview', 'https://pages.example/NemoClawDLIOS/nemoclaw/01a-loop.html'),
      deployedLessonUrl:resolveCoursePageUrl('02b-rag', 'https://pages.example/NemoClawDLIOS/nemoclaw/01a-loop.html'),
    };
  });
  if (!sourceAccess.artifactIds.includes('deep-src') || !sourceAccess.artifactIds.some(id => /^module-/.test(id)) || sourceAccess.indexHasBodies || !sourceAccess.deepIsJavaScript || !sourceAccess.runtimeFiles.includes('_shared.js') || !sourceAccess.runtimeFiles.includes('_openclaw_cli.js') || !sourceAccess.sharedIsExact || !sourceAccess.traversalRejected || !sourceAccess.fencedArtifactCaptured || !sourceAccess.rawArtifactCaptured || !sourceAccess.inlineScriptGuard || !sourceAccess.externalScriptGuard || !sourceAccess.inlineHelperGuard || !sourceAccess.inlineSourceRecovered || !sourceAccess.artifactAsyncGuard || !sourceAccess.artifactInputGuard || !sourceAccess.artifactTopLevelAwait || !sourceAccess.artifactCombinedGuard || !sourceAccess.helperAliasAllowed || !sourceAccess.helperAsyncGuard || !sourceAccess.helperAllowlistGuard || sourceAccess.deployedOverviewUrl !== 'https://pages.example/NemoClawDLIOS/index.html' || sourceAccess.deployedLessonUrl !== 'https://pages.example/NemoClawDLIOS/nemoclaw/02b-rag.html') throw new Error(`Course Assistant source/artifact access is incomplete or unsafe: ${JSON.stringify(sourceAccess)}`);
  const sessionCap = await coursePage.evaluate(async () => {
    const { saveCourseAssistantStore, loadCourseAssistantStore } = await import('./scripts/_course_assistant.js');
    const values = new Map();
    const storage = { getItem:key => values.get(key) || null, setItem:(key, value) => values.set(key, value) };
    const store = { activeId:'s14', sessions:Array.from({ length:15 }, (_, i) => ({ id:'s' + i, title:'Session ' + i, createdAt:i, updatedAt:i,
      history:[{ role:'user', content:'u'.repeat(60000) }, { role:'assistant', content:'a'.repeat(60000) }],
      activity:'trace'.repeat(20000),
      artifact:{ title:'Large artifact', html:'h'.repeat(80000), javascript:'j'.repeat(80000), updatedAt:i },
    })) };
    const saved = saveCourseAssistantStore(store, storage);
    const loaded = loadCourseAssistantStore(storage);
    return { live:store.sessions.length, stored:loaded.sessions.length, chars:saved.chars,
      maxHistory:Math.max(...loaded.sessions.map(session => session.history.reduce((sum, item) => sum + item.content.length, 0))),
      maxActivity:Math.max(...loaded.sessions.map(session => session.activity.length)),
      maxArtifact:Math.max(...loaded.sessions.map(session => (session.artifact?.html.length || 0) + (session.artifact?.javascript.length || 0))),
    };
  });
  if (sessionCap.live !== 12 || sessionCap.stored !== 12 || sessionCap.chars > 2550000 || sessionCap.maxHistory > 100000 || sessionCap.maxActivity > 20000 || sessionCap.maxArtifact > 80000) throw new Error(`Course Assistant cap diverged between live and stored state: ${JSON.stringify(sessionCap)}`);
  const assistantLauncher = coursePage.locator('.course-assistant-launcher');
  await assistantLauncher.waitFor({ state:'visible' });
  const launcherBox = await assistantLauncher.boundingBox();
  if (!launcherBox || launcherBox.width > 34 || launcherBox.height > 34) throw new Error('page assistant launcher is not compact');
  if (!/Course-authored prose, example code, and original diagrams/.test(await coursePage.locator('.course-license-note').innerText())) throw new Error('course license note lost its authored-material scope');
  await assistantLauncher.click();
  let assistantPanel = coursePage.locator('.course-assistant-panel');
  await assistantPanel.waitFor({ state:'visible' });
  if (!/COURSE ASSISTANT/.test(await assistantPanel.innerText())) throw new Error('shared assistant was not rebranded course-wide');
  let sessionSelect = assistantPanel.locator('#course-assistant-session');
  if (await sessionSelect.locator('option').count() !== 1 || !/Persisted learner question/.test(await assistantPanel.innerText())) throw new Error('Course Assistant did not restore its local session');
  if (!/Attached page: 01a-loop/.test(await assistantPanel.locator('.course-assistant-context').innerText())) throw new Error('restored Course Assistant session inherited the open page instead of its saved page');
  await assistantPanel.locator('[data-course-assistant-view="history"]').click();
  if (!/read_course_page · 01a-loop/.test(await assistantPanel.locator('.course-assistant-history pre').innerText()) || !/Persisted course answer/.test(await assistantPanel.locator('.course-assistant-history pre').innerText())) throw new Error('Course Assistant History did not restore saved agent activity');
  await assistantPanel.locator('[data-course-assistant-view="chat"]').click();
  const savedSessionId = await sessionSelect.inputValue();
  await assistantPanel.locator('[data-course-assistant-new]').click();
  await assistantPanel.locator('#course-assistant-session option').nth(1).waitFor({ state:'attached' });
  const newSessionId = await sessionSelect.inputValue();
  if (newSessionId === savedSessionId) throw new Error('Course Assistant New did not select a fresh session');
  if (!/Attached page: 02b-rag/.test(await assistantPanel.locator('.course-assistant-context').innerText())) throw new Error('new Course Assistant session did not record its source page');
  await assistantPanel.locator('.chatui-text').fill('Explain MCP trust boundaries');
  await assistantPanel.locator('.chatui-send').click();
  await coursePage.waitForFunction(() => document.querySelector('#course-assistant-session')?.selectedOptions[0]?.textContent.includes('Explain MCP trust boundaries'));
  const sessionName = assistantPanel.locator('.course-assistant-sessions input[type="text"]');
  await sessionName.fill('MCP study');
  await sessionName.press('Enter');
  if (!/MCP study/.test(await sessionSelect.locator('option:checked').innerText())) throw new Error('Course Assistant inline rename did not update the session list');
  await assistantPanel.locator('[data-course-assistant-new]').click();
  if (await sessionSelect.locator('option').count() !== 3) throw new Error('Course Assistant did not create a new session after a named session');
  await assistantPanel.locator('[data-course-assistant-new]').click();
  if (await sessionSelect.locator('option').count() !== 3) throw new Error('Course Assistant created duplicate empty sessions');
  await assistantPanel.locator('[data-course-assistant-delete]').click();
  if (await sessionSelect.locator('option').count() !== 2 || await sessionSelect.inputValue() !== newSessionId) throw new Error('Course Assistant did not return to the prior named session');
  await coursePage.reload({ waitUntil:'domcontentloaded' });
  await coursePage.locator('.course-assistant-launcher').click();
  assistantPanel = coursePage.locator('.course-assistant-panel');
  await assistantPanel.waitFor({ state:'visible' });
  sessionSelect = assistantPanel.locator('#course-assistant-session');
  if (await sessionSelect.locator('option').count() !== 2 || await sessionSelect.inputValue() !== newSessionId || !/MCP study/.test(await sessionSelect.locator('option:checked').innerText())) throw new Error('Course Assistant session selection/name did not survive reload');
  if (!/Explain MCP trust boundaries/.test(await assistantPanel.locator('.chatui-log').innerText())) throw new Error('failed Course Assistant turn did not survive reload');
  await assistantPanel.locator('[data-course-assistant-view="history"]').click();
  if (!/Explain MCP trust boundaries/.test(await assistantPanel.locator('.course-assistant-history pre').innerText())) throw new Error('failed Course Assistant agent activity did not survive reload');
  await assistantPanel.locator('[data-course-assistant-view="chat"]').click();
  await assistantPanel.locator('[data-course-assistant-view="artifact"]').click();
  await assistantPanel.locator('[data-course-artifact-title]').fill('MCP browser demo');
  if (!/await course\.embed/.test(await assistantPanel.locator('.course-artifact-api').innerText())) throw new Error('Course Assistant artifact editor hides its asynchronous embedding API');
  if (await assistantPanel.locator('.course-artifact-editors .CodeMirror').count() !== 2) throw new Error('Course Assistant artifact did not upgrade both code editors');
  await assistantPanel.evaluate(panel => {
    panel.querySelector('[data-course-artifact-html]').__courseAssistantEditor.setValue('<button id="artifact-run">Run artifact</button><output id="artifact-output"></output>');
    panel.querySelector('[data-course-artifact-js]').__courseAssistantEditor.setValue('document.querySelector("#artifact-run").addEventListener("click", () => { document.querySelector("#artifact-output").textContent = "artifact ran"; });');
  });
  if (!await assistantPanel.locator('.course-artifact-editors label').nth(0).locator('.cm-tag').count() || !await assistantPanel.locator('.course-artifact-editors label').nth(1).locator('.cm-variable').count()) throw new Error('Course Assistant artifact editors lost HTML or JavaScript syntax highlighting');
  await assistantPanel.locator('[data-course-artifact-run]').click();
  if (!String(await assistantPanel.locator('.course-assistant-artifact iframe').getAttribute('src')).startsWith('blob:')) throw new Error('Course Assistant artifact still relies on fragile srcdoc execution');
  let artifactFrame = assistantPanel.frameLocator('.course-assistant-artifact iframe');
  await artifactFrame.locator('#artifact-run').click();
  if (await artifactFrame.locator('#artifact-output').innerText() !== 'artifact ran') throw new Error('Course Assistant artifact did not run its queued browser JavaScript');
  await assistantPanel.locator('[data-course-artifact-clear]').click();
  const clearedArtifact = await assistantPanel.evaluate(panel => ({
    src:panel.querySelector('.course-assistant-artifact iframe').getAttribute('src'),
    html:panel.querySelector('[data-course-artifact-html]').__courseAssistantEditor.getValue(),
    javascript:panel.querySelector('[data-course-artifact-js]').__courseAssistantEditor.getValue(),
  }));
  if (clearedArtifact.src !== 'about:blank' || !/artifact-run/.test(clearedArtifact.html) || !/artifact-output/.test(clearedArtifact.javascript)) throw new Error(`Clear preview destroyed artifact source: ${JSON.stringify(clearedArtifact)}`);
  await assistantPanel.locator('[data-course-assistant-view="chat"]').click();
  const crossPage = await courseContext.newPage();
  await crossPage.goto(`http://127.0.0.1:${port}/nemoclaw/01b-react.html`, { waitUntil:'domcontentloaded' });
  await crossPage.locator('.course-assistant-launcher').click();
  const crossPanel = crossPage.locator('.course-assistant-panel');
  await crossPanel.waitFor({ state:'visible' });
  if (!/Attached page: 02b-rag/.test(await crossPanel.locator('.course-assistant-context').innerText()) || !/Use 01b-react/.test(await crossPanel.locator('[data-course-assistant-use-page]').innerText())) throw new Error('Course Assistant silently rebound a restored session to the currently open page');
  if (!/Explain MCP trust boundaries/.test(await crossPanel.locator('.chatui-log').innerText())) throw new Error('Course Assistant session metadata survived cross-page navigation but its transcript did not');
  await crossPanel.locator('[data-course-assistant-view="history"]').click();
  if (!/Explain MCP trust boundaries/.test(await crossPanel.locator('.course-assistant-history pre').innerText())) throw new Error('Course Assistant session transcript survived cross-page navigation but its agent activity did not');
  const historyCopyStyle = await crossPanel.locator('[data-course-history-copy]').evaluate(button => ({ width:button.getBoundingClientRect().width, fontSize:parseFloat(getComputedStyle(button).fontSize) }));
  if (historyCopyStyle.width <= 50 || historyCopyStyle.fontSize >= 18) throw new Error(`Course Assistant History copy control inherited top-level close-button sizing: ${JSON.stringify(historyCopyStyle)}`);
  await crossPanel.locator('[data-course-assistant-view="artifact"]').click();
  if (await crossPanel.locator('[data-course-artifact-title]').inputValue() !== 'MCP browser demo' || !/artifact-output/.test(await crossPanel.locator('[data-course-artifact-html]').inputValue())) throw new Error('Course Assistant Artifact view did not survive cross-page navigation');
  artifactFrame = crossPanel.frameLocator('.course-assistant-artifact iframe');
  await artifactFrame.locator('#artifact-run').click();
  if (await artifactFrame.locator('#artifact-output').innerText() !== 'artifact ran') throw new Error('restored Course Assistant artifact did not rerun in its sandbox');
  await crossPanel.evaluate(panel => {
    panel.querySelector('[data-course-artifact-html]').__courseAssistantEditor.setValue('<div id="bridge-result"></div>');
    panel.querySelector('[data-course-artifact-js]').__courseAssistantEditor.setValue('document.querySelector("#bridge-result").textContent = helpers.cosineSim([1, 0], [1, 0]).toFixed(1) + "|"; try { await helpers.embed([]); } catch (error) { document.querySelector("#bridge-result").textContent += error.message; }');
  });
  await crossPanel.locator('[data-course-artifact-run]').click();
  artifactFrame = crossPanel.frameLocator('.course-assistant-artifact iframe');
  await artifactFrame.locator('#bridge-result').waitFor({ state:'visible' });
  if (!/^1\.0\|.*accepts 1-16 non-empty strings/.test(await artifactFrame.locator('#bridge-result').innerText())) throw new Error('Course Assistant artifact helper facade did not expose cosineSim/embed or enforce its request bound');
  await crossPanel.evaluate(panel => {
    panel.querySelector('[data-course-artifact-html]').__courseAssistantEditor.setValue('<script>localStorage.setItem("blocked", "yes")</script>');
    panel.querySelector('[data-course-artifact-js]').__courseAssistantEditor.setValue('');
  });
  await crossPanel.locator('[data-course-artifact-run]').click();
  if (!/browser storage APIs/.test(await crossPanel.locator('.course-artifact-actions [role="status"]').innerText())) throw new Error('Course Assistant artifact validation ignored blocked APIs inside inline HTML scripts');
  await crossPage.evaluate(() => {
    window.__courseArtifactReadyChannels = [];
    window.addEventListener('message', event => {
      if (event.data?.type === 'artifact-ready' && event.data?.channel) window.__courseArtifactReadyChannels.push(event.data.channel);
    });
  });
  await crossPanel.evaluate(panel => {
    panel.querySelector('[data-course-artifact-html]').__courseAssistantEditor.setValue('<button id="broken-control" onclick="missingArtifactMethod()">Broken control</button>');
    panel.querySelector('[data-course-artifact-js]').__courseAssistantEditor.setValue('');
  });
  await crossPanel.locator('[data-course-artifact-run]').click();
  await crossPage.waitForFunction(() => window.__courseArtifactReadyChannels?.length > 0);
  await crossPage.evaluate(() => {
    const frame = document.querySelector('.course-assistant-artifact iframe');
    const channel = window.__courseArtifactReadyChannels.at(-1);
    frame.contentWindow.postMessage({ channel, type:'artifact-probe' }, '*');
  });
  await crossPage.waitForFunction(() => /missingArtifactMethod/.test(document.querySelector('.course-artifact-actions [role="status"]')?.textContent || ''));
  await crossPanel.evaluate(panel => {
    panel.querySelector('[data-course-artifact-html]').__courseAssistantEditor.setValue('<div>Broken initialization</div><script>document.querySelector("#missing-target").style.width="1px";</script>');
    panel.querySelector('[data-course-artifact-js]').__courseAssistantEditor.setValue('');
  });
  await crossPanel.locator('[data-course-artifact-run]').click();
  await crossPage.waitForFunction(() => /Cannot read properties of null/.test(document.querySelector('.course-artifact-actions [role="status"]')?.textContent || ''));
  await crossPanel.evaluate(panel => panel.querySelector('[data-course-artifact-js]').__courseAssistantEditor.setValue('const { broken } from "./_shared.js";'));
  await crossPanel.locator('[data-course-artifact-run]').click();
  if (!/Syntax error|Imports are unavailable/.test(await crossPanel.locator('.course-artifact-actions [role="status"]').innerText())) throw new Error('Course Assistant artifact did not surface generated JavaScript failure before execution');
  await crossPage.close();
  await assistantPanel.locator('[data-course-assistant-delete]').click();
  await sessionSelect.locator('option').nth(0).waitFor({ state:'attached' });
  if (await sessionSelect.locator('option').count() !== 1 || await sessionSelect.inputValue() !== savedSessionId) throw new Error('Course Assistant Delete did not return to the remaining session');
  const assistantText = await assistantPanel.innerText();
  if (!/Attached page: 01a-loop/.test(assistantText)) throw new Error('page assistant does not name its session-owned page context');
  if (!/course map, prose, code, and runtime-source tools available/.test(assistantText)) throw new Error('page assistant hides its prose/code exploration tools');
  if (await assistantPanel.locator('.rc-card, .cf-wrap').count()) throw new Error('page assistant exposed lesson cells instead of the artifact editor');
  const resizeHandle = assistantPanel.locator('.course-assistant-resizer');
  await resizeHandle.waitFor({ state:'visible' });
  const panelBeforeResize = await assistantPanel.boundingBox();
  const handleBox = await resizeHandle.boundingBox();
  if (!panelBeforeResize || !handleBox) throw new Error('page assistant resize geometry is unavailable');
  await coursePage.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + 120);
  await coursePage.mouse.down();
  await coursePage.mouse.move(120, handleBox.y + 120, { steps:8 });
  await coursePage.mouse.up();
  const panelAfterResize = await assistantPanel.boundingBox();
  if (!panelAfterResize || panelAfterResize.width <= panelBeforeResize.width || panelAfterResize.width > 1100 * 0.9 + 2) throw new Error(`page assistant drag did not expand within 90vw: ${JSON.stringify({ panelBeforeResize, panelAfterResize })}`);
  await resizeHandle.press('ArrowRight');
  const panelAfterKeyboard = await assistantPanel.boundingBox();
  if (!panelAfterKeyboard || panelAfterKeyboard.width >= panelAfterResize.width) throw new Error('page assistant keyboard resize did not shrink the panel');
  await coursePage.keyboard.press('Escape');
  if (await assistantPanel.isVisible()) throw new Error('page assistant did not close on Escape');
  await coursePage.setViewportSize({ width:390, height:844 });
  await assistantLauncher.click();
  await assistantPanel.locator('[data-course-assistant-view="artifact"]').click();
  const assistantOverflow = await coursePage.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  const mobileArtifactFrame = await assistantPanel.locator('.course-assistant-artifact iframe').boundingBox();
  if (assistantOverflow > 1 || !mobileArtifactFrame || mobileArtifactFrame.width > 390 || mobileArtifactFrame.height < 100) throw new Error(`page assistant/artifact overflowed or collapsed on narrow viewport: ${JSON.stringify({ assistantOverflow, mobileArtifactFrame })}`);
  await assistantPanel.locator('[data-course-assistant-view="chat"]').click();
  await coursePage.keyboard.press('Escape');
  await coursePage.setViewportSize({ width:1100, height:900 });
  await coursePage.locator('.learning-depth-select').waitFor({ state:'attached' });
  if (await coursePage.locator('.learning-depth-select').isVisible()) throw new Error('02b exposed the hidden global depth selector');
  await coursePage.locator('#cell-m3b-p1 .rc-card').waitFor({ state:'visible' });
  const courseBlocks = coursePage.locator('details.learning-block[data-learning-tier]');
  if (await courseBlocks.count() !== 8) throw new Error('02b learning depth lost one of its eight local disclosures');
  const guidedBodies = coursePage.locator('details.learning-block .learning-block-body:visible');
  const guidedReferences = coursePage.locator('details.learning-block[data-learning-always-open] .learning-block-body:visible');
  if (await guidedBodies.count() !== await guidedReferences.count()) throw new Error('02b Guided left optional narrative visible outside the always-open references');
  if (await coursePage.locator('#cell-m3b-p1 .cf-canvas').count() || !await coursePage.locator('#cell-m3b-p1 .rc-card').count()) throw new Error('02b single embedding regressed from RunCell to CanvasFlow');
  if (await coursePage.locator('[data-learning-id="graphrag-global-questions"] .learning-block-body').isVisible()) throw new Error('02b Guided left GraphRAG visible');
  const guidedHeight = await coursePage.evaluate(() => document.documentElement.scrollHeight);
  await coursePage.locator('.learning-depth-select').evaluate(el => { el.value='complete'; el.dispatchEvent(new Event('change', { bubbles:true })); });
  if (await coursePage.locator('details.learning-block .learning-block-body:visible').count() !== 8) throw new Error('02b Complete did not restore every local disclosure');
  if (!await coursePage.locator('#cell-graphrag').isVisible()) throw new Error('02b Complete did not restore the optional GraphRAG artifact');
  const completeHeight = await coursePage.evaluate(() => document.documentElement.scrollHeight);
  if (guidedHeight >= completeHeight * 0.7) throw new Error(`02b Guided remains too tall: ${guidedHeight}px versus ${completeHeight}px complete`);

  const deepPage = await courseContext.newPage();
  await deepPage.setViewportSize({ width:390, height:844 });
  await deepPage.goto(`http://127.0.0.1:${port}/nemoclaw/02c-deep.html`, { waitUntil:'domcontentloaded' });
  await deepPage.locator('#deep-artifact .chatui').waitFor({ state:'visible' });
  const materialsSearch = await deepPage.evaluate(async () => {
    const { webSearch, formatSearchResults } = await import('./scripts/_shared.js');
    const result = await webSearch('AI Agents', { maxResults:4 });
    return { count:result.count, source:result.source, formatted:formatSearchResults(result) };
  });
  if (!materialsSearch.count || materialsSearch.source !== 'materials' || /no results|search unavailable/i.test(materialsSearch.formatted)) throw new Error(`02c curated materials branch has no supported result: ${JSON.stringify(materialsSearch)}`);
  const deepBoard = await deepPage.evaluate(() => {
    const host = document.createElement('div');
    host.innerHTML = '<section class="research-board"><header><strong>Parallel research</strong><span class="research-board-status">Running</span></header><div class="research-thread-rail"></div></section>';
    const rail = host.querySelector('.research-thread-rail');
    for (let i = 0; i < 3; i++) {
      const card = document.createElement('article');
      card.className = 'research-thread running'; card.tabIndex = 0;
      card.innerHTML = '<header><span class="research-thread-kind">Worker</span><h3>Focused branch</h3></header><div class="research-thread-status">Extracting evidence</div><pre class="research-thread-stream"></pre>';
      card.querySelector('.research-thread-stream').textContent = Array(80).fill('streamed evidence').join('\n');
      rail.appendChild(card);
    }
    document.querySelector('#deep-artifact').appendChild(host);
    const card = rail.querySelector('.research-thread');
    const stream = card.querySelector('.research-thread-stream');
    card.focus();
    const railStyle = getComputedStyle(rail), streamStyle = getComputedStyle(stream);
    return {
      active: document.activeElement === card,
      railOverflow: rail.scrollWidth > rail.clientWidth,
      railOverflowX: railStyle.overflowX,
      justify: railStyle.justifyContent,
      streamOverflow: stream.scrollHeight > stream.clientHeight,
      streamOverflowY: streamStyle.overflowY,
      cardHeight: card.getBoundingClientRect().height,
    };
  });
  if (!deepBoard.active) throw new Error('02c worker panel cannot receive focus');
  if (!deepBoard.railOverflow || deepBoard.railOverflowX !== 'auto' || deepBoard.justify !== 'flex-start') throw new Error(`02c worker rail is not left-aligned and scrollable: ${JSON.stringify(deepBoard)}`);
  if (!deepBoard.streamOverflow || deepBoard.streamOverflowY !== 'auto' || deepBoard.cardHeight > 300) throw new Error(`02c worker stream is not height-bounded: ${JSON.stringify(deepBoard)}`);

  const furtherPage = await courseContext.newPage();
  await furtherPage.goto(`http://127.0.0.1:${port}/nemoclaw/04c-going-further.html`, { waitUntil:'domcontentloaded' });
  if (await furtherPage.locator('#capstone-artifact, #capstone-cell').count()) throw new Error('04c still duplicates the always-available Course Assistant');
  const faviconUrl = await furtherPage.locator('head link[rel~="icon"]').evaluate(link => link.href);
  if (!faviconUrl?.endsWith('/nemoclaw/assets/favicon.ico')) throw new Error(`04c did not pin the course favicon inside its deployed subpath: ${faviconUrl}`);
  const learningPathCards = await furtherPage.locator('#learning-path .step-card').evaluateAll(cards => cards.map(card => {
    const media = card.querySelector(':scope > .step-card-media');
    const image = media?.querySelector('img');
    const button = card.querySelector('a.btn[href]');
    return {
      hasMedia:!!media,
      hrefMatches:media?.href === button?.href,
      imageUrl:image?.src || '',
      alt:image?.alt || '',
      lazy:image?.loading === 'lazy',
      privateReferrer:image?.referrerPolicy === 'no-referrer',
    };
  }));
  if (!learningPathCards.length || learningPathCards.some(card => !card.hasMedia || !card.hrefMatches || !card.imageUrl.startsWith('https://developer.download.nvidia.com/images/learning-pathways/') || !card.alt || !card.lazy || !card.privateReferrer)) throw new Error(`04c learning-path cards lost their linked NVIDIA course art: ${JSON.stringify(learningPathCards)}`);
  const resourceFigures = await furtherPage.locator('figure.resource-aside-figure').evaluateAll(figures => figures.map(figure => {
    const source = figure.querySelector('figcaption a[href]');
    const media = figure.querySelector(':scope > a.resource-aside-media');
    const image = media?.querySelector('img');
    return {
      hrefMatches:Boolean(source && media && source.href === media.href),
      imageUrl:image?.src || '',
      alt:image?.alt || '',
      lazy:image?.loading === 'lazy',
      privateReferrer:image?.referrerPolicy === 'no-referrer',
      hasCaption:Boolean(figure.querySelector('figcaption')?.textContent.trim()),
    };
  }));
  const officialImageHosts = new Set(['build.nvidia.com', 'developer.download.nvidia.com']);
  if (!resourceFigures.length || resourceFigures.some(item => !item.hrefMatches || !officialImageHosts.has(new URL(item.imageUrl).hostname) || !item.alt || !item.lazy || !item.privateReferrer || !item.hasCaption)) throw new Error(`04c resource figures lost their source-linked NVIDIA art: ${JSON.stringify(resourceFigures)}`);
  const helperGrid = await furtherPage.locator('.lp-helpers').evaluate(list => ({
    display:getComputedStyle(list).display,
    items:[...list.children].map(item => ({ hasLink:Boolean(item.querySelector('a[href]')), borderRadius:getComputedStyle(item).borderRadius })),
    promotedRows:list.querySelectorAll('.resource-spotlight, .resource-aside-figure').length,
  }));
  if (helperGrid.display !== 'grid' || !helperGrid.items.length || helperGrid.items.some(item => !item.hasLink || item.borderRadius === '0px') || helperGrid.promotedRows) throw new Error(`04c helper articles are not a uniform card grid: ${JSON.stringify(helperGrid)}`);
  const furtherLayout = await furtherPage.locator('main').evaluate(main => {
    const sections = [...main.children]
      .map(node => node.dataset?.goingFurtherSection)
      .filter(Boolean);
    const built = main.querySelector('[data-going-further-section="built"]');
    const next = main.querySelector('[data-going-further-section="next"]');
    const lessons = next?.querySelector('details.deployment-lessons');
    return {
      sections,
      assistantIntegrated:Boolean(built?.querySelector('#open-course-assistant')),
      retiredArtifactCopy:Boolean(built?.textContent.includes('no longer mounts a second capstone chat')),
      helperInsideNext:Boolean(next?.querySelector('.lp-helpers')),
      lessonsInsideNext:Boolean(lessons),
      lessonsHidden:Boolean(lessons && !lessons.open),
      nextVisible:Boolean(next && (!next.matches('details') || next.open)),
      sourcesHidden:Boolean(!main.querySelector('[data-going-further-section="sources"]')?.open),
      malformedAssistantCopy:Boolean(built?.textContent.includes('lesson, It')),
      namedAssistantCopy:Boolean(built?.textContent.includes('Course Assistant')),
      compactAssistantHandoff:Boolean(built?.querySelector('.going-further-assistant #open-course-assistant')),
      artifactHeading:Boolean(main.querySelector('[data-going-further-section="interface"] > h2')?.textContent.toLowerCase().includes('artifact')),
      redundantNextSummary:Boolean(next?.matches('details')),
      detachedAssistantHeading:[...main.querySelectorAll(':scope > h2')].some(heading => /course assistant/i.test(heading.textContent)),
    };
  });
  const expectedFurtherOrder = ['built', 'deploy', 'knowledge', 'interface', 'next', 'learning-path', 'sources'];
  if (furtherLayout.sections.join('|') !== expectedFurtherOrder.join('|') || !furtherLayout.assistantIntegrated || furtherLayout.retiredArtifactCopy || !furtherLayout.helperInsideNext || !furtherLayout.lessonsInsideNext || !furtherLayout.lessonsHidden || !furtherLayout.nextVisible || !furtherLayout.sourcesHidden || furtherLayout.malformedAssistantCopy || furtherLayout.namedAssistantCopy || !furtherLayout.compactAssistantHandoff || furtherLayout.artifactHeading || furtherLayout.redundantNextSummary || furtherLayout.detachedAssistantHeading) throw new Error(`04c content hierarchy drifted: ${JSON.stringify(furtherLayout)}`);
  await furtherPage.locator('#open-course-assistant').click();
  if (!await furtherPage.locator('.course-assistant-panel').isVisible()) throw new Error('04c Course Assistant handoff does not open the shared panel');

  const loopPage = await courseContext.newPage();
  await loopPage.goto(`http://127.0.0.1:${port}/nemoclaw/01a-loop.html`, { waitUntil:'domcontentloaded' });
  await loopPage.locator('.learning-depth-select').waitFor({ state:'attached' });
  await loopPage.locator('#cell-reflex .cf-btn-run').waitFor({ state:'attached' });
  const loopBlocks = loopPage.locator('details.learning-block[data-learning-tier]');
  if (await loopBlocks.count() !== 5) throw new Error('01a learning depth lost one of its five local disclosures');
  if (await loopPage.locator('details.learning-block .learning-block-body:visible').count()) throw new Error('01a Guided left optional narrative visible');
  const loopGuidedHeight = await loopPage.evaluate(() => document.documentElement.scrollHeight);
  await loopPage.locator('.learning-depth-select').evaluate(el => { el.value='complete'; el.dispatchEvent(new Event('change', { bubbles:true })); });
  if (await loopPage.locator('details.learning-block .learning-block-body:visible').count() !== 5) throw new Error('01a Complete did not restore every local disclosure');
  if (!await loopPage.locator('[data-learning-id="replaceable-reasoning-lab"] .learning-block-body').isVisible()) throw new Error('01a Complete did not restore the local loop lab');
  const loopCompleteHeight = await loopPage.evaluate(() => document.documentElement.scrollHeight);
  if (loopGuidedHeight >= loopCompleteHeight * 0.65) throw new Error(`01a Guided remains too tall: ${loopGuidedHeight}px versus ${loopCompleteHeight}px complete`);
  await courseContext.close();

  const result = await page.evaluate(() => ({
    intro: document.querySelector('#run-cell .rc-intro')?.textContent.trim(),
    run: document.querySelector('#run-cell .rc-out')?.textContent.trim(),
    flow: document.querySelector('#canvas .cf-status-bar')?.textContent.trim(),
    chat: document.querySelector('#chat .chatui-state')?.textContent.trim(),
    console: document.querySelector('#console .da-console-state')?.textContent.trim(),
  }));
  console.log(JSON.stringify({
    ok:true,
    states:result,
    course01a:{ guidedHeight:loopGuidedHeight, completeHeight:loopCompleteHeight },
    course02b:{ guidedHeight, completeHeight },
    course02c:{ deepBoard, materialsSearch:{ count:materialsSearch.count, source:materialsSearch.source } },
    assistant:{ courseSearch:courseSearch.map(result => result.id), sourceAccess, sessions:{ restored:true, completedAcrossNavigation:true, inFlightAcrossNavigation:true, renamed:true, duplicateEmptyBlocked:true, pageOwned:true, artifactAcrossPages:true, cap:sessionCap.live, storeChars:sessionCap.chars, reload:true, createDelete:true }, widths:{ initial:panelBeforeResize.width, dragged:panelAfterResize.width, keyboard:panelAfterKeyboard.width } },
  }, null, 2));
  await browser.close();
  server.close();
})().catch(error => { try { server.close(); } catch (_) {} console.error(error.stack || String(error)); process.exit(1); });
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-root", default="web")
    args = parser.parse_args()
    site_arg = Path(args.site_root)
    site_root = site_arg.resolve() if site_arg.is_absolute() else (ROOT / site_arg).resolve()
    if not (site_root / "nemoclaw/scripts/_shared.js").is_file():
        print(f"learner_flow_runtime_audit: FAIL\n  - incomplete site root: {site_root}")
        return 1
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as handle:
        handle.write(RUNTIME_JS)
        script = Path(handle.name)
    try:
        proc = run_node(script, env=environment(SITE_ROOT=site_root), timeout=180)
    except (BrowserRuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"learner_flow_runtime_audit: FAIL\n  - {exc}")
        return 1
    finally:
        try:
            script.unlink()
        except OSError:
            pass
    print(proc.stdout.rstrip())
    print("learner_flow_runtime_audit: " + ("OK" if proc.returncode == 0 else "FAIL"))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
