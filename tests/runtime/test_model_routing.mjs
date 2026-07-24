// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import { sharedRuntime } from './course_runtime_fixture.mjs';

const {
  DEFAULT_MODEL_API_BASE_URL,
  defaultIframeProxyModeForLocation,
  fetchRetry,
  getConfig,
  setIframeProxyMode,
  setModelApiBaseUrl,
} = sharedRuntime;

test('the model relay default covers the exact DLI CDN origin and local file previews', () => {
  assert.equal(defaultIframeProxyModeForLocation('https://cdn.dli.learn.nvidia.com/course-static/nemoclaw/'), true);
  assert.equal(defaultIframeProxyModeForLocation('file:course-preview.html'), true);
  assert.equal(defaultIframeProxyModeForLocation('http://cdn.dli.learn.nvidia.com/course-static/nemoclaw/'), false);
  assert.equal(defaultIframeProxyModeForLocation('https://cdn.dli.learn.nvidia.com.example.invalid/'), false);
  assert.equal(defaultIframeProxyModeForLocation('https://example.com/'), false);
  assert.equal(defaultIframeProxyModeForLocation('data:text/html,course'), false);
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
