#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Gate key-based locale resources and the static pages they render.

Locales, templates, and resource files are discovered from the tree, so adding a page or a language
never edits this file. Valid JSON is not the bar: every resource is rendered and the rendered page
carries the same structure, links, and quality gates the reviewed overlay already answers to.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import add_script_paths, find_repo_root

add_script_paths(find_repo_root(Path(__file__).resolve()) / "scripts")
from translate.locale_catalog import LocaleCatalogError, LocaleSpec, discover_locales
from translate.locale_projection import project_locale_html
from translate.locale_resource_render import render_overlay, render_page
from translate.locale_resources import (
    applicable_media,
    base_key,
    bounded_tree_path,
    LocaleResourceError,
    consumer_map,
    expected_resource_path,
    has_english_shell,
    json_resources,
    load_resource,
    normalize,
    safe_template_path,
    template_units,
    unsupported_files,
    value_findings,
)
from translate.localization_scope import translation_sha

ROOT = find_repo_root(Path(__file__).resolve())
SOURCE_ROOT = "web"
TEMPLATE_SUFFIX = ".html"
BEACON_NAME = "SKILL.html"


def _finding(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def discover_templates(root: Path) -> dict[str, str]:
    """Return every shared page template a locale resource is allowed to translate."""
    source = root / SOURCE_ROOT
    if source.is_symlink():
        raise LocaleResourceError(f"{source}: template root must not be a symlink")
    source_resolved = source.resolve()
    templates: dict[str, str] = {}
    for path in sorted(source.rglob(f"*{TEMPLATE_SUFFIX}")) if source.is_dir() else ():
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise LocaleResourceError(f"{path}: shared page templates must not use symlinks")
        try:
            path.resolve().relative_to(source_resolved)
        except ValueError as exc:
            raise LocaleResourceError(f"{path}: shared page template escapes {source}") from exc
        rel = path.relative_to(root)
        if path.name == BEACON_NAME:
            continue
        try:
            templates[rel.as_posix()] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise LocaleResourceError(f"{path}: cannot read shared page template: {exc}") from exc
    return templates


def _locale_quality(root: Path, spec: LocaleSpec) -> dict:
    """Load the locale profile the reusable page checks read, plus its shell wording map."""
    profile = dict(spec.profile)
    shell = spec.profile_path.parent / "shell_translations.json"
    profile["_shell_translations"] = (
        json.loads(shell.read_text(encoding="utf-8")) if shell.is_file() else {}
    )
    return profile


def _display_resource_path(resource) -> str:
    parts = resource.path.parts
    if "i18n" in parts:
        return Path(*parts[parts.index("i18n"):]).as_posix()
    return resource.path.name


def _excerpt(value: object, limit: int = 180) -> object:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit - 3] + "..."
    return value


def _resource_context(resource, key: str, consumers: dict[str, list[str]],
                      correction: str) -> str:
    entry = resource.values.get(key)
    actual = _excerpt(entry.get("value") if isinstance(entry, dict) else entry)
    return (
        f"locale={resource.locale}; resource={_display_resource_path(resource)}; key={key}; "
        f"actual={actual!r}; rendered_page={resource.template}; "
        f"consuming_templates={consumers.get(key) or []}; correction={correction}"
    )


def _inferred_template(spec: LocaleSpec, path: Path) -> str:
    try:
        relative = path.relative_to(spec.locale_root / "resources").as_posix()
    except ValueError:
        return "<unreachable>"
    return relative[:-5] if relative.endswith(".json") else "<unreachable>"


