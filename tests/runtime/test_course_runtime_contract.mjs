// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {execFileSync, spawn} from 'node:child_process';
import vm from 'node:vm';
import {courseServiceFixture, scheduledFile} from './course_service_fixture.mjs';

test('scheduled fixture reads file arguments independently of instruction language', () => {
  const task = {path:'/sandbox/.openclaw/workspace/course-cron-fixture.txt', content:'CRON-fixture'};
  for (const instruction of ['Write the file.', 'Escribe el archivo.', 'Grave o arquivo.', '写入文件。', '寫入檔案。']) {
    assert.deepEqual(scheduledFile(instruction + '\n' + JSON.stringify(task)), task);
  }
  for (const malformed of ['Write exactly CRON-fixture to ' + task.path + '.', '{}', 'null',
    JSON.stringify({...task, path:'/tmp/elsewhere'}), JSON.stringify({...task, content:42}),
    JSON.stringify({...task, content:''})]) assert.throws(() => scheduledFile(malformed));
});
function staticContentType(file) {
  return {'.html':'text/html','.htm':'text/html','.js':'text/javascript','.mjs':'text/javascript',
    '.json':'application/json','.css':'text/css','.svg':'image/svg+xml','.txt':'text/plain'}[path.extname(file)] || 'application/octet-stream';
}

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const {discoverCourses} = createRequire(import.meta.url)('./course_exercise_fixture.cjs');
const course = discoverCourses(root).roots[0];
const profile = JSON.parse(fs.readFileSync(path.join(course,'lesson-map.json'),'utf8'));
const lesson = (module, number) => {
  const matches = profile.lessons.filter(entry => entry.module === module && entry.lesson === number);
  assert.equal(matches.length, 1, 'Expected one declared lesson for the exercised role');
  return path.join(course, matches[0].id + '.html');
};
const lessonRoute = (module, number) => '/' + path.relative(root, lesson(module, number));
const storage = () => {
  const values = new Map();
  return {getItem:key => values.get(key) ?? null, setItem:(key,value) => values.set(key,String(value)), removeItem:key => values.delete(key)};
};
globalThis.localStorage = storage();
globalThis.sessionStorage = storage();
globalThis.location = new URL(lessonRoute(4, 2), 'http://localhost');
const shared = await import(pathToFileURL(path.join(course,'scripts/_shared.js')));
const gateway = await import(pathToFileURL(path.join(course,'scripts/_openclaw.js')));
const shell = await import(pathToFileURL(path.join(course,'scripts/_openshell.js')));
const {bindRunSignal} = await import(pathToFileURL(path.join(course,'scripts/_canvas.js')));
const tick = () => new Promise(resolve => setImmediate(resolve));
async function until(predicate) {
  const deadline = Date.now() + 1000;
  while (!predicate()) {
    assert(Date.now() < deadline, 'fixture did not reach the expected external request');
    await tick();
  }
}
const metadata = (name, token = 'fixture-token') => new Response(JSON.stringify({agent:{name,dashboardUrl:'/#token='+token}}), {status:200});
function connect(name) {
  const rawUrl = 'https://nemoclaw-' + name + '.brevlab.com';
  shared.setOpenClawConnection({rawUrl,token:'fixture-saved-token',accessProvider:'cloudflare',accessSession:''});
  return rawUrl;
}

// These sockets stand only for the external launchable. Requests, parsing,
// subscriptions, cancellation and reconciliation use the production helpers.
function sockets(onRequest) {
  const instances = [], requests = [];
  class Socket {
    static OPEN = 1;
    constructor(url) {
      this.url = url;
      this.readyState = 0;
      instances.push(this);
      queueMicrotask(() => {
        if (this.readyState === 3) return;
        this.readyState = 1;
        this.onopen?.();
        if (new URL(url).pathname.endsWith('/cli/gateway')) this.event({event:'connect.challenge'});
        else onRequest(this,{method:'terminal',command:new URL(url).searchParams.get('cmd')});
      });
    }
    event(frame) { this.onmessage?.({data:JSON.stringify({type:'event',...frame})}); }
    reply(request, payload = {}) { this.event({type:'res',id:request.id,ok:true,payload}); }
    send(raw) {
      const request = JSON.parse(raw);
      requests.push(request);
      if (['connect','sessions.messages.subscribe','chat.abort'].includes(request.method)) this.reply(request);
      onRequest(this,request);
    }
    close() {
      if (this.readyState === 3) return;
      this.readyState = 3;
      this.onclose?.();
    }
  }
  globalThis.WebSocket = Socket;
  return {instances,requests,close:() => instances.forEach(socket => socket.close())};
}

test('metadata refresh cannot replace a newer learner connection', async () => {
  const first = connect('metadata-first');
  let release;
  globalThis.fetch = () => new Promise(resolve => {release=resolve;});
  const pending = gateway.refreshOpenClawGatewayToken({maxAgeMs:0});
  await until(() => release);
  const second = connect('metadata-second');
  release(metadata('first-sandbox'));
  await pending.catch(() => {});
  assert.notEqual(first,second);
  assert.equal(shared.getOpenClawConnection().rawUrl,second,'late metadata restored the previous runtime');
});

test('aborted metadata refresh rejects without saving a fallback token', async () => {
  connect('metadata-stop');
  const controller = new AbortController();
  let started = false;
  globalThis.fetch = (_url,{signal}) => new Promise((_resolve,reject) => {
    started = true;
    signal.addEventListener('abort',() => reject(signal.reason),{once:true});
  });
  const pending = gateway.refreshOpenClawGatewayToken({signal:controller.signal,maxAgeMs:0});
  await until(() => started);
  controller.abort();
  await assert.rejects(pending,{name:'AbortError'});
});

test('changing credentials at the same URL invalidates verified metadata cache', async () => {
  const rawUrl = connect('credential-refresh');
  let requests = 0;
  globalThis.fetch = async () => metadata('sandbox',++requests === 1 ? 'fixture-first-token' : 'fixture-new-token');
  assert.equal((await gateway.refreshOpenClawGatewayToken({maxAgeMs:0})).token,'fixture-first-token');
  shared.setOpenClawConnection({rawUrl,token:'fixture-new-token',accessProvider:'cloudflare',accessSession:''});
  const refreshed = await gateway.refreshOpenClawGatewayToken();
  assert.equal(refreshed.token,'fixture-new-token');
  assert.equal(requests,2,'an edited credential reused metadata verified for another token');
});

test('sandbox selection uses current metadata and rejects a URL switch during discovery', async () => {
  connect('sandbox-a');
  localStorage.setItem('nemoclaw_sandbox_name','obsolete-sandbox');
  let name = 'current-a';
  globalThis.fetch = async () => metadata(name);
  const external = sockets((socket,request) => {
    if (request.method !== 'terminal') return;
    socket.event({type:'data',data:'uid=1000\n'});
    socket.event({type:'exit',code:0});
  });
  try {
    const a = await shell.sandboxExec('id');
    assert.equal(a.sandbox,'current-a');
    name = 'current-b';
    connect('sandbox-b');
    const b = await shell.sandboxExec('id');
    assert.equal(b.sandbox,'current-b');
    assert(external.instances.every(socket => !socket.url.includes('obsolete-sandbox')));
    let release;
    globalThis.fetch = () => new Promise(resolve => {release=resolve;});
    const pending = shell.sandboxExec('id');
    await until(() => release);
    const count = external.instances.length;
    connect('sandbox-c');
    release(metadata('current-b'));
    await assert.rejects(pending,/changed/i);
    assert.equal(external.instances.length,count,'stale metadata opened a command socket');
  } finally { external.close(); }
});

test('a corrected gateway final replaces earlier deltas in the public view contract', async () => {
  connect('corrected-answer');
  globalThis.fetch = async () => metadata('sandbox');
  const external = sockets((socket,request) => {
    if (request.method !== 'chat.send') return;
    socket.reply(request,{runId:'owned-final'});
    queueMicrotask(() => {
      socket.event({event:'agent',payload:{sessionKey:'agent:research:task',runId:'owned-final',stream:'assistant',data:{text:'Old answer that is too long.'}}});
      socket.event({event:'chat',payload:{sessionKey:'agent:research:task',runId:'owned-final',state:'final',message:{content:'Corrected.'}}});
    });
  });
  let rendered = '', final = '';
  try {
    const answer = await gateway.openclawChat('question',{session:'task',idleMs:200,totalMs:500,
      view:{token:text => {rendered+=text;},replaceAnswer:text => {rendered=text;},usage() {}},
      onFinal:text => {final=text;},
    });
    assert.equal(answer,'Corrected.');
    assert.equal(rendered,answer);
    assert.equal(final,answer);
  } finally { external.close(); }
});

