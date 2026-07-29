#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit repository-local Codex skills and compaction continuity hooks."""
from __future__ import annotations

import json
import hashlib
import os
import re
import stat
import subprocess
import sys
import tomllib
from pathlib import Path

for _path in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_path / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_path / "scripts"))
        break
from _bootstrap import find_repo_root


ROOT = find_repo_root(Path(__file__).resolve())
SCHEMA = "nemoclaw-codex-continuity/1"
CONTRACT_PATH = Path(".codex/continuity-contract.json")
CONFIG_PATH = Path(".codex/config.toml")
AGENTS_PATH = Path("AGENTS.md")
CLAUDE_PATH = Path("CLAUDE.md")
ROOT_SKILL_PATH = Path("SKILL.html")

REQUIRED_CHECKPOINT_FIELDS = {
    "objective",
    "terminal_condition",
    "issue_branch_pull_request",
    "exact_local_remote_main_sha",
    "artifact_workflow_deployment",
    "constraints_and_authority",
    "verified_evidence",
    "current_failure",
    "remaining_actions",
    "terminal_owner",
}
REQUIRED_INVARIANTS = {
    "preserve-terminal-condition",
    "exact-head-evidence",
    "remote-commit-round-trip",
    "live-policy-discovery",
    "fail-fast-before-expensive",
    "changed-surface-preflight",
    "generated-projection-round-trip",
    "one-terminal-owner",
    "no-host-repository-python",
}
REQUIRED_REMOTE_ASSERTIONS = {"parent", "tree", "verified-signature", "dco-trailers"}
REQUIRED_SKILL_TOKENS = {
    "/hooks",
    "trusted checkout",
    "do not read transcripts",
    "bypass hook trust",
}
REQUIRED_CREDENTIAL_BINDING_ROWS = {
    "GITLAB_DLI": "| `GITLAB_DLI` | `gitlab.com/nvidia/DLI` |",
    "NEMOCLAWDLI_GITHUB": (
        "| `NEMOCLAWDLI_GITHUB` | `github.com/NVDLI/NemoClawDLI` |"
    ),
    "NEMOCLAW_DLIOS": (
        "| `NEMOCLAW_DLIOS` | internal GitLab `NemoClawDLIOS` origin; "
        "owner from `.gitlab/CODEOWNERS` |"
    ),
}
REQUIRED_CREDENTIAL_SAFETY_TOKENS = {
    "gitlab_master.com",
    "Never substitute",
    "NEMOCLAW_DLI_PAT",
    "Do not launch OAuth",
    "prompt for credentials",
}
REQUIRED_METADATA_FIELDS = {"display_name", "short_description", "default_prompt"}
SKILL_MANIFEST = "SKILL.md"
SKILL_METADATA = Path("agents/openai.yaml")
EXPECTED_EVENTS = {
    "SessionStart": {
        "matcher": "startup|resume|clear|compact",
        "phase": "session-start",
        "status": "Reconstructing the contribution checkpoint",
    },
    "PreCompact": {
        "matcher": "manual|auto",
        "phase": "pre-compact",
        "status": "Checking the contribution checkpoint before compaction",
    },
    "PostCompact": {
        "matcher": "manual|auto",
        "phase": "post-compact",
        "status": "Reconciling the contribution checkpoint after compaction",
    },
}
EXPECTED_HOOK_SHA256 = "8e445d2f715730d7be3859d51e3cc19f481a45e5ce75cf43b2d8089033aee428"
EXPECTED_HARNESS_CAPABILITIES = {
    "codex": {"entry": "AGENTS.md", "lifecycle_reminders": True},
    "claude-code": {"entry": "CLAUDE.md", "lifecycle_reminders": False},
}
HOOK_PATH = Path(".codex/hooks/continuity.sh")
HOOK_INTERPRETER = "#!/bin/sh\n"
HOOK_SHELL_OPTIONS = "set -eu"
HOOK_CASE_OPEN = 'case "$phase" in'
HOOK_PAYLOAD = '{"systemMessage":"%s"}'
HOOK_EMITTER = 'printf \'{"systemMessage":"%s"}\\n\' "$message"'
HOOK_MESSAGE_PREFIX = "NemoClawDLI continuity reminder"
_HOOK_COMMENT = re.compile(r"\A#[^\\]*\Z")
_HOOK_PHASE_BINDING = re.compile(r"\Aphase=\$\{1:-([a-z][a-z-]*)\}\Z")
_HOOK_CASE_LABEL = re.compile(r"\A(\*|[a-z][a-z-]*)\)\Z")
_HOOK_MESSAGE = re.compile(r"\Amessage='([^'\\]*)'\Z")


