#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Check Python material-tool SBOM completeness and reject runtime components."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def locked_names(path: Path) -> set[str]:
    names: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==", line.strip())
        if match:
            names.add(norm(match.group(1)))
    return names


def forbidden_names() -> set[str]:
    from audit_python_dependencies import FORBIDDEN_DIRECT_REQUIREMENTS
    return {norm(name) for name in FORBIDDEN_DIRECT_REQUIREMENTS}


def audit_document(document: dict, expected: set[str], forbidden: set[str]) -> dict:
    components = document.get("components") or []
    actual = {norm(str(component.get("name", ""))) for component in components if component.get("name")}
    prohibited = sorted(actual & forbidden)
    missing = sorted(expected - actual)
    license_counts = {"spdx": 0, "named": 0, "missing": 0}
    missing_license: list[str] = []
    for component in components:
        licenses = component.get("licenses") or []
        if not licenses:
            license_counts["missing"] += 1
            missing_license.append(norm(str(component.get("name", ""))))
        elif any(
            ((item.get("license") or {}).get("id") or item.get("expression")) not in {None, "", "NOASSERTION"}
            for item in licenses
        ):
            license_counts["spdx"] += 1
        else:
            license_counts["named"] += 1
            missing_license.append(norm(str(component.get("name", ""))))
    findings = []
    if prohibited:
        findings.append({"code": "retired-component", "packages": prohibited,
                         "fix": "remove the component or document new runtime need and source/license approval"})
    if missing:
        findings.append({"code": "incomplete-sbom", "packages": missing,
                         "fix": "generate the SBOM from scripts/materials/requirements.lock"})
    if missing_license:
        findings.append({
            "code": "unresolved-license",
            "packages": sorted(set(missing_license)),
            "fix": "resolve every exact package/version to SPDX before publishing or rendering the SBOM",
        })
    return {
        "schema": "nemoclaw-sbom-policy/1",
        "ok": not findings,
        "component_count": len(actual),
        "license_metadata": license_counts,
        "missing_license_components": sorted(set(missing_license)),
        "findings": findings,
    }


def self_test() -> list[str]:
    failures: list[str] = []
    clean = {"components": [{"name": "requests", "licenses": [{"license": {"id": "Apache-2.0"}}]}]}
    if not audit_document(clean, {"requests"}, {"jupyter-archive"})["ok"]:
        failures.append("clean fixture rejected")
    retired = {"components": [{"name": "jupyter_archive", "licenses": []}]}
    codes = {item["code"] for item in audit_document(retired, set(), {"jupyter-archive"})["findings"]}
    if "retired-component" not in codes:
        failures.append("retired component mutation escaped")
    codes = {item["code"] for item in audit_document({"components": []}, {"requests"}, set())["findings"]}
    if "incomplete-sbom" not in codes:
        failures.append("incomplete SBOM mutation escaped")
    codes = {item["code"] for item in audit_document(
        {"components": [{"name": "requests", "licenses": []}]}, {"requests"}, set()
    )["findings"]}
    if "unresolved-license" not in codes:
        failures.append("unresolved license mutation escaped")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sbom", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        if failures:
            print("SBOM policy self-test: FAIL")
            for failure in failures:
                print(f"  {failure}")
            return 1
        print("SBOM policy self-test: PASS")
        return 0
    if not args.sbom:
        parser.error("--sbom is required unless --self-test is used")
    result = audit_document(
        json.loads(args.sbom.read_text(encoding="utf-8")),
        locked_names(ROOT / "scripts/materials/requirements.lock"),
        forbidden_names(),
    )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    counts = result["license_metadata"]
    print(f"SBOM policy: {'PASS' if result['ok'] else 'FAIL'}; {result['component_count']} components; "
          f"license metadata SPDX={counts['spdx']} named={counts['named']} missing={counts['missing']}")
    print("License metadata summary is inventory evidence, not license approval; downstream policy remains required.")
    for finding in result["findings"]:
        print(f"  {finding['code']}: {', '.join(finding['packages'])}")
        print(f"    fix: {finding['fix']}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
