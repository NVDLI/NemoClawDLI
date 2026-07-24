# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Project a reviewed sparse translation onto the current canonical page structure."""
from __future__ import annotations

import re

from translate.code_localization import project_localized_code_templates
from translate.localization_scope import translation_canonical
from translate.translate_html_segments import extract_segments


def project_locale_html(source_raw: str, target_raw: str, shell_translations: dict[str, str]) -> str:
    """Keep current source structure while substituting reviewed prose and localized shell text."""
    full = extract_segments(source_raw)
    canonical = extract_segments(translation_canonical(source_raw))
    translated = extract_segments(target_raw)
    if len(canonical) != len(translated):
        raise ValueError(f"translation segment count differs: source {len(canonical)}, target {len(translated)}")
    for index, (source, target) in enumerate(zip(canonical, translated)):
        if source.kind != target.kind:
            raise ValueError(f"translation segment kind differs at {index}: {source.kind} != {target.kind}")

    replacements: list[tuple[int, int, str]] = []
    canonical_index = 0
    missing_shell: list[str] = []
    for segment in full:
        if (canonical_index < len(canonical)
                and segment.kind == canonical[canonical_index].kind
                and segment.text == canonical[canonical_index].text):
            replacements.append((segment.start, segment.end, translated[canonical_index].text))
            canonical_index += 1
            continue
        shell_key = " ".join(segment.text.split())
        replacement = shell_translations.get(shell_key)
        if replacement is None:
            missing_shell.append(" ".join(segment.text.split())[:160])
        else:
            replacements.append((segment.start, segment.end, replacement))
    if canonical_index != len(canonical):
        raise ValueError(f"only matched {canonical_index}/{len(canonical)} canonical translation segments")
    if missing_shell:
        raise ValueError("missing localized shell segment(s): " + " | ".join(missing_shell))

    projected = source_raw
    for start, end, replacement in reversed(replacements):
        projected = projected[:start] + replacement + projected[end:]
    projected = project_localized_code_templates(source_raw, target_raw, projected)
    target_lang = re.search(r'<html\b[^>]*\blang=["\']([^"\']+)', target_raw, re.I)
    if target_lang:
        projected = re.sub(r'(<html\b[^>]*\blang=["\'])[^"\']+(["\'])',
                           rf'\g<1>{target_lang.group(1)}\2', projected, count=1, flags=re.I)
    return projected
