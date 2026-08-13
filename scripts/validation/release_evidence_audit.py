#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate the public product design, release test plan, and evidence ownership map."""
from __future__ import annotations

import argparse
import copy
import json
import re
import shlex
import sys
from pathlib import Path

for _path in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_path / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_path / "scripts"))
        break
from _bootstrap import add_script_paths, find_repo_root  # noqa: E402

ROOT = find_repo_root(Path(__file__).resolve())
add_script_paths(ROOT / "scripts")
import prose_variety as pv  # noqa: E402

CONTRACT = ROOT / "docs" / "release-evidence.json"
SOURCE_INVENTORY = ROOT / "scripts" / "compliance" / "docs" / "source_inventory.json"

REQUIRED_DOCUMENTS = {
    "design", "test_plan", "security_design", "security_control_disposition",
    "security_control_themes", "security_architecture", "release_artifacts", "publication_state",
}
REQUIRED_RELEASE_ARTIFACTS = {
    "versioned-static-archive", "release-manifest", "cyclonedx-sbom", "sha256-checksums",
}
REQUIRED_AREAS = {
    "registration-context", "repository-baseline", "source-and-licenses", "privacy-and-data",
    "cryptography-and-export", "secret-scanning", "vulnerability-scanning", "malware-scanning",
    "architecture-and-deployment", "release-artifacts", "release-approval",
    "threat-control-disposition", "content-publication-integrity",
}
REQUIRED_EXTERNAL_CATEGORIES = {
    "registration", "public-repository-hosting", "legal-and-license", "export", "privacy",
    "verified-secret-scan", "final-artifact-vulnerability-scan", "malware-scan", "host-controls",
    "source-integration", "external-service-controls", "release-decision",
    "ai-content-transparency",
}
REQUIRED_HEADINGS = {
    "design": {
        "Purpose and users", "Release scope", "Deployment model", "Component design",
        "Data, credentials, and privacy", "Cryptography and integrity",
        "Third-party sources and licenses", "Security and reliability controls",
        "Release, versioning, and rollback", "Traceability",
    },
    "test_plan": {
        "Scope", "Roles and evidence ownership", "Entry criteria", "Test environments",
        "Automated test matrix", "Manual and external evidence matrix", "Execution order",
        "Pass, failure, and exception rules", "Exit criteria", "Evidence record",
    },
    "security_control_disposition": {
        "Status vocabulary", "Review synthesis", "Source and contribution controls", "Build and artifact controls",
        "Static hosting and browser controls", "Relay, model, launchable, and runtime controls",
        "Publication blockers and retained risks",
    },
}
REQUIRED_DESIGN_ANCHORS = {
    "static browser application", "localStorage", "personal or sensitive", "Embedded media",
    "access cookies", "no repository-operated database", "HTTPS and WSS", "browser dependency inventory",
    "SHA-256", "new patch tag", "The Type I subject is only the DLI course repository",
    "product, launchable, runtime, relays", "outside this classification",
}
REQUIRED_AUTOMATED_IDS = {f"A{index:02d}" for index in range(1, 13)}
REQUIRED_MANUAL_IDS = {f"M{index:02d}" for index in range(1, 12)}
REQUIRED_WIRING = {
    ".gitlab/ci/core.yml": ("release_gate.py --tier ship",),
    ".github/workflows/pages.yml": (
        "release_gate.py --tier ship", "BUILD_PAGES_PUBLICATION_MODE: public",
    ),
    ".github/workflows/release.yml": (
        "release_gate.py --tier ship", "BUILD_PAGES_PUBLICATION_MODE: public",
    ),
    "scripts/git-hooks/pre-commit": ("release_evidence_audit.py",),
    "scripts/git-hooks/pre-push": (
        "release_gate.py", "--tier ship --no-write --changed-since origin/main --reuse-success",
    ),
    "scripts/validation/validate_bundle.py": ("import release_evidence_audit as rea", '"release_evidence"'),
    "scripts/validation/publication_integrity_audit.py": (
        "release-owner-required", "substantive-human-review-and-editorial-control",
        "external-authoritative-system", "page-unclassified", "media-origin",
    ),
    "scripts/validation/release_gate.py": (
        "scripts/build/project_docs_explorer.py", '"--audit"',
        "scripts/validation/course_dependency_integrity.py",
        "scripts/validation/cell_audit.py",
        'unit_test("release_evidence_audit")',
        'unit_test("threat_control_audit")',
        "HARNESS_CONTRACT", "test_test_harness_contract", "STANDARD_TEST_DISCOVERY",
    ),
    "AGENTS.md": (
        "CONTRIBUTING.md", "docs/release-test-plan.md",
    ),
    "CONTRIBUTING.md": (
        "release_gate.py --tier fast --no-write", "release_gate.py --tier ship",
    ),
    "docs/agent_process.md": ("release_evidence_audit.py", "unittest discover -v -s tests/validation"),
    "docs/SKILL.html": (
        "product-design.md", "release-test-plan.md", "release-evidence.json",
        "security-control-disposition.md", "security-control-themes.json",
        '"../RELEASE_STATUS.json"', '"../CHANGELOG.md"', '"render_markdown": true',
    ),
    "web/_skill_explorer.js": (
        "safeMarkdownHtml", "new URLSearchParams(location.search", 'params.get("file")',
        'params.get("view")', "writeFileUrl", 'addEventListener("popstate"',
        "sx-heading-link",
    ),
    "scripts/build/build_pages.sh": (
        "project_source_tree.py",
        "--artifact-root",
        "project_docs_explorer.py",
        "-path 'web/nemoclaw/standalone' -prune",
        "project_publication_metadata.py",
        "publication_integrity_audit.py",
        "BUILD_PAGES_PUBLICATION_MODE",
    ),
    "scripts/build/project_docs_explorer.py": (
        "local_markdown_targets", "missing or unsafe", "--self-test",
    ),
    "scripts/build/SKILL.html": (
        "project_docs_explorer.py", "Docs catalog + projection",
        "vendor_browser_dependencies.mjs", "Browser package inventory",
    ),
    "scripts/validation/course_dependency_integrity.py": (
        "same-origin-vendored", "source-reference inventory drifted", "--self-test",
    ),
    "scripts/validation/SKILL.html": ("release_evidence_audit.py",),
    "scripts/validation/threat_control_audit.py": (
        "pages_artifact_integrity.py", "repository_sync_audit.py", "Not verified",
    ),
}
ALLOWED_OWNERS = {"repository", "operator", "shared"}
ALLOWED_EXTERNAL_STATUS = "operator-required"
PROSE_GRAMMAR_BLOCK = {
    "weak-opener", "question-as-statement", "expletive", "wordy-phrase", "run-on",
    "filler-word", "tack-on", "and-then-chain", "bare-and-chain", "stub-split",
}
PROSE_CADENCE_BLOCK = {
    "parallel-copula", "numeric-antithesis", "repeated-count-list", "one-word-punch",
    "same-X-reversal", "not-X-it-is-Y", "triad-semicolons", "welded-clauses",
    "negate-parallel", "repeated-pivot", "what-looks-like", "stub-assertion",
    "meta-emphasis", "not-X-but-Y",
}


