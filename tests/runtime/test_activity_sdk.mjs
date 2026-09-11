// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  ActivitySdkError,
  DLIActivity,
  DLIActivityError,
  createActivityClient,
  createMemoryActivityStorage,
} from '../../web/shared/activity-sdk.js';

const artifact = {
  artifact_id: 'artifact_nemoclaw_web',
  artifact_version: 'sdk-fixture-v1',
  artifact_digest: `sha256:${'a'.repeat(64)}`,
};

const ACTIVITY = artifact;

function fakeStorage() {
  return createMemoryActivityStorage();
}

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function sessionResponse(overrides = {}) {
  return {
    session_token: 'opaque-session-token-with-safe-length',
    session_id: '019f38f1-e5ab-7688-af0d-0e8925299e93',
    expires_at: '2026-08-19T21:00:00Z',
    ...overrides,
  };
}

test('public initialization creates one activity session', async () => {
  const sessionCreateBodies = [];
  const now = () => new Date('2026-08-19T20:00:00Z');
  const fetchImpl = async (_url, init) => {
    sessionCreateBodies.push(JSON.parse(init.body));
    return jsonResponse(201, sessionResponse());
  };

  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl,
    now,
  });

  assert.equal(activity instanceof DLIActivity, true);
  assert.deepEqual(sessionCreateBodies, [ACTIVITY]);
});

test('public initialization rejects unsafe activity API base URLs', async () => {
  const unsafeBaseUrls = [
    'https://user:secret@activity-api.example.test',
    'https://activity-api.example.test?mode=test',
    'https://activity-api.example.test#fragment',
    'http://activity-api.example.test',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://[::1]:8000',
  ];

  for (const baseUrl of unsafeBaseUrls) {
    await assert.rejects(
      DLIActivity.initialize({
        baseUrl,
        artifact: ACTIVITY,
        fetchImpl: async () => assert.fail('fetch must not run'),
      }),
      error => error instanceof DLIActivityError && error.code === 'invalid_base_url',
    );
  }
});

test('public initialization rejects the removed activity alias', async () => {
  await assert.rejects(
    DLIActivity.initialize({
      baseUrl: 'https://activity-api.example.test',
      activity: ACTIVITY,
    }),
    error => error instanceof DLIActivityError && error.code === 'invalid_configuration',
  );
});

test('low-level client rejects loopback HTTP base URLs', () => {
  for (const baseUrl of [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://[::1]:8000',
  ]) {
    assert.throws(
      () => createActivityClient({ baseUrl, artifact: ACTIVITY }),
      error => error instanceof ActivitySdkError && /must use HTTPS/.test(error.message),
    );
  }
});

test('concurrent public initialization shares one facade and retries after rejection', async () => {
  const storage = fakeStorage();
  const attempts = [];
  const options = {
    baseUrl: 'https://activity-api.example.test/',
    artifact: ACTIVITY,
    storage,
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: () => new Promise((resolve, reject) => attempts.push({ resolve, reject })),
  };

  const first = DLIActivity.initialize(options);
  const concurrent = DLIActivity.initialize({ ...options, baseUrl: 'https://activity-api.example.test' });
  await Promise.resolve();
  assert.equal(attempts.length, 1);
  attempts[0].reject(new TypeError('opaque network failure'));
  await assert.rejects(first, error => error instanceof DLIActivityError && error.code === 'network_error');
  await assert.rejects(concurrent, error => error instanceof DLIActivityError && error.code === 'network_error');

  const retry = DLIActivity.initialize(options);
  await Promise.resolve();
  assert.equal(attempts.length, 2);
  attempts[1].resolve(jsonResponse(201, sessionResponse()));
  assert.equal(await retry instanceof DLIActivity, true);
});

