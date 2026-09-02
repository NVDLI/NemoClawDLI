#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Keep repository explorer model selection delegated to one course default."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = re.compile(
    r'<script type="application/json" id="explorer-config">(.*?)</script>',
    re.DOTALL,
)
DEFAULT = "nvidia/nemotron-3.5-lightning-30b-a3b"
APPROVED = {
    DEFAULT,
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/llama-nemotron-embed-vl-1b-v2",
}
MODEL_ID = re.compile(r'''["']((?:nvidia|openai|qwen)/[A-Za-z0-9][A-Za-z0-9._/-]*)["']''')
SOURCE_SUFFIXES = {".html", ".js", ".json", ".mjs", ".py"}
REFERENCE_PARTS = {"mats", "node_modules", "standalone", "vendor"}
NON_RUNTIME_SCRIPT_DIRS = {
    "browser-vendor", "build", "compliance", "git-hooks", "security", "skills",
    "translate", "validation",
}


def runtime_model_references(root: Path) -> dict[str, list[str]]:
    references: dict[str, list[str]] = {}
    paths: list[Path] = []
    for surface_name in ("web", "scripts"):
        surface = root / surface_name
        if not surface.is_dir():
            continue
        for path in surface.rglob("*"):
            if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
                continue
            parts = path.relative_to(surface).parts
            if REFERENCE_PARTS.intersection(parts):
                continue
            if surface_name == "scripts" and parts[0] in NON_RUNTIME_SCRIPT_DIRS:
                continue
            paths.append(path)
    for path in paths:
        for model in MODEL_ID.findall(path.read_text(encoding="utf-8")):
            references.setdefault(model, []).append(path.relative_to(root).as_posix())
    return references


class ModelConfigurationTests(unittest.TestCase):
    def test_explorers_do_not_pin_independent_models(self) -> None:
        offenders: list[str] = []
        for path in ROOT.rglob("SKILL.html"):
            source = path.read_text(encoding="utf-8")
            match = CONFIG.search(source)
            if match and "model" in json.loads(match.group(1)):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], offenders)

    def test_course_runtime_declares_the_default_once(self) -> None:
        source = (ROOT / "web/nemoclaw/scripts/_shared.js").read_text(encoding="utf-8")
        self.assertEqual(1, source.count(DEFAULT))
        self.assertIn("export const REASONING_MODEL = DEFAULT_MODEL;", source)
        self.assertIn("const LAB_MODEL     = DEFAULT_MODEL;", source)

    def test_generators_do_not_reintroduce_a_model_pin(self) -> None:
        for relative in (
            "scripts/skills/gen_skill_hierarchy.py",
            "scripts/skills/gen_directory_beacons.py",
        ):
            with self.subTest(path=relative):
                source = (ROOT / relative).read_text(encoding="utf-8")
                self.assertNotIn(DEFAULT, source)

    def test_every_authored_runtime_model_is_approved(self) -> None:
        references = runtime_model_references(ROOT)
        self.assertEqual({}, {model: paths for model, paths in references.items() if model not in APPROVED})
        self.assertTrue(APPROVED <= references.keys())

    def test_discovery_covers_novel_rename_delete_and_near_match(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            novel = root / "web/new-course/nested/novel.html"
            novel.parent.mkdir(parents=True)
            novel.write_text('<script>const model = "openai/gpt-oss-120b";</script>\n', encoding="utf-8")
            self.assertIn("openai/gpt-oss-120b", runtime_model_references(root))
            renamed = novel.with_name("renamed.js")
            novel.rename(renamed)
            self.assertIn("openai/gpt-oss-120b", runtime_model_references(root))
            renamed.write_text('const model = "openai/gpt-oss-120b-extra";\n', encoding="utf-8")
            self.assertIn("openai/gpt-oss-120b-extra", runtime_model_references(root))
            renamed.unlink()
            self.assertEqual({}, runtime_model_references(root))

            script = root / "scripts/new-runtime/model_client.py"
            script.parent.mkdir(parents=True)
            script.write_text('MODEL = "openai/gpt-oss-120b"\n', encoding="utf-8")
            self.assertIn("openai/gpt-oss-120b", runtime_model_references(root))
            script.rename(script.with_name("renamed_client.py"))
            self.assertIn("openai/gpt-oss-120b", runtime_model_references(root))
            script.with_name("renamed_client.py").unlink()
            self.assertEqual({}, runtime_model_references(root))


if __name__ == "__main__":
    unittest.main()
