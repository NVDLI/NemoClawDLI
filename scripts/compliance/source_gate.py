#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Release-source, legal-file, and vendor-ingestion gate.

This is a deterministic pre-review check. It does not replace legal review; it blocks
known bad states before review: incomplete Apache/DCO/notices contracts, missing authored-source
headers, unclassified vendor transformations, private URLs, and missing provenance.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root  # noqa: E402

try:
    from . import source_license_contract
except ImportError:
    import source_license_contract

ROOT = find_repo_root(Path(__file__).resolve())
INVENTORY = ROOT / "scripts" / "compliance" / "docs" / "source_inventory.json"
TEXT_SUFFIXES = {
    ".css", ".csv", ".html", ".js", ".json", ".md", ".mjs", ".py", ".sh",
    ".svg", ".toml", ".txt", ".xml", ".yaml", ".yml",
}
SKIP_PARTS = {
    ".git", "__pycache__", "node_modules", "public", "export", "dist", "build",
    ".cache", "grounding_cache", ".figtools",
}
GOVERNED_SUFFIXES = {
    ".md", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".json", ".txt",
}


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def load_inventory() -> dict:
    if not INVENTORY.is_file():
        raise SystemExit("missing scripts/compliance/docs/source_inventory.json")
    return json.loads(INVENTORY.read_text(encoding="utf-8-sig"))


def tracked_files() -> list[Path]:
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    others = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                            cwd=ROOT, capture_output=True, text=True, check=True).stdout
    files = []
    seen = set()
    for line in (tracked + "\n" + others).splitlines():
        if not line or line in seen:
            continue
        seen.add(line)
        p = ROOT / line
        if not p.exists():
            continue
        if any(part in SKIP_PARTS for part in p.parts):
            continue
        files.append(p)
    return files


def is_text_file(p: Path) -> bool:
    return p.suffix.lower() in TEXT_SUFFIXES


def extract_json_script(path: Path, script_id: str) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    pat = re.compile(r'<script[^>]+id=["\']' + re.escape(script_id) + r'["\'][^>]*>(.*?)</script>', re.S)
    m = pat.search(text)
    if not m:
        return {}
    return json.loads(m.group(1))


def inventory_paths(inv: dict) -> set[str]:
    out = set()
    for item in inv.get("inventory_entries", []):
        p = item.get("path")
        if p:
            out.add(p.rstrip("/"))
    for p in inv.get("policy_docs", []):
        out.add(p.rstrip("/"))
    return out


def load_provenance_files(inv: dict) -> set[str]:
    out = set()
    for beacon in inv.get("provenance_beacons", []):
        root = beacon.get("root", "").rstrip("/")
        path = ROOT / beacon.get("beacon", "")
        if not path.is_file():
            continue
        data = extract_json_script(path, "provenance")
        for arr in beacon.get("arrays", []):
            for row in data.get(arr, []) or []:
                file_name = row.get("file")
                if file_name:
                    out.add(f"{root}/{file_name}".rstrip("/"))
    return out


def covered(path: str, covered_paths: set[str]) -> bool:
    path = path.rstrip("/")
    for c in covered_paths:
        c = c.rstrip("/")
        if path == c or path.startswith(c + "/"):
            return True
        if any(ch in c for ch in "*?[") and fnmatch.fnmatch(path, c):
            return True
    return False


def check_contribution_terms(fails: list[str], oks: list[str]) -> None:
    path = ROOT / "CONTRIBUTING.md"
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    if "Apache-2.0" in text and "Not a Contribution" in text:
        oks.append("contribution terms: inbound Apache-2.0 language present")
    else:
        fails.append("contribution terms: CONTRIBUTING.md must state inbound Apache-2.0 and Not a Contribution handling")


def check_private_links(inv: dict, files: list[Path], fails: list[str], oks: list[str]) -> None:
    regexes = [(row.get("name", "private link"), re.compile(row["pattern"]))
               for row in inv.get("forbidden_private_link_regexes", [])]
    hits = []
    for p in files:
        if p == INVENTORY or not p.is_file() or not is_text_file(p):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        for name, rx in regexes:
            m = rx.search(text)
            if m:
                line = text[:m.start()].count("\n") + 1
                hits.append(f"{rel(p)}:{line}: {name}")
    if hits:
        fails.extend(f"private link: {h}" for h in hits)
    else:
        oks.append("private links: no forbidden internal URL patterns in tracked text")


def check_inventory(inv: dict, fails: list[str], oks: list[str]) -> None:
    before = len(fails)
    for item in inv.get("inventory_entries", []):
        p = ROOT / item.get("path", "")
        if not p.exists():
            fails.append(f"inventory entry missing path: {item.get('path')}")
    if len(fails) == before:
        oks.append(f"source inventory: {len(inv.get('inventory_entries', []))} entries resolve")


def check_governed_material(inv: dict, files: list[Path], fails: list[str], oks: list[str]) -> None:
    covered_paths = inventory_paths(inv) | load_provenance_files(inv)
    governed = []
    for p in files:
        rp = rel(p)
        parts = rp.split("/")
        if len(parts) >= 3 and parts[0] == "web" and parts[2] in {"mats", "assets", "datasets"}:
            if p.suffix.lower() in GOVERNED_SUFFIXES and p.name != "SKILL.html":
                governed.append(rp)
        elif parts and parts[0] in {"datasets", "data"}:
            if p.suffix.lower() in GOVERNED_SUFFIXES:
                governed.append(rp)
    missing = [p for p in governed if not covered(p, covered_paths)]
    if missing:
        for p in missing:
            fails.append(f"unmanifested governed material: {p}")
    else:
        oks.append(f"governed material: {len(governed)} tracked file(s) covered by provenance or inventory")


def run() -> tuple[list[str], list[str]]:
    inv = load_inventory()
    files = tracked_files()
    fails: list[str] = []
    oks: list[str] = []
    # Legal-source discovery deliberately ignores the content-ingestion skip set above. Every
    # authored Python and JavaScript file in the governed roots enters this audit, including build
    # and generated-artifact tooling.
    legal_files = source_license_contract.repository_files(ROOT)
    legal_fails, legal_oks = source_license_contract.audit(ROOT, legal_files)
    fails.extend(legal_fails)
    oks.extend(legal_oks)
    check_contribution_terms(fails, oks)
    check_inventory(inv, fails, oks)
    check_private_links(inv, files, fails, oks)
    check_governed_material(inv, files, fails, oks)
    return fails, oks


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    fails, oks = run()
    if args.json:
        print(json.dumps({"ok": oks, "fail": fails}, indent=2))
    else:
        for msg in oks:
            print(f"  ok   {msg}")
        for msg in fails:
            print(f"  FAIL {msg}")
        print(f"\nsource_gate: {len(oks)} ok - {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
