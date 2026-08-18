#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Translate learner-facing HTML segments without rewriting document/code structure.

The source page remains canonical. This tool translates text nodes, accessibility attributes,
and known learner-facing JavaScript string fields/calls, then writes a sparse locale overlay.
Model prompts, code bodies, identifiers, tags, and executable tokens remain untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from threading import Lock
from typing import Iterable

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root
from runtime.html_document import raw_text_blocks_strict
from translate.locale_catalog import locale_by_tag

ROOT = find_repo_root(Path(__file__).resolve())
TRANSLATION_REVISION = "locale-editorial-v6-zh-spacing"
SKIP_TEXT = {"script", "style", "pre", "code", "svg", "noscript"}
ATTRS = {"alt", "aria-label", "placeholder", "title"}
BLOCK_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "figcaption", "button", "option", "label", "summary", "td", "th", "a"}
BLOCK_DIV_CLASSES = {"callout", "step", "sys-desc", "num", "eyebrow"}
UI_FIELD_RE = re.compile(
    r'\b(?:label|intro|title|summary|greeting|disabledMsg|kicker|socket'
    r'|[A-Za-z_$][\w$]*[Hh]int)\s*:\s*(["\'])(.*?)(?<!\\)\1', re.S)
UI_LINES_RE = re.compile(r'\blines\s*:\s*\[(.*?)\]', re.S)
# Help-panel bodies are named by the field they document, so a name allowlist silently drops any
# new field. Take every template-literal object value instead; runnable `code` bodies are excluded
# by name here and by the code-range guard below.
UI_HELP_RE = re.compile(r'\b(?!code\b)[A-Za-z_$][\w$]*\s*:\s*`(.*?)`', re.S)
# Learner-visible DOM text assigned from JavaScript rather than declared in an object literal.
UI_ASSIGN_RE = re.compile(r'\.(?:textContent|innerText)\s*=\s*([^\n;]*);', re.S)
UI_TERNARY_RE = re.compile(r'\b(?:greeting|disabledMsg)\s*:\s*([^\n]+)')
JS_STRING_RE = re.compile(r'(["\'])(.*?)(?<!\\)\1', re.S)
UI_CALL_RE = re.compile(r'\b(?:helpers\.log|log(?:\.h|\.details|\.html)?|info|show)\s*\((.*?)\)\s*;', re.S)
PLACEHOLDER_RE = re.compile(r'(?:<code\b[^>]*>.*?</code>|<kbd\b[^>]*>.*?</kbd>|\\?\$\{[^}]+\}|\{\{[^}]+\}\}|https?://[^\s<"\']+|nvapi-|&[A-Za-z0-9#]+;|<[^>]+>)', re.S | re.I)

# Whitespace around inline markup is semantic in English but usually typographic noise in Chinese.
# Keep tags untouched and remove only a whitespace run whose nearest visible characters on both
# sides are Chinese. Block boundaries stop the lookup, while inline tags such as links and emphasis
# are transparent. This covers both ordinary line wrapping and Markdown-derived HTML such as
# ``中文<strong>重点</strong>内容`` without disturbing CJK/Latin boundaries.
ZH_CONTEXT_RE = re.compile(r"[\u3400-\u9fff\u3000-\u303f\uff01-\uff65]")
HTML_TAG_TOKEN_RE = re.compile(r"<[^>]+>", re.S)
ZH_INLINE_TAGS = {
    "a", "abbr", "b", "bdi", "bdo", "cite", "code", "data", "del", "dfn", "em",
    "i", "ins", "kbd", "mark", "q", "s", "samp", "small", "span", "strong", "sub",
    "sup", "time", "u", "var",
}


def _inline_tag_at(text: str, start: int, end: int) -> bool:
    token = text[start:end]
    match = re.match(r"<\s*/?\s*([A-Za-z][A-Za-z0-9-]*)\b", token)
    return bool(match and match.group(1).lower() in ZH_INLINE_TAGS)


