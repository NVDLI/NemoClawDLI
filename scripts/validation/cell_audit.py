#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Minimal bars for the runnable cells (every mountCanvasFlow/mountRunCell `code:`).

A good cell is transparent (a model call surfaces its work via the house logger or a
raw-request <details>, not silence), uses helpers.log not console.* (which students
never see), and is correct: awaited model calls, keys from helpers.getKey() not inlined,
no blocking dialog. Duplicate keys and embedded credentials are ship-blocking because the browser
either executes different code than the learner reads or exposes a secret; other findings guide review.

Run:  python3 scripts/validation/cell_audit.py
"""
from __future__ import annotations
import re, sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root
from runtime.html_document import without_elements

HERE = Path(__file__).resolve()
TASK1 = find_repo_root(HERE)
WEB = TASK1 / "web"

# A cell's code field: `code:` then a backtick literal (may hold escaped \` from nesting).
CODE = re.compile(r"code:\s*`((?:\\.|[^`\\])*)`", re.S)
# Cell-only API (helpers./ctx.view) belongs in a runnable cell, never a static <pre>.
PRE_RE = re.compile(r"<pre\b.*?</pre>", re.S | re.I)
CELL_API = re.compile(r"\bhelpers\.|\bctx\.view\b")

MODEL_CALL = re.compile(r"(?<![\w.])(chat|chatStream)\s*\(|\.\s*stream\s*\(", re.I)
# Any one of these clears the transparency bar: house logger, view method, maze, artifact, or return.
# A returned value counts because the cell panel renders it.
# An unsuppressed chatStream also streams into the panel.
SURFACE = re.compile(
    r"\blog\s*\(|\blog\.|helpers\.log|ctx\.view|\.view\.|view\.(token|reasoning|usage|tool|warn|html)"
    r"|\binfo\s*\(|\bshow\s*\(|\.html\s*\(|mountChatUI|runMaze|\breturn\s+\S", re.I)
CONSOLE = re.compile(r"\bconsole\s*\.\s*(log|error|warn|info|debug)\b")
DIALOG = re.compile(r"\b(alert|confirm)\s*\(|\bwindow\s*\.\s*prompt\s*\(|document\s*\.\s*write\s*\(")
INLINE_KEY = re.compile(r"nvapi-(?!…|123|FAKE|xxx|redacted|FILL|YOUR)[A-Za-z0-9_-]{8,}")


def highlighter_missing(text: str) -> list[str]:
    """Return the missing CodeMirror pieces for one HTML document.

    The same-origin distribution contains unmodified CodeMirror core and mode
    files. The dependency-integrity gate owns their exact version and digests.
    """
    vendored_core = bool(re.search(
        r"[\"'](?:\.\./|\./)?vendor/codemirror-\d+\.\d+\.\d+\.js[\"']",
        text,
        re.I,
    ))
    vendored_javascript = bool(re.search(
        r"[\"'](?:\.\./|\./)?vendor/codemirror-mode-javascript-\d+\.\d+\.\d+\.js[\"']",
        text,
        re.I,
    ))
    return [n for n, ok in (
        ("CodeMirror core js", vendored_core or bool(re.search(r"codemirror(?:\.min)?\.js", text, re.I))),
        ("javascript mode", vendored_javascript or "mode/javascript" in text.lower()),
        ("editor css", bool(re.search(r"codemirror(?:-\d+\.\d+\.\d+)?(?:\.min)?\.css", text, re.I))),
    ) if not ok]


def strip_noise(c: str) -> str:
    """Blank strings + comments so `chat(` in either isn't read as a call.
    Strings first, so a // inside a string (a URL) can't eat the line."""
    c = re.sub(r'"(?:\\.|[^"\\])*"', '""', c)
    c = re.sub(r"'(?:\\.|[^'\\])*'", "''", c)
    c = re.sub(r"/\*.*?\*/", " ", c, flags=re.S)
    c = re.sub(r"//[^\n]*", " ", c)
    return c


def _mask_js_literals(code: str) -> str:
    """Blank comments and string bodies without moving any source position."""
    chars = list(code)
    i = 0
    while i < len(chars):
        if code.startswith("//", i):
            end = code.find("\n", i)
            end = len(code) if end < 0 else end
            for j in range(i, end):
                chars[j] = " "
            i = end
            continue
        if code.startswith("/*", i):
            end = code.find("*/", i + 2)
            end = len(code) if end < 0 else end + 2
            for j in range(i, end):
                if chars[j] != "\n":
                    chars[j] = " "
            i = end
            continue
        if code[i] in {'"', "'", "`"}:
            quote = code[i]
            end = i + 1
            while end < len(chars):
                if code[end] == "\\":
                    end += 2
                    continue
                if code[end] == quote:
                    break
                end += 1
            probe = end + 1
            while probe < len(chars) and code[probe].isspace():
                probe += 1
            quoted_key = quote != "`" and probe < len(chars) and code[probe] == ":"
            if not quoted_key:
                for j in range(i + 1, min(end, len(chars))):
                    if chars[j] != "\n":
                        chars[j] = " "
            i = min(end + 1, len(chars))
            continue
        i += 1
    return "".join(chars)


