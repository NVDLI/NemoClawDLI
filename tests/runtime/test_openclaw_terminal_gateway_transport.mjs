// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
// Locale materialization supplies HTML overlays; their shared runtime owner is canonical.
const course = createRequire(import.meta.url)('./course_exercise_fixture.cjs').discoverCourses(root).roots[0];
const prefix = '__DLI_GATEWAY__';
const packet = value => prefix + Buffer.from(JSON.stringify(value)).toString('base64') + '\r\n';

const file = path.join(course, 'scripts/_connection.js');
assert.ok(fs.existsSync(file), 'Missing shared gateway transport in ' + path.relative(root, course));
const {GatewayTerminalSocket, gatewayTerminalPath} = await import(pathToFileURL(file));
test(path.relative(root, course) + ': terminal gateway preserves frame and close semantics', () => {
  const original = globalThis.WebSocket;
  let terminal;
  globalThis.WebSocket = class {
    sent = [];
    closes = 0;
    constructor(url) { this.url = url; terminal = this; }
    send(value) { this.sent.push(JSON.parse(value)); }
    close() { this.closes++; }
  };
  try {
    const socket = new GatewayTerminalSocket('wss://approved.example/ws/terminal');
    const messages = []; let opens = 0, closes = 0, errors = 0;
    socket.onopen = () => { opens++; };
    socket.onmessage = event => messages.push(event.data);
    socket.onclose = () => { closes++; };
    socket.onerror = () => { errors++; };
    assert.throws(() => socket.send('before-ready'), /not open/);
    const output = text => terminal.onmessage({data:JSON.stringify({type:'output',data:text})});
    output('an unrelated launchable diagnostic\r\n');
    assert.equal(opens, 0);
    const joined = packet({type:'open'}) + packet({type:'message',data:'{"message":"你好 🌐\\nline"}'});
    for (let i = 0; i < joined.length; i += 7) output(joined.slice(i, i + 7));
    assert.equal(opens, 1);
    assert.deepEqual(messages, ['{"message":"你好 🌐\\nline"}']);
    const request = JSON.stringify({method:'connect',params:{auth:{deviceToken:'synthetic-device-secret'},text:'世界'}});
    socket.send(request);
    assert.equal(terminal.sent[0].type, 'input');
    assert.equal(Buffer.from(terminal.sent[0].data.trim(), 'base64').toString(), request);
    assert.doesNotMatch(terminal.url, /synthetic-device-secret/);
    output(packet({type:'close',code:1000}));
    terminal.onclose();
    assert.equal(closes, 1);
    assert.equal(errors, 0);
    assert.equal(socket.readyState, 3);
    assert.throws(() => socket.send('after-close'), /not open/);
  } finally { globalThis.WebSocket = original; }
});

test(path.relative(root, course) + ': failed or cancelled terminal cannot become a connected gateway', () => {
  const original = globalThis.WebSocket;
  let terminal;
  globalThis.WebSocket = class { constructor() { terminal = this; } close() {} };
  try {
    for (const cause of ['malformed', 'early-message', 'exit', 'error', 'cancel']) {
      const socket = new GatewayTerminalSocket('wss://approved.example/ws/terminal');
      let opens = 0, closes = 0;
      socket.onopen = () => { opens++; };
      socket.onclose = () => { closes++; };
      if (cause === 'cancel') socket.close();
      else if (cause === 'error') terminal.onerror();
      else terminal.onmessage({data:JSON.stringify(cause === 'exit' ? {type:'exit',code:0} :
        {type:'output',data:cause === 'malformed' ? prefix + '!invalid!\n' : packet({type:'message',data:'early'})})});
      terminal.onmessage({data:JSON.stringify({type:'output',data:packet({type:'open'})})});
      terminal.onclose();
      assert.equal(opens, 0, cause);
      assert.equal(closes, 1, cause);
      assert.equal(socket.readyState, 3, cause);
    }
  } finally { globalThis.WebSocket = original; }
});

test(path.relative(root, course) + ': loopback program disables echo before readiness and forwards stdin only to the fixed gateway', () => {
  const command = new URL('https://launchable.example' + gatewayTerminalPath()).searchParams.get('cmd');
  const match = command.match(/^node -e eval\(Buffer\.from\("([A-Za-z0-9+/=]+)","base64"\)\.toString\(\)\)$/);
  assert.ok(match);
  const program = Buffer.from(match[1], 'base64').toString();
  const events = [], input = {}, output = []; let gateway;
  class ExternalGateway {
    readyState = 1;
    listeners = {};
    constructor(url) { assert.equal(url, 'ws://127.0.0.1:18789'); gateway = this; }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    send(value) { events.push(['input', value]); }
    close() { events.push(['close']); }
  }
  vm.runInNewContext(program, {WebSocket:ExternalGateway,Buffer,setTimeout:() => 1,
    process:{stdin:{isTTY:true,setRawMode:value => events.push(['raw',value]),setEncoding(){},on:(name,callback) => {input[name] = callback;}},
      stdout:{write:value => output.push(value)},exit:code => events.push(['exit',code])}});
  assert.deepEqual(events, [['raw',true]]);
  gateway.listeners.open();
  const request = JSON.stringify({method:'models.list',params:{}});
  const encoded = Buffer.from(request).toString('base64');
  input.data(encoded.slice(0, 5)); input.data(encoded.slice(5) + '\n');
  assert.deepEqual(events[1], ['input',request]);
  gateway.listeners.message({data:'{"type":"event","event":"connect.challenge"}'});
  const decoded = output.map(line => JSON.parse(Buffer.from(line.trim().slice(prefix.length), 'base64').toString()));
  assert.deepEqual(decoded.map(value => value.type), ['open','message']);
  assert.match(decoded[1].data, /connect.challenge/);
  input.end();
  assert.ok(events.some(value => value[0] === 'close'));
});
