#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject security-finding details and private operational data from contributions."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
DEFAULT_POLICY = ROOT / "scripts" / "validation" / "sensitive-content-policy.json"
PRIVATE_POLICY_ENV = "SENSITIVE_CONTENT_POLICY_FILE"
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
HOST_RE = re.compile(r"(?<![A-Za-z0-9.-])(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?![A-Za-z0-9.-])")
IDENTIFIER_RES = (
    re.compile(
        r"\b(?P<prefix>[A-Z][A-Z0-9]{1,11})[\s:_-]+20\d{2}[\s:_-]+\d{3,}\b",
        re.I,
    ),
    re.compile(
        r"\b(?P<prefix>[A-Z][A-Z0-9]{2,11})(?:[\s:_-]+[A-Z0-9]{4}){2,3}\b",
        re.I,
    ),
    re.compile(r"\b(?P<prefix>[A-Z][A-Z0-9]{2,11})[\s:_-]+\d{4,}\b", re.I),
)
# Launchable host families supported by the course runtime. A provisioned instance publishes
# itself as <label>-<instance-id>.<family>, so the identifier is ephemeral infrastructure that
# must never be recorded. Fixtures keep the family and describe the instance with any segment
# length other than the provisioned one.
LAUNCHABLE_HOST_SUFFIXES = ("brevlab.com", "apps.run.brev.nvidia.com")
INSTANCE_ID_RE = re.compile(r"[a-z0-9]{9}")
DIRECT_PATTERNS = (
    ("private key material", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("cloud access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("source-host access token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,})\b")),
    ("collaboration access token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("signed bearer credential", re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("credential-bearing URL", re.compile(r"https?://[^\s/@:]+:[A-Za-z0-9._~-]{12,}@", re.I)),
    ("cloud account locator", re.compile(r"\barn:aws(?:-us-gov|-cn)?:[^:\s]*:[^:\s]*:\d{12}:", re.I)),
    ("corporate personal email", re.compile(r"\b[A-Za-z0-9._%+-]+@nvidia\.com\b", re.I)),
)
PUBLIC_ROLE_EMAILS = frozenset({"psirt@nvidia.com"})
PATH_PHRASE_ALLOWANCES = {
    # Ownership files must name a real host principal. Keep this single-token allowance
    # scoped to CODEOWNERS; the same identity stays blocked in prose, code, and metadata.
    ".gitlab/CODEOWNERS": frozenset({"v" + "kudlay"}),
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str


@dataclass(frozen=True)
class Policy:
    prefixes: frozenset[str]
    phrases: frozenset[str]
    hosts: frozenset[str]
    max_phrase_tokens: int


def format_finding(item: Finding) -> str:
    """Render an untrusted path without permitting log-control characters."""
    return f"{json.dumps(item.path, ensure_ascii=True)}:{item.line}: {item.kind}"


def digest(value: str) -> str:
    return hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()


def ephemeral_instance_host(host: str) -> bool:
    """Report whether a launchable hostname carries a provisioned instance identifier.

    The identifier is one alphanumeric segment of the launchable-specific prefix whose
    length matches a provisioned instance. Matching on shape rather than on a known value
    keeps discovery exhaustive: a new instance, a new label, and a deeper prefix all fail
    without touching a denylist.
    """
    for suffix in LAUNCHABLE_HOST_SUFFIXES:
        if not host.endswith("." + suffix):
            continue
        prefix = host[: -(len(suffix) + 1)]
        if any(INSTANCE_ID_RE.fullmatch(segment) for segment in re.split(r"[.-]", prefix)):
            return True
    return False


def isolated_git_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def read_policy(path: Path) -> Policy:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read sensitive-content policy {path}: {exc}") from exc
    if data.get("schema") != "sensitive-content-policy/1":
        raise RuntimeError(f"unsupported sensitive-content policy schema in {path}")

    def hashes(field: str) -> frozenset[str]:
        values = data.get(field)
        if not isinstance(values, list) or any(not re.fullmatch(r"[0-9a-f]{64}", str(v)) for v in values):
            raise RuntimeError(f"{field} must contain lowercase SHA-256 values in {path}")
        return frozenset(str(v) for v in values)

    maximum = data.get("max_phrase_tokens", 6)
    if not isinstance(maximum, int) or not 1 <= maximum <= 12:
        raise RuntimeError(f"max_phrase_tokens must be an integer from 1 to 12 in {path}")
    return Policy(
        hashes("blocked_prefix_sha256"),
        hashes("blocked_phrase_sha256"),
        hashes("blocked_host_sha256"),
        maximum,
    )


def load_policy(default: Path = DEFAULT_POLICY) -> Policy:
    policies = [read_policy(default)]
    extra = os.environ.get(PRIVATE_POLICY_ENV)
    if extra:
        policies.append(read_policy(Path(extra)))
    return Policy(
        frozenset().union(*(item.prefixes for item in policies)),
        frozenset().union(*(item.phrases for item in policies)),
        frozenset().union(*(item.hosts for item in policies)),
        max(item.max_phrase_tokens for item in policies),
    )


def repository_files(root: Path = ROOT) -> list[Path]:
    probe = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=root,
        env=isolated_git_env(), check=False, capture_output=True, text=True,
    )
    if probe.returncode or Path(probe.stdout.strip()).resolve() != root.resolve():
        return source_archive_files(root)
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        env=isolated_git_env(),
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("git ls-files failed; cannot prove sensitive-content hygiene")
    return [root / os.fsdecode(item) for item in result.stdout.split(b"\0") if item]


def source_archive_files(root: Path) -> list[Path]:
    """Discover source in a git archive used by protected-ref Pages builds."""
    if not root.is_dir():
        raise RuntimeError(f"source root is not a directory: {root}")
    skipped_paths = {"public", "docs/validation", "scripts/security/reports"}
    skipped_names = {
        ".git", ".cache", ".figtools", "__pycache__", "node_modules",
        "grounding_cache", ".release-runtime-venv", ".release-scan-venv",
        ".sca-runtime-venv", ".sca-tools-venv",
    }
    rows: list[Path] = []
    for current, dirs, files in os.walk(root, followlinks=False):
        base = Path(current)
        dirs[:] = [
            name for name in dirs
            if name not in skipped_names
            and (base / name).relative_to(root).as_posix() not in skipped_paths
        ]
        rows.extend(base / name for name in files)
    return sorted(rows)


def staged_texts(root: Path = ROOT) -> list[tuple[str, str]]:
    """Read exact proposed file content from the Git index, not the mutable worktree."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=root,
        env=isolated_git_env(),
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("git diff --cached failed; cannot prove staged sensitive-content hygiene")
    rows: list[tuple[str, str]] = []
    for item in result.stdout.split(b"\0"):
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
        if shown.returncode:
            continue
        rows.append((rel, shown.stdout.decode("utf-8", errors="replace")))
    return rows


def git_tree_texts(treeish: str, root: Path = ROOT) -> Iterator[tuple[str, str]]:
    """Read every text blob from a Git tree without materializing candidate paths."""
    if not re.fullmatch(r"[0-9a-f]{40}", treeish):
        raise RuntimeError("git tree must be an exact lowercase 40-character commit SHA")
    result = subprocess.run(
        ["git", "ls-tree", "-r", "-z", "--full-tree", treeish],
        cwd=root,
        env=isolated_git_env(),
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError(f"git ls-tree failed for {treeish[:12]}")
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        try:
            metadata, raw_path = item.split(b"\t", 1)
            _mode, kind, object_id = metadata.split()
        except ValueError as exc:
            raise RuntimeError("git ls-tree returned malformed candidate metadata") from exc
        if kind != b"blob":
            continue
        shown = subprocess.run(
            ["git", "cat-file", "blob", object_id.decode("ascii")],
            cwd=root,
            env=isolated_git_env(),
            check=False,
            capture_output=True,
        )
        if shown.returncode:
            raise RuntimeError("git cat-file failed for a proposed tree blob")
        yield (
            os.fsdecode(raw_path),
            shown.stdout.decode("utf-8", errors="replace"),
        )


def file_text(path: Path) -> str | None:
    try:
        raw = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
    except OSError:
        return None
    return raw.decode("utf-8", errors="replace")


def scan_text(path: str, text: str, policy: Policy) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[int, str]] = set()

    def add(offset: int, kind: str) -> None:
        line = text.count("\n", 0, offset) + 1
        key = (line, kind)
        if key not in seen:
            seen.add(key)
            findings.append(Finding(path, line, kind))

    for pattern in IDENTIFIER_RES:
        for match in pattern.finditer(text):
            if digest(match.group("prefix")) in policy.prefixes:
                add(match.start(), "restricted security or tracker identifier")
    for match in HOST_RE.finditer(text):
        host = match.group(0).rstrip(".").casefold()
        labels = host.split(".")
        suffixes = (".".join(labels[index:]) for index in range(max(1, len(labels) - 1)))
        if any(digest(suffix) in policy.hosts for suffix in suffixes):
            add(match.start(), "private service hostname")
        if ephemeral_instance_host(host):
            add(match.start(), "ephemeral infrastructure identifier")
    for kind, pattern in DIRECT_PATTERNS:
        for match in pattern.finditer(text):
            if kind == "corporate personal email" and match.group(0).casefold() in PUBLIC_ROLE_EMAILS:
                continue
            add(match.start(), kind)
    offset = 0
    for line in text.splitlines(keepends=True):
        tokens = [(match.group(0).casefold(), match.start()) for match in TOKEN_RE.finditer(line)]
        for start in range(len(tokens)):
            for size in range(1, min(policy.max_phrase_tokens, len(tokens) - start) + 1):
                phrase = " ".join(token for token, _ in tokens[start:start + size])
                if (phrase not in PATH_PHRASE_ALLOWANCES.get(path, frozenset())
                        and digest(phrase) in policy.phrases):
                    add(offset + tokens[start][1], "restricted active-finding detail")
        offset += len(line)
    return findings


def _scan_repository_path(item: tuple[Path, str, Policy]) -> tuple[list[Finding], int]:
    path, rel, policy = item
    text = file_text(path)
    if text is None:
        return [], 0
    return scan_text(rel, text, policy), 1


def audit(
    root: Path = ROOT,
    policy: Policy | None = None,
    *,
    workers: int | None = None,
) -> tuple[list[Finding], int]:
    active = policy or load_policy()
    findings: list[Finding] = []
    scanned = 0
    paths = repository_files(root)
    if workers is None:
        raw_workers = os.environ.get("SENSITIVE_AUDIT_WORKERS", "")
        workers = int(raw_workers) if raw_workers.isdigit() else min(4, os.cpu_count() or 1)
    work = [(path, path.relative_to(root).as_posix(), active) for path in paths]
    if workers > 1 and len(work) >= 32:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            for rows, count in pool.map(_scan_repository_path, work, chunksize=8):
                findings.extend(rows)
                scanned += count
    else:
        for item in work:
            rows, count = _scan_repository_path(item)
            findings.extend(rows)
            scanned += count
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind)), scanned


def audit_staged(root: Path = ROOT, policy: Policy | None = None) -> tuple[list[Finding], int]:
    active = policy or load_policy()
    rows = staged_texts(root)
    findings = [finding for path, text in rows for finding in scan_text(path, text, active)]
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind)), len(rows)


def audit_git_tree(
    treeish: str, root: Path = ROOT, policy: Policy | None = None,
) -> tuple[list[Finding], int]:
    """Scan proposed Git objects with this trusted scanner, never candidate code."""
    active = policy or load_policy()
    findings: list[Finding] = []
    scanned = 0
    for path, text in git_tree_texts(treeish, root):
        scanned += 1
        findings.extend(scan_text(path, text, active))
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind)), scanned


def audit_commit_range(commit_range: str, root: Path = ROOT, policy: Policy | None = None) -> tuple[list[Finding], int]:
    active = policy or load_policy()
    revs = subprocess.run(
        ["git", "rev-list", "--reverse", commit_range],
        cwd=root,
        env=isolated_git_env(),
        check=False,
        text=True,
        capture_output=True,
    )
    if revs.returncode:
        raise RuntimeError(f"git rev-list failed for {commit_range}")
    findings: list[Finding] = []
    commits = [item for item in revs.stdout.splitlines() if item]
    for commit in commits:
        shown = subprocess.run(
            ["git", "show", "--format=%B", "--no-ext-diff", "--no-renames", "--unified=0", commit],
            cwd=root,
            env=isolated_git_env(),
            check=False,
            text=True,
            errors="replace",
            capture_output=True,
        )
        if shown.returncode:
            raise RuntimeError(f"git show failed for {commit[:12]}")
        current_path = "commit-message"
        for patch_line, line in enumerate(shown.stdout.splitlines(), 1):
            if line.startswith("+++ b/"):
                current_path = line[6:]
                continue
            if current_path == "commit-message" or (line.startswith("+") and not line.startswith("+++")):
                candidate = line if current_path == "commit-message" else line[1:]
                if current_path == "commit-message" and candidate.casefold().startswith("signed-off-by:"):
                    continue
                for item in scan_text(current_path, candidate, active):
                    findings.append(Finding(f"{commit[:12]}:{current_path}", patch_line, item.kind))
            if line.startswith("diff --git "):
                current_path = "diff"
    return sorted(findings, key=lambda item: (item.path, item.line, item.kind)), len(commits)


def self_test() -> list[str]:
    policy = load_policy()
    # Compose launchable samples from parts so this detector's own source stays clean under it.
    relay_family, signed_in_family = LAUNCHABLE_HOST_SUFFIXES
    instance = "a1b2c3d4e"
    relay_host = "launchable-" + instance + "." + relay_family
    signed_in_host = "launchable-" + instance + "." + signed_in_family
    examples = (
        ("year and serial", "C" + "VE-2026-12345", True),
        ("advisory groups", "G" + "HSA-2345-cfgh-jmpq", True),
        ("scanner serial", "B" + "DSA-2026-123456", True),
        ("ecosystem advisory", "PY" + "SEC-2026-123", True),
        ("language advisory", "RUST" + "SEC-2026-1234", True),
        ("database alias", "O" + "SV-2026-123", True),
        ("language database alias", "G" + "O-2026-1234", True),
        ("malware database alias", "M" + "AL-2026-123456", True),
        ("program grouping", "N" + "SPECT-5Q1Z-SXLK", True),
        ("tracker key", "M" + "VSB-36950", True),
        ("loose separators", "C" + "VE: 2026 12345", True),
        ("private hostname", "https://" + "nspect" + ".nvidia.com/report", True),
        ("private hostname suffix", "https://branch." + "gitlab-master-pages" + ".nvidia.com", True),
        ("private project locator", "364" + "401", True),
        ("contributor-local identifier", "v" + "kudlay", True),
        ("declared code owner", "@" + "v" + "kudlay", False),
        ("active detail", "Parse" + "Dict", True),
        ("corporate email", "person@" + "nvidia.com", True),
        ("public security role email", "psirt@" + "nvidia.com", False),
        ("source token", "glpat-" + "a" * 24, True),
        ("signed credential", "eyJ" + "a" * 24 + "." + "b" * 12 + "." + "c" * 12, True),
        ("public standard", "RFC-6902", False),
        ("public product host", "https://build.nvidia.com", False),
        ("placeholder query", "cf_access_jwt=...", False),
        ("generic policy prose", "Report security concerns through the private route.", False),
        ("relay launchable instance", "https://" + relay_host + "/cli/gateway", True),
        ("signed-in launchable instance", "wss://" + signed_in_host + "/ws/terminal", True),
        ("nested launchable instance", "https://edge." + relay_host, True),
        ("bare launchable instance host", signed_in_host, True),
        ("short synthetic instance", "https://launchable-" + instance[:8] + "." + relay_family, False),
        ("long synthetic instance", "https://launchable-" + instance + "5." + signed_in_family, False),
        ("segmented synthetic instance", "https://launchable-test-fixture." + relay_family, False),
        ("launchable family root", "https://" + relay_family + "/status", False),
        ("unrelated nine-character host", "https://a1b2c3d4e.example.test/status", False),
    )
    failures: list[str] = []
    rendered = format_finding(Finding("candidate\n::error::forged", 7, "fixture"))
    if "\n" in rendered or "::error::" not in rendered:
        failures.append("finding rendering: untrusted path was not escaped onto one log line")
    for label, sample, should_fail in examples:
        path = ".gitlab/CODEOWNERS" if label == "declared code owner" else "fixture.txt"
        rejected = bool(scan_text(path, sample, policy))
        if rejected != should_fail:
            failures.append(f"{label}: expected rejected={should_fail}, got {rejected}")

    with tempfile.TemporaryDirectory(prefix="sensitive-content-audit-") as temp_dir:
        root = Path(temp_dir)
        env = isolated_git_env()
        subprocess.run(["git", "init", "-q"], cwd=root, env=env, check=True)
        (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=env, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "clean base"],
            cwd=root,
            env=env,
            check=True,
        )
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, env=env, check=True, text=True, capture_output=True,
        ).stdout.strip()
        signoff = "Signed-off-by: Fixture <person@" + "nvidia.com>"
        (root / "tracked.txt").write_text("B" + "DSA-2026-123456\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=env, check=True)
        staged_rows, _ = audit_staged(root, policy)
        if not any(item.path == "tracked.txt" for item in staged_rows):
            failures.append("staged-index discovery: proposed restricted detail was not rejected")
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "temporary detail", "-m", signoff],
            cwd=root,
            env=env,
            check=True,
        )
        (root / "tracked.txt").write_text("clean again\n", encoding="utf-8")
        subprocess.run(["git", "add", "tracked.txt"], cwd=root, env=env, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "remove detail", "-m", signoff],
            cwd=root,
            env=env,
            check=True,
        )
        rows, _ = audit_commit_range(f"{base}..HEAD", root, policy)
        if not any(item.path.endswith(":tracked.txt") for item in rows):
            failures.append("commit range: removed intermediate detail was not rejected")

        # A launchable instance must fail from a path no registry mentions, after a rename,
        # from the index, and from proposed history that later deletes it.
        added = "docs/runtime/notes/launchable.md"
        (root / added).parent.mkdir(parents=True)
        (root / added).write_text("App URL: https://" + relay_host + "\n", encoding="utf-8")
        rows, _ = audit(root, policy, workers=1)
        if not any(item.path == added for item in rows):
            failures.append("novel nested path: launchable instance escaped full-tree discovery")
        subprocess.run(["git", "add", added], cwd=root, env=env, check=True)
        staged_rows, _ = audit_staged(root, policy)
        if not any(item.path == added for item in staged_rows):
            failures.append("staged index: proposed launchable instance was not rejected")
        moved = "docs/runtime/relocated/launchable.md"
        (root / moved).parent.mkdir(parents=True)
        (root / added).rename(root / moved)
        (root / moved).write_text("App URL: https://" + signed_in_host + "\n", encoding="utf-8")
        rows, _ = audit(root, policy, workers=1)
        if not any(item.path == moved for item in rows):
            failures.append("renamed path: launchable instance escaped full-tree discovery")
        subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "temporary launchable note", "-m", signoff],
            cwd=root,
            env=env,
            check=True,
        )
        (root / moved).unlink()
        subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-qm", "remove launchable note", "-m", signoff],
            cwd=root,
            env=env,
            check=True,
        )
        rows, _ = audit_commit_range(f"{base}..HEAD", root, policy)
        if not any(item.kind == "ephemeral infrastructure identifier" for item in rows):
            failures.append("commit range: removed launchable instance was not rejected")

        # A pull_request_target job invokes this already-loaded base scanner against Git objects.
        # Candidate edits to its own workflow or scanner therefore remain inert untrusted bytes.
        candidate_tamper = {
            ".github/workflows/contribution-boundary.yml": "name: disabled candidate check\n",
            "scripts/validation/sensitive_content_audit.py": "def audit(*_args): return [], 0\n",
            "novel/deep/runtime/launchable.txt": "App URL: https://" + relay_host + "\n",
        }
        for rel, content in candidate_tamper.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, env=env, check=True)
        subprocess.run(
            ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.test",
             "commit", "-qm", "attempt to disable base scanner"],
            cwd=root,
            env=env,
            check=True,
        )
        candidate_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, env=env, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
        rows, _ = audit_git_tree(candidate_sha, root, policy)
        if not any(item.path == "novel/deep/runtime/launchable.txt" for item in rows):
            failures.append(
                "trusted-base tree scan: candidate workflow and validator edits disabled novel-path discovery"
            )
    with tempfile.TemporaryDirectory(prefix="sensitive-archive-") as temp_dir:
        archive = Path(temp_dir)
        (archive / "source.txt").write_text("B" + "DSA-2026-123456\n", encoding="utf-8")
        (archive / "docs/validation").mkdir(parents=True)
        (archive / "docs/validation/generated.txt").write_text(
            "B" + "DSA-2026-999999\n", encoding="utf-8"
        )
        nested = "deploy/regions/edge/launchable.md"
        (archive / nested).parent.mkdir(parents=True)
        (archive / nested).write_text("App URL: https://" + relay_host + "\n", encoding="utf-8")
        binary = "deploy/regions/edge/launchable.bin"
        (archive / binary).write_bytes(b"\0fixture\0App URL: https://" + signed_in_host.encode())
        rows, scanned = audit(archive, policy, workers=1)
        if scanned != 3 or not any(item.path == "source.txt" for item in rows):
            failures.append("source-archive discovery: source content was not scanned exactly once")
        if not any(item.path == nested for item in rows):
            failures.append("source-archive discovery: novel nested launchable instance was missed")
        if not any(item.path == binary for item in rows):
            failures.append("source-archive discovery: NUL-wrapped launchable instance was missed")
    return failures


def emit(findings: list[Finding], label: str, scanned: int, report: str | None) -> int:
    result = {
        "schema": "sensitive-content-audit/1",
        "ok": not findings,
        "label": label,
        "scanned": scanned,
        "findings": [item.__dict__ for item in findings],
    }
    if report:
        path = Path(report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if findings:
        print(f"sensitive content audit: FAIL ({len(findings)})")
        for item in findings:
            print("  " + format_finding(item))
        print("Move private security details to the approved non-repository record and keep only generic controls here.")
        return 1
    print(f"sensitive content audit: OK ({label}; {scanned} inputs)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--staged", action="store_true", help="scan exact file content staged in the Git index")
    parser.add_argument(
        "--git-tree", metavar="COMMIT_SHA",
        help="scan every blob in an exact proposed Git tree without checking it out",
    )
    parser.add_argument(
        "--root", type=Path, default=ROOT,
        help="scan this complete source or publication tree instead of the repository root",
    )
    parser.add_argument("--commit-range", metavar="BASE..HEAD")
    parser.add_argument("--submission-env", action="append", default=[], metavar="NAME")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        policy = load_policy()
        if args.self_test:
            failures = self_test()
            print("sensitive content self-test: " + ("FAIL" if failures else "PASS"))
            for failure in failures:
                print("  FAIL " + failure)
            return 1 if failures else 0
        if args.git_tree:
            findings, scanned = audit_git_tree(args.git_tree, args.root, policy)
            return emit(findings, f"git tree {args.git_tree[:12]}", scanned, args.report)
        if args.commit_range:
            findings, scanned = audit_commit_range(args.commit_range, args.root, policy)
            return emit(findings, f"commit range {args.commit_range}", scanned, args.report)
        if args.staged:
            findings, scanned = audit_staged(args.root, policy)
            return emit(findings, "staged index", scanned, args.report)
        if args.submission_env:
            text = "\n".join(os.environ.get(name, "") for name in args.submission_env)
            findings = scan_text("submission", text, policy)
            return emit(findings, "submission metadata", len(args.submission_env), args.report)
        findings, scanned = audit(args.root, policy)
        label = "working tree" if args.root == ROOT else f"tree {args.root}"
        return emit(findings, label, scanned, args.report)
    except RuntimeError as exc:
        print(f"sensitive content audit: FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