def _source_files(root: Path) -> list[Path]:
    try:
        raw = subprocess.check_output(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())
    return sorted(Path(os.fsdecode(item)) for item in raw.split(b"\0") if item)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("top level must be an object")
    return value


def _repo_path(base: Path, relative: Path) -> Path:
    """Collapse repository-relative ``..`` segments without resolving symlinks."""
    return Path(os.path.normpath((base / relative).as_posix()))


def _is_regular_repo_file(root: Path, relative: Path) -> bool:
    """Require a regular file reached without an absolute path, traversal, or symlink."""
    if relative.is_absolute():
        return False
    candidate = root
    mode = None
    for part in relative.parts:
        if part in ("", "."):
            continue
        if part == "..":
            return False
        candidate /= part
        try:
            mode = candidate.lstat().st_mode
        except OSError:
            return False
        if stat.S_ISLNK(mode):
            return False
    return mode is not None and stat.S_ISREG(mode)


def _read_utf8(root: Path, relative: Path, findings: list[str]) -> str | None:
    try:
        return (root / relative).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        findings.append(f"{relative}: must be a readable UTF-8 file")
        return None


def _skill_frontmatter(raw: str) -> tuple[str, str] | None:
    match = re.match(r"\A---\n(.*?)\n---\n", raw, re.DOTALL)
    if not match:
        return None
    name = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", match.group(1))
    description = re.search(r"(?m)^description:\s*(.+?)\s*$", match.group(1))
    if not name or not description:
        return None
    return name.group(1), description.group(1)


def _skill_metadata(raw: str) -> dict[str, str] | None:
    lines = raw.splitlines()
    if not lines or lines[0] != "interface:":
        return None
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line and not line[0].isspace():
            break
        match = re.fullmatch(r'  ([a-z_]+):\s*(".*")\s*', line)
        if not match or match.group(1) not in REQUIRED_METADATA_FIELDS:
            continue
        key = match.group(1)
        if key in values:
            return None
        try:
            value = json.loads(match.group(2))
        except json.JSONDecodeError:
            return None
        if not isinstance(value, str):
            return None
        values[key] = value
    return values if values.keys() == REQUIRED_METADATA_FIELDS else None


def _metadata_findings(path: Path, name: str, raw: str) -> list[str]:
    metadata = _skill_metadata(raw)
    if metadata is None:
        return [f"{path}: interface metadata is malformed or incomplete"]
    findings: list[str] = []
    if not metadata["display_name"].strip():
        findings.append(f"{path}: display_name must be a non-empty string")
    short_description = metadata["short_description"]
    if not 25 <= len(short_description) <= 64:
        findings.append(f"{path}: short_description must contain 25 to 64 characters")
    if f"${name}" not in metadata["default_prompt"]:
        findings.append(f"{path}: default_prompt must invoke ${name}")
    return findings


def _string_set(
    contract: dict[str, object],
    key: str,
    path: Path,
    findings: list[str],
) -> set[str]:
    value = contract.get(key)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        findings.append(f"{path}: {key} must be a list of strings")
        return set()
    return set(value)


def _inside_native_skill_root(path: Path, package: Path) -> bool:
    """Return whether ``package`` follows an ``.agents/skills`` root in ``path``."""
    parts = path.parts
    package_length = len(package.parts)
    return any(
        parts[index:index + 2] == (".agents", "skills") and index + 2 < package_length
        for index in range(max(0, package_length - 1))
    )


def _project_skill_packages(
    files: list[Path],
) -> list[tuple[Path, Path | None, tuple[Path, ...]]]:
    """Discover native packages from either required artifact or a manifest near-match."""
    packages: set[Path] = set()
    candidates: dict[Path, set[Path]] = {}
    for path in files:
        package: Path | None = None
        if (
            path.name.casefold().startswith("skill.")
            and path.name.casefold() != "skill.html"
        ):
            package = path.parent
            candidates.setdefault(package, set()).add(path)
        elif len(path.parts) >= 3 and path.parts[-2:] == SKILL_METADATA.parts:
            package = path.parent.parent
        if package is None or not _inside_native_skill_root(path, package):
            continue
        packages.add(package)
    rows: list[tuple[Path, Path | None, tuple[Path, ...]]] = []
    for package in sorted(packages):
        package_candidates = tuple(sorted(candidates.get(package, set())))
        exact = next(
            (path for path in package_candidates if path.name == SKILL_MANIFEST),
            None,
        )
        rows.append((package, exact or (package_candidates[0] if package_candidates else None),
                     package_candidates))
    return rows


