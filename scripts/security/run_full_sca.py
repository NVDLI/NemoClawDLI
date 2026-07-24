#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run or print the full SCA/SBOM commands for the built environment.

The fast source gate catches vulnerable floors before a build. This wrapper is the
agent-discoverable entry point for installed-environment scans and SBOM output.
It never installs tools; CI or the operator provides them.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = Path("/tmp/nemoclaw-security-reports")


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def command_available(command: list[str]) -> bool:
    if not command:
        return False
    exe = command[0]
    if exe == sys.executable and len(command) >= 3 and command[1] == "-m":
        probe = subprocess.run(
            [sys.executable, "-m", command[2], "--help"],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return probe.returncode == 0
    return shutil.which(exe) is not None


def run_step(name: str, command: list[str], *, out: Path, require_tools: bool, execute: bool) -> dict:
    available = command_available(command)
    result: dict = {"name": name, "command": command, "available": available}
    if not available:
        result["status"] = "missing-tool" if require_tools else "skipped"
        return result
    if not execute:
        result["status"] = "planned"
        return result

    out.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    result["returncode"] = completed.returncode
    result["status"] = "passed" if completed.returncode == 0 else "failed"
    return result


def planned_steps(args: argparse.Namespace, out: Path) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = []
    if args.python_local or args.all_available:
        python_audit = [sys.executable, "-m", "pip_audit"]
        if args.python_path:
            python_audit.extend(["--path", args.python_path])
        else:
            python_audit.append("--local")
        python_audit.extend(["--strict", "--format", "json", "--output", str(out / "pip-audit-local.json")])
        steps.append((
            "pip-audit installed Python environment",
            python_audit,
        ))
    if args.cyclonedx_env or args.all_available:
        cyclonedx = ["cyclonedx-py", "environment"]
        if args.python_executable:
            cyclonedx.append(args.python_executable)
        cyclonedx.extend(["--output-reproducible", "--of", "JSON",
                          "--output-file", str(out / "python-env.cdx.json")])
        steps.append((
            "CycloneDX SBOM for Python environment",
            cyclonedx,
        ))
    if args.osv_source or args.all_available:
        steps.append((
            "OSV-Scanner source scan",
            ["osv-scanner", "scan", "source", "--format", "json", "--output-file", str(out / "osv-source.json"), "."],
        ))
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=os.environ.get("NEMOCLAW_SECURITY_REPORT_DIR", str(DEFAULT_OUT)))
    parser.add_argument("--require-tools", action="store_true", help="fail when a selected scanner is unavailable")
    parser.add_argument("--execute", action="store_true", help="run selected scanners instead of printing the plan")
    parser.add_argument("--all-available", action="store_true", help="select all source/environment scanners that are installed")
    parser.add_argument("--python-local", action="store_true", help="run pip-audit against installed Python environment")
    parser.add_argument("--cyclonedx-env", action="store_true", help="write CycloneDX SBOM for installed Python environment")
    parser.add_argument("--python-executable", help="Python interpreter whose environment CycloneDX should inventory")
    parser.add_argument("--python-path", help="site-packages path pip-audit should inspect instead of the scanner environment")
    parser.add_argument("--osv-source", action="store_true", help="run OSV-Scanner source scan")
    parser.add_argument("--json", action="store_true", help="emit machine-readable report")
    args = parser.parse_args()

    selected = any((args.all_available, args.python_local, args.cyclonedx_env, args.osv_source))
    if not selected:
        args.all_available = True
        args.execute = False

    out = Path(args.out_dir)
    results = [
        run_step(name, command, out=out, require_tools=args.require_tools, execute=args.execute)
        for name, command in planned_steps(args, out)
    ]
    ok = all(step["status"] in {"planned", "passed", "skipped"} for step in results)
    report = {"ok": ok, "mode": "execute" if args.execute else "plan", "out_dir": rel(out), "steps": results}

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"full SCA mode: {report['mode']}")
        print(f"report dir: {out}")
        for step in results:
            marker = "OK" if step["status"] in {"planned", "passed"} else ("SKIP" if step["status"] == "skipped" else "FAIL")
            print(f"{marker} {step['name']}: {step['status']}")
            print("  " + " ".join(step["command"]))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
