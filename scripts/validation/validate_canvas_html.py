#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Static structural validator for canvas-flow HTML pages.

Catches issues that only appear at runtime (browser parse errors, TDZ,
duplicate blocks) without needing docker or playwright. Runs in <100ms.

Exit 0 = clean. Exit 1 = structural problems found (with details).

Usage:
    python3 scripts/validation/validate_canvas_html.py path/to/page.html [...]
"""

import re
import sys


def _find_canvas_nodes(txt):
    """Return list of (id, code_block, python_block) for each mountCanvasFlow node."""
    nodes = []
    for m in re.finditer(r'id:\s*"([^"]+)"', txt):
        node_id = m.group(1)
        # Find code: ` block after the id
        code_start = txt.find("      code: `", m.start())
        if code_start == -1 or code_start > txt.find("\n    },", m.start()) + 200:
            continue
        # Find closing backtick (unescaped)
        pos = code_start + len("      code: `")
        code_end = -1
        while pos < len(txt):
            if txt[pos] == '`' and (pos == 0 or txt[pos-1] != '\\'):
                code_end = pos
                break
            pos += 1
        if code_end == -1:
            continue
        code_block = txt[code_start:code_end + 1]

        # Find python: ` block if it follows
        py_search = txt[code_end + 1:code_end + 50]
        python_block = None
        if "python: `" in py_search:
            py_start = txt.find("      python: `", code_end)
            pos = py_start + len("      python: `")
            py_end = -1
            while pos < len(txt):
                if txt[pos] == '`' and (pos == 0 or txt[pos-1] != '\\'):
                    py_end = pos
                    break
                pos += 1
            if py_end != -1:
                python_block = txt[py_start:py_end + 1]

        nodes.append((node_id, code_block, python_block))
    return nodes


def _unescaped_ticks(block):
    """Return positions of unescaped backticks in block."""
    return [i for i, c in enumerate(block) if c == '`' and (i == 0 or block[i-1] != '\\')]


def validate(path):
    errors = []
    with open(path) as f:
        txt = f.read()

    # ── 1. Template-literal backtick balance ─────────────────────────────────
    # Each `code: ``...``  ` section should have exactly 2 unescaped backticks:
    # the opening (part of `code: ```) and the closing.
    for m in re.finditer(r'      code: `', txt):
        start = m.start()
        # Walk to the closing backtick
        pos = start + len("      code: `")
        close = -1
        while pos < len(txt):
            if txt[pos] == '`' and txt[pos-1] != '\\':
                close = pos
                break
            pos += 1
        if close == -1:
            errors.append(f"Unclosed code: ` block starting at offset {start}")
            continue

        # Count ALL unescaped backticks in the block (should be 0, since the opening
        # and closing are outside this window)
        inner = txt[start + len("      code: `"):close]
        stray = [i for i, c in enumerate(inner) if c == '`' and (i == 0 or inner[i-1] != '\\')]
        if stray:
            for s in stray:
                ctx = inner[max(0, s-40):s+40].replace('\n', '↵')
                errors.append(
                    f"Unescaped backtick inside code: ` block at inner-offset {s}: ...{ctx}..."
                )

    # ── 1b. Same check for python: ` blocks ─────────────────────────────────
    for m in re.finditer(r'      python: `', txt):
        start = m.start() + len("      python: `")
        pos = start
        close = -1
        while pos < len(txt):
            if txt[pos] == '`' and txt[pos-1] != '\\':
                close = pos; break
            pos += 1
        if close == -1:
            errors.append(f"Unclosed python: ` block at offset {m.start()}")
            continue
        inner = txt[start:close]
        stray = [i for i, c in enumerate(inner) if c == '`' and (i == 0 or inner[i-1] != '\\')]
        if stray:
            for s in stray:
                ctx = inner[max(0, s-40):s+40].replace('\n', '↵')
                errors.append(
                    f"Unescaped backtick inside python: ` block at inner-offset {s}: ...{ctx}..."
                )
        # Also check that what follows the closing backtick is `,` (not another backtick)
        after = txt[close+1:close+3]
        if after.startswith('\n`'):
            errors.append(
                f"Double-backtick after python: ` block at offset {close}: "
                f"{repr(txt[close-10:close+20])}"
            )

    # ── 2. Comma between code: and python: ───────────────────────────────────
    for m in re.finditer(r'`\n      python: `', txt):
        # There should be a comma right after the backtick
        before = txt[m.start()-5:m.start()+1]
        if '`,\n' not in txt[m.start()-1:m.start()+3]:
            ctx = txt[m.start()-20:m.start()+30].replace('\n', '↵')
            errors.append(f"Missing comma between code and python blocks: ...{ctx}...")

    # ── 3. Duplicate Python blocks ────────────────────────────────────────────
    py_starts = {}
    for m in re.finditer(r'      python: `([^\n]{0,60})', txt):
        sig = m.group(1)[:40]
        py_starts.setdefault(sig, []).append(m.start())
    for sig, positions in py_starts.items():
        if len(positions) > 1:
            errors.append(
                f"Duplicate python: ` block (signature: {sig!r}) at offsets {positions}"
            )

    # ── 4. TDZ: log used before declaration ──────────────────────────────────
    # Within each code: block, `const { log } = helpers;` must come before
    # any bare `log.html(` call.
    for m in re.finditer(r'      code: `', txt):
        start = m.start() + len("      code: `")
        pos = start
        close = -1
        while pos < len(txt):
            if txt[pos] == '`' and txt[pos-1] != '\\':
                close = pos
                break
            pos += 1
        if close == -1:
            continue
        block = txt[start:close]
        # Only flag bare log.html(. A helpers.log.html( call is safe and stays unflagged.
        log_decl = block.find("const { log } = helpers;")
        log_use  = next((m2.start() for m2 in re.finditer(r'(?<!\.)log\.html\(', block)), -1)
        if log_use != -1 and (log_decl == -1 or log_use < log_decl):
            errors.append(
                f"TDZ: log.html() used before 'const {{ log }} = helpers;' "
                f"in code: block at file offset {m.start()}"
            )

    # ── 5. LLM-maze node: state destructuring present ────────────────────────
    # Any node that CONSUMES generateMaze/validMoves (but doesn't define/export
    # them) must destructure from state.  Nodes that export (state.generateMaze=)
    # are providers, so they are skipped.
    maze_fns = ["generateMaze", "validMoves", "doMove", "toAscii", "SPRINT_TOOL"]
    for m in re.finditer(r'      code: `', txt):
        start = m.start() + len("      code: `")
        pos = start
        close = -1
        while pos < len(txt):
            if txt[pos] == '`' and txt[pos-1] != '\\':
                close = pos
                break
            pos += 1
        if close == -1:
            continue
        block = txt[start:close]
        # Skip nodes that define or export the functions (not consumers)
        if ("state.generateMaze" in block or "state.validMoves" in block
                or "function generateMaze" in block or "function validMoves" in block):
            continue
        uses_maze = any(fn in block for fn in maze_fns)
        if uses_maze and "= state;" not in block and "= state\n" not in block:
            errors.append(
                f"LLM maze node at offset {m.start()} uses maze helpers "
                f"(generateMaze/validMoves/…) but has no '= state;' destructuring"
            )

    return errors


def main():
    if len(sys.argv) < 2:
        print("Usage: validate_canvas_html.py <file.html> [...]")
        sys.exit(1)

    overall_fail = False
    for path in sys.argv[1:]:
        errs = validate(path)
        if errs:
            overall_fail = True
            print(f"FAIL {path}")
            for e in errs:
                print(f"  • {e}")
        else:
            print(f"ok   {path}")

    sys.exit(1 if overall_fail else 0)


if __name__ == "__main__":
    main()
