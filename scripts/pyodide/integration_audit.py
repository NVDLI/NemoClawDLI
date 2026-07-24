#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Audit Pyodide runtime adoption, distribution boundaries, and review evidence."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "scripts/pyodide/candidate-components.json"
BLUEPRINT = ROOT / "scripts/pyodide/integration-blueprint.md"
SKILL = ROOT / "scripts/pyodide/SKILL.html"
THIRD_PARTY = ROOT / "THIRD_PARTY_LICENSES.md"
CELL_EXAMPLES = ROOT / "scripts/pyodide/examples/cell-examples.js"
LIVE_PLAYGROUND = ROOT / "scripts/pyodide/examples/live-playground.js"
NOTEBOOK_EDITOR = ROOT / "scripts/pyodide/examples/notebook-editor.js"
EXECUTION_CONTRACT = ROOT / "scripts/pyodide/examples/execution-contract.js"
NOTEBOOK_SYNTAX = ROOT / "scripts/pyodide/examples/notebook-syntax.js"
RUNTIME_SMOKE = ROOT / "scripts/pyodide/runtime_smoke.mjs"
USE_CASES = ROOT / "scripts/pyodide/cookbook-use-cases.json"
SHARED_WORKBENCH = ROOT / "web/shared/runtime-workbench.js"
SHARED_WORKBENCH_STYLES = ROOT / "web/shared/runtime-workbench.css"

# These are the only core filenames evaluated from Pyodide's npm release.
# A new filename changes the browser artifact even when the version does not.
EXPECTED_CORE_ASSETS = {
    "pyodide.mjs",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
}
EXPECTED_LIVE_CORE_ASSETS = EXPECTED_CORE_ASSETS | {"pyodide.js"}

# Profiles encode distribution roles.
# They separate npm build input, core runtime, and optional network packages.
PROFILE_LABELS = {
    "acquisition": "Future asset preparation",
    "core": "Separate demonstration runtime",
    "network": "Future HTTP/API support",
}
PROFILE_RELATIONSHIPS = {
    "acquisition": {"build-input"},
    "core": {"runtime-core"},
    "network": {"direct", "transitive"},
}

EXAMPLE_MARKERS = {
    "examples/runtime-loader.js": ("loadRuntime", "pyodide.mjs", "indexURL"),
    "examples/python-worker.js": (
        "runCell", "stdout", "stderr", "value", "display", "executionCount",
        "__course_scope", "addEventListener", "PYODIDE_EXECUTION_CONTRACT",
    ),
    "examples/execution-contract.js": (
        "display_markdown", "display_html", "display_json", "display_code", "display_table",
        "application/json", "text/x-code", "DISPLAY_WIDTH = 100", "pprint.pformat",
        "_structured_json_value", "model_dump", "dataclasses.is_dataclass",
        "error_line", "PyCF_ALLOW_TOP_LEVEL_AWAIT", "__course_helper_overrides", "definitionSource",
        "display_artifact", "application/x-course-artifact+json", "register_background",
        "background_status", "wait_background", "cancel_background", "__course_background_tasks",
    ),
    "examples/notebook-syntax.js": (
        "PYODIDE_NOTEBOOK_SYNTAX", "value? / value??", "browser_shell", "inspect_object",
        'name === "who"', 'name === "whos"', 'name === "magic"', 'text.startsWith("%%bash\\n")',
    ),
    "examples/worker-client.js": ("class PythonRunner", "reset()", "stop()", "setTimeout"),
    "examples/network-fetch.js": ("createCourseFetch", "allowedOrigins", "relayUrl"),
    "examples/learner-cell.py": ("inputs", "result"),
    "examples/cell-examples.js": (
        "PYODIDE_CELL_EXAMPLES", "chat-app", "agent-loop", "mcp", "background-job", "artifact-generation",
    ),
    "examples/notebook-editor.js": (
        'defineMode("course-python"', 'mode: "course-python"', "CodeMirror.fromTextArea",
        "lineNumbers", "lineWrapping: true", "Shift-Enter", "Ctrl-Enter", "Cmd-Enter",
        '"Ctrl-/"', '"Cmd-/"', '"Shift-Tab"', "showError", "py-code-error-line",
    ),
    "examples/live-playground.js": (
        "new Worker", "runAll", "runRepl", "data-python-cells", "runtimeMounted",
        "PYODIDE_NOTEBOOK_EDITOR", "__course_scope", "execution_count", "courseStreamChat",
        "courseWebSocketRoundTrip", "sanitizeRichOutput", "BLOCKED_RICH_TAGS", "makeDisplayNode",
        "application/json", "highlightElement", "applyHelper", "helperEditors", "py-artifact-output",
        "data-artifact-url", "error_line", "wb-cell-workspace", "pyodide:status",
        "dli-pyodide-reference",
    ),
}

