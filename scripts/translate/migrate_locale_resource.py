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
    LocaleResourceError,
    dump_resource,
    expected_resource_path,
    load_resource,
    safe_template_path,
    source_identity,
    template_units,
)
from translate.localization_scope import translation_sha

ROOT = find_repo_root(Path(__file__).resolve())


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale", required=True, help="exact declared locale tag")
    parser.add_argument("--template", required=True, help="repository path of the shared template")
    parser.add_argument("--check", action="store_true",
                        help="compare the tracked resource with the reviewed overlay instead of writing")
    args = parser.parse_args()
    try:
        path, document = build(ROOT, args.locale, args.template)
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
