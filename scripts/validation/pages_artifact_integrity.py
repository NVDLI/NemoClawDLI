#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fail closed on an unexpected or substituted GitHub Pages artifact."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request, urlopen


MANIFEST_NAME = "pages-sha256.txt"
MANIFEST_SCHEMA = "nemoclaw-pages-sha256/1"
REQUIRED_ROOT = (
    "index.html",
    "branches.json",
    "languages.json",
    "gate.json",
)
REQUIRED_COURSE = (
    "nemoclaw/index.html",
    "nemoclaw/scripts/_shared.js",
    "nemoclaw/vendor/browser-dependencies.json",
    "nemoclaw/vendor/browser-sbom.cdx.json",
)


def required_paths(course_prefix: str = "") -> tuple[str, ...]:
    prefix = course_prefix.strip("/")
    if prefix not in {"", "web"}:
        raise ValueError("course prefix must be empty or 'web'")
    return REQUIRED_ROOT + tuple(f"{prefix}/{path}" if prefix else path for path in REQUIRED_COURSE)
SHA = re.compile(r"[0-9a-f]{7,40}")
MIB = 1024 * 1024
MAX_FILE_COUNT = 10_000
MAX_FILE_BYTES = 64 * MIB
MAX_TOTAL_BYTES = 512 * MIB
MAX_DIRECTORY_DEPTH = 20
MAX_ARCHIVE_BYTES = 256 * MIB
MAX_EXPANSION_RATIO = 100
DOWNLOAD_WORKERS = 12


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_relative_path(value: str) -> PurePosixPath | None:
    """Return a normalized relative artifact path, or None when it is unsafe."""
    candidate = PurePosixPath(value)
    if not value or "\\" in value or value.startswith("/") or candidate.is_absolute():
        return None
    if any(part in {"", ".", ".."} for part in candidate.parts):
        return None
    return candidate


def resource_findings(
    rows: list[tuple[str, int]], *, archive_bytes: int | None = None, label: str = "artifact",
) -> list[str]:
    findings: list[str] = []
    files = len(rows)
    total = sum(size for _, size in rows)
    if files > MAX_FILE_COUNT:
        findings.append(f"{label} has {files} files; limit is {MAX_FILE_COUNT}")
    if total > MAX_TOTAL_BYTES:
        findings.append(f"{label} totals {total} bytes; limit is {MAX_TOTAL_BYTES}")
    for rel, size in rows:
        if size > MAX_FILE_BYTES:
            findings.append(f"{label} file exceeds {MAX_FILE_BYTES} bytes: {rel} ({size})")
        path = safe_relative_path(rel)
        if path is None:
            findings.append(f"{label} path is unsafe: {rel}")
        elif len(path.parts) > MAX_DIRECTORY_DEPTH:
            findings.append(f"{label} path depth exceeds {MAX_DIRECTORY_DEPTH}: {rel}")
    if archive_bytes is not None:
        if archive_bytes > MAX_ARCHIVE_BYTES:
            findings.append(f"archive is {archive_bytes} bytes; limit is {MAX_ARCHIVE_BYTES}")
        if archive_bytes <= 0:
            findings.append("archive is empty")
        elif total / archive_bytes > MAX_EXPANSION_RATIO:
            findings.append(
                f"archive expansion ratio is {total / archive_bytes:.1f}; limit is {MAX_EXPANSION_RATIO}"
            )
    return findings


def source_tree_findings(root: Path) -> list[str]:
    """Bound proposed tracked and unignored source before expensive analysis."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip() or "git ls-files failed"
        return [f"cannot enumerate proposed source tree: {detail}"]
    rows: list[tuple[str, int]] = []
    findings: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="surrogateescape")
        path = root / rel
        try:
            size = path.lstat().st_size
        except OSError as exc:
            findings.append(f"cannot inspect source tree path {rel}: {exc}")
            continue
        rows.append((rel, size))
    return findings + resource_findings(rows, label="source tree")


def remote(value: str) -> bool:
    parsed = urlsplit(value.strip())
    return value.strip().startswith("//") or parsed.scheme.lower() in {"http", "https"}


class ExecutableReferenceParser(HTMLParser):
    """Find remote executable references; learner links and media remain allowed."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.findings: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()
        if tag == "script" and remote(values.get("src", "")):
            self.findings.append(f"remote script source {values['src']}")
        if tag == "link" and "stylesheet" in values.get("rel", "").lower().split() and remote(values.get("href", "")):
            self.findings.append(f"remote stylesheet source {values['href']}")
        if tag == "base" and remote(values.get("href", "")):
            self.findings.append(f"remote base URL {values['href']}")


