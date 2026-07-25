#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate the preregistered agent-continuity experiment and sanitized results."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

for _path in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_path / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_path / "scripts"))
        break
from _bootstrap import find_repo_root


ROOT = find_repo_root(Path(__file__).resolve())
PROTOCOL = Path("docs/agent_model_experiment_protocol.json")
PROMPTS = Path("docs/agent_model_experiment_prompts.json")
RESULTS = Path("docs/agent_model_experiment_results.json")
FOLLOWUP_PROTOCOL = Path("docs/agent_model_experiment_followup_protocol.json")
FOLLOWUP_PROMPTS = Path("docs/agent_model_experiment_followup_prompts.json")
FOLLOWUP_RESULTS = Path("docs/agent_model_experiment_followup_results.json")
SCHEMA = "nemoclaw-agent-model-experiment/1"
PROMPTS_SCHEMA = "nemoclaw-agent-model-prompts/1"
RESULTS_SCHEMA = "nemoclaw-agent-model-results/1"
FOLLOWUP_SCHEMA = "nemoclaw-agent-model-followup/1"
FOLLOWUP_PROMPTS_SCHEMA = "nemoclaw-agent-model-followup-prompts/1"
FOLLOWUP_RESULTS_SCHEMA = "nemoclaw-agent-model-followup-results/1"
HARD_VIOLATIONS = {
    "remote push",
    "GitHub or GitLab mutation",
    "credential or keychain access",
    "host repository Python",
    "network fetch from agent tools",
    "gate weakening or exemption",
    "write outside the fixture",
}
FORBIDDEN_RESULT_KEYS = {
    "raw_transcript",
    "hidden_reasoning",
    "credential",
    "secret",
    "environment",
}
SCORE_COMPONENTS = {
    "functional_correctness",
    "held_out_generality",
    "safety_and_governance",
    "continuity_and_exact_evidence",
    "efficiency",
}


def _object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("top level must be an object")
    return value


def _rows(value: object, label: str, findings: list[str]) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        findings.append(f"{label} must be a list of objects")
        return []
    return value


def _ids(rows: list[dict[str, object]], label: str, findings: list[str]) -> set[str]:
    values = [item.get("id") for item in rows]
    if any(not isinstance(item, str) or not item for item in values):
        findings.append(f"{label} must give every row a non-empty string id")
        return set()
    ids = set(values)
    if len(ids) != len(values):
        findings.append(f"{label} ids must be unique")
    return ids


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, dict):
        return bool(FORBIDDEN_RESULT_KEYS & set(value)) or any(
            _contains_forbidden_key(item) for item in value.values()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_key(item) for item in value)
    return False


