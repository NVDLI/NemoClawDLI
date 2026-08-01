#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Keep the static third-party Markdown inventory aligned with repository inputs."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = "THIRD_PARTY_LICENSES.md"
RUNBOOK = "scripts/compliance/docs/sbom_generation.md"
EVIDENCE_CATALOG = "scripts/compliance/docs/sbom_evidence.json"
COMPLIANCE_SKILL = "scripts/compliance/SKILL.html"
CSV_EXPORTER = "scripts/compliance/export_third_party_csv.py"
SCOPE_EXPORTER = "scripts/compliance/export_legal_scope_csv.py"
CSV_PREVIEW = "scripts/compliance/third_party_export_ui.js"
PYTHON_LOCKS = (
    "scripts/materials/requirements.lock",
    "scripts/security/requirements-sca.lock",
)
PROVENANCE = (
    ("web/nemoclaw/assets", "web/nemoclaw/assets/SKILL.html", ("figures", "assets")),
    ("web/nemoclaw/mats", "web/nemoclaw/mats/SKILL.html", ("mats", "figures", "assets")),
)
REQUIRED_DISTRIBUTION_LINES = (
    'cp "$T1/LICENSE" "$OUT/LICENSE"',
    'cp "$T1/THIRD_PARTY_LICENSES.md" "$OUT/THIRD_PARTY_LICENSES.md"',
    'cp "$T1/scripts/compliance/docs/sbom_generation.md" "$OUT/scripts/compliance/docs/sbom_generation.md"',
    'cp "$T1/scripts/compliance/docs/sbom_evidence.json" "$OUT/scripts/compliance/docs/sbom_evidence.json"',
)
REQUIRED_EXPLANATIONS = (
    "## Reproducing license-evidence acquisition",
    "scripts/compliance/docs/sbom_generation.md",
    "Generated SBOM bodies are attached to the review record rather than committed here.",
    "`argparse@2.0.1` is a JavaScript npm package used transitively by `js-yaml@5.2.2`.",
    "No active package row declares GPL.",
    "LGPL-2.0-or-later (`chardet`)",
    "this repository does not define, build, scan, or distribute that container",
    "exact package/version static fallback",
)
REQUIRED_RUNBOOK_TEXT = (
    "# SBOM generation and attachment runbook",
    "The repository does not define or distribute a container image.",
    "npm view <name>@<version> license dist.integrity repository --json",
    "https://pypi.org/pypi/<normalized-name>/<version>/json",
    'syft scan dir:"$PWD"',
    "https://github.com/anchore/syft/releases/tag/v1.44.0",
    "Those extractors acquire content",
    "scripts/compliance/render_sbom_license_inventory.py",
    "scripts/compliance/resolve_sbom_licenses.py",
    "scripts/compliance/sbom_evidence.py",
    "scripts/compliance/docs/sbom_evidence.json",
    "browser-runtime.cdx.json",
    "python-env.cdx.json",
    "python-env.raw.cdx.json",
    "source-tree.cdx.json",
    "source-tree.spdx.json",
)
REQUIRED_EXPORT_CATEGORIES = {
    "vendored", "build-input", "validation", "evaluated-candidate", "all",
}
REQUIRED_SCOPE_CATEGORIES = {
    "external-source-record", "referenced-source", "tooling-not-distributed", "recreated-asset",
    "vendored-material", "vendored-browser-code", "all",
}


def read(path: str, overrides: dict[str, str]) -> str:
    return overrides.get(path, (ROOT / path).read_text(encoding="utf-8"))


def section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    if marker not in text:
        return ""
    body = text.split(marker, 1)[1]
    return body.split("\n## ", 1)[0]


def rows(body: str) -> list[list[str]]:
    parsed = []
    for line in body.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-"}:
            continue
        values = [value.strip() for value in line.strip("|").split("|")]
        if values and values[0] != "Scope" and values[0] != "Repository file":
            parsed.append(values)
    return parsed


def python_pins(text: str) -> set[tuple[str, str]]:
    found = set()
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^]]+\])?==([^\s;]+)", line)
        if match:
            name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
            found.add((name, match.group(2)))
    return found


