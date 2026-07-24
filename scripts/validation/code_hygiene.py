#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Repo-wide code-hygiene validator (the code half of the cadence; prose lives in prose_variety.py).

Holds every CODE check to a single, rigid bar drawn from modern style guides
(PEP 8, the Google Python/JS guides, Clean-Code function sizing, jscpd/PMD copy-paste
detection). It reads our own source, never vendored trees, and is deterministic: it
ranks nothing on vibes and never treats a finding as noise it should hide.

Surfaces scanned:
  - Python source (.py) via tokenize + ast, so a '#' inside a string is never a comment.
  - JS / mjs source (.js, .mjs) via a string-masked line scanner.
  - The student-facing cell code inside every <script> body of a web page.

Detector families (each is a validate_bundle suite, auditable from the report):
  - comments:    block length, colon-leads-to-list, inline length, marker spacing.
  - walls:       runs of code with no blank line to breathe, and runs of same-prefix statements.
  - duplication: near-identical code blocks, the same interface defined twice, trivial wrappers.
  - size:        files past a line budget, and comment-density outside a healthy band.
  - constants:   the same literal hard-coded three or more times, and embedded URLs / hosts / ports.

Usage:
  python3 scripts/validation/code_hygiene.py                 # scan our code, grouped summary
  python3 scripts/validation/code_hygiene.py --scope all     # include every authored source surface
  python3 scripts/validation/code_hygiene.py --file scripts/runtime/engine.js   # one file, every finding
  python3 scripts/validation/code_hygiene.py --kind comments # one family only
  python3 scripts/validation/code_hygiene.py --json          # machine-readable (the gate reads this)
