#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject HTML structures browsers silently repair into broken learner UI."""
from __future__ import annotations

import argparse
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

for _path in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_path / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_path / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
SKIP_DIRS = {"mats", "standalone", "node_modules", "public", "dist", "build"}


class StructureParser(HTMLParser):
    """Track source nesting without applying the browser's error recovery."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchor_stack: list[tuple[int, int, str]] = []
        self.findings: list[tuple[int, int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        line, column = self.getpos()
        href = dict(attrs).get("href") or "(no href)"
        if self.anchor_stack:
            outer_line, outer_column, outer_href = self.anchor_stack[-1]
            self.findings.append(
                (line, column, f"nested <a href={href!r}> inside anchor at "
                               f"{outer_line}:{outer_column + 1} ({outer_href})")
            )
        self.anchor_stack.append((line, column, href))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.anchor_stack:
            self.anchor_stack.pop()


def inspect_html(raw: str) -> list[tuple[int, int, str]]:
    parser = StructureParser()
    parser.feed(raw)
    parser.close()
    return parser.findings


def source_pages(root: Path) -> list[Path]:
    candidates = list((root / "web").rglob("*.html"))
    candidates.extend((root / "i18n").glob("*/web/**/*.html"))
    return sorted({
        page for page in candidates
        if page.is_file() and not (set(page.relative_to(root).parts) & SKIP_DIRS)
    })


def audit(root: Path = ROOT) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for page in source_pages(root):
        for line, column, detail in inspect_html(page.read_text(encoding="utf-8")):
            findings.append({
                "path": str(page.relative_to(root)),
                "line": line,
                "column": column + 1,
                "detail": detail,
            })
    return findings


def self_test() -> list[str]:
    errors: list[str] = []
    valid = '<article><h3><a href="/launch">Launch</a></h3><p><a href="/local">Local</a></p></article>'
    invalid = '<a class="card" href="/launch"><p>Use <a href="/local">local</a>.</p></a>'
    if inspect_html(valid):
        errors.append("valid sibling anchors were rejected")
    hits = inspect_html(invalid)
    if len(hits) != 1 or "nested <a" not in hits[0][2]:
        errors.append("nested-anchor mutation was not rejected")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        canonical = root / "web" / "nemoclaw"
        locale = root / "i18n" / "pt" / "web" / "nemoclaw"
        canonical.mkdir(parents=True)
        locale.mkdir(parents=True)
        (canonical / "ok.html").write_text(valid, encoding="utf-8")
        (locale / "bad.html").write_text(invalid, encoding="utf-8")
        paths = audit(root)
        if [item["path"] for item in paths] != ["i18n/pt/web/nemoclaw/bad.html"]:
            errors.append("locale overlay mutation was not discovered")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        errors = self_test()
        if errors:
            for error in errors:
                print(f"html structure self-test: FAIL: {error}")
            return 1
        print("html structure self-test: PASS")
        return 0

    findings = audit()
    if findings:
        for item in findings:
            print(f"{item['path']}:{item['line']}:{item['column']}: {item['detail']}")
        return 1
    print(f"html structure audit: PASS ({len(source_pages(ROOT))} source pages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
