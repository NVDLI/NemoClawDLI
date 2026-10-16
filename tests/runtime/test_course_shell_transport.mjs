// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath, pathToFileURL} from 'node:url';

assert.equal(process.platform, 'linux', 'Real shell-boundary tests require the Linux course runtime');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const {discoverCourses} = createRequire(import.meta.url)('./course_exercise_fixture.cjs');
const course = discoverCourses(root).roots[0];
const shared = await import(pathToFileURL(path.join(course, 'scripts/_shared.js')));
const {courseShell, sandboxExec} = await import(pathToFileURL(path.join(course, 'scripts/_openshell.js')));

function fixture(t, mode) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'course-shell-'));
  t.after(() => fs.rmSync(directory, {recursive:true, force:true}));
  const host = path.join(directory, 'host'), child = path.join(directory, 'child');
  fs.mkdirSync(host); fs.mkdirSync(child);
  // The external sandbox executable changes working directory before exec. Both
  // shells and argv parsers are real; a misplaced redirection lands in host/.
  const executable = path.join(directory, 'openshell');
  fs.writeFileSync(executable, '#!/bin/sh\n'
    + '[ "$1" = sandbox ] && [ "$2" = exec ] && [ "$3" = -n ] && [ "$4" = fixture ] && [ "$5" = -- ] || exit 125\n'
    + 'shift 5\ncd "$COURSE_TEST_CHILD" || exit 125\nexec "$@"\n', {mode:0o755});
  const env = {PATH:directory + ':/usr/local/bin:/usr/bin:/bin', COURSE_TEST_CHILD:child};
  const calls = [], results = [];
  const controller = new AbortController();
  const helpers = {signal:controller.signal, sandboxExec:async (command, {signal}) => {
    assert.equal(signal, controller.signal);
    signal.throwIfAborted();
    calls.push(command);
    const line = 'openshell sandbox exec -n fixture -- ' + command;
    let result;
    if (mode === 'shell') {
      result = spawnSync('/bin/sh', ['-c', line], {cwd:host, env, encoding:'utf8'});
    } else {
      const argv = mode === 'whitespace' ? line.split(/\s+/) : JSON.parse(spawnSync('python3',
        ['-c', 'import json,shlex,sys;print(json.dumps(shlex.split(sys.argv[1])))', line],
        {env, encoding:'utf8'}).stdout);
      result = spawnSync(executable, argv.slice(1), {cwd:host, env, encoding:'utf8'});
    }
    assert.ifError(result.error);
    const observed = {exitCode:result.status, completion:result.signal ? 'disconnect' : 'exit',
      stdout:result.stdout, stderr:result.stderr, output:result.stdout + result.stderr};
    results.push(observed);
    return observed;
  }};
  return {helpers, controller, host, child, calls, results};
}

function terminalFixture(t, mode, afterProbe = () => {}) {
  const f = fixture(t,mode), errors = [], urls = [];
  const previous = {localStorage:globalThis.localStorage, sessionStorage:globalThis.sessionStorage,
    WebSocket:globalThis.WebSocket, fetch:globalThis.fetch};
  const storage = () => { const values = new Map(); return {
    getItem:key => values.get(key) ?? null, setItem:(key,value) => values.set(key,String(value)),
    removeItem:key => values.delete(key),
  }; };
  globalThis.localStorage = storage(); globalThis.sessionStorage = storage();
  const owner = 'https://nemoclaw-shell-fixture.brevlab.com';
  shared.setOpenClawConnection({rawUrl:owner,token:'',accessSession:''});
  let metadataReads = 0;
  globalThis.fetch = async () => {
    metadataReads++;
    return new Response(JSON.stringify({agent:{name:'fixture'}}),{status:200});
  };
  globalThis.WebSocket = class {
    constructor(url) {
      urls.push(url); this.readyState = 1;
      queueMicrotask(async () => {
        try {
          this.onopen?.();
          const command = new URL(url).searchParams.get('cmd');
          const prefix = 'openshell sandbox exec -n fixture -- ';
          assert(command.startsWith(prefix));
          const result = await f.helpers.sandboxExec(command.slice(prefix.length), {signal:f.controller.signal});
          if (f.calls.length === 1) afterProbe();
          this.onmessage?.({data:JSON.stringify({type:'output',stream:'stdout',data:result.stdout})});
          this.onmessage?.({data:JSON.stringify({type:'output',stream:'stderr',data:result.stderr})});
          this.onmessage?.({data:JSON.stringify({type:'exit',code:result.exitCode})});
        } catch (error) { errors.push(error); this.onclose?.(); }
      });
    }
    close() { this.readyState = 3; }
  };
  t.after(() => {
    Object.assign(globalThis,previous);
    assert.deepEqual(errors,[]);
  });
  return {...f,urls,owner,metadataReads:() => metadataReads};
}

