// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

const persistent = new Map();
const tab = new Map();
const storage = map => ({
  getItem: key => map.get(key) ?? null,
  setItem: (key, value) => map.set(key, String(value)),
  removeItem: key => map.delete(key),
});

globalThis.localStorage = storage(persistent);
globalThis.sessionStorage = storage(tab);
globalThis.location = new URL('https://cdn.dli.learn.nvidia.com/course-static/test/web/nemoclaw/03a-kickstart.html');

const terminalUrls = [];
const terminalCommands = [];
let failDirectTerminal = false;
let terminalResult = 'exit';
let terminalExitCode = 0;
let terminalFrames = null;
class FakeWebSocket {
  static OPEN = 1;
  constructor(url) {
    this.url = url;
    this.readyState = 0;
    terminalUrls.push(url);
    setTimeout(() => {
      if (failDirectTerminal &&
          new URL(url).hostname !== 'openclaw-cors-proxy.experiments.courses.nvidia.com') {
        this.onerror?.(new Error('direct route unavailable'));
        this.close();
        return;
      }
      this.readyState = FakeWebSocket.OPEN;
      this.onopen?.();
      const command = new URL(url).searchParams.get('cmd') || '';
      terminalCommands.push(command);
      const frames = terminalFrames
        ? terminalFrames(command)
        : [{ type: 'data', data: command.endsWith('http://127.0.0.1/api/agent')
          ? JSON.stringify({ agent: { dashboardUrl: '/#token=test-gateway-token' } })
          : JSON.stringify({ status: 'ok' }) }];
      for (const frame of frames) this.onmessage?.({ data: JSON.stringify(frame) });
      if (terminalResult === 'exit') {
        this.onmessage?.({ data: JSON.stringify({ type: 'exit', code: terminalExitCode }) });
      }
      if (terminalResult !== 'pending') this.close();
    }, 0);
  }
  send() {}
  close() {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.();
  }
}
globalThis.WebSocket = FakeWebSocket;

const connection = await import('../../web/nemoclaw/scripts/_connection.js');
const openshell = await import('../../web/nemoclaw/scripts/_openshell.js');
const shared = await import('../../web/nemoclaw/scripts/_shared.js');
const launchable = 'https://nemoclaw-test.apps.run.brev.nvidia.com';

test('Pomerium loopback probe is registered for learner cells', () => {
  assert.equal(shared.HELPER_FNS.openclawLoopbackProbe, openshell.openclawLoopbackProbe);
});

test('Pomerium keeps a supplied session tab-scoped and uses the provider-bound relay', async () => {
  const saved = connection.setOpenClawConnection({
    rawUrl: launchable,
    token: 'tab-token',
    accessProvider: 'pomerium',
    accessSession: 'manual-pomerium-session',
  });

  assert.equal(saved.accessSession, 'manual-pomerium-session');
  const restored = connection.getOpenClawConnection();
  assert.equal(restored.accessSession, 'manual-pomerium-session');
  assert.equal(
    restored.effectiveUrl,
    'https://openclaw-cors-proxy.experiments.courses.nvidia.com/https/nemoclaw-test.apps.run.brev.nvidia.com',
  );
  assert.equal(persistent.get(connection.OPENCLAW_TOKEN_KEY), undefined);
  assert.equal(persistent.get(connection.OPENCLAW_ACCESS_SESSION_KEY), undefined);
  assert.equal(tab.get(connection.OPENCLAW_TOKEN_KEY), 'tab-token');
  assert.equal(tab.get(connection.OPENCLAW_ACCESS_SESSION_KEY), 'manual-pomerium-session');

  const gateway = shared.openclawGatewayWsUrl(
    launchable,
    saved.accessSession,
    null,
    null,
    'pomerium',
  );
  assert.equal(
    gateway.url,
    'wss://openclaw-cors-proxy.experiments.courses.nvidia.com/https/nemoclaw-test.apps.run.brev.nvidia.com/cli/gateway?access_provider=pomerium&access_session=manual-pomerium-session',
  );
  assert.equal(gateway.viaProxy, true);
  assert.doesNotMatch(gateway.displayUrl, /manual-pomerium-session/);

  terminalUrls.length = 0;
  failDirectTerminal = true;
  let metadata;
  try {
    metadata = await openshell.openclawLoopbackProbe('/api/agent', { baseUrl: launchable });
  } finally {
    failDirectTerminal = false;
  }
  assert.equal(metadata.transport, 'approved-provider-relay-terminal-loopback');
  assert.equal(metadata.json.agent.dashboardUrl, '/#token=test-gateway-token');
  assert.equal(terminalUrls.length, 2);
  const terminal = new URL(terminalUrls[0]);
  assert.equal(terminal.origin, 'wss://nemoclaw-test.apps.run.brev.nvidia.com');
  assert.equal(terminal.pathname, '/ws/terminal');
  assert.equal(terminal.searchParams.get('cmd'), 'curl -fsS --max-time 10 http://127.0.0.1/api/agent');
  assert.equal(terminal.searchParams.get('access_provider'), null);
  assert.equal(terminal.searchParams.get('access_session'), null);
  const fallback = new URL(terminalUrls[1]);
  assert.equal(fallback.origin, 'wss://openclaw-cors-proxy.experiments.courses.nvidia.com');
  assert.equal(fallback.searchParams.get('cmd'), 'curl -fsS --max-time 10 http://127.0.0.1/api/agent');
  assert.equal(fallback.searchParams.get('access_provider'), 'pomerium');
  assert.equal(fallback.searchParams.get('access_session'), 'manual-pomerium-session');

  await assert.rejects(
    openshell.openclawLoopbackProbe('/arbitrary', { baseUrl: launchable }),
    /Unsupported loopback bootstrap path/,
  );
  assert.equal(terminalUrls.length, 2, 'unsupported path opened a terminal socket');
});