def _diagnostic_context(
    *,
    locale: object,
    resource: object,
    key: str,
    actual: object,
    rendered_page: object,
    consuming_templates: object,
    correction: str,
) -> str:
    return (
        f"locale={locale}; resource={resource}; key={key}; actual={_excerpt(actual)!r}; "
        f"rendered_page={rendered_page}; consuming_templates={consuming_templates}; "
        f"correction={correction}"
    )


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def review_findings(spec: LocaleSpec, resource, template_raw: str,
                    profile: dict) -> list[dict[str, str]]:
    """Reject review drift that would make a resource-authoritative page fall back to English."""
    if (spec.locale_root / resource.template).is_file():
        return []
    scoped = 'data-localization-scope="en-shell"' in template_raw
    source_digest = translation_sha(template_raw) if scoped else _sha(template_raw)
    review = spec.state.get("reviews", {}).get(resource.template, {})
    reviewed_source = (
        review.get("translation_sha256") if scoped else review.get("source_sha256")
    )
    rel = _display_resource_path(resource)
    out: list[dict[str, str]] = []
    if reviewed_source != source_digest:
        out.append(_finding(
            "resource-hidden-fallback",
            rel,
            f"locale={resource.locale}; resource={rel}; key=<publication-authority>; "
            f"actual={reviewed_source!r}; rendered_page={resource.template}; "
            f"consuming_templates={[resource.template]}; correction=accept the current template "
            "digest for this resource or restore its reviewed HTML override",
        ))
        return out
    if profile.get("reviewed_target_hashes"):
        try:
            rendered = render_overlay(template_raw, resource.values, spec.html_lang)
        except LocaleResourceError:
            return out
        reviewed_target = review.get("target_sha256")
        if reviewed_target != _sha(rendered):
            out.append(_finding(
                "resource-hidden-fallback",
                rel,
                f"locale={resource.locale}; resource={rel}; key=<publication-authority>; "
                f"actual={reviewed_target!r}; rendered_page={resource.template}; "
                f"consuming_templates={[resource.template]}; correction=have the locale reviewer "
                "accept the rendered resource target hash or restore its reviewed HTML override",
            ))
    return out


def key_findings(resource, units, consumers: dict[str, list[str]]) -> list[dict[str, str]]:
    """Report missing, unused, mistyped, unreachable, or conflicting keys for one resource."""
    out: list[dict[str, str]] = []
    rel = _display_resource_path(resource)
    required = {unit.key: unit for unit in units}
    for key in sorted(set(required) - set(resource.values)):
        unit = required[key]
        out.append(_finding(
            "resource-key-missing", rel,
            _resource_context(
                resource, key, consumers,
                f"add the {unit.value_type} value for source {unit.source[:80]!r} to {rel}",
            ),
        ))
    for key in sorted(set(resource.values) - set(required)):
        owners = consumers.get(key) or []
        reach = f"consumed only by {owners}" if owners else "consumed by no discovered template"
        out.append(_finding(
            "resource-key-unreachable", rel,
            _resource_context(
                resource, key, consumers,
                f"delete the unused entry ({reach}) or restore its template unit",
            ),
        ))
    for key in sorted(set(required) & set(resource.values)):
        for detail in value_findings(required[key], resource.values[key]):
            out.append(_finding(
                "resource-value", rel,
                _resource_context(resource, key, consumers, detail),
            ))
    return out


