#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject new course-specific validators while preserving narrow frozen baselines.

Universal validators discover applicable course form factors. Existing specialized files may stay
only as exact owner-gated migration baselines; they add checks and cannot exempt a course from any
universal suite. Added course literals in validator code fail over the proposed commit range.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
POLICY = Path(__file__).with_name("reacs_specialization_exceptions.json")
REGISTRY = Path(__file__).with_name("reacs_registry.json")
SCHEMA = "reacs-specialization-exceptions/1"
SCAN_ROOTS = ("scripts/validation", "scripts/pyodide", "tests/validation", "tests/runtime")
VALID_SUFFIXES = {".py", ".js", ".mjs", ".cjs", ".ts"}
COURSE_NAMED = re.compile(r"(?:^|[_-])({keys})(?:[_-]|\.)", re.I)
UNIVERSAL_DIMENSIONS = {
    "accessibility", "artifact-integrity", "credential-boundary", "dependency-security",
    "html-links", "syntax", "theme",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def course_keys(root: Path = ROOT) -> list[str]:
    return sorted(path.parent.name for path in (root / "web").glob("*/interface-inventory.json"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], text=True, capture_output=True, check=False,
    )


def _range_base(root: Path, commit_range: str) -> str | None:
    left = commit_range.split("...", 1)[0] if "..." in commit_range else commit_range.split("..", 1)[0]
    proc = _git(root, "rev-parse", "--verify", f"{left}^{{commit}}")
    return proc.stdout.strip() if proc.returncode == 0 else None


def _git_file(root: Path, revision: str, rel: str) -> bytes | None:
    proc = subprocess.run(
        ["git", "-C", str(root), "show", f"{revision}:{rel}"], capture_output=True, check=False,
    )
    return proc.stdout if proc.returncode == 0 else None


def _suite_index(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        return {}
    return {
        str(suite.get("id")): suite
        for suite in document.get("suites", [])
        if isinstance(suite, dict) and suite.get("id")
    }


def _history_allowances(root: Path, commit_range: str) -> tuple[set[str], set[str], bool]:
    """Return exact owner-declared baselines and whether policy literals are safe.

    An exception names the commit where the specialized bytes were reviewed. The file and suite
    must still be byte-for-byte identical, and that commit must remain an ancestor of the proposal.
    This permits an explicit migration baseline without letting a policy entry bless mutable code.
    """
    range_base = _range_base(root, commit_range)
    if not range_base:
        return set(), set(), False
    try:
        policy = _load(root / POLICY.relative_to(ROOT))
        current_registry = _load(root / REGISTRY.relative_to(ROOT))
    except (OSError, json.JSONDecodeError):
        return set(), set(), False
    current_suites = _suite_index(current_registry)
    frozen: set[str] = set()
    frozen_registry: set[str] = set()
    policy_safe = True
    entries = policy.get("entries", []) if isinstance(policy, dict) else []
    if not entries:
        return frozen, frozen_registry, policy_safe
    for entry in entries:
        if not isinstance(entry, dict):
            policy_safe = False
            continue
        entry_safe = True
        baseline_commit = str(entry.get("baseline_commit", ""))
        ancestor = _git(root, "merge-base", "--is-ancestor", baseline_commit, "HEAD")
        if (
            not re.fullmatch(r"[0-9a-f]{40}", baseline_commit)
            or baseline_commit == _git(root, "rev-parse", "HEAD").stdout.strip()
            or ancestor.returncode != 0
        ):
            entry_safe = False
        base_registry_raw = _git_file(root, baseline_commit, REGISTRY.relative_to(ROOT).as_posix())
        try:
            base_registry = json.loads(base_registry_raw) if base_registry_raw is not None else None
        except json.JSONDecodeError:
            base_registry = None
            entry_safe = False
        base_suites = _suite_index(base_registry)
        files = entry.get("files", {})
        if not isinstance(files, dict) or not files:
            entry_safe = False
        else:
            for rel, expected in files.items():
                baseline = _git_file(root, baseline_commit, str(rel))
                current = root / str(rel)
                if (
                    baseline is None
                    or not current.is_file()
                    or hashlib.sha256(baseline).hexdigest() != expected
                    or _sha(current) != expected
                ):
                    entry_safe = False
        registry_ids = entry.get("registry_ids", [])
        if not isinstance(registry_ids, list):
            entry_safe = False
        else:
            for suite_id in registry_ids:
                if base_suites.get(str(suite_id)) != current_suites.get(str(suite_id)):
                    entry_safe = False
        if entry_safe:
            frozen.update(map(str, files))
            frozen_registry.update(map(str, registry_ids))
        else:
            policy_safe = False
    return frozen, frozen_registry, policy_safe


def _policy(root: Path, findings: list[str]) -> tuple[set[str], set[str]]:
    path = root / POLICY.relative_to(ROOT)
    try:
        policy = _load(path)
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(f"{path.relative_to(root)}: cannot parse specialization policy: {exc}")
        return set(), set()
    if not isinstance(policy, dict) or policy.get("schema") != SCHEMA:
        findings.append(f"{path.relative_to(root)}: expected schema {SCHEMA}")
        return set(), set()
    expected_top_level = {"schema", "allowed_dimensions", "forbidden_dimensions", "entries"}
    if set(policy) != expected_top_level:
        findings.append(f"{path.relative_to(root)}: policy fields must be exact")
    allowed_dimensions = set(policy.get("allowed_dimensions", []))
    forbidden_dimensions = set(policy.get("forbidden_dimensions", []))
    if forbidden_dimensions != UNIVERSAL_DIMENSIONS or allowed_dimensions & forbidden_dimensions:
        findings.append(f"{path.relative_to(root)}: universal dimensions cannot be excepted or reclassified")
    allowed_files: set[str] = set()
    allowed_registry: set[str] = set()
    seen_ids: set[str] = set()
    keys = set(course_keys(root))
    for entry in policy.get("entries", []):
        if not isinstance(entry, dict):
            findings.append(f"{path.relative_to(root)}: exception entry must be an object")
            continue
        required = {
            "id", "course", "dimension", "rationale", "owning_contract", "migration",
            "baseline_commit", "files", "registry_ids",
        }
        if set(entry) != required:
            findings.append(f"{path.relative_to(root)}: exception fields must be exact")
            continue
        if entry["id"] in seen_ids:
            findings.append(f"{path.relative_to(root)}: duplicate exception id {entry['id']}")
        seen_ids.add(entry["id"])
        if entry["course"] not in keys or entry["dimension"] not in allowed_dimensions:
            findings.append(f"{path.relative_to(root)}: exception {entry['id']} has unknown course or dimension")
        if not all(isinstance(entry[key], str) and entry[key].strip() for key in ("rationale", "owning_contract", "migration")):
            findings.append(f"{path.relative_to(root)}: exception {entry['id']} needs rationale, owner contract, and migration")
        if not re.fullmatch(r"[0-9a-f]{40}", str(entry["baseline_commit"])):
            findings.append(f"{path.relative_to(root)}: exception {entry['id']} needs one full baseline commit")
        owner = root / entry["owning_contract"]
        if not owner.is_file():
            findings.append(f"{path.relative_to(root)}: owning contract is missing for {entry['id']}")
        files = entry["files"]
        if not isinstance(files, dict) or not files:
            findings.append(f"{path.relative_to(root)}: exception {entry['id']} needs exact file fingerprints")
            continue
        for rel, expected in files.items():
            target = root / rel
            if not target.is_file() or not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
                findings.append(f"{path.relative_to(root)}: invalid exception file record {rel}")
            elif _sha(target) != expected:
                findings.append(f"{rel}: specialized baseline changed; migrate the check or obtain owner review for a new fingerprint")
            allowed_files.add(rel)
        registry_ids = entry["registry_ids"]
        if not isinstance(registry_ids, list) or not all(isinstance(item, str) and item for item in registry_ids):
            findings.append(f"{path.relative_to(root)}: exception {entry['id']} registry_ids must be strings")
        else:
            allowed_registry.update(registry_ids)
    return allowed_files, allowed_registry


def audit(root: Path = ROOT, commit_range: str | None = None) -> list[str]:
    findings: list[str] = []
    allowed_files, allowed_registry = _policy(root, findings)
    keys = course_keys(root)
    if not keys:
        return findings + ["web/: no discovered course keys for specialization policy"]
    name_pattern = re.compile(COURSE_NAMED.pattern.format(keys="|".join(map(re.escape, keys))), re.I)

    for base in SCAN_ROOTS:
        directory = root / base
        for path in directory.rglob("*") if directory.is_dir() else ():
            if not path.is_file() or path.suffix.lower() not in VALID_SUFFIXES:
                continue
            rel = path.relative_to(root).as_posix()
            if name_pattern.search(path.name) and rel not in allowed_files:
                findings.append(f"{rel}: course-named validator or test needs a narrow frozen exception or generic form-factor implementation")

    try:
        registry = _load(root / REGISTRY.relative_to(ROOT))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(f"{REGISTRY.relative_to(ROOT)}: cannot parse ReACS registry: {exc}")
    else:
        for suite in registry.get("suites", []):
            suite_id = str(suite.get("id", ""))
            command = " ".join(map(str, suite.get("argv", [])))
            if (name_pattern.search(suite_id) or any(key in command.lower() for key in keys)) and suite_id not in allowed_registry:
                findings.append(f"{REGISTRY.relative_to(ROOT)}: course-specialized suite {suite_id!r} is not a frozen exception")

    if commit_range:
        history_allowed_files, history_allowed_registry, policy_literals_safe = _history_allowances(root, commit_range)
        policy_rel = POLICY.relative_to(ROOT).as_posix()
        registry_rel = REGISTRY.relative_to(ROOT).as_posix()
        specialized_registry = {
            str(suite.get("id", ""))
            for suite in registry.get("suites", [])
            if isinstance(suite, dict) and (
                name_pattern.search(str(suite.get("id", "")))
                or any(key in " ".join(map(str, suite.get("argv", []))).lower() for key in keys)
            )
        }
        registry_literals_safe = bool(specialized_registry) and specialized_registry <= history_allowed_registry
        proc = subprocess.run(
            ["git", "-C", str(root), "diff", "--unified=0", "--no-ext-diff", commit_range, "--", *SCAN_ROOTS],
            text=True, capture_output=True,
        )
        if proc.returncode:
            findings.append(f"git diff failed for specialization range: {commit_range}")
        else:
            current = ""
            for line in proc.stdout.splitlines():
                if line.startswith("+++ b/"):
                    current = line[6:]
                    continue
                if not line.startswith("+") or line.startswith("+++"):
                    continue
                lowered = line.lower()
                if any(f"web/{key}" in lowered or re.search(rf"[\"']{re.escape(key)}[\"']", lowered) for key in keys):
                    allowed_history = current in history_allowed_files
                    allowed_policy = current == policy_rel and policy_literals_safe
                    allowed_registry = current == registry_rel and registry_literals_safe
                    if not allowed_history and not allowed_policy and not allowed_registry:
                        findings.append(f"{current}: proposed validator code adds a course-specific literal")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit-range")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = audit(commit_range=args.commit_range)
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, indent=2))
    elif findings:
        print(f"validator specialization: FAIL ({len(findings)})")
        for item in findings:
            print(f"  {item}")
    else:
        print("validator specialization: OK")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