def duplicate_object_keys(code: str) -> list[tuple[str, int]]:
    """Return repeated literal keys inside one JavaScript object.

    JavaScript accepts duplicate object keys and silently keeps the last value. Runnable examples
    cannot rely on that behavior: a learner sees two instructions while the runtime follows one.
    The scanner operates at direct object depth and ignores strings, comments, nested objects,
    arrays, and function calls.
    """
    masked = _mask_js_literals(code)
    stack: list[int] = []
    spans: list[tuple[int, int]] = []
    for index, char in enumerate(masked):
        if char == "{":
            stack.append(index)
        elif char == "}" and stack:
            spans.append((stack.pop(), index))

    findings: list[tuple[str, int]] = []
    for start, end in spans:
        body = masked[start + 1:end]
        braces = brackets = parens = 0
        segment_start = 0
        keys: dict[str, int] = {}
        for offset, char in enumerate(body):
            if char == "{": braces += 1
            elif char == "}": braces = max(0, braces - 1)
            elif char == "[": brackets += 1
            elif char == "]": brackets = max(0, brackets - 1)
            elif char == "(": parens += 1
            elif char == ")": parens = max(0, parens - 1)
            elif not (braces or brackets or parens) and char == ",":
                segment_start = offset + 1
            elif not (braces or brackets or parens) and char == ":":
                lead = body[segment_start:offset]
                match = re.fullmatch(
                    r"\s*(?:([A-Za-z_$][\w$]*)|[\"']([A-Za-z_$][\w$]*)[\"'])\s*", lead)
                if not match:
                    continue
                key = match.group(1) or match.group(2)
                key_group = 1 if match.group(1) else 2
                absolute = start + 1 + segment_start + match.start(key_group)
                line = code[:absolute].count("\n") + 1
                if key in keys:
                    findings.append((key, line))
                else:
                    keys[key] = line
    return findings


def is_awaited(code: str, call_start: int) -> bool:
    """Is this model call awaited (or returned to a caller that will)? An un-awaited async call in a
    cell resolves to a Promise the student never sees, so the cell silently does nothing on Run.
    Looks back a short window for `await`, or a `return`/`=>` that hands the promise on."""
    pre = code[max(0, call_start - 48):call_start]   # the text just before the call
    return ("await" in pre) or bool(re.search(r"(return|=>)\s*$", pre.strip()))


def audit_page(path: Path):
    """Check every runnable cell on one page against the cell contract. This catches the cells that
    would frustrate or mislead a student: a model call that prints nothing, console.* output they
    never see, an un-awaited call that no-ops, a blocking alert/confirm, a real API key baked into the
    cell, and cell-only API left in a non-editable <pre>. Returns the finding lists run() merges."""
    text = path.read_text(errors="ignore")
    rel = str(path.relative_to(WEB.parent))
    opaque, console, unawaited, dialog, key = [], [], [], [], []
    for m in CODE.finditer(text):                 # each `code:` cell literal on the page
        code = m.group(1)
        clean = strip_noise(code)                 # blank strings/comments so keywords inside them are ignored
        calls = list(MODEL_CALL.finditer(clean))
        if calls and not SURFACE.search(clean):   # makes a model call but never surfaces its output
            snippet = clean[calls[0].start():calls[0].start() + 40].replace("\n", " ")
            opaque.append((rel, snippet.strip()))
        for cm in CONSOLE.finditer(clean):        # console.* output the student cannot see
            console.append((rel, cm.group(0)))
        for cm in calls:
            if not is_awaited(clean, cm.start()):  # async model call left un-awaited (silently no-ops)
                unawaited.append((rel, clean[cm.start():cm.start() + 32].replace("\n", " ").strip()))
        for dm in DIALOG.finditer(clean):         # blocking alert/confirm/prompt/document.write
            dialog.append((rel, dm.group(0)))
        for km in INLINE_KEY.finditer(code):   # keys live in string literals, so scan raw
            key.append((rel, km.group(0)[:14] + "..."))
    # cell-only API shown in a static <pre> (not a runnable cell)
    body = without_elements(text, {"script"})
    static = [(rel, "static <pre> uses cell-only API (helpers./ctx.view); should be a runnable, editable cell")
              for pm in PRE_RE.finditer(body) if CELL_API.search(pm.group(0))]
    # Editable cells need CodeMirror core, javascript mode, and editor CSS.
    # Otherwise the cell falls back to a plain, unhighlighted textarea.
    unhighlighted = []
    if re.search(r"mountRunCell\s*\(|mountCanvasFlow\s*\(", text):
        miss = highlighter_missing(text)
        if miss:
            unhighlighted.append((rel, "editable cells but the syntax highlighter is not loaded (missing: "
                                  + ", ".join(miss) + "); the editor falls back to a plain, unhighlighted textarea"))
    return opaque, console, unawaited, dialog, key, static, unhighlighted



