#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reject concrete operator-owned infrastructure identifiers from public source."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OBJECT_STORE_SUFFIX = ".amazonaws.com"
HOSTNAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789.-")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str


def repository_files(root: Path = ROOT) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode:
        raise RuntimeError("git file discovery failed")
    return [root / os.fsdecode(item) for item in result.stdout.split(b"\0") if item]


def text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def object_store_hostname_offsets(value: str) -> list[int]:
    lower = value.lower()
    offsets: list[int] = []
    cursor = 0
    while True:
        suffix_start = lower.find(OBJECT_STORE_SUFFIX, cursor)
        if suffix_start < 0:
            return offsets
        end = suffix_start + len(OBJECT_STORE_SUFFIX)
        start = suffix_start
        while start > 0 and lower[start - 1] in HOSTNAME_CHARS:
            start -= 1
        candidate = lower[start:end]
        stem = candidate[:-len(OBJECT_STORE_SUFFIX)]
        bucket, marker, service = stem.rpartition(".s3")
        valid_bucket = (
            marker == ".s3"
            and 3 <= len(bucket) <= 63
            and bucket[0].isalnum()
            and bucket[-1].isalnum()
            and all(char in HOSTNAME_CHARS for char in bucket)
        )
        valid_service = (
            not service
            or (
                service[0] in ".-"
                and len(service) > 1
                and all(char in HOSTNAME_CHARS for char in service[1:])
            )
        )
        if valid_bucket and valid_service:
            offsets.append(start)
        cursor = end


def scan_text(path: str, value: str) -> list[Finding]:
    patterns = (
        (
            "concrete object-store bucket",
            re.compile(r"(?i)\bs3://(?![<$%{])(?=[a-z0-9])[a-z0-9][a-z0-9.-]{1,61}[a-z0-9](?=/)"),
        ),
        (
            "cloud account identifier",
            re.compile(r"\barn:aws(?:-us-gov|-cn)?:[^:\s]*:[^:\s]*:\d{12}:"),
        ),
        ("hosted-zone identifier", re.compile(r"\bZ[A-Z0-9]{10,32}\b")),
        ("generated distribution hostname", re.compile(r"(?i)\b[a-z0-9-]+\.cloudfront\.net\b")),
    )
    findings: list[Finding] = []
    for kind, pattern in patterns:
        for match in pattern.finditer(value):
            findings.append(Finding(path, value.count("\n", 0, match.start()) + 1, kind))
    for offset in object_store_hostname_offsets(value):
        findings.append(Finding(
            path,
            value.count("\n", 0, offset) + 1,
            "concrete object-store website hostname",
        ))
    assignment = re.compile(
        r'''(?ix)
        ["']?
        (?P<key>aws_account_id|bucket|bucket_name|publish_bucket|cloudfront_distribution_id)
        ["']?
        \s*(?:=|:)\s*
        ["'](?P<value>[^"']+)["']
        '''
    )
    for match in assignment.finditer(value):
        key = match.group("key").lower()
        assigned = match.group("value").strip()
        placeholder = (
            assigned.startswith(("<", "${", "$", "%{", "example-", "sample-", "test-"))
            or assigned.endswith(".invalid")
        )
        if placeholder:
            continue
        concrete = (
            (key == "aws_account_id" and assigned.isdigit() and len(assigned) == 12)
            or (
                key in {"bucket", "bucket_name", "publish_bucket"}
                and 3 <= len(assigned) <= 63
                and assigned[0].isalnum()
                and assigned[-1].isalnum()
                and all(char in "abcdefghijklmnopqrstuvwxyz0123456789.-" for char in assigned.lower())
            )
            or (
                key == "cloudfront_distribution_id"
                and re.fullmatch(r"E[A-Z0-9]{10,31}", assigned) is not None
            )
        )
        if concrete:
            findings.append(Finding(
                path,
                value.count("\n", 0, match.start()) + 1,
                f"concrete {key} assignment",
            ))
    return findings


def scan(root: Path = ROOT) -> list[Finding]:
    findings: list[Finding] = []
    for path in repository_files(root):
        if path.is_symlink():
            continue
        value = text(path)
        if value is not None:
            findings.extend(scan_text(path.relative_to(root).as_posix(), value))
    return sorted(set(findings), key=lambda row: (row.path, row.line, row.kind))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    findings = scan(args.root.resolve())
    if findings:
        print(f"Public infrastructure audit: FAIL ({len(findings)})")
        for finding in findings:
            print(f"  {finding.path}:{finding.line}: {finding.kind}")
        return 1
    print("Public infrastructure audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
