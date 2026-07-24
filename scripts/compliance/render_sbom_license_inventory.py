#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Render a static component-license appendix from a CycloneDX JSON SBOM."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATIC_INVENTORY = ROOT / "THIRD_PARTY_LICENSES.md"
IMMUTABLE_ARTIFACT = re.compile(r"^.+@sha256:[0-9a-f]{64}$")


def escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def static_licenses(markdown: str) -> dict[tuple[str, str], str]:
    """Read exact package/version licenses from the static npm and Python tables."""
    found: dict[tuple[str, str], str] = {}
    for line in markdown.splitlines():
        if not line.startswith("| "):
            continue
        columns = [value.strip() for value in line.strip("|").split("|")]
        if len(columns) < 4 or columns[0] in {"Scope", "---"}:
            continue
        name, version, license_value = columns[1:4]
        if name and version and license_value and license_value != "NOASSERTION":
            found[(re.sub(r"[-_.]+", "-", name).casefold(), version)] = license_value
    return found


def component_licenses(component: dict) -> tuple[list[str], list[str]]:
    identifiers: list[str] = []
    names: list[str] = []
    for item in component.get("licenses") or []:
        if not isinstance(item, dict):
            continue
        expression = item.get("expression")
        license_data = item.get("license") or {}
        identifier = license_data.get("id") if isinstance(license_data, dict) else None
        name = license_data.get("name") if isinstance(license_data, dict) else None
        if expression and str(expression) not in identifiers:
            identifiers.append(str(expression))
        if identifier and str(identifier) not in identifiers:
            identifiers.append(str(identifier))
        if name and str(name) not in names:
            names.append(str(name))
    return identifiers, names


def render(sbom_path: Path, artifact_id: str, inventory_path: Path) -> tuple[str, int]:
    if not IMMUTABLE_ARTIFACT.fullmatch(artifact_id):
        raise ValueError("artifact ID must end with @sha256:<64 lowercase hex characters>")
    raw = sbom_path.read_bytes()
    document = json.loads(raw)
    if document.get("bomFormat") != "CycloneDX" or not isinstance(document.get("components"), list):
        raise ValueError("SBOM must be CycloneDX JSON with a components array")
    fallback = static_licenses(inventory_path.read_text(encoding="utf-8"))
    rows: list[tuple[str, str, str, str, str]] = []
    unresolved = 0
    for component in document["components"]:
        if not isinstance(component, dict):
            continue
        name = str(component.get("name") or "<unnamed>")
        version = str(component.get("version") or "<unversioned>")
        purl = str(component.get("purl") or component.get("bom-ref") or "")
        identifiers, names = component_licenses(component)
        key = (re.sub(r"[-_.]+", "-", name).casefold(), version)
        fallback_value = fallback.get(key)
        if identifiers:
            license_value = "; ".join(identifiers)
            source = "CycloneDX SPDX identifier/expression"
            if names:
                source += "; named metadata also present: " + "; ".join(names)
        elif fallback_value:
            license_value = fallback_value
            source = "exact package/version static SPDX fallback"
            if names:
                source += "; SBOM named: " + "; ".join(names)
        elif names:
            license_value = "; ".join(names)
            source = "CycloneDX named license; SPDX mapping required"
            unresolved += 1
        else:
            license_value = "MISSING SPDX EVIDENCE"
            source = "resolution required before export"
            unresolved += 1
        rows.append((name, version, license_value, source, purl))
    rows.sort(key=lambda row: (row[0].casefold(), row[1], row[4]))
    lines = [
        f"# Scanned component license inventory: {artifact_id}",
        "",
        f"- Artifact: `{artifact_id}`",
        f"- CycloneDX SBOM SHA-256: `{hashlib.sha256(raw).hexdigest()}`",
        f"- Components: {len(rows)}",
        f"- Unresolved license rows: {unresolved}",
        "",
        "Scanner-provided SPDX identifiers and expressions take precedence. When the SBOM has only "
        "a license name or omits license metadata, an exact package/version SPDX fallback comes "
        "from `THIRD_PARTY_LICENSES.md`. The export fails if any package/version lacks reviewed SPDX evidence.",
        "",
        "| Component | Version | License identifier or expression | Evidence | PURL / BOM reference |",
        "|---|---|---|---|---|",
    ]
    lines.extend("| " + " | ".join(escape(value) for value in row) + " |" for row in rows)
    return "\n".join(lines) + "\n", unresolved


def self_test() -> list[str]:
    tests: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="sbom-license-inventory-") as directory:
        root = Path(directory)
        inventory = root / "THIRD_PARTY_LICENSES.md"
        inventory.write_text(
            "| Scope | Package | Version | SPDX license | Evidence |\n"
            "|---|---|---|---|---|\n"
            "| runtime | fallback_pkg | 2.0 | BSD-3-Clause | fixture |\n",
            encoding="utf-8",
        )
        sbom = root / "fixture.cdx.json"
        sbom.write_text(json.dumps({
            "bomFormat": "CycloneDX",
            "components": [
                {"name": "scanner", "version": "1.0", "purl": "pkg:pypi/scanner@1.0",
                 "licenses": [{"license": {"id": "MIT"}}]},
                {"name": "fallback-pkg", "version": "2.0", "bom-ref": "fallback==2.0",
                 "licenses": [{"license": {"name": "BSD License"}}]},
                {"name": "unknown", "version": "3.0", "bom-ref": "unknown==3.0"},
            ],
        }), encoding="utf-8")
        artifact = "fixture@example@sha256:" + "a" * 64
        rendered, unresolved = render(sbom, artifact, inventory)
        tests.extend((
            ("scanner license retained", "| scanner | 1.0 | MIT | CycloneDX SPDX identifier/expression |" in rendered),
            ("named metadata gets static SPDX fallback", "| fallback-pkg | 2.0 | BSD-3-Clause | exact package/version static SPDX fallback; SBOM named: BSD License |" in rendered),
            ("unresolved is explicit", "| unknown | 3.0 | MISSING SPDX EVIDENCE | resolution required before export |" in rendered and unresolved == 1),
        ))
        try:
            render(sbom, "mutable:latest", inventory)
            tests.append(("mutable identity rejected", False))
        except ValueError:
            tests.append(("mutable identity rejected", True))
    failures = [name for name, passed in tests if not passed]
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sbom", type=Path)
    parser.add_argument("--artifact-id")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--inventory", type=Path, default=STATIC_INVENTORY)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        print("SBOM license inventory self-test: " + ("FAIL" if failures else "PASS"))
        for failure in failures:
            print(f"  {failure}")
        return 1 if failures else 0
    if not args.sbom or not args.artifact_id or not args.out:
        parser.error("--sbom, --artifact-id, and --out are required")
    rendered, unresolved = render(args.sbom, args.artifact_id, args.inventory)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.out}: unresolved={unresolved}")
    return 0 if unresolved == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
