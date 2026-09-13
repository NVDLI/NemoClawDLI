// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const {discoverCourses} = createRequire(import.meta.url)('./course_exercise_fixture.cjs');
const course = discoverCourses(root).roots[0];
const profile = JSON.parse(fs.readFileSync(path.join(course,'learning-profile.json'),'utf8'));
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
      response.writeHead(200,{'content-type':{'.html':'text/html','.js':'text/javascript','.json':'application/json','.css':'text/css','.svg':'image/svg+xml','.txt':'text/plain'}[path.extname(file)]||'application/octet-stream'}).end(body);
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
      await page.waitForFunction(() => document.documentElement.dataset.learningProfile === 'guided');
      assert((await page.locator('.hero .eyebrow').textContent()).startsWith(label),
        `${language}: the shared learning profile replaced the translated module label`);
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
    const load = async () => {
      await page.goto(origin+lessonRoute(4, 2));
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
      document.body.append(panel);panel.scrollTop=panel.scrollHeight;window.scrollTo({top:500,behavior:'instant'});
    });
    await page.locator('#wheel-contract').hover();
    await page.waitForTimeout(100);
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
    await page.locator('#wheel-contract').evaluate(node=>node.remove());

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
      document.body.appendChild(element);
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
      shared.mountOpenClawCli(element);
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
