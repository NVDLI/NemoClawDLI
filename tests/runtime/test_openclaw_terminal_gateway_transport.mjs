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
  vm.runInNewContext(program, {WebSocket:ExternalGateway,Buffer,setTimeout:() => 1,clearTimeout(){},
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

function loopbackFixture() {
  const command = new URL('https://launchable.example' + gatewayTerminalPath()).searchParams.get('cmd');
  const program = Buffer.from(command.match(/Buffer\.from\("([A-Za-z0-9+/=]+)"/)[1], 'base64').toString();
  const sockets = [], input = {}, output = [], timers = new Map();
  let sequence = 0;
  class Gateway {
    readyState = 1; listeners = {}; sent = []; closes = 0;
    constructor(url) { assert.equal(url,'ws://127.0.0.1:18789'); sockets.push(this); }
    addEventListener(name,callback) { this.listeners[name] = callback; }
    send(data) { this.sent.push(data); }
    close() { this.closes++; this.readyState = 3; this.listeners.close?.({code:1000}); }
    event(name,value = {}) { this.listeners[name](value); }
  }
  vm.runInNewContext(program,{WebSocket:Gateway,Buffer,
    setTimeout(callback,ms) { const id=++sequence;timers.set(id,{callback,ms});return id; },
    clearTimeout(id) {timers.delete(id);},
    process:{stdin:{setEncoding(){},on(name,callback){input[name]=callback;}},
      stdout:{write(line){output.push(JSON.parse(Buffer.from(line.trim().slice(prefix.length),'base64').toString()));}},exit(){}}});
  return {sockets,input,output,timers,retry() {
    const entry = [...timers].find(([,timer])=>timer.ms===250);
    assert.ok(entry,'one bounded reconnect scheduled');
    timers.delete(entry[0]);entry[1].callback();
  }};
}

test('loopback retries once before traffic, suppressing stale callbacks and duplicate readiness', () => {
  for (const opened of [false,true]) for (const cause of ['error',1006,1011]) {
    const f = loopbackFixture(), first = f.sockets[0];
    if (opened) first.event('open');
    first.event(cause === 'error' ? 'error' : 'close',{code:cause});
    assert.equal(first.closes,1);
    first.event('message',{data:'stale challenge'});
    first.event('open');
    first.event('error');
    f.retry();
    assert.equal(f.sockets.length,2);
    const second=f.sockets[1];second.event('open');
    second.event('message',{data:'current challenge'});
    const request='{"method":"connect"}';
    f.input.data(Buffer.from(request).toString('base64')+'\n');
    assert.deepEqual(first.sent,[]);
    assert.deepEqual(second.sent,[request]);
    assert.deepEqual(f.output,[{type:'open'},{type:'message',data:'current challenge'}]);
    second.event('close',{code:1011});
    assert.equal(f.output.at(-1).code,1011);
    assert.equal([...f.timers.values()].filter(timer=>timer.ms===250).length,0);
  }
});

test('loopback never retries observed frames, browser input, or nontransient closes', () => {
  for (const before of ['message','malformed','input','partial-input',1000,1008,4001]) {
    const f=loopbackFixture(), socket=f.sockets[0];socket.event('open');
    if (before==='message') socket.event('message',{data:'challenge'});
    if (before==='malformed') socket.event('message',{data:new Uint8Array([1])});
    if (before==='input') f.input.data(Buffer.from('request').toString('base64')+'\n');
    if (before==='partial-input') f.input.data('c');
    socket.event('close',{code:typeof before==='number'?before:1011});
    assert.equal(f.sockets.length,1,String(before));
    assert.equal([...f.timers.values()].filter(timer=>timer.ms===250).length,0,String(before));
    assert.equal(f.output.filter(frame=>frame.type==='close').length,1);
  }
});

test('loopback Stop clears pending recovery and closes owned sockets without replay', () => {
  for (const phase of ['pending','reconnected','second-failure']) {
    const f=loopbackFixture();f.sockets[0].event('error');
    const pending=[...f.timers.values()].find(timer=>timer.ms===250).callback;
    if (phase!=='pending') f.retry();
    if (phase==='second-failure') f.sockets[1].event('error');
    f.input.end();
    pending(); // Even an already-queued callback cannot revive a stopped bridge.
    f.input.data(Buffer.from('late request').toString('base64')+'\n');
    assert.equal(f.sockets.length,phase==='pending'?1:2);
    assert.ok(f.sockets.every(socket=>socket.closes===1 && socket.sent.length===0));
    assert.equal([...f.timers.values()].filter(timer=>timer.ms===250).length,0);
    assert.equal(f.output.filter(frame=>frame.type==='close').length,1);
  }
});
