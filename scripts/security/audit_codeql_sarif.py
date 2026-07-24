#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fail on authored CodeQL findings and unreviewed or drifted vendor findings."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = Path("scripts/security/codeql-vendor-dispositions.json")
POLICY_SCHEMA = "codeql-vendor-dispositions/1"
VENDOR_PREFIXES = ("web/nemoclaw/vendor/", "web/shared/vendor/")
REQUIRED_FIELDS = {
    "fingerprints",
    "artifact",
    "artifact_sha256",
    "component",
    "version",
    "decision",
    "owner",
    "expires",
    "evidence",
    "scope",
}
ALLOWED_DECISIONS = {
    "not-exploitable-in-delivered-use",
    "accepted-upstream-risk",
}
AUTHORED_REQUIRED_FIELDS = {
    "fingerprints",
    "artifact",
    "artifact_sha256",
    "decision",
    "owner",
    "expires",
    "controls",
    "scope",
}
AUTHORED_DECISIONS = {
    "explicit-user-tab-credential-boundary",
    "inert-parse-allowlist-reconstruction",
    "opaque-origin-sandbox-execution",
}


def _canonical_location(result: dict[str, Any]) -> dict[str, Any]:
    locations = result.get("locations")
    if not isinstance(locations, list) or not locations or not isinstance(locations[0], dict):
        return {}
    physical = locations[0].get("physicalLocation")
    if not isinstance(physical, dict):
        return {}
    artifact = physical.get("artifactLocation")
    region = physical.get("region")
    if not isinstance(artifact, dict) or not isinstance(region, dict):
        return {}
    uri = artifact.get("uri")
    if not isinstance(uri, str) or not uri.strip():
        return {}
    return {
        "uri": uri.replace("\\", "/").lstrip("./"),
        "startLine": region.get("startLine"),
        "startColumn": region.get("startColumn"),
        "endLine": region.get("endLine"),
        "endColumn": region.get("endColumn"),
    }


