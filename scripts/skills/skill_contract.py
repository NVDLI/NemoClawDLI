#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SKILL-contract conformance: is every skill-meta a VALID beacon, not just an accurate one?

The link engine proves SKILL paths resolve; skill_audit proves a beacon matches its
directory (drift); skill_consistency proves duplicated facts agree across files. None of
them check the one thing the SKILL contract is actually about: that each
`<script id="skill-meta">` block is a well-formed contract of its kind. This is that leg.

Two readers, one file, so three checks:

  SCHEMA  Every skill-meta classifies into exactly one kind and carries that kind's
          required keys, a known schema/node_type value, a semver version where the kind
          uses one, and only valid notebook status values. An unclassifiable or
          key-missing meta is a beacon an agent cannot trust. (the gap the other tools left)
  DRIFT   The beacon matches its directory: source_dir / human_landing point at the real
          location, the notebook list is complete, hub children exist. Reused wholesale
          from skill_audit (its detector is the source of truth; --fix delegates to it).

          Exhaustive discovery is part of this leg. Every tracked or proposed source
          directory and ancestor must contain SKILL.html. There is no exemption mechanism.

  GRAPH   Every discovered beacon is reachable from root SKILL.html through a visible link
          or an explorer link. A present but disconnected beacon is still unusable.

  SOURCE  SKILL.html source stays reviewable and durable: static card/command grids are not
          minified into one-line walls, and beacons do not expose numbered issue/MR/PR threads
          or user handles as course-facing provenance.

  RENDER  The human half has meaningful visible content, local links and renderer resources resolve,
          explorer-config mounts the declared shared renderer exactly once, and every configured
          source file exists. Playwright supplies the separate runtime rendering proof.

The KINDS table below is the contract implemented by the shipped tree and documented in
SKILL_CONTRACT.md. A new kind becomes valid only when its first beacon, implementation,
documentation, and mutation coverage arrive together.

Usage:
  python3 scripts/skills/skill_contract.py            # schema + coverage/drift + renderer
  python3 scripts/skills/skill_contract.py --json     # machine-readable finding groups
  python3 scripts/skills/skill_contract.py --fix      # mechanical drift fixes (delegated to skill_audit)
