#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import fs from 'node:fs';

const PATHS = {
  helper: 'web/nemoclaw/scripts/_openclaw.js',
  runtimeText: 'web/nemoclaw/scripts/_runtime_text.js',
  connection: 'web/nemoclaw/scripts/_connection.js',
  openshell: 'web/nemoclaw/scripts/_openshell.js',
  chat: 'web/nemoclaw/scripts/_chat.js',
  shared: 'web/nemoclaw/scripts/_shared.js',
  cliRuntime: 'web/nemoclaw/scripts/_openclaw_cli.js',
  runtime: 'scripts/runtime/test_page_runtime.js',
  lab: 'scripts/runtime/browser_runtime_test.sh',
  en: 'web/nemoclaw/03a-kickstart.html',
  pt: 'i18n/pt/web/nemoclaw/03a-kickstart.html',
  es: 'i18n/es/web/nemoclaw/03a-kickstart.html',
  en3b: 'web/nemoclaw/03b-openclaw.html',
  pt3b: 'i18n/pt/web/nemoclaw/03b-openclaw.html',
  es3b: 'i18n/es/web/nemoclaw/03b-openclaw.html',
  en3c: 'web/nemoclaw/03c-always-on.html',
  pt3c: 'i18n/pt/web/nemoclaw/03c-always-on.html',
  es3c: 'i18n/es/web/nemoclaw/03c-always-on.html',
  en4b: 'web/nemoclaw/04b-modern-clis.html',
  pt4b: 'i18n/pt/web/nemoclaw/04b-modern-clis.html',
  es4b: 'i18n/es/web/nemoclaw/04b-modern-clis.html',
};

function readAll(overrides = {}) {
  return Object.fromEntries(Object.entries(PATHS).map(([key, file]) => [
    key, Object.hasOwn(overrides, key) ? overrides[key] : fs.readFileSync(file, 'utf8'),
  ]));
}

function functionSource(source, declaration) {
  const start = source.indexOf(declaration);
  if (start < 0) return null;
  const brace = source.indexOf('{', start);
  if (brace < 0) return null;
  let depth = 0;
  for (let i = brace; i < source.length; i++) {
    if (source[i] === '{') depth++;
    if (source[i] === '}' && --depth === 0) return source.slice(start, i + 1);
  }
  return null;
}

function compile(source, declaration) {
  const found = functionSource(source, declaration);
  if (!found) return null;
  return Function(`return (${found.replace(/^export\s+/, '')})`)();
}

function parserFindings(label, parser) {
  if (!parser) return [`${label}: token parser is missing`];
  const urlSafe = 'AbCd_ef-0123456789.uvwxyz~token';
  const cases = [
    ['fragment', `/#token=${urlSafe}`, urlSafe],
    ['query', `/?token=${urlSafe}`, urlSafe],
    ['encoded', '/#token=abc%2D_DEF%2E123', 'abc-_DEF.123'],
    ['absent', '/dashboard', null],
  ];
  const out = [];
  for (const [name, value, expected] of cases) {
    const actual = parser(value) || null;
    if (actual !== expected) out.push(`${label}: ${name} token parsed as ${JSON.stringify(actual)}`);
  }
  return out;
}