def media_findings(root: Path, spec: LocaleSpec, resource, template_raw: str,
                   profile: dict) -> list[dict[str, str]]:
    """Require every declared locale media override to be referenced, present, and reviewed."""
    out: list[dict[str, str]] = []
    expected = set(applicable_media(
        resource.template, template_raw, spec.state.get("asset_files", [])))
    declared_assets = {Path(item).as_posix() for item in spec.state.get("asset_files", [])}
    asset_reviews = spec.state.get("asset_reviews", {})
    reviewed_assets = set(asset_reviews)
    resource_rel = resource.path.relative_to(root).as_posix()
    for item in sorted(expected - set(resource.media)):
        out.append(_finding(
            "resource-media-missing-declaration", resource_rel,
            _diagnostic_context(
                locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                actual="<missing declaration>", rendered_page=resource.template,
                consuming_templates=[resource.template],
                correction="add this reviewed localized asset to the resource media list",
            ),
        ))
    for item in resource.media:
        candidate = Path(item)
        if candidate.is_absolute() or ".." in candidate.parts or candidate.parts[:1] != (SOURCE_ROOT,):
            out.append(_finding(
                "resource-media-boundary", resource_rel,
                _diagnostic_context(
                    locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                    actual=item, rendered_page=resource.template,
                    consuming_templates=[resource.template],
                    correction=f"name a canonical {SOURCE_ROOT}/ asset inside the locale root",
                ),
            ))
            continue
        try:
            source = bounded_tree_path(root, item)
            target = bounded_tree_path(spec.locale_root, item)
        except LocaleResourceError as exc:
            out.append(_finding(
                "resource-media-boundary", resource_rel,
                _diagnostic_context(
                    locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                    actual=str(exc), rendered_page=resource.template,
                    consuming_templates=[resource.template],
                    correction="replace the symlinked media input or parent with a regular file "
                    "inside its declared canonical or locale tree",
                ),
            ))
            continue
        if item not in expected:
            out.append(_finding(
                "resource-media-unreferenced", resource_rel,
                _diagnostic_context(
                    locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                    actual=item, rendered_page=resource.template,
                    consuming_templates=[resource.template],
                    correction="remove the media entry or reference the reviewed override from the template",
                ),
            ))
        if not target.is_file():
            out.append(_finding(
                "resource-media-missing", resource_rel,
                _diagnostic_context(
                    locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                    actual="<missing locale file>", rendered_page=resource.template,
                    consuming_templates=[resource.template],
                    correction=f"restore the declared locale media under {spec.locale_root.name}",
                ),
            ))
        if not source.is_file():
            out.append(_finding(
                "resource-media-canonical-missing", resource_rel,
                _diagnostic_context(
                    locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                    actual="<missing canonical file>", rendered_page=resource.template,
                    consuming_templates=[resource.template],
                    correction="restore the canonical media referenced by the shared template",
                ),
            ))
        if item not in declared_assets:
            out.append(_finding(
                "resource-media-undeclared", resource_rel,
                _diagnostic_context(
                    locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                    actual="<absent from asset_files>", rendered_page=resource.template,
                    consuming_templates=[resource.template],
                    correction="declare the localized media in asset_files so its review gate owns it",
                ),
            ))
        elif item not in reviewed_assets:
            out.append(_finding(
                "resource-media-unreviewed", resource_rel,
                _diagnostic_context(
                    locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                    actual="<absent from asset_reviews>", rendered_page=resource.template,
                    consuming_templates=[resource.template],
                    correction="accept the localized media source and target hashes",
                ),
            ))
        else:
            review = asset_reviews[item]
            source_digest = _sha(source.read_text(encoding="utf-8")) if source.is_file() else None
            target_digest = _sha(target.read_text(encoding="utf-8")) if target.is_file() else None
            if review.get("source_sha256") != source_digest:
                out.append(_finding(
                    "resource-media-review-drift",
                    resource_rel,
                    _diagnostic_context(
                        locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                        actual=review.get("source_sha256"), rendered_page=resource.template,
                        consuming_templates=[resource.template],
                        correction="review the localized asset against the current canonical "
                        "source before this resource can publish it",
                    ),
                ))
            if (
                profile.get("reviewed_target_hashes")
                and review.get("target_sha256") != target_digest
            ):
                out.append(_finding(
                    "resource-media-target-drift",
                    resource_rel,
                    _diagnostic_context(
                        locale=resource.locale, resource=resource_rel, key=f"<media:{item}>",
                        actual=review.get("target_sha256"), rendered_page=resource.template,
                        consuming_templates=[resource.template],
                        correction="accept the exact localized asset target hash before publication",
                    ),
                ))
    return out