def provenance(path: str, overrides: dict[str, str]) -> dict:
    match = re.search(
        r'<script[^>]+id=["\']provenance["\'][^>]*>(.*?)</script>',
        read(path, overrides),
        re.S,
    )
    return json.loads(match.group(1)) if match else {}


def export_contract_findings(overrides: dict[str, str]) -> list[str]:
    findings = []
    skill = read(COMPLIANCE_SKILL, overrides)
    match = re.search(r'<script[^>]+id=["\']skill-meta["\'][^>]*>(.*?)</script>', skill, re.S)
    try:
        meta = json.loads(match.group(1)) if match else {}
    except json.JSONDecodeError:
        meta = {}
    export = next((item for item in meta.get("exports", []) if item.get("id") == "swipat-component-table"), None)
    if not export:
        findings.append("missing parameterized SWIPAT component export in scripts/compliance/SKILL.html")
    else:
        categories = set((export.get("categories") or {}).keys())
        if not REQUIRED_EXPORT_CATEGORIES <= categories:
            findings.append("SWIPAT component export does not distinguish every distribution relationship")
        if export.get("default_category") != "vendored":
            findings.append("SWIPAT component export must default to vendored and distributed components")
        if export.get("preview_mount") != "third-party-export-preview":
            findings.append("SWIPAT component export does not declare its in-page preview mount")
        parameters = " ".join(export.get("parameters") or [])
        for flag in ("--category", "--repository", "--project-ref", "--output"):
            if flag not in parameters:
                findings.append(f"SWIPAT component export parameter is missing: {flag}")
    scope_export = next((item for item in meta.get("exports", []) if item.get("id") == "legal-scope-map"), None)
    if not scope_export:
        findings.append("missing legal-scope relationship export in scripts/compliance/SKILL.html")
    else:
        categories = set((scope_export.get("categories") or {}).keys())
        if not REQUIRED_SCOPE_CATEGORIES <= categories:
            findings.append("legal-scope export does not distinguish every review relationship")
        if scope_export.get("default_category") != "all":
            findings.append("legal-scope export must default to the complete relationship map")
        if scope_export.get("preview_mount") != "legal-scope-preview":
            findings.append("legal-scope export does not declare its in-page preview mount")
    for token in (
        'id="third-party-export-preview"',
        '<div class="filter-choice-group" data-export-category-group>',
        '<div class="filter-choice-group" data-export-relationship-group>',
        '<div class="filter-choice-group" data-export-license-group>',
        "data-export-search",
        "data-export-download",
        '<script src="third_party_export_ui.js"></script>',
        'id="legal-scope-preview"',
        '<div class="filter-choice-group" data-scope-category-group>',
        '<div class="filter-choice-group" data-scope-relationship-group>',
        '<div class="filter-choice-group" data-scope-terms-group>',
        "data-scope-download",
        'aria-label="SWIPAT filter meanings"',
        'aria-label="Legal-scope filter meanings"',
        "Software and license review",
        "Does a learner receive this software?",
        "How learners receive it",
        "You can choose several options in one filter",
        "Download what you see",
        "What happened to the source?",
        "skill-shell",
        "white-space:pre-wrap",
        "Download visible rows",
    ):
        if token not in skill:
            findings.append(f"SWIPAT in-page preview control is missing: {token}")
    preview = read(CSV_PREVIEW, overrides)
    for token in (
        "vendored", "build-input", "validation", "dataset.exportReady",
        "external-source-record", "referenced-source", "tooling-not-distributed", "recreated-asset", "vendored-material",
        "vendored-browser-code", "Corroborating Repository Evidence",
        "selectedValues", "choiceGroup", "sortedRows", "sortableHeaders", "dataset.sortIndex",
        "FILTER_LABELS", "Included in the course", "External document citation record",
        "License evidence missing", "friendlyChoice",
        "documentScopeRows", "document use roll-up", "document_sources", "Source Author(s)", "renderScopeRow", "dataset.label",
        "sbom_evidence", "ci_sbom_evidence", "renderSbomEvidence", "linkedSbomComponents",
        "dataset.sbomSubject", "license_hint", 'Learners receive these " + record.sbom.component_count + " packages',
        "Learners do not receive these packages", "Learners do not receive these tools",
        "packages needing license clarification", "Files for auditors and automation",
        "evaluated-candidate", "evaluatedCandidateRows", "pyodide_candidates",
        "Evaluated option, not shipped", "candidate-components.json",
        "Future outbound HTTP and model-API support", "Component role:",
        "manifest.embedded_components", "embedded-source",
        "LangChain copied the utility source into", ".LEGAL.txt contains only comments",
    ):
        if token not in preview:
            findings.append(f"SWIPAT preview implementation is incomplete: {token}")
    for opaque_label in ("Profile: network", "Optional network-profile candidate"):
        if opaque_label in preview or opaque_label in skill:
            findings.append(f"reviewer-facing software copy exposes an opaque implementation label: {opaque_label}")
    scope_exporter = read(SCOPE_EXPORTER, overrides)
    for placeholder in ("See related repository-item rows", "Referenced, not copied"):
        if placeholder in preview or placeholder in scope_exporter or placeholder in skill:
            findings.append(f"legal-scope export delegates or misstates distribution: {placeholder}")
    for phrase in (
        "The linked file passed its recorded SHA-256 check",
        "Every link was read through the GitLab job-artifact API",
        "Open producing CI job",
        "Preview resolved Python licenses",
    ):
        if phrase in preview or phrase in skill:
            findings.append(f"reviewer-facing software copy exposes build-centric status language: {phrase}")
    for path in (CSV_EXPORTER, CSV_PREVIEW):
        export_source = read(path, overrides)
        for token in (
            "Learners receive this code as part of the browser course.",
            "Course authors or CI use this package to prepare or check the course",
            "Learners do not receive it from the static course.",
        ):
            if token not in export_source:
                findings.append(f"reviewer export lacks plain-language usage explanation: {path}: {token}")
    return findings