def manifest_text(root: Path, expected_sha: str) -> str:
    rows = [f"# {MANIFEST_SCHEMA} commit={expected_sha}"]
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        if rel == MANIFEST_NAME or not path.is_file() or path.is_symlink():
            continue
        rows.append(f"{digest(path)}  {rel}")
    return "\n".join(rows) + "\n"


def audit(
    root: Path, expected_sha: str, manifest: Path | None = None, *, course_prefix: str = "",
) -> list[str]:
    findings: list[str] = []
    if not SHA.fullmatch(expected_sha):
        return ["expected commit must be a 7-40 character lowercase hexadecimal SHA"]
    if not root.is_dir():
        return [f"artifact root is not a directory: {root}"]

    required = required_paths(course_prefix)
    for rel in required:
        if not (root / rel).is_file():
            findings.append(f"missing required artifact file: {rel}")

    files = 0
    resource_rows: list[tuple[str, int]] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            findings.append(f"artifact contains symlink: {rel}")
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            findings.append(f"artifact contains unsupported file type: {rel}")
            continue
        files += 1
        try:
            resource_rows.append((rel, path.stat().st_size))
        except OSError as exc:
            findings.append(f"cannot stat artifact file {rel}: {exc}")
        if path.suffix.lower() == ".html":
            parser = ExecutableReferenceParser()
            try:
                parser.feed(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError) as exc:
                findings.append(f"cannot parse HTML {rel}: {exc}")
            findings.extend(f"{rel}: {item}" for item in parser.findings)
    if files < len(required):
        findings.append(f"artifact file count is implausibly small: {files}")
    findings.extend(resource_findings(resource_rows))

    gate = root / "gate.json"
    if gate.is_file():
        try:
            data = json.loads(gate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(f"gate.json is unreadable: {exc}")
        else:
            from validation_report_audit import findings as report_findings

            findings.extend(f"gate.json: {item}" for item in report_findings(data, expected_sha))

    if manifest is not None:
        try:
            actual = manifest.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(f"cannot read integrity manifest: {exc}")
        else:
            expected = manifest_text(root, expected_sha)
            if actual != expected:
                findings.append("integrity manifest does not match the extracted Pages tree")
    return findings


def inspect_archive(path: Path) -> tuple[list[str], list[tuple[str, int]]]:
    """Inspect an archive without materializing any member."""
    if not path.is_file():
        return [f"Pages archive does not exist: {path}"], []
    archive_bytes = path.stat().st_size
    findings: list[str] = []
    rows: list[tuple[str, int]] = []
    seen: set[str] = set()
    try:
        with tarfile.open(path, mode="r:*") as archive:
            for member in archive:
                if member.name in {".", "./"} and member.isdir():
                    continue
                relative = safe_relative_path(member.name)
                if relative is None:
                    findings.append(f"archive member path is unsafe: {member.name}")
                    continue
                normalized = relative.as_posix()
                if normalized in seen:
                    findings.append(f"archive member path repeats: {normalized}")
                    continue
                seen.add(normalized)
                if member.isdir():
                    if len(relative.parts) > MAX_DIRECTORY_DEPTH:
                        findings.append(
                            f"archive directory depth exceeds {MAX_DIRECTORY_DEPTH}: {normalized}"
                        )
                    continue
                if not member.isfile():
                    findings.append(f"archive contains unsupported member type: {normalized}")
                    continue
                if member.size < 0:
                    findings.append(f"archive member has a negative size: {normalized}")
                    continue
                rows.append((normalized, member.size))
    except (OSError, tarfile.TarError) as exc:
        return [f"cannot read Pages archive: {exc}"], []
    findings.extend(resource_findings(rows, archive_bytes=archive_bytes))
    if not rows:
        findings.append("Pages archive contains no regular files")
    return findings, rows


def safe_extract_archive(path: Path, destination: Path) -> list[str]:
    """Extract only a previously bounded regular-file tree."""
    findings, _ = inspect_archive(path)
    if findings:
        return findings
    if destination.exists() and any(destination.iterdir()):
        return [f"extraction destination is not empty: {destination}"]
    destination.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(path, mode="r:*") as archive:
            for member in archive:
                if member.name in {".", "./"} and member.isdir():
                    continue
                relative = safe_relative_path(member.name)
                if relative is None:
                    return [f"archive member path became unsafe during extraction: {member.name}"]
                target = destination.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if not member.isfile():
                    return [f"archive member type changed during extraction: {relative.as_posix()}"]
                target.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    return [f"archive member cannot be read: {relative.as_posix()}"]
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=MIB)
                if target.stat().st_size != member.size:
                    return [f"archive member size changed during extraction: {relative.as_posix()}"]
                os.chmod(target, 0o644)
    except (OSError, tarfile.TarError) as exc:
        return [f"Pages archive extraction failed: {exc}"]
    return []


