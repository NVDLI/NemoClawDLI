#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Extract a trusted runtime archive without allowing paths outside its root."""
from __future__ import annotations

import argparse
import os
import shutil
import tarfile
from pathlib import Path, PurePosixPath


def _normalize(parts: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for part in parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not result:
                raise ValueError("archive path escapes its root")
            result.pop()
            continue
        result.append(part)
    return tuple(result)


def _member_path(member: tarfile.TarInfo, root: str) -> tuple[str, ...]:
    path = PurePosixPath(member.name)
    if path.is_absolute():
        raise ValueError("archive contains an absolute path")
    parts = _normalize(path.parts)
    if not parts or parts[0] != root:
        raise ValueError("archive path leaves the expected root")
    return parts


def _link_target(member: tarfile.TarInfo, path: tuple[str, ...], root: str) -> tuple[str, ...]:
    target = PurePosixPath(member.linkname)
    if target.is_absolute():
        raise ValueError("archive contains an absolute link")
    base = () if member.islnk() else path[:-1]
    parts = _normalize(base + target.parts)
    if not parts or parts[0] != root:
        raise ValueError("archive link leaves the expected root")
    return parts


def extract(archive: Path, destination: Path, root: str = "node_modules") -> None:
    destination = destination.resolve()
    hardlinks: list[tuple[Path, Path]] = []
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        checked: list[tuple[tarfile.TarInfo, tuple[str, ...]]] = []
        for member in members:
            parts = _member_path(member, root)
            if not (member.isdir() or member.isfile() or member.issym() or member.islnk()):
                raise ValueError("archive contains an unsupported special file")
            if member.issym() or member.islnk():
                _link_target(member, parts, root)
            checked.append((member, parts))

        for member, parts in checked:
            output = destination.joinpath(*parts)
            output.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                output.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError("archive file has no readable payload")
                with source, output.open("wb") as stream:
                    shutil.copyfileobj(source, stream)
                output.chmod(member.mode & 0o777)
            elif member.issym():
                os.symlink(member.linkname, output)
            else:
                target = destination.joinpath(*_link_target(member, parts, root))
                hardlinks.append((target, output))

    for target, output in hardlinks:
        if not target.is_file():
            raise ValueError("archive hard link target is unavailable")
        os.link(target, output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--root", default="node_modules")
    args = parser.parse_args()
    extract(args.archive, args.destination, args.root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
