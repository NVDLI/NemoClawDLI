#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Root-installed, fixed-vocabulary publisher for the DLI course CDN.

CI must invoke the reviewed copy under /opt/dli-course-publisher. Never execute
this repository copy from a pipeline that also carries publication authority.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath


SCHEMA = "dli-cdn-publication/2"
SHA = re.compile(r"^[0-9a-f]{40}$")
CONFIG = Path("/etc/dli-course-publisher.json")
COURSE_PREFIXES = {
    "nemoclaw": ("nemoclaw/", "shared/", "es/nemoclaw/", "pt/nemoclaw/"),
}
STABLE_ROOT_FILES = {
    "index.html", "languages.json", "branches.json", "LICENSE",
    "THIRD_PARTY_LICENSES.md", "THIRD-PARTY-NOTICES.md",
}


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _stable_prefixes(plan: dict[str, object]) -> tuple[str, ...]:
    courses = plan.get("courses")
    if (
        not isinstance(courses, list) or not courses or len(courses) != len(set(courses))
        or not all(isinstance(course, str) and course in COURSE_PREFIXES for course in courses)
        or "nemoclaw" not in courses
    ):
        raise ValueError("publication plan has an invalid course selection")
    return tuple(dict.fromkeys(prefix for course in courses for prefix in COURSE_PREFIXES[course]))


def validate(publication: Path, plan_path: Path, config_path: Path = CONFIG) -> tuple[dict[str, object], dict[str, str]]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if plan.get("schema") != SCHEMA:
        raise ValueError("publication plan schema is not approved")
    source_sha = str(plan.get("source_sha", ""))
    destination = str(plan.get("destination", ""))
    channel = plan.get("channel")
    if not SHA.fullmatch(source_sha):
        raise ValueError("source commit is invalid")
    if channel == "immutable" and destination != source_sha:
        raise ValueError("immutable destination must equal the reviewed commit")
    stable_refs = config.get("stable_refs", ["main", "nemoclaw-only"])
    if channel == "stable" and (destination != "course-static" or plan.get("source_ref") not in stable_refs):
        raise ValueError("stable publication source or destination is not approved")
    if channel not in {"immutable", "stable"}:
        raise ValueError("publication channel is invalid")
    stable_prefixes = _stable_prefixes(plan)
    rows = plan.get("files")
    if not isinstance(rows, list) or not rows:
        raise ValueError("publication plan has no files")
    expected: dict[str, tuple[int, str]] = {}
    for row in rows:
        rel = str(row.get("path", "")) if isinstance(row, dict) else ""
        candidate = PurePosixPath(rel)
        if not rel or candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
            raise ValueError("publication plan contains an unsafe path")
        digest = str(row.get("sha256", ""))
        size = row.get("bytes")
        if (
            set(row) != {"path", "bytes", "sha256"}
            or not isinstance(size, int) or isinstance(size, bool) or size < 0
            or not re.fullmatch(r"[0-9a-f]{64}", digest) or rel in expected
        ):
            raise ValueError("publication plan contains an invalid or repeated file record")
        expected[rel] = (size, digest)
    actual: dict[str, tuple[int, str]] = {}
    for path in publication.rglob("*"):
        if path.is_symlink():
            raise ValueError("publication contains a symlink")
        if path.is_file():
            actual[path.relative_to(publication).as_posix()] = (path.stat().st_size, _digest(path))
    if actual != expected:
        raise ValueError("publication bytes do not match the reviewed plan")
    if channel == "stable" and any(
        rel not in STABLE_ROOT_FILES and not any(rel.startswith(prefix) for prefix in stable_prefixes)
        for rel in expected
    ):
        raise ValueError("stable publication plan leaves the fixed course-owned roots")
    account = str(config.get("aws_account_id", ""))
    if not re.fullmatch(r"[0-9]{12}", account):
        raise ValueError("publisher account configuration is invalid")
    principal = str(config.get("principal_arn", ""))
    assumed = re.fullmatch(rf"arn:aws:sts::{account}:assumed-role/[A-Za-z0-9+=,.@_/-]+/", principal)
    user = re.fullmatch(rf"arn:aws:iam::{account}:user/[A-Za-z0-9+=,.@_/-]+", principal)
    if not (assumed or user):
        raise ValueError("publisher principal configuration is invalid")
    bucket = str(config.get("bucket_name", ""))
    prefix = str(config.get("key_prefix", "")).strip("/")
    cdn = str(config.get("public_base_url", "")).rstrip("/")
    parsed_cdn = urllib.parse.urlsplit(cdn)
    if (
        not re.fullmatch(r"(?=.{3,63}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])", bucket)
        or ".." in bucket
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9/_-]{0,126}[a-z0-9])?", prefix)
        or ".." in PurePosixPath(prefix).parts
        or parsed_cdn.scheme != "https" or not parsed_cdn.hostname
        or parsed_cdn.username or parsed_cdn.password or parsed_cdn.query or parsed_cdn.fragment
    ):
        raise ValueError("publisher destination configuration is invalid")
    aws = Path(str(config.get("aws_executable", "")))
    aws_sha = str(config.get("aws_executable_sha256", ""))
    aws_config = Path(str(config.get("aws_config_file", "")))
    aws_credentials = Path(str(config.get("aws_credentials_file", "")))
    protected_files = (aws_config, aws_credentials)
    if (
        not aws.is_absolute() or not aws.is_file() or aws.is_symlink()
        or aws.stat().st_uid != 0 or aws.stat().st_mode & 0o022
        or not re.fullmatch(r"[0-9a-f]{64}", aws_sha) or _digest(aws) != aws_sha
        or any(
            not path.is_absolute() or not path.is_file() or path.is_symlink()
            or path.stat().st_uid != 0 or path.stat().st_mode & 0o022
            for path in protected_files
        )
    ):
        raise ValueError("root-owned AWS runtime configuration is invalid")
    config_text = aws_config.read_text(encoding="utf-8", errors="strict")
    if re.search(
        r"(?im)^\s*(?:endpoint_url|credential_process|web_identity_token_file|ca_bundle|services)\s*=",
        config_text,
    ):
        raise ValueError("AWS runtime configuration contains an alternate authority endpoint")
    return plan, {
        "account": account, "destination": destination, "principal": principal,
        "aws": str(aws), "aws_config": str(aws_config), "aws_credentials": str(aws_credentials),
        "bucket": bucket, "prefix": prefix, "cdn": cdn,
        "cloudfront_distribution": str(config.get("cloudfront_distribution_id", "")),
    }


