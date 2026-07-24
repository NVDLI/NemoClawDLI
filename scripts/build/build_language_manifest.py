#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Write a build-time language manifest for the Pages foyer."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LABELS = {
    "en": "English",
    "pt": "Portuguese",
    "es": "Spanish",
}
SKIP_DIRS = {"docs", "scripts", "workspace", "validated-source", "web", "nemoclaw"}


def clean_prefix(prefix: str) -> str:
    return prefix.strip("/")


def language_label(code: str) -> str:
    return LABELS.get(code, code.replace("-", " ").title())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--site-root", required=True)
    ap.add_argument("--course-prefix", default="")
    ns = ap.parse_args()

    site = Path(ns.site_root)
    prefix = clean_prefix(ns.course_prefix)
    english_url = f"{prefix + '/' if prefix else ''}nemoclaw/"
    english_course = site / prefix / "nemoclaw" if prefix else site / "nemoclaw"
    english_pages = sorted(path.name for path in english_course.glob("*.html"))
    languages = [{"code": "en", "locale": "en", "label": language_label("en"),
                  "native_label": "English", "url": english_url,
                  "available_pages": english_pages}]

    for child in sorted(site.iterdir() if site.exists() else [], key=lambda p: p.name):
        if not child.is_dir() or child.name in SKIP_DIRS:
            continue
        code = child.name
        if not re.fullmatch(r"[a-z]{2}(?:-[a-z0-9]+)?", code):
            continue
        course = child / "nemoclaw"
        if (course / "index.html").is_file():
            drift_path = course / "assets" / f"localization-{code}.json"
            drift = json.loads(drift_path.read_text(encoding="utf-8")) if drift_path.is_file() else {}
            languages.append({
                "code": code,
                "locale": drift.get("locale", code),
                "label": drift.get("label", language_label(code)),
                "native_label": drift.get("native_label", language_label(code)),
                "url": f"{code}/nemoclaw/",
                "available_pages": drift.get("available_pages", []),
            })

    data = {
        "schema": "nemoclaw-languages/1",
        "default": "en",
        "languages": languages,
        "note": "Language entries appear when the build produced that language course under this Pages root.",
    }
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"[languages] wrote {out} ({len(languages)} languages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
