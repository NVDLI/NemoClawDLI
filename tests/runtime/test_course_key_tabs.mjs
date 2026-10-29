// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// On a NemoClaw launchable the course's tabs share the key each tab holds over a same-origin
// BroadcastChannel. This test plays the other tab with a raw channel, because one Node process has
// one sessionStorage, and loads a fresh copy of the course helpers for each page origin. The origin
// test runs first, so no launchable copy is listening yet.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const course = fs.readdirSync(path.join(root, 'web'), { withFileTypes:true })
  .filter(entry => entry.isDirectory())
  .map(entry => path.join(root, 'web', entry.name))
  .find(directory => fs.existsSync(path.join(directory, 'scripts', '_shared.js')));
const sharedUrl = pathToFileURL(path.join(course, 'scripts', '_shared.js')).href;
const CHANNEL = 'nemoclaw-course-key-v1';
const LAUNCHABLE = 'https://nemoclaw-example-tab.gobrev.dev/dli/nemoclaw/01a-loop.html';

function memoryStorage() {
  const values = new Map();
  return {
    getItem:key => values.has(key) ? values.get(key) : null,
    setItem:(key, value) => values.set(key, String(value)),
    removeItem:key => values.delete(key),
  };
}

function peer() {
  const channel = new BroadcastChannel(CHANNEL);
  const received = [];
  channel.onmessage = ({ data }) => received.push(data);
  return { channel, received };
}

const settle = () => new Promise(resolve => setTimeout(resolve, 60));

async function openTab(page, tag) {
  globalThis.location = new URL(page);
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  return import(`${sharedUrl}?tab=${tag}`);
}

test('published course origins and plain-HTTP hosts never open the channel', async () => {
  for (const [page, tag] of [['https://nvdli.github.io/NemoClawDLI/nemoclaw/01a-loop.html', 'pages'],
    ['http://nemoclaw-example-tab.gobrev.dev/dli/nemoclaw/01a-loop.html', 'http'],
    ['https://course-example-tab.gobrev.dev/dli/nemoclaw/01a-loop.html', 'course-link']]) {
    const other = peer();
    const tab = await openTab(page, tag);
    await settle();
    tab.setKey('nvapi-stays-in-this-tab');
    other.channel.postMessage({ type:'ask' });
    await settle();
    assert.deepEqual(other.received, [], page);
    other.channel.close();
  }
});

test('a new launchable tab takes the key from an open tab, answers for it, and shares a new one', async () => {
  const other = peer();
  other.channel.onmessage = ({ data }) => {
    other.received.push(data);
    if (data?.type === 'ask') other.channel.postMessage({ type:'key', key:'nvapi-from-another-tab' });
  };
  const tab = await openTab(LAUNCHABLE, 'new');
  await settle();
  assert.deepEqual(other.received[0], { type:'ask' });
  assert.equal(tab.getKey(), 'nvapi-from-another-tab');

  other.received.length = 0;
  other.channel.postMessage({ type:'ask' });
  await settle();
  assert.deepEqual(other.received.at(-1), { type:'key', key:'nvapi-from-another-tab' });

  other.received.length = 0;
  tab.setKey('nvapi-entered-here');
  await settle();
  assert.deepEqual(other.received.at(-1), { type:'key', key:'nvapi-entered-here' });

  other.channel.postMessage({ type:'key', key:'nvapi-someone-else' });
  await settle();
  assert.equal(tab.getKey(), 'nvapi-entered-here', 'a tab that holds a key keeps it');

  tab.setKey('');
  await settle();
  assert.equal(other.received.filter(message => message.key === '').length, 0, 'clearing a key is not broadcast');
  other.channel.close();
});