# These sentences are safety claims, not writing prompts.
# The audit aligns the blueprint with the machine-readable state boundary.
REQUIRED_BLUEPRINT_TEXT = (
    "The repository does not copy Pyodide",
    "Start with the browser-only runtime. Add the HTTP/API package set only when a named lesson requires outbound requests",
    "Do not use unrestricted `micropip.install()`",
    "Stop terminates the worker. Reset starts a new worker",
    "Pyodide follows browser networking rules.",
    "must not contain a deployment URL",
    "human-approval-required",
    "does not approve the candidate",
)

# A planned-only candidate must not appear in learner source by accident.
# These markers identify a loader or runtime asset, not a prose reference.
RUNTIME_MARKERS = (
    "loadPyodide(",
    "assets/pyodide/",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
)


def source_paths() -> list[str]:
    # Include untracked proposal files so the local gate sees a runtime before commit.
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(item.decode() for item in result.stdout.split(b"\0") if item)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_digest(data: dict) -> str:
    """Bind the reviewed runtime facts, profiles, assets, and components as one record."""
    fields = ("source_pattern", "runtime", "live_demo", "profiles", "core_assets", "live_core_assets", "components")
    payload = {field: data.get(field) for field in fields}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def component_findings(item: dict, third_party: str) -> list[str]:
    """Validate one serialized component and both human-readable projections."""
    findings: list[str] = []
    name = str(item.get("name", ""))
    version = str(item.get("version", ""))
    license_expression = str(item.get("license_expression", ""))
    profile = str(item.get("profile", ""))
    relationship = str(item.get("relationship", ""))

    if not name or not version:
        findings.append("Pyodide candidate component lacks a name or version")
    if profile not in PROFILE_LABELS:
        findings.append(f"Pyodide candidate component has an unknown profile: {name}")
    elif relationship not in PROFILE_RELATIONSHIPS[profile]:
        findings.append(f"Pyodide candidate component relationship does not match its profile: {name}")
    if license_expression in {"", "NOASSERTION"}:
        findings.append(f"Pyodide candidate component license is unresolved: {name}")

    evidence = urlparse(str(item.get("license_evidence_url", "")))
    if evidence.scheme != "https" or not evidence.netloc:
        findings.append(f"Pyodide candidate lacks HTTPS license evidence: {name}")
    if profile == "network" and not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
        findings.append(f"Pyodide candidate artifact hash missing or malformed: {name}")
    if profile == "acquisition" and not str(item.get("integrity", "")).startswith("sha512-"):
        findings.append(f"Pyodide npm build input lacks its lockfile integrity: {name}")

    profile_label = PROFILE_LABELS.get(profile, profile)
    inventory_row = f"| {profile_label} | {name} | {version} | {license_expression} |"
    if inventory_row not in third_party:
        findings.append(f"third-party inventory omits Pyodide candidate component: {name}")
    return findings