def audit_runtime_contract():
    """Guard the shared learner-facing cell UI against regressions that make code dominate again.
    This intentionally checks the runtime contract, not a validator tag: students should find helpers
    and editable code above the output, keep code collapsed by default unless a cell opts in, and reset
    one cell or node without rebuilding the whole page."""
    src = (WEB / "nemoclaw" / "scripts" / "_canvas.js").read_text(errors="ignore")
    shared = (WEB / "nemoclaw" / "scripts" / "_shared.js").read_text(errors="ignore")
    findings = []

    def need(ok: bool, msg: str):
        if not ok:
            findings.append(("web/nemoclaw/scripts/_canvas.js", msg))

    rc_out = src.find('class="rc-out')
    rc_code = src.find('class="rc-code-det"')
    need(rc_out >= 0 and rc_code >= 0 and rc_code < rc_out,
         "run-cell code controls must stay above output, with the code editor collapsed by default")
    need('const codeOpenAttr = opts.openCode === true ? " open" : "";' in src,
         "run-cell code visibility must be an explicit openCode opt-in, not a default-open editor")
    need('const autoCollapseCode = opts.autoCollapseCode !== false && opts.openCode !== true;' in src,
         "run-cell code should collapse after Run unless the cell explicitly starts open for student editing")
    need('class="rc-code-det"${codeOpenAttr}' in src,
         "run-cell code details must use the openCode opt-in so most cells hide code while selected cells can show it")
    need(not re.search(r'<details class="rc-code-det"\s+open\b', src),
         "run-cell code must not be hard-coded open by default")
    need(not re.search(r'<details class="rc-schemas-det"[^>]*\sopen\b', src),
         "run-cell schemas must be collapsed by default; schema plumbing should not lead the lesson")
    need('_cellBtnHTML("reset", "↺ Reset", "rc-reset"' in src and "function resetCell" in src,
         "run-cells need a per-cell Reset that restores original code/schema and clears output")
    need("const _runCellState = {};" in src and "\"state\",       ...Object.keys(schemaVars)" in src
         and "_runCellState, ...Object.values(schemaVars)" in src,
         "run-cells must inject a shared state object so one cell can hand data to the next")
    need('class="cf-code-copy rc-code-copy cell-code-copy"' in src,
         "run-cells need a copy affordance for students who want to take edited code elsewhere")
    need('cm = attachCM(ta, "javascript");' in src,
         "run-cell JavaScript editors must remain editable by default")
    need('_cellBtnHTML("reset", "↺ Reset", "cf-panel-reset"' in src and "function resetNode" in src,
         "canvas-flow nodes need per-node Reset so one step can be restored without resetting the whole flow")
    need('if (codeDet && !codeDet.open) codeDet.open = true;' in src,
         "run-cell errors should open the code panel when a failing line is marked")
    need('out.scrollIntoView({ block: "nearest", behavior: "smooth" });' not in src,
         "run-cell output must not auto-scroll on Run; hidden code should reduce page jumps, not move the viewport")
    shared_primitives = [
        "function _cellBtnHTML", "function _cellLangSummaryHTML", "function _cellCodeOpen",
        "function _appendCellJson", "function _appendCellText", "function _appendCellReturn",
        "function _installStructuredLog", "const CELL_CANVAS_VISIBLE_LINES = 39;",
    ]
    for token in shared_primitives:
        need(token in src, f"cell UI/runtime must use shared abstraction token: {token}")
    need('_cellBtnHTML("run", "▶ Run", "cf-panel-runone"' in src and '_cellBtnHTML("run", runLabel(), "rc-run"' in src,
         "CanvasFlow and RunCell run buttons must share cell-btn/cell-btn-run styling while preserving legacy selectors")
    need('_cellBtnHTML("reset", "↺ Reset", "cf-panel-reset"' in src and '_cellBtnHTML("reset", "↺ Reset", "rc-reset"' in src,
         "CanvasFlow and RunCell reset buttons must share cell-btn/cell-btn-reset styling while preserving legacy selectors")
    need('class="cf-det-chip cell-lang-chip rc-lang"' in src and 'class="cf-det-chip cell-lang-chip"' in src,
         "editable code headers must use the same JS language chip in RunCell and CanvasFlow")
    need('>code <span' not in src and '>code<' not in src,
         "editable code headers must not render the old plain 'code' label; use the JS chip abstraction")
    need('log.h = (title)' in src and 'log.json = (a, b)' in src and 'log.kv = (obj)' in src and 'log.clear = ()' in src,
         "helpers.log must expose the same h/json/kv/clear surfaces in CanvasFlow and RunCell")
    need(src.count('_installStructuredLog(log,') >= 2,
         "CanvasFlow and RunCell must both install structured logging through _installStructuredLog")
    need('div.dataset.logText = plain.join(" ");' in src and "return div;" in src,
         "helpers.log must return its created status element consistently in CanvasFlow and RunCell")
    need('err.className = "cell-runtime-error";' in src,
         "RunCell failures need a stable marker for Studio all-cell validation")
    need("export function delay(ms, signal = null)" in shared and "fetchRetry, delay," in shared,
         "student cells need one shared Stop-aware helpers.delay implementation")
    need("helpers.signal = ac.signal;" in src and "helpers.delay = (ms, signal = ac.signal)" in src,
         "RunCell must expose its Stop signal and inject it into helpers.delay")
    need("helpers.delay = (ms, signal = _sig)" in src,
         "CanvasFlow must inject its Stop signal into helpers.delay")
    need("if (!ac.signal.aborted && outputCount === 0)" not in src and
         'else if (result !== undefined && typeof result === "object"' in src and
         '_appendJson(result, "returned value")' in src,
         "RunCell must render a returned value even after the cell logged process output")
    return findings



