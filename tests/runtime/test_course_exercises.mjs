// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import os from 'node:os';
import {discoverCourses, courseLanguage} from './course_exercise_fixture.cjs';

const directory = path.dirname(fileURLToPath(import.meta.url));
const root = process.env.COURSE_SOURCE_ROOT || path.resolve(directory, '../..');

test('locale execution discovery follows metadata and rejects missing or malformed owners', () => {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'course-contract-locales-'));
  const previous = process.env.NEMOCLAW_LOCALE_PAGES;
  const write = (file, value) => {
    fs.mkdirSync(path.dirname(file), {recursive:true});
    fs.writeFileSync(file, typeof value === 'string' ? value : JSON.stringify(value));
  };
  try {
    const pages = path.join(temporary, 'pages');
    process.env.NEMOCLAW_LOCALE_PAGES = pages;
    write(path.join(temporary, 'web', 'novel-course', 'scripts', '_shared.js'), '');
    const metadata = path.join(temporary, 'i18n', 'new-language', 'locale.json');
    write(metadata, {schema:'nemoclaw-locale/1', locale:'xy-ZZ', url_code:'novel'});
    const localized = path.join(pages, 'novel', 'web', 'novel-course');
    fs.mkdirSync(localized, {recursive:true});
    const resource = path.join(path.dirname(metadata), 'resources', 'web', 'novel-course', 'nested', 'new.html.json');
    write(resource, {locale:'xy-ZZ', values:{'text.new':{source:'Expected (answer).', value:'Respuesta [exacta] (1).'}}});
    assert.deepEqual(discoverCourses(temporary).roots, [path.join(temporary, 'web', 'novel-course'), localized]);
    const language = courseLanguage(temporary, localized, ['nested/new.html']);
    assert.equal(language.text('Expected (answer).'), 'Respuesta [exacta] (1).');
    assert.match('Error: Respuesta [exacta] (1).', language.match(/Expected/));
    assert.doesNotMatch('Respuesta e (1)x', language.match(/Expected/));
    assert.throws(()=>language.text('Unlisted error'), /Missing exact diagnostic source/);
    assert.throws(()=>language.match(/Unlisted error/), /No diagnostic resource/);
    fs.renameSync(path.dirname(metadata), path.join(temporary, 'i18n', 'renamed-owner'));
    assert.equal(discoverCourses(temporary).roots.length, 2);
    fs.rmSync(localized, {recursive:true});
    assert.throws(()=>discoverCourses(temporary), /Missing materialized locale course/);
    fs.mkdirSync(path.join(pages, 'novel', 'novel-course'), {recursive:true});
    assert.equal(discoverCourses(temporary).roots.length, 2, 'published layout is also supported');
    const renamedMetadata = path.join(temporary, 'i18n', 'renamed-owner', 'locale.json');
    write(renamedMetadata, {schema:'nemoclaw-locale/near-match', locale:'xy-ZZ', url_code:'novel'});
    assert.throws(()=>discoverCourses(temporary), /Unknown locale metadata schema/);
    fs.rmSync(renamedMetadata);
    assert.throws(()=>discoverCourses(temporary), /Missing locale metadata/);
  } finally {
    if(previous === undefined) delete process.env.NEMOCLAW_LOCALE_PAGES;
    else process.env.NEMOCLAW_LOCALE_PAGES = previous;
    fs.rmSync(temporary, {recursive:true, force:true});
  }
});

const contracts = fs.readdirSync(directory).filter(name => /^test_.*_contract\.cjs$/.test(name)).sort();
assert(contracts.length, 'No displayed-course execution contracts discovered');
for (const name of contracts) {
  test(`displayed course code: ${name}`, () => {
    const env = {...process.env, COURSE_SOURCE_ROOT:root};
    // This child is collected through stdout, not the parent's test-runner IPC.
    // Inheriting this marker would emit a binary event stream on failures.
    delete env.NODE_TEST_CONTEXT;
    const result = spawnSync(process.execPath, [path.join(directory, name)], {
      cwd:root,
      env,
      encoding:'utf8',
      timeout:60000,
    });
    assert.equal(result.status, 0, result.error?.message || result.stderr || result.stdout);
  });
}
