#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Translate learner-facing SVG text while preserving authored geometry and markup."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root
from translate.locale_catalog import locale_by_tag
from translate.translate_html_segments import (
    Segment,
    UsageLedger,
    api_key,
    batches,
    cache_key,
    clean_translation,
    load_cache,
    restore_protected,
    save_cache,
    translate_batch,
    useful,
    valid_translation,
)

ROOT = find_repo_root(Path(__file__).resolve())
ATTR_RE = re.compile(r'\b(?:aria-label|title)\s*=\s*(["\'])(.*?)\1', re.S | re.I)
TEXT_RE = re.compile(r'<(?:text|tspan)\b[^>]*>([^<>]+)</(?:text|tspan)>', re.S | re.I)
TSPAN_RE = re.compile(r'(<tspan\b[^>]*\bx=")([^"]+)("[^>]*>)([^<]*)(</tspan>)', re.S | re.I)


def extract_svg_segments(raw: str) -> list[Segment]:
    found: dict[tuple[int, int], Segment] = {}
    for match in ATTR_RE.finditer(raw):
        value = match.group(2)
        if useful(value):
            found[(match.start(2), match.end(2))] = Segment(match.start(2), match.end(2), value, "attribute")
    for match in TEXT_RE.finditer(raw):
        value = match.group(1)
        left = len(value) - len(value.lstrip())
        right = len(value.rstrip())
        core = value[left:right]
        if useful(core):
            start = match.start(1) + left
            found[(start, start + len(core))] = Segment(start, start + len(core), core, "text")
    return [found[key] for key in sorted(found)]


def normalize_translated_tspan_positions(source_raw: str, translated_raw: str) -> str:
    """Replace source per-glyph positions when translated labels change length."""
    source_spans = list(TSPAN_RE.finditer(source_raw))
    target_spans = list(TSPAN_RE.finditer(translated_raw))
    if len(source_spans) != len(target_spans):
        return translated_raw
    replacements: list[tuple[int, int, str]] = []
    for source, target in zip(source_spans, target_spans):
        if source.group(4) == target.group(4):
            continue
        positions = target.group(2).split()
        if len(positions) < 2:
            continue
        try:
            center = (float(positions[0]) + float(positions[-1])) / 2
        except ValueError:
            continue
        suffix = target.group(3)
        if "text-anchor=" not in suffix:
            suffix = suffix[:-1] + ' text-anchor="middle">'
        replacement = target.group(1) + f"{center:.3f}" + suffix + target.group(4) + target.group(5)
        replacements.append((target.start(), target.end(), replacement))
    for start, end, value in reversed(replacements):
        translated_raw = translated_raw[:start] + value + translated_raw[end:]
    return translated_raw


def translate_svg(source: Path, target: Path, profile: dict, model: str, cache_path: Path,
                  workers: int, dry_run: bool, ledger: UsageLedger, dictionary: dict[str, str],
                  no_api: bool) -> tuple[int, int]:
    raw = source.read_text(encoding="utf-8")
    segments = extract_svg_segments(raw)
    cache = load_cache(cache_path)
    for source_text, target_text in dictionary.items():
        cache[cache_key(profile["locale"], source_text)] = target_text
    distinct = {cache_key(profile["locale"], item.text): item.text for item in segments}
    missing = [(key, text) for key, text in distinct.items()
               if key not in cache or not valid_translation(text, clean_translation(text, cache[key]))]
    label = source.relative_to(ROOT).as_posix()
    print(f"{label}: {len(segments)} SVG strings, {len(missing)} API", flush=True)
    if dry_run:
        return len(segments), len(missing)
    if no_api and missing:
        missing_text = "\n".join(f"  - {text}" for _, text in missing)
        raise ValueError(f"SVG translation dictionary misses {len(missing)} strings in {label}:\n{missing_text}")
    key = api_key() if missing else ""
    for index, batch in enumerate(batches(missing), 1):
        translated = translate_batch(batch, profile, model, key, False, ledger, label)
        for item_id, source_text in batch:
            value = clean_translation(source_text, restore_protected(source_text, translated.get(item_id, "")))
            if not valid_translation(source_text, value):
                raise ValueError(f"missing/placeholder-invalid SVG translation for {item_id[:10]}")
            cache[item_id] = value
        save_cache(cache_path, cache)
        print(f"  batch {index}: {len(batch)} translated", flush=True)
    replacements = [(item.start, item.end, clean_translation(item.text, cache[cache_key(profile["locale"], item.text)]))
                    for item in segments]
    translated_raw = raw
    for start, end, value in sorted(replacements, reverse=True):
        translated_raw = translated_raw[:start] + value + translated_raw[end:]
    translated_raw = normalize_translated_tspan_positions(raw, translated_raw)
    translated_raw = re.sub(r"<svg\b", f'<svg data-locale="{profile["locale"]}"', translated_raw, count=1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(translated_raw, encoding="utf-8")
    return len(segments), len(missing)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("assets", nargs="+")
    parser.add_argument("--locale", default="pt-BR")
    parser.add_argument("--model", default="meta/llama-3.3-70b-instruct")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-api", action="store_true", help="require every string from the locale SVG dictionary")
    parser.add_argument("--usage-report", type=Path)
    args = parser.parse_args()
    spec = locale_by_tag(ROOT, args.locale)
    profile = spec.profile
    if args.cache is None:
        args.cache = Path(f"/tmp/nemoclaw-{profile['url_code']}-svg-translation-cache-v1.json")
    dictionary_path = spec.profile_path.parent / "svg_translations.json"
    dictionary = json.loads(dictionary_path.read_text(encoding="utf-8")) if dictionary_path.is_file() else {}
    locale_root = spec.locale_root
    ledger = UsageLedger(args.model)
    for raw_asset in args.assets:
        source = (ROOT / raw_asset).resolve()
        try:
            rel = source.relative_to(ROOT)
        except ValueError:
            parser.error(f"outside repository: {raw_asset}")
        if not source.is_file() or rel.parts[:4] != ("web", "nemoclaw", "assets", "figures") or source.suffix != ".svg":
            parser.error(f"not a course figure SVG: {raw_asset}")
        translate_svg(source, locale_root / rel, profile, args.model, args.cache, args.workers, args.dry_run,
                      ledger, dictionary, args.no_api)
    if args.usage_report:
        args.usage_report.parent.mkdir(parents=True, exist_ok=True)
        args.usage_report.write_text(json.dumps(ledger.report(), indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
