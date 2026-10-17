// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import vm from 'node:vm';
import {spawnSync, spawn} from 'node:child_process';

const html = fs.readFileSync(new URL('../../web/nemoclaw/04a-safety.html', import.meta.url), 'utf8');
const mounts = new Map();
const moduleTag = '<script type="module">';
const moduleStart = html.lastIndexOf(moduleTag);
const moduleEnd = html.indexOf('</script>', moduleStart);
assert(moduleStart >= 0 && moduleEnd > moduleStart, 'authored lesson module must be complete');
const script = html.slice(moduleStart + moduleTag.length, moduleEnd).replace(/^import .*?;\s*$/gm, '');
const noop = () => {};
vm.runInNewContext(script, {
  document: {getElementById: () => ({}), querySelector: () => null},
  buildNav: () => '', updateKeyPill: noop, updateClawPill: noop,
  mountJourneyMap: noop, hljs: {highlightAll: noop}, mountGwRecover: noop,
  mountDiagram: noop, GW_CONNECT: '',
  mountRunCell: (id, options) => mounts.set(id, options),
  mountCanvasFlow: (id, options) => mounts.set(id, options),
});
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const cell = (id, node) => {
  const options = mounts.get(id);
  assert(options, 'authored exercise must exist: ' + id);
  const code = node ? options.nodes.find(entry => entry.id === node)?.code : options.code;
  assert.equal(typeof code, 'string');
  return new AsyncFunction('state', 'helpers', 'window', 'AbortSignal', code);
};
function fixture() {
  const state = {};
  const window = {};
  const log = Object.assign(noop, {details: noop});
  const helpers = {log, getOpenClawConnection: () => ({rawUrl: 'https://fixture.example'}),
    evalSandboxNetwork: () => ({action: 'allow'}),
    sandboxExec: async () => ({exitCode: 0, stdout: 'code=200', output: 'code=200'}),
    mountPolicyMap: noop};
  return {state, window, helpers, run: (id, node) => cell(id, node)(state, helpers, window, new AbortController().signal)};
}

test('missing lesson prerequisites reject instead of producing successful nodes', async () => {
  const f = fixture();
  await assert.rejects(f.run('#cell-predict-confirm', 'predict'), /Read your launchable/);
  await assert.rejects(f.run('#cell-predict-confirm', 'confirm'), /Run Predict first/);
  await assert.rejects(f.run('#cell-predict-confirm', 'compare'), /same action first/);
  await assert.rejects(f.run('#cell-token', 'tok-survey'), /Run Connect first/);
  f.helpers.policyGet = async () => ({parseError: 'invalid YAML', raw: 'invalid'});
  await assert.rejects(f.run('#cell-live-policy'), /Could not parse/);
  assert.equal(f.window.__SBX_POLICY, null);
});

test('valid prediction and confirmation compare; a changed selection cannot publish stale evidence', async () => {
  const f = fixture();
  Object.assign(f.window, {__SBX_POLICY: {}, __SBX_POLICY_OWNER: 'https://fixture.example',
    __SBX_POLICY_AGENT: 'fixture-agent', __SBX_POLICY_LOAD: 1});
  await f.run('#cell-predict-confirm', 'predict');
  await f.run('#cell-predict-confirm', 'confirm');
  assert.equal((await f.run('#cell-predict-confirm', 'compare')).agree, true);
  f.helpers.sandboxExec = async () => {
    f.window.__sbxAction = {...f.state.action, host: 'changed.example'};
    return {exitCode: 0, output: 'code=200'};
  };
  await assert.rejects(f.run('#cell-predict-confirm', 'confirm'), /changed while this request ran/);
  assert.equal(f.state.observed, null);
  await assert.rejects(f.run('#cell-predict-confirm', 'compare'), /same action first/);
});

async function packageCommands() {
  const f = fixture();
  const commands = [];
  f.helpers.sandboxExec = async command => {
    commands.push(command);
    return {exitCode: 0, output: '', completion: 'exit'};
  };
  await f.run('#cell-layers');
  assert(commands.some(command => command.includes('/proc/1/environ') && command.includes('count=0')));
  return commands.filter(command => command.includes('nemoclaw-packages.XXXXXX'));
}

test('incomplete command evidence stops the exercise; ordinary failures remain diagnostic results', async () => {
  const f = fixture();
  let calls = 0;
  f.helpers.sandboxExec = async () => { calls++; return {output: 'transport ended'}; };
  await assert.rejects(f.run('#cell-layers'), /No exit status arrived/);
  assert.equal(calls, 1, 'an incomplete probe must prevent later commands');
  f.helpers.sandboxExec = async () => ({exitCode: 1, output: 'command unavailable'});
  await assert.rejects(f.run('#cell-layers'), /command unavailable/);
  let index = 0;
  f.helpers.sandboxExec = async () => ++index === 1
    ? {exitCode: 1, output: 'permission denied'}
    : {exitCode: 1, output: 'command unavailable'};
  const result = await f.run('#cell-layers');
  assert(result.probes > 1);
  assert.equal(result.results[0].outcome, 'access-denial evidence');
  assert(result.results.slice(1).every(item => item.outcome === 'command failed'));
});

