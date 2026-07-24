#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fail before candidate or publication preparation if a privileged value is in scope."""
from __future__ import annotations

import os


FORBIDDEN_PREFIXES = ("LIVE_", "AWS_", "COURSE_GITLAB_")
FORBIDDEN_EXACT = {
    "NVIDIA_API_KEY", "BUILD_API_KEY", "CLAW_ACCESS_SESSION", "CLAW_CF",
}


def findings(env: dict[str, str]) -> list[str]:
    return sorted(
        name for name, value in env.items()
        if value and (name in FORBIDDEN_EXACT or name.startswith(FORBIDDEN_PREFIXES))
    )


def main() -> int:
    names = findings(dict(os.environ))
    if names:
        # Names are policy vocabulary, not values. Never print a value or file path.
        print("unprivileged environment: FAIL privileged variable names=" + ",".join(names))
        return 1
    print("unprivileged environment: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
