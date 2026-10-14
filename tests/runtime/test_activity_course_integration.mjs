// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import { createRequire } from 'node:module';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { pathToFileURL } from 'node:url';

const addedDiffText = diff => diff.split('\n').filter(line => line.startsWith('+') && !/^\+\+\+ (?:[ab]\/|\/dev\/null)/.test(line)).join('\n');

test('candidate label scan distinguishes removed examples from introduced configuration', () => {
  const label=['stag','ing'].join('');
  const forbidden=new RegExp(`\\b${label}\\b`,'i');
  for(const filename of ['new/config.json','nested/renamed.json']) {
    const header=`diff --git a/${filename} b/${filename}\n--- a/${filename}\n+++ b/${filename}\n@@ -1 +1 @@\n`;
    assert.doesNotMatch(addedDiffText(header+`-${label}\n+production`),forbidden);
    assert.match(addedDiffText(header+`-production\n+${label}`),forbidden);
    assert.match(addedDiffText(header+`+++${label}`),forbidden);
    assert.doesNotMatch(addedDiffText(header+`-${label}`),forbidden);
  }
});

const COURSE_ROOTS = fs.readdirSync('web', { withFileTypes: true })
  .filter(entry => entry.isDirectory() && (fs.existsSync(path.join('web', entry.name, 'activity-policy.json'))
    || fs.existsSync(path.join('web', entry.name, 'scripts', '_activity.js'))))
  .map(entry => path.join('web', entry.name));
assert.ok(COURSE_ROOTS.length, 'expected discovered Activity course contracts');
for (const COURSE_ROOT of COURSE_ROOTS) {
const COURSE_ID = path.basename(COURSE_ROOT);
const ACTIVITY_SOURCE = path.join(COURSE_ROOT, 'scripts', '_activity.js');
const ACTIVITY_RUNTIME_SOURCE = path.join(COURSE_ROOT, 'scripts', '_activity_runtime.js');
const originalFetch = globalThis.fetch;
globalThis.fetch = async url => url instanceof URL && url.protocol === 'file:'
  ? new Response(fs.readFileSync(url, 'utf8'), { status: 200 }) : originalFetch(url);
const activityModule = await import(pathToFileURL(path.resolve(ACTIVITY_SOURCE)));
globalThis.fetch = originalFetch;

const {
  ACTIVITY_MILESTONES,
  ACTIVITY_REFERRALS,
  ACTIVITY_ARTIFACT_ID,
  BUILD_SIGNUP_URL,
  createCourseActivity,
  isActivityPolicyApproved,
  resolveActivityArtifact,
  resolveActivityBaseUrl,
  validateActivityPolicy,
} = activityModule;

const APPROVED_POLICY = Object.freeze({
  schema: 'dli-activity-policy/1',
  notice_version: 'fixture-v1',
  publication_status: 'privacy-legal-reviewed',
  collection_enabled: true,
  api_base_url: 'https://activity-api.learn.nvidia.com',
  recipient: 'fixture Activity API',
  collection_defaults: { progress_sync: 'off', referral_tracking: 'off' },
  data_categories: ['course activity'],
  excluded_course_payloads: ['learner content'],
  purposes: ['save progress'],
  browser_retention: 'current tab',
  controller: { status: 'confirmed', name: 'fixture controller', owner: 'fixture owner' },
  service_retention: { status: 'confirmed', period_or_criteria: 'fixture period', owner: 'fixture owner' },
  legal_basis: { status: 'confirmed', basis: 'fixture basis', owner: 'fixture owner' },
  sale_sharing: {
    status: 'not-applicable', disposition: 'fixture disposition', owner: 'fixture owner',
    course_code_behavior: 'fixture endpoint only',
  },
  service_level: { status: 'unpublished', target: null, source_url: null },
  privacy_policy_url: 'https://www.nvidia.com/en-us/about-nvidia/privacy-policy/',
  privacy_center_url: 'https://www.nvidia.com/en-us/about-nvidia/privacy-center/',
  review_required: ['privacy', 'legal', 'activity-service-owner'],
});
const APPROVED_ARTIFACT = Object.freeze({
  artifact_id: ACTIVITY_ARTIFACT_ID,
  artifact_version: `git-${'a'.repeat(40)}`,
  artifact_digest: `sha256:${'b'.repeat(64)}`,
});

const SESSION_ID = '019f38f1-e5ab-7688-af0d-0e8925299e93';
const STAMP = '2026-09-09T19:00:00Z';
const IDS = Object.keys(ACTIVITY_MILESTONES);
const confirmedState = (count = 0) => ({ sessionId: SESSION_ID, completedAt: null,
  milestones: IDS.map((milestoneId, index) => ({ milestoneId, completedAt: index < count ? STAMP : null })) });
const rawState = (count = 0) => ({ session_id: SESSION_ID, completed_at: null,
  milestones: IDS.map((milestone_id, index) => ({ milestone_id, completed_at: index < count ? STAMP : null })) });
function createFixture({ count = 0 } = {}) {
  const calls = [];
  let remote = confirmedState(count);
  const facade = {
    completeMilestone: async (...args) => {
      calls.push(['completeMilestone', ...args]);
      remote.milestones.find(marker => marker.milestoneId === args[0]).completedAt = STAMP;
    },
    referral: async (...args) => { calls.push(['referral', ...args]); },
    getState: async () => { calls.push(['getState']); return remote; },
    complete: async (...args) => { calls.push(['complete', ...args]); remote.completedAt = STAMP; return { written: true }; },
  };
  const activity = createCourseActivity({
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async options => { calls.push(['initialize', options]); return facade; },
  });
  return { activity, calls, setState: value => { remote = value; } };
}

async function enableFixture(activity) {
  assert.equal(await activity.enable(), true);
}

test('the course imports only the public activity facade and contains no alternate hostnames', () => {
  const source = fs.readFileSync(ACTIVITY_SOURCE, 'utf8');
  const publicSource = fs.readFileSync(ACTIVITY_RUNTIME_SOURCE, 'utf8')
    + fs.readFileSync(path.join(COURSE_ROOT, '04c-going-further.html'), 'utf8') + source;

  assert.match(source, /import \{ DLIActivity,/);
  assert.doesNotMatch(source, /createActivityClient/);
  assert.doesNotMatch(publicSource, /activity-api\.(?:dev|stage)\.learn\.nvidia\.com/);
});

test('the base URL resolver always uses the public endpoint and rejects runtime override globals', () => {
  const overrideUrl = ['https://activity-api', 'stage', 'learn', 'nvidia', 'com'].join('.');
  assert.equal(
    resolveActivityBaseUrl({ __DLI_ACTIVITY_BASE_URL__: overrideUrl }),
    'https://activity-api.learn.nvidia.com',
  );
  assert.equal(resolveActivityBaseUrl({}), 'https://activity-api.learn.nvidia.com');
});

test('activity identity is derived from the exact Pages manifest', async () => {
  const commit = '1'.repeat(40);
  const manifest = `# ${COURSE_ID}-pages-sha256/1 commit=${commit}\nabc  ${COURSE_ID}/index.html\n`;
  const manifestUrl = `https://example.test/release/${COURSE_ID}/pages-sha256.txt`;
  const artifact = await resolveActivityArtifact({
    locationHref: `https://example.test/release/${COURSE_ID}/01a-loop.html`,
    fetchImpl: async url => ({
      ok: url.href === manifestUrl,
      url: url.href,
      arrayBuffer: async () => new TextEncoder().encode(manifest).buffer,
    }),
  });
  assert.deepEqual(artifact, {
    artifact_id: `artifact_${COURSE_ID}_web`,
    artifact_version: `git-${commit}`,
    artifact_digest: `sha256:${createHash('sha256').update(manifest).digest('hex')}`,
  });
});

test('materialized activity identity binds source, adapter and delivered manifest bytes', async () => {
  const commit = '2'.repeat(40);
  const adapter = '3'.repeat(64);
  const manifest = `# ${COURSE_ID}-materialized-sha256/1 commit=${commit} adapter=${adapter}\n`;
  const manifestUrl = 'https://example.test/lab/static/materialized-sha256.txt';
  for (const route of [`web/${COURSE_ID}`, `future-locale/${COURSE_ID}`]) {
    const artifact = await resolveActivityArtifact({
      locationHref: `https://example.test/lab/static/${route}/01a-loop.html`,
      fetchImpl: async url => ({
        ok: url.href === manifestUrl,
        url: url.href,
        arrayBuffer: async () => new TextEncoder().encode(manifest).buffer,
      }),
    });
    assert.equal(artifact.artifact_version, `git-${commit}-adapter-${adapter}`);
    assert.equal(artifact.artifact_digest, `sha256:${createHash('sha256').update(manifest).digest('hex')}`);
  }
});

test('sessions follow delivered content while identical locale artifacts share storage', async () => {
  const values = new Map();
  const restored = [];
  const storageTarget = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
  for (const digest of ['1', '2', '2']) {
    const artifact = { ...APPROVED_ARTIFACT, artifact_digest: `sha256:${digest.repeat(64)}` };
    const activity = createCourseActivity({
      policyLoader: async () => APPROVED_POLICY,
      artifactResolver: async () => artifact,
      storageTarget,
      initialize: async ({ storage }) => {
        restored.push(storage.load());
        storage.save({ digest });
        return { getState: async () => (confirmedState()) };
      },
    });
    await enableFixture(activity);
  }
  assert.deepEqual(restored, [null, null, { digest: '2' }]);
});

test('missing, redirected or malformed materialized identities are rejected', async () => {
  const header = `# ${COURSE_ID}-materialized-sha256/1 commit=${'2'.repeat(40)} adapter=${'3'.repeat(64)}`;
  for (const [manifest, redirected] of [
    [header.replace(/adapter=.*/, ''), false],
    [header.replace('materialized-sha256/1', 'materialized-sha256/2'), false],
    [header.replace(/.$/, 'z'), false],
    [header, true],
    ['', false],
  ]) {
    await assert.rejects(resolveActivityArtifact({
      locationHref: `https://example.test/lab/static/web/${COURSE_ID}/index.html`,
      fetchImpl: async url => ({
        ok: url.pathname.endsWith('/materialized-sha256.txt'),
        url: redirected ? 'https://other.test/materialized-sha256.txt' : url.href,
        arrayBuffer: async () => new TextEncoder().encode(`${manifest}\n`).buffer,
      }),
    }));
  }
});

test('the default Pages layout ships the public activity SDK at its imported path', () => {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), `${COURSE_ID}-activity-sdk-`));
  for (const courseRoot of [
    path.join(output, COURSE_ID),
    path.join(output, 'web', COURSE_ID),
    path.join(output, 'es', COURSE_ID),
    path.join(output, 'i18n', 'novel', 'web', COURSE_ID),
  ]) {
    execFileSync('bash', ['scripts/build/build_pages.sh', '--stage-activity-sdk', courseRoot]);
    for (const file of ['activity-sdk.js']) {
      assert.deepEqual(
        fs.readFileSync(path.resolve(courseRoot, 'scripts', '../../shared', file)),
        fs.readFileSync(path.join('web/shared', file)),
        `${courseRoot}: ${file} must preserve the shared JavaScript client`,
      );
    }
  }
});

