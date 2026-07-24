#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Map the file-reference web of the released course (web/nemoclaw/).

For every text-ish file under web/nemoclaw/, extract anything that looks
like a file path or import target, resolve it against the filesystem,
and classify the destination:

  internal       - resolves to a file inside web/nemoclaw/ (this includes the
                   course-scoped reference layer web/nemoclaw/mats/)
  shared         - resolves to shared repository tooling or documentation
  cross_course   - resolves to another course (none ship in this release)
  external_url   - http(s) URL
  missing        - looks like a path but does not resolve

The release ships a single course, so the "cross_course" bucket is expected
to be empty; any hit is a stray reference to removed content and is the
action list. A reference into the course-scoped mats/ (web/nemoclaw/mats/) is
the sanctioned reference-layer pattern.

Usage:

  python3 scripts/validation/reference_graph.py                  # human report to stdout
  python3 scripts/validation/reference_graph.py --json out.json  # machine-readable
  python3 scripts/validation/reference_graph.py --only-cross     # just the action list
  python3 scripts/validation/reference_graph.py --only-missing   # broken refs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root
from typing import Iterable

# ───────────────────────────────────────────────────────────────────────
# Paths
# ───────────────────────────────────────────────────────────────────────

HERE      = Path(__file__).resolve()
TASK1     = find_repo_root(HERE)
COURSE    = TASK1 / "web" / "nemoclaw"         # the released course
REPO      = TASK1.parent                        # the DLI wrapper root (above task1)

# Sibling courses (this list is the ground truth for "cross-course"). The
# release ships only nemoclaw, so there are no siblings; any name listed here
# is a removed course whose path, if it still appears, is a stray reference.
SIBLING_COURSES = {
    "adv_rag", "agent_fleets", "agent_interfaces", "agentic_ai",
    "build_agents", "openshell", "prompt_eng",
    "deep_learning", "graph_rag", "multimodal", "rag_agents",
    "rapid_app_dev", "video_agents",
}

# Shared-infra directories the released course may freely depend on.
SHARED_INFRA = {
    "services", "llm_client", "export",
}

# Where mats live. They are course-scoped under web/nemoclaw/; refs from mats are sanctioned.
MATS_DIR = TASK1 / "web" / "nemoclaw" / "mats"

# Text-ish file types worth scanning.
TEXT_EXTS = {
    ".md", ".html", ".htm", ".py", ".css", ".js", ".mjs", ".ipynb",
    ".json", ".svg", ".yaml", ".yml", ".toml", ".txt", ".sh", ".cfg",
}

# Skip these dirs entirely (large generated content, bundle outputs).
# web_standalone is the bundler's DEFAULT_OUT; nemoclaw_standalone is the
# auto-derived output for the shipped course (bundle_standalone.py appends
# _standalone to the --src name).
SKIP_DIRS = {
    "web_standalone", "nemoclaw_standalone", "node_modules",
    "__pycache__", ".ipynb_checkpoints", "_paper_cache", "export",
    ".gradio", ".pytest_cache",
}

# ───────────────────────────────────────────────────────────────────────
# Reference extraction
# ───────────────────────────────────────────────────────────────────────

# Token that looks like a path: a sequence of [\w./-] containing a slash OR ending in a known extension.
# Trailing punctuation stripped later.
PATH_TOKEN = re.compile(
    r"""
    (?:                                # path is either:
      [\w][\w.\-/]*                    #   bare word with dots/slashes/hyphens
    )
    """,
    re.VERBOSE,
)

# URL pattern (caught separately, not classified as a filesystem path).
URL_PATTERN = re.compile(r"https?://[^\s<>\"')]+")

# Domain-like tokens that often appear without a scheme and get
# mis-matched as relative paths (e.g. "lms.s3.amazonaws.com/x.png").
# We mask these before the path extractor runs.
DOMAIN_PATTERN = re.compile(
    r"\b[\w-]+\.(?:s3\.amazonaws\.com|amazonaws\.com|cloudfront\.net|"
    r"workers\.dev|build\.nvidia\.com|nvidia\.com|github\.com|"
    r"github\.io|cloudapp\.azure\.com|azurewebsites\.net|"
    r"azurecontainerapps\.io)(?:/[^\s<>\"')]+)?",
    re.IGNORECASE,
)

