# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation coverage for model-only locale-resource rebinding."""
from __future__ import annotations

import unittest

from translate.locale_resources import LocaleResourceError, template_units, validate_values
from translate.migrate_locale_resource import (
    insert_exact_values,
    rebind_exact_values_many,
    rebind_model_values,
    rebind_model_values_many,
)


OLD = "nvidia/retired-embed-model"
NEW = "nvidia/current-embed-model"
OLD_CHAT = "nvidia/retired-chat-model"
NEW_CHAT = "nvidia/current-chat-model"


def reviewed_values(source: str) -> dict[str, dict[str, str]]:
    return {
        unit.key: {
            "type": unit.value_type,
            "source": unit.source,
            "value": unit.source,
            "untranslated": "reviewed protected model identifier",
        }
        for unit in template_units(source)
    }


class LocaleResourceModelRebindTests(unittest.TestCase):
    def test_rekeys_repeated_model_units_without_changing_other_copy(self) -> None:
        previous = (
            "<html><body>"
            f"<p>The pinned model is <code>{OLD}</code>.</p>"
            f"<p>The pinned model is <code>{OLD}</code>.</p>"
            "<p>Texto revisado.</p>"
            "</body></html>"
        )
        current = previous.replace(OLD, NEW)
        values = rebind_model_values(current, reviewed_values(previous), OLD, NEW)
        validate_values(current, values)
        rendered_copy = "\n".join(entry["value"] for entry in values.values())
        self.assertEqual(2, rendered_copy.count(NEW))
        self.assertNotIn(OLD, rendered_copy)
        self.assertIn("Texto revisado.", rendered_copy)

    def test_add_delete_and_unrelated_edits_fail_closed(self) -> None:
        previous = (
            "<html><body>"
            f"<p>The pinned model is <code>{OLD}</code>.</p>"
            "<p>Reviewed copy.</p>"
            "</body></html>"
        )
        values = reviewed_values(previous)
        with self.assertRaisesRegex(LocaleResourceError, "drop reviewed values"):
            rebind_model_values(
                f"<html><body><p>The pinned model is <code>{NEW}</code>.</p></body></html>",
                values, OLD, NEW,
            )
        with self.assertRaisesRegex(LocaleResourceError, "outside the declared model rebind"):
            rebind_model_values(
                "<html><body>"
                f"<p>The pinned model is <code>{NEW}</code>.</p>"
                "<p>Changed copy.</p>"
                "</body></html>",
                values, OLD, NEW,
            )

    def test_malformed_near_match_is_not_rewritten(self) -> None:
        previous = f"<html><body><p>{OLD}-extra</p></body></html>"
        with self.assertRaisesRegex(LocaleResourceError, "does not contain"):
            rebind_model_values(
                previous.replace(OLD, NEW), reviewed_values(previous), OLD, NEW,
            )

    def test_rekeys_multiple_models_atomically(self) -> None:
        previous = (
            "<html><body>"
            f"<p>Embedding: <code>{OLD}</code>.</p>"
            f"<p>Chat: <code>{OLD_CHAT}</code>.</p>"
            "<p>Reviewed copy.</p>"
            "</body></html>"
        )
        current = previous.replace(OLD, NEW).replace(OLD_CHAT, NEW_CHAT)
        values = rebind_model_values_many(
            current, reviewed_values(previous), [(OLD, NEW), (OLD_CHAT, NEW_CHAT)]
        )
        validate_values(current, values)
        rendered_copy = "\n".join(entry["value"] for entry in values.values())
        self.assertIn(NEW, rendered_copy)
        self.assertIn(NEW_CHAT, rendered_copy)
        self.assertNotIn(OLD, rendered_copy)
        self.assertNotIn(OLD_CHAT, rendered_copy)

    def test_rekeys_language_neutral_label_inside_reviewed_copy(self) -> None:
        previous_label = "Nemotron Nano 30B"
        current_label = "Nemotron 3.5 Lightning 30B"
        previous = f"<html><body><p>{previous_label} · fast</p></body></html>"
        current = previous.replace(previous_label, current_label)
        values = reviewed_values(previous)
        entry = next(iter(values.values()))
        entry["value"] = f"{previous_label} · rápido"
        entry.pop("untranslated")
        rebound = rebind_exact_values_many(
            current, values, [(previous_label, current_label)]
        )
        self.assertEqual(
            f"{current_label} · rápido",
            next(iter(rebound.values()))["value"],
        )

    def test_inserts_only_declared_language_neutral_interface_literal(self) -> None:
        previous = "<html><p>vision</p></html>"
        current = previous.replace("</html>", "<p>vision-tool-calling</p></html>")
        inserted = insert_exact_values(current, reviewed_values(previous), ["vision-tool-calling"])
        validate_values(current, inserted)
        self.assertEqual(
            "vision-tool-calling",
            next(entry["value"] for entry in inserted.values() if entry["source"] == "vision-tool-calling"),
        )
        with self.assertRaisesRegex(LocaleResourceError, "outside the declared literal insertion"):
            insert_exact_values(current.replace("</html>", "<p>Novel prose.</p></html>"), reviewed_values(previous), ["vision-tool-calling"])
        with self.assertRaisesRegex(LocaleResourceError, "does not introduce"):
            insert_exact_values(previous, reviewed_values(previous), ["vision-tool-calling"])
        with self.assertRaisesRegex(LocaleResourceError, "drop reviewed values"):
            insert_exact_values("<html></html>", reviewed_values(previous), ["vision-tool-calling"])
        with self.assertRaisesRegex(LocaleResourceError, "outside the declared literal insertion"):
            insert_exact_values(current.replace("vision-tool-calling", "vision-tool-call"), reviewed_values(previous), ["vision-tool-calling"])


if __name__ == "__main__":
    unittest.main()
