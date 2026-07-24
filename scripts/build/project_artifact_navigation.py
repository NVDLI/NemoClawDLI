#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Project every generated explorer/navigation surface to one static artifact root."""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from bundle_standalone import project_artifact_navigation


LAB_STATIC_URL_RE = re.compile(
    r'(?P<quote>["\'])/lab/static/(?P<url>[^"\']*)(?P=quote)'
)


def project_lab_static_urls(root: Path, course_prefix: str = "") -> int:
    """Resolve lab-mounted URLs against files that exist in one static artifact.

    Repository paths remain rooted at the artifact root. A relocated course can
    live below ``course_prefix``; that candidate is used only when the literal
    artifact-root target does not exist. Unresolved and escaping targets remain
    visible for the exhaustive link audit to reject.
    """
    root = root.resolve()
    prefix = course_prefix.strip("/")
    changed = 0
    for page in sorted(root.rglob("*.html")):
        source = page.read_text(encoding="utf-8")

        def replace(match: re.Match[str]) -> str:
            parsed = urlsplit(match.group("url"))
            relative_path = Path(parsed.path)
            candidates = [root / relative_path]
            if prefix:
                candidates.append(root / prefix / relative_path)
            target = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
            try:
                target.resolve().relative_to(root)
            except ValueError:
                return match.group(0)
            path = Path(os.path.relpath(target, page.parent)).as_posix()
            projected = urlunsplit(("", "", path, parsed.query, parsed.fragment))
            quote = match.group("quote")
            return f"{quote}{projected}{quote}"

        updated = LAB_STATIC_URL_RE.sub(replace, source)
        if updated != source:
            page.write_text(updated, encoding="utf-8")
            changed += 1
    return changed


def project_generated_output_aliases(root: Path, course_prefix: str = "") -> int:
    """Resolve source-tree standalone routes to the freshly built course artifact.

    Source mirrors deliberately omit tracked generated output. If a course source map links its
    ``standalone/SKILL.html`` route, preserve that route as a redirect to the build produced in
    this artifact instead of hiding the link or copying a stale nested build.
    """
    root = root.resolve()
    prefix = course_prefix.strip("/")
    changed = 0
    for skill in sorted(root.rglob("SKILL.html")):
        if skill.parent.parent.name != "web" or "standalone/SKILL.html" not in skill.read_text(encoding="utf-8"):
            continue
        alias = skill.parent / "standalone/SKILL.html"
        if alias.is_file():
            continue
        course = skill.parent.name
        relative_parts = skill.relative_to(root).parts
        target = root / prefix / course / "SKILL.html"
        if "i18n" in relative_parts:
            index = relative_parts.index("i18n")
            if index + 1 < len(relative_parts):
                localized = root / relative_parts[index + 1] / course / "SKILL.html"
                if localized.is_file():
                    target = localized
        if not target.is_file():
            continue
        alias.parent.mkdir(parents=True, exist_ok=True)
        href = Path(os.path.relpath(target, alias.parent)).as_posix()
        alias.write_text(
            '<!doctype html><html><head><meta charset="utf-8">'
            f'<meta http-equiv="refresh" content="0;url={href}">'
            '<title>Current standalone artifact</title></head><body><p>'
            f'<a href="{href}">Open the current standalone artifact map</a>'
            '</p></body></html>\n',
            encoding="utf-8",
        )
        changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--lab-static-prefix", default="")
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"artifact root is not a directory: {args.root}")
    lab_urls = project_lab_static_urls(args.root, args.lab_static_prefix)
    aliases = project_generated_output_aliases(args.root, args.lab_static_prefix)
    changed = project_artifact_navigation(args.root.resolve())
    print(
        "artifact navigation projection: PASS "
        f"({changed} navigation files; {lab_urls} lab-static files; {aliases} generated-output aliases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