# Extension-anchored path matcher. A match must end with a text-ish extension.
# This is the primary extractor.
#
# Right boundary excludes `(` so that JS/Python method calls like
# `response.json()` or `record.toml(...)` don't get matched as files.
EXT_REGEX = re.compile(
    r"""
    (?<![A-Za-z0-9_./])                # left boundary: not a path char
    (
      (?:\.{1,2}/)?                    # optional ./ or ../ prefix
      (?:[\w@][\w.@\-]*/)*             # zero or more dir segments
      [\w@][\w.@\-]*                   # filename stem
      \.(?:md|html?|py|css|js|mjs|ipynb|json|svg|png|jpe?g|gif|webp|yaml|yml|toml|txt|sh|cfg|ya?ml)
    )
    (?![\w/(])                         # right boundary: not a path char, not a `(`
    """,
    re.VERBOSE | re.IGNORECASE,
)


@dataclass
class Reference:
    src_file: Path                      # absolute path of the file that contains the ref
    target: str                         # raw matched string
    line: int                           # 1-indexed line number
    resolved: Path | None = None        # absolute resolved path (None if URL/unresolvable)
    category: str = "unknown"           # see classify()
    kind: str = "path"                  # "path" | "url"


@dataclass
class Report:
    refs: list[Reference] = field(default_factory=list)
    scanned_files: int = 0
    scanned_bytes: int = 0

    def by_category(self) -> dict[str, list[Reference]]:
        out = defaultdict(list)
        for r in self.refs:
            out[r.category].append(r)
        return out


# ───────────────────────────────────────────────────────────────────────
# Resolution + classification
# ───────────────────────────────────────────────────────────────────────

def _strip_trailing_punct(s: str) -> str:
    """Most regex matches catch a trailing ).,;: from prose. Drop it."""
    while s and s[-1] in ").,;:!\"'>":
        s = s[:-1]
    return s


def resolve_target(target: str, src_file: Path) -> Path | None:
    """Try to resolve target relative to src_file's directory, then to
    a few sensible roots. Returns the absolute resolved path if it
    exists, else None."""
    target = _strip_trailing_punct(target)
    if not target:
        return None
    # Strip query / fragment.
    for sep in ("#", "?"):
        if sep in target:
            target = target.split(sep, 1)[0]
    if not target:
        return None

    candidates: list[Path] = []
    src_dir = src_file.parent
    if target.startswith("/"):
        # Treat absolute-style paths (e.g. /lab/static/foo) as repo-rooted.
        candidates.append(REPO / target.lstrip("/"))
        candidates.append(TASK1 / target.lstrip("/"))
    else:
        candidates.append((src_dir / target).resolve())
        candidates.append((COURSE / target).resolve())
        # Task1-root: catches a stray reference to a removed sibling course
        # written as "openshell/05_X.md" from a course page.
        candidates.append((TASK1 / target).resolve())

    for c in candidates:
        try:
            if c.exists():
                return c
        except OSError:
            continue
    return None


