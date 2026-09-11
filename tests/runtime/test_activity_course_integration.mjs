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

const COURSE_ROOTS = fs.readdirSync('web', { withFileTypes: true })
  .filter(entry => entry.isDirectory() && (fs.existsSync(path.join('web', entry.name, 'activity-policy.json'))
    || fs.existsSync(path.join('web', entry.name, 'scripts', '_activity.js'))))
  .map(entry => path.join('web', entry.name));
assert.ok(COURSE_ROOTS.length, 'expected discovered Activity course contracts');
for (const COURSE_ROOT of COURSE_ROOTS) {
const COURSE_ID = path.basename(COURSE_ROOT);
const ACTIVITY_SOURCE = path.join(COURSE_ROOT, 'scripts', '_activity.js');
const ACTIVITY_RUNTIME_SOURCE = path.join(COURSE_ROOT, 'scripts', '_activity_runtime.js');
const activityModule = await import(pathToFileURL(path.resolve(ACTIVITY_SOURCE)));

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

function createFixture({ progressPercent = 10 } = {}) {
  const calls = [];
  const facade = {
    progress: async (...args) => { calls.push(['progress', ...args]); },
    referral: async (...args) => { calls.push(['referral', ...args]); },
    getState: async () => {
      calls.push(['getState']);
      return { progressPercent, completedAt: null };
    },
    complete: async (...args) => {
      calls.push(['complete', ...args]);
      return progressPercent === 100 ? { written: true } : { written: false };
    },
  };
  const activity = createCourseActivity({
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async options => {
      calls.push(['initialize', options]);
      return facade;
    },
  });
  return { activity, calls, setProgress: value => { progressPercent = value; } };
}

async function enableFixture(activity) {
  assert.equal(await activity.enable(), true);
}

test('the course imports only the public activity facade and contains no alternate hostnames', () => {
  const source = fs.readFileSync(ACTIVITY_SOURCE, 'utf8');
  const publicSource = fs.readFileSync(ACTIVITY_RUNTIME_SOURCE, 'utf8')
    + fs.readFileSync(path.join(COURSE_ROOT, '04c-going-further.html'), 'utf8') + source;

  assert.match(source, /import \{ DLIActivity \}/);
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
        return { getState: async () => ({ progressPercent: 0, completedAt: null }) };
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
    assert.equal(
      fs.readFileSync(path.resolve(courseRoot, 'scripts', '../../shared/activity-sdk.js'), 'utf8'),
      fs.readFileSync('web/shared/activity-sdk.js', 'utf8'),
    );
  }
});

