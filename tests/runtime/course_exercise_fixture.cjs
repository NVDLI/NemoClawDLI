// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

function discoverCourses(root) {
  const web = path.join(root, 'web');
  const courses = fs.readdirSync(web, {withFileTypes:true})
    .filter(entry => entry.isDirectory())
    .map(entry => path.join(web, entry.name))
    .filter(directory => fs.existsSync(path.join(directory, 'scripts/_shared.js')));
  assert.equal(courses.length, 1, 'Expected one shared-runtime course');
  const canonical = courses[0];
  const roots = [canonical];
  const locales = process.env.NEMOCLAW_LOCALE_PAGES;
  if (locales) {
    for (const {metadata} of localeMetadata(root)) {
      const candidates = [path.join(locales, metadata.url_code, 'web', path.basename(canonical)),
        path.join(locales, metadata.url_code, path.basename(canonical))];
      const course = candidates.find(directory => fs.existsSync(directory));
      assert(course, `Missing materialized locale course for ${metadata.locale}: ${candidates.join(' or ')}`);
      roots.push(course);
    }
  }
  return {roots};
}

function localeMetadata(root) {
  const directory = path.join(root, 'i18n');
  const locales = fs.readdirSync(directory, {withFileTypes:true}).filter(entry => entry.isDirectory())
    .map(entry => path.join(directory, entry.name, 'locale.json'))
    .sort().map(file => {
      assert(fs.existsSync(file), `Missing locale metadata: ${file}`);
      const metadata = JSON.parse(fs.readFileSync(file, 'utf8'));
      assert.equal(metadata.schema, 'nemoclaw-locale/1', `Unknown locale metadata schema: ${file}`);
      assert(typeof metadata.locale === 'string' && metadata.locale.length
        && typeof metadata.url_code === 'string' && /^[a-z][a-z0-9-]*$/i.test(metadata.url_code), `Invalid locale metadata: ${file}`);
      return {file, metadata};
    });
  assert.equal(new Set(locales.map(({metadata})=>metadata.url_code)).size, locales.length, 'Duplicate locale URL ownership');
  assert.equal(new Set(locales.map(({metadata})=>metadata.locale)).size, locales.length, 'Duplicate locale language ownership');
  return locales;
}

// Expectations are translated from exact resource entries. Executable source is
// always the unmodified materialized page; this helper never rewrites its code.
function courseLanguage(root, course, pages) {
  const canonical = path.resolve(root, 'web', path.basename(course));
  if (path.resolve(course) === canonical) return {label:'en', text:source=>source, match:pattern=>pattern};
  const metadata = localeMetadata(root).filter(({metadata}) =>
    [path.join(process.env.NEMOCLAW_LOCALE_PAGES, metadata.url_code, 'web', path.basename(course)),
      path.join(process.env.NEMOCLAW_LOCALE_PAGES, metadata.url_code, path.basename(course))]
      .some(directory => path.resolve(directory) === path.resolve(course)));
  assert.equal(metadata.length, 1, `Locale ownership is ambiguous for ${course}`);
  const owner = metadata[0];
  const entries = pages.flatMap(page => {
    const resource = path.join(path.dirname(owner.file), 'resources', 'web', path.basename(course), page + '.json');
    const data = JSON.parse(fs.readFileSync(resource, 'utf8'));
    assert.equal(data.locale, owner.metadata.locale, `Resource locale mismatch: ${resource}`);
    return Object.entries(data.values).map(([key, entry]) => ({key, resource, ...entry}));
  });
  const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return {
    label:owner.metadata.locale,
    text(source) {
      const matches = entries.filter(entry => entry.source === source);
      assert(matches.length, `Missing exact diagnostic source in ${owner.metadata.locale}: ${source}`);
      const values = [...new Set(matches.map(entry => entry.value))];
      assert.equal(values.length, 1, `Ambiguous diagnostic resources: ${matches.map(entry=>entry.resource+'#'+entry.key).join(', ')}`);
      return values[0];
    },
    match(pattern, external = []) {
      const matches = entries.filter(entry => {pattern.lastIndex=0;return pattern.test(entry.source);});
      assert(matches.length || external.length, `No diagnostic resource matches ${pattern} in ${owner.metadata.locale}`);
      const values = [...new Set([...matches.map(entry => entry.value), ...external])];
      assert(values.every(value => typeof value === 'string' && value.length), 'Empty diagnostic expectation');
      return new RegExp(values.map(escape).join('|'));
    },
  };
}

module.exports = {discoverCourses, courseLanguage};
