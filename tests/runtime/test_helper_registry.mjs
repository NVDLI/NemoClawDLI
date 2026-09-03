// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import { sharedRuntime, canvasRuntime, localeRuntime } from './course_runtime_fixture.mjs';

const { HELPER_FNS, SPECIALS, VIZ_BUILDERS } = sharedRuntime;
const { HELPER_CATEGORIES, containNestedWheel, helperDocumentationGaps, helperMenuOrphans } = canvasRuntime;
const SHIPPED_LOCALES = fs.readdirSync(new URL('../../scripts/translate/locales/', import.meta.url), { withFileTypes: true })
  .filter(entry => entry.isDirectory())
  .map(entry => JSON.parse(fs.readFileSync(new URL(`../../scripts/translate/locales/${entry.name}/profile.json`, import.meta.url), 'utf8')).html_lang)
  .sort();
const RUNTIME_UI_LITERALS = new Set(fs.readdirSync(new URL('../../web/nemoclaw/scripts/', import.meta.url))
  .filter(name => name.endsWith('.js'))
  .flatMap(name => [...fs.readFileSync(new URL(`../../web/nemoclaw/scripts/${name}`, import.meta.url), 'utf8')
    .matchAll(/localizeCourseUiText\(\s*(["'])(.*?)\1\s*\)/gs)].map(match => match[2])));

test('every exposed course helper has a reviewed menu category', () => {
  assert.deepEqual(helperMenuOrphans(), []);
});

test('an unclassified helper mutation is rejected without a maintained count', () => {
  const helperFns = { ...HELPER_FNS, newlyIntroducedHelper() {} };
  assert.deepEqual(helperMenuOrphans({ helperFns }), ['newlyIntroducedHelper']);
});

test('removing a helper from its category is rejected', () => {
  const categories = HELPER_CATEGORIES.map(([heading, helpers]) => [
    heading,
    helpers.filter(name => name !== 'chat'),
  ]);
  assert.deepEqual(helperMenuOrphans({ categories }), ['chat']);
});

test('every exposed helper has a signature and description', () => {
  assert.deepEqual(helperDocumentationGaps(), []);
});

test('helper documentation discovery rejects novel and malformed functions', () => {
  const helperFns = { ...HELPER_FNS, newlyIntroducedHelper() {} };
  assert.deepEqual(helperDocumentationGaps({ helperFns }).find(item => item.name === 'newlyIntroducedHelper'), {
    name: 'newlyIntroducedHelper', missing: ['signature', 'description'],
  });
  helperFns.newlyIntroducedHelper = function () { /* @docs <code>helpers.newlyIntroducedHelper()</code> :: hidden typo */ };
  assert.deepEqual(helperDocumentationGaps({ helperFns }).find(item => item.name === 'newlyIntroducedHelper').missing, ['signature', 'description']);
});

test('renamed and deleted helpers cannot retain stale documentation contracts', () => {
  const { chat, ...withoutChat } = HELPER_FNS;
  assert.equal(helperDocumentationGaps({ helperFns: withoutChat }).some(item => item.name === 'chat'), false);
  const helperFns = { ...withoutChat, hat: chat };
  assert.deepEqual(helperDocumentationGaps({ helperFns }).find(item => item.name === 'hat'), {
    name: 'hat', missing: ['signature-name'],
  });
});

test('every discovered helper has a localized description in every shipped locale', () => {
  const originalDocument = globalThis.document;
  const names = new Set([
    ...Object.keys(HELPER_FNS), ...Object.keys(SPECIALS),
    ...Object.keys(VIZ_BUILDERS).map(name => `viz.${name}`),
  ]);
  try {
    for (const locale of SHIPPED_LOCALES) {
      globalThis.document = { documentElement: { lang: locale } };
      localeRuntime.clearCourseLocaleMisses();
      for (const name of names) {
        const source = `English description for ${name}`;
        const translated = localeRuntime.localizeCourseHelperDescription(name, source);
        assert.ok(translated.trim(), `${locale} ${name} has no description`);
        assert.notEqual(translated, source, `${locale} ${name} retains English fallback`);
      }
      assert.deepEqual(localeRuntime.courseLocaleMisses(), []);
    }
  } finally {
    globalThis.document = originalDocument;
  }
});

test('a novel helper cannot silently inherit English in any shipped locale', () => {
  const originalDocument = globalThis.document;
  try {
    for (const locale of SHIPPED_LOCALES) {
      globalThis.document = { documentElement: { lang: locale } };
      localeRuntime.clearCourseLocaleMisses();
      assert.equal(localeRuntime.localizeCourseHelperDescription('newlyIntroducedHelper', 'English fallback'), 'English fallback');
      assert.deepEqual(localeRuntime.courseLocaleMisses(), ['helper:newlyIntroducedHelper']);
    }
  } finally {
    globalThis.document = originalDocument;
  }
});

test('unknown runtime prose fails closed without partial substitution', () => {
  const originalDocument = globalThis.document;
  try {
    for (const locale of SHIPPED_LOCALES) {
      globalThis.document = { documentElement: { lang: locale } };
      localeRuntime.clearCourseLocaleMisses();
      const source = 'Novel untranslated sentence containing Run all and clear.';
      assert.equal(localeRuntime.localizeCourseUiText(source), source);
      assert.deepEqual(localeRuntime.courseLocaleMisses(), [source]);
    }
  } finally {
    globalThis.document = originalDocument;
  }
});

test('every discovered runtime UI literal is translated in every shipped locale', () => {
  const originalDocument = globalThis.document;
  try {
    for (const locale of SHIPPED_LOCALES) {
      globalThis.document = { documentElement: { lang: locale } };
      localeRuntime.clearCourseLocaleMisses();
      for (const source of RUNTIME_UI_LITERALS) {
        assert.notEqual(localeRuntime.localizeCourseUiText(source), source, `${locale} retains ${source}`);
      }
      assert.deepEqual(localeRuntime.courseLocaleMisses(), []);
    }
  } finally {
    globalThis.document = originalDocument;
  }
});

test('parameterized helper controls are translated in every shipped locale', () => {
  const originalDocument = globalThis.document;
  const sources = [
    '+ show all 17 more helpers', "− show only this section's helpers", "− show only this cell's helpers",
    'javascript · editable · 143 lines', '✓ ran 17 nodes', '⏹ stopped after 3 of 17 nodes',
    'done in 4.2s', 'context 900 / 2048 (44%)', '✗ stopped at Health check', '🧠 reasoning · ~320 tok',
  ];
  try {
    for (const locale of SHIPPED_LOCALES) {
      globalThis.document = { documentElement: { lang: locale } };
      localeRuntime.clearCourseLocaleMisses();
      for (const source of sources) assert.notEqual(localeRuntime.localizeCourseUiText(source), source, `${locale} retains ${source}`);
      assert.deepEqual(localeRuntime.courseLocaleMisses(), []);
    }
  } finally {
    globalThis.document = originalDocument;
  }
});

test('every nested scroll surface contains wheel chaining', () => {
  const css = fs.readFileSync(new URL('../../web/nemoclaw/styles/_style.css', import.meta.url), 'utf8');
  const containsNestedScroll = source => /body\s+\*\s*\{[^}]*overscroll-behavior:\s*contain/s.test(source);
  assert.equal(containsNestedScroll(css), true);
  assert.equal(containsNestedScroll(css.replace(/body\s+\*\s*\{[^}]*overscroll-behavior:\s*contain;?[^}]*\}/s, '')), false);
  let wheel;
  const node = { scrollHeight: 500, clientHeight: 200, scrollTop: 300,
    addEventListener: (type, listener, options) => { assert.equal(type, 'wheel'); assert.deepEqual(options, { passive: false, capture: true }); wheel = listener; } };
  containNestedWheel(node);
  let prevented = false;
  wheel({ deltaY: 1, preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);
  node.scrollTop = 150; prevented = false;
  wheel({ deltaY: 1, preventDefault: () => { prevented = true; } });
  assert.equal(prevented, false);
});

test('diagram renderer wraps and bounds long localized labels', () => {
  const svg = HELPER_FNS.diagramSVG({
    boxW: 180,
    nodes: [
      { id: 'latin', x: 0, y: 0, kind: 'agent', label: 'localized agent tool call label that exceeds forty characters', lines: ['bounded body'] },
      { id: 'cjk', x: 1, y: 0, kind: 'tool', label: '本地化后的智能体工具调用标签必须保持在卡片内部', lines: ['每轮都会读取完整策略配置'] },
    ],
    edges: [{ from: 'latin', to: 'cjk', label: 'localized network and filesystem boundary label' }],
  });
  assert.ok((svg.match(/font-weight="800"/g) || []).length >= 4);
  assert.match(svg, /font-style="italic" textLength="\d+" lengthAdjust="spacingAndGlyphs"/);
});
