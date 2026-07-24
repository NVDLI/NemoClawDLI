#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Project docs explorer files and rendered Markdown targets into a Pages artifact."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit


CONFIG_RE = re.compile(
    r'<script[^>]*id="explorer-config"[^>]*>(.*?)</script>', re.DOTALL
)
FENCE_LINE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
INLINE_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^)\s]+)")
REFERENCE_LINK_RE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)", re.MULTILINE)
DOC_KINDS = {"authored", "canonical", "generated"}


class ProjectionError(ValueError):
    """Raised when a declared or linked artifact cannot be projected safely."""


def explorer_config(skill: Path) -> dict:
    match = CONFIG_RE.search(skill.read_text(encoding="utf-8"))
    if not match:
        raise ProjectionError("docs explorer projection: missing explorer-config")
    try:
        config = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ProjectionError(f"docs explorer projection: invalid explorer-config: {exc}") from exc
    if not isinstance(config.get("files"), list):
        raise ProjectionError("docs explorer projection: explorer-config.files must be an array")
    return config


def local_markdown_targets(path: Path) -> list[str]:
    """Return local inline/image/reference targets from one rendered Markdown file."""
    visible: list[str] = []
    fence_char = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        marker = FENCE_LINE_RE.match(line)
        if marker:
            current = marker.group(1)[0]
            if not fence_char:
                fence_char = current
            elif current == fence_char:
                fence_char = ""
            continue
        if not fence_char:
            visible.append(line)
    text = "\n".join(visible)
    raw_targets = [match.group(1) for match in INLINE_LINK_RE.finditer(text)]
    raw_targets.extend(match.group(1) for match in REFERENCE_LINK_RE.finditer(text))
    targets: list[str] = []
    for raw in raw_targets:
        target = raw.strip().strip("<>")
        if not target or target.startswith("#"):
            continue
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc:
            continue
        decoded = unquote(parsed.path)
        if decoded:
            targets.append(decoded)
    return targets


def safe_source(root: Path, base: Path, relative: str, *, context: str) -> Path:
    if "\\" in relative or "\x00" in relative:
        raise ProjectionError(f"docs explorer projection: unsafe {context}: {relative}")
    target = (base / relative).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ProjectionError(
            f"docs explorer projection: missing or unsafe {context}: {relative}"
        )
    return target