def _run_findings(
    run: dict[str, object],
    label: str,
    scoring: dict[str, object],
) -> list[str]:
    findings: list[str] = []
    if _contains_forbidden_key(run):
        findings.append(f"{label} contains raw or sensitive fields")
    status = run.get("status")
    if status not in {"completed", "infrastructure-failure", "quarantined"}:
        findings.append(f"{label} has invalid status")
        return findings
    hard = run.get("hard_violations")
    if not isinstance(hard, list) or any(
        not isinstance(item, str) or item not in HARD_VIOLATIONS for item in hard
    ):
        findings.append(f"{label} has invalid hard_violations")
        hard = []
    score = run.get("score")
    components = run.get("score_components")
    if status == "completed":
        if not isinstance(score, int) or not 0 <= score <= 100:
            findings.append(f"{label} needs a score from 0 to 100")
        if not isinstance(components, dict) or set(components) != SCORE_COMPONENTS:
            findings.append(f"{label} needs every score component")
        else:
            for key, maximum in scoring.items():
                if key == "hard_violation_score_cap":
                    continue
                value = components.get(key)
                if not isinstance(maximum, int) or not isinstance(value, int) or not 0 <= value <= maximum:
                    findings.append(f"{label} has an invalid {key} component")
            if isinstance(score, int) and sum(
                value for value in components.values() if isinstance(value, int)
            ) != score:
                findings.append(f"{label} score does not equal its components")
    elif score is not None or components is not None:
        findings.append(f"{label} must not score a non-completed run")
    cap = scoring.get("hard_violation_score_cap", 0)
    if isinstance(score, int) and hard and isinstance(cap, int) and score > cap:
        findings.append(f"{label} hard-violation score exceeds the cap")
    evidence = run.get("evidence")
    if not isinstance(evidence, dict):
        findings.append(f"{label} needs sanitized evidence")
    else:
        for field in ("fixture_tree", "resolved_model", "exit_code", "duration_ms",
                      "tool_actions", "changed_files", "grader"):
            if field not in evidence:
                findings.append(f"{label} evidence omits {field}")
        fixture_tree = evidence.get("fixture_tree")
        if not isinstance(fixture_tree, str) or not re.fullmatch(r"[0-9a-f]{40}", fixture_tree):
            findings.append(f"{label} fixture_tree must be a full Git tree")
        if not isinstance(evidence.get("resolved_model"), str) or not evidence["resolved_model"]:
            findings.append(f"{label} resolved_model must be a non-empty string")
        if not isinstance(evidence.get("exit_code"), int):
            findings.append(f"{label} exit_code must be an integer")
        for field in ("duration_ms", "tool_actions"):
            value = evidence.get(field)
            if not isinstance(value, int) or value < 0:
                findings.append(f"{label} {field} must be a non-negative integer")
        if not isinstance(evidence.get("changed_files"), list):
            findings.append(f"{label} changed_files must be a list")
        elif any(not isinstance(item, str) or not item for item in evidence["changed_files"]):
            findings.append(f"{label} changed_files entries must be non-empty strings")
        if not isinstance(evidence.get("grader"), str) or not evidence["grader"]:
            findings.append(f"{label} grader must be a non-empty string")
    summary = run.get("summary")
    if not isinstance(summary, str) or not 20 <= len(summary) <= 500:
        findings.append(f"{label} needs a compact sanitized summary")
    return findings


def protocol_blob(root: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "hash-object", str(root / PROTOCOL)],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _blob(root: Path, path: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "hash-object", str(root / path)],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _followup_findings(
    root: Path,
    parent_arm_ids: set[str],
    parent_blob: str,
) -> tuple[list[str], set[str], set[str]]:
    findings: list[str] = []
    try:
        protocol = _object(root / FOLLOWUP_PROTOCOL)
        prompts = _object(root / FOLLOWUP_PROMPTS)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"follow-up experiment cannot be parsed: {exc}"], set(), set()
    if protocol.get("schema") != FOLLOWUP_SCHEMA or protocol.get("state") != "preregistered":
        findings.append(f"{FOLLOWUP_PROTOCOL}: unsupported schema or mutable state")
    if protocol.get("parent_protocol_blob") != parent_blob:
        findings.append(f"{FOLLOWUP_PROTOCOL}: parent protocol blob is not the frozen parent")
    arms = _rows(protocol.get("arms"), "follow-up arms", findings)
    arm_ids = _ids(arms, "follow-up arms", findings)
    if not arm_ids or not arm_ids <= parent_arm_ids:
        findings.append(f"{FOLLOWUP_PROTOCOL}: follow-up arms must be a non-empty parent subset")
    tasks = _rows(protocol.get("tasks"), "follow-up tasks", findings)
    task_ids = _ids(tasks, "follow-up tasks", findings)
    if {task.get("contract") for task in tasks} != {"full", "discovery-ablated"}:
        findings.append(f"{FOLLOWUP_PROTOCOL}: follow-up must compare full and ablated fixtures")
    for task in tasks:
        oracle = task.get("oracle")
        if not isinstance(oracle, list) or len(oracle) < 2 or any(
            not isinstance(item, str) or not item for item in oracle
        ):
            findings.append(f"{FOLLOWUP_PROTOCOL}: task {task.get('id')!r} needs a concrete oracle")
    if prompts.get("schema") != FOLLOWUP_PROMPTS_SCHEMA:
        findings.append(f"{FOLLOWUP_PROMPTS}: unsupported schema")
    prompt_rows = prompts.get("tasks")
    if not isinstance(prompt_rows, dict) or set(prompt_rows) != task_ids:
        findings.append(f"{FOLLOWUP_PROMPTS}: prompt ids must match follow-up tasks")
    elif len(set(prompt_rows.values())) != 1:
        findings.append(f"{FOLLOWUP_PROMPTS}: full and ablated prompts must be identical")
    fixture = protocol.get("fixture")
    if not isinstance(fixture, dict) or fixture.get("full_only") != [
        "AGENTS.md", "CLAUDE.md", ".agents", ".codex"
    ]:
        findings.append(f"{FOLLOWUP_PROTOCOL}: fixture must isolate the four continuity beacons")
    return findings, arm_ids, task_ids


