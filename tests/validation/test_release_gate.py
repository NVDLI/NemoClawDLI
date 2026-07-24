# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Behavioral tests for reusable local ReACS gate evidence."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.validation import release_gate


class ReleaseGateCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="release-gate-cache-")
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / "success.json"
        self.commands = [("python", "check.py")]

    def record(self, *, no_write: bool = True, changed_base: str | None = "base") -> None:
        with (
            patch.object(release_gate, "_cache_path", return_value=self.cache),
            patch.object(release_gate, "_head", return_value="a" * 40),
            patch.object(release_gate, "_clean", return_value=True),
            patch.dict(release_gate.os.environ, {}, clear=True),
        ):
            release_gate.record_success(
                tier="ship",
                no_write=no_write,
                commands=self.commands,
                changed_base=changed_base,
                duration=2.5,
                executed=1,
                skipped=0,
            )

    def reuse(self, *, no_write: bool = True, changed_base: str | None = "base") -> dict | None:
        with (
            patch.object(release_gate, "_cache_path", return_value=self.cache),
            patch.object(release_gate, "_head", return_value="a" * 40),
            patch.object(release_gate, "_clean", return_value=True),
        ):
            return release_gate.reusable_success(
                tier="ship",
                no_write=no_write,
                commands=self.commands,
                changed_base=changed_base,
            )

    def test_no_write_success_records_reusable_untracked_evidence(self) -> None:
        self.record(no_write=True)
        cached = self.reuse(no_write=True)
        self.assertIsNotNone(cached)
        self.assertTrue(cached["no_write"])

    def test_mode_and_base_are_part_of_cache_identity(self) -> None:
        self.record(no_write=True, changed_base="base-a")
        self.assertIsNone(self.reuse(no_write=False, changed_base="base-a"))
        self.assertIsNone(self.reuse(no_write=True, changed_base="base-b"))

    def test_corrupt_cache_is_ignored(self) -> None:
        self.cache.write_text("not-json\n", encoding="utf-8")
        self.assertIsNone(self.reuse())

    def test_dirty_tree_is_never_reused(self) -> None:
        self.record()
        with (
            patch.object(release_gate, "_cache_path", return_value=self.cache),
            patch.object(release_gate, "_clean", return_value=False),
        ):
            self.assertIsNone(release_gate.reusable_success(
                tier="ship", no_write=True, commands=self.commands, changed_base="base",
            ))

    def test_read_only_cache_failure_does_not_fail_a_green_gate(self) -> None:
        with (
            patch.object(release_gate, "_cache_path", return_value=self.cache),
            patch.object(release_gate, "_head", return_value="a" * 40),
            patch.object(release_gate, "_clean", return_value=True),
            patch.object(Path, "write_text", side_effect=PermissionError("read only")),
            patch.dict(release_gate.os.environ, {}, clear=True),
        ):
            release_gate.record_success(
                tier="ship", no_write=True, commands=self.commands, changed_base="base",
                duration=1.0, executed=1, skipped=0,
            )

    def test_ci_never_writes_local_reuse_evidence(self) -> None:
        with (
            patch.object(release_gate, "_cache_path", return_value=self.cache),
            patch.object(release_gate, "_clean", return_value=True),
            patch.dict(release_gate.os.environ, {"CI": "1"}, clear=True),
        ):
            release_gate.record_success(
                tier="ship", no_write=True, commands=self.commands, changed_base="base",
                duration=1.0, executed=1, skipped=0,
            )
        self.assertFalse(self.cache.exists())


class ReleaseGateParallelTests(unittest.TestCase):
    def test_parallel_group_preserves_registry_order(self) -> None:
        commands = [
            (sys.executable, "-c", "import time; time.sleep(.04); print('first')"),
            (sys.executable, "-c", "print('second')"),
        ]
        results = release_gate.run_parallel_group(commands, jobs=2, env=os.environ.copy())
        self.assertEqual(["first", "second"], [str(item["output"]).strip() for item in results])
        self.assertEqual([0, 0], [item["returncode"] for item in results])

    def test_parallel_group_keeps_failed_worker_visible(self) -> None:
        commands = [
            (sys.executable, "-c", "print('ok')"),
            (sys.executable, "-c", "raise SystemExit(7)"),
        ]
        results = release_gate.run_parallel_group(commands, jobs=2, env=os.environ.copy())
        self.assertEqual([0, 7], [item["returncode"] for item in results])

    def test_parallel_group_rejects_zero_workers(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            release_gate.run_parallel_group([], jobs=0, env=os.environ.copy())


class ReleaseGateChangeDiscoveryTests(unittest.TestCase):
    def test_name_status_keeps_add_modify_delete_and_both_rename_paths(self) -> None:
        raw = (
            b"A\0new.bin\0M\0docs/readme\0D\0retired.asset\0"
            b"R100\0old/location.txt\0new/location.txt\0"
        )
        rows = release_gate._parse_name_status(raw, "commit")
        self.assertEqual({"commit:A"}, rows["new.bin"])
        self.assertEqual({"commit:M"}, rows["docs/readme"])
        self.assertEqual({"commit:D"}, rows["retired.asset"])
        self.assertEqual({"commit:R100:from"}, rows["old/location.txt"])
        self.assertEqual({"commit:R100:to"}, rows["new/location.txt"])

    def test_malformed_name_status_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "malformed"):
            release_gate._parse_name_status(b"R100\0only-one-path\0", "index")


if __name__ == "__main__":
    unittest.main()
