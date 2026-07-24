#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject broken or deployment-root-dependent links in a static artifact.

The root passed on the command line is the exact unit that may be uploaded to a
static host.  Every HTML file below it is discovered automatically.  Every local
URL in an HTML navigation or resource attribute must remain below that root and
resolve to a file.  HTML fragments must identify an element in the target page.

There are no path allowlists, page opt-ins, or missing-target exemptions.
"""
from __future__ import annotations

import argparse
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


URL_ATTRIBUTES = frozenset({"action", "data-svg-src", "href", "poster", "src"})
REMOTE_SCHEMES = frozenset({"data", "http", "https", "mailto", "tel"})


@dataclass(frozen=True)
class Finding:
    page: str
    url: str
    reason: str

    def __str__(self) -> str:
        return f"{self.page} -> {self.url!r}: {self.reason}"


class Document(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []
        self.fragments: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        for name in URL_ATTRIBUTES:
            if name in values:
                self.urls.append(values[name] or "")
        for raw in (values.get("srcset") or "").split(","):
            candidate = raw.strip().split()[0] if raw.strip() else ""
            if candidate:
                self.urls.append(candidate)
        for name in ("id", "name"):
            if values.get(name):
                self.fragments.add(values[name] or "")


def _documents(root: Path) -> dict[Path, Document]:
    documents: dict[Path, Document] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.suffix.lower() in {".html", ".htm"}):
        document = Document()
        document.feed(path.read_text(encoding="utf-8", errors="replace"))
        documents[path.resolve()] = document
    return documents


def _target(root: Path, page: Path, raw: str) -> tuple[Path | None, str, str | None]:
    if not raw.strip():
        return None, "", "empty URL"
    parsed = urlsplit(raw.strip())
    if parsed.scheme.lower() in REMOTE_SCHEMES or parsed.netloc:
        return None, parsed.fragment, None
    if parsed.scheme:
        return None, parsed.fragment, f"unsupported URL scheme {parsed.scheme!r}"
    if parsed.path.startswith("/"):
        return None, parsed.fragment, "root-absolute URL depends on the host mount point"

    decoded = unquote(parsed.path)
    target = (page.parent / decoded).resolve() if decoded else page
    try:
        target.relative_to(root)
    except ValueError:
        return None, parsed.fragment, "URL escapes the deployment root"
    if target.is_dir():
        target = target / "index.html"
    return target, parsed.fragment, None


def audit(root: Path) -> list[Finding]:
    root = root.resolve()
    if not root.is_dir():
        return [Finding(".", str(root), "deployment root is not a directory")]
    documents = _documents(root)
    if not documents:
        return [Finding(".", str(root), "deployment root contains no HTML files")]

    findings: list[Finding] = []
    for page, document in documents.items():
        page_name = page.relative_to(root).as_posix()
        for raw in document.urls:
            target, fragment, error = _target(root, page, raw)
            if error:
                findings.append(Finding(page_name, raw, error))
                continue
            if target is None:
                continue
            if not target.is_file():
                findings.append(Finding(page_name, raw, "target does not exist in the deployment artifact"))
                continue
            if fragment and target.suffix.lower() in {".html", ".htm"}:
                target_document = documents.get(target.resolve())
                if target_document is None:
                    target_document = Document()
                    target_document.feed(target.read_text(encoding="utf-8", errors="replace"))
                if fragment not in target_document.fragments:
                    findings.append(Finding(page_name, raw, f"fragment #{fragment} does not exist"))
    return findings


def self_test() -> list[str]:
    failures: list[str] = []
    cases = {
        "valid nested navigation": (
            {
                "index.html": '<main id="top"><a href="nested/page.html#answer">open</a></main>',
                "nested/page.html": '<p id="answer"><a href="../index.html#top">home</a></p>',
            },
            None,
        ),
        "missing target": ({"index.html": '<a href="missing.html">missing</a>'}, "does not exist"),
        "root escape": ({"index.html": '<a href="../SKILL.html">map</a>'}, "escapes the deployment root"),
        "mount-dependent path": ({"index.html": '<script src="/shared.js"></script>'}, "host mount point"),
        "missing fragment": (
            {"index.html": '<a href="page.html#missing">open</a>', "page.html": '<p id="present">text</p>'},
            "fragment #missing does not exist",
        ),
        "resource attribute": ({"index.html": '<img src="missing.png" alt="fixture">'}, "does not exist"),
    }
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        for index, (label, (files, expected)) in enumerate(cases.items()):
            root = base / str(index)
            for relative, text in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            messages = [str(item) for item in audit(root)]
            if expected is None and messages:
                failures.append(f"{label}: valid fixture was rejected: {messages}")
            elif expected is not None and not any(expected in message for message in messages):
                failures.append(f"{label}: mutation was not rejected with {expected!r}: {messages}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
    elif args.root:
        failures = [str(item) for item in audit(args.root)]
    else:
        parser.error("provide a deployment root or --self-test")
    if failures:
        print("artifact link audit: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("artifact link audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
