#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve every CycloneDX component to a reviewed package/version SPDX expression.

The scanner-original SBOM remains separate evidence. This script creates the canonical review
SBOM consumed by the license UI, retaining the original scanner values as component properties
and binding the result to both the raw SBOM and the checked inventory by SHA-256.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

import render_sbom_license_inventory as license_inventory


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "THIRD_PARTY_LICENSES.md"
SOURCE_PROPERTY = "nemoclaw:license-resolution:source"
ORIGINAL_PROPERTY = "nemoclaw:license-resolution:scanner-original"


def normalized(name: object) -> str:
    return re.sub(r"[-_.]+", "-", str(name)).casefold()


def scanner_values(component: dict) -> list[str]:
    identifiers, names = license_inventory.component_licenses(component)
    return identifiers + [name for name in names if name not in identifiers]


def set_property(properties: list[dict], name: str, value: str) -> None:
    properties[:] = [item for item in properties if item.get("name") != name]
    properties.append({"name": name, "value": value})


def resolve_document(
    document: dict,
    inventory_text: str,
    raw_sha256: str,
    *,
    accept_scanner_spdx: bool = False,
    package_components_only: bool = False,
) -> tuple[dict, list[str]]:
    if document.get("bomFormat") != "CycloneDX" or not isinstance(document.get("components"), list):
        raise ValueError("SBOM must be CycloneDX JSON with a components array")
    reviewed = license_inventory.static_licenses(inventory_text)
    output = copy.deepcopy(document)
    excluded = 0
    if package_components_only:
        retained = [component for component in output["components"] if isinstance(component, dict) and component.get("purl")]
        excluded = len(output["components"]) - len(retained)
        output["components"] = retained
    findings: list[str] = []
    normalizations = 0
    for component in output["components"]:
        if not isinstance(component, dict):
            findings.append("SBOM component is not an object")
            continue
        name = str(component.get("name") or "")
        version = str(component.get("version") or "")
        expression = reviewed.get((normalized(name), version))
        identifiers, _names = license_inventory.component_licenses(component)
        if not name or not version:
            findings.append(f"component lacks exact name/version: {name or '<unnamed>'}@{version or '<unversioned>'}")
            continue
        source = "checked exact package/version inventory row"
        scanner_accepted = False
        if not expression and accept_scanner_spdx and identifiers:
            scanner_accepted = True
            source = "scanner-provided SPDX identifier or expression"
        if not expression and not scanner_accepted:
            findings.append(f"no reviewed SPDX expression for {name}@{version}")
            continue
        original = scanner_values(component)
        if expression and original and expression not in original:
            normalizations += 1
        if expression:
            component["licenses"] = [{"expression": expression}]
        properties = component.setdefault("properties", [])
        if not isinstance(properties, list):
            properties = component["properties"] = []
        set_property(properties, SOURCE_PROPERTY, source)
        set_property(properties, ORIGINAL_PROPERTY, json.dumps(original, ensure_ascii=False, separators=(",", ":")))

    metadata = output.setdefault("metadata", {})
    properties = metadata.setdefault("properties", [])
    if not isinstance(properties, list):
        properties = metadata["properties"] = []
    set_property(properties, "nemoclaw:license-resolution:raw-sbom-sha256", raw_sha256)
    set_property(
        properties,
        "nemoclaw:license-resolution:inventory-sha256",
        hashlib.sha256(inventory_text.encode("utf-8")).hexdigest(),
    )
    set_property(properties, "nemoclaw:license-resolution:component-count", str(len(output["components"])))
    set_property(properties, "nemoclaw:license-resolution:excluded-non-package-components", str(excluded))
    set_property(properties, "nemoclaw:license-resolution:scanner-normalization-count", str(normalizations))
    return output, findings


def resolve_file(
    source: Path,
    destination: Path,
    inventory: Path,
    *,
    accept_scanner_spdx: bool = False,
    package_components_only: bool = False,
) -> tuple[int, list[str]]:
    raw = source.read_bytes()
    inventory_text = inventory.read_text(encoding="utf-8")
    document = json.loads(raw)
    output, findings = resolve_document(
        document,
        inventory_text,
        hashlib.sha256(raw).hexdigest(),
        accept_scanner_spdx=accept_scanner_spdx,
        package_components_only=package_components_only,
    )
    if findings:
        return 0, findings
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return len(output["components"]), []


def self_test() -> list[str]:
    failures: list[str] = []
    inventory = (
        "| Scope | Package | Version | SPDX license | Evidence |\n"
        "|---|---|---|---|---|\n"
        "| validation | demo-pkg | 1.0 | MIT | fixture |\n"
    )
    raw = {
        "bomFormat": "CycloneDX", "specVersion": "1.6", "metadata": {},
        "components": [{
            "name": "demo_pkg", "version": "1.0",
            "licenses": [{"license": {"name": "MIT License"}}],
        }],
    }
    resolved, findings = resolve_document(raw, inventory, "a" * 64)
    component = resolved["components"][0]
    if findings or component.get("licenses") != [{"expression": "MIT"}]:
        failures.append("exact package/version license was not resolved")
    props = {item["name"]: item["value"] for item in component.get("properties", [])}
    if props.get(ORIGINAL_PROPERTY) != '["MIT License"]':
        failures.append("scanner-original license evidence was not retained")
    changed = copy.deepcopy(raw)
    changed["components"][0]["version"] = "2.0"
    if not resolve_document(changed, inventory, "a" * 64)[1]:
        failures.append("unreviewed package/version mutation escaped")
    scanner_only = copy.deepcopy(changed)
    scanner_only["components"][0]["licenses"] = [{"license": {"id": "Apache-2.0"}}]
    resolved_scanner, findings = resolve_document(
        scanner_only, inventory, "a" * 64, accept_scanner_spdx=True
    )
    if findings or resolved_scanner["components"][0]["licenses"] != [{"license": {"id": "Apache-2.0"}}]:
        failures.append("explicit scanner SPDX fallback was not resolved")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument(
        "--accept-scanner-spdx",
        action="store_true",
        help="accept one scanner-provided SPDX identifier/expression when no reviewed row exists",
    )
    parser.add_argument(
        "--package-components-only",
        action="store_true",
        help="exclude non-package metadata components without a package URL from the review inventory",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        print("SBOM license resolver self-test: " + ("FAIL" if failures else "PASS"))
        for failure in failures:
            print(f"  {failure}")
        return 1 if failures else 0
    if not args.input or not args.output:
        parser.error("--input and --output are required")
    try:
        count, findings = resolve_file(
            args.input,
            args.output,
            args.inventory,
            accept_scanner_spdx=args.accept_scanner_spdx,
            package_components_only=args.package_components_only,
        )
    except (ValueError, json.JSONDecodeError, OSError) as error:
        parser.error(str(error))
    if findings:
        print(f"SBOM license resolution: FAIL ({len(findings)})")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(f"SBOM license resolution: PASS ({count} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
