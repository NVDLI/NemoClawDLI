// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const COURSE_ROOTS = fs.readdirSync('web', {withFileTypes:true})
  .filter(entry => entry.isDirectory() && fs.existsSync(path.join('web', entry.name, 'COURSE_CANON.md')))
  .map(entry => path.join('web', entry.name));
assert.ok(COURSE_ROOTS.length, 'expected courses with milestone contracts');
import * as sdkModule from '../../web/activity/activity-sdk.js';
const contract = () => ({schemaVersion:1,milestones:[{id:'fixture:done',label:'Complete exercise',description:'Run the exercise successfully.',href:'lesson.html#exercise',evidence:[{event:'fixture:success',page:'lesson.html',target:'exercise',matches:{success:true},minimum:{count:1}}]}]});
const session={session_id:'019f38f1-e5ab-7688-af0d-0e8925299e93',session_token:'fixture-token-long-enough',expires_at:'2099-01-01T00:00:00Z'};
const artifact={artifact_id:'fixture-course',artifact_version:'v1',artifact_digest:'sha256:'+'a'.repeat(64)};
test('initialize loads the course JSON once and sends only published artifact fields',async()=>{
 const requests=[];const fetchImpl=async(url,options)=>{
  requests.push({url,options});
  if(!String(url).endsWith('.json') && JSON.stringify(Object.keys(JSON.parse(options.body)).sort())!==JSON.stringify(Object.keys(artifact).sort()))return new Response('{}',{status:422});
  return new Response(JSON.stringify(String(url).endsWith('.json')?contract():session),{status:201});
 };
 const milestoneConfigUrl='https://course.example.test/initialize/activity_milestones.json';
 const config=await sdkModule.loadActivityMilestoneConfig(milestoneConfigUrl,{fetchImpl});
 assert.ok(Object.isFrozen(config.milestones[0].evidence[0].matches));
 await sdkModule.DLIActivity.initialize({baseUrl:'https://activity.example.test',artifact,milestoneConfigUrl,fetchImpl});
 assert.equal(requests.filter(r=>String(r.url).endsWith('.json')).length,1);
 assert.deepEqual(JSON.parse(requests.at(-1).options.body),artifact);
});
test('generic config rejects unsafe shape, URLs, event targets and incomplete success evidence',()=>{
 for(const mutate of [c=>c.milestones[0].label='bad\u0000text',c=>c.milestones[0].description='bad\u0000text',c=>c.milestones[0].evidence[0].matches=null,c=>c.milestones[0].evidence[0].minimum=null,c=>c.milestones[0].evidence[0].requires=null,c=>c.schemaVersion=2,c=>c.extra=true,c=>c.milestones=[],c=>c.milestones.push(c.milestones[0]),c=>c.milestones[0].href='https://private.example.test/key',c=>c.milestones[0].href='../lesson.html#exercise',c=>c.milestones[0].evidence=[],c=>c.milestones[0].evidence[0].event='click',c=>c.milestones[0].evidence[0].target='#exercise',c=>c.milestones[0].evidence[0].page='../lesson.html',c=>c.milestones[0].evidence[0].minimum.count=-1,c=>c.milestones[0].evidence[0].requires=[0],c=>c.milestones[0].evidence[0].unknown=true]) {
  const config=contract();mutate(config);assert.throws(()=>sdkModule.validateActivityMilestoneConfig(config),error=>error.code==='invalid_configuration');
 }
});
test('declarative instrumenter uses page targets and success predicates without click/view awards',async()=>{
 const eventTarget=new EventTarget();const reached=[];const documentTarget={getElementById:id=>id==='exercise'?{}:null};
 const config=sdkModule.validateActivityMilestoneConfig(contract());
 const binding=sdkModule.bindActivityMilestones({config,eventTarget,documentTarget,page:'lesson.html',sessionId:'a',onMilestone:id=>reached.push(id)});
 const emit=detail=>{const event=new Event('fixture:success');event.detail=detail;eventTarget.dispatchEvent(event);};
 emit({success:false,count:1});emit({success:true,count:0});eventTarget.dispatchEvent(new Event('click'));assert.deepEqual(reached,[]);
 emit({success:true,count:1});assert.deepEqual(reached,['fixture:done']);binding.dispose();emit({success:true,count:1});assert.equal(reached.length,1);
 const other=sdkModule.bindActivityMilestones({config,eventTarget,documentTarget,page:'other.html',sessionId:'a',onMilestone:id=>reached.push(id)});emit({success:true,count:1});assert.equal(reached.length,1);other.dispose();
});
test('declarative ordered evidence and session replacement preserve live-only pairing',()=>{
 const source=contract();source.milestones[0].evidence=[{event:'fixture:key',page:'lesson.html',target:'exercise'},{event:'fixture:success',page:'lesson.html',target:'exercise',matches:{success:true},requires:[0]}];
 const eventTarget=new EventTarget();const reached=[];const binding=sdkModule.bindActivityMilestones({config:sdkModule.validateActivityMilestoneConfig(source),eventTarget,documentTarget:{getElementById:()=>({})},page:'lesson.html',sessionId:null,onMilestone:id=>reached.push(id)});
 const emit=name=>{const event=new Event(name);event.detail={success:true};eventTarget.dispatchEvent(event);};
 emit('fixture:success');emit('fixture:key');assert.deepEqual(reached,[]);binding.bindSession({sessionId:'a'});emit('fixture:success');assert.equal(reached.length,1);
 binding.bindSession({sessionId:'b'});emit('fixture:success');assert.equal(reached.length,1);emit('fixture:key');emit('fixture:success');assert.equal(reached.length,2);binding.dispose();
});
test('canonical Markdown owns the generated Activity JSON definition',()=>{
 for(const root of COURSE_ROOTS){const config=JSON.parse(fs.readFileSync(path.join('web/activity','activity_milestones.json'),'utf8'));assert.ok(config.milestones.length>0);const doc=fs.readFileSync(path.join('docs','ACTIVITY_MILESTONES.md'),'utf8');assert.match(doc,/^# Activity Milestones\n/);const blocks=[...doc.matchAll(/^```json[ \t]*\n([\s\S]*?)^```[ \t]*$/gm)];assert.equal(blocks.length,1);assert.deepEqual(config,JSON.parse(blocks[0][1]));assert.equal(fs.existsSync(path.join(root,'scripts/_activity_config.js')),false);}
});

test('course module remains importable when its JSON config is unavailable',async()=>{
 const {execFileSync}=await import('node:child_process');
 for(const root of COURSE_ROOTS) execFileSync(process.execPath,['--input-type=module','-e',"globalThis.fetch=async()=>new Response('{}',{status:503}); const m=await import(process.argv[1]); if(m.ACTIVITY_CONFIG!==null || Object.keys(m.ACTIVITY_MILESTONES).length) process.exit(1);",pathToFileURL(path.resolve('web/activity','_activity.js')).href],{cwd:process.cwd()});
});

test('invalid fetched JSON stops initialization before any Activity request and can be retried',async()=>{
 let reads=0;let sessions=0;const url='https://course.example.test/retry/activity_milestones.json';
 const fetchImpl=async(url)=>{if(String(url).endsWith('.json'))return new Response(JSON.stringify(++reads===1?{...contract(),extra:'https://private.example.test'}:contract()));sessions++;return new Response(JSON.stringify(session),{status:201});};
 await assert.rejects(sdkModule.DLIActivity.initialize({baseUrl:'https://activity.example.test',artifact,milestoneConfigUrl:url,fetchImpl}),error=>error.code==='invalid_configuration');assert.equal(sessions,0);
 await sdkModule.DLIActivity.initialize({baseUrl:'https://activity.example.test',artifact,milestoneConfigUrl:url,fetchImpl});assert.equal(reads,2);assert.equal(sessions,1);
});
test('loader rejects credential and cross-origin config URLs before fetching',()=>{
 const original=Object.getOwnPropertyDescriptor(globalThis,'location');Object.defineProperty(globalThis,'location',{configurable:true,value:{href:'https://course.example.test/lesson.html',origin:'https://course.example.test'}});
 try {for(const url of ['https://secret@course.example.test/activity_milestones.json','https://other.example.test/activity_milestones.json','javascript:bad','https://course.example.test/activity_milestones.json?secret=1'])assert.throws(()=>sdkModule.loadActivityMilestoneConfig(url,{fetchImpl:()=>assert.fail('unsafe URL must not fetch')}),error=>error.code==='invalid_configuration');}
 finally {if(original)Object.defineProperty(globalThis,'location',original);else delete globalThis.location;}
});
test('loader deadline bounds stalled JSON body reads',async()=>{
 const originalSetTimeout=globalThis.setTimeout,originalClearTimeout=globalThis.clearTimeout;let expire;let signal;
 globalThis.setTimeout=callback=>{expire=callback;return 1;};globalThis.clearTimeout=()=>{};
 try {const pending=sdkModule.loadActivityMilestoneConfig('https://course.example.test/stalled/activity_milestones.json',{fetchImpl:async(url,options)=>{signal=options.signal;return{ok:true,text:()=>new Promise(()=>{})};}}).then(()=>assert.fail('stalled body must time out'),error=>error);
 await Promise.resolve();await Promise.resolve();expire();assert.equal((await pending).code,'invalid_configuration');assert.equal(signal.aborted,true);
 }finally {globalThis.setTimeout=originalSetTimeout;globalThis.clearTimeout=originalClearTimeout;}
});
test('config snapshots reject sparse matcher arrays and never bind missing DOM targets',()=>{
 const config=contract();config.milestones[0].evidence[0].matches.success=new Array(1);
 assert.throws(()=>sdkModule.validateActivityMilestoneConfig(config),error=>error.code==='invalid_configuration');
 const eventTarget=new EventTarget();const reached=[];const binding=sdkModule.bindActivityMilestones({config:contract(),eventTarget,documentTarget:{getElementById:()=>null},page:'lesson.html',onMilestone:id=>reached.push(id)});
 const event=new Event('fixture:success');event.detail={success:true,count:1};eventTarget.dispatchEvent(event);assert.deepEqual(reached,[]);binding.dispose();
 const source=contract();const copied=sdkModule.validateActivityMilestoneConfig(source);source.milestones[0].evidence[0].matches.success=false;assert.equal(copied.milestones[0].evidence[0].matches.success,true);
});

test('held optional config does not hold shared helper exports or trigger Activity requests',async()=>{
 const {execFileSync}=await import('node:child_process');
 for(const root of COURSE_ROOTS) execFileSync(process.execPath,['--input-type=module','-e',`Object.defineProperty(globalThis,'localStorage',{value:{getItem:()=>null,setItem:()=>{},removeItem:()=>{}},configurable:true});let release;let startedResolve;const started=new Promise(resolve=>startedResolve=resolve);let apiRequests=0;globalThis.fetch=async url=>{if(String(url).endsWith('activity_milestones.json')){startedResolve();return new Promise(resolve=>release=resolve);}if(String(url).includes('/v1/activity-sessions'))apiRequests++;return new Response('{}',{status:503});};let ready=false;const shared=import(process.argv[1]).then(module=>{if(typeof module.buildNav!=='function' || typeof module.getModelId!=='function')throw Error('missing unrelated helpers');ready=true;});await started;await new Promise(resolve=>setTimeout(resolve,50));if(!ready || apiRequests)throw Error('optional config held unrelated course bootstrap');release(new Response('{}',{status:503}));await shared;`,pathToFileURL(path.resolve(root,'scripts/_shared.js')).href],{cwd:process.cwd()});
});

test('real course navigation renders with JSON held and makes no Activity API requests', {timeout:60000}, async()=>{
 const {createRequire}=await import('node:module');const path=await import('node:path');const http=await import('node:http');const {execFileSync}=await import('node:child_process');
 const require=createRequire(path.resolve('scripts/runtime/package.json'));const {chromium}=require('playwright-core');
 const server=http.createServer((request,response)=>{const pathname=new URL(request.url,'http://localhost').pathname;const file=path.resolve('.'+pathname);if(!file.startsWith(process.cwd()+path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile())return response.writeHead(404).end();response.setHeader('Content-Type',file.endsWith('.js')?'text/javascript':file.endsWith('.html')?'text/html':file.endsWith('.css')?'text/css':'application/octet-stream');response.end(fs.readFileSync(file));});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const executablePath=process.platform==='darwin'?'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome':execFileSync('python3',['scripts/runtime/host_browser.py'],{encoding:'utf8'}).trim();
 const browser=await chromium.launch({headless:true,executablePath,args:['--no-sandbox']});let apiRequests=0;const held=[];
 try {const context=await browser.newContext();await context.route('**/*',route=>{const url=new URL(route.request().url());if(url.hostname==='activity-api.learn.nvidia.com'){apiRequests++;return route.abort();}if(url.pathname.endsWith('/activity_milestones.json')){held.push(route);return;}if(url.hostname!=='127.0.0.1')return route.abort();return route.continue();});
 const port=server.address().port;
 for(const root of COURSE_ROOTS){const config=JSON.parse(fs.readFileSync(path.join('web/activity','activity_milestones.json'),'utf8'));const firstLesson=config.milestones[0].href.split('#')[0];const completionPages=fs.readdirSync(root).filter(file=>file.endsWith('.html') && fs.readFileSync(path.join(root,file),'utf8').includes('id="finish-course"'));for(const lesson of new Set([firstLesson,...completionPages])){const page=await context.newPage();const configRequested=page.waitForRequest(request=>request.url().endsWith('/activity_milestones.json'));await page.goto(`http://127.0.0.1:${port}/${root}/${lesson}`,{waitUntil:'commit'});await configRequested;await page.waitForFunction(()=>document.querySelector('#nav')?.children.length>0);assert.equal(await page.evaluate(async()=>typeof(await import('./scripts/_shared.js')).getModelId),'function');assert.equal(apiRequests,0);assert.ok(held.length>0);await page.close();}}
 }finally{await Promise.all(held.map(route=>route.abort().catch(()=>{})));await browser.close();await new Promise(resolve=>server.close(resolve));}
});

test('Activity browser runtime is isolated from the course directory',()=>{
 for(const file of ['activity-sdk.js','_activity.js','_activity_runtime.js','activity-policy.json','activity_milestones.json']) assert.ok(fs.existsSync('web/activity/'+file),file);
 const adapter=fs.readFileSync('web/activity/_activity.js','utf8');
 assert.match(adapter,/new URL\('\.\/activity_milestones\.json', import\.meta\.url\)/);
 assert.match(adapter,/new URL\('\.\/activity-policy\.json', import\.meta\.url\)/);
 assert.match(fs.readFileSync('web/activity/_activity_runtime.js','utf8'),/from '\.\.\/nemoclaw\/scripts\/_locale\.js'/);
 assert.match(fs.readFileSync('web/nemoclaw/scripts/_shared.js','utf8'),/import\("\.\.\/\.\.\/activity\/_activity_runtime\.js"\)/);
});
