# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public-checkout execution tests without personal tooling or credentials."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from scripts.build import course_contribute as public

ROOT = Path(__file__).resolve().parents[2]


class PublicContributionTests(unittest.TestCase):
    def test_tracked_graph_matches_current_discovered_source(self):
        result = subprocess.run(["bash", "scripts/runtime/run_engine.sh", "--graph-json"],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        marker = re.search(r"let DATA = (.*);", (ROOT / "scripts/runtime/link_graph.html").read_text())
        self.assertIsNotNone(marker, "Tracked graph is missing its DATA marker")
        self.assertTrue(json.loads(marker.group(1)) == json.loads(result.stdout),
                        "Tracked graph is stale; run bash scripts/runtime/run_engine.sh --embed and commit the projection")

    def test_gate_commands_preserve_full_validation_and_explicit_fork_base(self):
        for mode, tier in (("fast-gate", "fast"), ("ship-gate", "ship")):
            self.assertEqual(public.commands(mode, None, "public"), [[sys.executable,
                             "scripts/validation/release_gate.py", "--tier", tier, "--no-write"]])
            command = public.commands(mode, "upstream/main", "public")[0]
            self.assertEqual(command[-2:], ["--changed-since", "upstream/main"])

    def test_build_cannot_reuse_report_or_refresh_materials(self):
        with mock.patch.dict(os.environ, {"BUILD_PAGES_PULL_MATERIALS": "1", "BUILD_PAGES_REUSE_VALIDATION": "1"}), \
             mock.patch.object(public.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertEqual(0, public.main(["--repo", str(ROOT), "build-pages"]))
        self.assertEqual(run.call_args.kwargs["env"]["BUILD_PAGES_PULL_MATERIALS"], "0")
        self.assertEqual(run.call_args.kwargs["env"]["BUILD_PAGES_REUSE_VALIDATION"], "0")
        self.assertEqual(run.call_args.args[0], ["bash", "scripts/build/build_pages.sh", "public"])

    def test_doctor_stops_at_first_failed_probe(self):
        with mock.patch.object(public.subprocess, "run", return_value=subprocess.CompletedProcess([], 9)) as run:
            self.assertEqual(9, public.main(["--repo", str(ROOT), "doctor"]))
            self.assertEqual(1, run.call_count)

    def test_invalid_arguments_never_execute(self):
        for arguments in (("candidate",), ("doctor", "--changed-since", "main"),
                          ("ship-gate", "--changed-since=-malformed"), ("doctor", "--output", "elsewhere")):
            with self.subTest(arguments=arguments), mock.patch.object(public.subprocess, "run") as run:
                with self.assertRaises(SystemExit):
                    public.main(["--repo", str(ROOT), *arguments])
                run.assert_not_called()

    def test_no_repository_python_on_mac(self):
        with mock.patch.object(public.sys, "platform", "darwin"), mock.patch.object(public.subprocess, "run") as run:
            with self.assertRaises(SystemExit):
                public.main(["--repo", str(ROOT), "doctor"])
            run.assert_not_called()

    def test_public_checkout_without_personal_configuration(self):
        # Exercise the actual entry point in a new checkout-shaped tree. Only a fake
        # gate replaces expensive course checks; there are no private helper files.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts/build").mkdir(parents=True)
            (root / "scripts/validation").mkdir()
            (root / "home").mkdir()
            for name in ("course_contribute.py", "course_contribute.sh"):
                shutil.copyfile(ROOT / "scripts/build" / name, root / "scripts/build" / name)
            (root / "scripts/validation/release_gate.py").write_text(
                "import sys\nassert sys.argv[1:] == ['--tier', 'fast', '--no-write']\nprint('public-gate-executed')\n")
            env = {"PATH": os.environ["PATH"], "HOME": str(root / "home"), "GIT_CONFIG_NOSYSTEM": "1"}
            result = subprocess.run(["bash", str(root / "scripts/build/course_contribute.sh"), "fast-gate"],
                                    env=env, capture_output=True, text=True, check=False)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("public-gate-executed", result.stdout)
            self.assertEqual([], list((root / "home").iterdir()))

    def test_executor_arguments_are_literal_and_failure_never_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / "executor"
            runner.write_text("#!/bin/sh\ntest -z \"${COURSE_CONTRIBUTE_RUNNER:-}\" || exit 99\nprintf '%s\\n' \"$@\"\nexit 19\n")
            runner.chmod(0o700)
            attack = "$(touch unwanted); literal"
            env = {"PATH": os.environ["PATH"], "HOME": directory, "COURSE_CONTRIBUTE_RUNNER": str(runner)}
            result = subprocess.run(["bash", str(ROOT / "scripts/build/course_contribute.sh"), "fast-gate",
                                     "--changed-since", attack], cwd=directory, env=env,
                                    capture_output=True, text=True, check=False)
            self.assertEqual(19, result.returncode)
            self.assertEqual(["--repo", str(ROOT), "fast-gate", "--changed-since", attack], result.stdout.splitlines())
            self.assertFalse((Path(directory) / "unwanted").exists())

    def test_lifecycle_commands_are_rejected_before_delegation(self):
        with tempfile.TemporaryDirectory() as directory:
            runner = Path(directory) / "executor"
            marker = Path(directory) / "called"
            runner.write_text("#!/bin/sh\ntouch " + str(marker) + "\n")
            runner.chmod(0o700)
            for mode in ("candidate", "submit", "merge", "repair-signature", "unknown"):
                with self.subTest(mode=mode):
                    result = subprocess.run(["bash", str(ROOT / "scripts/build/course_contribute.sh"), mode],
                                            env={"PATH": os.environ["PATH"], "COURSE_CONTRIBUTE_RUNNER": str(runner)},
                                            capture_output=True, text=True, check=False)
                    self.assertEqual(2, result.returncode)
                    self.assertFalse(marker.exists())

    def test_invalid_executor_never_runs_local_gate(self):
        entry = ROOT / "scripts/build/course_contribute.sh"
        for runner in ("relative-executor", "/missing-executor", str(entry)):
            with self.subTest(runner=runner):
                result = subprocess.run(["bash", str(entry), "fast-gate"],
                                        env={"PATH": os.environ["PATH"], "COURSE_CONTRIBUTE_RUNNER": runner},
                                        capture_output=True, text=True, check=False)
                self.assertEqual(2, result.returncode)
                self.assertIn("separate absolute executable", result.stderr)
