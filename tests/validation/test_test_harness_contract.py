# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject hand-maintained test totals and misleading self-test reporting."""
from __future__ import annotations

import ast
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.skills import gen_directory_beacons, skill_audit


ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = tuple(ROOT / name for name in ("scripts", "workspace", "cpu", "deploy"))
EXCLUDED_PARTS = {"node_modules", "vendor", "mats", "artifacts", "public", "__pycache__"}
FRACTION = re.compile(
    r"(?:self[- _]?test[^\n]*(?:\{[^}]+\}\s*/\s*\{[^}]+\}|"
    r"[\"']\s*\+\s*[\"']/[\"']\s*\+|\b\d+\s*/\s*\d+\b)|"
    r"\b\d+\s*/\s*\d+\b[^\n]*(?:self[- ]?test|mutation detectors?))",
    re.I,
)
LITERAL_MUTATIONS = re.compile(r"(?:PASS|passed)[^\n]*\b\d+\s+mutations?\b", re.I)


def owned_files(*suffixes: str):
    for root in SCAN_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in suffixes or EXCLUDED_PARTS.intersection(path.parts):
                continue
            yield path


def fixed_total_lines(text: str, filename: str = "fixture.py") -> list[int]:
    if "--self-test" not in text and "def self_test" not in text:
        return []
    tree = ast.parse(text, filename=filename)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, int) or value.value <= 0:
            continue
        if any(isinstance(target, ast.Name) and target.id == "total" for target in targets):
            lines.append(node.lineno)
    return lines


def literal_minus_failure_lines(text: str, filename: str = "fixture.py") -> list[int]:
    tree = ast.parse(text, filename=filename)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Sub):
            continue
        if not isinstance(node.left, ast.Constant) or not isinstance(node.left.value, int):
            continue
        call = node.right
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "len":
            continue
        if call.args and isinstance(call.args[0], ast.Name) and call.args[0].id == "failures":
            lines.append(node.lineno)
    return lines


class TestHarnessContract(unittest.TestCase):
    def test_deleted_tracked_files_do_not_reenter_skill_indexes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="skill-source-set-") as directory:
            root = Path(directory)
            (root / "live.js").write_text("export {};\n", encoding="utf-8")
            git_rows = b"live.js\0deleted.js\0"
            with patch.object(gen_directory_beacons, "ROOT", root), patch(
                "scripts.skills.gen_directory_beacons.subprocess.check_output", return_value=git_rows,
            ):
                self.assertEqual([Path("live.js")], gen_directory_beacons.source_files())
            with patch.object(skill_audit, "TASK1", root), patch(
                "scripts.skills.skill_audit.subprocess.check_output", return_value=git_rows,
            ):
                self.assertEqual([Path("live.js")], skill_audit.source_files())

    def test_no_literal_pass_denominators(self) -> None:
        findings = []
        for path in owned_files(".py", ".js", ".mjs", ".sh"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number, line in enumerate(text.splitlines(), 1):
                if FRACTION.search(line) or LITERAL_MUTATIONS.search(line):
                    findings.append(f"{path.relative_to(ROOT)}:{line_number}: {line.strip()}")
        self.assertEqual([], findings, "hard-coded test report totals:\n" + "\n".join(findings))

    def test_no_fixed_total_variables_in_self_test_modules(self) -> None:
        findings = []
        for path in owned_files(".py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for line_number in fixed_total_lines(text, str(path)):
                findings.append(f"{path.relative_to(ROOT)}:{line_number}")
        self.assertEqual([], findings, "fixed self-test totals:\n" + "\n".join(findings))

    def test_no_literal_minus_failure_count(self) -> None:
        findings = []
        for path in owned_files(".py"):
            text = path.read_text(encoding="utf-8")
            for line_number in literal_minus_failure_lines(text, str(path)):
                findings.append(f"{path.relative_to(ROOT)}:{line_number}")
        self.assertEqual([], findings, "literal total minus failures:\n" + "\n".join(findings))

    def test_detects_literal_fraction_fixture(self) -> None:
        line = 'print("audit self-test: 24/24 mutation detectors passed")'
        self.assertIsNotNone(FRACTION.search(line))

    def test_detects_dynamic_fraction_fixture(self) -> None:
        line = 'print(f"audit self-test: {passed}/{total} passed")'
        self.assertIsNotNone(FRACTION.search(line))

    def test_detects_literal_mutation_count_fixture(self) -> None:
        line = 'print("audit self-test: PASS (13 mutations rejected)")'
        self.assertIsNotNone(LITERAL_MUTATIONS.search(line))

    def test_detects_fixed_total_fixture(self) -> None:
        source = 'def self_test():\n    total = 14\n    return total\n'
        self.assertEqual([2], fixed_total_lines(source))

    def test_detects_literal_minus_failures_fixture(self) -> None:
        source = 'def self_test(failures):\n    return 7 - len(failures)\n'
        self.assertEqual([2], literal_minus_failure_lines(source))


if __name__ == "__main__":
    unittest.main()
