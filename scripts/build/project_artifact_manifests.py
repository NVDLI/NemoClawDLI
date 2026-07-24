#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Project root manifests and license into every discovered source mirror."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def mirror_roots(manifest_root: Path) -> set[Path]:
    return {
        course.parents[1]
        for course in manifest_root.rglob("web/nemoclaw")
        if course.is_dir()
    }


def project_manifest(
    deployment_root: Path,
    manifest_root: Path,
    destinations: set[Path],
    source_name: str,
    list_name: str,
) -> None:
    source_path = manifest_root / source_name
    source = json.loads(source_path.read_text(encoding="utf-8"))
    for destination in sorted(destinations):
        if not destination.is_dir():
            continue
        value = json.loads(json.dumps(source))
        for item in value.get(list_name, []):
            raw = item.get("url")
            if not raw:
                continue
            target = (manifest_root / raw).resolve()
            try:
                target.relative_to(deployment_root)
            except ValueError as exc:
                raise ValueError(f"{source_name} URL escapes deployment root: {raw}") from exc
            item["url"] = Path(os.path.relpath(target, destination)).as_posix().rstrip("/") + "/"
        (destination / source_name).write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def project_artifact_manifests(deployment_root: Path, manifest_root: Path) -> int:
    deployment_root = deployment_root.resolve()
    manifest_root = manifest_root.resolve()
    manifest_root.relative_to(deployment_root)
    roots = mirror_roots(manifest_root)
    destinations = {
        destination
        for root in roots
        for destination in (root, root / "web")
    }
    project_manifest(deployment_root, manifest_root, destinations, "languages.json", "languages")
    project_manifest(deployment_root, manifest_root, destinations, "branches.json", "branches")
    license_source = manifest_root / "LICENSE"
    for root in sorted(roots):
        license_target = root / "LICENSE"
        if license_target != license_source:
            shutil.copyfile(license_source, license_target)
    return len(destinations)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deployment_root", type=Path)
    parser.add_argument("--manifest-root", type=Path)
    args = parser.parse_args()
    manifest_root = args.manifest_root or args.deployment_root
    count = project_artifact_manifests(args.deployment_root, manifest_root)
    print(f"artifact manifest projection: PASS ({count} destinations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