test('the complete candidate diff contains no private or non-production activity configuration', () => {
  const candidateBase = execFileSync(
    'git', ['merge-base', 'origin/main', 'HEAD'], { encoding: 'utf8' },
  ).trim();
  const committedDiff = execFileSync(
    'git', ['diff', '--no-ext-diff', '--unified=0', candidateBase, 'HEAD'], { encoding: 'utf8', maxBuffer:64 * 1024 * 1024 },
  );
  const worktreeDiff = execFileSync(
    'git', ['diff', '--no-ext-diff', '--unified=0', 'HEAD'], { encoding: 'utf8', maxBuffer:64 * 1024 * 1024 },
  );
  const candidateDiff = `${committedDiff}\n${worktreeDiff}`;

  const unsafeEndpoint = new RegExp(`activity-api\\.(?:${['dev', 'stage', 'test', 'qa'].join('|')})\\.`, 'i');
  const unsafeLabel = new RegExp(`\\b(?:${[
    ['dev', 'local'].join('-'), ['stag', 'ing'].join(''),
    ['pre', 'prod'].join(''), ['non', 'prod'].join(''),
  ].join('|')})\\b`, 'i');
  const privateTerm = new RegExp(`\\b(?:${[
    ['gitlab', 'master'].join('-'), ['alloc', 'ator'].join(''), ['aur', 'ora'].join(''),
  ].join('|')})\\b|nvidia\\.com:12051`, 'i');
  const credentialShape = new RegExp(`\\b(?:${['AK' + 'IA[0-9A-Z]{16}', 'gh' + 'p_[A-Za-z0-9]{36}', 'nv' + 'api-[A-Za-z0-9_-]{16,}'].join('|')})\\b`);

  assert.doesNotMatch(candidateDiff, unsafeEndpoint);
  // Removing a general course example is not introducing a deployment label.
  // Endpoint, private-term and credential scans still inspect the complete diff.
  assert.doesNotMatch(addedDiffText(candidateDiff), unsafeLabel);
  assert.doesNotMatch(candidateDiff, privateTerm);
  assert.doesNotMatch(candidateDiff, credentialShape);
});