test('a gateway run acknowledged after Stop is aborted by its exact run ID', async () => {
  connect('late-acknowledgement');
  globalThis.fetch = async () => metadata('sandbox');
  let acknowledge;
  const external = sockets((socket,request) => {
    if (request.method === 'chat.send') acknowledge = () => socket.reply(request,{runId:'late-run'});
  });
  const controller = new AbortController();
  try {
    const pending = gateway.openclawChat('question',{session:'task',signal:controller.signal,idleMs:200,totalMs:500});
    await until(() => acknowledge);
    controller.abort();
    await assert.rejects(pending,{name:'AbortError'});
    acknowledge();
    await tick();
    assert(external.requests.some(request => request.method === 'chat.abort' && request.params.runId === 'late-run'),
      'late acknowledged run remains active after the learner stopped');
  } finally { external.close(); }
});

test('run signal binding reaches each real HTTP/model helper and cancels its pending request', async () => {
  sessionStorage.setItem('nvapi','fixture-model-key');
  shared.setEmbeddingKey('fixture-embedding-key');
  const calls = {
    chat:helpers => helpers.chat({messages:[{role:'user',content:'fixture'}]}),
    chatStream:helpers => helpers.chatStream({messages:[{role:'user',content:'fixture'}]},null),
    embed:helpers => helpers.embed('fixture'),
    fetch:helpers => helpers.fetch('https://external.example.test/file'),
    fetchRetry:helpers => helpers.fetchRetry('https://external.example.test/file'),
  };
  for (const [name,invoke] of Object.entries(calls)) {
    const controller = new AbortController();
    let requestSignal;
    globalThis.fetch = (_url,options) => new Promise((_resolve,reject) => {
      requestSignal = options.signal;
      if (requestSignal?.aborted) reject(requestSignal.reason);
      else requestSignal?.addEventListener('abort',() => reject(requestSignal.reason),{once:true});
    });
    const helpers = bindRunSignal({...shared.HELPER_FNS,fetch:(...args) => globalThis.fetch(...args)},controller.signal);
    const pending = invoke(helpers);
    await until(() => requestSignal);
    controller.abort();
    await assert.rejects(pending,{name:'AbortError'},name+' ignored the run Stop signal');
    assert.equal(requestSignal.aborted,true);
  }
});

test('run signal binding cancels terminal, sandbox command and delay helpers', async () => {
  for (const name of ['terminal','sandboxExec','delay']) {
    connect('bound-'+name.toLowerCase());
    globalThis.fetch = async () => metadata('bound-sandbox');
    const external = sockets(() => {});
    const controller = new AbortController();
    const helpers = bindRunSignal({...shared.HELPER_FNS},controller.signal);
    try {
      const pending = name === 'delay' ? helpers.delay(5000) : helpers[name]('sleep 30');
      if (name !== 'delay') await until(() => external.instances.some(socket => socket.readyState === 1));
      controller.abort();
      await assert.rejects(pending,{name:'AbortError'});
      assert(external.instances.every(socket => socket.readyState === 3));
    } finally {controller.abort();external.close();}
  }
});

test('native policy confirmation targets the sandbox whose policy was read, even if metadata changes', async () => {
  const rawUrl = connect('policy-owner');
  let discoveries = 0, command = '';
  globalThis.fetch = async () => {discoveries++;return metadata('different-sandbox');};
  const external = sockets((socket,request) => {
    if (request.method !== 'terminal') return;
    command = request.command;
    socket.event({type:'data',data:'code=200'});
    socket.event({type:'exit',code:0});
  });
  const source = fs.readFileSync(lesson(4, 1),'utf8');
  const start = source.indexOf('code: `',source.indexOf('id: "confirm", icon:'))+'code: '.length;
  let end = start+1;
  for (;end<source.length;end++) {if(source[end]==='\\')end++;else if(source[end]==='`')break;}
  const code = vm.runInNewContext(source.slice(start,end+1));
  const action = {binary:'/usr/bin/curl',host:'example.com',port:443};
  const policy = {network_policies:{}};
  const window = {__SBX_POLICY:policy,__SBX_POLICY_AGENT:'policy-owner-sandbox',__SBX_POLICY_LOAD:4,__SBX_POLICY_OWNER:rawUrl};
  const state = {action,actionKey:JSON.stringify(action),predictionRun:1,policyKey:JSON.stringify([rawUrl,window.__SBX_POLICY_AGENT,4,policy])};
  const log = () => {};
  log.details = log;
  try {
    const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
    const result = await new AsyncFunction('helpers','state','window',code)({...shared.HELPER_FNS,log,signal:new AbortController().signal},state,window);
    assert.equal(result.observed,'allow');
    assert.match(command,/openshell sandbox exec -n policy-owner-sandbox --/);
    assert.equal(discoveries,0,'confirmation rediscovered a different sandbox instead of using the captured owner');
  } finally {external.close();}
});

