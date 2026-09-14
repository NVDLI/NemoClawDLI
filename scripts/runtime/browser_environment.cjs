// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

function browserExecutable(value) {
  if (typeof value !== 'string' || !value) return null;
  try {
    fs.accessSync(value, fs.constants.X_OK);
    return fs.statSync(value).isFile() ? path.resolve(value) : null;
  } catch { return null; }
}

function resolveChrome({env = process.env, chromium} = {}) {
  const onPath = name => (env.PATH || '').split(path.delimiter)
    .map(directory => browserExecutable(path.join(directory, name))).find(Boolean);
  const requested = browserExecutable(env.CHROME_BIN) || (env.CHROME_BIN && onPath(env.CHROME_BIN));
  if (requested) return requested;
  for (const name of ['chromium', 'chromium-browser', 'google-chrome', 'google-chrome-stable']) {
    const found = onPath(name);
    if (found) return found;
  }
  // The installed package owns its browser revision and platform-specific layout.
  try {
    const found = browserExecutable((chromium || require('playwright-core').chromium).executablePath());
    if (found) return found;
  } catch { /* Continue to contributor-installed and legacy cached browsers. */ }
  for (const root of [env.PLAYWRIGHT_BROWSERS_PATH || '/tmp/pw-browsers',
    '/sandbox/.cache/ms-playwright', path.join(env.HOME || '/root', '.cache/ms-playwright')]) {
    let revisions;
    try { revisions = fs.readdirSync(root).sort(); } catch { continue; }
    for (const revision of revisions) {
      for (const name of ['chrome-headless-shell-linux64/chrome-headless-shell', 'chrome-linux/chrome', 'chrome-linux64/chrome']) {
        const found = browserExecutable(path.join(root, revision, name));
        if (found) return found;
      }
    }
  }
  for (const name of ['Chromium.app/Contents/MacOS/Chromium', 'Google Chrome.app/Contents/MacOS/Google Chrome',
    'Microsoft Edge.app/Contents/MacOS/Microsoft Edge']) {
    const found = browserExecutable(path.join('/Applications', name));
    if (found) return found;
  }
  throw new Error('Chromium or compatible Chrome is required; install it or set CHROME_BIN');
}

function localCourseOrigins(port, interfaces = os.networkInterfaces()) {
  const address = Object.values(interfaces).flat().find(item => item.family === 'IPv4' && !item.internal)?.address;
  if (!address) throw new Error('A non-loopback IPv4 address is required for the HTTP lab browser contract.');
  return [
    {mode:'lab-http', origin:`http://${address}:${port}`, secure:false},
    {mode:'loopback', origin:`http://127.0.0.1:${port}`, secure:true},
  ];
}

function discoverCoursePages(directory) {
  const pages = new Set();
  const manifest = path.join(directory, 'learning-profile.json');
  if (fs.existsSync(manifest)) {
    const profile = JSON.parse(fs.readFileSync(manifest, 'utf8'));
    if (!Array.isArray(profile.lessons)) throw new Error(`Course profile requires a lessons array: ${manifest}`);
    for (const lesson of profile.lessons) {
      if (typeof lesson?.id !== 'string' || !lesson.id.trim()) throw new Error(`Course profile has an invalid lesson ID: ${manifest}`);
      const file = path.resolve(directory, lesson.id + '.html');
      if (!file.startsWith(path.resolve(directory) + path.sep) || !fs.existsSync(file)) {
        throw new Error(`Declared lesson is missing or escapes its course: ${lesson.id}`);
      }
      pages.add(file);
    }
  }
  function visit(owner) {
    for (const entry of fs.readdirSync(owner, {withFileTypes:true})) {
      const file = path.join(owner, entry.name);
      if (entry.isDirectory()) visit(file);
      else if (/\.html?$/i.test(entry.name) && /<script\b/i.test(fs.readFileSync(file, 'utf8'))) pages.add(file);
    }
  }
  visit(directory);
  return [...pages].sort();
}

function coursePageRole(directory, file) {
  const manifest = path.join(directory, 'learning-profile.json');
  if (!fs.existsSync(manifest)) return 'document';
  const profile = JSON.parse(fs.readFileSync(manifest,'utf8'));
  return profile.lessons.some(lesson => path.resolve(directory,lesson.id + '.html') === path.resolve(file)) ? 'lesson' : 'document';
}

// Executed in the page; keep it independent of Node and test-only globals.
function runtimeFailureSnapshot() {
  const cells = [...document.querySelectorAll('.cf-wrap,.rc-card,.xblock')].map((element, index) => ({
    id:element.id || element.parentElement?.id || `cell-${index + 1}`,
    state:element.dataset.state || '',
    error:element.querySelector('.cell-runtime-error,.cf-panel-error')?.textContent?.trim() || '',
  }));
  return {cells, failed:cells.filter(cell => cell.state === 'failed' || cell.error)};
}

function hasRuntimeFailures(pageErrors, snapshot, resourceErrors = []) {
  return pageErrors.length > 0 || snapshot.failed.length > 0 || resourceErrors.length > 0;
}

function assertRuntimeSuccess(pageErrors, snapshot, resourceErrors = []) {
  if (hasRuntimeFailures(pageErrors, snapshot, resourceErrors)) {
    throw new Error(JSON.stringify({pageErrors, resourceErrors, failedCells:snapshot.failed}));
  }
}

function runtimeCoverageFindings(snapshot, executed) {
  const expected = snapshot.cells.map(cell => cell.id);
  return {
    unexecuted:expected.filter(id => !executed.includes(id)),
    unexpected:executed.filter(id => !expected.includes(id)),
    duplicate:expected.filter((id,index) => expected.indexOf(id) !== index)
      .concat(executed.filter((id,index) => executed.indexOf(id) !== index)),
  };
}

function assertRuntimeCoverage(snapshot, executed) {
  const findings = runtimeCoverageFindings(snapshot, executed);
  if (Object.values(findings).some(entries => entries.length)) throw new Error(JSON.stringify(findings));
}

module.exports = {resolveChrome, localCourseOrigins, discoverCoursePages, coursePageRole, runtimeFailureSnapshot, hasRuntimeFailures,
  assertRuntimeSuccess, runtimeCoverageFindings, assertRuntimeCoverage};
if (require.main === module) {
  if (process.argv[2] === '--chrome') {
    try { console.log(resolveChrome()); }
    catch (error) { console.error(error.message); process.exitCode = 2; }
  } else if (process.argv[2] === '--pages') {
    for (const file of discoverCoursePages(process.argv[3])) console.log(file);
  } else if (process.argv[2] === '--role') console.log(coursePageRole(process.argv[3],process.argv[4]));
  else throw new Error('Expected --chrome, --pages COURSE_DIRECTORY or --role COURSE_DIRECTORY FILE');
}
