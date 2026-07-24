# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit and apply the repository's Apache-2.0 source-license contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Iterable


COPYRIGHT = "Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved."
SPDX = "SPDX-License-Identifier: Apache-2.0"
AUTHORED_ROOTS = {"scripts", "web", "tests", "cpu", "workspace"}
COMMENT_PREFIX = {".py": "#", ".js": "//", ".mjs": "//"}
NON_AUTHORED_PREFIXES = ("web/nemoclaw/vendor/", "web/shared/vendor/")
NOTICE_LINKS = (
    "THIRD_PARTY_LICENSES.md",
    "web/nemoclaw/vendor/browser-dependencies.json",
    "web/nemoclaw/vendor/licenses/",
    "web/shared/vendor/browser-dependencies.json",
    "web/shared/vendor/licenses/",
    "scripts/compliance/docs/browser_vendor_exceptions.json",
    "scripts/browser-vendor/embedded-component-evidence.json",
    "scripts/compliance/docs/vendor_policy.md",
)
BROWSER_EXCEPTION_POLICY_PATH = "scripts/compliance/docs/browser_vendor_exceptions.json"
BROWSER_EXCEPTION_POLICY_SCHEMA = "nemoclaw-browser-modification-exceptions/1"
LANGCHAIN_BROWSER_EXCEPTION = {
    "id": "langchain-browser-esm-commonjs-interop-v1",
    "asset": "langchain-1.4.7.esm.js",
    "entrypoint": "scripts/browser-vendor/langchain-entry.js",
    "distribution_form": "transformed-bundle",
    "publisher_provided_minified": False,
    "transformation": (
        "esbuild resolves the selected LangChain dependency graph into one browser ESM file "
        "without minification; no manual source patch is permitted."
    ),
    "required_exports": ["ChatOpenAI", "tool", "createReactAgent", "MemorySaver", "z"],
    "necessity": [
        "The learner exercises import five APIs from separate LangChain and Zod packages through one same-origin browser module.",
        "The locked graph contains Node-style bare package imports and CommonJS-only dependencies, including base64-js 1.5.1, eventemitter3 4.0.7, p-finally 1.0.0, p-queue 6.6.2, and p-timeout 3.2.0.",
        "The pinned @langchain/core package also contains Fast JSON Patch, js-sha256, sax-js, and String.fromCodePoint utility source copied by LangChain; embedded-component-evidence.json records those non-npm constituents and their full licenses.",
        "A static browser cannot resolve those bare package imports or execute CommonJS require/module.exports files directly from the vendored tree.",
        "Bundling supplies module resolution and CommonJS-to-ESM interoperability. Minification is unnecessary and forbidden.",
    ],
    "constraints": [
        "This is the only browser asset that may differ from publisher files.",
        "The generated file must not be minified.",
        "No manual edit to the generated file is permitted; CI regenerates it and requires a clean diff.",
        "esbuild-preserved legal comment sections must map to a recorded npm package or embedded component; the .LEGAL.txt file is supplemental and never substitutes for the full inventory or licenses.",
        "Every other browser asset must be a byte-for-byte upstream file copy with identical upstream and delivered SHA-256 values.",
    ],
}
DCO_1_1 = """Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.

Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved."""


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def repository_files(root: Path) -> list[Path]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    proposed = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return [root / item for item in dict.fromkeys(tracked + proposed) if (root / item).is_file()]


def authored_sources(root: Path, files: Iterable[Path]) -> list[Path]:
    sources = []
    for path in files:
        rel = relative(path, root)
        if path.suffix.lower() not in COMMENT_PREFIX or not path.stat().st_size:
            continue
        if rel.split("/", 1)[0] not in AUTHORED_ROOTS:
            continue
        if rel.startswith(NON_AUTHORED_PREFIXES) or "node_modules" in path.parts:
            continue
        sources.append(path)
    return sorted(sources)


def header_lines(path: Path) -> tuple[str, str]:
    prefix = COMMENT_PREFIX[path.suffix.lower()]
    return f"{prefix} {COPYRIGHT}", f"{prefix} {SPDX}"


def has_header(path: Path) -> bool:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    start = 1 if lines and lines[0].startswith("#!") else 0
    expected = header_lines(path)
    return tuple(lines[start:start + len(expected)]) == expected


