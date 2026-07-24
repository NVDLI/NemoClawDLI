#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Verify ES-module import/export integrity across every discovered web course.

The course pages and the _*.js modules import named bindings from ./_shared.js, and _shared.js
re-exports the names it pulls from the extracted modules (_glossary.js, _openclaw.js, ...). When
an extraction drops a name from that re-export, every page importing it breaks at load with
"does not provide an export named X". That is exactly how glossary.html broke once. render_check catches
that in a real browser; this catches the same class statically in milliseconds with no browser, so
it is cheap enough to run on every commit.

Two checks per discovered directory:
  1. Every `import { a, b } from "./mod.js"` resolves to a real export of mod.js (re-exports
     count, since `export { a }` is itself an export).
  2. Every name a module lists in `export { ... }` is defined in that module or imported into
     it (no re-exporting a name you never brought in).

Course roots are discovered from ``web/*/interface-inventory.json`` and the complete web tree is
checked recursively. A newly added course therefore enters this gate without a registry edit or
course-name allowlist. ``--dir`` remains available for focused diagnosis only.

Usage:
    python3 scripts/runtime/module_check.py                  # web plus every discovered course
    python3 scripts/runtime/module_check.py --dir web/nemoclaw  # focused diagnosis
Exit non-zero on any unresolved import or dangling re-export, so it works as a gate.
"""
import argparse, re, sys
from pathlib import Path

_DECL = re.compile(r'\bexport\s+(?:async\s+)?(?:function|const|let|var|class)\s+([A-Za-z_$][\w$]*)')
_EXPORT_BLOCK = re.compile(r'\bexport\s*\{([^}]*)\}')
_IMPORT_BLOCK = re.compile(r'\bimport\s*\{([^}]*)\}\s*from\s*["\']([^"\']+)["\']')
_LOCAL_DECL = re.compile(r'\b(?:function|const|let|var|class)\s+([A-Za-z_$][\w$]*)')
_DECLARATOR = re.compile(r'(?:\b(?:const|let|var)\s+|,)\s*([A-Za-z_$][\w$]*)\s*=')


def _names_in_clause(clause, want="exported"):
    """Yield the binding names a `{ ... }` import/export clause introduces.
    For `A as B`: the exported name is B; the imported name needed from the source is A."""
    for part in clause.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r'([A-Za-z_$][\w$]*)\s+as\s+([A-Za-z_$][\w$]*)', part)
        if m:
            yield m.group(2) if want == "exported" else m.group(1)
        else:
            m2 = re.match(r'([A-Za-z_$][\w$]*)', part)
            if m2:
                yield m2.group(1)


def parse_exports(src):
    names = set(_DECL.findall(src))
    for blk in _EXPORT_BLOCK.finditer(src):
        # Count re-export-from names as real exports of this module.
        names.update(_names_in_clause(blk.group(1), "exported"))
    return names


def parse_imports(src):
    """-> list of (source_module, [names_needed_from_it])."""
    out = []
    for m in _IMPORT_BLOCK.finditer(src):
        out.append((m.group(2), list(_names_in_clause(m.group(1), "imported"))))
    return out


def local_bindings(src):
    """Names defined or imported in a module (for the honest-re-export check)."""
    # _LOCAL_DECL catches function/class and the first variable declarator. _DECLARATOR also
    # catches later names in ``const a = 1, b = 2`` as emitted by reviewed minified ESM bundles.
    names = set(_LOCAL_DECL.findall(src)) | set(_DECLARATOR.findall(src))
    for m in _IMPORT_BLOCK.finditer(src):
        names.update(_names_in_clause(m.group(1), "exported"))  # local alias is the binding name
    return names


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
    """Return integrity findings, module count, and advisory dead-import rows for one root."""
    if not root.is_dir():
        return ["module_check: no such dir: " + str(root)], 0, []
    # Recursive discovery is deliberate: courses may keep modules in runtime/, scripts/, or a
    # shared sibling. Relative imports are resolved to their actual file rather than flattened to
    # a basename, so two courses may safely use the same module filename.
    module_files = sorted(root.rglob("*.js"))
    exports = {f.resolve(): parse_exports(f.read_text(encoding="utf-8")) for f in module_files}

    problems = []

    # Check 1: every relative-import name resolves.
    files = sorted(root.rglob("*.html")) + module_files
    for f in files:
        src = f.read_text(encoding="utf-8")
        for mod, names in parse_imports(src):
            if not mod.startswith("."):
                continue  # external (CDN) import
            target_path = (f.parent / mod).resolve()
            if target_path not in exports:
                # A focused --dir may import a shared sibling. Resolve that concrete module too,
                # while still rejecting missing paths and never scanning an unrelated allowlist.
                if target_path.is_file() and target_path.suffix == ".js":
                    exports[target_path] = parse_exports(target_path.read_text(encoding="utf-8"))
                else:
                    problems.append("%s imports from %s, which does not resolve to a JavaScript module" % (f, mod))
                    continue
            if target_path not in exports:
                continue
            for n in names:
                if n not in exports[target_path]:
                    problems.append("%s imports `%s` from %s, but %s does not export it"
                                    % (f, n, mod, target_path))

    # Check 2: re-exported names are actually present in the module.
    for f in module_files:
        name = f.name
        src = f.read_text(encoding="utf-8")
        local = local_bindings(src)
        for blk in _EXPORT_BLOCK.finditer(src):
            # `export { x } from "./y"` brings x straight through; not a dangling re-export.
            tail = src[blk.end():blk.end() + 40]
            if re.match(r'\s*from\s*["\']', tail):
                continue
            for n in _names_in_clause(blk.group(1), "imported"):
                if n not in local:
                    problems.append("%s re-exports `%s` but never defines or imports it" % (name, n))

    dead_rows = []
    if dead:
        for f in files:
            names = unused_imports(f.read_text(encoding="utf-8"))
            if names:
                dead_rows.append("%s: dead import(s): %s" % (f.name, ", ".join(names)))

    return problems, len(exports), dead_rows


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
    print("module_check: %d modules across %d discovered root(s); all imports resolve and all re-exports are honest" % (total_modules, len(roots)))


if __name__ == "__main__":
    main()