test('an unresolved confirmation cannot complete the policy comparison', async () => {
  const f = fixture();
  Object.assign(f.window, {__SBX_POLICY: {}, __SBX_POLICY_OWNER: 'https://fixture.example',
    __SBX_POLICY_AGENT: 'fixture-agent', __SBX_POLICY_LOAD: 1});
  await f.run('#cell-predict-confirm', 'predict');
  f.helpers.sandboxExec = async () => ({exitCode: 7, output: 'connection unavailable'});
  await f.run('#cell-predict-confirm', 'confirm');
  assert.equal(f.state.observed, 'unknown');
  await assert.rejects(f.run('#cell-predict-confirm', 'compare'), /did not establish an allow\/deny result/);
});

test('real npm accepts the authored isolated configuration and rejects a duplicate config path', async () => {
  const commands = await packageCommands();
  const command = commands.find(command => command.includes('npm install'));
  // Exercise the installed npm config loader without fetching or installing a package.
  // Only the command verb/package are changed; all authored config paths and flags remain.
  const inspect = command.replace('npm install ', 'npm config get userconfig ').replace(' left-pad', '');
  assert.notEqual(inspect, command);
  const run = source => spawnSync('/bin/sh', ['-c', source], {encoding: 'utf8', timeout: 5000,
    env: {PATH: path.dirname(process.execPath) + ':/usr/local/bin:/usr/bin:/bin'}});
  const result = run(inspect);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /\/dev\/null/);
  const mutation = inspect.replace('--globalconfig "$probe_dir/npm-globalrc"', '--globalconfig /dev/null');
  assert.notEqual(mutation, inspect, 'duplicate-config mutation must reach the authored arguments');
  const rejected = run(mutation);
  assert.notEqual(rejected.status, 0, 'real npm accepted loading one file as both configuration layers');
  assert.match(rejected.stderr, /double-loading config/i);
  for (const output of [result.stdout, rejected.stdout]) {
    const dir = output.match(/Temporary probe directory: (.+)/)?.[1];
    assert(dir, output);
    assert.equal(fs.existsSync(dir), false);
  }
});

test('authored package commands isolate writes and preserve failure evidence while cleaning up', async () => {
  const commands = await packageCommands();
  assert.equal(commands.length, 3);
  assert.match(commands[0], /download cowsay/);
  assert.doesNotMatch(commands[0], /install/);
  assert.match(commands[1], /--target/);
  assert.match(commands[1], /--only-binary=:all:/);
  assert.match(commands[2], /--ignore-scripts/);
  assert.match(commands[2], /--prefix/);
  const bin = fs.mkdtempSync(path.join(os.tmpdir(), 'course-package-test-'));
  try {
    for (const exit of [0, 37]) {
      for (const name of ['apt-get', 'pip', 'npm']) fs.writeFileSync(path.join(bin, name),
        '#!/bin/sh\nprintf fixture > owned-artifact\nexit ' + exit + '\n', {mode: 0o755});
      for (const command of commands) {
        const result = spawnSync('/bin/sh', ['-c', command], {encoding: 'utf8',
          env: {PATH: bin + ':/usr/bin:/bin'}, timeout: 5000});
        assert.equal(result.status, exit, result.stderr);
        const dir = result.stdout.match(/Temporary probe directory: (.+)/)?.[1];
        assert(dir, result.stdout + result.stderr);
        assert.equal(fs.existsSync(dir), false, 'owned package directory survived shell exit');
      }
    }
  } finally { fs.rmSync(bin, {recursive: true, force: true}); }
});

test('interrupting an authored package shell removes its owned directory', async () => {
  const [command] = await packageCommands();
  const bin = fs.mkdtempSync(path.join(os.tmpdir(), 'course-package-stop-'));
  const ready = path.join(bin, 'ready');
  fs.writeFileSync(path.join(bin, 'apt-get'), '#!/bin/sh\nprintf ready > "$TEST_READY"\nsleep 20\n', {mode: 0o755});
  const child = spawn('/bin/sh', ['-c', command], {detached: true,
    env: {PATH: bin + ':/usr/bin:/bin', TEST_READY: ready}, stdio: ['ignore', 'pipe', 'pipe']});
  let output = '';
  child.stdout.on('data', data => { output += data; });
  child.stderr.on('data',data=>{output+=data;});
  // The outer launcher can exit before the authored inner shell finishes its trap.
  // Inherited pipes close only after that shell and its cleanup command finish.
  const closed = new Promise(resolve => child.once('close', resolve));
  try {
    const deadline = Date.now() + 3000;
    while (!fs.existsSync(ready)) {
      assert(Date.now() < deadline, 'package fixture did not start');
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    process.kill(-child.pid, 'SIGTERM');
    let timer;
    try {
      await Promise.race([closed, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('Interrupted package shell did not finish cleanup: '+output)), 3000);
      })]);
    } finally { clearTimeout(timer); }
    const dir = output.match(/Temporary probe directory: (.+)/)?.[1];
    assert(dir, output);
    assert.equal(fs.existsSync(dir), false, 'owned directory survived interruption');
  } finally {
    try { process.kill(-child.pid, 'SIGKILL'); } catch {}
    fs.rmSync(bin, {recursive: true, force: true});
  }
});

