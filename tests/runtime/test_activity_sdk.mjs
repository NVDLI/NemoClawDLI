// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import test from 'node:test';
import { DLIActivity, DLIActivityError, ActivitySdkError, createActivityClient, createMemoryActivityStorage, createBrowserActivityStorage } from '../../web/shared/activity-sdk.js';

const sessionId='019f38f1-e5ab-7688-af0d-0e8925299e93';
const artifact={artifact_id:'fixture-course',artifact_version:'v1',artifact_digest:'sha256:'+ 'a'.repeat(64)};
const stamp='2026-10-14T12:00:00Z';
function fixture({markers=['early','later'],completed=[],legacy=false}={}) {
 const writes=[];let finished=false;const reached=new Set(completed);
 const remote=()=>({session_id:sessionId,completed_at:finished?stamp:null,...(legacy?{progress_percent:100}:{milestones:markers.map(milestone_id=>({milestone_id,completed_at:reached.has(milestone_id)?stamp:null}))})});
 const fetchImpl=async(url,options)=>{
  if(url.endsWith('/activity-sessions'))return new Response(JSON.stringify({session_id:sessionId,session_token:'fixture-token-long-enough',expires_at:'2099-01-01T00:00:00Z'}),{status:201});
  if(url.endsWith('/state'))return new Response(JSON.stringify(remote()));
  const body=JSON.parse(options.body);writes.push({body,options});
  if(body.type==='milestone_completed')reached.add(body.payload.milestone_id);
  if(body.type==='completed')finished=true;
  return new Response('{}',{status:201});
 };
 return {writes,options:{baseUrl:'https://activity.example.test',artifact,storage:createMemoryActivityStorage(),fetchImpl}};
}
test('milestones complete independently with confirmation and idempotency',async()=>{
 const f=fixture();const sdk=await DLIActivity.initialize(f.options);
 const result=await sdk.completeMilestone('later',{idempotencyKey:'fixture-later'});
 assert.equal(result.written,true);
 assert.deepEqual(result.state.milestones,[{milestoneId:'early',completedAt:null},{milestoneId:'later',completedAt:stamp}]);
 assert.deepEqual(f.writes[0].body,{type:'milestone_completed',payload:{milestone_id:'later'}});
 assert.equal(f.writes[0].options.headers['Idempotency-Key'],'fixture-later');
 assert.equal(f.writes[0].options.credentials,'omit');assert.equal(f.writes[0].options.redirect,'error');
 assert.equal((await sdk.completeMilestone('later')).written,false);assert.equal(f.writes.length,1);
});
test('completion requires every registered milestone and confirmation',async()=>{
 const f=fixture();const sdk=await DLIActivity.initialize(f.options);
 assert.equal((await sdk.complete()).written,false);
 await sdk.completeMilestone('later');assert.equal((await sdk.complete()).written,false);
 await sdk.completeMilestone('early');assert.equal((await sdk.complete()).state.completedAt,stamp);
 assert.equal((await sdk.complete()).written,false);
});
test('empty or legacy state cannot authorize completion',async()=>{
 for(const options of [{markers:[]},{legacy:true}]){
  const f=fixture(options);const sdk=await DLIActivity.initialize(f.options);
  let result;
  try{result=await sdk.complete();}catch(error){assert.ok(error instanceof DLIActivityError);}
  if(result)assert.equal(result.written,false);
  assert.deepEqual(f.writes,[]);
 }
});
test('invalid or unregistered milestone IDs never write',async()=>{
 const f=fixture();const sdk=await DLIActivity.initialize(f.options);
 for(const id of ['', 'contains space','unknown'])await assert.rejects(sdk.completeMilestone(id),error=>error.code==='invalid_milestone');
 assert.deepEqual(f.writes,[]);
});