def _visible_neighbor(text: str, position: int, direction: int) -> str | None:
    """Find one visible neighbor, treating inline HTML tags as transparent."""
    cursor = position
    while 0 <= cursor < len(text):
        if direction < 0 and text[cursor] == ">":
            start = text.rfind("<", 0, cursor + 1)
            if start < 0 or not _inline_tag_at(text, start, cursor + 1):
                return None
            cursor = start - 1
            continue
        if direction > 0 and text[cursor] == "<":
            match = HTML_TAG_TOKEN_RE.match(text, cursor)
            if match is None or not _inline_tag_at(text, match.start(), match.end()):
                return None
            cursor = match.end()
            continue
        if text[cursor].isspace():
            cursor += direction
            continue
        return text[cursor]
    return None


def normalize_zh_spacing(text: str) -> str:
    """Remove English authoring whitespace only at Chinese-to-Chinese inline boundaries."""
    replacements: list[tuple[int, int]] = []
    for match in re.finditer(r"\s+", text):
        left = _visible_neighbor(text, match.start() - 1, -1)
        right = _visible_neighbor(text, match.end(), 1)
        if left and right and ZH_CONTEXT_RE.fullmatch(left) and ZH_CONTEXT_RE.fullmatch(right):
            replacements.append((match.start(), match.end()))
    for start, end in reversed(replacements):
        text = text[:start] + text[end:]
    return text


def requests_client():
    """Load the network client only for authoring operations that call the translation API."""
    import requests  # type: ignore[import-not-found]
    return requests


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    text: str
    kind: str