test('the complete candidate diff contains no private or non-production activity configuration', () => {
  const candidateBase = execFileSync(
    'git', ['merge-base', 'origin/main', 'HEAD'], { encoding: 'utf8' },
  ).trim();
  const committedDiff = execFileSync(
    'git', ['diff', '--no-ext-diff', '--unified=0', candidateBase, 'HEAD'], { encoding: 'utf8' },
  );
  const worktreeDiff = execFileSync(
    'git', ['diff', '--no-ext-diff', '--unified=0', 'HEAD'], { encoding: 'utf8' },
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
  assert.doesNotMatch(candidateDiff, unsafeLabel);
  assert.doesNotMatch(candidateDiff, privateTerm);
  assert.doesNotMatch(candidateDiff, credentialShape);
});

test('the milestone registry defines one increasing cumulative progress model', () => {
  const progress = Object.values(ACTIVITY_MILESTONES).map(value => value.progressPercent);
  assert.equal(progress.length, 11);
  assert.deepEqual(progress, [...progress].sort((left, right) => left - right));
  assert.equal(progress.at(-1), 100);
  assert.deepEqual(
    Object.fromEntries(Object.entries(ACTIVITY_MILESTONES).map(([key, value]) => [key, value.progressPercent])),
    {
      '01a:model-call-verified': 10,
      '01b:react-loop-complete': 15,
      '01c:tool-roundtrip-complete': 25,
      '02a:routed-workflow-complete': 35,
      '02b:grounded-answer-complete': 45,
      '02c:deep-research-complete': 50,
      [`03a:${COURSE_ID}-connected`]: 60,
      '03b:workspace-inspected': 70,
      '03c:scheduled-run-complete': 80,
      '04a:policy-boundary-verified': 90,
      '04b:live-agent-operated': 100,
    },
  );
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
    phase: 'off', enabled: false, referralTracking: false, progressPercent: 0,
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
  const policy = { ...JSON.parse(fs.readFileSync(path.join(COURSE_ROOT, 'activity-policy.json'), 'utf8')), collection_enabled: false };
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
    const port = server.address().port;
    let apiRequests = 0;
    let apiMode = 'blocked';
    let confirmedProgress = 0;
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.hostname === 'activity-api.learn.nvidia.com') {
        apiRequests++;
        if (apiMode === 'blocked') return route.abort();
        const headers = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*', 'access-control-allow-methods': 'GET, POST, OPTIONS' };
        if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
        if (apiMode === 'unavailable') return route.fulfill({ status: 503, headers, json: {} });
        return route.fulfill({
          status: url.pathname.endsWith('/activity-sessions') ? 201 : 200, headers,
          json: url.pathname.endsWith('/activity-sessions') ? {
            session_id: '019f38f1-e5ab-7688-af0d-0e8925299e93',
            session_token: 'fixture-browser-session-token',
            expires_at: new Date(Date.now() + 3600000).toISOString(),
          } : { progress_percent: confirmedProgress, completed_at: null },
        });
      }
      return ['127.0.0.1', 'localhost', 'course.test'].includes(url.hostname) && url.port === String(port)
        ? route.continue() : route.abort();
    });
    await context.addCookies([{ name: 'course_fixture', value: 'authorized', url: `http://127.0.0.1:${port}` }]);
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:${port}/${COURSE_ROOT}/index.html`);
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
    await page.waitForFunction(() => document.querySelector('[data-activity-status]')?.textContent === 'Open this course over HTTPS to enable remote progress.');
    assert.equal(manifests, before, 'insecure pages must fail before manifest access');
    assert.equal(apiRequests, 0, 'no Activity API request is permitted in these cases');
    redirect = false;
    apiMode = 'healthy';
    const firstLesson = fs.readdirSync(COURSE_ROOT).find(name => name.startsWith('01a-') && name.endsWith('.html'));
    assert.ok(firstLesson);
    await page.goto(`http://127.0.0.1:${port}/${COURSE_ROOT}/${firstLesson}`);
    await page.locator('.activity-control-toggle').click();
    await page.locator('[data-activity-enable]').click();
    await page.waitForFunction(() => document.querySelector('[data-activity-notice]')?.textContent === 'Remote progress is enabled.');
    assert.equal(await page.locator('#activity-progress').getAttribute('value'), '0');
    assert.equal(await page.locator('#activity-progress-label').textContent(), 'Saved progress: 0%');
    assert.equal(await page.locator('[data-activity-status]').isHidden(), true);
    assert.equal(await page.locator('input[type="range"]').count(), 0, 'completion cannot be moved manually');
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('nemoclaw:api-key-verified'));
      window.dispatchEvent(new CustomEvent('nemoclaw:run-succeeded', { detail: { cellId: 'cell-onecall', hasContent: true } }));
    });
    await page.waitForFunction(() => document.querySelector('[data-activity-sync]')?.textContent.includes('Waiting for API confirmation.'));
    assert.equal(await page.locator('#activity-progress').getAttribute('value'), '0');
    assert.match(await page.locator('[data-activity-sync]').textContent(), /Local verified progress: 10%/);
    confirmedProgress = 45;
    await page.locator('[data-activity-refresh]').click();
    await page.waitForFunction(() => document.querySelector('#activity-progress')?.value === 45);
    assert.equal(await page.locator('#activity-progress-label').textContent(), 'Saved progress: 45%');
    await page.waitForLoadState('networkidle');
    const beforeReload = apiRequests;
    await page.reload();
    await page.locator('.activity-control-toggle').click();
    await page.waitForFunction(() => window.__nemoclawActivity.snapshot().enabled);
    await page.waitForLoadState('networkidle');
    assert.equal(apiRequests, beforeReload + 2, 'resume reads state, then confirms the synchronized local evidence without creating another session');
    assert.equal(await page.locator('[data-activity-enable]').isHidden(), true);
    await page.waitForFunction(() => document.querySelector('[data-activity-notice]')?.textContent === 'Remote progress is enabled.');
    apiMode = 'unavailable';
    await page.evaluate(() => window.__nemoclawActivity.recordMilestone('01a:model-call-verified'));
    assert.equal(await page.locator('.activity-control').getAttribute('data-state'), 'unavailable');
    assert.equal(await page.locator('#activity-progress-label').textContent(), 'Last confirmed progress: 45%');
    assert.equal(await page.locator('#activity-progress').getAttribute('value'), '45');
    apiMode = 'healthy';
    confirmedProgress = 60;
    await page.locator('[data-activity-refresh]').click();
    await page.waitForFunction(() => document.querySelector('#activity-progress')?.value === 60);
    assert.equal(await page.locator('[data-activity-sync]').textContent(), 'Confirmed by the Activity API.');
    assert.equal(await page.locator('#activity-progress').getAttribute('aria-valuetext'), 'Saved progress: 60%');
    await page.evaluate(() => sessionStorage.setItem('learner-work', 'retained'));
    const beforeDisconnect = apiRequests;
    await page.locator('[data-activity-disable]').click();
    assert.equal(await page.locator('.activity-control').getAttribute('data-state'), 'off');
    assert.equal(await page.locator('[data-activity-enable]').isVisible(), true);
    assert.equal(await page.evaluate(() => Object.keys(sessionStorage).filter(key => key.startsWith('dli_activity:') && !key.includes(':evidence:')).length), 0);
    assert.equal(await page.locator('#activity-progress-label').textContent(), 'Local verified progress: 10%');
    assert.equal(await page.locator('[data-activity-status]').isHidden(), true);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('learner-work')), 'retained');
    assert.equal(apiRequests, beforeDisconnect, 'disconnect must work without the service');
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
      return new Response(JSON.stringify({ progress_percent: 0, completed_at: null }), { status: 200 });
    }
    return new Response(JSON.stringify({ state: { progress_percent: 10 } }), { status: 201 });
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
      return { getState: async () => ({ progressPercent: 10 }) };
    },
  });
  const first = create();
  assert.equal(await first.resume(), false);
  assert.equal(sessions, 0);
  assert.equal(await first.enable(), true);
  first.setReferralTracking(true);
  assert.equal(await create({ ...APPROVED_ARTIFACT, artifact_digest: `sha256:${'c'.repeat(64)}` }).resume(), false);
  assert.equal(await create(APPROVED_ARTIFACT, { ...APPROVED_POLICY, notice_version: 'changed' }).resume(), false);
  assert.equal(sessions, 1);
  const nextPage = create();
  assert.equal(await nextPage.resume(), true);
  assert.equal(nextPage.snapshot().referralTracking, true);
  nextPage.disconnect();
  assert.equal(await create().resume(), false);
  assert.equal(values.size, 0);
  assert.equal(sessions, 2);
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
      return { getState: async () => ({ progressPercent: 0, completedAt: null }) };
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
      return { getState: async () => ({ progressPercent: 0, completedAt: null }) };
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
  const { activity, calls } = createFixture({ progressPercent: 100 });
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
      if (url.endsWith('/state')) return response({ progress_percent: 0 });
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

  assert.deepEqual(calls.at(-1), ['referral', {
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

test('Global Privacy Control blocks referrals at the activity facade', async () => {
  const activity = createCourseActivity({
    globalPrivacyControl: true,
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => ({
      getState: async () => ({ progressPercent: 0 }),
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

test('a named milestone sends its cumulative progress with a stable idempotency key', async () => {
  const { activity, calls } = createFixture();

  await enableFixture(activity);
  assert.equal(await activity.recordMilestone('02b:grounded-answer-complete'), true);

  assert.deepEqual(calls.findLast(call => call[0] === 'progress'), ['progress', 45, {
    idempotencyKey: `${COURSE_ID}:milestone:02b:grounded-answer-complete`,
  }]);
});

test('course completion is blocked below 100 percent', async () => {
  const { activity, calls } = createFixture({ progressPercent: 90 });

  await enableFixture(activity);
  assert.equal(await activity.recordCompletion(), false);
  assert.deepEqual(calls.slice(-2), [['getState'], ['getState']]);
  assert.equal(calls.some(call => call[0] === 'complete'), false);
});

test('course completion is sent once state reaches 100 percent', async () => {
  const { activity, calls } = createFixture({ progressPercent: 100 });

  await enableFixture(activity);
  assert.equal(await activity.recordCompletion(), true);

  assert.deepEqual(calls.slice(-3), [
    ['getState'],
    ['complete', { idempotencyKey: `${COURSE_ID}:course:completed` }],
    ['getState'],
  ]);
});

test('displayed progress follows API confirmation rather than the submitted percentage', async () => {
  const { activity, setProgress } = createFixture({ progressPercent: 10 });
  await enableFixture(activity);
  assert.equal(await activity.recordMilestone('02b:grounded-answer-complete'), true);
  assert.equal(activity.snapshot().progressPercent, 10);
  assert.ok(activity.snapshot().progressCheckedAt);
  setProgress(45);
  await activity.getCourseActivityState();
  assert.equal(activity.snapshot().progressPercent, 45);
});

test('invalid API percentages are unavailable instead of fabricated zero progress', async () => {
  for (const progressPercent of [-1, 101, 0.5, '45', null, NaN]) {
    const { activity } = createFixture({ progressPercent });
    assert.equal(await activity.enable(), false);
    assert.equal(activity.snapshot().phase, 'unavailable');
    assert.equal(activity.snapshot().progressCheckedAt, undefined);
  }
  const { activity } = createFixture({ progressPercent: 0 });
  assert.equal(await activity.enable(), true);
  assert.equal(activity.snapshot().progressPercent, 0);
});

test('refresh preserves the last confirmed value on failure and publishes recovery', async () => {
  let unavailable = false;
  let progressPercent = 25;
  const activity = createCourseActivity({
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => ({ getState: async () => {
      if (unavailable) throw new Error('service unavailable');
      return { progressPercent, completedAt: null };
    } }),
  });
  await enableFixture(activity);
  const checked = activity.snapshot().progressCheckedAt;
  unavailable = true;
  assert.equal(await activity.getCourseActivityState(), null);
  assert.equal(activity.snapshot().phase, 'unavailable');
  assert.equal(activity.snapshot().progressPercent, 25);
  assert.equal(activity.snapshot().progressCheckedAt, checked);
  unavailable = false;
  progressPercent = 45;
  await activity.getCourseActivityState();
  assert.equal(activity.snapshot().phase, 'connected');
  assert.equal(activity.snapshot().reason, null);
  assert.equal(activity.snapshot().progressPercent, 45);
});

test('course state is read through the facade', async () => {
  const { activity, calls } = createFixture({ progressPercent: 70 });

  await enableFixture(activity);
  assert.deepEqual(await activity.getCourseActivityState(), { progressPercent: 70, completedAt: null });
  assert.deepEqual(calls.at(-1), ['getState']);
});

test('an older concurrent refresh cannot replace newer confirmed progress or connection state', async () => {
  let pending = null;
  const activity = createCourseActivity({
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => ({ getState: () => pending
      ? new Promise((resolve, reject) => pending.push({ resolve, reject }))
      : Promise.resolve({ progressPercent: 10 }) }),
  });
  await enableFixture(activity);
  for (const failOlder of [false, true]) {
    pending = [];
    const older = activity.getCourseActivityState();
    const newer = activity.getCourseActivityState();
    await new Promise(resolve => setImmediate(resolve));
    pending[1].resolve({ progressPercent: 60 });
    await newer;
    if (failOlder) pending[0].reject(new Error('late failure'));
    else pending[0].resolve({ progressPercent: 25 });
    await older;
    assert.equal(activity.snapshot().progressPercent, 60);
    assert.equal(activity.snapshot().phase, 'connected');
  }
});

test('facade failures remain contained and retryable at the lesson boundary', async () => {
  let attempts = 0;
  const activity = createCourseActivity({
    policyLoader: async () => APPROVED_POLICY,
    artifactResolver: async () => APPROVED_ARTIFACT,
    initialize: async () => ({
      getState: async () => ({ progressPercent: 100, completedAt: null }),
      complete: async () => {
        attempts += 1;
        throw new Error('temporarily unavailable');
      },
    }),
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

test('the published opt-in notice requires complete disclosure and keeps both defaults off', () => {
  const policy = JSON.parse(fs.readFileSync(path.join(COURSE_ROOT, 'activity-policy.json'), 'utf8'));
  assert.equal(isActivityPolicyApproved(policy), true);
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
      return { getState: async () => ({ progressPercent: 0, completedAt: null }) };
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
