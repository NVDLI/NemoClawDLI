// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import test from 'node:test';
import { sharedRuntime } from './course_runtime_fixture.mjs';
import {ChatOpenAI} from '../../web/nemoclaw/vendor/langchain-1.4.7.esm.js';

const {
  DEFAULT_MODEL_API_BASE_URL,
  DEFAULT_MODEL_REQUEST_RETRIES,
  DEFAULT_MODEL_REQUEST_TIMEOUT_MS,
  defaultIframeProxyModeForLocation,
  fetchRetry,
  getConfig,
  getEmbeddingConfig,
  getEmbeddingModelId,
  getModelRequestPolicy,
  normalizeModelRequestRetries,
  normalizeModelRequestTimeoutMs,
  readModelStreamChunk,
  retryDelayMs,
  setIframeProxyMode,
  setEmbeddingApiBaseUrl,
  setModelApiBaseUrl,
  setModelRequestRetries,
  setModelRequestTimeoutMs,
} = sharedRuntime;

function memoryStorage() {
  const values = new Map();
  return {
    getItem:key => values.has(key) ? values.get(key) : null,
    setItem:(key, value) => values.set(key, String(value)),
    removeItem:key => values.delete(key),
  };
}

function modelTransportFixture(t) {
  const names = ['fetch','localStorage','sessionStorage','location'];
  const previous = new Map(names.map(name => [name,Object.getOwnPropertyDescriptor(globalThis,name)]));
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  globalThis.location = new URL('https://nvdli.github.io/NemoClawDLI/nemoclaw/');
  setModelApiBaseUrl('https://integrate.api.nvidia.com/v1');
  setIframeProxyMode(false);
  t.after(() => {
    for (const [name,descriptor] of previous) {
      if (descriptor) Object.defineProperty(globalThis,name,descriptor);
      else delete globalThis[name];
    }
  });
}

function completionFrames(parts, {done = true, newline = '\r\n'} = {}) {
  return ': keepalive' + newline + newline + parts.map(part => 'data: ' + JSON.stringify(part) + newline + newline).join('')
    + (done ? 'data: [DONE]' + newline + newline : '');
}

function streamResponse(text, {cancel = () => {}, keepOpen = false, delayed = false} = {}) {
  const bytes = new TextEncoder().encode(text);
  let offset = 0;
  return new Response(new ReadableStream({
    async pull(controller) {
      if (offset === bytes.length) { if (!keepOpen) controller.close(); return; }
      if (delayed) await new Promise(resolve => setTimeout(resolve,1));
      const end = Math.min(offset + 7,bytes.length);
      controller.enqueue(bytes.slice(offset,end)); offset = end;
    },
    cancel,
  }),{headers:{'content-type':'text/event-stream','x-request-id':'fixture-request'}});
}