def parse_manifest(text: str, expected_sha: str) -> tuple[list[str], list[tuple[str, str]]]:
    findings: list[str] = []
    lines = text.splitlines()
    expected_header = f"# {MANIFEST_SCHEMA} commit={expected_sha}"
    if not lines or lines[0] != expected_header:
        findings.append("integrity manifest header or commit does not match")
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in lines[1:]:
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            findings.append(f"integrity manifest row is malformed: {line[:120]}")
            continue
        digest_value, rel = match.groups()
        relative = safe_relative_path(rel)
        if relative is None or relative.as_posix() != rel:
            findings.append(f"integrity manifest path is unsafe or non-canonical: {rel}")
            continue
        if rel in seen:
            findings.append(f"integrity manifest path repeats: {rel}")
            continue
        seen.add(rel)
        entries.append((digest_value, rel))
    findings.extend(resource_findings([(rel, 0) for _, rel in entries]))
    if len(entries) < len(required_paths()):
        findings.append(f"integrity manifest file count is implausibly small: {len(entries)}")
    return findings, entries


def deployed_file_findings(
    entries: list[tuple[str, str]], fetch: Callable[[str], bytes], *,
    expected_sizes: dict[str, int] | None = None, workers: int = DOWNLOAD_WORKERS,
) -> dict[str, str]:
    def check(row: tuple[str, str]) -> tuple[str, str | None]:
        expected_digest, rel = row
        try:
            body = fetch(rel)
        except Exception as exc:  # network errors are findings, never a skipped check
            return rel, f"cannot fetch deployed file {rel}: {exc}"
        if len(body) > MAX_FILE_BYTES:
            return rel, f"deployed file exceeds {MAX_FILE_BYTES} bytes: {rel}"
        if expected_sizes is not None and len(body) != expected_sizes.get(rel):
            return rel, f"deployed file size differs from reviewed artifact: {rel}"
        actual = hashlib.sha256(body).hexdigest()
        if actual != expected_digest:
            return rel, f"deployed file digest differs from reviewed artifact: {rel}"
        return rel, None

    findings: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for rel, finding in pool.map(check, entries):
            if finding:
                findings[rel] = finding
    return findings


def compare_deployed_files(
    entries: list[tuple[str, str]], fetch: Callable[[str], bytes], *,
    expected_sizes: dict[str, int] | None = None, workers: int = DOWNLOAD_WORKERS,
) -> list[str]:
    return list(
        deployed_file_findings(
            entries, fetch, expected_sizes=expected_sizes, workers=workers,
        ).values()
    )


