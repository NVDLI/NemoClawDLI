#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Project authoring sources into Pages so every SKILL explorer remains usable.

Tracked generated delivery output is rebuilt elsewhere in the artifact and is not projected a
second time. This prevents stale standalone output from becoming a second served course tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

GENERATED_OUTPUT_PREFIXES = (("web", "nemoclaw", "standalone"),)
GENERATED_ALIAS = Path("web/nemoclaw/standalone/SKILL.html")
PUBLIC_SOURCE_PREFIXES = {
    ".github": Path("source/github"),
    ".gitlab": Path("source/gitlab"),
}
URL_ATTRIBUTE_RE = re.compile(
    r'(?P<prefix>\b(?:href|src)\s*=\s*)(?P<quote>["\'])(?P<url>[^"\']*)(?P=quote)',
    re.IGNORECASE,
)
EXPLORER_CONFIG_RE = re.compile(
    r'(?P<open><script\b[^>]*\bid=["\']explorer-config["\'][^>]*>)'
    r'(?P<body>.*?)(?P<close></script>)',
    re.IGNORECASE | re.DOTALL,
)


def is_authoring_source(path: Path) -> bool:
    parts = path.parts
    return not any(parts[:len(prefix)] == prefix for prefix in GENERATED_OUTPUT_PREFIXES)


def source_files(root: Path) -> list[Path]:
    raw = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    )
    return sorted(
        path
        for item in raw.split(b"\0")
        if item
        for path in (Path(item.decode()),)
        if is_authoring_source(path) and (root / path).is_file()
    )


