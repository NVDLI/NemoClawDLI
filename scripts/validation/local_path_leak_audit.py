#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject contributor-local paths and identifiers from repository source."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str


PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Windows or WSL user profile",
        re.compile(r"(?:[A-Z]:[\\/]+|/mnt/[a-z]/)Users[\\/]+[^\\/\s\"'<>]+[\\/]+", re.I),
    ),
    (
        "POSIX user home",
        re.compile(r"(?<![A-Za-z0-9_.-])/(?:home|Users)/[^/\s\"'<>]+/"),
    ),
    (
        "WSL UNC user home",
        re.compile(
            r"\\{2,4}(?:wsl(?:\.localhost|\$)?)[\\/]+[^\\/\s\"'<>]+[\\/]+home[\\/]+[^\\/\s\"'<>]+[\\/]+",
            re.I,
        ),
    ),
    (
        "host-mounted directory",
        re.compile(r"(?<![A-Za-z0-9_.-])/(?:media|Volumes)/[^/\s\"'<>]+/"),
    ),
    (
        "workstation temporary directory",
        re.compile(r"(?<![A-Za-z0-9_.-])/(?:private/)?var/folders/[^/\s\"'<>]+/"),
    ),
    (
        "absolute local file URI",
        re.compile(r"(?:file|vscode):/{2,3}(?:tmp|private|var/folders|media|Volumes)/[^\s\"'<>)]*", re.I),
    ),
    (
        "Codex runtime cache",
        re.compile(r"\.cache[\\/]+codex-runtimes[\\/]+", re.I),
    ),
    (
        "contributor-local identifier",
        re.compile(r"\bv[k]udlay\b", re.I),
    ),
)

# These are product/runtime identities, not contributor workstations. Keep each allowance
# bound to one source file; new paths or new consumers require deliberate review.
RUNTIME_ALLOWANCES = {
    # A maintainer identity is necessary and enforceable in the host's ownership file.
    # The same identifier remains prohibited in every other repository path.
    ".gitlab/CODEOWNERS": ("v" + "kudlay",),
}


def isolated_git_env() -> dict[str, str]:
    """Drop hook-provided repository variables before probing another worktree."""
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def repository_files(root: Path = ROOT) -> list[Path]:
    proc = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        env=isolated_git_env(),
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("git ls-files failed; cannot prove repository path hygiene")
    return [root / os.fsdecode(item) for item in proc.stdout.split(b"\0") if item]


def staged_texts(root: Path = ROOT) -> list[tuple[str, str]]:
    proc = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=root,
        env=isolated_git_env(),
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("git diff --cached failed; cannot prove staged path hygiene")
    rows: list[tuple[str, str]] = []
    for item in proc.stdout.split(b"\0"):
        if not item:
            continue
        rel = os.fsdecode(item)
        shown = subprocess.run(
            ["git", "show", f":{rel}"],
            cwd=root,
            env=isolated_git_env(),
            check=False,
            capture_output=True,
        )
        if shown.returncode or b"\0" in shown.stdout:
            continue
        rows.append((rel, shown.stdout.decode("utf-8", errors="replace")))
    return rows


def file_text(path: Path) -> str | None:
    try:
        if path.is_symlink():
            return os.readlink(path)
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def allowed(path: str, value: str) -> bool:
    return any(value.startswith(prefix) for prefix in RUNTIME_ALLOWANCES.get(path, ()))


def scan_text(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[int, str]] = set()
    for kind, pattern in PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if allowed(path, value):
                continue
            line = text.count("\n", 0, match.start()) + 1
            key = (line, kind)
            if key not in seen:
                findings.append(Finding(path, line, kind))
                seen.add(key)
    return findings


def audit(root: Path = ROOT) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    scanned = 0
    for path in repository_files(root):
        text = file_text(path)
        if text is None:
            continue
        scanned += 1
        findings.extend(scan_text(path.relative_to(root).as_posix(), text))
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind)), scanned


def audit_staged(root: Path = ROOT) -> tuple[list[Finding], int]:
    rows = staged_texts(root)
    findings = [finding for path, text in rows for finding in scan_text(path, text)]
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind)), len(rows)


def audit_commit_range(commit_range: str, root: Path = ROOT) -> tuple[list[Finding], int]:
    revs = subprocess.run(
        ["git", "rev-list", "--reverse", commit_range],
        cwd=root,
        env=isolated_git_env(),
        check=False,
        text=True,
        capture_output=True,
    )
    if revs.returncode != 0:
        raise RuntimeError(f"git rev-list failed for {commit_range}")
    findings: list[Finding] = []
    commits = [item for item in revs.stdout.splitlines() if item]
    for commit in commits:
        shown = subprocess.run(
            ["git", "show", "--format=", "--no-ext-diff", "--no-renames", "--unified=0", commit],
            cwd=root,
            env=isolated_git_env(),
            check=False,
            text=True,
            errors="replace",
            capture_output=True,
        )
        if shown.returncode != 0:
            raise RuntimeError(f"git show failed for {commit[:12]}")
        current_path = "unknown"
        for patch_line, line in enumerate(shown.stdout.splitlines(), 1):
            if line.startswith("+++ b/"):
                current_path = line[6:]
                continue
            if not line.startswith("+") or line.startswith("+++"):
                continue
            for finding in scan_text(current_path, line[1:]):
                findings.append(
                    Finding(f"{commit[:12]}:{current_path}", patch_line, finding.kind)
                )
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind)), len(commits)