def _aws_json(aws: str, env: dict[str, str], *args: str) -> dict[str, object]:
    result = subprocess.run([aws, *args, "--output", "json"], env=env, check=True, capture_output=True, text=True)
    value = json.loads(result.stdout or "{}")
    if not isinstance(value, dict):
        raise ValueError("AWS returned malformed inventory evidence")
    return value


def _list_prefix(aws: str, env: dict[str, str], bucket: str, prefix: str) -> dict[str, int]:
    out: dict[str, int] = {}
    token = ""
    for _page in range(10_000):
        args = ["s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix]
        if token:
            args.extend(["--continuation-token", token])
        value = _aws_json(aws, env, *args)
        rows = value.get("Contents", [])
        if not isinstance(rows, list):
            raise ValueError("S3 inventory evidence is malformed")
        for row in rows:
            if (
                not isinstance(row, dict) or not isinstance(row.get("Key"), str)
                or not isinstance(row.get("Size"), int) or row["Key"] in out
            ):
                raise ValueError("S3 inventory evidence is malformed or repeated")
            out[row["Key"]] = row["Size"]
        truncated = value.get("IsTruncated", False)
        next_token = value.get("NextContinuationToken", "")
        if truncated is False:
            if next_token:
                raise ValueError("S3 inventory pagination is malformed")
            return out
        if truncated is not True or not isinstance(next_token, str) or not next_token or next_token == token:
            raise ValueError("S3 inventory pagination is malformed")
        token = next_token
    raise ValueError("S3 inventory exceeds the fixed page bound")


def _remote_owned(
    plan: dict[str, object], aws: str, env: dict[str, str], bucket: str, prefix: str,
) -> dict[str, int]:
    if plan["channel"] == "immutable":
        return _list_prefix(aws, env, bucket, f"{prefix}/{plan['destination']}/")
    out: dict[str, int] = {}
    for relative in _stable_prefixes(plan):
        out.update(_list_prefix(aws, env, bucket, f"{prefix}/{relative}"))
    for relative in STABLE_ROOT_FILES:
        exact = f"{prefix}/{relative}"
        out.update({key: size for key, size in _list_prefix(aws, env, bucket, exact).items() if key == exact})
    return out


def _expected_remote(plan: dict[str, object], prefix: str) -> dict[str, int]:
    base = f"{prefix}/" if plan["channel"] == "stable" else f"{prefix}/{plan['destination']}/"
    return {base + str(row["path"]): int(row["bytes"]) for row in plan["files"]}


def _verify_cdn(plan: dict[str, object], cdn: str, prefix: str) -> None:
    destination = str(plan["destination"])
    source_sha = str(plan["source_sha"])
    rows = list(plan["files"])

    def check(row: dict[str, object]) -> None:
        rel = str(row["path"])
        encoded = urllib.parse.quote(rel, safe="/")
        base = f"{cdn}/{prefix}" if plan["channel"] == "stable" else f"{cdn}/{prefix}/{destination}"
        url = f"{base}/{encoded}?version={source_sha[:16]}"
        request = urllib.request.Request(url, headers={"Accept-Encoding": "identity", "User-Agent": "dli-course-publisher/1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            value = hashlib.sha256()
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > int(row["bytes"]) + 1:
                    raise ValueError("deployed object exceeds its reviewed size")
                value.update(chunk)
        if total != int(row["bytes"]) or value.hexdigest() != row["sha256"]:
            raise ValueError("deployed object differs from its reviewed bytes")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(check, row) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            future.result()


def publish(publication: Path, plan_path: Path, config_path: Path = CONFIG) -> None:
    plan, bounded = validate(publication, plan_path, config_path)
    env = {
        "HOME": "/var/empty", "PATH": "/usr/local/bin:/usr/bin:/bin",
        "AWS_CONFIG_FILE": bounded["aws_config"],
        "AWS_SHARED_CREDENTIALS_FILE": bounded["aws_credentials"],
        "AWS_PAGER": "", "AWS_EC2_METADATA_DISABLED": "true", "LC_ALL": "C.UTF-8",
    }
    identity = subprocess.run(
        [bounded["aws"], "sts", "get-caller-identity", "--output", "json"], env=env,
        check=True, capture_output=True, text=True,
    )
    identity_record = json.loads(identity.stdout)
    if (
        str(identity_record.get("Account", "")) != bounded["account"]
        or not _principal_matches(str(identity_record.get("Arn", "")), bounded["principal"])
    ):
        raise ValueError("ambient AWS identity is not the configured publisher principal")
    expected_remote = _expected_remote(plan, bounded["prefix"])
    before = _remote_owned(plan, bounded["aws"], env, bounded["bucket"], bounded["prefix"])
    if plan["channel"] == "immutable" and set(before) - set(expected_remote):
        raise ValueError("immutable CDN prefix already contains unreviewed objects")
    target = (
        f"s3://{bounded['bucket']}/{bounded['prefix']}/"
        if plan["channel"] == "stable"
        else f"s3://{bounded['bucket']}/{bounded['prefix']}/{bounded['destination']}/"
    )
    cache_control = "public,max-age=31536000,immutable" if plan["channel"] == "immutable" else "public,max-age=300"
    subprocess.run(
        [
            bounded["aws"], "s3", "cp", "--recursive", "--only-show-errors",
            "--cache-control", cache_control, str(publication), target,
        ],
        env=env, check=True,
    )
    if plan["channel"] == "stable":
        for key in sorted(set(before) - set(expected_remote)):
            subprocess.run(
                [bounded["aws"], "s3api", "delete-object", "--bucket", bounded["bucket"], "--key", key],
                env=env, check=True, capture_output=True,
            )
        distribution = bounded["cloudfront_distribution"]
        if not re.fullmatch(r"E[A-Z0-9]{8,20}", distribution):
            raise ValueError("stable publication requires the fixed CloudFront distribution")
        paths = [f"/{bounded['prefix']}/{prefix}*" for prefix in _stable_prefixes(plan)]
        paths.extend(f"/{bounded['prefix']}/{path}" for path in sorted(STABLE_ROOT_FILES))
        invalidation = _aws_json(
            bounded["aws"], env, "cloudfront", "create-invalidation",
            "--distribution-id", distribution, "--paths", *paths,
        )
        invalidation_id = str((invalidation.get("Invalidation") or {}).get("Id", ""))
        if not re.fullmatch(r"I[A-Z0-9]+", invalidation_id):
            raise ValueError("CloudFront returned malformed invalidation evidence")
        subprocess.run(
            [bounded["aws"], "cloudfront", "wait", "invalidation-completed",
             "--distribution-id", distribution, "--id", invalidation_id],
            env=env, check=True, capture_output=True,
        )
    after = _remote_owned(plan, bounded["aws"], env, bounded["bucket"], bounded["prefix"])
    if after != expected_remote:
        raise ValueError("remote course-owned S3 tree differs from the reviewed manifest")
    _verify_cdn(plan, bounded["cdn"], bounded["prefix"])


def _principal_matches(actual: str, configured: str) -> bool:
    if ":assumed-role/" in configured:
        suffix = actual.removeprefix(configured)
        return actual.startswith(configured) and bool(re.fullmatch(r"[A-Za-z0-9+=,.@_-]{1,64}", suffix))
    return actual == configured


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publication", required=True)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    try:
        publish(Path(args.publication).resolve(), Path(args.plan).resolve())
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError, urllib.error.URLError) as exc:
        print(f"DLI CDN publisher: FAIL: {type(exc).__name__}")
        return 1
    print("DLI CDN publisher: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
