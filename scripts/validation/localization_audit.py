#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate sparse same-branch localizations and emit the Studio drift manifest."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root
from runtime.html_document import raw_text_blocks
from translate.code_localization import code_contract_literals, code_templates, js_shape
from translate.locale_catalog import LocaleCatalogError, discover_locales, locale_by_tag
from translate.locale_projection import project_locale_html
from translate.locale_resource_render import render_overlay
from translate.locale_resources import (
    LocaleResourceError,
    expected_resource_path,
    json_resources,
    load_resource,
)
from translate.localization_scope import editorial_sha, translation_canonical, translation_sha
from translate.translate_html_segments import extract_segments, protected_tokens
from translate.translate_svg_text import extract_svg_segments

ROOT = find_repo_root(Path(__file__).resolve())
SKIP_TEXT = {"script", "style", "pre", "code", "svg", "noscript"}
STRUCTURE_NEUTRAL_TAGS = {"i", "em"}
INTERFACE_CONTRACT = {
    "web/nemoclaw/localization.html": ("id=\"loc-kinds\"", "data-kind=\"assets\"", "id=\"loc-filters\"", "id=\"loc-source\"", "id=\"loc-target\"", "scripts/localization_main.js"),
    "web/nemoclaw/scripts/localization_main.js": ("localization-", '"current", "stale", "blocked", "needs-review", "missing"', "reviewed_source_sha256", "asset_counts", 'activeKind === "assets"', "loc-locale", "languageManifest", 'import { languageManifestUrl } from "./_locale.js"'),
    "web/nemoclaw/scripts/_locale.js": ("mountLanguageMenu", "available_pages", 'aria-haspopup', "languageFallback", "language-fallback-badge", "PT_PREFIXES", "ES_PREFIXES", "export function languageManifestUrl"),
    "web/nemoclaw/scripts/_keypanel.js": ("mountKeyPanel", "model-api-base-url", "Save &amp; verify"),
    "web/nemoclaw/scripts/_connection.js": ("DEFAULT_OPENCLAW_PROXY_BASE", "isOpenClawLaunchableHost", "migrateOpenClawConnectionStorage"),
    "web/nemoclaw/scripts/_openclaw.js": ("mountClawProbe", "mountModelEndpointProbe", "connectionKind", "openclawBootstrapRequest", "CF-Access-Jwt-Assertion"),
    "web/nemoclaw/scripts/_shared.js": ("mountLanguageMenu()", "mountModelEndpointProbe"),
    "web/nemoclaw/studio.html": ('href="localization.html"',),
    "scripts/build/build_language_manifest.py": ("native_label", "available_pages", "localization-"),
    "scripts/build/build_pages.sh": ("assemble_locale_overlay.py",),
    "scripts/build/assemble_locale_overlay.py": ("source_sha256", "translation_sha256", "self-test", "stale translation did not fall back"),
    "scripts/translate/locale_catalog.py": ("discover_locales", "locale_by_tag", "unreachable from i18n/*/locale.json"),
    "scripts/translate/translate_svg_text.py": ("extract_svg_segments", "data-locale", "--no-api", "svg_translations.json"),
    "scripts/translate/translate_html_segments.py": ("review_protocol", "required_dimensions", "Review dimensions:",
                                                        "--revise-against-source", "editorial_examples"),
    "scripts/translate/localization_scope.py": ("en-shell", "data-localization-scope", "translation_sha"),
    "scripts/translate/locale_projection.py": ("project_locale_html", "project_localized_code_templates", "missing localized shell segment"),
    "scripts/translate/code_localization.py": ("project_localized_code_templates", "code_contract_literals", "localized runnable code contract differs"),
    "scripts/validation/localization_runtime_audit.py": (
        "pageerror",
        "language-menu entries are clipped",
        "Localization Studio",
        "localizedFigurePages",
        "labels outside their cards",
    ),
    ".gitlab/ci/core.yml": ("release_gate.py --tier ship",),
    ".github/workflows/pages.yml": ("release_gate.py --tier ship",),
    ".github/workflows/release.yml": ("release_gate.py --tier ship",),
    "scripts/validation/release_gate.py": (
        'assemble_locale_overlay.py", "--self-test"',
        'localization_audit.py", "--self-test"',
        "scripts/translate/locales",
    ),
    "scripts/translate/SKILL.html": ("locale_catalog.py", "same-branch localization", "translate_svg_text.py"),
}

RUNTIME_UI_TRANSLATION_KEYS = (
    "✓ API key available in this tab",
    "Chat route:",
    "Embedding route:",
    "Chat API base URL",
    "Chat model ID",
    "Chat API bearer key (NVIDIA keys start with",
    "Embedding route (persistent and independent)",
    "Embedding exercises keep this route when the chat route changes.",
    "Embedding API base URL",
    "Embedding model ID",
    "Embedding API bearer key",
    "Base URL",
    "Bearer token",
    "Access provider",
    "Access session",
    "Gateway recovery",
    "Retry Cloudflare WebSockets through the hosted relay",
    "Use only when a direct Cloudflare gateway or terminal socket fails.",
    "The recovery relay applies only to Cloudflare Access launchables.",
    "Use the NemoClaw App URL: https://nemoclaw-<id>.brevlab.com or https://nemoclaw-<id>.apps.run.brev.nvidia.com",
    "Access provider must be Automatic, Cloudflare Access, or Pomerium",
    "Selected access provider does not match the launchable URL",
    "OpenClaw relay URL cannot include credentials, query parameters, or a fragment",
    "Automatic from URL",
    "Cloudflare Access",
    "Pomerium",
    "Hosted relay",
    "Relay URL",
    "Use for cross-origin Cloudflare connections",
    "then open API Keys and generate one. This tab reuses the keys across lessons and discards them when it closes.",
    "Model discovery did not return JSON. Confirm this endpoint serves the OpenAI-compatible /models route, then try again",
    "Discovering models and verifying…",
    "Enter the key for the embedding route",
    "model discovery returned no model IDs",
    "embedding model discovery returned no model IDs",
    "Model ID is not served by this endpoint. Choose one of: ",
    "Embedding model ID is not served by this endpoint. Choose one of: ",
    "model discovery failed: ",
    "embedding model discovery failed: ",
    "localhost points to this browser, not a remote host. Enter the HTTPS model API base URL ending in /v1",
    "A Brev Jupyter /lab URL is not a model API. Enter the HTTPS model API base URL ending in /v1",
    "A NemoClaw launchable is not a model API. Connect it in Module 3a and keep this route on a model endpoint such as ",
    "Model API base URL",
    "Custom endpoint uses direct browser requests",
    "Use the NVIDIA DLI browser relay",
    "API bearer key (NVIDIA keys start with",
    "Key should start with nvapi-",
    "Enter the key for this endpoint",
    "✓ Connected.",
    "✓ Connected. Model replied: ",
    "Connection failed: ",
    "Model API base URL must use HTTPS",
    "Model API base URL cannot include credentials, query parameters, or a fragment",
    "model key verified this session",
    "the saved nvapi key was refused (401/403). Re-enter it on Module 1a.",
)
RUNNABLE_UI_FIELD_RE = re.compile(
    r'\b(?:label|intro|title|summary|greeting|disabledMsg|kicker|socket)\s*:\s*(["\'])(.*?)(?<!\\)\1',
    re.S,
)
RUNNABLE_UI_LOG_RE = re.compile(
    r'\b(?:helpers\.log|log(?:\.h|\.details|\.html)?|info|show)\s*\(\s*(["\'])(.*?)(?<!\\)\1',
    re.S,
)
RUNNABLE_UI_EXAMPLES_RE = re.compile(r'\bexamples\s*:\s*\[(.*?)\]', re.S)
RUNNABLE_UI_STRING_RE = re.compile(r'(["\'])(.*?)(?<!\\)\1', re.S)
SHARED_RUNTIME_FIELD_RE = re.compile(
    r'\b(?:greeting|disabledMsg)\s*:\s*(?:[^"\']*?\?\s*)?(["\'])(.*?)(?<!\\)\1',
    re.S,
)


