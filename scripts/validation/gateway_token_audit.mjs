#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

// A locale page is the bytes the build publishes. When it ships from a key-based resource there is
// no HTML file to read, so the caller renders the published pages and names their root here.
const LOCALE_ROOT = process.env.NEMOCLAW_LOCALE_PAGES || 'i18n';

function discoverLocaleCourses(root = LOCALE_ROOT, courseName = 'nemoclaw', publishedRoot = root) {
  if (!fs.existsSync(root)) return [];
  const seen = new Set();
  return fs.readdirSync(root, { withFileTypes: true })
    .filter(entry => entry.isDirectory())
    .sort((left, right) => left.name.localeCompare(right.name))
    .map(entry => {
      const metadataPath = path.join(root, entry.name, 'locale.json');
      if (!fs.existsSync(metadataPath)) {
        throw new Error(`${metadataPath}: every locale directory must declare locale.json`);
      }
      const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
      const code = String(metadata.url_code || '');
      if (code !== entry.name || !/^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$/.test(code)) {
        throw new Error(`${metadataPath}: url_code must match its safe lowercase directory name`);
      }
      if (seen.has(code)) throw new Error(`${metadataPath}: duplicate url_code ${code}`);
      seen.add(code);
      if (metadata.schema !== 'nemoclaw-locale/1' || !metadata.locale) {
        throw new Error(`${metadataPath}: invalid locale identity`);
      }
      const candidates = [path.join(publishedRoot, code, 'web', courseName), path.join(publishedRoot, code, courseName)];
      return { code, root: candidates.find(directory => fs.existsSync(directory)) || candidates[0] };
    });
}

function recursiveSources(directory) {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, {withFileTypes:true}).flatMap(entry => {
    const file = path.join(directory, entry.name);
    return entry.isDirectory() ? recursiveSources(file) : /\.(?:html|js)$/.test(entry.name) ? [file] : [];
  }).sort();
}

export function discoverGatewayInventory(root = process.cwd(), localeRoot = path.resolve(root, LOCALE_ROOT)) {
  const web = path.join(root, 'web');
  const owners = fs.readdirSync(web, {withFileTypes:true}).filter(entry => entry.isDirectory())
    .map(entry => path.join(web, entry.name))
    .filter(directory => fs.existsSync(path.join(directory, 'scripts/_openclaw.js')));
  if (owners.length !== 1) throw new Error(`${web}: expected one declared gateway runtime owner`);
  const canonical = owners[0];
  const profilePath = path.join(canonical, 'learning-profile.json');
  const profile = JSON.parse(fs.readFileSync(profilePath, 'utf8'));
  if (!Array.isArray(profile.lessons)) throw new Error(`${profilePath}: lessons must be an array`);
  const roles = new Map(), declared = new Set();
  for (const entry of profile.lessons) {
    if (!entry || typeof entry.id !== 'string' || !/^[a-zA-Z0-9_/-]+$/.test(entry.id) || entry.id.startsWith('/')
        || entry.id.split('/').includes('..') || !Number.isInteger(entry.module)
        || entry.module < 1 || !Number.isInteger(entry.lesson) || entry.lesson < 1 || entry.lesson > 26) {
      throw new Error(`${profilePath}: malformed lesson identity`);
    }
    const role = `${entry.module}${String.fromCharCode(96 + entry.lesson)}`;
    const relative = `${entry.id}.html`;
    if (roles.has(role) || declared.has(relative)) throw new Error(`${profilePath}: duplicate lesson identity`);
    roles.set(role, relative); declared.add(relative);
  }
  const courses = [{code:'en', root:canonical}, ...discoverLocaleCourses(path.join(root, 'i18n'), path.basename(canonical), localeRoot)];
  const paths = {}, surfaces = {}, findings = [];
  for (const course of courses) {
    for (const role of ['3a','3b','3c','4b']) {
      const relative = roles.get(role);
      if (!relative) throw new Error(`${profilePath}: missing gateway curriculum role ${role}`);
      paths[role === '3a' ? course.code : course.code + role] = path.join(course.root, relative);
    }
    for (const relative of declared) {
      if (!fs.existsSync(path.join(course.root, relative))) findings.push(`${course.code}/${relative}: gateway-discovery: declared lesson is missing`);
    }
    for (const file of recursiveSources(course.root)) {
      const relative = path.relative(course.root, file);
      const source = fs.readFileSync(file, 'utf8');
      surfaces[file] = source;
      if (file.endsWith('.html') && !declared.has(relative) && gatewayCode(source, file).some(code => hasGatewayConsumer(code))) {
        findings.push(`${file}: gateway-discovery: gateway consumer is absent from lesson metadata`);
      }
    }
  }
  return {canonical, courses, paths, surfaces, findings};
}

