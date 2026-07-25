#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Export an auditable relationship map without conflating software and course materials."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import io
import json
import sys
from pathlib import Path

import export_third_party_csv as software
import third_party_inventory_audit as inventory


ROOT = Path(__file__).resolve().parents[2]
DOCUMENT_INVENTORY = ROOT / "scripts/compliance/docs/document_sources.json"
CATEGORIES = (
    "external-source-record",
    "referenced-source",
    "tooling-not-distributed",
    "recreated-asset",
    "vendored-material",
    "vendored-browser-code",
)
HEADER = (
    "Repository Item",
    "Scope Category",
    "Artifact Relationship",
    "Distributed by NVIDIA in This Repository",
    "Executed in Learner Browser",
    "External Source or Package",
    "Recorded License or Terms",
    "Source Author(s)",
    "License or Author Evidence",
    "Corroborating Repository Evidence",
    "Legal Scope Note",
)


def document_inventory() -> dict:
    return json.loads(DOCUMENT_INVENTORY.read_text(encoding="utf-8"))


def source_metadata(repository_file: str, source_url: str, documents: dict) -> tuple[str, str, str]:
    for item in documents.get("arxiv_papers", []):
        if item.get("source_url") == source_url:
            return ", ".join(item.get("authors", [])), item.get("license_url", ""), item.get("reuse_summary", "")
    for item in documents.get("nvidia_documents", []):
        if repository_file in item.get("repository_items", []):
            authors = ", ".join(item.get("authors", [])) or "No author listed on official source page"
            return authors, item.get("author_evidence_url", source_url), ""
    return "Not recorded for this source", source_url, ""


def material_rows(base: str, ref: str) -> list[list[str]]:
    document = (ROOT / inventory.INVENTORY).read_text(encoding="utf-8")
    rows = inventory.rows(inventory.section(document, "Third-party course-material relationships"))
    output: list[list[str]] = []
    documents = document_inventory()
    for row in rows:
        if len(row) < 5 or row[0] == "Repository file":
            continue
        repository_file, relationship, source_name, terms, source_cell = row[:5]
        links = software.markdown_links(source_cell)
        source_url = links[0][1] if links else source_cell
        authors, source_evidence, reuse_summary = source_metadata(repository_file, source_url, documents)
        if relationship == "recreation":
            category = "recreated-asset"
            note = "A repository-authored recreation is distributed; review the recorded source terms before release."
        elif relationship in {"conversion", "provided course asset"}:
            category = "vendored-material"
            note = "A copied, provided, or format-shifted material artifact is distributed; the source terms remain controlling."
        elif relationship == "remote display":
            category = "referenced-source"
            note = (
                "The repository stores the source link and caption. The learner's browser requests "
                "the image from NVIDIA's host; the image is not copied into this repository."
            )
        else:
            category = "referenced-source"
            note = (
                "The repository item is distributed, but the external work is used as a citation, summary, "
                "inspiration, original-work reference, or link compilation rather than a vendored copy."
            )
        output.append([
            repository_file,
            category,
            relationship,
            (
                "No - the browser loads the image from NVIDIA's host"
                if relationship == "remote display"
                else "Yes - repository-authored item" if category == "referenced-source" else "Yes"
            ),
            "No",
            source_url,
            terms,
            authors,
            source_evidence,
            software.repository_file(base, ref, repository_file),
            f"Source label: {source_name}. {note}" + (f" {reuse_summary}" if reuse_summary else ""),
        ])
    return output


def document_rows(base: str, ref: str) -> list[list[str]]:
    data = document_inventory()
    inventory_document = (ROOT / inventory.INVENTORY).read_text(encoding="utf-8")
    provenance_rows = inventory.rows(inventory.section(
        inventory_document, "Third-party course-material relationships"
    ))
    relationship_by_item = {
        row[0]: row[1] for row in provenance_rows
        if len(row) >= 2 and row[0] != "Repository file"
    }
    rows: list[list[str]] = []
    for item in data.get("arxiv_papers", []):
        evidence_path = (item.get("cited_from") or ["THIRD_PARTY_LICENSES.md"])[0]
        rows.append([
            f"arXiv:{item['arxiv_id']}", "external-source-record", "paper citation",
            f"No - this row records an external paper cited from {len(item['cited_from'])} repository item(s); it does not distribute the paper", "No", item["source_url"], item["license"],
            ", ".join(item["authors"]), item["license_url"], software.repository_file(base, ref, evidence_path),
            f"Official arXiv license checked {item['verified_on']}. {item['reuse_summary']} "
            f"Canonical citations: {', '.join(item['cited_from'])}",
        ])
    for item in data.get("nvidia_documents", []):
        repository_items = item.get("repository_items") or []
        missing = [path for path in repository_items if path not in relationship_by_item]
        if missing:
            raise ValueError(f"NVIDIA document {item['title']!r} has unclassified repository items: {missing}")
        counts = Counter(relationship_by_item[path] for path in repository_items)
        copied = counts["conversion"] + counts["provided course asset"]
        recreated = counts["recreation"]
        remote = counts["remote display"]
        if copied:
            category = "vendored-material"
            distribution = f"Yes - copied or converted into {copied} repository item(s)"
        elif recreated:
            category = "recreated-asset"
            distribution = f"Yes - represented by {recreated} repository-authored recreation(s)"
        elif remote:
            category = "referenced-source"
            distribution = (
                f"No - {remote} course page(s) load the image from NVIDIA's host; "
                "the repository stores links and captions only"
            )
        else:
            category = "referenced-source"
            distribution = (
                f"Yes - represented by {len(repository_items)} repository-authored reference item(s); "
                "the external document is not copied wholesale"
            )
        evidence_path = (repository_items or ["THIRD_PARTY_LICENSES.md"])[0]
        authors = ", ".join(item.get("authors", [])) or "No author listed on official source page"
        uses = ", ".join(f"{name}: {count}" for name, count in sorted(counts.items()))
        rows.append([
            item["title"], category, "document use roll-up", distribution, "No",
            item["source_url"], item["terms"], authors, item["author_evidence_url"],
            software.repository_file(base, ref, evidence_path),
            f"Official source checked {item['verified_on']}. Classified uses: {uses}. "
            f"Repository items: {', '.join(repository_items)}",
        ])
    return rows


