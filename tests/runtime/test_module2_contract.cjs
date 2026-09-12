/* Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0 */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const root = process.env.COURSE_SOURCE_ROOT;
assert(root, 'COURSE_SOURCE_ROOT is required');
const {discoverCourses,courseLanguage}=require('./course_exercise_fixture.cjs');
let directory;
const noop = () => {};
const log = Object.assign(noop, {details: noop, html: noop});
const logs = [];

// Capture the actual displayed templates by evaluating page registration code.
// Model and embedding services are the only substituted execution dependencies.
function readPage(name) {
  const html = fs.readFileSync(path.join(directory, name), 'utf8');
  const flows = {}, cells = {};
  const source = html.match(/<script type="text\/plain" id="deep-src">([\s\S]*?)<\/script>/)?.[1];
  const document = {getElementById(id) {return {textContent:id === 'deep-src' ? source : '', innerHTML:''};}};
  const sandbox = {console, document, location:{href:'http://course/web/nemoclaw/' + name},
    buildNav:noop, updateKeyPill:noop, mountJourneyMap:noop, hljs:{highlightAll:noop},
    mountCanvasFlow:(id, value) => {flows[id]=value;}, mountRunCell:(id, value) => {cells[id]=value;}};
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  for (const match of html.matchAll(/<script type="module">([\s\S]*?)<\/script>/g)) {
    const code = match[1].replace(/^\s*import\s+.*?;\s*$/gm, '');
    vm.runInContext(code, sandbox, {filename:name});
  }
  const node = (flow, id) => {
    const value = flows[flow]?.nodes.find(value => value.id === id);
    assert(value, name + ': missing displayed node ' + flow + '/' + id);
    return value.code;
  };
  return {html, flows, cells, sandbox, node};
}

function run(code, state = {}, helpers = {}, window = {}) {
  const sandbox = {state, helpers:{log, getEmbeddingConfig:async()=>({url:'https://embedding.example/v1',model:'fixture-embedding'}), ...helpers}, window, console, performance, Date, Set,
    location:{href:'http://course/web/nemoclaw/'}};
  return vm.runInNewContext('(async () => {\n' + code + '\n})()', sandbox);
}
const response = (content, finish_reason='stop', tool_calls=[]) => ({content, finish_reason, tool_calls});
const call = (id, question, k=3) => ({id, type:'function', function:{name:'retrieve', arguments:JSON.stringify({question,k})}});
// File-condition fixtures bypass workers deliberately; lifecycle cases below run them.
function completedDispatch(state) {
  state.writtenPaths ||= new Set();
  const dispatch={goal:state.goal,expectedFiles:state.expectedFiles?.slice(),
    writtenPaths:state.writtenPaths,complete:true};
  state.dispatch=dispatch;
  dispatch.current=()=>state.dispatch===dispatch && state.goal===dispatch.goal
    && JSON.stringify(state.expectedFiles)===JSON.stringify(dispatch.expectedFiles);
}
let checked = 0;
const failures=[];
async function test(label, fn) {
  try { await fn(); checked++; console.log('PASS ' + label); }
  catch(error) { failures.push(error); console.error('FAIL ' + directory + ': ' + label, error); }
}

