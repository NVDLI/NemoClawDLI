# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.translate.locale_catalog import (
    LocaleCatalogError,
    discover_locales,
    locale_by_tag,
)
from scripts.build.build_language_manifest import build_manifest

ROOT = Path(__file__).resolve().parents[2]


class LocaleCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="locale-catalog-")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_locale(self, url_code: str, locale: str, *, profile_locale: str | None = None) -> Path:
        locale_root = self.root / "i18n" / url_code
        profile = self.root / "scripts" / "translate" / "locales" / locale / "profile.json"
        locale_root.mkdir(parents=True)
        profile.parent.mkdir(parents=True)
        (locale_root / "SKILL.html").write_text("<!doctype html>", encoding="utf-8")
        (profile.parent / "SKILL.html").write_text("<!doctype html>", encoding="utf-8")
        metadata = {
            "schema": "nemoclaw-locale/1",
            "locale": locale,
            "url_code": url_code,
            "label": f"Language {locale}",
            "native_label": f"Native {locale}",
            "profile": f"scripts/translate/locales/{locale}/profile.json",
            "source_root": "web",
            "overlay_root": f"i18n/{url_code}/web",
        }
        profile_data = {
            "schema": "nemoclaw-locale-profile/1",
            "locale": profile_locale or locale,
            "url_code": url_code,
            "label": metadata["label"],
            "native_label": metadata["native_label"],
            "html_lang": locale,
        }
        state = {
            "schema": "nemoclaw-localization-state/1",
            "locale": locale,
            "url_code": url_code,
            "overlay_files": [],
            "asset_files": [],
        }
        (locale_root / "locale.json").write_text(json.dumps(metadata), encoding="utf-8")
        (locale_root / "localization_state.json").write_text(json.dumps(state), encoding="utf-8")
        profile.write_text(json.dumps(profile_data), encoding="utf-8")
        return locale_root

    def test_new_locale_is_discovered_without_registry_edit(self) -> None:
        self.write_locale("fr", "fr-FR")
        specs = discover_locales(self.root)
        self.assertEqual([(item.url_code, item.locale) for item in specs], [("fr", "fr-FR")])
        self.assertEqual(locale_by_tag(self.root, "fr-FR").course_root, self.root / "i18n/fr/web/nemoclaw")

    def test_missing_state_is_rejected(self) -> None:
        root = self.write_locale("fr", "fr-FR")
        (root / "localization_state.json").unlink()
        with self.assertRaisesRegex(LocaleCatalogError, "missing localization state"):
            discover_locales(self.root)

    def test_deleted_locale_is_rejected_while_its_profile_remains(self) -> None:
        root = self.write_locale("fr", "fr-FR")
        for path in sorted(root.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        root.rmdir()
        with self.assertRaisesRegex(LocaleCatalogError, "locale profile is unreachable"):
            discover_locales(self.root)

    def test_missing_profile_is_rejected(self) -> None:
        self.write_locale("fr", "fr-FR")
        profile = self.root / "scripts/translate/locales/fr-FR/profile.json"
        profile.unlink()
        with self.assertRaisesRegex(LocaleCatalogError, "missing locale profile"):
            discover_locales(self.root)

    def test_missing_locale_beacon_is_rejected(self) -> None:
        root = self.write_locale("fr", "fr-FR")
        (root / "SKILL.html").unlink()
        with self.assertRaisesRegex(LocaleCatalogError, "missing its directory beacon"):
            discover_locales(self.root)

    def test_renamed_directory_cannot_disagree_with_url_code(self) -> None:
        root = self.write_locale("fr", "fr-FR")
        renamed = root.with_name("france")
        root.rename(renamed)
        with self.assertRaisesRegex(LocaleCatalogError, "locale directory must be"):
            discover_locales(self.root)

    def test_profile_and_html_language_must_match_metadata(self) -> None:
        self.write_locale("fr", "fr-FR", profile_locale="fr-CA")
        with self.assertRaisesRegex(LocaleCatalogError, "profile.json: locale must match"):
            discover_locales(self.root)

    def test_html_language_must_match_locale(self) -> None:
        self.write_locale("fr", "fr-FR")
        profile_path = self.root / "scripts/translate/locales/fr-FR/profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["html_lang"] = "fr-CA"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(LocaleCatalogError, "html_lang must match locale"):
            discover_locales(self.root)

    def test_duplicate_locale_is_rejected(self) -> None:
        self.write_locale("fr", "fr-FR")
        other = self.write_locale("ca", "ca-ES")
        metadata_path = other / "locale.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["locale"] = "fr-FR"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        state_path = other / "localization_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["locale"] = "fr-FR"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        profile_path = self.root / metadata["profile"]
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["locale"] = "fr-FR"
        profile["html_lang"] = "fr-FR"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaisesRegex(LocaleCatalogError, "duplicate locale"):
            discover_locales(self.root)

    def test_invalid_language_tag_is_rejected(self) -> None:
        root = self.write_locale("fr", "fr-FR")
        metadata_path = root / "locale.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["locale"] = "../../fr"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaisesRegex(LocaleCatalogError, "BCP 47"):
            discover_locales(self.root)

    def test_unreachable_profile_is_rejected(self) -> None:
        self.write_locale("fr", "fr-FR")
        orphan = self.root / "scripts/translate/locales/de-DE/profile.json"
        orphan.parent.mkdir(parents=True)
        orphan.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(LocaleCatalogError, "unreachable"):
            discover_locales(self.root)

    def test_unknown_locale_never_falls_back(self) -> None:
        self.write_locale("fr", "fr-FR")
        with self.assertRaisesRegex(LocaleCatalogError, "unknown locale 'de-DE'"):
            locale_by_tag(self.root, "de-DE")

    def test_built_locale_populates_language_manifest_from_metadata(self) -> None:
        course = self.root / "public/fr/nemoclaw"
        assets = course / "assets"
        assets.mkdir(parents=True)
        (course / "index.html").write_text("<!doctype html>", encoding="utf-8")
        metadata = {
            "locale": "fr-FR",
            "url_code": "fr",
            "label": "French",
            "native_label": "Français",
        }
        (assets / "locale.json").write_text(json.dumps(metadata), encoding="utf-8")
        (assets / "localization-fr.json").write_text(json.dumps({
            **metadata,
            "available_pages": ["index.html"],
        }), encoding="utf-8")
        manifest = build_manifest(self.root / "public")
        self.assertEqual([item["code"] for item in manifest["languages"]], ["en", "fr"])
        self.assertEqual(manifest["languages"][1]["native_label"], "Français")

    def test_language_manifest_cli_writes_the_discovered_manifest(self) -> None:
        site = self.root / "public"
        english = site / "nemoclaw"
        localized = site / "fr" / "nemoclaw"
        assets = localized / "assets"
        english.mkdir(parents=True)
        assets.mkdir(parents=True)
        (english / "index.html").write_text("<!doctype html>", encoding="utf-8")
        (localized / "index.html").write_text("<!doctype html>", encoding="utf-8")
        metadata = {
            "locale": "fr-FR",
            "url_code": "fr",
            "label": "French",
            "native_label": "Français",
        }
        (assets / "locale.json").write_text(json.dumps(metadata), encoding="utf-8")
        (assets / "localization-fr.json").write_text(json.dumps({
            **metadata,
            "available_pages": ["index.html"],
        }), encoding="utf-8")
        output = site / "languages.json"
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/build/build_language_manifest.py"),
                "--out",
                str(output),
                "--site-root",
                str(site),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("(2 languages)", result.stdout)
        manifest = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(["en", "fr"], [item["code"] for item in manifest["languages"]])


if __name__ == "__main__":
    unittest.main()