test('all low-level failures crossing public boundaries are translated with safe metadata', async () => {
  await assert.rejects(
    Promise.resolve().then(() => new DLIActivity({
      baseUrl: 'https://activity-api.example.test',
      artifact: { ...ACTIVITY, artifact_digest: 'invalid' },
    })),
    error => error instanceof DLIActivityError &&
      error.code === 'invalid_configuration' &&
      error.category === 'configuration' &&
      error.cause instanceof ActivitySdkError,
  );

  for (const { status, code, category } of [
    { status: 503, code: 'request_rejected', category: 'server' },
    { status: 409, code: 'idempotency_conflict', category: 'idempotency-conflict' },
  ]) {
    const activity = await DLIActivity.initialize({
      baseUrl: 'https://activity-api.example.test', artifact: ACTIVITY,
      storage: createMemoryActivityStorage(sessionResponse()),
      now: () => new Date('2026-08-19T20:00:00Z'),
      fetchImpl: async () => jsonResponse(status, { detail: 'must-not-escape' }),
    });
    await assert.rejects(
      activity.referral({ referenceId: 'safe-ref', destinationUrl: 'https://example.test/' }),
      error => error instanceof DLIActivityError && error.code === code &&
        error.operation === 'referral' && error.category === category && error.status === status &&
        !JSON.stringify(error).includes('must-not-escape'),
    );
  }
});

test('network and invalid-response failures are translated by every async public operation', async () => {
  const cases = [
    ['progress', activity => activity.progress(50), 'network_error', async () => { throw new TypeError('secret'); }],
    ['getState', activity => activity.getState(), 'invalid_response', async () => new Response('not-json', { status: 200 })],
    ['complete', activity => activity.complete(), 'invalid_response', async () => new Response('not-json', { status: 200 })],
  ];
  for (const [name, invoke, code, fetchImpl] of cases) {
    const activity = await DLIActivity.initialize({
      baseUrl: 'https://activity-api.example.test', artifact: ACTIVITY,
      storage: createMemoryActivityStorage(sessionResponse()),
      now: () => new Date('2026-08-19T20:00:00Z'), fetchImpl,
    });
    await assert.rejects(invoke(activity), error => error instanceof DLIActivityError &&
      error.code === code && error.cause instanceof ActivitySdkError,
      `${name} must translate its low-level error`);
  }
});

test('public progress hydrates restored server state before its first write', async () => {
  const calls = [];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test', artifact: ACTIVITY,
    storage: createMemoryActivityStorage(sessionResponse()),
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return jsonResponse(200, { progress_percent: 75, completed_at: null });
    },
  });

  assert.deepEqual(await activity.progress(50), { written: false, progressPercent: 75 });
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/state$/);
});

test('concurrent public progress calls never write a decrease', async () => {
  const writes = [];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test', artifact: ACTIVITY,
    storage: createMemoryActivityStorage(sessionResponse()),
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async (url, init) => {
      if (url.endsWith('/state')) return jsonResponse(200, { progress_percent: 0, completed_at: null });
      const percent = JSON.parse(init.body).payload.progress_percent;
      writes.push(percent);
      return jsonResponse(201, { update_id: `progress-${percent}`, state: { progress_percent: percent } });
    },
  });

  const [higher, lower] = await Promise.all([activity.progress(50), activity.progress(40)]);
  assert.equal(higher.result.state.progress_percent, 50);
  assert.deepEqual(lower, { written: false, progressPercent: 50 });
  assert.deepEqual(writes, [50]);
});

test('public progress records a monotonic integer percentage', async () => {
  const calls = [];
  const responses = [
    jsonResponse(201, sessionResponse()),
    jsonResponse(200, { progress_percent: 0, completed_at: null }),
    jsonResponse(201, { update_id: 'progress-50', state: { progress_percent: 75 } }),
  ];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return responses.shift();
    },
    now: () => new Date('2026-08-19T20:00:00Z'),
  });

  await activity.progress(50);
  await activity.progress(70);

  assert.equal(calls.length, 3);
  assert.equal(calls[2].init.headers['Idempotency-Key'], 'dli-activity:progress:50');
  assert.deepEqual(JSON.parse(calls[2].init.body), {
    type: 'progress',
    payload: { progress_percent: 50 },
  });
});

test('public progress preserves a caller idempotency key', async () => {
  const calls = [];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (calls.length === 1) return jsonResponse(201, sessionResponse());
      if (calls.length === 2) return jsonResponse(200, { progress_percent: 0, completed_at: null });
      return jsonResponse(201, { update_id: 'progress-25', state: { progress_percent: 25 } });
    },
    now: () => new Date('2026-08-19T20:00:00Z'),
  });

  await activity.progress(25, { idempotencyKey: 'course:checkpoint:25' });

  assert.equal(calls[2].init.headers['Idempotency-Key'], 'course:checkpoint:25');
});

