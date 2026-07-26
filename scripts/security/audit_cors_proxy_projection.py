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
SOURCE_SUFFIXES = {".js", ".mjs", ".sh", ".tf"}
SPDX = "SPDX-License-Identifier: Apache-2.0"
IGNORE_NAME = ".gitignore"
GENERATED_DIRECTORIES = {"build", "deployment-state", "node_modules"}
GENERATED_NAMES = {".DS_Store", "operator-values.json", "operator-parameters.json"}
EXPECTED_IGNORE_ENTRIES = {
    *(f"{name}/" for name in GENERATED_DIRECTORIES),
    *GENERATED_NAMES,
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def requires_spdx(path: Path) -> bool:
    return (
        path.suffix in SOURCE_SUFFIXES
        or path.name.endswith(".tfvars.example")
        or path.name.endswith(".hcl.example")
    )


def ignore_contract_findings(root: Path = PROJECTION) -> list[str]:
    """Require the reviewed output exclusions exactly.

    Manifest membership never follows arbitrary ignore patterns. This fixed contract lets local
    packaging output coexist with the source audit without giving a file an opt-in bypass.
    """
    findings: list[str] = []
    path = root / IGNORE_NAME
    if not path.is_file():
        return [f"{IGNORE_NAME}: missing reviewed generated-output contract"]
    entries = {
        raw.strip()
        for raw in path.read_text(encoding="utf-8").splitlines()
        if raw.strip() and not raw.strip().startswith("#")
    }
    if entries != EXPECTED_IGNORE_ENTRIES:
        findings.append(
            f"{IGNORE_NAME}: entries must exactly match reviewed generated-output paths"
        )
    return findings


def is_generated(relative: str) -> bool:
    segments = relative.split("/")
    if len(segments) > 1 and segments[0] in GENERATED_DIRECTORIES:
        return True
    leaf = segments[-1]
    return leaf == ".DS_Store" or relative in GENERATED_NAMES


def projected_files(root: Path = PROJECTION) -> dict[str, Path]:
    """Discover every file under the projection automatically, with no registration step."""
    rows: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows[relative] = path
        elif path.is_file() and relative != MANIFEST_NAME:
            rows[relative] = path
    return rows


def generated_paths(root: Path = PROJECTION, files: dict[str, Path] | None = None) -> set[str]:
    """Return fixed build, packaging, and operator-local output paths."""
    return {
        relative for relative in (files if files is not None else projected_files(root))
        if is_generated(relative)
    }


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
    if re.search(r"(?i)\b(?:account[_ -]?id|aws[_ -]?account)\b[\"']?\s*[:=]\s*[\"']?\d{12}\b", text):
        findings.append(f"{relative}: cloud account identifier")
    if re.search(r"\bZ[A-Z0-9]{10,32}\b", text):
        findings.append(f"{relative}: hosted-zone identifier")
    if re.search(r"\b[a-z0-9-]+\.cloudfront\.net\b", text, re.I):
        findings.append(f"{relative}: generated distribution hostname")
    if re.search(r"\b[a-z0-9-]+\.lambda-url\.[a-z0-9-]+\.on\.aws\b", text, re.I):
        findings.append(f"{relative}: generated function hostname")
    if private_source in lowered:
        findings.append(f"{relative}: private source location")
    if deployed_suffix in lowered:
        findings.append(f"{relative}: operated relay hostname")
    if re.search(
        r"(?i)\b(?:backend_bucket|state_bucket|artifact_bucket|bucket)\b[\"']?\s*[:=]\s*"
        r"[\"'][a-z0-9][a-z0-9.-]{2,62}[\"']",
        text,
    ):
        findings.append(f"{relative}: concrete object-store bucket")
    if re.search(
        r"\b(?:af|ap|ca|eu|il|me|mx|sa|us)-(?:gov-)?[a-z]+-\d\b",
        text,
        re.I,
    ):
        findings.append(f"{relative}: concrete cloud region")
    return findings


def audit(root: Path = PROJECTION) -> list[str]:
    failures: list[str] = []
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return [f"{MANIFEST_NAME}: missing projection manifest"]
    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = json.loads(manifest_text)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{MANIFEST_NAME}: unreadable projection manifest: {exc}"]
    if manifest.get("schema") != SCHEMA:
        failures.append(f"{MANIFEST_NAME}: unsupported schema")
    if manifest.get("license") != "Apache-2.0":
        failures.append(f"{MANIFEST_NAME}: projection license must be Apache-2.0")
    failures.extend(environment_identifier_findings(MANIFEST_NAME, manifest_text))
    revisions = manifest.get("source_revisions")
    if (
        not isinstance(revisions, list) or not revisions
        or any(not re.fullmatch(r"[0-9a-f]{40}", str(item)) for item in revisions)
    ):
        failures.append(f"{MANIFEST_NAME}: source revisions must be full commit IDs")
    transformations = manifest.get("projection_transformations")
    if not isinstance(transformations, list) or len(transformations) < 4:
        failures.append(f"{MANIFEST_NAME}: public projection transformations are incomplete")
    elif not (
        any("Terraform" in str(item) and "operator-supplied" in str(item) for item in transformations)
        and any("edge shared secret" in str(item) for item in transformations)
    ):
        failures.append(f"{MANIFEST_NAME}: required projection corrections are not recorded")
    if manifest.get("source_location") != "retained in the authorized release record":
        failures.append(f"{MANIFEST_NAME}: source location must remain public-safe")
    if "source_url" in manifest or "repository" in manifest:
        failures.append(f"{MANIFEST_NAME}: source location belongs in the authorized release record")

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

    failures.extend(ignore_contract_findings(root))
    files = projected_files(root)
    generated = generated_paths(root, files)
    symlinks = [relative for relative, path in files.items() if path.is_symlink()]
    failures.extend(f"{relative}: symlinks are not allowed" for relative in symlinks)
    actual = set(files)
    # Build and operator-local output is never committed, so it is not projected source. It is
    # still scanned below; only manifest membership treats it as outside the projection.
    missing = sorted(actual - set(recorded) - generated)
    stale = sorted(set(recorded) - actual)
    failures.extend(f"{MANIFEST_NAME}: unrecorded file {relative}" for relative in missing)
    failures.extend(f"{MANIFEST_NAME}: missing recorded file {relative}" for relative in stale)

    for relative, path in files.items():
        if path.is_symlink():
            continue
        projected = relative not in generated
        if projected and recorded.get(relative) != digest(path):
            failures.append(f"{relative}: SHA-256 differs from projection manifest")
        if projected and (
            path.name in {"backend.hcl", "local.tfvars"} or path.suffix in {".tfstate", ".zip"}
        ):
            failures.append(f"{relative}: local or generated deployment state is committed")
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # A packaged archive under an ignored build path is expected to be binary.
            # Projected source is not.
            if projected:
                failures.append(f"{relative}: unexpected binary file")
            continue
        if projected and requires_spdx(path) and SPDX not in text:
            failures.append(f"{relative}: missing Apache-2.0 SPDX header")
        # Content scanning covers build output too: an ignore entry must not become a
        # channel for committing environment-specific values.
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
            "LogRetentionDays",
            "CloudFrontPriceClass",
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

    terraform_paths = [
        "infrastructure/terraform.tf",
        "infrastructure/variables.tf",
        "infrastructure/main.tf",
        "infrastructure/outputs.tf",
    ]
    for relative in terraform_paths:
        if relative not in files:
            failures.append(f"{relative}: required Terraform source is missing")
    if all(relative in files and not files[relative].is_symlink() for relative in terraform_paths):
        terraform_text = "\n".join(
            files[relative].read_text(encoding="utf-8") for relative in terraform_paths
        )
        required_terraform_contracts = (
            (r'backend\s+"s3"\s*\{\s*\}', "operator-configured backend", 1),
            (r'provider\s+"aws"\s*\{[^}]*\bregion\s*=\s*var\.aws_region', "operator-supplied region", 1),
            (r'resource\s+"aws_lambda_function"\s+"model"', "model Lambda", 1),
            (r'resource\s+"aws_lambda_function"\s+"runtime"', "runtime Lambda", 1),
            (r'resource\s+"aws_cloudfront_distribution"\s+"model"', "model CloudFront distribution", 1),
            (r'resource\s+"aws_cloudfront_distribution"\s+"runtime"', "runtime CloudFront distribution", 1),
            (r'\binvoke_mode\s*=\s*"RESPONSE_STREAM"', "response streaming", 2),
            (r'\bname\s*=\s*"x-dli-cors-proxy-secret"', "direct-origin shared header", 2),
            (r'\bpath_pattern\s*=\s*"/https/\*/cli/gateway"', "gateway WebSocket route", 1),
            (r'\bpath_pattern\s*=\s*"/https/\*/ws/terminal"', "terminal WebSocket route", 1),
        )
        for pattern, label, expected_count in required_terraform_contracts:
            if len(re.findall(pattern, terraform_text, re.S)) != expected_count:
                failures.append(f"infrastructure Terraform: missing or duplicate {label}")

        variable_matches = list(re.finditer(r'variable\s+"([^"]+)"\s*\{', terraform_text))
        variable_bodies: dict[str, str] = {}
        for index, match in enumerate(variable_matches):
            end = (
                variable_matches[index + 1].start()
                if index + 1 < len(variable_matches)
                else len(terraform_text)
            )
            variable_bodies[match.group(1)] = terraform_text[match.end():end]
        for name in (
            "aws_region",
            "project_prefix",
            "lambda_artifact_bucket",
            "lambda_artifact_key",
            "model_relay_shared_secret",
            "runtime_relay_shared_secret",
            "cache_policy_id",
            "origin_request_policy_id",
            "log_retention_days",
            "cloudfront_price_class",
            "model_dns_names",
            "runtime_dns_names",
            "model_acm_certificate_arn",
            "runtime_acm_certificate_arn",
            "resource_tags",
        ):
            body = variable_bodies.get(name)
            if body is None or re.search(r"\bdefault\s*=", body):
                failures.append(
                    f"infrastructure Terraform: {name} must be operator-supplied"
                )
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
    ignore_findings = ignore_contract_findings(root)
    if ignore_findings:
        raise ValueError(ignore_findings[0])
    generated = generated_paths(root, files)
    manifest["files"] = {
        relative: digest(path)
        for relative, path in files.items()
        if relative not in generated
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