test('buffered NVIDIA transport preserves schema, tools, indexed choices, UTF-8 and final usage', async t => {
  modelTransportFixture(t);
  let calls = 0, canceled = false, requested;
  const original = {model:'fixture/model',messages:[{role:'user',content:'fixture'}],temperature:0,max_tokens:123,n:2,
    response_format:{type:'json_schema',json_schema:{name:'answer',strict:true,schema:{type:'object',properties:{answer:{type:'string'}}}}},
    tools:[{type:'function',function:{name:'inspect',parameters:{type:'object'}}}],tool_choice:'auto'};
  const parts = [
    {id:'completion-fixture',created:7,model:'provider/model',object:'chat.completion.chunk',choices:[
      {index:1,delta:{role:'assistant',content:'{"answer":"中'},finish_reason:null},
      {index:0,delta:{role:'assistant',tool_calls:[{index:0,id:'call-',type:'function',function:{name:'ins',arguments:'{"path":'}}]},finish_reason:null},
    ]},
    {choices:[{index:0,delta:{reasoning_content:'reason',tool_calls:[{index:0,id:'owned',function:{name:'pect',arguments:'"x"}'}}]},finish_reason:'tool_calls'},
      {index:1,delta:{content:'文"}',refusal:null},finish_reason:'stop',logprobs:{content:[{token:'文',logprob:-0.2}]}}]},
    {choices:[],usage:{prompt_tokens:4,completion_tokens:9,total_tokens:13}},
  ];
  globalThis.fetch = async (_url,init) => {
    calls++; requested = JSON.parse(init.body);
    return streamResponse(completionFrames(parts),{cancel:() => {canceled=true;},keepOpen:true,delayed:true});
  };
  const response = await sharedRuntime.browserChatFetch()('https://integrate.api.nvidia.com/v1/chat/completions',{
    method:'POST',body:JSON.stringify(original),headers:{'content-type':'application/json','x-stainless-lang':'js'},
  });
  assert.deepEqual(requested,{...original,stream:true,stream_options:{include_usage:true}});
  const result = await response.json();
  assert.equal(result.object,'chat.completion');
  assert.equal(result.model,'provider/model');
  assert.equal(result.id,'completion-fixture');
  assert.equal(result.choices[0].finish_reason,'tool_calls');
  assert.deepEqual(result.choices[0].message.tool_calls,[{id:'call-owned',type:'function',function:{name:'inspect',arguments:'{"path":"x"}'}}]);
  assert.equal(result.choices[0].message.reasoning_content,'reason');
  assert.equal(result.choices[1].message.content,'{"answer":"中文"}');
  assert.equal(result.choices[1].logprobs.content[0].token,'文');
  assert.deepEqual(result.usage,{prompt_tokens:4,completion_tokens:9,total_tokens:13});
  assert.equal(response.headers.get('x-request-id'),'fixture-request');
  assert.equal(calls,1);
  assert.equal(canceled,true);
});

test('actual vendored ChatOpenAI consumes one buffered tool response without replay', async t => {
  modelTransportFixture(t);
  let calls = 0, sdkMarker = false;
  const adaptedFetch = sharedRuntime.browserChatFetch();
  const sdkFetch = (url,init) => {
    assert.equal(new Headers(init.headers).get('x-stainless-lang'),'js');
    sdkMarker = true;
    return adaptedFetch(url,init);
  };
  globalThis.fetch = async (_url,init) => {
    calls++;
    assert.equal([...new Headers(init.headers).keys()].some(key=>key.startsWith('x-stainless')),false);
    const request = JSON.parse(init.body);
    assert.equal(request.stream,true);
    assert.equal(request.tools[0].function.name,'inspect');
    return streamResponse(completionFrames([
      {id:'tool-completion',model:'fixture/model',created:1,choices:[{index:0,delta:{role:'assistant',tool_calls:[
        {index:0,id:'owned-tool',type:'function',function:{name:'inspect',arguments:'{"path":'}}]},finish_reason:null}]},
      {choices:[{index:0,delta:{tool_calls:[{index:0,function:{arguments:'"file"}'}}]},finish_reason:'tool_calls'}]},
    ]));
  };
  const llm = new ChatOpenAI({model:'fixture/model',apiKey:'fixture-only-key',maxRetries:0,
    configuration:{baseURL:'https://integrate.api.nvidia.com/v1',dangerouslyAllowBrowser:true,fetch:sdkFetch}});
  const message = await llm.bindTools([{type:'function',function:{name:'inspect',parameters:{type:'object',properties:{path:{type:'string'}}}}}]).invoke('fixture');
  assert.deepEqual(message.tool_calls.map(call => ({name:call.name,args:call.args,id:call.id})),[
    {name:'inspect',args:{path:'file'},id:'owned-tool'},
  ]);
  assert.equal(calls,1);
  assert.equal(sdkMarker,true);
});

test('buffered transport rejects malformed, failed and truncated streams without retry', async t => {
  modelTransportFixture(t);
  setModelRequestRetries(2);
  const complete = {choices:[{index:0,delta:{content:'partial'},finish_reason:'stop'}]};
  for (const text of [
    'data: {broken}\n\n',
    completionFrames([{error:{message:'provider failed'}}]),
    completionFrames([complete],{done:false}),
    completionFrames([{choices:[{index:0,delta:{content:'partial'},finish_reason:null}]}]),
    completionFrames([{choices:[{index:0,delta:{tool_calls:[{index:1,id:'gap',function:{name:'inspect',arguments:'{}'}}]},finish_reason:'tool_calls'}]}]),
    completionFrames([{choices:[{index:0,delta:{tool_calls:[{index:0,id:'missing-name',function:{arguments:'{}'}}]},finish_reason:'tool_calls'}]}]),
  ]) {
    let calls = 0;
    globalThis.fetch = async () => {calls++;return streamResponse(text);};
    await assert.rejects(sharedRuntime.browserChatFetch()('https://integrate.api.nvidia.com/v1/chat/completions',{
      method:'POST',body:JSON.stringify({model:'fixture/model',messages:[]}),headers:{'x-stainless-lang':'js'},
    }),/Malformed JSON|provider failed|complete final response|Incomplete streamed tool call/);
    assert.equal(calls,1);
  }
});

