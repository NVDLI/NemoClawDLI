#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Thin python interface to the SINGLE link engine (scripts/runtime/engine.js).

The graph engine (link resolution, crawl, nodes/edges, reachability, the foyer contract)
lives in scripts/runtime/engine.js and runs in BOTH the browser viewer and headless via node
(scripts/runtime/run_engine.sh uses host Node). There is no second Python graph engine to drift from.

This module keeps only:
  * the pure CRAWL / CLASSIFICATION helpers that grounding.py reuses (course_of, _iter_pages,
    _read_for_links, _strip_noncontent, ship_relevant, the link regexes, _clamp), and
  * THIN SHIMS (check / reachability / graph_json / foyer_release_check / embed_snapshot)
    that invoke engine.js and return its JSON, so the cadence validators read the same numbers
    the viewer and CI do.

Run the engine directly with `python3 scripts/runtime/link_projection.py --self-test` (it forwards to
run_engine.sh) or, equivalently, `bash scripts/runtime/run_engine.sh --self-test`.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from html_document import without_elements

HERE = Path(__file__).resolve()


def _find_task1(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "AGENTS.md").is_file():
            return p
    return start.parents[1]


TASK1 = _find_task1(HERE)

PAGE_EXT = (".md", ".ipynb", ".html", ".htm")
ASSET_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".css", ".js",
             ".mjs", ".woff", ".woff2", ".ttf", ".mp4", ".webm", ".json", ".pdf")
SKIP_DIR = {"__pycache__", ".ipynb_checkpoints", "node_modules", "export", "standalone",
            "_paper_cache", "repos_index", "docstore_index", "artifacts", ".pytest_cache",
            "skills-seed", "generated_images", "sample_videos", "_offloaded_tracks",
            ".git", ".cache", "dist", "build", "venv", ".venv", "composer", "validation",
            "i18n"}   # i18n/<lang>/ is staged translation content (a copy of web/), not source to crawl

# Release contract mirrored from engine.js for Python callers.
RELEASED = ("nemoclaw",)
PREVIEWS = ()

# mats are course-scoped reference packets; match engine.js segment detection.
MAT_REL = "web/nemoclaw/mats"


def is_mat_path(rel: str) -> bool:
    return "mats" in rel.replace("\\", "/").split("/")


SHIP_PREFIXES = ("web/nemoclaw/", "web/index", "web/courses",
                 "docs/", "scripts/")
SHIP_HUBS = {"SKILL.html", "web/SKILL.html"}

# mats now live UNDER web/ (already a crawl root that recurses), so "mats" is no longer a separate top-level crawl root or shared TOPDIR.
# It is still shared infra, detected by path segment.
SHARED_SUBDIRS = {"mats", "repos"}
SHARED_TOPDIRS = {"repos", "scripts", "docs"}
CRAWL_TOP = ("web", "docs", "scripts")

_TEMPLATE_MARK = ("{{", "}}", "<?", "?>", "<%", "%>", "${", "&lt;", "&gt;", "&#")


def _junk_file(fn: str) -> bool:
    return fn.startswith("._") or fn.endswith(".nbconvert.ipynb") or "-checkpoint." in fn


def _is_template_link(t: str) -> bool:
    return any(m in t for m in _TEMPLATE_MARK)


def ship_relevant(rel: str) -> bool:
    rel = rel.replace("\\", "/")
    base = rel.rsplit("/", 1)[-1].lower()
    if base.startswith(("example", "template", "sample")):
        return False
    if "/" not in rel:
        return True
    if rel in SHIP_HUBS:
        return True
    return any(rel.startswith(p) for p in SHIP_PREFIXES)


def course_of(p: str) -> str:
    """Classify a repo-relative path to a course id, or '_shared'. Mirrors engine.js courseOf."""
    parts = [x for x in p.split("/") if x]
    if len(parts) < 2:
        return "_shared"
    if parts[-1] == "SKILL.html" and len(parts) <= 2:
        return "_shared"
    if parts[0] == "docs":
        return "_shared"
    # Mats are shared references, even when stored under a course path.
    if is_mat_path(p):
        return "_shared"
    if parts[0] == "web":
        if parts[1] in SHARED_SUBDIRS:
            return "_shared"
        if len(parts) == 2 and "." in parts[1]:
            return "_shared"
        return parts[1]
    if parts[0] in SHARED_TOPDIRS:
        return "_shared"
    return parts[0]


