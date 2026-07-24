#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Verify that the Pages branch selector advertises only published artifact paths."""
from __future__ import annotations

import argparse
import json
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

COURSE_EVIDENCE = (
    "dependencies.html",
    "vendor/browser-dependencies.json",
    "vendor/browser-sbom.cdx.json",
    "scripts/_langchain.js",
)


def browser_sbom_coverage_findings(manifest: dict, sbom: dict, label: str) -> list[str]:
    """Compare the identities in both reviewer inventories, including embedded source."""
    findings: list[str] = []
    packages = manifest.get("packages") if isinstance(manifest.get("packages"), list) else []
    embedded = manifest.get("embedded_components") if isinstance(manifest.get("embedded_components"), list) else []
    components = sbom.get("components") if isinstance(sbom.get("components"), list) else []
    expected_packages = {(row.get("name"), row.get("version")) for row in packages
                         if isinstance(row, dict) and row.get("name") and row.get("version")}
    expected_embedded = {row.get("id") for row in embedded
                         if isinstance(row, dict) and row.get("id")}
    actual_packages = {(row.get("name"), row.get("version")) for row in components
                       if isinstance(row, dict) and str(row.get("bom-ref", "")).startswith("pkg:npm/")}
    actual_embedded = {str(row.get("bom-ref"))[len("embedded:"):]
                       for row in components
                       if isinstance(row, dict) and str(row.get("bom-ref", "")).startswith("embedded:")}
    if sbom.get("bomFormat") != "CycloneDX":
        findings.append(f"{label} browser SBOM is not CycloneDX")
    if (expected_packages != actual_packages or expected_embedded != actual_embedded or
            len(expected_packages) != len(packages) or len(expected_embedded) != len(embedded) or
            len(actual_packages) + len(actual_embedded) != len(components)):
        missing_packages = sorted(f"{name}@{version}" for name, version in expected_packages - actual_packages)
        extra_packages = sorted(f"{name}@{version}" for name, version in actual_packages - expected_packages)
        missing_embedded = sorted(expected_embedded - actual_embedded)
        extra_embedded = sorted(actual_embedded - expected_embedded)
        detail = "; ".join(part for part in (
            "missing packages: " + ", ".join(missing_packages) if missing_packages else "",
            "extra packages: " + ", ".join(extra_packages) if extra_packages else "",
            "missing embedded components: " + ", ".join(missing_embedded) if missing_embedded else "",
            "extra embedded components: " + ", ".join(extra_embedded) if extra_embedded else "",
        ) if part) or "duplicate or incomplete component identities"
        findings.append(f"{label} browser SBOM does not cover the package and embedded-component inventory ({detail})")
    return findings


def audit_course_source_resolver(source: str, label: str) -> list[str]:
    findings: list[str] = []
    for token in (
        "export function resolveCoursePageUrl",
        'const courseDirectory = new URL("./", pageHref)',
        'new URL(id === "overview" ? "../index.html" : id + ".html", courseDirectory)',
        "fetch(resolveCoursePageUrl(id)",
    ):
        if token not in source:
            findings.append(f"{label} Course Assistant source resolver is missing: {token}")
    if '"../../index.html"' in source:
        findings.append(f"{label} Course Assistant overview escapes the deployed project subpath")
    return findings


def audit_course_evidence(course_root: Path, label: str) -> list[str]:
    findings = [f"{label} missing course evidence: {rel}"
                for rel in COURSE_EVIDENCE if not (course_root / rel).is_file()]
    if findings:
        return findings
    dashboard = (course_root / "dependencies.html").read_text(encoding="utf-8", errors="replace")
    if "Browser dependency inventory" not in dashboard or "vendor/browser-dependencies.json" not in dashboard:
        findings.append(f"{label} dependency dashboard is not wired to its inventory")
    langchain = course_root / "scripts/_langchain.js"
    if langchain.is_file():
        findings.extend(audit_course_source_resolver(
            langchain.read_text(encoding="utf-8", errors="replace"), label
        ))
    try:
        manifest = json.loads((course_root / "vendor/browser-dependencies.json").read_text())
        sbom = json.loads((course_root / "vendor/browser-sbom.cdx.json").read_text())
    except json.JSONDecodeError as exc:
        return findings + [f"{label} browser dependency evidence is invalid JSON: {exc}"]
    packages = manifest.get("packages") if isinstance(manifest.get("packages"), list) else []
    if manifest.get("delivery") != "same-origin-vendored" or not packages:
        findings.append(f"{label} browser dependency inventory is empty or not same-origin")
    findings.extend(browser_sbom_coverage_findings(manifest, sbom, label))
    return findings