CANVAS_MOUNT_RE = re.compile(r"mount(?:CanvasFlow|RunCell)\s*\(")
CANVAS_LONG_DEFAULT_OPEN_LINES = 40
CANVAS_DEFAULT_VISIBLE_MAX_LINES = 39
VISIBLE_COMMENT_WALL = 4
VISIBLE_LINE_LIMIT = 180
VISIBLE_INDENT_LIMIT = 24
CANVAS_LABEL_WORD_LIMIT = 14
CANVAS_TITLE_WORD_LIMIT = 10
CANVAS_COPY_WORD_LIMIT = 55
CANVAS_COPY_RE = re.compile(
    r'\b(label|intro|title|summary)\s*:\s*(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\')',
    re.S,
)
RUN_CELL_LINE_LIMIT = 120
RUN_CELL_COMPRESSED_LIMIT = 4
RUN_CELL_SINGLE_LETTER_LIMIT = 5
OPTIONAL_VISIBILITY_RE = re.compile(
    r"^\s*//\s*(?:(?:helpers\.)?log(?:\.(?:details|json|kv))?\s*\(|Optional visibility:|Alternate input:)",
    re.M | re.I,
)
RAW_SLEEP_RE = re.compile(r"await\s+new\s+Promise\([^\n]*(?:setTimeout|sleep)", re.I)
PROMPT_ASSIGNMENT_RE = re.compile(
    r'^\s*state\.(question|userQuestion|goal|ticket|topic|input|query)\s*=\s*(?:["\'\[]|EXAMPLES\b)',
    re.M,
)
PROMPT_BANNED_NARRATION = "Set the student-editable prompt/input for the next step."
PROMPT_PAGE_COUNTS = {
    "01c-tools.html": 4,
    "02a-routing.html": 4,
    "02b-rag.html": 3,
    "02c-deep.html": 1,
}


def _is_visible_cell(block: str, code_start: int, lines: int, canvas: bool) -> bool:
    """Return whether the code is visible by default. Collapsed cells can still be opened,
    but this rule is for code that occupies the learner's first view."""
    pre = block[max(0, code_start - 700):code_start]
    if "showCode: false" in pre[-350:]:
        return False
    if "showCode: true" in pre[-350:] or "openCode: true" in pre[-350:]:
        return True
    return canvas and lines <= CANVAS_DEFAULT_VISIBLE_MAX_LINES