test('native README attachment UI labels fallback, retries, and stops an in-flight asset request', {timeout:60000}, async () => {
  const require = createRequire(path.join(root,'scripts/runtime/package.json'));
  const {chromium} = require('playwright-core');
  const prompts = [];
  let readmeMode = 'failed', readmeRequests = 0, pendingReadme;
  const server = http.createServer((request,response) => {
    const pathname = new URL(request.url,'http://localhost').pathname;
    if (pathname === '/fixture-scroll/nested/region.html') {
      const runtime = '/' + path.relative(root,path.join(course,'scripts/_shared.js'));
      const stylesheet = '/' + path.relative(root,path.join(course,'styles/_style.css'));
      response.writeHead(200,{'content-type':'text/html'}).end(`<!doctype html>
        <html lang="en"><head><link rel="stylesheet" href="${stylesheet}"></head>
        <body><main style="height:5000px">Scroll boundary fixture</main>
        <script type="module">import '${runtime}';</script></body></html>`);
      return;
    }
    if (pathname.startsWith('/fixture-learning/')) {
      const language = new URL(request.url,'http://localhost').searchParams.get('lang');
      assert(['en','es-ES','pt-BR','zh-CN','zh-TW'].includes(language));
      const runtime = '/' + path.relative(root,path.join(course,'scripts/_learning.js'));
      response.writeHead(200,{'content-type':'text/html'}).end(`<!doctype html>
        <html lang="${language}"><body data-learning-view><nav class="topbar"></nav>
        <main><div class="hero"><span class="eyebrow">Original label</span></div></main>
        <script type="module">import {mountLearningView} from '${runtime}'; mountLearningView();</script>
        </body></html>`);
      return;
    }
    if (pathname === '/api/agent') {
      response.writeHead(200,{'content-type':'application/json'}).end(JSON.stringify({agent:{name:'fixture-sandbox',dashboardUrl:'/#token=fixture-token'}}));
      return;
    }
    if (pathname === '/fixture-model/v1/chat/completions') {
      let body = '';
      request.on('data',chunk => {body+=chunk;});
      request.on('end',() => {
        prompts.push(JSON.parse(body));
        response.writeHead(200,{'content-type':'text/event-stream'});
        response.end('data: '+JSON.stringify({model:'fixture-model',choices:[{index:0,delta:{content:'Evidence reviewed.'},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n');
      });
      return;
    }
    if (pathname.endsWith('/cli_readme_claude-code.txt')) {
      readmeRequests++;
      if (readmeMode === 'failed') { response.writeHead(503).end('fixture outage'); return; }
      if (readmeMode === 'pending') { pendingReadme=response; return; }
    }
    const file = path.resolve(root,'.'+pathname);
    if (!file.startsWith(root+path.sep)) {response.writeHead(403).end();return;}
    fs.readFile(file,(error,body) => {
      if (error) {response.writeHead(404).end();return;}
      response.writeHead(200,{'content-type':staticContentType(file)}).end(body);
    });
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser = await chromium.launch({headless:true,executablePath:execFileSync('python3',['scripts/runtime/host_browser.py'],{cwd:root,encoding:'utf8'}).trim(),args:['--no-sandbox']});
    const context = await browser.newContext();
    const origin = 'http://127.0.0.1:'+server.address().port;
    await context.route('**/*',route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    await context.addInitScript(base => {
      sessionStorage.setItem('nvapi','fixture-model-key');
      localStorage.setItem('nemoclaw_model_api_base_url_v1',base+'/fixture-model/v1');
      localStorage.setItem('nemoclaw_model_id_v1','fixture-model');
    },origin);
    const page = await context.newPage();
    for (const [language,label] of [['en','Module 4 · Lesson'],['es-ES','Módulo 4 · Lección'],
      ['pt-BR','Módulo 4 · Lição'],['zh-CN','模块 4 · 课时'],['zh-TW','模組 4 · 課時']]) {
      await page.goto(origin+'/fixture-learning/'+path.basename(lesson(4,2))+'?lang='+language);
      await page.waitForFunction(expected => document.querySelector('.hero .eyebrow')?.textContent.startsWith(expected), label);
      assert((await page.locator('.hero .eyebrow').textContent()).startsWith(label),
        `${language}: the shared lesson map replaced the translated module label`);
      const command = "agent printf '<heading>'";
      await page.evaluate(async ({runtime,command}) => {
        const {mountConsole} = await import(runtime);
        const target = document.createElement('div'); target.id = 'command-fixture'; document.body.append(target);
        mountConsole(target,{suggestions:[{command},'What can you do?'],onSubmit:value=>{window.submittedCommand=value;}});
      }, {runtime:'/'+path.relative(root,path.join(course,'scripts/_chat.js')),command});
      const consoleUi = page.locator('#command-fixture');
      assert.equal(await consoleUi.locator('.da-chip code').textContent(),command);
      assert.equal(await consoleUi.locator('.da-chips .da-chip').nth(1).locator('code').count(),0,
        'natural-language suggestions must remain prose, including in a mixed console');
      assert.equal(await consoleUi.locator('heading').count(),0,'command text must not become HTML');
      await consoleUi.locator('input').fill('agent p');
      await consoleUi.locator('input').press('Tab');
      assert.equal(await consoleUi.locator('input').inputValue(),command);
      await consoleUi.locator('.da-chips .da-chip').nth(1).click();
      assert.equal(await consoleUi.locator('input').inputValue(),'What can you do?');
      await consoleUi.locator('.da-chips .da-chip').first().click();
      await consoleUi.locator('input').press('Enter');
      assert.equal(await page.evaluate(()=>window.submittedCommand),command,
        `${language}: selecting a command must preserve its executable bytes`);
    }
    // Measure wheel chaining without unrelated lesson initialization changing scroll anchors.
    // This new consumer loads the production listener and stylesheet unchanged.
    await page.goto(origin+'/fixture-scroll/nested/region.html');
    const scrolling = await page.evaluate(() => {
      const plain = document.createElement('button');
      document.body.append(plain);
      plain.dispatchEvent(new PointerEvent('pointerover', {bubbles:true,composed:true}));
      const normal = getComputedStyle(plain).overscrollBehavior;
      const panel = document.createElement('div');
      panel.style.cssText = 'height:20px;overflow-y:auto';
      panel.innerHTML = '<button style="height:80px">scroll control</button>';
      document.body.append(panel);
      panel.firstElementChild.dispatchEvent(new PointerEvent('pointerover', {bubbles:true,composed:true}));
      const contained = getComputedStyle(panel).overscrollBehavior;
      panel.replaceChildren();
      panel.dispatchEvent(new WheelEvent('wheel', {bubbles:true,composed:true}));
      const collapsed = getComputedStyle(panel).overscrollBehavior;
      plain.remove(); panel.remove();
      return {normal,contained,collapsed};
    });
    assert.deepEqual(scrolling,{normal:'auto',contained:'contain',collapsed:'auto'});
    await page.evaluate(() => {
      const panel=document.createElement('div');panel.id='wheel-contract';
      panel.style.cssText='position:fixed;top:160px;left:160px;width:180px;height:40px;overflow:auto;z-index:99999';
      panel.innerHTML='<div style="height:200px">wheel boundary</div>';
      document.body.append(panel);panel.scrollTop=panel.scrollHeight;
    });
    await page.mouse.move(0,0);
    await page.locator('#wheel-contract').hover();
    await page.waitForFunction(() => {
      const panel=document.querySelector('#wheel-contract');
      return panel.classList.contains('course-scroll-containment')
        && getComputedStyle(panel).overscrollBehavior==='contain';
    });
    await page.evaluate(() => window.scrollTo({top:500,behavior:'instant'}));
    await page.waitForFunction(()=>scrollY===500);
    const scrollBefore=await page.evaluate(() => scrollY);
    await page.mouse.wheel(0,200);await page.waitForTimeout(150);
    assert.equal(await page.evaluate(() => scrollY),scrollBefore,'overflowing region contains actual wheel input');
    const broken=await page.addStyleTag({content:'body #wheel-contract.course-scroll-containment {overscroll-behavior:auto!important}'});
    await page.mouse.wheel(0,200);await page.waitForTimeout(150);
    assert.ok(await page.evaluate(() => scrollY)>scrollBefore+2,'wheel test detects missing containment');
    await broken.evaluate(node=>node.remove());
    await page.locator('#wheel-contract').evaluate(node=>node.replaceChildren());
    const emptyBefore=await page.evaluate(() => scrollY);
    await page.mouse.wheel(0,200);await page.waitForTimeout(150);
    assert.ok(await page.evaluate(() => scrollY)>emptyBefore+2,'non-overflowing region permits page scrolling');
    assert.equal(await page.locator('#wheel-contract').evaluate(node=>
      node.classList.contains('course-scroll-containment')),false,
      'wheel input clears stale containment after content shrinks under a stationary pointer');
    await page.locator('#wheel-contract').evaluate(node=>node.remove());

    const load = async () => {
      await page.goto(origin+lessonRoute(4, 2));
      await page.locator('#clis-artifact .chatui-send').waitFor();
    };
    const select = async () => page.locator('#clis-readme-bar button').filter({hasText:'Claude Code'}).click();
    const ask = async () => {
      await page.locator('#clis-artifact textarea').fill('Compare the supplied evidence.');
      await page.locator('#clis-artifact .chatui-send').click();
    };
    await load();
    await select();
    await ask();
    await page.locator('#clis-artifact .chatui-state.ready').waitFor();
    assert.equal(prompts.length,1);
    assert.match(prompts[0].messages[0].content,/Claude Code · Course-authored description/);
    assert.match(await page.locator('#clis-artifact .chatui-tool').textContent(),/503/);
    readmeMode='ready';
    await select();
    await ask();
    await page.locator('#clis-artifact .chatui-state.ready').waitFor();
    assert.equal(readmeRequests,2,'transient fallback was cached permanently');
    assert.match(prompts[1].messages[0].content,/Claude Code · Full README/);
    const actual = fs.readFileSync(path.join(course,'assets/cli_readme_claude-code.txt'),'utf8');
    assert(prompts[1].messages[0].content.includes(actual),'full README did not come from the actual vendored asset');

    readmeMode='pending';
    await load();
    await select();
    await ask();
    await until(() => pendingReadme);
    await page.locator('#clis-artifact .chatui-send').click();
    await page.waitForFunction(() => document.querySelector('#clis-artifact .chatui-state')?.textContent.includes('Stopped'));
    assert.equal(prompts.length,2,'stopped README load sent a model request');

    await page.evaluate(async () => {
      const shared = await import('./scripts/_shared.js');
      const element = document.createElement('div');
      element.id='correction-artifact';
      document.querySelector('main').appendChild(element);
      shared.mountChatUI(element,{memory:true,respond:async (_text,{view}) => {
        view.token('Earlier incorrect response.');
        view.replaceAnswer('Authoritative corrected response.');
      }});
    });
    await page.locator('#correction-artifact textarea').fill('Show the final answer.');
    await page.locator('#correction-artifact .chatui-send').click();
    await page.locator('#correction-artifact .chatui-state.ready').waitFor();
    assert.equal(await page.locator('#correction-artifact .chatui-bot').count(),1);
    assert.equal(await page.locator('#correction-artifact .chatui-bot').innerText(),'Authoritative corrected response.');

    await page.evaluate(async () => {
      const shared = await import('./scripts/_shared.js');
      // Only the external gateway is scripted. The CLI, chat transport and views
      // are imported unchanged from their public native owners.
      window.WebSocket = class {
        static OPEN = 1;
        constructor() {
          this.readyState=0;
          queueMicrotask(() => {
            this.readyState=1;
            this.onopen?.();
            this.frame({event:'connect.challenge'});
          });
        }
        frame(frame) {this.onmessage?.({data:JSON.stringify({type:'event',...frame})});}
        send(raw) {
          const request=JSON.parse(raw);
          this.frame({type:'res',id:request.id,ok:true,payload:request.method==='chat.send'?{runId:'cli-owned'}:{}});
          if(request.method!=='chat.send')return;
          queueMicrotask(() => {
            const payload={sessionKey:request.params.sessionKey,runId:'cli-owned'};
            this.frame({event:'agent',payload:{...payload,stream:'assistant',data:{text:'Wrong before tool.'}}});
            this.frame({event:'agent',payload:{...payload,stream:'tool',data:{phase:'start',name:'inspect',toolCallId:'tool-1',args:{path:'fixture'}}}});
            this.frame({event:'agent',payload:{...payload,stream:'tool',data:{phase:'result',name:'inspect',toolCallId:'tool-1',result:'observed'}}});
            this.frame({event:'agent',payload:{...payload,stream:'assistant',data:{text:'Wrong before tool.Wrong after tool.'}}});
            this.frame({event:'chat',payload:{...payload,state:'final',message:{content:'Correct CLI answer.'}}});
          });
        }
        close() {if(this.readyState===3)return;this.readyState=3;this.onclose?.();}
      };
      shared.setOpenClawConnection({rawUrl:location.origin,token:'fixture-token',accessProvider:'auto',accessSession:''});
      localStorage.setItem('nemoclaw_warmed',JSON.stringify(['main']));
      const element=document.createElement('div');
      element.id='cli-correction-artifact';
      document.body.appendChild(element);
      await shared.mountOpenClawCli(element);
    });
    const cli = page.locator('#cli-correction-artifact');
    await cli.locator('input').fill('Inspect the fixture.');
    await cli.locator('input').press('Enter');
    await page.waitForFunction(() => document.querySelector('#cli-correction-artifact .da-out')?.textContent.includes('Correct CLI answer.'));
    assert.doesNotMatch(await cli.locator('.da-out').textContent(),/Wrong before tool|Wrong after tool/);
    assert.equal(await cli.locator('.da-out details').filter({hasText:'Final answer'}).count(),0,'corrected answer remains hidden in a collapsed tool disclosure');
  } finally {
    pendingReadme?.destroy();
    await browser?.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});

test('shared identifiers retain UUID v4 bits and fail without cryptographic randomness', () => {
  const source = fs.readFileSync(path.join(course, 'scripts/_ids.js'), 'utf8')
    .replace('export function randomId', 'function randomId') + '\nrandomId;';
  for (const byte of [0, 255]) {
    const randomId = vm.runInNewContext(source, {
      crypto: {getRandomValues: bytes => bytes.fill(byte)},
      Math: {random() { throw new Error('insecure randomness must never be used'); }},
    });
    assert.equal(randomId(), byte === 0
      ? '00000000-0000-4000-8000-000000000000' : 'ffffffff-ffff-4fff-bfff-ffffffffffff');
    assert.match(randomId('session-'), /^session-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  }
  assert.throws(vm.runInNewContext(source), /Cryptographic random values are unavailable/);
});

test('metadata startup reports retries, cancels promptly and bounds headers and body reads', async () => {
  const previousFetch = globalThis.fetch;
  const starting = () => new Response(JSON.stringify({status:'starting'}), {status:503,headers:{'Retry-After':'0'}});
  try {
    connect('metadata-startup');
    let calls=0;
    const updates=[];
    globalThis.fetch = async () => ++calls === 1 ? starting() : metadata('ready');
    const ready = await gateway.openclawBootstrapRequest('/api/agent', {
      requestTimeoutMs:1000,waitForReadyMs:2000,onRetry:update=>updates.push(update),
    });
    assert.equal(ready.status,200);
    assert.equal(calls,2);
    assert.equal(updates[0].response.status,503);
    assert.equal(updates[0].retryMs,250);

    const stop = new AbortController(); calls=0;
    globalThis.fetch = async () => { calls++; return starting(); };
    await assert.rejects(gateway.openclawBootstrapRequest('/api/agent', {
      signal:stop.signal,onRetry:()=>stop.abort(),
    }), {name:'AbortError'});
    assert.equal(calls,1);

    for (const phase of ['headers','body']) {
      let requestSignal;
      globalThis.fetch = async (_, options) => {
        requestSignal=options.signal;
        if (phase === 'headers') return new Promise(()=>{});
        return new Response(new ReadableStream({start(){}}));
      };
      await assert.rejects(gateway.openclawBootstrapRequest('/api/agent', {requestTimeoutMs:20}), /request timed out/);
      assert.equal(requestSignal.aborted,true);
    }

    calls=0;
    globalThis.fetch = async () => { calls++; return starting(); };
    const saved = await gateway.refreshOpenClawGatewayToken({maxAgeMs:0});
    assert.equal(saved.source,'saved');
    assert.equal(saved.token,'fixture-saved-token');
    assert.equal(calls,1,'saved gateway credentials must not wait for metadata readiness');

    shared.setOpenClawConnection({...shared.getOpenClawConnection(),token:''});
    calls=0;
    globalThis.fetch = async () => {
      calls++;
      return new Response(JSON.stringify({status:'failed',message:'OpenClaw startup failed. Inspect the course runtime logs, then retry.'}), {status:503});
    };
    await assert.rejects(gateway.refreshOpenClawGatewayToken({maxAgeMs:0,
      onRetry:()=>assert.fail('failed startup must not enter the starting retry loop'),
    }), /OpenClaw startup failed\. Inspect the course runtime logs/);
    assert.equal(calls,1);
  } finally { globalThis.fetch=previousFetch; }
});


test('connection audit clears startup progress when metadata passes, fails or is stopped', async () => {
  const previousFetch = globalThis.fetch;
  const previousDocument = globalThis.document, previousWindow = globalThis.window;
  globalThis.document = {documentElement:{lang:"en"},getElementById:()=>null};
  globalThis.window = {dispatchEvent:()=>{}};
  try {
    for (const outcome of ['passed','failed','stopped']) {
      const controller = new AbortController();
      const updates = [];
      let calls = 0;
      globalThis.fetch = async () => {
        calls++;
        if (calls === 1) return new Response(JSON.stringify({status:'starting'}),
          {status:503,headers:{'Retry-After':'0'}});
        return outcome === 'passed' ? metadata('ready')
          : new Response(JSON.stringify({status:'failed',message:'OpenClaw startup failed.'}), {status:503});
      };
      const result = await gateway.runOpenClawConnectionAudit({
        baseUrl:connect('audit-settlement'),signal:controller.signal,
        onStep:step=>{
          updates.push(step);
          if (step.id !== 'agent-metadata') return;
          if ((outcome === 'stopped' && step.progress) || step.status !== 'running') controller.abort();
        },
      });
      const metadataUpdates = updates.filter(step=>step.id === 'agent-metadata');
      assert(metadataUpdates.some(step=>step.status === 'running' && /Retrying/.test(step.progress)),
        'the audit must publish startup progress while it is waiting');
      const final = metadataUpdates.at(-1);
      assert.equal(final.status,outcome === 'passed' ? 'passed' : 'failed');
      assert.equal(final.progress,undefined,'settled diagnostics must not retain retry instructions');
      assert.equal(result.checks.find(step=>step.id === 'agent-metadata').progress,undefined);
      assert.equal(calls,outcome === 'stopped' ? 1 : 2);
    }
  } finally {
    globalThis.fetch=previousFetch; globalThis.document=previousDocument; globalThis.window=previousWindow;
  }
});

test('discovered browser workflows load real modules and reject import, name and callable failures in both origins', {timeout:110000}, async () => {
  const {chromium} = createRequire(path.join(root,'scripts/runtime/package.json'))('playwright-core');
  const {localCourseOrigins, discoverCoursePages, runtimeFailureSnapshot, assertRuntimeSuccess, assertRuntimeCoverage} =
    createRequire(import.meta.url)(path.join(root, 'scripts/runtime/browser_environment.cjs'));
  const requests = [], fixtures = new Map(), moduleOverrides = new Map();
  let pendingMetadata = null;
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, 'http://fixture').pathname;
    if (fixtures.has(pathname)) {
      response.writeHead(200, {'content-type':'text/html'}).end(fixtures.get(pathname)); return;
    }
    if (moduleOverrides.has(pathname)) {
      response.writeHead(200, {'content-type':'text/javascript'}).end(moduleOverrides.get(pathname)); return;
    }
    if (pathname === '/api/agent') {
      if (pendingMetadata) {
        const pending = {response,closed:false}; pendingMetadata.push(pending);
        response.on('close',()=>{pending.closed=true;}); return;
      }
      response.writeHead(200, {'content-type':'application/json'}).end(JSON.stringify({
        agent: {name:'browser-fixture', dashboardUrl:'/#token=fixture-token'},
      })); return;
    }
    const file = path.resolve(root, '.' + pathname);
    if (!file.startsWith(root + path.sep)) { response.writeHead(403).end(); return; }
    fs.readFile(file, (error, body) => {
      if (error) { response.writeHead(404).end(); return; }
      response.writeHead(200, {'content-type':staticContentType(file)}).end(body);
    });
  });
  await new Promise(resolve => server.listen(0, '0.0.0.0', resolve));
  let browser;
  try {
    browser = await chromium.launch({headless:true, executablePath:execFileSync('python3',
      ['scripts/runtime/host_browser.py'],{cwd:root,encoding:'utf8'}).trim()});
    const discovered = discoverCoursePages(course);
    const part3 = profile.lessons.filter(entry => entry.module === 3).map(entry => path.join(course, entry.id + '.html'));
    assert(part3.every(file => discovered.includes(file)), 'all declared Part 3 lessons must enter browser discovery');
    const runtimeUrl = '/' + path.relative(root, path.join(course, 'scripts/_shared.js'));
    for (const environment of localCourseOrigins(server.address().port)) {
      const {origin} = environment;
      const context = await browser.newContext();
      let service = courseServiceFixture();
      const cronWorkflows = [];
      const fixtureErrors = [];
      await context.route('**/*', route => {
        const request = route.request(), target = new URL(request.url());
        if (target.pathname.endsWith('/v1/models')) return route.fulfill({json:{data:[{id:shared.DEFAULT_MODEL}]}});
        if (target.pathname.endsWith('/chat/completions')) {
          const payload = request.postDataJSON();
          const completion = {model:payload.model,choices:[{message:{role:'assistant',content:'Fixture model response.'},finish_reason:'stop'}],usage:{prompt_tokens:1,completion_tokens:3}};
          if (payload.stream) return route.fulfill({contentType:'text/event-stream',body:'data: '+JSON.stringify({model:payload.model,choices:[{delta:{content:'Fixture model response.'},finish_reason:'stop'}]})+'\n\ndata: [DONE]\n\n'});
          return route.fulfill({json:completion});
        }
        return target.origin === origin ? route.continue() : route.abort();
      });
      await context.addInitScript(() => { if (window === window.top) sessionStorage.setItem('nvapi','fixture-model-key'); });
      await context.routeWebSocket(origin.replace('http:', 'ws:') + '/**', socket => {
        const target = new URL(socket.url());
        if (target.pathname === '/ws/terminal') {
          let reply;
          try { reply = service.terminal(target.searchParams.get('cmd')); }
          catch(error) { fixtureErrors.push(String(error)); reply={code:127,data:String(error)}; }
          socket.send(JSON.stringify({type:'output',data:reply.data}));
          if (reply.interactive) {
            let commands = 0;
            socket.onMessage(() => {
              socket.send(JSON.stringify({type:'output',data:'Fixture workspace observation.\n'}));
              if (++commands === 4) socket.send(JSON.stringify({type:'exit',code:0}));
            });
          } else socket.send(JSON.stringify({type:'exit',code:reply.code}));
          return;
        }
        assert.equal(target.pathname,'/cli/gateway');
        socket.onMessage(raw => {
          const request = JSON.parse(raw); requests.push(request);
          let payload;
          try { payload = service.rpc(request.method,request.params); }
          catch(error) {
            fixtureErrors.push(String(error));
            socket.send(JSON.stringify({type:'res',id:request.id,ok:false,error:{message:String(error)}}));
            return;
          }
          socket.send(JSON.stringify({type:'res',id:request.id,ok:true,payload}));
          if (request.method === 'chat.send') {
            let answer;
            try { answer = service.answer(request.params); }
            catch(error) { fixtureErrors.push(String(error)); answer=String(error); }
            const event = {sessionKey:request.params.sessionKey,runId:payload.runId};
            if (request.params.message.includes('HEALTHCHECK_OK')) {
              for (const data of [{phase:'start',name:'exec'}, {phase:'result',name:'exec',result:{exitCode:0,output:'HEALTHCHECK_OK'}}])
                socket.send(JSON.stringify({type:'event',event:'agent',payload:{...event,stream:'tool',data}}));
            }
            socket.send(JSON.stringify({type:'event',event:'chat',payload:{...event,state:'final',
              message:{role:'assistant',content:[{type:'text',text:answer}]},
            }}));
          }
        });
        socket.send(JSON.stringify({type:'event',event:'connect.challenge',payload:{nonce:'fixture'}}));
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('response', response => {
        if (response.request().resourceType() === 'script' && response.status() >= 400) {
          errors.push(`Module response ${response.status()}: ${response.url()}`);
        }
      });
      page.on('requestfailed', request => {
        if (request.resourceType() === 'script' && new URL(request.url()).origin === origin) {
          errors.push(`Module request failed: ${request.url()}: ${request.failure()?.errorText}`);
        }
      });

      for (const file of part3) {
        errors.length = 0;
        await page.goto(origin + '/' + path.relative(root, file));
        await page.waitForFunction(() => document.querySelector('.cf-wrap,.rc-card'));
        assert.equal(await page.evaluate(() => isSecureContext), environment.secure);
        assertRuntimeSuccess(errors, await page.evaluate(runtimeFailureSnapshot));
        await page.evaluate(async ({runtimeUrl, origin}) => {
          const runtime = await import(runtimeUrl);
          runtime.setOpenClawConnection({rawUrl:origin,token:'fixture-token',accessProvider:'auto',accessSession:''});
        }, {runtimeUrl,origin});
        const coverage = await page.evaluate(() => ({
          cells:[...document.querySelectorAll('.cf-wrap,.rc-card')].map(item => item.id || item.parentElement.id),
          controls:[...document.querySelectorAll('button,input,textarea,select')]
            .filter(item=>!item.closest('.cf-wrap,.rc-card'))
            .map(item=>({tag:item.tagName,id:item.id,label:(item.getAttribute('aria-label')||item.textContent||item.placeholder||'').trim().slice(0,80)})),
        }));
        const executed = [], failed = [];
        const buttons = page.locator('.cf-btn-run,.rc-run');
        for (let index=0; index<await buttons.count(); index++) {
          const button = buttons.nth(index);
          const owner = button.locator('xpath=ancestor::*[contains(concat(" ",normalize-space(@class)," ")," cf-wrap ") or contains(concat(" ",normalize-space(@class)," ")," rc-card ")][1]');
          const id = await owner.evaluate(item=>item.id||item.parentElement.id);
          console.log('PART3_BROWSER_RUN', environment.mode, path.basename(file), id);
          const scheduledBefore = service.scheduled.length;
          try {
            await button.evaluate(button => {
              if (button.disabled) throw new Error('Discovered workflow is disabled');
              const disclosures=[];
              for(let parent=button.parentElement;parent;parent=parent.parentElement) {
                if(parent.tagName==='DETAILS'&&!parent.open) disclosures.push(parent);
              }
              for(const disclosure of disclosures.reverse()) disclosure.querySelector(':scope > summary').click();
            });
            await button.click();
            await owner.evaluate(item=>new Promise((resolve,reject)=>{
              const timer=setTimeout(()=>{observer.disconnect();reject(new Error('Fixture workflow did not settle'));},20000);
              const observer=new MutationObserver(()=>{
                if (['succeeded','failed','stopped'].includes(item.dataset.state)) {clearTimeout(timer);observer.disconnect();resolve();}
              });
              observer.observe(item,{attributes:true,attributeFilter:['data-state']});
              if (['succeeded','failed','stopped'].includes(item.dataset.state)) {clearTimeout(timer);observer.disconnect();resolve();}
            }));
            const state = await owner.getAttribute('data-state');
            if (state !== 'succeeded') throw new Error(await owner.innerText());
            executed.push(id);
            if (service.scheduled.length > scheduledBefore) cronWorkflows.push({file,id});
          } catch(error) { failed.push({id,error:String(error).slice(0,700)}); }
        }
        const executedHandlers = [];
        const chatPanels = page.locator('.chatui').filter({has:page.locator('.chatui-text')});
        for (let index=0; index<await chatPanels.count(); index++) {
          const panel = chatPanels.nth(index);
          if (!await panel.isVisible()) continue;
          const input = panel.locator('.chatui-text');
          await input.fill('Report which workspace tools are available.');
          await panel.locator('.chatui-send').click();
          await panel.locator('.chatui-bot').filter({hasText:'Gateway reply received.'}).waitFor();
          assert.equal(await panel.locator('.chatui-error').count(),0);
          executedHandlers.push({panel:await panel.getAttribute('id'),action:'chat input and Send'});
        }
        console.log('PART3_BROWSER_INVENTORY', JSON.stringify({environment:environment.mode,
          page:path.relative(course,file),...coverage,executed,failed,executedHandlers,
          unexecutedHandlers:coverage.controls.filter(control => control.label !== 'Send' && control.label !== 'Ask a question…')}));
        assertRuntimeSuccess(errors, await page.evaluate(runtimeFailureSnapshot));
        assert.deepEqual(failed,[]);
        assertRuntimeCoverage(await page.evaluate(runtimeFailureSnapshot), executed);
        assert.deepEqual(fixtureErrors,[]);
      }

      // Discover scheduling workflows by their observed RPCs, then rerun the same mounted UI.
      assert(cronWorkflows.length > 0,'no mounted workflow reached the external scheduler');
      for (const workflow of cronWorkflows) {
        const route = '/' + path.relative(root,workflow.file);
        const original = fs.readFileSync(workflow.file,'utf8');
        const fixedWork = original.replace(/const nonce = [^;\n]+;/,'const nonce = "fixed-work";');
        const fixedReference = original.replace(/state\.cronReference = [^;\n]+;/,'state.cronReference = "FIXED-REFERENCE";');
        assert.notEqual(fixedWork,original,'work-identity mutation did not reach the scheduled workflow');
        assert.notEqual(fixedReference,original,'reference mutation did not reach the scheduled workflow');
        for (const [name,body,noSecondWrite] of [
          ['fresh',original,false],['constant-work',fixedWork,false],['constant-reference',fixedReference,false],
          ['stale-prior-file',original,true],['stale-reused-path',fixedWork,true],
        ]) {
          service = courseServiceFixture(); fixtures.set(route,body); errors.length=0;
          await page.goto(origin+route);
          await page.evaluate(async ({runtimeUrl,origin})=>{
            const runtime=await import(runtimeUrl);
            runtime.setOpenClawConnection({rawUrl:origin,token:'fixture-token',accessProvider:'auto',accessSession:''});
          },{runtimeUrl,origin});
          const owner=page.locator('[id="'+workflow.id+'"]');
          const button=owner.locator('.cf-btn-run');
          await button.evaluate(button=>{
            for(let p=button.parentElement;p;p=p.parentElement) if(p.tagName==='DETAILS') p.open=true;
          });
          for (let iteration=0;iteration<2;iteration++) {
            service.scheduler.write=!(noSecondWrite&&iteration===1);
            await button.click();
            await owner.evaluate(item=>new Promise((resolve,reject)=>{
              const timer=setTimeout(()=>{observer.disconnect();reject(new Error('Scheduled workflow did not settle'));},10000);
              const observer=new MutationObserver(()=>{
                if(['succeeded','failed','stopped'].includes(item.dataset.state)){clearTimeout(timer);observer.disconnect();resolve();}
              });
              observer.observe(item,{attributes:true,attributeFilter:['data-state']});
              if(['succeeded','failed','stopped'].includes(item.dataset.state)){clearTimeout(timer);observer.disconnect();resolve();}
            }));
            const expected=noSecondWrite&&iteration===1?'failed':'succeeded';
            assert.equal(await owner.getAttribute('data-state'),expected,await owner.innerText());
          }
          const records=service.scheduled.map(job=>{
            const {path, content}=scheduledFile(job.payload.message);
            return {id:job.id,name:job.name,reference:content,file:path};
          });
          assert.equal(records.length,2,'both invocations must create their own scheduled work');
          const [first,second]=records;
          const freshWork=()=>{
            assert.notEqual(first.name,second.name,'scheduled name was reused');
            assert.notEqual(first.file,second.file,'scheduled file path was reused');
          };
          const freshReference=()=>assert.notEqual(first.reference,second.reference,'scheduled reference was reused');
          if(name==='constant-work'||name==='stale-reused-path') assert.throws(freshWork,/was reused/);
          else freshWork();
          if(name==='constant-reference') assert.throws(freshReference,/was reused/);
          else freshReference();
          assert.deepEqual(service.rpc('cron.list',{}).jobs,[],'both runs must remove only their owned work');
          assert.deepEqual(service.terminalReads.slice(-2),records.map(record=>record.file));
          if(noSecondWrite) {
            assert.equal(service.files.get(first.file),first.reference+'\n','prior evidence must remain present');
            assert.deepEqual(service.scheduledRuns.map(run=>({status:run.status,wrote:run.wrote})),
              [{status:'ok',wrote:true},{status:'ok',wrote:false}]);
            if(name==='stale-reused-path') assert.match(await owner.innerText(),/did not produce the expected file reference/);
          } else assertRuntimeSuccess(errors,await page.evaluate(runtimeFailureSnapshot));
          assert.deepEqual(fixtureErrors,[]);
          console.log('CRON_FRESHNESS',JSON.stringify({environment:environment.mode,scenario:name,records,
            secondWrite:!noSecondWrite,secondState:await owner.getAttribute('data-state')}));
        }
        fixtures.delete(route);
      }

      const gatewayPath='/' + path.relative(root,path.join(course,'scripts/_openclaw.js'));
      const gatewaySource=fs.readFileSync(path.join(course,'scripts/_openclaw.js'),'utf8');
      for(const entry of ['chat','connect']) for(const mutated of [false,true]) {
        const source=entry==='chat'
          ? gatewaySource.replace('const refreshed = await refreshOpenClawGatewayToken({ signal,',
              'const refreshed = await refreshOpenClawGatewayToken({')
          : gatewaySource.replace('const refreshedGateway = await helpers.refreshOpenClawGatewayToken({\n  signal: helpers.signal,',
              'const refreshedGateway = await helpers.refreshOpenClawGatewayToken({');
        assert.notEqual(source,gatewaySource,'signal mutation did not reach its bootstrap entry point');
        if(mutated) moduleOverrides.set(gatewayPath,source);
        const stopRoute='/contract-pages/pending-metadata.html';
        const code=entry==='chat'?'await helpers.openclawChat("Question", {signal:helpers.signal});':null;
        fixtures.set(stopRoute,'<!doctype html><main><div id="stop-workflow"></div></main><script type="module">'
          + `import {mountCanvasFlow,GW_CONNECT,setOpenClawConnection} from '${runtimeUrl}';`
          + 'setOpenClawConnection({rawUrl:location.origin,token:"",accessProvider:"auto",accessSession:""});'
          + `mountCanvasFlow('#stop-workflow',{nodes:[{id:'bootstrap',title:'Connect',code:${code?JSON.stringify(code):'GW_CONNECT'}}]});</script>`);
        const stoppedContext=await browser.newContext(), sockets=[];
        await stoppedContext.routeWebSocket(origin.replace('http:','ws:')+'/**',socket=>{sockets.push(socket.url());socket.close();});
        const stoppedPage=await stoppedContext.newPage();
        pendingMetadata=[];
        try {
          await stoppedPage.goto(origin+stopRoute);
          const run=stoppedPage.locator('#stop-workflow .cf-btn-run');
          await run.click();
          await until(()=>pendingMetadata.length===1);
          const pending=pendingMetadata[0];
          assert.equal(pending.closed,false,'metadata must still be pending before Stop');
          await run.click();
          const promptlyClosed=()=>until(()=>pending.closed);
          if(mutated) await assert.rejects(promptlyClosed,/fixture did not reach/);
          else await promptlyClosed();
          assert.deepEqual(sockets,[],'Stop during metadata must not open a gateway or start a turn');
          if(!mutated) await stoppedPage.waitForFunction(()=>document.querySelector('#stop-workflow')?.dataset.state==='stopped');
          console.log('METADATA_STOP',JSON.stringify({environment:environment.mode,entry,mutated,
            transportClosed:pending.closed,sockets:sockets.length}));
        } finally {
          for(const pending of pendingMetadata) pending.response.destroy();
          pendingMetadata=null; moduleOverrides.delete(gatewayPath);fixtures.delete(stopRoute);
          await stoppedContext.close();
        }
      }

      const modulePage = body => '<!doctype html><div id="exercise"></div><script type="module">' + body + '</script>';
      const disclosureRoute = '/contract-pages/nested/source-disclosure.html';
      const longCode = 'state.operation = function inspect() { return 7; };\n' + '// supporting code\n'.repeat(45);
      const courseStyles = '/' + path.relative(root, path.join(course, 'styles/_style.css'));
      const streamRoute = '/contract-pages/nested/streamed-answer.html';
      const streamCode = `state.call = async method => method === 'chat.send' ? {runId:'owned'} : {};
        window.streamFrame = event => state._chatCb?.(event);
        state.answer = await helpers.courseTurn(state, helpers, 'stream-task', 'List workspace files');`;
      fixtures.set(streamRoute, modulePage(`import {mountCanvasFlow,mountRunCell} from '${runtimeUrl}';
        mountCanvasFlow('#exercise',{nodes:[{id:'stream',title:'Workspace',code:${JSON.stringify(streamCode)}}]});
        const run=document.createElement('div');run.id='stream-run';document.body.append(run);
        mountRunCell('#stream-run',{code:${JSON.stringify(streamCode)}});`).replace('<div id="exercise">',
          `<link rel="stylesheet" href="${courseStyles}"><div id="exercise">`));
      for (const [button, output, rowSelector] of [
        ['#exercise .cf-btn-run', '#exercise .cf-panel-log', '.cf-panel-log-line'],
        ['#stream-run .rc-run', '#stream-run .rc-out', '.cell-log-line'],
      ]) {
        await page.goto(origin + streamRoute);
        await page.locator(button).click();
        await page.waitForFunction(() => typeof window.streamFrame === 'function');
        const snapshots = ['Read c', 'Read config', 'Read config.md', 'Read config.md\n\n- 中文'];
        const sendFrame = payload => page.evaluate(payload => window.streamFrame({
          event:payload.state ? 'chat' : 'agent',
          payload:{runId:'owned',sessionKey:'stream-task',...payload},
        }), payload);
        for (const text of snapshots) {
          await sendFrame({stream:'assistant',data:{text}});
          const matches = page.locator(output + ' ' + rowSelector).filter({hasText:'Read c'});
          assert.equal(await matches.count(), 1, 'stream fragments share one block');
          assert.equal(await matches.textContent(), text);
          assert.equal(await matches.evaluate(element => getComputedStyle(element).whiteSpace), 'pre-wrap');
          assert(await matches.evaluate(element => element === element.parentElement.lastElementChild),
            'updated answer follows intervening tool records');
          if (text === 'Read config') {
            await sendFrame({stream:'tool',data:{phase:'start',name:'read'}});
            await sendFrame({stream:'tool',data:{phase:'result',name:'read',isError:true,result:'Permission denied'}});
          }
        }
        const final = 'Read config.md\n\n- 中文\n- <img src=x onerror=alert(1)> literal';
        await sendFrame({state:'final',message:{content:final}});
        const answer = page.locator(output + ' ' + rowSelector).filter({hasText:'Read config.md'});
        assert.equal(await answer.count(), 1, 'completed answer is shown once');
        assert.equal(await answer.textContent(), final);
        assert.equal(await answer.getAttribute('data-log-text'), final);
        assert.equal(await answer.locator('img').count(), 0, 'model output remains literal text');
        assert(await answer.evaluate(element => element === element.parentElement.lastElementChild),
          'authoritative answer follows diagnostic events');
        assert.match(await page.locator(output).textContent(), /Permission denied/,
          'tool failures remain available alongside the answer');
      }
      fixtures.delete(streamRoute);
      fixtures.set(disclosureRoute, modulePage(`import {mountCanvasFlow,mountRunCell} from '${runtimeUrl}';
        mountCanvasFlow('#exercise',{nodes:[{id:'long',showCode:true,code:${JSON.stringify(longCode)}}]});
        const run=document.createElement('div');run.id='long-run';document.body.append(run);
        mountRunCell('#long-run',{openCode:true,code:${JSON.stringify(longCode)}});`).replace('<div id="exercise">',
          `<link rel="stylesheet" href="${courseStyles}"><div id="exercise">`));
      await page.goto(origin + disclosureRoute);
      await page.locator('#long-run .rc-run').waitFor();
      assert.equal(await page.locator('.cf-panel-code-det[open],.rc-code-det[open]').count(), 0,
        'long source stays closed even when older lesson options request expansion');
      await page.locator('#exercise .cf-btn-run').click();
      await page.waitForFunction(() => document.querySelector('#exercise .cf-node')?.classList.contains('complete'));
      assert.match(await page.locator('.cf-panel-overview').textContent(), /\[Function: inspect\]/);
      assert.doesNotMatch(await page.locator('.cf-panel-overview').textContent(), /return 7/,
        'state summaries must not re-expose the function body');
      await page.locator('.cf-panel-code-det > summary').click();
      assert.equal(await page.locator('.cf-panel-code-det').evaluate(e=>e.open), true);
      assert.equal(await page.locator('.cf-panel-code').inputValue(), longCode);
      await page.locator('#exercise .cf-panel-reset').click();
      assert.equal(await page.locator('.cf-panel-code').inputValue(), longCode);
      fixtures.delete(disclosureRoute);
      const chatLayoutRoute = '/contract-pages/nested/translated-chat-layout.html';
      fixtures.set(chatLayoutRoute, modulePage(`import {mountChatUI} from '${runtimeUrl}';
        window.layoutChat=mountChatUI('#exercise',{memory:true,resetLabel:'Nueva conversación',models:[
          {id:'first',label:'Modelo para comparar respuestas y revisar el contexto disponible'},
          {id:'second',label:'Modelo alternativo para outra comparação de respostas'}],
          respond:async(text,ctx)=>{ctx.view.token('Response');ctx.view.usage({context:120000,window:128000});}});
        document.querySelector('.chatui-mem').textContent='Memoria: activada';
        document.querySelector('.chatui-options>summary').textContent='Opciones del modelo y del contexto disponible';`).replace('<div id="exercise">',
          `<link rel="stylesheet" href="${courseStyles}"><div id="exercise">`));
      const originalViewport = page.viewportSize();
      for (const width of [320,390]) {
        await page.setViewportSize({width,height:900});
        await page.goto(origin + chatLayoutRoute);
        await page.locator('.chatui-options>summary').waitFor();
        const contextMeter = page.locator('[data-ctx]');
        assert.equal(await contextMeter.isVisible(),false,'unused context must respect hidden');
        await page.locator('.chatui-options>summary').focus();
        await page.keyboard.press('Enter');
        await page.locator('.chatui-model').focus();
        await page.keyboard.press('Home');
        await page.keyboard.press('ArrowDown');
        await page.keyboard.press('Tab');
        assert.equal(await page.locator('.chatui-model').inputValue(),'second');
        await page.locator('.chatui-text').fill('Inspect usage');
        await page.locator('.chatui-send').click();
        await contextMeter.waitFor({state:'visible'});
        assert.equal(await page.locator('.chatui-ctxbar').isVisible(),true);
        assert.deepEqual(await page.evaluate(()=>{
          const box=document.querySelector('.chatui').getBoundingClientRect();
          return Array.from(document.querySelectorAll('.chatui-options,.chatui-model,[data-ctx],.chatui-ctxbar'))
            .filter(element=>{const r=element.getBoundingClientRect();return r.left<box.left-1||r.right>box.right+1;})
            .map(element=>element.className);
        }),[],'translated controls and populated context stay inside the widget');
        await page.evaluate(()=>window.layoutChat.reset());
        assert.equal(await contextMeter.isVisible(),false,'reset hides the context meter again');
      }
      await page.setViewportSize(originalViewport);
      fixtures.delete(chatLayoutRoute);
      const mutations = [
        ['missing-export', `import { nonexistentExport } from '${runtimeUrl}';`],
        ['missing-import', "import '/contract-pages/deleted-module.js';"],
        ['node-only-import', "await import('node:fs');"],
        ['missing-package', "await import('missing-browser-package');"],
        ['undefined-reference', 'missingRuntimeBinding();'],
        ['noncallable-operation', `import {mountRunCell} from '${runtimeUrl}'; mountRunCell('#exercise',{code:'const operation = {}; operation.run();'});`],
        ['success', `import {mountRunCell} from '${runtimeUrl}'; mountRunCell('#exercise',{code:'return {observed:7};'});`],
      ];
      for (const [name, body] of mutations) {
        const route = '/contract-pages/nested/' + name + '.html';
        fixtures.set(route, modulePage(body)); errors.length = 0;
        await page.goto(origin + route);
        if (['noncallable-operation','success'].includes(name)) {
          await page.locator('#exercise .rc-run').click();
          await page.waitForFunction(() => ['succeeded','failed'].includes(document.querySelector('#exercise')?.dataset.state));
        }
        const snapshot = await page.evaluate(runtimeFailureSnapshot);
        if (name === 'success') assertRuntimeSuccess(errors, snapshot);
        else assert.throws(() => assertRuntimeSuccess(errors, snapshot), /pageErrors|failedCells/, name);
      }
      for (const removeButton of [false,true]) {
        const route = '/contract-pages/coverage.html';
        fixtures.set(route,modulePage(`import {mountRunCell} from '${runtimeUrl}'; mountRunCell('#exercise',{code:'return 1;'});`));
        await page.goto(origin + route);
        await page.locator('#exercise .rc-run').waitFor();
        if (removeButton) await page.locator('#exercise .rc-run').evaluate(button=>button.remove());
        const pageSnapshot = await page.evaluate(runtimeFailureSnapshot);
        assert.throws(() => assertRuntimeCoverage(pageSnapshot,[]), /unexecuted/);
      }
      const delayedRoute = '/contract-pages/delayed-document.html';
      fixtures.set(delayedRoute, '<!doctype html><main><h1>Delayed exercise</h1><div id="exercise"></div></main>'
        + `<script type="module">import {mountRunCell} from '${runtimeUrl}'; setTimeout(()=>mountRunCell('#exercise',{code:'return 7;'}),100);</script>`);
      const harness = await new Promise((resolve,reject) => {
        const child = spawn(process.execPath,[path.join(root,'scripts/runtime/test_page_runtime.js'),
          '--course-document',origin + delayedRoute],{cwd:root,env:process.env});
        let output='';
        child.stdout.on('data',chunk=>{output+=chunk;});
        child.stderr.on('data',chunk=>{output+=chunk;});
        const deadline=setTimeout(()=>{child.kill();reject(new Error('Delayed-document browser harness did not finish'));},15000);
        child.on('error',error=>{clearTimeout(deadline);reject(error);});
        child.on('close',code=>{clearTimeout(deadline);resolve({code,output});});
      });
      assert.equal(harness.code,0,harness.output);
      assert.match(harness.output,/RUNTIME_COVERAGE:/,'late document mounts must execute rather than pass as static render');
      assert.match(harness.output,/"id":"exercise","state":"succeeded"/);
      await context.close();
    }
    const turns = requests.filter(request => request.method === 'chat.send');
    assert(turns.length > 0,'actual displayed workflows must reach the gateway');
    const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
    requests.forEach(request => assert.equal(typeof request.id,'string'));
    assert.equal(new Set(requests.map(request=>request.id)).size,requests.length);
    turns.forEach(request => assert.match(request.params.idempotencyKey, uuid));
    const reviewTurns=turns.filter(request=>request.params.sessionKey.startsWith('quick-3b-general-')||request.params.sessionKey.startsWith('quick-3b-review-'));
    assert.equal(new Set(reviewTurns.map(request=>request.params.sessionKey)).size,4);
  } finally {
    await browser?.close(); server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
  }
});

test('browser page discovery follows new, renamed, deleted and malformed declarations', () => {
  const {discoverCoursePages, localCourseOrigins} = createRequire(import.meta.url)(path.join(root, 'scripts/runtime/browser_environment.cjs'));
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'browser-discovery-'));
  try {
    const file = path.join(temporary, 'nested/novel.html'); fs.mkdirSync(path.dirname(file));
    fs.writeFileSync(file, '<script>mountRunCell("#x", {code:"return 1"});</script>');
    assert.deepEqual(discoverCoursePages(temporary), [file]);
    fs.writeFileSync(file, '<script type="module">import {mountRunCell as mount} from "./runtime.js"; mount /* comment */ ("#x", {code:"return 1"});</script>');
    assert.deepEqual(discoverCoursePages(temporary), [file]);
    fs.writeFileSync(file, '<script type="module">const missing = {}; missing.operation();</script>');
    assert.deepEqual(discoverCoursePages(temporary), [file]);
    const renamed = path.join(path.dirname(file), 'renamed.htm'); fs.renameSync(file,renamed);
    assert.deepEqual(discoverCoursePages(temporary), [renamed]);
    fs.unlinkSync(renamed); assert.deepEqual(discoverCoursePages(temporary), []);
    fs.writeFileSync(path.join(temporary,'lesson-map.json'), JSON.stringify({lessons:[{id:'nested/renamed'}]}));
    assert.throws(() => discoverCoursePages(temporary), /missing/);
    fs.writeFileSync(path.join(temporary,'lesson-map.json'), '{broken');
    assert.throws(() => discoverCoursePages(temporary), SyntaxError);
    fs.writeFileSync(path.join(temporary,'lesson-map.json'), JSON.stringify({lessons:null}));
    assert.throws(() => discoverCoursePages(temporary), /lessons array/);
    fs.writeFileSync(path.join(temporary,'lesson-map.json'), JSON.stringify({lessons:[{id:null}]}));
    assert.throws(() => discoverCoursePages(temporary), /invalid lesson ID/);
    assert.throws(() => localCourseOrigins(4173,{}), /non-loopback/);
  } finally { fs.rmSync(temporary,{recursive:true,force:true}); }
});

const previousDocument = globalThis.document;

function element() {
  return { style: {}, addEventListener() {}, appendChild() {} };
}

async function mount(runtime, options = {}, language = 'en') {
  globalThis.document = { createElement: element, documentElement: {lang: language} };
  const { mountOpenClawCliRuntime } = await import(pathToFileURL(path.join(course, 'scripts/_openclaw_cli.js')));
  return mountOpenClawCliRuntime({ querySelector: () => null }, runtime, options);
}

test('OpenClaw CLI refreshes gateway metadata before deciding it is disabled', async () => {
  const connection = { rawUrl: 'https://runtime.example.test', token: '' };
  let refreshes = 0, options;
  try {
    const cli = await mount({
      getOpenClawConnection: () => connection,
      refreshOpenClawGatewayToken: async ({ signal }) => { refreshes += 1; assert.equal(signal, null); connection.token = 'fixture-token'; },
      mountConsole: (_target, value) => { options = value; return { write() {} }; },
      openclawGatewayWsUrl: () => { throw new Error('No external RPC in the metadata fixture'); },
      openclawChat: async () => '',
    });
    assert.equal(refreshes, 1);
    assert.equal(options.disabled, false);
    assert.equal(cli.connected, true);
    assert.equal(cli.reason, '');
  } finally {
    globalThis.document = previousDocument;
  }
});

test('OpenClaw CLI exposes failed metadata bootstrap without declaring a connection', async () => {
  const connection = { rawUrl: 'https://runtime.example.test', token: '' };
  let options;
  try {
    const cli = await mount({
      getOpenClawConnection: () => connection,
      refreshOpenClawGatewayToken: async () => { throw new Error('metadata unavailable'); },
      mountConsole: (_target, value) => { options = value; return { write() {} }; },
      openclawGatewayWsUrl: () => { throw new Error('No external RPC in the metadata fixture'); },
      openclawChat: async () => '',
    });
    assert.equal(options.disabled, true);
    assert.equal(options.disabledMsg, 'metadata unavailable');
    assert.equal(cli.connected, false);
    assert.equal(cli.reason, 'metadata unavailable');
  } finally {
    globalThis.document = previousDocument;
  }
});

test('OpenClaw CLI does not mount after its owning cell stops during metadata bootstrap', async () => {
  const connection = { rawUrl: 'https://runtime.example.test', token: '' };
  const controller = new AbortController();
  let mounted = false;
  try {
    await assert.rejects(mount({
      getOpenClawConnection: () => connection,
      refreshOpenClawGatewayToken: async ({ signal }) => { controller.abort(); signal.throwIfAborted(); },
      mountConsole: () => { mounted = true; },
      openclawGatewayWsUrl: () => { throw new Error('No external RPC in the metadata fixture'); },
      openclawChat: async () => '',
    }, { signal: controller.signal }), /stopped|aborted|AbortError/);
    assert.equal(mounted, false);
  } finally {
    globalThis.document = previousDocument;
  }
});

test('OpenClaw CLI localizes submitted suggestions for every declared locale and preserves commands', async () => {
  const locales = fs.readdirSync(path.join(root, 'i18n'), {withFileTypes:true})
    .filter(entry => entry.isDirectory())
    .map(entry => JSON.parse(fs.readFileSync(path.join(root, 'i18n', entry.name, 'locale.json'), 'utf8')).locale);
  const suggestions = async language => {
    let options;
    await mount({
      getOpenClawConnection: () => ({rawUrl:'https://runtime.example.test', token:'fixture-token'}),
      refreshOpenClawGatewayToken: async () => {},
      mountConsole: (_target, value) => { options = value; return {write() {}}; },
      openclawGatewayWsUrl: () => { throw new Error('No external RPC in the locale fixture'); },
      openclawChat: async () => '',
    }, {}, language);
    return options.suggestions;
  };
  try {
    const english = await suggestions('en');
    for (const locale of locales) {
      assert.equal(typeof locale, 'string');
      const localized = await suggestions(locale);
      assert.equal(localized.length, english.length);
      english.forEach((value, index) => {
        if (typeof value === 'object') assert.deepEqual(localized[index], value);
        else assert.notEqual(localized[index], value, `${locale}: untranslated CLI suggestion`);
      });
      assert(localized.some(value => typeof value === 'string' && value.includes('SOUL.md')));
      assert(localized.some(value => typeof value === 'string' && value.includes('ls -la /sandbox/.openclaw/workspace')));
    }
  } finally { globalThis.document = previousDocument; }
});