for (const mode of ['shell', 'quoted-argv', 'whitespace']) {
  test(mode + ': Unicode, newlines and redirections remain in sandbox', async t => {
    const f = fixture(t, mode);
    const text = "第一行\nfrançais 'quoted' $literal\n";
    const command = "cat > retained.txt <<'COURSE_EOF'\n" + text + 'COURSE_EOF\ncat retained.txt';
    assert.equal(await courseShell(f.helpers, command), text);
    assert.equal(fs.readFileSync(path.join(f.child,'retained.txt'),'utf8'), text);
    assert(!fs.existsSync(path.join(f.host,'retained.txt')), 'host shell must not own redirection');
    assert.equal(f.calls.length,2, 'probe plus exactly one learner action');
    assert.equal(f.results[1].exitCode,0);
    assert.equal(f.results[1].completion,'exit');
  });

  test(mode + ': exact nonzero exit survives; learner action never retries', async t => {
    const f = fixture(t, mode);
    await assert.rejects(courseShell(f.helpers, 'printf once >> attempts.txt\nexit 37'), /exit 37; exit/);
    assert.equal(f.results[1].exitCode,37);
    assert.equal(fs.readFileSync(path.join(f.child,'attempts.txt'),'utf8'),'once');
    assert(!fs.existsSync(path.join(f.host,'attempts.txt')));
    assert.equal(f.calls.length,2);
  });

  test(mode + ': missing file fails rather than returning framed success', async t => {
    const f = fixture(t, mode);
    await assert.rejects(courseShell(f.helpers, "printf '\\036' && base64 < missing.txt && printf '\\037'"), /did not complete successfully/);
    assert.notEqual(f.results[1].exitCode,0);
    assert(!f.results[1].stdout.includes('\x1f'));
    assert.equal(f.calls.length,2);
  });

  test(mode + ': sandbox shell mode preserves denial status and one captured sandbox', async t => {
    const f = terminalFixture(t,mode);
    const command = "printf 'Permission denied\\n' >&2\nprintf once > attempts.txt\nexit 13";
    const result = await sandboxExec(command,{shell:true,signal:f.controller.signal});
    assert.equal(result.exitCode,13);
    assert.equal(result.completion,'exit');
    assert.equal(result.stderr,'Permission denied');
    assert.equal(result.stdout,'');
    assert.equal(result.command,command);
    assert.equal(result.sandbox,'fixture');
    assert.equal(f.metadataReads(),1,'probe and action share the selected sandbox');
    assert.equal(f.calls.length,2);
    assert(f.urls.every(url => new URL(url).origin === f.owner.replace('https:','wss:')));
    assert.equal(fs.readFileSync(path.join(f.child,'attempts.txt'),'utf8'),'once');
    assert(!fs.existsSync(path.join(f.host,'attempts.txt')));
  });
}

test('sandbox raw mode remains a single argv command without a probe', async t => {
  const f = terminalFixture(t,'whitespace');
  const result = await sandboxExec('printf raw',{signal:f.controller.signal});
  assert.equal(result.output,'raw');
  assert.deepEqual(f.calls,['printf raw']);
});

test('runtime change during sandbox probe prevents learner execution', async t => {
  const f = terminalFixture(t,'whitespace',() => shared.setOpenClawConnection({
    rawUrl:'https://nemoclaw-other-fixture.brevlab.com',token:'',accessSession:'',
  }));
  await assert.rejects(sandboxExec('printf forbidden > attempts.txt',{shell:true,signal:f.controller.signal}),/runtime changed/);
  assert.equal(f.calls.length,1);
  assert(!fs.existsSync(path.join(f.child,'attempts.txt')));
  assert(!fs.existsSync(path.join(f.host,'attempts.txt')));
});

test('unknown, malformed and incomplete probes never run the learner command', async () => {
  for (const result of [
    {output:'DLI-ARGab-END',exitCode:0,completion:'exit'},
    {output:'DLI-ARG a b-END\n',exitCode:0,completion:'exit'},
    {output:"'DLI-ARGab-END'",exitCode:1,completion:'exit'},
    {output:'DLI-ARG a b-END',exitCode:0,completion:'idle'},
    {output:'DLI-ARG a b-END',exitCode:null,completion:'disconnect'},
  ]) {
    const commands = [];
    const helpers = {sandboxExec:async command => { commands.push(command); return result; }};
    await assert.rejects(courseShell(helpers,'printf forbidden > learner.txt'), /probe did not complete|parsing is unsupported/);
    assert.deepEqual(commands,["printf %s 'DLI-ARG a b-END'"]);
  }
});

test('Stop after probe prevents learner action', async () => {
  const controller = new AbortController(), commands = [];
  const helpers = {signal:controller.signal,sandboxExec:async command => {
    commands.push(command); controller.abort();
    return {output:'DLI-ARG a b-END',exitCode:0,completion:'exit'};
  }};
  await assert.rejects(courseShell(helpers,'printf forbidden'),{name:'AbortError'});
  assert.equal(commands.length,1);
});