def tracked_generated_files(root: Path) -> list[Path]:
    """Find checked-in delivery output while allowing the source-tree navigation alias."""
    raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
    return sorted(
        path
        for item in raw.split(b"\0")
        if item
        for path in (Path(item.decode()),)
        if not is_authoring_source(path) and path != GENERATED_ALIAS and (root / path).is_file()
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def projected_path(relative: Path) -> Path:
    """Map source-control metadata directories to routes GitLab Pages serves verbatim."""
    if relative.parts and relative.parts[0] in PUBLIC_SOURCE_PREFIXES:
        return PUBLIC_SOURCE_PREFIXES[relative.parts[0]].joinpath(*relative.parts[1:])
    return relative


def _normalized_relative(base: Path, raw: str) -> Path | None:
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
        return None
    normalized = posixpath.normpath((base / parsed.path).as_posix())
    if normalized == ".." or normalized.startswith("../"):
        return None
    return Path(normalized)


def _project_url(raw: str, source_page: Path, artifact_page: Path, source_files_set: set[Path]) -> str:
    parsed = urlsplit(raw)
    source_target = _normalized_relative(source_page.parent, raw)
    if source_target is None or source_target not in source_files_set:
        return raw
    artifact_target = projected_path(source_target)
    relative = Path(os.path.relpath(artifact_target, artifact_page.parent)).as_posix()
    return urlunsplit(("", "", relative, parsed.query, parsed.fragment))


def _project_explorer_value(value: object, source_page: Path, artifact_page: Path,
                            source_files_set: set[Path]) -> object:
    if isinstance(value, list):
        return [_project_explorer_value(item, source_page, artifact_page, source_files_set) for item in value]
    if not isinstance(value, dict):
        return value
    projected: dict[str, object] = {}
    for key, item in value.items():
        if key in {"href", "path"} and isinstance(item, str):
            projected[key] = _project_url(item, source_page, artifact_page, source_files_set)
        else:
            projected[key] = _project_explorer_value(item, source_page, artifact_page, source_files_set)
    return projected


def project_html_urls(source_page: Path, artifact_page: Path, output: Path,
                      source_files_set: set[Path]) -> None:
    """Keep local links truthful when source-control metadata directories move to public routes."""
    artifact_file = output / artifact_page
    source = artifact_file.read_text(encoding="utf-8")

    def attribute(match: re.Match[str]) -> str:
        url = _project_url(match.group("url"), source_page, artifact_page, source_files_set)
        return f'{match.group("prefix")}{match.group("quote")}{url}{match.group("quote")}'

    updated = URL_ATTRIBUTE_RE.sub(attribute, source)

    def explorer(match: re.Match[str]) -> str:
        try:
            config = json.loads(match.group("body"))
        except json.JSONDecodeError:
            return match.group(0)
        config = _project_explorer_value(config, source_page, artifact_page, source_files_set)
        body = json.dumps(config, indent=2, ensure_ascii=False)
        return f'{match.group("open")}\n{body}\n{match.group("close")}'

    updated = EXPLORER_CONFIG_RE.sub(explorer, updated)
    if updated != source:
        artifact_file.write_text(updated, encoding="utf-8")


def project_json_urls(source_file: Path, artifact_file: Path, output: Path,
                      source_files_set: set[Path]) -> None:
    """Rebase local evidence/configuration links that browser renderers resolve at runtime."""
    target = output / artifact_file
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    projected = _project_explorer_value(value, source_file, artifact_file, source_files_set)
    if projected != value:
        target.write_text(json.dumps(projected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def project(root: Path, output: Path) -> tuple[int, list[str]]:
    findings = [
        f"tracked generated output must be rebuilt, not versioned: {path}"
        for path in tracked_generated_files(root)
    ]
    files = source_files(root)
    file_set = set(files)
    for relative in files:
        source = root / relative
        target = output / projected_path(relative)
        if not source.is_file():
            findings.append(f"source is not a regular file: {relative}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for relative in files:
        source = root / relative
        target = output / projected_path(relative)
        if not target.is_file():
            findings.append(f"projected source is missing: {relative}")
        elif source.stat().st_size != target.stat().st_size or digest(source) != digest(target):
            findings.append(f"projected source differs: {relative}")
    for relative in files:
        if relative.suffix.lower() == ".html":
            project_html_urls(relative, projected_path(relative), output, file_set)
        elif relative.suffix.lower() == ".json":
            project_json_urls(relative, projected_path(relative), output, file_set)
    return len(files), findings


class ProjectionTests(unittest.TestCase):
    def test_tracked_and_proposed_files_project_but_ignored_output_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            output = Path(temp) / "artifact"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
            (root / "SKILL.html").write_text(
                '<a href=".github/SKILL.html">workflow map</a>', encoding="utf-8"
            )
            workflow_skill = root / ".github" / "SKILL.html"
            workflow_skill.parent.mkdir()
            workflow_skill.write_text(
                '<a href="../SKILL.html">root</a>'
                '<script type="application/json" id="explorer-config">'
                '{"files":[{"path":"workflows/pages.yml"}]}</script>',
                encoding="utf-8",
            )
            workflow = root / ".github" / "workflows" / "pages.yml"
            workflow.parent.mkdir()
            workflow.write_text("name: pages\n", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "tracked.txt").write_text("tracked", encoding="utf-8")
            (root / "nested" / "evidence.json").write_text(
                '{"links":[{"href":"../.github/SKILL.html"}]}\n', encoding="utf-8"
            )
            generated = root / "web" / "nemoclaw" / "standalone" / "index.html"
            generated.parent.mkdir(parents=True)
            generated.write_text("generated", encoding="utf-8")
            subprocess.run([
                "git", "-C", str(root), "add", ".gitignore", "SKILL.html", "nested/tracked.txt",
                ".github/SKILL.html", ".github/workflows/pages.yml", "nested/evidence.json",
            ], check=True)
            subprocess.run(["git", "-C", str(root), "add", "web/nemoclaw/standalone/index.html"], check=True)
            alias = root / GENERATED_ALIAS
            alias.write_text("navigation alias", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", str(GENERATED_ALIAS)], check=True)
            (root / "nested" / "deleted-after-indexing.txt").write_text("gone", encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "nested/deleted-after-indexing.txt"],
                check=True,
            )
            (root / "nested" / "deleted-after-indexing.txt").unlink()
            (root / "nested" / "proposed.txt").write_text("proposed", encoding="utf-8")
            (root / "ignored").mkdir()
            (root / "ignored" / "build.txt").write_text("ignored", encoding="utf-8")
            count, findings = project(root, output)
            self.assertEqual(
                findings,
                ["tracked generated output must be rebuilt, not versioned: "
                 "web/nemoclaw/standalone/index.html"],
            )
            self.assertEqual(count, 7)
            self.assertTrue((output / "nested" / "tracked.txt").is_file())
            self.assertTrue((output / "nested" / "proposed.txt").is_file())
            self.assertFalse((output / "nested" / "deleted-after-indexing.txt").exists())
            self.assertFalse((output / "ignored" / "build.txt").exists())
            self.assertFalse((output / "web" / "nemoclaw" / "standalone" / "index.html").exists())
            self.assertFalse((output / ".github").exists())
            projected_skill = output / "source" / "github" / "SKILL.html"
            self.assertTrue(projected_skill.is_file())
            self.assertIn('href="../../SKILL.html"', projected_skill.read_text(encoding="utf-8"))
            self.assertIn('"path": "workflows/pages.yml"', projected_skill.read_text(encoding="utf-8"))
            self.assertIn(
                'href="source/github/SKILL.html"',
                (output / "SKILL.html").read_text(encoding="utf-8"),
            )
            evidence = json.loads((output / "nested" / "evidence.json").read_text(encoding="utf-8"))
            self.assertEqual("../source/github/SKILL.html", evidence["links"][0]["href"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check-generated", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProjectionTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.check_generated:
        root = (args.source_root or Path(__file__).resolve().parents[2]).resolve()
        findings = tracked_generated_files(root)
        if findings:
            for path in findings:
                print(f"tracked generated output must be rebuilt, not versioned: {path}")
            return 1
        print("tracked generated output: PASS")
        return 0
    if not args.source_root or not args.artifact_root:
        parser.error("--source-root and --artifact-root are required unless a check mode is used")
    count, findings = project(args.source_root.resolve(), args.artifact_root.resolve())
    if findings:
        print(f"source explorer projection: FAIL ({len(findings)})")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(f"source explorer projection: PASS ({count} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
