# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render a self-contained localized page from one canonical template and its locale resource.

Rendering happens before publication, so a reader never fetches translations at runtime. Structure
always comes from the template: a resource supplies values only, and every value it fails to supply
is an error rather than a silent English fallback.
"""
from __future__ import annotations

import re
from typing import Any

from runtime.html_document import raw_text_blocks_strict
from translate.code_localization import (
    body_contract_literals,
    code_template_matches,
    js_shape,
)
from translate.locale_projection import project_locale_html
from translate.locale_resources import (
    LocaleResourceError,
    authored_structure,
    code_copy_segments,
    fallback_identity,
    has_english_shell,
    template_units,
    validate_values,
)
from translate.translate_html_segments import extract_segments

HTML_LANG_RE = re.compile(r'(<html\b[^>]*\blang=["\'])[^"\']+(["\'])', re.I)


def _require_parity(source: list[Any], target: list[Any], label: str) -> None:
    if len(source) != len(target):
        raise LocaleResourceError(
            f"{label} count differs: template {len(source)}, reviewed translation {len(target)}"
        )


def extract_resource(source_raw: str, target_raw: str, locale: str, template: str,
                     untranslated_reasons: dict[str, str] | None = None,
                     provenance_reason: str | None = None) -> dict[str, Any]:
    """Derive a resource from a canonical template and its reviewed sparse overlay.

    Units are addressed positionally against ``template_units`` so a template that repeats one
    English source keeps each reviewed occurrence, rather than forcing a reviewer to reconcile
    wording the release already publishes.
    """
    canonical = extract_segments(authored_structure(source_raw))
    translated = extract_segments(target_raw)
    _require_parity(canonical, translated, "translatable segment")
    for index, (unit, target) in enumerate(zip(canonical, translated)):
        if unit.kind != target.kind:
            raise LocaleResourceError(f"segment kind differs at {index}: {unit.kind} != {target.kind}")
    source_code = code_template_matches(source_raw)
    target_code = code_template_matches(target_raw)
    _require_parity(source_code, target_code, "runnable code template")
    target_copy = []
    for index, (source_match, target_match) in enumerate(zip(source_code, target_code)):
        source_body = source_match.group(1)
        target_body = target_match.group(1)
        if js_shape(source_body) != js_shape(target_body):
            raise LocaleResourceError(
                f"runnable code structure differs at template {index}")
        if body_contract_literals(source_body) != body_contract_literals(target_body):
            raise LocaleResourceError(
                f"runnable code contract differs at template {index}")
        source_segments = code_copy_segments(source_body)
        target_segments = code_copy_segments(target_body)
        _require_parity(source_segments, target_segments, f"runnable copy at template {index}")
        if [item.kind for item in source_segments] != [item.kind for item in target_segments]:
            raise LocaleResourceError(
                f"runnable comment/string delimiters differ at template {index}")
        target_copy.extend(target_segments)
    units = template_units(source_raw)
    reviewed = [segment.text for segment in translated] + [
        segment.text for segment in target_copy]
    if len(units) != len(reviewed):
        raise LocaleResourceError(
            f"template unit count {len(units)} does not match the reviewed unit count "
            f"{len(reviewed)}"
        )
    values: dict[str, dict[str, str]] = {}
    for unit, target_text in zip(units, reviewed):
        _record(values, unit.key, unit.value_type, unit.source, target_text,
                (untranslated_reasons or {}).get(unit.key), provenance_reason)
    return {"schema": "nemoclaw-locale-resource/1", "locale": locale,
            "template": template, "values": values}


def _record(values: dict[str, dict[str, str]], key: str, value_type: str,
            source: str, translated: str, untranslated_reason: str | None = None,
            provenance_reason: str | None = None) -> None:
    existing = values.get(key)
    if existing is not None and existing["value"] != translated:
        raise LocaleResourceError(
            f"{key}: two distinct template units collide on one derived key; "
            "repair the derived-key identity before migrating this template"
        )
    entry = {"type": value_type, "source": source, "value": translated}
    if fallback_identity(value_type, translated) == fallback_identity(value_type, source):
        reason = untranslated_reason or provenance_reason
        if reason:
            entry["untranslated"] = reason
    values[key] = entry


def missing_keys(source_raw: str, values: dict[str, Any]) -> list[str]:
    """Return every template unit the resource does not supply."""
    return sorted({unit.key for unit in template_units(source_raw) if unit.key not in values})


def _script_shapes(raw: str) -> list[str]:
    """Return executable shapes through the package-free strict raw-text parser."""
    try:
        return [
            js_shape(script.body)
            for script in raw_text_blocks_strict(raw, "script")
            if "src" not in script.attributes
        ]
    except ValueError as exc:
        raise LocaleResourceError(f"localized script boundary is invalid: {exc}") from exc


def _code_contracts(raw: str) -> list[list[tuple[str, str]]]:
    return [
        body_contract_literals(match.group(1))
        for match in code_template_matches(raw)
    ]


def render_overlay(source_raw: str, values: dict[str, Any], html_lang: str) -> str:
    """Build the sparse localized page the existing quality and drift gates already read."""
    validate_values(source_raw, values)
    rendered = authored_structure(source_raw)
    canonical_script_shapes = _script_shapes(rendered)
    canonical_code_contracts = _code_contracts(rendered)
    units = template_units(source_raw)
    segments = extract_segments(rendered)
    # Substitution is positional, not by re-derived key: a unit that already carries a locale value
    # no longer hashes to its template address, and a repeated source has one key per occurrence.
    for segment, unit in reversed(list(zip(segments, units[:len(segments)]))):
        entry = values[unit.key]
        rendered = rendered[:segment.start] + entry["value"] + rendered[segment.end:]
    matches = code_template_matches(rendered)
    code_units = units[len(segments):]
    copy_segments = [
        (match.start(1) + segment.start, match.start(1) + segment.end)
        for match in matches
        for segment in code_copy_segments(match.group(1))
    ]
    if len(copy_segments) != len(code_units):
        raise LocaleResourceError(
            f"runnable copy count changed during rendering: template {len(code_units)}, "
            f"rendered {len(copy_segments)}"
        )
    for (start, end), unit in reversed(list(zip(copy_segments, code_units))):
        entry = values[unit.key]
        rendered = rendered[:start] + entry["value"] + rendered[end:]
    rendered = HTML_LANG_RE.sub(rf'\g<1>{html_lang}\2', rendered, count=1)
    if canonical_script_shapes != _script_shapes(rendered):
        raise LocaleResourceError(
            "localized script strings changed executable JavaScript structure"
        )
    if canonical_code_contracts != _code_contracts(rendered):
        raise LocaleResourceError(
            "localized runnable copy changed a protocol or configuration literal"
        )
    return rendered


def render_page(source_raw: str, values: dict[str, Any], shell_translations: dict[str, str],
                html_lang: str) -> str:
    """Render the published static page: template structure with reviewed locale values.

    The branch mirrors the assembler exactly. A shell-scoped page publishes the projection of its
    reviewed body onto the full template; every other page publishes the localized document itself,
    the way the assembler copies a non-scoped overlay verbatim.
    """
    overlay = render_overlay(source_raw, values, html_lang)
    if not has_english_shell(source_raw):
        return overlay
    try:
        return project_locale_html(source_raw, overlay, shell_translations)
    except ValueError as exc:
        raise LocaleResourceError(f"rendered page does not fit the current template: {exc}") from exc
