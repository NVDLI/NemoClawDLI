#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Require course attribution on learner-facing NVIDIA Build and Brev links.

Captured reference packets under ``mats/`` are deliberately outside this audit: they
preserve the URLs published by their original sources. The audit covers authored
course pages, localized overlays, shared browser helpers, the standalone bundler,
and, when requested, generated course artifacts.
"""
from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[2]
BUILD_NCID = "ref-dli-146986"
BREV_NCID = "ref-dli-759990"
BUILD_HOME_URL = f"https://build.nvidia.com/?ncid={BUILD_NCID}"
BREV_LAUNCH_URL = (
    "https://brev.nvidia.com/launchable/deploy"
    "?launchableID=env-3Azt0aYgVNFEuz7opyx3gscmowS"
    f"&ncid={BREV_NCID}"
)
URL_RE = re.compile(r"https://(?:build|brev)\.nvidia\.com[^\s\"'<>`\\)]*")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    url: str
    reason: str


def source_files(root: Path = ROOT) -> list[Path]:
    files: set[Path] = set()
    web = root / "web"
    files.update(web.glob("*.html"))
    files.update(web.glob("*.js"))
    course = web / "nemoclaw"
    files.update(course.glob("*.html"))
    files.update((course / "scripts").glob("*.js"))
    # The repository also carries a browsable standalone snapshot. Production
    # rebuilds it, but repository previews must not retain stale destinations.
    files.update(artifact_files(course / "standalone"))
    for locale_web in (root / "i18n").glob("*/web"):
        files.update(locale_web.glob("*.html"))
        files.update(locale_web.glob("*.js"))
        locale_course = locale_web / "nemoclaw"
        files.update(locale_course.glob("*.html"))
        files.update((locale_course / "scripts").glob("*.js"))
    files.add(root / "scripts" / "build" / "bundle_standalone.py")
    return sorted(path for path in files if path.is_file())


def artifact_files(course_root: Path) -> list[Path]:
    files = set(course_root.glob("*.html"))
    files.update((course_root / "scripts").glob("*.js"))
    return sorted(path for path in files if path.is_file())


def url_problem(raw_url: str) -> str | None:
    url = html.unescape(raw_url)
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.hostname == "build.nvidia.com":
        if query.get("ncid") != [BUILD_NCID]:
            return f"Build link must carry exactly ncid={BUILD_NCID}"
        return None
    if parsed.hostname == "brev.nvidia.com" and url != BREV_LAUNCH_URL:
        return "Brev link must use the attributed NemoClaw launchable URL"
    return None


def scan_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in URL_RE.finditer(text):
        raw_url = match.group(0)
        problem = url_problem(raw_url)
        if problem:
            findings.append(
                Finding(path, text.count("\n", 0, match.start()) + 1, html.unescape(raw_url), problem)
            )
    return findings


def audit(files: list[Path], *, display_root: Path = ROOT) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    scanned = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        try:
            shown = path.relative_to(display_root).as_posix()
        except ValueError:
            shown = path.as_posix()
        findings.extend(scan_text(shown, text))
    return sorted(findings, key=lambda item: (item.path, item.line, item.url)), scanned


def self_test() -> list[str]:
    cases = (
        ("attributed Build home", BUILD_HOME_URL, False),
        ("attributed Build deep link", f"https://build.nvidia.com/blueprints?ncid={BUILD_NCID}", False),
        ("attributed Brev launch", BREV_LAUNCH_URL, False),
        ("HTML-escaped Brev launch", BREV_LAUNCH_URL.replace("&", "&amp;"), False),
        ("unattributed Build home", "https://build.nvidia.com", True),
        ("unattributed Build deep link", "https://build.nvidia.com/blueprints", True),
        ("wrong Build attribution", "https://build.nvidia.com/?ncid=other", True),
        (
            "legacy Brev route",
            "https://brev.nvidia.com/launchable/deploy/now?launchableID=env-3Azt0aYgVNFEuz7opyx3gscmowS",
            True,
        ),
        ("generic Brev home", "https://brev.nvidia.com", True),
        ("unrelated host", "https://docs.nvidia.com/brev/cli/connectivity", False),
    )
    failures: list[str] = []
    for label, sample, should_fail in cases:
        rejected = bool(scan_text("fixture.html", f'<a href="{sample}">link</a>'))
        if rejected != should_fail:
            failures.append(f"{label}: expected rejected={should_fail}, got {rejected}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-root",
        action="append",
        type=Path,
        default=[],
        help="Generated course root to inspect; may be supplied more than once.",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        failures = self_test()
        print("external link attribution self-test: " + ("FAIL" if failures else "PASS"))
        for item in failures:
            print("  FAIL " + item)
        return 1 if failures else 0

    files = source_files()
    for course_root in args.artifact_root:
        files.extend(artifact_files(course_root.resolve()))
    findings, scanned = audit(files)
    if findings:
        print("external link attribution audit: FAIL")
        for item in findings:
            print(f"  {item.path}:{item.line}: {item.reason}: {item.url}")
        return 1
    print(f"external link attribution audit: PASS ({scanned} authored/generated files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