def self_test() -> list[str]:
    slash = "/"
    backslash = "\\"
    cases = (
        (
            "Windows profile",
            "tool=" + "C:" + backslash + "Users" + backslash + "alice" + backslash + "bin",
            True,
        ),
        ("WSL profile", slash + "mnt/c/Users/alice/project", True),
        (
            "escaped Windows profile",
            "C:" + backslash * 2 + "Users" + backslash * 2 + "alice" + backslash * 2 + "bin",
            True,
        ),
        ("Linux home", slash + "home/alice/project", True),
        ("macOS home", slash + "Users/alice/project", True),
        (
            "WSL UNC",
            backslash * 2 + "wsl.localhost" + backslash + "Ubuntu" + backslash
            + "home" + backslash + "alice" + backslash + "project",
            True,
        ),
        (
            "escaped WSL UNC",
            backslash * 4 + "wsl.localhost" + backslash * 2 + "Ubuntu" + backslash * 2
            + "home" + backslash * 2 + "alice" + backslash * 2 + "project",
            True,
        ),
        ("host mount", slash + "media/disk/alice/project", True),
        ("local file URI", "file:" + slash * 3 + "tmp/report.html", True),
        ("runtime cache", ".cache" + slash + "codex-runtimes" + slash + "node", True),
        ("contributor-local identifier", "v" + "kudlay", True),
        ("declared code owner", "@" + "v" + "kudlay", False),
        ("portable variables", "$HOME/.cache and ${TMPDIR:-/tmp} and file://", False),
    )
    failures: list[str] = []
    for label, sample, should_fail in cases:
        path = ".gitlab/CODEOWNERS" if label == "declared code owner" else "fixture.txt"
        rejected = bool(scan_text(path, sample))
        if rejected != should_fail:
            failures.append(f"{label}: expected rejected={should_fail}, got {rejected}")
    with tempfile.TemporaryDirectory(prefix="local-path-audit-") as temp_dir:
        root = Path(temp_dir)
        git_env = isolated_git_env()
        subprocess.run(["git", "init", "-q"], cwd=root, env=git_env, check=True)
        (root / "tracked.txt").write_text("portable=$HOME/project\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=git_env, check=True)
        (root / "untracked.txt").write_text(slash + "home/alice/project\n", encoding="utf-8")
        rows, _ = audit(root)
        if not any(row.path == "untracked.txt" for row in rows):
            failures.append("working-tree discovery: untracked path leak was not rejected")
        (root / "tracked.txt").write_text(slash + "home/alice/staged\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=git_env, check=True)
        rows, _ = audit_staged(root)
        if not any(row.path == "tracked.txt" for row in rows):
            failures.append("staged-index discovery: proposed path leak was not rejected")
        (root / "tracked.txt").write_text("portable=$HOME/project\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=git_env, check=True)
        link = root / "runtime-link"
        try:
            link.symlink_to("C:" + backslash + "Users" + backslash + "alice" + backslash + "node.exe")
            rows, _ = audit(root)
            if not any(row.path == "runtime-link" for row in rows):
                failures.append("symlink discovery: local target was not rejected")
        except OSError as exc:
            failures.append(f"symlink discovery could not run: {exc}")
        link.unlink(missing_ok=True)
        (root / "untracked.txt").unlink()
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
             "commit", "-qm", "clean base"],
            cwd=root,
            env=git_env,
            check=True,
        )
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, env=git_env, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
        (root / "tracked.txt").write_text(slash + "home/alice/project\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=git_env, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
             "commit", "-qm", "introduce leak"],
            cwd=root,
            env=git_env,
            check=True,
        )
        (root / "tracked.txt").write_text("portable=$HOME/project\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=git_env, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
             "commit", "-qm", "remove leak"],
            cwd=root,
            env=git_env,
            check=True,
        )
        rows, _ = audit_commit_range(f"{base}..HEAD", root)
        if not any(row.path.endswith(":tracked.txt") for row in rows):
            failures.append("commit-range discovery: removed intermediate leak was not rejected")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--staged", action="store_true", help="scan exact file content staged in the Git index")
    parser.add_argument("--commit-range", help="also reject path additions in every commit in RANGE")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        print("local path leak self-test: " + ("FAIL" if failures else "PASS"))
        for finding in failures:
            print("  FAIL " + finding)
        return 1 if failures else 0

    try:
        findings, scanned = audit_staged() if args.staged else audit()
        commits = 0
        if args.commit_range:
            range_findings, commits = audit_commit_range(args.commit_range)
            findings.extend(range_findings)
    except RuntimeError as exc:
        print(f"local path leak audit: FAIL: {exc}")
        return 1
    if findings:
        print("local path leak audit: FAIL")
        for finding in findings:
            print(f"  {finding.path}:{finding.line}: {finding.kind}")
        return 1
    suffix = f", {commits} commits" if args.commit_range else ""
    label = "staged files" if args.staged else "text files"
    print(f"local path leak audit: OK ({scanned} {label}{suffix})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