@dataclass
class UsageLedger:
    """Thread-safe, secret-free request and provider-usage accounting."""

    model: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    attempts: int = 0
    completed: int = 0
    failed: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    request_seconds: float = 0.0
    pages: dict[str, dict[str, int]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record(self, page: str, seconds: float, usage: dict | None, *, failed: bool) -> None:
        usage = usage or {}
        with self._lock:
            self.attempts += 1
            self.request_seconds += seconds
            self.failed += int(failed)
            self.completed += int(not failed)
            row = self.pages.setdefault(page, {"attempts": 0, "completed": 0, "failed": 0,
                                               "prompt_tokens": 0, "completion_tokens": 0,
                                               "total_tokens": 0})
            row["attempts"] += 1
            row["failed"] += int(failed)
            row["completed"] += int(not failed)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                value = int(usage.get(key) or 0)
                setattr(self, key, getattr(self, key) + value)
                row[key] += value

    def report(self) -> dict:
        return {
            "schema": "nemoclaw-translation-usage/1",
            "model": self.model,
            "endpoint": "https://integrate.api.nvidia.com/v1/chat/completions",
            "started_at": self.started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "attempts": self.attempts,
            "completed": self.completed,
            "failed": self.failed,
            "provider_reported_usage": {
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": self.total_tokens,
            },
            "request_seconds": round(self.request_seconds, 3),
            "pages": self.pages,
        }


class SegmentParser(HTMLParser):
    def __init__(self, raw: str) -> None:
        super().__init__(convert_charrefs=False)
        self.raw = raw
        self.line_starts = [0]
        self.line_starts.extend(match.end() for match in re.finditer("\n", raw))
        self.skip_depth = 0
        self.segments: list[Segment] = []
        self.blocks: list[Segment] = []
        self.block_stack: list[tuple[str, int]] = []

    def absolute_offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self.absolute_offset()
        token = self.get_starttag_text() or ""
        tag = tag.lower()
        classes = set()
        for key, value in attrs:
            if key.lower() == "class" and value:
                classes.update(value.split())
        selected = tag in BLOCK_TAGS or (tag == "div" and bool(classes & BLOCK_DIV_CLASSES))
        if not self.skip_depth and selected:
            self.block_stack.append((tag, start + len(token)))
        if not self.skip_depth:
            attr_pattern = re.compile(r'(?i)\b(alt|aria-label|placeholder|title)\s*=\s*(["\'])(.*?)\2', re.S)
            for match in attr_pattern.finditer(token):
                value = match.group(3)
                if useful(value):
                    self.segments.append(Segment(start + match.start(3), start + match.end(3), value, "attribute"))
        if tag in SKIP_TEXT:
            self.skip_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() in SKIP_TEXT and self.skip_depth:
            self.skip_depth -= 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if not self.skip_depth:
            for index in range(len(self.block_stack) - 1, -1, -1):
                block_tag, content_start = self.block_stack[index]
                if block_tag == tag:
                    del self.block_stack[index:]
                    content_end = self.absolute_offset()
                    value = self.raw[content_start:content_end]
                    visible = re.sub(r"<[^>]+>", " ", value)
                    if useful(visible):
                        self.blocks.append(Segment(content_start, content_end, value, "block"))
                    break
        if tag in SKIP_TEXT and self.skip_depth:
            self.skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth or not data.strip():
            return
        left = len(data) - len(data.lstrip())
        right = len(data.rstrip())
        core = data[left:right]
        if useful(core):
            start = self.absolute_offset() + left
            self.segments.append(Segment(start, start + len(core), core, "text"))


def useful(text: str) -> bool:
    value = re.sub(r"\s+", " ", text).strip()
    # Source templates are English, but projection also parses rendered targets.
    # Accept CJK text so a Simplified Chinese locale preserves the same segment
    # topology checks already enforced for Latin-script locales.
    if len(value) < 2 or not re.search(r"[A-Za-z\u3400-\u9fff]", value):
        return False
    if re.fullmatch(r"(?:https?://|mailto:|#|\.?\.?/)[^\s]+", value):
        return False
    if re.fullmatch(r"[\w.-]+/[\w./-]+", value):
        return False
    return True


CODE_FIELD_RE = re.compile(r'\bcode\s*:\s*')
_STRING_DELIMITERS = "\"'`"


def code_value_ranges(body: str) -> list[tuple[int, int]]:
    """Return the span of every runnable ``code:`` value, however that value is written.

    A runnable cell body is not always one template literal: it can be a helper call that carries
    literals of its own. Matching only the literal shape leaves those inner strings looking like
    learner-facing prose, which would offer executable code for translation.
    """
    ranges: list[tuple[int, int]] = []
    for match in CODE_FIELD_RE.finditer(body):
        # A runnable body can mention ``code:`` in its own text. Never restart a span inside one.
        if any(begin <= match.start() < end for begin, end in ranges):
            continue
        start = match.end()
        depth = 0
        index = start
        quote: str | None = None
        while index < len(body):
            char = body[index]
            if quote:
                if char == "\\":
                    index += 2
                    continue
                if char == quote:
                    quote = None
            elif body.startswith("//", index):
                newline = body.find("\n", index)
                index = len(body) if newline < 0 else newline
                continue
            elif body.startswith("/*", index):
                close = body.find("*/", index + 2)
                index = len(body) if close < 0 else close + 2
                continue
            elif char in _STRING_DELIMITERS:
                quote = char
            elif char in "([{":
                depth += 1
            elif char in ")]}":
                if depth == 0:
                    break
                depth -= 1
            elif char == "," and depth == 0:
                break
            index += 1
        ranges.append((start, index))
    return ranges


def script_segments(raw: str) -> list[Segment]:
    out: list[Segment] = []
    for script in raw_text_blocks_strict(raw, "script"):
        body = script.body
        if "src" in script.attributes or "application/json" in script.attributes.get("type", "").casefold():
            continue
        body_start = script.body_start
        code_ranges = code_value_ranges(body)

        def inside_code(position: int) -> bool:
            return any(start <= position < end for start, end in code_ranges)

        for match in UI_FIELD_RE.finditer(body):
            text = match.group(2)
            if useful(text) and not inside_code(match.start(2)):
                out.append(Segment(body_start + match.start(2), body_start + match.end(2), text, "script-ui"))
            cursor = match.end()
            while True:
                continuation = re.match(r'\s*\+\s*(["\'])(.*?)(?<!\\)\1', body[cursor:], re.S)
                if not continuation:
                    break
                extra = continuation.group(2)
                extra_start = cursor + continuation.start(2)
                if useful(extra) and not inside_code(extra_start):
                    out.append(Segment(body_start + extra_start,
                                       body_start + cursor + continuation.end(2),
                                       extra, "script-ui"))
                cursor += continuation.end()
        for call in UI_CALL_RE.finditer(body):
            if inside_code(call.start()):
                continue
            for match in JS_STRING_RE.finditer(call.group(1)):
                text = match.group(2)
                if useful(text):
                    start = body_start + call.start(1) + match.start(2)
                    out.append(Segment(start, body_start + call.start(1) + match.end(2), text, "script-ui"))
        for array in UI_LINES_RE.finditer(body):
            if inside_code(array.start()):
                continue
            for match in JS_STRING_RE.finditer(array.group(1)):
                text = match.group(2)
                if useful(text):
                    start = body_start + array.start(1) + match.start(2)
                    out.append(Segment(start, body_start + array.start(1) + match.end(2), text, "script-ui"))
        for match in UI_HELP_RE.finditer(body):
            text = match.group(1)
            if useful(text) and not inside_code(match.start(1)):
                out.append(Segment(body_start + match.start(1), body_start + match.end(1), text, "script-ui"))
        for field in UI_TERNARY_RE.finditer(body):
            if "?" not in field.group(1) or inside_code(field.start(1)):
                continue
            for match in JS_STRING_RE.finditer(field.group(1)):
                text = match.group(2)
                if useful(text):
                    start = body_start + field.start(1) + match.start(2)
                    out.append(Segment(start, body_start + field.start(1) + match.end(2), text, "script-ui"))
        for assignment in UI_ASSIGN_RE.finditer(body):
            if inside_code(assignment.start(1)):
                continue
            for match in JS_STRING_RE.finditer(assignment.group(1)):
                text = match.group(2)
                if useful(text):
                    start = body_start + assignment.start(1) + match.start(2)
                    out.append(Segment(start, body_start + assignment.start(1) + match.end(2),
                                       text, "script-ui"))
    return out


def extract_segments(raw: str) -> list[Segment]:
    parser = SegmentParser(raw)
    parser.feed(raw)
    blocks: list[Segment] = []
    for item in sorted(parser.blocks, key=lambda segment: (segment.start, -segment.end)):
        if not any(item.start >= parent.start and item.end <= parent.end for parent in blocks):
            blocks.append(item)
    uncovered = [item for item in parser.segments
                 if not any(item.start >= block.start and item.end <= block.end for block in blocks)]
    candidates = blocks + uncovered + script_segments(raw)
    unique: dict[tuple[int, int], Segment] = {}
    for item in candidates:
        unique[(item.start, item.end)] = item
    ordered = sorted(unique.values(), key=lambda item: (item.start, item.end))
    for previous, current in zip(ordered, ordered[1:]):
        if previous.end > current.start:
            raise ValueError(f"overlapping translation segments: {previous} / {current}")
    return ordered


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def api_key() -> str:
    load_env(ROOT / ".env-dev")
    for name in ("NVIDIA_API_KEY", "NGC_API_KEY"):
        if os.environ.get(name):
            return os.environ[name]
    raise RuntimeError("no NVIDIA_API_KEY or NGC_API_KEY available")


def batches(items: list[tuple[str, ...]], max_items: int = 16, max_chars: int = 6000) -> Iterable[list[tuple[str, ...]]]:
    batch: list[tuple[str, ...]] = []
    chars = 0
    for item in items:
        size = sum(len(value) for value in item[1:])
        if batch and (len(batch) >= max_items or chars + size > max_chars):
            yield batch
            batch, chars = [], 0
        batch.append(item)
        chars += size
    if batch:
        yield batch


def parse_json_array(content: str) -> list[dict[str, str]]:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    start, end = content.find("["), content.rfind("]")
    if start < 0 or end < start:
        raise ValueError("model response did not contain a JSON array")
    data = json.loads(content[start:end + 1])
    if not isinstance(data, list):
        raise ValueError("model response was not a JSON list")
    return data


def translate_batch(batch: list[tuple[str, ...]], profile: dict, model: str, key: str, polish: bool,
                    ledger: UsageLedger, page: str) -> dict[str, str]:
    requests = requests_client()
    terminology = "; ".join(f"{source} => {target}" for source, target in profile.get("preferred_terms", {}).items())
    rejected = "; ".join(f"{phrase} ({fix})" for phrase, fix in profile.get("unfit_phrases", {}).items())
    revising = bool(batch and len(batch[0]) == 3)
    payload = [({"id": item[0], "source": item[1], "draft": item[2]}
                if len(item) == 3 else {"id": item[0], "source": item[1]}) for item in batch]
    language_name = profile.get("language_name", profile["native_label"])
    audience = profile.get("audience", f"students and software developers who use {language_name}")
    locale_guidance = profile.get("generation_guidance", "Use natural technical language for the target audience.")
    review_dimensions = "; ".join(profile.get("review_protocol", {}).get("required_dimensions", []))
    if revising:
        action = (f"Revise each {language_name} draft against its English source. Preserve every technical fact and "
                  "the full teaching sequence, but rewrite machine-like prose as fluent developer documentation. "
                  "Do not merely patch spelling or grammar; replace unnatural syntax and literal calques.")
    elif polish:
        action = (f"Edit each {language_name} source for grammar, agreement, precision, rhythm, and natural technical flow. "
                  "Do not retranslate technical tokens that were deliberately preserved.")
    else:
        action = f"Translate each source into natural {language_name}."
    examples = profile.get("editorial_examples", [])
    example_guidance = ("\nAuthoritative editorial examples (English source followed by style-PIC Spanish):\n" +
                        json.dumps(examples, ensure_ascii=False, indent=2)) if examples else ""
    system = f"""You localize an NVIDIA course for {audience}.
{action}
Produce natural, publication-quality {language_name} while preserving full technical meaning and teaching sequence.
Return ONLY a JSON array of objects with exactly keys id and translation, one per input id.
Preserve HTML tags, entities, escaped characters, ${{...}} placeholders, URLs, file paths, code identifiers, API fields,
model IDs, product names, and English titles of cited papers/books. Do not translate model prompts or invent explanations.
Avoid literal calques. Check articles, gender, number, prepositions, rhythm, and sentence flow after translating. Prefer
concise, fluent instructional prose. Avoid repetitive sentence openings, slogan cadence, and stacked noun phrases.
{locale_guidance}
Review dimensions: {review_dimensions or "semantic fidelity; technical precision; natural flow; grammar"}
Terminology: {terminology}
Rejected literal translations: {rejected}
{example_guidance}"""
    started = time.monotonic()
    try:
        response = requests.post(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
                "temperature": 0.1,
                "max_tokens": 8000,
            },
            timeout=180,
        )
    except requests.RequestException:
        ledger.record(page, time.monotonic() - started, None, failed=True)
        raise
    try:
        body = response.json()
    except requests.JSONDecodeError:
        body = {}
    usage = body.get("usage", {}) if response.ok else {}
    ledger.record(page, time.monotonic() - started, usage, failed=not response.ok)
    if not response.ok:
        raise RuntimeError(f"translation API HTTP {response.status_code}: {response.text[:300]}")
    content = body["choices"][0]["message"].get("content") or ""
    result = {}
    for row in parse_json_array(content):
        if isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("translation"), str):
            result[row["id"]] = row["translation"]
    return result