test('plain client rejects unsafe endpoints before any request',()=>{
 for(const baseUrl of ['http://activity.example.test','https://secret@activity.example.test','https://activity.example.test?q=secret'])assert.throws(()=>createActivityClient({baseUrl,artifact}),ActivitySdkError);
});
test('browser storage remains tab scoped and tolerates disabled storage',()=>{
 const values=new Map();const storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 const first=createBrowserActivityStorage({storage,key:'course-a'});first.save({session_id:sessionId});
 assert.deepEqual(createBrowserActivityStorage({storage,key:'course-a'}).load(),{session_id:sessionId});
 assert.equal(createBrowserActivityStorage({storage,key:'course-b'}).load(),null);first.clear();assert.equal(first.load(),null);
 const blocked=createBrowserActivityStorage({storage:{getItem(){throw Error('disabled');}},key:'course'});blocked.save({session_id:sessionId});assert.deepEqual(blocked.load(),{session_id:sessionId});
});
test('sessions are reused only for the same endpoint and artifact identity',async()=>{
 const storage=createMemoryActivityStorage();const f=fixture();let requests=0;const fetchImpl=async(...args)=>{requests++;return f.options.fetchImpl(...args);};
 const options={...f.options,storage,fetchImpl};await createActivityClient(options).ensureSession();
 await createActivityClient(options).ensureSession();assert.equal(requests,1);
 await createActivityClient({...options,artifact:{...artifact,artifact_version:'v2'}}).ensureSession();assert.equal(requests,2);
 await createActivityClient({...options,baseUrl:'https://other.example.test'}).ensureSession();assert.equal(requests,3);
});
test('diagnostics and normalized state exclude authentication material',async()=>{
 const f=fixture();const baseFetch=f.options.fetchImpl;const sdk=await DLIActivity.initialize({...f.options,fetchImpl:async(url,init)=>{
  if(url.endsWith('/state'))return new Response(JSON.stringify({session_id:sessionId,completed_at:null,milestones:[],session_token:'sensitive',authorization:'sensitive',nested:{token:'sensitive'}}));
  return baseFetch(url,init);
 }});assert.equal(JSON.stringify(await sdk.getState()).includes('sensitive'),false);
 const events=[];const client=createActivityClient({...f.options,onDiagnostic:e=>events.push(e),fetchImpl:async(url,init)=>url.endsWith('/activity-sessions')?baseFetch(url,init):new Response('{"detail":"sensitive"}',{status:403})});
 await assert.rejects(client.recordReferral({referenceId:'fixture',destinationUrl:'https://example.test',idempotencyKey:'fixture'}),ActivitySdkError);
 assert.equal(JSON.stringify(events).includes('sensitive'),false);
});

test('request deadline also bounds a stalled response body',async()=>{
 const originalSetTimeout=globalThis.setTimeout,originalClearTimeout=globalThis.clearTimeout;
 let expire;let cleared=false;globalThis.setTimeout=callback=>{expire=callback;return 1;};globalThis.clearTimeout=()=>{cleared=true;};
 try{
  const client=createActivityClient({baseUrl:'https://activity.example.test',artifact,fetchImpl:async()=>({ok:true,status:201,json:()=>new Promise(()=>{})})});
  const result=client.ensureSession().then(()=>({passed:true}),error=>({error}));
  await Promise.resolve();await Promise.resolve();
  assert.equal(cleared,false,'the request deadline must remain active while parsing the body');
  expire();const outcome=await result;assert.ok(outcome.error instanceof ActivitySdkError);assert.equal(outcome.error.category,'timeout');
 }finally{globalThis.setTimeout=originalSetTimeout;globalThis.clearTimeout=originalClearTimeout;}
});

test('authentication recovery never forwards a different client scope token',async()=>{
 const storage=createMemoryActivityStorage();const f=fixture();let releaseA;let announceA;
 const waiting=new Promise(resolve=>{announceA=resolve;});const aAuth=[];let aSessions=0;
 const optsA={...f.options,storage,fetchImpl:async(url,options)=>{
  if(url.endsWith('/activity-sessions')){aSessions++;return new Response(JSON.stringify({session_id:sessionId,session_token:'token-a-long-enough',expires_at:'2099-01-01T00:00:00Z'}),{status:201});}
  aAuth.push(options.headers.Authorization);
  if(aAuth.length===1){announceA();return new Promise(resolve=>{releaseA=resolve;});}
  return new Response(JSON.stringify({session_id:sessionId,completed_at:null,milestones:[]}));
 }};
 const clientA=createActivityClient(optsA);await clientA.ensureSession();const pending=clientA.getState();await waiting;
 const clientB=createActivityClient({...optsA,baseUrl:'https://other.example.test',fetchImpl:async()=>new Response(JSON.stringify({session_id:'019f38f1-e5ab-7688-af0d-0e8925299e94',session_token:'token-b-long-enough',expires_at:'2099-01-01T00:00:00Z'}),{status:201})});
 await clientB.ensureSession();releaseA(new Response('{}',{status:401}));await pending;
 assert.equal(aAuth.includes('Bearer token-b-long-enough'),false);assert.equal(aSessions,2);
});