const INVENTORY = discoverGatewayInventory();
const LOCALE_COURSES = INVENTORY.courses;
const LOCALIZED_CODES = LOCALE_COURSES.filter(item => item.code !== 'en').map(item => item.code);
const PAGE_PATHS = INVENTORY.paths;

const PATHS = {
  ...Object.fromEntries(Object.entries({
    helper:'_openclaw.js', runtimeText:'_runtime_text.js', connection:'_connection.js',
    openshell:'_openshell.js', chat:'_chat.js', shared:'_shared.js', cliRuntime:'_openclaw_cli.js',
  }).map(([key, name]) => [key, path.join(INVENTORY.canonical, 'scripts', name)])),
  runtime: 'scripts/runtime/test_page_runtime.js',
  lab: 'scripts/runtime/browser_runtime_test.sh',
  ...PAGE_PATHS,
};

function readAll(overrides = {}) {
  return Object.fromEntries(Object.entries(PATHS).map(([key, file]) => [
    key, Object.hasOwn(overrides, key) ? overrides[key] : fs.readFileSync(file, 'utf8'),
  ]));
}

function functionSource(source, declaration) {
  const start = source.indexOf(declaration);
  if (start < 0) return null;
  const signature = source.slice(start).match(/\)\s*\{/);
  if (!signature) return null;
  const brace = start + signature.index + signature[0].lastIndexOf('{');
  let depth = 0;
  for (let i = brace; i < source.length; i++) {
    if (source[i] === '{') depth++;
    if (source[i] === '}' && --depth === 0) return source.slice(start, i + 1);
  }
  return null;
}