def result_fingerprint(result: dict[str, Any]) -> str:
    """Return an identity stable across CodeQL upload and download processing."""
    partial = result.get("partialFingerprints")
    if not isinstance(partial, dict):
        partial = {}
    location = _canonical_location(result)
    identity = {
        "rule": result.get("ruleId"),
        "artifact": location.get("uri"),
        "startLine": location.get("startLine"),
        "startColumn": location.get("startColumn"),
        "primaryLocationLineHash": partial.get("primaryLocationLineHash"),
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_json(path: Path, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, [f"missing {label}: {path}"]
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"invalid {label} {path}: {exc}"]
    if not isinstance(value, dict):
        return None, [f"{label} root must be an object: {path}"]
    return value, []


def _validate_policy(
    root: Path,
    policy: dict[str, Any],
    *,
    today: dt.date,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    findings: list[str] = []
    if policy.get("schema") != POLICY_SCHEMA:
        findings.append(f"policy schema must be {POLICY_SCHEMA}")
    dispositions = policy.get("artifacts")
    if not isinstance(dispositions, list):
        return {}, findings + ["policy artifacts must be a list"]

    indexed: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(dispositions):
        label = f"artifacts[{index}]"
        if not isinstance(item, dict):
            findings.append(f"{label} must be an object")
            continue
        missing = sorted(REQUIRED_FIELDS - set(item))
        unknown = sorted(set(item) - REQUIRED_FIELDS)
        if missing:
            findings.append(f"{label} missing fields: {', '.join(missing)}")
        if unknown:
            findings.append(f"{label} has unknown fields: {', '.join(unknown)}")

        fingerprints = item.get("fingerprints")
        if not isinstance(fingerprints, list) or not fingerprints:
            findings.append(f"{label} fingerprints must be a non-empty list")
        else:
            for fingerprint in fingerprints:
                if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                    findings.append(f"{label} fingerprint must be lowercase SHA-256")
                elif fingerprint in indexed:
                    findings.append(f"{label} has duplicate fingerprint")
                else:
                    indexed[fingerprint] = item

        artifact = str(item.get("artifact", "")).replace("\\", "/").lstrip("./")
        if not artifact.startswith(VENDOR_PREFIXES):
            findings.append(f"{label} artifact is not a vendored artifact")
        artifact_path = root / artifact
        if not artifact_path.is_file():
            findings.append(f"{label} artifact does not exist")
        else:
            digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            if digest != item.get("artifact_sha256"):
                findings.append(f"{label} artifact digest differs from reviewed bytes")

        if item.get("decision") not in ALLOWED_DECISIONS:
            findings.append(f"{label} decision is unsupported")
        for field in ("component", "version", "owner", "scope"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                findings.append(f"{label} {field} must be a non-empty string")

        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            findings.append(f"{label} evidence must be a non-empty list")
        else:
            for evidence_path in evidence:
                if not isinstance(evidence_path, str) or not (root / evidence_path).is_file():
                    findings.append(f"{label} evidence path does not exist: {evidence_path}")

        try:
            expires = dt.date.fromisoformat(str(item.get("expires", "")))
        except ValueError:
            findings.append(f"{label} expires must be YYYY-MM-DD")
        else:
            if expires < today:
                findings.append(f"{label} disposition expired on {expires.isoformat()}")
    authored = policy.get("authored_controls", [])
    if not isinstance(authored, list):
        return indexed, findings + ["policy authored_controls must be a list"]
    for index, item in enumerate(authored):
        label = f"authored_controls[{index}]"
        if not isinstance(item, dict):
            findings.append(f"{label} must be an object")
            continue
        missing = sorted(AUTHORED_REQUIRED_FIELDS - set(item))
        unknown = sorted(set(item) - AUTHORED_REQUIRED_FIELDS)
        if missing:
            findings.append(f"{label} missing fields: {', '.join(missing)}")
        if unknown:
            findings.append(f"{label} has unknown fields: {', '.join(unknown)}")

        fingerprints = item.get("fingerprints")
        if not isinstance(fingerprints, list) or not fingerprints:
            findings.append(f"{label} fingerprints must be a non-empty list")
        else:
            for fingerprint in fingerprints:
                if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
                    findings.append(f"{label} fingerprint must be lowercase SHA-256")
                elif fingerprint in indexed:
                    findings.append(f"{label} has duplicate fingerprint")
                else:
                    indexed[fingerprint] = item

        artifact = str(item.get("artifact", "")).replace("\\", "/").lstrip("./")
        if artifact.startswith(VENDOR_PREFIXES):
            findings.append(f"{label} must not classify vendor code as authored")
        artifact_path = root / artifact
        if not artifact_path.is_file():
            findings.append(f"{label} artifact does not exist")
        else:
            digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            if digest != item.get("artifact_sha256"):
                findings.append(f"{label} artifact digest differs from reviewed bytes")

        if item.get("decision") not in AUTHORED_DECISIONS:
            findings.append(f"{label} decision is not an approved reviewed-boundary class")
        for field in ("owner", "scope"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                findings.append(f"{label} {field} must be a non-empty string")
        controls = item.get("controls")
        if not isinstance(controls, list) or not controls:
            findings.append(f"{label} controls must be a non-empty list")
        else:
            has_executable_control = False
            for control in controls:
                if not isinstance(control, dict) or set(control) != {"path", "contains"}:
                    findings.append(f"{label} controls require exact path and contains fields")
                    continue
                control_path = str(control.get("path", ""))
                token = str(control.get("contains", ""))
                path = root / control_path
                if not path.is_file() or not token or token not in path.read_text(encoding="utf-8"):
                    findings.append(f"{label} control evidence is missing its exact token: {control_path}")
                if control_path.startswith(("tests/", "scripts/validation/")):
                    has_executable_control = True
            if not has_executable_control:
                findings.append(f"{label} requires an executable validation control")
        try:
            expires = dt.date.fromisoformat(str(item.get("expires", "")))
        except ValueError:
            findings.append(f"{label} expires must be YYYY-MM-DD")
        else:
            if expires < today:
                findings.append(f"{label} disposition expired on {expires.isoformat()}")
    return indexed, findings


def _sarif_results(document: dict[str, Any], label: str) -> tuple[list[dict[str, Any]], list[str]]:
    runs = document.get("runs")
    if document.get("version") != "2.1.0" or not isinstance(runs, list):
        return [], [f"{label} is not valid SARIF 2.1.0"]
    results: list[dict[str, Any]] = []
    findings: list[str] = []
    for run_index, run in enumerate(runs):
        if not isinstance(run, dict):
            findings.append(f"{label} run {run_index} must be an object")
            continue
        run_results = run.get("results", [])
        if not isinstance(run_results, list):
            findings.append(f"{label} run {run_index} results must be a list")
            continue
        for result in run_results:
            if not isinstance(result, dict) or not result.get("ruleId") or not _canonical_location(result):
                findings.append(f"{label} contains a result without a rule or physical location")
                continue
            partial = result.get("partialFingerprints")
            if (
                not isinstance(partial, dict)
                or not isinstance(partial.get("primaryLocationLineHash"), str)
                or not partial["primaryLocationLineHash"].strip()
            ):
                findings.append(
                    f"{label} contains a result without CodeQL primaryLocationLineHash",
                )
                continue
            results.append(result)
    return results, findings


def audit(
    root: Path,
    policy: dict[str, Any],
    sarif_documents: Iterable[dict[str, Any]],
    *,
    today: dt.date,
) -> list[str]:
    indexed, findings = _validate_policy(root, policy, today=today)
    for document_index, document in enumerate(sarif_documents):
        results, sarif_findings = _sarif_results(document, f"SARIF document {document_index}")
        findings.extend(sarif_findings)
        for result in results:
            location = _canonical_location(result)
            artifact = location["uri"]
            fingerprint = result_fingerprint(result)
            disposition = indexed.get(fingerprint)
            is_vendor = artifact.startswith(VENDOR_PREFIXES)
            if disposition is None:
                category = "unreviewed vendor finding" if is_vendor else "authored finding must be fixed"
                findings.append(
                    f"{category}: {result.get('ruleId')} at {artifact}:{location.get('startLine')}",
                )
                continue
            if disposition.get("artifact") != artifact:
                findings.append(
                    f"disposition does not match SARIF artifact for fingerprint {fingerprint}",
                )
    return findings


def _sarif_paths(values: Iterable[str]) -> tuple[list[Path], list[str]]:
    paths: list[Path] = []
    findings: list[str] = []
    for value in values:
        candidate = Path(value)
        if candidate.is_dir():
            paths.extend(sorted(candidate.rglob("*.sarif")))
        elif candidate.is_file():
            paths.append(candidate)
        else:
            findings.append(f"SARIF input does not exist: {candidate}")
    if values and not paths:
        findings.append("no SARIF files were discovered")
    return paths, findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", default=str(DEFAULT_POLICY), help="repository-relative policy JSON")
    parser.add_argument("--sarif", action="append", default=[], help="SARIF file or directory; repeatable")
    parser.add_argument("--today", help="override current date for deterministic tests")
    args = parser.parse_args()

    policy_path = ROOT / args.policy
    policy, findings = _load_json(policy_path, "CodeQL vendor disposition policy")
    sarif_paths, path_findings = _sarif_paths(args.sarif)
    findings.extend(path_findings)
    documents: list[dict[str, Any]] = []
    for path in sarif_paths:
        document, load_findings = _load_json(path, "SARIF")
        findings.extend(load_findings)
        if document is not None:
            documents.append(document)
    if policy is not None:
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
        findings.extend(audit(ROOT, policy, documents, today=today))

    if findings:
        print("CodeQL SARIF policy: FAIL", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("CodeQL SARIF policy: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
