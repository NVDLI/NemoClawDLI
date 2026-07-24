#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build deterministic, checksummed release assets from an assembled Pages tree."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


SEMVER = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:[-+][0-9A-Za-z.-]+)?$")
OBJECT_ID = re.compile(r"[0-9a-f]{40,64}$")
MALWARE_SCAN_SUFFIXES = (".tar.gz", ".tgz", ".zip", ".whl", ".exe", ".msi", ".deb", ".rpm")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def requires_malware_scan(path: Path) -> bool:
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in MALWARE_SCAN_SUFFIXES)


def validate(tag: str, commit: str, tag_object: str, epoch: int, site: Path) -> None:
    if not SEMVER.fullmatch(tag):
        raise ValueError("tag must match semantic vMAJOR.MINOR.PATCH")
    if not OBJECT_ID.fullmatch(commit) or not OBJECT_ID.fullmatch(tag_object):
        raise ValueError("commit and tag object must be full hexadecimal object IDs")
    if epoch < 0:
        raise ValueError("source date epoch must be non-negative")
    if not site.is_dir() or not (site / "index.html").is_file():
        raise ValueError("site root must contain index.html")


def add_tree(archive: tarfile.TarFile, site: Path, prefix: str, epoch: int) -> int:
    paths = [site, *sorted(site.rglob("*"), key=lambda path: path.relative_to(site).as_posix())]
    count = 0
    for path in paths:
        if path.is_symlink():
            raise ValueError(f"release tree contains unsupported symlink: {path}")
        if not path.is_file() and not path.is_dir():
            raise ValueError(f"release tree contains unsupported file type: {path}")
        relative = path.relative_to(site)
        name = PurePosixPath(prefix, relative.as_posix()) if relative.parts else PurePosixPath(prefix)
        info = archive.gettarinfo(str(path), arcname=str(name))
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = epoch
        info.mode = 0o755 if path.is_dir() else 0o644
        if path.is_file():
            with path.open("rb") as stream:
                archive.addfile(info, stream)
            count += 1
        else:
            archive.addfile(info)
    return count


def package(site: Path, out: Path, tag: str, commit: str, tag_object: str,
            epoch: int, assets: list[Path]) -> dict[str, object]:
    site = site.resolve()
    out = out.resolve()
    validate(tag, commit, tag_object, epoch, site)
    if out == site or site in out.parents:
        raise ValueError("output directory must not be inside the release tree")
    if out.exists() and any(out.iterdir()):
        raise ValueError("output directory must be empty to prevent stale release assets")
    out.mkdir(parents=True, exist_ok=True)

    resolved_assets: list[Path] = []
    reserved = {f"nemoclaw-{tag}.tar.gz", "release-manifest.json", "SHA256SUMS"}
    for source in assets:
        source = source.resolve()
        if not source.is_file():
            raise ValueError(f"release asset is missing: {source}")
        if source.name in reserved or any(path.name == source.name for path in resolved_assets):
            raise ValueError(f"duplicate or reserved release asset name: {source.name}")
        resolved_assets.append(source)

    archive_path = out / f"nemoclaw-{tag}.tar.gz"
    with archive_path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                file_count = add_tree(archive, site, f"nemoclaw-{tag}", epoch)

    copied: list[Path] = []
    for source in resolved_assets:
        target = out / source.name
        if source != target:
            shutil.copy2(source, target)
        copied.append(target)

    manifest_path = out / "release-manifest.json"
    manifest = {
        "schema": "nemoclaw-release-artifact/1",
        "tag": tag,
        "tag_object": tag_object,
        "commit": commit,
        "source_date_epoch": epoch,
        "archive": archive_path.name,
        "archive_sha256": digest(archive_path),
        "file_count": file_count,
        "assets": [
            {"name": path.name, "sha256": digest(path), "size": path.stat().st_size}
            for path in sorted(copied, key=lambda item: item.name)
        ],
        "external_evidence": {
            "malware_scan_required": sorted(
                path.name for path in (archive_path, *copied) if requires_malware_scan(path)
            ),
            "policy": "required-before-publication",
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    checksum_paths = [archive_path, manifest_path, *copied]
    checksums = out / "SHA256SUMS"
    checksums.write_text(
        "".join(f"{digest(path)}  {path.name}\n" for path in sorted(checksum_paths, key=lambda item: item.name)),
        encoding="utf-8",
    )
    return manifest


def self_test() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="nemoclaw-release-") as temp:
        root = Path(temp)
        site = root / "site"
        (site / "assets").mkdir(parents=True)
        (site / "index.html").write_text("release\n", encoding="utf-8")
        (site / "assets" / "app.js").write_text("console.log('ok');\n", encoding="utf-8")
        sbom = root / "python-env.cdx.json"
        sbom.write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
        addon = root / "optional-addon.zip"
        addon.write_bytes(b"archive fixture\n")
        args = (site, "v1.2.3", "a" * 40, "b" * 40, 1_700_000_000, [sbom, addon])
        first = package(args[0], root / "one", *args[1:])
        (site / "index.html").chmod(0o600)
        second = package(args[0], root / "two", *args[1:])
        if first != second:
            failures.append("manifest changed across identical package inputs")
        expected_scan = ["nemoclaw-v1.2.3.tar.gz", "optional-addon.zip"]
        if first.get("external_evidence", {}).get("malware_scan_required") != expected_scan:
            failures.append("manifest does not identify every archive requiring malware evidence")
        for name in ("nemoclaw-v1.2.3.tar.gz", "release-manifest.json", "SHA256SUMS"):
            if (root / "one" / name).read_bytes() != (root / "two" / name).read_bytes():
                failures.append(f"non-deterministic release output: {name}")
        with tarfile.open(root / "one" / "nemoclaw-v1.2.3.tar.gz", "r:gz") as archive:
            names = archive.getnames()
            if "nemoclaw-v1.2.3/index.html" not in names:
                failures.append("archive lacks versioned top-level directory")
        try:
            package(site, root / "bad", "latest", "a" * 40, "b" * 40, 0, [])
            failures.append("non-semantic tag passed")
        except ValueError:
            pass
        try:
            package(site, site / "release", "v1.2.3", "a" * 40, "b" * 40, 0, [])
            failures.append("output inside release tree passed")
        except ValueError:
            pass
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-root", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--tag")
    parser.add_argument("--commit")
    parser.add_argument("--tag-object")
    parser.add_argument("--source-date-epoch", type=int)
    parser.add_argument("--asset", action="append", type=Path, default=[])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        if failures:
            print("package_release: FAIL")
            for failure in failures:
                print(f"  - {failure}")
            return 1
        print("package_release: OK (determinism self-test)")
        return 0
    required = (args.site_root, args.out_dir, args.tag, args.commit,
                args.tag_object, args.source_date_epoch)
    if any(value is None for value in required):
        parser.error("package mode requires site root, output, tag, commit, tag object, and epoch")
    manifest = package(args.site_root, args.out_dir, args.tag, args.commit,
                       args.tag_object, args.source_date_epoch, args.asset)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
