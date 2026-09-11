// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)('playwright-core');
const root = path.resolve('web');
const courses = fs.readdirSync(root).filter(name =>
  fs.existsSync(path.join(root, name, 'scripts/_course_assistant.js')));
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
      await page.locator('.course-assistant-resizer').focus();
      await page.keyboard.press('Shift+Tab');
      assert.equal(await panel.evaluate(node => node.contains(document.activeElement)), true);
      await page.keyboard.press('Tab');
      assert.equal(await panel.evaluate(node => node.contains(document.activeElement)), true);
      await page.keyboard.press('Escape');
      assert.equal(await panel.evaluate(node => node.open), false);
      assert.equal(await launcher.evaluate(node => document.activeElement === node), true);
    }
    assert.deepEqual(errors, []);
    await page.close();
  }
  console.log('Assistant modal, keyboard restoration and service links: PASS');
} finally {
  await browser?.close();
  await new Promise(resolve => server.close(resolve));
}