test('Pomerium remains direct when no manual access session is supplied', () => {
  connection.setOpenClawConnection({
    rawUrl: launchable,
    token: 'tab-token',
    accessProvider: 'pomerium',
    accessSession: '',
  });
  const gateway = connection.openclawWebSocketUrl(
    launchable,
    '/cli/gateway',
    '',
    undefined,
    'pomerium',
  );
  assert.equal(gateway.url, 'wss://nemoclaw-test.apps.run.brev.nvidia.com/cli/gateway');
  assert.equal(gateway.viaProxy, false);
});

test('Cloudflare terminal retries through relay only after direct failure', async () => {
  const launchable = 'https://nemoclaw-test.brevlab.com';
  connection.setOpenClawConnection({
    rawUrl: launchable,
    token: 'tab-token',
    accessProvider: 'cloudflare',
    accessSession: 'cloudflare-session',
  });
  terminalUrls.length = 0;
  failDirectTerminal = true;
  try {
    await openshell.terminal('printf ready', {
      baseUrl: launchable,
      openMs: 20,
      idleMs: 20,
      totalMs: 2000,
    });
  } finally {
    failDirectTerminal = false;
  }

  assert.equal(terminalUrls.length, 2);
  assert.equal(new URL(terminalUrls[0]).origin, 'wss://nemoclaw-test.brevlab.com');
  const fallback = new URL(terminalUrls[1]);
  assert.equal(fallback.origin, 'wss://openclaw-cors-proxy.experiments.courses.nvidia.com');
  assert.equal(fallback.searchParams.get('cf_access_jwt'), 'cloudflare-session');
});

test('terminal distinguishes command exit, disconnected output, and idle output', async () => {
  connection.setOpenClawConnection({ rawUrl:launchable, accessProvider:'pomerium', accessSession:'' });
  try {
    terminalExitCode = 23;
    const failed = await openshell.terminal('false', { baseUrl:launchable, idleMs:20 });
    assert.equal(failed.exitCode, 23);
    assert.equal(failed.completion, 'exit');

    terminalResult = 'disconnect';
    const disconnected = await openshell.terminal('printf partial', { baseUrl:launchable, idleMs:20 });
    assert.equal(disconnected.exitCode, null);
    assert.equal(disconnected.completion, 'disconnect');

    terminalResult = 'pending';
    const idle = await openshell.terminal('bash', { baseUrl:launchable, idleMs:20 });
    assert.equal(idle.exitCode, null);
    assert.equal(idle.completion, 'idle');
  } finally {
    terminalResult = 'exit';
    terminalExitCode = 0;
  }
});

