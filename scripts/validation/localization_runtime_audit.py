#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Discover and browser-check every built learner page in every locale."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.runtime.host_browser import BrowserRuntimeError, environment, run_node
from scripts.translate.locale_catalog import discover_locales


RUNTIME = r"""
const http = require('http'), fs = require('fs'), path = require('path');
const { chromium } = require('playwright-core');
const root = path.resolve(process.env.SITE_ROOT), shots = process.env.SHOTS, port = 4197;
const profiles = JSON.parse(process.env.LOCALE_PROFILES);
const learnerPages = JSON.parse(process.env.LEARNER_PAGES);
const mime = {'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.svg':'image/svg+xml','.ico':'image/x-icon'};
const server = http.createServer((req, res) => {
  let file = path.resolve(root, decodeURIComponent(req.url.split('?')[0]).replace(/^\/+/, ''));
  if (!file.startsWith(root)) { res.writeHead(403); return res.end(); }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  fs.readFile(file, (error, data) => {
    if (error) { res.writeHead(404); return res.end('not found'); }
    res.writeHead(200, {'content-type': mime[path.extname(file)] || 'application/octet-stream'}); res.end(data);
  });
});
const findings = [];
const record = (code, route, detail) => findings.push({code, route, detail});
async function capture(code, route, run) {
  try { return await run(); }
  catch (error) { record(code, route, error.stack || String(error)); return null; }
}

function localizedFigurePages(language) {
  const base = path.resolve(root, language.url);
  return language.available_pages.filter(file => {
    const candidate = path.resolve(base, file);
    const relative = path.relative(base, candidate);
    return !relative.startsWith('..') && !path.isAbsolute(relative) && fs.existsSync(candidate) && fs.readFileSync(candidate, 'utf8').includes('data-svg-src');
  });
}

async function open(page, route) {
  const errors = [];
  page.removeAllListeners();
  page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('response', response => { if (response.status() >= 400) errors.push(`HTTP ${response.status()}: ${response.url()}`); });
  await page.goto(`http://127.0.0.1:${port}${route}`, {waitUntil:'domcontentloaded'});
  await page.waitForTimeout(350);
  errors.forEach(detail => record('browser-error', route, detail));
}

async function inspect(page, language, file, viewport, sourceUi, isDefault) {
  const route = `/${language.url.replace(/^\/+|\/+$/g, '')}/${file}`;
  await page.setViewportSize(viewport);
  await open(page, route);
  const result = await page.evaluate(async ({profile, expectedLang, sourceUi, isDefault}) => {
    document.querySelectorAll('details').forEach(node => { node.open = true; });
    document.querySelectorAll('.cf-helpers-showall[aria-expanded="false"]').forEach(node => node.click());
    await new Promise(resolve => setTimeout(resolve, 50));
    document.querySelector('.language-menu-button')?.click();
    await new Promise(resolve => setTimeout(resolve, 20));
    const localized = await import(new URL('./scripts/_locale.js', location.href));
    const skip = 'pre,code,textarea,script,style,svg,a[href^="http"],[data-preserve-language],.CodeMirror,.cm-editor,.cf-det-sig,[data-code-meta]';
    const controls = 'button,label,option,summary,[role="button"],[role="tab"],[role="menuitem"]';
    const words = new Set((profile.english_function_words || []).map(word => word.toLowerCase()));
    const threshold = Number(profile.english_function_word_threshold || 0);
    const preserved = [...(profile.canonical_english_titles || []), ...(profile.allowed_english_tokens || [])].sort((a, b) => b.length - a.length);
    const isPreserved = value => {
      if (/^(?:https?:\/\/\S+|(?:GET|POST|PUT|PATCH|DELETE)\s+\/\S+|nvapi-\S+|Apache-2\.0|[\w.-]+\/[\w./-]+|[A-Za-z]\w*(?:_[A-Za-z]\w*)+)$/.test(value)) return true;
      let remaining = value;
      for (const term of preserved) remaining = remaining.split(term).join(' ');
      return !/[A-Za-z]{3}/.test(remaining);
    };
    const residues = [];
    const uiText = [];
    const walker = document.createTreeWalker(document.querySelector('main') || document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const parent = walker.currentNode.parentElement;
      if (!parent || parent.closest(skip)) continue;
      const text = walker.currentNode.nodeValue.replace(/\s+/g, ' ').trim();
      if (text && parent.closest(controls)) uiText.push(text);
    }
    for (const element of (document.querySelector('main') || document.body).querySelectorAll('[placeholder],[title],[aria-label]')) {
      if (element.closest(skip)) continue;
      for (const name of ['placeholder', 'title', 'aria-label']) {
        const text = (element.getAttribute(name) || '').replace(/\s+/g, ' ').trim();
        if (text) uiText.push(text);
      }
    }
    if (!isDefault && threshold && words.size) {
      for (let text of uiText) {
        for (const allowed of [...(profile.canonical_english_titles || []), ...(profile.allowed_english_tokens || [])]) text = text.split(allowed).join(' ');
        const count = (text.toLowerCase().match(/[a-z]+/g) || []).filter(word => words.has(word)).length;
        if (count >= threshold) residues.push(text.slice(0, 240));
      }
    }
    const helpers = [...document.querySelectorAll('tr[data-helper]')].map(row => ({
      name: row.dataset.helper,
      signature: row.cells[0]?.textContent.trim() || '',
      description: row.cells[1]?.textContent.trim() || '',
    }));
    const scrollLeaks = [...document.querySelectorAll('body *')].flatMap(node => {
      const style = getComputedStyle(node), x = node.scrollWidth > node.clientWidth + 1, y = node.scrollHeight > node.clientHeight + 1;
      if ((!x && !y) || !/(auto|scroll)/.test(`${style.overflowX} ${style.overflowY}`)) return [];
      if ((!x || style.overscrollBehaviorX === 'contain') && (!y || style.overscrollBehaviorY === 'contain')) return [];
      return [`${node.tagName}.${String(node.className || '').replace(/\s+/g,'.').slice(0,100)}`];
    });
    const diagramEscapes = [...new Set(document.querySelectorAll('[data-svg-src] svg,svg.dg-svg'))].flatMap(svg => {
      const cards = [...svg.querySelectorAll('rect')].filter(node => {
        const stroke = node.getAttribute('stroke');
        return node.hasAttribute('rx') || node.hasAttribute('ry') || (stroke && stroke !== 'none');
      }).map(node => node.getBoundingClientRect()).filter(box => box.width > 20 && box.height > 15);
      return [...svg.querySelectorAll('text')].flatMap(node => {
        const box = node.getBoundingClientRect(), cx = box.left + box.width / 2, cy = box.top + box.height / 2;
        const card = cards.filter(item => item.left <= cx && cx <= item.right && item.top <= cy && cy <= item.bottom).sort((a,b) => a.width*a.height-b.width*b.height)[0];
        return card && (box.left < card.left - 2 || box.right > card.right + 2 || box.top < card.top - 2 || box.bottom > card.bottom + 2) ? [node.textContent.trim()] : [];
      });
    });
    return {
      lang: document.documentElement.lang,
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      residues: [...new Set(residues)],
      emptyHelpers: helpers.filter(item => !item.signature || !item.description),
      misses: localized.courseLocaleMisses(),
      scrollLeaks: [...new Set(scrollLeaks)],
      diagramEscapes: [...new Set(diagramEscapes)],
      languageMenuClipped: [...document.querySelectorAll('.language-menu-popover a')].some(node => {
        const box = node.getBoundingClientRect();
        return box.left < 0 || box.top < 0 || box.right > innerWidth || box.bottom > innerHeight;
      }),
      untranslatedUi: isDefault ? [] : [...new Set(uiText.filter(text =>
        sourceUi.includes(text) && /[A-Za-z]{3}/.test(text) && !text.startsWith('/') && !isPreserved(text)))],
      expectedLang,
    };
  }, {profile: profiles[language.code] || {}, expectedLang: language.locale, sourceUi, isDefault});
  if (result.lang !== result.expectedLang) record('html-lang', route, `${result.lang} != ${result.expectedLang}`);
  if (result.overflow > 2) record('page-overflow', route, `${result.overflow}px at ${viewport.width}px`);
  if (result.languageMenuClipped) record('language-menu-layout', route, 'language-menu entries are clipped');
  for (const [code, values] of Object.entries({
    'mixed-language': result.residues,
    'helper-documentation': result.emptyHelpers.map(item => `${item.name}: ${item.signature ? 'description' : 'signature'}`),
    'runtime-locale-miss': result.misses,
    'scroll-chain': result.scrollLeaks,
    'diagram-overflow': result.diagramEscapes.map(value => `${value} has labels outside their cards`),
    'untranslated-ui': result.untranslatedUi,
  })) values.forEach(detail => record(code, route, detail));
}

async function inspectLocalizationStudio(page, manifest, language) {
  const primary = manifest.languages.find(item => item.code === manifest.default);
  if (!primary?.available_pages.includes('localization.html')) return;
  const route = `/${primary.url.replace(/^\/+|\/+$/g, '')}/localization.html?locale=${encodeURIComponent(language.code)}`;
  await open(page, route);
  const ready = await page.locator('#loc-source,#loc-target').count();
  if (ready !== 2) record('localization-studio', route, 'Localization Studio did not render both comparison frames');
}

async function wheelProbe(page, language, files) {
  await page.setViewportSize({width:1280,height:900});
  for (const file of files) {
    const route = `/${language.url.replace(/^\/+|\/+$/g, '')}/${file}`;
    await open(page, route);
    const helpers = page.locator('details.cf-helpers').filter({has: page.locator('tr[data-helper]')}).first();
    if (!await helpers.count()) continue;
    await helpers.evaluate(node => {
      for (let current = node; current; current = current.parentElement) {
        if (current.tagName === 'DETAILS') current.open = true;
      }
    });
    const showAll = helpers.locator('.cf-helpers-showall:visible').first();
    if (await showAll.count()) await showAll.click();
    const helper = helpers.locator('tr[data-helper]:visible').first();
    if (!await helper.count()) continue;
    await helper.click();
    const editor = helpers.locator('tr.cf-helpers-source-row:visible .CodeMirror-scroll').first();
    if (!await editor.count()) continue;
    await editor.evaluate(node => { node.scrollTop = node.scrollHeight; node.scrollIntoView({block:'center'}); });
    await editor.hover();
    await page.waitForTimeout(500);
    const before = await page.evaluate(() => scrollY);
    await page.mouse.wheel(0, 480); await page.waitForTimeout(100);
    const after = await page.evaluate(() => scrollY);
    if (Math.abs(after - before) > 2) record('scroll-chain-wheel', route, `${before} -> ${after}`);
    return;
  }
  record('wheel-probe-missing', language.code, 'no discovered learner page exposes a helper editor');
}

(async () => {
  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'languages.json'), 'utf8'));
  const languages = manifest.languages;
  const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_BIN});
  const page = await browser.newPage();
  const primary = manifest.languages.find(item => item.code === manifest.default);
  const primaryPages = learnerPages;
  const sourceUi = {};
  for (const file of primaryPages) {
    const route = `/${primary.url.replace(/^\/+|\/+$/g, '')}/${file}`;
    console.log(`[locale-runtime] source ${route}`);
    await capture('source-inspection', route, async () => {
      await open(page, route);
      sourceUi[file] = await page.evaluate(() => {
        const skip = 'pre,code,textarea,script,style,svg,a[href^="http"],[data-preserve-language],.CodeMirror,.cm-editor,.cf-det-sig,[data-code-meta]';
        const controls = 'button,label,option,summary,[role="button"],[role="tab"],[role="menuitem"]';
        const values = [], walker = document.createTreeWalker(document.querySelector('main') || document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          const parent = walker.currentNode.parentElement;
          if (!parent || parent.closest(skip)) continue;
          const text = walker.currentNode.nodeValue.replace(/\s+/g, ' ').trim();
          if (text && parent.closest(controls)) values.push(text);
        }
        for (const element of (document.querySelector('main') || document.body).querySelectorAll('[placeholder],[title],[aria-label]')) {
          if (element.closest(skip)) continue;
          for (const name of ['placeholder', 'title', 'aria-label']) {
            const text = (element.getAttribute(name) || '').replace(/\s+/g, ' ').trim();
            if (text) values.push(text);
          }
        }
        return [...new Set(values)];
      });
    });
  }
  for (const language of languages) {
    if (language.code !== manifest.default && !profiles[language.code]) {
      record('locale-profile', language.code, 'missing browser audit profile'); continue;
    }
    const available = new Set(language.available_pages);
    const missing = primaryPages.filter(file => !available.has(file));
    if (missing.length) record('locale-page-parity', language.code, `missing learner pages: ${missing.join(', ')}`);
    const pages = [...new Set([...primaryPages, ...localizedFigurePages(language)])].sort();
    if (!pages.length) { record('locale-pages', language.code, 'no discovered learner pages'); continue; }
    for (const file of pages) {
      const route = `/${language.url.replace(/^\/+|\/+$/g, '')}/${file}`;
      const isDefault = language.code === manifest.default;
      console.log(`[locale-runtime] ${language.code} ${route}`);
      await capture('page-inspection', route, () => inspect(page, language, file, {width:1280,height:900}, sourceUi[file] || [], isDefault));
      await capture('page-inspection', route, () => inspect(page, language, file, {width:390,height:844}, sourceUi[file] || [], isDefault));
    }
    const lessons = pages.filter(file => /^\d{2}[a-z]-/.test(file));
    if (lessons.length) await capture('wheel-probe', language.code, () => wheelProbe(page, language, lessons));
    if (language.code !== manifest.default) {
      await capture('localization-studio', language.code, () => inspectLocalizationStudio(page, manifest, language));
    }
    await capture('locale-screenshot', language.code, async () => {
      await open(page, `/${language.url.replace(/^\/+|\/+$/g, '')}/${pages[0]}`);
      await page.screenshot({path:path.join(shots, `${language.code}-learner-page.png`), fullPage:false, animations:'disabled'});
    });
  }
  await browser.close(); server.close();
  if (findings.length) throw new Error(JSON.stringify(findings, null, 2));
  console.log(JSON.stringify({ok:true, locales:languages.map(item => item.code), screenshots:fs.readdirSync(shots).sort()}));
})().catch(error => { try { server.close(); } catch (_) {} console.error(error.stack || String(error)); process.exit(1); });
"""


