// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import { sharedRuntime } from './course_runtime_fixture.mjs';

const {
  DEFAULT_MODEL_API_BASE_URL,
  DEFAULT_MODEL_REQUEST_RETRIES,
  DEFAULT_MODEL_REQUEST_TIMEOUT_MS,
  defaultIframeProxyModeForLocation,
  fetchRetry,
  getConfig,
  getEmbeddingConfig,
  getModelRequestPolicy,
  normalizeModelRequestRetries,
  normalizeModelRequestTimeoutMs,
  readModelStreamChunk,
  retryDelayMs,
  setIframeProxyMode,
  setEmbeddingApiBaseUrl,
  setModelApiBaseUrl,
  setModelRequestRetries,
  setModelRequestTimeoutMs,
} = sharedRuntime;

function memoryStorage() {
  const values = new Map();
  return {
    getItem:key => values.has(key) ? values.get(key) : null,
    setItem:(key, value) => values.set(key, String(value)),
    removeItem:key => values.delete(key),
  };
}

test('the model relay default covers only the exact published course origins and local files', () => {
  const cases = [
    ['https://cdn.dli.learn.nvidia.com/course-static/nemoclaw/', true],
    ['https://nvdli.github.io/NemoClawDLI/nemoclaw/', true],
    ['file:course-preview.html', true],
    ['http://cdn.dli.learn.nvidia.com/course-static/nemoclaw/', false],
    ['https://cdn.dli.learn.nvidia.com.example.invalid/', false],
    ['http://nvdli.github.io/NemoClawDLI/nemoclaw/', false],
    ['https://nvdli.github.io.example.invalid/NemoClawDLI/', false],
    ['https://example.com/', false],
    ['data:text/html,course', false],
  ];
  for (const [location, expected] of cases) {
    assert.equal(defaultIframeProxyModeForLocation(location), expected, location);
  }
});

test('a failed model call from a local file explains the supported preview paths', async () => {
  const previous = { location:globalThis.location, fetch:globalThis.fetch };
  globalThis.location = new URL('file:course-preview.html');
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
  try {
    await assert.rejects(
      fetchRetry('https://integrate.api.nvidia.com/v1/chat/completions', {}, { retries:0 }),
      error => /local course preview.*NVIDIA DLI browser relay.*http:\/\/localhost:8000\/nemoclaw\//s.test(error.message),
    );
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  }
});

test('a local file preview ignores stale direct mode but still bypasses for custom endpoints', async () => {
  const memoryStorage = () => {
    const values = new Map();
    return {
      getItem:key => values.has(key) ? values.get(key) : null,
      setItem:(key, value) => values.set(key, String(value)),
      removeItem:key => values.delete(key),
    };
  };
  const previous = {
    location:globalThis.location,
    localStorage:globalThis.localStorage,
    sessionStorage:globalThis.sessionStorage,
  };
  globalThis.location = new URL('file:course-preview.html');
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  try {
    setIframeProxyMode(false);
    const staleDirect = await getConfig();
    assert.equal(staleDirect.iframeProxy, true);
    assert.equal(staleDirect.url, 'https://nvidia-api-cors-proxy.experiments.courses.nvidia.com/v1');

    setModelApiBaseUrl('https://models.example.test/v1');
    const custom = await getConfig();
    assert.equal(custom.iframeProxy, false);
    assert.equal(custom.url, 'https://models.example.test/v1');
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  }
});

test('CDN default, direct override, and custom endpoint bypass resolve consistently', async () => {
  const previous = {
    location:globalThis.location,
    localStorage:globalThis.localStorage,
    sessionStorage:globalThis.sessionStorage,
  };
  globalThis.location = new URL('https://cdn.dli.learn.nvidia.com/course-static/nemoclaw/');
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  try {
    setModelApiBaseUrl(DEFAULT_MODEL_API_BASE_URL);
    const cdnDefault = await getConfig();
    assert.equal(cdnDefault.iframeProxy, true);
    assert.equal(cdnDefault.url, 'https://nvidia-api-cors-proxy.experiments.courses.nvidia.com/v1');

    setIframeProxyMode(false);
    const direct = await getConfig();
    assert.equal(direct.iframeProxy, false);
    assert.equal(direct.url, DEFAULT_MODEL_API_BASE_URL);

    setModelApiBaseUrl('https://models.example.test/v1');
    setIframeProxyMode(true);
    const custom = await getConfig();
    assert.equal(custom.iframeProxy, false);
    assert.equal(custom.url, 'https://models.example.test/v1');
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  }
});

test('embedding route shares relay selection but keeps its own endpoint', async () => {
  const previous = {
    location:globalThis.location,
    localStorage:globalThis.localStorage,
    sessionStorage:globalThis.sessionStorage,
  };
  globalThis.location = new URL('https://nvdli.github.io/NemoClawDLI/nemoclaw/02b-rag.html');
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  try {
    const relayed = await getEmbeddingConfig();
    assert.deepEqual(relayed, {
      mode:'direct',
      url:'https://nvidia-api-cors-proxy.experiments.courses.nvidia.com/v1',
      model:'nvidia/llama-nemotron-embed-1b-v2',
      needsKey:true,
      iframeProxy:true,
    });

    setIframeProxyMode(false);
    const direct = await getEmbeddingConfig();
    assert.equal(direct.url, DEFAULT_MODEL_API_BASE_URL);
    assert.equal(direct.iframeProxy, false);

    setIframeProxyMode(true);
    setEmbeddingApiBaseUrl('https://embedding.example.test/v1');
    const custom = await getEmbeddingConfig();
    assert.equal(custom.url, 'https://embedding.example.test/v1');
    assert.equal(custom.iframeProxy, false);
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  }
});

