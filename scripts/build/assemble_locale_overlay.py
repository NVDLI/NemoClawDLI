#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Assemble one sparse language overlay over the canonical web tree.

Localized prose, reviewed runnable-code language, and reviewed SVG text may diverge. Executable
structure, protocol literals, runtime modules, styles, data, and untranslated pages stay canonical,
so a language cannot silently fork the application or silently fall back to English learner output.
The committed overlay allow-lists in `localization_state.json` are the only locale files applied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import find_repo_root
from translate.code_localization import project_localized_code_templates
from translate.locale_projection import project_locale_html
from translate.localization_scope import translation_sha

ROOT = find_repo_root(Path(__file__).resolve())


def source_sha(path: Path) -> str:
    raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def safe_relative(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != "web":
        raise ValueError(f"unsafe overlay path: {raw}")
    return path


def assemble(locale_root: Path, out: Path, canonical_root: Path = ROOT) -> list[str]:
    state_path = locale_root / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    overlay_files = [safe_relative(item) for item in state.get("overlay_files", [])]
    asset_files = [safe_relative(item) for item in state.get("asset_files", [])]
    reviews = state.get("reviews", {})
    asset_reviews = state.get("asset_reviews", {})
    locale_meta = json.loads((locale_root / "locale.json").read_text(encoding="utf-8"))
    profile_ref = locale_meta.get("profile")
    profile_path = canonical_root / profile_ref if profile_ref else None
    shell_path = profile_path.parent / "shell_translations.json" if profile_path else locale_root / "shell_translations.json"
    shell_translations = json.loads(shell_path.read_text(encoding="utf-8")) if shell_path.is_file() else {}
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(canonical_root / "web", out / "web")
    applied: list[str] = []
    for rel in overlay_files + asset_files:
        src = locale_root / rel
        if not src.is_file():
            raise FileNotFoundError(f"declared locale overlay is missing: {src}")
        canonical = canonical_root / rel
        review = (asset_reviews if rel in asset_files else reviews).get(rel.as_posix(), {})
        if not canonical.is_file():
            continue
        canonical_raw = canonical.read_text(encoding="utf-8")
        scoped_html = rel.suffix == ".html" and 'data-localization-scope="en-shell"' in canonical_raw
        current_digest = translation_sha(canonical_raw) if scoped_html else source_sha(canonical)
        reviewed_digest = review.get("translation_sha256") if scoped_html else review.get("source_sha256")
        if reviewed_digest != current_digest:
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if scoped_html:
            dst.write_text(project_locale_html(canonical_raw, src.read_text(encoding="utf-8"), shell_translations),
                           encoding="utf-8")
        else:
            shutil.copy2(src, dst)
        applied.append(rel.as_posix())
    browser_meta = out / "web" / "nemoclaw" / "assets" / "locale.json"
    browser_meta.parent.mkdir(parents=True, exist_ok=True)
    browser_meta.write_text(json.dumps(locale_meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return applied


def self_test() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="locale-overlay-") as td:
        root = Path(td)
        canonical = root / "canonical"
        locale = root / "i18n/pt"
        rel = Path("web/nemoclaw/index.html")
        source = canonical / rel
        target = locale / rel
        source.parent.mkdir(parents=True)
        target.parent.mkdir(parents=True)
        source.write_text("English source", encoding="utf-8")
        target.write_text("Fonte em português", encoding="utf-8")
        (locale / "locale.json").write_text(json.dumps({"locale": "pt-BR"}), encoding="utf-8")
        (locale / "shell_translations.json").write_text(json.dumps({
            "Need detail?": "Precisa de detalhes?"
        }), encoding="utf-8")
        state = {"overlay_files": [rel.as_posix()],
                 "reviews": {rel.as_posix(): {"source_sha256": source_sha(source)}}}
        (locale / "localization_state.json").write_text(json.dumps(state), encoding="utf-8")
        out = root / "out"
        if assemble(locale, out, canonical) != [rel.as_posix()] or (out / rel).read_text(encoding="utf-8") != "Fonte em português":
            failures.append("accepted translation was not applied")
        source.write_text("Changed English source", encoding="utf-8")
        if assemble(locale, out, canonical) or (out / rel).read_text(encoding="utf-8") != "Changed English source":
            failures.append("stale translation did not fall back to canonical English")
        scoped = '<details class="learning-block" data-localization-scope="en-shell"><summary data-localization-scope="en">Need detail?</summary><div class="learning-block-body">English source</div></details>'
        source.write_text(scoped, encoding="utf-8")
        state["reviews"][rel.as_posix()]["translation_sha256"] = translation_sha(scoped)
        (locale / "localization_state.json").write_text(json.dumps(state), encoding="utf-8")
        if assemble(locale, out, canonical) != [rel.as_posix()]:
            failures.append("English-only presentation shell invalidated a reviewed translation")
        projected = (out / rel).read_text(encoding="utf-8")
        if "<details" not in projected or "Precisa de detalhes?" not in projected or "Fonte em português" not in projected:
            failures.append("localized prose was not projected into the current presentation shell")
        code_source = ('<script>const cell={code:`const job=await state.call("cron.add",'
                       '{kind:"agentTurn"}); helpers.log("Installed job");`};</script>')
        code_target = code_source.replace("Installed job", "Tarefa instalada")
        code_projected = project_localized_code_templates(code_source, code_target, code_source)
        if "Tarefa instalada" not in code_projected or 'state.call("cron.add"' not in code_projected:
            failures.append("localized runnable-code text was not projected onto canonical structure")
        try:
            project_localized_code_templates(
                code_source, code_target.replace('"cron.add"', '"cron.adicionar"'), code_source)
            failures.append("localized runnable-code RPC drift was projected")
        except ValueError:
            pass
        source.write_text(scoped.replace("Need detail?", "Open detail?"), encoding="utf-8")
        try:
            assemble(locale, out, canonical)
            failures.append("untranslated presentation-shell change was accepted")
        except ValueError:
            pass
        (locale / "shell_translations.json").write_text(json.dumps({
            "Need detail?": "Precisa de detalhes?", "Open detail?": "Abrir detalhes?"
        }), encoding="utf-8")
        if assemble(locale, out, canonical) != [rel.as_posix()]:
            failures.append("translated presentation-shell change was rejected")
        source.write_text(scoped.replace("English source", "Changed lesson"), encoding="utf-8")
        if assemble(locale, out, canonical):
            failures.append("translatable body change did not invalidate a reviewed translation")
        svg_rel = Path("web/nemoclaw/assets/figures/lesson.svg")
        svg_source = canonical / svg_rel
        svg_target = locale / svg_rel
        svg_source.parent.mkdir(parents=True, exist_ok=True)
        svg_target.parent.mkdir(parents=True, exist_ok=True)
        svg_source.write_text('<svg><text>Agent loop</text></svg>', encoding="utf-8")
        svg_target.write_text('<svg data-locale="pt-BR"><text>Ciclo do agente</text></svg>', encoding="utf-8")
        state["asset_files"] = [svg_rel.as_posix()]
        state["asset_reviews"] = {svg_rel.as_posix(): {"source_sha256": source_sha(svg_source)}}
        source.write_text(scoped.replace("Need detail?", "Open detail?"), encoding="utf-8")
        state["reviews"][rel.as_posix()]["translation_sha256"] = translation_sha(source.read_text(encoding="utf-8"))
        (locale / "localization_state.json").write_text(json.dumps(state), encoding="utf-8")
        applied = assemble(locale, out, canonical)
        if svg_rel.as_posix() not in applied or (out / svg_rel).read_text(encoding="utf-8") != svg_target.read_text(encoding="utf-8"):
            failures.append("accepted localized SVG was not applied")
        svg_source.write_text('<svg><text>Changed agent loop</text></svg>', encoding="utf-8")
        applied = assemble(locale, out, canonical)
        if svg_rel.as_posix() in applied or (out / svg_rel).read_text(encoding="utf-8") != svg_source.read_text(encoding="utf-8"):
            failures.append("stale localized SVG did not fall back to canonical source")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--locale-root", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        failures = self_test()
        if failures:
            print("assemble_locale_overlay self-test: FAIL", file=sys.stderr)
            for item in failures:
                print(f"  - {item}", file=sys.stderr)
            return 1
        print("assemble_locale_overlay self-test: OK")
        return 0
    if args.locale_root is None or args.out is None:
        parser.error("--locale-root and --out are required unless --self-test is used")
    locale_root = args.locale_root if args.locale_root.is_absolute() else ROOT / args.locale_root
    out = args.out if args.out.is_absolute() else ROOT / args.out
    try:
        applied = assemble(locale_root.resolve(), out.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"assemble_locale_overlay: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"assemble_locale_overlay: {locale_root.name} -> {out} ({len(applied)} localized files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
