#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Add a deterministic semantic navigation header to every SKILL.html page."""
from __future__ import annotations

import argparse
import json
import os
import re
import unittest
from pathlib import Path

import skill_audit


ROOT = Path(__file__).resolve().parents[2]
HEADER_MARKER = 'data-skill-header="1"'
HEADER_RE = re.compile(r'<header\b[^>]*data-skill-header=["\']1["\'][^>]*>.*?</header>', re.I | re.S)
NAV_RE = re.compile(r"<nav(?P<attrs>[^>]*)>(?P<body>.*?)</nav>", re.I | re.S)
CONFIG_RE = re.compile(r'<script[^>]+id="explorer-config"[^>]*>(.*?)</script>', re.I | re.S)
BODY_RE = re.compile(r"(<body[^>]*>)", re.I)


def config(text: str) -> dict:
    match = CONFIG_RE.search(text)
    if not match:
        return {}
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}


def relative_link(skill: Path, target: Path) -> str:
    return Path(os.path.relpath(target, skill.parent)).as_posix()


def navigation(skill: Path, text: str) -> list[tuple[str, str, str]]:
    data = config(text)
    nav = data.get("nav") if isinstance(data.get("nav"), dict) else {}
    root_map = relative_link(skill, ROOT / "SKILL.html")
    if skill.resolve() == (ROOT / "SKILL.html").resolve():
        root_map = "web/SKILL.html"
    home = nav.get("home") or relative_link(skill, ROOT / "web" / "index.html")
    up_data = nav.get("up") if isinstance(nav.get("up"), dict) else {}
    parent_skill = skill.parent.parent / "SKILL.html"
    up = up_data.get("href") or (relative_link(skill, parent_skill) if parent_skill.is_file() else root_map)
    rows = [("home", "Home", home), ("up", "Up", up), ("map", "Repository map", root_map)]
    if len({row[2] for row in rows}) < 2 and skill.resolve() != (ROOT / "scripts" / "SKILL.html").resolve():
        rows.append(("around", "Related tools", relative_link(skill, ROOT / "scripts" / "SKILL.html")))
    return rows


def anchor(role: str, label: str, href: str) -> str:
    return f'<a data-skill-nav="{role}" href="{href}">{label}</a>'


def normalize(skill: Path, text: str) -> str:
    existing = HEADER_RE.search(text)
    if existing:
        hrefs = set(re.findall(r'<a\b[^>]*href=["\']([^"\']+)', existing.group(0), re.I))
        if len(hrefs) >= 2 and "<nav" in existing.group(0).lower():
            return text
        text = text[:existing.start()] + text[existing.end():]
    links = navigation(skill, text)
    map_href = relative_link(skill, ROOT / "SKILL.html")
    if skill.resolve() == (ROOT / "SKILL.html").resolve():
        map_href = "web/SKILL.html"
    nav_match = NAV_RE.search(text)
    if nav_match:
        attrs = nav_match.group("attrs")
        if "aria-label=" not in attrs:
            attrs += ' aria-label="Skill navigation"'
        body = nav_match.group("body").rstrip()
        if not re.search(r'data-skill-nav=["\']map["\']', body):
            body += f' <span aria-hidden="true"> · </span> {anchor("map", "Repository map", map_href)}'
        nav_html = f"<nav{attrs}>{body}</nav>"
        header = f'<header data-skill-header="1">\n{nav_html}\n</header>'
        return text[:nav_match.start()] + header + text[nav_match.end():]
    body_match = BODY_RE.search(text)
    if not body_match:
        return text
    nav_html = ' <span aria-hidden="true"> · </span> '.join(anchor(*row) for row in links)
    header = (
        '\n<header data-skill-header="1" style="padding:.65rem 1rem;border-bottom:1px solid ButtonBorder;background:Canvas;color:CanvasText">\n'
        f'  <nav aria-label="Skill navigation" style="display:flex;gap:.6rem;flex-wrap:wrap">{nav_html}</nav>\n'
        '</header>'
    )
    return text[:body_match.end()] + header + text[body_match.end():]


class HeaderTests(unittest.TestCase):
    def test_wraps_existing_nav_and_is_idempotent(self) -> None:
        source = '<html><body><nav><a href="../index.html">Home</a></nav><main>Body</main></body></html>'
        skill = ROOT / "fixture" / "SKILL.html"
        result = normalize(skill, source)
        self.assertIn(HEADER_MARKER, result)
        self.assertIn("Repository map", result)
        self.assertEqual(normalize(skill, result), result)

    def test_adds_navigation_when_missing(self) -> None:
        result = normalize(ROOT / "fixture" / "SKILL.html", "<html><body><main>Body</main></body></html>")
        self.assertIn('aria-label="Skill navigation"', result)
        self.assertGreaterEqual(result.count("data-skill-nav="), 2)

    def test_repairs_incomplete_existing_header(self) -> None:
        source = '<html><body><header data-skill-header="1"><nav><a href="../SKILL.html">Up</a></nav></header><main>Body</main></body></html>'
        result = normalize(ROOT / "fixture" / "SKILL.html", source)
        self.assertEqual(result.count(HEADER_MARKER), 1)
        self.assertIn("Repository map", result)
        self.assertGreaterEqual(len(set(re.findall(r'href="([^"]+)', result))), 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(HeaderTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if not args.apply and not args.check:
        parser.error("choose --apply, --check, or --self-test")
    stale = []
    for skill in skill_audit.skills():
        source = skill.read_text(encoding="utf-8")
        updated = normalize(skill, source)
        if updated != source:
            stale.append(skill.relative_to(ROOT).as_posix())
            if args.apply:
                skill.write_text(updated, encoding="utf-8")
    if stale and args.check:
        print("skill header contract: FAIL")
        for path in stale:
            print(f"  missing deterministic header: {path}")
        return 1
    print(f"skill header contract: {'updated' if args.apply else 'PASS'} ({len(stale)} file(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
