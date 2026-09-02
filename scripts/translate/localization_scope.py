# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Normalize English-only presentation shells around translatable course prose."""
from __future__ import annotations

import hashlib
from html import escape
from html.parser import HTMLParser

VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class TranslationCanonicalizer(HTMLParser):
    """Remove an en-shell's controls while retaining its translatable body."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.stack: list[tuple[str, str | None, bool]] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        classes = set(values.get("class", "").split())
        scoped = values.get("data-localization-scope") == "en"
        if self.skip_depth or scoped:
            if tag not in VOID_ELEMENTS:
                self.skip_depth += 1
                self.stack.append((tag, None, True))
            return
        output_tag: str | None = tag
        output_attrs = attrs
        if tag == "details" and values.get("data-localization-scope") == "en-shell":
            output_tag = "div" if "references" in classes else None
            output_attrs = [("class", "references")] if output_tag else []
        elif tag == "div" and "learning-block-body" in classes:
            output_tag = None
            output_attrs = []
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, output_tag, False))
        if output_tag:
            rendered = "".join(
                f' {key}="{escape(value or "", quote=True)}"' for key, value in output_attrs
            )
            self.parts.append(f"<{output_tag}{rendered}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip_depth:
            return
        rendered = "".join(f' {key}="{escape(value or "", quote=True)}"' for key, value in attrs)
        self.parts.append(f"<{tag}{rendered}/>")

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            if not self.skip_depth:
                self.parts.append(f"</{tag}>")
            return
        index = next((i for i in range(len(self.stack) - 1, -1, -1) if self.stack[i][0] == tag), -1)
        if index < 0:
            if not self.skip_depth:
                self.parts.append(f"</{tag}>")
            return
        removed = self.stack[index:]
        _, output_tag, skipped = removed[0]
        del self.stack[index:]
        if skipped:
            self.skip_depth = max(0, self.skip_depth - sum(1 for _, _, item_skipped in removed if item_skipped))
        elif output_tag:
            self.parts.append(f"</{output_tag}>")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self.skip_depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self.skip_depth:
            self.parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(f"<!--{data}-->")


def translation_canonical(raw: str) -> str:
    parser = TranslationCanonicalizer()
    parser.feed(raw.replace("\r\n", "\n"))
    return "".join(parser.parts)


def translation_sha(raw: str) -> str:
    return hashlib.sha256(translation_canonical(raw).encode("utf-8")).hexdigest()


class EditorialText(HTMLParser):
    """Hash an explicit style sample, or all visible prose for legacy references."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.pin_depth = 0
        self.pin_seen = False
        self.stack: list[tuple[str, bool, bool]] = []
        self.all_parts: list[str] = []
        self.pinned_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        skipped = tag in {"script", "style"}
        pinned = values.get("data-editorial-pin") == "1"
        if skipped:
            self.skip_depth += 1
        if pinned:
            self.pin_depth += 1
            self.pin_seen = True
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, skipped, pinned))

    def handle_endtag(self, tag: str) -> None:
        index = next(
            (index for index in range(len(self.stack) - 1, -1, -1)
             if self.stack[index][0] == tag),
            -1,
        )
        if index < 0:
            return
        removed = self.stack[index:]
        del self.stack[index:]
        self.skip_depth = max(0, self.skip_depth - sum(item[1] for item in removed))
        self.pin_depth = max(0, self.pin_depth - sum(item[2] for item in removed))

    def handle_data(self, data: str) -> None:
        if not self.skip_depth and data.strip():
            text = " ".join(data.split())
            self.all_parts.append(text)
            if self.pin_depth:
                self.pinned_parts.append(text)

    @property
    def parts(self) -> list[str]:
        return self.pinned_parts if self.pin_seen else self.all_parts


def editorial_sha(raw: str) -> str:
    parser = EditorialText()
    parser.feed(raw.replace("\r\n", "\n"))
    return hashlib.sha256("\n".join(parser.parts).encode("utf-8")).hexdigest()
