#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Consistency guard: catch "changed a fact in one place, forgot the others".

Enforcement layer behind the SKILL.html change_impact maps. The maps DECLARE which
files move together; this script CHECKS that duplicated facts agree and that every
path a SKILL points at exists.

The proof-surface follows the content across the whole tree, and absence where a fact
is expected is a FAIL, not a pass. A canonical source whose shape changed out from
under the parser, or a config value present nowhere, is a real regression.

Checks
------
INVARIANTS  A fact duplicated across files must agree everywhere; a canonical source
            that exists but no longer parses, or a value expected but absent, FAILs.
DANGLING    Every concrete repo path a SKILL skill-meta points at must exist. FAIL.
HARNESS     A SKILL self-test must be fully wired; the tests are the agent-facing contract.
PROPAGATION (advisory, --since REF) change_impact when_files moved without then_review.

Usage
-----
  scripts/skills/skill_consistency.py                 # invariants + dangling + harness; exit 1 on FAIL
  scripts/skills/skill_consistency.py --since origin/main   # + propagation reminders
  scripts/skills/skill_consistency.py --json          # machine-readable
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

# Resolve the canonical content root in normal and linked worktrees.
TASK1 = find_repo_root(Path(__file__).resolve())
add_script_paths(TASK1 / "scripts")
import scripts_hierarchy as sh  # noqa: E402
REPO = TASK1.parent if (TASK1.parent / ".git").exists() else TASK1
SKIP_PARTS = {"__pycache__", ".ipynb_checkpoints", "node_modules", ".git", ".cache",
              # generated build output (gitignored): public/ is the Pages build, the rest are bundler/export trees.
              # Never source, and a build mid-flight makes subdirs appear and vanish under us, so walking into them crashes the scan.
              # Prune them.
              "public", "export", "standalone", "dist", "build", "i18n",
              # Skip gitignored local runtime output explicitly.
              ".Trash-0", "artifacts", "grounding_cache", "_paper_cache",
              ".exec_stage", ".solution"}
# config/source suffixes worth scanning for duplicated facts
SCAN_SUFFIX = (".html", ".md", ".py", ".js", ".yaml", ".yml", ".conf", ".json")


def walk_files(root: Path, suffixes=None):
    """os.walk with SKIP_PARTS pruned at the DIRECTORY level. Pruning beats rglob's
    post-filter twice over: we never descend into a generated/cache tree, and we never
    crash when a build dir vanishes mid-scan (the public/ FileNotFoundError this fixes)."""
    import os
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_PARTS]
        for fn in fns:
            p = Path(dp) / fn
            if suffixes is None or p.suffix in suffixes:
                yield p


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, IsADirectoryError):
        return ""


def skill_files() -> list[Path]:
    return sorted(p for p in TASK1.rglob("SKILL.html")
                  if not any(s in p.parts for s in SKIP_PARTS))


