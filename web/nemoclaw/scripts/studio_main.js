// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { chat, getConfig, hasKey } from './_shared.js';

const STUDIO_ZH = document.documentElement.lang.toLowerCase().startsWith('zh');
const STUDIO_ZH_TEXT = Object.freeze({
  '01a · The Agent Loop': '01a · 智能体循环',
  '01b · ReAct Loop': '01b · ReAct 循环',
  '01c · Tools at Scale': '01c · 规模化工具调用',
  '02a · Workflows': '02a · 工作流',
  '02b · Index Agent': '02b · 索引智能体',
  '02c · Deep Agents': '02c · 深度智能体',
  '03a · Kickstart': '03a · 快速上手',
  '03c · Always-On': '03c · 持久在线',
  '04b · Modern CLIs': '04b · 现代 CLI',
  '04c · Going Further': '04c · 延伸学习',
  'Static studio contract': 'Studio 静态约定',
  'Helper notebook static contract': '辅助 notebook 静态约定',
  'Helper notebook browser contract': '辅助 notebook 浏览器约定',
  'Cell UI source/browser contract': '代码单元 UI 源文件/浏览器约定',
  'Cell UI production bundle contract': '代码单元 UI 生产课程包约定',
  'Studio responsive contract': 'Studio 响应式约定',
  'Browser environment probe': '浏览器环境探测',
  'Browser runtime smoke': '浏览器运行时冒烟测试',
  'Static browser render': '静态浏览器渲染',
  'no lab stack': '无实验环境栈',
  'host Chromium, no lab stack': '宿主机 Chromium，无实验环境栈',
  'host prerequisites': '宿主机前置条件',
  'Checks studio controls, self-hosted assets, read-only fallback, and script SKILL testing docs.': '检查 Studio 控件、自托管资源、只读回退和脚本 SKILL 测试文档。',
  'Checks helper notebook examples, validation command parity, syntax asset hooks, and CanvasFlow versus RunCell helper surfaces.': '检查辅助 notebook 示例、验证命令一致性、语法资源挂钩，以及 CanvasFlow 与 RunCell 的辅助函数界面。',
  'Clicks every helper notebook run control and verifies CodeMirror, highlighted JSON logs, table layout, and page overflow.': '点击辅助 notebook 中的每个运行控件，并检查 CodeMirror、JSON 日志高亮、表格布局和页面溢出。',
  'Checks CanvasFlow and RunCell across desktop/mobile and dark/light themes; verifies unified buttons, JS chips, syntax highlighting, hidden-code heuristics, and captures screenshots.': '在桌面端、移动端及深色/浅色主题下检查 CanvasFlow 和 RunCell；验证统一按钮、JS 标记、语法高亮和隐藏代码启发式规则，并截取屏幕截图。',
  'Run after BUILD_PAGES_LANGS=0 scripts/build/build_pages.sh; repeats the cell UI browser suite against public/ to prove the shipped bundle keeps the contract.': '在运行 BUILD_PAGES_LANGS=0 scripts/build/build_pages.sh 后执行；针对 public/ 重复代码单元 UI 浏览器测试，验证发布课程包仍满足约定。',
  'Stress-tests narrow and short Studio viewports for topbar scrolling, usable controls, sidebar list floors, and internal scrolling.': '对窄屏和低高度 Studio 视口进行压力测试，检查顶部栏滚动、控件可用性、侧边栏列表最小高度和内部滚动。',
  'Verifies host Node.js, the pinned Playwright API, and Chromium before browser checks run.': '在浏览器检查前验证宿主机 Node.js、固定版本的 Playwright API 和 Chromium。',
  'Runs the direct Node/Playwright/Chromium smoke test.': '运行直接调用 Node/Playwright/Chromium 的冒烟测试。',
  'Runs host Chromium against a static course page.': '使用宿主机 Chromium 渲染静态课程页面。',
  'Copy': '复制',
  'Copied': '已复制',
  'Copy failed': '复制失败',
  'Dark': '深色',
  'Light': '浅色',
  'Switch back to dark lab mode': '切换回深色实验模式',
  'Toggle light export mode': '切换浅色导出模式',
  'Read-only static preview: Jupyter contents API not available on this origin.': '静态预览为只读：当前来源无法使用 Jupyter contents API。',
  'Read-only preview: Jupyter contents API not available on this origin.': '预览为只读：当前来源无法使用 Jupyter contents API。',
  'References unavailable for this frame.': '无法获取此框架中的引用。',
  'No page references found.': '本页未找到引用。',
  'Read-only static preview': '静态预览为只读',
  'No module loaded.': '尚未加载模块。',
  'No comments for this page.': '本页暂无批注。',
  '(page-level)': '（页面级）',
  'resolve': '解决',
  'resolved': '已解决',
  '(page-level comment)': '（页面级批注）',
  'No runnable blocks on this page.': '本页没有可运行的内容块。',
  'Annotate': '注解',
  'Ask the LLM to annotate this output': '让 LLM 注解此输出',
  'no output': '无输出',
  'Annotating': '正在注解',
  'Studio Annotation': 'Studio 注解',
  'annotating': '正在注解',
  '(no response)': '（无响应）',
  'Save cell': '保存代码单元',
  "Save this cell's code to the source file (only this cell)": '仅将此代码单元的代码保存到源文件',
  'no change': '无变更',
  'saving': '正在保存',
  'saved': '已保存',
  'No pending edits.': '暂无待保存的编辑。',
  'Save checked': '保存已勾选项',
  'external': '外部',
  'material': '资料',
  'page': '页面',
  'asset': '资源',
  'link': '链接',
});

function studioText(value) {
  if (!STUDIO_ZH || typeof value !== 'string') return value;
  if (STUDIO_ZH_TEXT[value]) return STUDIO_ZH_TEXT[value];
  const patterns = [
    [/^loading (.+)$/, '正在加载 $1'],
    [/^loaded · (.+)$/, '已加载 · $1'],
    [/^Write access: Jupyter contents API at (.+)$/, '写入权限：Jupyter contents API 位于 $1'],
    [/^Last modified: (.+) UTC$/, '最后修改时间：$1 UTC'],
    [/^On: "(.+)"$/, '定位到：“$1”'],
    [/^running (\d+\/\d+) runnable block\(s\)$/, '正在运行 $1 个可运行内容块'],
    [/^running (\d+\/\d+): (.+)$/, '正在运行 $1：$2'],
    [/^stopped at (\d+\/\d+): (.+)$/, '在 $1 处停止：$2'],
    [/^ran (\d+\/\d+) runnable block\(s\) · (\d+) failed$/, '已运行 $1 个可运行内容块 · $2 个失败'],
    [/^LLM unavailable: (.+)$/, 'LLM 不可用：$1'],
    [/^(\d+) changed section\(s\)\. Use the sidebar to jump$/, '$1 个章节有变更。请使用侧边栏跳转'],
    [/^saved (\d+) change\(s\)$/, '已保存 $1 项变更'],
    [/^save failed: (.+)$/, '保存失败：$1'],
  ];
  for (const [pattern, replacement] of patterns) {
    if (pattern.test(value)) return value.replace(pattern, replacement);
  }
  return value;
}

function localizeStudioNode(root) {
  if (!STUDIO_ZH || !root) return;
  const doc = root.nodeType === Node.DOCUMENT_NODE ? root : root.ownerDocument;
  const scope = root.nodeType === Node.DOCUMENT_NODE ? root.documentElement : root;
  if (!doc || !scope) return;
  const walker = doc.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(node => {
    if (node.parentElement?.closest('code,pre,textarea,script,style')) return;
    const raw = node.nodeValue || '';
    const trimmed = raw.trim();
    if (!trimmed) return;
    const translated = studioText(trimmed);
    if (translated !== trimmed) node.nodeValue = raw.replace(trimmed, translated);
  });
  scope.querySelectorAll?.('[title],[aria-label],[placeholder]').forEach(element => {
    for (const name of ['title', 'aria-label', 'placeholder']) {
      if (!element.hasAttribute(name)) continue;
      const current = element.getAttribute(name);
      const translated = studioText(current);
      if (translated !== current) element.setAttribute(name, translated);
    }
  });
}

function observeStudioUi(root) {
  if (!STUDIO_ZH || !root || root._studioZhObserver) return;
  localizeStudioNode(root);
  const scope = root.nodeType === Node.DOCUMENT_NODE ? root.documentElement : root;
  const observer = new MutationObserver(records => {
    records.forEach(record => {
      if (record.type === 'characterData') localizeStudioNode(record.target.parentElement);
      record.addedNodes.forEach(node => localizeStudioNode(
        node.nodeType === Node.TEXT_NODE ? node.parentElement : node));
    });
  });
  observer.observe(scope, {childList:true, characterData:true, subtree:true});
  root._studioZhObserver = observer;
}

// ═══════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════

