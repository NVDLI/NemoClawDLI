#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Parse browser scripts and verify their complete static module linkage.

The pinned browser compiler resolves default, named, namespace, side-effect, dynamic-literal
imports and re-export chains. HTML script bodies retain their actual page-relative resolution.
Recursive discovery includes new courses and .mjs files. Every HTML script is checked without
filename exemptions. External imports are reported for browser execution.

This gate does not infer values produced by executing code or strings passed to cell runtimes.
Known Node built-ins and owning-package declarations resolve runtime dependencies only; they
do not prove browser applicability. Those require the actual browser execution gate, including
its supported origin environments.
"""
import argparse, json, re, subprocess, sys
from pathlib import Path
from urllib.parse import unquote, urlsplit
from html_document import raw_text_blocks
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

_IMPORT_BLOCK = re.compile(r'\bimport\s*\{([^}]*)\}\s*from\s*["\']([^"\']+)["\']')


def unused_imports(src):
    """Imported names that never appear again in the file body. A dead import is harmless at
    runtime but it is drift: it implies the code that used it moved or was deleted (this is how
    the stale `chat` import in _openclaw.js was caught). Advisory only, since a name referenced
    solely inside a string would read as unused; triage before removing."""
    imported = []
    for m in _IMPORT_BLOCK.finditer(src):
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            mm = re.match(r'[A-Za-z_$][\w$]*\s+as\s+([A-Za-z_$][\w$]*)', part)
            imported.append(mm.group(1) if mm else re.match(r'([A-Za-z_$][\w$]*)', part).group(1))
    body = _IMPORT_BLOCK.sub("", src)   # drop the import lines, then look for each name
    return [n for n in imported if not re.search(r'\b' + re.escape(n) + r'\b', body)]


def check_root(root: Path, *, dead: bool = False) -> tuple[list[str], int, list[str]]:
    """Parse every script and link modules at their actual browser-relative locations."""
    if not root.is_dir():
        return ["module_check: no such dir: " + str(root)], 0, []
    files = sorted(path for path in root.rglob('*') if path.is_file()
                   and path.suffix.lower() in {'.html', '.htm', '.js', '.mjs'})
    entries = []
    problems = []
    for f in files:
        src = f.read_text(encoding="utf-8")
        if f.suffix.lower() in {'.js', '.mjs'}:
            entries.append({'file': str(f.resolve()), 'source': src, 'module': f.suffix == '.mjs'})
            continue
        for block in raw_text_blocks(src, 'script'):
            kind = block.attributes.get('type', '').strip().lower()
            if kind not in {'', 'module', 'text/javascript', 'application/javascript'}:
                continue
            external = block.attributes.get('src')
            if external:
                if not re.match(r'^(?:[a-z][a-z0-9+.-]*:|//)', external, re.I):
                    pathname = unquote(urlsplit(external).path)
                    target = (root / pathname.lstrip('/') if pathname.startswith('/') else f.parent / pathname).resolve()
                    if not target.is_file():
                        problems.append(f'{f}: script src does not resolve: {external}')
                continue
            # Leading newlines retain source line numbers in compiler diagnostics.
            entries.append({'file': str(f.resolve()),
                            'source': '\n' * src[:block.body_start].count('\n') + block.body,
                            'module': kind == 'module'})
    result = subprocess.run(['node', str(Path(__file__).with_name('module_linkage.mjs'))],
                            input=json.dumps(entries), capture_output=True, text=True)
    if result.returncode:
        return problems + ['module compiler failed: ' + result.stderr.strip()], 0, []
    report = json.loads(result.stdout)
    problems.extend(report['findings'])
    dead_rows = []
    if dead:
        for f in files:
            names = unused_imports(f.read_text(encoding="utf-8"))
            if names:
                dead_rows.append("%s: dead import(s): %s" % (f.name, ", ".join(names)))

    dead_rows.extend('external module requires browser execution: ' + row for row in report['external'])
    return problems, report['modules'], dead_rows


def discover_roots(web: Path) -> list[Path]:
    """Require course contracts, then scan their shared served tree once."""
    if not list(web.glob("*/interface-inventory.json")):
        return []
    return [web]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", action="append", help="focused root; repeat for several roots")
    ap.add_argument("--web-root", default="web", help="bundle root used for exhaustive discovery")
    ap.add_argument("--dead", action="store_true", help="also report dead (never-referenced) imports, advisory only")
    a = ap.parse_args()
    roots = [Path(value).resolve() for value in a.dir] if a.dir else discover_roots(Path(a.web_root).resolve())
    if not roots:
        sys.exit("module_check: no course interface inventories discovered under " + str(Path(a.web_root).resolve()))

    total_modules = 0
    all_problems = []
    for root in roots:
        problems, nmods, dead_rows = check_root(root, dead=a.dead)
        total_modules += nmods
        all_problems.extend(f"{root}: {problem}" for problem in problems)
        for row in dead_rows:
            print("  · %s: %s" % (root, row))

    if all_problems:
        print("module_check: %d integrity problem(s) across %d discovered root(s)" % (len(all_problems), len(roots)))
        for p in all_problems:
            print("  ✗ " + p)
        sys.exit(1)
    print("module_check: %d modules across %d discovered root(s); static module linkage passed; runtime values require browser execution" % (total_modules, len(roots)))


if __name__ == "__main__":
    main()
