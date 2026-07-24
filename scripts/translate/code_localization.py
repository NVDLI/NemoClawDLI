# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Project localized runnable-code language without permitting executable drift."""
from __future__ import annotations

import re


CODE_TEMPLATE_RE = re.compile(
    r'\bcode\s*:\s*(?:(?:[A-Za-z_$][\w$]*(?:\.[\w$]+)*)\s*\+\s*)*`((?:\\.|[^`\\])*)`',
    re.S,
)


def js_shape(raw: str) -> str:
    """Remove comments, whitespace, and string text while retaining executable tokens."""
    out: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        following = raw[index + 1] if index + 1 < len(raw) else ""
        if char == "/" and following == "/":
            index += 2
            while index < len(raw) and raw[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and following == "*":
            end = raw.find("*/", index + 2)
            index = len(raw) if end < 0 else end + 2
            continue
        if char in {'"', "'", "`"}:
            quote = char
            index += 1
            while index < len(raw):
                if raw[index] == "\\":
                    index += 2
                    continue
                if raw[index] == quote:
                    index += 1
                    break
                index += 1
            out.append("S")
            continue
        if not char.isspace():
            out.append(char)
        index += 1
    return "".join(out)


def code_template_matches(raw: str) -> list[re.Match[str]]:
    return list(CODE_TEMPLATE_RE.finditer(raw))


def code_templates(raw: str) -> list[str]:
    return [match.group(1) for match in code_template_matches(raw)]


def body_contract_literals(body: str) -> list[tuple[str, str]]:
    """Return protocol/config literals that translations must preserve exactly."""
    patterns = (
        ("rpc", r'\b(?:state\.)?call\(\s*["\']([^"\']+)["\']'),
        ("module", r'\bimport\(\s*["\']([^"\']+)["\']'),
        ("storage", r'\blocalStorage\.(?:getItem|setItem|removeItem)\(\s*["\']([^"\']+)["\']'),
        ("field", r'\b(kind|sessionTarget|wakeMode|method|path|id|name|tz)\s*:\s*["\']([A-Za-z0-9_./:*?~={}<>-]+)["\']'),
        ("schedule", r'\bschedule\s*:\s*["\']([^"\']+)["\']'),
    )
    out: list[tuple[str, str]] = []
    for label, pattern in patterns:
        for match in re.finditer(pattern, body):
            value = "=".join(group for group in match.groups() if group is not None)
            out.append((label, value))
    return out


def code_contract_literals(raw: str) -> list[tuple[int, str, str]]:
    return [
        (index, label, value)
        for index, body in enumerate(code_templates(raw))
        for label, value in body_contract_literals(body)
    ]


def project_localized_code_templates(source_raw: str, target_raw: str, projected_raw: str) -> str:
    """Copy reviewed localized code text onto canonical syntax after fail-closed checks."""
    source = code_template_matches(source_raw)
    target = code_template_matches(target_raw)
    projected = code_template_matches(projected_raw)
    if len(source) != len(target) or len(source) != len(projected):
        raise ValueError(
            f"runnable code template count differs: source {len(source)}, target {len(target)}, projected {len(projected)}"
        )
    for index, (source_match, target_match) in enumerate(zip(source, target)):
        source_body = source_match.group(1)
        target_body = target_match.group(1)
        if js_shape(source_body) != js_shape(target_body):
            raise ValueError(f"localized runnable code structure differs at template {index}")
        if body_contract_literals(source_body) != body_contract_literals(target_body):
            raise ValueError(f"localized runnable code contract differs at template {index}")
    result = projected_raw
    for projected_match, target_match in reversed(list(zip(projected, target))):
        start, end = projected_match.span(1)
        result = result[:start] + target_match.group(1) + result[end:]
    return result
