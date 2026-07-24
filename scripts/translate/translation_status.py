#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""What changed on the source branch since a translation was last synced (the drift report).

A translation branch (`translate-<lang>`) is a full overlay of the source branch: the same
files, with the human-facing prose rendered in <lang> and everything else (code, assets, the
skill-meta machine contracts) carried verbatim. The hard part of keeping it alive is not the
first pass; it is staying in step as the source moves. This tool answers the one question a
translator keeps asking: "what changed on the source branch since I last caught up, and which
of it do I need to re-translate versus just merge as-is?"

The abstraction is a single marker. `translation_base.json` records the source commit this
translation reflects (the "base"). The drift is `git diff base..upstream`, classified per file:

  TRANSLATE   prose the reader sees (.html pages and .md companions). Re-translate it.
  VERBATIM    code, styles, data, assets, the skill-meta JSON contract. Merge it unchanged;
              a translation must never fork the code or the machine contract from the source.

The workflow is a loop: read the status, translate the TRANSLATE deltas, merge the VERBATIM
deltas, then advance the marker (`--set-base`) so the next round starts from here.

Usage
-----
  scripts/translate/translation_status.py                 # report drift since the base
  scripts/translate/translation_status.py --json          # machine-readable
  scripts/translate/translation_status.py --check         # exit 1 if any TRANSLATE file drifted (CI)
  scripts/translate/translation_status.py --set-base HEAD  # after syncing: pin base to the upstream tip
  scripts/translate/translation_status.py --upstream nemoclaw-only   # override the source branch
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK1 = HERE.parent.parent                       # scripts/translate -> scripts -> content root
MARKER = HERE / "translation_base.json"

# Translate reader-facing web prose only; keep code, metadata, and agent docs verbatim.
TRANSLATE_EXT = {".html", ".md"}
TRANSLATE_ROOT = "web/"                          # reader-facing content only; dev docs stay English
# Paths that never carry reader prose even under web/ (generated data / binary assets).
VERBATIM_PATH_HINTS = ("/assets/", "materials_index.json", "_materials.json")
# Generated or vendored trees that are not part of the sync surface at all.
SKIP_PREFIXES = ("public/", "docs/validation/", "node_modules/", "scripts/.figtools/",
                 ".git/", "__pycache__/")


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(TASK1), *args],
                          capture_output=True, text=True).stdout.strip()


def resolve_upstream(name: str) -> str | None:
    """Prefer the remote-tracking ref (CI fetches it); fall back to a local branch; else None."""
    for ref in (f"origin/{name}", name):
        if git("rev-parse", "--verify", "--quiet", ref):
            return ref
    return None


def load_marker() -> dict:
    if MARKER.exists():
        try:
            return json.loads(MARKER.read_text())
        except Exception:
            return {}
    return {}


def classify(path: str) -> str:
    if any(h in ("/" + path) or path.endswith(h) for h in VERBATIM_PATH_HINTS):
        return "verbatim"
    if path.startswith(TRANSLATE_ROOT) and Path(path).suffix in TRANSLATE_EXT:
        return "translate"
    return "verbatim"


def in_surface(path: str) -> bool:
    return not any(path.startswith(p) for p in SKIP_PREFIXES)


def drift(base: str, upstream: str) -> list[dict]:
    """git diff base..upstream as classified, in-surface changes."""
    raw = git("diff", "--name-status", "-M", f"{base}..{upstream}")
    out = []
    for ln in raw.splitlines():
        parts = ln.split("\t")
        code = parts[0]
        path = parts[-1]                         # for renames (R100) the new path is last
        if not in_surface(path):
            continue
        status = {"A": "added", "M": "modified", "D": "deleted"}.get(code[0], code[0].lower())
        out.append({"path": path, "status": status, "class": classify(path)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upstream", help="source branch to diff against (default: marker's `upstream`)")
    ap.add_argument("--json", action="store_true", help="machine-readable report")
    ap.add_argument("--check", action="store_true", help="exit 1 if any TRANSLATE file drifted (for CI)")
    ap.add_argument("--set-base", metavar="REF",
                    help="pin the base to REF's commit (e.g. HEAD of the upstream), then exit")
    ap.add_argument("--no-fetch", action="store_true", help="skip the best-effort git fetch")
    a = ap.parse_args()

    marker = load_marker()
    upstream_name = a.upstream or marker.get("upstream") or "main"
    if not a.no_fetch:
        git("fetch", "origin", upstream_name, "--quiet")   # best-effort; offline is fine
    upstream = resolve_upstream(upstream_name)

    if a.set_base:
        sha = git("rev-parse", a.set_base)
        if not sha:
            print(f"translation_status: cannot resolve {a.set_base!r}", file=sys.stderr)
            return 2
        marker.update({"upstream": upstream_name, "base_sha": sha})
        MARKER.write_text(json.dumps(marker, indent=2) + "\n")
        print(f"translation_status: base pinned to {sha[:10]} on {upstream_name}")
        return 0

    base = marker.get("base_sha")
    lang = marker.get("lang")
    if not base or not lang:
        msg = ("translation_status: no translation base set. This is the source branch or a fresh "
               "translation. On a translate-<lang> branch, fill translation_base.json (lang + upstream) "
               "and run --set-base <upstream-tip> once the first pass matches that commit.")
        print(json.dumps({"ready": False, "reason": msg}, indent=2) if a.json else msg)
        return 0
    if not upstream:
        print(f"translation_status: upstream {upstream_name!r} not found (origin/{upstream_name} or "
              f"{upstream_name}). Fetch it or pass --upstream.", file=sys.stderr)
        return 2

    items = drift(base, upstream)
    translate = [d for d in items if d["class"] == "translate"]
    verbatim = [d for d in items if d["class"] == "verbatim"]
    behind = git("rev-list", "--count", f"{base}..{upstream}")

    if a.json:
        print(json.dumps({"ready": True, "lang": lang, "upstream": upstream_name,
                          "base_sha": base, "commits_behind": int(behind or 0),
                          "translate": translate, "verbatim": verbatim}, indent=2))
        return 1 if (a.check and translate) else 0

    print(f"translation [{lang}] base {base[:10]} → {upstream_name} ({behind} commit(s) ahead)")
    if not items:
        print("  up to date: nothing changed on the source since the base.")
        return 0
    print(f"\n  TO RE-TRANSLATE ({len(translate)} prose file(s) the reader sees):")
    for d in translate:
        print(f"    {d['status']:9} {d['path']}")
    if not translate:
        print("    (none)")
    print(f"\n  TO MERGE VERBATIM ({len(verbatim)} code / asset / contract file(s), do NOT translate):")
    for d in verbatim:
        print(f"    {d['status']:9} {d['path']}")
    if not verbatim:
        print("    (none)")
    print("\n  When the deltas above are translated/merged, advance the base:")
    print(f"    scripts/translate/translation_status.py --set-base origin/{upstream_name}")
    return 1 if (a.check and translate) else 0


if __name__ == "__main__":
    sys.exit(main())