def finding(code: str, path: str, detail: str, fix: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail, "fix": fix}


def load_contract(path: Path = CONTRACT) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def private_link_patterns(path: Path = SOURCE_INVENTORY) -> list[tuple[str, re.Pattern[str]]]:
    inventory = json.loads(path.read_text(encoding="utf-8"))
    return [
        (str(row["name"]), re.compile(str(row["pattern"]), re.I))
        for row in inventory.get("forbidden_private_link_regexes", [])
    ]


def headings(text: str) -> set[str]:
    return {match.group(1).strip() for match in re.finditer(r"^##\s+(.+?)\s*$", text, re.M)}


def command_path(command: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    for token in tokens:
        token = token.rstrip(";")
        if token.startswith(("scripts/", "tests/")):
            return token
    return None


def text_for(path: str, root: Path, overrides: dict[str, str]) -> str:
    if path in overrides:
        return overrides[path]
    return (root / path).read_text(encoding="utf-8")


def audit_contract(data: dict, *, root: Path = ROOT,
                   text_overrides: dict[str, str] | None = None) -> list[dict[str, str]]:
    overrides = text_overrides or {}
    out: list[dict[str, str]] = []
    if data.get("schema") != "nemoclaw-release-evidence/1":
        out.append(finding("schema", "docs/release-evidence.json", "unexpected schema",
                           "restore nemoclaw-release-evidence/1"))

    documents = data.get("documents")
    if not isinstance(documents, dict):
        return out + [finding("documents", "docs/release-evidence.json", "documents must be an object",
                              "restore the required document map")]
    for key in sorted(REQUIRED_DOCUMENTS - set(documents)):
        out.append(finding("document-key", "docs/release-evidence.json", f"missing document key {key}",
                           "add the public evidence path"))
    for key, rel in documents.items():
        if not isinstance(rel, str) or not rel or not (root / rel).is_file():
            out.append(finding("path-missing", "docs/release-evidence.json",
                               f"{key} path does not resolve: {rel}", "restore the referenced file"))

    artifacts = set(data.get("release_artifacts") or [])
    for name in sorted(REQUIRED_RELEASE_ARTIFACTS - artifacts):
        out.append(finding("release-artifact", "docs/release-evidence.json",
                           f"release artifact omitted: {name}", "restore the deterministic artifact contract"))

    scope = data.get("product_scope") or {}
    if scope.get("production_runtime") != "static-browser-course":
        out.append(finding("product-runtime", "docs/release-evidence.json",
                           "production runtime must remain static-browser-course",
                           "restore the static browser course production scope"))
    for key in ("canonical_source", "locale_overlays"):
        values = scope.get(key)
        values = [values] if isinstance(values, str) else values or []
        for rel in values:
            if not (root / rel).exists():
                out.append(finding("scope-path", "docs/release-evidence.json",
                                   f"{key} path does not resolve: {rel}", "repair the product scope path"))
    if set(scope.get("hosting_paths") or []) != {"public-static-host", "co-located-launchable"}:
        out.append(finding("hosting-paths", "docs/release-evidence.json",
                           "hosting paths must cover public static and co-located launchable delivery",
                           "restore both supported delivery paths"))

    areas = data.get("evidence_areas") or []
    ids = [row.get("id") for row in areas if isinstance(row, dict)]
    if len(ids) != len(set(ids)):
        out.append(finding("area-duplicate", "docs/release-evidence.json", "evidence area IDs repeat",
                           "keep one authoritative row per area"))
    for area in sorted(REQUIRED_AREAS - set(ids)):
        out.append(finding("area-missing", "docs/release-evidence.json",
                           f"required evidence area omitted: {area}", "restore its ownership and tests"))
    for row in areas:
        if not isinstance(row, dict):
            out.append(finding("area-shape", "docs/release-evidence.json", "evidence area is not an object",
                               "restore id, owner, commands, and external evidence"))
            continue
        area = str(row.get("id", "<missing>"))
        if row.get("owner") not in ALLOWED_OWNERS:
            out.append(finding("area-owner", "docs/release-evidence.json",
                               f"{area} has invalid owner {row.get('owner')}", "use repository, operator, or shared"))
        if row.get("external_evidence") != ALLOWED_EXTERNAL_STATUS:
            out.append(finding("external-status", "docs/release-evidence.json",
                               f"{area} claims unsupported external status {row.get('external_evidence')}",
                               "use operator-required; repository files cannot grant approval"))
        commands = row.get("automated_commands")
        if not isinstance(commands, list) or not commands:
            out.append(finding("commands", "docs/release-evidence.json", f"{area} has no automated command",
                               "name the earliest deterministic repository check"))
            continue
        for command in commands:
            rel = command_path(str(command))
            if not rel or not (root / rel).is_file():
                out.append(finding("command-path", "docs/release-evidence.json",
                                   f"{area} command does not resolve: {command}",
                                   "use a real repository entrypoint"))

    policy = data.get("external_evidence_policy") or {}
    categories = set(policy.get("required_categories") or [])
    for category in sorted(REQUIRED_EXTERNAL_CATEGORIES - categories):
        out.append(finding("external-category", "docs/release-evidence.json",
                           f"external evidence category omitted: {category}",
                           "restore the operator-owned evidence category"))
    if policy.get("retention") != "authorized-system-only" or policy.get("repository_claim") != "not-approved-by-repository":
        out.append(finding("external-boundary", "docs/release-evidence.json",
                           "external evidence retention or repository approval boundary changed",
                           "keep private evidence external and prevent self-approval claims"))

    public_paths = [
        documents.get("design"), documents.get("test_plan"),
        documents.get("security_control_disposition"), "docs/release-evidence.json",
    ]
    for rel in filter(None, public_paths):
        if rel != "docs/release-evidence.json" and not (root / rel).is_file() and rel not in overrides:
            continue
        text = json.dumps(data, indent=2) if rel == "docs/release-evidence.json" else text_for(rel, root, overrides)
        for name, pattern in private_link_patterns():
            if pattern.search(text):
                out.append(finding("internal-metadata", rel, f"contains {name}",
                                   "keep ticket and approval-system details outside the repository"))

    for key, required in REQUIRED_HEADINGS.items():
        rel = documents.get(key)
        if not rel or (not (root / rel).is_file() and rel not in overrides):
            continue
        text = text_for(rel, root, overrides)
        for heading in sorted(required - headings(text)):
            out.append(finding("heading-missing", rel, f"missing section: {heading}",
                               "restore the reviewable design or test-plan section"))
        chunks = pv.narrative(root / rel) if rel not in overrides else [p.strip() for p in text.split("\n\n") if p.strip() and not p.lstrip().startswith(("#", "|", "-"))]
        for kind, sentence in pv.grammar_hits(chunks):
            if kind in PROSE_GRAMMAR_BLOCK:
                out.append(finding("prose", rel, f"{kind}: {sentence[:180]}",
                                   "rewrite the sentence using the course prose standard"))
        for kind, sentence in pv.antithesis_hits(chunks):
            if kind in PROSE_CADENCE_BLOCK:
                out.append(finding("prose", rel, f"{kind}: {sentence[:180]}",
                                   "remove the slogan-like or mirrored construction"))

    design_path = documents.get("design")
    test_path = documents.get("test_plan")
    if design_path and (root / design_path).is_file():
        design = text_for(design_path, root, overrides)
        if "release-test-plan.md" not in design or "RELEASE_STATUS.json" not in design:
            out.append(finding("design-links", design_path,
                               "design must link the test plan and publication state",
                               "restore both traceability links"))
        for anchor in sorted(REQUIRED_DESIGN_ANCHORS):
            if anchor not in design:
                out.append(finding("design-anchor", design_path, f"missing design evidence: {anchor}",
                                   "restore the concrete product, data, cryptography, or rollback statement"))
    if test_path and (root / test_path).is_file():
        plan = text_for(test_path, root, overrides)
        if "product-design.md" not in plan or "release-evidence.json" not in plan:
            out.append(finding("test-links", test_path,
                               "test plan must link the design and evidence map",
                               "restore both traceability links"))
        test_ids = set(re.findall(r"\|\s*([AM]\d{2})\s*\|", plan))
        for test_id in sorted((REQUIRED_AUTOMATED_IDS | REQUIRED_MANUAL_IDS) - test_ids):
            out.append(finding("test-id", test_path, f"missing release test {test_id}",
                               "restore the test, pass condition, evidence, and owner"))
        for anchor in (
            "| M10a | Generated threat-analysis reconciliation |",
            "public repository contains no private row-by-row assessment",
        ):
            if anchor not in plan:
                out.append(finding(
                    "threat-reconciliation",
                    test_path,
                    f"missing generated-review evidence boundary: {anchor}",
                    "restore aggregate public reconciliation and private row-level ownership",
                ))
    for rel, tokens in REQUIRED_WIRING.items():
        if not (root / rel).is_file():
            out.append(finding("wiring-path", rel, "required release-evidence surface is missing",
                               "restore the CI, hook, beacon, or contributor surface"))
            continue
        text = text_for(rel, root, overrides)
        for token in tokens:
            if token not in text:
                out.append(finding("wiring", rel, f"missing release-evidence token: {token}",
                                   "wire the validator into the required feedback and authority layer"))
    return out


def self_test() -> list[str]:
    base = load_contract()
    baseline = audit_contract(base)
    if baseline:
        return [f"baseline is not clean: {item['code']} {item['detail']}" for item in baseline]
    tests: list[tuple[str, dict, dict[str, str], str]] = []

    def mutated() -> dict:
        return copy.deepcopy(base)

    value = mutated(); value["evidence_areas"] = [row for row in value["evidence_areas"] if row["id"] != "privacy-and-data"]
    tests.append(("missing area", value, {}, "area-missing"))
    value = mutated(); value["evidence_areas"][0]["external_evidence"] = "complete"
    tests.append(("false approval", value, {}, "external-status"))
    value = mutated(); value["evidence_areas"][0]["automated_commands"] = ["python3 scripts/validation/missing.py"]
    tests.append(("bad command", value, {}, "command-path"))
    value = mutated(); value["documents"]["design"] = "docs/missing.md"
    tests.append(("missing document", value, {}, "path-missing"))
    design_path = base["documents"]["design"]
    design_text = (ROOT / design_path).read_text(encoding="utf-8")
    private_sample = "http://" + "nv/" + "private-review"
    tests.append(("internal metadata", mutated(), {design_path: design_text + f"\n{private_sample}\n"}, "internal-metadata"))
    tests.append(("missing heading", mutated(), {design_path: design_text.replace("## Purpose and users", "## Users")}, "heading-missing"))
    value = mutated(); value["release_artifacts"].remove("cyclonedx-sbom")
    tests.append(("missing artifact", value, {}, "release-artifact"))
    value = mutated(); value["evidence_areas"].append(copy.deepcopy(value["evidence_areas"][0]))
    tests.append(("duplicate area", value, {}, "area-duplicate"))
    value = mutated(); value["product_scope"]["production_runtime"] = "server-application"
    tests.append(("runtime drift", value, {}, "product-runtime"))
    test_path = base["documents"]["test_plan"]
    test_text = (ROOT / test_path).read_text(encoding="utf-8")
    tests.append(("broken crosslink", mutated(), {test_path: test_text.replace("product-design.md", "design.md")}, "test-links"))
    ci_path = ".gitlab/ci/core.yml"
    ci_text = (ROOT / ci_path).read_text(encoding="utf-8")
    tests.append(("missing CI wiring", mutated(),
                  {ci_path: ci_text.replace("release_gate.py --tier ship", "release gate removed")},
                  "wiring"))
    tests.append(("missing test case", mutated(), {test_path: test_text.replace("| M09 |", "| MXX |")},
                  "test-id"))
    tests.append(("missing threat reconciliation", mutated(),
                  {test_path: test_text.replace("| M10a | Generated threat-analysis reconciliation |",
                                               "| M10a | Generated review removed |")},
                  "threat-reconciliation"))
    explorer_path = "web/_skill_explorer.js"
    explorer_text = (ROOT / explorer_path).read_text(encoding="utf-8")
    tests.append(("missing document URL state", mutated(),
                  {explorer_path: explorer_text.replace('params.get("file")', 'params.get("removed")')},
                  "wiring"))
    build_path = "scripts/build/build_pages.sh"
    build_text = (ROOT / build_path).read_text(encoding="utf-8")
    tests.append(("missing explorer artifact check", mutated(),
                  {build_path: build_text.replace("project_docs_explorer.py",
                                                 "explorer projection check removed")},
                  "wiring"))
    tests.append(("missing exhaustive source projection", mutated(),
                  {build_path: build_text.replace("project_source_tree.py",
                                                 "source projection removed")},
                  "wiring"))
    skill_path = "docs/SKILL.html"
    skill_text = (ROOT / skill_path).read_text(encoding="utf-8")
    tests.append(("missing publication projection", mutated(),
                  {skill_path: skill_text.replace('"../RELEASE_STATUS.json"', '"../release-state-removed.json"')},
                  "wiring"))
    projection_path = "scripts/build/project_docs_explorer.py"
    projection_text = (ROOT / projection_path).read_text(encoding="utf-8")
    tests.append(("missing Markdown target detector", mutated(),
                  {projection_path: projection_text.replace("local_markdown_targets", "removed_target_detector")},
                  "wiring"))
    gate_path = "scripts/validation/release_gate.py"
    gate_text = (ROOT / gate_path).read_text(encoding="utf-8")
    tests.append(("missing browser dependency CI", mutated(),
                  {gate_path: gate_text.replace("course_dependency_integrity.py", "browser dependency gate removed")},
                  "wiring"))

    failures: list[str] = []
    for name, fixture, overrides, expected in tests:
        codes = {item["code"] for item in audit_contract(fixture, text_overrides=overrides)}
        if expected not in codes:
            failures.append(f"{name}: expected {expected}, got {sorted(codes)}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        if failures:
            print("release_evidence_audit self-test: FAIL")
            for item in failures:
                print(f"  FAIL {item}")
            return 1
        print("release_evidence_audit self-test: PASS")
        return 0
    try:
        rows = audit_contract(load_contract())
    except (OSError, json.JSONDecodeError) as exc:
        rows = [finding("contract-read", "docs/release-evidence.json", str(exc),
                        "restore valid machine-readable release evidence")]
    if args.json:
        print(json.dumps({"schema": "nemoclaw-release-evidence-audit/1", "findings": rows}, indent=2))
    else:
        print(f"release_evidence_audit: {len(rows)} finding(s)")
        for item in rows:
            print(f"  [{item['code']}] {item['path']}: {item['detail']}")
            print(f"    fix: {item['fix']}")
    return 1 if rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