def classify(target: str, resolved: Path | None, src_file: Path) -> str:
    """Classify a reference into one of the buckets defined at top."""
    if resolved is None:
        # Even an unresolvable ref can be semantically cross-course if the
        # first path segment names a known sibling. Catches dangling refs
        # like "agentic_ai/foo.ipynb" where the link rotted but the intent
        # is obvious.
        stripped = _strip_trailing_punct(target).lstrip("./")
        first_seg = stripped.split("/", 1)[0]
        if first_seg in SIBLING_COURSES:
            return "cross_course"
        return "missing"
    try:
        resolved.relative_to(COURSE)
        return "internal"
    except ValueError:
        pass
    # Anchor the lookup on the repo root rather than on substring matches,
    # so we don't accidentally pick up a "workspace" segment from an
    # unrelated host mount outside the repository.
    try:
        rel = resolved.relative_to(REPO).parts
    except ValueError:
        return "shared"
    if rel and rel[0] == "archived_courses":
        return "cross_course"
    # Surface-first layout: task1/{web,cpu,dgx}/<course>/...
    if len(rel) >= 3 and rel[0] == "task1" and rel[1] in ("web", "cpu", "dgx"):
        surface, top = rel[1], rel[2]
        if surface == "web" and top == "nemoclaw":
            return "internal"
        if top in SHARED_INFRA or top == "services":
            return "shared"
        if top in SIBLING_COURSES:
            return "cross_course"
    return "shared"  # fallback: anywhere else under the repo (docs, ci, …)


# ───────────────────────────────────────────────────────────────────────
# Scan
# ───────────────────────────────────────────────────────────────────────

SELF_PATH = Path(__file__).resolve()

# Derived/generated files that live under the course dir but don't reflect
# course truth. navigator.html is produced by vendor_navigator.py;
# graphics.html is produced by aggregate_graphics.py. Both are gitignored.
DERIVED_FILES = {
    COURSE / "navigator.html",
    COURSE / "graphics.html",
}


def iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in TEXT_EXTS:
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.resolve() == SELF_PATH:
            continue  # don't flag the script's own sibling-course list
        if p.resolve() in {d.resolve() for d in DERIVED_FILES if d.exists()}:
            continue
        yield p


def extract_refs(text: str, src_file: Path) -> list[Reference]:
    refs: list[Reference] = []
    # URLs.
    for m in URL_PATTERN.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        refs.append(Reference(
            src_file=src_file, target=m.group(0), line=line,
            resolved=None, category="external_url", kind="url",
        ))
    # Mask URLs and bare-domain tokens before the path extractor sees them,
    # otherwise tokens like "lms.s3.amazonaws.com/foo.png" or the path part
    # of a full URL get re-matched as relative paths.
    masked = URL_PATTERN.sub(lambda m: " " * len(m.group(0)), text)
    masked = DOMAIN_PATTERN.sub(lambda m: " " * len(m.group(0)), masked)
    # Path-like tokens.
    seen: set[tuple[str, int]] = set()
    for m in EXT_REGEX.finditer(masked):
        raw = m.group(1)
        line = text.count("\n", 0, m.start()) + 1
        # de-dupe per (target, line)
        key = (raw, line)
        if key in seen:
            continue
        seen.add(key)
        resolved = resolve_target(raw, src_file)
        cat = classify(raw, resolved, src_file)
        refs.append(Reference(
            src_file=src_file, target=raw, line=line,
            resolved=resolved, category=cat, kind="path",
        ))
    return refs


def scan(root: Path = COURSE) -> Report:
    rep = Report()
    for f in iter_files(root):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rep.scanned_files += 1
        rep.scanned_bytes += len(text)
        rep.refs.extend(extract_refs(text, f))
    return rep


# ───────────────────────────────────────────────────────────────────────
# Reporting
# ───────────────────────────────────────────────────────────────────────

def _rel(p: Path) -> str:
    """Path relative to course root, falling back to repo-relative."""
    for base in (COURSE, TASK1, REPO):
        try:
            return str(p.relative_to(base))
        except ValueError:
            continue
    return str(p)


