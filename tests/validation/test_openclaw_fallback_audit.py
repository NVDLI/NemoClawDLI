#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation tests for the OpenClaw relay provider boundary."""
from __future__ import annotations

import unittest

from scripts.validation import openclaw_fallback_audit as audit


class OpenClawFallbackAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.worker = audit.read(audit.FILES["cors_worker"])

    def test_current_worker_binds_only_the_validated_pomerium_cookie(self) -> None:
        self.assertEqual([], audit.worker_provider_findings(self.worker))

    def test_incoming_pomerium_header_must_be_stripped(self) -> None:
        mutated = self.worker.replace(
            'fwdHeaders.delete("X-Pomerium-Authorization");',
            "// caller header retained",
            1,
        )
        self.assertTrue(any("strip caller-supplied" in item for item in audit.worker_provider_findings(mutated)))

    def test_incoming_cookie_header_must_be_stripped(self) -> None:
        mutated = self.worker.replace(
            'fwdHeaders.delete("Cookie");',
            "// caller cookie retained",
            1,
        )
        self.assertTrue(any("strip caller cookies" in item for item in audit.worker_provider_findings(mutated)))

    def test_provider_bound_pomerium_cookie_must_be_added(self) -> None:
        mutated = self.worker.replace(
            'fwdHeaders.set("Cookie", "_pomerium=" + accessSession);',
            "// provider binding removed",
            1,
        )
        self.assertTrue(any("allowlisted upstream cookie" in item for item in audit.worker_provider_findings(mutated)))


if __name__ == "__main__":
    unittest.main()