"""
from __future__ import annotations
import argparse, ast, io, json, re, sys, tokenize
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

HERE = Path(__file__).resolve()
TASK1 = find_repo_root(HERE)
SCRIPTS = TASK1 / "scripts"
add_script_paths(SCRIPTS)
from html_document import raw_text_blocks  # noqa: E402
import link_projection as lp  # noqa: E402

# ── tunables, named so no detector below carries a bare magic number ──
MAX_BLOCK_COMMENT_LINES = 3      # a run of full-line comments longer than this is a wall.
MAX_INLINE_COMMENT_LEN = 100     # a trailing comment longer than this wants to be a block.
WALL_LINES = {"cell": 16, "src": 30}   # consecutive non-blank code lines with no breather.
REPEATED_STARTER_RUN = 5         # consecutive statements sharing one prefix: copy-paste smell.
DUP_WINDOW = 10                  # consecutive normalized code lines that must match for a clone.
DUP_IFACE_MIN_BODY = 3           # an interface shorter than this is too trivial to dedupe on.
MAX_FILE_LINES = {".py": 1000, ".js": 1000, ".mjs": 1000, "cell": 220}
DENSITY_HIGH = 0.45              # comment lines / (code + comment) above this is over-documented.
DENSITY_LOW = 0.02               # a substantial file below this is under-documented.
DENSITY_MIN_CODE = 60            # only judge density once a file has at least this much code.
REPEATED_LITERAL_MIN = 3         # the same magic number this many times wants a named constant.

# Structural numbers, not configuration: indices, identity cases, percents, bytes, rounding bases.
# A literal outside this set, repeated, is a real constant worth a name.
_ALLOW_NUM = {-1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 15, 16, 18, 20, 24, 30, 32, 40, 50, 60, 64, 90, 100,
              120, 128, 255, 256, 1000, 1024,
              # HTTP status codes and well-known ports read as themselves, not as tunable config.
              80, 200, 201, 204, 301, 302, 304, 400, 401, 403, 404, 405, 409, 422, 429, 500, 502, 503,
              443, 3000, 5000, 8000, 8080, 9000}

_NONJS_SCRIPT_TYPES = {"application/json", "application/ld+json", "text/css"}
_LIST_ITEM = re.compile(r"^\s*(?:[-*•·]\s+\S|\d+[.)]\s+\S|[a-zA-Z][.)]\s+\S|\S[^:]*\s[:=-]\s+\S)")
_BANNER = re.compile(r"^[\W_]+$")                       # a separator rule: only punctuation / box-drawing.
_URL = re.compile(r"https?://[^\s'\"`)]+", re.I)
_NAMED_CONSTANT_ASSIGN = re.compile(r"^\s*(?:(?:const|let|var)\s+)?[A-Z][A-Z0-9_]*\s*(?::[^=]+)?=")
_CONFIG_KEY_ASSIGN = re.compile(r"^\s*[\"']?[A-Z][A-Z0-9_]*[\"']?\s*:")
_EXAMPLE_URL_HOSTS = {"example.com", "collector.example.com", "api.example.com", "your-tunnel.example.com", "en.wikipedia.org"}
_EXAMPLE_URL_SUBSTRINGS = ("https://nemoclaw-", "nemoclaw-<id>.brevlab.com", "nemoclaw-&lt;id&gt;.brevlab.com")
_LESSON_URLS = ("http://169.254.169.254/latest/meta-data/", "http://localhost:8088")
# Self-congratulatory or over-elaborating comment register: praise of the code, or throat-clearing
# that restates instead of informing. The reader wants what the code does, not the editorial.
_VANITY = re.compile(
    r"\b(?:elegant(?:ly)?|clever(?:ly)?|beautiful(?:ly)?|seamless(?:ly)?"
    r"|bulletproof|battle-tested|slick"
    r"|needless to say|simply put|put simply|in other words|to put it another way"
    r"|what this means is|at a high level|it'?s worth noting|it is worth noting"
    r"|the (?:real |key )?(?:headline|insight|trick|magic|beauty|genius|secret sauce))\b", re.I)


# ── source enumeration ───────────────────────────────────────────────────────
def _is_ours(rel: str) -> bool:
    parts = rel.split("/")
    if any(p in lp.SKIP_DIR for p in parts):
        return False
    if lp.is_mat_path(rel) or any(p in parts for p in ("repos", "node_modules", "vendor")):
        return False
    return not rel.endswith(".min.js")


def _iter_files(scope: str):
    """(path, rel, suffix) for every code file we own. ship scope is the released course plus
    its shared infra; all scope adds other authored source. Vendored and generated trees are
    always skipped."""
    ship = ("web/nemoclaw/", "scripts/", "web/_shared",
            "web/index", "web/courses")
    for f in sorted(TASK1.rglob("*")):
        if not f.is_file() or f.suffix not in (".py", ".js", ".mjs", ".html", ".htm"):
            continue
        rel = f.relative_to(TASK1).as_posix()
        if not _is_ours(rel):
            continue
        if scope != "all" and not rel.startswith(ship):
            continue
        yield f, rel, f.suffix.lower()


def _cells(raw: str):
    """(start_line, body) for each JS <script> body in a page. start_line is the file line the
    body opens on. A json / ld+json / css block or an external src is data, not code, and is
    skipped so the skill-meta JSON never reads as source."""
    for script in raw_text_blocks(raw, "script"):
        body = script.body
        if (
            script.attributes.get("type", "").casefold() in _NONJS_SCRIPT_TYPES
            or "src" in script.attributes
        ):
            continue
        if body.strip():
            yield raw[:script.body_start].count("\n") + 1, body


_UNIT_CACHE = {}


def units(scope: str):
    """(rel, lang, body, line_offset) for every scannable unit, read once and cached per scope.
    A .py/.js file is one unit at offset 0; a page contributes one unit per cell, lang 'cell', at
    the cell's line offset. The five families share the cache, so the tree is read once, not five times."""
    if scope in _UNIT_CACHE:
        return _UNIT_CACHE[scope]
    out = []
    for f, rel, suf in _iter_files(scope):
        text = lp._read_for_links(f)[0]
        if suf in (".html", ".htm"):
            out.extend((rel, "cell", body, start - 1) for start, body in _cells(text))
        else:
            out.append((rel, suf, text, 0))
    _UNIT_CACHE[scope] = out
    return out


# ── line model: classify every physical line once, language-aware ─────────────
class Line:
    """One physical line: blank, code, or comment, plus the comment marker, its text, whether code
    precedes it, and the spaces after the marker. Python is lexed with tokenize, so a '#' inside a
    string never reads as a comment."""
    __slots__ = ("n", "raw", "kind", "marker", "ctext", "inline", "spaces", "code")

    def __init__(self, n, raw):
        self.n, self.raw = n, raw
        self.kind = "blank" if not raw.strip() else "code"
        self.marker = self.ctext = None
        self.inline = False
        self.spaces = None
        self.code = "" if not raw.strip() else raw


def _spaces_after(text: str, marker: str) -> int:
    rest = text[text.index(marker) + len(marker):]
    return len(rest) - len(rest.lstrip(" "))