test('the milestone registry defines eleven independent named milestones', () => {
  for (const milestone of Object.values(ACTIVITY_MILESTONES)) {
    assert.ok(milestone.label?.trim(), 'every milestone needs a learner-facing label');
    assert.ok(milestone.description?.trim(), 'every milestone explains its success check');
    assert.match(milestone.href, /^[\w-]+\.html#[\w-]+$/);
    const [lesson, anchor] = milestone.href.split('#');
    const source = fs.readFileSync(path.join(COURSE_ROOT, lesson), 'utf8');
    assert.match(source, new RegExp(`id=["']${anchor}["']`), `${milestone.href} targets an existing exercise`);
  }
  assert.equal(IDS.length, 11);
  assert.equal(new Set(IDS).size, IDS.length);
});

test('the referral registry uses unique references and HTTPS destinations', () => {
  assert.equal(ACTIVITY_REFERRALS[BUILD_SIGNUP_URL], 'build:nvidia-api-key');
  const entries = Object.entries(ACTIVITY_REFERRALS);
  assert.ok(entries.length > 1);
  assert.equal(new Set(entries.map(([, referenceId]) => referenceId)).size, entries.length);
  for (const [destination, referenceId] of entries) {
    assert.equal(new URL(destination).protocol, 'https:');
    assert.match(referenceId, /^[a-z0-9][a-z0-9:-]+$/);
  }
});

test('course activity is local-only until the learner enables remote progress', async () => {
  const { activity, calls } = createFixture();

  assert.deepEqual(activity.snapshot(), {
    phase: 'off', enabled: false, referralTracking: false, sessionId: null, milestones: [],
  });
  assert.equal(await activity.recordMilestone('01a:model-call-verified'), false);
  assert.equal(await activity.trackBuildReferral(BUILD_SIGNUP_URL), false);
  assert.deepEqual(calls, []);

  await enableFixture(activity);
  assert.equal(calls[0][0], 'initialize');
  assert.equal(calls[0][1].baseUrl, 'https://activity-api.learn.nvidia.com');
  assert.deepEqual(calls[0][1].artifact, APPROVED_ARTIFACT);
  assert.equal('activity' in calls[0][1], false);
  assert.equal(typeof calls[0][1].storage.load, 'function');
});

test('a deployment with collection disabled blocks artifact and API access', async () => {
  const policy = JSON.parse(fs.readFileSync(path.join(COURSE_ROOT, 'activity-policy.json'), 'utf8'));
  policy.collection_enabled = false;
  const activity = createCourseActivity({
    policyLoader: async () => policy,
    artifactResolver: async () => assert.fail('artifact discovery must not run'),
    initialize: async () => assert.fail('Activity API must not run'),
  });
  assert.equal(isActivityPolicyApproved(policy), false);
  assert.equal(await activity.enable(), false);
  assert.equal(activity.snapshot().reason, 'policy');
});

test('source previews without a validated Pages manifest cannot start collection', async () => {
  let initialized = false;
  const activity = createCourseActivity({
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => { throw new Error('manifest missing'); },
    initialize: async () => { initialized = true; },
  });
  assert.equal(await activity.enable(), false);
  assert.equal(activity.snapshot().reason, 'artifact');
  assert.equal(initialized, false);
});

test('insecure contexts are identified before manifest access without weakening artifact validation', async () => {
  const activity = createCourseActivity({
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: () => resolveActivityArtifact({
      secureContext: false,
      fetchImpl: async () => assert.fail('insecure pages must not fetch a manifest'),
    }),
    initialize: async () => assert.fail('insecure pages must not contact the Activity API'),
  });
  assert.equal(await activity.enable(), false);
  assert.equal(activity.snapshot().reason, 'secure-context');
  await assert.rejects(resolveActivityArtifact({
    secureContext: true, cryptoImpl: {},
    fetchImpl: async () => assert.fail('missing hashing must fail before manifest access'),
  }), /Secure artifact hashing is unavailable/);
});

test('browser artifact discovery preserves same-origin authentication and blocks insecure collection', { timeout: 60000 }, async () => {
  const require = createRequire(path.resolve('scripts/runtime/package.json'));
  const { chromium } = require('playwright-core');
  const root = path.resolve('.');
  const manifest = `# ${COURSE_ID}-materialized-sha256/1 commit=${'2'.repeat(40)} adapter=${'3'.repeat(64)}\n`;
  let redirect = false;
  let manifests = 0;
  let authenticatedManifests = 0;
  let redirectTargets = 0;
  const server = http.createServer((req, res) => {
    const pathname = new URL(req.url, 'http://localhost').pathname;
    if (pathname === '/redirect-target') { redirectTargets++; res.writeHead(200).end(manifest); return; }
    if (pathname.endsWith('-sha256.txt')) {
      manifests++;
      if (!req.headers.cookie?.split('; ').includes('course_fixture=authorized')) {
        res.writeHead(403).end('authentication required'); return;
      }
      authenticatedManifests++;
      if (redirect) {
        res.writeHead(302, { location: `http://localhost:${server.address().port}/redirect-target` }).end();
      } else res.writeHead(200, { 'content-type': 'text/plain' }).end(manifest);
      return;
    }
    if (pathname.endsWith('/activity-policy.json')) {
      res.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify(APPROVED_POLICY)); return;
    }
    const file = path.resolve(root, `.${pathname}`);
    if (!file.startsWith(`${root}${path.sep}`)) { res.writeHead(403).end(); return; }
    fs.readFile(file, (error, body) => {
      if (error) { res.writeHead(404).end(); return; }
      const mime = { '.js': 'text/javascript', '.html': 'text/html', '.css': 'text/css', '.json': 'application/json' };
      res.writeHead(200, { 'content-type': mime[path.extname(file)] || 'application/octet-stream' }).end(body);
    });
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      executablePath: execFileSync('python3', ['scripts/runtime/host_browser.py'], { encoding: 'utf8' }).trim(),
      args: ['--host-resolver-rules=MAP course.test 127.0.0.1', '--no-proxy-server'],
    });
    const context = await browser.newContext();
    await context.addInitScript(() => {
      const callbacks = [];
      const chosen = () => sessionStorage.getItem('fixture-performance-consent') === 'true';
      window.OnetrustActiveGroups = chosen() ? ',C0001,C0002,' : ',C0001,';
      window.OneTrust = {
        IsAlertBoxClosed: chosen,
        OnConsentChanged: callback => callbacks.push(callback),
        RejectAll: () => {
          sessionStorage.removeItem('fixture-performance-consent');
          window.OnetrustActiveGroups = ',C0001,';
          callbacks.forEach(callback => callback());
        },
        SetAlertBoxClosed: () => sessionStorage.setItem('fixture-performance-consent', 'true'),
        UpdateConsent: (kind, value) => {
          if (kind !== 'Category' || value !== 'C0002:1') throw new Error('Only performance-cookie consent may be enabled');
          window.OnetrustActiveGroups = ',C0001,C0002,';
          callbacks.forEach(callback => callback());
        },
      };
    });
    const port = server.address().port;
    const apiRequests = [];
    let apiMode = 'blocked';
    let confirmedCount = 0;
    let confirmWrites = false;
    const confirmedIds = new Set();
    let courseCompleted = false;
    const eventWrites = [];
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.hostname === 'activity-api.learn.nvidia.com') {
        apiRequests.push({ method: route.request().method(), pathname: url.pathname });
        if (apiMode === 'blocked') return route.abort();
        const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET, POST, OPTIONS' };
        if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
        if (apiMode === 'unavailable') return route.fulfill({ status: 503, headers, json: {} });
        if (confirmWrites && url.pathname.endsWith('/updates') && route.request().method() === 'POST') {
          const event = route.request().postDataJSON(); eventWrites.push(event);
          if (event.type === 'milestone_completed') confirmedIds.add(event.payload.milestone_id);
          if (event.type === 'completed') courseCompleted = true;
        }
        const remote = confirmWrites ? { ...rawState(), completed_at: courseCompleted ? STAMP : null,
          milestones: IDS.map(milestone_id => ({ milestone_id, completed_at: confirmedIds.has(milestone_id) ? STAMP : null })),
        } : rawState(confirmedCount);
        return route.fulfill({
          status: url.pathname.endsWith('/activity-sessions') ? 201 : 200, headers,
          json: url.pathname.endsWith('/activity-sessions') ? {
            session_id: '019f38f1-e5ab-7688-af0d-0e8925299e93',
            session_token: 'fixture-browser-session-token',
            expires_at: new Date(Date.now() + 3600000).toISOString(),
          } : remote,
        });
      }
      return ['127.0.0.1', 'localhost', 'course.test'].includes(url.hostname) && url.port === String(port)
        ? route.continue() : route.abort();
    });
    await context.addCookies([{ name: 'course_fixture', value: 'authorized', url: `http://127.0.0.1:${port}` }]);
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${port}/${COURSE_ROOT}/index.html`);
    const assertActivityButton = async (count, connected = false) => {
      const button = page.locator('.activity-control-toggle');
      const optedIn = await page.evaluate(() => window.OneTrust.IsAlertBoxClosed() && window.OnetrustActiveGroups.split(',').includes('C0002'));
      assert.equal((await button.textContent()).trim(), optedIn ? `Progress ${count}/11` : 'Progress');
      assert.equal(await button.getAttribute('aria-label'), optedIn ? `Progress: ${count} / 11` : 'Progress');
      assert.equal(await button.getAttribute('title'), 'Progress');
      assert.ok(await button.evaluate((node, isConnected) => {
        const probe = document.createElement('span');
        probe.style.color = isConnected ? 'var(--g)' : 'var(--tf)';
        node.append(probe);
        const expected = getComputedStyle(probe).color;
        probe.remove();
        return getComputedStyle(node).color === expected && !node.querySelector('.activity-control-dot');
      }, connected));
    };
    const assertMilestones = async (count, savedCount = 0) => {
      assert.equal(await page.locator('[data-milestone-summary]').textContent(), `${count} / 11 milestones reached`);
      assert.equal(await page.locator('.course-milestones li').count(), 11);
      assert.equal(await page.locator('.course-milestones li[data-completed="true"]').count(), count);
      const states = await page.locator('.course-milestones .milestone-state').allTextContents();
      assert.equal(states.filter(value => value === 'Saved').length, savedCount);
      assert.equal(states.filter(value => value === 'Not yet reached').length + states.filter(value => value === 'Waiting to save').length, 11 - count);
    };
    await assertActivityButton(0);
    await page.locator('.activity-control-toggle').click();
    assert.equal(await page.locator('[data-activity-enable]').isEnabled(), true);
    assert.equal(await page.locator('[data-activity-milestones]').isVisible(), true);
    assert.equal(await page.locator('[data-activity-milestones]').evaluate(node => node.inert), true);
    assert.equal(await page.locator('[data-activity-enable]').textContent(), 'Enable Milestone Tracking');
    assert.equal(await page.locator('[data-activity-enable]').isVisible(), true);
    assert.equal(await page.locator('#activity-control-panel details, #activity-control-panel input, #activity-control-panel [data-activity-policy], #activity-control-panel [data-activity-rights]').count(), 0);
    const initialViewport = page.viewportSize();
    await page.setViewportSize({ width: 375, height: 280 });
    await page.locator('[data-activity-enable]').focus();
    const promptFits = await page.locator('[data-activity-enable]').evaluate(button => {
      const bounds = button.getBoundingClientRect();
      const stage = button.closest('.activity-progress-stage').getBoundingClientRect();
      return bounds.top >= stage.top + 4 && bounds.bottom <= stage.bottom - 4
        && bounds.top >= 0 && bounds.bottom <= innerHeight;
    });
    assert.equal(promptFits, true, 'short viewports must not clip the opt-in button or focus outline');
    await page.setViewportSize(initialViewport);
    await page.locator('[data-activity-close]').click();
    const artifact = await page.evaluate(async source => (await import(source)).resolveActivityArtifact(), `/${ACTIVITY_SOURCE}`);
    assert.equal(artifact.artifact_digest, `sha256:${createHash('sha256').update(manifest).digest('hex')}`);
    assert.ok(authenticatedManifests > 0);
    redirect = true;
    assert.equal(await page.evaluate(async source => {
      try { await (await import(source)).resolveActivityArtifact(); return false; }
      catch (_) { return true; }
    }, `/${ACTIVITY_SOURCE}`), true);
    assert.equal(redirectTargets, 0, 'manifest requests must not follow redirects');
    const before = manifests;
    await page.goto(`http://course.test:${port}/${COURSE_ROOT}/index.html`);
    assert.equal(await page.evaluate(() => globalThis.isSecureContext), false);
    await page.locator('.activity-control-toggle').click();
    await page.locator('[data-activity-enable]').click();
    await page.waitForFunction(() => window.__nemoclawActivity.snapshot().reason === 'secure-context');
    assert.equal(manifests, before, 'insecure pages must fail before manifest access');
    assert.equal(apiRequests.length, 0, 'no Activity API request is permitted in these cases');
    redirect = false;
    apiMode = 'healthy';
    const firstLesson = fs.readdirSync(COURSE_ROOT).find(name => name.startsWith('01a-') && name.endsWith('.html'));
    assert.ok(firstLesson);
    await page.goto(`http://127.0.0.1:${port}/${COURSE_ROOT}/${firstLesson}`);
    await page.locator('.activity-control-toggle').click();
    await assertMilestones(0);
    assert.equal(await page.locator('[data-activity-milestones]').isVisible(), true);
    assert.equal(await page.locator('[data-activity-milestones]').evaluate(node => node.inert), true);
    assert.equal(await page.locator('[data-activity-enable]').textContent(), 'Enable Milestone Tracking');
    assert.equal(apiRequests.length, 0, 'viewing milestones must not enable collection');
    for (const [index, milestone] of Object.values(ACTIVITY_MILESTONES).entries()) {
      const row = page.locator('.course-milestones li').nth(index);
      assert.equal(await row.locator('a').textContent(), milestone.label);
      assert.equal(await row.locator('a').getAttribute('href'), milestone.href);
      assert.ok((await row.textContent()).includes(milestone.description));
    }
    const firstMilestone = Object.values(ACTIVITY_MILESTONES)[0];
    const callout = page.locator('.course-milestone-callout');
    assert.equal(await callout.count(), 1);
    assert.ok((await callout.textContent()).includes(firstMilestone.label));
    assert.ok((await callout.textContent()).includes(firstMilestone.description));
    assert.equal(await callout.getAttribute('data-completed'), 'false');
    assert.equal(await page.locator('progress, [role="progressbar"]').count(), 0);
    assert.equal(await page.locator('.course-milestones input[type="checkbox"], .course-milestones [role="checkbox"]').count(), 0);
    await page.evaluate(() => {
      window.fixtureConsentMethods = {
        UpdateConsent: window.OneTrust.UpdateConsent,
        SetAlertBoxClosed: window.OneTrust.SetAlertBoxClosed,
      };
      delete window.OneTrust.UpdateConsent;
      delete window.OneTrust.SetAlertBoxClosed;
    });
    assert.equal(await page.locator('[data-activity-enable]').isEnabled(), true);
    await page.locator('[data-activity-enable]').click();
    assert.equal(await page.evaluate(() => window.__nemoclawActivity.snapshot().enabled), false);
    await page.evaluate(() => {
      Object.assign(window.OneTrust, window.fixtureConsentMethods);
      window.dispatchEvent(new Event('bannerLoaded'));
    });
    await page.waitForFunction(() => window.__nemoclawActivity.snapshot().enabled);
    // A later explicit rejection must supersede a click queued during SDK loading.
    await page.evaluate(() => {
      window.OneTrust.RejectAll();
      delete window.OneTrust.UpdateConsent;
      delete window.OneTrust.SetAlertBoxClosed;
    });
    await page.locator('[data-activity-enable]').click();
    await page.evaluate(() => {
      window.OneTrust.RejectAll();
      Object.assign(window.OneTrust, window.fixtureConsentMethods);
      window.dispatchEvent(new Event('bannerLoaded'));
    });
    await page.waitForTimeout(50);
    assert.equal(await page.evaluate(() => window.__nemoclawActivity.snapshot().enabled), false,
      'queued opt-in must not override a newer cookie rejection');
    await page.locator('[data-activity-enable]').click();
    await page.waitForFunction(() => window.__nemoclawActivity.snapshot().enabled);
    assert.equal(await page.locator('[data-activity-milestones]').isVisible(), true);
    assert.equal(await page.locator('[data-activity-milestones]').evaluate(node => node.inert), false);
    await assertMilestones(0);
    assert.equal(await page.locator('input[type="range"]').count(), 0, 'completion cannot be moved manually');
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('nemoclaw:api-key-verified'));
      window.dispatchEvent(new CustomEvent('nemoclaw:run-succeeded', { detail: { cellId: 'cell-onecall', hasContent: true } }));
    });
    await page.waitForFunction(() => document.querySelector('.course-milestones .milestone-state')?.textContent === 'Waiting to save');
    await assertMilestones(0);
    assert.equal(await callout.getAttribute('data-completed'), 'false');
    assert.equal(await page.locator('.course-milestones li').first().locator('.milestone-state').textContent(), 'Waiting to save');
    confirmedCount = 5;
    await page.evaluate(() => window.__nemoclawActivity.getCourseActivityState());
    await page.waitForFunction(() => document.querySelectorAll('.course-milestones li[data-completed="true"]').length === 5);
    await assertMilestones(5, 5);
    assert.equal(await callout.locator('.milestone-state').textContent(), '✓ Saved');
    await assertActivityButton(5, true);
    await page.waitForLoadState('networkidle');
    const beforeReload = apiRequests.length;
    await page.reload();
    await page.locator('.activity-control-toggle').click();
    await page.waitForFunction(() => window.__nemoclawActivity.snapshot().enabled);
    await page.waitForLoadState('networkidle');
    const resumedRequests = apiRequests.slice(beforeReload);
    assert.ok(resumedRequests.length > 0);
    assert.ok(resumedRequests.every(request => request.method === 'GET'
      && request.pathname === '/v1/activity-sessions/019f38f1-e5ab-7688-af0d-0e8925299e93/state'),
    'resume reads the saved session without creating a session or replaying stored exercise flags');
    assert.equal(await page.locator('[data-activity-enable]').isHidden(), true);
    await page.waitForFunction(() => window.__nemoclawActivity.snapshot().enabled);
    apiMode = 'unavailable';
    await page.evaluate(() => window.__nemoclawActivity.recordMilestone('01a:model-call-verified'));
    assert.equal(await page.locator('.activity-control').getAttribute('data-state'), 'unavailable');
    await assertActivityButton(5);
    await assertMilestones(5, 5);
    apiMode = 'healthy';
    confirmedCount = 7;
    await page.evaluate(() => window.__nemoclawActivity.getCourseActivityState());
    await page.waitForFunction(() => document.querySelectorAll('.course-milestones li[data-completed="true"]').length === 7);
    await assertMilestones(7, 7);
    await assertActivityButton(7, true);
    await page.evaluate(() => sessionStorage.setItem('learner-work', 'retained'));
    const beforeDisconnect = apiRequests.length;
    await page.evaluate(() => window.OneTrust.RejectAll());
    assert.equal(await page.locator('.activity-control').getAttribute('data-state'), 'off');
    await assertActivityButton(0);
    assert.equal(await page.locator('[data-activity-enable]').isVisible(), true);
    assert.equal(await page.locator('[data-activity-milestones]').isVisible(), true);
    assert.equal(await page.locator('[data-activity-milestones]').evaluate(node => node.inert), true);
    assert.equal(await page.locator('[data-activity-enable]').textContent(), 'Enable Milestone Tracking');
    assert.equal(await page.evaluate(() => Object.keys(sessionStorage).filter(key => key.startsWith('dli_activity:') && !key.includes(':evidence:')).length), 0);
    await assertMilestones(0);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('learner-work')), 'retained');
    assert.equal(apiRequests.length, beforeDisconnect, 'disconnect must work without the service');

    // The shared client writes a later ID independently and Finish remains explicit.
    confirmWrites = true;
    await page.evaluate(() => sessionStorage.clear());
    await page.goto(`http://127.0.0.1:${port}/${COURSE_ROOT}/04c-going-further.html`);
    await page.locator('#nav a').first().waitFor({ timeout: 3000 });
    await page.locator('.activity-control-toggle').click();
    await page.locator('[data-activity-enable]').click();
    await page.waitForFunction(() => window.__nemoclawActivity?.snapshot().enabled);
    const finish = page.locator('#finish-course');
    await page.waitForFunction(() => !document.querySelector('#course-finish').hidden);
    await page.waitForTimeout(200);
    const idleReads = apiRequests.filter(request => request.method === 'GET' && request.pathname.endsWith('/state')).length;
    await page.waitForTimeout(200);
    assert.equal(apiRequests.filter(request => request.method === 'GET' && request.pathname.endsWith('/state')).length, idleReads,
      'rendering Finish readiness must settle without polling the service while idle');
    assert.equal(await finish.isDisabled(), true);
    await page.evaluate(id => window.__nemoclawActivity.recordMilestone(id), IDS.at(-1));
    assert.deepEqual([...confirmedIds], [IDS.at(-1)]);
    assert.equal(await finish.isDisabled(), true);
    for (const id of IDS.slice(0, -2)) {
      assert.equal(await page.evaluate(id => window.__nemoclawActivity.recordMilestone(id), id), true);
    }
    assert.equal(confirmedIds.size, 10);
    assert.equal(await finish.isDisabled(), true);
    assert.equal(eventWrites.some(event => event.type === 'completed'), false);
    assert.equal(await page.evaluate(id => window.__nemoclawActivity.recordMilestone(id), IDS.at(-2)), true);
    await page.waitForFunction(() => !document.querySelector('#finish-course').disabled);
    assert.equal(courseCompleted, false);
    await finish.click();
    await page.waitForFunction(() => document.querySelector('#finish-course').textContent === 'Course completed');
    assert.equal(courseCompleted, true);
    assert.equal(eventWrites.filter(event => event.type === 'completed').length, 1);



  } finally {
    await browser?.close();
    await new Promise(resolve => server.close(resolve));
  }
});