"""
from __future__ import annotations
import argparse, json, re, shlex, sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import skill_audit as sa  # drift detector + --fix engine + skills()/parse_meta(); single source of truth

TASK1 = sa.TASK1
sys.path.insert(0, str(TASK1))
from scripts.validation import interface_inventory_audit
_SEMVER = re.compile(r"^\d+\.\d+\.\d+([.\-+].*)?$")
_STATUS = {"ready", "setup", "wip", "ref"}
_PROCESS_REF = re.compile(r"(?:GitLab\s+issue\s*#?\d+|\bissue\s*#\d+|\bMR\s*!?\d+|\bPR\s*#?\d+|merge request\s*!?\d+|pull request\s*#?\d+|@(?!media\b|supports\b|keyframes\b|font-face\b|import\b)(?![A-Za-z0-9_.-]+__)[A-Za-z0-9_][A-Za-z0-9_.-]*)", re.I)

# Contract matrix: classify by schema/node_type and require stable beacon keys.
KINDS = {
    "service-skill/1.0":   {"req": ["schema", "service", "address", "source_dir", "summary",
                                    "interfaces", "tests", "title", "version"], "label_any": []},
    "service-index/1.0":   {"req": ["schema", "id", "source_dir", "summary", "services",
                                    "tests", "title", "version"], "label_any": []},
    "dir-skill/1.0":       {"req": ["schema", "node_type", "source_dir", "summary", "title",
                                    "explorer"], "label_any": []},
    "node:hub":            {"req": ["node_type", "children"], "label_any": ["title", "course"]},
    "node:leaf":           {"req": ["node_type", "source_dir", "summary", "self_path"],
                            "label_any": ["title", "course"]},
}
SCHEMA_VALUES = set(KINDS) - {"node:hub", "node:leaf"}
NODE_TYPES = {"hub", "leaf", "directory-explorer"}
VERSIONED = {"service-skill/1.0", "service-index/1.0"}


def classify(meta: dict):
    """Which contract kind is this? schema wins, then node_type. None = unclassifiable."""
    if meta.get("schema"):
        return meta["schema"]
    if meta.get("node_type"):
        return "node:" + meta["node_type"]
    return None


def schema_findings():
    """One pass over every SKILL.html: classify, then check required keys, enums, semver, status."""
    out = []
    for sk in sa.skills():
        rel = str(sk.relative_to(TASK1))
        meta, _ = sa.parse_meta(sk.read_text())
        if meta is None:
            out.append((rel, "no skill-meta JSON block")); continue
        if meta == "ERR":
            out.append((rel, "skill-meta JSON does not parse")); continue

        # schema / node_type values must be known before we trust the classification.
        if meta.get("schema") and meta["schema"] not in SCHEMA_VALUES:
            out.append((rel, f"unknown schema value {meta['schema']!r}"))
        if meta.get("node_type") and meta["node_type"] not in NODE_TYPES:
            out.append((rel, f"unknown node_type {meta['node_type']!r}"))

        kind = classify(meta)
        spec = KINDS.get(kind)
        if spec is None:
            out.append((rel, f"unclassifiable skill-meta (no known schema or node_type): keys {sorted(meta)}"))
            continue

        missing = [k for k in spec["req"] if k not in meta]
        if missing:
            out.append((rel, f"[{kind}] missing required key(s): {missing}"))
        if spec["label_any"] and not any(k in meta for k in spec["label_any"]):
            out.append((rel, f"[{kind}] needs a human label: one of {spec['label_any']}"))

        if kind in VERSIONED and "version" in meta and not _SEMVER.match(str(meta["version"])):
            out.append((rel, f"version {meta['version']!r} is not semver (MAJOR.MINOR.PATCH)"))

        for nb in (meta.get("notebooks") or []):
            st = nb.get("status") if isinstance(nb, dict) else None
            if st is not None and st not in _STATUS:
                out.append((rel, f"notebook {nb.get('file')!r} has invalid status {st!r} (want {sorted(_STATUS)})"))
    return out


def source_quality_findings():
    """Source-level quality checks for SKILL.html files.

    These catch failures the JSON schema cannot see: unreadable static HTML walls and
    process/provenance references that should not leak into durable course beacons.
    """
    out = []
    for sk in sa.skills():
        rel = str(sk.relative_to(TASK1))
        text = sk.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            card_count = line.count('class="skill-card"')
            cmd_count = line.count('class="skill-cmd"')
            if len(line) > 320 and card_count + cmd_count >= 3:
                out.append((rel, f"source-quality line {lineno}: static grid/list packs {card_count + cmd_count} cards or commands onto one line"))
            if _PROCESS_REF.search(line):
                out.append((rel, f"source-quality line {lineno}: numbered issue/MR/PR or user-handle provenance does not belong in SKILL.html"))
    return out


class _RendererParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.resources: list[tuple[str, str]] = []
        self.has_main = False
        self.has_section = False
        self.has_skill_header = False
        self._skill_header_depth = 0
        self._skill_nav_depth = 0
        self.skill_header_links: list[str] = []
        self.links: list[str] = []
        self._hidden = 0
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        if values.get("id"):
            self.ids.add(values["id"])
        self.has_main = self.has_main or tag == "main"
        self.has_section = self.has_section or tag == "section"
        if tag == "header" and values.get("data-skill-header") == "1":
            self.has_skill_header = True
            self._skill_header_depth = 1
        elif self._skill_header_depth:
            self._skill_header_depth += 1
        if self._skill_header_depth and tag == "nav":
            self._skill_nav_depth = 1
        elif self._skill_nav_depth:
            self._skill_nav_depth += 1
        if self._skill_nav_depth and tag == "a" and values.get("href"):
            self.skill_header_links.append(values["href"])
        if tag == "a" and values.get("href"):
            self.links.append(values["href"])
        if tag in {"script", "style"}:
            self._hidden += 1
        if tag == "script" and values.get("src"):
            self.resources.append(("script", values["src"]))
        elif tag == "link" and "stylesheet" in values.get("rel", "").lower() and values.get("href"):
            self.resources.append(("stylesheet", values["href"]))
        elif tag in {"img", "source"} and values.get("src"):
            self.resources.append((tag, values["src"]))

    def handle_endtag(self, tag: str) -> None:
        if self._skill_nav_depth:
            self._skill_nav_depth -= 1
        if self._skill_header_depth:
            self._skill_header_depth -= 1
        if tag in {"script", "style"} and self._hidden:
            self._hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden and data.strip():
            self.text.append(data.strip())


def _local_target(skill: Path, reference: str, root: Path) -> Path | None:
    parsed = urlsplit(reference)
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("data:"):
        return None
    path = unquote(parsed.path)
    if path.startswith("/lab/static/"):
        return root / path.removeprefix("/lab/static/")
    if path.startswith("/"):
        return root / path.lstrip("/")
    return (skill.parent / path).resolve()


def _config_paths(config: dict) -> list[str]:
    paths: list[str] = []
    for item in config.get("files", []) or []:
        if isinstance(item, dict) and item.get("path"):
            paths.append(item["path"])
    for group in config.get("groups", []) or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("files", []) or []:
            if isinstance(item, dict) and item.get("path"):
                paths.append(item["path"])
    if config.get("readme"):
        paths.append(config["readme"])
    for group in config.get("links", []) or []:
        if not isinstance(group, dict):
            continue
        for item in group.get("items", []) or []:
            if isinstance(item, dict) and item.get("href"):
                paths.append(item["href"])
    return paths


def _skill_references(value: object) -> list[str]:
    """Collect local SKILL.html references from machine-readable metadata."""
    if isinstance(value, str):
        return [value] if urlsplit(value).path.endswith("SKILL.html") else []
    if isinstance(value, list):
        return [item for child in value for item in _skill_references(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in _skill_references(child)]
    return []


def skill_graph_findings(root: Path, skill_paths: list[Path] | None = None) -> list[tuple[str, str]]:
    """Require every beacon to be reachable from the root through declared or visible links."""
    root = root.resolve()
    paths = sorted((skill_paths or list(root.rglob("SKILL.html"))))
    skills = {path.resolve() for path in paths}
    root_skill = (root / "SKILL.html").resolve()
    if root_skill not in skills:
        return [("SKILL.html", "root beacon is missing from the discovered SKILL graph")]
    edges: dict[Path, set[Path]] = {path: set() for path in skills}
    for skill in skills:
        text = skill.read_text(encoding="utf-8", errors="replace")
        parser = _RendererParser()
        try:
            parser.feed(text)
        except Exception:
            continue
        config_match = re.search(
            r'<script type="application/json" id="explorer-config">(.*?)</script>', text, re.S
        )
        try:
            config = json.loads(config_match.group(1)) if config_match else {}
        except Exception:
            config = {}
        references = parser.links + _skill_references(config)
        for reference in references:
            target = _local_target(skill, reference, root)
            if target is not None and target.resolve() in skills:
                edges[skill].add(target.resolve())
    reached = {root_skill}
    pending = [root_skill]
    while pending:
        current = pending.pop()
        for target in edges[current] - reached:
            reached.add(target)
            pending.append(target)
    return [
        (str(path.relative_to(root)), "beacon is disconnected from the root SKILL graph")
        for path in sorted(skills - reached)
    ]


def renderer_findings_for(skill: Path, root: Path) -> list[str]:
    text = skill.read_text(encoding="utf-8", errors="replace")
    parser = _RendererParser()
    try:
        parser.feed(text)
    except Exception as exc:
        return [f"HTML parser failed: {exc}"]
    findings: list[str] = []
    meta, _ = sa.parse_meta(text)
    config_match = re.search(
        r'<script type="application/json" id="explorer-config">(.*?)</script>', text, re.S
    )
    config = None
    if config_match:
        try:
            config = json.loads(config_match.group(1))
        except Exception as exc:
            findings.append(f"explorer-config JSON does not parse: {exc}")

    for kind, reference in parser.resources:
        target = _local_target(skill, reference, root)
        if kind == "script" and reference.startswith("/"):
            findings.append(f"renderer script uses root-absolute URL {reference!r}; use a directory-relative source URL")
        if target is not None:
            try:
                target.relative_to(root.resolve())
            except ValueError:
                findings.append(f"{kind} resource escapes the repository: {reference!r}")
                continue
            if not target.is_file():
                findings.append(f"{kind} resource is missing: {reference!r}")

    for reference in parser.links:
        target = _local_target(skill, reference, root)
        if target is None:
            continue
        try:
            target.relative_to(root.resolve())
        except ValueError:
            findings.append(f"link escapes the repository: {reference!r}")
            continue
        if not target.exists():
            findings.append(f"local link target is missing: {reference!r}")

    visible = " ".join(parser.text).strip()
    if len(visible) < 20:
        findings.append("human renderer has no meaningful visible text")
    if not parser.has_skill_header:
        findings.append("missing semantic skill navigation header")
    elif len(set(parser.skill_header_links)) < 2:
        findings.append("skill navigation header needs at least two distinct links")

    explorer_scripts = [
        reference for kind, reference in parser.resources
        if kind == "script" and "_skill_explorer.js" in reference
    ]
    if len(explorer_scripts) != 1:
        findings.append(
            "every SKILL page requires exactly one shared _skill_explorer.js shell; "
            f"found {len(explorer_scripts)}"
        )

    if isinstance(meta, dict):
        exports = meta.get("exports", [])
        if exports and not isinstance(exports, list):
            findings.append("skill-meta.exports must be a list")
            exports = []
        for number, export in enumerate(exports, 1):
            if not isinstance(export, dict):
                findings.append(f"export {number} must be an object")
                continue
            missing = [key for key in ("id", "label", "format", "preview_mount", "command", "parameters") if not export.get(key)]
            if missing:
                findings.append(f"export {number} is missing required key(s): {missing}")
            mount = export.get("preview_mount")
            if mount and mount not in parser.ids:
                findings.append(f"export {export.get('id', number)!r} preview mount #{mount} is missing")
            categories = export.get("categories")
            default_category = export.get("default_category")
            if categories is not None and not isinstance(categories, dict):
                findings.append(f"export {export.get('id', number)!r} categories must be an object")
            elif default_category and default_category not in (categories or {}):
                findings.append(f"export {export.get('id', number)!r} default category {default_category!r} is not declared")
            try:
                tokens = shlex.split(str(export.get("command", "")))
            except ValueError as exc:
                findings.append(f"export {export.get('id', number)!r} command does not parse: {exc}")
                tokens = []
            scripts = [token for token in tokens if token.endswith((".py", ".js", ".mjs", ".sh"))]
            if scripts and not (root / scripts[0]).is_file():
                findings.append(f"export {export.get('id', number)!r} command target is missing: {scripts[0]!r}")
    if config is not None:
        if "explorer" not in parser.ids:
            findings.append("explorer-config has no #explorer mount")
        if isinstance(meta, dict) and meta.get("schema") == "dir-skill/1.0":
            declared = meta.get("explorer")
            if not declared:
                findings.append("dir-skill renderer does not declare skill-meta.explorer")
            elif not explorer_scripts:
                findings.append("declared explorer is not loaded by the page")
            else:
                declared_target = _local_target(skill, declared, root)
                loaded_target = _local_target(skill, explorer_scripts[0], root)
                if declared_target != loaded_target:
                    findings.append(
                        f"skill-meta.explorer {declared!r} does not match loaded renderer {explorer_scripts[0]!r}"
                    )
        for reference in _config_paths(config):
            target = _local_target(skill, reference, root)
            if target is not None and not target.is_file():
                findings.append(f"explorer-config file is missing: {reference!r}")
    elif not (parser.has_main or parser.has_section):
        findings.append("custom renderer needs a semantic <main> or <section> human view")
    return findings


def renderer_findings() -> list[tuple[str, str]]:
    out = []
    for skill in sa.skills():
        rel = str(skill.relative_to(TASK1))
        out.extend((rel, detail) for detail in renderer_findings_for(skill, TASK1))
    return out


def run(verbose: bool = False) -> dict:
    """Gate entrypoint. Return schema, exhaustive coverage/drift, and renderer findings."""
    interface_findings, _ = interface_inventory_audit.audit(TASK1)
    return {
        "schema": schema_findings() + source_quality_findings(),
        "drift": sa.audit(fix=False),
        "graph": skill_graph_findings(TASK1, list(sa.skills())),
        "interfaces": [(item.split(": ", 1)[0], item.split(": ", 1)[-1]) for item in interface_findings],
        "renderer": renderer_findings(),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    ap.add_argument("--fix", action="store_true", help="apply mechanical drift fixes (delegated to skill_audit)")
    a = ap.parse_args()

    if a.fix:
        sa.audit(fix=True)   # drift is the only mechanically-fixable leg; schema needs a human

    res = run()
    if a.json:
        print(json.dumps({k: [{"page": p, "detail": d} for p, d in v] for k, v in res.items()}, indent=2))
        return 1 if any(res.values()) else 0

    if not any(res.values()):
        print("skill_contract: ✅ every source directory has a valid, accurate, renderable SKILL.html")
        return 0
    for label, items, stream in (
        ("schema", res["schema"], sys.stderr),
        ("drift", res["drift"], sys.stderr),
        ("graph", res["graph"], sys.stderr),
        ("interfaces", res["interfaces"], sys.stderr),
        ("renderer", res["renderer"], sys.stderr),
    ):
        if items:
            print(f"skill_contract: ✗ {len(items)} {label} finding(s):", file=stream)
            for p, d in items:
                print(f"  {p}: {d}", file=stream)
    return 1


if __name__ == "__main__":
    sys.exit(main())
