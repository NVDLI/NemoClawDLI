# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation coverage for the checked-in Module 2b embedding artifact."""
from __future__ import annotations

import copy
import json
import unittest

from scripts.materials import build_rag_index


class RagIndexContractTests(unittest.TestCase):
    def manifest(self) -> dict:
        return json.loads(build_rag_index.OUT.read_text(encoding="utf-8"))

    def test_current_artifact_matches_script_and_course_cell(self) -> None:
        self.assertEqual(
            [],
            build_rag_index.manifest_problems(
                self.manifest(),
                cell_docs=build_rag_index.cell_corpus(),
            ),
        )

    def test_corpus_change_invalidates_the_artifact(self) -> None:
        changed = [*build_rag_index.CORPUS, "A newly authored retrieval document."]
        problems = build_rag_index.manifest_problems(
            self.manifest(),
            corpus=changed,
            cell_docs=changed,
        )
        self.assertTrue(any("corpus_hash drift" in problem for problem in problems))

    def test_manifest_text_change_is_rejected(self) -> None:
        manifest = copy.deepcopy(self.manifest())
        manifest["docs"][0]["text"] = "Different text with an old embedding."
        problems = build_rag_index.manifest_problems(
            manifest,
            cell_docs=build_rag_index.CORPUS,
        )
        self.assertTrue(any("manifest docs" in problem for problem in problems))

    def test_course_cell_change_is_rejected(self) -> None:
        problems = build_rag_index.manifest_problems(
            self.manifest(),
            cell_docs=build_rag_index.CORPUS[:-1],
        )
        self.assertTrue(any("#rag-cell" in problem for problem in problems))


if __name__ == "__main__":
    unittest.main()