def _hook_groups(config: dict[str, object], event: str) -> list[dict[str, object]]:
    hooks = config.get("hooks", {})
    if not isinstance(hooks, dict):
        return []
    groups = hooks.get(event, [])
    return [group for group in groups if isinstance(group, dict)] if isinstance(groups, list) else []


def _hook_effect_findings(path: Path, raw: str, phases: list[str]) -> list[str]:
    """Require the unattended hook to be only a literal-message emitter."""
    findings: list[str] = []
    if not raw.startswith(HOOK_INTERPRETER):
        findings.append(f"{path}: hook must declare the reviewed {HOOK_INTERPRETER.strip()} interpreter")
    lines = raw.split("\n")
    if lines[-1:] == [""]:
        lines.pop()
    else:
        findings.append(f"{path}: hook must end with a single trailing newline")

    labels: list[str] = []
    messages: list[str] = []
    state = "options"
    for number, line in enumerate(lines, start=1):
        statement = line.strip()
        if not statement:
            continue
        if statement.startswith("#"):
            if not _HOOK_COMMENT.fullmatch(statement):
                findings.append(f"{path}:{number}: comment must not continue onto the next line")
                return findings
            continue
        if state == "options" and statement == HOOK_SHELL_OPTIONS:
            state = "binding"
            continue
        if state == "binding":
            match = _HOOK_PHASE_BINDING.fullmatch(statement)
            if match:
                if match.group(1) not in phases:
                    findings.append(
                        f"{path}:{number}: default phase {match.group(1)!r} is not a lifecycle phase"
                    )
                state = "case"
                continue
        elif state == "case" and statement == HOOK_CASE_OPEN:
            state = "label"
            continue
        elif state == "label":
            match = _HOOK_CASE_LABEL.fullmatch(statement)
            if match:
                labels.append(match.group(1))
                state = "message"
                continue
            if statement == "esac":
                state = "emit"
                continue
        elif state == "message":
            match = _HOOK_MESSAGE.fullmatch(statement)
            if match:
                messages.append(match.group(1))
                state = "break"
                continue
        elif state == "break" and statement == ";;":
            state = "label"
            continue
        elif state == "emit" and statement == HOOK_EMITTER:
            state = "end"
            continue
        findings.append(
            f"{path}:{number}: statement is outside the reviewed hook grammar: {statement!r}"
        )
        return findings

    if findings:
        return findings
    if state != "end":
        return [f"{path}: hook must end with the single reviewed message emitter"]
    if labels[-1:] != ["*"]:
        findings.append(f"{path}: hook must close its case with a default phase branch")
    covered = labels[:-1] if labels[-1:] == ["*"] else labels
    if sorted(covered) != sorted(phases) or len(set(covered)) != len(covered):
        findings.append(
            f"{path}: hook phase branches {covered} differ from the lifecycle oracle {phases}"
        )
    for index, message in enumerate(messages, start=1):
        try:
            payload = json.loads(HOOK_PAYLOAD % message)
        except json.JSONDecodeError:
            findings.append(f"{path}: message {index} does not emit a valid hook payload")
            continue
        if not str(payload.get("systemMessage", "")).startswith(HOOK_MESSAGE_PREFIX):
            findings.append(f"{path}: message {index} is not a {HOOK_MESSAGE_PREFIX}")
    return findings