def _python_lines(text: str):
    lines = [Line(i + 1, ln) for i, ln in enumerate(text.split("\n"))]
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return lines, set()
    for t in toks:
        if t.type != tokenize.COMMENT:
            continue
        n = t.start[0]
        if n - 1 >= len(lines):
            continue
        raw_line = text.split("\n")[n - 1]
        if n == 1 and raw_line.startswith("#!"):
            continue
        L = lines[n - 1]
        L.marker = "#"
        L.ctext = t.string[1:].strip()
        L.inline = bool(raw_line[:t.start[1]].strip())
        L.spaces = _spaces_after(raw_line[t.start[1]:], "#")
        if not L.inline:
            L.kind = "comment"
        else:
            L.code = text.split("\n")[n - 1][:t.start[1]].rstrip()
    doc = _docstring_lines(text)
    for n in doc:
        if 1 <= n <= len(lines):
            lines[n - 1].kind = "doc"
    return lines, doc


def _docstring_lines(text: str) -> set:
    """Line numbers covered by a module/class/function docstring. Docstrings are documentation,
    so they count toward density, but they are never comments for the formatting rules."""
    out = set()
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) \
           and isinstance(first.value.value, str):
            for n in range(first.lineno, getattr(first, "end_lineno", first.lineno) + 1):
                out.add(n)
    return out


_STR_MASK = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")


def _js_lines(text: str):
    """Lex JS-ish source a line at a time. Block comments are tracked across lines; single-line
    strings are masked before the '//' hunt, and '://' is treated as a URL, not a comment. Cell
    code is the same dialect, just carried inside a page's <script> body."""
    lines, in_block = [], False
    for i, raw in enumerate(text.split("\n")):
        L = Line(i + 1, raw)
        if in_block:
            L.kind = "comment"
            L.marker = "*"
            end = raw.find("*/")
            L.ctext = (raw[:end] if end >= 0 else raw).strip().lstrip("* ").strip()
            if end >= 0:
                in_block = False
            lines.append(L)
            continue
        masked = _STR_MASK.sub(lambda m: " " * len(m.group(0)), raw)
        b = masked.find("/*")
        s = masked.find("//")

        if 0 <= b and (s < 0 or b < s):
            pre = raw[:b].strip()
            L.marker, L.inline = "/*", bool(pre)
            L.code = raw[:b].rstrip() if pre else ""
            L.kind = "code" if pre else "comment"
            end = masked.find("*/", b + 2)
            L.ctext = (raw[b + 2:end] if end >= 0 else raw[b + 2:]).strip()
            L.spaces = _spaces_after(raw[b:], "/*")
            in_block = end < 0
        elif s >= 0 and not (s > 0 and raw[s - 1] == ":"):
            pre = raw[:s].strip()
            L.marker, L.inline = "//", bool(pre)
            L.code = raw[:s].rstrip() if pre else ""
            L.kind = "code" if pre else "comment"
            L.ctext = raw[s + 2:].strip()
            L.spaces = _spaces_after(raw[s:], "//")
        lines.append(L)
    return lines, set()


_ANALYZE_CACHE = {}


def analyze(lang: str, text: str):
    """Lex one unit into Line objects, cached: the same text is read by all five families, so it is
    tokenized once. The cached Lines are read-only to every detector, so sharing them is safe."""
    key = (lang, len(text), hash(text))
    if key not in _ANALYZE_CACHE:
        _ANALYZE_CACHE[key] = _python_lines(text) if lang == ".py" else _js_lines(text)
    return _ANALYZE_CACHE[key]


def _blocks(lines):
    """(block, after) for each maximal run of full-line comments. after is the first non-comment
    line that follows (or None at end of file), so a colon-led block can tell a list it forgot
    from a colon that legitimately introduces the code below it."""
    run, out = [], []
    for L in lines:
        if L.kind == "comment":
            run.append(L)
        elif run:
            out.append((run, L)); run = []
    if run:
        out.append((run, None))
    return out


# ── family 1: comment formatting ──────────────────────────────────────────────
def _emit(out, rel, line, kind, snippet, detail):
    out.append({"path": rel, "line": line, "kind": kind, "snippet": snippet[:120], "detail": detail})