def fetch_deployed(base_url: str, rel: str, *, max_bytes: int = MAX_FILE_BYTES) -> bytes:
    encoded = "/".join(quote(part, safe="") for part in PurePosixPath(rel).parts)
    url = urljoin(base_url.rstrip("/") + "/", encoded)
    expected_origin = urlsplit(base_url)
    request = Request(url, headers={"User-Agent": "nemoclaw-pages-integrity/1"})
    with urlopen(request, timeout=30) as response:
        final = urlsplit(response.geturl())
        if (final.scheme, final.netloc) != (expected_origin.scheme, expected_origin.netloc):
            raise RuntimeError(f"cross-origin redirect to {response.geturl()}")
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise RuntimeError(f"response exceeds {max_bytes} bytes")
    return body


def verify_deployment(
    base_url: str, root: Path, manifest: Path, expected_sha: str, *,
    attempts: int = 18, delay: float = 5.0, course_prefix: str = "",
    fetcher: Callable[..., bytes] = fetch_deployed,
    sleeper: Callable[[float], None] = time.sleep,
    workers: int = DOWNLOAD_WORKERS,
    progress: Callable[[str], None] = print,
) -> list[str]:
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return ["deployed Pages base URL must be an absolute HTTPS URL"]
    try:
        expected_text = manifest.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"cannot read reviewed integrity manifest: {exc}"]
    findings, entries = parse_manifest(expected_text, expected_sha)
    if findings:
        return findings
    local_findings = audit(root, expected_sha, manifest, course_prefix=course_prefix)
    if local_findings:
        return [f"reviewed artifact: {item}" for item in local_findings]
    expected_sizes = {rel: (root / rel).stat().st_size for _, rel in entries}
    pending = entries
    last_findings = ["deployed integrity manifest differs from the reviewed artifact"]
    limit = max(1, attempts)
    for attempt in range(1, limit + 1):
        try:
            live_text = fetcher(
                base_url, MANIFEST_NAME, max_bytes=max(MIB, len(expected_text.encode("utf-8"))),
            ).decode("utf-8")
        except (OSError, UnicodeError, RuntimeError) as exc:
            pending = entries
            last_findings = [f"cannot fetch deployed integrity manifest: {exc}"]
        else:
            if live_text != expected_text:
                pending = entries
                last_findings = ["deployed integrity manifest differs from the reviewed artifact"]
            else:
                findings_by_path = deployed_file_findings(
                    pending,
                    lambda rel: fetcher(base_url, rel, max_bytes=expected_sizes[rel]),
                    expected_sizes=expected_sizes,
                    workers=workers,
                )
                if not findings_by_path:
                    return []
                pending = [row for row in pending if row[1] in findings_by_path]
                last_findings = list(findings_by_path.values())
        if attempt < limit:
            progress(
                f"deployed Pages attempt {attempt}/{limit} not ready "
                f"({len(last_findings)} finding(s)); retrying"
            )
            sleeper(max(0.0, delay))
    return last_findings