function gatewayCode(source, name) {
  if (name.endsWith('.js')) return [source];
  // Browsers accept whitespace, slash and even attributes on script end tags.
  // Audit an unterminated block through EOF too, rather than silently losing it.
  return [...source.matchAll(/<script(?=[\t\n\f\r />])((?:"[^"]*"|'[^']*'|[^'">])*)>([\s\S]*?)(?:<\/script(?=[\t\n\f\r />])[^>]*>|$)/gi)]
    .filter(match => {
      // Read whole attributes so data-type or text inside another quoted value
      // cannot disguise executable code as an application/json data block.
      const attributes = [...match[1].matchAll(/(?:^|[\t\n\f\r /])([^\t\n\f\r /=>]+)(?:[\t\n\f\r ]*=[\t\n\f\r ]*(?:"([^"]*)"|'([^']*)'|([^\t\n\f\r >]+)))?/g)];
      const type = attributes.find(attribute => attribute[1].toLowerCase() === 'type');
      return !type || !/^application\/(?:ld\+)?json$/i.test((type[2] ?? type[3] ?? type[4] ?? '').trim());
    })
    .map(match => match[2]);
}

function hasGatewayConsumer(source) {
  return /\b(?:courseTur\w*|openclawCha\w*)\s*\(|\b_chatCb\s*=|\.call\(\s*["']chat\.send["']/.test(source);
}

function codeWithoutComments(source) {
  // Preserve strings (including displayed-cell templates) while removing comment witnesses.
  return source.replace(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\/\/[^\n]*|\/\*[\s\S]*?\*\//g,
    token => token.startsWith('//') || token.startsWith('/*') ? '' : token);
}

export function gatewayLifecycleFindings(source) {
  const findings = [];
  const chat = codeWithoutComments(functionSource(source, 'export async function openclawChat') || '');
  const turn = codeWithoutComments(functionSource(source, 'export async function courseTurn') || '');
  const need = (condition, message) => { if (!condition) findings.push(message); };
  need(chat.includes('if (d.event === "chat" && pl.state === "final")')
    && chat.includes('const finalText = openclawMessageText(pl.message);')
    && chat.includes('text = finalText; done(); return;')
    && (chat.match(/\bdone\(\s*(?:false|null)?\s*\)/g) || []).length === 1,
  'openclawChat: gateway-final: only the authoritative chat.final may complete successfully');
  need(chat.includes('view.replaceAnswer(finalText)') && chat.includes('onFinal?.(finalText)'),
    'openclawChat: gateway-final: reconcile corrected final text with streamed output');
  need(chat.includes('const resText = openclawResultText;')
    && chat.includes('resText(data.partialResult)') && chat.includes('resText(data.result)')
    && chat.includes('full = filterOpenClawRuntimeNoise(full)'),
  'openclawChat: gateway-noise: filter partial and complete tool results and streamed text');
  need(chat.includes('if (!matchesGatewaySession(key, session)) return;')
    && chat.includes('if (!acknowledged) { queued.push(d); return; }')
    && chat.includes('if (!myRun || pl.runId !== myRun) return;'),
  'openclawChat: gateway-owner: final events must match the acknowledged run and session');
  need(turn.includes('if (event.event === "chat" && p.state === "final")')
    && turn.includes('settle(null, helpers.openclawMessageText(p.message));')
    && (turn.match(/\bsettle\(\s*null\s*,/g) || []).length === 1,
  'courseTurn: gateway-final: only the authoritative chat.final may complete successfully');
  need(turn.includes('helpers.log.details(label, helpers.filterOpenClawRuntimeValue(event))')
    && turn.includes('helpers.log.details("final event", helpers.filterOpenClawRuntimeValue(event))'),
  'courseTurn: gateway-noise: filter tool and final diagnostic events at the shared owner');
  need(turn.includes('matchesGatewaySession(p.sessionKey || "", session)')
    && turn.includes('if (!acknowledged) { queued.push(event); return; }')
    && turn.includes('if (!runId || p.runId !== runId) return;'),
  'courseTurn: gateway-owner: final events must match the acknowledged run and session');
  for (const [name, code] of [['courseTurn', turn], ['openclawChat', chat]]) {
    need(code.includes('idleMs') && code.includes('totalMs') && code.includes('setTimeout(')
      && code.includes('new Error("No matching agent activity before the idle deadline")')
      && code.includes('new Error("Agent turn exceeded its total deadline")'),
    `${name}: gateway-final: missing final must fail at bounded deadlines`);
  }
  return findings;
}

export function gatewayConsumerFindings(surfaces, ownerPaths) {
  const findings = [];
  const owners = new Set(ownerPaths.map(file => path.resolve(file)));
  for (const [name, source] of Object.entries(surfaces)) {
    if (owners.has(path.resolve(name))) continue;
    for (const raw of gatewayCode(source, name)) {
      const code = codeWithoutComments(raw);
      for (const match of code.matchAll(/\b(?:helpers|runtime)\.(courseTur\w*|openclawCha\w*)\b/g)) {
        if (!['courseTurn', 'openclawChat'].includes(match[1])) findings.push(`${name}: gateway-discovery: malformed shared turn helper ${match[1]}`);
      }
      for (const match of code.matchAll(/\bcourseTurn\s*\(([^)]*)\)/g)) {
        if (!/^\s*state\s*,\s*(?:helpers|currentHelpers)\s*,/.test(match[1])) {
          findings.push(`${name}: gateway-owner: pass current state and helpers to courseTurn`);
        }
      }
      if (/\bcourseTurn\s*\(/.test(code)
          && !/helpers\.courseTurn\s*\(|\bcourseTurn\s*=\s*helpers\.courseTurn\b|\{[^}]*\bcourseTurn\b[^}]*\}\s*=\s*helpers\b/.test(code)) {
        findings.push(`${name}: gateway-owner: turn consumer is not bound to the shared courseTurn owner`);
      }
      if (/\.call\(\s*["']chat\.send["']|\b_chatCb\s*=/.test(code)) {
        findings.push(`${name}: gateway-owner: inline gateway lifecycle must use the shared turn owner`);
      }
    }
  }
  return findings;
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

export function audit(overrides = {}) {
  const files = readAll(overrides);
  const findings = [];

  const metadataParser = compile(files.helper, 'export function gatewayTokenFromAgentMetadata');
  findings.push(...parserFindings('course helper', raw => metadataParser?.({ agent: { dashboardUrl: raw } })));

  const runtimeParser = compile(files.runtime, 'function gatewayTokenFromDashboardUrl');
  findings.push(...parserFindings('browser harness', runtimeParser));

  for (const { code: key } of LOCALE_COURSES) {
    const source = files[key];
    if (!source.includes('mountOpenClawConnectionAudit("#probe-claw"')) {
      findings.push(`${key}: guided connection audit is not imported and mounted`);
    }
    if (/token=\(\[a-f0-9\]/i.test(source)) {
      findings.push(`${key}: hex-only gateway-token parser returned`);
    }
    if (!source.includes('helpers.runOpenClawConnectionAudit({')
        || !source.includes('baseUrl: connection.rawUrl')
        || !source.includes('accessSession: connection.accessSession')
        || !source.includes('checks: result.checks')
        || source.includes("helpers.log.json('redacted response', redacted)")
        || source.includes('const TRANSPORT =')
        || source.includes('X-OpenClaw-Access-Session')
        || source.includes('CF-Access-Jwt-Assertion')) {
      findings.push(`${key}: learner connection audit does not delegate all four routes to the shared provider decision`);
    }
  }

  if (!files.connection.includes('DEFAULT_OPENCLAW_PROXY_BASE')
      || !files.connection.includes('OPENCLAW_PROXY_ENABLED_KEY')
      || !files.connection.includes('OPENCLAW_WS_RELAY_ENABLED_KEY')
      || !files.connection.includes('getOpenClawWsRelayEnabled')
      || !files.connection.includes('migrateOpenClawConnectionStorage')
      || !files.connection.includes('new URL(DEFAULT_OPENCLAW_PROXY_BASE)')
      || /\.get\("openclaw_(?:url|access_provider|proxy|proxy_base)"\)/.test(files.connection)
      || files.connection.includes('new URL(config.base)')
      || !files.connection.includes('upstream.origin === loc.origin')) {
    findings.push('shared OpenClaw connection module lacks relay-backed metadata and explicit WebSocket-relay opt-in');
  }
  if (!files.openshell.includes('const direct = openclawWebSocketUrl(')
      || !files.openshell.includes('? openclawWebSocketUrl(')
      || !files.openshell.includes('"/ws/terminal?cmd=" + encodeURIComponent(cmd)')) {
    findings.push('terminal WebSocket bypasses shared OpenClaw routing');
  }
  if (!files.openshell.includes('Boolean(accessSession) && relayWebSocket !== false')
      || !files.openshell.includes('{ enabled: false, base: "" }')
      || !files.openshell.includes('? [direct.url, routed.url]')
      || !files.openshell.includes('Math.min(8000, openMs)')
      || files.openshell.includes('resolvedProvider === "cloudflare" || relayWebSocket === true')) {
    findings.push('terminal WebSocket must try direct before a provider-bound manual-session relay');
  }
  const gatewayRouter = functionSource(files.helper, 'export function openclawGatewayWsUrl');
  if (!gatewayRouter
      || !/\bproxyEnabled\s*===\s*true\b/.test(gatewayRouter)
      || !gatewayRouter.includes('provider === "pomerium" && Boolean(String(accessSession || "").trim())')
      || !gatewayRouter.includes('if (!relayEnabled)')
      || !gatewayRouter.includes('{ enabled: false, base: "" }')
      || !/openclawWebSocketUrl\s*\(\s*rawUrl\s*,\s*["']\/cli\/gateway["']\s*,\s*accessSession\s*,\s*config\s*,\s*accessProvider\s*\)/.test(gatewayRouter)) {
    findings.push('gateway WebSocket lost direct browser routing or Pomerium manual-session relay inference');
  }
  const bootstrap = functionSource(files.helper, 'export async function openclawBootstrapRequest');
  if (!files.runtimeText.includes('/proc\\/self\\/oom_score_adj')
      || !files.runtimeText.includes('filterOpenClawRuntimeNoise')
      || !files.runtimeText.includes('export function filterOpenClawRuntimeValue(')
      || !files.runtimeText.includes('openclawMessageText')
      || !files.runtimeText.includes('openclawResultText')) {
    findings.push('shared OpenClaw runtime-text filter or parser is missing');
  }
  findings.push(...gatewayLifecycleFindings(files.helper), ...INVENTORY.findings);
  if (!files.helper.includes('export async function refreshOpenClawGatewayToken(')
      || !/const\s+refreshed\s*=\s*await\s+refreshOpenClawGatewayToken\(\{\s*signal\s*[,}]/.test(files.helper)
      || !/const\s+refreshedGateway\s*=\s*await\s+helpers\.refreshOpenClawGatewayToken\(\{\s*signal\s*:\s*helpers\.signal\s*[,}]/.test(files.helper)
      || !bootstrap
      || !files.helper.includes('await openclawBootstrapRequest("/api/agent"')
      || !files.helper.includes('gatewayTokenFromAgentMetadata(response.json)')
      || !bootstrap.includes('if (provider === "pomerium")')
      || !files.helper.includes('openclawLoopbackProbe(actionPath, { baseUrl: rawUrl, signal })')
      || !bootstrap.includes('headers["CF-Access-Jwt-Assertion"] = connection.accessSession;')
      || !bootstrap.includes('headers["X-OpenClaw-Access-Provider"] = provider;')
      || !bootstrap.includes('headers["X-OpenClaw-Access-Session"] = connection.accessSession;')) {
    findings.push('gateway entry points do not discover the current token through the provider-safe /api/agent bootstrap');
  }
  if (!files.openshell.includes('filterOpenClawRuntimeNoise')
      || !files.openshell.includes('output: clean(raw)')
      || !files.openshell.includes('raw: filterOpenClawRuntimeNoise(raw)')) {
    findings.push('launchable terminal bypasses the shared runtime-noise filter');
  }
  if (files.chat.includes('d.textContent = "(no answer)"') || !files.chat.includes('opts.emptyResponseMessage')) {
    findings.push('chat UI still presents an unexplained no-answer placeholder');
  }
  for (const { code } of LOCALE_COURSES) {
    for (const key of [code, `${code}3b`, `${code}3c`]) {
      if (!files[key].includes('helpers.courseTurn')) {
        findings.push(`${key}: gateway-owner: gateway lesson must delegate cell turns to courseTurn`);
      }
    }
  }
  const surfaces = {...INVENTORY.surfaces};
  for (const [key, file] of Object.entries(PAGE_PATHS)) surfaces[file] = files[key];
  findings.push(...gatewayConsumerFindings(surfaces,
    LOCALE_COURSES.map(course => path.join(course.root, 'scripts/_openclaw.js'))));
  for (const { code: key } of LOCALE_COURSES) {
    const start = files[key].indexOf('helpers.mountChatUI("#kickstart-artifact"');
    const end = start < 0 ? -1 : files[key].indexOf('\n});', start);
    const artifact = start < 0 || end < 0 ? '' : files[key].slice(start, end);
    if (!artifact.includes('exec') || !artifact.includes('/sandbox/.openclaw/workspace')) {
      findings.push(`${key}: Kickstart workspace prompt does not select the reliable exec path`);
    }
  }
  for (const { code } of LOCALE_COURSES) {
    const key = `${code}4b`;
    if (!files[key].includes('helpers.mountOpenClawCli("#agent-chat")')) {
      findings.push(`${key}: Module 4b bypasses the shared OpenClaw CLI runtime`);
    }
  }
  if (!files.cliRuntime.includes('runtime.openclawGatewayWsUrl(connection.rawUrl, connection.accessSession, null, null, connection.accessProvider).url')) {
    findings.push('OpenClaw CLI runtime bypasses shared OpenClaw routing');
  }

  if (!files.shared.includes('gatewayTokenFromAgentMetadata')
      || !files.shared.includes('refreshOpenClawGatewayToken')
      || !files.shared.includes('openclawBootstrapRequest')) {
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
  if (!files.runtime.includes("const runnableSelector = '.cf-btn-run,.rc-run'")
      || !files.runtime.includes("for (let index = 0; index < runnableCount; index++)")
      || !files.runtime.includes("document.querySelectorAll('.cf-btn-run,.rc-run')[i]?.click()")
      || files.runtime.includes("btns.forEach(b => b.click())")) {
    findings.push('full-course harness must run CanvasFlow and RunCell sequentially in document order');
  }
  if (!files.runtime.includes("flow?.querySelector('.cf-panel.running')")
      || files.runtime.includes(".cf-panel.cf-running")) {
    findings.push('full-course harness does not wait for the CanvasFlow running class');
  }
  if (!files.runtime.includes('expectsGateway:')
      || !files.runtime.includes('activity.allFrames > 0 && activity.resOk > 0')
      || !files.runtime.includes('const gatewayExpected = !!CLAW_URL')
      || !files.runtime.includes('const gatewayMissing = gatewayExpected')
      || !files.runtime.includes('cellRuns.some(cell => cell.expectsGateway')
      || files.runtime.includes('const expectedTools = !!(CLAW_URL && CLAW_TOKEN)')) {
    findings.push('full-course harness must fail closed on token bootstrap and use cell-specific gateway evidence');
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
  const localized = LOCALIZED_CODES[0];
  const mutations = [
    ['fragment token', { helper: base.helper.replace('fragment.get("token")', 'null') }],
    ['query token', { helper: base.helper.replace('parsed.searchParams.get("token")', 'null') }],
    ...(localized ? [[
      'localized wiring',
      { [localized]: base[localized].replace(
        'mountOpenClawConnectionAudit("#probe-claw"',
        'mountRemovedConnectionAudit("#probe-claw"',
      ) },
    ]] : []),
    ['learner four-route helper', { en: base.en.replace('helpers.runOpenClawConnectionAudit({', 'helpers.runSingleOpenClawCheck({') }],
    ['learner connection input', { en: base.en.replace('baseUrl: connection.rawUrl', 'baseUrl: "https://example.invalid"') }],
    ['learner duplicate diagnostic output', { en: base.en.replace('return redacted;', "helpers.log.json('redacted response', redacted);\nreturn redacted;") }],
    ['learner transport branch', { en: base.en.replace('const connection = helpers.getOpenClawConnection();', "const TRANSPORT = 'direct';\nconst connection = helpers.getOpenClawConnection();") }],
    ['approved relay construction', { connection: base.connection.replace('new URL(DEFAULT_OPENCLAW_PROXY_BASE)', 'new URL(config.base)') }],
    ['retired presenter query', { connection: base.connection.replace('export function getOpenClawProxyConfig()', 'const legacyRelay = new URLSearchParams(location.search).get("openclaw_proxy");\n\nexport function getOpenClawProxyConfig()') }],
    ['same-origin launchable exception', { connection: base.connection.replace('if (loc && upstream.origin === loc.origin) return false;', '') }],
    ['terminal relay', { openshell: base.openshell.replace('const direct = openclawWebSocketUrl(', 'const direct = directTerminalUrl(', 1) }],
    ['terminal manual-session route', { openshell: base.openshell.replace('Boolean(accessSession) && relayWebSocket !== false', 'Boolean(accessSession) && relayWebSocket === true') }],
    ['terminal direct-first recovery', { openshell: base.openshell.replace('? [direct.url, routed.url]', '? [routed.url]') }],
    ['gateway direct default', { helper: base.helper.replace('if (!relayEnabled)', 'if (false)') }],
    ['gateway Pomerium manual fallback', { helper: base.helper.replace('provider === "pomerium" && Boolean(String(accessSession || "").trim())', 'provider === "pomerium" && false') }],
    ['gateway relay opt-in', { helper: base.helper.replace('proxyEnabled === true', 'proxyEnabled !== false') }],
    ['downstream gateway', { cliRuntime: base.cliRuntime.replace('runtime.openclawGatewayWsUrl(connection.rawUrl, connection.accessSession, null, null, connection.accessProvider).url', 'connection.rawUrl + "/cli/gateway"') }],
    ['downstream page boundary', { en4b: base.en4b.replace('helpers.mountOpenClawCli("#agent-chat")', 'mountDirectCli("#agent-chat")') }],
    ['shared export', { shared: base.shared.replaceAll('gatewayTokenFromAgentMetadata', 'removedGatewayTokenParser') }],
    ['automatic token bootstrap', { helper: base.helper.replaceAll('refreshOpenClawGatewayToken({ signal', 'removedGatewayTokenRefresh({ signal') }],
    ['metadata token discovery', { helper: base.helper.replace('gatewayTokenFromAgentMetadata(response.json)', 'null') }],
    ['Pomerium loopback bootstrap', { helper: base.helper.replace('openclawLoopbackProbe(actionPath, { baseUrl: rawUrl, signal })', 'fetch(actionPath)') }],
    ['Pomerium manual-session loopback bootstrap', { helper: base.helper.replace('if (provider === "pomerium")', 'if (provider === "pomerium" && !connection.accessSession)') }],
    ['bootstrap assertion header', { helper: base.helper.replace('headers["CF-Access-Jwt-Assertion"] = connection.accessSession;', 'headers["X-Removed-Assertion"] = connection.accessSession;') }],
    ['Pomerium provider header', { helper: base.helper.replace('headers["X-OpenClaw-Access-Provider"] = provider;', 'headers["X-OpenClaw-Access-Provider"] = "cloudflare";') }],
    ['Pomerium session header', { helper: base.helper.replace('headers["X-OpenClaw-Access-Session"] = connection.accessSession;', 'headers["X-OpenClaw-Access-Session"] = "";') }],
    ['harness relay', { runtime: base.runtime.replaceAll('openclaw-cors-proxy.experiments.courses.nvidia.com', 'relay.invalid') }],
    ['focused browser check', { runtime: base.runtime.replace("args.includes('--gateway-only')", 'false') }],
    ['cron cleanup', { runtime: base.runtime.replace("output.cleanupId = ''", "output.cleanupId = id") }],
    ['cron run history', { runtime: base.runtime.replace("id: 'browser-cron-runs', method: 'cron.runs'", "id: 'browser-cron-remove', method: 'cron.remove'") }],
    ['cron wrapper', { lab: base.lab.replace('--cron-contract) cron_contract=1', '--cron-contract) cron_contract=0') }],
    ['live chat harness', { runtime: base.runtime.replace("args.includes('--chat-contract')", 'false') }],
    ['live chat wrapper', { lab: base.lab.replace('--chat-contract) chat_contract=1', '--chat-contract) chat_contract=0') }],
    ['parallel full-course cells', { runtime: base.runtime.replace('for (let index = 0; index < runnableCount; index++)', 'for (const index of [0])') }],
    ['hidden full-course cell click', { runtime: base.runtime.replace("document.querySelectorAll('.cf-btn-run,.rc-run')[i]?.click()", "document.querySelectorAll('.cf-btn-run,.rc-run')[0]?.click()") }],
    ['wrong full-course running selector', { runtime: base.runtime.replace("flow?.querySelector('.cf-panel.running')", "flow?.querySelector('.cf-panel.cf-running')") }],
    ['blanket full-course tool requirement', { runtime: base.runtime.replace('const gatewayMissing =', 'const expectedTools =') }],
    ['token-bootstrap false green', { runtime: base.runtime.replace('const gatewayExpected = !!CLAW_URL', 'const gatewayExpected = !!(CLAW_URL && CLAW_TOKEN)') }],
    ['runtime noise filter', { runtimeText: base.runtimeText.replace('/proc\\/self\\/oom_score_adj', '/proc/noise') }],
    ['nested runtime filter', { runtimeText: base.runtimeText.replace('filterOpenClawRuntimeValue(value)', 'removedRuntimeValueFilter(value)') }],
    ['final event delivery', { helper: base.helper.replace('text = finalText; done(); return;', 'done(); return;') }],
    ['lifecycle early completion', { helper: base.helper.replace('// Lifecycle end is not authoritative chat completion. Wait for chat.final.', 'if (stream === "lifecycle") done();') }],
    ['shared final event parser', { helper: base.helper.replace('settle(null, helpers.openclawMessageText(p.message))', 'settle(null, p.message.content[0].text)') }],
    ['shared diagnostic filter', { helper: base.helper.replaceAll('helpers.filterOpenClawRuntimeValue(event)', 'event') }],
    ['terminal noise filter', { openshell: base.openshell.replace('output: clean(raw)', 'output: strip(raw)') }],
    ['terminal raw noise filter', { openshell: base.openshell.replace('raw: filterOpenClawRuntimeNoise(raw)', 'raw') }],
    ['chat empty response', { chat: base.chat.replace('opts.emptyResponseMessage', 'removedEmptyResponseMessage') }],
    ...(localized ? [[
      'localized lifecycle',
      { [`${localized}3b`]: base[`${localized}3b`].replaceAll('helpers.courseTurn', 'helpers.removedCourseTurn') },
    ], [
      'localized diagnostic filter',
      { [`${localized}3c`]: base[`${localized}3c`].replaceAll('courseTurn(state, helpers,', 'courseTurn(state, {},') },
    ]] : []),
    ['Kickstart exec prompt', { en: base.en.replace('Use your exec tool to run ls -la /sandbox/.openclaw/workspace, then explain each file', 'List the files in your workspace') }],
  ];
  const failures = audit().map(finding => `invalid mutation baseline: ${finding}`);
  const unsafeConsumer = 'await state.call("chat.send", {});';
  const scriptCases = [
    ['ordinary script', `<script>${unsafeConsumer}</script>`],
    ['end whitespace', `<script>${unsafeConsumer}</script \t\n>`],
    ['end attributes', `<script>${unsafeConsumer}</script data-note="ignored">`],
    ['mixed case', `<ScRiPt>${unsafeConsumer}</sCrIpT>`],
    ['slash delimiters', `<script/>${unsafeConsumer}</script/>`],
    ['quoted opening delimiter', `<script data-note=">">${unsafeConsumer}</script>`],
    ['unterminated block', `<script>${unsafeConsumer}`],
    ['misleading end name', `<script>const text = '</script-extra>'; ${unsafeConsumer}</script>`],
    ['data-type is not type', `<script data-type="application/json">${unsafeConsumer}</script>`],
    ['type text in another attribute', `<script data-note='type="application/json"'>${unsafeConsumer}</script>`],
    ['first duplicate type owns block', `<script type="module" type="application/json">${unsafeConsumer}</script>`],
  ];
  for (const [label, source] of scriptCases) {
    if (!gatewayConsumerFindings({'novel/nested/renamed.html':source}, [])
      .some(finding => finding.includes('inline gateway lifecycle'))) failures.push(`missed script extraction mutation: ${label}`);
  }
  for (const [label, source] of [
    ['near-match opening name', `<script-extra>${unsafeConsumer}</script-extra>`],
    ['deleted executable block', '<p>Gateway exercise removed</p>'],
    ['JSON data block', `<script type="application/json">${unsafeConsumer}</script>`],
    ['JSON-LD data block', `<script TYPE = 'application/ld+json'>${unsafeConsumer}</script>`],
    ['unquoted JSON type', `<script type=application/json>${unsafeConsumer}</script>`],
  ]) {
    if (gatewayConsumerFindings({'novel/nested/renamed.html':source}, []).length) failures.push(`unexpected script extraction finding: ${label}`);
  }
  for (const [label, overrides] of mutations) {
    if (!Object.entries(overrides).some(([key, value]) => value !== base[key])) {
      failures.push(`unchanged ${label} mutation`);
    } else if (!audit(overrides).length) failures.push(`missed ${label} mutation`);
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

async function main() {
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
}
if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await main();
}