test('public progress rejects invalid percentages before fetch', async () => {
  const activity = new DLIActivity({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async () => assert.fail('fetch must not run'),
  });

  for (const progressPercent of [-1, 101, 50.5, '50']) {
    await assert.rejects(
      activity.progress(progressPercent),
      error => error instanceof DLIActivityError && error.code === 'invalid_progress',
    );
  }
});

test('public referral records a portable destination', async () => {
  const calls = [];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return calls.length === 1
        ? jsonResponse(201, sessionResponse())
        : jsonResponse(201, { referral_id: 'referral-1' });
    },
    now: () => new Date('2026-08-19T20:00:00Z'),
  });

  await activity.referral({
    referenceId: 'brev:course-lab',
    destinationUrl: 'https://brev.nvidia.com/',
  });

  assert.equal(calls[1].init.headers['Idempotency-Key'], 'dli-activity:referral:brev:course-lab');
  assert.deepEqual(JSON.parse(calls[1].init.body), {
    reference_id: 'brev:course-lab',
    destination_url: 'https://brev.nvidia.com/',
  });
});

test('public referral rejects invalid input before fetch', async () => {
  const activity = new DLIActivity({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async () => assert.fail('fetch must not run'),
  });

  for (const referral of [
    { referenceId: ' ', destinationUrl: 'https://brev.nvidia.com/' },
    { referenceId: 'brev:nemoclaw-lab', destinationUrl: 'not a URL' },
    { referenceId: 'brev:nemoclaw-lab', destinationUrl: 'javascript:alert(1)' },
    { referenceId: 'brev:nemoclaw-lab', destinationUrl: 'http://brev.nvidia.com/' },
  ]) {
    await assert.rejects(
      activity.referral(referral),
      error => error instanceof DLIActivityError && error.code === 'invalid_referral',
    );
  }
});

test('public state normalizes documented fields without authentication data', async () => {
  const responses = [
    jsonResponse(201, sessionResponse()),
    jsonResponse(200, {
      progress_percent: 50,
      completed_at: null,
      last_update: {
        update_id: 'update-50',
        checkpoint_items: [{ reference_id: 'module:02c' }],
      },
      session_token: 'must-not-escape',
      authorization: { bearer_token: 'must-not-escape' },
      nested_authentication: {
        access_token: 'must-not-escape',
        bearer_token: 'must-not-escape',
        refresh_token: 'must-not-escape',
        sessionToken: 'must-not-escape',
        authorizationData: { value: 'must-not-escape' },
        public_value: 'preserved',
      },
    }),
  ];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async () => responses.shift(),
    now: () => new Date('2026-08-19T20:00:00Z'),
  });

  const state = await activity.getState();

  assert.deepEqual(state, {
    progressPercent: 50,
    completedAt: null,
    lastUpdate: {
      updateId: 'update-50',
      checkpointItems: [{ referenceId: 'module:02c' }],
    },
    nestedAuthentication: {
      publicValue: 'preserved',
    },
  });
  assert.equal('sessionToken' in state, false);
  assert.equal('authorization' in state, false);
});

test('public state raises the monotonic progress floor learned from a read', async () => {
  const calls = [];
  const responses = [
    jsonResponse(201, sessionResponse()),
    jsonResponse(200, { progress_percent: 75, completed_at: null }),
  ];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return responses.shift();
    },
    now: () => new Date('2026-08-19T20:00:00Z'),
  });

  await activity.getState();
  assert.deepEqual(await activity.progress(70), {
    written: false,
    progressPercent: 75,
  });
  assert.equal(calls.length, 2);
});

test('public completion refreshes state and skips a premature write', async () => {
  const calls = [];
  const responses = [
    jsonResponse(201, sessionResponse()),
    jsonResponse(200, { progress_percent: 90, completed_at: null }),
  ];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return responses.shift();
    },
    now: () => new Date('2026-08-19T20:00:00Z'),
  });

  assert.deepEqual(await activity.complete(), {
    written: false,
    state: { progressPercent: 90, completedAt: null },
  });
  assert.equal(calls.length, 2);
  assert.equal(calls[1].init.method, 'GET');
});