test('Stop also terminates an owned command before it establishes a process group', async () => {
  const [command] = await packageCommands();
  const bin = fs.mkdtempSync(path.join(os.tmpdir(), 'course-package-startup-'));
  const ready = path.join(bin, 'ready');
  fs.writeFileSync(path.join(bin, 'timeout'), '#!' + process.execPath + '\n' +
    'require("fs").writeFileSync(process.env.TEST_READY,JSON.stringify({pid:process.pid,owner:process.ppid}));setInterval(()=>{},1000);\n', {mode:0o755});
  const child = spawn('/bin/sh', ['-c',command], {detached:true,
    env:{PATH:bin + ':/usr/bin:/bin', TEST_READY:ready}, stdio:['ignore','pipe','pipe']});
  let output='', timer, owned;
  child.stdout.on('data',data=>{output+=data;}); child.stderr.resume();
  const closed=new Promise(resolve=>child.once('close',(code,signal)=>resolve({code,signal})));
  try {
    const deadline=Date.now()+3000;
    while(!fs.existsSync(ready)) {
      assert(Date.now()<deadline,'startup fixture did not start');
      await new Promise(resolve=>setTimeout(resolve,10));
    }
    owned=JSON.parse(fs.readFileSync(ready,'utf8'));
    process.kill(owned.owner,'SIGTERM');
    const result=await Promise.race([closed,new Promise((_,reject)=>{
      timer=setTimeout(()=>reject(new Error('Stop waited for command group initialization')),1500);
    })]);
    assert.notEqual(result.code,0);
    const dir=output.match(/Temporary probe directory: (.+)/)?.[1];
    assert(dir,output); assert.equal(fs.existsSync(dir),false);
    assert.throws(()=>process.kill(owned.pid,0),/ESRCH/,'owned startup process survived Stop');
  } finally {
    clearTimeout(timer);
    if(owned) {try {process.kill(owned.pid,'SIGKILL');} catch {}}
    try {process.kill(-child.pid,'SIGKILL');} catch {}
    fs.rmSync(bin,{recursive:true,force:true});
  }
});

for (const parent of ['resistant', 'responsive', 'exited']) test('package cleanup terminates a resistant descendant with a ' + parent + ' parent', async () => {
  const [original] = await packageCommands();
  const command = original.replace('--kill-after=5s 25s', '--kill-after=0.2s 1s');
  assert.notEqual(command, original);
  const bin = fs.mkdtempSync(path.join(os.tmpdir(), 'course-package-deadline-'));
  const pidFile = path.join(bin, 'descendant');
  const quote = text => "'" + text.replace(/'/g, "'\"'\"'") + "'";
  const program = "process.on('SIGTERM',()=>{});require('fs').writeFileSync(process.env.TEST_PID,String(process.pid));setInterval(()=>{},1000)";
  const behavior = parent === 'resistant' ? 'trap "" TERM\n' : '';
  const finish = parent === 'exited' ? 'while [ ! -s "$TEST_PID" ]; do sleep 0.01; done\nexit 37\n' : 'wait\n';
  fs.writeFileSync(path.join(bin, 'apt-get'), '#!/bin/sh\n' + behavior + quote(process.execPath) + ' -e ' + quote(program) + ' &\n' + finish, {mode:0o755});
  const child = spawn('/bin/sh', ['-c', command], {detached:true,
    env:{PATH:bin + ':/usr/bin:/bin', TEST_PID:pidFile},stdio:['ignore','pipe','pipe']});
  let output = '', timer;
  child.stdout.on('data', data => {output += data;}); child.stderr.resume();
  const closed = new Promise(resolve => child.once('close', (code,signal) => resolve({code,signal})));
  try {
    const result = await Promise.race([closed,new Promise((_,reject) => {
      timer=setTimeout(()=>reject(new Error('Authored deadline left a descendant holding terminal pipes')),3500);
    })]);
    assert.notEqual(result.code,0);
    if (parent === 'exited') assert.equal(result.code,37,'cleanup must preserve the command failure');
    assert(fs.existsSync(pidFile),'TERM-resistant descendant did not start');
    const pid=Number(fs.readFileSync(pidFile,'utf8'));
    const stat='/proc/'+pid+'/stat';
    if(fs.existsSync(stat)) assert.equal(fs.readFileSync(stat,'utf8').split(') ')[1][0],'Z','descendant still running after deadline');
    const dir=output.match(/Temporary probe directory: (.+)/)?.[1];
    assert(dir,output); assert.equal(fs.existsSync(dir),false);
  } finally {
    clearTimeout(timer);
    if(fs.existsSync(pidFile)) {try {process.kill(Number(fs.readFileSync(pidFile,'utf8')),'SIGKILL');} catch {}}
    try {process.kill(-child.pid,'SIGKILL');} catch {}
    fs.rmSync(bin,{recursive:true,force:true});
  }
});
