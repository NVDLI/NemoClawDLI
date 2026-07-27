#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit GitHub-facing agent publishers for bounded identity, data, and authority."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[2]
BRIDGE_MARKERS = ("/check-runs", "AGENT_GITHUB_TOKEN_FILE", "AGENT_TRANSPARENCY_BRIDGE")
FORBIDDEN_SOURCE = {
    "shell=True": "do not run publisher input through a shell",
    "os.system(": "do not run publisher input through a shell",
    "print(token": "never print a bot token",
    "logger.info(token": "never log a bot token",
    '"administration": "write"': "do not grant repository administration",
    '"workflows": "write"': "do not let the agent edit workflows",
    '"environments": "write"': "do not let the agent edit environments",
    '["push", "--force': "do not let the agent rewrite a remote ref",
}
REQUIRED_SOURCE = (
    'AGENT_TRANSPARENCY_BRIDGE = True',
    '"AGENT_GITHUB_TOKEN_FILE"',
    'token.startswith("github_pat_")',
    "group or others",
    '"/user"',
    'permissions.get("admin") is True',
    'branch in {"main", "master"}',
    "event sequence must increase",
    "COMMENT_MARKER",
    '"push", "--porcelain"',
    "GIT_TRACE_CURL",
    "Signed-off-by",
    "cryptographic commit signature",
    'verification.get("verified") is not True',
)
REQUIRED_DOC = (
    "dedicated bot account",
    "human contributor",
    "commit author",
    "Developer Certificate of Origin",
    "fine-grained personal access token",
    "one repository",
    "Do not grant the account administrator or maintainer authority",
    "prompts, model messages",
    "token file",
)
EXPECTED_BOT_PERMISSIONS = {
    "checks": "write",
    "contents": "write",
    "issues": "write",
}


def declared_permissions(path: str, text: str) -> tuple[dict[str, str] | None, list[str]]:
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError:
        return None, [f"{path}: publisher source must parse as Python"]
    values = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "REQUIRED_PERMISSIONS" for target in targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            return None, [f"{path}: REQUIRED_PERMISSIONS must be a literal mapping"]
        values.append(value)
    if len(values) != 1 or not isinstance(values[0], dict):
        return None, [f"{path}: exactly one REQUIRED_PERMISSIONS mapping is required"]
    if values[0] != EXPECTED_BOT_PERMISSIONS:
        return values[0], [
            f"{path}: bot token permissions must be exactly checks, contents, and issues at write level"
        ]
    return values[0], []


def repository_texts(root: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for path in sorted((root / "scripts" / "ci").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in BRIDGE_MARKERS):
            rows[path.relative_to(root).as_posix()] = text
    doc = root / "docs" / "agent-github-bot.md"
    schema = root / "scripts" / "ci" / "agent-transparency.schema.json"
    if doc.is_file():
        rows[doc.relative_to(root).as_posix()] = doc.read_text(encoding="utf-8")
    if schema.is_file():
        rows[schema.relative_to(root).as_posix()] = schema.read_text(encoding="utf-8")
    return rows


def audit_texts(rows: dict[str, str]) -> list[str]:
    findings: list[str] = []
    bridges = {
        path: text for path, text in rows.items()
        if path.endswith(".py") and any(marker in text for marker in BRIDGE_MARKERS)
    }
    if not bridges:
        findings.append("no GitHub agent publisher was discovered from content")
    for path, text in bridges.items():
        _, permission_findings = declared_permissions(path, text)
        findings.extend(permission_findings)
        for token, fix in FORBIDDEN_SOURCE.items():
            if token in text:
                findings.append(f"{path}: {fix}")
        for token in REQUIRED_SOURCE:
            if token not in text:
                findings.append(f"{path}: missing authority or reuse contract {token!r}")
    docs = [text for path, text in rows.items() if path.endswith("/agent-github-bot.md")]
    if len(docs) != 1:
        findings.append("exactly one agent GitHub bot operator document is required")
    else:
        for token in REQUIRED_DOC:
            if token not in docs[0]:
                findings.append(f"agent GitHub bot document is missing {token!r}")
    schemas = [text for path, text in rows.items() if path.endswith("agent-transparency.schema.json")]
    if len(schemas) != 1:
        findings.append("exactly one public agent event schema is required")
    else:
        try:
            schema = json.loads(schemas[0])
        except json.JSONDecodeError:
            findings.append("public agent event schema must be valid JSON")
        else:
            if schema.get("additionalProperties") is not False:
                findings.append("public agent event schema must reject unknown fields")
    return findings


def audit(root: Path = ROOT) -> list[str]:
    return audit_texts(repository_texts(root))


def self_test() -> list[str]:
    source = (ROOT / "scripts" / "ci" / "github_agent_bridge.py").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "agent-github-bot.md").read_text(encoding="utf-8")
    schema = (ROOT / "scripts" / "ci" / "agent-transparency.schema.json").read_text(encoding="utf-8")
    base = {
        "scripts/ci/renamed_publisher.py": source,
        "docs/agent-github-bot.md": doc,
        "scripts/ci/agent-transparency.schema.json": schema,
    }
    failures = []
    mutations = {
        "newly-named-publisher": {
            **base,
            "scripts/ci/future_publisher.py": source.replace(
                "AGENT_TRANSPARENCY_BRIDGE = True", "AGENT_TRANSPARENCY_BRIDGE = False", 1,
            ),
        },
        "arbitrary-shell": {
            **base,
            "scripts/ci/renamed_publisher.py": source + "\nsubprocess.run(value, shell=True)\n",
        },
        "token-log": {
            **base,
            "scripts/ci/renamed_publisher.py": source + "\nprint(token)\n",
        },
        "remote-rewrite": {
            **base,
            "scripts/ci/renamed_publisher.py": source.replace(
                '["push", "--porcelain"', '["push", "--force", "--porcelain"', 1,
            ),
        },
        "extra-bot-permission": {
            **base,
            "scripts/ci/renamed_publisher.py": source.replace(
                '    "checks": "write",',
                '    "actions": "read",\n    "checks": "write",',
                1,
            ),
        },
        "protected-ref": {
            **base,
            "scripts/ci/renamed_publisher.py": source.replace(
                'branch in {"main", "master"}', 'branch in {"never"}',
            ),
        },
        "unknown-event-fields": {
            **base,
            "scripts/ci/agent-transparency.schema.json": schema.replace(
                '"additionalProperties": false', '"additionalProperties": true', 1,
            ),
        },
        "missing-operator-doc": {
            path: text for path, text in base.items() if not path.endswith("agent-github-bot.md")
        },
    }
    for name, rows in mutations.items():
        if not audit_texts(rows):
            failures.append(f"mutation escaped: {name}")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "scripts" / "ci").mkdir(parents=True)
        (root / "docs").mkdir()
        for path, text in base.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        if audit(root):
            failures.append("renamed valid fixture did not pass discovery")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    findings = self_test() if args.self_test else audit()
    if findings:
        print(f"agent transparency audit: FAIL ({len(findings)})")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("agent transparency audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