test('public completion fails closed unless normalized progress is numeric integer 100', async () => {
  for (const progressPercent of [undefined, '100', 99.5, 101]) {
    const calls = [];
    const state = { completed_at: null };
    if (progressPercent !== undefined) state.progress_percent = progressPercent;
    const responses = [
      jsonResponse(201, sessionResponse()),
      jsonResponse(200, state),
    ];
    const activity = await DLIActivity.initialize({
      baseUrl: 'https://activity-api.example.test',
      artifact: ACTIVITY,
      storage: fakeStorage(),
      fetchImpl: async (url, init) => {
        calls.push({ url, init });
        return responses.shift();
      },
      now: () => new Date('2026-08-19T20:00:00Z'),
    });

    const result = await activity.complete();

    assert.equal(result.written, false);
    assert.equal(calls.length, 2, `must not write completion for ${String(progressPercent)}`);
  }
});

test('public completion records an eligible completed update', async () => {
  const calls = [];
  const responses = [
    jsonResponse(201, sessionResponse()),
    jsonResponse(200, { progress_percent: 100, completed_at: null }),
    jsonResponse(201, { update_id: 'completed-1', state: { progress_percent: 100 } }),
  ];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return responses.shift();
    },
    now: () => new Date('2026-08-19T20:00:00Z'),
  });

  await activity.complete();

  assert.equal(calls.length, 3);
  assert.equal(calls[2].init.headers['Idempotency-Key'], 'dli-activity:completed');
  assert.deepEqual(JSON.parse(calls[2].init.body), { type: 'completed', payload: {} });
});

test('public completion preserves a caller idempotency key', async () => {
  const calls = [];
  const responses = [
    jsonResponse(201, sessionResponse()),
    jsonResponse(200, { progress_percent: 100, completed_at: null }),
    jsonResponse(201, { update_id: 'completed-1' }),
  ];
  const activity = await DLIActivity.initialize({
    baseUrl: 'https://activity-api.example.test',
    artifact: ACTIVITY,
    storage: fakeStorage(),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return responses.shift();
    },
    now: () => new Date('2026-08-19T20:00:00Z'),
  });

  await activity.complete({ idempotencyKey: 'course:completed' });

  assert.equal(calls[2].init.headers['Idempotency-Key'], 'course:completed');
});

test('concurrent initialization creates and stores one activity session', async () => {
  const calls = [];
  const storage = createMemoryActivityStorage();
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test',
    artifact,
    storage,
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return jsonResponse(201, sessionResponse());
    },
  });

  const [first, second] = await Promise.all([client.ensureSession(), client.ensureSession()]);

  assert.deepEqual(first, second);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, 'https://activity.example.test/v1/activity-sessions');
  assert.equal(calls[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].init.body), artifact);
  assert.equal(calls[0].init.headers.Authorization, undefined);
  assert.deepEqual(storage.load(), sessionResponse());
});

test('an unexpired stored session is reused without a request', async () => {
  const storage = createMemoryActivityStorage(sessionResponse());
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test',
    artifact,
    storage,
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async () => assert.fail('fetch must not run'),
  });

  assert.deepEqual(await client.ensureSession(), sessionResponse());
});

test('an expired stored session is replaced', async () => {
  const storage = createMemoryActivityStorage(sessionResponse({ expires_at: '2026-08-19T19:00:00Z' }));
  let requests = 0;
  const replacement = sessionResponse({ session_id: '0198f100-0000-7000-8000-000000000002' });
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test',
    artifact,
    storage,
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async () => {
      requests += 1;
      return jsonResponse(201, replacement);
    },
  });

  assert.deepEqual(await client.ensureSession(), replacement);
  assert.equal(requests, 1);
  assert.deepEqual(storage.load(), replacement);
});