def parse_ref(spec: str) -> tuple[str, str]:
    name, sep, slug = spec.partition("=")
    slug = slug if sep else name
    if not name or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", slug):
        raise ValueError(f"invalid preview ref: {spec!r}")
    return name, slug


def audit(artifact_root: Path, manifest: Path, expected: list[str] | None = None) -> list[str]:
    findings: list[str] = []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read branch manifest {manifest}: {exc}"]
    if data.get("schema") != "nemoclaw-branches/2":
        findings.append("branch manifest must use availability-aware schema nemoclaw-branches/2")
    items = data.get("branches")
    if not isinstance(items, list) or not items:
        return findings + ["branch manifest must contain at least the production entry"]

    names: set[str] = set()
    slugs: set[str] = set()
    previews: dict[str, str] = {}
    current = []
    production = 0
    for item in items:
        if not isinstance(item, dict):
            findings.append("branch manifest entries must be objects")
            continue
        name = item.get("name")
        slug = item.get("slug")
        kind = item.get("kind")
        if not isinstance(name, str) or not name:
            findings.append("branch manifest entry is missing its name")
            continue
        if name in names:
            findings.append(f"duplicate branch name: {name}")
        names.add(name)
        if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", slug):
            findings.append(f"invalid branch slug for {name}: {slug!r}")
            continue
        if slug in slugs:
            findings.append(f"duplicate branch slug: {slug}")
        slugs.add(slug)
        if item.get("preview_ready") is not True:
            findings.append(f"{name} is listed without preview_ready=true")
        if item.get("current") is True:
            current.append(name)
        if kind == "production":
            production += 1
            course_root = artifact_root / "nemoclaw"
            target = course_root / "index.html"
            if not expected:
                findings.extend(audit_course_evidence(course_root, name))
        elif kind == "preview":
            previews[name] = slug
            course_root = artifact_root / slug / "web" / "nemoclaw"
            target = course_root / "index.html"
            findings.extend(audit_course_evidence(course_root, name))
        else:
            findings.append(f"invalid branch kind for {name}: {kind!r}")
            continue
        raw_url = item.get("url")
        parsed = urllib.parse.urlsplit(raw_url if isinstance(raw_url, str) else "")
        resolved = (manifest.parent / parsed.path).resolve() if parsed.path and not parsed.scheme and not parsed.netloc else None
        if resolved != course_root.resolve():
            findings.append(
                f"{name} URL must resolve from {manifest.parent} to {course_root}, got {raw_url!r}"
            )
        if not target.is_file():
            findings.append(f"{name} advertises missing preview target: {target}")

    if production != 1:
        findings.append(f"branch manifest must contain exactly one production entry, found {production}")
    declared_current = data.get("current") or {}
    if len(current) != 1 or current[0] != declared_current.get("name"):
        findings.append("branch manifest current entry must uniquely match data.current.name")

    discovered = {
        path.relative_to(artifact_root).parts[0]
        for path in artifact_root.glob("*/web/nemoclaw/index.html")
        if path.relative_to(artifact_root).parts[0] != "validated-source"
    }
    listed = set(previews.values())
    for slug in sorted(discovered - listed):
        findings.append(f"published preview path is missing from manifest: {slug}")
    for slug in sorted(listed - discovered):
        findings.append(f"manifest preview has no published artifact path: {slug}")
    for spec in expected or []:
        name, slug = parse_ref(spec)
        if previews.get(name) != slug:
            findings.append(f"expected published preview missing: {name}={slug}")
    return findings


