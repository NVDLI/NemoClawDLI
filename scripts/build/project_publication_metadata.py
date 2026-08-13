#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Project publication metadata onto built course pages without changing lesson prose."""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit


SCHEMA = "dli-publication-integrity/1"
PUBLIC_MODE = "public"
PREVIEW_MODE = "preview"
MODES = {PUBLIC_MODE, PREVIEW_MODE}
MARKER_OPEN = "<!-- publication-metadata:start -->"
MARKER_CLOSE = "<!-- publication-metadata:end -->"
MARKER_RE = re.compile(
    re.escape(MARKER_OPEN) + r".*?" + re.escape(MARKER_CLOSE), re.S
)
TITLE_RE = re.compile(r"<title\b[^>]*>.*?</title>", re.I | re.S)
HEAD_CLOSE_RE = re.compile(r"</head\s*>", re.I)
ROOT_HTML = re.compile(r"^[^/]+\.html$")
WS = re.compile(r"\s+")


class PageText(HTMLParser):
    """Extract title, first useful paragraph, H1, and course objectives."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._capture: list[str] = []
        self._kind = ""
        self.title = ""
        self.h1 = ""
        self.paragraphs: list[str] = []
        self.objectives: list[str] = []
        self._in_objectives = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() in {"script", "style", "template", "noscript"}:
            self._skip += 1
            return
        if self._skip:
            return
        tag = tag.lower()
        if values.get("id") == "learning-objectives":
            self._in_objectives += 1
        if tag in {"title", "h1", "p"} or (tag == "li" and self._in_objectives):
            self._kind = tag
            self._capture = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template", "noscript"}:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        tag = tag.lower()
        if tag == self._kind:
            value = WS.sub(" ", "".join(self._capture)).strip()
            if value:
                if tag == "title" and not self.title:
                    self.title = value
                elif tag == "h1" and not self.h1:
                    self.h1 = value
                elif tag == "p":
                    self.paragraphs.append(value)
                elif tag == "li" and self._in_objectives:
                    self.objectives.append(value)
            self._kind = ""
            self._capture = []
        if self._in_objectives and tag in {"div", "section"}:
            self._in_objectives = max(0, self._in_objectives - 1)

    def handle_data(self, data: str) -> None:
        if not self._skip and self._kind:
            self._capture.append(data)


def load_contract(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: expected {SCHEMA}")
    return data


def clean_base(raw: str) -> str:
    value = raw.rstrip("/") + "/"
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(f"canonical_base must be an absolute clean HTTPS directory: {raw}")
    return value


def parse_page(raw: str) -> PageText:
    parser = PageText()
    parser.feed(raw)
    return parser


def localized_description(page: PageText, fallback: str) -> str:
    for paragraph in page.paragraphs:
        if len(paragraph) >= 60:
            return paragraph
    return fallback


def localized_title(page: PageText, fallback: str) -> str:
    return page.title or page.h1 or fallback


def language_roots(site: Path, course_root: Path, contract: dict) -> list[tuple[str, str, Path, str]]:
    source_code = str(contract["source_language"])
    slug = str(contract["course_slug"])
    roots = [(source_code, str(contract["languages"][source_code]), course_root, "")]
    for code, locale in sorted(contract.get("languages", {}).items()):
        if code == source_code:
            continue
        root = site / code / slug
        if root.is_dir():
            roots.append((code, str(locale), root, f"{code}/"))
    return roots


def course_url(base: str, language_prefix: str, filename: str, slug: str = "") -> str:
    suffix = "" if filename == "index.html" else filename
    if language_prefix:
        return urljoin(base, f"../{language_prefix}{slug}/{suffix}")
    return urljoin(base, suffix)


def page_json_ld(
    record: dict,
    page: PageText,
    url: str,
    title: str,
    description: str,
    language: str,
    contract: dict,
) -> list[dict]:
    publisher = {
        "@type": "Organization",
        "name": contract["publisher"]["name"],
        "url": contract["publisher"]["url"],
    }
    entities = [
        {"@type": "SoftwareApplication", "name": name, "url": contract["entities"][name]["url"]}
        for name in record.get("entities", [])
    ]
    if record["kind"] == "Course":
        node: dict = {
            "@context": "https://schema.org",
            "@type": "Course",
            "name": page.h1 or contract["course_name"],
            "description": description,
            "url": url,
            "inLanguage": language,
            "provider": publisher,
            "publisher": publisher,
            "isAccessibleForFree": True,
            "sameAs": contract["repository_url"],
        }
        if page.objectives:
            node["teaches"] = page.objectives
        if entities:
            node["mentions"] = entities
        return [node]
    node = {
        "@context": "https://schema.org",
        "@type": "LearningResource",
        "name": page.h1 or title,
        "description": description,
        "url": url,
        "inLanguage": language,
        "publisher": publisher,
        "isPartOf": {
            "@type": "Course",
            "name": contract["course_name"],
            "url": course_url(clean_base(contract["canonical_base"]), "", "index.html"),
        },
    }
    if entities:
        node["mentions"] = entities
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": contract["course_name"],
                "item": course_url(clean_base(contract["canonical_base"]), "", "index.html"),
            },
            {"@type": "ListItem", "position": 2, "name": page.h1 or title, "item": url},
        ],
    }
    return [node, breadcrumb]


def metadata_block(
    *,
    record: dict,
    page: PageText,
    url: str,
    title: str,
    description: str,
    language: str,
    alternatives: list[tuple[str, str]],
    mode: str,
    contract: dict,
) -> str:
    esc = lambda value: html.escape(str(value), quote=True)
    robots = "index,follow,max-image-preview:large,max-snippet:-1" if mode == PUBLIC_MODE and record["index"] else "noindex,follow"
    lines = [
        MARKER_OPEN,
        f'<meta name="description" content="{esc(description)}"/>',
        f'<meta name="robots" content="{robots}"/>',
        f'<link rel="canonical" href="{esc(url)}"/>',
    ]
    if record["index"]:
        lines.extend(
            f'<link rel="alternate" hreflang="{esc(code)}" href="{esc(href)}"/>'
            for code, href in alternatives
        )
        lines.append(f'<link rel="alternate" hreflang="x-default" href="{esc(alternatives[0][1])}"/>')
    lines.extend(
        [
            f'<meta property="og:type" content="{ "website" if record["kind"] == "Course" else "article" }"/>',
            f'<meta property="og:site_name" content="{esc(contract["course_name"])}"/>',
            f'<meta property="og:title" content="{esc(title)}"/>',
            f'<meta property="og:description" content="{esc(description)}"/>',
            f'<meta property="og:url" content="{esc(url)}"/>',
            '<meta name="twitter:card" content="summary"/>',
            f'<meta name="twitter:title" content="{esc(title)}"/>',
            f'<meta name="twitter:description" content="{esc(description)}"/>',
        ]
    )
    payload = page_json_ld(record, page, url, title, description, language, contract)
    for node in payload:
        serialized = json.dumps(node, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
        lines.append('<script type="application/ld+json">' + serialized + "</script>")
    lines.append(MARKER_CLOSE)
    return "\n".join(lines)


def project(site: Path, course_root: Path, contract: dict, mode: str, contract_path: Path | None = None) -> dict:
    if mode not in MODES:
        raise ValueError(f"unsupported publication mode: {mode}")
    base = clean_base(str(contract["canonical_base"]))
    slug = str(contract["course_slug"])
    source_code = str(contract["source_language"])
    records = contract.get("pages")
    if not isinstance(records, dict):
        raise ValueError("publication contract pages must be an object")
    source_names = {path.name for path in course_root.glob("*.html")}
    if source_names != set(records):
        missing = sorted(source_names - set(records))
        stale = sorted(set(records) - source_names)
        raise ValueError(f"publication page classification drift; missing={missing}, stale={stale}")

    roots = language_roots(site, course_root, contract)
    projected = 0
    indexed_urls: list[str] = []
    for code, locale, root, prefix in roots:
        if contract_path is not None:
            shutil.copy2(contract_path, root / "publication-integrity.json")
        for filename, record in sorted(records.items()):
            path = root / filename
            if not path.is_file():
                continue
            raw = path.read_text(encoding="utf-8")
            raw = MARKER_RE.sub("", raw)
            page = parse_page(raw)
            title = record["seo_title"] if code == "en" else localized_title(page, record["seo_title"])
            description = record["description"] if code == "en" else localized_description(page, record["description"])
            url = course_url(base, prefix, filename, slug)
            alternatives = [
                (alt_locale, course_url(base, alt_prefix, filename, slug))
                for _, alt_locale, alt_root, alt_prefix in roots
                if (alt_root / filename).is_file()
            ]
            block = metadata_block(
                record=record,
                page=page,
                url=url,
                title=title,
                description=description,
                language=locale,
                alternatives=alternatives,
                mode=mode,
                contract=contract,
            )
            if code == source_code:
                raw, count = TITLE_RE.subn(f"<title>{html.escape(title)}</title>", raw, count=1)
                if count != 1:
                    raise ValueError(f"{path}: expected exactly one title")
            match = HEAD_CLOSE_RE.search(raw)
            if not match:
                raise ValueError(f"{path}: missing </head>")
            raw = raw[:match.start()] + block + "\n" + raw[match.start():]
            path.write_text(raw, encoding="utf-8")
            projected += 1
            if mode == PUBLIC_MODE and record["index"]:
                indexed_urls.append(url)

    known_roots = {root.resolve() for _, _, root, _ in roots}
    for filename, record in sorted(records.items()):
        for path in sorted(site.rglob(f"{slug}/{filename}")):
            if path.parent.resolve() in known_roots:
                continue
            raw = MARKER_RE.sub("", path.read_text(encoding="utf-8"))
            page = parse_page(raw)
            title = localized_title(page, record["seo_title"])
            description = localized_description(page, record["description"])
            url = course_url(base, "", filename)
            block = metadata_block(
                record=record,
                page=page,
                url=url,
                title=title,
                description=description,
                language="en",
                alternatives=[("en", url)],
                mode=PREVIEW_MODE,
                contract=contract,
            )
            match = HEAD_CLOSE_RE.search(raw)
            if not match:
                raise ValueError(f"{path}: missing </head>")
            path.write_text(raw[:match.start()] + block + "\n" + raw[match.start():], encoding="utf-8")
            projected += 1

    sitemap = site / "sitemap.xml"
    robots = site / "robots.txt"
    if mode == PUBLIC_MODE:
        body = "\n".join(f"  <url><loc>{html.escape(url)}</loc></url>" for url in sorted(indexed_urls))
        sitemap.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}\n</urlset>\n",
            encoding="utf-8",
        )
        robots.write_text(f"User-agent: *\nAllow: /\nSitemap: {urljoin(base, '../sitemap.xml')}\n", encoding="utf-8")
    else:
        sitemap.unlink(missing_ok=True)
        robots.write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    return {"pages": projected, "indexed_urls": len(indexed_urls), "mode": mode}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", required=True, type=Path)
    parser.add_argument("--course-root", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--mode", choices=sorted(MODES), default=PREVIEW_MODE)
    args = parser.parse_args()
    result = project(
        args.site_root,
        args.course_root,
        load_contract(args.contract),
        args.mode,
        args.contract,
    )
    print(
        f"[publication] {result['mode']}: {result['pages']} page projections, "
        f"{result['indexed_urls']} sitemap URLs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
