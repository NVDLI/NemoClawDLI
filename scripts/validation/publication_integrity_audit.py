#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate search discovery and AI-content transparency across the published course."""
from __future__ import annotations

import argparse
import json
import re
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

for _path in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_path / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_path / "scripts"))
        break
from _bootstrap import find_repo_root

try:
    from scripts.validation.figure_provenance import figure_rows
except ModuleNotFoundError:
    from figure_provenance import figure_rows


ROOT = find_repo_root(Path(__file__).resolve())
CONTRACTS = tuple(sorted((ROOT / "web").glob("*/publication-integrity.json")))
CONTRACT = CONTRACTS[0] if len(CONTRACTS) == 1 else ROOT / "web" / "publication-integrity.json"
COURSE = CONTRACT.parent
SCHEMA = "dli-publication-integrity/1"
VALID_ORIGINS = {
    "course-authored",
    "deterministic-code-generated",
    "deterministic-source-figure-conversion",
    "publisher-provided",
    "remote-publisher-provided",
    "source-figure-redraw",
    "source-inspired-course-authored",
}
VALID_CLASSES = {
    "brand-asset",
    "deepfake",
    "publisher-reference",
    "source-figure-conversion",
    "stylized-illustration",
    "technical-diagram",
}
VALID_KINDS = {"Course", "LearningResource", "Lesson", "Support"}
ENTITY_ALIAS = re.compile(r"[\W_]+", re.UNICODE)
STATIC_MEDIA = re.compile(r"(?:<img\b[^>]*\bsrc|\bdata-svg-src)=[\"']([^\"']+)[\"']", re.I)
RUNTIME_MEDIA_SIGNALS = re.compile(r"\.(?:toDataURL|srcdoc\s*=)|createElement\([\"']canvas[\"']\)")
MEDIA_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
JS_IMAGE_VALUES = re.compile(
    r"[\"']([^\"']+?(?:\.gif|\.jpeg|\.jpg|\.png|\.svg|\.webp)(?:\?[^\"']*)?)[\"']",
    re.I,
)
MARKDOWN_MEDIA = re.compile(r"!?\[[^\]]*\]\(([^)\s]+(?:\s+[\"'][^\"']*[\"'])?)\)")


class ProvenanceParser(HTMLParser):
    """Read JSON inventories from SKILL pages without interpreting their UI previews."""

    def __init__(self, script_id: str) -> None:
        super().__init__(convert_charrefs=True)
        self.script_id = script_id
        self.active = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "script" and values.get("id") == self.script_id:
            self.active = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.active:
            self.active = False

    def handle_data(self, data: str) -> None:
        if self.active:
            self.parts.append(data)


class VisibleTextParser(HTMLParser):
    """Extract rendered text while excluding non-visible document containers."""

    EXCLUDED = {"noscript", "script", "style", "template"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in self.EXCLUDED:
            self.hidden.append(normalized_tag)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in self.EXCLUDED and normalized_tag in self.hidden:
            reverse_index = self.hidden[::-1].index(normalized_tag)
            del self.hidden[len(self.hidden) - reverse_index - 1 :]

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def json_script(path: Path, script_id: str) -> dict:
    if not path.is_file():
        return {}
    parser = ProvenanceParser(script_id)
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return json.loads("".join(parser.parts)) if parser.parts else {}


def material_media_rows(course: Path = COURSE) -> tuple[dict[str, object], ...]:
    payload = json_script(course / "mats" / "SKILL.html", "provenance")
    defaults = payload.get("media_transparency", {})
    if not isinstance(defaults, dict):
        defaults = {}
    return tuple(
        {**defaults, **row}
        for row in payload.get("mats", [])
        if isinstance(row, dict) and Path(str(row.get("file", ""))).suffix.lower() in MEDIA_SUFFIXES
    )


def discovered_material_media(course: Path = COURSE) -> set[str]:
    """Discover cached media from the tree and Markdown, including future nested files."""
    root = course / "mats"
    tree = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES
    }
    referenced: set[str] = set()
    for source in root.rglob("*.md"):
        for match in MARKDOWN_MEDIA.findall(source.read_text(encoding="utf-8", errors="replace")):
            target = match.split(maxsplit=1)[0].strip("<>\"'")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or target.startswith(("#", "data:")):
                continue
            try:
                candidate = (source.parent / parsed.path).resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                candidate = ""
            if candidate and Path(candidate).suffix.lower() in MEDIA_SUFFIXES:
                referenced.add(candidate)
    return tree | referenced


