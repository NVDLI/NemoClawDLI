/* Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0 */
const fs=require('node:fs'), path=require('node:path'), vm=require('node:vm'), assert=require('node:assert/strict');
const root=process.env.COURSE_SOURCE_ROOT; assert(root);
const {discoverCourses,courseLanguage}=require('./course_exercise_fixture.cjs');
const noop=()=>{};
function load(name,course) {
  const html=fs.readFileSync(path.join(course,name),'utf8'),flows={},cells={};
  const sandbox={console,location:{href:'http://course/'+name},document:{getElementById:()=>({})},
    buildNav:noop,updateKeyPill:noop,mountJourneyMap:noop,hljs:{highlightAll:noop},
    mountCanvasFlow:(id,flow)=>flows[id]=flow,mountRunCell:(id,cell)=>cells[id]=cell};
  sandbox.window=sandbox;vm.createContext(sandbox);
  for(const script of html.matchAll(/<script type="module">([\s\S]*?)<\/script>/g))
    vm.runInContext(script[1].replace(/^\s*import\s+.*?;\s*$/gm,''),sandbox);
  const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
  for(const c of [...Object.values(cells),...Object.values(flows).flatMap(f=>f.nodes)])new AsyncFunction(c.code);
  return {html,flows,cells,sandbox};
}
const log=Object.assign(noop,{details:noop,html:noop,kv:noop,h:noop});
async function run(page,code,state,helpers={}) {
  Object.assign(page.sandbox,{state,helpers:{log,getConfig:async()=>({model:'fixture'}),isDefaultModelApiBaseUrl:()=>false,...helpers}});
  return vm.runInContext('(async()=>{'+code+'})()',page.sandbox);
}
const response=(content,tool_calls=[],finish_reason='stop')=>({model:'fixture',content,tool_calls,finish_reason});
const clock=(name='get_current_time',args='{}')=>({id:'clock',type:'function',function:{name,arguments:args}});
(async()=>{
 for(const course of discoverCourses(root).roots) {
 const language=courseLanguage(root,course,['01b-react.html','01c-tools.html']);
 const d=language.match;
 const react=load('01b-react.html',course),tools=load('01c-tools.html',course);
 const loop=react.flows['#cell-m2c-p3'].nodes.find(n=>n.id==='loop').code;
 let executions=0,n=0;
 const state={systemPrompt:'test',userPrompt:'clock',TOOLS:[],execTool:()=>{executions++;return '2026-09-12 00:00:00 UTC'}};
 const result=await run(react,loop,state,{chatStream:async()=>++n===1?response('',[clock()],'tool_calls'):response('2026-09-12 00:00:00 UTC')});
 assert.equal(executions,1);assert.equal(result.clock_read,true);assert.equal(result.steps_taken,2);
 const unsupported=await run(react,loop,state,{chatStream:async()=>response('an unsupported date')});
 assert.equal(unsupported.clock_read,false);assert.equal(executions,1);
 for(const bad of [response('',[],'length'),response(''),response('',[clock('other')],'tool_calls'),response('',[clock('get_current_time','{')],'tool_calls')])
  await assert.rejects(run(react,loop,state,{chatStream:async()=>bad}));
 for (const requests of [[clock(),{...clock('other'),id:'other'}], [clock(),clock()], [{id:'broken',type:'function'}]]) {
   const before = executions;
   await assert.rejects(run(react,loop,state,{chatStream:async()=>response('',requests,'tool_calls')}));
   assert.equal(executions,before,'validate the whole batch before any tool executes');
 }
 await assert.rejects(run(react,loop,state,{chatStream:async()=>response('',[clock()],'tool_calls')}),d(/Step cap/));
 const search=tools.flows['#cell-m2b-p4'].nodes.find(n=>n.id==='search').code;
 let calls=0;tools.sandbox.glossaryMCP.request=async()=>{calls++;return {content:[{text:'source'}],structuredContent:{count:1,source:'fixture'}}};
 const s={s1:response('direct'),messages:[]};await run(tools,search,s);assert.equal(s.skipped,true);
 s.s1=response('',[{id:'search',type:'function',function:{name:'glossary_search',arguments:'{"query":"GPU"}'}}],'tool_calls');
 await run(tools,search,s);assert.equal(s.skipped,false);assert.equal(calls,1);assert.equal(s.messages.filter(m=>m.role==='tool').length,1);
 s.s1.tool_calls.push({...s.s1.tool_calls[0],id:'second'});
 await assert.rejects(run(tools,search,s),d(/expects one/));assert.equal(calls,1);
 const finalCode=tools.flows['#cell-m2b-p4'].nodes.find(n=>n.id==='llm2').code;
 for(const finish of ['length',null]) {
   s.s1.tool_calls.pop();s.s1.finish_reason=finish;
   await assert.rejects(run(tools,search,s),d(/Incomplete model response/));assert.equal(calls,1);
   await assert.rejects(run(tools,finalCode,{skipped:false,messages:[]},{chatStream:async()=>response('partial answer',[],finish)}),d(/complete final answer/));
 }
 for (const [flow,name,args] of [['#cell-m2b-p5','query_customer_db',{question:'What plan is listed?'}],['#cell-m2b-p6','lookup',{query:'GPU'}]]) {
   const actualFlow=tools.flows[flow];
   assert(actualFlow,'native dispatch flow must exist');
   const dispatch=actualFlow.nodes.find(n=>n.id==='dispatch').code;
   const request=id=>({id,type:'function',function:{name,arguments:JSON.stringify(args)}});
   let executed=0;
   const base={mainMessages:[],messages:[],tools:[{type:'function',function:{name,parameters:{required:['query'],properties:{query:{type:'string'}}}}}],
     queryCustomerDB:async()=>{executed++;return 'Listed plan: pro';},mcpServer:{request:async()=>{executed++;return {content:[{text:'A GPU result'}]};}}};
   const helpers={chatStream:async()=>response('Final answer')};
   const good={...base,s1:response('',[request('one'),request('two')],'tool_calls')};
   assert.equal(await run(tools,dispatch,good,helpers),'Final answer');
   assert.equal(executed,2);
   for(const calls of [[request('one'),{...request('bad'),function:{name:'unknown',arguments:'{}'}}],
     [request('same'),request('same')],[request('one'),{...request('bad'),function:{name,arguments:'{'}}]]) {
     const candidate={...base,mainMessages:[],messages:[],s1:response('',calls,'tool_calls')};
     const before=executed;
     await assert.rejects(run(tools,dispatch,candidate,helpers));
     assert.equal(executed,before,'a malformed later request cannot execute an earlier valid one');
     assert.equal(candidate.messages.length+candidate.mainMessages.length,0);
   }
   const before=executed;
   await assert.rejects(run(tools,dispatch,{...base,s1:response('partial',[request('one')],'length')},helpers));
   assert.equal(executed,before);
   const stopped=new AbortController();stopped.abort();
   await assert.rejects(run(tools,dispatch,{...base,s1:response('',[request('one')],'tool_calls')},{...helpers,signal:stopped.signal}),{name:'AbortError'});
   assert.equal(executed,before,'Stop prevents tool execution at the dispatch boundary');
   await assert.rejects(run(tools,dispatch,{...base,s1:response('',[request('one')],'tool_calls')},
     {chatStream:async()=>response('I also need another tool',[request('pending')],'stop')}),d(/complete final answer/));
 }
 console.log(JSON.stringify({result:'PASS',locale:language.label,checks:['all displayed code compiles','clock execution evidence','unsupported answer identified','invalid and truncated responses','step cap fails','search rerun clears stale state','multiple calls rejected before search','customer and discovered-tool batches validate before execution','Stop prevents dispatch']}));
 }
})().catch(error=>{console.error(error);process.exitCode=1});