def comment_findings(scope: str):
    """Block comments stay short and well-shaped; inline comments stay short and well-spaced.
    Blocks over three lines, a colon that opens no list, an inline essay, or extra spaces after
    an inline marker each surface here. Normal line wrapping inside a short block is allowed."""
    out = []
    for rel, lang, text, off in units(scope):
        lines, _ = analyze(lang, text)
        for blk, after in _blocks(lines):
            if any("@doc" in (L.ctext or "") for L in blk):
                continue                                   # rendered helper-doc DSL, not free prose.
            if len(blk) > MAX_BLOCK_COMMENT_LINES:
                _emit(out, rel, blk[0].n + off, "comment-block-too-long",
                      f"{len(blk)}-line comment: {blk[0].ctext}",
                      "Keep a comment block to three lines. Cut it to the load-bearing point, or move a "
                      "long enumeration into a named data structure the code reads.")
            for i, L in enumerate(blk):
                ct = (L.ctext or "").rstrip()
                if ct.endswith(":"):
                    nxt = blk[i + 1] if i + 1 < len(blk) else None
                    intro_list = nxt is not None and bool(_LIST_ITEM.match(nxt.ctext or ""))
                    intro_code = nxt is None and after is not None and after.kind == "code"
                    if not intro_list and not intro_code:
                        _emit(out, rel, L.n + off, "comment-colon-no-list",
                              f"colon opens no list: {ct}",
                              "A comment colon promises a list or the code below it. Make the next lines list "
                              "items (- / 1. / key: value), or end the line with a period.")

        for L in lines:
            if not L.marker or not L.inline:
                continue
            banner = bool(_BANNER.match(L.ctext or "x"))
            if L.spaces is not None and L.spaces >= 2 and not banner:
                _emit(out, rel, L.n + off, "inline-comment-spacing",
                      f"{L.spaces} spaces after {L.marker}: {L.ctext}",
                      "Use exactly one space between the marker and an inline comment. Aligned comment columns "
                      "drift the moment the code beside them changes.")
            if len(L.ctext or "") > MAX_INLINE_COMMENT_LEN:
                _emit(out, rel, L.n + off, "inline-comment-too-long",
                      f"{len(L.ctext)}-char trailing comment: {L.ctext}",
                      "An inline comment should be a short aside on one line. Shorten it, or lift it to a "
                      "block comment on the line above.")

        for L in lines:
            if not L.ctext or not (L.kind == "comment" or L.inline):
                continue
            m = _VANITY.search(L.ctext)
            if m:
                _emit(out, rel, L.n + off, "comment-vanity",
                      f"editorializing ('{m.group(0)}'): {L.ctext}",
                      "Cut the self-congratulatory or over-elaborating aside and state plainly what the code "
                      "does. Praise of the code and throat-clearing restatement carry no information.")
    return out


# ── family 2: code walls + repeated statements ────────────────────────────────
def _is_statement(nm: str) -> bool:
    """True for an imperative line (a call or an assignment), false for a declarative data entry.
    A run of identical statements is a loop waiting to happen; a run of array/object/tuple literals
    is just a table, which is fine."""
    return ("(" in nm or "=" in nm) and nm[:1] not in "{[.("


def _counts_for_wall(code: str) -> bool:
    """True for an imperative source line that should contribute to a wall-of-code run."""
    s = code.strip()
    if not s or s[:1] in "}])" or s.startswith(("<", "</", "+", "${", "`")):
        return False
    if s.startswith(("{", "[", ".")):
        return False
    if s.endswith(",") and ":" in s and "=>" not in s and "=" not in s:
        return False
    return True


def _flips_template(raw: str) -> bool:
    """True when this physical line opens or closes a JS template body."""
    count = 0
    escaped = False
    for ch in raw:
        if ch == "`" and not escaped:
            count += 1
        escaped = (ord(ch) == 92 and not escaped)
    return count % 2 == 1


def wall_findings(scope: str):
    """Code that never stops to breathe, and copy-paste hiding as a run of identical statements.
    A long unbroken block, or the same statement repeated line after line, each surface here."""
    out = []
    for rel, lang, text, off in units(scope):
        lines, _ = analyze(lang, text)
        budget = WALL_LINES["cell"] if lang == "cell" else WALL_LINES["src"]
        run = 0
        in_template = False
        for L in lines:
            if L.kind != "code":
                run = 0
                continue
            if in_template:
                if _flips_template(L.raw):
                    in_template = False
                run = 0
                continue
            if _flips_template(L.raw):
                in_template = True
            run = run + 1 if _counts_for_wall(L.code) else 0
            if run == budget:
                _emit(out, rel, L.n + off, "code-wall",
                      f"{budget}+ code lines with no blank line: {L.raw.strip()}",
                      "Insert a blank line at the next logical seam so the block can breathe. A wall of code "
                      "reads as one undifferentiated lump.")
        prev, count, start = None, 0, None

        def flush(at):
            if count >= REPEATED_STARTER_RUN:
                _emit(out, rel, (start or at) + off, "repeated-statement",
                      f"{count} identical statements in a row: {prev}",
                      "The same statement repeats line after line. Drive it from a list or a loop so the "
                      "intent is one place, not copied per case.")
        for L in lines:
            nm = _norm(L.code) if L.kind == "code" else ""
            if nm and _is_statement(nm) and nm == prev:
                count += 1
            else:
                flush(L.n)
                prev, count, start = (nm, 1, L.n) if nm and _is_statement(nm) else (None, 0, None)
        flush(lines[-1].n if lines else 0)
    return out