def protected_tokens(text: str) -> list[str]:
    return PLACEHOLDER_RE.findall(text)


def restore_protected(source: str, target: str) -> str:
    expected = protected_tokens(source)
    matches = list(PLACEHOLDER_RE.finditer(target))
    if len(expected) != len(matches):
        return target
    for match, token in zip(reversed(matches), reversed(expected)):
        target = target[:match.start()] + token + target[match.end():]
    return target


def valid_translation(source: str, target: str) -> bool:
    if not target.strip():
        return False
    return protected_tokens(source) == protected_tokens(target)


def clean_translation(source: str, target: str, locale: str = "") -> str:
    if "\\n" not in source:
        target = target.replace("\\n", " ")
    if "\\t" not in source:
        target = target.replace("\\t", " ")
    if locale.casefold().startswith("zh"):
        target = normalize_zh_spacing(target)
    return target


def cache_key(locale: str, source: str, draft: str = "", mode: str = "translate") -> str:
    return hashlib.sha256(
        f"{TRANSLATION_REVISION}\0{locale}\0{mode}\0{source}\0{draft}".encode("utf-8")
    ).hexdigest()


def load_cache(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def translate_page(source_path: Path, target_path: Path, profile: dict, model: str, cache_path: Path,
                   dry_run: bool, workers: int, polish: bool, revise: bool,
                   ledger: UsageLedger) -> tuple[int, int]:
    input_path = target_path if polish or revise else source_path
    if (polish or revise) and not input_path.is_file():
        raise FileNotFoundError(f"cannot polish missing target: {target_path}")
    raw = input_path.read_text(encoding="utf-8")
    segments = extract_segments(raw)
    source_segments = segments
    if revise:
        # Imported lazily: localization_scope imports extract_segments from this module.
        from translate.localization_scope import translation_canonical
        canonical_source = translation_canonical(source_path.read_text(encoding="utf-8"))
        source_segments = extract_segments(canonical_source)
        if (len(source_segments) != len(segments)
                or [item.kind for item in source_segments] != [item.kind for item in segments]):
            raise ValueError(
                f"cannot revise source/target with different segment shape: "
                f"source {len(source_segments)}, target {len(segments)}"
            )
    cache = load_cache(cache_path)
    mode = "revise" if revise else "polish" if polish else "translate"
    distinct: dict[str, tuple[str, ...]] = {}
    for source_segment, target_segment in zip(source_segments, segments):
        draft = target_segment.text if revise else ""
        key = cache_key(profile["locale"], source_segment.text, draft, mode)
        distinct.setdefault(key, (source_segment.text, draft) if revise else (source_segment.text,))
    missing = [(key, *values) for key, values in distinct.items()
               if key not in cache or not valid_translation(
                   values[-1] if revise else values[0], clean_translation(
                       values[-1] if revise else values[0], cache[key], profile["locale"]))]
    label = f"{source_path.relative_to(ROOT)} ({mode})"
    print(f"{label}: {len(segments)} segments, {len(distinct)} distinct, {len(missing)} API", flush=True)
    if dry_run:
        return len(segments), len(missing)
    requests = requests_client()
    key = api_key()
    work = list(enumerate(batches(missing), 1))

    def run_batch(index: int, batch: list[tuple[str, ...]]) -> tuple[int, dict[str, str]]:
        translated: dict[str, str] | None = None
        for attempt in range(3):
            try:
                translated = translate_batch(batch, profile, model, key, polish, ledger, label)
                break
            except (requests.RequestException, RuntimeError, ValueError, json.JSONDecodeError) as exc:
                if attempt == 2:
                    raise
                print(f"  batch {index}: retry {attempt + 1}: {exc}", flush=True)
                time.sleep(2 ** attempt)
        assert translated is not None
        accepted = {}
        bad = []
        for item in batch:
            item_id, source = item[:2]
            protected_source = item[2] if len(item) == 3 else source
            target = clean_translation(
                protected_source,
                restore_protected(protected_source, translated.get(item_id, "")),
                profile["locale"],
            )
            if valid_translation(protected_source, target):
                accepted[item_id] = target
            else:
                bad.append(item)
        for item in bad:
            item_id, source = item[:2]
            protected_source = item[2] if len(item) == 3 else source
            repaired = ""
            for attempt in range(3):
                try:
                    one = translate_batch([item], profile, model, key, polish, ledger, label)
                    repaired = clean_translation(
                        protected_source,
                        restore_protected(protected_source, one.get(item_id, "")),
                        profile["locale"],
                    )
                    if valid_translation(protected_source, repaired):
                        break
                except (requests.RequestException, RuntimeError, ValueError, json.JSONDecodeError):
                    pass
                time.sleep(2 ** attempt)
            if valid_translation(protected_source, repaired):
                accepted[item_id] = repaired
            elif polish:
                accepted[item_id] = source
                print(f"  batch {index}: retained one protected source segment", flush=True)
            else:
                raise ValueError(f"missing/placeholder-invalid translation for {item_id[:10]}")
        return index, accepted

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(run_batch, index, batch) for index, batch in work]
        for future in as_completed(futures):
            index, accepted = future.result()
            cache.update(accepted)
            save_cache(cache_path, cache)
            print(f"  batch {index}/{len(work)}: {len(accepted)} translated", flush=True)
    replacements = []
    for source_segment, target_segment in zip(source_segments, segments):
        draft = target_segment.text if revise else ""
        value = clean_translation(
            target_segment.text,
            cache[cache_key(profile["locale"], source_segment.text, draft, mode)],
            profile["locale"],
        )
        replacements.append((target_segment.start, target_segment.end, value))
    translated_raw = raw
    for start, end, value in sorted(replacements, reverse=True):
        translated_raw = translated_raw[:start] + value + translated_raw[end:]
    translated_raw = re.sub(r'(<html\b[^>]*\blang=)(["\'])[^"\']*\2',
                            rf'\1"{profile["html_lang"]}"', translated_raw, count=1, flags=re.I)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(translated_raw, encoding="utf-8")
    return len(segments), len(missing)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pages", nargs="+")
    parser.add_argument("--locale", default="pt-BR")
    parser.add_argument("--model", default="meta/llama-3.3-70b-instruct")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--polish", action="store_true")
    parser.add_argument("--revise-against-source", action="store_true",
                        help="revise an existing locale target using both canonical English and current draft")
    parser.add_argument("--usage-report", type=Path,
                        help="write secret-free provider token/request accounting JSON")
    args = parser.parse_args()
    if args.polish and args.revise_against_source:
        parser.error("--polish and --revise-against-source are mutually exclusive")
    spec = locale_by_tag(ROOT, args.locale)
    profile = spec.profile
    if args.cache is None:
        args.cache = Path(f"/tmp/nemoclaw-{profile['url_code']}-translation-cache-v1.json")
    locale_root = spec.locale_root
    ledger = UsageLedger(args.model)
    for raw_page in args.pages:
        source = (ROOT / raw_page).resolve()
        try:
            rel = source.relative_to(ROOT)
        except ValueError:
            parser.error(f"outside repository: {raw_page}")
        allowed = rel in {Path("web/index.html"), Path("web/courses.html")} or rel.parts[:2] == ("web", "nemoclaw")
        if not source.is_file() or not allowed or source.suffix != ".html":
            parser.error(f"not a learner-facing HTML source: {raw_page}")
        translate_page(source, locale_root / rel, profile, args.model, args.cache, args.dry_run, args.workers,
                       args.polish, args.revise_against_source, ledger)
    if args.usage_report:
        args.usage_report.parent.mkdir(parents=True, exist_ok=True)
        args.usage_report.write_text(json.dumps(ledger.report(), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
