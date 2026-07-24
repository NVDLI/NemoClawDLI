#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic auto-fixer for the comment-formatting findings code_hygiene.py reports.

Clears the mechanically-safe majority of the comment backlog without touching logic:
  - Reflows a multi-line full-line comment block to semantic line breaks, so each line
    ends on a sentence boundary instead of wrapping mid-clause.
  - Collapses two or more spaces after an inline comment marker to one.

It is conservative on purpose. A block is reflowed only when the result is at most three
lines and each line is at most 110 characters; a long prose paragraph is left for a human,
since shortening it is editing, not formatting. Banners, headers, shebangs, list blocks, and
'/* */' blocks are never touched, and an already-compliant block is left alone, so the pass
is idempotent.

It reuses code_hygiene's lexer, so the fixer and the validator always agree on what a comment is.

Usage:
  python3 scripts/validation/fix_comment_hygiene.py                      # dry run; count only
  python3 scripts/validation/fix_comment_hygiene.py --apply              # fix ship-surface .py/.js/.mjs
  python3 scripts/validation/fix_comment_hygiene.py --apply --scope all  # include workspace + service code
  python3 scripts/validation/fix_comment_hygiene.py --apply --file scripts/runtime/engine.js
"""
from __future__ import annotations
import argparse, re, sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

HERE = Path(__file__).resolve()
TASK1 = find_repo_root(HERE)
SCRIPTS = TASK1 / "scripts"
add_script_paths(SCRIPTS)
import code_hygiene as ch  # noqa: E402

MAX_LINE = 140                                   # a reflowed comment line longer than this is left alone.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")   # split on sentence ends only, never on a colon.
_ABBR = re.compile(r"\b(?:e\.g|i\.e|vs|etc|al|Inc|cf|Dr|Mr|Ms|Fig|No)\.$", re.I)


def _indent_of(raw: str) -> str:
    return raw[:len(raw) - len(raw.lstrip())]


def _reflow_block(block) -> list | None:
    """New comment lines for one full-line comment block, or None to leave it untouched. Joins the
    block into one string, splits on sentence ends, and re-emits one sentence per line. Returns None
    for a block that is a banner, a list, a /* */ block, already compliant, or too long to pack."""
    marker = block[0].marker
    if marker not in ("#", "//"):
        return None
    for L in block:
        ct = L.ctext or ""
        if ch._BANNER.match(ct) or ch._HEADER.match(ct) or ch._LIST_ITEM.match(ct) or ct.startswith("!"):
            return None
    # Already compliant: every non-last line ends on a sentence boundary and the block fits.
    compliant = len(block) <= ch.MAX_BLOCK_COMMENT_LINES and all(
        ch._END_OK.search((L.ctext or "").rstrip()) for L in block[:-1])
    if compliant:
        return None
    joined = " ".join((L.ctext or "").strip() for L in block).strip()
    parts, buf = [], ""
    for piece in _SENT_SPLIT.split(joined):
        buf = (buf + " " + piece).strip() if buf else piece
        if not _ABBR.search(buf):                # keep an abbreviation glued to its sentence.
            parts.append(buf); buf = ""
    if buf:
        parts.append(buf)
    parts = [p for p in parts if p]
    indent = _indent_of(block[0].raw)
    new = [f"{indent}{marker} {p}" for p in parts]
    if len(new) > ch.MAX_BLOCK_COMMENT_LINES or any(len(x) > MAX_LINE for x in new):
        return None
    return new


def fix_text(lang: str, text: str):
    """Return (new_text, n_blocks_reflowed, n_inline_fixed) for one file's source."""
    lines = text.split("\n")
    infos, _ = ch.analyze(lang, text)
    out = list(lines)
    reflowed = inline = 0

    # Inline spacing: collapse 2+ spaces after the marker on a trailing comment.
    for L in infos:
        if L.inline and L.marker in ("#", "//") and (L.spaces or 0) >= 2:
            raw = lines[L.n - 1]
            idx = raw.find(L.marker, len(L.code))
            if idx >= 0:
                fixed = raw[:idx + len(L.marker)] + " " + raw[idx + len(L.marker):].lstrip(" ")
                if fixed != raw:
                    out[L.n - 1] = fixed; inline += 1

    # Block reflow: walk blocks bottom-up so edits do not shift the spans still to process.
    blocks = [blk for blk, _after in ch._blocks(infos)]
    for blk in reversed(blocks):
        new = _reflow_block(blk)
        if new is None:
            continue
        lo, hi = blk[0].n - 1, blk[-1].n
        if out[lo:hi] != new:
            out[lo:hi] = new; reflowed += 1
    return "\n".join(out), reflowed, inline


def fix_html_text(text: str):
    """Return (new_text, n_blocks_reflowed, n_inline_fixed) after fixing JS comments inside
    HTML script bodies. Edits run bottom-up so replacing one cell body never shifts the next one."""
    changes = []
    total_blocks = total_inline = 0
    for m in ch._SCRIPT_BODY.finditer(text):
        attrs, body = m.group(1), m.group(2)
        if ch._NONJS_SCRIPT.search(attrs) or "src=" in attrs.lower() or not body.strip():
            continue
        new, blocks, inline = fix_text("cell", body)
        if new == body:
            continue
        changes.append((m.start(2), m.end(2), new))
        total_blocks += blocks
        total_inline += inline
    for start, end, new in reversed(changes):
        text = text[:start] + new + text[end:]
    return text, total_blocks, total_inline


def fix_one_pass(targets, apply: bool):
    """Run one deterministic pass across targets and return (files, blocks, inline, changed)."""
    tot_files = tot_blocks = tot_inline = 0
    changed = False
    for f, rel, suf in targets:
        text = f.read_text(encoding="utf-8", errors="ignore")
        new, blocks, inline = fix_html_text(text) if suf in (".html", ".htm") else fix_text(suf, text)
        if not blocks and not inline:
            continue
        tot_files += 1; tot_blocks += blocks; tot_inline += inline
        print(f"  {rel}: {blocks} block(s) reflowed, {inline} inline spacing")
        if apply and new != text:
            f.write_text(new, encoding="utf-8")
            changed = True
    return tot_files, tot_blocks, tot_inline, changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Auto-fix mechanical comment-formatting findings.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--scope", choices=["ship", "all"], default="ship")
    ap.add_argument("--file", help="limit to one file (path fragment)")
    ap.add_argument("--apply", action="store_true", help="write the fixes (default is a dry run)")
    a = ap.parse_args()

    targets = [(f, rel, suf) for f, rel, suf in ch._iter_files(a.scope) if suf in (".py", ".js", ".mjs", ".html", ".htm")]
    if a.file:
        targets = [t for t in targets if a.file in t[1]]
    total_files = total_blocks = total_inline = 0
    passes = 0
    while True:
        files, blocks, inline, changed = fix_one_pass(targets, a.apply)
        passes += 1
        total_files += files
        total_blocks += blocks
        total_inline += inline
        if not a.apply or not changed:
            break
    verb = "fixed" if a.apply else "would fix"
    print(f"\n{verb}: {total_blocks} comment block(s) + {total_inline} inline spacing across {total_files} file-pass(es)"
          + ("" if a.apply else "  (dry run; pass --apply to write)"))
    if a.apply:
        print(f"passes: {passes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