def rendered_findings(spec: LocaleSpec, resource, template_raw: str,
                      profile: dict) -> list[dict[str, str]]:
    """Render the static page and hold the output to the reviewed-overlay quality bar."""
    from localization_audit import page_quality, tag_skeleton

    shell = profile["_shell_translations"]
    try:
        overlay = render_overlay(template_raw, resource.values, spec.html_lang)
        page = render_page(template_raw, resource.values, shell, spec.html_lang)
    except LocaleResourceError as exc:
        return [_finding(
            "resource-render", _display_resource_path(resource),
            _diagnostic_context(
                locale=resource.locale,
                resource=_display_resource_path(resource),
                key="<rendered-output>",
                actual=str(exc),
                rendered_page=resource.template,
                consuming_templates=[resource.template],
                correction="repair the typed locale value so rendering preserves the shared "
                "template's HTML and JavaScript boundaries",
            ),
        )]
    out = [
        _finding(
            "resource-rendered-quality",
            _display_resource_path(resource),
            _diagnostic_context(
                locale=resource.locale,
                resource=_display_resource_path(resource),
                key="<rendered-output>",
                actual=f"{item.get('code', 'quality')}: {item.get('detail', '')}",
                rendered_page=resource.template,
                consuming_templates=[resource.template],
                correction="repair the typed locale value in the named resource so the rendered "
                "page passes this existing locale page-quality rule",
            ),
        )
        for item in page_quality(
            template_raw,
            overlay,
            profile,
            reviewed_untranslated=tuple(
                entry["value"]
                for entry in resource.values.values()
                if isinstance(entry.get("untranslated"), str)
            ),
        )
    ]
    if tag_skeleton(page) != tag_skeleton(template_raw):
        out.append(_finding(
            "resource-rendered-structure", _display_resource_path(resource),
            _diagnostic_context(
                locale=resource.locale,
                resource=_display_resource_path(resource),
                key="<rendered-output>",
                actual="rendered tag skeleton differs from the shared template",
                rendered_page=resource.template,
                consuming_templates=[resource.template],
                correction="restore the template tag and attribute-name structure",
            ),
        ))
    out.extend(_overlay_equivalence(spec, resource, template_raw, page, shell))
    return out


def _overlay_equivalence(spec: LocaleSpec, resource, template_raw: str, page: str,
                         shell: dict) -> list[dict[str, str]]:
    """While a page still ships from a reviewed overlay, the resource must render it exactly."""
    overlay_path = spec.locale_root / resource.template
    if not overlay_path.is_file():
        return []
    overlay_raw = overlay_path.read_text(encoding="utf-8")
    if not has_english_shell(template_raw):
        # The assembler copies a non-scoped overlay verbatim, so those bytes are the published page.
        published = overlay_raw
        return [] if published == page else [_finding(
            "resource-publication-drift", _display_resource_path(resource),
            f"locale={resource.locale}; rendered_page={resource.template}; "
            f"resource={_display_resource_path(resource)}; overlay={resource.template}; "
            f"consuming_templates={[resource.template]}; "
            "correction=re-extract the resource or restore the reviewed value bytes",
        )]
    try:
        published = project_locale_html(template_raw, overlay_raw, shell)
    except ValueError as exc:
        return [_finding(
            "resource-overlay-projection", _display_resource_path(resource),
            f"locale={resource.locale}; rendered_page={resource.template}; "
            f"consuming_templates={[resource.template]}; overlay={resource.template}; "
            f"correction=repair the reviewed overlay before migration: {exc}",
        )]
    if published != page:
        return [_finding(
            "resource-publication-drift", _display_resource_path(resource),
            f"locale={resource.locale}; rendered_page={resource.template}; "
            f"resource={_display_resource_path(resource)}; overlay={resource.template}; "
            f"consuming_templates={[resource.template]}; "
            "correction=re-extract the resource or restore the reviewed value bytes",
        )]
    return []