test('sandboxExec requests pipe transport and retains separate command streams and completion', async () => {
  connection.setOpenClawConnection({rawUrl:launchable, accessProvider:'pomerium', accessSession:''});
  terminalFrames = () => {
    assert.equal(new URL(terminalUrls.at(-1)).searchParams.get('stdio'), 'pipe');
    return [
      {type:'data', stream:'stdout', data:'code=200'},
      {type:'data', stream:'stderr', data:'Connection to sandbox closed.\n'},
    ];
  };
  try {
    for (const mode of ['exit', 'disconnect', 'pending']) {
      terminalResult = mode;
      const result = await openshell.sandboxExec('printf code=200', {agent:'test-sandbox', idleMs:20});
      assert.equal(result.stdout, 'code=200');
      assert.equal(result.stderr, 'Connection to sandbox closed.');
      assert.equal(result.exitCode, mode === 'exit' ? 0 : null);
      assert.equal(result.completion, mode === 'pending' ? 'idle' : mode);
    }
  } finally { terminalFrames = null; terminalResult = 'exit'; }
});

test('policyGet parses bounded stdout while preserving SSH diagnostics and malformed YAML', async () => {
  connection.setOpenClawConnection({ rawUrl:launchable, accessProvider:'pomerium', accessSession:'' });
  terminalFrames = command => {
    assert.equal(new URL(terminalUrls.at(-1)).searchParams.get('stdio'), 'pipe');
    const stdoutMarker = command.match(/__DLI_OPENSHELL_POLICY_STDOUT_END_[a-z0-9]+__/)?.[0];
    const stderrMarker = command.match(/__DLI_OPENSHELL_POLICY_STDERR_END_[a-z0-9]+__/)?.[0];
    assert(stdoutMarker && stderrMarker, 'policy transport command has stream markers');
    return [
      { type: 'data', stream: 'stdout', data: 'active policy\n---\nversion: 1\nnetwork_policies: {}\n' + stdoutMarker + '\n' + stderrMarker + '\n' },
      { type: 'data', stream: 'stderr', data: 'Connection to 172.18.0.1 closed.\n' },
    ];
  };
  try {
    const policy = await openshell.policyGet('learner-agent', { idleMs:20 });
    assert.equal(policy.command, 'openshell policy get learner-agent --full');
    assert.equal(policy.raw, 'active policy\n---\nversion: 1\nnetwork_policies: {}');
    assert.equal(policy.stderr, 'Connection to 172.18.0.1 closed.');
    assert.match(policy.transcript, /Connection to 172\.18\.0\.1 closed\./);
    assert.deepEqual(policy.policy, { version: 1, network_policies: {} });

    terminalFrames = command => {
      const stdoutMarker = command.match(/__DLI_OPENSHELL_POLICY_STDOUT_END_[a-z0-9]+__/)?.[0];
      const stderrMarker = command.match(/__DLI_OPENSHELL_POLICY_STDERR_END_[a-z0-9]+__/)?.[0];
      return [{ type: 'data', data: 'active policy\n---\nversion: [\n' + stdoutMarker + '\n' + stderrMarker + '\n' }];
    };
    const malformed = await openshell.policyGet('learner-agent', { idleMs:20 });
    assert.equal(malformed.policy, null);
    assert.notEqual(malformed.parseError, '');

    terminalFrames = command => {
      const stderrMarker = command.match(/__DLI_OPENSHELL_POLICY_STDERR_END_[a-z0-9]+__/)?.[0];
      return [{ type: 'data', data: 'active policy\n---\nversion: 1\n' + stderrMarker + '\n' }];
    };
    const missingStdoutBoundary = await openshell.policyGet('learner-agent', { idleMs:20 });
    assert.equal(missingStdoutBoundary.policy, null);
    assert.match(missingStdoutBoundary.parseError, /stdout boundary/);

    terminalFrames = command => {
      const stdoutMarker = command.match(/__DLI_OPENSHELL_POLICY_STDOUT_END_[a-z0-9]+__/)?.[0];
      return [{ type: 'data', data: 'active policy\n---\nversion: 1\n' + stdoutMarker + '\n' }];
    };
    const missingStderrBoundary = await openshell.policyGet('learner-agent', { idleMs:20 });
    assert.equal(missingStderrBoundary.policy, null);
    assert.match(missingStderrBoundary.parseError, /stderr boundary/);

    terminalExitCode = 23;
    await assert.rejects(
      openshell.policyGet('learner-agent', { idleMs:20 }),
      /Policy command did not complete successfully/,
    );
  } finally {
    terminalFrames = null;
    terminalExitCode = 0;
  }
});