test('actual vendored ChatOpenAI does not replay a truncated streamed completion', async t => {
  modelTransportFixture(t);
  setModelRequestRetries(2);
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    return streamResponse(completionFrames([
      {choices:[{index:0,delta:{content:'partial'},finish_reason:'stop'}]},
    ],{done:false}));
  };
  const llm = new ChatOpenAI({model:'fixture/model',apiKey:'fixture-only-key',maxRetries:0,
    configuration:{baseURL:'https://integrate.api.nvidia.com/v1',dangerouslyAllowBrowser:true,fetch:sharedRuntime.browserChatFetch()}});
  await assert.rejects(llm.invoke('fixture'), error => {
    assert.match(String(error.cause?.message || error.message), /complete final response/);
    return true;
  });
  assert.equal(calls,1);
});

test('SDK body reads honor Stop after headers without waiting for stalled cancellation', async t => {
  modelTransportFixture(t);
  const controller = new AbortController();
  let canceled = false;
  globalThis.fetch = async () => new Response(new ReadableStream({cancel() {
    canceled = true; return new Promise(() => {});
  }}),{headers:{'content-type':'application/json'}});
  const response = await sharedRuntime.browserChatFetch()('https://models.example.test/v1/models',{signal:controller.signal});
  const reading = response.json();
  controller.abort(new Error('stopped after SDK headers'));
  await assert.rejects(reading,/stopped after SDK headers/);
  assert.equal(canceled,true);
});

test('retry releases an unused HTTP body before the next request', async t => {
  modelTransportFixture(t);
  let calls = 0, canceled = false;
  globalThis.fetch = async () => {
    if (++calls === 1) return new Response(new ReadableStream({cancel() {canceled=true;return new Promise(() => {});}}),{status:503});
    assert.equal(canceled,true);
    return new Response('ready');
  };
  const response = await fetchRetry('https://models.example.test/v1/models',{}, {retries:1,backoffMs:0,timeoutMs:100});
  assert.equal(await response.text(),'ready');
  assert.equal(calls,2);
});

test('actual vendored ChatOpenAI stops a stalled JSON body without replay', async t => {
  modelTransportFixture(t);
  const controller = new AbortController();
  let calls = 0, canceled = false;
  globalThis.fetch = async () => {
    calls++;
    setTimeout(() => controller.abort(new Error('learner stopped SDK response')), 5);
    return new Response(new ReadableStream({cancel() {
      canceled = true;
      return new Promise(() => {});
    }}), {headers:{'content-type':'application/json'}});
  };
  const llm = new ChatOpenAI({model:'fixture/model',apiKey:'fixture-only-key',maxRetries:0,
    configuration:{baseURL:'https://models.example.test/v1',dangerouslyAllowBrowser:true,fetch:sharedRuntime.browserChatFetch()}});
  await assert.rejects(llm.invoke('fixture', {signal:controller.signal}), /abort|stopped/i);
  assert.equal(calls,1);
  assert.equal(canceled,true);
});

test('custom providers, raw fetch and explicit streaming keep their caller request', async t => {
  modelTransportFixture(t);
  for (const [url,body] of [
    ['https://models.example.test/v1/chat/completions',{messages:[],stream:false}],
    ['https://integrate.api.nvidia.com/v1/chat/completions',{messages:[],stream:true}],
  ]) {
    let requested;
    globalThis.fetch = async (_url,init) => {requested=init.body;return new Response('{}',{headers:{'content-type':'application/json'}});};
    const response = await sharedRuntime.browserChatFetch()(url,{method:'POST',body:JSON.stringify(body),headers:{'x-stainless-lang':'js'}});
    await response.json();
    assert.equal(requested,JSON.stringify(body));
  }
  let raw;
  globalThis.fetch = async (_url,init) => {raw=init.body;return new Response('{}');};
  await fetch('https://integrate.api.nvidia.com/v1/chat/completions',{method:'POST',body:'{"stream":false}'});
  assert.equal(raw,'{"stream":false}');
});