# ── family 3: duplication (blocks, interfaces, trivial wrappers) ───────────────
_NORM_STR = re.compile(r"'[^']*'|\"[^\"]*\"|`[^`]*`")
_NORM_NUM = re.compile(r"\b\d+\.?\d*\b")
_NORM_WS = re.compile(r"\s+")


def _norm(code: str) -> str:
    s = _NORM_STR.sub("S", code)
    s = _NORM_NUM.sub("N", s)
    return _NORM_WS.sub(" ", s).strip()


def duplication_findings(scope: str):
    """Three faces of duplication: a block of code repeated almost verbatim elsewhere, the same
    interface defined in two places, and a function that only forwards to another."""
    out = []
    index = defaultdict(list)
    for rel, lang, text, off in units(scope):
        lines, _ = analyze(lang, text)
        norm = [(_norm(L.code), L.n + off) for L in lines if L.kind == "code" and len(L.code.strip()) > 3]
        for i in range(len(norm) - DUP_WINDOW + 1):
            sig = tuple(c for c, _ in norm[i:i + DUP_WINDOW])
            if any(len(c) < 4 for c in sig):
                continue
            index[sig].append((rel, norm[i][1]))
    # A clone has a constant line-shift between its two copies.
    # Grouping windows by (fileA, fileB, shift), then merging consecutive starts, gives one region.
    pairs = defaultdict(list)
    for sig, locs in index.items():
        locs = sorted(set(locs))
        if len(locs) < 2 or len(locs) > 8:           # >8 copies is a shared idiom, not a clone.
            continue
        for a in range(len(locs)):
            for b in range(a + 1, len(locs)):
                (ra, la), (rb, lb) = locs[a], locs[b]
                if ra == rb and abs(la - lb) < DUP_WINDOW:
                    continue
                pairs[(ra, rb, lb - la)].append(la)

    seen = set()
    for (ra, rb, shift), starts in pairs.items():
        starts = sorted(set(starts))
        runs, s0, prev = [], starts[0], starts[0]
        for x in starts[1:]:
            if x - prev <= DUP_WINDOW:
                prev = x
            else:
                runs.append((s0, prev)); s0 = prev = x
        runs.append((s0, prev))
        for lo, hi in runs:
            length = (hi - lo) + DUP_WINDOW
            key = (ra, lo, rb, lo + shift)
            if key in seen:
                continue
            seen.add(key)
            _emit(out, ra, lo, "duplicate-block",
                  f"~{length} lines mirror {rb}:{lo + shift}",
                  f"This block is near-identical to {rb}:{lo + shift}. Extract one shared helper both call; "
                  "if the duplication is deliberate teaching, keep it and note why.")
    out.extend(_interface_findings(scope))
    out.extend(_wrapper_findings(scope))
    return out


def _body_sig(src_lines) -> frozenset:
    """Normalized non-trivial code lines of a function body, for telling whether two same-named
    functions share an implementation or only a common name."""
    return frozenset(n for ln in src_lines if len(n := _norm(ln)) > 3)


def _js_body(text: str, after: int):
    """Lines of a JS function body, brace-matched from the first '{' after its signature."""
    j = text.find("{", after)
    if j < 0:
        return []
    depth, k = 0, j
    while k < len(text):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                break
        k += 1
    return text[j + 1:k].split("\n")