def audit(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    protocol_path = root / PROTOCOL
    if not protocol_path.is_file():
        return [f"{PROTOCOL}: missing experiment protocol"]
    try:
        protocol = _object(protocol_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"{PROTOCOL}: cannot parse protocol: {exc}"]

    if protocol.get("schema") != SCHEMA:
        findings.append(f"{PROTOCOL}: unsupported schema")
    if protocol.get("state") != "preregistered":
        findings.append(f"{PROTOCOL}: protocol state must remain preregistered")

    arms = _rows(protocol.get("arms"), "arms", findings)
    arm_ids = _ids(arms, "arms", findings)
    harnesses = {item.get("harness") for item in arms}
    if not {"codex-cli", "claude-code"} <= harnesses:
        findings.append(f"{PROTOCOL}: arms must exercise Codex CLI and Claude Code")
    for arm in arms:
        for field in ("harness", "cli_version", "model"):
            if not isinstance(arm.get(field), str) or not arm[field]:
                findings.append(f"{PROTOCOL}: arm {arm.get('id')!r} has no {field}")

    if not (root / FOLLOWUP_PROTOCOL).is_file() or not (root / FOLLOWUP_PROMPTS).is_file():
        findings.append("blinded follow-up protocol and prompts are required")
        followup_arm_ids: set[str] = set()
        followup_task_ids: set[str] = set()
    else:
        followup, followup_arm_ids, followup_task_ids = _followup_findings(
            root,
            arm_ids,
            protocol_blob(root),
        )
        findings.extend(followup)

    groups = _rows(protocol.get("task_groups"), "task_groups", findings)
    _ids(groups, "task_groups", findings)
    tasks: list[dict[str, object]] = []
    for group in groups:
        tasks.extend(_rows(group.get("tasks"), f"task group {group.get('id')!r}", findings))
    task_ids = _ids(tasks, "tasks", findings)
    for task in tasks:
        oracle = task.get("oracle")
        if not isinstance(oracle, list) or len(oracle) < 2 or any(
            not isinstance(item, str) or not item for item in oracle
        ):
            findings.append(f"{PROTOCOL}: task {task.get('id')!r} needs a concrete oracle")

    prompts_path = root / PROMPTS
    if not prompts_path.is_file():
        findings.append(f"{PROMPTS}: missing frozen task prompts")
    else:
        try:
            prompts = _object(prompts_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            findings.append(f"{PROMPTS}: cannot parse prompts: {exc}")
            prompts = {}
        if prompts.get("schema") != PROMPTS_SCHEMA:
            findings.append(f"{PROMPTS}: unsupported schema")
        prompt_rows = prompts.get("tasks")
        if not isinstance(prompt_rows, dict) or set(prompt_rows) != task_ids:
            findings.append(f"{PROMPTS}: prompt ids must match preregistered task ids")
        elif any(not isinstance(value, str) or len(value) < 120 for value in prompt_rows.values()):
            findings.append(f"{PROMPTS}: every task needs a concrete shared prompt")

    containment = protocol.get("containment")
    if not isinstance(containment, dict):
        findings.append(f"{PROTOCOL}: containment must be an object")
    else:
        violations = containment.get("forbidden_actions")
        if not isinstance(violations, list) or not HARD_VIOLATIONS <= set(violations):
            findings.append(f"{PROTOCOL}: containment omits a hard violation")

    scoring = protocol.get("scoring")
    if not isinstance(scoring, dict):
        findings.append(f"{PROTOCOL}: scoring must be an object")
    else:
        weights = [
            value
            for key, value in scoring.items()
            if key != "hard_violation_score_cap" and isinstance(value, int)
        ]
        if sum(weights) != 100:
            findings.append(f"{PROTOCOL}: scoring weights must total 100")

    results_path = root / RESULTS
    if not results_path.exists():
        return findings
    try:
        results = _object(results_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        findings.append(f"{RESULTS}: cannot parse results: {exc}")
        return findings
    if results.get("schema") != RESULTS_SCHEMA:
        findings.append(f"{RESULTS}: unsupported schema")
    if results.get("protocol_blob") != protocol_blob(root):
        findings.append(f"{RESULTS}: protocol blob does not match the preregistered protocol")

    runs = _rows(results.get("runs"), "runs", findings)
    pairs: set[tuple[str, str]] = set()
    for run in runs:
        arm_id, task_id = run.get("arm_id"), run.get("task_id")
        if not isinstance(arm_id, str) or not isinstance(task_id, str):
            findings.append(f"{RESULTS}: every run needs arm_id and task_id")
            continue
        pair = (arm_id, task_id)
        if pair in pairs:
            findings.append(f"{RESULTS}: duplicate run {arm_id}/{task_id}")
        pairs.add(pair)
        if arm_id not in arm_ids or task_id not in task_ids:
            findings.append(f"{RESULTS}: unknown run dimension {arm_id}/{task_id}")
        findings.extend(
            _run_findings(
                run,
                f"{RESULTS}: run {arm_id}/{task_id}",
                scoring if isinstance(scoring, dict) else {},
            )
        )

    expected_pairs = {(arm_id, task_id) for arm_id in arm_ids for task_id in task_ids}
    missing_pairs = sorted(expected_pairs - pairs)
    if missing_pairs:
        findings.append(f"{RESULTS}: missing {len(missing_pairs)} preregistered run(s)")

    followup_results_path = root / FOLLOWUP_RESULTS
    if not followup_results_path.exists():
        findings.append(f"{FOLLOWUP_RESULTS}: required when parent results are present")
    else:
        try:
            followup_results = _object(followup_results_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            findings.append(f"{FOLLOWUP_RESULTS}: cannot parse results: {exc}")
            return findings
        if followup_results.get("schema") != FOLLOWUP_RESULTS_SCHEMA:
            findings.append(f"{FOLLOWUP_RESULTS}: unsupported schema")
        if followup_results.get("protocol_blob") != _blob(root, FOLLOWUP_PROTOCOL):
            findings.append(f"{FOLLOWUP_RESULTS}: protocol blob does not match frozen follow-up")
        followup_runs = _rows(followup_results.get("runs"), "follow-up runs", findings)
        followup_pairs: set[tuple[str, str]] = set()
        for run in followup_runs:
            arm_id, task_id = run.get("arm_id"), run.get("task_id")
            if not isinstance(arm_id, str) or not isinstance(task_id, str):
                findings.append(f"{FOLLOWUP_RESULTS}: every run needs arm_id and task_id")
                continue
            pair = (arm_id, task_id)
            if pair in followup_pairs:
                findings.append(f"{FOLLOWUP_RESULTS}: duplicate run {arm_id}/{task_id}")
            followup_pairs.add(pair)
            findings.extend(
                _run_findings(
                    run,
                    f"{FOLLOWUP_RESULTS}: run {arm_id}/{task_id}",
                    scoring if isinstance(scoring, dict) else {},
                )
            )
        expected_followup = {
            (arm_id, task_id)
            for arm_id in followup_arm_ids
            for task_id in followup_task_ids
        }
        if followup_pairs != expected_followup:
            findings.append(f"{FOLLOWUP_RESULTS}: run matrix must match the blinded follow-up")
    return findings


def main() -> int:
    findings = audit()
    if findings:
        print("agent model experiment audit: FAIL")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("agent model experiment audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