def apply_headers(root: Path, files: Iterable[Path]) -> list[str]:
    changed = []
    for path in authored_sources(root, files):
        if has_header(path):
            continue
        text = path.read_text(encoding="utf-8-sig")
        lines = text.splitlines(keepends=True)
        insertion = 1 if lines and lines[0].startswith("#!") else 0
        newline = "\r\n" if "\r\n" in text else "\n"
        header = [line + newline for line in header_lines(path)]
        if text.strip():
            header.append(newline)
        else:
            lines = []
            insertion = 0
        path.write_text("".join(lines[:insertion] + header + lines[insertion:]), encoding="utf-8")
        changed.append(relative(path, root))
    return changed


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(
    root: Path,
    files: Iterable[Path],
    *,
    verify_browser_upstream: bool = False,
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    successes: list[str] = []

    license_path = root / "LICENSE"
    license_text = license_path.read_text(encoding="utf-8", errors="replace") if license_path.is_file() else ""
    if license_text.startswith(COPYRIGHT + "\n\n") and "Apache License\n" in license_text and "Version 2.0" in license_text:
        successes.append("root license: NVIDIA copyright precedes Apache-2.0")
    else:
        failures.append("root license: LICENSE must begin with the exact NVIDIA copyright line before Apache-2.0")

    dco_path = root / "DCO.md"
    dco_text = dco_path.read_text(encoding="utf-8", errors="replace") if dco_path.is_file() else ""
    if DCO_1_1 in dco_text:
        successes.append("DCO: complete verbatim Developer Certificate of Origin 1.1 present")
    else:
        failures.append("DCO: DCO.md must contain the complete verbatim Developer Certificate of Origin 1.1 text")

    notice_path = root / "THIRD-PARTY-NOTICES.md"
    notice_text = notice_path.read_text(encoding="utf-8", errors="replace") if notice_path.is_file() else ""
    missing_links = [item for item in NOTICE_LINKS if item not in notice_text]
    if not missing_links and "modified_from_upstream" in notice_text:
        successes.append("third-party notices: top-level index and modification explanation present")
    else:
        detail = ", ".join(missing_links) if missing_links else "modified_from_upstream explanation"
        failures.append(f"third-party notices: missing {detail}")

    sources = authored_sources(root, files)
    missing_headers = [relative(path, root) for path in sources if not has_header(path)]
    if missing_headers:
        failures.extend(f"source header: missing or misplaced Apache-2.0 header: {path}" for path in missing_headers)
    else:
        successes.append(f"source headers: {len(sources)} authored Python/JavaScript file(s) covered")

    manifest_path = root / "web/nemoclaw/vendor/browser-dependencies.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"browser vendor: unreadable browser-dependencies.json: {error}")
        manifest = {}

    # The exception document is a review boundary, not an extensible allowlist.
    exception_path = root / BROWSER_EXCEPTION_POLICY_PATH
    try:
        exception_policy = json.loads(exception_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"browser vendor: unreadable modification exception policy: {error}")
        exception_policy = {}

    # Duplicating the expected record here makes a policy change modify both evidence and detector.
    expected_policy = {
        "schema": BROWSER_EXCEPTION_POLICY_SCHEMA,
        "exceptions": [LANGCHAIN_BROWSER_EXCEPTION],
    }
    if exception_policy != expected_policy:
        failures.append(
            "browser vendor: modification exception policy must contain the exact, sole "
            f"LangChain exception {LANGCHAIN_BROWSER_EXCEPTION['id']}"
        )
    expected_policy_record = {
        "file": BROWSER_EXCEPTION_POLICY_PATH,
        "sha256": sha256(exception_path) if exception_path.is_file() else "",
        "exception_ids": [LANGCHAIN_BROWSER_EXCEPTION["id"]],
    }
    if manifest.get("modification_exception_policy") != expected_policy_record:
        failures.append("browser vendor: manifest is not digest-bound to the sole modification exception policy")

    embedded_path = root / "scripts/browser-vendor/embedded-component-evidence.json"
    try:
        embedded_evidence = json.loads(embedded_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"browser vendor: unreadable embedded component evidence: {error}")
        embedded_evidence = {}
    expected_embedded_record = {
        "file": "scripts/browser-vendor/embedded-component-evidence.json",
        "sha256": sha256(embedded_path) if embedded_path.is_file() else "",
        "parent": embedded_evidence.get("parent"),
        "explanation": embedded_evidence.get("explanation"),
    }
    if manifest.get("embedded_component_evidence") != expected_embedded_record:
        failures.append("browser vendor: manifest is not digest-bound to embedded component evidence")
    expected_embedded_ids = {
        item.get("id") for item in embedded_evidence.get("components") or [] if item.get("id")
    }
    actual_embedded_ids = {
        item.get("id") for item in manifest.get("embedded_components") or [] if item.get("id")
    }
    if not expected_embedded_ids or actual_embedded_ids != expected_embedded_ids:
        failures.append("browser vendor: embedded component manifest differs from reviewed source evidence")
    assets = manifest.get("assets") or []
    valid_forms = {"transformed-bundle", "upstream-file-copy"}
    unclassified = []
    modified_assets = []
    upstream_verification_failed = False

    # Classification is exhaustive: an asset is either a publisher copy or the one derived bundle.
    for asset in assets:
        distribution_form = asset.get("distribution_form")
        modified = asset.get("modified_from_upstream")
        publisher_minified = asset.get("publisher_provided_minified")
        filename = str(asset.get("file") or "")
        if modified is True:
            modified_assets.append(filename)
        minified_filename = ".min." in filename
        modification_matches_form = (
            distribution_form == "transformed-bundle" and modified is True
        ) or (
            distribution_form == "upstream-file-copy" and modified is False
        )
        upstream_hash_matches = (
            modified is True and not asset.get("upstream_sha256")
        ) or (
            modified is False
            and asset.get("upstream_sha256") == asset.get("sha256")
        )
        if (
            distribution_form not in valid_forms
            or not isinstance(modified, bool)
            or not isinstance(publisher_minified, bool)
            or not modification_matches_form
            or not upstream_hash_matches
            or (minified_filename and publisher_minified is not True)
            or (publisher_minified is True and modified is not False)
            or not asset.get("transformation")
            or not asset.get("source_files")
        ):
            unclassified.append(filename or "<unnamed>")

        # No label alone grants an exception; every field must match the reviewed LangChain record.
        if modified is True:
            if (
                filename != LANGCHAIN_BROWSER_EXCEPTION["asset"]
                or distribution_form != LANGCHAIN_BROWSER_EXCEPTION["distribution_form"]
                or publisher_minified is not LANGCHAIN_BROWSER_EXCEPTION["publisher_provided_minified"]
                or asset.get("modification_exception_id") != LANGCHAIN_BROWSER_EXCEPTION["id"]
                or asset.get("transformation") != LANGCHAIN_BROWSER_EXCEPTION["transformation"]
                or asset.get("source_files") != [LANGCHAIN_BROWSER_EXCEPTION["entrypoint"]]
            ):
                failures.append(
                    "browser vendor: transformed asset is not the exact documented LangChain "
                    f"exception: {filename or '<unnamed>'}"
                )
        elif asset.get("modification_exception_id") is not None:
            failures.append(f"browser vendor: upstream copy claims a modification exception: {filename}")

        # The manifest must describe the bytes that learners actually receive.
        delivered = root / "web/nemoclaw/vendor" / filename
        if not delivered.is_file():
            failures.append(f"browser vendor: delivered asset is missing: {filename or '<unnamed>'}")
            upstream_verification_failed = upstream_verification_failed or verify_browser_upstream
        elif asset.get("sha256") != sha256(delivered) or asset.get("bytes") != delivered.stat().st_size:
            failures.append(f"browser vendor: delivered asset hash or size differs from manifest: {filename}")
            upstream_verification_failed = upstream_verification_failed or verify_browser_upstream

        # CI installs the pinned graph so publisher-copy claims can be proven from real inputs.
        if verify_browser_upstream and modified is False:
            source_files = asset.get("source_files") or []
            if len(source_files) != 1:
                failures.append(f"browser vendor: upstream copy must name exactly one publisher file: {filename}")
                upstream_verification_failed = True
                continue
            source = root / str(source_files[0])
            modules = (root / "scripts/browser-vendor/node_modules").resolve()
            if not source.is_file() or not source.resolve().is_relative_to(modules):
                failures.append(f"browser vendor: publisher file is unavailable after npm ci: {filename}")
                upstream_verification_failed = True
            elif not delivered.is_file() or source.read_bytes() != delivered.read_bytes():
                failures.append(f"browser vendor: publisher byte identity failed: {filename}")
                upstream_verification_failed = True
            elif asset.get("upstream_sha256") != sha256(source):
                failures.append(f"browser vendor: publisher source digest differs from manifest: {filename}")
                upstream_verification_failed = True
    if not assets:
        failures.append("browser vendor: manifest must list delivered assets")
    elif unclassified:
        failures.extend(f"browser vendor: missing modification classification: {item}" for item in unclassified)
    else:
        successes.append(f"browser vendor: {len(assets)} delivered asset(s) classify upstream modification status")
    expected_modified = [LANGCHAIN_BROWSER_EXCEPTION["asset"]]
    if sorted(modified_assets) != expected_modified:
        observed = ", ".join(sorted(modified_assets)) or "none"
        failures.append(
            "browser vendor: modified asset set must be exactly "
            f"{LANGCHAIN_BROWSER_EXCEPTION['asset']}; observed {observed}"
        )
    else:
        successes.append(
            "browser vendor: LangChain browser interoperability bundle is the sole documented modification"
        )
    if verify_browser_upstream and not upstream_verification_failed:
        successes.append("browser vendor: every non-exception asset matches its publisher file byte-for-byte")

    shared_manifest_path = root / "web/shared/vendor/browser-dependencies.json"
    try:
        shared_manifest = json.loads(shared_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        failures.append(f"shared browser vendor: unreadable browser-dependencies.json: {error}")
        shared_manifest = {}
    if shared_manifest.get("schema") != "dli-shared-browser-dependencies/1":
        failures.append("shared browser vendor: unexpected or missing manifest schema")
    shared_assets = shared_manifest.get("assets") or []
    described = {str(asset.get("file") or "") for asset in shared_assets}
    delivered_files = {
        path.name for path in (root / "web/shared/vendor").iterdir()
        if path.is_file() and path.suffix.lower() in {".css", ".js", ".mjs"}
    } if (root / "web/shared/vendor").is_dir() else set()
    if not shared_assets or described != delivered_files:
        failures.append("shared browser vendor: manifest must exhaustively describe every delivered asset")
    shared_packages = {f"{item.get('name')}@{item.get('version')}": item for item in shared_manifest.get("packages") or []}
    for package_id, package in shared_packages.items():
        license_file = root / "web/shared/vendor" / str(package.get("license_file") or "")
        if not package.get("license") or not license_file.is_file() or not license_file.stat().st_size:
            failures.append(f"shared browser vendor: missing license evidence for {package_id}")
    for asset in shared_assets:
        filename = str(asset.get("file") or "")
        delivered = root / "web/shared/vendor" / filename
        reviewed = root / str(asset.get("reviewed_copy") or "")
        package_id = str(asset.get("package") or "")
        if package_id not in shared_packages:
            failures.append(f"shared browser vendor: {filename} names an unrecorded package {package_id}")
        if not delivered.is_file() or sha256(delivered) != asset.get("sha256") or delivered.stat().st_size != asset.get("bytes"):
            failures.append(f"shared browser vendor: delivered asset hash or size differs from manifest: {filename}")
        elif not reviewed.is_file() or reviewed.read_bytes() != delivered.read_bytes():
            failures.append(f"shared browser vendor: {filename} differs from its reviewed publisher copy")
    if shared_assets and not any(item.startswith("shared browser vendor:") for item in failures):
        successes.append(f"shared browser vendor: {len(shared_assets)} byte-identical reviewed asset(s) covered")

    return failures, successes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix", action="store_true", help="insert missing headers in authored source files")
    parser.add_argument(
        "--verify-browser-upstream",
        action="store_true",
        help="require npm-installed publisher inputs and compare every non-exception asset byte-for-byte",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    files = repository_files(root)
    changed = apply_headers(root, files) if args.fix else []
    failures, successes = audit(
        root,
        repository_files(root),
        verify_browser_upstream=args.verify_browser_upstream,
    )
    if args.json:
        print(json.dumps({"changed": changed, "ok": successes, "fail": failures}, indent=2))
    else:
        for item in changed:
            print(f"  fixed {item}")
        for item in successes:
            print(f"  ok    {item}")
        for item in failures:
            print(f"  FAIL  {item}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
