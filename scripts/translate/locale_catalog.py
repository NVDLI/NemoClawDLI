# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Discover and validate every same-branch locale from repository metadata."""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from pathlib import Path
from typing import Any

LOCALE_SCHEMA = "nemoclaw-locale/1"
PROFILE_SCHEMA = "nemoclaw-locale-profile/1"
STATE_SCHEMA = "nemoclaw-localization-state/1"
LOCALE_TAG_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
URL_CODE_RE = re.compile(r"^[a-z]{2,3}(?:-[a-z0-9]{2,8})*$")


class LocaleCatalogError(ValueError):
    """One or more locale declarations are unsafe, incomplete, or contradictory."""


@dataclass(frozen=True)
class LocaleSpec:
    """Resolved paths and metadata for one published locale."""

    locale: str
    url_code: str
    html_lang: str
    label: str
    native_label: str
    locale_root: Path
    overlay_root: Path
    course_root: Path
    profile_path: Path
    state_path: Path
    metadata: dict[str, Any]
    profile: dict[str, Any]
    state: dict[str, Any]


def _object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise LocaleCatalogError(f"{path}: missing {label}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocaleCatalogError(f"{path}: invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise LocaleCatalogError(f"{path}: {label} must be a JSON object")
    return value


def _required_text(data: dict[str, Any], field: str, path: Path) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LocaleCatalogError(f"{path}: {field} must be a non-empty string")
    return value.strip()


def _repo_path(root: Path, value: str, field: str, path: Path) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise LocaleCatalogError(f"{path}: {field} must stay inside the repository")
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise LocaleCatalogError(f"{path}: {field} escapes the repository") from exc
    return resolved


def load_locale(root: Path, locale_root: Path) -> LocaleSpec:
    """Load one locale directory and require all cross-file declarations to agree."""
    root = root.resolve()
    locale_root = locale_root.resolve()
    metadata_path = locale_root / "locale.json"
    state_path = locale_root / "localization_state.json"
    metadata = _object(metadata_path, "locale metadata")
    state = _object(state_path, "localization state")

    if metadata.get("schema") != LOCALE_SCHEMA:
        raise LocaleCatalogError(f"{metadata_path}: schema must be {LOCALE_SCHEMA}")
    if state.get("schema") != STATE_SCHEMA:
        raise LocaleCatalogError(f"{state_path}: schema must be {STATE_SCHEMA}")

    locale = _required_text(metadata, "locale", metadata_path)
    url_code = _required_text(metadata, "url_code", metadata_path)
    label = _required_text(metadata, "label", metadata_path)
    native_label = _required_text(metadata, "native_label", metadata_path)
    source_root = _required_text(metadata, "source_root", metadata_path)
    overlay_ref = _required_text(metadata, "overlay_root", metadata_path)
    profile_ref = _required_text(metadata, "profile", metadata_path)

    if not LOCALE_TAG_RE.fullmatch(locale):
        raise LocaleCatalogError(f"{metadata_path}: locale is not a supported BCP 47 language tag: {locale}")
    if not URL_CODE_RE.fullmatch(url_code):
        raise LocaleCatalogError(f"{metadata_path}: url_code is not a safe lowercase path code: {url_code}")
    expected_locale_root = (root / "i18n" / url_code).resolve()
    if locale_root != expected_locale_root:
        raise LocaleCatalogError(
            f"{metadata_path}: locale directory must be {expected_locale_root}"
        )
    if source_root != "web":
        raise LocaleCatalogError(f"{metadata_path}: source_root must be 'web'")

    expected_overlay = f"i18n/{url_code}/web"
    if overlay_ref != expected_overlay:
        raise LocaleCatalogError(f"{metadata_path}: overlay_root must be {expected_overlay!r}")
    overlay_root = _repo_path(root, overlay_ref, "overlay_root", metadata_path)
    profile_path = _repo_path(root, profile_ref, "profile", metadata_path)
    profile = _object(profile_path, "locale profile")
    for beacon in (locale_root / "SKILL.html", profile_path.parent / "SKILL.html"):
        if not beacon.is_file():
            raise LocaleCatalogError(f"{beacon}: declared locale is missing its directory beacon")

    if profile.get("schema") != PROFILE_SCHEMA:
        raise LocaleCatalogError(f"{profile_path}: schema must be {PROFILE_SCHEMA}")
    for field, expected in (
        ("locale", locale),
        ("url_code", url_code),
        ("label", label),
        ("native_label", native_label),
    ):
        if profile.get(field) != expected:
            raise LocaleCatalogError(
                f"{profile_path}: {field} must match {metadata_path}: expected {expected!r}"
            )
    html_lang = _required_text(profile, "html_lang", profile_path)
    if html_lang != locale:
        raise LocaleCatalogError(f"{profile_path}: html_lang must match locale {locale!r}")
    if state.get("locale") != locale or state.get("url_code") != url_code:
        raise LocaleCatalogError(
            f"{state_path}: locale and url_code must match {metadata_path}"
        )

    course_root = overlay_root / "nemoclaw"
    return LocaleSpec(
        locale=locale,
        url_code=url_code,
        html_lang=html_lang,
        label=label,
        native_label=native_label,
        locale_root=locale_root,
        overlay_root=overlay_root,
        course_root=course_root,
        profile_path=profile_path,
        state_path=state_path,
        metadata=metadata,
        profile=profile,
        state=state,
    )


def discover_locales(root: Path) -> list[LocaleSpec]:
    """Return every declared locale or fail once with all catalog defects."""
    root = root.resolve()
    i18n_root = root / "i18n"
    specs: list[LocaleSpec] = []
    errors: list[str] = []
    locale_roots = (
        sorted((path for path in i18n_root.iterdir() if path.is_dir()), key=lambda path: path.name)
        if i18n_root.is_dir()
        else []
    )
    for child in locale_roots:
        try:
            specs.append(load_locale(root, child))
        except LocaleCatalogError as exc:
            errors.append(str(exc))

    locale_owners: dict[str, Path] = {}
    url_owners: dict[str, Path] = {}
    for spec in specs:
        for value, owners, label in (
            (spec.locale, locale_owners, "locale"),
            (spec.url_code, url_owners, "url_code"),
        ):
            previous = owners.get(value)
            if previous is not None:
                errors.append(
                    f"{spec.locale_root / 'locale.json'}: duplicate {label} {value!r}; "
                    f"already declared by {previous}"
                )
            else:
                owners[value] = spec.locale_root / "locale.json"

    profile_roots = root / "scripts" / "translate" / "locales"
    declared_profiles = {spec.profile_path.resolve() for spec in specs}
    if profile_roots.is_dir():
        for profile_path in sorted(profile_roots.glob("*/profile.json")):
            if profile_path.resolve() not in declared_profiles:
                errors.append(
                    f"{profile_path}: locale profile is unreachable from i18n/*/locale.json"
                )

    if errors:
        raise LocaleCatalogError("\n".join(errors))
    return specs


def locale_by_tag(root: Path, locale: str) -> LocaleSpec:
    """Resolve one exact locale tag without a fallback to English or another language."""
    specs = discover_locales(root)
    for spec in specs:
        if spec.locale == locale:
            return spec
    available = ", ".join(spec.locale for spec in specs) or "(none)"
    raise LocaleCatalogError(f"unknown locale {locale!r}; declared locales: {available}")
