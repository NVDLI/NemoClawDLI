#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build and verify immutable links between SBOMs, license appendices, and inventory scope."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import render_sbom_license_inventory as license_inventory


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CATALOG = ROOT / "scripts/compliance/docs/sbom_evidence.json"
INVENTORY = ROOT / "THIRD_PARTY_LICENSES.md"
COMMIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
ALLOWED_STATES = {"available", "ci-generated"}
ALLOWED_DISTRIBUTION = {"distributed", "not-distributed"}
CI_LINK_SCHEMA = "nemoclaw-ci-evidence-links/1"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def active_publication_policy() -> object | None:
    """Load the public policy plus any additive private publication policy."""
    from scripts.validation.sensitive_content_audit import load_policy

    return load_policy()


def publication_safe_text(value: str, policy: object | None) -> bool:
    """Return whether generated text is safe for the current publication boundary."""
    if policy is None:
        return True
    from scripts.validation.sensitive_content_audit import scan_text

    return not scan_text("generated-ci-evidence", value, policy)


def set_publication_field(
    output: dict, key: str, value: str, policy: object | None,
) -> bool:
    """Set optional generated metadata only when the publication policy accepts it."""
    if not value or not publication_safe_text(value, policy):
        return False
    output[key] = value
    return True


def copy_publication_evidence(
    source: Path, destination: Path, policy: object | None,
) -> bool:
    """Copy evidence only when its complete bytes pass the active publication policy."""
    destination.unlink(missing_ok=True)
    try:
        text = source.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return False
    if not publication_safe_text(text, policy):
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def license_summary(components: list[dict]) -> dict[str, int]:
    summary = {"spdx": 0, "named": 0, "missing": 0}
    for component in components:
        licenses = component.get("licenses") or []
        if not licenses:
            summary["missing"] += 1
        elif any(
            ((item.get("license") or {}).get("id") or item.get("expression")) not in {None, "", "NOASSERTION"}
            for item in licenses
        ):
            summary["spdx"] += 1
        else:
            summary["named"] += 1
    return summary


def load_sbom(path: Path) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("bomFormat") != "CycloneDX" or not isinstance(document.get("components"), list):
        raise ValueError("SBOM must be CycloneDX JSON with a components array")
    return document


def resolve_catalog_path(href: str) -> Path:
    path = (CATALOG.parent / href).resolve()
    if ROOT.resolve() not in path.parents:
        raise ValueError(f"SBOM href escapes the repository: {href}")
    return path


def is_external_href(href: str) -> bool:
    return urllib.parse.urlparse(href).scheme in {"http", "https"}


def href_finding(label: str, field: str, href: object, *, require_local_file: bool = False) -> str | None:
    if not isinstance(href, str) or not href.strip():
        return f"{label}: {field} is missing"
    parsed = urllib.parse.urlparse(href)
    if parsed.scheme:
        if parsed.scheme != "https" or not parsed.netloc:
            return f"{label}: {field} must be an absolute HTTPS URL"
        return None
    if href.startswith(("#", "/")) or "<" in href or ">" in href:
        return f"{label}: {field} is not a usable repository-relative link"
    if require_local_file:
        try:
            path = resolve_catalog_path(href)
        except ValueError as error:
            return f"{label}: {error}"
        if not path.is_file():
            return f"{label}: {field} points to a missing repository file: {href}"
    return None


def external_hrefs(document: dict) -> list[str]:
    values: set[str] = set()
    for record in document.get("records", []):
        for subject in record.get("subjects", []):
            for field in ("upstream_href", "license_hint_href"):
                href = subject.get(field)
                if isinstance(href, str) and is_external_href(href):
                    values.add(href)
    return sorted(values)


