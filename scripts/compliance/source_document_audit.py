#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit and refresh paper-license and NVIDIA document-author evidence.

The normal audit is offline. ``--refresh`` is an explicit acquisition step that reads
official arXiv and NVIDIA pages and writes a candidate JSON file for human review.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from translate.locale_catalog import discover_locales  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "scripts/compliance/docs/document_sources.json"
THIRD_PARTY = ROOT / "THIRD_PARTY_LICENSES.md"
SECTION_HEADING = "## Document source evidence"
ARXIV_RE = re.compile(r"https?://arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})(?:v\d+)?(?:\.pdf)?")
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
ALLOWED_HOSTS = {
    "arxiv.org",
    "assets.ngc.nvidia.com",
    "developer.nvidia.com",
    "blogs.nvidia.com",
    "build.nvidia.com",
    "www.nvidia.com",
}
LICENSES = {
    "https://creativecommons.org/licenses/by/4.0/": (
        "CC-BY-4.0",
        "Reuse and adaptation are allowed, including commercially, with attribution.",
    ),
    "https://creativecommons.org/licenses/by-nc-nd/4.0/": (
        "CC-BY-NC-ND-4.0",
        "Only attributed, noncommercial sharing of unadapted copies is allowed.",
    ),
    "https://arxiv.org/licenses/nonexclusive-distrib/1.0/": (
        "arXiv perpetual, non-exclusive distribution license 1.0",
        "This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper.",
    ),
}


class PageMetadata(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.authors: list[str] = []
        self.license_url = ""
        self._json_ld = False
        self.json_ld: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        data = dict(attrs)
        if tag == "meta" and data.get("name") == "citation_title":
            self.title = data.get("content", "").strip()
        if tag == "meta" and data.get("name") == "citation_author":
            self.authors.append(data.get("content", "").strip())
        if tag == "a" and data.get("title") == "Rights to this article":
            self.license_url = data.get("href", "").strip()
        if tag == "script" and data.get("type") == "application/ld+json":
            self._json_ld = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._json_ld = False

    def handle_data(self, data: str) -> None:
        if self._json_ld:
            self.json_ld.append(data)


def normalize_url(url: str) -> str:
    return "https://" + url.split("://", 1)[-1]


def canonical_course_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "web/nemoclaw"], cwd=ROOT, text=True, capture_output=True, check=True
    )
    selected = []
    for name in result.stdout.splitlines():
        path = Path(name)
        if name.startswith("web/nemoclaw/standalone/") or path.name == "SKILL.html":
            continue
        if re.fullmatch(r"web/nemoclaw/\d\w+-[^/]+\.html", name) or (
            name.startswith("web/nemoclaw/mats/") and path.suffix in {".md", ".json"}
        ):
            selected.append(ROOT / path)
    return selected


def arxiv_citations() -> dict[str, list[str]]:
    citations: dict[str, set[str]] = {}
    for path in canonical_course_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for paper_id in ARXIV_RE.findall(text):
            citations.setdefault(paper_id, set()).add(path.relative_to(ROOT).as_posix())
    return {paper_id: sorted(paths) for paper_id, paths in sorted(citations.items())}


def published_locale_pages() -> dict[str, str]:
    """Return every localized page the build publishes, keyed by repository-relative path.

    A locale page ships either from a reviewed HTML overlay or from a key-based resource. Globbing
    the locale tree would only see the first kind, so a migrated page would silently drop out of
    both the projected-citation check and the repository-item evidence.
    """
    from translate.locale_pages import published_pages

    return published_pages(ROOT)


def page_arxiv_ids(pages: dict[str, str]) -> set[str]:
    paper_ids: set[str] = set()
    for text in pages.values():
        paper_ids.update(ARXIV_RE.findall(text))
    return paper_ids


def directory_pages(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): path.read_text(encoding="utf-8", errors="replace")
        for path in directory.glob("*.html")
    }


