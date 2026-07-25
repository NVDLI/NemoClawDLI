#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Write a build-time language manifest for the Pages foyer."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SKIP_DIRS = {"docs", "scripts", "workspace", "validated-source", "web", "nemoclaw"}


def clean_prefix(prefix: str) -> str:
    return prefix.strip("/")


def build_manifest(site: Path, prefix: str = "") -> dict:
    """Describe English and every metadata-bearing locale emitted under a site root."""
    prefix = clean_prefix(prefix)
    english_url = f"{prefix + '/' if prefix else ''}nemoclaw/"
    english_course = site / prefix / "nemoclaw" if prefix else site / "nemoclaw"
    english_pages = sorted(path.name for path in english_course.glob("*.html"))
    languages = [{"code": "en", "locale": "en", "label": "English",
                  "native_label": "English", "url": english_url,
                  "available_pages": english_pages}]

    for child in sorted(site.iterdir() if site.exists() else [], key=lambda p: p.name):
        if not child.is_dir() or child.name in SKIP_DIRS:
            continue
        code = child.name
        course = child / "nemoclaw"
        locale_path = course / "assets" / "locale.json"
        if (course / "index.html").is_file() and locale_path.is_file():
            if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", code):
                raise ValueError(f"{locale_path}: unsafe locale URL code {code!r}")
            drift_path = course / "assets" / f"localization-{code}.json"
            if not drift_path.is_file():
                raise ValueError(f"{drift_path}: built locale is missing its reviewed drift manifest")
            locale = json.loads(locale_path.read_text(encoding="utf-8"))
            drift = json.loads(drift_path.read_text(encoding="utf-8"))
            if locale.get("url_code") != code or drift.get("url_code") != code:
                raise ValueError(f"{course}: built locale metadata does not match URL code {code!r}")
            for field in ("locale", "label", "native_label"):
                if not isinstance(locale.get(field), str) or not locale[field].strip():
                    raise ValueError(f"{locale_path}: {field} must be a non-empty string")
                if drift.get(field) != locale[field]:
                    raise ValueError(f"{drift_path}: {field} must match {locale_path}")
            languages.append({
                "code": code,
                "locale": locale["locale"],
                "label": locale["label"],
                "native_label": locale["native_label"],
                "url": f"{code}/nemoclaw/",
                "available_pages": drift.get("available_pages", []),
            })

    return {
        "schema": "nemoclaw-languages/1",
        "default": "en",
        "languages": languages,
        "note": "Language entries appear when the build produced that language course under this Pages root.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--site-root", required=True)
    ap.add_argument("--course-prefix", default="")
    ns = ap.parse_args()

    data = build_manifest(Path(ns.site_root), ns.course_prefix)
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"[languages] wrote {out} ({len(data['languages'])} languages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