def skill_meta(p: Path) -> dict | None:
    m = re.search(r'<script type="application/json" id="skill-meta">(.*?)</script>', read(p), re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


# ── results ───────────────────────────────────────────────────────────────────
FAILS: list[str] = []
WARNS: list[str] = []
OKS: list[str] = []


def ok(msg): OKS.append(msg)
def fail(msg): FAILS.append(msg)
def warn(msg): WARNS.append(msg)


# ── INVARIANTS ──────────────────────────────────────────────────────────────────
def inv_openclaw_token():
    """Every <prefix>-openclaw-token literal in the tree must be dli-openclaw-token."""
    found: dict[str, list[str]] = {}
    for p in walk_files(TASK1, SCAN_SUFFIX):
        for tok in re.findall(r'\b([a-z0-9][a-z0-9_-]*-openclaw-token)\b', read(p)):
            found.setdefault(tok, []).append(str(p.relative_to(REPO)))
    distinct = set(found)
    if not distinct:
        # Total absence means the scan surface broke, not that token refs are clean.
        fail("openclaw token: NOT FOUND anywhere. The scan surface is wrong or the refs were dropped.")
    elif distinct == {"dli-openclaw-token"}:
        ok(f"openclaw token: single value across {sum(len(v) for v in found.values())} refs")
    else:
        for t in distinct - {"dli-openclaw-token"}:
            fail(f"openclaw token DIVERGENCE: '{t}' in {found[t][:4]} (expected dli-openclaw-token)")


# Dangling refs: mats paths stay recognized so stale SKILL links fail loudly.
_PREFIXES = ("task1/", "web/", "repos/", ".github/", ".gitlab/", "i18n/",
             "docs/", "scripts/", "tests/")


def _resolve(ref: str, base: Path | None = None) -> Path | None:
    """Map a declared path to a filesystem path, or None if it is not a repo path."""
    ref = ref.strip()
    if not ref or ref.startswith(("http://", "https://", "#", "mailto:")):
        return None
    token = ref.split()[0].rstrip(".,;:")
    if "/" not in token and not token.endswith((".md", ".py", ".html", ".yaml", ".yml", ".json")):
        return None
    if token.startswith("task1/"):
        return REPO / token
    if token.startswith(_PREFIXES):
        return TASK1 / token
    if base is not None:                       # relative to the SKILL's own dir
        return base / token
    return None


def check_dangling():
    for p in skill_files():
        meta = skill_meta(p)
        rel = str(p.relative_to(REPO))
        if meta is None:
            fail(f"dangling/JSON: {rel} has no parseable skill-meta")
            continue
        refs: list[str] = []
        if isinstance(meta.get("source_dir"), str):
            refs.append(meta["source_dir"])
        for r in meta.get("related", []) or []:
            if isinstance(r, str):
                refs.append(r)
        for ci in meta.get("change_impact", []) or []:
            for key in ("when_files", "then_review"):
                for r in ci.get(key, []) or []:
                    refs.append(r)
        for ch in meta.get("children", []) or []:        # hub children, now also checked
            if isinstance(ch, dict) and ch.get("path"):
                refs.append(ch["path"])
        bad = [r for r in refs if (fp := _resolve(r, p.parent)) is not None and not fp.exists()]
        if bad:
            fail(f"dangling ref in {rel}: {bad}")
        else:
            ok(f"refs resolve: {rel} ({len(refs)} checked)")


# ── HARNESS WIRING ───────────────────────────────────────────────────────────────
def check_harness_wiring():
    """A self-test mount must load the harness AND call it. A SERVICE SKILL with no
    tester at all is a FAIL: the self-test is the agent-facing contract for a service."""
    for p in skill_files():
        h = read(p)
        rel = str(p.relative_to(REPO))
        meta = skill_meta(p) or {}
        # Directory explorers may list harness files without mounting them.
        if meta.get("node_type") == "directory-explorer":
            continue
        mount = 'id="selftest"' in h
        inc = "_skill_selftest.js" in h
        call = "SkillSelfTest.run(" in h
        if mount and inc and call:
            ok(f"harness wiring: {rel}")
        elif not (mount or inc or call):
            if meta.get("service"):
                fail(f"harness wiring: service SKILL {rel} has NO self-test (services must self-verify)")
        else:
            missing = [n for n, v in (("#selftest mount", mount), ("harness include", inc), ("run() call", call)) if not v]
            fail(f"harness wiring in {rel}: half-wired tester, missing {missing}")


def check_scripts_hierarchy():
    rows = sh.findings()
    if rows:
        for row in rows:
            fail(f"scripts hierarchy: {row}")
    else:
        ok("scripts hierarchy: implementations live in grouped subdirectories; root has no compatibility wrappers")


def check_scripts_skill_static_body():
    """scripts/* SKILL pages are user interfaces, not metadata shells.

    Keep this scoped to the scripts tree. Other directory SKILL pages can adopt the
    same pattern on their own cadence, but this MR owns the scripts hierarchy.
    """
    base_required = {
        "static section": 'class="skill-static"',
        "interactive explorer": 'id="explorer"',
        "explorer script": "_skill_explorer.js",
    }
    for p in skill_files():
        rel_task = p.relative_to(TASK1)
        if rel_task.parts[0] != "scripts":
            continue
        meta = skill_meta(p) or {}
        if meta.get("node_type") != "directory-explorer":
            continue
        h = read(p)
        if "generated by scripts/skills/gen_directory_beacons.py" in h:
            required = dict(base_required, **{
                "file inventory": "<h2>Files</h2>",
                "child directory inventory": "<h2>Child directories</h2>",
            })
        else:
            required = dict(base_required, **{
                "executable checks": "Executable checks",
                "linkage map": "Linkage map",
            })
        missing = [name for name, needle in required.items() if needle not in h]
        if missing:
            fail(f"scripts SKILL UI body in {p.relative_to(REPO)}: missing {missing}")
        else:
            ok(f"scripts SKILL UI body: {p.relative_to(REPO)}")

# ── PROPAGATION (advisory) ───────────────────────────────────────────────────────
def changed_files(since: str) -> set[str]:
    try:
        out = subprocess.run(["git", "diff", "--name-only", f"{since}...HEAD"],
                             cwd=REPO, capture_output=True, text=True, check=True).stdout
        staged = subprocess.run(["git", "diff", "--name-only"], cwd=REPO,
                                capture_output=True, text=True).stdout
        return set(filter(None, (out + "\n" + staged).splitlines()))
    except subprocess.CalledProcessError:
        return set()


def check_propagation(since: str):
    changed = changed_files(since)
    if not changed:
        return
    for p in skill_files():
        meta = skill_meta(p) or {}
        for ci in meta.get("change_impact", []) or []:
            when = [w for w in ci.get("when_files", []) if w in changed]
            if not when:
                continue
            then = ci.get("then_review", [])
            missing = [t for t in then if t not in changed and (_resolve(t) is None or _resolve(t).exists())]
            if missing:
                warn(f"propagation: {when} changed but change_impact says also review {missing} "
                     f"(declared in {p.relative_to(REPO)})")


def main():
    ap = argparse.ArgumentParser(description="SKILL.html consistency guard")
    ap.add_argument("--since", help="git ref; add propagation reminders vs this base")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    inv_openclaw_token()
    check_dangling()
    check_harness_wiring()
    check_scripts_hierarchy()
    check_scripts_skill_static_body()
    if args.since:
        check_propagation(args.since)

    if args.json:
        print(json.dumps({"fail": FAILS, "warn": WARNS, "ok": OKS}, indent=2))
    else:
        for m in OKS:
            print(f"  \033[32mok\033[0m   {m}")
        for m in WARNS:
            print(f"  \033[33mwarn\033[0m {m}")
        for m in FAILS:
            print(f"  \033[31mFAIL\033[0m {m}")
        print(f"\n{len(OKS)} ok · {len(WARNS)} warn · {len(FAILS)} FAIL")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