test('referral and progress writes use bearer and idempotency headers', async () => {
  const calls = [];
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test',
    artifact,
    storage: createMemoryActivityStorage(sessionResponse()),
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return jsonResponse(201, url.endsWith('/referrals')
        ? { referral_id: 'referral-1', received_at: '2026-08-19T20:00:01Z' }
        : { update_id: 'update-1', received_at: '2026-08-19T20:00:02Z', state: { progress_percent: 10 } });
    },
  });

  await client.recordReferral({
    referenceId: 'build:nvidia-api-key',
    destinationUrl: 'https://build.nvidia.com/?ncid=ref-dli-146986',
    idempotencyKey: 'referral-key',
  });
  await client.recordProgress({ progressPercent: 10, idempotencyKey: 'progress-key' });

  assert.equal(calls.length, 2);
  assert.match(calls[0].url, /\/v1\/activity-sessions\/019f38f1-e5ab-7688-af0d-0e8925299e93\/referrals$/);
  assert.match(calls[0].url, /\/referrals$/);
  assert.deepEqual(JSON.parse(calls[0].init.body), {
    reference_id: 'build:nvidia-api-key',
    destination_url: 'https://build.nvidia.com/?ncid=ref-dli-146986',
  });
  assert.match(calls[1].url, /\/updates$/);
  assert.deepEqual(JSON.parse(calls[1].init.body), {
    type: 'progress',
    payload: { progress_percent: 10 },
  });
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${sessionResponse().session_token}`);
  assert.equal(calls[0].init.headers['Idempotency-Key'], 'referral-key');
  assert.equal(calls[1].init.headers['Idempotency-Key'], 'progress-key');
  for (const { init } of calls) {
    assert.equal(init.credentials, 'omit');
    assert.equal(init.cache, 'no-store');
    assert.equal(init.redirect, 'error');
    assert.equal(init.referrerPolicy, 'no-referrer');
    assert.equal(init.mode, 'cors');
    assert.equal(init.signal instanceof AbortSignal, true);
  }
});

test('a 200 write response is identified as an idempotent replay', async () => {
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test',
    artifact,
    storage: createMemoryActivityStorage(sessionResponse()),
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async () => jsonResponse(200, { update_id: 'original' }),
  });

  assert.deepEqual(
    await client.recordProgress({ progressPercent: 10, idempotencyKey: 'progress-key' }),
    { result: { update_id: 'original' }, replayed: true },
  );
});

test('completion is an authenticated idempotent completed update', async () => {
  const calls = [];
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test', artifact,
    storage: createMemoryActivityStorage(sessionResponse()),
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return jsonResponse(201, { update_id: 'completed-1', state: { progress_percent: 100 } });
    },
  });

  await client.recordCompleted({ idempotencyKey: 'course-completed' });

  assert.match(calls[0].url, /\/updates$/);
  assert.equal(calls[0].init.method, 'POST');
  assert.equal(calls[0].init.headers['Idempotency-Key'], 'course-completed');
  assert.deepEqual(JSON.parse(calls[0].init.body), { type: 'completed', payload: {} });
});

test('state is read with bearer authentication and no request body', async () => {
  const calls = [];
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test', artifact,
    storage: createMemoryActivityStorage(sessionResponse()),
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      return jsonResponse(200, { progress_percent: 100, completed_at: null });
    },
  });

  const state = await client.getState();

  assert.deepEqual(state, { progress_percent: 100, completed_at: null });
  assert.match(calls[0].url, /\/state$/);
  assert.equal(calls[0].init.method, 'GET');
  assert.equal(calls[0].init.body, undefined);
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${sessionResponse().session_token}`);
});

test('errors and diagnostics never expose bearer material', async () => {
  const diagnostics = [];
  const token = sessionResponse().session_token;
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test',
    artifact,
    storage: createMemoryActivityStorage(sessionResponse()),
    now: () => new Date('2026-08-19T20:00:00Z'),
    onDiagnostic: event => diagnostics.push(event),
    fetchImpl: async () => jsonResponse(401, { detail: `rejected ${token}` }),
  });

  await assert.rejects(
    client.recordProgress({ progressPercent: 10, idempotencyKey: 'progress-key' }),
    error => error instanceof ActivitySdkError && error.category === 'authentication' && error.status === 401,
  );

  assert.equal(JSON.stringify(diagnostics).includes(token), false);
  assert.equal(diagnostics[0].operation, 'progress');
  assert.equal(diagnostics[0].category, 'authentication');
});