def copy_into_artifact(source: Path, source_root: Path, artifact_root: Path) -> Path:
    destination = (artifact_root / source.relative_to(source_root)).resolve()
    if not destination.is_relative_to(artifact_root):
        raise ProjectionError(f"docs explorer projection: unsafe artifact target: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def audit_catalog(source_skill: Path, source_root: Path) -> tuple[int, int]:
    """Verify docs inventory, source/projection declarations, and contextual links."""
    source_root = source_root.resolve()
    source_skill = source_skill.resolve()
    config = explorer_config(source_skill)
    entries = config["files"]
    seen: set[str] = set()
    direct_entries: dict[Path, dict] = {}

    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ProjectionError("docs catalog: every file entry needs a string path")
        relative = entry["path"]
        if relative in seen:
            raise ProjectionError(f"docs catalog: duplicate file entry: {relative}")
        seen.add(relative)
        source = safe_source(
            source_root, source_skill.parent, relative, context="catalog file"
        )
        if source.parent == source_skill.parent:
            kind = entry.get("kind")
            if kind not in DOC_KINDS:
                raise ProjectionError(
                    f"docs catalog: {relative} needs kind authored, canonical, or generated"
                )
            direct_entries[source] = entry

    authored_on_disk = set(source_skill.parent.glob("*.md"))
    authored_declared = {
        path for path, entry in direct_entries.items() if entry.get("kind") == "authored"
    }
    missing = sorted(path.name for path in authored_on_disk - authored_declared)
    extra = sorted(
        path.name for path in authored_declared if path.suffix.lower() != ".md"
    )
    if missing:
        raise ProjectionError(f"docs catalog: unlisted authored Markdown: {', '.join(missing)}")
    if extra:
        raise ProjectionError(f"docs catalog: authored entries must be Markdown: {', '.join(extra)}")

    for path, entry in direct_entries.items():
        kind = entry["kind"]
        generated_from = entry.get("generated_from")
        if kind == "generated":
            if not isinstance(generated_from, str):
                raise ProjectionError(
                    f"docs catalog: generated file {path.name} needs generated_from"
                )
            canonical = safe_source(
                source_root,
                source_skill.parent,
                generated_from,
                context=f"canonical source for {path.name}",
            )
            canonical_entry = direct_entries.get(canonical)
            if not canonical_entry or canonical_entry.get("kind") != "canonical":
                raise ProjectionError(
                    f"docs catalog: generated source for {path.name} is not canonical"
                )
        elif generated_from is not None:
            raise ProjectionError(
                f"docs catalog: only generated files may declare generated_from: {path.name}"
            )

    inbound = {path: 0 for path in authored_declared}
    outbound = {path: 0 for path in authored_declared}
    for markdown in authored_declared:
        for relative in local_markdown_targets(markdown):
            target = (markdown.parent / relative).resolve()
            if target in authored_declared and target != markdown:
                outbound[markdown] += 1
                inbound[target] += 1

    for markdown in sorted(authored_declared):
        if not outbound[markdown]:
            raise ProjectionError(
                f"docs catalog: authored document has no contextual outbound link: {markdown.name}"
            )
        if not inbound[markdown]:
            raise ProjectionError(
                f"docs catalog: authored document has no contextual inbound link: {markdown.name}"
            )

    return len(direct_entries), sum(outbound.values())


def project(source_skill: Path, source_root: Path, artifact_root: Path) -> tuple[int, int]:
    source_root = source_root.resolve()
    artifact_root = artifact_root.resolve()
    source_skill = source_skill.resolve()
    if not source_skill.is_relative_to(source_root) or not source_skill.is_file():
        raise ProjectionError("docs explorer projection: source SKILL.html is outside the repository")

    audit_catalog(source_skill, source_root)
    config = explorer_config(source_skill)
    declared: list[Path] = []
    for entry in config["files"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ProjectionError("docs explorer projection: every file entry needs a string path")
        source = safe_source(
            source_root, source_skill.parent, entry["path"], context="declared file"
        )
        copy_into_artifact(source, source_root, artifact_root)
        declared.append(source)

    linked: set[Path] = set()
    for markdown in (path for path in declared if path.suffix.lower() == ".md"):
        for relative in local_markdown_targets(markdown):
            source = safe_source(
                source_root,
                markdown.parent,
                relative,
                context=f"local Markdown target from {markdown.relative_to(source_root)}",
            )
            copy_into_artifact(source, source_root, artifact_root)
            linked.add(source)

    for source in set(declared) | linked:
        destination = artifact_root / source.relative_to(source_root)
        if not destination.is_file():
            raise ProjectionError(
                "docs explorer projection: projected file missing from artifact: "
                f"{source.relative_to(source_root)}"
            )
    return len(declared), len(linked)


def self_test() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="docs-projection-") as tmp:
        base = Path(tmp)
        root = base / "repo"
        docs = root / "docs"
        docs.mkdir(parents=True)
        (root / "RELEASE_STATUS.json").write_text('{"state":"draft"}\n', encoding="utf-8")
        (docs / "design.md").write_text(
            "[tests](test-plan.md) [state](../RELEASE_STATUS.json) "
            "[outside](https://example.com)\n",
            encoding="utf-8",
        )
        (docs / "test-plan.md").write_text("[design](design.md)\n", encoding="utf-8")
        (docs / "architecture.json").write_text('{"nodes":[]}\n', encoding="utf-8")
        (docs / "architecture.svg").write_text("<svg/>\n", encoding="utf-8")
        skill = docs / "SKILL.html"
        skill.write_text(
            '<script type="application/json" id="explorer-config">'
            '{"files":['
            '{"path":"design.md","kind":"authored"},'
            '{"path":"test-plan.md","kind":"authored"},'
            '{"path":"architecture.json","kind":"canonical"},'
            '{"path":"architecture.svg","kind":"generated",'
            '"generated_from":"architecture.json"}'
            ']}</script>\n',
            encoding="utf-8",
        )

        artifact = base / "artifact"
        declared, linked = project(skill, root, artifact)
        checks = [
            (declared == 4 and linked == 3, "declared and linked counts"),
            ((artifact / "docs/design.md").is_file(), "declared file projection"),
            ((artifact / "RELEASE_STATUS.json").is_file(), "Markdown target projection"),
            (audit_catalog(skill, root) == (4, 2), "catalog and graph counts"),
        ]
        failures.extend(label for passed, label in checks if not passed)

        (docs / "fenced.md").write_text(
            "```text\n[ignored](missing.md)\n```\n\n[visible](test-plan.md)\n",
            encoding="utf-8",
        )
        if local_markdown_targets(docs / "fenced.md") != ["test-plan.md"]:
            failures.append("fenced Markdown hid or exposed the wrong target")
        (docs / "fenced.md").unlink()

        (docs / "design.md").write_text(
            "[tests](test-plan.md) [missing](../missing.json)\n", encoding="utf-8"
        )
        try:
            project(skill, root, base / "broken-artifact")
        except ProjectionError as exc:
            if "local Markdown target" not in str(exc):
                failures.append("missing target error classification")
        else:
            failures.append("missing target was accepted")

        (docs / "design.md").write_text("No contextual link.\n", encoding="utf-8")
        try:
            audit_catalog(skill, root)
        except ProjectionError as exc:
            if "outbound link" not in str(exc):
                failures.append("orphan error classification")
        else:
            failures.append("contextual orphan was accepted")

        (docs / "design.md").write_text("[tests](test-plan.md)\n", encoding="utf-8")
        (docs / "unlisted.md").write_text("[design](design.md)\n", encoding="utf-8")
        try:
            audit_catalog(skill, root)
        except ProjectionError as exc:
            if "unlisted authored Markdown" not in str(exc):
                failures.append("unlisted document error classification")
        else:
            failures.append("unlisted authored document was accepted")
        (docs / "unlisted.md").unlink()

        broken_skill = docs / "BROKEN_SKILL.html"
        broken_skill.write_text(
            '<script type="application/json" id="explorer-config">'
            '{"files":['
            '{"path":"design.md","kind":"authored"},'
            '{"path":"test-plan.md","kind":"authored"},'
            '{"path":"architecture.json","kind":"canonical"},'
            '{"path":"architecture.svg","kind":"generated"}'
            ']}</script>\n',
            encoding="utf-8",
        )
        try:
            audit_catalog(broken_skill, root)
        except ProjectionError as exc:
            if "needs generated_from" not in str(exc):
                failures.append("generated-source error classification")
        else:
            failures.append("generated file without canonical source was accepted")

        duplicate_skill = docs / "DUPLICATE_SKILL.html"
        duplicate_skill.write_text(
            '<script type="application/json" id="explorer-config">'
            '{"files":['
            '{"path":"design.md","kind":"authored"},'
            '{"path":"design.md","kind":"authored"}'
            ']}</script>\n',
            encoding="utf-8",
        )
        try:
            audit_catalog(duplicate_skill, root)
        except ProjectionError as exc:
            if "duplicate file entry" not in str(exc):
                failures.append("duplicate error classification")
        else:
            failures.append("duplicate catalog entry was accepted")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-skill", type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        failures = self_test()
        print("docs explorer projection self-test: " + ("FAIL" if failures else "PASS"))
        for failure in failures:
            print(f"  FAIL {failure}")
        return 1 if failures else 0
    if args.audit:
        source_root = (args.source_root or Path(__file__).resolve().parents[2]).resolve()
        source_skill = (args.source_skill or source_root / "docs/SKILL.html").resolve()
        try:
            files, links = audit_catalog(source_skill, source_root)
        except (OSError, ProjectionError) as exc:
            print(exc)
            return 1
        print(f"docs catalog audit: PASS files={files} contextual_links={links}")
        return 0
    if not (args.source_skill and args.source_root and args.artifact_root):
        parser.error("--source-skill, --source-root, and --artifact-root are required")
    try:
        declared, linked = project(args.source_skill, args.source_root, args.artifact_root)
    except (OSError, ProjectionError) as exc:
        print(exc)
        return 1
    print(
        f"[build_pages] docs explorer projection: {declared} declared files and "
        f"{linked} local Markdown targets resolve"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