def _resource_findings(root: Path, spec: LocaleSpec, path: Path, templates: dict[str, str],
                       consumers: dict[str, list[str]], profile: dict) -> list[dict[str, str]]:
    rel = path.relative_to(root).as_posix()
    try:
        resource = load_resource(path, source_root=SOURCE_ROOT)
    except LocaleResourceError as exc:
        inferred = _inferred_template(spec, path)
        return [_finding(
            "resource-schema", rel,
            _diagnostic_context(
                locale=spec.locale, resource=rel, key="<schema>", actual=str(exc),
                rendered_page=inferred,
                consuming_templates=[inferred] if inferred in templates else [],
                correction="repair the JSON schema and typed value named by the error",
            ),
        )]
    if resource.locale != spec.locale:
        return [_finding(
            "resource-locale", rel,
            _diagnostic_context(
                locale=spec.locale, resource=rel, key="<locale>", actual=resource.locale,
                rendered_page=resource.template,
                consuming_templates=[resource.template],
                correction=f"set locale to {spec.locale!r}",
            ),
        )]
    if path != expected_resource_path(spec.locale_root, resource.template):
        expected = expected_resource_path(spec.locale_root, resource.template).relative_to(root)
        return [_finding(
            "resource-path", rel,
            _diagnostic_context(
                locale=resource.locale, resource=rel, key="<resource-path>", actual=rel,
                rendered_page=resource.template,
                consuming_templates=[resource.template],
                correction=f"move the resource to {expected}",
            ),
        )]
    template_raw = templates.get(resource.template)
    if template_raw is None:
        return [_finding(
            "resource-template-unreachable", rel,
            _diagnostic_context(
                locale=resource.locale, resource=rel, key="<template>",
                actual=resource.template, rendered_page=resource.template,
                consuming_templates=[],
                correction="delete the resource or restore its discovered shared page template",
            ),
        )]
    findings = key_findings(resource, template_units(template_raw), consumers)
    findings.extend(review_findings(spec, resource, template_raw, profile))
    findings.extend(media_findings(root, spec, resource, template_raw, profile))
    if any(item["code"].startswith("resource-key") or item["code"] == "resource-value"
           for item in findings):
        return findings
    return findings + rendered_findings(spec, resource, template_raw, profile)


