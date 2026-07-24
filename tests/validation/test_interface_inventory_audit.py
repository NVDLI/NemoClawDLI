# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.validation import interface_inventory_audit as audit
from scripts.validation import interface_inventory_browser_audit as browser_audit


class InterfaceInventoryAuditTests(unittest.TestCase):
    def runtime_surfaces(self, form_factor: str, relative_script: str) -> list[tuple[dict, str]]:
        surfaces: list[tuple[dict, str]] = []
        for inventory_path in sorted((audit.ROOT / "web").glob("*/interface-inventory.json")):
            contract = json.loads(inventory_path.read_text(encoding="utf-8"))
            script_path = inventory_path.parent / relative_script
            if form_factor in contract.get("form_factors", {}) and script_path.is_file():
                surfaces.append((contract, script_path.read_text(encoding="utf-8")))
        self.assertTrue(surfaces, f"no discovered {form_factor} runtime surface")
        return surfaces

    def fixture(self) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="interface-inventory-"))
        course = directory / "web" / "sample"
        course.mkdir(parents=True)
        contract = {
            "schema": audit.SCHEMA,
            "course": "sample",
            "discovery": {"html": "all", "mount_calls": "all", "markers": "all"},
            "factory_profiles": {"mountRunCell": "editable-code-cell"},
            "marker_profiles": {"nav": "navigation"},
            "form_factors": {
                "editable-code-cell": {"states": ["ready", "failed"], "authority": "bounded-browser"},
                "navigation": {"states": ["ready", "failed"], "authority": "none"},
            },
            "validation_profile": ["editable-code-cells"],
            "live_capabilities": [],
        }
        (course / "interface-inventory.json").write_text(json.dumps(contract), encoding="utf-8")
        (course / "SKILL.html").write_text(
            '<script id="skill-meta" type="application/json">'
            + json.dumps({
                "interface_inventory": {"schema": audit.SCHEMA, "source": "interface-inventory.json"},
                "validation_profile": {"schema": audit.VALIDATION_PROFILE_SCHEMA, "form_factors": ["editable-code-cells"]},
            })
            + '</script><a href="interface-inventory.json">Interface inventory</a>',
            encoding="utf-8",
        )
        (course / "lesson.html").write_text(
            '<div id="cell"></div><nav id="nav" data-dli-interface="nav">Next</nav>'
            '<script>mountRunCell("#cell", {});</script>', encoding="utf-8",
        )
        return directory

    def test_clean_discovered_contract(self) -> None:
        findings, instances = audit.audit(self.fixture())
        self.assertEqual([], findings)
        self.assertEqual(2, len(instances))

    def test_built_candidate_uses_validated_source_projection(self) -> None:
        root = self.fixture()
        projected = root / "validated-source"
        projected.mkdir()
        shutil.move(str(root / "web"), str(projected / "web"))
        findings, instances = audit.audit(root)
        self.assertEqual([], findings)
        self.assertEqual(2, len(instances))

    def test_unknown_mount_factory_is_rejected(self) -> None:
        root = self.fixture()
        page = root / "web/sample/lesson.html"
        page.write_text(page.read_text().replace("mountRunCell", "mountMystery"), encoding="utf-8")
        findings, _ = audit.audit(root)
        self.assertTrue(any("undeclared mount factory" in item for item in findings))

    def test_orphan_interface_root_is_rejected(self) -> None:
        root = self.fixture()
        page = root / "web/sample/lesson.html"
        page.write_text(page.read_text().replace('<div id="cell"></div>', '<div id="cell"></div><div id="policy-map"></div>'), encoding="utf-8")
        findings, _ = audit.audit(root)
        self.assertTrue(any("empty interface-like root #policy-map" in item for item in findings))

    def test_opt_out_vocabulary_is_rejected(self) -> None:
        root = self.fixture()
        path = root / "web/sample/interface-inventory.json"
        contract = json.loads(path.read_text())
        contract["exclude"] = ["lesson.html"]
        path.write_text(json.dumps(contract), encoding="utf-8")
        findings, _ = audit.audit(root)
        self.assertTrue(any("opt-out vocabulary" in item for item in findings))

    def test_missing_skill_binding_is_rejected(self) -> None:
        root = self.fixture()
        skill = root / "web/sample/SKILL.html"
        skill.write_text('<script id="skill-meta" type="application/json">{}</script>', encoding="utf-8")
        findings, _ = audit.audit(root)
        self.assertTrue(any("skill-meta does not bind" in item for item in findings))

    def test_new_live_transport_requires_inventory_update(self) -> None:
        root = self.fixture()
        page = root / "web/sample/lesson.html"
        page.write_text(page.read_text() + '<script>fetch("https://integrate.api.nvidia.com/v1/models")</script>')
        findings, _ = audit.audit(root)
        self.assertTrue(any("live_capabilities" in item and "model-stream" in item for item in findings))

    def test_browser_harness_denies_candidate_egress_and_checks_every_expanded_instance(self) -> None:
        source = browser_audit.RUNTIME
        self.assertIn("serviceWorkers:'block'", source)
        self.assertIn("route.abort('blockedbyclient')", source)
        self.assertIn("routeWebSocket('**/*'", source)
        self.assertIn("checked.length !== inventory.instances.length", source)
        self.assertIn("for (const theme of ['light','dark'])", source)

    def test_browser_harness_exercises_each_form_factor_and_requires_a_state_transition(self) -> None:
        source = browser_audit.RUNTIME
        self.assertIn("async function exercise(locator, profile, id)", source)
        self.assertIn("action.click()", source)
        self.assertIn("action produced no observable state transition", source)
        self.assertIn("not every discovered form factor was exercised", source)
        self.assertIn("exercised.size !== factors.length", source)

    def test_browser_harness_does_not_infer_state_from_arbitrary_page_prose(self) -> None:
        source = browser_audit.RUNTIME
        self.assertIn("node.getAttribute?.('role') === 'status'", source)
        self.assertNotIn("`${node.className || ''} ${node.textContent || ''}`", source)

    def test_editable_cells_emit_their_declared_lifecycle(self) -> None:
        for contract, source in self.runtime_surfaces("editable-code-cell", "scripts/_canvas.js"):
            declared = set(contract["form_factors"]["editable-code-cell"]["states"])
            emitted = set(re.findall(r'setCellState\("([a-z-]+)"\)', source))
            self.assertEqual({"ready", "running", "stopped", "succeeded", "failed", "reset"}, declared)
            self.assertTrue(declared.issubset(emitted))

    def test_ordered_flows_emit_observable_lifecycle_states(self) -> None:
        expected = {"ready", "running", "stopped", "succeeded", "failed", "reset"}
        for _, source in self.runtime_surfaces("ordered-flow", "scripts/_canvas.js"):
            emitted = set(re.findall(r'setFlowState\("([a-z-]+)"\)', source))
            self.assertEqual(expected, emitted)

    def test_credential_controls_emit_semantic_connection_states(self) -> None:
        for contract, source in self.runtime_surfaces("credential-controls", "scripts/_keypanel.js"):
            emitted = set(re.findall(r'_setState\("([a-z-]+)"\)', source)) | {"ready", "empty"}
            declared = set(contract["form_factors"]["credential-controls"]["states"])
            self.assertIn('_setState(keySaved ? "ready" : "empty")', source)
            self.assertTrue(declared.issubset(emitted))

    def test_deferred_interface_runs_trigger_then_exercises_mounted_widget(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="deferred-interface-browser-"))
        self.addCleanup(shutil.rmtree, root)
        course = root / "web/sample"
        course.mkdir(parents=True)
        contract = {
            "schema": audit.SCHEMA,
            "course": "sample",
            "discovery": {"html": "all", "mount_calls": "all", "markers": "all"},
            "factory_profiles": {}, "marker_profiles": {},
            "form_factors": {
                "streaming-chat": {
                    "states": ["ready", "running", "failed"],
                    "authority": "bounded-browser",
                },
            },
            "instance_templates": [{
                "id": "sample.chat", "source": "course.json", "kind": "course-cell-id",
                "value": "lesson:1", "form_factor": "streaming-chat", "selector": ".course-chat",
                "mount_probe": {
                    "mode": "return-node",
                    "module": "course.js", "export": "renderDisplay",
                    "argument": {"type": "application/x-course-chat+json", "data": "{}"},
                },
            }],
            "validation_profile": ["browser-course"], "live_capabilities": [],
        }
        (course / "interface-inventory.json").write_text(json.dumps(contract), encoding="utf-8")
        (course / "course.json").write_text(json.dumps({
            "lessons": [{"id": "lesson", "cells": [{"id": "lesson:1", "type": "code"}]}],
        }), encoding="utf-8")
        (course / "SKILL.html").write_text(
            '<script id="skill-meta" type="application/json">'
            + json.dumps({
                "interface_inventory": {"schema": audit.SCHEMA, "source": "interface-inventory.json"},
                "validation_profile": {"schema": audit.VALIDATION_PROFILE_SCHEMA, "form_factors": ["browser-course"]},
            })
            + '</script><a href="interface-inventory.json">Interface inventory</a>', encoding="utf-8",
        )
        (course / "index.html").write_text(
            '<!doctype html><style>body{color:#111;background:#fff}[data-theme="dark"] body{color:#fff;background:#111}</style>'
            '<div class="xblock" data-cell-id="lesson:1" data-state="ready"><textarea>mount_chat()</textarea><button>Run</button></div>'
            '<script>document.querySelector("button").onclick=()=>document.querySelector(".xblock").dataset.state="running"</script>',
            encoding="utf-8",
        )
        (course / "course.js").write_text(
            'export function renderDisplay(){const chat=document.createElement("section");'
            'chat.className="course-chat";chat.dataset.state="ready";'
            'chat.innerHTML="<form><textarea required></textarea><button type=submit>Send</button></form>";'
            'chat.querySelector("form").onsubmit=event=>{event.preventDefault();chat.dataset.state="running"};return chat}',
            encoding="utf-8",
        )
        self.assertEqual(0, browser_audit.run(root, 30_000))

    def test_mount_probe_cannot_escape_the_course(self) -> None:
        root = self.fixture()
        contract_path = root / "web/sample/interface-inventory.json"
        contract = json.loads(contract_path.read_text())
        contract["instance_templates"] = [{
            "id": "sample.chat", "source": "course.json", "kind": "course-cell-id",
            "value": "sample:1", "form_factor": "panel", "selector": ".course-chat",
            "mount_probe": {
                "mode": "return-node", "module": "../outside.js", "export": "render", "argument": {},
            },
        }]
        (root / "web/sample/course.json").write_text(json.dumps({
            "lessons": [{"id": "sample", "cells": [{"id": "sample:1", "type": "code"}]}],
        }))
        contract_path.write_text(json.dumps(contract))
        findings, _ = audit.audit(root)
        self.assertTrue(any("mount_probe module escapes" in item for item in findings))

    def test_deferred_factory_probe_mounts_the_real_course_export(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="factory-probe-browser-"))
        self.addCleanup(shutil.rmtree, root)
        course = root / "web/sample"
        course.mkdir(parents=True)
        contract = {
            "schema": audit.SCHEMA,
            "course": "sample",
            "discovery": {"html": "all", "mount_calls": "all", "markers": "all"},
            "factory_profiles": {"mountPanel": "panel"},
            "factory_mount_probes": {
                "mountPanel": {
                    "mode": "mount-target", "module": "panel.js", "export": "mountPanel", "argument": {},
                },
            },
            "marker_profiles": {},
            "form_factors": {"panel": {"states": ["ready", "selected"], "authority": "none"}},
            "validation_profile": ["browser-course"],
            "live_capabilities": [],
        }
        (course / "interface-inventory.json").write_text(json.dumps(contract), encoding="utf-8")
        (course / "SKILL.html").write_text(
            '<script id="skill-meta" type="application/json">'
            + json.dumps({
                "interface_inventory": {"schema": audit.SCHEMA, "source": "interface-inventory.json"},
                "validation_profile": {"schema": audit.VALIDATION_PROFILE_SCHEMA, "form_factors": ["browser-course"]},
            })
            + '</script><a href="interface-inventory.json">Interface inventory</a>', encoding="utf-8",
        )
        (course / "index.html").write_text(
            '<!doctype html><style>body{color:#111;background:#fff}[data-theme="dark"] body{color:#fff;background:#111}</style>'
            '<div id="panel"></div><script>window.source = \'mountPanel("#panel", {})\'</script>',
            encoding="utf-8",
        )
        (course / "panel.js").write_text(
            'export function mountPanel(root){root.dataset.state="ready";root.innerHTML="<button>Select</button>";'
            'root.querySelector("button").onclick=()=>root.dataset.state="selected"}', encoding="utf-8",
        )
        self.assertEqual(0, browser_audit.run(root, 30_000))


if __name__ == "__main__":
    unittest.main()