def _signatures(scope: str):
    """(name, arity, rel, line, body_len, body_sig) for every function we define, across languages.
    The key for duplicate-interface is (name, arity), later gated on body overlap; a tiny body is
    skipped as too trivial to matter."""
    sigs = []
    for rel, lang, text, off in units(scope):
        src = text.split("\n")
        if lang == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    arity = len(node.args.args) + len(node.args.kwonlyargs)
                    end = getattr(node, "end_lineno", node.lineno) or node.lineno
                    sigs.append((node.name, arity, rel, node.lineno + off, end - node.lineno,
                                 _body_sig(src[node.lineno:end])))
        else:
            for m in re.finditer(r"\bfunction\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", text):
                arity = len([a for a in m.group(2).split(",") if a.strip()])
                ln = text[:m.start()].count("\n") + 1
                sigs.append((m.group(1), arity, rel, ln + off, DUP_IFACE_MIN_BODY,
                             _body_sig(_js_body(text, m.end()))))
    return sigs


# Conventional entrypoint, lifecycle, and UI-callback names that recur across modules by design.
# A shared 'main' or 'render' is convention, so a name collision alone is not a duplicated interface.
_CONVENTIONAL = {"main", "run", "setup", "teardown", "handler", "health", "index", "init", "save",
                 "load", "show", "hide", "render", "update", "draw", "paint", "tick", "read", "write",
                 "fetch", "build", "check", "send", "close", "open", "start", "stop", "reset",
                 "toggle", "refresh", "finish", "flush", "tostring", "format", "setstatus"}


def _interface_findings(scope: str):
    out, by_key = [], defaultdict(list)
    for name, arity, rel, ln, blen, bodysig in _signatures(scope):
        if blen >= DUP_IFACE_MIN_BODY and not name.startswith("_") and name.lower() not in _CONVENTIONAL:
            by_key[(name, arity)].append((rel, ln, bodysig))
    for (name, arity), locs in by_key.items():
        files = {r for r, _, _ in locs}
        if len(files) < 2 and len(locs) < 3:
            continue
        # A real duplicate interface shares an implementation, not just a name: require two of the
        # definitions to overlap by half their body lines before flagging.
        similar = any(
            locs[a][2] and locs[b][2]
            and len(locs[a][2] & locs[b][2]) / len(locs[a][2] | locs[b][2]) >= 0.5
            for a in range(len(locs)) for b in range(a + 1, len(locs)))
        if not similar:
            continue
        where = ", ".join(f"{r}:{l}" for r, l, _ in sorted(locs)[:6])
        first = sorted(locs)[0]
        _emit(out, first[0], first[1], "duplicate-interface",
              f"{name}/{arity} defined {len(locs)}x: {where}",
              f"'{name}' is defined in {len(files)} places with a near-identical body. Hoist it into one "
              "shared module both import, so a fix lands once instead of drifting between copies.")
    return out


def _wrapper_findings(scope: str):
    out = []
    for rel, lang, text, off in units(scope):
        if lang != ".py":
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = [b for b in node.body if not (isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant))]
            if len(body) != 1 or not isinstance(body[0], ast.Return):
                continue
            val = body[0].value
            if not isinstance(val, ast.Call):
                continue
            params = [a.arg for a in node.args.args]
            args = [a.id for a in val.args if isinstance(a, ast.Name)]
            if params and args == params and not node.decorator_list:
                _emit(out, rel, node.lineno + off, "trivial-wrapper",
                      f"{node.name}() only forwards to another call",
                      "This function only passes its arguments straight through. Call the inner function "
                      "directly, or give the wrapper a reason to exist (a default, a guard, a rename).")
    return out


# ── family 4: file size + comment density ──────────────────────────────────────
def size_findings(scope: str):
    """A file past its line budget, and a real source file whose comment density sits outside a
    healthy band. Teaching cells are exempt from density: they are taught, not just shipped."""
    out = []
    page_cells = defaultdict(lambda: [0, []])
    for rel, lang, text, off in units(scope):
        lines, _ = analyze(lang, text)
        n = len(lines)
        if lang == "cell":
            page_cells[rel][0] += n
            continue
        cap = MAX_FILE_LINES.get(lang)
        if cap and n > cap:
            _emit(out, rel, 1, "file-too-large", f"{n} lines (budget {cap})",
                  "Split this file along a seam: pull a cohesive group of functions into its own module. "
                  "A file this long is hard to hold in one read.")
        code = sum(1 for L in lines if L.kind == "code")
        comment = sum(1 for L in lines if L.kind in ("comment", "doc"))
        total = code + comment
        if total:
            density = comment / total
            if density > DENSITY_HIGH and total > 20:
                _emit(out, rel, 1, "over-documented", f"{density:.0%} of lines are comments",
                      "More than two lines of comment for every three of code. Let clear names and small "
                      "functions carry the meaning; keep comments for the why, not the what.")
            if density < DENSITY_LOW and code >= DENSITY_MIN_CODE:
                _emit(out, rel, 1, "under-documented", f"{code} code lines, {density:.0%} comments",
                      "A substantial file with almost no comment. Add a module docstring and a why-comment "
                      "at each non-obvious decision.")

    for rel, (n, _) in page_cells.items():
        if n > MAX_FILE_LINES["cell"]:
            _emit(out, rel, 1, "cell-too-large", f"{n} lines of cell code on one page",
                  "This page carries a lot of cell code. Consider splitting a cell, or moving shared engine "
                  "code into a helper the cells import.")
    return out