def self_test() -> list[str]:
    misses: list[str] = []
    valid_gate = {"git_sha": "01234567", "ok": True}
    if audit_gate_sha(valid_gate, "0123456789abcdef", "fixture"):
        misses.append("valid short gate SHA rejected")
    for label, mutated, expected in (
        ("wrong gate SHA", {"git_sha": "89abcdef", "ok": True}, "gate report is for"),
        ("failed gate", {"git_sha": "01234567", "ok": False}, "not passing"),
        ("missing gate SHA", {"ok": True}, "no usable git_sha"),
    ):
        if not any(expected in finding for finding in audit_gate_sha(mutated, "0123456789abcdef", "fixture")):
            misses.append(f"detector missed {label}")
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        (root / "nemoclaw").mkdir()
        (root / "nemoclaw" / "index.html").write_text("production", encoding="utf-8")
        (root / "ready" / "web" / "nemoclaw").mkdir(parents=True)
        (root / "ready" / "web" / "nemoclaw" / "index.html").write_text("preview", encoding="utf-8")
        (root / "ready" / "web" / "nemoclaw" / "dependencies.html").write_text(
            "Browser dependency inventory vendor/browser-dependencies.json", encoding="utf-8"
        )
        (root / "ready" / "web" / "nemoclaw" / "vendor").mkdir()
        (root / "ready" / "web" / "nemoclaw" / "scripts").mkdir()
        resolver = (
            'export function resolveCoursePageUrl(pageId, pageHref) {\n'
            '  const id = pageId;\n'
            '  const courseDirectory = new URL("./", pageHref);\n'
            '  return new URL(id === "overview" ? "../index.html" : id + ".html", courseDirectory).href;\n'
            '}\nfetch(resolveCoursePageUrl(id), { credentials: "same-origin" });\n'
        )
        (root / "ready" / "web" / "nemoclaw" / "scripts" / "_langchain.js").write_text(
            resolver, encoding="utf-8"
        )
        (root / "ready" / "web" / "nemoclaw" / "vendor" / "browser-dependencies.json").write_text(
            json.dumps({"delivery": "same-origin-vendored", "packages": [{"name": "fixture", "version": "1.0.0"}],
                        "embedded_components": [{"id": "embedded-fixture"}]}), encoding="utf-8"
        )
        (root / "ready" / "web" / "nemoclaw" / "vendor" / "browser-sbom.cdx.json").write_text(
            json.dumps({"bomFormat": "CycloneDX", "components": [
                {"name": "fixture", "version": "1.0.0", "bom-ref": "pkg:npm/fixture@1.0.0"},
                {"name": "Embedded fixture", "bom-ref": "embedded:embedded-fixture"},
            ]}), encoding="utf-8"
        )
        base = {
            "schema": "nemoclaw-branches/2",
            "current": {"name": "main", "slug": "main"},
            "branches": [
                {"name": "main", "slug": "main", "kind": "production", "url": "nemoclaw/", "preview_ready": True, "current": True},
                {"name": "ready", "slug": "ready", "kind": "preview", "url": "ready/web/nemoclaw/", "preview_ready": True, "current": False},
            ],
        }
        manifest = root / "branches.json"
        manifest.write_text(json.dumps(base), encoding="utf-8")
        if audit(root, manifest, ["ready=ready"]):
            misses.append("valid artifact rejected")
        nested = json.loads(json.dumps(base))
        nested["current"] = {"name": "ready", "slug": "ready"}
        nested["branches"][0]["url"] = "../nemoclaw/"
        nested["branches"][0]["current"] = False
        nested["branches"][1]["url"] = "web/nemoclaw/"
        nested["branches"][1]["current"] = True
        nested_manifest = root / "ready" / "branches.json"
        nested_manifest.write_text(json.dumps(nested), encoding="utf-8")
        if audit(root, nested_manifest, ["ready=ready"]):
            misses.append("valid nested manifest rejected")
        cases = []
        ghost = json.loads(json.dumps(base))
        ghost["branches"].append({"name": "ghost", "slug": "ghost", "kind": "preview", "url": "ghost/web/nemoclaw/", "preview_ready": True, "current": False})
        cases.append(("ghost target", ghost, "missing preview target"))
        unready = json.loads(json.dumps(base))
        unready["branches"][1]["preview_ready"] = False
        cases.append(("readiness flag", unready, "preview_ready=true"))
        old = json.loads(json.dumps(base))
        old["schema"] = "nemoclaw-branches/1"
        cases.append(("old schema", old, "availability-aware schema"))
        for label, mutated, expected in cases:
            manifest.write_text(json.dumps(mutated), encoding="utf-8")
            if not any(expected in finding for finding in audit(root, manifest)):
                misses.append(f"detector missed {label}")
        manifest.write_text(json.dumps(base), encoding="utf-8")
        (root / "unlisted" / "web" / "nemoclaw").mkdir(parents=True)
        (root / "unlisted" / "web" / "nemoclaw" / "index.html").write_text("preview", encoding="utf-8")
        if not any("missing from manifest" in finding for finding in audit(root, manifest)):
            misses.append("detector missed unlisted published path")
        missing = root / "ready" / "web" / "nemoclaw" / "vendor" / "browser-sbom.cdx.json"
        missing.unlink()
        if not any("missing course evidence" in finding for finding in audit(root, manifest, ["ready=ready"])):
            misses.append("detector missed absent browser dependency evidence")
        (root / "ready" / "web" / "nemoclaw" / "vendor" / "browser-sbom.cdx.json").write_text(
            json.dumps({"bomFormat": "CycloneDX", "components": [
                {"name": "fixture", "version": "1.0.0", "bom-ref": "pkg:npm/fixture@1.0.0"},
                {"name": "Embedded fixture", "bom-ref": "embedded:embedded-fixture"},
            ]}), encoding="utf-8"
        )
        incomplete = root / "ready" / "web" / "nemoclaw" / "vendor" / "browser-sbom.cdx.json"
        incomplete.write_text(json.dumps({"bomFormat": "CycloneDX", "components": [
            {"name": "fixture", "version": "1.0.0", "bom-ref": "pkg:npm/fixture@1.0.0"},
        ]}), encoding="utf-8")
        if not any("missing embedded components: embedded-fixture" in finding
                   for finding in audit(root, manifest, ["ready=ready"])):
            misses.append("detector missed embedded browser component omission")
        incomplete.write_text(json.dumps({"bomFormat": "CycloneDX", "components": [
            {"name": "fixture", "version": "1.0.0", "bom-ref": "pkg:npm/fixture@1.0.0"},
            {"name": "Embedded fixture", "bom-ref": "embedded:embedded-fixture"},
        ]}), encoding="utf-8")
        bad_resolver = resolver.replace('"../index.html"', '"../../index.html"')
        (root / "ready" / "web" / "nemoclaw" / "scripts" / "_langchain.js").write_text(
            bad_resolver, encoding="utf-8"
        )
        if not any("escapes the deployed project subpath" in finding for finding in audit(root, manifest, ["ready=ready"])):
            misses.append("detector missed Course Assistant project-subpath escape")
    return misses