def render_text(rep: Report, *, only: str | None = None) -> str:
    by = rep.by_category()
    lines: list[str] = []
    lines.append("# web/nemoclaw/ reference graph")
    lines.append("")
    lines.append(f"Scanned {rep.scanned_files} files / "
                 f"{rep.scanned_bytes/1024:.0f} KB total.")
    lines.append("")
    lines.append("## Summary by category")
    lines.append("")
    for cat in ("internal", "shared", "cross_course", "external_url", "missing"):
        n = len(by.get(cat, []))
        lines.append(f"  {cat:14s} {n:5d}")
    lines.append("")

    def emit(cat: str, header: str, *, show_sanctioned_separately: bool = False):
        bucket = by.get(cat, [])
        if not bucket:
            return
        lines.append(f"## {header} ({len(bucket)})")
        lines.append("")
        # Group by source file for readability.
        by_src: dict[Path, list[Reference]] = defaultdict(list)
        for r in bucket:
            by_src[r.src_file].append(r)
        sanctioned_refs: list[Reference] = []
        for src in sorted(by_src, key=_rel):
            in_mats = src.is_relative_to(MATS_DIR) if hasattr(src, "is_relative_to") else (MATS_DIR in src.parents)
            if show_sanctioned_separately and in_mats:
                sanctioned_refs.extend(by_src[src])
                continue
            lines.append(f"### {_rel(src)}")
            for r in sorted(by_src[src], key=lambda x: x.line):
                rt = _rel(r.resolved) if r.resolved else "(unresolved)"
                lines.append(f"  L{r.line:<4d} {r.target}")
                if r.resolved:
                    lines.append(f"         → {rt}")
            lines.append("")
        if sanctioned_refs:
            lines.append(f"### · mats/ learning-path entries (sanctioned, {len(sanctioned_refs)})")
            by_src_mats: dict[Path, list[Reference]] = defaultdict(list)
            for r in sanctioned_refs:
                by_src_mats[r.src_file].append(r)
            for src in sorted(by_src_mats, key=_rel):
                lines.append(f"  · {_rel(src)} ({len(by_src_mats[src])} refs)")
            lines.append("")

    if only is None or only == "cross_course":
        emit("cross_course", "Cross-course references (action list)",
             show_sanctioned_separately=True)
    if only is None or only == "missing":
        emit("missing", "Missing / broken references")
    if only is None:
        lines.append("## Shared-infra references")
        lines.append("")
        by_top: dict[str, int] = defaultdict(int)
        for r in by.get("shared", []):
            if r.resolved:
                # Surface-first layout: shared repository infrastructure resolves from the root.
                # (for example scripts/) or a top-level task1 peer (docs/); the mats
                # reference layer is now course-scoped under web/nemoclaw/mats/.
                # Bucket by the meaningful shared-dir segment relative to task1/.
                try:
                    rel = r.resolved.relative_to(TASK1).parts
                except ValueError:
                    by_top["(other)"] += 1
                    continue
                if len(rel) >= 2 and rel[0] in ("cpu", "dgx"):
                    by_top[rel[1]] += 1
                elif rel:
                    by_top[rel[0]] += 1
                else:
                    by_top["(other)"] += 1
        for top in sorted(by_top, key=lambda k: -by_top[k]):
            lines.append(f"  {top:20s} {by_top[top]:5d}")
        lines.append("")

    return "\n".join(lines)


def render_json(rep: Report) -> str:
    out = {
        "scanned_files": rep.scanned_files,
        "scanned_bytes": rep.scanned_bytes,
        "refs": [
            {
                "src":      _rel(r.src_file),
                "target":   r.target,
                "line":     r.line,
                "resolved": _rel(r.resolved) if r.resolved else None,
                "category": r.category,
                "kind":     r.kind,
            }
            for r in rep.refs
        ],
    }
    return json.dumps(out, indent=2)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", metavar="PATH", default=None,
                    help="Write machine-readable JSON to PATH (also prints text report unless --quiet)")
    ap.add_argument("--quiet", action="store_true", help="Skip the text report")
    ap.add_argument("--only-cross", action="store_true",
                    help="Only show the cross-course action list")
    ap.add_argument("--only-missing", action="store_true",
                    help="Only show missing/broken refs")
    args = ap.parse_args()

    rep = scan()

    if args.json:
        Path(args.json).write_text(render_json(rep), encoding="utf-8")

    if not args.quiet:
        only = None
        if args.only_cross:   only = "cross_course"
        if args.only_missing: only = "missing"
        print(render_text(rep, only=only))

    return 0


if __name__ == "__main__":
    sys.exit(main())
