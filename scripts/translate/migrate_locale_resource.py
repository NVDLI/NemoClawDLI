#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Derive a key-based locale resource from a reviewed sparse overlay, or check one against it.

Migration never retranslates. The resource records wording a language reviewer already accepted
while moving authored markup and executable syntax back to the shared template. The preflight
reports any resulting publication-byte difference for review.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root
from translate.locale_catalog import LocaleCatalogError, locale_by_tag
from translate.locale_resource_render import extract_resource
from translate.locale_resources import (
    applicable_media,
    derive_key,
    dump_resource,
    LocaleResourceError,
    expected_resource_path,
    load_resource,
    safe_template_path,
    source_identity,
    template_units,
    validate_values,
)
from translate.localization_scope import translation_sha

ROOT = find_repo_root(Path(__file__).resolve())
MODEL_ID_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+$")
MODEL_ID_CHAR = r"[A-Za-z0-9._/-]"


def _text_sha(raw: str) -> str:
    return hashlib.sha256(raw.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def review_provenance(locale: str, template: str) -> str:
    """Record where a decision to keep the English source was already reviewed.

    This is a provenance record, not an invented rationale. ``build`` reaches this line only after
    the reviewed overlay's accepted source digest matches the tree, and so does its accepted target
    digest for a locale that requires target hashes. The English wording at this unit is therefore
    bytes a language reviewer already accepted. A hand-authored resource has no overlay to derive
    from and still fails closed until a reviewer records the decision.
    """
    return (
        f"kept English: the reviewed {locale} overlay of {template} carries the canonical source "
        "at this unit unchanged"
    )


def build(root: Path, locale: str, template: str) -> tuple[Path, str]:
    """Return the resource path and serialized document for one reviewed page."""
    spec = locale_by_tag(root, locale)
    relative = safe_template_path(template, "web")
    source = root / relative
    overlay = spec.locale_root / relative
    for path, label in ((source, "canonical template"), (overlay, "reviewed overlay")):
        if not path.is_file():
            raise LocaleResourceError(f"{path}: {label} is missing")
    template_name = relative.as_posix()
    if template_name not in {
            Path(item).as_posix() for item in spec.state.get("overlay_files", [])}:
        raise LocaleResourceError(
            f"{overlay}: overlay is not declared in localization_state.json")
    source_raw = source.read_text(encoding="utf-8")
    overlay_raw = overlay.read_text(encoding="utf-8")
    scoped = 'data-localization-scope="en-shell"' in source_raw
    review = spec.state.get("reviews", {}).get(template_name, {})
    source_field = "translation_sha256" if scoped else "source_sha256"
    source_digest = translation_sha(source_raw) if scoped else _text_sha(source_raw)
    if review.get(source_field) != source_digest:
        raise LocaleResourceError(
            f"{overlay}: overlay was not reviewed against the current canonical template")
    if (
        spec.profile.get("reviewed_target_hashes")
        and review.get("target_sha256") != _text_sha(overlay_raw)
    ):
        raise LocaleResourceError(
            f"{overlay}: overlay bytes do not match the accepted locale target hash")
    resource_path = expected_resource_path(spec.locale_root, relative.as_posix())
    existing_reasons: dict[str, str] = {}
    if resource_path.is_file():
        existing = load_resource(resource_path)
        existing_reasons = {
            key: entry["untranslated"]
            for key, entry in existing.values.items()
            if isinstance(entry.get("untranslated"), str) and entry["untranslated"].strip()
        }
        # A key-derivation repair can rename an entry without changing reviewed wording. Carry the
        # decision to the exact current template unit, including whitespace-sensitive code copy.
        for unit in template_units(source_raw):
            for entry in existing.values.values():
                reason = entry.get("untranslated")
                if (
                    isinstance(reason, str)
                    and reason.strip()
                    and entry.get("type") == unit.value_type
                    and source_identity(unit.kind, entry.get("source", ""))
                    == source_identity(unit.kind, unit.source)
                ):
                    existing_reasons.setdefault(unit.key, reason)
                    break
    document = extract_resource(
        source_raw, overlay_raw,
        spec.locale, relative.as_posix(), existing_reasons,
        provenance_reason=review_provenance(spec.locale, template_name),
    )
    media = applicable_media(
        relative.as_posix(), source_raw, spec.state.get("asset_files", []))
    if media:
        document["media"] = list(media)
    return resource_path, dump_resource(document)


def _replace_exact_model(text: str, previous: str, current: str) -> tuple[str, int]:
    pattern = re.compile(
        rf"(?<!{MODEL_ID_CHAR}){re.escape(previous)}(?!{MODEL_ID_CHAR})"
    )
    return pattern.subn(current, text)


def rebind_model_values(
    source_raw: str,
    values: dict[str, dict[str, str]],
    previous: str,
    current: str,
) -> dict[str, dict[str, str]]:
    """Carry reviewed wording across one exact model-ID replacement and nothing else."""
    return rebind_model_values_many(source_raw, values, [(previous, current)])


def rebind_model_values_many(
    source_raw: str,
    values: dict[str, dict[str, str]],
    replacements: list[tuple[str, str]],
) -> dict[str, dict[str, str]]:
    """Carry reviewed wording across exact model-ID replacements and nothing else."""
    if not all(MODEL_ID_RE.fullmatch(item) for pair in replacements for item in pair):
        raise LocaleResourceError("model rebind requires complete model IDs")
    return rebind_exact_values_many(source_raw, values, replacements)


def insert_exact_values(
    source_raw: str,
    values: dict[str, dict[str, str]],
    literals: list[str],
) -> dict[str, dict[str, str]]:
    """Add newly introduced language-neutral interface literals without translation review."""
    if not literals or any(not item.strip() for item in literals) or len(literals) != len(set(literals)):
        raise LocaleResourceError("exact insertion requires distinct non-empty literals")
    units = template_units(source_raw)
    missing = [unit for unit in units if unit.key not in values]
    if any(unit.source not in literals for unit in missing):
        raise LocaleResourceError("current template changed outside the declared literal insertion")
    unused = sorted(set(values) - {unit.key for unit in units})
    if unused:
        raise LocaleResourceError(f"literal insertion would drop reviewed values: {unused}")
    absent = sorted(set(literals) - {unit.source for unit in missing})
    if absent:
        raise LocaleResourceError(f"current template does not introduce declared literals: {absent}")
    inserted = {key: dict(entry) for key, entry in values.items()}
    for unit in missing:
        inserted[unit.key] = {
            "type": unit.value_type,
            "source": unit.source,
            "value": unit.source,
            "untranslated": "kept English: exact executable code, protocol, punctuation, or interface literal",
        }
    validate_values(source_raw, inserted)
    return inserted


def rebind_exact_values_many(
    source_raw: str,
    values: dict[str, dict[str, str]],
    replacements: list[tuple[str, str]],
) -> dict[str, dict[str, str]]:
    """Carry reviewed wording across bounded literal replacements and nothing else."""
    if (
        not replacements
        or any(previous == current for previous, current in replacements)
        or any(not item.strip() for pair in replacements for item in pair)
        or len({item for pair in replacements for item in pair}) != 2 * len(replacements)
    ):
        raise LocaleResourceError("exact rebind requires distinct non-empty pairs")
    for previous, current in replacements:
        _, previous_count = _replace_exact_model(source_raw, previous, current)
        if previous_count:
            raise LocaleResourceError("current template still contains a previous model ID")
        _, current_count = _replace_exact_model(source_raw, current, previous)
        if not current_count:
            raise LocaleResourceError("current template does not contain every replacement model ID")

    rebound: dict[str, dict[str, str]] = {}
    consumed: set[str] = set()
    rebound_occurrences = 0
    for unit in template_units(source_raw):
        entry = values.get(unit.key)
        if entry is not None:
            rebound[unit.key] = dict(entry)
            consumed.add(unit.key)
            continue

        previous_source = unit.source
        unit_counts: list[int] = []
        for previous, current in replacements:
            previous_source, count = _replace_exact_model(previous_source, current, previous)
            unit_counts.append(count)
        if not any(unit_counts):
            raise LocaleResourceError(
                f"{unit.key}: current template changed outside the declared model rebind"
            )
        occurrence = int(unit.key.rsplit("~", 1)[1]) if "~" in unit.key else 0
        previous_key = derive_key(unit.kind, previous_source, occurrence)
        entry = values.get(previous_key)
        if entry is None:
            raise LocaleResourceError(
                f"{unit.key}: no reviewed value exists for previous key {previous_key}"
            )
        recorded_source = entry["source"]
        translated_value = entry["value"]
        source_counts: list[int] = []
        value_counts: list[int] = []
        for previous, current in replacements:
            recorded_source, count = _replace_exact_model(recorded_source, previous, current)
            source_counts.append(count)
            translated_value, count = _replace_exact_model(translated_value, previous, current)
            value_counts.append(count)
        if source_counts != unit_counts or value_counts != unit_counts or recorded_source != unit.source:
            raise LocaleResourceError(
                f"{previous_key}: reviewed source/value do not carry the exact model token"
            )
        updated = dict(entry)
        updated["source"] = unit.source
        updated["value"] = translated_value
        rebound[unit.key] = updated
        consumed.add(previous_key)
        rebound_occurrences += sum(unit_counts)

    if not rebound_occurrences:
        raise LocaleResourceError("no locale resource value references the previous model ID")
    unused = sorted(set(values) - consumed)
    if unused:
        raise LocaleResourceError(
            f"model rebind would drop reviewed values: {unused}"
        )
    validate_values(source_raw, rebound)
    return rebound


def rebind_models(
    root: Path,
    locale: str,
    template: str,
    replacements: list[tuple[str, str]],
    literals: list[tuple[str, str]] | None = None,
    insert_literals: list[str] | None = None,
) -> tuple[Path, str]:
    """Re-key one authoritative locale resource after exact model-ID replacements."""
    spec = locale_by_tag(root, locale)
    relative = safe_template_path(template, "web")
    source = root / relative
    if not source.is_file():
        raise LocaleResourceError(f"{source}: canonical template is missing")
    resource_path = expected_resource_path(spec.locale_root, relative.as_posix())
    resource = load_resource(resource_path)
    if resource.locale != spec.locale or resource.template != relative.as_posix():
        raise LocaleResourceError(f"{resource_path}: locale or template identity differs")
    source_raw = source.read_text(encoding="utf-8")
    values = resource.values
    if replacements or literals:
        values = (
            rebind_exact_values_many(source_raw, values, replacements + (literals or []))
            if literals else rebind_model_values_many(source_raw, values, replacements)
        )
    if insert_literals:
        values = insert_exact_values(source_raw, values, insert_literals)
    document = {
        "schema": "nemoclaw-locale-resource/1",
        "locale": resource.locale,
        "template": resource.template,
        "values": values,
    }
    if resource.media:
        document["media"] = list(resource.media)
    return resource_path, dump_resource(document)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", required=True, help="exact declared locale tag")
    parser.add_argument("--template", required=True, help="repository path of the shared template")
    parser.add_argument("--check", action="store_true",
                        help="compare the tracked resource with the reviewed overlay instead of writing")
    parser.add_argument(
        "--rebind-model", nargs=2, action="append", metavar=("PREVIOUS", "CURRENT"),
        help="re-key an authoritative resource after exact canonical model-ID replacements",
    )
    parser.add_argument(
        "--rebind-literal", nargs=2, action="append", metavar=("PREVIOUS", "CURRENT"),
        help="also carry a bounded language-neutral label or code token",
    )
    parser.add_argument(
        "--insert-literal", action="append", default=[], metavar="LITERAL",
        help="add a newly introduced language-neutral interface literal",
    )
    args = parser.parse_args()
    try:
        path, document = (
            rebind_models(
                ROOT, args.locale, args.template,
                [tuple(pair) for pair in (args.rebind_model or [])],
                [tuple(pair) for pair in (args.rebind_literal or [])],
                args.insert_literal,
            )
            if args.rebind_model or args.rebind_literal or args.insert_literal
            else build(ROOT, args.locale, args.template)
        )
    except (LocaleCatalogError, LocaleResourceError, ValueError) as exc:
        print(f"migrate locale resource: FAIL: {exc}", file=sys.stderr)
        return 1
    relative = path.relative_to(ROOT)
    if args.check:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current != document:
            print(f"migrate locale resource: FAIL: {relative} differs from the reviewed overlay",
                  file=sys.stderr)
            return 1
        print(f"migrate locale resource: OK {relative}")
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    print(f"migrate locale resource: wrote {relative}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