test('default browserChatFetch preserves the authored JSON wire request and response', async t => {
  modelTransportFixture(t);
  const body=' { "model": "fixture/model", "messages": [], "stream": false } ';
  const reply=' { "choices": [{"message":{"content":"raw response"}}] } ';
  for (const headers of [{},{'x-stainless-runtime':'browser'}]) {
    let calls=0;
    globalThis.fetch=async(_url,init)=>{
      calls++;
      assert.equal(init.body,body,'wire bytes match the authored raw request');
      return new Response(reply,{headers:{'content-type':'application/json; charset=utf-8'}});
    };
    const response=await sharedRuntime.browserChatFetch()('https://integrate.api.nvidia.com/v1/chat/completions',{
      method:'POST',body,headers,
    });
    assert.equal(response.headers.get('content-type'),'application/json; charset=utf-8');
    assert.equal(await response.text(),reply);
    assert.equal(calls,1);
  }
});

test('Stop cancels a pending body read and removes its listener', async () => {
  const controller = new AbortController();
  let canceled = false;
  let added = 0;
  let removed = 0;
  const add = controller.signal.addEventListener.bind(controller.signal);
  const remove = controller.signal.removeEventListener.bind(controller.signal);
  controller.signal.addEventListener = (...args) => { added++; return add(...args); };
  controller.signal.removeEventListener = (...args) => { removed++; return remove(...args); };
  const reader = new ReadableStream({ cancel() { canceled = true; } }).getReader();
  const pending = readModelStreamChunk(reader, 1000, controller.signal);
  controller.abort(new Error('learner stopped the body read'));
  await assert.rejects(pending, /learner stopped the body read/);
  assert.equal(canceled, true);
  assert.equal(added, removed);
  reader.releaseLock();
});

test('successful body reads remove listeners and retain byte content', async () => {
  const controller = new AbortController();
  let added = 0;
  let removed = 0;
  const add = controller.signal.addEventListener.bind(controller.signal);
  const remove = controller.signal.removeEventListener.bind(controller.signal);
  controller.signal.addEventListener = (...args) => { added++; return add(...args); };
  controller.signal.removeEventListener = (...args) => { removed++; return remove(...args); };
  const bytes = new TextEncoder().encode('model response');
  const reader = new ReadableStream({ start(stream) { stream.enqueue(bytes); stream.close(); } }).getReader();
  assert.deepEqual((await readModelStreamChunk(reader, 100, controller.signal)).value, bytes);
  assert.equal((await readModelStreamChunk(reader, 100, controller.signal)).done, true);
  assert.equal(added, removed);
  controller.abort();
  reader.releaseLock();
});

for (const operation of ['chat', 'chatStream']) {
  test(`${operation} observes Stop after the HTTP headers arrive`, async () => {
    const previous = { fetch:globalThis.fetch, localStorage:globalThis.localStorage };
    globalThis.localStorage = memoryStorage();
    setModelApiBaseUrl('https://models.example.test/v1');
    const controller = new AbortController();
    let canceled = false;
    globalThis.fetch = async () => {
      setTimeout(() => controller.abort(new Error('stopped after headers')), 10);
      return new Response(new ReadableStream({ cancel() { canceled = true; } }));
    };
    try {
      await assert.rejects(sharedRuntime[operation]({ messages:[], signal:controller.signal }), /stopped after headers/);
      assert.equal(canceled, true);
    } finally {
      for (const [name, value] of Object.entries(previous)) {
        if (value === undefined) delete globalThis[name];
        else globalThis[name] = value;
      }
    }
  });
}

