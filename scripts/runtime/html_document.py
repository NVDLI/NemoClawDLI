#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Browser-tolerant HTML projections shared by repository validators.

The course validators inspect authored HTML but do not sanitize learner input. Even so, their view
of script boundaries must agree with a browser: a regex that misses a malformed end tag can hide
code from a gate. BeautifulSoup's pinned lxml backend handles those recovery cases. The package-free
strict parser is reserved for deterministic projection after that browser-tolerant validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Iterable


@dataclass(frozen=True)
class RawTextBlock:
    """One raw-text element and its source-relative body position."""

    attributes: dict[str, str]
    body: str
    body_start: int
    element_start: int
    element_end: int


def _tag_end(raw: str, start: int) -> int:
    """Return the first tag-closing `>` outside an attribute quote."""

    quote = ""
    for index in range(start, len(raw)):
        char = raw[index]
        if quote:
            if char == quote:
                quote = ""
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == ">":
            return index + 1
    raise ValueError("unterminated script start tag")


def _next_start_tag(raw: str, name: str, start: int) -> int:
    """Return the next exact start tag while ignoring comments and longer tag names."""

    lowered = raw.casefold()
    cursor = start
    prefix = f"<{name.casefold()}"
    while cursor < len(raw):
        candidate = raw.find("<", cursor)
        if candidate < 0:
            return -1
        if lowered.startswith("<!--", candidate):
            comment_end = raw.find("-->", candidate + 4)
            cursor = len(raw) if comment_end < 0 else comment_end + 3
            continue
        after_name = candidate + len(prefix)
        if (
            lowered.startswith(prefix, candidate)
            and after_name < len(raw)
            and (raw[after_name].isspace() or raw[after_name] in {"/", ">"})
        ):
            return candidate
        cursor = candidate + 1
    return -1


class _StrictRawTextParser(HTMLParser):
    """Locate verified raw-text elements without optional third-party packages."""

    def __init__(self, raw: str, name: str) -> None:
        super().__init__(convert_charrefs=False)
        self.raw = raw
        self.name = name.casefold()
        self.line_starts = [0, *(match.end() for match in re.finditer("\n", raw))]
        self.active: tuple[int, int, dict[str, str]] | None = None
        self.blocks: list[RawTextBlock] = []

    def absolute_offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    @staticmethod
    def attributes(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {str(key).casefold(): str(value or "") for key, value in attrs}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != self.name:
            return
        if self.active is not None:
            raise ValueError(f"nested {self.name} start tag")
        element_start = self.absolute_offset()
        body_start = _tag_end(self.raw, element_start)
        self.active = (element_start, body_start, self.attributes(attrs))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == self.name:
            raise ValueError(f"self-closing {self.name} is not a valid raw-text boundary")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != self.name:
            return
        if self.active is None:
            raise ValueError(f"unmatched {self.name} end tag")
        element_start, body_start, attributes = self.active
        close_start = self.absolute_offset()
        close_end = _tag_end(self.raw, close_start)
        self.blocks.append(
            RawTextBlock(
                attributes,
                self.raw[body_start:close_start],
                body_start,
                element_start,
                close_end,
            )
        )
        self.active = None

    def finish(self) -> list[RawTextBlock]:
        self.feed(self.raw)
        self.close()
        if self.active is not None:
            raise ValueError(f"unterminated {self.name} element")
        return self.blocks


def raw_text_blocks_strict(raw: str, name: str) -> list[RawTextBlock]:
    """Return exact raw-text spans for source that already passed browser validation."""

    if name.casefold() not in {"script", "style"}:
        raise ValueError(f"unsupported raw-text element: {name}")
    return _StrictRawTextParser(raw, name).finish()


def raw_text_blocks(raw: str, name: str) -> list[RawTextBlock]:
    """Return raw-text element blocks after lxml establishes browser-compatible boundaries."""

    from bs4 import BeautifulSoup

    blocks = []
    cursor = 0
    lowered = raw.casefold()
    closer = f"</{name}"
    for element in BeautifulSoup(raw, "lxml").find_all(name):
        open_start = _next_start_tag(raw, name, cursor)
        if open_start < 0:
            raise ValueError(f"parsed {name} element has no source start tag")
        open_end = _tag_end(raw, open_start)
        body = str(element.string) if element.string is not None else element.decode_contents()
        body_start = raw.find(body, open_end) if body else open_end
        if body_start < 0:
            raise ValueError(f"parsed {name} body does not match the authored source")
        close_start = body_start + len(body)
        if not lowered.startswith(closer, close_start):
            raise ValueError(f"parsed {name} element has no source end tag")
        close_end = _tag_end(raw, close_start)
        attributes = {
            str(key).casefold(): (
                " ".join(str(item) for item in value)
                if isinstance(value, list)
                else str(value)
            )
            for key, value in element.attrs.items()
        }
        blocks.append(
            RawTextBlock(attributes, body, body_start, open_start, close_end)
        )
        cursor = close_end
    return blocks


def script_body_by_id(raw: str, element_id: str) -> str | None:
    """Return a script element body selected by its exact id."""

    from bs4 import BeautifulSoup

    element = BeautifulSoup(raw, "lxml").find("script", id=element_id)
    if element is None:
        return None
    return str(element.string) if element.string is not None else element.decode_contents()


def without_elements(raw: str, names: Iterable[str]) -> str:
    """Remove raw-text elements while preserving every untouched authored byte."""

    wanted = {name.casefold() for name in names}
    unsupported = wanted - {"script", "style"}
    if unsupported:
        raise ValueError(f"unsupported raw-text element(s): {sorted(unsupported)}")
    spans = [
        (block.element_start, block.element_end)
        for name in wanted
        for block in raw_text_blocks(raw, name)
    ]
    projected = raw
    for start, end in sorted(spans, reverse=True):
        projected = projected[:start] + projected[end:]
    return projected