const MODULES = [
  { label:'01a · The Agent Loop',    file:'01a-loop.html'          },
  { label:'01b · ReAct Loop',        file:'01b-react.html'         },
  { label:'01c · Tools at Scale',    file:'01c-tools.html'         },
  { label:'02a · Workflows',         file:'02a-routing.html'       },
  { label:'02b · Index Agent',       file:'02b-rag.html'           },
  { label:'02c · Deep Agents',       file:'02c-deep.html'          },
  { label:'03a · Kickstart',         file:'03a-kickstart.html'     },
  { label:'03b · OpenClaw',          file:'03b-openclaw.html'      },
  { label:'03c · Always-On',         file:'03c-always-on.html'     },
  { label:'04a · NemoClaw',          file:'04a-safety.html'        },
  { label:'04b · Modern CLIs',       file:'04b-modern-clis.html'   },
  { label:'04c · Going Further',     file:'04c-going-further.html' },
];

const API_CANDIDATES = [
  '/lab/api/contents/web/nemoclaw/',
  '/lab/api/contents/nemoclaw/',
];
const COMMENT_FILE  = 'studio_comments.json';
const LAB_AUTHORING = location.pathname.startsWith('/lab/static/');
let contentApiBase  = null;
let contentApiReady = !LAB_AUTHORING;
const SNAPSHOT_SEL  = 'h1,h2,h3,p,li,td,.callout,.hero .lead,.cf-panel-title';
const ANNOTATE_SYS  = `You are a concise teaching assistant for an AI agent engineering course.
A student just ran a code exercise and got the following output. In 2–4 sentences explain what
this output demonstrates about LLM or agent behavior, and the key takeaway. Be concrete to what
is shown. No bullet points or headers. Do not repeat the output verbatim.`;

// ═══════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════

let currentFile   = null;   // e.g. '01a-agents.html'
let lastModified  = null;   // ISO string from JupyterLab
let pollTimer     = null;
let comments      = [];     // all persisted comments
let pendingChgs   = [];     // { id, type, label, oldVal, newVal, checked }
let pickActive    = false;
let editActive    = false;
let liteMode      = false;  // true = light/export overlay active
let _liteCss      = null;   // cached styles/_lite_overlay.css text
let diffSnap      = null;   // element-text snapshot before a reload
let changedEls    = [];     // elements highlighted after diff

// ═══════════════════════════════════════════════════════════════
// DOM REFS
// ═══════════════════════════════════════════════════════════════

const frame     = document.getElementById('studio-frame');
const sidebar   = document.getElementById('sidebar');
const loadingEl = document.getElementById('loading');
const pickOv    = document.getElementById('pick-ov');
const modSel    = document.getElementById('mod-sel');
const urlBar    = document.getElementById('url-bar');
const tbStatus  = document.getElementById('tb-status');
const lmRow     = document.getElementById('lm-row');
const runNote   = document.getElementById('run-note');
const cmtList   = document.getElementById('cmt-list');
const cmtBadge  = document.getElementById('cmt-badge');
const chgList   = document.getElementById('chg-list');
const jumpBtn   = document.getElementById('jump-btn');
const saveSelBtn= document.getElementById('save-sel-btn');
const liteBtn   = document.getElementById('lite-btn');
const refList   = document.getElementById('ref-list');
const writeNote = document.getElementById('write-note');
const testList  = document.getElementById('test-list');

// ═══════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════