def audit(
    data: dict | None = None,
    blueprint: str | None = None,
    skill: str | None = None,
    paths: list[str] | None = None,
    runtime_texts: dict[str, str] | None = None,
    implementation_texts: dict[str, str] | None = None,
    use_cases: dict | None = None,
) -> list[str]:
    findings: list[str] = []
    try:
        data = read_json(MANIFEST) if data is None else data
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read Pyodide candidate inventory: {exc}"]
    try:
        blueprint = BLUEPRINT.read_text(encoding="utf-8") if blueprint is None else blueprint
        skill = SKILL.read_text(encoding="utf-8") if skill is None else skill
        third_party = THIRD_PARTY.read_text(encoding="utf-8")
        use_cases = read_json(USE_CASES) if use_cases is None else use_cases
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read Pyodide integration documentation: {exc}"]

    # The status fields prevent design evidence from being mistaken for approval.
    if data.get("schema") != "pyodide-candidate-components/1.0":
        findings.append("Pyodide candidate inventory schema is missing or unsupported")
    if data.get("status") != "runtime-fetch-only":
        findings.append("Pyodide inventory no longer states its runtime-fetch-only boundary")
    if data.get("review_state") != "human-approval-required":
        findings.append("Pyodide candidate inventory overstates or omits human review ownership")

    # The source record describes only the local reference supplied for this task.
    # It must not invent a publication URL or claim that reference files were copied.
    source = data.get("source_pattern") or {}
    if source.get("kind") != "task-supplied-local-reference":
        findings.append("Pyodide example provenance no longer identifies the task-supplied local reference")
    if "repository" in source or "commit" in source:
        findings.append("Pyodide example provenance invents an external repository identity")
    if source.get("relationship") != "behavior synthesized into course-authored examples; no reference file or binary copied":
        findings.append("Pyodide source relationship no longer distinguishes synthesis from copying")
    if source.get("license") != "MIT" or source.get("license_evidence") != "LICENSE file in the task-supplied local reference tree":
        findings.append("Pyodide local reference license evidence drifted")
    expected_reference_files = {
        "scripts/vendor-pyodide.mjs",
        "src/components/interactive-code/python-worker.ts",
        "src/components/interactive-code/client.ts",
        "src/components/interactive-code/proxy-fetch.ts",
        "public/assets/pyodide/0.27.7/pyodide-lock.json",
    }
    if set(source.get("files_reviewed") or []) != expected_reference_files:
        findings.append("Pyodide local reference file list drifted")

    # Runtime facts are the compatibility tuple behind every selected wheel.
    runtime = data.get("runtime") or {}
    required_runtime = {
        "pyodide": "0.27.7",
        "python": "3.12.7",
        "abi": "2024_0",
        "architecture": "wasm32",
        "platform": "emscripten_3_1_58",
    }
    for key, expected in required_runtime.items():
        if runtime.get(key) != expected:
            findings.append(f"Pyodide runtime fact drifted: {key}")
    live_demo = data.get("live_demo") or {}
    if live_demo.get("base_url") != "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/":
        findings.append("Pyodide live demo CDN or pinned version drifted")
    if live_demo.get("profile") != "core" or "not copied into this repository" not in str(live_demo.get("distribution", "")):
        findings.append("Pyodide live demo distribution boundary drifted")
    # Validate every serialized component uniformly.
    # The digest catches changes without a second package list in code.
    components = data.get("components") or []
    index = {item.get("name"): item for item in components if isinstance(item, dict)}
    if len(index) != len(components):
        findings.append("Pyodide candidate component names are missing or duplicated")
    for item in index.values():
        findings.extend(component_findings(item, third_party))

    # One digest binds the profile graph, component records, and exact assets.
    reviewed_snapshot = str(data.get("reviewed_snapshot_sha256", ""))
    if reviewed_snapshot != snapshot_digest(data):
        findings.append("Pyodide candidate component snapshot changed without a reviewed digest update")

    # Preserve the known recipe-versus-upstream discrepancy as a named review item.
    openssl = index.get("openssl", {})
    if openssl.get("version") != "1.1.1w" or openssl.get("license_expression") != "OpenSSL":
        findings.append("OpenSSL 1.1.1w legacy license disposition drifted")
    if "metadata conflict" not in str(openssl.get("review_note", "")):
        findings.append("OpenSSL recipe metadata conflict is no longer recorded")

    ssl = index.get("ssl", {})
    if ssl.get("license_expression") != "PSF-2.0 AND OpenSSL":
        findings.append("Pyodide ssl module no longer records both source license families")

    # Core hashes refer to the evaluated local reference output.
    assets = data.get("core_assets") or []
    asset_index = {item.get("file"): item for item in assets if isinstance(item, dict)}
    if set(asset_index) != EXPECTED_CORE_ASSETS:
        findings.append("Pyodide core asset set drifted")
    for name, item in asset_index.items():
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            findings.append(f"Pyodide core asset hash missing or malformed: {name}")
    live_assets = data.get("live_core_assets") or []
    live_asset_index = {item.get("file"): item for item in live_assets if isinstance(item, dict)}
    if set(live_asset_index) != EXPECTED_LIVE_CORE_ASSETS:
        findings.append("Pyodide live core asset set drifted")
    for name, item in live_asset_index.items():
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))):
            findings.append(f"Pyodide live core asset hash missing or malformed: {name}")

    # Profile membership must agree in both directions with component records.
    profiles = data.get("profiles") or {}
    acquisition = set((profiles.get("acquisition") or {}).get("components") or [])
    core = set((profiles.get("core") or {}).get("components") or [])
    network = set((profiles.get("network") or {}).get("components") or [])
    roots = set((profiles.get("network") or {}).get("root_packages") or [])
    profiled = {
        profile: {name for name, item in index.items() if item.get("profile") == profile}
        for profile in PROFILE_LABELS
    }
    if acquisition != profiled["acquisition"]:
        findings.append("Pyodide acquisition profile does not match its component records")
    if core != {"pyodide", "cpython-standard-library"}:
        findings.append("Pyodide Core profile is not the minimal evaluated runtime")
    if core != profiled["core"]:
        findings.append("Pyodide Core profile does not match its component records")
    if network != profiled["network"]:
        findings.append("Pyodide network profile does not match its component records")
    direct_network = {name for name in network if index.get(name, {}).get("relationship") == "direct"}
    if roots != direct_network:
        findings.append("Pyodide network root packages do not match direct component records")

    # Human pages must expose the same boundary and every component name.
    normalized_blueprint = " ".join(blueprint.split())
    normalized_data = " ".join(json.dumps(data).split())
    for phrase in REQUIRED_BLUEPRINT_TEXT:
        if phrase not in normalized_blueprint and phrase not in normalized_data:
            findings.append(f"Pyodide integration boundary is undocumented: {phrase}")
    for phrase in (
        "Pyodide code cookbook", "persistent Python kernel in a Web Worker", "Scratch REPL",
        "syntax-highlighted cells", "Shift+Enter", "Jupyter-style execution prompts",
        "Run all 12 cells", "Run intentional error", "Stop", "Reset runtime",
        "build.nvidia.com", "HTTP Server-Sent Events", "WebSocket", "display_markdown()", "display_json()",
        "display_code()", "display_table()", "display_artifact()", "register_background()",
        "select a row to edit its real source",
        "runtime-loader.js", "python-worker.js", "worker-client.js",
        "network-fetch.js", "learner-cell.py", "data-reference-workbench",
    ):
        if phrase not in skill:
            findings.append(f"Pyodide SKILL page is missing its code-first contract: {phrase}")

    for relative, markers in EXAMPLE_MARKERS.items():
        example_path = SKILL.parent / relative
        try:
            example_text = example_path.read_text(encoding="utf-8")
        except OSError:
            findings.append(f"Pyodide example is missing: {relative}")
            continue
        for marker in markers:
            if marker not in example_text:
                findings.append(f"Pyodide example lost required behavior: {relative}: {marker}")

    if implementation_texts is None:
        try:
            implementation_texts = {
                "cells": CELL_EXAMPLES.read_text(encoding="utf-8"),
                "editor": NOTEBOOK_EDITOR.read_text(encoding="utf-8"),
                "playground": LIVE_PLAYGROUND.read_text(encoding="utf-8"),
                "contract": EXECUTION_CONTRACT.read_text(encoding="utf-8"),
                "syntax": NOTEBOOK_SYNTAX.read_text(encoding="utf-8"),
                "smoke": RUNTIME_SMOKE.read_text(encoding="utf-8"),
                "workbench": skill,
                "workbench_controller": SHARED_WORKBENCH.read_text(encoding="utf-8"),
                "workbench_styles": SHARED_WORKBENCH_STYLES.read_text(encoding="utf-8"),
            }
        except OSError as exc:
            findings.append(f"cannot read executable Pyodide contract: {exc}")
            implementation_texts = {}
    cells_source = implementation_texts.get("cells", "")
    editor_source = implementation_texts.get("editor", "")
    playground_source = implementation_texts.get("playground", "")
    contract_source = implementation_texts.get("contract", "")
    syntax_source = implementation_texts.get("syntax", "")
    smoke_source = implementation_texts.get("smoke", "")
    workbench_source = implementation_texts.get("workbench", "")
    workbench_controller = implementation_texts.get("workbench_controller", "")
    workbench_styles = implementation_texts.get("workbench_styles", "")
    example_ids = re.findall(r'^\s+id:\s+"([a-z0-9-]+)"', cells_source, re.M)
    if len(example_ids) < 8 or len(example_ids) != len(set(example_ids)):
        findings.append("Pyodide cookbook needs at least eight uniquely identified progressive cells")
    if use_cases.get("schema") != "pyodide-cookbook-use-cases/1.0":
        findings.append("Pyodide cookbook use-case inventory schema is missing or unsupported")
    serialized_cases = use_cases.get("cases") or []
    mapped_examples = set()
    required_coverage = set()
    for case in serialized_cases:
        case_id = str(case.get("id", ""))
        examples = set(case.get("examples") or [])
        coverage = set(case.get("required_coverage") or [])
        if not case_id or not case.get("label") or not case.get("evidence") or not examples or not coverage:
            findings.append(f"Pyodide cookbook use case is incomplete: {case_id or '<missing id>'}")
        if not examples.issubset(example_ids):
            findings.append(f"Pyodide cookbook use case maps to a missing cell: {case_id}")
        if case_id not in skill:
            findings.append(f"Pyodide SKILL page omits cookbook use-case evidence: {case_id}")
        mapped_examples.update(examples)
        required_coverage.update(coverage)
    if set(example_ids) != mapped_examples:
        findings.append("Pyodide progressive cells and serialized cookbook mappings disagree")
    for use_case in sorted(required_coverage):
        if f'"{use_case}"' not in cells_source:
            findings.append(f"Pyodide progressive cells omit cookbook use case: {use_case}")
    for marker in (
        "https://cdn.jsdelivr.net/pyodide/v", "fetch(BASE_URL", "pyodide.js", "new Worker", "data-python-cells",
        "reply.stdout", "reply.stderr", "reply.value", 'action === "stop"',
        'action === "reset"', "runAll", "runRepl", "user_input", "history",
        "PYODIDE_NOTEBOOK_EDITOR", "__course_scope", "execution_count",
        "reply.display", "Out[", "data-repl-transcript", "courseStreamChat",
        "courseWebSocketRoundTrip", "sanitizeRichOutput", "BLOCKED_RICH_TAGS", "display_type", "error_line",
        "makeDisplayNode", "highlightElement", "applyHelper", "helperEditors",
        "application/x-course-artifact+json", "py-artifact-output", "data-artifact-url",
    ):
        if marker not in playground_source:
            findings.append(f"Pyodide browser runner lost executable behavior: {marker}")
    for marker in (
        "display_json", "display_code", "display_table", "application/json", "text/x-code",
        "display_artifact", "application/x-course-artifact+json", "register_background",
        "background_status", "wait_background", "cancel_background", "__course_background_tasks",
        "DISPLAY_WIDTH = 100", "__course_helper_overrides", "definitionSource", "inspect_object",
        "browser_shell", "notebook_who", "notebook_time", "notebook_magic",
        "_structured_json_value", "model_dump", "dataclasses.is_dataclass",
    ):
        if marker not in contract_source:
            findings.append(f"Pyodide execution contract lost display behavior: {marker}")
    for marker in ("PYODIDE_NOTEBOOK_SYNTAX", "normalizeLine", "%%bash", "value? / value??", "%magic"):
        if marker not in syntax_source:
            findings.append(f"Pyodide notebook syntax lost executable behavior: {marker}")
    markdown_helper = re.search(r"def display_markdown\(source\):(?P<body>.*?)(?=\ndef display_html)", contract_source, re.S)
    if not markdown_helper or not all(
        marker in markdown_helper.group("body") for marker in ("course_displays.append", '"type": "text/markdown"', '"data": str(source)')
    ):
        findings.append("Pyodide Markdown helper hides its output contract behind unrelated helpers")
    if "display(Markdown(source))" in contract_source:
        findings.append("Pyodide Markdown helper still relies on an opaque wrapper chain")
    for marker in (
        "CodeMirror.fromTextArea", 'mode: "course-python"', "lineNumbers: true",
        '"Shift-Enter"', '"Ctrl-Enter"', '"Cmd-Enter"', '"Ctrl-/"', '"Shift-Tab"',
        "lineWrapping: true", "PYODIDE_NOTEBOOK_EDITOR",
        "showError", "clearError", "py-code-error-line",
    ):
        if marker not in editor_source:
            findings.append(f"Pyodide notebook editor lost executable behavior: {marker}")
    for marker in (
        "EXAMPLES.length < 8", "for (const example of EXAMPLES)",
        "outputReply.stdout", "errorReply.stderr.includes(\"IndexError\")",
        "SHA-256 mismatch", "expressionReply.display", "stateNext.display",
        "execution counter did not persist", "prettyReply.display_type", "richReply.displays",
        "errorReply.error_line !== 2", "Editable helper override did not persist",
        "Notebook ?? inspection did not resolve a persistent value", "Bounded browser-shell pipeline did not execute",
        "Background registration did not produce the downloadable JSON artifact",
        "Background cancellation did not settle the registered task",
    ):
        if marker not in smoke_source:
            findings.append(f"Pyodide runtime verifier lost an assertion: {marker}")
    for marker in (
        "pyodide-playground", "data-python-cells", "data-reference-workbench",
        "data-workbench-view", "data-workbench-content", "data-python-diagnostic",
        "examples/live-playground.js", "runtime-workbench.js",
    ):
        if marker not in workbench_source:
            findings.append(f"Pyodide course workbench reference lost executable behavior: {marker}")
    for marker in (
        "mountRuntimeWorkbench", "setSelection", "returnFocus", 'event.key !== "Escape"',
        "workbench:viewchange",
    ):
        if marker not in workbench_controller:
            findings.append(f"shared runtime workbench lost accessible behavior: {marker}")
    for marker in ("--wb-panel: var(--e1", "--wb-text: var(--tx", "color: var(--wb-muted)"):
        if marker not in workbench_styles:
            findings.append(f"shared runtime workbench lost cross-surface theme behavior: {marker}")
    for marker in ('cell.output.dataset.state = "empty"', 'cell.output.dataset.state = "rendered"'):
        if marker not in playground_source:
            findings.append(f"Pyodide reset/output state lost its explicit contract: {marker}")

    # Path scans reject copied runtime binaries outside the reviewed integration evidence.
    paths = source_paths() if paths is None else paths
    for path in paths:
        if path.startswith("scripts/pyodide/"):
            continue
        lowered = path.lower()
        if lowered.endswith(".whl"):
            findings.append(f"unlocked browser Python wheel appeared: {path}")
        elif "pyodide" in lowered and lowered.endswith((".wasm", ".zip", "pyodide.mjs")):
            findings.append(f"Pyodide runtime artifact appeared outside the planned integration area: {path}")

    if runtime_texts is None:
        runtime_texts = {}
        for path in paths:
            if not path.startswith(("web/", "i18n/")) or not path.endswith((".html", ".js", ".mjs", ".json")):
                continue
            try:
                runtime_texts[path] = (ROOT / path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    for path, text in runtime_texts.items():
        if any(marker in text for marker in RUNTIME_MARKERS):
            findings.append(f"course source loads Pyodide outside the reviewed integration area: {path}")
    return findings


def self_test() -> list[str]:
    base = read_json(MANIFEST)
    blueprint = BLUEPRINT.read_text(encoding="utf-8")
    skill = SKILL.read_text(encoding="utf-8")
    failures: list[str] = []

    implementation = {
        "cells": CELL_EXAMPLES.read_text(encoding="utf-8"),
        "editor": NOTEBOOK_EDITOR.read_text(encoding="utf-8"),
        "playground": LIVE_PLAYGROUND.read_text(encoding="utf-8"),
        "contract": EXECUTION_CONTRACT.read_text(encoding="utf-8"),
        "syntax": NOTEBOOK_SYNTAX.read_text(encoding="utf-8"),
        "smoke": RUNTIME_SMOKE.read_text(encoding="utf-8"),
        "workbench": skill,
        "workbench_controller": SHARED_WORKBENCH.read_text(encoding="utf-8"),
        "workbench_styles": SHARED_WORKBENCH_STYLES.read_text(encoding="utf-8"),
    }

    use_cases = read_json(USE_CASES)
    if audit(base, blueprint, skill, [], {}, implementation, use_cases):
        failures.append("baseline candidate inventory did not pass")

    # Mutations cover scope, package, license, integrity, runtime, and approval drift.
    cases = []
    changed = copy.deepcopy(base)
    changed["status"] = "repository-copied"
    cases.append(("distribution status", changed, blueprint, skill, [], {}, implementation, use_cases))
    changed = copy.deepcopy(base)
    changed["components"] = changed["components"][:-1]
    cases.append(("missing component", changed, blueprint, skill, [], {}, implementation, use_cases))
    changed = copy.deepcopy(base)
    changed["components"][0]["license_expression"] = "NOASSERTION"
    cases.append(("license drift", changed, blueprint, skill, [], {}, implementation, use_cases))
    changed = copy.deepcopy(base)
    next(item for item in changed["components"] if item["name"] == "annotated-types")["sha256"] = "short"
    cases.append(("hash drift", changed, blueprint, skill, [], {}, implementation, use_cases))
    cases.append(("runtime artifact", base, blueprint, skill, ["web/nemoclaw/pyodide.asm.wasm"], {}, implementation, use_cases))
    cases.append(("runtime loader", base, blueprint, skill, [], {"web/nemoclaw/example.js": "loadPyodide({})"}, implementation, use_cases))
    changed = copy.deepcopy(base)
    changed["review_state"] = "approved"
    cases.append(("approval overclaim", changed, blueprint, skill, [], {}, implementation, use_cases))
    broken = dict(implementation)
    broken["cells"] = broken["cells"].replace('id: "chat-app"', 'legacy: "chat-app"')
    cases.append(("too few progressive cells", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["playground"] = broken["playground"].replace('action === "stop"', 'action === "halt"')
    cases.append(("missing stop control", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["smoke"] = broken["smoke"].replace('errorReply.stderr.includes("IndexError")', 'Boolean(errorReply.stderr)')
    cases.append(("missing traceback assertion", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["editor"] = broken["editor"].replace('mode: "course-python"', 'mode: null')
    cases.append(("missing syntax highlighting", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["smoke"] = broken["smoke"].replace("stateNext.display !== \"42\"", "false")
    cases.append(("missing persistent namespace assertion", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["editor"] = broken["editor"].replace("py-code-error-line", "removed-error-line")
    cases.append(("missing source-line highlight", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["playground"] = broken["playground"].replace("courseStreamChat", "removed_stream")
    cases.append(("missing NVIDIA stream", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["playground"] = broken["playground"].replace("courseWebSocketRoundTrip", "removed_socket")
    cases.append(("missing WebSocket transport", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["contract"] = broken["contract"].replace("__course_helper_overrides", "removed_helper_overrides")
    cases.append(("missing editable helper contract", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["contract"] = broken["contract"].replace("display_artifact", "removed_artifact_helper")
    cases.append(("missing artifact helper", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["contract"] = broken["contract"].replace("register_background", "removed_background_helper")
    cases.append(("missing background helper", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["contract"] = broken["contract"].replace("_structured_json_value", "object_formatter_removed")
    cases.append(("missing structured object display", base, blueprint, skill, [], {}, broken, use_cases))
    broken = dict(implementation)
    broken["workbench"] = broken["workbench"].replace("data-workbench-view", "removed-workbench-view")
    cases.append(("missing course workbench controls", base, blueprint, skill, [], {}, broken, use_cases))

    changed_cases = copy.deepcopy(use_cases)
    changed_cases["cases"][0]["examples"].append("missing-cell")
    cases.append(("missing use-case cell", base, blueprint, skill, [], {}, implementation, changed_cases))

    for label, data, doc, page, paths, texts, impl, mapping in cases:
        if not audit(data, doc, page, paths, texts, impl, mapping):
            failures.append(f"mutation was not detected: {label}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = self_test() if args.self_test else audit()
    if args.json:
        print(json.dumps({"findings": findings}, indent=2))
    else:
        label = "Pyodide integration audit self-test" if args.self_test else "Pyodide integration audit"
        print(f"{label}: {'FAIL' if findings else 'PASS'}")
        for finding in findings:
            print(f"  - {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
