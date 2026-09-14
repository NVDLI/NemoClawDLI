// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// External gateway and sandbox responses only. Course modules, cells, clocks,
// cancellation, protocol handling and UI event handlers remain production code.
export function courseServiceFixture() {
  const files = new Map(), memories = new Map(), jobs = new Map();
  let sequence = 0;
  const scheduled = [], scheduledRuns = [], terminalReads = [];
  const scheduler = {write:true};
  return {
    files, scheduled, scheduledRuns, terminalReads, scheduler,
    rpc(method, params) {
      if (method === 'connect') return {server:{version:'fixture'},auth:{scopes:['operator.read','operator.write']}};
      if (method === 'chat.send') return {runId:'fixture-run-' + ++sequence};
      if (['sessions.messages.subscribe','chat.abort'].includes(method)) return {};
      if (['sessions.reset','sessions.delete'].includes(method)) { memories.delete(params.key); return {}; }
      if (method === 'models.list') return {models:[{id:'fixture-model',name:'Fixture model'}]};
      if (method === 'environments.list') return {environments:[{id:'fixture-sandbox',status:'running'}]};
      if (method === 'config.get') return {parsed:{tools:{toolSearch:false}},hash:'fixture-config'};
      if (method === 'exec.approval.list') return [];
      if (method === 'sessions.list') return {sessions:[]};
      if (method === 'logs.tail') return {lines:['Fixture gateway ready.']};
      if (method === 'cron.add') {
        const id = 'fixture-job-' + ++sequence;
        jobs.set(id,{id,...params}); scheduled.push({id,...params}); return {id};
      }
      if (method === 'cron.runs') {
        const job = jobs.get(params.id);
        if (!job) throw new Error('Unknown scheduled fixture job');
        const write = job.payload.message.match(/Write exactly (\S+) to (\/sandbox\/[^ ]+)\./);
        if (!write) throw new Error('Unknown scheduled fixture payload');
        if (scheduler.write) files.set(write[2],write[1] + '\n');
        scheduledRuns.push({id:params.id,status:'ok',wrote:scheduler.write});
        return {entries:[{status:'ok',runId:'fixture-scheduled-run'}]};
      }
      if (method === 'cron.remove') { jobs.delete(params.id); return {ok:true}; }
      if (method === 'cron.list') return {jobs:[...jobs.values()]};
      throw new Error(`Unimplemented external gateway fixture: ${method}`);
    },
    answer({sessionKey,message}) {
      const planted = message.match(/Remember this only in our conversation: ([^.]+)\./);
      if (planted) { memories.set(sessionKey,planted[1]); return planted[1]; }
      if (message.includes('What code did I give you earlier?')) return memories.get(sessionKey) || 'unknown';
      if (message.startsWith('Append this preference to MEMORY.md')) {
        const reference = message.match(/REF-[0-9a-f-]+/)?.[0];
        const label = message.match(/course-review-[0-9a-f-]+/)?.[0];
        if (!reference || !label) throw new Error('Memory fixture requires the supplied label and reference');
        files.set('/sandbox/.openclaw/workspace/MEMORY.md',label + ' ' + reference);
        return reference;
      }
      if (message.startsWith('Read MEMORY.md')) return files.get('/sandbox/.openclaw/workspace/MEMORY.md') || 'No saved memory.';
      const skill = message.match(/Read (\/sandbox\/[^ ]+)\/SKILL\.md/);
      if (skill) return files.get(skill[1] + '/runbook.md') || 'Runbook unavailable.';
      if (message.includes('HEALTHCHECK_OK')) return 'HEALTHCHECK_OK';
      return 'Gateway reply received.';
    },
    terminal(command) {
      const exec = command.match(/^openshell sandbox exec -n [\w.-]+ -- ([\s\S]+)$/);
      const shell = exec ? exec[1] : command;
      if (shell === "printf '__NEMOCLAW_CONNECTION_READY__\\n'") return {code:0,data:'__NEMOCLAW_CONNECTION_READY__\n'};
      const read = shell.match(/base64 < '([^']+)'/);
      if (read) {
        terminalReads.push(read[1]);
        if (!files.has(read[1])) return {code:1,data:'fixture file missing'};
        return {code:0,data:'\x1e' + Buffer.from(files.get(read[1])).toString('base64') + '\x1f'};
      }
      const writes = [...shell.matchAll(/printf '%s' '([^']+)' \| base64 -d > '([^']+)'/g)];
      if (writes.length) {
        writes.forEach(write => files.set(write[2],Buffer.from(write[1],'base64').toString()));
        return {code:0,data:''};
      }
      if (/^openshell sandbox connect [\w.-]+$/.test(shell)) return {interactive:true,data:'Fixture operator terminal ready.\n'};
      throw new Error(`Unimplemented external terminal fixture: ${shell}`);
    },
  };
}