def shared_key_findings(root: Path, spec: LocaleSpec, paths: list[Path],
                        consumers: dict[str, list[str]]) -> list[dict[str, str]]:
    """Require every same-locale divergence on one English source to be a recorded decision.

    One English source can reach several pages, and can reach one page more than once. A language
    reviewer may legitimately render those occurrences differently, and this repository's locale
    review protocol forbids an agent or maintainer from normalizing a style PIC's wording. So the
    gate does not demand one wording; it demands that a divergence is written down in the locale's
    review state. An unrecorded divergence fails, and so does a record that no longer describes a
    real divergence, which keeps the reviewer worklist honest in both directions.
    """
    by_key: dict[str, list[tuple[object, str, object]]] = {}
    for path in paths:
        try:
            resource = load_resource(path, source_root=SOURCE_ROOT)
        except LocaleResourceError:
            continue
        if resource.locale != spec.locale:
            continue
        for key, entry in resource.values.items():
            by_key.setdefault(base_key(key), []).append((resource, key, entry))
    recorded = spec.state.get("shared_key_variants", {})
    out: list[dict[str, str]] = []
    if not isinstance(recorded, dict):
        return [_finding(
            "resource-shared-key-record-invalid",
            spec.state_path.relative_to(root).as_posix(),
            f"locale={spec.locale}; key=<shared_key_variants>; actual={type(recorded).__name__!r}; "
            "correction=map each divergent derived key to a recorded reviewed decision",
        )]
    divergent: set[str] = set()
    for key, rows in sorted(by_key.items()):
        # Compare the reader-visible wording only. An ``untranslated`` record names the page it was
        # reviewed on, so comparing reasons would report every shared English term as divergent.
        signatures = {
            (
                entry.get("type"),
                normalize(entry.get("source", "")),
                normalize(entry.get("value", "")),
            )
            for _, _, entry in rows
            if isinstance(entry, dict)
        }
        if len(rows) < 2 or len(signatures) == 1:
            continue
        divergent.add(key)
        locations = [
            {
                "resource": resource.path.relative_to(root).as_posix(),
                "template": resource.template,
                "key": full_key,
                "actual": _excerpt(entry.get("value") if isinstance(entry, dict) else entry),
            }
            for resource, full_key, entry in rows
        ]
        if key not in recorded:
            out.append(_finding(
                "resource-shared-key-unrecorded",
                locations[0]["resource"],
                f"locale={spec.locale}; key={key}; values={locations}; "
                f"rendered_page={[item['template'] for item in locations]}; "
                f"consuming_templates={consumers.get(key) or []}; "
                f"correction=record this reviewed divergence under shared_key_variants[{key!r}] in "
                f"{spec.state_path.relative_to(root).as_posix()}, or have the language reviewer "
                "reconcile the wording in every named resource",
            ))
    for key in sorted(recorded):
        reason = recorded[key]
        rel_state = spec.state_path.relative_to(root).as_posix()
        if not isinstance(reason, str) or not reason.strip():
            out.append(_finding(
                "resource-shared-key-record-invalid", rel_state,
                f"locale={spec.locale}; key={key}; actual={reason!r}; "
                f"rendered_page={consumers.get(key) or []}; "
                f"consuming_templates={consumers.get(key) or []}; "
                "correction=record the reviewed decision as a non-empty reason",
            ))
        elif key not in divergent:
            out.append(_finding(
                "resource-shared-key-record-unused", rel_state,
                f"locale={spec.locale}; key={key}; actual=<no same-locale divergence>; "
                f"rendered_page={[row[0].template for row in by_key.get(key, [])]}; "
                f"consuming_templates={consumers.get(key) or []}; "
                f"correction=delete the stale shared_key_variants[{key!r}] record",
            ))
    return out


def authority_findings(root: Path, spec: LocaleSpec) -> list[dict[str, str]]:
    """Require every reviewed non-overlay page to retain its derived resource file.

    Resource discovery cannot begin from files alone: deleting a whole resource would otherwise
    delete the only object the audit iterates. Review state is the durable consumer declaration
    that lets the gate distinguish an intentionally untranslated canonical page from a migrated
    page whose publication input disappeared.
    """
    overlays = {
        Path(item).as_posix()
        for item in spec.state.get("overlay_files", [])
        if isinstance(item, str)
    }
    reviews = spec.state.get("reviews", {})
    if not isinstance(reviews, dict):
        return [_finding(
            "resource-review-state",
            spec.state_path.relative_to(root).as_posix(),
            _diagnostic_context(
                locale=spec.locale,
                resource="<review state>",
                key="<reviews>",
                actual=type(reviews).__name__,
                rendered_page="<undiscovered>",
                consuming_templates=[],
                correction="restore reviews as an object keyed by each reviewed template",
            ),
        )]
    out: list[dict[str, str]] = []
    for template in sorted(set(reviews) - overlays):
        try:
            safe_template_path(template, SOURCE_ROOT)
        except LocaleResourceError as exc:
            out.append(_finding(
                "resource-review-template",
                spec.state_path.relative_to(root).as_posix(),
                _diagnostic_context(
                    locale=spec.locale,
                    resource="<review state>",
                    key="<reviewed-template>",
                    actual=template,
                    rendered_page="<unsafe>",
                    consuming_templates=[],
                    correction=f"replace the unsafe reviewed template path: {exc}",
                ),
            ))
            continue
        expected = expected_resource_path(spec.locale_root, template)
        if expected.is_file():
            continue
        rel = expected.relative_to(root).as_posix()
        out.append(_finding(
            "resource-missing",
            rel,
            _diagnostic_context(
                locale=spec.locale,
                resource=rel,
                key="<resource-file>",
                actual="<missing>",
                rendered_page=template,
                consuming_templates=[template],
                correction=f"restore the reviewed locale resource at {rel} or restore and "
                "declare its reviewed HTML overlay",
            ),
        ))
    return out


