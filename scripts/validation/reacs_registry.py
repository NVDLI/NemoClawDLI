#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Load and validate the declarative ReACS suite registry.

The registry is proposal-controlled input, so malformed or ambiguous policy must fail before any
selective execution occurs. Current-tree suites always run. Mutation suites may be skipped only
when a valid changed-path set proves that none of their declared inputs changed.
"""
from __future__ import annotations

from dataclasses import dataclass
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path(__file__).with_name("reacs_registry.json")
SCHEMA = "reacs-suite-registry/2"
ID = re.compile(r"^[a-z][a-z0-9-]*$")
GLOB_FORBIDDEN = ("\\", "\n", "\r", "\0")
ARGV_FORBIDDEN = ("\n", "\r", "\0")


class RegistryError(ValueError):
    """Registry policy is invalid and selective execution is unsafe."""


@dataclass(frozen=True)
class Suite:
    id: str
    tiers: tuple[str, ...]
    order: dict[str, int]
    mode: str
    argv: tuple[str, ...]
    impacts: tuple[str, ...]
    parallel_safe: bool
    exclusive_resources: tuple[str, ...]
    write_only: bool
    no_report_args: tuple[str, ...]

    def command(self, *, no_reports: bool, python: str = sys.executable) -> tuple[str, ...] | None:
        if no_reports and self.write_only:
            return None
        command = tuple(python if item == "{python}" else item for item in self.argv)
        if no_reports:
            command += self.no_report_args
        return command


@dataclass(frozen=True)
class Registry:
    path: Path
    raw_bytes: bytes
    suites: tuple[Suite, ...]
    policy_paths: tuple[str, ...]
    default_impact: str

    @property
    def signature(self) -> str:
        return hashlib.sha256(self.raw_bytes).hexdigest()

    def for_tier(self, tier: str, *, no_reports: bool) -> list[tuple[Suite, tuple[str, ...]]]:
        if tier not in {"fast", "ship"}:
            raise RegistryError(f"unsupported ReACS tier: {tier}")
        rows = []
        for suite in sorted(
            (item for item in self.suites if tier in item.tiers),
            key=lambda item: item.order[tier],
        ):
            command = suite.command(no_reports=no_reports)
            if command is not None:
                rows.append((suite, command))
        return rows

    def impact_matches(self, suite: Suite, paths: Iterable[str]) -> bool:
        return any(
            fnmatch.fnmatchcase(path, pattern)
            for path in paths
            for pattern in suite.impacts
        )

    def policy_changed(self, paths: Iterable[str]) -> bool:
        return any(
            fnmatch.fnmatchcase(path, pattern)
            for path in paths
            for pattern in self.policy_paths
        )

    def unclaimed_paths(self, paths: Iterable[str]) -> list[str]:
        """Paths with no specialized detector ownership receive the registry default."""
        mutation = [suite for suite in self.suites if suite.mode == "mutation"]
        return sorted(
            path for path in paths
            if not any(self.impact_matches(suite, (path,)) for suite in mutation)
        )

    @staticmethod
    def structural_change(path_signals: dict[str, set[str]]) -> bool:
        return any(
            signal.split(":", 2)[1][:1] in {"A", "D", "R", "C"}
            for signals in path_signals.values()
            for signal in signals
            if ":" in signal
        )

    def selected_mutations(
        self, paths: set[str] | None, path_signals: dict[str, set[str]] | None = None,
    ) -> tuple[set[str], str]:
        mutation = {suite.id for suite in self.suites if suite.mode == "mutation"}
        if paths is None:
            return mutation, "full-matrix"
        if path_signals and self.structural_change(path_signals):
            return mutation, "structural-change-full-matrix"
        if self.policy_changed(paths):
            return mutation, "policy-change-full-matrix"
        unclaimed = self.unclaimed_paths(paths)
        if unclaimed:
            return mutation, "unclaimed-path-full-matrix"
        selected = {
            suite.id for suite in self.suites
            if suite.mode == "mutation" and self.impact_matches(suite, paths)
        }
        return selected, "change-aware"


def _strings(value: object, label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        raise RegistryError(f"{label} must be {'a non-empty' if nonempty else 'a'} list")
    if not all(isinstance(item, str) and item for item in value):
        raise RegistryError(f"{label} must contain non-empty strings")
    return tuple(value)


def _safe_globs(values: tuple[str, ...], label: str) -> None:
    for value in values:
        if value.startswith(("/", "../")) or "/../" in value or any(token in value for token in GLOB_FORBIDDEN):
            raise RegistryError(f"{label} contains unsafe path pattern: {value!r}")


def _suite(raw: object, index: int) -> Suite:
    if not isinstance(raw, dict):
        raise RegistryError(f"suites[{index}] must be an object")
    required = {"id", "tiers", "order", "mode", "argv", "parallel_safe"}
    allowed = required | {"impacts", "exclusive_resources", "write_only", "no_report_args"}
    missing = required - raw.keys()
    extra = raw.keys() - allowed
    if missing or extra:
        raise RegistryError(f"suites[{index}] fields invalid; missing={sorted(missing)} extra={sorted(extra)}")
    suite_id = raw["id"]
    if not isinstance(suite_id, str) or not ID.fullmatch(suite_id):
        raise RegistryError(f"suites[{index}].id is invalid: {suite_id!r}")
    tiers = _strings(raw["tiers"], f"{suite_id}.tiers", nonempty=True)
    if len(set(tiers)) != len(tiers) or not set(tiers) <= {"fast", "ship"}:
        raise RegistryError(f"{suite_id}.tiers must be unique fast/ship values")
    order = raw["order"]
    if not isinstance(order, dict) or set(order) != set(tiers):
        raise RegistryError(f"{suite_id}.order must name exactly its tiers")
    if not all(isinstance(value, int) and value > 0 for value in order.values()):
        raise RegistryError(f"{suite_id}.order values must be positive integers")
    mode = raw["mode"]
    if mode not in {"current-tree", "mutation"}:
        raise RegistryError(f"{suite_id}.mode must be current-tree or mutation")
    argv = _strings(raw["argv"], f"{suite_id}.argv", nonempty=True)
    for item in argv:
        if any(token in item for token in ARGV_FORBIDDEN):
            raise RegistryError(f"{suite_id}.argv contains a control character")
        placeholders = re.findall(r"\{[^{}]+\}", item)
        if placeholders and (placeholders != ["{python}"] or item != "{python}"):
            raise RegistryError(f"{suite_id}.argv uses an unsupported placeholder: {item!r}")
    impacts = _strings(raw.get("impacts", []), f"{suite_id}.impacts")
    _safe_globs(impacts, f"{suite_id}.impacts")
    if mode == "mutation" and not impacts:
        raise RegistryError(f"mutation suite {suite_id} must declare impacts")
    if mode == "current-tree" and impacts:
        raise RegistryError(f"current-tree suite {suite_id} cannot declare impacts")
    if not isinstance(raw["parallel_safe"], bool):
        raise RegistryError(f"{suite_id}.parallel_safe must be boolean")
    resources = _strings(raw.get("exclusive_resources", []), f"{suite_id}.exclusive_resources")
    if any(not ID.fullmatch(item) for item in resources):
        raise RegistryError(f"{suite_id}.exclusive_resources contains an invalid identifier")
    write_only = raw.get("write_only", False)
    if not isinstance(write_only, bool):
        raise RegistryError(f"{suite_id}.write_only must be boolean")
    no_report_args = _strings(raw.get("no_report_args", []), f"{suite_id}.no_report_args")
    return Suite(
        id=suite_id, tiers=tiers, order=dict(order), mode=mode, argv=argv, impacts=impacts,
        parallel_safe=raw["parallel_safe"], exclusive_resources=resources,
        write_only=write_only, no_report_args=no_report_args,
    )


def load_registry(path: Path = REGISTRY_PATH) -> Registry:
    try:
        raw_bytes = path.read_bytes()
        document = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError(f"cannot load ReACS registry {path}: {exc}") from exc
    required = {"schema", "description", "default_impact", "policy_paths", "suites"}
    if not isinstance(document, dict) or set(document) != required:
        raise RegistryError("registry top-level fields do not match the required schema")
    if document["schema"] != SCHEMA:
        raise RegistryError(f"unsupported ReACS registry schema: {document['schema']!r}")
    if not isinstance(document["description"], str) or not document["description"].strip():
        raise RegistryError("registry description must be non-empty")
    if document["default_impact"] != "full-matrix":
        raise RegistryError("registry default_impact must remain full-matrix")
    policy_paths = _strings(document["policy_paths"], "policy_paths", nonempty=True)
    _safe_globs(policy_paths, "policy_paths")
    suites_raw = document["suites"]
    if not isinstance(suites_raw, list) or not suites_raw:
        raise RegistryError("registry suites must be a non-empty list")
    suites = tuple(_suite(item, index) for index, item in enumerate(suites_raw))
    ids = [suite.id for suite in suites]
    if len(ids) != len(set(ids)):
        raise RegistryError("registry suite identifiers must be unique")
    for tier in ("fast", "ship"):
        orders = [suite.order[tier] for suite in suites if tier in suite.tiers]
        if sorted(orders) != list(range(1, len(orders) + 1)):
            raise RegistryError(f"{tier} suite order must be contiguous and unique")
    return Registry(
        path=path, raw_bytes=raw_bytes, suites=suites, policy_paths=policy_paths,
        default_impact=document["default_impact"],
    )


def main() -> int:
    try:
        registry = load_registry()
    except RegistryError as exc:
        print(f"reacs registry: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        f"reacs registry: PASS schema={SCHEMA} suites={len(registry.suites)} "
        f"signature={registry.signature[:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