# ── family 5: hard-coded / non-surfaced constants ──────────────────────────────
def _url_is_example_or_lesson(url: str) -> bool:
    """True for intentionally fake URLs and security-demo URLs used as lesson material."""
    clean = url.replace("</code>", "").rstrip(".,);")
    from urllib.parse import urlparse
    try:
        host = re.sub(r"^www\.", "", urlparse(clean).hostname or "")
    except ValueError:
        # Regex source can contain URL-shaped fragments such as ``https://[^``. A malformed
        # literal is not an example URL and must remain visible to the caller as a finding.
        return False
    return (host in _EXAMPLE_URL_HOSTS or any(part in clean for part in _EXAMPLE_URL_SUBSTRINGS)
            or any(clean.startswith(part) for part in _LESSON_URLS))


def _url_is_named_config(lines: list[Line], idx: int) -> bool:
    """True when a URL is already surfaced as an uppercase constant/config value."""
    code = lines[idx].code.strip()
    if _NAMED_CONSTANT_ASSIGN.match(code) or _CONFIG_KEY_ASSIGN.match(code):
        return True
    cur_indent = len(lines[idx].code) - len(lines[idx].code.lstrip())
    for prev in range(idx - 1, max(-1, idx - 12), -1):
        prev_code = lines[prev].code.strip()
        if not prev_code:
            continue
        prev_indent = len(lines[prev].code) - len(lines[prev].code.lstrip())
        if prev_indent <= cur_indent and _NAMED_CONSTANT_ASSIGN.match(prev_code):
            return True
    return False


def constant_findings(scope: str):
    """A value baked into the code instead of surfaced as a named constant: the same magic number
    used three or more times, or an embedded URL a reader cannot retune in one place. String
    literals are left alone; keys and enum values legitimately repeat."""
    out = []
    for rel, lang, text, off in units(scope):
        lines, _ = analyze(lang, text)
        code_text = "\n".join(L.code for L in lines if L.kind == "code")
        masked = _NORM_STR.sub(" ", code_text)         # never read a digit inside a string literal.
        nums = Counter()
        for tok in re.findall(r"(?<![\w.])-?\d+\.?\d*\b", masked):
            try:
                v = float(tok)
            except ValueError:
                continue
            if v.is_integer() and int(v) in _ALLOW_NUM:
                continue
            nums[tok] += 1
        for lit, c in nums.items():
            if c >= REPEATED_LITERAL_MIN:
                _emit(out, rel, 1, "repeated-literal", f"{lit} appears {c}x",
                      f"The number {lit} is hard-coded {c} times. Name it once as a constant and reference "
                      "the name, so a change lands in one place.")
        for idx, L in enumerate(lines):
            if L.kind != "code":
                continue
            u = _URL.search(L.code)
            if not u:
                continue
            url = u.group(0)
            try:
                host = (urlsplit(url).hostname or "").lower()
            except ValueError:
                host = ""
            if (host == "workers.dev" or host.endswith(".workers.dev")
                    or host in {"schema.org", "www.schema.org", "w3.org", "www.w3.org"}
                    or host.endswith(".schema.org") or host.endswith(".w3.org")
                    or _url_is_named_config(lines, idx) or _url_is_example_or_lesson(url)):
                continue
            _emit(out, rel, L.n + off, "embedded-url", f"{url[:60]}",
                  "A URL is hard-coded in the logic. Surface it as a named constant or a config value so "
                  "the endpoint is retuned in one place, not hunted through the code.")
    return out


# ── family 6: prose tells in code (em-dash anywhere, vanity inside user-facing strings) ──
# These validators define and quote the tell-patterns by necessity, so the prose family would only
# flag its own detection machinery there.
_PROSE_EXEMPT = {"scripts/validation/code_hygiene.py", "scripts/validation/prose_variety.py",
                 "scripts/validation/grounding.py", "scripts/validation/validate_bundle.py"}