function audit(overrides = {}) {
  const files = readAll(overrides);
  const findings = [];

  const metadataParser = compile(files.helper, 'export function gatewayTokenFromAgentMetadata');
  findings.push(...parserFindings('course helper', raw => metadataParser?.({ agent: { dashboardUrl: raw } })));

  const runtimeParser = compile(files.runtime, 'function gatewayTokenFromDashboardUrl');
  findings.push(...parserFindings('browser harness', runtimeParser));

  for (const key of ['en', 'pt', 'es']) {
    const source = files[key];
    if (!source.includes('gatewayTokenFromAgentMetadata')) {
      findings.push(`${key}: shared gateway-token parser is not imported`);
    }
    if (!source.includes('autofillToken: gatewayTokenFromAgentMetadata')) {
      findings.push(`${key}: OpenClaw probe does not use the shared gateway-token parser`);
    }
    if (/token=\(\[a-f0-9\]/i.test(source)) {
      findings.push(`${key}: hex-only gateway-token parser returned`);
    }
    if (!source.includes('proxyControls: true') || source.includes('proxyBase: "https://openclaw-cors-proxy.')) {
      findings.push(`${key}: OpenClaw probe does not use shared configurable relay controls`);
    }
  }

  if (!files.connection.includes('DEFAULT_OPENCLAW_PROXY_BASE')
      || !files.connection.includes('OPENCLAW_PROXY_ENABLED_KEY')
      || !files.connection.includes('migrateOpenClawConnectionStorage')) {
    findings.push('shared OpenClaw connection module lacks default, toggle, or migration contract');
  }
  if (!files.openshell.includes('openclawWebSocketUrl(rawUrl, "/ws/terminal?cmd="')) {
    findings.push('terminal WebSocket bypasses shared OpenClaw routing');
  }
  if (!files.openshell.includes('[direct.url, routed.url]')
      || !files.openshell.includes('{ enabled: false, base: "" }')) {
    findings.push('terminal WebSocket lacks authenticated direct-first routing with relay fallback');
  }
  if (!files.runtimeText.includes('/proc\\/self\\/oom_score_adj')
      || !files.runtimeText.includes('filterOpenClawRuntimeNoise')
      || !files.runtimeText.includes('export function filterOpenClawRuntimeValue(')
      || !files.runtimeText.includes('openclawMessageText')
      || !files.runtimeText.includes('openclawResultText')) {
    findings.push('shared OpenClaw runtime-text filter or parser is missing');
  }
  if (!files.helper.includes('deliverFull(openclawMessageText(pl.message)); done(false);')
      || !files.helper.includes('endGrace = setTimeout(() => done(false), finalGraceMs)')
      || !files.helper.includes('const resText = openclawResultText;')) {
    findings.push('OpenClaw chat can lose chat.final text or expose unfiltered tool output');
  }
  if (!files.helper.includes('export async function refreshOpenClawGatewayToken(')
      || !files.helper.includes('const refreshed = await refreshOpenClawGatewayToken({ signal });')
      || !files.helper.includes('const refreshedGateway = await helpers.refreshOpenClawGatewayToken({ signal: helpers.signal });')) {
    findings.push('gateway entry points do not bootstrap the current token from /api/agent before connecting');
  }
  if (!files.openshell.includes('filterOpenClawRuntimeNoise')
      || !files.openshell.includes('output: clean(raw)')
      || !files.openshell.includes('raw: filterOpenClawRuntimeNoise(raw)')) {
    findings.push('launchable terminal bypasses the shared runtime-noise filter');
  }
  if (files.chat.includes('d.textContent = "(no answer)"') || !files.chat.includes('opts.emptyResponseMessage')) {
    findings.push('chat UI still presents an unexplained no-answer placeholder');
  }
  for (const key of ['en', 'pt', 'es', 'en3b', 'pt3b', 'es3b', 'en3c', 'pt3c', 'es3c']) {
    if (!files[key].includes('helpers.openclawMessageText(pl.message)')
        || !files[key].includes('helpers.openclawResultText(data.result)')
        || !files[key].includes('helpers.filterOpenClawRuntimeValue(d)')
        || !files[key].includes('FINAL_EVENT_GRACE_MS')) {
      findings.push(`${key}: gateway cell can finish before chat.final or expose unfiltered diagnostics`);
    }
  }
  for (const key of ['en', 'pt', 'es']) {
    const start = files[key].indexOf('helpers.mountChatUI("#kickstart-artifact"');
    const end = start < 0 ? -1 : files[key].indexOf('\n});', start);
    const artifact = start < 0 || end < 0 ? '' : files[key].slice(start, end);
    if (!artifact.includes('exec') || !artifact.includes('/sandbox/.openclaw/workspace')) {
      findings.push(`${key}: Kickstart workspace prompt does not select the reliable exec path`);
    }
  }
  for (const key of ['en4b', 'pt4b', 'es4b']) {
    if (!files[key].includes('helpers.mountOpenClawCli("#agent-chat")')) {
      findings.push(`${key}: Module 4b bypasses the shared OpenClaw CLI runtime`);
    }
  }
  if (!files.cliRuntime.includes('runtime.openclawGatewayWsUrl(connection.rawUrl, connection.accessSession, null, null, connection.accessProvider).url')) {
    findings.push('OpenClaw CLI runtime bypasses shared OpenClaw routing');
  }

  if (!files.shared.includes('gatewayTokenFromAgentMetadata')
      || !files.shared.includes('refreshOpenClawGatewayToken')) {
    findings.push('shared runtime does not re-export the gateway token bootstrap helpers');
  }
  if (!files.runtime.includes('openClawHttpUrl')) {
    findings.push('browser harness does not route credentialed Brev HTTP probes through the hosted relay');
  }
  if (!/https:\/\/openclaw-cors-proxy\.experiments\.courses\.nvidia\.com(?=["'/])/.test(files.runtime)) {
    findings.push('browser harness does not name the hosted OpenClaw relay');
  }
  if (!files.runtime.includes("args.includes('--gateway-only')")
      || !files.runtime.includes("method: 'models.list'")) {
    findings.push('browser harness lacks the focused hosted gateway check');
  }
  if (!files.runtime.includes("args.includes('--cron-contract')")
      || !files.runtime.includes("method: 'cron.add'")
      || !files.runtime.includes("method: 'cron.remove'")
      || !files.runtime.includes("schedule: { kind: 'cron'")
      || !files.runtime.includes("output.cleanupId = ''")) {
    findings.push('browser harness lacks fail-clean structured cron contract coverage');
  }
  if (!files.runtime.includes("args.includes('--chat-contract')")
      || !files.runtime.includes('Use your exec tool to run whoami and pwd')
      || !files.runtime.includes("result.chatToolNames.includes('exec')")
      || !files.runtime.includes('result.chatToolErrors === 0')
      || !files.runtime.includes('!result.chatNoise')) {
    findings.push('browser harness lacks the focused live OpenClaw chat contract');
  }
  if (!files.runtime.includes("document.querySelectorAll('.cf-btn-run')[i]")
      || !files.runtime.includes("for (let index = 0; index < flowCount; index++)")
      || !files.runtime.includes("document.querySelectorAll('.cf-btn-run')[i]?.click()")
      || files.runtime.includes("btns.forEach(b => b.click())")) {
    findings.push('full-canvas harness must run page-level flows sequentially');
  }
  if (!files.runtime.includes("flow?.querySelector('.cf-panel.running')")
      || files.runtime.includes(".cf-panel.cf-running")) {
    findings.push('full-canvas harness does not wait for the CanvasFlow running class');
  }
  if (!files.runtime.includes('expectsGateway:')
      || !files.runtime.includes('activity.allFrames > 0 && activity.resOk > 0')
      || !files.runtime.includes('const gatewayMissing =')
      || files.runtime.includes('const expectedTools = !!(CLAW_URL && CLAW_TOKEN)')) {
    findings.push('full-canvas harness must use flow-specific gateway evidence instead of a blanket tool requirement');
  }
  if (!files.lab.includes('--cron-contract requires --gateway-only')
      || !files.lab.includes('--cron-contract) cron_contract=1')) {
    findings.push('lab runtime wrapper does not expose the opt-in cron contract check');
  }
  if (!files.lab.includes('--chat-contract requires --gateway-only')
      || !files.lab.includes('--chat-contract) chat_contract=1')) {
    findings.push('lab runtime wrapper does not expose the opt-in live chat contract check');
  }
  if (!files.runtime.includes("id: 'browser-cron-runs', method: 'cron.runs'")
      || !files.runtime.includes('result.cronAdd && result.cronRuns && result.cronRemove')) {
    findings.push('live cron harness does not verify run history before cleanup');
  }
  if (/token=\(\[a-f0-9\]/i.test(files.runtime)) {
    findings.push('browser harness still assumes hexadecimal gateway tokens');
  }
  return findings;
}

function selfTest() {
  const base = readAll();
  const mutations = [
    ['fragment token', { helper: base.helper.replace('fragment.get("token")', 'null') }],
    ['query token', { helper: base.helper.replace('parsed.searchParams.get("token")', 'null') }],
    ['Portuguese wiring', { pt: base.pt.replace('autofillToken: gatewayTokenFromAgentMetadata', 'autofillToken: null') }],
    ['shared relay controls', { en: base.en.replace('proxyControls: true', 'proxyControls: false') }],
    ['terminal relay', { openshell: base.openshell.replace('openclawWebSocketUrl(rawUrl, "/ws/terminal?cmd="', 'directTerminalUrl(rawUrl, "/ws/terminal?cmd="') }],
    ['terminal direct fallback', { openshell: base.openshell.replace('[direct.url, routed.url]', '[routed.url]') }],
    ['downstream gateway', { cliRuntime: base.cliRuntime.replace('runtime.openclawGatewayWsUrl(connection.rawUrl, connection.accessSession, null, null, connection.accessProvider).url', 'connection.rawUrl + "/cli/gateway"') }],
    ['downstream page boundary', { en4b: base.en4b.replace('helpers.mountOpenClawCli("#agent-chat")', 'mountDirectCli("#agent-chat")') }],
    ['shared export', { shared: base.shared.replaceAll('gatewayTokenFromAgentMetadata', 'removedGatewayTokenParser') }],
    ['automatic token bootstrap', { helper: base.helper.replaceAll('refreshOpenClawGatewayToken({ signal', 'removedGatewayTokenRefresh({ signal') }],
    ['harness relay', { runtime: base.runtime.replaceAll('openclaw-cors-proxy.experiments.courses.nvidia.com', 'relay.invalid') }],
    ['focused browser check', { runtime: base.runtime.replace("args.includes('--gateway-only')", 'false') }],
    ['cron cleanup', { runtime: base.runtime.replace("output.cleanupId = ''", "output.cleanupId = id") }],
    ['cron run history', { runtime: base.runtime.replace("id: 'browser-cron-runs', method: 'cron.runs'", "id: 'browser-cron-remove', method: 'cron.remove'") }],
    ['cron wrapper', { lab: base.lab.replace('--cron-contract) cron_contract=1', '--cron-contract) cron_contract=0') }],
    ['live chat harness', { runtime: base.runtime.replace("args.includes('--chat-contract')", 'false') }],
    ['live chat wrapper', { lab: base.lab.replace('--chat-contract) chat_contract=1', '--chat-contract) chat_contract=0') }],
    ['parallel full-canvas flows', { runtime: base.runtime.replace('for (let index = 0; index < flowCount; index++)', 'for (const index of [0])') }],
    ['hidden full-canvas flow click', { runtime: base.runtime.replace("document.querySelectorAll('.cf-btn-run')[i]?.click()", "document.querySelectorAll('.cf-btn-run')[0]?.click()") }],
    ['wrong full-canvas running selector', { runtime: base.runtime.replace("flow?.querySelector('.cf-panel.running')", "flow?.querySelector('.cf-panel.cf-running')") }],
    ['blanket full-canvas tool requirement', { runtime: base.runtime.replace('const gatewayMissing =', 'const expectedTools =') }],
    ['runtime noise filter', { runtimeText: base.runtimeText.replace('/proc\\/self\\/oom_score_adj', '/proc/noise') }],
    ['nested runtime filter', { runtimeText: base.runtimeText.replace('filterOpenClawRuntimeValue(value)', 'removedRuntimeValueFilter(value)') }],
    ['final event delivery', { helper: base.helper.replace('deliverFull(openclawMessageText(pl.message)); done(false);', 'done(false);') }],
    ['final event grace', { helper: base.helper.replace('endGrace = setTimeout(() => done(false), finalGraceMs)', 'done(false)') }],
    ['terminal noise filter', { openshell: base.openshell.replace('output: clean(raw)', 'output: strip(raw)') }],
    ['terminal raw noise filter', { openshell: base.openshell.replace('raw: filterOpenClawRuntimeNoise(raw)', 'raw') }],
    ['chat empty response', { chat: base.chat.replace('opts.emptyResponseMessage', 'removedEmptyResponseMessage') }],
    ['localized lifecycle', { pt3b: base.pt3b.replace('helpers.openclawMessageText(pl.message)', 'pl.message.content[0].text') }],
    ['localized diagnostic filter', { es3c: base.es3c.replaceAll('helpers.filterOpenClawRuntimeValue(d)', 'd') }],
    ['Kickstart exec prompt', { en: base.en.replace('Use your exec tool to run ls -la /sandbox/.openclaw/workspace, then explain each file', 'List the files in your workspace') }],
  ];
  const failures = [];
  for (const [label, overrides] of mutations) {
    if (!audit(overrides).length) failures.push(`missed ${label} mutation`);
  }
  return failures;
}

async function runtimeTextBehaviorFindings(source) {
  const mod = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
  const noise = '/bin/bash: 1: cannot create /proc/self/oom_score_adj: Permission denied';
  const findings = [];
  if (mod.filterOpenClawRuntimeNoise(`${noise}\nroot\n/sandbox`) !== 'root\n/sandbox') {
    findings.push('runtime-text filter did not remove only the oom_score_adj bootstrap line');
  }
  if (mod.filterOpenClawRuntimeNoise('Permission denied: keep this') !== 'Permission denied: keep this') {
    findings.push('runtime-text filter removed unrelated permission evidence');
  }
  if (mod.openclawMessageText({ content: [{ text: 'first' }, { text: 'second' }] }) !== 'first\nsecond') {
    findings.push('final-message parser dropped content blocks');
  }
  if (mod.openclawResultText({ content: [{ text: `${noise}\nresult` }] }) !== 'result') {
    findings.push('tool-result parser did not filter runtime noise');
  }
  const nested = mod.filterOpenClawRuntimeValue({ result: { content: [{ text: `keep\n${noise}` }] }, error: 'Permission denied: keep this' });
  if (nested.result.content[0].text !== 'keep' || nested.error !== 'Permission denied: keep this') {
    findings.push('nested runtime filter hid actionable evidence or retained bootstrap noise');
  }
  return findings;
}

if (process.argv.includes('--self-test')) {
  const failures = selfTest();
  failures.push(...await runtimeTextBehaviorFindings(readAll().runtimeText));
  console.log(`gateway token self-test: ${failures.length ? 'FAIL' : 'PASS'}`);
  for (const failure of failures) console.error(`  FAIL ${failure}`);
  process.exit(failures.length ? 1 : 0);
}

const findings = [...audit(), ...await runtimeTextBehaviorFindings(readAll().runtimeText)];
if (findings.length) {
  console.error(`gateway token audit: FAIL (${findings.length})`);
  for (const finding of findings) console.error(`  ${finding}`);
  process.exit(1);
}
console.log('gateway token audit: ok');