test('policyGet keeps legacy PTY diagnostics outside YAML without stripping similar output', async () => {
  connection.setOpenClawConnection({ rawUrl:launchable, accessProvider:'pomerium', accessSession:'' });
  terminalFrames = command => {
    const stdoutMarker = command.match(/__DLI_OPENSHELL_POLICY_STDOUT_END_[a-z0-9]+__/)?.[0];
    const stderrMarker = command.match(/__DLI_OPENSHELL_POLICY_STDERR_END_[a-z0-9]+__/)?.[0];
    return [{ type: 'data', data: 'active policy\n---\nmessage: "Connection to 172.18.0.1 closed."\n'
      + stdoutMarker + '\noperator warning\n' + stderrMarker + '\nConnection to 172.18.0.1 closed.\n' }];
  };
  try {
    const policy = await openshell.policyGet('learner-agent', { idleMs:20 });
    assert.equal(policy.policy.message, 'Connection to 172.18.0.1 closed.');
    assert.equal(policy.stderr, 'operator warning');
    assert.match(policy.transcript, /Connection to 172\.18\.0\.1 closed\.$/);
  } finally {
    terminalFrames = null;
  }
});

test('policyGet shell wrapper preserves streams and exit status through a real outer shell', async () => {
  connection.setOpenClawConnection({ rawUrl:launchable, accessProvider:'pomerium', accessSession:'' });
  terminalCommands.length = 0;
  terminalFrames = command => {
    const stdoutMarker = command.match(/__DLI_OPENSHELL_POLICY_STDOUT_END_[a-z0-9]+__/)?.[0];
    const stderrMarker = command.match(/__DLI_OPENSHELL_POLICY_STDERR_END_[a-z0-9]+__/)?.[0];
    return [{ type: 'data', data: 'active policy\n---\nversion: 1\n' + stdoutMarker + '\n' + stderrMarker + '\n' }];
  };
  const fakeBin = fs.mkdtempSync(path.join(os.tmpdir(), 'openshell-policy-'));
  const fakeOpenShell = path.join(fakeBin, 'openshell');
  fs.writeFileSync(fakeOpenShell, [
    '#!/bin/sh',
    "printf '%s\\n' 'active policy'",
    "printf '%s\\n' '---'",
    "printf '%s\\n' 'message: \"$HOME $(whoami) `uname`\"'",
    "printf '%s\\n' 'operator warning: $tmp $(id) `date`' >&2",
    'exit 23',
  ].join('\n') + '\n', { mode: 0o755 });
  try {
    await openshell.policyGet('learner-agent', { idleMs:20 });
    const transportCommand = terminalCommands.at(-1);
    assert.match(transportCommand, /^sh -c '/);
    const result = await execFileAsync('sh', ['-c', transportCommand], {
      env: { ...process.env, PATH: fakeBin + path.delimiter + process.env.PATH },
    });
    assert.fail('expected policy command failure, got ' + result.stdout);
  } catch (error) {
    if (error?.code !== 23) throw error;
    assert.match(error.stdout, /message: "\$HOME \$\(whoami\) `uname`"/);
    assert.match(error.stdout, /operator warning: \$tmp \$\(id\) `date`/);
    assert.equal(error.stderr, '');
  } finally {
    terminalFrames = null;
    fs.rmSync(fakeBin, { recursive: true, force: true });
  }
});

test('terminal retains genuine output that resembles an SSH close diagnostic', async () => {
  connection.setOpenClawConnection({ rawUrl:launchable, accessProvider:'pomerium', accessSession:'' });
  terminalFrames = () => [{ type: 'data', data: 'Connection to 172.18.0.1 closed.\n' }];
  try {
    const result = await openshell.terminal('printf diagnostic', { baseUrl:launchable, idleMs:20 });
    assert.equal(result.output, 'Connection to 172.18.0.1 closed.');
    assert.equal(result.stdout, 'Connection to 172.18.0.1 closed.');
    assert.equal(result.stderr, '');
  } finally {
    terminalFrames = null;
  }
});

test('terminal Stop rejects and prevents an already stopped socket from opening', async () => {
  connection.setOpenClawConnection({ rawUrl:launchable, accessProvider:'pomerium', accessSession:'' });
  terminalResult = 'pending';
  try {
    const controller = new AbortController();
    const pending = openshell.terminal('bash', { baseUrl:launchable, signal:controller.signal });
    setTimeout(() => controller.abort(), 10);
    await assert.rejects(pending, { name:'AbortError' });
    const count = terminalUrls.length;
    await assert.rejects(
      openshell.terminal('bash', { baseUrl:launchable, signal:controller.signal }),
      { name:'AbortError' },
    );
    assert.equal(terminalUrls.length, count);
  } finally {
    terminalResult = 'exit';
  }
});
