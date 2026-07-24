# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standard-framework coverage for localization ownership classification."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.validation.contribution_safety_audit import (
    audit_language_ownership,
    changed_learner_prose_paths,
    learner_text,
)


class ContributionLanguageOwnershipTests(unittest.TestCase):
    locale_page = "i18n/es/web/nemoclaw/01a-loop.html"
    canonical_page = "web/nemoclaw/01a-loop.html"

    def test_transport_attributes_are_not_learner_prose(self) -> None:
        before = '<a href="../index.html" class="old" aria-label="Inicio">Volver</a>'
        after = '<a href="index.html" class="new" aria-label="Inicio">Volver</a>'
        self.assertEqual(learner_text(before), learner_text(after))

    def test_visible_and_accessibility_text_are_learner_prose(self) -> None:
        baseline = '<a href="index.html" aria-label="Inicio">Volver</a>'
        for changed in (
            '<a href="index.html" aria-label="Inicio del curso">Volver</a>',
            '<a href="index.html" aria-label="Inicio">Volver al curso</a>',
        ):
            with self.subTest(changed=changed):
                self.assertNotEqual(learner_text(baseline), learner_text(changed))

    def test_git_range_classifies_content_instead_of_the_file_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git(root, "init", "-q")
            self.git(root, "config", "user.name", "Test Author")
            self.git(root, "config", "user.email", "test@example.com")
            page = root / self.locale_page
            page.parent.mkdir(parents=True)
            page.write_text('<a href="../index.html" aria-label="Inicio">Volver</a>\n', encoding="utf-8")
            self.git(root, "add", ".")
            self.git(root, "commit", "-qm", "base")
            base = self.git(root, "rev-parse", "HEAD").stdout.strip()

            page.write_text('<a href="index.html" aria-label="Inicio">Volver</a>\n', encoding="utf-8")
            self.git(root, "commit", "-qam", "route only")
            route_head = self.git(root, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(
                set(),
                changed_learner_prose_paths(
                    f"{base}..{route_head}", [self.locale_page], root,
                ),
            )

            page.write_text(
                '<a href="index.html" aria-label="Inicio del curso">Volver</a>\n',
                encoding="utf-8",
            )
            self.git(root, "commit", "-qam", "prose")
            prose_head = self.git(root, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(
                {self.locale_page},
                changed_learner_prose_paths(
                    f"{route_head}..{prose_head}", [self.locale_page], root,
                ),
            )

    def test_ownership_gate_still_blocks_actual_uncredited_prose(self) -> None:
        pages = [self.locale_page, self.canonical_page]
        self.assertEqual([], audit_language_ownership(pages, "", ["route"], set()))
        codes = {
            item["code"]
            for item in audit_language_ownership(pages, "", ["prose"], set(pages))
        }
        self.assertEqual({"contributor-credit", "mixed-language-ownership"}, codes)

    @staticmethod
    def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True, text=True,
        )


if __name__ == "__main__":
    unittest.main()
