#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Validate that course asset and material SKILL pages document local files.
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root  # noqa: E402

ROOT = find_repo_root(Path(__file__).resolve())
IMAGE_EXT = {".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}
ATTR_RE = re.compile(r"(?:href|src|data-svg-src|data-md-src)=[\"']([^\"']+)[\"']", re.I)
ASSET_CARD_RE = re.compile(r"<article[^>]+data-asset=[\"\']([^\"\']+)[\"\'][^>]*data-course-use=[\"\']([^\"\']+)[\"\']", re.I | re.S)


def local_targets(skill: Path) -> set[str]:
    text = skill.read_text(encoding="utf-8", errors="replace")
    out: set[str] = set()
    for raw in ATTR_RE.findall(text):
        raw = raw.strip()
        if not raw or raw.startswith(("#", "mailto:", "tel:", "data:")):
            continue
        u = urlparse(raw)
        if u.scheme or u.netloc:
            continue
        rel = unquote(u.path.split("#", 1)[0].split("?", 1)[0])
        if rel:
            out.add(rel)
    return out


def resolve(skill: Path, rel: str) -> Path:
    return (skill.parent / rel).resolve()


def asset_course_uses(skill: Path) -> dict[str, str]:
    text = skill.read_text(encoding="utf-8", errors="replace")
    return {unquote(asset): unquote(use) for asset, use in ASSET_CARD_RE.findall(text)}


def check_asset_images(fail: list[str]) -> tuple[int, int]:
    skill = ROOT / "web/nemoclaw/assets/SKILL.html"
    base = ROOT / "web/nemoclaw/assets"
    targets = local_targets(skill)
    uses = asset_course_uses(skill)
    images = sorted(
        p.relative_to(base).as_posix()
        for p in base.rglob("*")
        if p.is_file() and p.name != "SKILL.html" and p.suffix.lower() in IMAGE_EXT
    )
    for rel in [rel for rel in images if rel not in targets]:
        fail.append(f"assets/SKILL.html missing direct link for image: {rel}")
    for rel in images:
        use = uses.get(rel, "")
        if rel != "favicon.ico" and (not use or use == "not-used"):
            fail.append(f"assets/SKILL.html missing course-use link for image: {rel}")
        elif use and use != "not-used" and not (ROOT / "web/nemoclaw" / use).is_file():
            fail.append(f"assets/SKILL.html course-use target does not exist for {rel}: {use}")
    for rel in sorted(targets):
        if rel.startswith("../"):
            continue
        p = resolve(skill, rel)
        if (base in p.parents or p == base) and not p.is_file():
            fail.append(f"assets/SKILL.html local target does not exist: {rel}")
    return len(images), len(targets)


def check_mats(fail: list[str]) -> tuple[int, int]:
    skill = ROOT / "web/nemoclaw/mats/SKILL.html"
    base = ROOT / "web/nemoclaw/mats"
    targets = local_targets(skill)
    files = sorted(
        p.relative_to(base).as_posix()
        for p in base.rglob("*")
        if p.is_file() and p.name != "SKILL.html"
    )
    for rel in [rel for rel in files if rel not in targets]:
        fail.append(f"mats/SKILL.html missing direct link for material: {rel}")
    for rel in sorted(targets):
        if rel.startswith("../"):
            continue
        p = resolve(skill, rel)
        if (base in p.parents or p == base) and not p.is_file():
            fail.append(f"mats/SKILL.html local target does not exist: {rel}")
    return len(files), len(targets)


def run(verbose: bool = True) -> int:
    fail: list[str] = []
    n_img, _ = check_asset_images(fail)
    n_mat, _ = check_mats(fail)
    if fail:
        print("skill_asset_coverage: FAIL", file=sys.stderr)
        for item in fail:
            print("  " + item, file=sys.stderr)
        return 1
    if verbose:
        print(f"skill_asset_coverage: OK ({n_img} asset image(s), {n_mat} material file(s))")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    return run(verbose=not a.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
