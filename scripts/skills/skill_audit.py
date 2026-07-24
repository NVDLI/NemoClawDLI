#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit (and --fix) every SKILL.html so it is a TRUE beacon of its own directory.

Per the SKILL contract each SKILL.html is a per-directory brain: human prose +
an authoritative `skill-meta` JSON block. After the surface-first migration many
metas drifted (stale `source_dir`/`human_landing` pointing at task1/workspace/…,
notebook lists out of sync with the actual files). This tool re-derives the
scope from where the file actually lives and reconciles the notebook list with
the directory contents, so the beacon is self-updating and accurate.

Checks per SKILL.html:
  coverage   every tracked or proposed source directory and ancestor has SKILL.html;
             there is no directory exemption mechanism
  scope      skill-meta.source_dir == its real dir; human_landing == its real path
  notebooks  every *.md in the course dir is listed (full-directory observability);
             no listed file is missing; notebook_count matches
  hub        node_type:hub children paths all exist on disk

Usage:
  python3 skill_audit.py            # report drift, exit 1 if any
  python3 skill_audit.py --fix      # rewrite skill-meta to match reality, then report
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

HERE = Path(__file__).resolve()
TASK1 = find_repo_root(HERE)
# Wrapper layout: task1/ is a subdir of the git repo, so a SKILL's source_dir and human_landing carry the leading 'task1/' segment.
# Promoted standalone: task1 IS the repo root, so there is no prefix.
# Same detection the hooks use.
PREFIX = "task1/" if (TASK1.name == "task1" and (TASK1.parent / ".git").exists()) else ""
META_RE = re.compile(r'(<script type="application/json" id="skill-meta">)(.*?)(</script>)', re.S)
# top-level course-content notebooks: *.md not under an asset subdir
ASSET_SUB = {"code", "data", "images", "imgs", "exercises", "demo", "skills", "ocstart",
             "_paper_cache", "repos_index", "docstore_index", "composer", "chat_helpers",
             "extra_utils", "skills-seed", "chats", "bin", "hooks", "tests", "routers", "store"}


