#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Write a manifest containing only branch previews present in the Pages artifact."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path


def slug_ref(name: str) -> str:
    slug = re.sub(r"[^0-9a-z]+", "-", name.lower()).strip("-")[:63].strip("-")
    return slug or "branch"


def published_ref(spec: str) -> tuple[str, str]:
    name, sep, slug = spec.partition("=")
    name = name.strip()
    slug = (slug if sep else slug_ref(name)).strip()
    if not name or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", slug):
        raise ValueError(f"invalid published ref: {spec!r}")
    return name, slug


def generated_at() -> str:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None:
        value = dt.datetime.now(dt.timezone.utc)
    else:
        try:
            epoch = int(raw)
        except ValueError as exc:
            raise SystemExit("SOURCE_DATE_EPOCH must be a non-negative integer") from exc
        if epoch < 0:
            raise SystemExit("SOURCE_DATE_EPOCH must be a non-negative integer")
        value = dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
    return value.replace(microsecond=0).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--default-branch", default=os.environ.get("CI_DEFAULT_BRANCH", "main"))
    ap.add_argument("--current-ref")
    ap.add_argument("--current-slug")
    ap.add_argument("--published-ref", action="append", default=[], metavar="NAME[=SLUG]")
    ap.add_argument("--site-root-prefix", default="")
    ap.add_argument("--max", type=int, default=80)
    ns = ap.parse_args()

    default_branch = ns.default_branch or "main"
    production_refs = {default_branch, "nemoclaw-only"}
    current = ns.current_ref or default_branch
    current_slug = ns.current_slug or slug_ref(current)
    site_root_prefix = ns.site_root_prefix
    if site_root_prefix and not re.fullmatch(r"(?:\.\./)+", site_root_prefix):
        raise SystemExit("--site-root-prefix must be empty or one or more ../ segments")
    production_name = current if current in production_refs else default_branch

    refs: list[tuple[str, str, str]] = [(production_name, slug_ref(production_name), "production")]
    if current not in production_refs:
        refs.append((current, current_slug, "preview"))
    for spec in ns.published_ref:
        name, slug = published_ref(spec)
        kind = "production" if name in production_refs else "preview"
        refs.append((name, slug, kind))

    seen_slugs: set[str] = set()
    items = []
    for name, slug, kind in refs:
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        if kind == "production":
            url = f"{site_root_prefix}nemoclaw/"
        elif site_root_prefix and name == current:
            url = "web/nemoclaw/"
        else:
            url = f"{site_root_prefix}{slug}/web/nemoclaw/"
        items.append({
            "name": name,
            "slug": slug,
            "kind": kind,
            "url": url,
            "preview_ready": True,
            "current": bool(current and name == current),
        })
        if len(items) >= ns.max:
            break

    data = {
        "schema": "nemoclaw-branches/2",
        "generated_at": generated_at(),
        "default_branch": default_branch,
        "current": {"name": current, "slug": current_slug} if current else None,
        "production_url": f"{site_root_prefix}nemoclaw/",
        "note": "Every listed preview path is present in this Pages artifact.",
        "branches": items,
    }
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"[branches] wrote {out} ({len(items)} branches)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
