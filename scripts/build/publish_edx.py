#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Publish the nemoclaw standalone bundle to S3 for the edX HtmlBlock view.

The student-facing edX page is a single HtmlBlock that iframes module
pages out of S3. This script keeps the S3 prefix in sync with whatever
the latest `scripts/build/bundle_standalone.py` run produced.

Pass the local source directory with --src; the S3 sub-prefix is derived
from the directory name by stripping `_standalone`:

  --src web/nemoclaw_standalone  → s3://dli-lms/assets/<course>/nemoclaw/

Override with --prefix when needed.

Every object is uploaded with ACL `public-read` so the edX iframe can
fetch it without auth.

Usage:

  # Bundle + publish:
  python3 scripts/build/bundle_standalone.py --src web/nemoclaw --clean
  python3 scripts/build/publish_edx.py --src web/nemoclaw_standalone

  # Dry-run (prints what would upload, no S3 calls):
  python3 scripts/build/publish_edx.py --src web/nemoclaw_standalone --dry-run

  # Skip the zip:
  python3 scripts/build/publish_edx.py --no-zip

Credentials come from the standard AWS chain (env, ~/.aws/credentials,
instance profile). The dev box this script runs from has a
`content-dev` IAM user with write access to s3://dli-lms/assets/.
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import zipfile
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

BUCKET           = "dli-lms"
# The course code comes from the environment; never hardcode one here.
COURSE_CODE      = os.environ.get("DLI_COURSE_CODE")
if not COURSE_CODE:
    sys.exit("set DLI_COURSE_CODE before publishing")
KEY_PREFIX_ROOT  = f"assets/{COURSE_CODE}/"
PUBLIC_URL       = f"https://{BUCKET}.s3.us-east-1.amazonaws.com/"

DEFAULT_SRC = Path(__file__).resolve().parent.parent / "web" / "nemoclaw_standalone"
ZIP_NAME    = "current-html-pages.zip"


def _derive_prefix(src: Path) -> str:
    """nemoclaw_standalone/ → 'nemoclaw/'."""
    name = src.name
    if name.endswith("_standalone"):
        return KEY_PREFIX_ROOT + name[: -len("_standalone")] + "/"
    # Fallback: assume the directory name IS the S3 sub-prefix.
    return KEY_PREFIX_ROOT + name + "/"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg":  "image/svg+xml",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".woff2":"font/woff2",
    ".zip":  "application/zip",
}


def _aws(args: list[str], *, dry_run: bool) -> None:
    """Run an aws CLI command (or print it in dry-run mode)."""
    cmd = ["aws"] + args
    if dry_run:
        print("  DRY  " + " ".join(_quote(a) for a in cmd))
        return
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(f"aws failed: {' '.join(cmd)}\n{res.stderr}\n")
        sys.exit(res.returncode)


def _quote(s: str) -> str:
    return f'"{s}"' if (" " in s or "&" in s) else s


def _upload_file(src: Path, key: str, *, dry_run: bool) -> str:
    """Upload a single file with the right content-type and public ACL.
    Returns the public URL the upload would resolve to."""
    ct = CONTENT_TYPES.get(src.suffix.lower(), "application/octet-stream")
    _aws(
        [
            "s3", "cp", str(src), f"s3://{BUCKET}/{key}",
            "--acl", "public-read",
            "--content-type", ct,
            "--cache-control", "public, max-age=300",
        ],
        dry_run=dry_run,
    )
    return PUBLIC_URL + key


def _build_zip(src_dir: Path) -> bytes:
    """Pack every .html file in src_dir into a flat zip archive in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(src_dir.glob("*.html")):
            z.write(p, arcname=p.name)
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC,
                    help="Local directory to publish (default: web/nemoclaw_standalone/). "
                         "Pass a relative name (e.g. 'web/nemoclaw_standalone') or absolute path.")
    ap.add_argument("--prefix", default=None,
                    help="Explicit S3 key prefix override (must end with '/'). "
                         "Default: derived from --src by stripping '_standalone'.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print the upload plan without touching S3")
    ap.add_argument("--no-zip", action="store_true",
                    help="Skip building & uploading current-html-pages.zip")
    args = ap.parse_args()

    src = args.src
    if not src.is_absolute():
        src = Path(__file__).resolve().parent.parent / src
    if not src.is_dir():
        sys.stderr.write(f"source directory not found: {src}\n")
        sys.stderr.write("Run scripts/build/bundle_standalone.py first.\n")
        return 1

    key_prefix = args.prefix or _derive_prefix(src)
    if not key_prefix.endswith("/"):
        key_prefix += "/"

    pages = sorted(p for p in src.glob("*.html") if not p.name.startswith("."))
    if not pages:
        sys.stderr.write(f"no *.html under {src}\n")
        return 1

    print(f"src:     {src}")
    print(f"target:  s3://{BUCKET}/{key_prefix}")
    print(f"pages:   {len(pages)}")
    print()

    urls: list[str] = []
    for p in pages:
        url = _upload_file(p, key_prefix + p.name, dry_run=args.dry_run)
        size_kb = p.stat().st_size / 1024
        print(f"  {p.name:<32} {size_kb:6.1f} KB")
        urls.append(url)

    # Pack everything into a zip for the "Download all" affordance.
    if not args.no_zip:
        zip_bytes = _build_zip(src)
        tmp_zip = src.parent / ZIP_NAME
        tmp_zip.write_bytes(zip_bytes)
        try:
            _upload_file(tmp_zip, key_prefix + ZIP_NAME, dry_run=args.dry_run)
            print(f"\n  {ZIP_NAME:<32} {len(zip_bytes)/1024:6.1f} KB")
        finally:
            tmp_zip.unlink(missing_ok=True)

    print(f"\nDone. Live URL prefix:")
    print(f"  {PUBLIC_URL}{key_prefix}")
    print(f"\nSample entry: {PUBLIC_URL}{key_prefix}index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