# ── crawl helpers (link surfaces), shared with grounding.py ───────────────────
_HREF = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', re.I)
_MDL = re.compile(r'!?\[[^\]]*\]\(\s*<?([^)\s>]+)')
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]*`")


def _strip_noncontent(text: str, suffix: str) -> str:
    if suffix in (".html", ".htm"):
        text = without_elements(text, {"script", "style"})
        text = _HTML_COMMENT.sub(" ", text)
    else:
        text = _FENCE.sub(" ", text)
        text = _INLINE_CODE.sub(" ", text)
    return text


def _iter_pages(task1: Path):
    roots = [task1 / d for d in CRAWL_TOP] + [task1]
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        if root == task1:
            for f in sorted(root.glob("*")):
                if f.is_file() and not _junk_file(f.name) and f.suffix.lower() in PAGE_EXT and f not in seen:
                    seen.add(f)
                    yield f
            continue
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if d not in SKIP_DIR]
            for fn in sorted(fns):
                if _junk_file(fn):
                    continue
                if Path(fn).suffix.lower() in PAGE_EXT:
                    f = Path(dp) / fn
                    if f not in seen:
                        seen.add(f)
                        yield f


@lru_cache(maxsize=2048)
def _read_snapshot(path: str, modified_ns: int, size: int) -> str:
    """Read one immutable file snapshot; stat identity prevents stale in-process reuse."""
    del modified_ns, size
    return Path(path).read_text(errors="ignore")


def _read_for_links(f: Path):
    """(text, effective_suffix). Notebooks contribute MARKDOWN cell sources only."""
    stat = f.stat()
    raw = _read_snapshot(str(f), stat.st_mtime_ns, stat.st_size)
    if f.suffix.lower() == ".ipynb":
        try:
            nb = json.loads(raw)
        except Exception:
            return "", ".md"
        md = []
        for c in nb.get("cells", []):
            if c.get("cell_type") == "markdown":
                s = c.get("source", "")
                md.append("".join(s) if isinstance(s, list) else (s or ""))
        return "\n\n".join(md), ".md"
    return raw, f.suffix.lower()


def _clamp(base_dir: str, tgt: str) -> str:
    parts = [x for x in base_dir.split("/") if x]
    for seg in tgt.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


class Projection:
    """Slim handle: grounding.py uses only `.host_root`. The graph engine is engine.js."""

    def __init__(self, task1: Path = TASK1):
        self.task1 = task1
        self.host_root = task1


# ── engine shims (the single graph engine lives in engine.js) ─────────────────
_RUN_ENGINE = HERE.parent / "run_engine.sh"


def _engine(*args: str) -> str:
    """Invoke engine.js via run_engine.sh and return stdout. Raises on failure (a graph gate
    that cannot run is an error, never a silent pass)."""
    p = subprocess.run(["bash", str(_RUN_ENGINE), *args],
                       capture_output=True, text=True)
    if p.returncode not in (0, 1) or (p.returncode == 1 and not p.stdout.strip()):
        # 0 ok, 1 = blocking issues only when the engine still emitted its JSON report.
        # Empty stdout with return code 1 means the host engine failed before producing a report.
        raise RuntimeError(f"engine.js failed ({p.returncode}): {p.stderr.strip() or p.stdout.strip()}")
    return p.stdout


def _engine_json(*args: str) -> dict:
    out = _engine(*args)
    line = out.strip().splitlines()[-1] if out.strip() else "{}"
    try:
        return json.loads(line)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"engine.js returned non-JSON output for {' '.join(args)}: {line[:240]}") from e


def check(proj: Projection | None = None) -> dict:
    return _engine_json("--check-json")


def reachability(proj: Projection | None = None) -> dict:
    return _engine_json("--reach")


def graph_json(proj: Projection | None = None) -> dict:
    return _engine_json("--graph-json")


def foyer_release_check(proj: Projection | None = None) -> dict:
    return _engine_json("--foyer-json")


def page_audit(proj: Projection | None = None) -> dict:
    """Per-.html drift audit (stale tokens, missing assets, skill-meta / foyer-release contract
    drift) from engine.js, so every page auto-verifies through the one engine."""
    return _engine_json("--audit-json")


def bundle_snapshot(proj: Projection | None = None, *, include_graph: bool = False) -> dict:
    """Return the related link projections from one engine process and filesystem snapshot."""
    flag = "--bundle-graph-json" if include_graph else "--bundle-json"
    data = _engine_json(flag)
    if data.get("schema") != "link-engine-bundle/1":
        raise RuntimeError("engine.js returned an unsupported bundle snapshot")
    return data


def embed_graph_snapshot(graph: dict) -> bool:
    """Embed graph data already produced by engine.js without launching it again."""
    html_path = TASK1 / "scripts" / "runtime" / "link_graph.html"
    lines = html_path.read_text(encoding="utf-8").splitlines()
    replacement = "let DATA = " + json.dumps(graph, separators=(",", ":")) + ";"
    for index, line in enumerate(lines):
        marker = re.match(r"^(\s*)let DATA = ", line)
        if marker:
            lines[index] = marker.group(1) + replacement
            html_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return True
    return False


def embed_snapshot(proj: Projection | None = None) -> bool:
    _engine("--embed")
    return True


def main():
    # Forward everything to the JS engine through the host Node runner.
    args = sys.argv[1:] or ["--self-test"]
    return subprocess.run(["bash", str(_RUN_ENGINE), *args]).returncode


if __name__ == "__main__":
    sys.exit(main())
