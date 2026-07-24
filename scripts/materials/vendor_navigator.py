#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Wrap scripts/edx/edx_navigator_quick.html in a full HTML5 document and publish
to S3 as a standalone, shareable entry point to the nemoclaw course.

The navigator was originally an edX HtmlBlock fragment (no <html>/<body>
wrapper). This script wraps it with a minimal page shell so it works as
a direct URL anyone can open in a browser, no LMS required.

After running:

  https://dli-lms.s3.us-east-1.amazonaws.com/assets/<course>/navigator.html
  https://dli-lms.s3.us-east-1.amazonaws.com/assets/<course>/index.html

both serve the navigator standalone (index.html so the natural bucket
prefix URL resolves; navigator.html for an explicit name).

Usage:

  python3 scripts/materials/vendor_navigator.py            # build + upload
  python3 scripts/materials/vendor_navigator.py --dry-run  # build local only
  python3 scripts/materials/vendor_navigator.py --local    # build local, no S3
"""
from __future__ import annotations
import argparse
import subprocess
import os
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

BUCKET = "dli-lms"
COURSE_CODE = os.environ.get("DLI_COURSE_CODE")
if not COURSE_CODE:
    sys.exit("set DLI_COURSE_CODE before vendoring")
PREFIX = f"assets/{COURSE_CODE}/"   # course code is wrapper-injected, never hardcoded

HERE = Path(__file__).resolve()
ROOT = find_repo_root(HERE)
SRC  = ROOT / "scripts" / "edx" / "edx_navigator_quick.html"
OUT  = ROOT / "scripts" / "navigator.html"

HTML_SHELL_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Securing Agents with OpenShell and NemoClaw &middot; Navigator</title>
<meta name="description" content="NVIDIA DLI Securing Agents workshop. Pick the long or short browser course."/>
<style>
html, body { margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
  background: #ffffff;
  color: #1a1a1a;
  -webkit-font-smoothing: antialiased;
}
/* The fragment was written for an edX HtmlBlock whose outer container
   was .content-wrapper.main-container. Replicate the same constraint so
   the chip rows and iframe line up with the design the fragment expects. */
.content-wrapper.main-container { max-width: 1500px; margin: 0 auto; padding: 0 20px; }
</style>
</head>
<body>
<div class="content-wrapper main-container">
"""

HTML_SHELL_TAIL = """
</div>
</body>
</html>
"""


# Strip stale editor-prefixed document copies before ingest.
FRAGMENT_MARKER = "<!-- ─── edX HtmlBlock"


def build() -> str:
    if not SRC.is_file():
        sys.stderr.write(f"missing source: {SRC}\n")
        sys.exit(1)
    fragment = SRC.read_text(encoding="utf-8")
    idx = fragment.find(FRAGMENT_MARKER)
    if idx > 0:
        sys.stderr.write(
            f"WARNING: stripping {idx} bytes of pre-marker garbage from "
            f"{SRC.name} (likely an IDE-buffer-race artefact)\n"
        )
        fragment = fragment[idx:]
    elif idx < 0:
        sys.stderr.write(f"ERROR: marker not found in {SRC.name}\n")
        sys.exit(1)
    return HTML_SHELL_HEAD + fragment + HTML_SHELL_TAIL


def upload(local: Path, key: str, *, dry_run: bool) -> None:
    cmd = [
        "aws", "s3", "cp", str(local), f"s3://{BUCKET}/{key}",
        "--acl", "public-read",
        "--content-type", "text/html; charset=utf-8",
        "--cache-control", "public, max-age=300",
    ]
    if dry_run:
        print("  DRY  " + " ".join(cmd))
        return
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(f"aws failed: {' '.join(cmd)}\n{res.stderr}\n")
        sys.exit(res.returncode)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the upload plan without touching S3")
    ap.add_argument("--local", action="store_true",
                    help="Build the local file only; skip S3 entirely")
    args = ap.parse_args()

    html = build()
    OUT.write_text(html, encoding="utf-8")
    size_kb = len(html.encode("utf-8")) / 1024
    print(f"built {OUT.relative_to(HERE.parent)} ({size_kb:.1f} KB)")

    if args.local:
        return 0

    upload(OUT, PREFIX + "navigator.html", dry_run=args.dry_run)
    upload(OUT, PREFIX + "index.html",     dry_run=args.dry_run)

    base = S3_STATIC_BASE.format(BUCKET=BUCKET, PREFIX=PREFIX)
    print()
    print(f"Live:")
    print(f"  {base}navigator.html")
    print(f"  {base}index.html  (natural prefix URL)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
