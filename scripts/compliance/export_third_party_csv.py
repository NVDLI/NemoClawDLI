#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Export the checked third-party inventory in the SWIPAT component-table CSV shape.

The default export contains only software copied into and distributed with the static course.
Additional categories are opt-in so reviewers never have to infer whether a row is vendored,
downloaded for a build, installed for validation, or only evaluated for future use.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

import third_party_inventory_audit as inventory


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPOSITORY = "https://github.com/NVDLI/NemoClawDLI"
CATEGORIES = ("vendored", "build-input", "validation", "evaluated-candidate")
PYODIDE_CANDIDATES = ROOT / "scripts/pyodide/candidate-components.json"
HEADER = (
    "Package / Component Name",
    "Version",
    "License",
    "Link to Component's License",
    "Method of Distribution",
    "Usage Method with NV proprietary code",
    "Comments",
    "Location where component was downloaded from",
    "Link to internal IT Controlled Repository",
)
OTHER = "Other (Please describe in Comments)"
INTERNAL = "Internal Use Only"


def repository_file(base: str, ref: str, path: str) -> str:
    encoded = quote(path, safe="/@._-")
    host = (urlsplit(base).hostname or "").lower()
    blob = "/blob/" if host == "github.com" or host.endswith(".github.com") else "/-/blob/"
    return f"{base.rstrip('/')}{blob}{quote(ref, safe='._-')}/{encoded}"


def npm_page(name: str, version: str) -> str:
    return f"https://www.npmjs.com/package/{quote(name, safe='@/')}/v/{quote(version, safe='._+-')}"


def markdown_links(text: str) -> list[tuple[str, str]]:
    return re.findall(r"\[([^]]+)]\(([^)]+)\)", text)


def package_assets(document: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for asset in document.get("assets", []):
        for package in asset.get("packages", []):
            out.setdefault(package, []).append(asset["file"])
    return out


def vendored_rows(base: str, ref: str) -> list[list[str]]:
    path = ROOT / "web/nemoclaw/vendor/browser-dependencies.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assets = package_assets(document)
    rows = []
    for package in document.get("packages", []):
        name = package["name"]
        version = str(package["version"])
        license_path = "web/nemoclaw/vendor/" + package["license_file"]
        relationship = "direct" if package.get("direct") else "transitive"
        shipped = ", ".join(sorted(assets.get(name, []))) or "shared browser bundle"
        source = "This project selected it directly." if package.get("direct") else "Another browser package requires it."
        comments = (
            f"Learners receive this code as part of the browser course. {source} "
            f"Relationship: {relationship}. Used for: {package['purpose']} Browser file(s): {shipped}. "
            "Used with NVIDIA-authored Apache-2.0 course source; no proprietary-code claim."
        )
        rows.append([
            name,
            version,
            package["license"],
            repository_file(base, ref, license_path),
            OTHER,
            OTHER,
            comments,
            npm_page(name, version),
            repository_file(base, ref, license_path),
        ])
    for component in document.get("embedded_components", []):
        license_path = "web/nemoclaw/vendor/" + component["license_file"]
        comments = (
            "Learners receive this code inside the LangChain browser bundle. LangChain copied the "
            f"utility source into {component['parent_package']} before publishing that npm package; "
            "this project does not patch it. Relationship: embedded-source. "
            f"Used for: {component['purpose']} {component['version_note']} "
            "The adjacent .LEGAL.txt contains only comments that esbuild was instructed to preserve; "
            "the complete license and pinned source evidence are linked here. "
            "Used with NVIDIA-authored Apache-2.0 course source; no proprietary-code claim."
        )
        rows.append([
            component["name"],
            str(component["version"]),
            component["license"],
            repository_file(base, ref, license_path),
            OTHER,
            OTHER,
            comments,
            component["upstream_url"],
            repository_file(base, ref, license_path),
        ])
    return rows


def browser_build_rows(base: str, ref: str) -> list[list[str]]:
    document = (ROOT / inventory.INVENTORY).read_text(encoding="utf-8")
    parsed = inventory.rows(inventory.section(document, "Browser runtime and browser-build packages"))
    rows = []
    for scope, name, version, license_id, _evidence, *_ in parsed:
        if scope not in {"browser-bundle-input", "browser-build-only"}:
            continue
        description = "Course authors download this package while building the browser course. "
        description += (
            "Some of its code becomes part of a generated browser file, but learners do not receive "
            "the package as a separate dependency."
            if scope == "browser-bundle-input"
            else "It runs only during the build; learners do not receive it."
        )
        rows.append([
            name,
            version,
            license_id,
            npm_page(name, version),
            INTERNAL,
            OTHER,
            f"Category: {scope}. {description} No proprietary-code claim.",
            npm_page(name, version),
            repository_file(base, ref, "scripts/browser-vendor/package-lock.json"),
        ])
    return rows


def python_rows(base: str, ref: str) -> list[list[str]]:
    document = (ROOT / inventory.INVENTORY).read_text(encoding="utf-8")
    parsed = inventory.rows(inventory.section(document, "Python and Node repository-tool packages"))
    rows = []
    for row in parsed:
        if len(row) < 5 or row[0] == "Identifier":
            continue
        scope, name, version, license_id, evidence, *_ = row
        links = markdown_links(evidence)
        upstream = next((url for label, url in links if label in {"PyPI", "npm"}), "")
        lock_path = next((url for _label, url in links if not url.startswith(("http://", "https://"))), "")
        internal = repository_file(base, ref, lock_path) if lock_path else repository_file(base, ref, inventory.INVENTORY)
        rows.append([
            name,
            version,
            license_id,
            upstream,
            INTERNAL,
            OTHER,
            f"Course authors or CI use this package to prepare or check the course ({scope}). "
            "Learners do not receive it from the static course. No proprietary-code claim.",
            upstream,
            internal,
        ])
    return rows


def evaluated_candidate_rows(base: str, ref: str) -> list[list[str]]:
    """Expose the complete reviewed Pyodide candidate closure without implying distribution."""
    document = json.loads(PYODIDE_CANDIDATES.read_text(encoding="utf-8"))
    live_demo = document["live_demo"]
    use_labels = {
        "acquisition": "Future asset-preparation helper",
        "core": "Separate browser-Python demonstration",
        "network": "Future outbound HTTP and model-API support",
    }
    role_labels = {
        "build-input": "download helper used while preparing browser files",
        "runtime-core": "runtime required by the separate demonstration",
        "direct": "package selected for the proposed capability",
        "transitive": "dependency brought in by a selected package",
    }
    rows = []
    for component in document["components"]:
        profile = component["profile"]
        if profile == "core":
            download = live_demo["base_url"]
        else:
            download = component["license_evidence_url"]
        review_note = component.get("review_note", "")
        comments = (
            f"Evaluated use: {use_labels.get(profile, 'Possible future capability')}. "
            f"Component role: {role_labels.get(component['relationship'], component['relationship'])}. "
            f"{document['profiles'][profile]['description']} "
            "Human approval remains required before distribution."
        )
        if review_note:
            comments += f" Review note: {review_note}"
        rows.append([
            component["name"],
            str(component["version"]),
            component["license_expression"],
            component["license_evidence_url"],
            INTERNAL,
            OTHER,
            comments,
            download,
            repository_file(base, ref, "scripts/pyodide/candidate-components.json"),
        ])
    return rows


def component_rows(categories: list[str], base: str, ref: str) -> list[list[str]]:
    loaders = {
        "vendored": vendored_rows,
        "build-input": browser_build_rows,
        "validation": python_rows,
        "evaluated-candidate": evaluated_candidate_rows,
    }
    rows = []
    for category in CATEGORIES:
        if category in categories:
            rows.extend(loaders[category](base, ref))
    return rows


def render_csv(rows: list[list[str]], base_container: str) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["Base Container used (if applicable):", "", base_container, "", "", "", "", "", ""])
    writer.writerow([""] * len(HEADER))
    writer.writerow(HEADER)
    writer.writerows(rows)
    return stream.getvalue()