def projected_page_sets(published: dict[str, str]) -> list[tuple[str, dict[str, str]]]:
    """Return each projection of the canonical course, whatever representation publishes it."""
    projections = [("web/nemoclaw/standalone", directory_pages(ROOT / "web/nemoclaw/standalone"))]
    for spec in discover_locales(ROOT):
        prefix = spec.course_root.relative_to(ROOT).as_posix() + "/"
        projections.append((prefix.rstrip("/"), {
            rel: text for rel, text in published.items()
            if rel.startswith(prefix) and rel.count("/") == prefix.count("/")
        }))
    return projections


def projection_findings(label: str, canonical: set[str], projected: set[str]) -> list[str]:
    return [
        f"projected course has an unknown arXiv citation: {label}: {paper_id}"
        for paper_id in sorted(projected - canonical)
    ]


def fetch(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if urlparse(url).scheme != "https" or host not in ALLOWED_HOSTS:
        raise ValueError(f"unsupported source URL: {url}")
    request = Request(url, headers={"User-Agent": "NVIDIA-DLI-source-review/1.0"})
    with urlopen(request, timeout=45) as response:
        final_host = (urlparse(response.geturl()).hostname or "").lower()
        if final_host not in ALLOWED_HOSTS:
            raise ValueError(f"source redirected to unsupported host: {final_host}")
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError(f"source exceeds {MAX_RESPONSE_BYTES} bytes: {url}")
    return body.decode("utf-8", errors="replace")


def arxiv_record(paper_id: str, cited_from: list[str], verified_on: str) -> dict:
    source_url = f"https://arxiv.org/abs/{paper_id}"
    parser = PageMetadata()
    parser.feed(fetch(source_url))
    license_url = normalize_url(unescape(parser.license_url))
    if license_url not in LICENSES:
        raise ValueError(f"unsupported or missing arXiv license for {paper_id}: {license_url or 'missing'}")
    label, summary = LICENSES[license_url]
    if not parser.title or not parser.authors:
        raise ValueError(f"missing arXiv title or authors for {paper_id}")
    return {
        "arxiv_id": paper_id,
        "title": parser.title,
        "authors": parser.authors,
        "source_url": source_url,
        "license": label,
        "license_url": license_url,
        "reuse_summary": summary,
        "cited_from": cited_from,
        "verified_on": verified_on,
    }


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def published_authors(html: str) -> tuple[list[str], list[str]]:
    parser = PageMetadata()
    parser.feed(html)
    names: list[str] = []
    profiles: list[str] = []
    for block in parser.json_ld:
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in _walk_json(data):
            if node.get("@type") not in {"Article", "BlogPosting", "NewsArticle"}:
                continue
            authors = node.get("author", [])
            if isinstance(authors, (dict, str)):
                authors = [authors]
            for author in authors:
                if isinstance(author, str):
                    name, profile = author, ""
                elif isinstance(author, dict):
                    name, profile = author.get("name", ""), author.get("url", "")
                else:
                    continue
                if name and name not in names:
                    names.append(name)
                if profile and profile not in profiles:
                    profiles.append(profile)
    return names, profiles


def refresh_document_sources(source: dict, output: Path) -> None:
    verified_on = dt.date.today().isoformat()
    citations = arxiv_citations()
    papers = [arxiv_record(paper_id, paths, verified_on) for paper_id, paths in citations.items()]
    documents = []
    for item in source.get("nvidia_documents", []):
        record = dict(item)
        names, profiles = published_authors(fetch(record["source_url"]))
        record["authors"] = names
        record["author_profiles"] = profiles
        record["author_status"] = "published-byline" if names else "not-listed-on-source"
        record["author_evidence_url"] = record["source_url"]
        record["verified_on"] = verified_on
        documents.append(record)
    refreshed = {
        "schema": "document-source-evidence/1.0",
        "arxiv_license_policy_url": "https://info.arxiv.org/help/license/index.html",
        "arxiv_papers": papers,
        "nvidia_documents": documents,
    }
    output.write_text(json.dumps(refreshed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def material_rows() -> list[list[str]]:
    text = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
    marker = "## Third-party course-material relationships"
    body = text.split(marker, 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in body.splitlines():
        if line.startswith("|") and not re.fullmatch(r"[| :\-]+", line):
            row = [cell.strip() for cell in line.strip("|").split("|")]
            if row[0] != "Repository file":
                rows.append(row)
    return rows


def _cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(data: dict) -> str:
    lines = [
        SECTION_HEADING,
        "",
        "This section covers documents rather than software. Paper licenses are the exact choices",
        "shown by the official arXiv abstract pages at the recorded review date. The repository's",
        "Apache-2.0 license applies to NVIDIA-authored course summaries and diagrams, not to the papers",
        "they cite. NVIDIA document authors are recorded only when the official source publishes a byline.",
        "A missing byline is reported as such and is not replaced with a guessed team or owner.",
        "",
        "### Research papers cited by the course",
        "",
        "| arXiv ID | Paper and authors | Exact source license | Reuse meaning | Evidence | Canonical course citations |",
        "|---|---|---|---|---|---|",
    ]
    for item in data.get("arxiv_papers", []):
        paper = f"{item['title']}<br>Authors: {', '.join(item['authors'])}"
        source = f"[arXiv:{item['arxiv_id']}]({item['source_url']})"
        license_cell = f"[{item['license']}]({item['license_url']})"
        citations = "<br>".join(f"`{path}`" for path in item["cited_from"])
        lines.append(
            "| " + " | ".join(map(_cell, [source, paper, license_cell, item["reuse_summary"], item["verified_on"], citations])) + " |"
        )
    lines.extend([
        "",
        "### NVIDIA documents used as course sources",
        "",
        "| Document | Published author(s) | Source terms | Relationship | Repository items | Evidence checked |",
        "|---|---|---|---|---|---|",
    ])
    for item in data.get("nvidia_documents", []):
        document = f"[{item['title']}]({item['source_url']})"
        if item.get("asset_url"):
            document += f"<br>[Displayed image]({item['asset_url']})"
        if item.get("authors"):
            authors = []
            profiles = item.get("author_profiles") or []
            for index, name in enumerate(item["authors"]):
                authors.append(f"[{name}]({profiles[index]})" if index < len(profiles) else name)
            author_cell = ", ".join(authors)
        else:
            author_cell = "No author listed on the official source page"
        repository_items = "<br>".join(f"`{path}`" for path in item.get("repository_items", []))
        lines.append(
            "| " + " | ".join(map(_cell, [
                document, author_cell, item["terms"], item["relationship"], repository_items, item["verified_on"],
            ])) + " |"
        )
    return "\n".join(lines) + "\n"


def replace_markdown_section(document: str, rendered: str) -> str:
    if SECTION_HEADING in document:
        before, remainder = document.split(SECTION_HEADING, 1)
        next_heading = remainder.find("\n## ")
        after = "" if next_heading < 0 else remainder[next_heading + 1:]
        return before.rstrip() + "\n\n" + rendered.rstrip() + ("\n\n" + after.lstrip() if after else "\n")
    marker = "## Third-party course-material relationships"
    if marker not in document:
        raise ValueError("cannot place document source evidence before course-material relationships")
    return document.replace(marker, rendered.rstrip() + "\n\n" + marker, 1)


def expected_material_source(data: dict, repository_item: str, source_url: str) -> tuple[str, str]:
    match = ARXIV_RE.search(source_url)
    if match:
        paper = next((item for item in data.get("arxiv_papers", []) if item.get("arxiv_id") == match.group(1)), None)
        if paper:
            return paper["license"], paper["source_url"]
    for document in data.get("nvidia_documents", []):
        if repository_item in document.get("repository_items", []):
            return document["terms"], document["source_url"]
    return "", ""


def sync_material_relationships(document: str, data: dict) -> str:
    lines = []
    for line in document.splitlines():
        if not re.match(r"\| (?:web/nemoclaw|i18n/[^/]+/web/nemoclaw)/", line):
            lines.append(line)
            continue
        row = [cell.strip() for cell in line.strip("|").split("|")]
        if len(row) < 5:
            lines.append(line)
            continue
        links = re.findall(r"\[[^]]+\]\((https?://[^)]+)\)", row[4])
        terms, source_url = expected_material_source(data, row[0], links[0] if links else row[4])
        if terms:
            row[3] = terms
            row[4] = f"[source]({source_url})"
            line = "| " + " | ".join(row) + " |"
        lines.append(line)
    return "\n".join(lines) + ("\n" if document.endswith("\n") else "")


def audit(data: dict | None = None) -> list[str]:
    if data is None:
        try:
            data = json.loads(INVENTORY.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return [f"cannot read document source inventory: {exc}"]
    findings: list[str] = []
    if data.get("schema") != "document-source-evidence/1.0":
        findings.append("document source inventory schema is missing or unsupported")
    citations = arxiv_citations()
    published = published_locale_pages()
    canonical_page_ids = page_arxiv_ids(directory_pages(ROOT / "web/nemoclaw"))
    for label, pages in projected_page_sets(published):
        findings.extend(projection_findings(label, canonical_page_ids, page_arxiv_ids(pages)))
    papers = data.get("arxiv_papers", [])
    by_id = {item.get("arxiv_id"): item for item in papers if isinstance(item, dict)}
    if set(by_id) != set(citations):
        for paper_id in sorted(set(citations) - set(by_id)):
            findings.append(f"missing arXiv source record: {paper_id}")
        for paper_id in sorted(set(by_id) - set(citations)):
            findings.append(f"stale arXiv source record: {paper_id}")
    for paper_id, paths in citations.items():
        item = by_id.get(paper_id, {})
        if item.get("source_url") != f"https://arxiv.org/abs/{paper_id}":
            findings.append(f"arXiv source URL drift: {paper_id}")
        if not item.get("title") or not item.get("authors"):
            findings.append(f"arXiv title or authors missing: {paper_id}")
        if item.get("license_url") not in LICENSES:
            findings.append(f"arXiv license evidence missing or unsupported: {paper_id}")
        elif item.get("license") != LICENSES[item["license_url"]][0]:
            findings.append(f"arXiv license label does not match evidence URL: {paper_id}")
        if item.get("cited_from") != paths:
            findings.append(f"arXiv citation locations drifted: {paper_id}")
    covered_items: set[str] = set()
    for item in data.get("nvidia_documents", []):
        source_url = item.get("source_url", "")
        if (urlparse(source_url).hostname or "") not in ALLOWED_HOSTS or not item.get("title"):
            findings.append(f"invalid NVIDIA document source: {source_url or 'missing URL'}")
        status = item.get("author_status")
        authors = item.get("authors") or []
        if status not in {"published-byline", "not-listed-on-source"}:
            findings.append(f"NVIDIA author status missing: {source_url}")
        if (status == "published-byline") != bool(authors):
            findings.append(f"NVIDIA byline/status mismatch: {source_url}")
        if item.get("author_evidence_url") != source_url:
            findings.append(f"NVIDIA author evidence URL drift: {source_url}")
        asset_url = item.get("asset_url", "")
        if item.get("relationship") == "remote display":
            if (urlparse(asset_url).hostname or "") not in ALLOWED_HOSTS:
                findings.append(f"remote NVIDIA image URL missing or invalid: {source_url}")
        elif asset_url:
            findings.append(f"NVIDIA document has an asset URL without remote-display use: {source_url}")
        for path in item.get("repository_items", []):
            # A localized page is evidence when the build publishes it, whether it ships from a
            # reviewed HTML overlay or from a key-based locale resource.
            if path not in published and not (ROOT / path).exists():
                findings.append(f"NVIDIA document references missing repository item: {path}")
            covered_items.add(path)
    expected_items = {
        row[0] for row in material_rows()
        if len(row) >= 4 and row[3].startswith("(c) NVIDIA")
    }
    for path in sorted(expected_items - covered_items):
        findings.append(f"NVIDIA material lacks author/source record: {path}")
    for row in material_rows():
        if len(row) < 5:
            continue
        links = re.findall(r"\[[^]]+\]\((https?://[^)]+)\)", row[4])
        terms, source_url = expected_material_source(data, row[0], links[0] if links else row[4])
        if terms and (row[3] != terms or not links or links[0] != source_url):
            findings.append(f"course-material source evidence is stale: {row[0]}")
    try:
        document = THIRD_PARTY.read_text(encoding="utf-8")
        if SECTION_HEADING not in document:
            findings.append("THIRD_PARTY_LICENSES.md lacks document source evidence")
        else:
            before, remainder = document.split(SECTION_HEADING, 1)
            next_heading = remainder.find("\n## ")
            actual = SECTION_HEADING + (remainder if next_heading < 0 else remainder[:next_heading + 1])
            if actual.strip() != render_markdown(data).strip():
                findings.append("THIRD_PARTY_LICENSES.md document source evidence is stale")
    except OSError as exc:
        findings.append(f"cannot read THIRD_PARTY_LICENSES.md: {exc}")
    return findings


def self_test() -> list[str]:
    baseline = audit()
    if baseline:
        return ["baseline is not clean: " + finding for finding in baseline]
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    failures = []

    def remove_nvidia_material_coverage(value: dict) -> None:
        """Remove one repository item from every source that corroborates it."""
        documents = value.get("nvidia_documents", [])
        target = next(
            (path for item in documents for path in item.get("repository_items", [])),
            None,
        )
        if not target:
            return
        for item in documents:
            item["repository_items"] = [
                path for path in item.get("repository_items", []) if path != target
            ]
    mutations = [
        ("paper license", lambda value: value["arxiv_papers"][0].update(license="Apache-2.0"), "license label"),
        ("paper coverage", lambda value: value["arxiv_papers"].pop(), "missing arXiv source record"),
        ("NVIDIA author state", lambda value: value["nvidia_documents"][0].update(author_status="unknown"), "author status"),
        ("remote NVIDIA image", lambda value: value["nvidia_documents"][0].update(asset_url="https://example.invalid/image.jpg"), "remote NVIDIA image URL"),
        ("NVIDIA material coverage", remove_nvidia_material_coverage, "lacks author/source record"),
    ]
    for label, mutate, expected in mutations:
        candidate = json.loads(json.dumps(data))
        mutate(candidate)
        if not any(expected in finding for finding in audit(candidate)):
            failures.append(f"mutation escaped: {label}")
    if not projection_findings("projection", {"1234.56789"}, {"1234.56789", "9876.54321"}):
        failures.append("mutation escaped: projected arXiv citation")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="query official sources and write a review candidate")
    parser.add_argument("--output", type=Path, help="candidate JSON path for --refresh")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--update-markdown", action="store_true", help="project reviewed JSON into THIRD_PARTY_LICENSES.md")
    args = parser.parse_args()
    if args.refresh:
        if not args.output:
            parser.error("--refresh requires --output; review the candidate before replacing the committed inventory")
        source = json.loads(INVENTORY.read_text(encoding="utf-8"))
        refresh_document_sources(source, args.output)
        print(f"wrote source-review candidate to {args.output}")
        return 0
    if args.update_markdown:
        data = json.loads(INVENTORY.read_text(encoding="utf-8"))
        document = replace_markdown_section(THIRD_PARTY.read_text(encoding="utf-8"), render_markdown(data))
        THIRD_PARTY.write_text(sync_material_relationships(document, data), encoding="utf-8")
        print("updated THIRD_PARTY_LICENSES.md document source evidence")
        return 0
    findings = self_test() if args.self_test else audit()
    label = "source document audit self-test" if args.self_test else "source document audit"
    print(label + ": " + ("PASS" if not findings else f"FAIL ({len(findings)})"))
    for finding in findings:
        print("  " + finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
