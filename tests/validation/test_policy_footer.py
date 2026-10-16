# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Published course pages retain policy links and the supplied consent notice."""
from pathlib import Path
import re
import tempfile
import unittest

from scripts.build.assemble_locale_overlay import assemble
from scripts.build.bundle_standalone import bundle_one


class PolicyFooterTests(unittest.TestCase):
    def test_every_course_export_has_static_policy_links(self):
        root = Path(__file__).resolve().parents[2]
        courses = sorted(path.parent for path in (root / "web").glob("*/interface-inventory.json"))
        self.assertTrue(courses, "expected discovered course interface inventories")
        sources = list(courses)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        for locale in sorted(root.glob("i18n/*/locale.json")):
            output = Path(temporary.name) / locale.parent.name
            assemble(locale.parent, output)
            sources.extend(output / course.relative_to(root) for course in courses)
        expected = [
            ("https://www.nvidia.com/en-us/about-nvidia/privacy-policy/", "Privacy Policy"),
            ("https://www.nvidia.com/en-us/about-nvidia/privacy-center/", "Your Privacy Choices"),
            ("https://www.nvidia.com/en-us/about-nvidia/terms-of-service/", "Terms of Service"),
            ("https://www.nvidia.com/en-us/about-nvidia/accessibility/", "Accessibility"),
            ("https://www.nvidia.com/en-us/about-nvidia/company-policies/", "Corporate Policies"),
            ("https://www.nvidia.com/en-us/product-security/", "Product Security"),
            ("https://www.nvidia.com/en-us/contact/", "Contact"),
        ]
        for directory in sources:
            self.assertTrue(directory.is_dir(), str(directory))
            pages = sorted(directory.glob("*.html"))
            self.assertTrue(pages, f"no course pages in {directory}")
            for page in pages:
                for full in (False, True):
                    with self.subTest(page=str(page), full=full):
                        result = bundle_one(page, "", "", "", full=full)
                        footers = re.findall(
                            r'<footer class="nvidia-policy-footer">(.*?)</footer>',
                            result, re.S,
                        )
                        self.assertEqual(len(footers), 1)
                        self.assertIn('aria-label="NVIDIA legal and policies"', footers[0])
                        self.assertEqual(re.findall(r'<a href="([^"]+)">([^<]+)</a>', footers[0]), expected)
                        self.assertLess(result.index(footers[0]), result.index("</body>"))
                        self.assertNotIn("<script", footers[0])
                        stub = 'https://cdn.cookielaw.org/scripttemplates/otSDKStub.js'
                        custom = 'https://images.nvidia.com/aem-dam/Solutions/ot-js/ot-custom.js'
                        tenant = '01a13400-6831-707e-9897-c2ef6262efc7'
                        self.assertEqual(result.count(stub), 1)
                        self.assertEqual(result.count(custom), 1)
                        self.assertEqual(result.count("stub.setAttribute('data-domain-script', '" + tenant + "')"), 1)
                        self.assertIn("location.protocol !== 'https:' || location.hostname !== 'nvdli.github.io'", result)
                        self.assertLess(result.index('function OptanonWrapper()'), result.index(stub))
                        self.assertLess(result.index(stub), result.index(custom))
                        self.assertLess(result.index(custom), result.index('</head>'))
                        self.assertIn("new Event('bannerLoaded')", result)
                        self.assertIn("window.dispatchEvent(new Event('bannerLoaded'))", result)
                        source = page.read_text(encoding="utf-8")
                        for footer in re.findall(r"<footer>.*?</footer>", source, re.S):
                            self.assertIn(footer, result)


if __name__ == "__main__":
    unittest.main()