def discovered_script_media(course: Path = COURSE) -> set[str]:
    values: set[str] = set()
    for path in sorted((course / "scripts").rglob("*.js")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        if "createElement(\"img\")" not in raw and "createElement('img')" not in raw:
            continue
        values.update(JS_IMAGE_VALUES.findall(raw))
    return values


def finding(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def load_contract(path: Path = CONTRACT) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def visible_text(raw: str) -> str:
    parser = VisibleTextParser()
    parser.feed(raw)
    parser.close()
    return re.sub(r"\s+", " ", unescape(" ".join(parser.parts))).strip()


def normalized(raw: str) -> str:
    return ENTITY_ALIAS.sub(" ", raw).strip().casefold()


def _public_html(course: Path) -> set[str]:
    return {path.name for path in course.glob("*.html")}


def audit_contract(
    data: dict,
    *,
    course: Path = COURSE,
    provenance: tuple[dict[str, object], ...] | None = None,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    rel = course.relative_to(ROOT).as_posix() if course.is_relative_to(ROOT) else str(course)
    contract_path = f"{rel}/publication-integrity.json"
    if data.get("schema") != SCHEMA:
        out.append(finding("schema", contract_path, f"expected {SCHEMA}"))
    slug = data.get("course_slug")
    if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        out.append(finding("course-slug", contract_path, "course_slug must be a lowercase URL segment"))
    elif slug != course.name:
        out.append(finding("course-slug", contract_path, "course_slug must match the classified source directory"))
    base = str(data.get("canonical_base", ""))
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment or not base.endswith("/"):
        out.append(finding("canonical-base", contract_path, "canonical_base must be a clean absolute HTTPS directory"))
    languages = data.get("languages")
    source_language = data.get("source_language")
    if (
        not isinstance(languages, dict)
        or not languages
        or source_language not in languages
        or any(
            not isinstance(code, str)
            or not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", str(locale))
            for code, locale in languages.items()
        )
    ):
        out.append(finding("languages", contract_path, "language routes and source_language must be explicit valid language tags"))

    pages = data.get("pages")
    if not isinstance(pages, dict):
        return out + [finding("pages", contract_path, "pages must be an object")]
    actual = _public_html(course)
    declared = set(pages)
    for name in sorted(actual - declared):
        out.append(finding("page-unclassified", f"{rel}/{name}", "new course page has no search or transparency disposition"))
    for name in sorted(declared - actual):
        out.append(finding("page-stale", contract_path, f"page disposition names a missing course page: {name}"))
    indexed = {name for name, row in pages.items() if isinstance(row, dict) and row.get("index") is True}
    lesson_pages = {path.name for path in course.glob("[0-9][0-9][a-z]-*.html")}
    required_indexed = {"index.html", "glossary.html", *lesson_pages}
    if indexed != required_indexed:
        out.append(finding("index-scope", contract_path, f"indexable page set drifted; expected {sorted(required_indexed)}, got {sorted(indexed)}"))

    entities = data.get("entities")
    if not isinstance(entities, dict):
        entities = {}
        out.append(finding("entities", contract_path, "entities must be an object"))
    required_entities = set(data.get("required_entity_names", []))
    if not required_entities or set(entities) != required_entities:
        out.append(finding("entity-set", contract_path, f"entity vocabulary must match required_entity_names: {sorted(required_entities)}"))
    content_data = {key: value for key, value in data.items() if key != "forbidden_terms"}
    serialized_content = json.dumps(content_data, ensure_ascii=False)
    for forbidden in data.get("forbidden_terms", []):
        if isinstance(forbidden, str) and forbidden in serialized_content:
            out.append(finding("entity-name", contract_path, f"forbidden product spelling appears in publication data: {forbidden}"))
    for entity, record in sorted(entities.items()):
        if not isinstance(record, dict):
            out.append(finding("entity-record", contract_path, f"{entity} must be an object"))
            continue
        entity_url = urlsplit(str(record.get("url", "")))
        aliases = record.get("aliases")
        if entity_url.scheme != "https" or not entity_url.netloc or entity_url.query or entity_url.fragment:
            out.append(finding("entity-url", contract_path, f"{entity} must use a clean official HTTPS URL"))
        if not isinstance(aliases, list) or not aliases or any(not isinstance(alias, str) or not alias.strip() for alias in aliases):
            out.append(finding("entity-aliases", contract_path, f"{entity} must declare non-empty visible aliases"))

    for name, row in sorted(pages.items()):
        if not isinstance(row, dict):
            out.append(finding("page-record", contract_path, f"{name} record must be an object"))
            continue
        for field in ("index", "kind", "seo_title", "description", "entities"):
            if field not in row:
                out.append(finding("page-field", contract_path, f"{name} missing {field}"))
        if not isinstance(row.get("index"), bool):
            out.append(finding("page-index", contract_path, f"{name} index must be boolean"))
        title = row.get("seo_title")
        description = row.get("description")
        if row.get("kind") not in VALID_KINDS:
            out.append(finding("page-kind", contract_path, f"{name} has unknown kind {row.get('kind')!r}"))
        minimum_title = 20 if row.get("index") else 15
        minimum_description = 80 if row.get("index") else 50
        if not isinstance(title, str) or not minimum_title <= len(title) <= 90:
            out.append(finding("seo-title", contract_path, f"{name} needs a specific {minimum_title}-90 character title"))
        if not isinstance(description, str) or not minimum_description <= len(description) <= 320:
            out.append(finding("seo-description", contract_path, f"{name} needs a {minimum_description}-320 character description"))
        page_path = course / name
        raw = page_path.read_text(encoding="utf-8", errors="replace") if page_path.is_file() else ""
        visible = normalized(visible_text(raw))
        for entity in row.get("entities", []) if isinstance(row.get("entities"), list) else []:
            if entity not in entities:
                out.append(finding("entity-unknown", contract_path, f"{name} names unknown entity {entity!r}"))
                continue
            aliases = entities[entity].get("aliases", [])
            if not any(normalized(str(alias)) in visible for alias in aliases):
                out.append(finding("entity-hidden", f"{rel}/{name}", f"metadata entity {entity!r} does not appear in learner-visible page content"))
        if row.get("index"):
            for entity in required_entities:
                if normalized(entity) in normalized(str(title) + " " + str(description)) and entity not in row.get("entities", []):
                    out.append(finding("entity-undisposed", contract_path, f"{name} metadata uses {entity} without declaring it"))

    text = data.get("text_transparency")
    required_text = {
        "origin": "ai-assisted-standard-edit",
        "public_interest_assessment": "release-owner-required",
        "publication_basis": "substantive-human-review-and-editorial-control",
        "accountable_editorial_owner_record": "external-authoritative-system",
        "repository_record": "approval-state-only",
        "unknown_blocks_publication": True,
    }
    if not isinstance(text, dict):
        out.append(finding("text-transparency", contract_path, "text_transparency must be an object"))
    else:
        for key, value in required_text.items():
            if text.get(key) != value:
                out.append(finding("text-transparency", contract_path, f"text_transparency {key} must be {value!r}"))

    runtime_media = data.get("runtime_media")
    if not isinstance(runtime_media, list):
        out.append(finding("runtime-media", contract_path, "runtime_media must be a list"))
    else:
        seen: set[str] = set()
        for row in runtime_media:
            media_id = row.get("id") if isinstance(row, dict) else None
            if not isinstance(media_id, str) or not media_id or media_id in seen:
                out.append(finding("runtime-media", contract_path, "runtime media IDs must be unique non-empty strings"))
                continue
            seen.add(media_id)
            source = course / str(row.get("source", ""))
            if not source.is_file() or str(row.get("source_token", "")) not in source.read_text(encoding="utf-8", errors="replace"):
                out.append(finding("runtime-media-source", contract_path, f"{media_id} source/token does not resolve"))
            if row.get("origin") not in VALID_ORIGINS or row.get("transparency_class") not in VALID_CLASSES:
                out.append(finding("runtime-media-class", contract_path, f"{media_id} has an unknown origin or transparency class"))
            if row.get("visible_disclosure_required") != (row.get("transparency_class") == "deepfake"):
                out.append(finding("runtime-media-disclosure", contract_path, f"{media_id} disclosure requirement does not match its class"))

    script_media = data.get("script_media")
    if not isinstance(script_media, list):
        out.append(finding("script-media", contract_path, "script_media must be a list"))
    elif (course / "scripts").is_dir():
        declared = {str(row.get("value", "")) for row in script_media if isinstance(row, dict)}
        discovered = discovered_script_media(course)
        for value in sorted(discovered - declared):
            out.append(finding("script-media-unclassified", f"{rel}/scripts", f"runtime-mounted image has no publication-integrity record: {value}"))
        for value in sorted(declared - discovered):
            out.append(finding("script-media-stale", contract_path, f"script media record is no longer discovered: {value}"))
        for row in script_media:
            if not isinstance(row, dict):
                out.append(finding("script-media", contract_path, "script media records must be objects"))
                continue
            value = str(row.get("value", ""))
            if row.get("origin") not in VALID_ORIGINS or row.get("transparency_class") not in VALID_CLASSES:
                out.append(finding("script-media-class", contract_path, f"{value} has an unknown origin or transparency class"))
            if row.get("visible_disclosure_required") != (row.get("transparency_class") == "deepfake"):
                out.append(finding("script-media-disclosure", contract_path, f"{value} disclosure requirement does not match its class"))
            if not isinstance(row.get("basis"), str) or not row["basis"].strip():
                out.append(finding("script-media-basis", contract_path, f"{value} lacks a transparency basis"))

    if (course / "mats").is_dir():
        material_rows = material_media_rows(course)
        material_declared = {str(row.get("file", "")) for row in material_rows}
        material_discovered = discovered_material_media(course)
        for value in sorted(material_discovered - material_declared):
            out.append(finding("material-media-unclassified", f"{rel}/mats/SKILL.html", f"cached media has no publication-integrity record: {value}"))
        for value in sorted(material_declared - material_discovered):
            out.append(finding("material-media-stale", f"{rel}/mats/SKILL.html", f"material media record is no longer discovered: {value}"))
        for row in material_rows:
            name = str(row.get("file", "<unnamed>"))
            media_class = row.get("transparency_class")
            if row.get("content_origin") not in VALID_ORIGINS:
                out.append(finding("material-media-origin", f"{rel}/mats/SKILL.html", f"{name} has unknown or missing content_origin"))
            if media_class not in VALID_CLASSES:
                out.append(finding("material-media-class", f"{rel}/mats/SKILL.html", f"{name} has unknown or missing transparency_class"))
            if row.get("visible_disclosure_required") != (media_class == "deepfake"):
                out.append(finding("material-media-disclosure", f"{rel}/mats/SKILL.html", f"{name} disclosure requirement does not match its class"))
            if not isinstance(row.get("transparency_basis"), str) or not row["transparency_basis"].strip():
                out.append(finding("material-media-basis", f"{rel}/mats/SKILL.html", f"{name} lacks a transparency basis"))

    rows = provenance if provenance is not None else figure_rows()
    known_media = {
        str(row.get("file") or row.get("image_url"))
        for row in rows
        if row.get("file") or row.get("image_url")
    }
    for page_path in sorted(course.glob("*.html")):
        raw = page_path.read_text(encoding="utf-8", errors="replace")
        for source in STATIC_MEDIA.findall(raw):
            normalized_source = source.removeprefix("assets/")
            if normalized_source.startswith(("data:", "#")):
                continue
            if normalized_source not in known_media:
                out.append(finding("media-unclassified", f"{rel}/{page_path.name}", f"displayed media has no provenance row: {source}"))
        if RUNTIME_MEDIA_SIGNALS.search(raw):
            matching = [
                row for row in (runtime_media if isinstance(runtime_media, list) else [])
                if row.get("source") == page_path.name
            ]
            if not matching:
                out.append(finding("runtime-media-unclassified", f"{rel}/{page_path.name}", "runtime-generated media surface has no publication-integrity record"))
    for row in rows:
        name = str(row.get("file") or row.get("image_url") or "<unnamed>")
        origin = row.get("content_origin")
        media_class = row.get("transparency_class")
        disclosure = row.get("visible_disclosure_required")
        if origin not in VALID_ORIGINS:
            out.append(finding("media-origin", f"{rel}/assets/SKILL.html", f"{name} has unknown or missing content_origin"))
        if media_class not in VALID_CLASSES:
            out.append(finding("media-class", f"{rel}/assets/SKILL.html", f"{name} has unknown or missing transparency_class"))
        if not isinstance(row.get("transparency_basis"), str) or not row["transparency_basis"].strip():
            out.append(finding("media-basis", f"{rel}/assets/SKILL.html", f"{name} lacks a transparency basis"))
        expected = media_class == "deepfake"
        if disclosure != expected:
            out.append(finding("media-disclosure", f"{rel}/assets/SKILL.html", f"{name} disclosure requirement does not match its class"))
        if expected:
            used_by = course / str(row.get("used_by", ""))
            marker = f'data-ai-content-disclosure="{name}"'
            if not used_by.is_file() or marker not in used_by.read_text(encoding="utf-8", errors="replace"):
                out.append(finding("media-label", str(used_by), f"deepfake media {name} lacks an adjacent visible disclosure"))
    return out


def _meta_values(raw: str, pattern: str) -> list[str]:
    return [unescape(value) for value in re.findall(pattern, raw, re.I | re.S)]


def audit_artifact(
    root: Path,
    contract: dict,
    expected_mode: str,
    *,
    primary_course_root: Path | None = None,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    pages = contract["pages"]
    base = contract["canonical_base"]
    slug = str(contract["course_slug"])
    source_language = str(contract["source_language"])
    course_roots = sorted(path.parent for path in root.rglob(f"{slug}/index.html"))
    canonical_root = primary_course_root.resolve() if primary_course_root is not None else None
    if canonical_root is not None and canonical_root not in {path.resolve() for path in course_roots}:
        return [finding("artifact-course", str(canonical_root), "declared primary course root is missing from the artifact")]
    canonical_root = next((path for path in course_roots if path.resolve() == canonical_root), None)
    if canonical_root is None:
        canonical_root = next((path for path in course_roots if path == root / slug), None)
    if canonical_root is None:
        canonical_root = next((path for path in course_roots if path == root / "web" / slug), None)
    if canonical_root is None:
        return [finding("artifact-course", str(root), "cannot find canonical built course root")]
    locale_roots = {
        root / code / slug
        for code in contract["languages"]
        if code != source_language
    }
    for course_root in course_roots:
        is_primary = course_root == canonical_root or course_root in locale_roots
        for name, record in pages.items():
            path = course_root / name
            if not path.is_file():
                if course_root == canonical_root:
                    out.append(finding("artifact-page", str(path), "primary course projection is missing a classified page"))
                continue
            raw = path.read_text(encoding="utf-8", errors="replace")
            descriptions = _meta_values(raw, r'<meta\b[^>]*\bname=["\']description["\'][^>]*\bcontent=["\']([^"\']+)["\'][^>]*>')
            robots = _meta_values(raw, r'<meta\b[^>]*\bname=["\']robots["\'][^>]*\bcontent=["\']([^"\']+)["\'][^>]*>')
            canonicals = _meta_values(raw, r'<link\b[^>]*\brel=["\']canonical["\'][^>]*\bhref=["\']([^"\']+)["\'][^>]*>')
            json_ld = _meta_values(raw, r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script>')
            if len(descriptions) != 1 or len(robots) != 1 or len(canonicals) != 1 or not json_ld:
                out.append(finding("artifact-metadata", str(path), "requires exactly one description, robots, canonical, and at least one JSON-LD block"))
                continue
            expected_index = expected_mode == "public" and is_primary and record["index"]
            if ("noindex" not in robots[0]) != expected_index:
                out.append(finding("artifact-index", str(path), f"robots directive does not match expected indexability {expected_index}"))
            parsed = urlsplit(canonicals[0])
            if parsed.scheme != "https" or parsed.query or parsed.fragment or canonicals[0].endswith("/index.html"):
                out.append(finding("artifact-canonical", str(path), f"unsafe canonical URL: {canonicals[0]}"))
            for payload in json_ld:
                try:
                    json.loads(payload)
                except json.JSONDecodeError:
                    out.append(finding("artifact-jsonld", str(path), "JSON-LD is malformed"))
    sitemap = root / "sitemap.xml"
    robots_path = root / "robots.txt"
    if expected_mode == "public":
        expected_urls = {
            base if name == "index.html" else base + name
            for name, row in pages.items() if row["index"]
        }
        for code in sorted(set(contract["languages"]) - {source_language}):
            locale_root = root / code / slug
            locale_base = urljoin(base, f"../{code}/{slug}/")
            if locale_root.is_dir():
                expected_urls.update(
                    locale_base if name == "index.html" else urljoin(locale_base, name)
                    for name, row in pages.items() if row["index"] and (locale_root / name).is_file()
                )
        actual_urls = set(_meta_values(sitemap.read_text(encoding="utf-8") if sitemap.is_file() else "", r"<loc>(.*?)</loc>"))
        if actual_urls != expected_urls:
            out.append(finding("sitemap", str(sitemap), "sitemap URL set does not exactly match discovered indexable course pages and locales"))
        expected_sitemap = f"Sitemap: {urljoin(base, '../sitemap.xml')}"
        if not robots_path.is_file() or expected_sitemap not in robots_path.read_text(encoding="utf-8"):
            out.append(finding("robots", str(robots_path), "public robots.txt must point at the public sitemap"))
    elif sitemap.exists() or not robots_path.is_file() or "Disallow: /" not in robots_path.read_text(encoding="utf-8"):
        out.append(finding("preview-robots", str(root), "preview artifacts must have no sitemap and must disallow crawling"))
    return out


def run(
    *,
    artifact_root: Path | None = None,
    primary_course_root: Path | None = None,
    expected_mode: str = "preview",
    verbose: bool = True,
) -> list[dict[str, str]]:
    data = load_contract()
    findings = audit_contract(data)
    if artifact_root is not None:
        findings.extend(
            audit_artifact(
                artifact_root,
                data,
                expected_mode,
                primary_course_root=primary_course_root,
            )
        )
    if verbose:
        if findings:
            print("publication_integrity_audit: FAIL")
            for item in findings:
                print(f"  - [{item['code']}] {item['path']}: {item['detail']}")
        else:
            print("publication_integrity_audit: OK")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--course-root", type=Path)
    parser.add_argument("--expected-mode", choices=("preview", "public"), default="preview")
    args = parser.parse_args()
    return 1 if run(
        artifact_root=args.artifact_root,
        primary_course_root=args.course_root,
        expected_mode=args.expected_mode,
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