test('activity policy validation rejects deleted, renamed, and malformed controls', () => {
  const variants = [
    { ...APPROVED_POLICY, collection_defaults: undefined },
    { ...APPROVED_POLICY, api_base_url: 'https://example.test' },
    { ...APPROVED_POLICY, recipient: '' },
    { ...APPROVED_POLICY, data_categories: 'course activity' },
    { ...APPROVED_POLICY, controller: { status: 'confirmed', owner: 'fixture owner' } },
    { ...APPROVED_POLICY, service_retention: { status: 'confirmed', owner: 'fixture owner' } },
    { ...APPROVED_POLICY, legal_basis: { status: 'confirmed', basis: 'fixture basis' } },
    { ...APPROVED_POLICY, sale_sharing: { status: 'confirmed', disposition: 'fixture disposition' } },
    { ...APPROVED_POLICY, privacy_center_url: 'https://example.test/privacy' },
    { ...APPROVED_POLICY, review_required: ['privacy', 'legal'] },
  ];
  for (const policy of variants) assert.throws(() => validateActivityPolicy(policy));
  assert.equal(isActivityPolicyApproved(APPROVED_POLICY), true);
});

test('unavailable session storage keeps one activity session in memory', async () => {
  const requests = [];
  const storageTarget = {
    getItem() { throw new DOMException('denied', 'SecurityError'); },
    setItem() { throw new DOMException('denied', 'SecurityError'); },
    removeItem() { throw new DOMException('denied', 'SecurityError'); },
  };
  let recorded = false;
  const fetchImpl = async (url, init) => {
    requests.push([url, init]);
    if (url.endsWith('/v1/activity-sessions')) {
      return new Response(JSON.stringify({
        session_id: '019f38f1-e5ab-7688-af0d-0e8925299e93',
        session_token: 'opaque-session-token-with-safe-length',
        expires_at: '2026-09-09T20:00:00Z',
      }), { status: 201 });
    }
    if (url.endsWith('/state')) {
      return new Response(JSON.stringify(rawState(recorded ? 1 : 0)), { status: 200 });
    }
    recorded = true;
    return new Response(JSON.stringify({ state: rawState(1) }), { status: 201 });
  };
  const activity = createCourseActivity({
    fetchImpl,
    storageTarget,
    now: () => new Date('2026-09-09T19:00:00Z'),
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
  });

  await enableFixture(activity);
  assert.equal(await activity.recordMilestone('01a:model-call-verified'), true);
  assert.equal(requests.filter(([url]) => url.endsWith('/v1/activity-sessions')).length, 1);
});