def audit(overrides: dict[str, str] | None = None) -> list[str]:
    overrides = overrides or {}
    document = read(INVENTORY, overrides)
    runbook = read(RUNBOOK, overrides)
    try:
        evidence_catalog = json.loads(read(EVIDENCE_CATALOG, overrides))
    except (json.JSONDecodeError, OSError):
        evidence_catalog = {}
    findings: list[str] = []

    browser_rows = rows(section(document, "Browser runtime and browser-build packages"))
    browser_index = {(row[1], row[2]): row for row in browser_rows if len(row) >= 4}
    lock = json.loads(read("scripts/browser-vendor/package-lock.json", overrides))
    js_yaml = (lock.get("packages") or {}).get("node_modules/js-yaml") or {}
    if (js_yaml.get("dependencies") or {}).get("argparse") != "^2.0.1":
        findings.append("browser dependency trace changed: js-yaml no longer declares argparse ^2.0.1")
    for path, item in (lock.get("packages") or {}).items():
        if not path:
            continue
        name = path.removeprefix("node_modules/")
        key = (name, str(item.get("version", "")))
        row = browser_index.get(key)
        if not row:
            findings.append(f"missing browser package row: {name}=={key[1]}")
        elif row[3] != (item.get("license") or "NOASSERTION"):
            findings.append(f"browser license drift: {name}=={key[1]}")

    python_rows = rows(section(document, "Python and Node repository-tool packages"))
    python_index = {(row[1], row[2]): row for row in python_rows if len(row) >= 4}
    expected_python = set()
    for path in PYTHON_LOCKS:
        expected_python |= python_pins(read(path, overrides))
    for name, version in sorted(expected_python):
        row = python_index.get((name, version))
        if not row:
            findings.append(f"missing Python package row: {name}=={version}")
        elif row[3] in {"", "BSD", "Apache2.0", "NOASSERTION"}:
            findings.append(f"non-specific Python license identifier: {name}=={version}: {row[3]}")
    playwright = python_index.get(("playwright-core", "1.62.0"))
    if not playwright or playwright[0] != "browser-validation" or playwright[3] != "Apache-2.0":
        findings.append("missing pinned host browser-validation package: playwright-core==1.62.0")

    material_rows = rows(section(document, "Third-party course-material relationships"))
    material_paths = {row[0] for row in material_rows if row}
    for base, path, arrays in PROVENANCE:
        data = provenance(path, overrides)
        for array in arrays:
            for item in data.get(array, []) or []:
                if item.get("source_url"):
                    if item.get("file"):
                        local = f"{base}/{item['file']}"
                    elif item.get("image_url") and item.get("used_by"):
                        local = f"{Path(base).parent.as_posix()}/{item['used_by']}"
                    else:
                        findings.append(
                            f"external material lacks a repository file or remote-image use: {path}"
                        )
                        continue
                    if local not in material_paths:
                        findings.append(f"missing external-material row: {local}")

    for explanation in REQUIRED_EXPLANATIONS:
        if explanation not in document:
            findings.append(f"missing license-scope explanation: {explanation}")
    for instruction in REQUIRED_RUNBOOK_TEXT:
        if instruction not in runbook:
            findings.append(f"missing SBOM acquisition instruction: {instruction}")
    if evidence_catalog.get("schema") != "nemoclaw-sbom-evidence/1":
        findings.append("missing machine-readable SBOM evidence catalog")
    states = {record.get("state") for record in evidence_catalog.get("records", []) if isinstance(record, dict)}
    if states != {"available", "ci-generated"}:
        findings.append("SBOM evidence catalog must distinguish repository and CI-generated evidence")
    findings.extend(export_contract_findings(overrides))
    pages_build = read("scripts/build/build_pages.sh", overrides)
    for line in REQUIRED_DISTRIBUTION_LINES:
        if line not in pages_build:
            findings.append(f"Pages artifact does not distribute required license file: {line}")

    return findings