def _visible_hygiene(rel: str, cell_line: int, code: str):
    """Low-noise checks for code students see by default: no tabs, no giant comment
    wall, no extreme indentation, and no very long lines that force horizontal reading."""
    findings = []
    comment_run = 0
    for i, line in enumerate(code.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("//"):
            comment_run += 1
            if len(line) > 130:
                findings.append((rel, f"line {cell_line + i - 1}: visible comment line is too long; wrap or shorten it"))
            if comment_run == VISIBLE_COMMENT_WALL + 1:
                findings.append((rel, f"line {cell_line + i - 1}: visible code opens with more than {VISIBLE_COMMENT_WALL} consecutive // lines; move detail into prose or a helper note"))
        elif stripped:
            comment_run = 0
        if "\t" in line:
            findings.append((rel, f"line {cell_line + i - 1}: tab indentation in visible learner code; use spaces"))
        indent = len(line) - len(line.lstrip(" "))
        if indent > VISIBLE_INDENT_LIMIT and stripped and not stripped.startswith("//"):
            findings.append((rel, f"line {cell_line + i - 1}: {indent} leading spaces in visible learner code; split or unnest the block"))
        if len(line) > VISIBLE_LINE_LIMIT and not stripped.startswith(("const ", "let ", "var ")):
            findings.append((rel, f"line {cell_line + i - 1}: visible learner code line exceeds {VISIBLE_LINE_LIMIT} characters"))
    return findings



def audit_code_surface():
    """Find canvas-flow nodes whose code starts open despite being long enough to dominate the page.
    mountCanvasFlow opens short node code automatically; that is useful for small teaching
    steps but rough for plumbing-heavy visualization or orchestration blocks. Anything at or above
    CANVAS_LONG_DEFAULT_OPEN_LINES must choose deliberately: add showCode:false for plumbing, or
    shrink/split the code if students really need to read it inline."""
    findings = []
    pages = sorted((WEB / "nemoclaw").glob("0*.html"))
    for path in pages:
        text = path.read_text(errors="ignore")
        rel = str(path.relative_to(WEB.parent))
        mounts = list(CANVAS_MOUNT_RE.finditer(text))
        for i, mount in enumerate(mounts):
            if not text.startswith("mountCanvasFlow", mount.start()):
                continue
            start = mount.start()
            end = mounts[i + 1].start() if i + 1 < len(mounts) else len(text)
            block = text[start:end]
            label_m = re.search(r'label:\s*"([^"]+)"', block[:800])
            canvas = label_m.group(1) if label_m else "canvas"
            for m in CODE.finditer(block):
                code = m.group(1)
                lines = code.count("\n") + 1
                pre = block[max(0, m.start() - 700):m.start()]
                show_false = "showCode: false" in pre[-350:]
                show_true = "showCode: true" in pre[-350:]
                default_open = show_true or (lines <= CANVAS_DEFAULT_VISIBLE_MAX_LINES and not show_false)
                if not default_open or lines < CANVAS_LONG_DEFAULT_OPEN_LINES:
                    continue
                title_m = re.search(r'title:\s*"([^"]+)"', pre)
                id_m = re.search(r'id:\s*"([^"]+)"', pre)
                name = title_m.group(1) if title_m else (id_m.group(1) if id_m else "node")
                line_no = text[:start + m.start()].count("\n") + 1
                findings.append((rel, f"line {line_no}: default-open canvas node '{name}' has {lines} code lines in '{canvas}'; add showCode:false for plumbing-heavy code or split the node"))
    return findings



def audit_visible_code_hygiene():
    """Find hygiene problems in code that is visible by default. This intentionally does
    not force first-line comments or formatting churn across collapsed implementation cells."""
    findings = []
    pages = sorted((WEB / "nemoclaw").glob("0*.html"))
    for path in pages:
        text = path.read_text(errors="ignore")
        rel = str(path.relative_to(WEB.parent))
        mounts = list(CANVAS_MOUNT_RE.finditer(text))
        for i, mount in enumerate(mounts):
            start = mount.start()
            end = mounts[i + 1].start() if i + 1 < len(mounts) else len(text)
            block = text[start:end]
            is_canvas = text.startswith("mountCanvasFlow", start)
            for m in CODE.finditer(block):
                code = m.group(1)
                lines = code.count("\n") + 1
                if not _is_visible_cell(block, m.start(), lines, is_canvas):
                    continue
                cell_line = text[:start + m.start()].count("\n") + 1
                findings.extend(_visible_hygiene(rel, cell_line, code))

    return findings


def audit_duplicate_cell_keys():
    """Reject silent last-key-wins behavior in every canonical and localized runnable cell."""
    findings = []
    roots = [WEB / "nemoclaw", *sorted((TASK1 / "i18n").glob("*/web/nemoclaw"))]
    for root in roots:
        for path in sorted(root.glob("0*.html")):
            text = path.read_text(errors="ignore")
            rel = str(path.relative_to(TASK1))
            for cell in CODE.finditer(text):
                cell_line = text[:cell.start(1)].count("\n") + 1
                for key, local_line in duplicate_object_keys(cell.group(1)):
                    findings.append((rel, f"line {cell_line + local_line - 1}: duplicate object key "
                                          f"{key!r}; JavaScript silently discards the earlier value"))
    return findings


def audit_canvas_copy():
    """Keep learner-facing canvas chrome shorter than the implementation it introduces.

    Page headings already provide module coordinates, so repeating ``Module 2a Part 4`` in every
    canvas label is navigation scaffolding rather than teaching. Long intros and summaries are a
    second prose layer above code that is already available on demand; cap only extreme cases so
    useful conceptual guidance survives while implementation inventories move back into the code.
    """
    findings = []
    pages = sorted((WEB / "nemoclaw").glob("0*.html"))
    for path in pages:
        text = path.read_text(errors="ignore")
        rel = str(path.relative_to(WEB.parent))
        mounts = list(CANVAS_MOUNT_RE.finditer(text))
        for i, mount in enumerate(mounts):
            start = mount.start()
            end = mounts[i + 1].start() if i + 1 < len(mounts) else len(text)
            block = text[start:end]
            # Strings inside runnable code are program data, not CanvasFlow chrome.
            surface = CODE.sub("code: ``", block)
            for m in CANVAS_COPY_RE.finditer(surface):
                kind = m.group(1)
                value = re.sub(
                    r"\\n|\s+",
                    " ",
                    m.group(2) if m.group(2) is not None else m.group(3),
                ).strip()
                words = len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", value))
                reason = ""
                if kind == "label" and re.search(r"\bModule\s+\d+[a-c]?\s+Part\s+\d+", value, re.I):
                    reason = "repeats the page's module/part coordinate"
                elif kind == "label" and words > CANVAS_LABEL_WORD_LIMIT:
                    reason = f"label has {words} words (limit {CANVAS_LABEL_WORD_LIMIT})"
                elif kind == "title" and words > CANVAS_TITLE_WORD_LIMIT:
                    reason = f"node title has {words} words (limit {CANVAS_TITLE_WORD_LIMIT})"
                elif kind in ("intro", "summary") and words > CANVAS_COPY_WORD_LIMIT:
                    reason = f"{kind} has {words} words (limit {CANVAS_COPY_WORD_LIMIT})"
                if reason:
                    line_no = text[:start].count("\n") + surface[:m.start()].count("\n") + 1
                    findings.append((rel, f"line {line_no}: {reason}: {value[:120]}"))
    return findings


def run_cell_style_findings(code: str) -> list[str]:
    """Return objective clarity findings for one editable RunCell body.

    RunCells are the course's copy-and-edit surface. Infrastructure belongs behind a
    named helper; process logs may explain progress, but a structured return remains
    the outcome; and long waits must use the Stop-aware shared delay.
    """
    findings = []
    lines = [line for line in code.splitlines() if line.strip()]
    if len(lines) > RUN_CELL_LINE_LIMIT:
        findings.append(f"has {len(lines)} nonblank lines (limit {RUN_CELL_LINE_LIMIT}); move infrastructure behind a named helper")
    compressed = [line for line in lines if line.count(";") >= 3]
    if len(compressed) > RUN_CELL_COMPRESSED_LIMIT:
        findings.append(f"has {len(compressed)} compressed multi-statement lines (limit {RUN_CELL_COMPRESSED_LIMIT})")
    declarations = re.findall(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)", strip_noise(code))
    single_letter = sorted({name for name in declarations if len(name) == 1})
    if len(single_letter) > RUN_CELL_SINGLE_LETTER_LIMIT:
        findings.append("declares too many single-letter variables: " + ", ".join(single_letter))
    if RAW_SLEEP_RE.search(strip_noise(code)):
        findings.append("uses a raw awaited timer; use Stop-aware helpers.delay(ms)")
    if "new AbortController" in code and "browserChatFetch" in code and "helpers.signal.addEventListener" not in code:
        findings.append("owns a fetch AbortController without wiring the RunCell Stop signal")
    has_structured_return = bool(re.search(r"^return\s*\{", strip_noise(code), re.M))
    has_process_log = bool(re.search(r"(?<![\w.])(?:helpers\.)?log(?:\.|\s*\()", strip_noise(code)))
    if has_structured_return and has_process_log and not OPTIONAL_VISIBILITY_RE.search(code):
        findings.append("logs process output and returns a result but offers no commented optional visibility line")
    return findings


def prompt_experiment_code_findings(code: str) -> list[str]:
    """Require prompt cells to invite an edit and provide runnable alternatives."""
    assignments = list(PROMPT_ASSIGNMENT_RE.finditer(code))
    if not assignments:
        return []
    findings = []
    if PROMPT_BANNED_NARRATION.lower() in code.lower():
        findings.append("uses mechanical student-editable prompt/input narration")
    if not re.search(r"^\s*//\s*TODO:\s*\S", code, re.M):
        findings.append("does not address the learner with a TODO experiment prompt")
    for variable in sorted({match.group(1) for match in assignments}):
        alternatives = re.findall(rf"^\s*//\s*state\.{re.escape(variable)}\s*=", code, re.M)
        has_examples = bool(re.search(r"\bconst\s+EXAMPLES\s*=\s*\{", code))
        if not has_examples and len(alternatives) < 2:
            findings.append(
                f"state.{variable} offers {len(alternatives)} commented alternate assignment(s); provide two or an EXAMPLES selector"
            )
    return findings


def audit_prompt_experiments():
    """Audit the issue-scoped prompt cells in the canonical course and every published locale."""
    from translate.locale_pages import course_pages

    findings = []
    # Locales are discovered, and each locale page is the bytes the build publishes, whether they
    # come from a reviewed HTML overlay or a key-based resource.
    sources = {
        f"web/nemoclaw/{name}": (TASK1 / "web" / "nemoclaw" / name).read_text(errors="ignore")
        for name in PROMPT_PAGE_COUNTS
    }
    sources.update(course_pages(TASK1, "nemoclaw"))
    for rel, text in sorted(sources.items()):
        filename = rel.rsplit("/", 1)[-1]
        expected = PROMPT_PAGE_COUNTS.get(filename)
        if expected is None:
            continue
        if PROMPT_BANNED_NARRATION.lower() in text.lower():
            findings.append((rel, "mechanical student-editable prompt/input narration remains"))
        prompt_cells = []
        for match in CODE.finditer(text):
            code = match.group(1)
            if PROMPT_ASSIGNMENT_RE.search(code):
                prompt_cells.append(match)
                line_no = text[:match.start()].count("\n") + 1
                for message in prompt_experiment_code_findings(code):
                    findings.append((rel, f"line {line_no}: {message}"))
        if len(prompt_cells) != expected:
            findings.append((rel, f"found {len(prompt_cells)} prompt-input cells; expected {expected}"))
    return findings


def audit_run_cell_style():
    findings = []
    for path in sorted((WEB / "nemoclaw").glob("0*.html")):
        text = path.read_text(errors="ignore")
        rel = str(path.relative_to(WEB.parent))
        mounts = list(CANVAS_MOUNT_RE.finditer(text))
        for i, mount in enumerate(mounts):
            if not text.startswith("mountRunCell", mount.start()):
                continue
            start = mount.start()
            end = mounts[i + 1].start() if i + 1 < len(mounts) else len(text)
            block = text[start:end]
            code_match = CODE.search(block)
            if not code_match:
                continue
            label_match = re.search(r'label:\s*"([^"]+)"', block[:code_match.start()])
            label = label_match.group(1) if label_match else "unlabeled RunCell"
            line_no = text[:start + code_match.start()].count("\n") + 1
            for message in run_cell_style_findings(code_match.group(1)):
                findings.append((rel, f"line {line_no}: '{label}' {message}"))
    return findings


def run(verbose=True):
    """Driver: audit every numbered lesson page's runnable cells and aggregate the findings. It exists
    so the gate and a reviewer get one accounting of cells that violate the runnable-cell contract.
    Returns the finding lists; the report and exit code are derived from them."""
    pages = sorted((WEB / "nemoclaw").glob("0*.html"))   # the numbered lesson pages carry the runnable cells
    opaque, console, unawaited, dialog, key, static, unhi = [], [], [], [], [], [], []
    ui_contract = audit_runtime_contract()
    code_surface = audit_code_surface()

    readability = audit_visible_code_hygiene()
    duplicate_keys = audit_duplicate_cell_keys()
    copy_surface = audit_canvas_copy()
    run_cell_style = audit_run_cell_style()
    prompt_experiment = audit_prompt_experiments()

    for p in pages:
        o, c, u, d, k, st, uh = audit_page(p)  # per-page findings, by category
        opaque += o; console += c; unawaited += u; dialog += d; key += k; static += st; unhi += uh
    if verbose:
        def show(name, items, fmt):
            if items:
                print(f"[{name}] {len(items)}")
                for it in items:
                    print("   " + fmt(it))
        show("opaque cell · model call with no visible output", opaque, lambda it: f"{it[0]}  «…{it[1]}…»")
        show("console.* in cell (use helpers.log)", console, lambda it: f"{it[0]}  {it[1]}")
        show("un-awaited model call", unawaited, lambda it: f"{it[0]}  «{it[1]}…»")
        show("blocking dialog in cell", dialog, lambda it: f"{it[0]}  {it[1]}")
        show("inlined API key in cell", key, lambda it: f"{it[0]}  {it[1]}")
        show("cell-only code shown statically (not editable)", static, lambda it: f"{it[0]}  {it[1]}")
        show("editable cells without the syntax highlighter loaded", unhi, lambda it: f"{it[0]}  {it[1]}")
        show("learner-facing cell UI contract", ui_contract, lambda it: f"{it[0]}  {it[1]}")
        show("default-open canvas code surface", code_surface, lambda it: f"{it[0]}  {it[1]}")

        show("visible learner code hygiene", readability, lambda it: f"{it[0]}  {it[1]}")
        show("duplicate object keys in learner code", duplicate_keys, lambda it: f"{it[0]}  {it[1]}")
        show("learner-facing canvas copy", copy_surface, lambda it: f"{it[0]}  {it[1]}")
        show("student RunCell style", run_cell_style, lambda it: f"{it[0]}  {it[1]}")
        show("prompt experimentation", prompt_experiment, lambda it: f"{it[0]}  {it[1]}")

        total = (len(opaque) + len(console) + len(unawaited) + len(dialog) + len(key) + len(static)
                 + len(unhi) + len(ui_contract) + len(code_surface) + len(readability)
                 + len(duplicate_keys) + len(copy_surface) + len(run_cell_style) + len(prompt_experiment))
        print(f"\ncell_audit: {total} finding(s) (opaque {len(opaque)}, console {len(console)}, "
              f"unawaited {len(unawaited)}, dialog {len(dialog)}, inline-key {len(key)}, static {len(static)}, "

              f"unhighlighted {len(unhi)}, ui-contract {len(ui_contract)}, code-surface {len(code_surface)}, "
              f"readability {len(readability)}, duplicate-keys {len(duplicate_keys)}, "
              f"copy {len(copy_surface)}, run-cell-style {len(run_cell_style)}, "
              f"prompt-experiment {len(prompt_experiment)})")

    return {"opaque": opaque, "console": console, "unawaited": unawaited,
            "dialog": dialog, "inline_key": key, "static_cell_code": static,
            "unhighlighted": unhi, "ui_contract": ui_contract,
            "code_surface": code_surface, "readability": readability, "duplicate_keys": duplicate_keys,
            "copy_surface": copy_surface, "run_cell_style": run_cell_style,
            "prompt_experiment": prompt_experiment}


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        fixtures = (
            ("same-origin copies", '<script src="vendor/codemirror-5.65.21.js"></script><script src="vendor/codemirror-mode-javascript-5.65.21.js"></script><link href="vendor/codemirror-5.65.21.css">', []),
            ("parent-path copies", '<script src="../vendor/codemirror-5.65.21.js"></script><script src="../vendor/codemirror-mode-javascript-5.65.21.js"></script><link href="../vendor/codemirror-5.65.21.css">', []),
            ("split distribution", '<script src="codemirror.min.js"></script><script src="mode/javascript/javascript.min.js"></script><link href="codemirror.min.css">', []),
            ("missing JavaScript", '<link href="vendor/codemirror-5.65.21.css">', ["CodeMirror core js", "javascript mode"]),
            ("missing CSS", '<script src="vendor/codemirror-5.65.21.js"></script><script src="vendor/codemirror-mode-javascript-5.65.21.js"></script>', ["editor css"]),
        )
        failures = [(name, highlighter_missing(source), expected) for name, source, expected in fixtures
                    if highlighter_missing(source) != expected]
        good_style = '''const response = await helpers.browserChatFetch()(url, { signal: helpers.signal });
helpers.log("request complete");
// helpers.log.json("raw response", response);
return { ok: response.ok };'''
        bad_style = '''const a = 1;
const b = 2;
const c = 3;
const d = 4;
const e = 5;
const f = 6;
const controller = new AbortController();
await new Promise(resolve => setTimeout(resolve, 1000));
await helpers.browserChatFetch()(url, { signal: controller.signal });
helpers.log("request complete");
return { ok: true };'''
        if run_cell_style_findings(good_style):
            failures.append(("clear RunCell style", run_cell_style_findings(good_style), []))
        bad_findings = run_cell_style_findings(bad_style)
        expected_style = ("single-letter", "raw awaited timer", "without wiring", "no commented optional visibility")
        missing_style = [token for token in expected_style if not any(token in item for item in bad_findings)]
        if missing_style:
            failures.append(("adversarial RunCell style", bad_findings, list(expected_style)))
        too_large = "\n".join(f"const value{i} = {i};" for i in range(RUN_CELL_LINE_LIMIT + 1))
        if not any("nonblank lines" in item for item in run_cell_style_findings(too_large)):
            failures.append(("oversized RunCell style", run_cell_style_findings(too_large), ["nonblank lines"]))
        good_prompt = '''// TODO: Try another question or write your own.
state.question = "What is an AI agent?";
// state.question = "When should an agent call a tool?";
// state.question = "How does agent memory work?";
return state.question;'''
        good_examples = '''// TODO: Choose an example or write your own.
const EXAMPLES = { default: "What is RAG?", alternate: "What is ReAct?" };
state.question = EXAMPLES.default;
return state.question;'''
        if prompt_experiment_code_findings(good_prompt) or prompt_experiment_code_findings(good_examples):
            failures.append(("valid prompt experiments", prompt_experiment_code_findings(good_prompt), []))
        banned_prompt = good_prompt.replace(
            "// TODO: Try another question or write your own.",
            "// Set the student-editable prompt/input for the next step.",
        )
        if not any("mechanical" in item for item in prompt_experiment_code_findings(banned_prompt)):
            failures.append(("banned prompt narration", prompt_experiment_code_findings(banned_prompt), ["mechanical"]))
        missing_alternates = '''// TODO: Try another question or write your own.
state.question = "What is an AI agent?";
return state.question;'''
        if not any("alternate assignment" in item for item in prompt_experiment_code_findings(missing_alternates)):
            failures.append(("missing prompt alternatives", prompt_experiment_code_findings(missing_alternates), ["alternate assignment"]))
        if failures:
            print("cell_audit self-test: FAIL")
            for name, actual, expected in failures:
                print(f"  FAIL {name}: got {actual}, expected {expected}")
            sys.exit(1)
        print("cell_audit self-test: PASS")
        sys.exit(0)
    r = run()
    sys.exit(1 if sum(len(v) for v in r.values()) else 0)
