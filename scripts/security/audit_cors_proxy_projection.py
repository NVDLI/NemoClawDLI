#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Verify the complete, history-free CORS relay source projection."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTION = ROOT / "scripts" / "cors-proxy" / "deployable"
MANIFEST_NAME = "PROJECTION.json"
SCHEMA = "source-projection/1"
SOURCE_SUFFIXES = {".js", ".mjs", ".sh"}
SPDX = "SPDX-License-Identifier: Apache-2.0"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def projected_files(root: Path = PROJECTION) -> dict[str, Path]:
    rows: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows[relative] = path
        elif path.is_file() and relative != MANIFEST_NAME:
            rows[relative] = path
    return rows


def environment_identifier_findings(relative: str, text: str) -> list[str]:
    findings: list[str] = []
    lowered = text.lower()
    literal_s3 = "s3" + "://"
    private_source = "gitlab" + ".com/nvidia/dli/platform/"
    deployed_suffix = ".experiments" + ".courses.nvidia.com"
    if re.search(rf"{literal_s3}(?![<$%{{])[-a-z0-9.]+", text, re.I):
        findings.append(f"{relative}: concrete object-store bucket")
    if re.search(r"\barn:aws(?:-us-gov|-cn)?:[^:\s]*:[^:\s]*:\d{12}:", text, re.I):
        findings.append(f"{relative}: cloud account identifier")
    if re.search(r"\bZ[A-Z0-9]{10,32}\b", text):
        findings.append(f"{relative}: hosted-zone identifier")
    if re.search(r"\b[a-z0-9-]+\.cloudfront\.net\b", text, re.I):
        findings.append(f"{relative}: generated distribution hostname")
    if private_source in lowered:
        findings.append(f"{relative}: private source location")
    if deployed_suffix in lowered:
        findings.append(f"{relative}: operated relay hostname")
    if re.search(r"(?i)\b(?:hashi" + r"corp|registry\.terra" + r"form\.io)\b", text):
        findings.append(f"{relative}: disallowed provisioning-vendor reference")
    if re.search(r"(?i)\bMPL-(?:1\.1|2\.0)\b", text):
        findings.append(f"{relative}: disallowed reciprocal-license dependency")
    return findings


def audit(root: Path = PROJECTION) -> list[str]:
    failures: list[str] = []
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return [f"{MANIFEST_NAME}: missing projection manifest"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{MANIFEST_NAME}: unreadable projection manifest: {exc}"]
    if manifest.get("schema") != SCHEMA:
        failures.append(f"{MANIFEST_NAME}: unsupported schema")
    if manifest.get("license") != "Apache-2.0":
        failures.append(f"{MANIFEST_NAME}: projection license must be Apache-2.0")
    revisions = manifest.get("source_revisions")
    if (
        not isinstance(revisions, list) or not revisions
        or any(not re.fullmatch(r"[0-9a-f]{40}", str(item)) for item in revisions)
    ):
        failures.append(f"{MANIFEST_NAME}: source revisions must be full commit IDs")
    transformations = manifest.get("projection_transformations")
    if not isinstance(transformations, list) or len(transformations) < 4:
        failures.append(f"{MANIFEST_NAME}: public projection transformations are incomplete")
    if "source_url" in manifest or "repository" in manifest:
        failures.append(f"{MANIFEST_NAME}: source location belongs in the authorized release record")

    files = projected_files(root)
    symlinks = [relative for relative, path in files.items() if path.is_symlink()]
    failures.extend(f"{relative}: symlinks are not allowed" for relative in symlinks)
    actual = set(files)
    recorded = manifest.get("files")
    if not isinstance(recorded, dict):
        failures.append(f"{MANIFEST_NAME}: files must be a path-to-SHA-256 object")
        recorded = {}
    else:
        invalid = [
            relative for relative, value in recorded.items()
            if not isinstance(relative, str) or not re.fullmatch(r"[0-9a-f]{64}", str(value))
        ]
        failures.extend(f"{MANIFEST_NAME}: invalid file record {relative}" for relative in invalid)
    missing = sorted(actual - set(recorded))
    stale = sorted(set(recorded) - actual)
    failures.extend(f"{MANIFEST_NAME}: unrecorded file {relative}" for relative in missing)
    failures.extend(f"{MANIFEST_NAME}: missing recorded file {relative}" for relative in stale)

    for relative, path in files.items():
        if path.is_symlink():
            continue
        if recorded.get(relative) != digest(path):
            failures.append(f"{relative}: SHA-256 differs from projection manifest")
        if path.name in {"backend.hcl", "local.tfvars"} or path.suffix in {".tfstate", ".zip"}:
            failures.append(f"{relative}: local or generated deployment state is committed")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"{relative}: unexpected binary file")
            continue
        if path.suffix in SOURCE_SUFFIXES and SPDX not in text:
            failures.append(f"{relative}: missing Apache-2.0 SPDX header")
        failures.extend(environment_identifier_findings(relative, text))

    package_path = root / "package.json"
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"package.json: unreadable: {exc}")
    else:
        if package.get("license") != "Apache-2.0":
            failures.append("package.json: license must be Apache-2.0")
        if package.get("dependencies") or package.get("devDependencies"):
            failures.append("package.json: deployable runtime must remain dependency-free")

    template_path = root / "infrastructure" / "template.json"
    try:
        template = json.loads(template_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"infrastructure/template.json: unreadable: {exc}")
    else:
        if template.get("Metadata", {}).get("License") != "Apache-2.0":
            failures.append("infrastructure/template.json: license must be Apache-2.0")
        parameters = template.get("Parameters", {})
        for name in (
            "ProjectPrefix",
            "LambdaArtifactBucket",
            "LambdaArtifactKey",
            "ModelRelaySharedSecret",
            "RuntimeRelaySharedSecret",
            "CachePolicyId",
            "OriginRequestPolicyId",
        ):
            if not isinstance(parameters.get(name), dict) or "Default" in parameters[name]:
                failures.append(f"infrastructure/template.json: {name} must be operator-supplied")
        code = (
            template.get("Resources", {})
            .get("RuntimeWebSocketRequest", {})
            .get("Properties", {})
            .get("FunctionCode")
        )
        if code != "__OPENCLAW_WEBSOCKET_FUNCTION_CODE__":
            failures.append("infrastructure/template.json: WebSocket source marker is missing")
    return failures


def refresh_manifest(root: Path = PROJECTION) -> None:
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    revisions = manifest.get("source_revisions")
    if (
        manifest.get("schema") != SCHEMA
        or manifest.get("license") != "Apache-2.0"
        or not isinstance(revisions, list)
        or not revisions
        or any(not re.fullmatch(r"[0-9a-f]{40}", str(item)) for item in revisions)
        or not isinstance(manifest.get("projection_transformations"), list)
        or len(manifest["projection_transformations"]) < 4
    ):
        raise ValueError("review projection metadata before refreshing file hashes")
    files = projected_files(root)
    if any(path.is_symlink() for path in files.values()):
        raise ValueError("projection contains a symlink")
    manifest["files"] = {
        relative: digest(path)
        for relative, path in files.items()
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECTION)
    parser.add_argument(
        "--refresh-manifest",
        action="store_true",
        help="recompute file hashes while preserving reviewed source revisions",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    if args.refresh_manifest:
        try:
            refresh_manifest(root)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"CORS proxy projection manifest refresh: FAIL: {exc}")
            return 1
        print("CORS proxy projection manifest refresh: OK")
    failures = audit(root)
    if failures:
        print(f"CORS proxy projection audit: FAIL ({len(failures)})")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("CORS proxy projection audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