def tooling_rows(base: str, ref: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for item in software.browser_build_rows(base, ref):
        if "Category: browser-build-only." not in item[6]:
            continue
        rows.append([
            f"{item[0]}@{item[1]}", "tooling-not-distributed", "browser-build-only", "No", "No",
            item[7], item[2], "Not applicable to software package", item[3] or item[7], item[8], item[6],
        ])
    for item in software.python_rows(base, ref):
        rows.append([
            f"{item[0]}@{item[1]}", "tooling-not-distributed", "validation dependency",
            "No", "No", item[7], item[2], "Not applicable to software package", item[3] or item[7], item[8], item[6],
        ])
    return rows


def browser_code_rows(base: str, ref: str) -> list[list[str]]:
    rows = []
    for item in software.vendored_rows(base, ref):
        relationship = next(
            (value for value in ("direct", "transitive", "embedded-source")
             if f"Relationship: {value}." in item[6]),
            "unclassified",
        )
        rows.append([
            f"{item[0]}@{item[1]}", "vendored-browser-code",
            relationship,
            "Yes", "Yes", item[7], item[2], "Not applicable to software package", item[3], item[8],
            "Copied into the same-origin static course; the linked repository license text and package source corroborate scope.",
        ])
    return rows


def scope_rows(categories: list[str], base: str, ref: str) -> list[list[str]]:
    rows = document_rows(base, ref) + material_rows(base, ref) + tooling_rows(base, ref) + browser_code_rows(base, ref)
    return [row for row in rows if row[1] in categories]


def render_csv(rows: list[list[str]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return stream.getvalue()


def validate(rows: list[list[str]]) -> list[str]:
    findings = []
    for number, row in enumerate(rows, 2):
        if len(row) != len(HEADER):
            findings.append(f"row {number} has {len(row)} columns instead of {len(HEADER)}")
        elif any(not row[index].strip() for index in (0, 1, 2, 3, 5, 6, 7, 8, 9, 10)):
            findings.append(f"row {number} lacks scope, source, terms, evidence, or disposition detail")
        elif "see related" in row[3].lower():
            findings.append(f"row {number} delegates its distribution answer instead of stating it")
    return findings


def self_test() -> list[str]:
    rows = scope_rows(list(CATEGORIES), software.DEFAULT_REPOSITORY, "main")
    findings = validate(rows)
    if {row[1] for row in rows} != set(CATEGORIES):
        findings.append("scope export does not exercise every legal relationship category")
    material_count = len(inventory.rows(inventory.section(
        (ROOT / inventory.INVENTORY).read_text(encoding="utf-8"),
        "Third-party course-material relationships",
    )))
    material_relationships = {
        "recreation", "conversion", "provided course asset", "remote display", "summary", "inspiration",
        "compilation", "original", "original course graphic",
    }
    exported_material_count = sum(row[2] in material_relationships for row in rows)
    if exported_material_count != material_count:
        findings.append("scope export does not exactly cover the material-provenance table")
    favicon = next((row for row in rows if row[0] == "web/nemoclaw/assets/favicon.ico"), None)
    if not favicon or favicon[1] != "vendored-material" or favicon[2] != "provided course asset":
        findings.append("NVIDIA favicon is not exported as a provided, vendored brand asset")
    remote_image = next((row for row in rows if row[2] == "remote display"), None)
    if not remote_image or remote_image[1] != "referenced-source" or not remote_image[3].startswith("No -"):
        findings.append("remote NVIDIA image is not exported as externally loaded and not distributed")
    documents = document_inventory()
    expected_documents = len(documents.get("arxiv_papers", [])) + len(documents.get("nvidia_documents", []))
    if sum(row[2] in {"paper citation", "document use roll-up"} for row in rows) != expected_documents:
        findings.append("scope export does not exactly cover the document-source inventory")
    nvidia_rollups = [row for row in rows if row[2] == "document use roll-up"]
    if len(nvidia_rollups) != len(documents.get("nvidia_documents", [])):
        findings.append("scope export does not produce one classified roll-up per NVIDIA document")
    if any(not row[3].startswith(("Yes - ", "No - ")) for row in nvidia_rollups):
        findings.append("NVIDIA document roll-ups do not state their repository distribution directly")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--category", action="append", choices=(*CATEGORIES, "all"))
    parser.add_argument("--repository", default=software.DEFAULT_REPOSITORY)
    parser.add_argument("--project-ref", default="main")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        findings = self_test()
        print("legal-scope CSV exporter self-test: " + ("PASS" if not findings else f"FAIL ({len(findings)})"))
        for finding in findings:
            print(f"  {finding}")
        return bool(findings)
    categories = args.category or list(CATEGORIES)
    if "all" in categories:
        categories = list(CATEGORIES)
    rows = scope_rows(list(dict.fromkeys(categories)), args.repository, args.project_ref)
    findings = validate(rows)
    if findings:
        for finding in findings:
            print(f"export error: {finding}", file=sys.stderr)
        return 1
    text = render_csv(rows)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {len(rows)} legal-scope rows to {args.output}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