class ReaderText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in SKIP_TEXT:
            self.depth += 1
        if not self.depth:
            for key, value in attrs:
                if key.lower() in {"alt", "aria-label", "placeholder", "title"} and value:
                    self.parts.append(value.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in SKIP_TEXT and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.depth and data.strip():
            self.parts.append(data.strip())


class ProsePunctuation(HTMLParser):
    """Reader text kept adjacent, with each protected span collapsed to one sentinel.

    ``ReaderText`` joins parts with spaces, which detaches a closing `?` from the `code` span it
    ends. Punctuation balance needs the original adjacency, so this parser preserves it and marks
    a skipped span with a non-space sentinel instead of dropping it.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in SKIP_TEXT:
            if not self.depth:
                self.parts.append(PROTECTED_SENTINEL)
            self.depth += 1
        elif not self.depth:
            for key, value in attrs:
                if key.lower() in {"alt", "aria-label", "placeholder", "title"} and value:
                    self.parts.append(f" {value} ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in SKIP_TEXT and self.depth:
            self.depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.depth:
            self.parts.append(data)


def prose_punctuation_markup(raw: str) -> str:
    """Return the reader's prose from an HTML document, preserving punctuation adjacency."""
    parser = ProsePunctuation()
    parser.feed(raw)
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


class TagSkeleton(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in STRUCTURE_NEUTRAL_TAGS:
            return
        self.tags.append(f"<{tag.lower()}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in STRUCTURE_NEUTRAL_TAGS:
            return
        self.tags.append(f"<{tag.lower()}/>")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in STRUCTURE_NEUTRAL_TAGS:
            return
        self.tags.append(f"</{tag.lower()}>")


def sha(raw: str) -> str:
    return hashlib.sha256(raw.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def reader_text(raw: str) -> str:
    parser = ReaderText()
    parser.feed(raw)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def tag_skeleton(raw: str) -> list[str]:
    parser = TagSkeleton()
    parser.feed(raw)
    return parser.tags


def script_shapes(raw: str) -> list[str]:
    inline = [
        script.body
        for script in raw_text_blocks(raw, "script")
        if "src" not in script.attributes
    ]
    cells = re.findall(r"\bcode\s*:\s*`((?:\\.|[^`\\])*)`", raw, re.S)
    return [js_shape(item) for item in inline + cells]


def scripted_ui_text(raw: str) -> str:
    """Extract common learner-facing object fields without treating model prompts as UI prose."""
    values = [item.text.replace("\\n", " ") for item in extract_segments(raw)
              if item.kind == "script-ui"]
    return re.sub(r"\s+", " ", " ".join(values)).strip()


def runnable_code_ui_strings(raw: str) -> list[str]:
    """Extract learner-facing strings from editable code without scanning model prompts.

    Keep each value separate: joining a translated greeting to one untranslated example can
    dilute the English function-word density and let the smaller residue disappear.
    """
    values: list[str] = []
    for body in code_templates(raw):
        values.extend(match.group(2) for match in RUNNABLE_UI_FIELD_RE.finditer(body))
        values.extend(match.group(2) for match in RUNNABLE_UI_LOG_RE.finditer(body))
        for array in RUNNABLE_UI_EXAMPLES_RE.finditer(body):
            values.extend(match.group(2) for match in RUNNABLE_UI_STRING_RE.finditer(array.group(1)))
    return [re.sub(r"\s+", " ", value.replace("\\n", " ")).strip()
            for value in values if value.strip()]


def editorial_pattern_quality(text: str, profile: dict) -> list[dict[str, str]]:
    """Reject measurable machine-translation artifacts declared by a locale profile."""
    out: list[dict[str, str]] = []
    for rule in profile.get("editorial_patterns", []):
        pattern = rule.get("pattern", "")
        if pattern and re.search(pattern, text, re.I):
            out.append({"code": rule.get("code", "locale-editorial-pattern"),
                        "detail": rule.get("detail", f"unfit localized pattern: {pattern}")})
    return out


CLOSING_QUESTION_RE = re.compile(r"(?<=\S)\?")
CLOSING_EXCLAMATION_RE = re.compile(r"(?<=\S)!")
PROTECTED_SPAN_RE = re.compile(r"<(code|kbd)\b[^>]*>.*?</\1\s*>", re.I | re.S)
INLINE_MARKUP_RE = re.compile(r"<[^>]+>")
PROTECTED_SENTINEL = "§"


def prose_punctuation_text(raw: str) -> str:
    """Return prose whose punctuation belongs to the language, not to code or markup.

    A protected `code` or `kbd` span carries executable text: the `?` opening a URL query string
    is not a Spanish question. Collapse each span to one non-space sentinel rather than deleting
    it, and drop the remaining inline tags without inserting whitespace, so a closing mark stays
    attached to the word or span it ends.
    """
    return INLINE_MARKUP_RE.sub("", PROTECTED_SPAN_RE.sub(PROTECTED_SENTINEL, raw))


def orthography_quality(text: str, profile: dict, *, balance_text: str | None = None) -> list[dict[str, str]]:
    """Reject locale-wide punctuation artifacts without interpreting HTML layout."""
    rules = profile.get("orthography_rules", {})
    out: list[dict[str, str]] = []
    if rules.get("reject_space_before_punctuation") and re.search(
            r"[\wÁÉÍÓÚÜÑáéíóúüñ)\]]\s+[.,;:](?!\w)", text):
        out.append({"code": "locale-punctuation-spacing",
                    "detail": "unexpected space before punctuation in learner-facing prose"})
    if rules.get("require_balanced_opening_punctuation"):
        # A closing mark attaches to the word or protected span it ends. A whitespace-isolated `?`
        # or `!` names the on-screen glyph ("select the ? beside that field") and opens no
        # sentence, so counting it would demand an opening mark that would be wrong on the page.
        punctuation = prose_punctuation_text(text if balance_text is None else balance_text)
        attached_questions = len(CLOSING_QUESTION_RE.findall(punctuation))
        all_questions = punctuation.count("?")
        opening_questions = punctuation.count("¿")
        # A runnable UI sentence can be assembled from "¿... " + value + "?". The closing mark is
        # whitespace-isolated in static extraction even though it closes the question at runtime.
        # Pair isolated marks only with otherwise-unmatched openings; a standalone on-screen "?"
        # glyph remains neutral.
        if not attached_questions <= opening_questions <= all_questions:
            out.append({"code": "locale-question-punctuation",
                        "detail": "Spanish question marks are missing or have unmatched opening punctuation"})
        attached_exclamations = len(CLOSING_EXCLAMATION_RE.findall(punctuation))
        all_exclamations = punctuation.count("!")
        opening_exclamations = punctuation.count("¡")
        if not attached_exclamations <= opening_exclamations <= all_exclamations:
            out.append({"code": "locale-exclamation-punctuation",
                        "detail": "Spanish exclamation marks are missing or have unmatched opening punctuation"})
    return out


def mixed_language_quality(text: str, profile: dict) -> list[dict[str, str]]:
    """Catch English prose residue by density, not an ever-growing phrase list."""
    words = {word.lower() for word in profile.get("english_function_words", [])}
    threshold = int(profile.get("english_function_word_threshold", 0))
    if not words or not threshold:
        return []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        tokens = re.findall(r"\b[A-Za-z]+\b", sentence.lower())
        matches = [token for token in tokens if token in words]
        if len(matches) >= threshold:
            excerpt = re.sub(r"\s+", " ", sentence).strip()[:180]
            return [{"code": "locale-mixed-language",
                     "detail": f"English function-word density suggests untranslated prose: {excerpt!r}"}]
    return []


def foreign_language_quality(text: str, profile: dict) -> list[dict[str, str]]:
    """Catch residue from a known neighboring source language by sentence density."""
    words = {word.casefold() for word in profile.get("foreign_function_words", [])}
    threshold = int(profile.get("foreign_function_word_threshold", 0))
    if not words or not threshold:
        return []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        tokens = re.findall(r"\b[^\W\d_]+\b", sentence.casefold(), re.UNICODE)
        matches = [token for token in tokens if token in words]
        if len(matches) >= threshold:
            excerpt = re.sub(r"\s+", " ", sentence).strip()[:180]
            return [{"code": "locale-foreign-language",
                     "detail": f"neighboring-language density suggests untranslated prose: {excerpt!r}"}]
    return []


def repetition_quality(text: str, profile: dict) -> list[dict[str, str]]:
    """Reject copy/paste repetition that is grammatical nonsense, not emphasis."""
    if not profile.get("reject_accidental_repetition"):
        return []
    adjacent = re.search(r"(?i)\b([a-záéíóúüñ]{4,})\s+\1\b", text)
    nested = re.search(r"(?i)\b([a-záéíóúüñ]{5,})\s+de(?:l| la)\s+\1\b", text)
    phrase = re.search(
        r"(?i)\b((?:[a-záéíóúüñ]{2,}\s+){1,4}[a-záéíóúüñ]{2,})\s+\1\b", text)
    match = adjacent or nested or phrase
    if not match:
        return []
    return [{"code": "locale-accidental-repetition",
             "detail": f"accidental repeated word or phrase: {match.group(0)!r}"}]


def citation_titles(raw: str) -> list[tuple[str, str]]:
    """Return cited titles that remain canonical across language overlays."""
    out = []
    anchor = re.compile(r'<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    for href, body in anchor.findall(raw):
        title = re.search(r"<em>(.*?)</em>", body, re.I | re.S)
        if title:
            out.append((href, re.sub(r"\s+", " ", title.group(1)).strip()))
    return out


def reference_citation_titles(raw: str) -> list[tuple[str, str]]:
    """Return academic titles from the module-organized references hub.

    Localized prose may translate descriptions and link labels, but published paper and
    book titles remain canonical. Academic entries in this hub begin with an author and year.
    """
    start = raw.find('id="refs"')
    if start < 0:
        return []
    end = raw.find('id="learning-path"', start)
    body = raw[start:end if end >= 0 else len(raw)]
    out: list[tuple[str, str]] = []
    anchor = re.compile(r'<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.I | re.S)
    for item in re.findall(r"<li\b[^>]*>(.*?)</li>", body, re.I | re.S):
        first = anchor.search(item)
        if not first:
            continue
        prefix = item[:first.start()]
        if not re.search(r"\(\d{4}\)\.", prefix) or "<em" in prefix.lower():
            continue
        title = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", first.group(2))).strip())
        if title:
            out.append((first.group(1), title))
    return out


def html_lang(raw: str) -> str:
    match = re.search(r"<html\b[^>]*\blang=[\"']([^\"']+)", raw, re.I)
    return match.group(1) if match else ""


def segment_contract_tokens(raw: str) -> list[str]:
    """Return tokens that must stay in the same learner-facing segment."""
    protected = [token for token in protected_tokens(raw)
                 if token.lower().startswith(("<code", "<kbd", "http", "${", "{{", "nvapi-"))]
    urls = re.findall(r"https?://[^\s<\"']+", raw, re.I)
    visible = re.sub(r"<[^>]+>", " ", raw)
    routes = re.findall(r"(?<!\w)/(?:[A-Za-z0-9_.{}:<>-]+/?)+", visible)
    return sorted(Counter(protected + urls + routes).elements())


def rhythm_quality(text: str, profile: dict) -> list[dict[str, str]]:
    rules = profile.get("rhythm_rules", {})
    if not rules:
        return []
    sentences = [re.sub(r"\s+", " ", item).strip(" \n\t•")
                 for item in re.split(r"(?<=[.!?])\s+", text) if item.strip()]
    out: list[dict[str, str]] = []
    limit = int(rules.get("max_sentence_words", 0))
    for sentence in sentences:
        words = re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", sentence)
        if limit and len(words) > limit:
            out.append({"code": "locale-long-sentence", "detail": f"sentence has {len(words)} words; limit is {limit}"})
            break
    opening_limit = int(rules.get("repeated_opening_run", 0))
    openings = [" ".join(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", item.lower())[:2]) for item in sentences]
    for index in range(max(0, len(openings) - opening_limit + 1)):
        run = openings[index:index + opening_limit]
        if opening_limit and len(run) == opening_limit and len(set(run)) == 1 and run[0]:
            out.append({"code": "locale-repeated-opening", "detail": f"{opening_limit} consecutive sentences start with {run[0]!r}"})
            break
    short_run = int(rules.get("short_sentence_run", 0))
    short_words = int(rules.get("short_sentence_words", 0))
    lengths = [len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ]+\b", item)) for item in sentences]
    for index in range(max(0, len(lengths) - short_run + 1)):
        run = lengths[index:index + short_run]
        if short_run and len(run) == short_run and all(length <= short_words for length in run):
            out.append({"code": "locale-choppy-run", "detail": f"{short_run} consecutive sentences have at most {short_words} words"})
            break
    return out


def voice_quality(text: str, profile: dict) -> list[dict[str, str]]:
    """Reject explicit locale-level voice drift without pretending to parse all grammar."""
    rules = profile.get("voice_rules", {})
    out: list[dict[str, str]] = []
    for phrase in rules.get("disallowed_formal_address", []):
        if re.search(rf"(?i)\b{re.escape(phrase)}\b", text):
            out.append({"code": "locale-formal-address",
                        "detail": f"formal learner address remains: {phrase!r}"})
            break
    for phrase in rules.get("disallowed_formal_imperatives", []):
        cue = r"(?:^|[.!?;·:]\s+|\b(?:ahora|después|primero|luego),?\s+)"
        if re.search(rf"(?i){cue}{re.escape(phrase)}\b", text):
            out.append({"code": "locale-formal-imperative",
                        "detail": f"formal learner imperative remains: {phrase!r}"})
            break
    for rule in rules.get("disallowed_formal_patterns", []):
        pattern = rule.get("pattern", "")
        if pattern and re.search(pattern, text, re.I):
            out.append({"code": rule.get("code", "locale-formal-address"),
                        "detail": rule.get("detail", f"formal learner-address pattern remains: {pattern}")})
    return out


def html_ids(raw: str) -> set[str]:
    return set(re.findall(r"\bid=[\"']([^\"']+)", raw, re.I))


def local_deps(raw: str) -> set[str]:
    refs = re.findall(r"<(?:script|link)\b[^>]*(?:src|href)=[\"']([^\"']+)", raw, re.I)
    return {ref for ref in refs if not re.match(r"(?:https?:|data:|#)", ref)}


def skill_meta(raw: str) -> object | None:
    match = re.search(r'<script[^>]*id=["\']skill-meta["\'][^>]*>(.*?)</script>', raw, re.S | re.I)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def svg_geometry(raw: str) -> list[tuple[str, tuple[tuple[str, str], ...]]]:
    """Represent non-language SVG structure; text coordinates may change to repair wrapping."""
    root = ET.fromstring(raw)
    out = []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in {"text", "tspan", "title", "desc"}:
            out.append((tag, ()))
            continue
        attrs = tuple(sorted((key.rsplit("}", 1)[-1], value) for key, value in element.attrib.items()
                             if key not in {"aria-label", "data-locale"}))
        out.append((tag, attrs))
    return out


def svg_visible_text(raw: str) -> str:
    root = ET.fromstring(raw)
    values = [root.attrib.get("aria-label", "")]
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] in {"text", "tspan", "title", "desc"} and element.text:
            values.append(element.text)
    return re.sub(r"\s+", " ", " ".join(values)).strip()


def svg_prose_text(raw: str) -> str:
    """Return descriptive SVG prose; terse diagram labels are not sentences."""
    root = ET.fromstring(raw)
    values = [root.attrib.get("aria-label", "")]
    values.extend(element.text for element in root.iter()
                  if element.tag.rsplit("}", 1)[-1] in {"title", "desc"} and element.text)
    return re.sub(r"\s+", " ", " ".join(values)).strip()


def svg_quality(source_raw: str, target_raw: str, profile: dict) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    try:
        source_geometry = svg_geometry(source_raw)
        target_geometry = svg_geometry(target_raw)
        source_root = ET.fromstring(source_raw)
        target_root = ET.fromstring(target_raw)
    except ET.ParseError as exc:
        return [{"code": "svg-xml", "detail": f"invalid localized SVG: {exc}"}]
    expected_locale = profile["locale"]
    if f'data-locale="{expected_locale}"' not in target_raw:
        out.append({"code": "svg-locale", "detail": f"localized SVG needs data-locale={expected_locale}"})
    if source_geometry != target_geometry:
        out.append({"code": "svg-geometry", "detail": "localized SVG changed non-text geometry or element order"})
    for source_el, target_el in zip(source_root.iter(), target_root.iter()):
        if source_el.tag.rsplit("}", 1)[-1] != "tspan":
            continue
        source_text = "".join(source_el.itertext()).strip()
        target_text = "".join(target_el.itertext()).strip()
        if source_text != target_text and len(target_el.attrib.get("x", "").split()) > 1:
            out.append({"code": "svg-glyph-positions",
                        "detail": f"translated tspan {target_text!r} retains source per-glyph x positions"})
            break
    if re.search(r"<script\b|\bon\w+\s*=", target_raw, re.I):
        out.append({"code": "svg-script", "detail": "localized SVG may not add executable content"})
    visible = svg_visible_text(target_raw)
    source_segments = [item.text for item in extract_svg_segments(source_raw)]
    target_segments = [item.text for item in extract_svg_segments(target_raw)]
    translations = profile.get("_svg_translations", {})
    if len(source_segments) != len(target_segments):
        out.append({"code": "svg-text-shape", "detail": "localized SVG changed the number of translatable text nodes"})
    else:
        for source_text, target_text in zip(source_segments, target_segments):
            if source_text not in translations:
                out.append({"code": "svg-translation-map", "detail": f"missing reviewed SVG mapping for {source_text!r}"})
                break
            if translations[source_text] != target_text:
                out.append({"code": "svg-translation-drift", "detail": f"localized SVG text differs from reviewed mapping for {source_text!r}"})
                break
    for phrase, fix in profile.get("unfit_phrases", {}).items():
        if re.search(rf"(?i)\b{re.escape(phrase)}\b", visible):
            out.append({"code": "unfit-locale", "detail": f"{phrase!r}: {fix}"})
    out.extend(voice_quality(visible, profile))
    out.extend(rhythm_quality(svg_prose_text(target_raw), profile))
    return out


def canonical_pages(root: Path) -> list[Path]:
    pages = [root / "web" / "index.html", root / "web" / "courses.html"]
    pages.extend(sorted((root / "web" / "nemoclaw").glob("*.html")))
    return [page for page in pages if page.is_file() and page.name not in {"localization.html"}]


def locale_paths(root: Path, locale: str) -> tuple[Path, Path, Path, dict, dict]:
    spec = locale_by_tag(root, locale)
    return spec.profile_path, spec.locale_root, spec.state_path, spec.profile, spec.state


def interface_findings(root: Path) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for rel, tokens in INTERFACE_CONTRACT.items():
        path = root / rel
        if not path.is_file():
            out.append({"code": "interface-file", "path": rel, "detail": "required localization interface file is missing"})
            continue
        raw = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in raw:
                out.append({"code": "interface-contract", "path": rel, "detail": f"missing contract token: {token}"})
    locale_path = root / "web/nemoclaw/scripts/_locale.js"
    if locale_path.is_file():
        locale_raw = locale_path.read_text(encoding="utf-8")
        runtime_paths = (
            root / "web/nemoclaw/scripts/_keypanel.js",
            root / "web/nemoclaw/scripts/_connection.js",
            root / "web/nemoclaw/scripts/_openclaw.js",
            root / "web/nemoclaw/scripts/_shared.js",
            root / "web/nemoclaw/scripts/_openclaw_cli.js",
        )
        runtime_raw = html.unescape("\n".join(
            path.read_text(encoding="utf-8")
            for path in runtime_paths
            if path.is_file()
        ))
        runtime_keys = set(RUNTIME_UI_TRANSLATION_KEYS)
        cli_path = root / "web/nemoclaw/scripts/_openclaw_cli.js"
        if cli_path.is_file():
            runtime_keys.update(match.group(2) for match in SHARED_RUNTIME_FIELD_RE.finditer(
                cli_path.read_text(encoding="utf-8")
            ) if match.group(2))
        for key in sorted(runtime_keys):
            needle = json.dumps(key, ensure_ascii=False) + ":"
            if locale_raw.count(needle) < 2:
                out.append({
                    "code": "runtime-ui-translation",
                    "path": "web/nemoclaw/scripts/_locale.js",
                    "detail": f"runtime UI key must have reviewed Portuguese and Spanish mappings: {key}",
                })
            if key not in runtime_raw:
                out.append({
                    "code": "runtime-ui-source-contract",
                    "path": "web/nemoclaw/scripts/_keypanel.js",
                    "detail": f"reviewed runtime UI key no longer matches its source string: {key}",
                })
    return out


def _remove_reviewed_untranslated(text: str, values: tuple[str, ...]) -> str:
    """Remove explicit resource fallbacks from language-residue checks only."""
    candidates: set[str] = set()
    for value in values:
        plain = html.unescape(re.sub(r"<[^>]+>", "", value)).replace("\\n", " ")
        candidates.update((
            plain.strip(),
            re.sub(r"\s+", " ", plain).strip(),
        ))
    # Granular runnable-copy resources legitimately contain tiny strings such as "s", "no", or
    # punctuation. A raw str.replace would erase those characters inside translated prose and
    # manufacture language, punctuation, and density failures. Remove only whole reviewed spans.
    for candidate in sorted(candidates, key=len, reverse=True):
        if candidate and any(char.isalpha() for char in candidate):
            text = re.sub(
                rf"(?<!\w){re.escape(candidate)}(?!\w)",
                "",
                text,
            )
    return text


def page_quality(source_raw: str, target_raw: str, profile: dict, *, skill: bool = False,
                 enforce_editorial_patterns: bool = True,
                 reviewed_untranslated: tuple[str, ...] = ()) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if 'data-localization-scope="en-shell"' in source_raw:
        try:
            # Projection validates the English-only wrapper map, but quality and
            # integrity checks must inspect the committed sparse overlay itself.
            # Checking only the projected result can silently replace bad target
            # code or structure with canonical source before validators see it.
            project_locale_html(source_raw, target_raw, profile.get("_shell_translations", {}))
        except ValueError as exc:
            return [{"code": "locale-projection", "detail": str(exc)}]
        source_raw = translation_canonical(source_raw)
    expected_lang = profile["html_lang"]
    if html_lang(target_raw) != expected_lang:
        out.append({"code": "html-lang", "detail": f"expected <html lang=\"{expected_lang}\">"})
    source_segments = extract_segments(source_raw)
    target_segments = extract_segments(target_raw)
    if (len(source_segments) != len(target_segments)
            or [item.kind for item in source_segments] != [item.kind for item in target_segments]):
        out.append({"code": "content-segments",
                    "detail": f"learner-facing segment parity differs: source {len(source_segments)}, target {len(target_segments)}"})
    else:
        for index, (source_segment, target_segment) in enumerate(zip(source_segments, target_segments)):
            if segment_contract_tokens(source_segment.text) != segment_contract_tokens(target_segment.text):
                out.append({"code": "segment-token-drift",
                            "detail": f"segment {index} moved or changed a protected URL, path, placeholder, or code token"})
                break
            source_words = len(re.findall(r"\b\w+\b", re.sub(r"<[^>]+>", " ", source_segment.text)))
            target_words = len(re.findall(r"\b\w+\b", re.sub(r"<[^>]+>", " ", target_segment.text)))
            minimum_ratio = float(profile.get("minimum_block_word_ratio", 0.35))
            if (source_segment.kind == "block" and source_words >= 12
                    and target_words / source_words < minimum_ratio):
                out.append({"code": "content-shortfall",
                            "detail": (f"segment {index} retained only {target_words}/{source_words} words "
                                       f"(minimum ratio {minimum_ratio:.2f})")})
                break
    ui_text = scripted_ui_text(target_raw)
    source_runnable_ui = set(runnable_code_ui_strings(source_raw))
    runnable_ui = runnable_code_ui_strings(target_raw)
    reviewed_runnable_ui = {
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()
        for value in reviewed_untranslated
    }
    localized_runtime_refs = {
        html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
        for value in re.findall(r"<(?:em|code)\b[^>]*>.*?</(?:em|code)>", target_raw, re.I | re.S)
    }
    visible = reader_text(target_raw) + " " + ui_text
    # Preserve segment boundaries for voice rules. Concatenating blocks and UI
    # fields with spaces can hide an imperative that begins a later segment.
    voice_text = ". ".join(
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", item.text))).strip()
        for item in target_segments
        if item.kind in {"block", "text", "attribute", "script-ui"}
    )
    repetition_text = ". ".join(
        re.sub(r"\s+", " ", html.unescape(re.sub(
            r"<[^>]+>", "", re.sub(r"<code\b[^>]*>.*?</code>", " ", item.text,
                                     flags=re.I | re.S)))).strip()
        for item in target_segments
        if item.kind in {"block", "text", "attribute", "script-ui"}
    )
    source_reference_titles = set(reference_citation_titles(source_raw))
    target_reference_titles = set(reference_citation_titles(target_raw))
    # A cited title stays canonical English by contract, so its wording and its punctuation both
    # belong to the citation rather than to the locale. Every reader-text rule reads the same
    # removal list; a rule that skipped it would report the citation as a locale defect.
    canonical_titles = [
        html.unescape(re.sub(r"<[^>]+>", "", title)) for _, title in citation_titles(target_raw)
    ]
    canonical_titles.extend(title for _, title in source_reference_titles & target_reference_titles)
    canonical_titles.extend(profile.get("canonical_english_titles", []))
    for title in canonical_titles:
        visible = visible.replace(title, "")
    # A resource fallback is never implicit: the typed entry must carry a reviewed reason. Keep
    # every structural, token, link, code, and non-residue locale-quality check on the rendered
    # page, but do not rediscover that same declared English copy as hidden language residue.
    # Remove canonical citation titles first: a short reviewed code term such as "RAG" must not
    # alter the title before the citation exception can recognize it.
    visible = _remove_reviewed_untranslated(visible, reviewed_untranslated)
    ui_text = _remove_reviewed_untranslated(ui_text, reviewed_untranslated)
    for marker in profile.get("english_sentence_markers", []):
        if marker in visible:
            out.append({"code": "untranslated-english", "detail": f"reader text still contains {marker!r}"})
    for marker in profile.get("english_ui_markers", []):
        if marker.lower() in ui_text.lower():
            out.append({"code": "untranslated-ui", "detail": f"scripted learner UI still contains {marker!r}"})
    for phrase, fix in profile.get("unfit_phrases", {}).items():
        if re.search(rf"(?i)\b{re.escape(phrase)}\b", voice_text):
            out.append({"code": "unfit-locale", "detail": f"{phrase!r}: {fix}"})
    if (citation_titles(source_raw) != citation_titles(target_raw)
            or reference_citation_titles(source_raw) != reference_citation_titles(target_raw)):
        out.append({"code": "citation-title", "detail": "cited paper/book titles must remain canonical"})
    missing_ids = sorted(html_ids(source_raw) - html_ids(target_raw))
    if missing_ids:
        out.append({"code": "structure-ids", "detail": "missing source ids: " + ", ".join(missing_ids[:12])})
    missing_deps = sorted(local_deps(source_raw) - local_deps(target_raw))
    if missing_deps:
        out.append({"code": "structure-deps", "detail": "missing source dependencies: " + ", ".join(missing_deps)})
    if tag_skeleton(source_raw) != tag_skeleton(target_raw):
        out.append({"code": "structure-tags", "detail": "HTML tag order differs from the canonical source"})
    if script_shapes(source_raw) != script_shapes(target_raw):
        out.append({"code": "script-structure", "detail": "executable JavaScript structure differs from the canonical source"})
    if code_contract_literals(source_raw) != code_contract_literals(target_raw):
        out.append({"code": "code-contract-drift", "detail": "localized runnable code changed protocol or configuration literals"})
    if profile.get("canonical_code_templates") and code_templates(source_raw) != code_templates(target_raw):
        out.append({"code": "code-cell-drift", "detail": "localized runnable code differs from the canonical source"})
    if skill and skill_meta(source_raw) != skill_meta(target_raw):
        out.append({"code": "skill-meta-drift", "detail": "localized skill-meta differs from canonical JSON"})
    if enforce_editorial_patterns:
        out.extend(editorial_pattern_quality(voice_text, profile))
        out.extend(voice_quality(voice_text, profile))
        balance = prose_punctuation_markup(target_raw) + " " + ui_text
        balance = _remove_reviewed_untranslated(balance, reviewed_untranslated)
        for title in canonical_titles:
            balance = balance.replace(title, "")
        out.extend(orthography_quality(voice_text, profile, balance_text=balance))
        out.extend(mixed_language_quality(visible, profile))
        out.extend(foreign_language_quality(visible, profile))
        out.extend(repetition_quality(repetition_text, profile))
    # A style reference pins editorial prose, not executable UI. Locales that require reviewed
    # target hashes promise complete runnable UI too, including on the pinned style-reference page.
    if profile.get("reviewed_target_hashes"):
        for value in runnable_ui:
            for item in mixed_language_quality(value, profile):
                out.append({"code": "locale-code-mixed-language", "detail": item["detail"]})
            # Exact source/target equality is stronger evidence than a language-density guess.
            # Ignore unfinished markup and code-shaped output while rejecting ordinary labels.
            plain_value = html.unescape(re.sub(r"<[^>]*>", " ", value))
            words = re.findall(r"\b[A-Za-z]+\b", plain_value)
            unfinished_markup = value.startswith("<") and ">" not in value
            english_cues = {word.lower() for word in profile.get("english_function_words", [])}
            has_english_cue = any(word.lower() in english_cues for word in words)
            code_shaped = bool(re.search(r"(?:\w\.){1,}|->|--|[<>{}=]", plain_value))
            if (value in source_runnable_ui
                    and re.sub(r"\s+", " ", plain_value).strip() not in reviewed_runnable_ui
                    and plain_value.strip() not in localized_runtime_refs
                    and not unfinished_markup and len(words) >= 2
                    and any(word[:1].islower() for word in words)
                    and (has_english_cue or not code_shaped)):
                out.append({"code": "locale-code-untranslated",
                            "detail": f"learner-facing runnable-code text matches English source: {value!r}"})
    return out


def scan(root: Path, locale: str) -> tuple[list[dict[str, str]], dict]:
    spec = locale_by_tag(root, locale)
    locale_root, profile, state = spec.locale_root, dict(spec.profile), spec.state
    svg_map = root / "scripts" / "translate" / "locales" / locale / "svg_translations.json"
    profile["_svg_translations"] = json.loads(svg_map.read_text(encoding="utf-8")) if svg_map.is_file() else {}
    shell_map = root / "scripts" / "translate" / "locales" / locale / "shell_translations.json"
    profile["_shell_translations"] = json.loads(shell_map.read_text(encoding="utf-8")) if shell_map.is_file() else {}
    overlay_root = locale_root / "web"
    declared = {Path(item).as_posix() for item in state.get("overlay_files", [])}
    declared_assets = {Path(item).as_posix() for item in state.get("asset_files", [])}
    declared_all = declared | declared_assets
    # SKILL.html is the required directory contract for the locale source tree, not a translated
    # overlay payload. The global SKILL gate validates every one exhaustively; localization still
    # rejects any other undeclared file.
    actual = {
        path.relative_to(locale_root).as_posix()
        for path in overlay_root.rglob("*")
        if path.is_file() and path.name != "SKILL.html"
    }
    findings: list[dict[str, str]] = interface_findings(root) if (root / "web/nemoclaw/localization.html").exists() else []
    resources: dict[str, object] = {}
    try:
        resource_paths = json_resources(locale_root)
    except LocaleResourceError as exc:
        resource_paths = []
        findings.append({"code": "resource-discovery", "path": "resources", "detail": str(exc)})
    for resource_path in resource_paths:
        try:
            resource = load_resource(resource_path)
            if resource.locale != spec.locale:
                raise LocaleResourceError(
                    f"declares locale {resource.locale!r} inside {spec.locale!r}")
            if resource_path != expected_resource_path(locale_root, resource.template):
                raise LocaleResourceError(
                    f"resource for {resource.template} is not at its derived path")
            if resource.template in resources:
                raise LocaleResourceError(
                    f"duplicate resource for template {resource.template}")
            resources[resource.template] = resource
        except LocaleResourceError as exc:
            findings.append({
                "code": "resource-target",
                "path": resource_path.relative_to(root).as_posix(),
                "detail": str(exc),
            })
    for path in sorted(actual - declared_all):
        findings.append({"code": "overlay-extra", "path": path,
                         "detail": "not declared as localized prose; code/assets and fallback pages belong to canonical web/"})
    for path in sorted(declared_all - actual):
        findings.append({"code": "overlay-missing", "path": path, "detail": "declared overlay file is missing"})
    for path in sorted(declared):
        if not path.startswith("web/") or not path.endswith(".html") or not (root / path).is_file():
            findings.append({"code": "overlay-boundary", "path": path,
                             "detail": "locale overlays may contain only HTML files with a canonical web/ source"})
    for path in sorted(declared_assets):
        if not path.startswith("web/nemoclaw/assets/figures/") or not path.endswith(".svg") or not (root / path).is_file():
            findings.append({"code": "overlay-asset-boundary", "path": path,
                             "detail": "localized assets may contain only reviewed course figure SVGs"})

    reviews = state.get("reviews", {})
    asset_reviews = state.get("asset_reviews", {})
    review_protocol = profile.get("review_protocol", {})
    style_reference = review_protocol.get("style_reference")
    if style_reference:
        if style_reference not in declared and style_reference not in resources:
            findings.append({"code": "style-reference-boundary", "path": style_reference,
                             "detail": "locale style reference must be a reviewed overlay or resource"})
        elif not reviews.get(style_reference, {}).get("target_sha256"):
            findings.append({"code": "style-reference-review", "path": style_reference,
                             "detail": "locale style reference needs an accepted target hash"})
        expected_style_sha = review_protocol.get("style_reference_editorial_sha256", "")
        origin_commit = review_protocol.get("style_reference_origin_commit", "")
        style_target = locale_root / style_reference
        style_raw = ""
        if style_target.is_file():
            style_raw = style_target.read_text(encoding="utf-8")
        elif style_reference in resources:
            style_source = root / style_reference
            if style_source.is_file():
                try:
                    style_raw = render_overlay(
                        style_source.read_text(encoding="utf-8"),
                        resources[style_reference].values,
                        spec.html_lang,
                    )
                except LocaleResourceError as exc:
                    findings.append({
                        "code": "style-reference-resource",
                        "path": style_reference,
                        "detail": f"cannot render locale style reference: {exc}",
                    })
        if not re.fullmatch(r"[0-9a-f]{64}", expected_style_sha):
            findings.append({"code": "style-reference-pin", "path": style_reference,
                             "detail": "locale style reference needs a full pinned SHA-256"})
        elif style_raw and editorial_sha(style_raw) != expected_style_sha:
            findings.append({"code": "style-reference-drift", "path": style_reference,
                             "detail": "locale style reference prose differs from the style PIC's editorial pin"})
        if not re.fullmatch(r"[0-9a-f]{40}", origin_commit):
            findings.append({"code": "style-reference-origin", "path": style_reference,
                             "detail": "locale style reference needs the full originating commit id"})
    for path in sorted(set(reviews) - declared - set(resources)):
        findings.append({"code": "review-orphan", "path": path,
                         "detail": "review entry has neither a declared HTML overlay nor a locale resource"})
    for path in sorted(set(asset_reviews) - declared_assets):
        findings.append({"code": "asset-review-orphan", "path": path,
                         "detail": "asset review entry is not present in asset_files"})
    rows: list[dict[str, object]] = []
    for source in canonical_pages(root):
        rel = source.relative_to(root).as_posix()
        target = locale_root / rel
        source_raw = source.read_text(encoding="utf-8")
        scoped = 'data-localization-scope="en-shell"' in source_raw
        source_digest = translation_sha(source_raw) if scoped else sha(source_raw)
        representation = "html-overlay"
        target_raw = target.read_text(encoding="utf-8") if target.is_file() and (
            target.name != "SKILL.html" or rel in declared
        ) else ""
        resource = resources.get(rel)
        reviewed_untranslated: tuple[str, ...] = ()
        if not target_raw and resource is not None:
            representation = "locale-resource"
            try:
                target_raw = render_overlay(source_raw, resource.values, spec.html_lang)
                reviewed_untranslated = tuple(
                    entry["value"]
                    for entry in resource.values.values()
                    if isinstance(entry.get("untranslated"), str)
                )
            except LocaleResourceError as exc:
                findings.append({
                    "code": "resource-target",
                    "path": rel,
                    "detail": f"locale={spec.locale}; correction=repair the resource values: {exc}",
                })
                target_raw = ""
        elif not target_raw:
            representation = "canonical-fallback"
        review = reviews.get(rel) or {}
        reviewed_digest = review.get("translation_sha256") if scoped else review.get("source_sha256")
        target_digest = sha(target_raw) if target_raw else None
        reviewed_target = review.get("target_sha256")
        require_target_review = bool(profile.get("reviewed_target_hashes"))
        quality = page_quality(
            source_raw,
            target_raw,
            profile,
            skill=source.name == "SKILL.html",
            enforce_editorial_patterns=rel != style_reference,
            reviewed_untranslated=reviewed_untranslated,
        ) if target_raw else []
        if not target_raw:
            status = "missing"
        elif not reviewed_digest or (require_target_review and not reviewed_target):
            status = "needs-review"
        elif reviewed_digest != source_digest:
            status = "stale"
        elif require_target_review and reviewed_target != target_digest:
            status = "needs-review"
        elif quality:
            status = "blocked"
        else:
            status = "current"
        if reviewed_digest and reviewed_digest != source_digest:
            findings.append({"code": "stale-source", "path": rel,
                             "detail": f"reviewed {reviewed_digest[:12]}, source is {source_digest[:12]}"})
        if require_target_review and reviewed_target and reviewed_target != target_digest:
            findings.append({"code": "target-drift", "path": rel,
                             "detail": f"reviewed target {reviewed_target[:12]}, target is {(target_digest or 'missing')[:12]}"})
        elif require_target_review and target_raw and not reviewed_target:
            findings.append({"code": "target-unreviewed", "path": rel,
                             "detail": "locale requires an accepted target hash"})
        if reviewed_digest:
            findings.extend({"code": item["code"], "path": rel, "detail": item["detail"]} for item in quality)
        rows.append({
            "path": rel,
            "file": source.name,
            "source_sha256": source_digest,
            "reviewed_source_sha256": reviewed_digest,
            "target_sha256": target_digest,
            "reviewed_target_sha256": reviewed_target,
            "target_representation": representation,
            "status": status,
            "quality": quality,
        })

    for rel in sorted(path for path in declared if path.endswith("SKILL.html")):
        source = root / rel
        target = locale_root / rel
        if source.is_file() and target.is_file() and skill_meta(source.read_text(encoding="utf-8")) != skill_meta(target.read_text(encoding="utf-8")):
            findings.append({"code": "skill-meta-drift", "path": rel,
                             "detail": "localized skill-meta differs from canonical JSON"})

    asset_rows = []
    for rel in sorted(declared_assets):
        source, target = root / rel, locale_root / rel
        source_raw = source.read_text(encoding="utf-8") if source.is_file() else ""
        target_raw = target.read_text(encoding="utf-8") if target.is_file() else ""
        review = asset_reviews.get(rel) or {}
        source_digest = sha(source_raw) if source_raw else None
        target_digest = sha(target_raw) if target_raw else None
        reviewed_target = review.get("target_sha256")
        require_target_review = bool(profile.get("reviewed_target_hashes"))
        quality = svg_quality(source_raw, target_raw, profile) if source_raw and target_raw else []
        if not target_raw:
            status = "missing"
        elif not review.get("source_sha256") or (require_target_review and not reviewed_target):
            status = "needs-review"
        elif review.get("source_sha256") != source_digest:
            status = "stale"
        elif require_target_review and reviewed_target != target_digest:
            status = "needs-review"
        elif quality:
            status = "blocked"
        else:
            status = "current"
        if review.get("source_sha256") and review.get("source_sha256") != source_digest:
            findings.append({"code": "stale-asset-source", "path": rel,
                             "detail": f"reviewed {review['source_sha256'][:12]}, source is {source_digest[:12]}"})
        if require_target_review and reviewed_target and reviewed_target != target_digest:
            findings.append({"code": "target-asset-drift", "path": rel,
                             "detail": f"reviewed target {reviewed_target[:12]}, target is {(target_digest or 'missing')[:12]}"})
        elif require_target_review and target_raw and not reviewed_target:
            findings.append({"code": "target-asset-unreviewed", "path": rel,
                             "detail": "locale requires an accepted target hash"})
        if review.get("source_sha256"):
            findings.extend({"code": item["code"], "path": rel, "detail": item["detail"]} for item in quality)
        asset_rows.append({"path": rel, "file": Path(rel).name, "source_sha256": source_digest,
                           "reviewed_source_sha256": review.get("source_sha256"),
                           "target_sha256": target_digest,
                           "reviewed_target_sha256": reviewed_target,
                           "status": status, "quality": quality})

    available = sorted(row["file"] for row in rows
                       if row["path"].startswith("web/nemoclaw/") and row["status"] == "current")
    manifest = {
        "schema": "nemoclaw-localization-drift/1",
        "locale": profile["locale"],
        "url_code": profile["url_code"],
        "label": profile["label"],
        "native_label": profile["native_label"],
        "available_pages": available,
        "counts": {name: sum(1 for row in rows if row["status"] == name)
                   for name in ("current", "stale", "blocked", "needs-review", "missing")},
        "pages": rows,
        "assets": asset_rows,
        "asset_counts": {name: sum(1 for row in asset_rows if row["status"] == name)
                         for name in ("current", "stale", "blocked", "needs-review", "missing")},
        "terminology_sources": profile.get("terminology_sources", []),
    }
    return findings, manifest


def manifest_path(root: Path, profile: dict) -> Path:
    return root / "web" / "nemoclaw" / "assets" / f"localization-{profile['url_code']}.json"


def manifest_bytes(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def write_manifest(root: Path, profile: dict, manifest: dict) -> Path:
    path = manifest_path(root, profile)
    path.write_text(manifest_bytes(manifest), encoding="utf-8")
    return path


def manifest_drift(root: Path, profile: dict, manifest: dict) -> list[dict[str, str]]:
    """Compare the tracked drift manifest with the manifest this scan just derived.

    The manifest is a generated projection, so a scan that rewrites it always passes. Without
    this comparison a change to the manifest schema or to any input it reads only surfaces when
    a build diffs its tracked source, long after the cheap checks have finished.
    """
    path = manifest_path(root, profile)
    rel = path.relative_to(root).as_posix()
    fix = f"regenerate with: python3 scripts/validation/localization_audit.py --locale {profile['locale']}"
    if not path.is_file():
        return [{"code": "manifest-projection-missing", "path": rel,
                 "detail": f"locale={profile['locale']}; correction={fix}"}]
    try:
        tracked = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [{"code": "manifest-projection-unreadable", "path": rel,
                 "detail": f"locale={profile['locale']}; {exc}; correction={fix}"}]
    if tracked != manifest:
        return [{"code": "manifest-projection-stale", "path": rel,
                 "detail": f"locale={profile['locale']}; tracked projection does not match this "
                           f"scan; correction={fix}"}]
    if path.read_text(encoding="utf-8") != manifest_bytes(manifest):
        return [{"code": "manifest-projection-format", "path": rel,
                 "detail": f"locale={profile['locale']}; tracked projection carries the right "
                           f"values in the wrong bytes; correction={fix}"}]
    return []


def _other_value(value: object) -> object:
    """A value of the same shape that no correct projection can also hold."""
    if isinstance(value, bool) or value is None:
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if isinstance(value, str):
        return value + "-drifted"
    if isinstance(value, list):
        return value + ["drifted"]
    if isinstance(value, dict):
        return {**value, "drifted": True}
    return "drifted"


def manifest_projection_mutations(manifest: dict) -> list[tuple[str, dict]]:
    """Structural mutations of a manifest, derived from the document rather than named fields.

    A field added to the projection later, such as a new per-page attribute, joins this matrix
    without a validator edit, so the freshness check cannot silently stop covering it.
    """
    mutations: list[tuple[str, dict]] = []
    for key in manifest:
        mutations.append((f"drop top-level {key}", {k: v for k, v in manifest.items() if k != key}))
        mutations.append((f"alter top-level {key}", {**manifest, key: _other_value(manifest[key])}))
    for key, value in manifest.items():
        if isinstance(value, list) and value:
            mutations.append((f"drop first {key} row", {**manifest, key: value[1:]}))
            mutations.append((f"duplicate first {key} row", {**manifest, key: [value[0], *value]}))
        if not (isinstance(value, list) and value and isinstance(value[0], dict)):
            continue
        for field in value[0]:
            dropped = [{k: v for k, v in value[0].items() if k != field}, *value[1:]]
            mutations.append((f"drop {key}[0].{field}", {**manifest, key: dropped}))
            altered = [{**value[0], field: _other_value(value[0][field])}, *value[1:]]
            mutations.append((f"alter {key}[0].{field}", {**manifest, key: altered}))
    return mutations


def accept(root: Path, locale: str, paths: list[str]) -> list[str]:
    spec = locale_by_tag(root, locale)
    locale_root, state_path, profile, state = (
        spec.locale_root, spec.state_path, dict(spec.profile), spec.state)
    svg_map = root / "scripts" / "translate" / "locales" / locale / "svg_translations.json"
    profile["_svg_translations"] = json.loads(svg_map.read_text(encoding="utf-8")) if svg_map.is_file() else {}
    shell_map = root / "scripts" / "translate" / "locales" / locale / "shell_translations.json"
    profile["_shell_translations"] = json.loads(shell_map.read_text(encoding="utf-8")) if shell_map.is_file() else {}
    errors: list[str] = []
    reviews = state.setdefault("reviews", {})
    asset_reviews = state.setdefault("asset_reviews", {})
    for rel in paths:
        source, target = root / rel, locale_root / rel
        if not source.is_file():
            errors.append(f"{rel}: canonical source missing")
            continue
        source_raw = source.read_text(encoding="utf-8")
        if target.is_file():
            target_raw = target.read_text(encoding="utf-8")
        elif source.suffix == ".html":
            resource_path = expected_resource_path(locale_root, rel)
            try:
                resource = load_resource(resource_path)
                if resource.locale != spec.locale or resource.template != rel:
                    raise LocaleResourceError(
                        f"resource identity does not match locale={spec.locale}, template={rel}")
                target_raw = render_overlay(source_raw, resource.values, spec.html_lang)
            except LocaleResourceError as exc:
                errors.append(f"{rel}: localized HTML target missing and resource is invalid: {exc}")
                continue
        else:
            errors.append(f"{rel}: localized target missing")
            continue
        style_reference = profile.get("review_protocol", {}).get("style_reference")
        quality = (svg_quality(source_raw, target_raw, profile) if source.suffix == ".svg" else
                   page_quality(source_raw, target_raw, profile, skill=source.name == "SKILL.html",
                                enforce_editorial_patterns=rel != style_reference))
        if quality:
            errors.append(f"{rel}: " + "; ".join(item["detail"] for item in quality))
            continue
        raw = source_raw
        if source.suffix == ".svg":
            asset_reviews[rel] = {"source_sha256": sha(raw), "target_sha256": sha(target_raw),
                                  "reviewed_on": date.today().isoformat()}
            continue
        if 'data-localization-scope="en-shell"' in raw:
            reviews[rel] = {"source_sha256": sha(raw), "translation_sha256": translation_sha(raw),
                            "target_sha256": sha(target_raw),
                            "reviewed_on": date.today().isoformat()}
        else:
            reviews[rel] = {"source_sha256": sha(raw), "target_sha256": sha(target_raw),
                            "reviewed_on": date.today().isoformat()}
    if not errors:
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return errors


def _manifest_projection_failures(root: Path, profile: dict, manifest: dict) -> list[str]:
    """Every way a tracked drift manifest can go stale must reach the projection detector."""
    failures: list[str] = []
    path = manifest_path(root, profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    codes = {item["code"] for item in manifest_drift(root, profile, manifest)}
    if "manifest-projection-missing" not in codes:
        failures.append("absent tracked drift manifest escaped the projection detector")
    write_manifest(root, profile, manifest)
    if manifest_drift(root, profile, manifest):
        failures.append("freshly written drift manifest was reported as stale")
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    if "manifest-projection-format" not in {
            item["code"] for item in manifest_drift(root, profile, manifest)}:
        failures.append("reformatted drift manifest escaped the projection detector")
    path.write_text("{not json", encoding="utf-8")
    if "manifest-projection-unreadable" not in {
            item["code"] for item in manifest_drift(root, profile, manifest)}:
        failures.append("corrupt drift manifest escaped the projection detector")
    for name, mutated in manifest_projection_mutations(manifest):
        path.write_text(manifest_bytes(mutated), encoding="utf-8")
        if "manifest-projection-stale" not in {
                item["code"] for item in manifest_drift(root, profile, manifest)}:
            failures.append(f"stale drift manifest escaped the projection detector: {name}")
    write_manifest(root, profile, manifest)
    return failures


def self_test() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="localization-audit-") as td:
        root = Path(td)
        profile_dir = root / "scripts/translate/locales/pt-BR"
        target_dir = root / "i18n/pt/web/nemoclaw"
        source_dir = root / "web/nemoclaw"
        profile_dir.mkdir(parents=True)
        target_dir.mkdir(parents=True)
        source_dir.mkdir(parents=True)
        (root / "i18n/pt/SKILL.html").write_text("<!doctype html>")
        (profile_dir / "SKILL.html").write_text("<!doctype html>")
        profile = {"schema": "nemoclaw-locale-profile/1",
                   "locale": "pt-BR", "url_code": "pt", "label": "Portuguese", "native_label": "Português",
                   "html_lang": "pt-BR", "english_sentence_markers": ["Course home"],
                   "english_ui_markers": ["Run the node"],
                   "unfit_phrases": {"soquete de raciocínio": "use etapa de decisão"}}
        profile["_svg_translations"] = {"Agent loop": "Ciclo do agente"}
        (profile_dir / "profile.json").write_text(json.dumps(profile))
        (profile_dir / "svg_translations.json").write_text(json.dumps(profile["_svg_translations"]))
        source_raw = '<!doctype html><html lang="en"><body><main id="lesson">Course home</main><script>const x=1; helpers.log("Run the node");</script></body></html>'
        target_raw = '<!doctype html><html lang="pt-BR"><body><main id="lesson">Início do curso</main><script>const x=1; helpers.log("Execute o nó");</script></body></html>'
        (source_dir / "index.html").write_text(source_raw)
        (target_dir / "index.html").write_text(target_raw)
        (root / "i18n/pt/locale.json").write_text(json.dumps({
            "schema": "nemoclaw-locale/1",
            "locale": "pt-BR",
            "url_code": "pt",
            "label": "Portuguese",
            "native_label": "Português",
            "profile": "scripts/translate/locales/pt-BR/profile.json",
            "source_root": "web",
            "overlay_root": "i18n/pt/web",
        }))
        state = {"schema": "nemoclaw-localization-state/1", "locale": "pt-BR", "url_code": "pt",
                 "overlay_files": ["web/nemoclaw/index.html"],
                 "reviews": {"web/nemoclaw/index.html": {"source_sha256": sha(source_raw)}}}
        (root / "i18n/pt/localization_state.json").write_text(json.dumps(state))
        base, base_manifest = scan(root, "pt-BR")
        if base:
            failures.append(f"clean fixture rejected: {base}")
        failures.extend(_manifest_projection_failures(root, profile, base_manifest))
        profile["review_protocol"] = {"style_reference": "web/nemoclaw/missing-style-reference.html"}
        (profile_dir / "profile.json").write_text(json.dumps(profile))
        style_findings, _ = scan(root, "pt-BR")
        if "style-reference-boundary" not in {item["code"] for item in style_findings}:
            failures.append("undeclared locale style reference escaped detector")
        profile["review_protocol"] = {
            "style_reference": "web/nemoclaw/index.html",
            "style_reference_origin_commit": "a" * 40,
            "style_reference_editorial_sha256": editorial_sha(target_raw),
        }
        (profile_dir / "profile.json").write_text(json.dumps(profile))
        (target_dir / "index.html").write_text(target_raw.replace("const x=1", "const x=2"))
        runtime_style, _ = scan(root, "pt-BR")
        if "style-reference-drift" in {item["code"] for item in runtime_style}:
            failures.append("runtime-only style-reference change tripped editorial pin")
        (target_dir / "index.html").write_text(target_raw.replace("Início do curso", "Curso inicial"))
        style_drift, _ = scan(root, "pt-BR")
        if "style-reference-drift" not in {item["code"] for item in style_drift}:
            failures.append("modified locale style prose escaped editorial-pin detector")
        (target_dir / "index.html").write_text(target_raw)
        profile.pop("review_protocol")
        profile["reviewed_target_hashes"] = True
        (profile_dir / "profile.json").write_text(json.dumps(profile))
        state["reviews"]["web/nemoclaw/index.html"]["target_sha256"] = sha(target_raw)
        (root / "i18n/pt/localization_state.json").write_text(json.dumps(state))
        (target_dir / "index.html").write_text(target_raw.replace("Início do curso", "Curso inicial"))
        target_changed, _ = scan(root, "pt-BR")
        if not any(item["code"] == "target-drift" for item in target_changed):
            failures.append("post-review localized prose mutation escaped target hash")
        (target_dir / "index.html").write_text(target_raw)
        cited_source = '<html lang="en"><a href="paper"><em>Canonical Paper Title</em></a></html>'
        cited_target = '<html lang="pt-BR"><a href="paper"><em>Título traduzido</em></a></html>'
        if "citation-title" not in {item["code"] for item in page_quality(cited_source, cited_target, profile)}:
            failures.append("translated citation title escaped detector")
        reference_source = ('<html lang="en"><div class="section" id="refs"><ul><li>Doe et al. (2025). '
                            '<a href="paper">The Canonical Paper Title.</a></li></ul></div>'
                            '<div id="learning-path">What comes next</div></html>')
        reference_target = ('<html lang="pt-BR"><div class="section" id="refs"><ul><li>Doe et al. (2025). '
                            '<a href="paper">The Canonical Paper Title.</a></li></ul></div>'
                            '<div id="learning-path">Próximos pasos</div></html>')
        reference_profile = {**profile, "english_sentence_markers": ["The ", "What "]}
        if page_quality(reference_source, reference_target, reference_profile):
            failures.append("canonical English reference title was rejected as untranslated prose")
        translated_reference = reference_target.replace("The Canonical Paper Title.", "Título traducido.")
        if "citation-title" not in {item["code"] for item in page_quality(reference_source, translated_reference, reference_profile)}:
            failures.append("translated reference-hub paper title escaped detector")
        line_source = '<html lang="en"><script>const x={lines:["Run the node"]}</script></html>'
        line_target = '<html lang="pt-BR"><script>const x={lines:["Run the node"]}</script></html>'
        if "untranslated-ui" not in {item["code"] for item in page_quality(line_source, line_target, profile)}:
            failures.append("English diagram line escaped detector")
        concat_ui_source = ('<html lang="en"><script>const x={intro:"Course home " + '
                            '"Run the node"};</script></html>')
        concat_ui_target = ('<html lang="pt-BR"><script>const x={intro:"Início do curso " + '
                            '"Run the node"};</script></html>')
        if "untranslated-ui" not in {
                item["code"] for item in page_quality(concat_ui_source, concat_ui_target, profile)}:
            failures.append("English continuation in concatenated learner UI escaped detector")
        editorial_profile = {**profile, "editorial_patterns": [{
            "code": "locale-article-agreement",
            "pattern": r"\buna\s+mensaje\b",
            "detail": "use un mensaje",
        }]}
        editorial_target = target_raw.replace("Início do curso", "Recebe una mensaje")
        if "locale-article-agreement" not in {
                item["code"] for item in page_quality(source_raw, editorial_target, editorial_profile)}:
            failures.append("locale editorial grammar pattern escaped detector")
        contraction_profile = {**profile, "editorial_patterns": [{
            "code": "locale-contraction",
            "pattern": r"\b(?:de el|a el)\b",
            "detail": "use del or al",
        }]}
        contraction_target = target_raw.replace("Início do curso", "Conecta a el agente")
        if "locale-contraction" not in {
                item["code"] for item in page_quality(
                    source_raw, contraction_target, contraction_profile)}:
            failures.append("invalid Spanish contraction escaped detector")
        boundary_contraction_source = ('<html lang="en"><table><tr><td>call '
                                       'through</td><td>the agent decides</td></tr></table></html>')
        boundary_contraction_target = ('<html lang="pt-BR"><table><tr><td>llamar a'
                                       '</td><td>el agente decide</td></tr></table></html>')
        if "locale-contraction" in {
                item["code"] for item in page_quality(
                    boundary_contraction_source, boundary_contraction_target,
                    contraction_profile)}:
            failures.append("editorial contraction detector crossed an HTML segment boundary")
        emphasis_source = '<html lang="en"><p>Course home text</p></html>'
        emphasis_target = '<html lang="pt-BR"><p>Texto do <i>curso</i></p></html>'
        if "structure-tags" in {item["code"] for item in page_quality(emphasis_source, emphasis_target, profile)}:
            failures.append("locale-only inline emphasis was rejected as structural drift")
        voice_profile = {**profile, "voice_rules": {
            "disallowed_formal_address": ["você"],
            "disallowed_formal_imperatives": ["Execute"],
        }}
        formal_target = target_raw.replace("Início do curso", "Você. Execute o nó")
        voice_codes = {item["code"] for item in page_quality(source_raw, formal_target, voice_profile)}
        if not {"locale-formal-address", "locale-formal-imperative"} <= voice_codes:
            failures.append("formal locale voice mutation escaped detector")
        lower_formal_target = target_raw.replace("Início do curso", "Edita el objetivo. Después, ejecute otra vez")
        lower_voice_profile = {**profile, "voice_rules": {"disallowed_formal_imperatives": ["ejecute"]}}
        if "locale-formal-imperative" not in {
                item["code"] for item in page_quality(source_raw, lower_formal_target, lower_voice_profile)}:
            failures.append("mixed-register lowercase imperative escaped detector")
        boundary_source = ('<html lang="en"><script>const x={label:"First field", '
                           'summary:"Run the node"};</script></html>')
        boundary_target = ('<html lang="pt-BR"><script>const x={label:"Primer campo", '
                           'summary:"Ejecute el nodo"};</script></html>')
        if "locale-formal-imperative" not in {
                item["code"] for item in page_quality(
                    boundary_source, boundary_target, lower_voice_profile)}:
            failures.append("formal imperative at a later UI-segment boundary escaped detector")
        register_profile = {**profile, "voice_rules": {"disallowed_formal_patterns": [{
            "pattern": r"(?:^|[.!?;:]\s+)(?:Puede|Podrá)\s+(?:cambiar|seguir)\b",
            "detail": "formal learner address",
        }, {
            "pattern": r"\bque\s+(?:conoció|construyó)\s+en\b",
            "detail": "formal prior-activity address",
        }, {
            "pattern": r"\bdonde verá\s+(?:el|la|los|las)\b",
            "detail": "formal learner observation",
        }]}}
        formal_narrative_target = target_raw.replace(
            "Início do curso", "Puede cambiar el ejemplo. Es la API que conoció en el módulo anterior")
        narrative_codes = {
            item["code"] for item in page_quality(source_raw, formal_narrative_target, register_profile)}
        if "locale-formal-address" not in narrative_codes:
            failures.append("formal narrative learner address escaped detector")
        formal_future_target = target_raw.replace(
            "Início do curso", "Ejecuta la celda, donde verá el resultado")
        if "locale-formal-address" not in {
                item["code"] for item in page_quality(
                    source_raw, formal_future_target, register_profile)}:
            failures.append("formal future learner observation escaped detector")
        impersonal_target = target_raw.replace(
            "Início do curso", "Un modelo que puede cambiar el resultado")
        if "locale-formal-address" in {
                item["code"] for item in page_quality(source_raw, impersonal_target, register_profile)}:
            failures.append("impersonal capability statement was misclassified as learner address")
        spacing_profile = {**profile, "orthography_rules": {"reject_space_before_punctuation": True}}
        spacing_target = target_raw.replace("Início do curso", "Conecta el agente . Después continúa")
        if "locale-punctuation-spacing" not in {
                item["code"] for item in page_quality(source_raw, spacing_target, spacing_profile)}:
            failures.append("space-before-punctuation artifact escaped detector")
        punctuation_profile = {**profile, "orthography_rules": {
            "require_balanced_opening_punctuation": True,
        }}
        punctuation_target = target_raw.replace(
            "Início do curso", "Qué cambia cuando ejecutas el agente?")
        if "locale-question-punctuation" not in {
                item["code"] for item in page_quality(
                    source_raw, punctuation_target, punctuation_profile)}:
            failures.append("missing Spanish opening-question punctuation escaped detector")
        exclamation_target = target_raw.replace(
            "Início do curso", "Ejecuta la celda ahora!")
        if "locale-exclamation-punctuation" not in {
                item["code"] for item in page_quality(
                    source_raw, exclamation_target, punctuation_profile)}:
            failures.append("missing Spanish opening-exclamation punctuation escaped detector")
        glyph_target = target_raw.replace(
            "Início do curso", "¿Necesitas un valor? Selecciona el ? junto al campo")
        if {"locale-question-punctuation", "locale-exclamation-punctuation"} & {
                item["code"] for item in page_quality(
                    source_raw, glyph_target, punctuation_profile)}:
            failures.append("a named on-screen ? glyph was misread as an unbalanced question")
        unbalanced_glyph_target = target_raw.replace(
            "Início do curso", "Selecciona el ? junto al campo. Qué cambia después?")
        if "locale-question-punctuation" not in {
                item["code"] for item in page_quality(
                    source_raw, unbalanced_glyph_target, punctuation_profile)}:
            failures.append("an unbalanced question beside a ? glyph escaped detector")
        repeat_profile = {**profile, "reject_accidental_repetition": True}
        repeat_target = target_raw.replace(
            "Início do curso", "Separa la aplicación de la aplicación de políticas")
        if "locale-accidental-repetition" not in {
                item["code"] for item in page_quality(source_raw, repeat_target, repeat_profile)}:
            failures.append("accidental nested repetition escaped detector")
        repeated_phrase_target = target_raw.replace(
            "Início do curso", "El agente conserva el contexto el agente conserva el contexto")
        if "locale-accidental-repetition" not in {
                item["code"] for item in page_quality(
                    source_raw, repeated_phrase_target, repeat_profile)}:
            failures.append("accidental repeated clause escaped detector")
        mixed_profile = {**profile,
                         "english_function_words": ["the", "and", "with", "your", "to"],
                         "english_function_word_threshold": 2}
        mixed_target = target_raw.replace(
            "Início do curso", "Ejecuta the agent to continue")
        if "locale-mixed-language" not in {
                item["code"] for item in page_quality(source_raw, mixed_target, mixed_profile)}:
            failures.append("short English residue escaped density detector")
        foreign_profile = {**profile,
                           "foreign_function_words": ["você", "não", "depois"],
                           "foreign_function_word_threshold": 2}
        foreign_target = target_raw.replace(
            "Início do curso", "Você executa o agente; depois, leia o resultado")
        if "locale-foreign-language" not in {
                item["code"] for item in page_quality(source_raw, foreign_target, foreign_profile)}:
            failures.append("neighboring-language residue escaped density detector")
        subordinate_target = target_raw.replace("Início do curso", "Indica al agente que cite la fuente")
        if "locale-formal-imperative" in {
                item["code"] for item in page_quality(source_raw, subordinate_target, lower_voice_profile)}:
            failures.append("subordinate present-tense verb was misclassified as a formal imperative")
        code_profile = {**profile, "canonical_code_templates": True}
        code_source = '<html lang="en"><script>const x={code:`return 1;`}</script></html>'
        code_target = '<html lang="pt-BR"><script>const x={code:`return 2;`}</script></html>'
        if "code-cell-drift" not in {item["code"] for item in page_quality(code_source, code_target, code_profile)}:
            failures.append("localized runnable-code mutation escaped detector")
        code_ui_source = (
            '<html lang="en"><script>const x={code:`helpers.mountChatUI("#x", '
            '{disabledMsg: "Connect your launchable to the gateway before using this panel."});'
            '`}</script></html>'
        )
        code_ui_target = code_ui_source.replace('lang="en"', 'lang="pt-BR"')
        if "locale-code-mixed-language" not in {
                item["code"] for item in page_quality(
                    code_ui_source, code_ui_target, mixed_profile)}:
            failures.append("English runnable-code UI escaped locale detector")
        localized_code_ui = code_ui_target.replace(
            "Connect your launchable to the gateway before using this panel.",
            "Conecte o launchable ao gateway antes de usar este painel.",
        )
        if "locale-code-mixed-language" in {
                item["code"] for item in page_quality(
                    code_ui_source, localized_code_ui, mixed_profile)}:
            failures.append("localized runnable-code UI was misclassified as English")
        terse_source = ('<html lang="en"><script>const x={code:`'
                        'helpers.log("raw output");`}</script></html>')
        terse_target = terse_source.replace('lang="en"', 'lang="es-ES"')
        if "locale-code-untranslated" not in {
                item["code"] for item in page_quality(
                    terse_source, terse_target, mixed_profile)}:
            failures.append("terse English runnable-code label escaped exact-source detector")
        referenced_target = terse_target.replace(
            '<script>', '<p>Abre <em>raw output</em> para inspeccionarlo.</p><script>')
        if "locale-code-untranslated" in {
                item["code"] for item in page_quality(
                    terse_source, referenced_target, mixed_profile)}:
            failures.append("human-referenced canonical runtime label was rejected")
        concat_source = '<html lang="en"><script>const x={code: PREFIX + `return 1;`}</script></html>'
        concat_target = '<html lang="pt-BR"><script>const x={code: PREFIX + `return 2;`}</script></html>'
        if "code-cell-drift" not in {item["code"] for item in page_quality(concat_source, concat_target, code_profile)}:
            failures.append("concatenated runnable-code mutation escaped detector")
        localized_code_profile = {**profile, "canonical_code_templates": False}
        localized_code_source = ('<html lang="en"><script>const x={code:`'
                                 'const job=await state.call("cron.add",{kind:"agentTurn"});'
                                 'helpers.log("installed job");`}</script></html>')
        localized_code_target = ('<html lang="pt-BR"><script>const x={code:`'
                                 'const job=await state.call("cron.add",{kind:"agentTurn"});'
                                 'helpers.log("tarefa instalada");`}</script></html>')
        localized_codes = {item["code"] for item in page_quality(
            localized_code_source, localized_code_target, localized_code_profile)}
        if "script-structure" in localized_codes or "code-contract-drift" in localized_codes:
            failures.append("translated runnable-code message was treated as executable drift")
        contract_target = localized_code_target.replace('"cron.add"', '"cron.agregar"')
        if "code-contract-drift" not in {item["code"] for item in page_quality(
                localized_code_source, contract_target, localized_code_profile)}:
            failures.append("localized RPC method mutation escaped detector")
        missing_source = '<html lang="en"><p>Course home contains a complete explanatory paragraph for students.</p></html>'
        missing_target = '<html lang="pt-BR"><p></p></html>'
        if "content-segments" not in {item["code"] for item in page_quality(missing_source, missing_target, profile)}:
            failures.append("missing localized prose segment escaped detector")
        compressed_source = ('<html lang="en"><p>This complete paragraph carries mechanism, '
                             'boundary, consequence, evidence, operating guidance, and concrete '
                             'instructions for every student.</p></html>')
        compressed_target = '<html lang="pt-BR"><p>Parágrafo com mecanismo e limite.</p></html>'
        ratio_profile = {**profile, "minimum_block_word_ratio": 0.6}
        if "content-shortfall" not in {
                item["code"] for item in page_quality(
                    compressed_source, compressed_target, ratio_profile)}:
            failures.append("compressed localized prose escaped retention-ratio detector")
        shifted_ui_source = ('<html lang="en"><script>const cells=['
                             '{label:"GET /healthz"},{label:"Describe workspace"}];</script></html>')
        shifted_ui_target = ('<html lang="pt-BR"><script>const cells=['
                             '{label:"Comprobar estado"},{label:"GET /healthz"}];</script></html>')
        if "segment-token-drift" not in {item["code"] for item in page_quality(shifted_ui_source, shifted_ui_target, profile)}:
            failures.append("learner UI path shifted between adjacent segments without detection")
        svg_rel = "web/nemoclaw/assets/figures/lesson.svg"
        svg_source = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 30" aria-label="Agent loop"><rect width="100" height="30"/><text x="5" y="20">Agent loop</text></svg>'
        svg_target = '<svg data-locale="pt-BR" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 30" aria-label="Ciclo do agente"><rect width="100" height="30"/><text x="5" y="20">Ciclo do agente</text></svg>'
        positioned_source = '<svg xmlns="http://www.w3.org/2000/svg"><text><tspan x="1 2 3">Run</tspan></text></svg>'
        positioned_target = '<svg data-locale="pt-BR" xmlns="http://www.w3.org/2000/svg"><text><tspan x="1 2 3">Executar</tspan></text></svg>'
        positioned_profile = {**profile, "_svg_translations": {"Run": "Executar"}}
        if "svg-glyph-positions" not in {item["code"] for item in svg_quality(positioned_source, positioned_target, positioned_profile)}:
            failures.append("translated text retaining source glyph positions escaped detector")
        terse_profile = {**positioned_profile, "rhythm_rules": {"short_sentence_run": 3, "short_sentence_words": 2}}
        terse_source = '<svg xmlns="http://www.w3.org/2000/svg" aria-label="Agent loop"><text>One.</text><text>Two.</text><text>Three.</text></svg>'
        terse_target = '<svg data-locale="pt-BR" xmlns="http://www.w3.org/2000/svg" aria-label="Ciclo do agente"><text>Um.</text><text>Dois.</text><text>Três.</text></svg>'
        terse_profile["_svg_translations"] = {"Agent loop": "Ciclo do agente", "One.": "Um.", "Two.": "Dois.", "Three.": "Três."}
        if "locale-choppy-run" in {item["code"] for item in svg_quality(terse_source, terse_target, terse_profile)}:
            failures.append("terse SVG labels were incorrectly treated as prose sentences")
        (root / svg_rel).parent.mkdir(parents=True)
        (root / svg_rel).write_text(svg_source)
        (root / "i18n/pt" / svg_rel).parent.mkdir(parents=True)
        (root / "i18n/pt" / svg_rel).write_text(svg_target)
        state["asset_files"] = [svg_rel]
        state["asset_reviews"] = {svg_rel: {"source_sha256": sha(svg_source), "target_sha256": sha(svg_target)}}
        (root / "i18n/pt/localization_state.json").write_text(json.dumps(state))
        svg_base, _ = scan(root, "pt-BR")
        if svg_base:
            failures.append(f"clean SVG fixture rejected: {svg_base}")
        (root / "i18n/pt" / svg_rel).write_text(svg_target.replace('<rect width="100"', '<rect width="90"'))
        svg_changed, _ = scan(root, "pt-BR")
        if not any(item["code"] == "svg-geometry" for item in svg_changed):
            failures.append("localized SVG geometry mutation was not rejected")
        (root / "i18n/pt" / svg_rel).write_text(svg_target.replace('data-locale="pt-BR" ', ""))
        svg_unmarked, _ = scan(root, "pt-BR")
        if not any(item["code"] == "svg-locale" for item in svg_unmarked):
            failures.append("unmarked localized SVG was not rejected")
        (root / "i18n/pt" / svg_rel).write_text(svg_target)
        scoped_raw = source_raw.replace(
            "Course home",
            '<details class="learning-block" data-localization-scope="en-shell"><summary data-localization-scope="en">Need detail?</summary><div class="learning-block-body">Course home</div></details>',
        )
        profile["_shell_translations"] = {"Need detail?": "Precisa de detalhes?"}
        if page_quality(scoped_raw, target_raw, profile):
            failures.append("English-only presentation shell changed locale structure checks")
        scoped_code_source = ('<html lang="en"><details data-localization-scope="en-shell">'
                              '<summary data-localization-scope="en">Need detail?</summary>'
                              '<div class="learning-block-body">Course home</div></details>'
                              '<script>const x={code:`// Keep this exact\nreturn 1;`}</script></html>')
        scoped_code_target = ('<html lang="pt-BR">Início do curso'
                              '<script>const x={code:`// Keep this exact\nreturn 1;`}</script></html>')
        scoped_code_mutation = scoped_code_target.replace("Keep this exact", "Compara this exact")
        scoped_code_profile = {**profile, "canonical_code_templates": True}
        if "code-cell-drift" not in {
                item["code"] for item in page_quality(
                    scoped_code_source, scoped_code_mutation, scoped_code_profile)}:
            failures.append("en-shell projection masked raw localized code drift")
        profile["_shell_translations"] = {}
        if "locale-projection" not in {item["code"] for item in page_quality(scoped_raw, target_raw, profile)}:
            failures.append("missing localized presentation shell escaped detector")
        profile["_shell_translations"] = {"Need detail?": "Precisa de detalhes?"}
        if (translation_sha(scoped_raw) != translation_sha(scoped_raw.replace("Need detail?", "Open detail?")) or
                translation_sha(scoped_raw) == translation_sha(scoped_raw.replace("Course home", "Changed lesson", 1))):
            failures.append("translation digest did not isolate controls from translatable body changes")
        cases = (
            ("html-lang", lambda: (target_dir / "index.html").write_text(target_raw.replace('lang="pt-BR"', 'lang="en"'))),
            ("untranslated-english", lambda: (target_dir / "index.html").write_text(target_raw.replace("Início do curso", "Course home"))),
            ("untranslated-ui", lambda: (target_dir / "index.html").write_text(target_raw.replace("Execute o nó", "Run the node"))),
            ("structure-tags", lambda: (target_dir / "index.html").write_text(target_raw.replace("</main>", "</section>"))),
            ("script-structure", lambda: (target_dir / "index.html").write_text(target_raw.replace("const x=1", "const x=2"))),
            ("stale-source", lambda: (source_dir / "index.html").write_text(source_raw.replace("Course home", "Course home changed"))),
            ("overlay-extra", lambda: (target_dir / "extra.js").write_text("x")),
        )
        for expected, mutate in cases:
            shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True)
            (target_dir / "index.html").write_text(target_raw)
            (source_dir / "index.html").write_text(source_raw)
            mutate()
            codes = {item["code"] for item in scan(root, "pt-BR")[0]}
            if expected not in codes:
                failures.append(f"mutation escaped detector: {expected}")
    with tempfile.TemporaryDirectory(prefix="localization-interface-") as td:
        fixture = Path(td)
        for rel in INTERFACE_CONTRACT:
            src, dst = ROOT / rel, fixture / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        if interface_findings(fixture):
            failures.append("clean localization interface fixture rejected")
        for rel, tokens in INTERFACE_CONTRACT.items():
            path = fixture / rel
            raw = path.read_text(encoding="utf-8")
            for index, token in enumerate(tokens):
                replacement = f"removed-contract-token-{index}"
                path.write_text(raw.replace(token, replacement), encoding="utf-8")
                if "interface-contract" not in {
                        item["code"] for item in interface_findings(fixture)}:
                    failures.append(
                        f"interface mutation escaped detector: {rel}: {token}")
                path.write_text(raw, encoding="utf-8")
        path = fixture / "web/nemoclaw/scripts/_locale.js"
        raw = path.read_text(encoding="utf-8")
        key = RUNTIME_UI_TRANSLATION_KEYS[0]
        needle = json.dumps(key, ensure_ascii=False) + ":"
        path.write_text(raw.replace(needle, '"removed-runtime-ui-key":', 1), encoding="utf-8")
        if "runtime-ui-translation" not in {item["code"] for item in interface_findings(fixture)}:
            failures.append("runtime UI translation mutation escaped detector")
        path.write_text(raw, encoding="utf-8")
        path = fixture / "web/nemoclaw/scripts/_keypanel.js"
        raw = path.read_text(encoding="utf-8")
        key = RUNTIME_UI_TRANSLATION_KEYS[1]
        path.write_text(raw.replace(key, "removed source UI key", 1), encoding="utf-8")
        if "runtime-ui-source-contract" not in {item["code"] for item in interface_findings(fixture)}:
            failures.append("runtime UI source mutation escaped detector")
        path.write_text(raw, encoding="utf-8")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", help="exact declared locale tag; omit to audit every locale")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--accept", action="append", default=[], metavar="REPO_PATH")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        if failures:
            print("localization audit self-test: FAIL")
            for item in failures:
                print(f"  - {item}")
            return 1
        print("localization audit self-test: OK")
        return 0
    if args.accept and not args.locale:
        parser.error("--accept requires --locale so review authority cannot cross locale boundaries")
    if args.accept:
        errors = accept(ROOT, args.locale, args.accept)
        if errors:
            print("localization accept: REFUSED")
            for item in errors:
                print(f"  - {item}")
            return 1
    try:
        specs = [locale_by_tag(ROOT, args.locale)] if args.locale else discover_locales(ROOT)
    except LocaleCatalogError as exc:
        print(f"localization audit: FAIL: {exc}")
        return 1
    findings: list[dict[str, str]] = []
    manifests: dict[str, dict] = {}
    for spec in specs:
        locale_findings, manifest = scan(ROOT, spec.locale)
        findings.extend(locale_findings)
        manifests[spec.locale] = manifest
        if not args.no_write:
            path = write_manifest(ROOT, spec.profile, manifest)
            print(f"localization manifest: {path.relative_to(ROOT)}")
    result = {
        "ok": not findings,
        "findings": findings,
        "manifest": next(iter(manifests.values())) if len(manifests) == 1 else None,
        "locales": manifests,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if findings:
        print(f"localization audit: FAIL ({len(findings)})")
        for item in findings:
            print(f"  [{item['code']}] {item['path']}: {item['detail']}")
        return 1
    summary = ", ".join(f"{locale}={manifest['counts']}" for locale, manifest in manifests.items())
    print(f"localization audit: OK ({summary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
