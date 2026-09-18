// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)('playwright-core');
const root = path.resolve(process.env.COURSE_WEB_ROOT || 'web');
function discoverCourses(base, directory = base) {
  const entries = fs.readdirSync(directory, {withFileTypes:true});
  const assistant = path.join(directory, 'scripts/_course_assistant.js');
  const found = fs.existsSync(assistant) && fs.lstatSync(assistant).isFile()
    ? [path.relative(base, directory)] : [];
  for (const entry of entries) {
    if (entry.isDirectory() && !['.git', 'node_modules'].includes(entry.name))
      found.push(...discoverCourses(base, path.join(directory, entry.name)));
  }
  return found.sort();
}
// Discovery must include future nested projections and exclude deleted/malformed beacons.
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'assistant-discovery-'));
try {
  const nested = 'new/locale/profile/course';
  fs.mkdirSync(path.join(fixture, nested, 'scripts'), {recursive:true});
  fs.writeFileSync(path.join(fixture, nested, 'scripts/_course_assistant.js'), '');
  assert.deepEqual(discoverCourses(fixture), [nested]);
  fs.renameSync(path.join(fixture, 'new'), path.join(fixture, 'renamed'));
  assert.deepEqual(discoverCourses(fixture), ['renamed/locale/profile/course']);
  const beacon = path.join(fixture, 'renamed/locale/profile/course/scripts/_course_assistant.js');
  fs.renameSync(beacon, beacon + '.bak');
  assert.deepEqual(discoverCourses(fixture), []);
  fs.rmSync(beacon + '.bak');
  assert.deepEqual(discoverCourses(fixture), []);
} finally { fs.rmSync(fixture, {recursive:true, force:true}); }
const courses = discoverCourses(root);
assert.ok(courses.length, 'No assistant implementation discovered');
const server = http.createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  const file = path.resolve(root, pathname.replace(/^\/project\//, ''));
  if (!file.startsWith(root + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    response.writeHead(404).end(); return;
  }
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml' };
  response.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
  response.end(fs.readFileSync(file));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
let browser;
try {
  browser = await chromium.launch({ executablePath: process.env.CHROME_BIN, args: ['--no-sandbox'] });
  for (const course of courses) {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    await page.goto(`${origin}/project/${course}/index.html`, { waitUntil: 'networkidle' });
    const launcher = page.locator('.course-assistant-launcher');
    const panel = page.locator('#course-assistant-panel');
    assert.equal(await page.locator('.course-license-note a').first().getAttribute('href'),
      'https://github.com/NVDLI/NemoClawDLI/blob/main/LICENSE');
    assert.ok(await page.locator('.course-license-note a[href*="privacy-policy"]').count());
    for (const width of [1280, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await launcher.click();
      assert.equal(await panel.evaluate(node => node.matches(':modal')), true);
      assert.ok(await panel.evaluate(node => {
        const box = node.getBoundingClientRect();
        return box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight;
      }), 'Assistant fits the viewport');
      await page.locator('.course-assistant-resizer').focus();
      await page.keyboard.press('Shift+Tab');
      assert.equal(await panel.evaluate(node => node.contains(document.activeElement)), true);
      await page.keyboard.press('Tab');
      assert.equal(await panel.evaluate(node => node.contains(document.activeElement)), true);
      await page.keyboard.press('Escape');
      assert.equal(await panel.evaluate(node => node.open), false);
      assert.equal(await launcher.evaluate(node => document.activeElement === node), true);
      assert.ok(await page.locator('.topbar').evaluate(node => [...node.children].every(child => {
        const box = child.getBoundingClientRect();
        const bar = node.getBoundingClientRect();
        return !box.width || (box.left >= 0 && box.right <= innerWidth + 1 && box.top >= bar.top && box.bottom <= bar.bottom + 1);
      })), 'Setup and navigation controls fit the viewport');
      if (process.env.SCREENSHOT_DIR) {
        fs.mkdirSync(process.env.SCREENSHOT_DIR, {recursive:true});
        await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR, `${course.replaceAll('/', '-')}-home-${width}.png`)});
      }
    }
    assert.ok(await launcher.evaluate(node => {
      const box = node.getBoundingClientRect();
      return box.width >= 44 && box.height >= 44 && !node.textContent.includes('✦');
    }));
    assert.ok(await page.locator('.course-assistant-entry').evaluate(node =>
      !!(document.querySelector('#setup').compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING)));
    for (const input of await page.locator('#key-panel input').all())
      assert.ok(await input.evaluate(node => node.labels.length > 0), 'Setup field has an accessible name');
    await launcher.click();
    await page.waitForSelector('#course-assistant-panel .chatui-text');
    assert.equal(await panel.locator('.chatui-text').isDisabled(), true);
    assert.ok(await panel.locator('a[href="index.html#setup"]').count());
    await page.keyboard.press('Escape');
    await page.evaluate(() => {
      const outer = document.createElement('details');
      outer.id = 'nested-outer';
      outer.innerHTML = '<summary>Outer</summary><details id="nested-inner"><summary>Inner</summary><p id="nested-target">Nested target</p></details>';
      document.querySelector('main').append(outer);
      location.hash = 'nested-target';
    });
    await page.waitForFunction(() => document.querySelector('#nested-outer').open && document.querySelector('#nested-inner').open);
    assert.equal(await page.locator('#nested-target').isVisible(), true);

    await page.goto(`${origin}/project/${course}/01c-tools.html#mcp-context`, { waitUntil: 'networkidle' });
    assert.equal(await page.locator('[data-learning-id="mcp-protocol-detail"]').getAttribute('open'), '');
    const outline = page.locator('.lesson-outline');
    assert.equal(await outline.count(), 1);
    assert.equal(await outline.evaluate(node => node.open), true);
    await outline.locator('a[href="#agents-as-tools"]').click();
    assert.equal(await page.locator('[data-learning-id="subagent-as-tool"]').getAttribute('open'), '');
    await page.reload({waitUntil:'networkidle'});
    assert.equal(await page.locator('.lesson-resume, .lesson-outline a[aria-current]').count(), 0);
    assert.equal(await outline.locator('summary').evaluate(node => getComputedStyle(node).fontWeight), '700');
    assert.equal(await outline.locator('a').first().evaluate(node => getComputedStyle(node).fontWeight), '400');
    assert.equal(await page.locator('[data-learning-id="mcp-protocol-detail"]').getAttribute('open'), '');

    // Only the external model service is replaced; exercise the shipped LangGraph/checkpointer.
    const requests = [];
    await page.route('**/model-fixture*/v1/chat/completions', async route => {
      requests.push({...route.request().postDataJSON(), endpoint:route.request().url(),
        authorization:route.request().headers().authorization});
      const delayedArtifact = requests.at(-1).messages.filter(message => message.role === 'user').at(-1)?.content === 'Create a delayed artifact';
      const content = delayedArtifact
        ? '```html\n<div id="old-artifact">Old artifact</div>\n```\n```javascript\nawait new Promise(resolve => setTimeout(resolve, 1500));\ndocument.querySelector("#old-artifact").textContent = "Old artifact ready";\n```'
        : 'Fixture answer.';
      const data = {id:'test-response', object:'chat.completion.chunk', created:1, model:'fixture',
        choices:[{index:0, delta:{role:'assistant',content}, finish_reason:null}]};
      await route.fulfill({contentType:'text/event-stream', body:
        'data: ' + JSON.stringify(data) + '\n\n' +
        'data: ' + JSON.stringify({...data, choices:[{index:0,delta:{},finish_reason:'stop'}]}) + '\n\ndata: [DONE]\n\n'});
    });
    await page.evaluate(async () => {
      const helpers = await import('./scripts/_shared.js');
      helpers.setModelApiBaseUrl(location.origin + '/model-fixture/v1');
      helpers.setKey('test-only-fixture');
      const host = document.createElement('div'); host.id = 'memory-regression'; document.querySelector('main').prepend(host);
      const {mountAgentChat} = await import('./scripts/_chat.js');
      await mountAgentChat(host, {memory:true, models:[{id:'fixture',label:'Fixture'}], modules:helpers.coursePages(),
        system:'Test conversation memory.', currentContext:() => 'Current section: ' + document.documentElement.dataset.courseSection});
    });
    const chat = page.locator('#memory-regression');
    assert.equal(await chat.locator('.chatui-mem').isVisible(), true);
    assert.equal(await chat.locator('details.chatui-options').getAttribute('open'), null);
    const send = async text => {
      const response = page.waitForResponse(response => response.url().includes('/v1/chat/completions'));
      await chat.locator('textarea').fill(text); await chat.locator('.chatui-send').click();
      await response;
      await page.waitForFunction(() => !document.querySelector('#memory-regression .chatui-cursor'));
      assert.equal(await chat.locator('.chatui-msg.err').count(), 0);
    };
    await send('Remember apple'); await send('Remember banana');
    assert.ok(requests.at(-1).messages.some(message => message.content === 'Remember apple'));
    await chat.locator('.chatui-msgctl.user').last().locator('button').last().click();
    await send('Remember pear');
    assert.deepEqual(requests.at(-1).messages.filter(message => message.role === 'user').map(message => message.content), ['Remember apple','Remember pear']);
    await chat.locator('.chatui-mem').click();
    await send('Only cherry'); await send('Only date');
    assert.deepEqual(requests.at(-1).messages.filter(message => message.role === 'user').map(message => message.content), ['Only date']);
    assert.ok(requests.at(-1).messages.some(message => String(message.content).includes('Current section:')));
    await chat.locator('.chatui-mem').click();
    await send('Recall the conversation');
    assert.ok(requests.at(-1).messages.some(message => message.content === 'Remember apple'));
    await page.evaluate(async () => {
      const helpers = await import('./scripts/_shared.js');
      helpers.setModelApiBaseUrl(location.origin + '/model-fixture-new/v1');
      helpers.setKey('test-only-replacement');
    });
    await send('Use the updated connection');
    assert.ok(requests.at(-1).endpoint.includes('/model-fixture-new/'));
    assert.equal(requests.at(-1).authorization, 'Bearer test-only-replacement');
    await chat.locator('.chatui-options summary').click();
    const chip = chat.locator('.chatui-modchip').first();
    assert.notEqual(await chip.textContent(), await chip.getAttribute('data-id'));
    await chip.click(); assert.equal(await chip.getAttribute('aria-pressed'), 'true');
    await page.evaluate(() => document.querySelector('#memory-regression').remove());
    for (const section of ['tool-contract', 'agents-as-tools']) {
      await outline.evaluate(node => { node.open = true; });
      await outline.locator(`ol a[href="#${section}"]`).click();
      await launcher.click();
      await panel.locator('.chatui-text').fill('Explain the section I am reading.');
      const label = await page.evaluate(async () => {
        const {localizeCourseUiText} = await import('./scripts/_locale.js');
        return localizeCourseUiText('Model and context options');
      });
      if (!/^en(?:-|$)/i.test(await page.locator('html').getAttribute('lang')))
        assert.notEqual(label, 'Model and context options', 'Declared locales translate the owned control');
      assert.equal(await panel.locator('.chatui-options summary').textContent(), label,
        'The dialog control matches the localized lesson instruction');
      const inputLabel = await page.evaluate(async () => {
        const {localizeCourseUiText} = await import('./scripts/_locale.js');
        return localizeCourseUiText('Message');
      });
      assert.equal(await panel.locator('.chatui-text').getAttribute('aria-label'), inputLabel,
        'The dialog input has a localized accessible name');
      const response = page.waitForResponse(response => response.url().includes('/v1/chat/completions'));
      await panel.locator('.chatui-send').click();
      await response;
      await page.waitForFunction(() => !document.querySelector('#course-assistant-panel .chatui-cursor'));
      assert.equal(await panel.locator('.chatui-msg.err').count(), 0);
      const context = requests.at(-1).messages.filter(message =>
        message.role === 'system' && String(message.content).startsWith('Current reading section')).at(-1);
      assert.ok(context?.content.includes(`#${section}.`), `Assistant receives the current section on every turn (${course}, ${section}): ${JSON.stringify(context)}`);
      if (process.env.SCREENSHOT_DIR) {
        await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR, `${course.replaceAll('/', '-')}-assistant.png`)});
      }
      await page.keyboard.press('Escape');
    }
    if (course === courses[0]) {
      await launcher.click();
      await panel.locator('.course-assistant-options summary').click();
      const sessions = panel.locator('#course-assistant-session');
      const original = await sessions.inputValue();
      await panel.locator('.chatui-text').fill('Create a delayed artifact');
      await panel.locator('.chatui-send').click();
      await page.locator('body > iframe[hidden]').waitFor({state:'attached'});
      await panel.locator('[data-course-assistant-new]').click();
      assert.notEqual(await sessions.inputValue(), original);
      await sessions.selectOption(original);
      await page.locator('body > iframe[hidden]').waitFor({state:'detached'});
      const artifact = await page.evaluate(id => JSON.parse(localStorage.getItem('nemoclaw_course_assistant_sessions_v1')).sessions.find(session => session.id === id).artifact, original);
      assert.equal(artifact, null, 'Old artifact validation cannot overwrite a remounted session');
      await page.keyboard.press('Escape');
    }
    await page.locator('.theme-toggle').click();
    await outline.scrollIntoViewIfNeeded();
    if (process.env.SCREENSHOT_DIR)
      await page.screenshot({path:path.join(process.env.SCREENSHOT_DIR, `${course.replaceAll('/', '-')}-outline-light.png`)});
    assert.deepEqual(errors, []);
    await page.close();
  }
  console.log('Assistant setup, navigation, accessibility and checkpoint memory: PASS');
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