def audit(root: Path = ROOT) -> list[dict[str, str]]:
    """Return every locale-resource defect across discovered locales and templates."""
    try:
        specs = discover_locales(root)
    except LocaleCatalogError as exc:
        return [_finding("locale-catalog", "i18n", str(exc))]
    try:
        templates = discover_templates(root)
    except LocaleResourceError as exc:
        return [_finding(
            "resource-template-discovery", SOURCE_ROOT,
            _diagnostic_context(
                locale=[spec.locale for spec in specs], resource="<template discovery>",
                key="<template-discovery>", actual=str(exc), rendered_page="<undiscovered>",
                consuming_templates=[],
                correction="remove the symlink or unsafe template path and restore a regular HTML file",
            ),
        )]
    if not templates:
        return [_finding("resource-templates", SOURCE_ROOT, "no shared page templates were discovered")]
    try:
        consumers = consumer_map(templates)
    except LocaleResourceError as exc:
        return [_finding(
            "resource-key-collision", SOURCE_ROOT,
            _diagnostic_context(
                locale=[spec.locale for spec in specs], resource="<consumer map>",
                key="<derived-key-collision>", actual=str(exc), rendered_page="<multiple>",
                consuming_templates="<collision prevents a trustworthy map>",
                correction="increase or repair the derived-key identity before adding resources",
            ),
        )]
    findings: list[dict[str, str]] = []
    for spec in specs:
        profile = _locale_quality(root, spec)
        findings.extend(authority_findings(root, spec))
        try:
            unsupported = unsupported_files(spec.locale_root)
            resources = json_resources(spec.locale_root)
        except LocaleResourceError as exc:
            rel_root = spec.locale_root.relative_to(root).as_posix()
            findings.append(_finding(
                "resource-discovery", rel_root,
                _diagnostic_context(
                    locale=spec.locale, resource=rel_root, key="<resource-discovery>",
                    actual=str(exc), rendered_page="<undiscovered>", consuming_templates=[],
                    correction="remove the symlink or unsupported filesystem entry and restore "
                    "regular resource files",
                ),
            ))
            continue
        for path in unsupported:
            rel = path.relative_to(root).as_posix()
            findings.append(_finding(
                "resource-unsupported-file", rel,
                _diagnostic_context(
                    locale=spec.locale, resource=rel, key="<unsupported-file>",
                    actual=path.name, rendered_page="<unreachable>", consuming_templates=[],
                    correction="delete the file; resource directories hold JSON and SKILL.html only",
                ),
            ))
        for path in resources:
            findings.extend(_resource_findings(root, spec, path, templates, consumers, profile))
        findings.extend(shared_key_findings(root, spec, resources, consumers))
    return findings


def _report(findings: list[dict[str, str]], as_json: bool) -> int:
    if as_json:
        print(json.dumps({"ok": not findings, "findings": findings}, indent=2, ensure_ascii=False))
    elif findings:
        print(f"locale resource audit: FAIL ({len(findings)})")
        for item in findings:
            print(f"  [{item['code']}] {item['path']}: {item['detail']}")
    else:
        print("locale resource audit: OK")
    return 1 if findings else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        from locale_resource_mutations import run_mutations

        failures = run_mutations()
        if failures:
            print("locale resource audit self-test: FAIL", file=sys.stderr)
            for item in failures:
                print(f"  - {item}", file=sys.stderr)
            return 1
        print("locale resource audit self-test: OK")
        return 0
    return _report(audit(), args.json)


if __name__ == "__main__":
    raise SystemExit(main())
