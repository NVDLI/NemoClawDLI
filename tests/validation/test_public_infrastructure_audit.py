#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for automatic public infrastructure-identifier discovery."""
from __future__ import annotations

import unittest

from scripts.validation import public_infrastructure_audit as audit


class PublicInfrastructureAuditTests(unittest.TestCase):
    def test_current_source_has_no_concrete_operator_identifiers(self) -> None:
        self.assertEqual([], audit.scan())

    def test_identifier_families_are_detected_in_any_text_file(self) -> None:
        values = (
            "s3" + "://example-operator-bucket/prefix",
            "example-operator-bucket" + ".s3.us-west-2.amazonaws.com",
            "arn:aws:iam::" + "123456789012" + ":role/example",
            "Z" + "1234567890ABC",
            "d" + "1234567890.cloudfront" + ".net",
            '"aws_account_id": "' + "123456789012" + '"',
            '"bucket_name": "' + "operator-course-assets" + '"',
            'BUCKET = "' + "operator-course-assets" + '"',
            '"cloudfront_distribution_id": "' + "E1234567890AB" + '"',
        )
        for value in values:
            with self.subTest(value=value):
                self.assertNotEqual([], audit.scan_text("new/source.txt", value))

    def test_placeholders_and_runtime_service_urls_are_not_misclassified(self) -> None:
        value = "\n".join((
            "s3" + "://<operator-bucket>/<prefix>",
            "s3" + "://${var.bucket}/${var.key}",
            "https://openclaw-cors-proxy.example.invalid",
            "https://cdn.example.invalid/course-static/",
            '"aws_account_id": "<operator-account>"',
            '"bucket_name": "example-course-bucket"',
            'BUCKET = "example-course-bucket"',
            '"cloudfront_distribution_id": "<operator-distribution>"',
        ))
        self.assertEqual([], audit.scan_text("documentation.md", value))

    def test_object_store_hostname_scanner_is_bounded_and_boundary_aware(self) -> None:
        suffix = "amazonaws" + ".com/key"
        value = "\n".join((
            "https://bucket-name.s3." + suffix,
            "https://bucket-name.s3-us-west-2." + suffix,
            "https://bucket-name.s3.us-west-2." + suffix,
        ))
        findings = audit.scan_text("documentation.md", value)
        self.assertEqual(
            3,
            sum(item.kind == "concrete object-store website hostname" for item in findings),
        )
        self.assertEqual([], audit.scan_text("documentation.md", "https://s3." + suffix))


if __name__ == "__main__":
    unittest.main()