test('model request handling is bounded and retries are opt-in', () => {
  const previous = globalThis.localStorage;
  globalThis.localStorage = memoryStorage();
  try {
    assert.deepEqual(getModelRequestPolicy(), {
      retries: DEFAULT_MODEL_REQUEST_RETRIES,
      timeoutMs: DEFAULT_MODEL_REQUEST_TIMEOUT_MS,
    });
    assert.equal(setModelRequestTimeoutMs(120000), 120000);
    assert.equal(setModelRequestRetries(2), 2);
    assert.deepEqual(getModelRequestPolicy(), { retries:2, timeoutMs:120000 });
    assert.throws(() => normalizeModelRequestTimeoutMs(4999), /between 5 and 300 seconds/);
    assert.throws(() => normalizeModelRequestRetries(6), /0 to 5/);
  } finally {
    if (previous === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = previous;
  }
});

test('Retry-After supports seconds and HTTP dates within the request bound', () => {
  const headers = value => ({ get:name => name.toLowerCase() === 'retry-after' ? value : null });
  assert.equal(retryDelayMs({ headers:headers('7') }, 500, 0, 60000, 1000), 7000);
  assert.equal(retryDelayMs(
    { headers:headers('Thu, 01 Jan 1970 00:00:12 GMT') },
    500, 0, 60000, 10000,
  ), 2000);
  assert.equal(retryDelayMs({ headers:headers('900') }, 500, 0, 60000, 1000), 60000);
  assert.equal(retryDelayMs({ headers:headers('invalid') }, 500, 2, 60000, 1000), 2000);
});

test('HTTP 429 retries only when configured and then returns the usable response', async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return calls === 1
      ? new Response('', { status:429, headers:{ 'Retry-After':'0' } })
      : new Response('ready', { status:200 });
  };
  try {
    const response = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:1, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(await response.text(), 'ready');
    assert.equal(calls, 2);
  } finally {
    if (previous === undefined) delete globalThis.fetch;
    else globalThis.fetch = previous;
  }
});

test('caller errors do not retry and caller aborts stop before fetch', async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response('', { status:400 });
  };
  try {
    const response = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:5, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(response.status, 400);
    assert.equal(calls, 1);
    const controller = new AbortController();
    controller.abort(new Error('learner stopped'));
    await assert.rejects(
      fetchRetry('https://models.example.test/v1/models', { signal:controller.signal }),
      /learner stopped/,
    );
    assert.equal(calls, 1);
  } finally {
    if (previous === undefined) delete globalThis.fetch;
    else globalThis.fetch = previous;
  }
});

test('HTTP 503 and network failures retry only when the learner opts in', async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls === 1) return new Response('', { status:503 });
    return new Response('recovered', { status:200 });
  };
  try {
    const first = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:0, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(first.status, 503);
    assert.equal(calls, 1);
    const recovered = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:1, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(await recovered.text(), 'recovered');
    assert.equal(calls, 2);

    calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      if (calls === 1) throw new TypeError('socket closed');
      return new Response('network recovered', { status:200 });
    };
    await assert.rejects(
      fetchRetry('https://models.example.test/v1/models', {}, {
        retries:0, timeoutMs:1000, backoffMs:1,
      }),
      /after 1 attempt.*socket closed/s,
    );
    assert.equal(calls, 1);
    const networkRecovered = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:1, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(await networkRecovered.text(), 'network recovered');
    assert.equal(calls, 2);
  } finally {
    if (previous === undefined) delete globalThis.fetch;
    else globalThis.fetch = previous;
  }
});

test('timeouts and caller cancellation remain bounded without a hidden retry', async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async (_url, init = {}) => {
    calls += 1;
    return new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(init.signal.reason), { once:true });
    });
  };
  try {
    await assert.rejects(
      fetchRetry('https://models.example.test/v1/models', {}, {
        retries:0, timeoutMs:5, backoffMs:1,
      }),
      /wait limit 0s.*timeout after 5ms/s,
    );
    assert.equal(calls, 1);

    const controller = new AbortController();
    globalThis.fetch = async () => {
      calls += 1;
      queueMicrotask(() => controller.abort(new Error('learner stopped during recovery')));
      return new Response('', { status:503 });
    };
    await assert.rejects(
      fetchRetry('https://models.example.test/v1/models', { signal:controller.signal }, {
        retries:5, timeoutMs:1000, backoffMs:100,
      }),
      /learner stopped during recovery/,
    );
    assert.equal(calls, 2);
  } finally {
    if (previous === undefined) delete globalThis.fetch;
    else globalThis.fetch = previous;
  }
});

test('stream stalls and mid-stream failures are visible and cancel the reader', async () => {
  let cancelled = false;
  const stalled = {
    read:async () => new Promise(() => {}),
    cancel:async () => { cancelled = true; },
  };
  await assert.rejects(
    readModelStreamChunk(stalled, 5),
    /stopped producing data.*Request handling/s,
  );
  assert.equal(cancelled, true);

  let reads = 0;
  const failed = {
    read:async () => {
      reads += 1;
      if (reads === 1) {
        return { done:false, value:new TextEncoder().encode('data: partial\n\n') };
      }
      throw new Error('mid-stream socket failure');
    },
    cancel:async () => {},
  };
  const first = await readModelStreamChunk(failed, 100);
  assert.equal(new TextDecoder().decode(first.value), 'data: partial\n\n');
  await assert.rejects(
    readModelStreamChunk(failed, 100),
    /mid-stream socket failure/,
  );
});