def fetch(url: str, method: str = "GET") -> bytes:
    request = urllib.request.Request(url, method=method, headers={"User-Agent": "nemoclaw-pages-audit/1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status < 200 or response.status >= 400:
            raise RuntimeError(f"HTTP {response.status}: {url}")
        return response.read()


def audit_live_course_evidence(course_url: str, label: str) -> list[str]:
    findings: list[str] = []
    try:
        dashboard = fetch(urllib.parse.urljoin(course_url, "dependencies.html")).decode("utf-8", "replace")
        manifest = json.loads(fetch(urllib.parse.urljoin(course_url, "vendor/browser-dependencies.json")))
        sbom = json.loads(fetch(urllib.parse.urljoin(course_url, "vendor/browser-sbom.cdx.json")))
        source = fetch(urllib.parse.urljoin(course_url, "scripts/_langchain.js")).decode("utf-8", "replace")
        fetch(urllib.parse.urljoin(course_url, "../index.html"), "HEAD")
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        return [f"{label} live browser dependency evidence unavailable: {exc}"]
    packages = manifest.get("packages") if isinstance(manifest.get("packages"), list) else []
    if "Browser dependency inventory" not in dashboard or "vendor/browser-dependencies.json" not in dashboard:
        findings.append(f"{label} live dependency dashboard is not wired to its inventory")
    if manifest.get("delivery") != "same-origin-vendored" or not packages:
        findings.append(f"{label} live browser dependency inventory is empty or not same-origin")
    findings.extend(browser_sbom_coverage_findings(manifest, sbom, f"{label} live"))
    findings.extend(audit_course_source_resolver(source, label))
    return findings


def audit_gate_sha(payload: object, expected_git_sha: str, label: str) -> list[str]:
    if not isinstance(payload, dict):
        return [f"{label} gate report must be a JSON object"]
    actual = str(payload.get("git_sha") or "").strip().lower()
    expected = expected_git_sha.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{8,40}", expected):
        return [f"invalid expected Git SHA: {expected_git_sha!r}"]
    if not re.fullmatch(r"[0-9a-f]{8,40}", actual):
        return [f"{label} gate report has no usable git_sha: {actual!r}"]
    if not (actual == expected or actual.startswith(expected) or expected.startswith(actual)):
        return [f"{label} gate report is for {actual}, expected {expected}"]
    if payload.get("ok") is not True:
        return [f"{label} gate report is not passing"]
    return []


def audit_live_once(base_url: str, expected: list[str], expected_git_sha: str = "") -> list[str]:
    base = base_url.rstrip("/") + "/"
    findings: list[str] = []
    expected_map = dict(parse_ref(spec) for spec in expected)
    try:
        root_html = fetch(urllib.parse.urljoin(base, "index.html")).decode("utf-8", "replace")
        root_data = json.loads(fetch(urllib.parse.urljoin(base, "branches.json")))
    except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
        return [f"live Pages root unavailable: {exc}"]
    if not expected_map and ("b.preview_ready === true" not in root_html or 'method: "HEAD"' not in root_html):
        findings.append("live foyer lacks readiness filtering and same-origin HEAD probes")
    if root_data.get("schema") != "nemoclaw-branches/2":
        findings.append("live root manifest is not nemoclaw-branches/2")
    items = root_data.get("branches") if isinstance(root_data.get("branches"), list) else []
    actual = {
        item.get("name"): item.get("slug")
        for item in items
        if isinstance(item, dict) and item.get("kind") == "preview"
    }
    if actual != expected_map:
        findings.append(f"live root preview set mismatch: expected {expected_map}, got {actual}")
    for item in items:
        if not isinstance(item, dict):
            findings.append("live root manifest contains a non-object entry")
            continue
        if item.get("preview_ready") is not True:
            findings.append(f"live branch lacks preview_ready=true: {item.get('name')}")
        target = urllib.parse.urljoin(base, str(item.get("url") or "") + "index.html")
        try:
            fetch(target, "HEAD")
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            findings.append(f"advertised branch target unavailable: {target}: {exc}")
        kind = item.get("kind")
        if (kind == "preview" and item.get("name") in expected_map) or (kind == "production" and not expected_map):
            findings.extend(audit_live_course_evidence(urllib.parse.urljoin(base, str(item.get("url") or "")), str(item.get("name"))))
    for name, slug in expected_map.items():
        branch_base = urllib.parse.urljoin(base, f"{slug}/")
        try:
            branch_html = fetch(urllib.parse.urljoin(branch_base, "index.html")).decode("utf-8", "replace")
            branch_data = json.loads(fetch(urllib.parse.urljoin(branch_base, "branches.json")))
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            findings.append(f"branch foyer unavailable for {name}: {exc}")
            continue
        if "b.preview_ready === true" not in branch_html or 'method: "HEAD"' not in branch_html:
            findings.append(f"branch foyer lacks readiness filtering and HEAD probes: {name}")
        if branch_data.get("schema") != "nemoclaw-branches/2":
            findings.append(f"branch foyer manifest is not nemoclaw-branches/2: {name}")
        branch_previews = {
            item.get("name"): item.get("slug")
            for item in branch_data.get("branches", [])
            if isinstance(item, dict) and item.get("kind") == "preview"
        }
        if branch_previews != expected_map:
            findings.append(f"branch foyer preview set mismatch for {name}: {branch_previews}")
        if expected_git_sha:
            try:
                gate = json.loads(fetch(urllib.parse.urljoin(branch_base, "gate.json")))
            except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
                findings.append(f"live gate report unavailable for {name}: {exc}")
            else:
                findings.extend(audit_gate_sha(gate, expected_git_sha, name))
    if expected_git_sha and not expected_map:
        try:
            gate = json.loads(fetch(urllib.parse.urljoin(base, "gate.json")))
        except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            findings.append(f"live production gate report unavailable: {exc}")
        else:
            findings.extend(audit_gate_sha(gate, expected_git_sha, "production"))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact-root", type=Path)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--expect-preview", action="append", default=[])
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--base-url", help="live Pages project root")
    ap.add_argument("--expect-git-sha", default="", help="exact commit represented by the live gate report")
    ap.add_argument("--attempts", type=int, default=12)
    ap.add_argument("--delay", type=float, default=5.0)
    ns = ap.parse_args()
    findings = self_test() if ns.self_test else []
    if ns.base_url:
        for attempt in range(1, max(1, ns.attempts) + 1):
            findings = audit_live_once(ns.base_url, ns.expect_preview, ns.expect_git_sha)
            if not findings:
                break
            if attempt < ns.attempts:
                print(f"branch_preview_manifest_audit: live attempt {attempt}/{ns.attempts} not ready")
                time.sleep(max(0, ns.delay))
    elif not ns.self_test:
        if not ns.artifact_root or not ns.manifest:
            ap.error("--artifact-root and --manifest are required unless --self-test or --base-url is used")
        findings.extend(audit(ns.artifact_root.resolve(), ns.manifest.resolve(), ns.expect_preview))
    if findings:
        print("branch_preview_manifest_audit: FAIL")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("branch_preview_manifest_audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