def self_test() -> list[str]:
    failures: list[str] = []
    fixture_sha = "a" * 40
    valid_report = {
        "schema": "bundle-validation/1",
        "git_sha": fixture_sha,
        "scope": "ship",
        "lang": "en",
        "ok": True,
        "validate_layout_ok": True,
        "gradient": {"required": 0},
        "degraded": [],
        "link_stats": {"blocking_failures": 0, "blocking_asset_leaks": 0, "blocking_cross_course": 0},
        "suites": [{"id": "bundle", "tag": "required", "status": "clean"}],
    }
    with tempfile.TemporaryDirectory(prefix="pages-artifact-integrity-") as tmp:
        root = Path(tmp) / "baseline"
        for rel in required_paths():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("<html></html>\n" if path.suffix == ".html" else "{}\n", encoding="utf-8")
        (root / "gate.json").write_text(json.dumps(valid_report), encoding="utf-8")
        manifest = root / MANIFEST_NAME
        manifest.write_text(manifest_text(root, fixture_sha), encoding="utf-8")
        if audit(root, fixture_sha, manifest):
            failures.append("clean fixture was rejected")

        preview = Path(tmp) / "preview-prefix"
        shutil.copytree(root, preview)
        (preview / "web").mkdir()
        shutil.move(str(preview / "nemoclaw"), str(preview / "web" / "nemoclaw"))
        preview_manifest = preview / MANIFEST_NAME
        preview_manifest.write_text(manifest_text(preview, fixture_sha), encoding="utf-8")
        if audit(preview, fixture_sha, preview_manifest, course_prefix="web"):
            failures.append("clean web-prefixed preview fixture was rejected")
        if not audit(preview, fixture_sha, preview_manifest):
            failures.append("web-prefixed preview escaped the default production-root contract")

        mutations = (
            ("missing file", lambda fixture: (fixture / "nemoclaw/index.html").unlink()),
            ("remote script", lambda fixture: (fixture / "index.html").write_text('<script src="https://evil.invalid/x.js"></script>', encoding="utf-8")),
            ("wrong gate SHA", lambda fixture: (fixture / "gate.json").write_text(json.dumps({**valid_report, "git_sha": "b" * 40}), encoding="utf-8")),
            ("changed after manifest", lambda fixture: (fixture / "languages.json").write_text('{"changed":true}\n', encoding="utf-8")),
            ("symlink", lambda fixture: (fixture / "injected-link").symlink_to(fixture / "index.html")),
        )
        for label, mutate in mutations:
            fixture = Path(tmp) / f"case-{label.replace(' ', '-')}"
            shutil.copytree(root, fixture)
            mutate(fixture)
            if not audit(fixture, fixture_sha, fixture / MANIFEST_NAME):
                failures.append(f"mutation escaped: {label}")

        archive_path = Path(tmp) / "artifact.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(root.rglob("*")):
                archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
        archive_findings, archive_rows = inspect_archive(archive_path)
        if archive_findings or not archive_rows:
            failures.append(f"clean archive was rejected: {archive_findings}")
        extracted = Path(tmp) / "extracted"
        extract_findings = safe_extract_archive(archive_path, extracted)
        if extract_findings or audit(extracted, fixture_sha, extracted / MANIFEST_NAME):
            failures.append(f"clean archive extraction was rejected: {extract_findings}")

        traversal = Path(tmp) / "traversal.tar"
        with tarfile.open(traversal, "w") as archive:
            member = tarfile.TarInfo("../escape.txt")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        if not inspect_archive(traversal)[0]:
            failures.append("archive traversal mutation escaped")

        linked = Path(tmp) / "linked.tar"
        with tarfile.open(linked, "w") as archive:
            member = tarfile.TarInfo("alias")
            member.type = tarfile.SYMTYPE
            member.linkname = "index.html"
            archive.addfile(member)
        if not inspect_archive(linked)[0]:
            failures.append("archive link mutation escaped")

        synthetic_bounds = (
            resource_findings([("deep/" * MAX_DIRECTORY_DEPTH + "file", 0)])
            + resource_findings([("large.bin", MAX_FILE_BYTES + 1)])
            + resource_findings([("expanded.txt", MAX_EXPANSION_RATIO + 1)], archive_bytes=1)
        )
        if len(synthetic_bounds) < 3:
            failures.append("artifact resource-bound mutation escaped")
        source_label = resource_findings(
            [("deep/" * MAX_DIRECTORY_DEPTH + "file", 0)], label="source tree"
        )
        if not source_label or "source tree" not in source_label[0]:
            failures.append("source-tree resource preflight label escaped")

        expected_text = manifest_text(root, fixture_sha)
        parse_findings, entries = parse_manifest(expected_text, fixture_sha)
        if parse_findings:
            failures.append(f"clean manifest parse was rejected: {parse_findings}")
        payloads = {
            rel: (root / rel).read_bytes()
            for _, rel in entries
        }
        if compare_deployed_files(entries, payloads.__getitem__, workers=2):
            failures.append("matching deployed bytes were rejected")
        sizes = {rel: len(body) for rel, body in payloads.items()}
        if compare_deployed_files(entries, payloads.__getitem__, expected_sizes=sizes, workers=2):
            failures.append("matching deployed sizes were rejected")
        payloads[entries[0][1]] += b"changed"
        if not compare_deployed_files(entries, payloads.__getitem__, workers=2):
            failures.append("deployed-byte substitution mutation escaped")
        payloads = {rel: (root / rel).read_bytes() for _, rel in entries}
        stale_rel = entries[0][1]
        calls: dict[str, int] = {}

        def converging_fetch(_base: str, rel: str, *, max_bytes: int) -> bytes:
            del max_bytes
            if rel == MANIFEST_NAME:
                return expected_text.encode("utf-8")
            calls[rel] = calls.get(rel, 0) + 1
            if rel == stale_rel and calls[rel] == 1:
                return payloads[rel] + b"stale"
            return payloads[rel]

        if verify_deployment(
            "https://example.test/", root, manifest, fixture_sha,
            attempts=2, delay=0, fetcher=converging_fetch, sleeper=lambda _delay: None,
            workers=1, progress=lambda _message: None,
        ):
            failures.append("partially propagated deployment did not converge on retry")

        def stale_fetch(_base: str, rel: str, *, max_bytes: int) -> bytes:
            del max_bytes
            if rel == MANIFEST_NAME:
                return expected_text.encode("utf-8")
            if rel == stale_rel:
                return payloads[rel] + b"stale"
            return payloads[rel]

        if not verify_deployment(
            "https://example.test/", root, manifest, fixture_sha,
            attempts=2, delay=0, fetcher=stale_fetch, sleeper=lambda _delay: None,
            workers=1, progress=lambda _message: None,
        ):
            failures.append("persistent deployed-byte substitution escaped retry exhaustion")
        unsafe_manifest = expected_text + f"{'0' * 64}  ../escape\n"
        if not parse_manifest(unsafe_manifest, fixture_sha)[0]:
            failures.append("unsafe manifest path mutation escaped")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--expect-sha")
    parser.add_argument("--write-manifest", type=Path)
    parser.add_argument("--check-manifest", type=Path)
    parser.add_argument("--course-prefix", choices=("", "web"), default="")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--extract-to", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--attempts", type=int, default=18)
    parser.add_argument("--delay", type=float, default=5.0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        print("Pages artifact integrity self-test: " + ("FAIL" if failures else "PASS"))
        for finding in failures:
            print("  " + finding)
        return 1 if failures else 0
    if args.source_root:
        findings = source_tree_findings(args.source_root.resolve())
        if findings:
            print(f"Source tree resource preflight: FAIL ({len(findings)})")
            for finding in findings:
                print("  " + finding)
            return 1
        print("Source tree resource preflight: PASS")
        return 0
    if args.archive:
        if not args.extract_to:
            parser.error("--archive requires --extract-to")
        findings = safe_extract_archive(args.archive.resolve(), args.extract_to.resolve())
        if findings:
            print(f"Pages archive integrity: FAIL ({len(findings)})")
            for finding in findings:
                print("  " + finding)
            return 1
        print(f"Pages archive integrity: PASS ({args.archive})")
        return 0
    if args.base_url:
        if not args.root or not args.check_manifest or not args.expect_sha:
            parser.error("--base-url requires --root, --check-manifest, and --expect-sha")
        findings = verify_deployment(
            args.base_url, args.root.resolve(), args.check_manifest.resolve(), args.expect_sha,
            attempts=args.attempts, delay=args.delay, course_prefix=args.course_prefix,
        )
        if findings:
            print(f"Deployed Pages integrity: FAIL ({len(findings)})")
            for finding in findings:
                print("  " + finding)
            return 1
        print(f"Deployed Pages integrity: PASS ({args.expect_sha})")
        return 0
    if not args.root or not args.expect_sha:
        parser.error("--root and --expect-sha are required")
    root = args.root.resolve()
    findings = audit(root, args.expect_sha, args.check_manifest, course_prefix=args.course_prefix)
    if findings:
        print(f"Pages artifact integrity: FAIL ({len(findings)})")
        for finding in findings:
            print("  " + finding)
        return 1
    if args.write_manifest:
        target = args.write_manifest.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(manifest_text(root, args.expect_sha), encoding="utf-8")
    print(f"Pages artifact integrity: PASS ({sum(1 for path in root.rglob('*') if path.is_file())} files @ {args.expect_sha})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
