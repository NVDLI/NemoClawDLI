# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""One source for the localized pages a build publishes, whatever representation holds them.

Runtime and content audits used to read `i18n/<code>/<template>` straight off disk. That path only
exists while a page ships from a reviewed HTML overlay, so an audit written that way silently loses
its locale coverage the moment a page migrates to a key-based resource. Ask this module instead: it
resolves each page the same way `assemble_locale_overlay` does and returns the published bytes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from translate.locale_catalog import LocaleSpec, discover_locales
from translate.locale_projection import project_locale_html
from translate.locale_resource_render import render_overlay, render_page
from translate.locale_resources import (
    bounded_tree_path,
    expected_resource_path,
    LocaleResourceError,
    has_english_shell,
    json_resources,
    load_resource,
)
from translate.localization_scope import translation_sha


def _shell_translations(spec: LocaleSpec) -> dict[str, str]:
    path = spec.profile_path.parent / "shell_translations.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def text_sha(raw: str) -> str:
    """Hash text the same way locale review state and the assembler do."""
    return hashlib.sha256(raw.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def reviewed_source_current(spec: LocaleSpec, template: str, source_raw: str) -> bool:
    """Return whether locale review authority covers the current canonical template."""
    scoped = has_english_shell(source_raw)
    digest = translation_sha(source_raw) if scoped else text_sha(source_raw)
    review = spec.state.get("reviews", {}).get(template, {})
    field = "translation_sha256" if scoped else "source_sha256"
    return review.get(field) == digest


def resolve_overlay_page(
    spec: LocaleSpec,
    template: str,
    source_raw: str,
    overlay_raw: str,
    shell_translations: dict[str, str],
) -> str:
    """Return the bytes an overlay publishes, including safe canonical fallback."""
    if not reviewed_source_current(spec, template, source_raw):
        return source_raw
    review = spec.state.get("reviews", {}).get(template, {})
    if (
        spec.profile.get("reviewed_target_hashes")
        and review.get("target_sha256") != text_sha(overlay_raw)
    ):
        return source_raw
    return (
        project_locale_html(source_raw, overlay_raw, shell_translations)
        if has_english_shell(source_raw) else overlay_raw
    )


def resolve_resource_page(
    spec: LocaleSpec,
    resource,
    source_raw: str,
    shell_translations: dict[str, str],
) -> str:
    """Return the bytes a resource publishes, including safe canonical fallback."""
    if not reviewed_source_current(spec, resource.template, source_raw):
        return source_raw
    if spec.profile.get("reviewed_target_hashes"):
        overlay = render_overlay(source_raw, resource.values, spec.html_lang)
        review = spec.state.get("reviews", {}).get(resource.template, {})
        if review.get("target_sha256") != text_sha(overlay):
            return source_raw
    return render_page(
        source_raw, resource.values, shell_translations, spec.html_lang)


def locale_pages(root: Path, spec: LocaleSpec) -> dict[str, str]:
    """Return one locale's published pages, keyed by repository-relative locale path."""
    shell = _shell_translations(spec)
    pages: dict[str, str] = {}
    for template in spec.state.get("overlay_files", []):
        overlay = bounded_tree_path(spec.locale_root, template)
        source = bounded_tree_path(root, template)
        if not overlay.is_file():
            raise LocaleResourceError(f"{overlay}: declared locale overlay is missing")
        if not source.is_file():
            raise LocaleResourceError(f"{source}: declared locale template is missing")
        source_raw = source.read_text(encoding="utf-8")
        overlay_raw = overlay.read_text(encoding="utf-8")
        pages[(spec.locale_root / template).relative_to(root).as_posix()] = resolve_overlay_page(
            spec, template, source_raw, overlay_raw, shell
        )
    for path in json_resources(spec.locale_root):
        resource = load_resource(path)
        if resource.locale != spec.locale:
            raise LocaleResourceError(
                f"{path}: declares locale {resource.locale!r} inside {spec.locale!r}")
        expected = expected_resource_path(spec.locale_root, resource.template)
        if path != expected:
            raise LocaleResourceError(
                f"{path}: resource for {resource.template} must live at {expected}")
        relative = (spec.locale_root / resource.template).relative_to(root).as_posix()
        if relative in pages:
            # A declared overlay still owns the page, including its canonical fallback state.
            continue
        source = bounded_tree_path(root, resource.template)
        if not source.is_file():
            raise LocaleResourceError(
                f"{path}: locale resource names a missing template: {resource.template}")
        source_raw = source.read_text(encoding="utf-8")
        if (spec.locale_root / resource.template).is_file():
            # File presence keeps a resource shadow-only. If that file is undeclared, the
            # assembler applies neither representation and safely retains canonical English.
            pages[relative] = source_raw
            continue
        pages[relative] = resolve_resource_page(spec, resource, source_raw, shell)
    return pages


def published_pages(root: Path) -> dict[str, str]:
    """Return every discovered locale's published pages, keyed by repository-relative path."""
    pages: dict[str, str] = {}
    for spec in discover_locales(root):
        pages.update(locale_pages(root, spec))
    return pages


def course_pages(root: Path, course: str) -> dict[str, str]:
    """Return the published locale pages of one course directory name, such as ``nemoclaw``."""
    marker = f"/web/{course}/"
    return {rel: raw for rel, raw in published_pages(root).items() if marker in rel}


def materialize(root: Path, out: Path) -> Path:
    """Write every published locale page under ``out`` and return the mirrored locale root.

    A validator that cannot import Python, such as a Node runtime audit, reads the result instead
    of the source tree, so it keeps inspecting real published bytes rather than a representation.
    """
    for relative, raw in published_pages(root).items():
        destination = out / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(raw, encoding="utf-8")
    locale_roots = set()
    for spec in discover_locales(root):
        # Locale discovery itself reads locale.json, so a mirrored tree needs it to stay walkable.
        mirrored = out / spec.locale_root.relative_to(root)
        mirrored.mkdir(parents=True, exist_ok=True)
        (mirrored / "locale.json").write_text(
            json.dumps(spec.metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        locale_roots.add(mirrored.parent)
    if len(locale_roots) != 1:
        raise LocaleResourceError(
            f"expected one mirrored locale root, found {sorted(str(item) for item in locale_roots)}")
    return locale_roots.pop()