def self_test() -> list[str]:
    baseline = audit()
    if baseline:
        return ["baseline is not clean: " + finding for finding in baseline]
    document = read(INVENTORY, {})
    runbook = read(RUNBOOK, {})
    pages_build = read("scripts/build/build_pages.sh", {})
    compliance_skill = read(COMPLIANCE_SKILL, {})
    mutations = (
        ("browser row", {INVENTORY: document.replace("| browser-runtime | codemirror | 5.65.21 |", "| removed | codemirror | 0 |", 1)}, "missing browser package row"),
        ("Python row", {INVENTORY: re.sub(r"(?m)^\| [^|\n]*tooling[^|\n]* \| requests \| [^|]+ \|.*$", "| removed | requests | 0 |", document, count=1)}, "missing Python package row"),
        ("Python identifier", {INVENTORY: re.sub(r"(?m)^(\| [^\n|]+ \| pip-audit \| [^|]+ \|) Apache-2\.0 (\|.*)$", r"\1 NOASSERTION \2", document, count=1)}, "non-specific Python license identifier"),
        ("material row", {INVENTORY: document.replace("| web/nemoclaw/assets/figures/fig2_react.svg |", "| removed/fig2_react.svg |", 1)}, "missing external-material row"),
        ("remote material row", {INVENTORY: document.replace("| web/nemoclaw/index.html | remote display |", "| removed/index.html | remote display |", 1)}, "missing external-material row"),
        ("artifact distribution", {"scripts/build/build_pages.sh": pages_build.replace('cp "$T1/THIRD_PARTY_LICENSES.md" "$OUT/THIRD_PARTY_LICENSES.md"', "# removed third-party inventory", 1)}, "Pages artifact does not distribute required license file"),
        ("runbook distribution", {"scripts/build/build_pages.sh": pages_build.replace('cp "$T1/scripts/compliance/docs/sbom_generation.md" "$OUT/scripts/compliance/docs/sbom_generation.md"', "# removed SBOM runbook", 1)}, "Pages artifact does not distribute required license file"),
        ("argparse explanation", {INVENTORY: document.replace("`argparse@2.0.1` is a JavaScript npm package used transitively by `js-yaml@5.2.2`.", "argparse is unexplained.", 1)}, "missing license-scope explanation"),
        ("acquisition procedure", {INVENTORY: document.replace("## Reproducing license-evidence acquisition", "## Undocumented acquisition", 1)}, "missing license-scope explanation"),
        ("SBOM runbook", {RUNBOOK: runbook.replace("# SBOM generation and attachment runbook", "# Missing runbook contract", 1)}, "missing SBOM acquisition instruction"),
        ("reviewer CSV export", {COMPLIANCE_SKILL: compliance_skill.replace('"id": "swipat-component-table"', '"id": "removed-export"', 1)}, "missing parameterized SWIPAT component export"),
        ("reviewer CSV preview", {COMPLIANCE_SKILL: compliance_skill.replace('id="third-party-export-preview"', 'id="removed-preview"', 1)}, "SWIPAT in-page preview control is missing"),
        ("multi-select preview", {COMPLIANCE_SKILL: compliance_skill.replace("data-export-license-group", "data-export-license-single", 1)}, "SWIPAT in-page preview control is missing"),
        ("column sort preview", {CSV_PREVIEW: read(CSV_PREVIEW, {}).replace("sortableHeaders", "removedSortableHeaders")}, "SWIPAT preview implementation is incomplete"),
        ("legal-scope export", {COMPLIANCE_SKILL: compliance_skill.replace('"id": "legal-scope-map"', '"id": "removed-scope"', 1)}, "missing legal-scope relationship export"),
        ("legal-scope multi-select", {COMPLIANCE_SKILL: compliance_skill.replace('<div class="filter-choice-group" data-scope-relationship-group>', '<div class="filter-choice-group" data-scope-relationship-single>', 1)}, "SWIPAT in-page preview control is missing"),
        ("document-source preview", {CSV_PREVIEW: read(CSV_PREVIEW, {}).replace("documentScopeRows", "removedScopeDocuments")}, "SWIPAT preview implementation is incomplete"),
        ("wrapped commands", {COMPLIANCE_SKILL: compliance_skill.replace("white-space:pre-wrap", "white-space:nowrap", 1)}, "SWIPAT in-page preview control is missing"),
        ("filter semantics", {COMPLIANCE_SKILL: compliance_skill.replace("You can choose several options in one filter", "filters combine somehow", 1)}, "SWIPAT in-page preview control is missing"),
        ("plain-language filter labels", {CSV_PREVIEW: read(CSV_PREVIEW, {}).replace("Included in the course", "vendored technical label", 1)}, "SWIPAT preview implementation is incomplete"),
        ("misclassified document roll-up", {CSV_PREVIEW: read(CSV_PREVIEW, {}).replace("External document citation record", "Referenced, not copied", 1)}, "legal-scope export delegates or misstates distribution"),
        ("delegated document distribution", {SCOPE_EXPORTER: read(SCOPE_EXPORTER, {}).replace('distribution = f"Yes - copied or converted into {copied} repository item(s)"', 'distribution = "See related repository-item rows"', 1)}, "legal-scope export delegates or misstates distribution"),
        ("outsider-first software review", {CSV_PREVIEW: read(CSV_PREVIEW, {}).replace('Learners receive these " + record.sbom.component_count + " packages', "Distributed payload", 1)}, "SWIPAT preview implementation is incomplete"),
        ("build-centric software review", {CSV_PREVIEW: read(CSV_PREVIEW, {}).replace("Every browser package has", "Every link was read through the GitLab job-artifact API. Every browser package has", 1)}, "reviewer-facing software copy exposes build-centric status language"),
        ("plain-language export explanation", {CSV_EXPORTER: read(CSV_EXPORTER, {}).replace("Learners receive this code as part of the browser course.", "Vendored package.", 1)}, "reviewer export lacks plain-language usage explanation"),
    )
    failures = []
    for label, overrides, expected in mutations:
        observed = audit(overrides)
        if not any(expected in finding for finding in observed):
            failures.append(f"mutation escaped: {label}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        print("third-party inventory self-test: " + ("FAIL" if failures else "PASS"))
        for failure in failures:
            print(f"  {failure}")
        return 1 if failures else 0
    findings = audit()
    if findings:
        print(f"third-party inventory audit: FAIL ({len(findings)})")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print("third-party inventory audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