(async () => {
  for(const course of discoverCourses(root).roots) {
  directory=course; checked=0;
  const language=courseLanguage(root,course,['02a-routing.html','02b-rag.html','02c-deep.html']);
  const d=language.match, t=language.text;
  const routing = readPage('02a-routing.html');
  const retrieval = readPage('02b-rag.html');
  const deep = readPage('02c-deep.html');
  const planner = routing.node('#cell-m2a-rewoo', 'planner');
  const triage = routing.node('#cell-m2a-triage', 'triage');

  await test('every displayed Module 2 code template compiles after projection', async () => {
    for (const page of [routing, retrieval, deep]) {
      const nodes = Object.values(page.flows).flatMap(flow => flow.nodes);
      for (const entry of [...nodes, ...Object.values(page.cells)]) {
        new vm.Script('(async () => {\n' + entry.code + '\n})');
      }
    }
  });

  // These validation diagnostics live in the native inline helper, outside locale resources.
  // Their exact English text remains executable in every materialized locale.
  await test('planner validates final JSON and never silently substitutes a plan', async () => {
    const state={goal:'question'};
    const valid={topic:'topic', queries:['one','two','three']};
    await run(planner, state, {chatStream:async()=>response(JSON.stringify(valid))}, routing.sandbox);
    assert.equal(state.plan.queries.length, 3);
    for (const value of [null, {}, {topic:'a',queries:['a']}, {topic:'a',queries:'bad'},
      {topic:'a',queries:['a','','c']}, {topic:'a',queries:['a','b','c'],extra:true}]) {
      await assert.rejects(run(planner, {}, {chatStream:async()=>response(JSON.stringify(value))}, routing.sandbox), /Planner must return (?:a JSON object|a topic and 3–5 nonempty search queries)\./);
    }
    await assert.rejects(run(planner, {}, {chatStream:async()=>({...response('', 'length'),reasoning:JSON.stringify(valid)})}, routing.sandbox), /Planner did not finish a JSON answer \(finish_reason: length\)\. Inspect the response before retrying\./);
  });

  await test('triage rejects invalid enum and never defaults to software', async () => {
    const state={ticket:'test'};
    await run(triage, state, {chatStream:async()=>response('{"category":"network","priority":"high","summary":"VPN unavailable"}')}, routing.sandbox);
    assert.equal(state.classification.category, 'network');
    for (const value of [{category:'billing',priority:'high',summary:'test'},
      {category:'network',priority:'urgent',summary:'test'}, {category:'account',priority:'low'}]) {
      await assert.rejects(run(triage, {}, {chatStream:async()=>response(JSON.stringify(value))}, routing.sandbox), /Triage returned an invalid category, priority, or summary\./);
    }
    await assert.rejects(run(routing.node('#cell-m2a-triage','router'), {classification:{category:'billing'}}), d(/Unknown specialist/));
  });

  await test('live router accepts exactly one label and rejects ambiguous or truncated output', async () => {
    let config;
    for (const [raw, finish, valid] of [['billing','stop',true],[' TECHNICAL ','stop',true],
      ['not billing; technical','stop',false],['mother','stop',false],['billing and account','stop',false],['billing','length',false],['','stop',false]]) {
      let answers=0, successes=0;
      await run(routing.cells['#router-cell'].code, {}, {
        mountChatUI:(id,value)=>{config=value;},
        chat:async()=>({choices:[{finish_reason:finish,message:{content:raw}}]}),
        chatStream:async()=>{answers++;return response('answer');},
      });
      const task=config.respond('question',{model:'fixture',history:[],view:{tool:noop,token:noop,reasoning:noop,usage:noop,activitySuccess(){successes++;}}});
      if(valid) await task; else await assert.rejects(task, d(/allowed category/));
      assert.equal(answers, valid?1:0); assert.equal(successes, valid?1:0);
    }
  });

  await test('one-call specialist retains tool requests without pretending to execute them', async () => {
    const requested = [{id:'clock',type:'function',function:{name:'get_current_time',arguments:'{}'}}];
    const state={}; let calls=0;
    await run(routing.node('#cell-m2a-factory','factory'), state);
    const result=await state.createSpecialist({role:'clock',systemPrompt:'test',tools:[{}]}).run('now', {log,chatStream:async()=>{calls++; return response('', 'tool_calls',requested);}});
    assert.equal(calls,1); assert.equal(result.tool_requests[0].id,'clock'); assert.equal(result.reply,'');
  });

  const flow='#cell-m3b-p4';
  await test('retrieval preserves the authored corpus and matching passage vectors',async()=>{
    const state={}; let embedded;
    await run(retrieval.node(flow,'build_corpus'),state,{embed:async passages=>{
      embedded=Array.from(passages);
      return passages.map(()=>[1,0]);
    }});
    assert.equal(embedded.length,6);
    assert.equal(state.index.length,6);
    for (let i = 0; i < embedded.length; i++) {
      assert.equal(state.index[i].text, embedded[i]);
      assert.deepEqual(Array.from(state.index[i].vector), [1, 0]);
    }
    assert.match(embedded[0],/NVIDIA Nemotron/);
    assert.match(embedded[5],/LangChain\.js/);
  });
  const embed=async()=>[[1,0]];
  const fixture={embed, cosineSim:(q,v)=>v[0],viz:{retrievalBars:noop}};
  const state={corpus:['first passage','second passage'],RETRIEVE_SCHEMA:[],messages:[],query:'question'};
  await run(retrieval.node('#cell-m3b-p2','index'),state,{embed:async()=>[[1,0],[.5,1]]});
  async function decide(target, value) {
    target.messages=[];
    await run(retrieval.node(flow,'agent'),target,{chatStream:async()=>value});
  }
  await test('retrieval direct-to-tool-to-direct rerun resets state and synthesizes only when needed', async () => {
    let syntheses=0;
    for (const needed of [false,true,false]) {
      state.messages=[];
      await run(retrieval.node(flow,'agent'), state, {chatStream:async()=>response(needed?'':'direct', needed?'tool_calls':'stop', needed?[call('r1','question',2)]:[])});
      await run(retrieval.node(flow,'retrieve'), state, fixture);
      const final=await run(retrieval.node(flow,'answer'),state,{chatStream:async()=>{syntheses++;return response('grounded');}});
      assert.equal(final,needed?'grounded':'direct');
    }
    assert.equal(syntheses,1);
  });

  await test('retrieval responds to every unique request ID and bounds requested k', async () => {
    await decide(state,response('', 'tool_calls',[call('a','one',1),call('b','two',10)]));
    await run(retrieval.node(flow,'retrieve'),state,fixture);
    const resultIds=state.messages.filter(m=>m.role==='tool').map(m=>m.tool_call_id);
    assert.equal(resultIds.join(','),'a,b');
    assert.equal(state.retrievals[1].passages.length,2);
    const malformed=[call('a','one',0),call('a','one',11),call('a','one',1.5),call('a','',1),
      {...call('a','one'),function:{name:'other',arguments:'{}'}},
      {...call('a','one'),function:{name:'retrieve',arguments:'not JSON'}}];
    for (const bad of malformed) {
      const candidate={...state};
      await decide(candidate,response('','tool_calls',[call('good','question'),bad]));
      const prior=JSON.stringify(candidate.messages);
      let embeds=0;
      await assert.rejects(run(retrieval.node(flow,'retrieve'),candidate,{...fixture,embed:async()=>{embeds++;return [[1,0]];}}), d(/[Ii]nvalid|[Rr]etrieve/));
      assert.equal(embeds,0,'validate all calls before any retrieval'); assert.equal(JSON.stringify(candidate.messages),prior);
    }
    const duplicate={...state};
    await decide(duplicate,response('','tool_calls',[call('same','one'),call('same','two')]));
    await assert.rejects(run(retrieval.node(flow,'retrieve'),duplicate,fixture), d(/duplicate/));
  });

  await test('retrieval reports incomplete output instead of stripping it into an answer', async () => {
    await assert.rejects(run(retrieval.node(flow,'agent'),state,{chatStream:async()=>response('', 'length')}), d(/did not finish/));
    await assert.rejects(run(retrieval.node(flow,'retrieve'),state,fixture), d(/complete decision/));
    await decide(state,response('','tool_calls',[call('r','question')]));
    await run(retrieval.node(flow,'retrieve'),state,fixture);
    await assert.rejects(run(retrieval.node(flow,'answer'),state,{chatStream:async()=>response('partial','length')}), d(/complete answer/));
    await decide(state,response(''));
    await assert.rejects(run(retrieval.node(flow,'retrieve'),state,fixture), d(/without an answer/));
  });

  await test('research controller preserves both source types at cap and identifies repairs', async () => {
    const pages=[{id:'overview',title:'Overview'},{id:'02a-routing',title:'Routing'}];
    const examples=[
      Array.from({length:4},(_,i)=>({source:'section',target:'overview',goal:'section '+i})),
      Array.from({length:4},(_,i)=>({source:'materials',target:'AI Agents',goal:'material '+i})),
      [{source:'section',target:'overview',goal:'course'},{source:'materials',target:'AI Agents',goal:'materials'},
        {source:'section',target:'02a-routing',goal:'routing'}],
    ];
    for (const branches of examples) {
      let config, plan;
      await run(deep.cells['#deep-cell'].code, {}, {coursePages:()=>pages,mountChatUI:(id,value)=>{config=value;},chatStream:async()=>response(JSON.stringify({branches}))});
      const sentinel=new Error('stop after actual plan selection');
      await assert.rejects(config.respond('question',{model:'fixture',view:{tool(label,value){if(label==='plan'){plan=value;throw sentinel;}}}}),error=>error===sentinel);
      assert(plan.branches.length<=4); assert(plan.branches.some(b=>b.source==='section'));assert(plan.branches.some(b=>b.source==='materials'));
      assert.equal(plan.controller_adjustments.length>0, branches.length===4);
      assert.equal(plan.model_branches.length,branches.length);
    }
    for(const bad of [{branches:{}},{branches:[]},{branches:[{source:'materials',target:'not listed',goal:'x'}]}]) {
      let config;
      await run(deep.cells['#deep-cell'].code, {}, {coursePages:()=>pages,mountChatUI:(id,value)=>{config=value;},chatStream:async()=>response(JSON.stringify(bad))});
      await assert.rejects(config.respond('question',{view:{tool:noop}}), /Planner returned an invalid source, target, goal, or branches array\./);
    }
  });

  await test('research planner receives current page IDs and rejects display-label aliases', async () => {
    for(const id of ['02c-deep','newly-added-lesson']) {
      const pages=[{id:'overview',title:'Home'},{id,title:'2c · Deep Agents'}];
      let config,request;
      const branches=[{source:'section',target:'2c',goal:'Read the lesson'},
        {source:'section',target:'overview',goal:'Read the overview'},
        {source:'materials',target:'Deep Agents',goal:'Read the definition'}];
      await run(deep.cells['#deep-cell'].code,{}, {
        coursePages:()=>pages,mountChatUI:(_id,value)=>{config=value;},
        chatStream:async value=>{request=value;return response(JSON.stringify({branches}));},
      });
      await assert.rejects(config.respond('Compare patterns',{model:'fixture',view:{tool:noop}}),/Planner returned an invalid source, target, goal, or branches array\./);
      assert.equal(request.response_format.type,'json_schema');
      const choices=request.response_format.json_schema.schema.properties.branches.items.properties;
      assert(choices.target.enum.includes(id));
      assert(choices.target.enum.includes('Deep Agents'));
      assert(!choices.target.enum.includes('2c'));
      assert.equal(request.model,'fixture');
    }
  });

  await test('rendered parent lookup does not claim an unexecuted generation call', async () => {
    const output=retrieval.node('#cell-m3b-p3','lookup');
    const state={docs:[{id:'one',title:'One',body:'Full parent.'}],query:'question'};
    await run(retrieval.node('#cell-m3b-p3','split'),state);
    await run(retrieval.node('#cell-m3b-p3','index'),state,fixture);
    let calls=0;
    const result=await run(output,state,{...fixture,chatStream:async()=>{calls++;throw Error('unexpected model call');}});
    assert.equal(calls,0);assert.equal(state.hit.parent_body,'Full parent.');
    assert.equal(result.parent_returned,'One');
    assert.equal(result.precision_gain,t('child chunk score; full parent body returned by retrieval'));
  });

  await test('file synthesis rejects placeholder output and reports each missing deliverable', async () => {
    const expectedFiles = ['nim_overview.md', 'nim_use_cases.md', 'nim_vs_hosting.md'];
    const state = {expectedFiles, writtenPaths:new Set(['placeholder.txt']), vfs:{'placeholder.txt':'Completed'}, goal:'Draft NIM notes'};
    completedDispatch(state);
    let calls = 0;
    await assert.rejects(run(deep.node('#cell-m3c-p3','synth'), state, {
      chatStream:async()=>{calls++; return response('Completed');},
    }, deep.sandbox), error => expectedFiles.every(p => error.message.includes(p)));
    assert.equal(calls, 0);
    assert.equal(state.synthesis, '');
    assert.equal(Object.hasOwn(state.vfs, 'final_report.md'), false);
  });

  await test('file synthesis uses exactly the expected nonempty drafts', async () => {
    const expectedFiles = ['nim_overview.md', 'nim_use_cases.md', 'nim_vs_hosting.md'];
    const state = {expectedFiles, writtenPaths:new Set(expectedFiles), goal:'Draft NIM notes', vfs:{
      'nim_overview.md':'Unverified overview draft.',
      'nim_use_cases.md':'Unverified use-case draft.',
      'nim_vs_hosting.md':'Unverified comparison draft.',
      'unrelated.md':'EXCLUDE_UNRELATED', 'final_report.md':'EXCLUDE_OLD_REPORT',
    }};
    completedDispatch(state);
    const result = await run(deep.node('#cell-m3c-p3','synth'),state,{
      chatStream:async request=>{
        const context=request.messages.at(-1).content;
        for(const file of expectedFiles) assert(context.includes(file));
        assert.doesNotMatch(context,/EXCLUDE_UNRELATED|EXCLUDE_OLD_REPORT/);
        return response('Combined unverified draft.');
      },
    }, deep.sandbox);
    assert.equal(result.synthesised,true);
    assert.deepEqual(Array.from(result.source_files),expectedFiles);
    assert.equal(state.vfs['final_report.md'],'Combined unverified draft.');
  });

  await test('stale reports and empty drafts cannot satisfy the expected-file contract', async () => {
    for(const state of [
      {expectedFiles:['nim_overview.md'],vfs:{'final_report.md':'Old completed report'}},
      {expectedFiles:['nim_overview.md'],vfs:{'nim_overview.md':'   ','final_report.md':'Old report'}},
      {expectedFiles:['final_report.md'],vfs:{'final_report.md':'Old report'}},
    ]){
      state.synthesis='Previous successful answer';
      completedDispatch(state);
      let calls=0;
      await assert.rejects(run(deep.node('#cell-m3c-p3','synth'),state,{
        chatStream:async()=>{calls++;return response('Unexpected');},
      },deep.sandbox),d(/expected drafts|reserved/));
      assert.equal(calls,0);assert.equal(state.synthesis,'');
      assert.equal(Object.hasOwn(state.vfs,'final_report.md'),false);
    }
  });

  await test('old valid drafts cannot substitute for writes from the current dispatch', async () => {
    const expectedFiles=['nim_overview.md','nim_use_cases.md','nim_vs_hosting.md'];
    const state={expectedFiles, writtenPaths:new Set(['placeholder.txt']),
      vfs:Object.fromEntries(expectedFiles.map(p=>[p,'Old valid draft.']))};
    state.vfs['placeholder.txt']='Current worker reported completion.';
    completedDispatch(state);
    let calls=0;
    await assert.rejects(run(deep.node('#cell-m3c-p3','synth'),state,{
      chatStream:async()=>{calls++;return response('Unexpected');},
    },deep.sandbox),error=>expectedFiles.every(p=>error.message.includes(p)));
    assert.equal(calls,0);
    assert(expectedFiles.every(p=>state.vfs[p]==='Old valid draft.'));
    assert.equal(Object.hasOwn(state.vfs,'final_report.md'),false);
  });

  const draftFlow='#cell-m3c-p3';
  const finalMessage=(content='Saved the requested draft.',finish='stop',extra={})=>({
    content,response_metadata:{finish_reason:finish},tool_calls:[],...extra});
  const planResponse=(parsed,finish='stop')=>({parsed,raw:finalMessage(JSON.stringify(parsed),finish,finish==='tool_calls'?{tool_calls:[{id:'plan-1',name:'plan',args:parsed}]}:{})});
  await test('file planner binds typed instructions to every expected path and retains raw finish evidence',async()=>{
    const files=['nim_overview.md','nim_use_cases.md','nim_vs_hosting.md'];
    const valid={subtasks:files.map(file=>({file,instruction:'Draft an unverified overview for '+file}))};
    async function plan(candidate,finish='stop') {
      const state={}; let receivedSchema,receivedOptions;
      state.llm={withStructuredOutput:(schema,options)=>{
        receivedSchema=schema; receivedOptions=options;
        return {invoke:async messages=>{
          for(const file of files) assert(messages.at(-1).content.includes(file));
          return planResponse(candidate,finish);
        }};
      }};
      const result=run(deep.node(draftFlow,'planner'),state);
      assert.equal(receivedOptions.includeRaw,true);
      assert.equal(receivedOptions.method,undefined,'allow the SDK to select the compatible structured-output method');
      assert.deepEqual(Array.from(receivedSchema.properties.subtasks.items.properties.file.enum),files);
      assert.equal(receivedSchema.properties.subtasks.minItems,files.length);
      assert.equal(receivedSchema.properties.subtasks.maxItems,files.length);
      return {state,result};
    }
    for(const candidate of [valid,{subtasks:files.map(file=>({file,instruction:'撰寫並儲存草稿'}))}]) {
      const {state,result}=await plan(candidate); await result;
      assert.equal(state.subtasks.length,files.length);
      assert.equal(state.subtasks[0].file,files[0]);
    }
    for(const candidate of [
      {subtasks:['.','.','.']},
      {subtasks:files.map(file=>({file,instruction:'...!?'}))},
      {subtasks:files.map(file=>({file,instruction:'123'}))},
      {subtasks:valid.subtasks.slice(1)},
      {subtasks:[valid.subtasks[0],valid.subtasks[0],valid.subtasks[2]]},
      {subtasks:valid.subtasks.map((task,i)=>i?task:{...task,file:'draft.txt'})},
      {subtasks:valid.subtasks.map((task,i)=>i?task:{...task,unexpected:true})},
      {subtasks:valid.subtasks,unexpected:true},null,
    ]) {
      const {state,result}=await plan(candidate);
      await assert.rejects(result,d(/cover every expected file/));
      assert.equal(state.subtasks.length,0,'invalid plans never reach workers');
      assert.equal(state.dispatch,null);
    }
    const completedToolPlan=await plan(valid,'tool_calls'); await completedToolPlan.result;
    assert.equal(completedToolPlan.state.subtasks.length,files.length);
    const {state,result}=await plan(valid,'length');
    await assert.rejects(result,d(/did not finish/));
    assert.equal(state.subtasks.length,0);
  });
  async function workerFixture(worker) {
    const state={deps:{tool:(invoke,spec)=>({...spec,invoke}),z:{object:()=>({}),string:()=>({})}}};
    await run(deep.node(draftFlow,'vfs'),state);
    state.goal='Draft NIM notes';
    state.expectedFiles=['nim_overview.md','nim_use_cases.md','nim_vs_hosting.md'];
    state.planInput={goal:state.goal,expectedFiles:[...state.expectedFiles]};
    state.subtasks=state.expectedFiles.map(file=>({file,instruction:'Draft '+file}));
    state.vfs['personal.md']='Keep this user draft.';
    let index=0, sharedWrite;
    state.deps.createReactAgent=options=>{
      if(sharedWrite) assert.equal(options.tools[0],sharedWrite,'workers share the same file tool');
      sharedWrite=options.tools[0];
      assert.equal(options.tools[1],state.readFile);
      assert.equal(options.tools[2],state.listFiles);
      const i=index++;
      return {invoke:async (request,config)=>{
        assert.match(request.messages[0].content,d(/without retrieval or external sources/));
        assert.match(request.messages[0].content,d(/100–150 words/));
        assert(request.messages[0].content.includes(t('Call write_file to save the draft to ')+state.expectedFiles[i]));
        return worker(state,options.tools[0],i,request,config);
      }};
    };
    return state;
  }
  async function saveAll(state,write) {
    for(const p of state.expectedFiles) await write.invoke({path:p,content:'Unverified draft for '+p});
  }
  async function blockedSynthesis(state) {
    let calls=0;
    await assert.rejects(run(deep.node(draftFlow,'synth'),state,{chatStream:async()=>{calls++;return response('Unexpected report');}},deep.sandbox),d(/Run all workers successfully/));
    assert.equal(calls,0);
    assert.equal(state.vfs['personal.md'],'Keep this user draft.');
    assert.equal(Object.hasOwn(state.vfs,'final_report.md'),false);
  }
  async function emptyReportRender(state) {
    let diagram;
    const result=await run(deep.node(draftFlow,'render'),state,{viz:{diagram:value=>{diagram=value;}}});
    assert.equal(result.final_report,'');
    assert.equal(Object.hasOwn(result.vfs_contents,'final_report.md'),false);
    assert.equal(result.vfs_contents['personal.md'],'Keep this user draft.');
    assert(diagram.nodes.find(n=>n.id==='synth').lines.includes(t('no current final report')));
  }
  await test('actual writes followed by worker failure cannot produce a completed report',async()=>{
    const outcomes=[
      async()=>{throw Error('External service failed');},
      async()=>({messages:[finalMessage('Partial answer','length')]}),
      async()=>({messages:[finalMessage('')]}),
      async()=>({messages:[finalMessage('Pending','stop',{tool_calls:[{name:'write_file'}]})]}),
      async()=>({messages:[finalMessage('Invalid','stop',{invalid_tool_calls:[{error:'bad JSON'}]})]}),
      async()=>({messages:[{content:'Tool execution failed',status:'error',tool_call_id:'w'},finalMessage('[Error: write failed]')]}),
    ];
    for(const outcome of outcomes){
      const state=await workerFixture(async(state,write)=>{await saveAll(state,write);return outcome();});
      await assert.rejects(run(deep.node(draftFlow,'dispatcher'),state),d(/failed|token limit|complete answer/, ['External service failed']));
      assert.equal(state.dispatch.complete,false);
      assert(state.expectedFiles.every(p=>state.vfs[p]?.trim()),'partial writes remain inspectable');
      await blockedSynthesis(state);
    }
  });
  await test('successful shared workers permit synthesis but planner-only rerun invalidates it',async()=>{
    const state=await workerFixture(async(state,write,i)=>{
      await write.invoke({path:state.expectedFiles[i],content:'Unverified saved draft '+i});
      return {messages:[finalMessage()]};
    });
    await run(deep.node(draftFlow,'dispatcher'),state);
    assert.equal(state.dispatch.complete,true);
    await run(deep.node(draftFlow,'synth'),state,{chatStream:async()=>response('Combined draft.')},deep.sandbox);
    assert.equal(state.vfs['final_report.md'],'Combined draft.');
    state.llm={withStructuredOutput:()=>({invoke:async()=>planResponse({subtasks:state.expectedFiles.map(file=>({file,instruction:'Draft new notes'}))})})};
    await run(deep.node(draftFlow,'planner'),state);
    assert.notEqual(state.goal,'Draft NIM notes');
    assert.equal(state.dispatch,null);
    await emptyReportRender(state);
    assert.equal(state.subResults.length,0);
    await blockedSynthesis(state);
    assert(state.expectedFiles.every(p=>state.vfs[p]?.trim()));
  });
  await test('dispatcher restart invalidates prior success and rejects stale writes',async()=>{
    let oldWrite;
    const state=await workerFixture(async(state,write)=>{oldWrite=write;await saveAll(state,write);return {messages:[finalMessage()]};});
    await run(deep.node(draftFlow,'dispatcher'),state);
    await run(deep.node(draftFlow,'synth'),state,{chatStream:async()=>response('Previous report')},deep.sandbox);
    state.deps.createReactAgent=()=>({invoke:async()=>{throw Error('New dispatcher failed');}});
    await assert.rejects(run(deep.node(draftFlow,'dispatcher'),state),/New dispatcher failed/);
    await emptyReportRender(state);
    await assert.rejects(oldWrite.invoke({path:'personal.md',content:'Stale overwrite'}),d(/no longer current/));
    await blockedSynthesis(state);
  });
  await test('expected paths changed after dispatch and rerun during synthesis cannot publish stale output',async()=>{
    const state=await workerFixture(async(state,write)=>{await saveAll(state,write);return {messages:[finalMessage()]};});
    await run(deep.node(draftFlow,'dispatcher'),state);
    const original=state.expectedFiles;
    state.expectedFiles=['different.md'];
    await blockedSynthesis(state);
    state.expectedFiles=original;
    await assert.rejects(run(deep.node(draftFlow,'synth'),state,{chatStream:async()=>{
      state.dispatch=null;
      return response('Stale combined draft');
    }},deep.sandbox),d(/changed during synthesis/));
    assert.equal(Object.hasOwn(state.vfs,'final_report.md'),false);
  });
  await test('render requires a synthesis receipt for the current goal and file paths',async()=>{
    const state=await workerFixture(async(state,write)=>{await saveAll(state,write);return {messages:[finalMessage()]};});
    await run(deep.node(draftFlow,'dispatcher'),state);
    await run(deep.node(draftFlow,'synth'),state,{chatStream:async()=>response('Current report')},deep.sandbox);
    const render=async()=>run(deep.node(draftFlow,'render'),state,{viz:{diagram:spec=>{
      assert.equal(spec.nodes.find(n=>n.id==='synth').lines[0],'4'+t(' files available'));
    }}});
    assert.equal((await render()).final_report,'Current report');
    state.goal='A different goal';
    assert.equal((await render()).final_report,'');
    state.goal='Draft NIM notes';
    state.expectedFiles=['another.md'];
    assert.equal((await render()).final_report,'');
    assert.equal(state.vfs['personal.md'],'Keep this user draft.');
    assert.equal(state.vfs['final_report.md'],'Current report','old file remains available for inspection');
  });

  await test('stopping a worker passes its signal and rejects late file writes',async()=>{
    const controller=new AbortController();
    const state=await workerFixture(async(state,write,index,request,config)=>{
      assert.equal(config.signal,controller.signal);
      controller.abort();
      await assert.rejects(write.invoke({path:state.expectedFiles[0],content:'late content'}),d(/changed|current|dispatch/));
      return {messages:[finalMessage()]};
    });
    await assert.rejects(run(deep.node(draftFlow,'dispatcher'),state,{signal:controller.signal}),{name:'AbortError'});
    assert.equal(state.dispatch.complete,false);
    assert(state.expectedFiles.every(file=>!Object.hasOwn(state.vfs,file)));
  });
  await test('RAG artifact invalidates cached vectors when the embedding route or model changes',async()=>{
    let widget,config={url:'https://embedding-a.example/v1',model:'custom-a'},passageRequests=0;
    const helpers={getEmbeddingConfig:async()=>config,
      fetch:async()=>({json:async()=>({model:'nvidia-prebuilt',docs:[],queries:[]})}),
      mountChatUI:(_id,value)=>{widget=value;},
      embed:async(input,options)=>{if(options.inputType==='passage')passageRequests++;return (Array.isArray(input)?input:[input]).map(()=>[1,0,0]);},
      cosineSim:(a,b)=>{assert.equal(a.length,b.length);return 1;},
      chatStream:async()=>response('Grounded answer')};
    await run(retrieval.cells['#rag-cell'].code,{},helpers);
    const ctx={model:'chat',view:{tool:noop,html:noop,activitySuccess:noop,token:noop}};
    await widget.respond('question',ctx);assert.equal(passageRequests,1);
    await widget.respond('another',ctx);assert.equal(passageRequests,1);
    config={...config,model:'custom-b'};
    await widget.respond('question',ctx);assert.equal(passageRequests,2);
    config={...config,url:'https://embedding-b.example/v1'};
    await widget.respond('question',ctx);assert.equal(passageRequests,3);
  });
  await test('all canvas indexes reject changed embedding routes and same-dimension models before ranking',async()=>{
    for(const change of [c=>({...c,model:'different-model'}),c=>({...c,url:'https://different.example/v1'})]) {
      for(const name of ['#cell-m3b-p2','#cell-m3b-p3',flow]) {
        let config={url:'https://embedding.example/v1',model:'fixture-embedding'},embeds=0;
        const helpers={...fixture,getEmbeddingConfig:async()=>config,embed:async input=>{
          embeds++;return (Array.isArray(input)?input:[input]).map(()=>[1,0]);
        }};
        const s={};
        if(name==='#cell-m3b-p2') {
          await run(retrieval.node(name,'corpus'),s,helpers);
          await run(retrieval.node(name,'index'),s,helpers);
          await run(retrieval.node(name,'query'),s,helpers);
        } else if(name==='#cell-m3b-p3') {
          for(const node of ['docs','split','index','query']) await run(retrieval.node(name,node),s,helpers);
        } else {
          await run(retrieval.node(name,'build_corpus'),s,helpers);
          await run(retrieval.node(name,'query'),s,helpers);
          await run(retrieval.node(name,'agent'),s,{...helpers,chatStream:async()=>response('','tool_calls',[call('r',s.query)])});
        }
        config=change(config);const before=embeds;
        await assert.rejects(run(retrieval.node(name,name==='#cell-m3b-p3'?'lookup':'retrieve'),s,helpers),d(/rebuild the index/));
        assert.equal(embeds,before,'a stale index must fail before querying another vector space');
      }
    }
  });
  await test('corpus changes during embedding cannot relabel old vectors as new text',async()=>{
    const s={corpus:['Original passage.']};
    await assert.rejects(run(retrieval.node('#cell-m3b-p2','index'),s,{embed:async()=>{
      s.corpus=['Changed passage.'];return [[1,0]];
    }}),d(/rebuild the index/));
    assert.equal(s.index,null);
  });
  await test('retrieval requires current decision and successful retrieval before answering',async()=>{
    const s={...state,query:'original'};
    await decide(s,response('','tool_calls',[call('r','original')]));
    await assert.rejects(run(retrieval.node(flow,'answer'),s,fixture),d(/Complete retrieval/));
    s.query='changed';let embeds=0;
    await assert.rejects(run(retrieval.node(flow,'retrieve'),s,{...fixture,embed:async()=>{embeds++;return [[1,0]];}}),d(/complete decision/));
    assert.equal(embeds,0);
    await decide(s,response('','tool_calls',[call('r','changed')]));
    const before=JSON.stringify(s.messages);
    await assert.rejects(run(retrieval.node(flow,'retrieve'),s,{...fixture,embed:async()=>{
      s.query='changed again';return [[1,0]];
    }}),d(/input changed/));
    assert.equal(JSON.stringify(s.messages),before,'do not append results from an obsolete input');
    assert.equal(s.retrievalQuery,null);
  });
  await test('GraphRAG stops on incomplete basic, map, or reduce output and retains the raw response',async()=>{
    for(const failedCall of [0,1,4]) {
      let calls=0,panels=0,raw=0;
      await assert.rejects(run(retrieval.cells['#cell-graphrag'].code,{}, {
        ...fixture,embed:async input=>(Array.isArray(input)?input:[input]).map(()=>[1,0]),
        log:Object.assign(noop,{details:()=>{raw++;},html:()=>{panels++;}}),
        chat:async()=>({choices:[{finish_reason:calls++===failedCall?'length':'stop',message:{content:'Partial or complete text'}}]}),
      }),d(/Generation did not return a complete answer/));
      assert.equal(calls,failedCall+1);assert.equal(raw,calls);assert.equal(panels,0);
    }
  });
  await test('live RAG reports incomplete synthesis and never caches vectors under a changed route',async()=>{
    let widget,config={url:'https://embedding.example/v1',model:'model-a'},passages=0,change=true;
    const initial=config;
    const helpers={getEmbeddingConfig:async()=>config,
      fetch:async()=>({json:async()=>({model:'other',docs:[],queries:[]})}),mountChatUI:(_id,value)=>{widget=value;},
      embed:async(input,options)=>{
        if(options.inputType==='passage') {passages++;if(change){config={...config,model:'model-b'};change=false;}}
        return (Array.isArray(input)?input:[input]).map(()=>[1,0]);
      },cosineSim:()=>1,chatStream:async()=>response('partial','length')};
    await run(retrieval.cells['#rag-cell'].code,{},helpers);
    const ctx={model:'chat',view:{tool:noop,html:noop,activitySuccess:noop,token:noop}};
    await assert.rejects(widget.respond('question',ctx),d(/Embedding configuration changed/));
    config=initial;
    await assert.rejects(widget.respond('question',ctx),d(/Generation did not return a complete answer/));
    assert.equal(passages,2,'the rejected batch was not cached under its old route');
  });
  await test('live router rejects incomplete or pending-tool specialist output',async()=>{
    for(const answer of [response('partial','length'),response(''),response('pending','stop',[call('unexpected','question')])]) {
      let widget;
      await run(routing.cells['#router-cell'].code,{}, {
        mountChatUI:(_id,value)=>{widget=value;},chat:async()=>({choices:[{finish_reason:'stop',message:{content:'billing'}}]}),
        chatStream:async()=>answer,
      });
      await assert.rejects(widget.respond('question',{model:'fixture',view:{tool:noop,token:noop,reasoning:noop,activitySuccess:noop}}),d(/No complete answer/));
    }
  });
  await test('ReWOO synthesis requires searches from the current goal and rejects changes during generation',async()=>{
    const s={goal:'Original goal'};
    const helpers={chatStream:async()=>response(JSON.stringify({topic:'Original topic',queries:['one','two','three']})),
      webSearch:async query=>({query,count:1}),formatSearchResults:r=>'Evidence for '+r.query,viz:{diagram:noop}};
    await run(planner,s,helpers,routing.sandbox);
    await run(routing.node('#cell-m2a-rewoo','executor'),s,helpers);
    let generations=0;
    const synth=()=>run(routing.node('#cell-m2a-rewoo','synth'),s,{...helpers,chatStream:async()=>{generations++;return response('A sourced brief.');}});
    assert.equal(await synth(),'A sourced brief.');
    s.goal='Changed goal';
    await assert.rejects(synth(),d(/Run searches/));assert.equal(generations,1);
    s.goal='Original goal';
    await assert.rejects(run(routing.node('#cell-m2a-rewoo','synth'),s,{...helpers,chatStream:async()=>{
      s.goal='Changed during generation';return response('Obsolete brief.');
    }}),d(/Run searches/));
    s.goal='Original goal';
    await assert.rejects(run(routing.node('#cell-m2a-rewoo','executor'),s,{...helpers,webSearch:async()=>{
      s.goal='Changed during search';return {query:'one',count:1};
    }}),d(/Run searches/));
    assert.equal(s.context,null);assert.equal(s.searchPlan,null);
  });
  console.log('Module 2 displayed-code contracts passed for ' + language.label + ': ' + checked);
  }
  if(failures.length) throw new AggregateError(failures, failures.length + ' displayed-code contracts failed');
})().catch(error=>{console.error(error);process.exitCode=1;});
