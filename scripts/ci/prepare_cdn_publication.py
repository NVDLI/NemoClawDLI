#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Create a bounded CDN tree from an already verified Pages candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


SCHEMA = "dli-cdn-publication/2"
PRIMARY_COURSE = "nemoclaw"


def _copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise ValueError(f"required publication source is missing: {source}")
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"publication source contains a symlink: {path}")
        if path.is_file():
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def prepare(candidate: Path, output: Path, plan_path: Path, request: dict[str, object]) -> dict[str, object]:
    languages_path = candidate / "languages.json"
    if not languages_path.is_file():
        raise ValueError("candidate has no languages.json")
    language_manifest = json.loads(languages_path.read_text(encoding="utf-8"))
    available = {item["code"]: item for item in language_manifest.get("languages", [])}
    requested = request.get("languages")
    courses = request.get("courses")
    if not isinstance(requested, list) or not requested or not all(item in available for item in requested):
        raise ValueError("requested language is absent from the reviewed artifact")
    if (
        not isinstance(courses, list) or not courses or len(courses) != len(set(courses))
        or courses != [PRIMARY_COURSE]
    ):
        raise ValueError("requested courses are outside the reviewed publication vocabulary")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    english_root = candidate / "web" if (candidate / "web" / PRIMARY_COURSE).is_dir() else candidate
    if "en" in requested:
        # Both trees are relative to a site root. Stable uploads that tree at /course-static/;
        # immutable uploads it at /course-static/<sha>/.
        _copy_tree(english_root / PRIMARY_COURSE, output / PRIMARY_COURSE)
        if (english_root / "shared").is_dir():
            _copy_tree(english_root / "shared", output / "shared")
    for language in requested:
        if language == "en":
            continue
        _copy_tree(candidate / language / PRIMARY_COURSE, output / language / PRIMARY_COURSE)

    for name in ("LICENSE", "THIRD_PARTY_LICENSES.md", "THIRD-PARTY-NOTICES.md"):
        if (candidate / name).is_file():
            shutil.copy2(candidate / name, output / name)
    entry = f"{PRIMARY_COURSE}/" if "en" in requested else f"{requested[0]}/{PRIMARY_COURSE}/"
    if not (candidate / "index.html").is_file() or "en" not in requested:
        (output / "index.html").write_text(
            f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={entry}">'
            f'<title>NVIDIA DLI course</title><a href="{entry}">Open the course</a>\n', encoding="utf-8",
        )
    selected_languages = [
        {
            **available[code],
            "url": f"{PRIMARY_COURSE}/" if code == "en" else f"{code}/{PRIMARY_COURSE}/",
        }
        for code in requested
    ]
    (output / "languages.json").write_text(json.dumps({
        "schema": language_manifest.get("schema"), "default": "en" if "en" in requested else requested[0],
        "languages": selected_languages,
        "note": "This manifest lists only languages selected from the reviewed publication artifact.",
    }, indent=2) + "\n", encoding="utf-8")
    if "en" in requested and (candidate / "index.html").is_file():
        shutil.copy2(candidate / "index.html", output / "index.html")
    if (candidate / "branches.json").is_file():
        shutil.copy2(candidate / "branches.json", output / "branches.json")

    files = []
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        rel = path.relative_to(output).as_posix()
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    plan = {
        "schema": SCHEMA,
        "source_ref": request["source_ref"],
        "source_sha": request["source_sha"],
        "source_job_id": request["job_id"],
        "channel": request["channel"],
        "destination": request["destination"],
        "courses": courses,
        "languages": requested,
        "files": files,
    }
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return plan


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    try:
        plan = prepare(Path(args.candidate), Path(args.output), Path(args.plan), json.loads(Path(args.request).read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"CDN publication preparation: FAIL: {exc}")
        return 1
    print(f"CDN publication preparation: OK files={len(plan['files'])} destination={plan['destination']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