test('an unauthorized write clears the rejected session and retries once with a fresh token', async () => {
  const rejected = sessionResponse();
  const replacement = sessionResponse({
    session_token: 'replacement-session-token-safe-length',
    session_id: '019f38f1-e5ab-7688-af0d-0e8925299e94',
  });
  const storage = createMemoryActivityStorage(rejected);
  const calls = [];
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test', artifact, storage,
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async (url, init) => {
      calls.push({ url, init });
      if (calls.length === 1) return jsonResponse(401, { detail: 'rejected' });
      if (calls.length === 2) return jsonResponse(201, replacement);
      return jsonResponse(201, { update_id: 'progress-1', state: { progress_percent: 10 } });
    },
  });
  const response = await client.recordProgress({ progressPercent: 10, idempotencyKey: 'progress-key' });
  assert.equal(response.result.state.progress_percent, 10);
  assert.equal(calls.length, 3);
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${rejected.session_token}`);
  assert.equal('Authorization' in calls[1].init.headers, false);
  assert.equal(calls[2].init.headers.Authorization, `Bearer ${replacement.session_token}`);
  assert.equal(JSON.stringify(calls).includes(rejected.session_token), true);
  assert.deepEqual(storage.load(), replacement);
});

test('authentication recovery retries only once', async () => {
  const storage = createMemoryActivityStorage(sessionResponse());
  let calls = 0;
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test', artifact, storage,
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async (_url, init) => {
      calls += 1;
      return init.headers.Authorization
        ? jsonResponse(403, { detail: 'rejected' })
        : jsonResponse(201, sessionResponse({ session_token: 'replacement-session-token-safe-length' }));
    },
  });
  await assert.rejects(
    client.getState(),
    error => error instanceof ActivitySdkError && error.category === 'authentication' && error.status === 403,
  );
  assert.equal(calls, 3);
  assert.equal(storage.load(), null);
});

test('staggered write and state authentication failures share one replacement session', async () => {
  const stale = sessionResponse();
  const replacement = sessionResponse({
    session_token: 'shared-replacement-token-safe-length',
    session_id: '019f38f1-e5ab-7688-af0d-0e8925299e95',
  });
  let releaseSlowFailure;
  let markSlowStarted;
  let markReplacementCreated;
  const slowStarted = new Promise(resolve => { markSlowStarted = resolve; });
  const replacementCreated = new Promise(resolve => { markReplacementCreated = resolve; });
  const calls = [];
  const client = createActivityClient({
    baseUrl: 'https://activity.example.test', artifact,
    storage: createMemoryActivityStorage(stale),
    now: () => new Date('2026-08-19T20:00:00Z'),
    fetchImpl: async (url, init) => {
      calls.push({ url, authorization: init.headers.Authorization });
      if (!init.headers.Authorization) {
        markReplacementCreated();
        return jsonResponse(201, replacement);
      }
      if (init.headers.Authorization === `Bearer ${stale.session_token}` && url.endsWith('/updates')) {
        markSlowStarted();
        return new Promise(resolve => { releaseSlowFailure = resolve; });
      }
      if (init.headers.Authorization === `Bearer ${stale.session_token}`) {
        return jsonResponse(401, { detail: 'stale' });
      }
      if (url.endsWith('/state')) return jsonResponse(200, { progress_percent: 10, completed_at: null });
      return jsonResponse(201, { update_id: 'progress-1', state: { progress_percent: 10 } });
    },
  });

  const write = client.recordProgress({ progressPercent: 10, idempotencyKey: 'progress-key' });
  await slowStarted;
  const state = client.getState();
  await replacementCreated;
  const stateResult = await state;
  releaseSlowFailure(jsonResponse(403, { detail: 'stale' }));

  const writeResult = await write;
  assert.equal(writeResult.result.state.progress_percent, 10);
  assert.equal(stateResult.progress_percent, 10);
  assert.equal(calls.filter(call => call.authorization === undefined).length, 1);
  assert.equal(calls.filter(call => call.authorization === `Bearer ${replacement.session_token}`).length, 2);
  assert.equal(calls.length, 5);
});