def source_files() -> list[Path]:
    """Return every tracked or proposed source file known to Git.

    Git's source set is the exhaustive boundary. Ignored build output is absent by
    construction; tracked locale, vendor, workflow, data, and hidden directories are not.
    There is no directory exemption mechanism.
    """
    raw = subprocess.check_output(
        ["git", "-C", str(TASK1), "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    )
    files = (Path(item.decode()) for item in raw.split(b"\0") if item)
    return sorted(path for path in files if (TASK1 / path).is_file())


def directories_for_files(files: list[Path]) -> list[Path]:
    directories = {Path(".")}
    for path in files:
        parent = path.parent
        while parent != Path("."):
            directories.add(parent)
            parent = parent.parent
    return sorted(directories, key=lambda path: (len(path.parts), str(path)))


def source_directories() -> list[Path]:
    return directories_for_files(source_files())


def skills():
    for rel in source_directories():
        directory = TASK1 if rel == Path(".") else TASK1 / rel
        skill = directory / "SKILL.html"
        if skill.is_file():
            yield skill


def coverage_findings() -> list[tuple[str, str]]:
    findings = []
    for rel in source_directories():
        directory = TASK1 if rel == Path(".") else TASK1 / rel
        skill = directory / "SKILL.html"
        if not skill.is_file():
            label = "." if rel == Path(".") else str(rel)
            findings.append((label, "directory has source files or source descendants but no SKILL.html"))
    return findings


def parse_meta(text):
    m = META_RE.search(text)
    if not m:
        return None, None
    try:
        return json.loads(m.group(2)), m
    except Exception:
        return "ERR", m


_NOT_NOTEBOOK = {"README.md", "ARTIFACT_QUALITY_BAR.md"}


def course_notebooks(d: Path):
    """The course's navigable notebooks (basenames), sorted. They live in a
    notebooks/ subdir when one is present, else flat in the course dir. Underscore-
    prefixed files (_demo_doc.md) and dir docs (README) are aux, not notebooks."""
    base = d / "notebooks" if (d / "notebooks").is_dir() else d
    return sorted(p.name for p in base.glob("*.md")
                  if not p.name.startswith(".") and not p.name.startswith("_")
                  and p.name not in _NOT_NOTEBOOK)


def audit(fix: bool):
    problems = coverage_findings()
    for sk in skills():
        rel = sk.relative_to(TASK1)
        d = sk.parent
        reldir = str(d.relative_to(TASK1)) + "/" if d != TASK1 else ""
        text = sk.read_text()
        meta, m = parse_meta(text)
        if meta is None:
            problems.append((str(rel), "no skill-meta JSON block")); continue
        if meta == "ERR":
            problems.append((str(rel), "skill-meta JSON does not parse")); continue
        changed = False
        is_hub = meta.get("node_type") == "hub"

        # ── scope: source_dir + human_landing reflect the real location ──
        want_src = f"{PREFIX}{reldir}" if reldir else PREFIX
        want_land = f"{PREFIX}{rel}"
        if not is_hub:
            if meta.get("source_dir") not in (want_src, want_src.rstrip("/")):
                problems.append((str(rel), f"source_dir {meta.get('source_dir')!r} != {want_src!r}"))
                if fix: meta["source_dir"] = want_src; changed = True
            if "human_landing" in meta and meta.get("human_landing") != want_land:
                problems.append((str(rel), f"human_landing {meta.get('human_landing')!r} != {want_land!r}"))
                if fix: meta["human_landing"] = want_land; changed = True

        # ── notebooks: full-directory observability for course SKILLs ──
        if "notebooks" in meta or "notebook_count" in meta:
            actual = course_notebooks(d)
            listed = {n.get("file") for n in meta.get("notebooks", []) if isinstance(n, dict)}
            missing = [f for f in actual if f not in listed]
            stale = [f for f in listed if f and f not in actual]
            if missing:
                problems.append((str(rel), f"notebooks MISSING from meta: {missing}"))
            if stale:
                problems.append((str(rel), f"notebooks STALE in meta (file gone): {stale}"))
            if meta.get("notebook_count") not in (None, len(actual)):
                problems.append((str(rel), f"notebook_count {meta.get('notebook_count')} != actual {len(actual)}"))
            if fix and (missing or stale or meta.get("notebook_count") not in (None, len(actual))):
                nbs = [n for n in meta.get("notebooks", []) if isinstance(n, dict) and n.get("file") in actual]
                have = {n["file"] for n in nbs}
                for f in actual:
                    if f not in have:
                        nbs.append({"file": f, "topic": "", "section": "", "status": "ready"})
                nbs.sort(key=lambda n: actual.index(n["file"]))
                meta["notebooks"] = nbs
                if "notebook_count" in meta or meta.get("notebooks"):
                    meta["notebook_count"] = len(actual)
                changed = True

        # ── hub: children paths exist ──
        if is_hub:
            for ch in meta.get("children", []):
                cp = TASK1 / ch.get("path", "")
                if not cp.exists():
                    problems.append((str(rel), f"hub child missing on disk: {ch.get('path')}"))

        if fix and changed:
            new_block = m.group(1) + "\n" + json.dumps(meta, indent=2) + "\n" + m.group(3)
            sk.write_text(text[:m.start()] + new_block + text[m.end():])
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true", help="rewrite skill-meta to match reality")
    a = ap.parse_args()
    if a.fix:
        audit(fix=True)            # first pass mutates
    problems = audit(fix=False)    # re-audit to report residual
    if not problems:
        print("skill_audit: ✅ every SKILL.html beacon matches its directory")
        return 0
    print(f"skill_audit: ✗ {len(problems)} issue(s):", file=sys.stderr)
    for f, why in problems:
        print(f"  {f}: {why}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