test('tab choices resume only for the same delivered artifact and notice, and disconnect clears them', async () => {
  const values = new Map();
  const storageTarget = {
    getItem: key => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
  let sessions = 0;
  const create = (artifact = APPROVED_ARTIFACT, policy = APPROVED_POLICY) => createCourseActivity({
    storageTarget, artifactResolver: async () => artifact, policyLoader: async () => policy,
    initialize: async () => {
      sessions += 1;
      return { getState: async () => (confirmedState(1)) };
    },
  });
  const first = create();
  assert.equal(await first.resume(), false);
  assert.equal(sessions, 0);
  assert.equal(await first.enable(), true);
  first.setReferralTracking(true);
  assert.equal(await create({ ...APPROVED_ARTIFACT, artifact_digest: `sha256:${'c'.repeat(64)}` }).resume(), false);
  assert.equal(await create(APPROVED_ARTIFACT, { ...APPROVED_POLICY, notice_version: 'changed' }).resume(), false);
  assert.equal(await create(APPROVED_ARTIFACT, { ...APPROVED_POLICY, collection_enabled: false }).resume(), false);
  assert.equal(sessions, 1);
  const nextPage = create();
  assert.equal(await nextPage.resume(), true);
  assert.equal(nextPage.snapshot().referralTracking, true);
  nextPage.disconnect();
  assert.equal(await create().resume(), false);
  assert.equal(values.size, 0);
  assert.equal(sessions, 2);
});

test('reaccepting consent can establish a new connection before the withdrawn attempt settles', async () => {
  let releaseOld;
  let enteredOld;
  const oldPending = new Promise(resolve => { releaseOld = resolve; });
  const entered = new Promise(resolve => { enteredOld = resolve; });
  let initializations = 0;
  const activity = createCourseActivity({ storageTarget: null,
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => {
      initializations++;
      if (initializations === 1) { enteredOld(); await oldPending; }
      return { getState: async () => confirmedState() };
    },
  });
  const oldAttempt = activity.enable(); await entered;
  activity.disconnect();
  const newAttempt = activity.enable();
  await new Promise(resolve => setImmediate(resolve));
  const startedFresh = initializations === 2;
  releaseOld();
  assert.equal(await oldAttempt, false);
  assert.equal(await newAttempt, true);
  assert.equal(startedFresh, true);
  assert.equal(activity.snapshot().enabled, true);
  activity.disconnect();
});

test('a withdrawn state read cannot discard the replacement Activity facade', async () => {
  let releaseOld; let enteredOld;
  const oldState = new Promise(resolve => { releaseOld = resolve; });
  const entered = new Promise(resolve => { enteredOld = resolve; });
  let initializations = 0;
  const activity = createCourseActivity({ storageTarget: null,
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => {
      const first = ++initializations === 1;
      return { getState: async () => {
        if (first) { enteredOld(); return oldState; }
        return confirmedState();
      } };
    },
  });
  const oldAttempt = activity.enable(); await entered;
  activity.disconnect();
  assert.equal(await activity.enable(), true);
  releaseOld(confirmedState()); assert.equal(await oldAttempt, false);
  assert.ok(await activity.getCourseActivityState());
  assert.equal(initializations, 2, 'refresh must reuse the replacement facade');
  activity.disconnect();
});

test('concurrent enable requests share one remote session initialization', async () => {
  let release;
  let initializationCount = 0;
  const waiting = new Promise(resolve => { release = resolve; });
  const activity = createCourseActivity({
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => {
      initializationCount += 1;
      await waiting;
      return { getState: async () => (confirmedState()) };
    },
  });

  const first = activity.enable();
  const second = activity.enable();
  release();
  assert.deepEqual(await Promise.all([first, second]), [true, true]);
  assert.equal(initializationCount, 1);
});

test('disconnect invalidates an in-flight enable and clears its session state', async () => {
  let release;
  let enter;
  const waiting = new Promise(resolve => { release = resolve; });
  const entered = new Promise(resolve => { enter = resolve; });
  const stored = new Map();
  const removed = [];
  const activity = createCourseActivity({
    storageTarget: {
      getItem: key => stored.get(key) || null,
      setItem: (key, value) => stored.set(key, value),
      removeItem: key => { removed.push(key); stored.delete(key); },
    },
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async options => {
      enter();
      await waiting;
      options.storage.save({
        session_id: '019f38f1-e5ab-7688-af0d-0e8925299e93',
        session_token: 'late-session-token-with-safe-length',
        expires_at: '2026-09-09T20:00:00Z',
      });
      return { getState: async () => (confirmedState()) };
    },
  });

  const enabling = activity.enable();
  await entered;
  activity.disconnect();
  release();
  assert.equal(await enabling, false);
  assert.equal(activity.snapshot().phase, 'off');
  assert.equal(activity.snapshot().enabled, false);
  assert.equal(stored.size, 0);
  assert.equal(removed.length, 2, 'disconnect clears the session and tab choice once each');
  assert.equal(new Set(removed).size, 2, 'retired storage must not clear a later connection');
});

for (const stage of ['policyLoader', 'artifactResolver']) {
  test(`disconnect preserves local state when a pending ${stage} fails`, async () => {
    let enter;
    let reject;
    const entered = new Promise(resolve => { enter = resolve; });
    const pending = new Promise((_, fail) => { reject = fail; });
    const activity = createCourseActivity({
      policyLoader: async () => APPROVED_POLICY,
      artifactResolver: async () => APPROVED_ARTIFACT,
      [stage]: () => { enter(); return pending; },
      initialize: () => assert.fail('disconnected preflight must not initialize the API'),
    });
    const enabling = activity.enable();
    await entered;
    activity.disconnect();
    const disconnected = activity.snapshot();
    reject(new Error('late preflight failure'));
    assert.equal(await enabling, false);
    assert.deepEqual(activity.snapshot(), disconnected);
  });
}

test('disconnect prevents queued progress and completion from starting', async () => {
  const { activity, calls } = createFixture({ count: 11 });
  await enableFixture(activity);
  calls.length = 0;
  const progress = activity.recordMilestone('01a:model-call-verified');
  const completion = activity.recordCompletion();
  activity.disconnect();
  assert.deepEqual(await Promise.all([progress, completion]), [false, false]);
  assert.deepEqual(calls, []);
});

test('disconnect cancels an in-flight request and blocks queued SDK writes and refresh', async () => {
  const stored = new Map();
  const requests = [];
  let release;
  let enter;
  let heldSignal;
  const entered = new Promise(resolve => { enter = resolve; });
  const waiting = new Promise(resolve => { release = resolve; });
  const response = (body, status = 200) => new Response(JSON.stringify(body), { status });
  const activity = createCourseActivity({
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    storageTarget: {
      getItem: key => stored.get(key) || null,
      setItem: (key, value) => stored.set(key, value),
      removeItem: key => stored.delete(key),
    },
    fetchImpl: async (url, options) => {
      requests.push(url);
      if (url.endsWith('/v1/activity-sessions')) return response({
        session_id: '019f38f1-e5ab-7688-af0d-0e8925299e93',
        session_token: 'fixture-session-token-safe-length',
        expires_at: '2099-01-01T00:00:00Z',
      }, 201);
      if (url.endsWith('/state')) return response(rawState());
      heldSignal = options.signal;
      enter();
      await waiting;
      // A response that wins the abort race must not start authentication refresh.
      return response({}, 401);
    },
  });
  await enableFixture(activity);
  const first = activity.recordMilestone('01a:model-call-verified');
  const queued = activity.recordMilestone('01b:react-loop-complete');
  await entered;
  const countAtDisconnect = requests.length;
  activity.disconnect();
  assert.equal(heldSignal.aborted, true);
  assert.equal(activity.snapshot().phase, 'off');
  assert.equal(stored.size, 0);
  await enableFixture(activity);
  const reconnectedCount = requests.length;
  const reconnectedStorage = [...stored];
  assert.equal(reconnectedCount, countAtDisconnect + 2);
  release();
  assert.deepEqual(await Promise.all([first, queued]), [false, false]);
  assert.equal(requests.length, reconnectedCount, 'retired connection cannot issue requests after reconnect');
  assert.deepEqual([...stored], reconnectedStorage, 'retired connection cannot alter the new session');
  assert.equal(activity.snapshot().phase, 'connected');
});

test('the approved NVIDIA Build destination records one referral', async () => {
  const { activity, calls } = createFixture();

  await enableFixture(activity);
  activity.setReferralTracking(true);
  await activity.trackBuildReferral(BUILD_SIGNUP_URL);

  assert.deepEqual(calls.findLast(call => call[0] === 'referral'), ['referral', {
    referenceId: 'build:nvidia-api-key',
    destinationUrl: BUILD_SIGNUP_URL,
    idempotencyKey: `${COURSE_ID}:referral:build:nvidia-api-key`,
  }]);
});

test('referrals remain off after progress sync is enabled', async () => {
  const { activity, calls } = createFixture();
  await enableFixture(activity);

  assert.equal(await activity.trackBuildReferral(BUILD_SIGNUP_URL), false);
  assert.equal(calls.some(call => call[0] === 'referral'), false);
});

test('withdrawn referral consent cancels a queued selection before it writes', async () => {
  const { activity, calls } = createFixture();
  await enableFixture(activity);
  activity.setReferralTracking(true);
  const selected = activity.trackBuildReferral(BUILD_SIGNUP_URL);
  activity.setReferralTracking(false);
  assert.equal(await selected, false);
  assert.equal(calls.some(call => call[0] === 'referral'), false);
});

test('Global Privacy Control blocks referrals at the activity facade', async () => {
  const activity = createCourseActivity({
    globalPrivacyControl: true,
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => ({
      getState: async () => (confirmedState()),
      referral: () => assert.fail('GPC must block referral calls outside the toolbar too'),
    }),
  });
  await enableFixture(activity);
  assert.equal(activity.setReferralTracking(true), false);
  assert.equal(await activity.trackBuildReferral(BUILD_SIGNUP_URL), false);
  assert.equal(activity.snapshot().referralTracking, false);
});

test('an unapproved destination is not recorded as a referral', async () => {
  const { activity, calls } = createFixture();

  await enableFixture(activity);
  activity.setReferralTracking(true);
  assert.equal(await activity.trackBuildReferral('https://attacker.example'), false);
  assert.equal(calls.filter(call => call[0] === 'referral').length, 0);
});

test('a later milestone writes its own ID without awarding earlier milestones', async () => {
  const { activity, calls } = createFixture();
  await enableFixture(activity);
  assert.equal(await activity.recordMilestone('02b:grounded-answer-complete'), true);
  assert.deepEqual(calls.find(call => call[0] === 'completeMilestone'), ['completeMilestone', '02b:grounded-answer-complete', {
    idempotencyKey: `${COURSE_ID}:milestone:02b:grounded-answer-complete`,
  }]);
  assert.deepEqual(activity.snapshot().milestones.filter(marker => marker.completedAt !== null).map(marker => marker.milestoneId), ['02b:grounded-answer-complete']);
});

test('explicit completion requires all configured IDs confirmed by the server', async () => {
  const { activity, calls, setState } = createFixture({ count: 10 });
  await enableFixture(activity);
  assert.equal(await activity.recordCompletion(), false);
  assert.equal(calls.some(call => call[0] === 'complete'), false);
  setState(confirmedState(11));
  assert.equal(await activity.recordCompletion(), true);
  assert.equal(activity.snapshot().completedAt, STAMP);
});

test('invalid or duplicated milestone policies cannot fabricate completion', async () => {
  const missing = confirmedState(11); missing.milestones.pop();
  const duplicate = confirmedState(11); duplicate.milestones[0] = { ...duplicate.milestones[1] };
  const unknown = confirmedState(11); unknown.milestones[0].milestoneId = 'unknown-id';
  const invalid = confirmedState(11); invalid.milestones[0].completedAt = 'not-a-timestamp';
  for (const remote of [missing, duplicate, unknown, invalid]) {
    const { activity, setState } = createFixture();
    setState(remote);
    assert.equal(await activity.enable(), false);
    assert.equal(activity.snapshot().phase, 'unavailable');
    assert.equal(activity.snapshot().milestonesCheckedAt, undefined);
  }
});

test('a submitted milestone receives no checkmark until state confirms its timestamp', async () => {
  let submitted = false;
  let remote = confirmedState();
  const activity = createCourseActivity({ policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => ({ getState: async () => remote, completeMilestone: async () => { submitted = true; } }),
  });
  await enableFixture(activity);
  assert.equal(await activity.recordMilestone(IDS[0]), false);
  assert.equal(submitted, true);
  assert.equal(activity.snapshot().milestones.filter(marker => marker.completedAt !== null).length, 0);
  remote = confirmedState(1);
  await activity.getCourseActivityState();
  assert.equal(activity.snapshot().milestones[0].completedAt, STAMP);
});

test('refresh preserves confirmed milestones on failure and publishes recovery', async () => {
  let unavailable = false;
  let remote = confirmedState(3);
  const activity = createCourseActivity({ policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => ({ getState: async () => { if (unavailable) throw new Error('unavailable'); return remote; } }),
  });
  await enableFixture(activity);
  const checked = activity.snapshot().milestonesCheckedAt;
  unavailable = true;
  assert.equal(await activity.getCourseActivityState(), null);
  assert.equal(activity.snapshot().phase, 'unavailable');
  assert.deepEqual(activity.snapshot().milestones, confirmedState(3).milestones);
  assert.equal(activity.snapshot().milestonesCheckedAt, checked);
  unavailable = false; remote = confirmedState(5);
  assert.deepEqual(await activity.getCourseActivityState(), remote);
  assert.equal(activity.snapshot().phase, 'connected');
});

test('queued refreshes publish in order and recover after a failed read', async () => {
  let pending = null;
  const activity = createCourseActivity({ policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => ({ getState: () => pending ? new Promise((resolve, reject) => pending.push({ resolve, reject })) : Promise.resolve(confirmedState(1)) }),
  });
  await enableFixture(activity);
  for (const failOlder of [false, true]) {
    pending = [];
    const older = activity.getCourseActivityState(); const newer = activity.getCourseActivityState();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(pending.length, 1, 'the second SDK read waits for the first');
    if (failOlder) pending[0].reject(new Error('temporary read failure')); else pending[0].resolve(confirmedState(3));
    await older;
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(pending.length, 2);
    pending[1].resolve(confirmedState(7)); await newer;
    assert.deepEqual(activity.snapshot().milestones, confirmedState(7).milestones);
    assert.equal(activity.snapshot().phase, 'connected');
  }
});

test('facade failures remain contained and retryable at the lesson boundary', async () => {
  let attempts = 0;
  const activity = createCourseActivity({ policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => ({ getState: async () => confirmedState(11), complete: async () => { attempts++; throw new Error('unavailable'); } }),
  });
  await enableFixture(activity);
  assert.equal(await activity.recordCompletion(), false);
  assert.equal(await activity.recordCompletion(), false);
  assert.equal(attempts, 2);
});

test('Module 1a explicitly wires session, referral, and verified progress events', () => {
  const page = fs.readFileSync(path.join(COURSE_ROOT, '01a-loop.html'), 'utf8');

  assert.match(page, new RegExp(`${COURSE_ID}:api-key-verified`));
  assert.doesNotMatch(page, /recordApiKeyVerified/);
});

test('the published notice permits consented collection and keeps both opt-in defaults off', () => {
  const policy = JSON.parse(fs.readFileSync(path.join(COURSE_ROOT, 'activity-policy.json'), 'utf8'));
  assert.equal(isActivityPolicyApproved(policy), true);
  assert.equal(isActivityPolicyApproved({ ...policy, collection_enabled: false }), false);
  for (const key of Object.keys(policy)) {
    const missing = { ...policy }; delete missing[key];
    assert.throws(() => validateActivityPolicy(missing), key);
    assert.throws(() => validateActivityPolicy({ ...missing, [`renamed_${key}`]: policy[key] }), key);
  }
  for (const base_path of ['https://example.test/api', '//example.test/api', '/api/../redirect', '/api/path?url=https://example.test', '/api/%2e%2e/path']) {
    assert.throws(() => validateActivityPolicy({ ...policy, lab_transport: { base_path, allow_http: true } }));
  }
  assert.throws(() => validateActivityPolicy({ ...policy, api_base_url: 'http://activity-api.learn.nvidia.com' }));
  assert.throws(() => validateActivityPolicy({ ...policy, collection_defaults: { progress_sync: 'on', referral_tracking: 'off' } }));
});

test('HTTP lab transport requires deployment permission and preserves authenticated HTTPS SDK semantics', async () => {
  const policy = JSON.parse(fs.readFileSync(path.join(COURSE_ROOT, 'activity-policy.json'), 'utf8'));
  policy.collection_enabled = true;
  policy.lab_transport = { base_path: '/lab/api/course/activity', allow_http: true };
  const identity = { ...APPROVED_ARTIFACT, artifact_version: `git-${'a'.repeat(40)}-adapter-${'b'.repeat(64)}` };
  const requests = [];
  let sdkOptions;
  const make = p => createCourseActivity({
    policyLoader: async () => p,
    locationHref: 'http://lab.example.test/lab/static/web/nemoclaw/index.html',
    cryptoImpl: {},
    fetchImpl: async (url, options) => {
      requests.push({ url, options });
      return { ok: true, url, json: async () => ({ artifact: identity, xsrf_token: 'fixture-xsrf' }) };
    },
    initialize: async options => {
      sdkOptions = options;
      return { getState: async () => (confirmedState()) };
    },
  });
  const blocked = make({ ...policy, lab_transport: { ...policy.lab_transport, allow_http: false } });
  assert.equal(await blocked.enable(), false);
  assert.equal(requests.length, 0);
  const activity = make(policy);
  await activity.getPolicy();
  assert.equal(requests.length, 0, 'no session or manifest access before consent');
  assert.equal(await activity.enable(), true);
  assert.deepEqual(sdkOptions.artifact, identity);
  assert.equal(sdkOptions.baseUrl, 'https://activity-api.learn.nvidia.com');
  await sdkOptions.fetchImpl('https://activity-api.learn.nvidia.com/v1/activity-sessions', {
    method: 'POST', headers: { Authorization: 'Bearer fixture-activity', 'Idempotency-Key': 'fixture-key' },
  });
  const last = requests.at(-1);
  assert.equal(last.url, 'http://lab.example.test/lab/api/course/activity/v1/activity-sessions');
  assert.equal(last.options.credentials, 'same-origin');
  assert.equal(last.options.headers.get('Authorization'), null);
  assert.equal(last.options.headers.get('X-Activity-Authorization'), 'Bearer fixture-activity');
  assert.equal(last.options.headers.get('X-XSRFToken'), 'fixture-xsrf');
  await assert.rejects(sdkOptions.fetchImpl('https://example.test/v1/activity-sessions', {}), /Unexpected Activity destination/);
  activity.disconnect();
});
}

