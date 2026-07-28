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
        cls.openclaw = audit.read(audit.FILES["openclaw_js"])
        cls.connection = audit.read(audit.FILES["connection_js"])
        cls.openshell = audit.read(audit.FILES["openshell_js"])

    def test_current_worker_uses_provider_native_pomerium_transport(self) -> None:
        self.assertEqual([], audit.worker_provider_findings(self.worker))

    def test_pomerium_cookie_transport_is_rejected(self) -> None:
        mutated = self.worker + '\nconst unsafe = "_pomerium=session";\n'
        self.assertTrue(any("not synthesize" in item for item in audit.worker_provider_findings(mutated)))

    def test_incoming_pomerium_header_must_be_stripped(self) -> None:
        mutated = self.worker.replace(
            'fwdHeaders.delete("X-Pomerium-Authorization");',
            "// caller header retained",
            1,
        )
        self.assertTrue(any("strip caller-supplied" in item for item in audit.worker_provider_findings(mutated)))

    def test_provider_bound_pomerium_header_must_be_added(self) -> None:
        mutated = self.worker.replace(
            'fwdHeaders.set("X-Pomerium-Authorization", accessSession);',
            "// provider binding removed",
            1,
        )
        self.assertTrue(any("upstream-only provider header" in item for item in audit.worker_provider_findings(mutated)))

    def test_current_client_keeps_pomerium_sender_bound(self) -> None:
        self.assertEqual([], audit.browser_session_findings(self.openclaw, self.connection))
        self.assertEqual([], audit.terminal_routing_findings(self.openshell))

    def test_client_mutation_contract_covers_sender_bound_auth(self) -> None:
        self.assertEqual([], audit.browser_session_contract(self.openclaw, self.connection))
        self.assertEqual([], audit.terminal_routing_contract(self.openshell))


if __name__ == "__main__":
    unittest.main()
