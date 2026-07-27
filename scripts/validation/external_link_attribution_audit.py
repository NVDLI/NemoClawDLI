#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Require approved routes on learner-facing NVIDIA Build and Brev links.

Captured reference packets under ``mats/`` are deliberately outside this audit: they
preserve the URLs published by their original sources. Third-party inventories are
governed by ``scripts/compliance/source_gate.py`` instead. This audit covers authored
course pages, localized overlays, shared browser helpers, the standalone bundler, the
public README, and, when requested, generated course artifacts.
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
    "https://brev.nvidia.com/launchable/deploy/now"
    "?launchableID=env-3Azt0aYgVNFEuz7opyx3gscmowS"
    f"&ncid={BREV_NCID}"
)
# Account-specific launchable hostnames are runtime addresses the learner reads from their
# own Brev dashboard, not attributed marketing routes, so they carry no ncid. Anchoring the
# suffix keeps a deceptive lookalike such as ``*.apps.run.brev.nvidia.com.evil`` rejected.
LAUNCHABLE_HOST_RE = re.compile(
    r"^nemoclaw-(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?|<id>)"
    r"\.(?:apps\.run\.brev\.nvidia\.com|brevlab\.com)$",
    re.IGNORECASE,
)
# Include non-HTTPS and deceptive-host near matches so the audit can reject them
# instead of silently treating them as unrelated text.
URL_RE = re.compile(
    r"(?:[A-Za-z][A-Za-z0-9+.-]*:)?//"
    r"[^\s\"'<>`\\)]*(?:(?:build|brev)\.nvidia\.com|brevlab\.com)"
    r"[^\s\"'<>`\\)]*",
    re.IGNORECASE,
)


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
    files.add(root / "README.md")
    return sorted(path for path in files if path.is_file())


def artifact_files(course_root: Path) -> list[Path]:
    files = set(course_root.glob("*.html"))
    files.update((course_root / "scripts").glob("*.js"))
    return sorted(path for path in files if path.is_file())


def url_problem(raw_url: str) -> str | None:
    url = html.unescape(raw_url)
    try:
        parsed = urlsplit(url)
    except ValueError:
        return "learner link is malformed"
    query = parse_qs(parsed.query, keep_blank_values=True)
    if parsed.scheme.casefold() != "https":
        return "learner link must use HTTPS"
    if parsed.username is not None or parsed.password is not None:
        return "learner link must not embed user information"
    if parsed.hostname and LAUNCHABLE_HOST_RE.match(parsed.hostname):
        if query or parsed.fragment:
            return "launchable host reference must not carry query parameters or a fragment"
        if re.match(r"^/v1(?:/|$)", parsed.path, re.IGNORECASE):
            return "NemoClaw launchable must not be presented as a model API"
        return None
    if parsed.hostname == "build.nvidia.com":
        if query.get("ncid") != [BUILD_NCID]:
            return f"Build link must carry exactly ncid={BUILD_NCID}"
        return None
    if parsed.hostname == "brev.nvidia.com":
        if url != BREV_LAUNCH_URL:
            return "Brev link must use the attributed NemoClaw launchable URL"
        return None
    return "link resembles an NVIDIA learner route but does not use the approved host"


def safe_url_for_finding(raw_url: str) -> str:
    """Retain route shape without echoing user information or query values."""
    try:
        parsed = urlsplit(html.unescape(raw_url))
    except ValueError:
        return "[malformed learner route]"
    host = parsed.hostname or "[invalid-host]"
    userinfo = "[redacted]@" if parsed.username is not None or parsed.password is not None else ""
    shown = f"{parsed.scheme}://{userinfo}{host}{parsed.path}"
    if parsed.query:
        shown += "?[query-redacted]"
    if parsed.fragment:
        shown += "#[fragment-redacted]"
    return shown