def check_external_links(document: dict, attempts: int = 3, timeout: float = 20.0) -> list[str]:
    """Read one byte from each authoritative external link and report terminal failures."""
    findings: list[str] = []
    for href in external_hrefs(document):
        last_error = "unknown error"
        for attempt in range(1, attempts + 1):
            request = urllib.request.Request(
                href,
                headers={
                    "Range": "bytes=0-0",
                    "User-Agent": "NemoClawDLI-license-evidence-check/1.0",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    if 200 <= response.status < 400:
                        last_error = ""
                        break
                    last_error = f"HTTP {response.status}"
            except urllib.error.HTTPError as error:
                last_error = f"HTTP {error.code}"
                if 400 <= error.code < 500 and error.code not in {408, 429}:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = str(getattr(error, "reason", error))
            if attempt < attempts:
                time.sleep(attempt)
        if last_error:
            findings.append(f"dead or unreachable evidence link: {href} ({last_error})")
    return findings


def audit_catalog(document: dict | None = None) -> list[str]:
    """Check the committed catalog against its linked files and inventory boundary."""
    findings: list[str] = []
    data = document if document is not None else json.loads(CATALOG.read_text(encoding="utf-8"))
    if data.get("schema") != "nemoclaw-sbom-evidence/1":
        findings.append("unexpected SBOM evidence schema")
    records = data.get("records")
    if not isinstance(records, list) or not records:
        return findings + ["SBOM evidence records must be a non-empty list"]
    ids = [record.get("id") for record in records if isinstance(record, dict)]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        findings.append("SBOM evidence record IDs must be present and unique")

    for record in records:
        if not isinstance(record, dict):
            findings.append("SBOM evidence record is not an object")
            continue
        label = record.get("id", "<missing>")
        if record.get("state") not in ALLOWED_STATES:
            findings.append(f"{label}: unsupported evidence state")
        if record.get("distribution") not in ALLOWED_DISTRIBUTION:
            findings.append(f"{label}: unsupported distribution state")
        if not record.get("selectors"):
            findings.append(f"{label}: no inventory selectors")

        if record.get("state") == "available":
            sbom = record.get("sbom") or {}
            href = sbom.get("href")
            try:
                path = resolve_catalog_path(href) if href else None
            except ValueError as error:
                findings.append(f"{label}: {error}")
                path = None

            if not path or not path.is_file():
                findings.append(f"{label}: linked SBOM is missing")
                continue
            try:
                source = load_sbom(path)
            except (ValueError, json.JSONDecodeError) as error:
                findings.append(f"{label}: invalid linked SBOM: {error}")
                continue

            expected = {
                "sha256": digest(path),
                "bytes": path.stat().st_size,
                "component_count": len(source["components"]),
                "license_metadata": license_summary(source["components"]),
            }
            for key, value in expected.items():
                if sbom.get(key) != value:
                    findings.append(f"{label}: linked SBOM {key} is stale")
        elif record.get("state") == "ci-generated":
            ci = record.get("ci") or {}
            for key in ("job", "raw_sbom_artifact_path", "sbom_artifact_path", "manifest_artifact_path", "appendix_artifact_path", "retention_days"):
                if not ci.get(key):
                    findings.append(f"{label}: CI evidence location lacks {key}")
            for index, link in enumerate(record.get("evidence_links", []), start=1):
                if not isinstance(link, dict) or not link.get("label"):
                    findings.append(f"{label}: evidence link {index} lacks a label")
                    continue
                finding = href_finding(label, f"evidence link {index}", link.get("href"), require_local_file=True)
                if finding:
                    findings.append(finding)
    return findings


def ci_link_catalog(args: argparse.Namespace) -> tuple[dict, int]:
    """Resolve one pipeline job and verify each named artifact before exposing browser links."""
    publication_policy = active_publication_policy()
    output = {
        "schema": CI_LINK_SCHEMA,
        "record_id": "python-material-tooling",
        "state": "unavailable",
        "source_commit": args.ci_commit,
        "reason": "The expected CI artifact was not available in this validated pipeline.",
        "artifacts": [],
    }
    set_publication_field(output, "pipeline_url", args.ci_pipeline_url, publication_policy)
    token = os.environ.get(args.ci_job_token_env, "")
    if not token:
        output["reason"] = f"{args.ci_job_token_env} was unavailable while resolving CI evidence."
        return output, 1
    api_root = args.ci_api_url.rstrip("/")
    project_id = urllib.parse.quote(args.ci_project_id, safe="")
    job_id = str(args.ci_artifact_job_id or "")
    if not job_id.isdigit():
        output["reason"] = "The producing CI job ID was unavailable; no artifact links were inferred from a ref."
        return output, 1
    artifact_root = f"{api_root}/projects/{project_id}/jobs/{job_id}/artifacts"
    manifest_path = urllib.parse.quote(args.ci_manifest_artifact_path, safe="/")
    manifest_url = f"{artifact_root}/{manifest_path}"
    request = urllib.request.Request(manifest_url, headers={"JOB-TOKEN": token})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            manifest = json.load(response)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
        output["reason"] = f"The CI evidence manifest could not be read: {getattr(error, 'reason', error)}"
        return output, 1
    records = manifest.get("records") if isinstance(manifest, dict) else None
    if not isinstance(records, list) or len(records) != 1 or records[0].get("source_commit") != args.ci_commit:
        output["reason"] = "The producing CI artifact does not identify the preview commit."
        return output, 1
    job_url = args.ci_project_url.rstrip("/") + "/-/jobs/" + job_id
    set_publication_field(output, "job_url", job_url, publication_policy)
    missing = 0
    artifact_source_root = args.ci_artifact_root.resolve()
    args.ci_preview_root.mkdir(parents=True, exist_ok=True)
    for kind, path in (
        ("Scanner-original CycloneDX SBOM", args.ci_raw_sbom_artifact_path),
        ("CycloneDX SBOM", args.ci_sbom_artifact_path),
        ("Evidence manifest", args.ci_manifest_artifact_path),
        ("License appendix", args.ci_appendix_artifact_path),
    ):
        encoded_path = urllib.parse.quote(path, safe="/")
        api_href = f"{artifact_root}/{encoded_path}"
        artifact_request = urllib.request.Request(
            api_href,
            headers={"JOB-TOKEN": token, "Range": "bytes=0-0"},
        )
        entry = {"label": kind, "repository_path": path, "status": "missing"}
        try:
            with urllib.request.urlopen(artifact_request, timeout=20) as response:
                if response.status not in {200, 206}:
                    raise ValueError(f"HTTP {response.status}")
            source = (artifact_source_root / path).resolve()
            if artifact_source_root != source and artifact_source_root not in source.parents:
                raise ValueError("artifact path escapes its downloaded root")
            if not source.is_file():
                raise ValueError("downloaded artifact is absent from the Pages workspace")
            destination = args.ci_preview_root / source.name
            entry["status"] = "available"
            direct_href = (
                args.ci_project_url.rstrip("/") + "/-/jobs/" + job_id +
                "/artifacts/file/" + encoded_path
            )
            set_publication_field(entry, "href", direct_href, publication_policy)
            if copy_publication_evidence(source, destination, publication_policy):
                entry["preview_href"] = os.path.relpath(
                    destination, args.ci_links_out.parent,
                ).replace(os.sep, "/")
            else:
                entry["publication_status"] = "withheld"
                entry["publication_reason"] = (
                    "The verified source is not distributed in this preview."
                )
            entry["sha256"] = digest(source)
            entry["bytes"] = source.stat().st_size
            if kind == "CycloneDX SBOM":
                sbom = load_sbom(source)
                entry["component_count"] = len(sbom["components"])
                entry["license_metadata"] = license_summary(sbom["components"])
                if entry["license_metadata"]["named"] or entry["license_metadata"]["missing"]:
                    raise ValueError("resolved SBOM still contains non-SPDX or missing license rows")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as error:
            missing += 1
            reason = f"Artifact read failed: {getattr(error, 'reason', error)}"
            entry["reason"] = (
                reason if publication_safe_text(reason, publication_policy)
                else "Artifact verification did not complete."
            )
        output["artifacts"].append(entry)
    if missing:
        output["state"] = "incomplete"
        output["reason"] = f"{missing} expected artifact path(s) were missing from the successful job."
    else:
        output["state"] = "available"
        output["reason"] = "Every referenced artifact was verified before this preview was built."
    encoded = json.dumps(output, indent=2, sort_keys=True) + "\n"
    if not publication_safe_text(encoded, publication_policy):
        raise ValueError("generated CI evidence still violates the publication policy")
    return output, missing


def emit(args: argparse.Namespace) -> tuple[dict, int]:
    """Write one digest-bound evidence manifest and its license appendix."""
    if not COMMIT.fullmatch(args.source_commit):
        raise ValueError("source commit must be a full 40- or 64-character lowercase hexadecimal ID")
    document = load_sbom(args.sbom)
    sbom_sha = digest(args.sbom)
    artifact_id = args.artifact_id or f"{args.artifact_name}@sha256:{sbom_sha}"
    rendered, unresolved = license_inventory.render(args.sbom, artifact_id, args.inventory)
    args.appendix_out.parent.mkdir(parents=True, exist_ok=True)
    args.appendix_out.write_text(rendered, encoding="utf-8")
    record = {
        "id": args.record_id,
        "state": "available",
        "distribution": args.distribution,
        "description": args.description,
        "selectors": [{"category": category} for category in args.category],
        "artifact_id": artifact_id,
        "source_commit": args.source_commit,
        "sbom": {
            "href": args.sbom_href or args.sbom.name,
            "sha256": sbom_sha,
            "bytes": args.sbom.stat().st_size,
            "format": "CycloneDX",
            "spec_version": document.get("specVersion"),
            "component_count": len(document["components"]),
            "license_metadata": license_summary(document["components"]),
        },
        "license_appendix": {
            "href": args.appendix_href or args.appendix_out.name,
            "sha256": digest(args.appendix_out),
            "unresolved_count": unresolved,
        },
        "ci": {
            "job": args.ci_job,
            "pipeline_url": args.pipeline_url,
            "job_url": args.job_url,
            "retention_days": args.retention_days,
        },
    }
    if args.raw_sbom:
        raw_sha = digest(args.raw_sbom)
        properties = {
            item.get("name"): item.get("value")
            for item in (document.get("metadata") or {}).get("properties", [])
            if isinstance(item, dict)
        }
        if properties.get("nemoclaw:license-resolution:raw-sbom-sha256") != raw_sha:
            raise ValueError("resolved SBOM is not bound to the supplied scanner-original SBOM")
        record["raw_sbom"] = {
            "href": args.raw_sbom_href or args.raw_sbom.name,
            "sha256": raw_sha,
            "bytes": args.raw_sbom.stat().st_size,
            "purpose": "Scanner-original evidence retained before package/version SPDX resolution",
        }
    output = {"schema": "nemoclaw-sbom-evidence/1", "records": [record]}
    args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output, unresolved


def compose_release_catalog(base_path: Path, generated_path: Path, browser_href: str) -> dict:
    """Replace transient declarations with the records shipped beside release SBOMs."""
    base = json.loads(base_path.read_text(encoding="utf-8"))
    generated = json.loads(generated_path.read_text(encoding="utf-8"))
    if base.get("schema") != "nemoclaw-sbom-evidence/1" or generated.get("schema") != base.get("schema"):
        raise ValueError("release catalog inputs must use nemoclaw-sbom-evidence/1")
    generated_records = generated.get("records") or []
    if len(generated_records) != 1 or generated_records[0].get("id") != "python-material-tooling":
        raise ValueError("generated release evidence must contain the Python material-tool record")
    output = copy.deepcopy(base)
    records = output.get("records") or []
    browser = next((record for record in records if record.get("id") == "browser-runtime"), None)
    if not browser or not browser.get("sbom"):
        raise ValueError("base catalog lacks browser runtime evidence")
    browser["sbom"]["href"] = browser_href
    python_index = next((index for index, record in enumerate(records)
                         if record.get("id") == "python-material-tooling"), None)
    if python_index is None:
        raise ValueError("base catalog lacks the Python evidence declaration")
    records[python_index] = generated_records[0]
    output["release_source_commit"] = generated_records[0].get("source_commit")
    return output


def self_test() -> list[str]:
    """Exercise linked-file drift, inventory coverage, emission, and release composition."""
    failures: list[str] = []
    clean = json.loads(CATALOG.read_text(encoding="utf-8"))
    if audit_catalog(clean):
        failures.append("clean evidence catalog rejected")
    mutations = []
    stale = copy.deepcopy(clean)
    stale["records"][0]["sbom"]["sha256"] = "0" * 64
    mutations.append(("linked SBOM digest", stale, "sha256 is stale"))
    dead_link = copy.deepcopy(clean)
    dead_link["records"][-1]["evidence_links"][0]["href"] = "../../../missing-evidence.md"
    mutations.append(("local evidence link", dead_link, "missing repository file"))
    for label, mutation, expected in mutations:
        if not any(expected in finding for finding in audit_catalog(mutation)):
            failures.append(f"mutation escaped: {label}")
    with tempfile.TemporaryDirectory(prefix="sbom-evidence-") as directory:
        root = Path(directory)
        sbom = root / "fixture.cdx.json"
        sbom.write_text(json.dumps({
            "bomFormat": "CycloneDX", "specVersion": "1.6",
            "components": [{"name": "fixture", "version": "1", "licenses": [{"license": {"id": "MIT"}}]}],
        }), encoding="utf-8")
        appendix = root / "licenses.md"
        manifest = root / "evidence.json"
        args = argparse.Namespace(
            source_commit="a" * 40, sbom=sbom, raw_sbom=None, raw_sbom_href=None,
            artifact_id=None, artifact_name="fixture",
            inventory=INVENTORY, appendix_out=appendix, manifest_out=manifest,
            record_id="python-material-tooling", distribution="not-distributed", description="fixture",
            category=["validation"], sbom_href=None, appendix_href=None, ci_job="fixture",
            pipeline_url="", job_url="",
            retention_days=30,
        )
        emitted, unresolved = emit(args)
        if unresolved or emitted["records"][0]["sbom"]["sha256"] != digest(sbom):
            failures.append("emitted evidence does not bind the fixture SBOM")
        release = compose_release_catalog(CATALOG, manifest, "nemoclaw-v1.0.0.browser.cdx.json")
        release_records = {record["id"]: record for record in release["records"]}
        if release_records["browser-runtime"]["sbom"]["href"] != "nemoclaw-v1.0.0.browser.cdx.json":
            failures.append("release catalog does not link the versioned browser SBOM")
        if release_records["python-material-tooling"]["state"] != "available":
            failures.append("release catalog does not replace the transient Python declaration")

        from scripts.validation.sensitive_content_audit import Policy

        private_host = "review.private.invalid"
        policy = Policy(
            frozenset(),
            frozenset(),
            frozenset({hashlib.sha256("private.invalid".encode("utf-8")).hexdigest()}),
            6,
        )
        optional: dict[str, str] = {}
        if set_publication_field(optional, "href", f"https://{private_host}/job", policy):
            failures.append("private generated URL escaped the publication policy")
        if not set_publication_field(optional, "preview_href", "ci/evidence.json", policy):
            failures.append("safe same-origin preview path was removed")
        blocked_source = root / "blocked.json"
        blocked_source.write_text(json.dumps({"href": f"https://{private_host}/job"}), encoding="utf-8")
        blocked_destination = root / "published" / "blocked.json"
        if copy_publication_evidence(blocked_source, blocked_destination, policy):
            failures.append("private evidence file escaped the publication policy")
        if blocked_destination.exists():
            failures.append("withheld evidence left stale publication bytes")
        safe_source = root / "safe.json"
        safe_source.write_text(json.dumps({"state": "available"}), encoding="utf-8")
        safe_destination = root / "published" / "safe.json"
        if not copy_publication_evidence(safe_source, safe_destination, policy):
            failures.append("safe evidence file was withheld")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-external-links", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--write-ci-links", action="store_true")
    parser.add_argument("--compose-release-catalog", action="store_true")
    parser.add_argument("--base-catalog", type=Path, default=CATALOG)
    parser.add_argument("--generated-manifest", type=Path)
    parser.add_argument("--browser-href")
    parser.add_argument("--release-catalog-out", type=Path)
    parser.add_argument("--sbom", type=Path)
    parser.add_argument("--raw-sbom", type=Path)
    parser.add_argument("--raw-sbom-href")
    parser.add_argument("--artifact-name")
    parser.add_argument("--artifact-id")
    parser.add_argument("--record-id")
    parser.add_argument("--description", default="CI-generated SBOM evidence")
    parser.add_argument("--distribution", choices=sorted(ALLOWED_DISTRIBUTION))
    parser.add_argument("--category", action="append", choices=("vendored", "build-input", "validation"))
    parser.add_argument("--source-commit")
    parser.add_argument("--ci-job")
    parser.add_argument("--pipeline-url", default="")
    parser.add_argument("--job-url", default="")
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--sbom-href")
    parser.add_argument("--appendix-href")
    parser.add_argument("--appendix-out", type=Path)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--ci-links-out", type=Path)
    parser.add_argument("--ci-api-url")
    parser.add_argument("--ci-project-id")
    parser.add_argument("--ci-project-url")
    parser.add_argument("--ci-pipeline-url", default="")
    parser.add_argument("--ci-commit", default="")
    parser.add_argument("--ci-artifact-job-id")
    parser.add_argument("--ci-artifact-root", type=Path, default=ROOT)
    parser.add_argument("--ci-preview-root", type=Path)
    parser.add_argument("--ci-job-token-env", default="CI_JOB_TOKEN")
    parser.add_argument("--ci-sbom-artifact-path", default="scripts/security/reports/python-materials/python-env.cdx.json")
    parser.add_argument("--ci-raw-sbom-artifact-path", default="scripts/security/reports/python-materials/python-env.raw.cdx.json")
    parser.add_argument("--ci-manifest-artifact-path", default="scripts/security/reports/python-materials/sbom-evidence.json")
    parser.add_argument("--ci-appendix-artifact-path", default="scripts/security/reports/python-materials/python-license-appendix.md")
    args = parser.parse_args()

    if args.self_test:
        failures = self_test()
        print("SBOM evidence self-test: " + ("FAIL" if failures else "PASS"))
        for failure in failures:
            print(f"  {failure}")
        return 1 if failures else 0

    if args.write_ci_links:
        missing = [flag for flag, value in {
            "--ci-links-out": args.ci_links_out,
            "--ci-api-url": args.ci_api_url,
            "--ci-project-id": args.ci_project_id,
            "--ci-project-url": args.ci_project_url,
            "--ci-artifact-job-id": args.ci_artifact_job_id,
            "--ci-preview-root": args.ci_preview_root,
        }.items() if not value]
        if missing:
            parser.error("CI link emission requires " + ", ".join(missing))
        output, unresolved = ci_link_catalog(args)
        args.ci_links_out.parent.mkdir(parents=True, exist_ok=True)
        args.ci_links_out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote CI SBOM evidence links: state={output['state']} unresolved={unresolved}")
        return 0

    if args.check or args.check_external_links:
        findings = audit_catalog()
        if args.check_external_links and not findings:
            findings.extend(check_external_links(json.loads(CATALOG.read_text(encoding="utf-8"))))
        print("SBOM evidence catalog: " + (f"FAIL ({len(findings)})" if findings else "PASS"))
        for finding in findings:
            print(f"  {finding}")
        return 1 if findings else 0

    if args.compose_release_catalog:
        if not args.generated_manifest or not args.browser_href or not args.release_catalog_out:
            parser.error("release catalog composition requires --generated-manifest, --browser-href, and --release-catalog-out")
        try:
            output = compose_release_catalog(args.base_catalog, args.generated_manifest, args.browser_href)
        except (ValueError, json.JSONDecodeError) as error:
            parser.error(str(error))
        args.release_catalog_out.parent.mkdir(parents=True, exist_ok=True)
        args.release_catalog_out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote release SBOM evidence catalog: {args.release_catalog_out}")
        return 0

    required = {
        "--sbom": args.sbom, "--artifact-name": args.artifact_name, "--record-id": args.record_id,
        "--distribution": args.distribution, "--category": args.category, "--source-commit": args.source_commit,
        "--ci-job": args.ci_job, "--appendix-out": args.appendix_out, "--manifest-out": args.manifest_out,
    }
    missing = [flag for flag, value in required.items() if not value]
    if missing:
        parser.error("evidence emission requires " + ", ".join(missing))
    if args.record_id == "python-material-tooling" and not args.raw_sbom:
        parser.error("Python material-tool evidence requires --raw-sbom")
    try:
        _output, unresolved = emit(args)
    except (ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"wrote {args.manifest_out} and {args.appendix_out}: unresolved={unresolved}")
    return 0 if unresolved == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