function xsrf() {
  const m = document.cookie.match(/_xsrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
}
function setStatus(msg, cls='') {
  tbStatus.textContent = studioText(msg);
  tbStatus.className = 'tb-status' + (cls ? ' '+cls : '');
}
function getIdoc() {
  try { return frame.contentDocument; } catch { return null; }
}


const TEST_COMMANDS = [
  {
    name: 'Static studio contract',
    mode: 'no lab stack',
    desc: 'Checks studio controls, self-hosted assets, read-only fallback, and script SKILL testing docs.',
    cmd: 'python3 scripts/validation/studio_interface_audit.py',
  },
  {
    name: 'Helper notebook static contract',
    mode: 'no lab stack',
    desc: 'Checks helper notebook examples, validation command parity, syntax asset hooks, and CanvasFlow versus RunCell helper surfaces.',
    cmd: 'python3 scripts/validation/helper_notebook_runtime_audit.py --static-only',
  },
  {
    name: 'Helper notebook browser contract',
    mode: 'host Chromium, no lab stack',
    desc: 'Clicks every helper notebook run control and verifies CodeMirror, highlighted JSON logs, table layout, and page overflow.',
    cmd: 'python3 scripts/validation/helper_notebook_runtime_audit.py',
  },
  {
    name: 'Cell UI source/browser contract',
    mode: 'host Chromium, no lab stack',
    desc: 'Checks CanvasFlow and RunCell across desktop/mobile and dark/light themes; verifies unified buttons, JS chips, syntax highlighting, hidden-code heuristics, and captures screenshots.',
    cmd: 'python3 scripts/validation/cell_ui_runtime_audit.py --screenshots tmp/cell-ui-audit-source',
  },
  {
    name: 'Cell UI production bundle contract',
    mode: 'host Chromium, no lab stack',
    desc: 'Run after BUILD_PAGES_LANGS=0 scripts/build/build_pages.sh; repeats the cell UI browser suite against public/ to prove the shipped bundle keeps the contract.',
    cmd: 'python3 scripts/validation/cell_ui_runtime_audit.py --site-root public --screenshots tmp/cell-ui-audit-public',
  },
  {
    name: 'Studio responsive contract',
    mode: 'host Chromium, no lab stack',
    desc: 'Stress-tests narrow and short Studio viewports for topbar scrolling, usable controls, sidebar list floors, and internal scrolling.',
    cmd: 'python3 scripts/validation/studio_responsive_audit.py',
  },
  {
    name: 'Browser environment probe',
    mode: 'host prerequisites',
    desc: 'Verifies host Node.js, the pinned Playwright API, and Chromium before browser checks run.',
    cmd: 'scripts/runtime/browser_env_probe.sh',
  },
  {
    name: 'Browser runtime smoke',
    mode: 'host Chromium, no lab stack',
    desc: 'Runs the direct Node/Playwright/Chromium smoke test.',
    cmd: 'scripts/runtime/browser_runtime_test.sh --smoke',
  },
  {
    name: 'Static browser render',
    mode: 'host Chromium, no lab stack',
    desc: 'Runs host Chromium against a static course page.',
    cmd: 'scripts/runtime/browser_runtime_test.sh --render-only',
  },
];

function renderTestCommands() {
  if (!testList) return;
  testList.innerHTML = '';
  TEST_COMMANDS.forEach((row, idx) => {
    const item = document.createElement('div');
    item.className = 'test-item';
    item.innerHTML = `
      <div class="test-name">${esc(row.name)}</div>
      <div class="test-desc">${esc(row.mode)} - ${esc(row.desc)}</div>
      <code class="test-cmd">${esc(row.cmd)}</code>
      <button type="button" class="test-copy" data-test-i="${idx}">Copy</button>`;
    testList.appendChild(item);
  });
  testList.querySelectorAll('.test-copy').forEach(btn => {
    btn.addEventListener('click', async () => {
      const row = TEST_COMMANDS[Number(btn.dataset.testI)];
      try {
        await navigator.clipboard.writeText(row.cmd);
        btn.textContent = 'Copied';
      } catch {
        btn.textContent = 'Copy failed';
      }
      setTimeout(() => { btn.textContent = 'Copy'; }, 1400);
    });
  });
}

// ═══════════════════════════════════════════════════════════════
// LIGHT / EXPORT MODE
// ═══════════════════════════════════════════════════════════════

// Caches styles/_lite_overlay.css once for the light-mode (edX export) toggle.
async function fetchLiteCSS() {
  if (_liteCss !== null) return _liteCss;
  try {
    const r = await fetch('styles/_lite_overlay.css?t=' + Date.now());
    _liteCss = r.ok ? await r.text() : '';
  } catch { _liteCss = ''; }
  return _liteCss;
}

async function applyLiteMode(idoc) {
  if (!idoc) return;
  // Remove any stale tag from a previous load
  idoc.getElementById('_studio_lite')?.remove();
  const css = await fetchLiteCSS();
  if (!css) return;
  const s = idoc.createElement('style');
  s.id = '_studio_lite';
  s.textContent = css;
  idoc.head.appendChild(s);
  // Keep the iframe body background in sync so the studio frame bg matches
  frame.style.background = '#ffffff';
}

function removeLiteMode(idoc) {
  if (!idoc) return;
  idoc.getElementById('_studio_lite')?.remove();
  frame.style.background = 'var(--bg)';
}

liteBtn.addEventListener('click', async () => {
  liteMode = !liteMode;
  liteBtn.classList.toggle('active', liteMode);
  liteBtn.textContent = liteMode ? 'Dark' : 'Light';
  liteBtn.title = liteMode
    ? 'Switch back to dark lab mode'
    : 'Toggle light export mode';
  const idoc = getIdoc();
  if (idoc) {
    if (liteMode) await applyLiteMode(idoc);
    else removeLiteMode(idoc);
  }
});

// ═══════════════════════════════════════════════════════════════
// BLOCK EDITOR
// ═══════════════════════════════════════════════════════════════

let blockEditActive = false;
let _beEl           = null;   // currently selected iframe element
let _beOrigHTML     = null;   // outerHTML at selection time (display/revert baseline)
let _beFileLoc      = null;   // block's exact slice in the source file: { content, start, end, raw }
let _beCm           = null;   // optional editor instance when an embedding page provides one

const blockEditorPanel = document.getElementById('block-editor');
const beBadge = document.getElementById('be-badge');
const bePath2 = document.getElementById('be-path');
const beMsg   = document.getElementById('be-msg');
const beTa    = document.getElementById('be-ta');

// Selector for what counts as a "block"
const _BLOCK_SEL =
  'h1,h2,h3,h4,h5,h6,p,li,ul,ol,table,pre,blockquote,figure,' +
  '.callout,.hero,section,.card,.cf-wrap,details,summary,' +
  'div[id^="cell-"],div[id^="fig-"],.lead,.note,td,th';

function _nearestBlock(el) {
  // Anchor on the <svg> itself: its viewBox/class attributes are unique.
  // An id-bearing semantic ancestor is preferred when one wraps it.
  const svgEl = el.closest('svg');
  if (svgEl) {
    const p = svgEl.parentElement;
    // Prefer a <figure> ancestor (may contain caption + svg together)
    if (p && p.tagName === 'FIGURE') return p;
    // Prefer an id-bearing parent, even an empty JS-mount placeholder (fig-*).
    // The locate callback then warns that a save here is overwritten on reload.
    if (p && p.id) return p;
    return svgEl;
  }
  // Standard blocks: semantic selector first, then any id'd or class'd ancestor
  return el.closest(_BLOCK_SEL)
      || el.closest('[id]')
      || el.closest('[class]')
      || el;
}

function _blockType(el) {
  if (el.classList.contains('cf-wrap'))       return 'canvas';
  if (el.tagName==='SVG' || el.closest('figure svg')) return 'svg';
  return 'html';
}

function _elPath(el) {
  const parts = [];
  let cur = el;
  while (cur && cur.tagName !== 'BODY') {
    let p = cur.tagName.toLowerCase();
    if (cur.id) p += '#' + cur.id;
    else if (cur.className) {
      const cls = String(cur.className).trim().split(/\s+/)[0];
      if (cls) p += '.' + cls;
    }
    parts.unshift(p);
    cur = cur.parentElement;
    if (parts.length >= 5) break;
  }
  return parts.join(' › ');
}

// Pretty-print HTML with block-tag indentation
function _fmtHTML(html) {
  const BT = /^(div|section|article|header|footer|h[1-6]|p|ul|ol|li|table|tr|td|th|thead|tbody|tfoot|figure|figcaption|details|summary|blockquote|pre|main|nav|aside|form|fieldset)$/i;
  let out = '', depth = 0;
  for (const raw of html.replace(/>\s*</g, '>\n<').split('\n')) {
    const t = raw.trim(); if (!t) continue;
    const isClose    = /^<\//.test(t);
    const isSelf     = /\/>$/.test(t) || /^<!--/.test(t) || /^<!/.test(t);
    const tag        = (t.match(/^<\/?(\w+)/) || [])[1] || '';
    const isBlock    = BT.test(tag);
    if (isClose && isBlock) depth = Math.max(0, depth - 1);
    out += '  '.repeat(depth) + t + '\n';
    if (!isClose && !isSelf && isBlock) depth++;
  }
  return out.trim();
}

// Init optional rich editor inside the panel (lazy, once)
function _ensureBeCM() {
  if (_beCm) return _beCm;
  if (typeof window.CodeMirror !== 'function') return null;
  _beCm = window.CodeMirror.fromTextArea(beTa, {
    mode: 'htmlmixed',
    theme: 'monokai',
    lineNumbers: true,
    lineWrapping: true,
    tabSize: 2, indentUnit: 2,
    viewportMargin: Infinity,
    extraKeys: {
      'Tab':       cm => cm.execCommand('indentMore'),
      'Shift-Tab': cm => cm.execCommand('indentLess'),
    },
  });
  return _beCm;
}

function _beSetMsg(txt, cls='') {
  beMsg.textContent = txt;
  beMsg.className = 'be-msg' + (cls ? ' '+cls : '');
}

// ── File-location helpers ────────────────────────────────────────

// outerHTML differs from raw file text (normalised whitespace, self-closing tags, xmlns reorder).
// So we fetch the file and locate the block by its opening-tag prefix plus a balanced close-tag walk.

function _beClosingTagEnd(src, from, tag) {
  const t = tag.toLowerCase();
  // Skip past the opening tag's >
  let i = from;
  while (i < src.length && src[i] !== '>') i++;
  if (i >= src.length) return -1;
  if (src[i-1] === '/') return i + 1;  // self-closing
  i++;

  // Standard HTML void elements never have a close tag
  const VOID = new Set(['area','base','br','col','embed','hr','img','input',
                        'link','meta','param','source','track','wbr']);
  if (VOID.has(t)) return i;

  // SVG/HTML paired elements: balanced walk
  let depth = 1;
  while (i < src.length && depth > 0) {
    const lt = src.indexOf('<', i);
    if (lt < 0) break;
    // Peek at the tag name after <
    const slice = src.slice(lt + 1, lt + t.length + 3).toLowerCase();
    if (slice.startsWith('/' + t) &&
        /[\s>]/.test(src[lt + 1 + t.length + 1] || '')) {
      depth--;
      if (depth === 0) {
        const gt = src.indexOf('>', lt);
        return gt >= 0 ? gt + 1 : -1;
      }
      i = lt + 1;
    } else if (slice.startsWith(t) &&
               /[\s>/]/.test(src[lt + 1 + t.length] || '')) {
      // A nested same-name tag deepens the count, unless it is self-closing.
      const gt = src.indexOf('>', lt);
      if (gt >= 0 && src[gt-1] !== '/') depth++;
      i = gt >= 0 ? gt + 1 : lt + 1;
    } else {
      i = lt + 1;
    }
  }
  return depth === 0 ? i : -1;
}

async function _locateBlockInFile(el) {
  if (!currentFile) return null;
  try {
    const content = await fetchContent();
    const outer   = el.outerHTML.trim();
    const tagName = (outer.match(/^<([\w:-]+)/) || [])[1];
    if (!tagName) return null;
    const t = tagName.toLowerCase();

    // S1: exact match, for plain HTML blocks whose attributes are not reordered.
    if (content.includes(outer)) {
      const s = content.indexOf(outer);
      return { content, start: s, end: s + outer.length };
    }

    // S2: attribute-value fingerprint, immune to SVG attribute reordering.
    // Find a stable attr value present verbatim, then walk back to the opening < and out to the close tag.
    const fps = [];
    if (el.id)
      fps.push(`id="${el.id}"`);
    if (t === 'svg') {
      const vb = el.getAttribute('viewBox') || el.getAttribute('viewbox');
      if (vb) { fps.push(`viewBox="${vb}"`); fps.push(`viewbox="${vb}"`); }
    }
    const cls = typeof el.className === 'string' ? el.className.trim() : '';
    if (cls) fps.push(`class="${cls}"`);

    for (const fp of fps) {
      let search = 0;
      while (true) {
        const fpIdx = content.indexOf(fp, search);
        if (fpIdx < 0) break;
        // Walk back to the < that opens this tag
        let start = fpIdx;
        while (start > 0 && content[start] !== '<') start--;
        // Confirm it is our tag
        if (content.slice(start + 1, start + 1 + t.length).toLowerCase() === t) {
          const end = _beClosingTagEnd(content, start, t);
          if (end > start) return { content, start, end };
        }
        search = fpIdx + 1;
      }
    }

    // S3: opening-tag prefix, the non-SVG fallback when attribute order is preserved.
    const firstGt = outer.indexOf('>');
    if (firstGt >= 0) {
      const openTag = outer.slice(0, firstGt + 1);
      for (const len of [openTag.length, 100, 60, 40, 20]) {
        const key = openTag.slice(0, len).trimStart();
        if (!key) continue;
        const idx = content.indexOf(key);
        if (idx < 0) continue;
        const end = _beClosingTagEnd(content, idx, t);
        if (end > idx) return { content, start: idx, end };
      }
    }

    return null;
  } catch(err) {
    console.warn('[studio] _locateBlockInFile:', err);
    return null;
  }
}

function openBlockEditor(el) {
  _beEl       = el;
  _beOrigHTML = el.outerHTML;
  _beFileLoc  = null;

  const type = _blockType(el);
  beBadge.textContent = type;
  beBadge.className   = 'be-badge ' + type;
  bePath2.textContent = _elPath(el);
  _beSetMsg('locating in file…');

  const cm = _ensureBeCM();
  const pretty = _fmtHTML(_beOrigHTML);
  if (cm) { cm.setValue(pretty); setTimeout(() => cm.refresh(), 40); }
  else    { beTa.value = pretty; }

  blockEditorPanel.classList.add('open');

  // Kick off file-location in the background (fast; reuses cached content)
  _locateBlockInFile(el).then(loc => {
    _beFileLoc = loc;
    if (type === 'canvas') {
      _beSetMsg('Canvas flow: edits update the live DOM only. Edit the mountCanvasFlow() source to persist.');
      return;
    }
    if (!loc) {
      _beSetMsg('Could not locate the <' + el.tagName.toLowerCase() + '> block in source. Apply works, Save disabled');
      return;
    }
    // A mount call targeting this id regenerates the content on every load, so any save is overwritten.
    // Checking for the call is reliable even after a prior save wrote SVG into the placeholder.
    if (el.id) {
      const id = el.id;
      const src = loc.content;
      const isMounted =
        src.includes(`mountDiagram("#${id}"`)  || src.includes(`mountDiagram('#${id}'`) ||
        src.includes(`mountDiagram("${id}"`)   || src.includes(`mountDiagram('${id}'`) ||
        src.includes(`mountCanvasFlow("#${id}"`) || src.includes(`mountCanvasFlow('#${id}'`) ||
        src.includes(`mountRunCell("#${id}"`)  || src.includes(`mountRunCell('#${id}'`);
      if (isMounted) {
        _beFileLoc = null; // block Save
        _beSetMsg(
          'JS-mounted by a mountDiagram() / mountCanvasFlow() call that regenerates ' +
          '#' + id + ' on every page load. Any save is overwritten on refresh. ' +
          'To change this diagram edit the spec object in the page <script> tag.'
        );
        return;
      }
    }
    const rawLen = loc.end - loc.start;
    const preview = loc.content.slice(loc.start, loc.start + 60).replace(/\s+/g,' ');
    _beSetMsg('ready · ' + rawLen + ' chars · "' + preview + '…"', 'ok');
  });
}

function closeBlockEditor() {
  blockEditorPanel.classList.remove('open');
  const idoc = getIdoc();
  if (idoc) idoc.querySelectorAll('._beSelected,._beHover').forEach(e => {
    e.classList.remove('_beSelected','_beHover');
  });
  _beEl = null; _beOrigHTML = null; _beFileLoc = null;
}

function safeStudioUrl(raw, attribute) {
  const value = String(raw || "").trim();
  if (!value) return null;
  try {
    const url = new URL(value, location.href);
    if (url.protocol === "http:" || url.protocol === "https:") return url.href;
    if (attribute === "href" && url.protocol === "mailto:") return url.href;
  } catch (_) {}
  return value.startsWith("#") ? value : null;
}

function sanitizeStudioPreview(source) {
  const parsed = new DOMParser().parseFromString(String(source), "text/html");
  parsed.querySelectorAll("script,iframe,object,embed,base,link,style,meta[http-equiv]").forEach(node => node.remove());
  const urlAttributes = new Set(["href", "src", "xlink:href", "action", "formaction", "poster", "background", "cite", "data"]);
  parsed.querySelectorAll("*").forEach(node => {
    [...node.attributes].forEach(attribute => {
      const name = attribute.name.toLowerCase();
      if (name.startsWith("on") || name === "srcdoc") {
        node.removeAttribute(attribute.name);
        return;
      }
      if (urlAttributes.has(name)) {
        const safe = safeStudioUrl(attribute.value, name);
        if (safe) node.setAttribute(attribute.name, safe);
        else node.removeAttribute(attribute.name);
      }
    });
    if (node.tagName === "A" && node.getAttribute("target") === "_blank") {
      node.setAttribute("rel", "noopener noreferrer");
    }
  });
  return parsed.body.firstElementChild;
}

// Apply edited HTML back into the live iframe DOM
document.getElementById('be-apply').addEventListener('click', () => {
  if (!_beEl) return;
  const newHTML = (_beCm ? _beCm.getValue() : beTa.value).trim();
  try {
    const newEl = sanitizeStudioPreview(newHTML);
    if (!newEl) throw new Error('parsed HTML produced no element');
    _beEl.replaceWith(newEl);
    _beEl = newEl;
    newEl.classList.add('_beSelected');
    _beSetMsg('applied to page', 'ok');
  } catch(e) {
    _beSetMsg(e.message.slice(0,70), 'err');
  }
});

// Save this block's raw file slice back to the source file
document.getElementById('be-save').addEventListener('click', async () => {
  if (!_beEl || !currentFile) return;
  const newHTML = (_beCm ? _beCm.getValue() : beTa.value).trim();
  _beSetMsg('saving');
  try {
    // Use the location found at selection time, anchored to the original element.
    // Re-locating after Apply would fail: _beEl holds edited content by then.
    const loc = _beFileLoc;
    if (!loc) throw new Error(
      'block not found in source file. The status bar shows the tag name; ' +
      'try clicking a different ancestor (e.g. the parent <figure> or a div with an id)'
    );

    // Strip studio selection classes the browser baked into outerHTML
    const cleanHTML = newHTML
      .replace(/ _beSelected\b/g, '').replace(/ _beHover\b/g, '')
      .replace(/ _stBlockSelected\b/g, '').replace(/ _stChanged\b/g, '')
      .replace(/\s+class=""\s*/g, ' ');
    // Replace the exact raw slice we found at selection time
    const newContent = loc.content.slice(0, loc.start) + cleanHTML + loc.content.slice(loc.end);
    await putContent(newContent);

    // Update baseline so the next save diffs against the new content
    _beFileLoc = { content: newContent, start: loc.start, end: loc.start + cleanHTML.length };
    _beOrigHTML = cleanHTML;
    _beSetMsg('saved to ' + currentFile, 'ok');
  } catch(e) {
    _beSetMsg(e.message.slice(0,80), 'err');
  }
});

// Revert editor content to what was loaded from the page
document.getElementById('be-revert').addEventListener('click', () => {
  if (!_beOrigHTML) return;
  const pretty = _fmtHTML(_beOrigHTML);
  if (_beCm) _beCm.setValue(pretty);
  else beTa.value = pretty;
  _beSetMsg('reverted to original');
});

document.getElementById('be-close').addEventListener('click', closeBlockEditor);
document.getElementById('be-close2').addEventListener('click', closeBlockEditor);

// Toggle block-edit mode
const blockEditBtn = document.getElementById('block-edit-btn');
blockEditBtn.addEventListener('click', () => {
  blockEditActive = !blockEditActive;
  blockEditBtn.classList.toggle('active', blockEditActive);
  const idoc = getIdoc();
  if (blockEditActive) { if (idoc) _injectBlockPick(idoc); }
  else { if (idoc) _removeBlockPick(idoc); closeBlockEditor(); }
});

function _injectBlockPick(idoc) {
  if (!idoc) return;
  if (!idoc.getElementById('_beStyle')) {
    const s = idoc.createElement('style');
    s.id = '_beStyle';
    s.textContent = `
      ._beHover {
        outline: 2px dashed rgba(118,185,0,.75) !important;
        outline-offset: 2px !important;
        cursor: pointer !important;
      }
      ._beSelected {
        outline: 2px solid var(--g) !important;
        outline-offset: 2px !important;
        background: rgba(118,185,0,.05) !important;
      }
    `;
    idoc.head.appendChild(s);
  }

  idoc._beOver = e => {
    const b = _nearestBlock(e.target);
    if (b && !b.classList.contains('_beSelected')) b.classList.add('_beHover');
  };
  idoc._beOut = e => {
    const b = _nearestBlock(e.target); if (b) b.classList.remove('_beHover');
  };
  idoc._beClick = e => {
    if (e.target.closest('._stBadge,._stSaveBtn,._stAnnBtn,._stBlockSelected')) return;
    const b = _nearestBlock(e.target); if (!b) return;
    e.preventDefault(); e.stopPropagation();
    idoc.querySelectorAll('._beSelected,._beHover').forEach(el => {
      el.classList.remove('_beSelected','_beHover');
    });
    b.classList.add('_beSelected');
    openBlockEditor(b);
  };

  idoc.addEventListener('mouseover', idoc._beOver,  true);
  idoc.addEventListener('mouseout',  idoc._beOut,   true);
  idoc.addEventListener('click',     idoc._beClick, true);
}

function _removeBlockPick(idoc) {
  if (!idoc) return;
  idoc.querySelectorAll('._beHover,._beSelected').forEach(e => {
    e.classList.remove('_beHover','_beSelected');
  });
  if (idoc._beOver)  idoc.removeEventListener('mouseover', idoc._beOver,  true);
  if (idoc._beOut)   idoc.removeEventListener('mouseout',  idoc._beOut,   true);
  if (idoc._beClick) idoc.removeEventListener('click',     idoc._beClick, true);
}

// ═══════════════════════════════════════════════════════════════
// MODULE SELECTOR & NAVIGATION
// ═══════════════════════════════════════════════════════════════

MODULES.forEach(m => {
  const o = document.createElement('option');
  o.value = m.file; o.textContent = m.label;
  modSel.appendChild(o);
});

modSel.addEventListener('change', () => { if (modSel.value) loadPage(modSel.value); });
// Re-selecting the same option fires no 'change', so a click on the select reloads it.
modSel.addEventListener('click', () => {
  if (modSel.value && modSel.value === currentFile) loadPage(currentFile, true);
});
urlBar.addEventListener('keydown', e => { if (e.key==='Enter') loadPage(urlBar.value.trim()); });
document.getElementById('reload-btn').addEventListener('click', () => {
  if (currentFile) loadPage(currentFile, true);
});

// ═══════════════════════════════════════════════════════════════
// PAGE LOADING
// ═══════════════════════════════════════════════════════════════

function loadPage(file, forceReload=false) {
  if (!file) return;

  // Snapshot before reload for diff
  if (forceReload && currentFile === file) {
    const idoc = getIdoc();
    if (idoc) diffSnap = snapshotEls(idoc);
  } else {
    diffSnap = null;
  }

  currentFile = file;
  urlBar.value = file;
  const match = MODULES.find(m => m.file===file);
  modSel.value = match ? match.file : '';

  loadingEl.style.display = 'flex';
  setStatus('loading ' + file);
  // Absolute URL so the iframe resolves in the lab, Pages, and local static previews.
  frame.src = directPageUrl(file) + '?studio=1&t=' + Date.now();
}

// After iframe loads: inject studio tooling and trigger auto-features
frame.addEventListener('load', () => {
  loadingEl.style.display = 'none';
  const idoc = getIdoc();
  if (!currentFile) return;
  if (!idoc) {
    // contentDocument is null → cross-origin block or sandbox restriction.
    // The page is visible but studio tooling cannot reach into it.
    setStatus('cannot access page: same-origin frame access is blocked', 'warn');
    return;
  }

  checkLastModified();
  renderComments();
  renderReferences(idoc);

  // Module scripts are type=module (async). Give them ~700ms to finish mounting.
  setTimeout(() => {
    injectStyles(idoc);
    // Re-apply light overlay if active (injected styles are lost on each load)
    if (liteMode) applyLiteMode(idoc);
    // Re-inject block-pick listeners if active
    if (blockEditActive) _injectBlockPick(idoc);
    injectCommentBadges(idoc);
    if (editActive) enableEditMode(idoc);

    // Auto-run
    if (document.getElementById('autorun-on').checked) {
      triggerRunAll(idoc).then(count => {
        if (count > 0 && document.getElementById('autoannotate-on').checked) {
          watchRunCompletion(idoc);
        }
      });
    }

    // Always inject per-panel annotate buttons and save buttons
    injectAnnotateBtns(idoc);
    if (editActive) injectSaveBtns(idoc);
    observeStudioUi(idoc);

    // Diff highlight
    if (diffSnap) {
      changedEls = diffWithSnap(diffSnap, idoc);
      diffSnap = null;
      jumpBtn.disabled = changedEls.length===0;
      if (changedEls.length) {
        highlightEls(changedEls, idoc);
        setStatus(`${changedEls.length} changed section(s). Use the sidebar to jump`, 'ok');
      }
    } else {
      setStatus('loaded · ' + currentFile);
    }
  }, 700);
});


function directPageUrl(file) {
  return new URL(file, new URL('.', location.href)).href;
}

async function resolveContentApi(file=currentFile) {
  if (contentApiReady) {
    if (!contentApiBase && writeNote) {
      writeNote.textContent = 'Read-only static preview: Jupyter contents API not available on this origin.';
    }
    return contentApiBase;
  }
  if (!file) return null;
  for (const base of API_CANDIDATES) {
    try {
      const r = await fetch(base + encodeURIComponent(file) + '?content=0&t=' + Date.now(), {cache:'no-store'});
      if (r.ok) {
        contentApiBase = base;
        contentApiReady = true;
        if (writeNote) writeNote.textContent = 'Write access: Jupyter contents API at ' + base;
        return contentApiBase;
      }
    } catch { /**/ }
  }
  contentApiBase = null;
  contentApiReady = true;
  if (writeNote) writeNote.textContent = 'Read-only preview: Jupyter contents API not available on this origin.';
  return null;
}

function contentApiUrl(file=currentFile, query='') {
  return contentApiBase + encodeURIComponent(file) + query;
}

function commentStorageKey() {
  return 'nemoclaw.studio.comments.v2';
}

function classifyReference(href) {
  if (/^https?:\/\//i.test(href)) return 'external';
  if (href.includes('/mats/') || href.includes('mats/')) return 'material';
  if (/\.html(?:$|[?#])/i.test(href)) return 'page';
  if (/\.(js|css|json|png|svg|jpg|jpeg|webp|ico)(?:$|[?#])/i.test(href)) return 'asset';
  return 'link';
}

function renderReferences(idoc) {
  if (!refList) return;
  if (!idoc) {
    refList.innerHTML = '<div class="empty-hint">References unavailable for this frame.</div>';
    return;
  }
  const seen = new Set();
  const rows = [];
  idoc.querySelectorAll('a[href]').forEach(a => {
    const raw = a.getAttribute('href') || '';
    if (!raw || raw.startsWith('#')) return;
    let parsed;
    try { parsed = new URL(raw, directPageUrl(currentFile || '')); }
    catch (_) { return; }
    if (!['http:', 'https:'].includes(parsed.protocol)) return;
    const abs = parsed.href;
    const key = abs.replace(/[?#].*$/, '');
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({raw, abs, text:(a.textContent || raw).trim().replace(/\s+/g,' ').slice(0,90), kind:classifyReference(raw)});
  });
  if (!rows.length) {
    refList.innerHTML = '<div class="empty-hint">No page references found.</div>';
    return;
  }
  rows.sort((a,b) => a.kind.localeCompare(b.kind) || a.text.localeCompare(b.text));
  refList.innerHTML = '';
  rows.slice(0,24).forEach(r => {
    const div = document.createElement('div');
    div.className = 'ref-item';
    const kind = document.createElement('span');
    kind.className = 'ref-kind';
    kind.textContent = r.kind;
    const link = document.createElement('a');
    link.target = '_blank';
    link.rel = 'noopener';
    link.href = r.abs;
    link.textContent = r.text || r.raw;
    const meta = document.createElement('div');
    meta.className = 'ref-meta';
    meta.textContent = r.raw;
    div.append(kind, link, meta);
    refList.appendChild(div);
  });
}

// ═══════════════════════════════════════════════════════════════
// JUPYTERLAB API
// ═══════════════════════════════════════════════════════════════

async function checkLastModified() {
  if (!currentFile) return;
  const base = await resolveContentApi(currentFile);
  if (!base) {
    lmRow.textContent = 'Read-only static preview';
    return;
  }
  try {
    const r = await fetch(contentApiUrl(currentFile, '?content=0&t=' + Date.now()));
    if (!r.ok) return;
    const meta = await r.json();
    if (meta.last_modified) {
      const lm = meta.last_modified;
      if (lastModified && lm !== lastModified) setStatus('file changed externally since load', 'warn');
      lastModified = lm;
      lmRow.textContent = 'Last modified: ' + lm.replace('T',' ').slice(0,16) + ' UTC';
    }
  } catch { /**/ }
}

async function fetchContent() {
  const base = await resolveContentApi(currentFile);
  if (base) {
    const r = await fetch(contentApiUrl(currentFile, '?type=file&format=text&content=1&t=' + Date.now()));
    if (!r.ok) throw new Error('fetch ' + r.status);
    const meta = await r.json();
    if (typeof meta.content !== 'string') throw new Error('content must be a string but got ' + typeof meta.content);
    return meta.content;
  }
  const r = await fetch(directPageUrl(currentFile) + '?source=1&t=' + Date.now(), {cache:'no-store'});
  if (!r.ok) throw new Error('static fetch ' + r.status);
  return await r.text();
}

async function putContent(content) {
  const base = await resolveContentApi(currentFile);
  if (!base) throw new Error('write API unavailable on this origin');
  const r = await fetch(contentApiUrl(currentFile), {
    method:'PUT',
    headers:{'Content-Type':'application/json','X-XSRFToken':xsrf()},
    body:JSON.stringify({type:'file',format:'text',content}),
  });
  if (!r.ok) throw new Error('PUT ' + r.status + ' ' + (await r.text()).slice(0,80));
}

// ═══════════════════════════════════════════════════════════════
// AUTO-REFRESH / POLLING
// ═══════════════════════════════════════════════════════════════

document.getElementById('poll-on').addEventListener('change', e => {
  e.target.checked ? startPolling() : stopPolling();
});
document.getElementById('poll-secs').addEventListener('change', () => {
  if (document.getElementById('poll-on').checked) { stopPolling(); startPolling(); }
});

function startPolling() {
  stopPolling();
  const s = parseInt(document.getElementById('poll-secs').value) || 8;
  pollTimer = setInterval(pollTick, s * 1000);
}
function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer=null; } }

async function pollTick() {
  if (!currentFile) return;
  try {
    const base = await resolveContentApi(currentFile);
    if (!base) return;
    const r = await fetch(contentApiUrl(currentFile, '?content=0&t=' + Date.now()));
    if (!r.ok) return;
    const meta = await r.json();
    const lm = meta.last_modified;
    if (!lm) return;
    lmRow.textContent = 'Last modified: ' + lm.replace('T',' ').slice(0,16) + ' UTC';
    if (lastModified && lm !== lastModified) {
      lastModified = lm;
      const idoc = getIdoc();
      if (idoc) diffSnap = snapshotEls(idoc);
      setStatus('reloading changed file', 'warn');
      frame.src = directPageUrl(currentFile) + '?studio=1&t=' + Date.now();
    }
    lastModified = lm;
  } catch { /**/ }
}

// ═══════════════════════════════════════════════════════════════
// DIFF / CHANGE HIGHLIGHTING
// ═══════════════════════════════════════════════════════════════

function snapshotEls(idoc) {
  return Array.from(idoc.querySelectorAll(SNAPSHOT_SEL)).map(el => ({
    text: el.textContent.trim().slice(0,150),
    tag:  el.tagName,
  }));
}

function diffWithSnap(snap, idoc) {
  const newEls = Array.from(idoc.querySelectorAll(SNAPSHOT_SEL));
  const changed = [];
  const len = Math.min(snap.length, newEls.length);
  for (let i=0; i<len; i++) {
    if (newEls[i].textContent.trim().slice(0,150) !== snap[i].text)
      changed.push(newEls[i]);
  }
  // Completely new elements at the end
  for (let i=snap.length; i<newEls.length; i++) changed.push(newEls[i]);
  return changed;
}

function highlightEls(els, idoc) {
  // Ensure animation style is injected
  if (!idoc.getElementById('studio-flash-style')) {
    const s = idoc.createElement('style');
    s.id = 'studio-flash-style';
    s.textContent = `
      @keyframes _stFlash{
        0%{outline:3px solid var(--g);background:rgba(118,185,0,.18)}
        80%{outline:3px solid var(--g);background:rgba(118,185,0,.06)}
        100%{outline:none;background:transparent}
      }
      ._stChanged{animation:_stFlash 2.2s ease forwards;border-radius:4px}
    `;
    idoc.head.appendChild(s);
  }
  for (const el of els) {
    el.classList.add('_stChanged');
    setTimeout(()=>el.classList.remove('_stChanged'), 2500);
  }
  if (els.length) els[0].scrollIntoView({behavior:'smooth',block:'center'});
}

jumpBtn.addEventListener('click', () => {
  const idoc = getIdoc();
  if (!idoc || !changedEls.length) return;
  highlightEls(changedEls, idoc);
});

// ═══════════════════════════════════════════════════════════════
// COMMENT SYSTEM
// ═══════════════════════════════════════════════════════════════

async function loadComments() {
  const base = await resolveContentApi(MODULES[0]?.file || 'index.html');
  if (!base) {
    try { comments = JSON.parse(localStorage.getItem(commentStorageKey()) || '[]'); }
    catch { comments = []; }
    return;
  }
  try {
    const r = await fetch(contentApiBase + COMMENT_FILE + '?type=file&format=text&content=1&t=' + Date.now());
    if (!r.ok) { comments=[]; return; }
    const meta = await r.json();
    comments = JSON.parse(typeof meta.content === 'string' ? meta.content : '[]');
  } catch { comments=[]; }
}

async function saveComments() {
  const base = await resolveContentApi(MODULES[0]?.file || 'index.html');
  if (!base) {
    localStorage.setItem(commentStorageKey(), JSON.stringify(comments, null, 2));
    return;
  }
  const r = await fetch(contentApiBase + COMMENT_FILE, {
    method:'PUT',
    headers:{'Content-Type':'application/json','X-XSRFToken':xsrf()},
    body:JSON.stringify({type:'file',format:'text',content:JSON.stringify(comments,null,2)}),
  });
  if (!r.ok) throw new Error('save comments: '+r.status);
}

function renderComments() {
  if (!currentFile) {
    cmtList.innerHTML = '<div class="empty-hint">No module loaded.</div>';
    cmtBadge.style.display='none';
    return;
  }
  const mine  = comments.filter(c => c.file===currentFile);
  const open  = mine.filter(c => !c.done);
  cmtBadge.style.display = open.length ? '' : 'none';
  cmtBadge.textContent   = open.length;

  if (!mine.length) {
    cmtList.innerHTML='<div class="empty-hint">No comments for this page.</div>';
    return;
  }
  cmtList.innerHTML='';
  mine.forEach(c => {
    const idx = comments.indexOf(c);
    const div = document.createElement('div');
    div.className='cmt-item'+(c.done?' done':'');
    div.innerHTML=`
      <div class="cmt-text">${esc(c.text)}</div>
      <div class="cmt-meta">
        <span>${esc(c.anchor?.textStart?.slice(0,28)||'(page-level)')}…</span>
        ${!c.done
          ? `<button class="cmt-resolve" data-i="${idx}">resolve</button>`
          : `<span style="color:var(--gd)">resolved</span>`}
      </div>`;
    cmtList.appendChild(div);
  });
  cmtList.querySelectorAll('.cmt-resolve').forEach(btn => {
    btn.addEventListener('click', async () => {
      const i = parseInt(btn.dataset.i);
      comments[i].done=true;
      try { await saveComments(); } catch {/***/}
      renderComments();
      injectCommentBadges(getIdoc());
    });
  });
}

// Inject studio base styles into iframe (idempotent)
function injectStyles(idoc) {
  if (idoc.getElementById('_stStyles')) return;
  const s = idoc.createElement('style');
  s.id = '_stStyles';
  s.textContent = `
    ._stBadge{
      display:inline-block;background:var(--err);color:#fff;
      font-size:10px;font-weight:700;border-radius:10px;
      padding:1px 5px;margin-left:5px;cursor:pointer;
      vertical-align:middle;user-select:none;font-family:Arial,sans-serif;
      transition:background .1s;
    }
    ._stBadge:hover{background:color-mix(in srgb,var(--err) 82%,black)}
    body._stPick *{cursor:crosshair!important}
    body._stPick h1:hover,body._stPick h2:hover,body._stPick h3:hover,
    body._stPick p:hover,body._stPick li:hover,body._stPick td:hover,
    body._stPick .callout:hover,body._stPick .hero:hover{
      outline:2px dashed var(--g)!important;
    }
    .studio-annotation{
      background:rgba(118,185,0,.09);border-left:3px solid var(--g);
      border-radius:0 6px 6px 0;padding:8px 12px;margin:8px 0 4px;
      font-size:.8rem;color:var(--td);line-height:1.5;
    }
    .studio-annotation .ann-head{
      font-size:.68rem;color:var(--g);font-weight:700;
      margin-bottom:4px;letter-spacing:.06em;text-transform:uppercase;
    }
    .studio-annotation.ann-loading{opacity:.45}
    ._stSaveBtn{
      display:inline-flex;align-items:center;gap:3px;
      font-size:.72rem;font-family:Arial,sans-serif;
      padding:2px 8px;border-radius:5px;
      border:1px solid var(--gd);background:rgba(118,185,0,.1);
      color:var(--g);cursor:pointer;margin-left:8px;font-weight:600;
      line-height:1.5;transition:background .1s;
    }
    ._stSaveBtn:hover{background:rgba(118,185,0,.22)}
    ._stSaveBtn.ok{background:rgba(118,185,0,.28);color:var(--gs)}
    ._stAnnBtn{
      font-size:.7rem;font-family:Arial,sans-serif;
      padding:2px 8px;border-radius:5px;
      border:1px solid var(--gd);background:rgba(118,185,0,.08);
      color:var(--g);cursor:pointer;font-weight:600;
      margin-left:8px;transition:background .1s;
    }
    ._stAnnBtn:hover{background:rgba(118,185,0,.2)}
    body._stEditMode [contenteditable="true"]:focus{
      outline:2px dashed rgba(118,185,0,.55)!important;
      background:rgba(118,185,0,.04)!important;border-radius:3px;
    }
  `;
  idoc.head.appendChild(s);
}

function injectCommentBadges(idoc) {
  if (!idoc || !currentFile) return;
  idoc.querySelectorAll('._stBadge').forEach(b=>b.remove());
  comments
    .filter(c => c.file===currentFile && !c.done && c.anchor?.textStart)
    .forEach(c => {
      const el = findByTextStart(idoc, c.anchor.tag, c.anchor.textStart);
      if (!el) return;
      const badge = idoc.createElement('span');
      badge.className='_stBadge';
      badge.textContent='note';
      badge.title=c.text;
      el.appendChild(badge);
    });
}

function findByTextStart(idoc, tag, textStart) {
  const prefix = (textStart||'').trim().slice(0,30);
  for (const el of idoc.querySelectorAll(tag||'*')) {
    if (el.textContent.trim().startsWith(prefix)) return el;
  }
  return null;
}

function makeAnchor(el) {
  return { tag: el.tagName, textStart: el.textContent.trim().slice(0,50) };
}

// ── Comment pick mode ───────────────────────────────────────

document.getElementById('add-cmt-btn').addEventListener('click', enterPick);
document.getElementById('comment-btn').addEventListener('click', () => {
  pickActive ? exitPick() : enterPick();
});

function enterPick() {
  pickActive=true;
  pickOv.style.display='block';
  document.getElementById('comment-btn').classList.add('active');
  const idoc=getIdoc();
  if (idoc) idoc.body.classList.add('_stPick');
}
function exitPick() {
  pickActive=false;
  pickOv.style.display='none';
  document.getElementById('comment-btn').classList.remove('active');
  const idoc=getIdoc();
  if (idoc) idoc.body.classList.remove('_stPick');
}

document.addEventListener('keydown', e => { if(e.key==='Escape'&&pickActive) exitPick(); });

// overlay click → find element in iframe at that screen position
pickOv.addEventListener('click', e => {
  if (!pickActive) return;
  const idoc=getIdoc();
  if (!idoc) return;
  const fr = frame.getBoundingClientRect();
  const x = e.clientX - fr.left;
  const y = e.clientY - fr.top;
  const el = idoc.elementFromPoint(x, y);
  if (!el) return;
  const anchor = el.closest('h1,h2,h3,p,li,td,.callout,.card,.hero') || el;
  exitPick();
  showPop(anchor, e.clientX, e.clientY);
});

// ── Comment popover ─────────────────────────────────────────

const pop      = document.getElementById('studio-pop');
const popAnc   = document.getElementById('pop-anchor');
const popTa    = document.getElementById('pop-ta');
let   _popAnchorEl = null;

document.getElementById('pop-cancel').addEventListener('click', hidePop);
document.getElementById('pop-save').addEventListener('click', async () => {
  const text = popTa.value.trim();
  if (!text || !currentFile) return;
  comments.push({
    file: currentFile,
    anchor: _popAnchorEl ? makeAnchor(_popAnchorEl) : null,
    text,
    ts: new Date().toISOString(),
    done: false,
  });
  try { await saveComments(); } catch {/***/}
  hidePop();
  renderComments();
  injectCommentBadges(getIdoc());
});

function showPop(anchorEl, cx, cy) {
  _popAnchorEl = anchorEl;
  popAnc.textContent = anchorEl
    ? 'On: "' + anchorEl.textContent.trim().slice(0,50) + '…"'
    : '(page-level comment)';
  popTa.value='';

  const W=window.innerWidth, H=window.innerHeight;
  pop.style.left = Math.min(cx+6, W-285) + 'px';
  pop.style.top  = Math.min(cy+6, H-175) + 'px';
  pop.style.display='block';
  setTimeout(()=>popTa.focus(),30);

  // close on outside click
  setTimeout(()=>{
    document.addEventListener('click', function outsideClick(ev){
      if (!pop.contains(ev.target)){ hidePop(); document.removeEventListener('click',outsideClick); }
    });
  }, 50);
}
function hidePop(){ pop.style.display='none'; _popAnchorEl=null; }

// ═══════════════════════════════════════════════════════════════
// AUTO-RUN
// ═══════════════════════════════════════════════════════════════

document.getElementById('run-btn').addEventListener('click', async () => {
  const idoc=getIdoc();
  if (idoc) await triggerRunAll(idoc);
  else setStatus('no accessible frame loaded', 'warn');
});

function isRunnableButton(btn) {
  if (!btn || btn.disabled) return false;
  if (btn.closest('.cf-helpers,.studio-annotation,._stBadge')) return false;
  const txt = (btn.textContent || '').toLowerCase();
  return !/stop|stopping|saving|annotating/.test(txt);
}

function waitFrame() {
  return new Promise(resolve => requestAnimationFrame(() => resolve()));
}

async function waitForRunComplete(btn, timeoutMs = 180000) {
  const start = performance.now();
  await waitFrame();
  while (performance.now() - start < timeoutMs) {
    const txt = (btn.textContent || '').toLowerCase();
    if (!btn.isConnected) return;
    if (!btn.disabled && !/stop|stopping|running|saving/.test(txt)) return;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error('timed out waiting for ' + ((btn.textContent || 'run button').trim()));
}

async function triggerRunAll(idoc) {
  const btns = Array.from(idoc.querySelectorAll('.cf-btn-run,.rc-run,.cell-run'))
    .filter((btn, idx, arr) => arr.indexOf(btn) === idx)
    .filter(isRunnableButton);
  if (!btns.length) {
    runNote.textContent = 'No runnable blocks on this page.';
    return 0;
  }
  let ran = 0;
  const failures = [];
  runNote.textContent = `running 0/${btns.length} runnable block(s)`;
  for (const btn of btns) {
    if (!isRunnableButton(btn)) continue;
    btn.scrollIntoView({block:'center', behavior:'smooth'});
    btn.click();
    ran++;
    runNote.textContent = `running ${ran}/${btns.length}: ${(btn.closest('.cf-wrap,.rc-wrap,[id]')?.id || btn.textContent || 'cell').trim()}`;
    try { await waitForRunComplete(btn); }
    catch (e) {
      runNote.textContent = `stopped at ${ran}/${btns.length}: ${e.message}`;
      setStatus('run all stopped: ' + e.message, 'warn');
      return ran;
    }
    const scope = btn.closest('.cf-wrap,.rc-wrap,[id]');
    const flowFailure = scope?.querySelector('.cf-status-bar.err');
    const cellFailure = scope?.querySelector('.cf-panel-error,.cell-runtime-error');
    const failure = flowFailure || cellFailure;
    if (failure) failures.push((failure.textContent || 'runtime error').trim());
  }
  runNote.textContent = `ran ${ran}/${btns.length} runnable block(s) · ${failures.length} failed`;
  setStatus(failures.length
    ? `run all finished: ${failures.length} failed`
    : `run all complete: ${ran} runnable block(s)`, failures.length ? 'warn' : 'ok');
  return ran;
}

// ═══════════════════════════════════════════════════════════════
// AUTO-ANNOTATE
// ═══════════════════════════════════════════════════════════════

function watchRunCompletion(idoc) {
  idoc.querySelectorAll('.cf-wrap').forEach(wrap => {
    const bar = wrap.querySelector('.cf-status-bar');
    if (!bar) return;
    const obs = new MutationObserver(() => {
      if (/ran|done|complete/i.test(bar.textContent)) {
        obs.disconnect();
        wrap.querySelectorAll('.cf-panel-output').forEach(outEl => {
          const text = outEl.textContent.trim();
          if (text.length>20 && !outEl.querySelector('.studio-annotation'))
            annotateEl(outEl, text);
        });
      }
    });
    obs.observe(bar, {childList:true,characterData:true,subtree:true});
  });
}

// Inject an annotate button into each results summary (idempotent)
function injectAnnotateBtns(idoc) {
  idoc.querySelectorAll('.cf-panel-results-det').forEach(det => {
    if (det.querySelector('._stAnnBtn')) return;
    const summary = det.querySelector('summary');
    if (!summary) return;
    const btn = idoc.createElement('button');
    btn.className='_stAnnBtn';
    btn.textContent='Annotate';
    btn.title='Ask the LLM to annotate this output';
    btn.addEventListener('click', async ev => {
      ev.stopPropagation();
      const outEl = det.querySelector('.cf-panel-output');
      if (!outEl) return;
      const text=outEl.textContent.trim();
      if (!text){btn.textContent='no output';setTimeout(()=>btn.textContent='Annotate',1500);return;}
      btn.disabled=true; btn.textContent='Annotating';
      await annotateEl(outEl, text);
      btn.textContent='Annotate'; btn.disabled=false;
    });
    summary.appendChild(btn);
  });
}

async function annotateEl(outEl, outputText) {
  if (outEl.querySelector('.studio-annotation')) return;
  // Skip if no LLM route is available
  const cfg = await getConfig().catch(()=>null);
  if (!cfg) return;
  if (cfg.needsKey && !hasKey()) {
    // Don't inject a broken annotation div; just silently skip
    return;
  }

  const ann = outEl.ownerDocument.createElement('div');
  ann.className='studio-annotation ann-loading';
  ann.innerHTML='<div class="ann-head">Studio Annotation</div><span>annotating</span>';
  outEl.appendChild(ann);

  try {
    const resp = await chat({
      model: cfg.model,   // use lab model (proxy) or default (direct)
      messages:[
        {role:'system', content:ANNOTATE_SYS},
        {role:'user',   content:outputText.slice(0,2500)},
      ],
      max_tokens:1024,
      temperature:0.3,
    });
    const content = resp.choices?.[0]?.message?.content || '(no response)';
    ann.innerHTML = `<div class="ann-head">Studio Annotation</div>${esc(content)}`;
    ann.classList.remove('ann-loading');
  } catch(e) {
    ann.innerHTML = `<div class="ann-head">Studio Annotation</div><span style="opacity:.5">LLM unavailable: ${esc(e.message.slice(0,60))}</span>`;
    ann.classList.remove('ann-loading');
  }
}

// ═══════════════════════════════════════════════════════════════
// EDIT MODE & SELECTIVE SAVE
// ═══════════════════════════════════════════════════════════════

document.getElementById('edit-btn').addEventListener('click', () => {
  editActive = !editActive;
  document.getElementById('editmode-on').checked = editActive;
  document.getElementById('edit-btn').classList.toggle('active', editActive);
  const idoc=getIdoc();
  if (!idoc) return;
  editActive ? enableEditMode(idoc) : disableEditMode(idoc);
});

document.getElementById('editmode-on').addEventListener('change', e => {
  editActive = e.target.checked;
  document.getElementById('edit-btn').classList.toggle('active', editActive);
  const idoc=getIdoc();
  if (!idoc) return;
  editActive ? enableEditMode(idoc) : disableEditMode(idoc);
});

function enableEditMode(idoc) {
  idoc.body.classList.add('_stEditMode');

  // Text elements: make contentEditable (skip canvas-flow internals)
  const TEXT_SEL='h1,h2,h3,p,li,td,.callout p,.hero .lead,.eyebrow';
  idoc.querySelectorAll(TEXT_SEL).forEach(el => {
    if (el.closest('.cf-wrap,.topbar,.studio-annotation,._stBadge')) return;
    if (el.isContentEditable) return;
    const original = el.textContent;
    el.contentEditable='true';
    el.dataset.stOrig = original;
    el.addEventListener('input', ()=>{
      trackChange({type:'html', label: el.tagName+': "'+original.slice(0,28)+'"',
        oldVal:original, newVal:el.textContent});
    });
  });

  injectSaveBtns(idoc);
}

function disableEditMode(idoc) {
  idoc.body.classList.remove('_stEditMode');
  idoc.querySelectorAll('[contenteditable="true"]').forEach(el=>{
    el.contentEditable='false';
  });
}

// Save a canvas-flow node's code into its template literal in the source.
// We navigate by mountCanvasFlow() selector plus node id and replace the raw backtick content.
// ta.defaultValue is unusable here: its escapes have already been spent by the JS engine.
async function _saveNodeCode(cellSel, nodeId, newCode) {
  let content = await fetchContent();
  const bare = cellSel.replace(/^#/, '');

  // Find the mountCanvasFlow call for this cell
  let mountPos = content.indexOf(`mountCanvasFlow("#${bare}"`);
  if (mountPos < 0) mountPos = content.indexOf(`mountCanvasFlow('#${bare}'`);
  if (mountPos < 0) throw new Error(`mountCanvasFlow("${cellSel}") not found in file`);

  // Find the node by id after the mount call
  let nodePos = content.indexOf(`id: "${nodeId}"`, mountPos);
  if (nodePos < 0) nodePos = content.indexOf(`id: '${nodeId}'`, mountPos);
  if (nodePos < 0) throw new Error(`node "${nodeId}" not found in ${cellSel}`);

  // Find the code: ` template literal that follows
  const codeKey = content.indexOf('code: `', nodePos);
  if (codeKey < 0) throw new Error(`code template literal not found for node "${nodeId}"`);
  const litStart = codeKey + 'code: `'.length;

  // Walk to the matching close backtick, skipping \` escaped ones
  let litEnd = litStart;
  while (litEnd < content.length) {
    if (content[litEnd] === '`' && content[litEnd - 1] !== '\\') break;
    litEnd++;
  }
  if (litEnd >= content.length) throw new Error('no closing backtick found, so the file may be malformed');

  // Re-escape the new code for storage inside a JS template literal.
  // Backslash is escaped first so the later escapes do not double up.
  const escaped = newCode
    .replace(/\\/g, '\\\\')
    .replace(/`/g, '\\`')
    .replace(/\$\{/g, '\\${');

  await putContent(content.slice(0, litStart) + escaped + content.slice(litEnd));
}

function injectSaveBtns(idoc) {
  idoc.querySelectorAll('.cf-panel').forEach(panel => {
    if (panel.querySelector('._stSaveBtn')) return;
    const nodeId = panel.dataset.id; if (!nodeId) return;
    const head   = panel.querySelector('.cf-panel-head'); if (!head) return;

    // Resolve the mountCanvasFlow() cell selector from the mount-target id.
    // That target is the <div id="cell-…"> wrapping this .cf-wrap.
    const mountDiv = panel.closest('[id^="cell-"]');
    const cellSel  = mountDiv ? '#' + mountDiv.id : null;

    const ta = panel.querySelector('.cf-panel-code');

    const btn = idoc.createElement('button');
    btn.className='_stSaveBtn'; btn.dataset.nodeId=nodeId;
    btn.textContent='Save cell';
    btn.title='Save this cell\'s code to the source file (only this cell)';
    head.appendChild(btn);

    btn.addEventListener('click', async () => {
      const cmEl = panel.querySelector('.cf-code-view[data-lang="js"] .CodeMirror');
      const cm   = cmEl?.CodeMirror;
      const codeEl = panel.querySelector('.cf-panel-code code, .cf-code-view code');
      const newCode = cm ? cm.getValue() : (ta?.value || codeEl?.textContent || '');
      if (!newCode) { btn.textContent='no change'; setTimeout(()=>btn.textContent='Save cell',1500); return; }

      btn.disabled=true; btn.textContent='saving';
      try {
        if (cellSel) {
          await _saveNodeCode(cellSel, nodeId, newCode);
        } else {
          // Fallback for non-canvas-flow textareas (plain text, no template literal)
          const orig = ta ? ta.defaultValue : '';
          await doSingleSave(orig, newCode);
        }
        btn.textContent='saved'; btn.classList.add('ok');
        setTimeout(()=>{btn.textContent='Save cell';btn.classList.remove('ok');btn.disabled=false;},2000);
      } catch(e) {
        btn.textContent=e.message.slice(0,40); btn.disabled=false;
      }
    });
  });
}

// ─── Pending-changes tracking ────────────────────────────────

function trackChange(ch) {
  // Deduplicate by oldVal
  const existing = pendingChgs.find(c=>c.oldVal===ch.oldVal);
  if (existing) { existing.newVal=ch.newVal; renderPending(); return; }
  pendingChgs.push({id:'chg-'+Date.now(), checked:true, ...ch});
  renderPending();
}

function renderPending() {
  if (!pendingChgs.length) {
    chgList.innerHTML='<div class="empty-hint">No pending edits.</div>';
    saveSelBtn.disabled=true;
    return;
  }
  chgList.innerHTML='';
  pendingChgs.forEach((ch,i)=>{
    const div=document.createElement('div');
    div.className='chg-item';
    div.innerHTML=`
      <input type="checkbox" ${ch.checked?'checked':''} data-i="${i}"/>
      <div class="chg-label">
        <div>${esc(ch.label)}</div>
        ${ch.type==='html'
          ? `<div class="chg-diff">"${esc(ch.oldVal.slice(0,22))}…" → "${esc(ch.newVal.slice(0,22))}…"</div>`
          : ''}
      </div>`;
    div.querySelector('input').addEventListener('change',e=>{pendingChgs[i].checked=e.target.checked;});
    chgList.appendChild(div);
  });
  saveSelBtn.disabled=false;
}

// ─── Save logic ───────────────────────────────────────────────

saveSelBtn.addEventListener('click', async()=>{
  const toSave = pendingChgs.filter(c=>c.checked);
  if (!toSave.length||!currentFile) return;
  saveSelBtn.disabled=true; saveSelBtn.textContent='saving';
  try {
    let content = await fetchContent();
    for (const ch of toSave) {
      if (content.includes(ch.oldVal)) content=content.replace(ch.oldVal, ch.newVal);
      else console.warn('Studio: text not found in file:', ch.oldVal.slice(0,40));
    }
    await putContent(content);
    pendingChgs = pendingChgs.filter(c=>!c.checked);
    renderPending();
    setStatus('saved '+toSave.length+' change(s)', 'ok');
  } catch(e) {
    setStatus('save failed: '+e.message, 'warn');
  }
  saveSelBtn.textContent='Save checked';
  saveSelBtn.disabled=pendingChgs.length===0;
});

async function doSingleSave(oldVal, newVal) {
  let content = await fetchContent();
  if (!content.includes(oldVal))
    throw new Error('original text not found. Reload and try again');
  content = content.replace(oldVal, newVal);
  await putContent(content);
}

// ═══════════════════════════════════════════════════════════════
// SIDEBAR TOGGLE & SECTION COLLAPSING
// ═══════════════════════════════════════════════════════════════

document.getElementById('sidebar-btn').addEventListener('click',()=>{
  sidebar.classList.toggle('collapsed');
});

document.querySelectorAll('.sb-head[data-sec]').forEach(head=>{
  const body=document.getElementById('sec-'+head.dataset.sec);
  head.addEventListener('click',()=>{ if(body) body.classList.toggle('hidden'); });
});

// ═══════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════

async function init() {
  observeStudioUi(document);
  await resolveContentApi(MODULES[0]?.file || 'index.html');
  await loadComments();
  renderTestCommands();

  // Honour ?page= query param
  const p = new URLSearchParams(location.search).get('page');
  loadPage(p || MODULES[0].file);
}

init();
