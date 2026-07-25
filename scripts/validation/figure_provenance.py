#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Read the image-provenance contract without filename allowlists."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROVENANCE_PAGE = ROOT / "web" / "nemoclaw" / "assets" / "SKILL.html"
PROVENANCE_BLOCK = re.compile(
    r'<script type="application/json" id="provenance">(.*?)</script>', re.S
)


@lru_cache(maxsize=1)
def provenance_payload() -> dict[str, object]:
    """Return the complete image-provenance payload or fail on malformed data."""
    raw = PROVENANCE_PAGE.read_text(encoding="utf-8")
    match = PROVENANCE_BLOCK.search(raw)
    if not match:
        raise ValueError(f"missing provenance JSON in {PROVENANCE_PAGE.relative_to(ROOT)}")
    payload = json.loads(match.group(1))
    if not isinstance(payload, dict):
        raise ValueError("image provenance must be a JSON object")
    return payload


@lru_cache(maxsize=1)
def figure_rows() -> tuple[dict[str, object], ...]:
    """Return every displayed figure row, whether stored here or loaded remotely."""
    rows = provenance_payload().get("figures")
    if not isinstance(rows, list):
        raise ValueError("image provenance must contain a figures list")
    return tuple(row for row in rows if isinstance(row, dict))


@lru_cache(maxsize=1)
def remote_figure_rows() -> tuple[dict[str, object], ...]:
    """Derive remotely displayed figures from the common provenance inventory."""
    return tuple(row for row in figure_rows() if row.get("connection") == "remote display")


def svg_modes() -> dict[str, str]:
    """Map each declared SVG to its rendering mode."""
    modes: dict[str, str] = {}
    for row in figure_rows():
        name = str(row.get("file", ""))
        if not name.endswith(".svg"):
            continue
        if name in modes:
            raise ValueError(f"duplicate image-provenance row: {name}")
        modes[name] = "fixed-white" if row.get("connection") == "conversion" else "theme-aware"
    return modes


def svg_semantic_contracts() -> dict[str, dict[str, object]]:
    """Map attributed SVGs to optional, machine-readable meaning contracts."""
    contracts: dict[str, dict[str, object]] = {}
    for row in figure_rows():
        name = str(row.get("file", ""))
        contract = row.get("semantic_contract")
        if contract is None:
            continue
        if not name.endswith(".svg"):
            raise ValueError(f"semantic figure contract must target an SVG: {name}")
        if not isinstance(contract, dict):
            raise ValueError(f"semantic figure contract must be an object: {name}")
        if name in contracts:
            raise ValueError(f"duplicate semantic figure contract: {name}")
        contracts[name] = contract
    return contracts


def fixed_white_figures() -> frozenset[str]:
    """Derive paper conversions from provenance instead of maintaining an exception list."""
    return frozenset(name for name, mode in svg_modes().items() if mode == "fixed-white")