test('DONE cancels an open response body and preserves the provider model identity', async () => {
  const previous = { fetch:globalThis.fetch, localStorage:globalThis.localStorage };
  globalThis.localStorage = memoryStorage();
  setModelApiBaseUrl('https://models.example.test/v1');
  let canceled = false;
  globalThis.fetch = async () => new Response(new ReadableStream({
    start(stream) {
      const frame = { model:'provider/actual-model', choices:[{ delta:{ content:'ready' }, finish_reason:'stop' }] };
      stream.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(frame)}\n\ndata: [DONE]\n\n`));
    },
    cancel() { canceled = true; },
  }));
  try {
    const result = await sharedRuntime.chatStream({ messages:[] });
    assert.equal(result.model, 'provider/actual-model');
    assert.equal(result.content, 'ready');
    assert.equal(result.finish_reason, 'stop');
    assert.equal(canceled, true);
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  }
});

test('public chatStream delivers incremental CRLF deltas and completes before socket EOF', async t => {
  modelTransportFixture(t);
  const usage={prompt_tokens:2,completion_tokens:4,total_tokens:6};
  const last={model:'provider/actual-model',choices:[],usage};
  let stream, canceled=false, meta=null;
  const content=[],reasoning=[];
  const first={model:'provider/actual-model',choices:[{index:0,delta:{content:'你好',reasoning_content:'Check '},finish_reason:null}]};
  globalThis.fetch=async () => new Response(new ReadableStream({
    start(controller) {stream=controller;controller.enqueue(new TextEncoder().encode(completionFrames([first],{done:false})));},
    cancel(){canceled=true;},
  }),{headers:{'content-type':'text/event-stream'}});
  const result=await sharedRuntime.chatStream({messages:[]}, text => {
    content.push(text);
    assert.equal(meta,null,'metadata is published only after complete response');
    // The provider cannot finish until the first incremental callback runs.
    if(content.length===1) stream.enqueue(new TextEncoder().encode(completionFrames([
      {choices:[{index:0,delta:{content:' 🌐',reasoning_content:'clock',tool_calls:[{index:0,id:'tool-1',function:{name:'get_',arguments:'{'}}]},finish_reason:null}]},
      {choices:[{index:0,delta:{tool_calls:[{index:0,function:{name:'time',arguments:'}'}}]},finish_reason:'tool_calls'}]},last,
    ])));
  },{onReasoning:text=>reasoning.push(text),onMeta:value=>{meta=value;}});
  assert.deepEqual(content,['你好',' 🌐']);
  assert.deepEqual(reasoning,['Check ','clock']);
  assert.equal(result.content,'你好 🌐');
  assert.equal(result.reasoning,'Check clock');
  assert.deepEqual(result.tool_calls,[{index:0,id:'tool-1',type:'function',function:{name:'get_time',arguments:'{}'}}]);
  assert.equal(result.finish_reason,'tool_calls');
  assert.equal(result.model,'provider/actual-model');
  assert.deepEqual(result.usage,usage);
  assert.deepEqual(result.raw,last);
  assert.equal(meta,result);
  assert.equal(canceled,true);
});

test('single-choice missing indices remain compatible while explicit or ambiguous indices fail', async t => {
  modelTransportFixture(t);
  const choice={delta:{content:'one'},finish_reason:'stop'};
  globalThis.fetch=async()=>streamResponse(completionFrames([{choices:[choice]}]));
  const delivered=[];
  assert.equal((await sharedRuntime.chatStream({messages:[]},text=>delivered.push(text))).content,'one');
  assert.deepEqual(delivered,['one']);
  for(const [choices,n] of [
    [[{...choice,index:'0'}],1],
    [[{...choice,index:null}],1],
    [[choice,choice],1],
    [[choice],2],
    [[choice,choice],2],
  ]) {
    globalThis.fetch=async()=>streamResponse(completionFrames([{choices}]));
    await assert.rejects(sharedRuntime.chatStream({messages:[],extra_body:{n}}),/Invalid model stream choice index/);
  }
});

test('public chatStream rejects invalid or incomplete streams without replay or success metadata', async t => {
  modelTransportFixture(t);
  setModelRequestRetries(2);
  for(const text of [
    'data: {invalid}\r\n\r\n',
    completionFrames([{error:{message:'stream provider failed'}}]),
    completionFrames([{choices:[{index:0,delta:{content:'partial'},finish_reason:'stop'}]}],{done:false}),
    completionFrames([{choices:[{index:0,delta:{content:'partial'},finish_reason:null}]}]),
    completionFrames([{choices:[{index:0,delta:{content:42},finish_reason:'stop'}]}]),
  ]) {
    let calls=0,metadata=0,canceled=false;
    globalThis.fetch=async()=>{calls++;return streamResponse(text,{keepOpen:text.includes('[DONE]'),cancel(){canceled=true;}});};
    await assert.rejects(sharedRuntime.chatStream({messages:[]},null,{onMeta(){metadata++;}}),
      /Malformed JSON|stream provider failed|complete final response|Invalid text/);
    assert.equal(calls,1);
    assert.equal(metadata,0);
    if(text.includes('[DONE]'))assert.equal(canceled,true);
  }
});

test('public chatStream Stop during a callback cancels before further callbacks or completion', async t => {
  modelTransportFixture(t);
  const controller=new AbortController();
  let calls=0,canceled=false,reasoning=0,metadata=0;
  globalThis.fetch=async()=>{calls++;return streamResponse(completionFrames([
    {choices:[{index:0,delta:{content:'partial',reasoning_content:'late'},finish_reason:'stop'}]},
  ]),{keepOpen:true,cancel(){canceled=true;return new Promise(()=>{});}});};
  await assert.rejects(sharedRuntime.chatStream({messages:[],signal:controller.signal},()=>{
    controller.abort(new Error('stopped incremental output'));
  },{onReasoning(){reasoning++;},onMeta(){metadata++;}}),/stopped incremental output/);
  assert.equal(calls,1);
  assert.equal(canceled,true);
  assert.equal(reasoning,0);
  assert.equal(metadata,0);
});

test('only the former NVIDIA hosted embedding default migrates', () => {
  const previous = globalThis.localStorage;
  globalThis.localStorage = memoryStorage();
  const oldModel = 'nvidia/llama-nemotron-embed-vl-1b-v2';
  try {
    assert.equal(getEmbeddingModelId(), 'nvidia/nemotron-3-embed-1b');
    localStorage.setItem('nemoclaw_embedding_model_id_v1', oldModel);
    assert.equal(getEmbeddingModelId(), 'nvidia/nemotron-3-embed-1b');
    setEmbeddingApiBaseUrl('https://models.example.test/v1');
    assert.equal(getEmbeddingModelId(), oldModel);
    setEmbeddingApiBaseUrl(DEFAULT_MODEL_API_BASE_URL);
    localStorage.setItem('nemoclaw_embedding_model_id_v1', `${oldModel}-custom`);
    assert.equal(getEmbeddingModelId(), `${oldModel}-custom`);
    localStorage.setItem('nemoclaw_embedding_model_id_v1', 'example/custom-embed');
    assert.equal(getEmbeddingModelId(), 'example/custom-embed');
  } finally {
    if (previous === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = previous;
  }
});

test('the model relay default covers only the exact published course origins and local files', () => {
  const cases = [
    ['https://cdn.dli.learn.nvidia.com/course-static/nemoclaw/', true],
    ['https://nvdli.github.io/NemoClawDLI/nemoclaw/', true],
    ['file:course-preview.html', true],
    ['http://127.0.0.1:4173/nemoclaw/', true],
    ['http://localhost:8000/nemoclaw/', true],
    ['http://staging.localhost:8000/nemoclaw/', true],
    ['https://localhost:8443/nemoclaw/', true],
    ['http://cdn.dli.learn.nvidia.com/course-static/nemoclaw/', false],
    ['https://cdn.dli.learn.nvidia.com.example.invalid/', false],
    ['http://nvdli.github.io/NemoClawDLI/nemoclaw/', false],
    ['https://nvdli.github.io.example.invalid/NemoClawDLI/', false],
    ['http://localhost.example.invalid/nemoclaw/', false],
    ['https://example.com/', false],
    ['data:text/html,course', false],
  ];
  for (const [location, expected] of cases) {
    assert.equal(defaultIframeProxyModeForLocation(location), expected, location);
  }
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

test('embedding route shares relay selection but keeps its own endpoint', async () => {
  const previous = {
    location:globalThis.location,
    localStorage:globalThis.localStorage,
    sessionStorage:globalThis.sessionStorage,
  };
  globalThis.location = new URL('https://nvdli.github.io/NemoClawDLI/nemoclaw/02b-rag.html');
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  try {
    const relayed = await getEmbeddingConfig();
    assert.deepEqual(relayed, {
      mode:'direct',
      url:'https://nvidia-api-cors-proxy.experiments.courses.nvidia.com/v1',
      model:'nvidia/nemotron-3-embed-1b',
      needsKey:true,
      iframeProxy:true,
    });

    setIframeProxyMode(false);
    const direct = await getEmbeddingConfig();
    assert.equal(direct.url, DEFAULT_MODEL_API_BASE_URL);
    assert.equal(direct.iframeProxy, false);

    setIframeProxyMode(true);
    setEmbeddingApiBaseUrl('https://embedding.example.test/v1');
    const custom = await getEmbeddingConfig();
    assert.equal(custom.url, 'https://embedding.example.test/v1');
    assert.equal(custom.iframeProxy, false);
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete globalThis[name];
      else globalThis[name] = value;
    }
  }
});

test('model request handling is bounded and retries are opt-in', () => {
  const previous = globalThis.localStorage;
  globalThis.localStorage = memoryStorage();
  try {
    assert.deepEqual(getModelRequestPolicy(), {
      retries: DEFAULT_MODEL_REQUEST_RETRIES,
      timeoutMs: DEFAULT_MODEL_REQUEST_TIMEOUT_MS,
    });
    assert.equal(setModelRequestTimeoutMs(120000), 120000);
    assert.equal(setModelRequestRetries(2), 2);
    assert.deepEqual(getModelRequestPolicy(), { retries:2, timeoutMs:120000 });
    assert.throws(() => normalizeModelRequestTimeoutMs(4999), /between 5 and 300 seconds/);
    assert.throws(() => normalizeModelRequestRetries(6), /0 to 5/);
  } finally {
    if (previous === undefined) delete globalThis.localStorage;
    else globalThis.localStorage = previous;
  }
});

test('Retry-After supports seconds and HTTP dates within the request bound', () => {
  const headers = value => ({ get:name => name.toLowerCase() === 'retry-after' ? value : null });
  assert.equal(retryDelayMs({ headers:headers('7') }, 500, 0, 60000, 1000), 7000);
  assert.equal(retryDelayMs(
    { headers:headers('Thu, 01 Jan 1970 00:00:12 GMT') },
    500, 0, 60000, 10000,
  ), 2000);
  assert.equal(retryDelayMs({ headers:headers('900') }, 500, 0, 60000, 1000), 60000);
  assert.equal(retryDelayMs({ headers:headers('invalid') }, 500, 2, 60000, 1000), 2000);
});

test('HTTP 429 retries only when configured and then returns the usable response', async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return calls === 1
      ? new Response('', { status:429, headers:{ 'Retry-After':'0' } })
      : new Response('ready', { status:200 });
  };
  try {
    const response = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:1, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(await response.text(), 'ready');
    assert.equal(calls, 2);
  } finally {
    if (previous === undefined) delete globalThis.fetch;
    else globalThis.fetch = previous;
  }
});

test('caller errors do not retry and caller aborts stop before fetch', async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response('', { status:400 });
  };
  try {
    const response = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:5, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(response.status, 400);
    assert.equal(calls, 1);
    const controller = new AbortController();
    controller.abort(new Error('learner stopped'));
    await assert.rejects(
      fetchRetry('https://models.example.test/v1/models', { signal:controller.signal }),
      /learner stopped/,
    );
    assert.equal(calls, 1);
  } finally {
    if (previous === undefined) delete globalThis.fetch;
    else globalThis.fetch = previous;
  }
});

test('HTTP 503 and network failures retry only when the learner opts in', async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls === 1) return new Response('', { status:503 });
    return new Response('recovered', { status:200 });
  };
  try {
    const first = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:0, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(first.status, 503);
    assert.equal(calls, 1);
    const recovered = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:1, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(await recovered.text(), 'recovered');
    assert.equal(calls, 2);

    calls = 0;
    globalThis.fetch = async () => {
      calls += 1;
      if (calls === 1) throw new TypeError('socket closed');
      return new Response('network recovered', { status:200 });
    };
    await assert.rejects(
      fetchRetry('https://models.example.test/v1/models', {}, {
        retries:0, timeoutMs:1000, backoffMs:1,
      }),
      /after 1 attempt.*socket closed/s,
    );
    assert.equal(calls, 1);
    const networkRecovered = await fetchRetry('https://models.example.test/v1/models', {}, {
      retries:1, timeoutMs:1000, backoffMs:1,
    });
    assert.equal(await networkRecovered.text(), 'network recovered');
    assert.equal(calls, 2);
  } finally {
    if (previous === undefined) delete globalThis.fetch;
    else globalThis.fetch = previous;
  }
});

test('timeouts and caller cancellation remain bounded without a hidden retry', async () => {
  const previous = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async (_url, init = {}) => {
    calls += 1;
    return new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(init.signal.reason), { once:true });
    });
  };
  try {
    await assert.rejects(
      fetchRetry('https://models.example.test/v1/models', {}, {
        retries:0, timeoutMs:5, backoffMs:1,
      }),
      /wait limit 0s.*timeout after 5ms/s,
    );
    assert.equal(calls, 1);

    const controller = new AbortController();
    globalThis.fetch = async () => {
      calls += 1;
      queueMicrotask(() => controller.abort(new Error('learner stopped during recovery')));
      return new Response('', { status:503 });
    };
    await assert.rejects(
      fetchRetry('https://models.example.test/v1/models', { signal:controller.signal }, {
        retries:5, timeoutMs:1000, backoffMs:100,
      }),
      /learner stopped during recovery/,
    );
    assert.equal(calls, 2);
  } finally {
    if (previous === undefined) delete globalThis.fetch;
    else globalThis.fetch = previous;
  }
});

test('stream stalls and mid-stream failures are visible and cancel the reader', async () => {
  let cancelled = false;
  const stalled = {
    read:async () => new Promise(() => {}),
    cancel:async () => { cancelled = true; },
  };
  await assert.rejects(
    readModelStreamChunk(stalled, 5),
    /stopped producing data.*Request handling/s,
  );
  assert.equal(cancelled, true);

  let reads = 0;
  const failed = {
    read:async () => {
      reads += 1;
      if (reads === 1) {
        return { done:false, value:new TextEncoder().encode('data: partial\n\n') };
      }
      throw new Error('mid-stream socket failure');
    },
    cancel:async () => {},
  };
  const first = await readModelStreamChunk(failed, 100);
  assert.equal(new TextDecoder().decode(first.value), 'data: partial\n\n');
  await assert.rejects(
    readModelStreamChunk(failed, 100),
    /mid-stream socket failure/,
  );
});

test('idle timeout survives transport cancellation that never settles', async () => {
  const reader = new ReadableStream({ cancel:() => new Promise(() => {}) }).getReader();
  const pending = readModelStreamChunk(reader, 5);
  await assert.rejects(Promise.race([
    pending,
    new Promise((_, reject) => setTimeout(() => reject(new Error('cancellation hung')), 100)),
  ]), /stopped producing data/);
  reader.releaseLock();
});

for (const operation of ['chat', 'chatStream']) {
  test(`${operation} propagates Stop despite a hanging cancel implementation`, async () => {
    const previous = { fetch:globalThis.fetch, localStorage:globalThis.localStorage };
    globalThis.localStorage = memoryStorage();
    setModelApiBaseUrl('https://models.example.test/v1');
    const controller = new AbortController();
    let canceled = false;
    globalThis.fetch = async () => {
      setTimeout(() => controller.abort(new Error('learner stopped')), 5);
      return new Response(new ReadableStream({ cancel() {
        canceled = true;
        return new Promise(() => {});
      } }));
    };
    try {
      await assert.rejects(Promise.race([
        sharedRuntime[operation]({ messages:[], signal:controller.signal }),
        new Promise((_, reject) => setTimeout(() => reject(new Error('cleanup hung')), 100)),
      ]), /learner stopped/);
      assert.equal(canceled, true);
    } finally {
      for (const [name, value] of Object.entries(previous)) {
        if (value === undefined) delete globalThis[name];
        else globalThis[name] = value;
      }
    }
  });
}