def validate_export(text: str, expected_rows: int, require_resolved: bool) -> list[str]:
    parsed = list(csv.reader(io.StringIO(text)))
    findings = []
    if len(parsed) != expected_rows + 3:
        findings.append(f"row count {len(parsed)} does not equal metadata/header plus {expected_rows} components")
    if len(parsed) < 3 or tuple(parsed[2]) != HEADER:
        findings.append("SWIPAT header does not match the supplied nine-column template")
    for number, row in enumerate(parsed[3:], 4):
        if len(row) != len(HEADER):
            findings.append(f"row {number} has {len(row)} columns instead of {len(HEADER)}")
            continue
        if not all(row[index].strip() for index in (0, 1, 2, 6, 8)):
            findings.append(f"row {number} is missing component, version, license, comments, or internal repository link")
        if require_resolved and row[2] in {"NOASSERTION", "Missing license evidence"}:
            findings.append(f"row {number} leaves a vendored component license unresolved")
    return findings


def self_test() -> list[str]:
    vendored = component_rows(["vendored"], DEFAULT_REPOSITORY, "main")
    text = render_csv(vendored, "Not Applicable - static browser course")
    findings = validate_export(text, len(vendored), require_resolved=True)
    manifest = json.loads((ROOT / "web/nemoclaw/vendor/browser-dependencies.json").read_text(encoding="utf-8"))
    expected = manifest["packages"] + manifest["embedded_components"]
    if {(row[0], row[1], row[2]) for row in vendored} != {
        (row["name"], str(row["version"]), row["license"]) for row in expected
    }:
        findings.append("vendored export does not exactly match browser-dependencies.json")
    if "/blob/main/" not in repository_file(DEFAULT_REPOSITORY, "main", "LICENSE"):
        findings.append("GitHub repository links do not use the GitHub blob route")
    if "/-/blob/main/" not in repository_file("https://gitlab.example/review/course", "main", "LICENSE"):
        findings.append("GitLab repository links do not use the GitLab blob route")
    all_rows = component_rows(list(CATEGORIES), DEFAULT_REPOSITORY, "main")
    all_text = render_csv(all_rows, "Not Applicable - static browser course")
    findings.extend(validate_export(all_text, len(all_rows), require_resolved=False))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--category",
        action="append",
        choices=(*CATEGORIES, "all"),
        help="repeatable relationship filter; default: vendored",
    )
    parser.add_argument("--base-container", default="Not Applicable - static browser course")
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--project-ref", default="main")
    parser.add_argument("--output", type=Path, help="write CSV here; omit to print to stdout")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        findings = self_test()
        if findings:
            print(f"third-party CSV exporter self-test: FAIL ({len(findings)})")
            for finding in findings:
                print(f"  {finding}")
            return 1
        print("third-party CSV exporter self-test: PASS")
        return 0

    categories = args.category or ["vendored"]
    if "all" in categories:
        categories = list(CATEGORIES)
    categories = list(dict.fromkeys(categories))
    rows = component_rows(categories, args.repository, args.project_ref)
    text = render_csv(rows, args.base_container)
    findings = validate_export(text, len(rows), require_resolved=(categories == ["vendored"]))
    if findings:
        for finding in findings:
            print(f"export error: {finding}", file=sys.stderr)
        return 1
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        print(f"wrote {len(rows)} component rows to {args.output}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