test('course adapter writes independent milestones with the shared JavaScript facade', () => {
  const source = fs.readFileSync('web/nemoclaw/scripts/_activity.js', 'utf8');
  assert.match(source, /activity\.completeMilestone\(milestoneRef/);
  assert.doesNotMatch(source, /progressPercent|activity\.progress\(/);
});

test('concurrent authentication renewal cannot move live exercise evidence into a replacement session', async () => {
  const { createCourseActivity } = await import('../../web/nemoclaw/scripts/_activity.js');
  const { installCourseActivityTracking } = await import('../../web/nemoclaw/scripts/_activity_runtime.js');
  const sessionA = '019f38f1-e5ab-7688-af0d-0e8925299e93';
  const sessionB = '019f38f1-e5ab-7688-af0d-0e8925299e94';
  const config = { milestones: Object.keys((await import('../../web/nemoclaw/scripts/_activity.js')).ACTIVITY_MILESTONES).map(id => ({ id })) };
  const writes = [];
  const marked = new Set();
  let sessions = 0; let readsA = 0; let readsB = 0;
  let releaseOld; let releaseNew; let enterReplacement;
  const heldOld = new Promise(resolve => { releaseOld = resolve; });
  const heldNew = new Promise(resolve => { releaseNew = resolve; });
  const replacementEntered = new Promise(resolve => { enterReplacement = resolve; });
  const response = (body, status = 200) => new Response(JSON.stringify(body), { status });
  const remote = session_id => ({ session_id, completed_at: null, milestones: config.milestones.map(({ id: milestone_id }) => ({
    milestone_id, completed_at: marked.has(`${session_id}:${milestone_id}`) ? '2026-10-12T12:00:00Z' : null,
  })) });
  const policy = JSON.parse(fs.readFileSync('web/nemoclaw/activity-policy.json', 'utf8'));
  policy.collection_enabled = true;
  const activity = createCourseActivity({ storageTarget: null,
    policyLoader: async () => policy,
    artifactResolver: async () => ({ artifact_id: 'artifact_nemoclaw_web', artifact_version: `git-${'a'.repeat(40)}`, artifact_digest: `sha256:${'b'.repeat(64)}` }),
    fetchImpl: async (url, options) => {
      if (url.endsWith('/activity-sessions')) return response({ session_id: ++sessions === 1 ? sessionA : sessionB,
        session_token: 'fixture-session-token-long-enough', expires_at: '2099-01-01T00:00:00Z' }, 201);
      if (url.endsWith('/updates')) {
        const id = JSON.parse(options.body).payload.milestone_id;
        writes.push({ url, id }); marked.add(`${url.includes(sessionA) ? sessionA : sessionB}:${id}`);
        return response({});
      }
      if (url.includes(sessionA) && url.endsWith('/state')) {
        if (++readsA === 2) return heldOld;
        if (readsA === 3) return response({}, 401);
        return response(remote(sessionA));
      }
      if (url.includes(sessionB) && url.endsWith('/state')) {
        if (++readsB === 1) { enterReplacement(); return heldNew; }
        return response(remote(sessionB));
      }
      throw new Error(`unexpected fixture request: ${url}`);
    },
  });
  assert.equal(await activity.enable(), true);
  const previous = Object.getOwnPropertyDescriptor(globalThis, 'location');
  Object.defineProperty(globalThis, 'location', { configurable: true, value: { pathname: '/nemoclaw/03b-openclaw.html' } });
  const windowTarget = new EventTarget(); const documentTarget = new EventTarget();
  windowTarget.OneTrust = { IsAlertBoxClosed: () => true, OnConsentChanged: () => {} };
  windowTarget.OnetrustActiveGroups = ",C0001,C0002,";
  installCourseActivityTracking({ windowTarget, documentTarget, activity, storageTarget: null });
  const emit = cellId => { const event = new Event('nemoclaw:run-succeeded'); event.detail = { cellId }; windowTarget.dispatchEvent(event); };
  const flush = () => new Promise(resolve => setImmediate(resolve));
  try {
    emit('cell-introspect'); emit('cell-workspace-term'); await flush();
    const concurrent = activity.getCourseActivityState(); await flush();
    releaseOld(response(remote(sessionA)));
    await replacementEntered; await flush(); await flush();
    const crossedBeforePublish = writes.some(write => write.url.includes(sessionB));
    releaseNew(response(remote(sessionB))); await concurrent; await flush(); await flush();
    assert.equal(crossedBeforePublish, false, 'old evidence must not write while the replacement state is pending');
    assert.equal(writes.some(write => write.url.includes(sessionB)), false, 'old evidence must be dropped after replacement');
    assert.equal(activity.snapshot().sessionId, sessionB);
    emit('cell-introspect'); emit('cell-workspace-term');
    await flush(); await flush(); await flush();
    assert.equal(writes.filter(write => write.url.includes(sessionB)).length, 1, 'fresh work may save in the replacement session');
  } finally {
    releaseOld(response(remote(sessionA))); releaseNew(response(remote(sessionB))); activity.disconnect();
    if (previous) Object.defineProperty(globalThis, 'location', previous); else delete globalThis.location;
  }
});

test('a failed SDK write that renews authentication cannot transfer the next pending milestone', async () => {
  const { createCourseActivity } = await import('../../web/nemoclaw/scripts/_activity.js');
  const config = { milestones: Object.keys((await import('../../web/nemoclaw/scripts/_activity.js')).ACTIVITY_MILESTONES).map(id => ({ id })) };
  const policy = JSON.parse(fs.readFileSync('web/nemoclaw/activity-policy.json', 'utf8')); policy.collection_enabled = true;
  const sessionA = '019f38f1-e5ab-7688-af0d-0e8925299e93';
  const sessionB = '019f38f1-e5ab-7688-af0d-0e8925299e94';
  let sessions = 0;
  const marked = new Set(); const writes = [];
  const response = (body, status = 200) => new Response(JSON.stringify(body), { status });
  const activity = createCourseActivity({ storageTarget: null,
    policyLoader: async () => policy,
    artifactResolver: async () => ({ artifact_id: 'artifact_nemoclaw_web', artifact_version: `git-${'a'.repeat(40)}`, artifact_digest: `sha256:${'b'.repeat(64)}` }),
    fetchImpl: async (url, options) => {
      if (url.endsWith('/activity-sessions')) return response({ session_id: ++sessions === 1 ? sessionA : sessionB,
        session_token: 'fixture-session-token-long-enough', expires_at: '2099-01-01T00:00:00Z' }, 201);
      if (url.endsWith('/state')) return response({ session_id: url.includes(sessionA) ? sessionA : sessionB, completed_at: null,
        milestones: config.milestones.map(({ id: milestone_id }) => ({ milestone_id, completed_at: marked.has(milestone_id) ? '2026-10-12T12:00:00Z' : null })),
      });
      if (url.includes(sessionA)) return response({}, 401);
      const id = JSON.parse(options.body).payload.milestone_id; writes.push(id); marked.add(id); return response({});
    },
  });
  try {
    assert.equal(await activity.enable(), true);
    assert.equal(await activity.recordMilestone(config.milestones[0].id), false);
    assert.equal(sessions, 2, 'the failed SDK write already replaced its private session');
    assert.equal(await activity.recordMilestone(config.milestones[1].id), false);
    assert.deepEqual(writes, [], 'pending evidence from the old published session cannot use the hidden replacement');
    assert.equal(activity.snapshot().sessionId, sessionB);
    assert.equal(await activity.recordMilestone(config.milestones[1].id), true, 'fresh work can use the confirmed replacement');
    assert.deepEqual(writes, [config.milestones[1].id]);
  } finally { activity.disconnect(); }
});

function consentFixture({ groups = ',C0001,', chosen = false, loaded = true } = {}) {
  const windowTarget = new EventTarget();
  let consentChanged;
  if (loaded) windowTarget.OneTrust = {
    IsAlertBoxClosed: () => chosen,
    OnConsentChanged: callback => { consentChanged = callback; },
  };
  windowTarget.OnetrustActiveGroups = groups;
  let enabled = false;
  const calls = [];
  const activity = {
    snapshot: () => ({ enabled, phase: enabled ? 'connected' : 'off' }),
    resume: async () => false,
    enable: async () => { calls.push('enable'); enabled = true; return true; },
    disconnect: () => { calls.push('disconnect'); enabled = false; },
  };
  const syncLocal = async () => { calls.push('sync'); };
  const change = (nextGroups, nextChosen = true) => {
    windowTarget.OnetrustActiveGroups = nextGroups; chosen = nextChosen;
    consentChanged?.();
  };
  return { windowTarget, activity, calls, syncLocal, change };
}
const flushConsent = async () => { await new Promise(resolve => setImmediate(resolve)); };

async function bindConsent(fixture) {
  const runtime = await import('../../web/nemoclaw/scripts/_activity_runtime.js');
  assert.equal(typeof runtime.bindNemoClawProgressConsent, 'function', 'course runtime needs a consent bridge');
  return runtime.bindNemoClawProgressConsent(fixture);
}

test('performance consent requires a valid saved choice, not a default active category', async () => {
  const fixture = consentFixture({ groups: ',C0001,C0002,', chosen: false });
  await bindConsent(fixture); await flushConsent();
  assert.equal(fixture.calls.includes('enable'), false);
  fixture.change(',C0001,C0002,'); await flushConsent();
  assert.deepEqual(fixture.calls.filter(call => call !== 'disconnect'), ['enable', 'sync']);
});

test('saved performance consent enables progress once and ignores unrelated category changes', async () => {
  const fixture = consentFixture({ groups: ',C0001,C0002,', chosen: true });
  await bindConsent(fixture); await flushConsent();
  fixture.change(',C0001,C0002,C0003,'); await flushConsent();
  assert.equal(fixture.calls.filter(call => call === 'enable').length, 1);
  assert.equal(fixture.calls.filter(call => call === 'sync').length, 1);
});

test('rejecting or withdrawing performance consent stops progress and later acceptance reconnects', async () => {
  const fixture = consentFixture({ groups: ',C0001,C0002,', chosen: true });
  await bindConsent(fixture); await flushConsent();
  fixture.change(',C0001,C0003,');
  assert.equal(fixture.activity.snapshot().enabled, false);
  fixture.change(',C0001,C0002,'); await flushConsent();
  assert.equal(fixture.activity.snapshot().enabled, true);
  assert.equal(fixture.calls.filter(call => call === 'enable').length, 2);
});

test('missing or delayed CMP fails closed and bannerLoaded reconciles late initialization', async () => {
  const fixture = consentFixture({ loaded: false, groups: ',C0001,C0002,', chosen: true });
  await bindConsent(fixture); await flushConsent();
  assert.equal(fixture.calls.includes('enable'), false);
  fixture.windowTarget.OneTrust = { IsAlertBoxClosed: () => true, OnConsentChanged: () => {} };
  fixture.windowTarget.dispatchEvent(new Event('bannerLoaded')); await flushConsent();
  assert.equal(fixture.calls.includes('enable'), true);
});

test('withdrawal while enabling cannot sync a stale connection', async () => {
  const fixture = consentFixture({ groups: ',C0001,C0002,', chosen: true });
  let finish;
  fixture.activity.enable = () => new Promise(resolve => { finish = resolve; fixture.calls.push('enable'); });
  await bindConsent(fixture); await flushConsent();
  fixture.change(',C0001,');
  finish(true); await flushConsent();
  assert.equal(fixture.calls.includes('disconnect'), true);
  assert.equal(fixture.calls.includes('sync'), false);
});

test('malformed category identifiers do not grant performance consent', async () => {
  const fixture = consentFixture({ groups: ',C0001,C00020,', chosen: true });
  await bindConsent(fixture); await flushConsent();
  assert.equal(fixture.calls.includes('enable'), false);
});

 test('saved CMP consent resumes the matching Activity choice before making a fresh opt-in', async () => {
  const fixture = consentFixture({ groups: ',C0001,C0002,', chosen: true });
  fixture.activity.resume = async () => { fixture.calls.push('resume'); return true; };
  await bindConsent(fixture); await flushConsent();
  assert.deepEqual(fixture.calls, ['resume', 'sync']);
});

test('waiting for the CMP preserves stored choices while an off adapter cannot collect', async () => {
  const fixture = consentFixture({ loaded: false, groups: undefined });
  await bindConsent(fixture); await flushConsent();
  assert.deepEqual(fixture.calls, []);
  fixture.windowTarget.OneTrust = { IsAlertBoxClosed: () => true, OnConsentChanged: () => {} };
  fixture.windowTarget.OnetrustActiveGroups = ',C0001,C0002,';
  fixture.activity.resume = async () => { fixture.calls.push('resume'); return true; };
  fixture.windowTarget.dispatchEvent(new Event('bannerLoaded')); await flushConsent();
  assert.deepEqual(fixture.calls, ['resume', 'sync']);
});

test('loss of the CMP cancels a pending consent connection before its phase becomes connecting', async () => {
  const fixture = consentFixture({ groups: ',C0001,C0002,', chosen: true });
  let finish;
  fixture.activity.enable = () => new Promise(resolve => { finish = resolve; });
  await bindConsent(fixture); await flushConsent();
  delete fixture.windowTarget.OneTrust;
  fixture.windowTarget.dispatchEvent(new Event('bannerLoaded'));
  assert.deepEqual(fixture.calls, ['disconnect']);
  finish(true); await flushConsent();
  assert.equal(fixture.calls.includes('sync'), false);
});