def audit(root: Path = ROOT, files: list[Path] | None = None) -> list[str]:
    source_files = files if files is not None else _source_files(root)
    source_set = set(source_files)
    findings: list[str] = []

    for package, skill_path, manifest_candidates in _project_skill_packages(source_files):
        if skill_path is None:
            findings.append(f"{package / SKILL_MANIFEST}: native skill payload is missing")
            continue
        for candidate in manifest_candidates:
            if candidate.name != SKILL_MANIFEST:
                findings.append(f"{candidate}: skill manifest must be named {SKILL_MANIFEST}")
        if not _is_regular_repo_file(root, skill_path):
            findings.append(
                f"{skill_path}: must be a regular repository file without symlink components"
            )
            continue
        skill_raw = _read_utf8(root, skill_path, findings)
        if skill_raw is None:
            continue
        parsed = _skill_frontmatter(skill_raw)
        if not parsed:
            findings.append(f"{skill_path}: missing valid name/description frontmatter")
            continue
        name, description = parsed
        if name != package.name:
            findings.append(f"{skill_path}: skill name {name!r} must match directory {package.name!r}")
        if len(description) < 40:
            findings.append(f"{skill_path}: description is too short to support implicit discovery")
        metadata_path = package / SKILL_METADATA
        if metadata_path not in source_set:
            findings.append(f"{metadata_path}: skill UI metadata is missing")
        elif not _is_regular_repo_file(root, metadata_path):
            findings.append(
                f"{metadata_path}: must be a regular repository file without symlink components"
            )
        else:
            metadata_raw = _read_utf8(root, metadata_path, findings)
            if metadata_raw is None:
                continue
            findings.extend(
                _metadata_findings(
                    metadata_path,
                    package.name,
                    metadata_raw,
                )
            )

    missing_required: list[Path] = []
    for required in (CONTRACT_PATH, CONFIG_PATH, AGENTS_PATH, CLAUDE_PATH, ROOT_SKILL_PATH):
        if required not in source_set:
            findings.append(f"{required}: required Codex continuity file is missing")
            missing_required.append(required)
        elif not _is_regular_repo_file(root, required):
            findings.append(
                f"{required}: must be a regular repository file without symlink components"
            )
            missing_required.append(required)

    if missing_required:
        return findings

    try:
        contract = _read_json(root / CONTRACT_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"{CONTRACT_PATH}: cannot parse continuity contract: {exc}"]
    if contract.get("schema") != SCHEMA:
        findings.append(f"{CONTRACT_PATH}: unsupported schema {contract.get('schema')!r}")

    checkpoint_fields = _string_set(contract, "checkpoint_fields", CONTRACT_PATH, findings)
    missing_fields = sorted(REQUIRED_CHECKPOINT_FIELDS - checkpoint_fields)
    if missing_fields:
        findings.append(f"{CONTRACT_PATH}: missing checkpoint fields: {', '.join(missing_fields)}")

    invariants = _string_set(contract, "invariants", CONTRACT_PATH, findings)
    missing_invariants = sorted(REQUIRED_INVARIANTS - invariants)
    if missing_invariants:
        findings.append(f"{CONTRACT_PATH}: missing invariants: {', '.join(missing_invariants)}")

    assertions = _string_set(contract, "remote_commit_assertions", CONTRACT_PATH, findings)
    missing_assertions = sorted(REQUIRED_REMOTE_ASSERTIONS - assertions)
    if missing_assertions:
        findings.append(f"{CONTRACT_PATH}: missing remote commit assertions: {', '.join(missing_assertions)}")

    skill_rel = Path(str(contract.get("skill", "")))
    normalized_skill = _repo_path(CONTRACT_PATH.parent, skill_rel)
    if normalized_skill not in source_set:
        findings.append(f"{CONTRACT_PATH}: referenced contribution skill is missing: {normalized_skill}")
        skill_raw = ""
    elif not _is_regular_repo_file(root, normalized_skill):
        findings.append(
            f"{normalized_skill}: must be a regular repository file without symlink components"
        )
        skill_raw = ""
    else:
        skill_raw = _read_utf8(root, normalized_skill, findings) or ""
    for invariant in sorted(REQUIRED_INVARIANTS):
        if invariant not in skill_raw:
            findings.append(f"{normalized_skill}: missing continuity invariant {invariant}")
    for token in sorted(REQUIRED_SKILL_TOKENS):
        if token not in skill_raw:
            findings.append(f"{normalized_skill}: missing hook trust boundary {token!r}")
    for credential, binding in sorted(REQUIRED_CREDENTIAL_BINDING_ROWS.items()):
        if binding not in skill_raw:
            findings.append(
                f"{normalized_skill}: missing exclusive credential binding {credential}"
            )
    for token in sorted(REQUIRED_CREDENTIAL_SAFETY_TOKENS):
        if token not in skill_raw:
            findings.append(
                f"{normalized_skill}: missing credential safety boundary {token!r}"
            )

    agents_raw = _read_utf8(root, AGENTS_PATH, findings) or ""
    for token in (normalized_skill.as_posix(), CONTRACT_PATH.as_posix()):
        if token not in agents_raw:
            findings.append(f"{AGENTS_PATH}: missing Codex continuity route {token}")
    claude_raw = _read_utf8(root, CLAUDE_PATH, findings) or ""
    if claude_raw.strip() != "# Claude Code entry point\n\n@AGENTS.md":
        findings.append(f"{CLAUDE_PATH}: must import AGENTS.md without duplicating its directives")
    beacons = _string_set(contract, "harness_beacons", CONTRACT_PATH, findings)
    if beacons != {AGENTS_PATH.as_posix(), CLAUDE_PATH.as_posix()}:
        findings.append(f"{CONTRACT_PATH}: harness_beacons must bind Codex and Claude entry points")
    root_skill_raw = _read_utf8(root, ROOT_SKILL_PATH, findings) or ""
    for beacon in sorted(beacons):
        if not re.search(rf'href=["\']{re.escape(beacon)}["\']', root_skill_raw):
            findings.append(f"{ROOT_SKILL_PATH}: missing navigable harness beacon {beacon}")
    if contract.get("harness_capabilities") != EXPECTED_HARNESS_CAPABILITIES:
        findings.append(
            f"{CONTRACT_PATH}: harness_capabilities must distinguish Codex reminders from Claude fallback"
        )

    try:
        config = tomllib.loads((root / CONFIG_PATH).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        findings.append(f"{CONFIG_PATH}: cannot parse project config: {exc}")
        return findings
    features = config.get("features", {})
    if not isinstance(features, dict) or features.get("hooks") is not True:
        findings.append(f"{CONFIG_PATH}: trusted project must enable lifecycle hooks")

    event_contracts = contract.get("events")
    expected_contract_events = {
        event: {"matcher": values["matcher"], "phase": values["phase"]}
        for event, values in EXPECTED_EVENTS.items()
    }
    if event_contracts != expected_contract_events:
        findings.append(f"{CONTRACT_PATH}: events differ from the independent lifecycle oracle")

    hook_rel = Path(str(contract.get("hook", "")))
    declared_hook = _repo_path(CONTRACT_PATH.parent, hook_rel)
    if declared_hook != HOOK_PATH:
        findings.append(
            f"{CONTRACT_PATH}: declared hook {declared_hook} is not the hook the config executes"
        )
    hook_path = HOOK_PATH
    if hook_path not in source_set:
        findings.append(f"{CONTRACT_PATH}: referenced hook is missing: {hook_path}")
        hook_raw = ""
    elif not _is_regular_repo_file(root, hook_path):
        findings.append(
            f"{hook_path}: must be a regular repository file without symlink components"
        )
        hook_raw = ""
    else:
        hook_raw = _read_utf8(root, hook_path, findings) or ""
        if hook_raw:
            hook_digest = hashlib.sha256(hook_raw.encode("utf-8")).hexdigest()
            if hook_digest != EXPECTED_HOOK_SHA256:
                findings.append(f"{hook_path}: executable hook differs from the reviewed canonical body")
            findings.extend(
                _hook_effect_findings(
                    hook_path,
                    hook_raw,
                    [values["phase"] for values in EXPECTED_EVENTS.values()],
                )
            )

    hooks_table = config.get("hooks")
    if not isinstance(hooks_table, dict) or set(hooks_table) != set(EXPECTED_EVENTS):
        findings.append(f"{CONFIG_PATH}: hook events differ from the independent lifecycle oracle")
    for event, expected in sorted(EXPECTED_EVENTS.items()):
        groups = _hook_groups(config, event)
        if len(groups) != 1:
            findings.append(f"{CONFIG_PATH}: {event} must have one continuity hook group")
            continue
        group = groups[0]
        if set(group) != {"matcher", "hooks"}:
            findings.append(f"{CONFIG_PATH}: {event} hook group has unexpected fields")
        if group.get("matcher") != expected["matcher"]:
            findings.append(f"{CONFIG_PATH}: {event} matcher differs from the lifecycle oracle")
        handlers = group.get("hooks", [])
        if not isinstance(handlers, list) or len(handlers) != 1 or not isinstance(handlers[0], dict):
            findings.append(f"{CONFIG_PATH}: {event} must have one command handler")
            continue
        handler = handlers[0]
        expected_handler = {
            "type": "command",
            "command": (
                f'sh "$(git rev-parse --show-toplevel)/{HOOK_PATH.as_posix()}" '
                f'{expected["phase"]}'
            ),
            "timeout": 5,
            "statusMessage": expected["status"],
        }
        if handler != expected_handler:
            findings.append(f"{CONFIG_PATH}: {event} handler differs from the reviewed command")

    if hook_raw:
        for phase in sorted(values["phase"] for values in EXPECTED_EVENTS.values()):
            if phase not in hook_raw:
                findings.append(f"{hook_path}: missing declared hook phase {phase}")
        if CONTRACT_PATH.as_posix() not in hook_raw:
            findings.append(f"{hook_path}: hook output does not route back to the continuity contract")

    return findings


def main() -> int:
    findings = audit()
    if findings:
        print("Codex continuity audit: FAIL")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Codex continuity audit: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