LESSON_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$", re.IGNORECASE)


def discover_learner_pages(site: Path, manifest: dict) -> list[str]:
    """Resolve learner routes from the built course's explicit learning profile."""
    languages = manifest.get("languages")
    if not isinstance(languages, list):
        raise ValueError("languages.json has no languages list")
    primary = next((item for item in languages if item.get("code") == manifest.get("default")), None)
    if not isinstance(primary, dict) or not isinstance(primary.get("url"), str):
        raise ValueError("languages.json has no valid default-language route")
    course = (site / primary["url"]).resolve()
    if site != course and site not in course.parents:
        raise ValueError("default-language route escapes the site root")
    profile_path = course / "learning-profile.json"
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{profile_path}: invalid learning profile: {exc}") from exc
    lessons = profile.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        raise ValueError(f"{profile_path}: no lessons declared")
    ids = [item.get("id") if isinstance(item, dict) else None for item in lessons]
    invalid = [value for value in ids if not isinstance(value, str) or not LESSON_ID.fullmatch(value)]
    if invalid:
        raise ValueError(f"{profile_path}: invalid lesson ids: {invalid}")
    if len(ids) != len(set(ids)):
        raise ValueError(f"{profile_path}: duplicate lesson ids")
    return sorted(["index.html", *(f"{lesson_id}.html" for lesson_id in ids)])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-root", default="/tmp/course-localization-pages")
    parser.add_argument("--screenshots", default="/tmp/course-localization-screenshots")
    args = parser.parse_args()
    site, shots = Path(args.site_root).resolve(), Path(args.screenshots).resolve()
    shots.mkdir(parents=True, exist_ok=True)
    try:
        manifest = json.loads((site / "languages.json").read_text(encoding="utf-8"))
        learner_pages = discover_learner_pages(site, manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"localization runtime audit: FAIL\n  - {exc}")
        return 1
    profiles = {
        spec.url_code: {
            key: spec.profile.get(key, [] if key != "english_function_word_threshold" else 0)
            for key in ("english_function_words", "english_function_word_threshold", "allowed_english_tokens", "canonical_english_titles")
        }
        for spec in discover_locales(ROOT)
    }
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as handle:
        handle.write(RUNTIME)
        script = Path(handle.name)
    try:
        language_count = len(manifest["languages"])
        timeout = max(240, 5 * len(learner_pages) * (1 + 2 * language_count))
        run = run_node(script, env=environment(
            SITE_ROOT=site, SHOTS=shots, LOCALE_PROFILES=json.dumps(profiles),
            LEARNER_PAGES=json.dumps(learner_pages)), timeout=timeout)
    except BrowserRuntimeError as exc:
        print(f"localization runtime audit: FAIL\n  - {exc}")
        return 1
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        print(f"localization runtime audit: FAIL\n  - timed out after {timeout}s\n{output[-4000:]}")
        return 1
    finally:
        script.unlink(missing_ok=True)
    print((run.stdout or "").rstrip())
    if (run.stderr or "").strip(): print(run.stderr.rstrip(), file=sys.stderr)
    print("localization runtime audit: " + ("OK" if run.returncode == 0 else "FAIL"))
    return run.returncode


if __name__ == "__main__":
    raise SystemExit(main())