def scan_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in URL_RE.finditer(text):
        raw_url = match.group(0)
        problem = url_problem(raw_url)
        if problem:
            findings.append(
                Finding(
                    path,
                    text.count("\n", 0, match.start()) + 1,
                    safe_url_for_finding(raw_url),
                    problem,
                )
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
        ("HTTP Build downgrade", BUILD_HOME_URL.replace("https://", "http://"), True),
        ("HTTP Brev downgrade", BREV_LAUNCH_URL.replace("https://", "http://"), True),
        ("scheme-relative Build route", "//build.nvidia.com/", True),
        ("FTP Build route", "ftp://build.nvidia.com/models", True),
        (
            "unattributed Brev route",
            "https://brev.nvidia.com/launchable/deploy/now?launchableID=env-3Azt0aYgVNFEuz7opyx3gscmowS",
            True,
        ),
        (
            "superseded non-/now Brev route",
            BREV_LAUNCH_URL.replace("/launchable/deploy/now", "/launchable/deploy"),
            True,
        ),
        ("generic Brev home", "https://brev.nvidia.com", True),
        ("Pomerium launchable host", "https://nemoclaw-abc123.apps.run.brev.nvidia.com", False),
        ("Pomerium launchable dashboard", "https://nemoclaw-abc123.apps.run.brev.nvidia.com/dashboard", False),
        ("Cloudflare launchable host", "https://nemoclaw-abc123.brevlab.com", False),
        # Course pages document the account-specific host with an HTML-escaped placeholder.
        ("escaped launchable placeholder", "https://nemoclaw-&lt;id&gt;.apps.run.brev.nvidia.com", False),
        ("launchable presented as model API", "https://nemoclaw-abc123.brevlab.com/v1", True),
        ("launchable model catalog path", "https://nemoclaw-abc123.apps.run.brev.nvidia.com/v1/models", True),
        ("HTTP launchable downgrade", "http://nemoclaw-abc123.apps.run.brev.nvidia.com", True),
        ("unsupported generic Brev app", "https://other-abc123.brevlab.com", True),
        ("unsupported bare Brev app", "https://brevlab.com", True),
        ("deceptive launchable host", "https://nemoclaw-abc123.apps.run.brev.nvidia.com.evil/", True),
        ("launchable host with query", "https://nemoclaw-abc123.apps.run.brev.nvidia.com/?token=leak", True),
        ("launchable host with fragment", "https://nemoclaw-abc123.brevlab.com/#token=leak", True),
        ("near-miss Build attribution", f"https://build.nvidia.com/?ncid={BUILD_NCID}0", True),
        ("duplicated Build attribution", f"https://build.nvidia.com/?ncid={BUILD_NCID}&ncid=other", True),
        ("deceptive Build host", f"https://build.nvidia.com.evil/?ncid={BUILD_NCID}", True),
        ("deceptive Brev host", BREV_LAUNCH_URL.replace("brev.nvidia.com", "brev.nvidia.com.evil"), True),
        ("Build route with user information", f"https://learner@build.nvidia.com/?ncid={BUILD_NCID}", True),
        ("malformed learner route", "https://[build.nvidia.com", True),
        ("plain host prose", "build.nvidia.com is the catalog host", False),
        ("unrelated host", "https://docs.nvidia.com/brev/cli/connectivity", False),
    )
    failures: list[str] = []
    for label, sample, should_fail in cases:
        for fixture_path, fixture in (
            ("fixture.html", f'<a href="{sample}">link</a>'),
            ("fixture.md", f"Start here: [link]({sample})"),
        ):
            rejected = bool(scan_text(fixture_path, fixture))
            if rejected != should_fail:
                failures.append(
                    f"{label} ({fixture_path}): expected rejected={should_fail}, got {rejected}",
                )
    credential_fixture = f"https://learner:do-not-echo@build.nvidia.com/?ncid={BUILD_NCID}"
    credential_findings = scan_text("fixture.md", f"[link]({credential_fixture})")
    if not credential_findings or any(
        "do-not-echo" in finding.url for finding in credential_findings
    ):
        failures.append("learner-route finding does not redact embedded user information")
    scanned = {path.as_posix() for path in source_files()}
    if (ROOT / "README.md").as_posix() not in scanned:
        failures.append("public README is not scanned")
    # Detector behavior must not depend on a known filename. This covers renamed and
    # newly introduced learner surfaces while source_files owns the selected release set.
    if not scan_text("docs/learner-start.md", "https://build.nvidia.com/?ncid=near-match"):
        failures.append("novel-path attribution mutation is accepted")
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