def prose_findings(scope: str):
    """Prose tells the comment checks miss: an em-dash anywhere (comment, string, or UI copy),
    and self-congratulatory phrasing inside a string literal a user reads."""
    out = []
    for rel, lang, text, off in units(scope):
        if rel in _PROSE_EXEMPT:
            continue
        lines, _ = analyze(lang, text)
        for L in lines:
            if "—" in L.raw:
                _emit(out, rel, L.n + off, "em-dash", L.raw.strip(),
                      "An em-dash reads as an AI tell. Rewrite the whole phrase so no dash is needed; "
                      "do not swap it for a colon, comma, or hyphen in place.")
            if L.kind == "code":
                for m in _NORM_STR.finditer(L.code):
                    v = _VANITY.search(m.group(0))
                    if v:
                        _emit(out, rel, L.n + off, "string-vanity",
                              f"editorializing ('{v.group(0)}') in copy: {m.group(0)}",
                              "Cut the self-congratulatory or over-elaborating phrasing from this user-facing "
                              "string; say plainly what it conveys.")
    return out


# ── aggregation + CLI ──────────────────────────────────────────────────────────
FAMILIES = {
    "comments": comment_findings,
    "walls": wall_findings,
    "duplication": duplication_findings,
    "size": size_findings,
    "constants": constant_findings,
    "prose": prose_findings,
}


def scan(scope: str = "ship", families=None):
    """Every finding across the requested families. Each is a dict of family, path, line, kind,
    snippet, detail, so a caller can route it to its suite by the family tag."""
    out = []
    for name, fn in FAMILIES.items():
        if families and name not in families:
            continue
        for r in fn(scope):
            r["family"] = name
            out.append(r)
    return out


def cell_hygiene(f: Path):
    """(kind, snippet) for one HTML page's cell comments and walls. Kept for the quick per-page
    check and older callers; the repo-wide gate uses scan() instead."""
    raw = lp._read_for_links(f)[0]
    out = []
    for _start, body in _cells(raw):
        lines, _ = _js_lines(body)
        for blk, _after in _blocks(lines):
            if len(blk) > MAX_BLOCK_COMMENT_LINES:
                out.append(("comment-block-too-long", (blk[0].ctext or "")[:88]))
        run = 0
        for L in lines:
            run = run + 1 if L.kind != "blank" else 0
            if run == WALL_LINES["cell"]:
                out.append(("code-wall", L.raw.strip()[:88]))
    return out


def self_test() -> list[str]:
    """Check source ownership and executable-header parsing."""
    failures = []
    cases = {
        "web/nemoclaw/vendor/marked.esm.js": False,
        "scripts/.figtools/node_modules/pkg/index.js": False,
        "web/nemoclaw/mats/reference.js": False,
        "web/nemoclaw/scripts/_shared.js": True,
        "scripts/runtime/engine.js": True,
    }
    for rel, expected in cases.items():
        if _is_ours(rel) != expected:
            failures.append(f"source ownership misclassified: {rel}")
    parsed, _ = _python_lines("#!/usr/bin/env python3\n# explanatory comment.\nprint('ok')\n")
    if parsed[0].kind != "code" or parsed[0].marker:
        failures.append("Python shebang was classified as prose commentary")
    if parsed[1].kind != "comment":
        failures.append("ordinary Python comment disappeared with the shebang carve-out")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description="Repo-wide code-hygiene validator.",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--scope", choices=["ship", "all"], default="ship")
    ap.add_argument("--kind", help="one family: " + ", ".join(FAMILIES))
    ap.add_argument("--file", help="limit to one file (path fragment)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        failures = self_test()
        if failures:
            for item in failures:
                print(item)
            return 1
        print("code_hygiene self-test: PASS")
        return 0
    fams = [a.kind] if a.kind else None
    rows = scan(a.scope, fams)
    if a.file:
        rows = [r for r in rows if a.file in r["path"]]
    if a.json:
        print(json.dumps({"scope": a.scope, "count": len(rows), "findings": rows}, indent=2))
        return 0
    by_kind = Counter(r["kind"] for r in rows)
    print(f"code_hygiene scope={a.scope}: {len(rows)} finding(s) across {len({r['path'] for r in rows})} file(s)")
    for kind, c in by_kind.most_common():
        print(f"  {c:4d}  {kind}")
    if a.file or a.kind:
        print()
        for r in rows[:200]:
            print(f"  {r['path']}:{r['line']}  [{r['kind']}] {r['snippet']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
