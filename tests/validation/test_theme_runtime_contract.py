# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Standard-library contracts for browser-theme coverage and its CI triggers."""
from __future__ import annotations

import shlex
import tempfile
import unittest
from pathlib import Path

from scripts.skills import skill_renderer_runtime_audit as theme_runtime
from scripts.validation import (
    cell_ui_runtime_audit as cell_runtime,
    contribution_safety_audit as contribution_safety,
    helper_notebook_runtime_audit as helper_notebook,
    learner_flow_audit as learner_flow,
)


ROOT = Path(__file__).resolve().parents[2]


def ci_job(name: str) -> str:
    source = (ROOT / ".gitlab/ci/sca.yml").read_text(encoding="utf-8")
    start = source.index(f"{name}:\n")
    next_job = source.find("\nsecurity_", start + len(name) + 2)
    return source[start : next_job if next_job >= 0 else len(source)]


def core_job(name: str, next_name: str) -> str:
    source = (ROOT / ".gitlab/ci/core.yml").read_text(encoding="utf-8")
    start = source.index(f"{name}:\n")
    end = source.index(f"\n{next_name}:\n", start)
    return source[start:end]


class ThemeRuntimeContractTests(unittest.TestCase):
    def test_browser_vendor_refresh_preserves_skill_contracts(self):
        source = (ROOT / "scripts/build/vendor_browser_dependencies.mjs").read_text(encoding="utf-8")
        self.assertNotIn('fs.rmSync(vendor, { recursive: true', source)
        self.assertIn('item.name === "SKILL.html"', source)

    def test_discovery_includes_every_nested_html_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / "index.html", root / "nested" / "SKILL.html", root / "vendor" / "page.html"]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("<!doctype html><title>fixture</title>", encoding="utf-8")
            self.assertEqual(
                theme_runtime.discover_html(root),
                ["index.html", "nested/SKILL.html", "vendor/page.html"],
            )

    def test_artifact_scan_root_has_no_file_exemptions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            preview = site / "preview"
            for path in (site / "index.html", preview / "index.html", preview / "nested/page.html"):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("<!doctype html>", encoding="utf-8")
            self.assertEqual(
                ["preview/index.html", "preview/nested/page.html"],
                theme_runtime.discover_html(site, preview),
            )
            with self.assertRaises(ValueError):
                theme_runtime.discover_html(site, site.parent)

    def test_runtime_has_dark_light_dependency_detection(self) -> None:
        source = theme_runtime.RUNTIME_JS
        for token in (
            "themeSnapshot('dark')",
            "themeSnapshot('light')",
            "contrastFailures",
            "themeControl",
            "SKILL theme control is missing or ineffective",
            "figureThemeFailures",
            "same rendered SVG palette in dark and light mode",
            "data-figure-mode=\"fixed-white\"",
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn("themeCapable", source)
        self.assertNotIn("node.closest('.CodeMirror", source)

    def test_preview_serves_the_deployment_and_exhausts_its_owned_artifact(self) -> None:
        job = core_job("theme_runtime", "human_review")
        self.assertIn("THEME_SITE_ROOT=public", job)
        self.assertIn('THEME_SCAN_ROOT="public/$CI_COMMIT_REF_SLUG"', job)
        self.assertIn('--site-root "$THEME_SITE_ROOT" --scan-root "$THEME_SCAN_ROOT"', job)
        self.assertNotIn('THEME_SITE_ROOT="public/$CI_COMMIT_REF_SLUG"', job)

    def test_every_ci_renderer_command_matches_the_runtime_cli(self) -> None:
        workflow_paths = {
            *ROOT.glob(".github/workflows/*.yml"),
            *ROOT.glob(".github/workflows/*.yaml"),
            *ROOT.glob(".gitlab/**/*.yml"),
            *ROOT.glob(".gitlab/**/*.yaml"),
        }
        commands: list[tuple[Path, int, list[str]]] = []
        script_name = "scripts/skills/skill_renderer_runtime_audit.py"
        for path in sorted(workflow_paths):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if script_name not in line or line.lstrip().startswith("#"):
                    continue
                tokens = shlex.split(line.strip())
                script = tokens.index(script_name)
                commands.append((path, line_number, tokens[script + 1 :]))

        self.assertTrue(commands)
        for path, line_number, arguments in commands:
            with self.subTest(path=path.relative_to(ROOT), line=line_number):
                theme_runtime.build_parser().parse_args(arguments)

    def test_report_producer_has_the_pinned_browser_runtime(self) -> None:
        core = (ROOT / ".gitlab/ci/core.yml").read_text(encoding="utf-8")
        test_job = core_job("test", "external_integration_audit")
        image = (
            "mcr.microsoft.com/playwright:v1.61.1-noble@sha256:"
            "5b8f294aff9041b7191c34a4bab3ac270157a28774d4b0660e9743297b697e48"
        )
        self.assertIn(f"image: {image}", test_job)
        self.assertIn('BROWSER_TOOLS_REQUIRED: "1"', test_job)
        self.assertIn('cd scripts/runtime && pnpm install --frozen-lockfile --ignore-scripts', core)

    def test_github_validation_jobs_install_the_pinned_browser_runtime(self) -> None:
        for workflow in ("pages.yml", "release.yml"):
            with self.subTest(workflow=workflow):
                source = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
                browser_jobs = [
                    (name, job)
                    for name, job in contribution_safety.workflow_jobs(source)
                    if any(
                        consumer in job
                        for consumer in contribution_safety.BROWSER_RUNTIME_CONSUMERS
                    )
                ]
                self.assertTrue(browser_jobs)
                for job_name, job in browser_jobs:
                    with self.subTest(workflow=workflow, job=job_name):
                        install_steps = [
                            step for step in contribution_safety.workflow_steps(job)
                            if "pnpm install --frozen-lockfile --ignore-scripts" in step
                        ]
                        self.assertEqual(len(install_steps), 1)
                        self.assertIn("working-directory: scripts/runtime", install_steps[0])
                        self.assertNotIn("--dir scripts/runtime", install_steps[0])
                        self.assertIn('node-version: "24"', job)
                        first_consumer = min(
                            job.index(token)
                            for token in contribution_safety.BROWSER_RUNTIME_CONSUMERS
                            if token in job
                        )
                        install_position = (
                            job.index(install_steps[0])
                            + install_steps[0].index("pnpm install --frozen-lockfile --ignore-scripts")
                        )
                        self.assertLess(install_position, first_consumer)

    def test_each_browser_backed_job_rejects_an_unscoped_runtime_install(self) -> None:
        for workflow, prefix in (("pages.yml", "github"), ("release.yml", "release")):
            source = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8")
            rel = f".github/workflows/{workflow}"
            for job_name, job in contribution_safety.workflow_jobs(source):
                if not any(
                    consumer in job
                    for consumer in contribution_safety.BROWSER_RUNTIME_CONSUMERS
                ):
                    continue
                with self.subTest(workflow=workflow, job=job_name):
                    mutated_job = job.replace(
                        "working-directory: scripts/runtime",
                        "working-directory: .",
                        1,
                    )
                    self.assertNotEqual(mutated_job, job)
                    mutated = source.replace(job, mutated_job, 1)
                    codes = {
                        item["code"]
                        for item in contribution_safety.audit_browser_runtime_jobs(
                            mutated, rel, prefix,
                        )
                    }
                    self.assertIn(f"{prefix}-browser-runtime-lock", codes)

    def test_codeql_job_has_minimal_workflow_metadata_access(self) -> None:
        source = (ROOT / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
        job_permissions = source.split("jobs:\n", 1)[1].split("strategy:\n", 1)[0]
        self.assertIn("actions: read", job_permissions)
        self.assertIn("contents: read", job_permissions)
        self.assertIn("security-events: write", job_permissions)
        self.assertNotIn("actions: write", source)
        self.assertNotIn("contents: write", source)

    def test_declared_course_previews_are_projected_with_their_runtime_assets(self) -> None:
        build = (ROOT / "scripts/build/build_pages.sh").read_text(encoding="utf-8")
        for token in (
            'previews = manifest.get("previews", [])',
            'entries = manifest.get("preview_entries", {})',
            'shutil.copytree(source, target_root / name, dirs_exist_ok=True)',
            'shutil.copytree(shared, target_root / "shared", dirs_exist_ok=True)',
            'shutil.copy2(root / "web/_skill_explorer.js", target_root / "_skill_explorer.js")',
            'for course in [*manifest.get("released", []), *manifest.get("previews", [])]',
            'for course in manifest.get("previews", [])',
        ):
            with self.subTest(token=token):
                self.assertIn(token, build)
        self.assertIn('entries.get(name) != f"/lab/static/{name}/index.html"', build)
        self.assertEqual(3, build.count('re.sub(r"<!--.*?-->", "",'))
        self.assertEqual(3, build.count(r'<script\b(?=[^>]*\bid="foyer-release")'))

    def test_required_worker_builds_the_candidate_once_for_pages(self) -> None:
        core = (ROOT / ".gitlab/ci/core.yml").read_text(encoding="utf-8")
        test_job = core_job("test", "external_integration_audit")
        pages = core_job("pages", "pages_smoke")
        self.assertIn('bash scripts/build/build_pages.sh "$CI_PROJECT_DIR/candidate"', test_job)
        self.assertIn('git worktree add --quiet --detach "$candidate_source" "$CI_COMMIT_SHA"', test_job)
        self.assertIn('cp -a docs/validation/. "$candidate_source/docs/validation/"', test_job)
        self.assertIn("tar -czf validated-candidate.tar.gz -C candidate .", test_job)
        self.assertIn("- validated-candidate.tar.gz", test_job)
        self.assertIn("--archive validated-candidate.tar.gz --extract-to candidate", pages)
        self.assertIn('cp -a candidate/. "public/$CI_COMMIT_REF_SLUG/"', pages)
        self.assertIn("cp -a candidate public", pages)
        self.assertIn('--expect-sha "$CI_COMMIT_SHA"', test_job)
        self.assertIn('--expect-sha "$CI_COMMIT_SHA"', pages)
        self.assertNotIn("build_pages.sh public", pages)
        self.assertNotIn('build_pages.sh "public/$CI_COMMIT_REF_SLUG"', pages)
        self.assertIn("stages: [test, deploy, verify, review]", core)
        self.assertNotIn("stage: build", core)

    def test_manifest_rewrites_reproject_every_discovered_mirror(self) -> None:
        pages = core_job("pages", "pages_smoke")
        self.assertIn(
            'project_artifact_manifests.py public --manifest-root "public/$CI_COMMIT_REF_SLUG"',
            pages,
        )
        self.assertIn('project_artifact_manifests.py public\n', pages)
        self.assertIn('artifact_link_audit.py "public/$CI_COMMIT_REF_SLUG"', pages)
        build = (ROOT / "scripts/build/build_pages.sh").read_text(encoding="utf-8")
        self.assertIn('project_artifact_manifests.py" "$OUT"', build)

    def test_pages_locale_assertions_follow_the_supported_build_switch(self) -> None:
        pages = core_job("pages", "pages_smoke")
        guard = 'if [ "${BUILD_PAGES_LANGS:-1}" != "0" ]; then'
        locale_assertion = 'for locale in i18n/*; do if [ -d "$locale/web/nemoclaw" ]'
        self.assertIn(guard, pages)
        self.assertIn(locale_assertion, pages)
        self.assertLess(pages.index(guard), pages.index(locale_assertion))

    def test_english_only_projection_makes_locale_studio_inert(self) -> None:
        studio = (ROOT / "web/nemoclaw/scripts/localization_main.js").read_text(encoding="utf-8")
        self.assertIn('if (lang && !localized.length)', studio)
        self.assertIn('This build contains English only.', studio)
        self.assertIn('localeSelect.hidden = true', studio)

    def test_runtime_keeps_universal_narrow_layout_coverage(self) -> None:
        source = theme_runtime.RUNTIME_JS
        for token in (
            "setViewportSize({ width:390, height:844 })",
            "narrow contrast",
            "narrow layout overflows 390px viewport",
            "documentWidth:document.documentElement.scrollWidth",
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)

    def test_runtime_checks_every_internal_url_and_owned_request(self) -> None:
        source = theme_runtime.RUNTIME_JS
        for token in (
            "urlAttributes = ['href', 'src', 'poster', 'action', 'data-svg-src']",
            "document.querySelectorAll('*')",
            "isSkill = await page.evaluate",
            "!!document.getElementById('skill-meta')",
            "internal response HTTP",
            "internal request failed",
            "internal URLs failed",
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn("anchor.dataset.evidenceLink === 'local'", source)

    def test_runtime_settles_declared_redirects_without_a_path_exemption(self) -> None:
        source = theme_runtime.RUNTIME_JS
        self.assertIn('meta[http-equiv="refresh" i]', source)
        self.assertIn("await page.waitForLoadState('domcontentloaded');", source)
        self.assertNotIn("file.endsWith('standalone/SKILL.html')", source)

    def test_runtime_uses_an_ephemeral_server_port(self) -> None:
        source = theme_runtime.RUNTIME_JS
        self.assertIn("server.listen(0, '127.0.0.1'", source)
        self.assertIn("port = server.address().port", source)
        self.assertNotIn("const port = 4214", source)

    def test_long_returned_sequences_need_visual_evidence_without_an_authored_marker(self) -> None:
        path = ROOT / "web/nemoclaw/fixture.html"
        safe = '''<script>mountCanvasFlow("#cell", { nodes: [{ id:"trace", code: `
            const values = [];
            for (let i = 0; i < 25; i++) values.push(i);
            helpers.viz.lineChart(values);
            return { values };
        `}]});</script>'''
        missing_visual = safe.replace("helpers.viz.lineChart(values);", "")
        short_sequence = missing_visual.replace("i < 25", "i < 8")
        self.assertEqual([], learner_flow.audit_learning_evidence(path, safe))
        findings = learner_flow.audit_learning_evidence(path, missing_visual)
        self.assertTrue(any("returns long sequence" in finding for finding in findings), findings)
        self.assertEqual([], learner_flow.audit_learning_evidence(path, short_sequence))
        source = (ROOT / "scripts/validation/learner_flow_audit.py").read_text(encoding="utf-8")
        self.assertNotIn("data-learning-evidence", source)

    def test_helper_visual_audit_discovers_all_theme_aware_svg_output(self) -> None:
        source = helper_notebook.RUNTIME_JS
        self.assertIn('.helper-notebook svg.gfx-dark[role="img"]', source)
        self.assertIn("const badVisuals = lightVisuals.filter", source)
        self.assertNotIn("position by tick", source)
        self.assertNotIn("line chart is not visible", source)

    def test_runtime_rejects_nested_controls_after_page_mount(self) -> None:
        source = theme_runtime.RUNTIME_JS
        self.assertIn("interactiveSelector", source)
        self.assertIn("nested interactive controls", source)

    def test_cell_discovery_includes_every_language_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for prefix in ("", "es", "pt"):
                course = root / prefix / "nemoclaw"
                (course / "scripts").mkdir(parents=True)
                (course / "scripts" / "SKILL.html").write_text("<!doctype html>", encoding="utf-8")
                (course / "lesson.html").write_text("<script>mountRunCell('#cell', {})</script>", encoding="utf-8")
            self.assertEqual(
                cell_runtime.discover_default_pages(root),
                [
                    "/nemoclaw/scripts/SKILL.html", "/nemoclaw/lesson.html",
                    "/es/nemoclaw/scripts/SKILL.html", "/es/nemoclaw/lesson.html",
                    "/pt/nemoclaw/scripts/SKILL.html", "/pt/nemoclaw/lesson.html",
                ],
            )

    def test_cell_runtime_rejects_split_action_groups(self) -> None:
        source = cell_runtime.RUNTIME_JS
        self.assertIn("cellActionLayout", source)
        self.assertIn("cell actions split or wrapped", source)

    def test_pages_build_has_an_unconditional_artifact_boundary_gate(self) -> None:
        source = (ROOT / "scripts/build/build_pages.sh").read_text(encoding="utf-8")
        self.assertIn('artifact_link_audit.py" "$OUT"', source)
        self.assertNotIn("ARTIFACT_LINK_AUDIT", source)

    def test_direct_pages_build_runs_the_ship_gate_before_assembly(self) -> None:
        source = (ROOT / "scripts/build/build_pages.sh").read_text(encoding="utf-8")
        ship_gate = 'release_gate.py" --tier ship --no-write'
        validation = 'validate_bundle.py" --scope ship'
        self.assertIn(ship_gate, source)
        self.assertLess(source.index(ship_gate), source.index(validation))
        self.assertIn('if [ "$REUSE_VALIDATION" = "1" ]; then', source)

    def test_human_review_is_bound_to_the_live_branch_and_exact_commit(self) -> None:
        source = (ROOT / ".gitlab/ci/core.yml").read_text(encoding="utf-8")
        job = source[source.index("human_review:\n") :]
        for token in (
            "resource_group: pages-site",
            "branch_preview_manifest_audit.py",
            '--expect-preview "$preview_ref=$CI_COMMIT_REF_SLUG"',
            '--expect-git-sha "$CI_COMMIT_SHORT_SHA"',
            "Retry only the pages job",
        ):
            with self.subTest(token=token):
                self.assertIn(token, job)

    def test_live_pages_smoke_is_bound_to_the_exact_commit(self) -> None:
        job = core_job("pages_smoke", "theme_runtime")
        self.assertIn('--expect-git-sha "$CI_COMMIT_SHORT_SHA"', job)

    def test_live_pages_jobs_normalize_the_instance_url_to_https(self) -> None:
        canonicalization = 'pages_base_url="${CI_PAGES_URL/http:/https:}"'
        smoke = core_job("pages_smoke", "theme_runtime")
        human = (ROOT / ".gitlab/ci/core.yml").read_text(encoding="utf-8")
        human = human[human.index("human_review:\n") :]
        for name, job in (("pages_smoke", smoke), ("human_review", human)):
            with self.subTest(job=name):
                self.assertIn(canonicalization, job)
                self.assertIn('--base-url "$pages_base_url/"', job)
                self.assertNotIn('--base-url "$CI_PAGES_URL/"', job)

    def test_sbom_runtime_accepts_zero_only_when_the_rendered_count_agrees(self) -> None:
        renderer = (ROOT / "scripts/compliance/third_party_export_ui.js").read_text(encoding="utf-8")
        runtime = theme_runtime.RUNTIME_JS
        self.assertIn('key:"unresolved"', renderer)
        self.assertIn('item.dataset.sbomFact = fact.key', renderer)
        self.assertIn("clarificationRows !== state.sbomEvidence.clarificationCount", runtime)
        self.assertIn("!Number.isInteger(state.sbomEvidence.clarificationCount)", runtime)
        self.assertNotIn("!state.sbomEvidence.clarificationRows", runtime)

class ScaTriggerContractTests(unittest.TestCase):
    def test_wheel_only_gitlab_commands_are_quoted_yaml_scalars(self) -> None:
        sca = (ROOT / ".gitlab/ci/sca.yml").read_text(encoding="utf-8")
        token = "--only-binary=:all:"
        self.assertEqual(2, sum(token in line and line.strip().startswith("- '") for line in sca.splitlines()))

    def test_pages_does_not_wait_on_an_unplayed_manual_sca_job(self) -> None:
        pages = core_job("pages", "pages_smoke")
        header = pages.split("  script:\n", 1)[0]
        self.assertIn('needs: ["test"]', header)
        self.assertNotIn("optional: true", header)
        self.assertIn('if [ -z "${PYTHON_SCA_JOB_ID:-}" ]', pages)
        self.assertIn("- job: security_python_sca\n          artifacts: true", pages)

    def test_pages_python_sca_override_tracks_scanner_inputs(self) -> None:
        pages = core_job("pages", "pages_smoke")
        scanner = ci_job("security_python_sca")
        for path in (
            "scripts/materials/requirements.lock",
            "scripts/security/requirements-sca.lock",
            "scripts/compliance/sbom_evidence.py",
            ".gitlab/ci/sca.yml",
        ):
            with self.subTest(path=path):
                self.assertIn(f"- {path}", scanner)
                self.assertIn(f"- {path}", pages)

    def test_expensive_scans_are_automatic_only_for_relevant_inputs(self) -> None:
        cases = {
            "security_browser_sca": "scripts/browser-vendor/package-lock.json",
            "security_python_sca": "scripts/materials/requirements.lock",
        }
        for job_name, relevant_input in cases.items():
            with self.subTest(job=job_name):
                job = ci_job(job_name)
                self.assertIn(relevant_input, job)
                self.assertIn("- .gitlab/ci/sca.yml", job)
                self.assertNotIn("- .gitlab-ci.yml", job)
                self.assertNotIn("- .gitlab/ci/core.yml", job)

    def test_browser_sca_audits_the_frozen_host_runtime(self) -> None:
        job = ci_job("security_browser_sca")
        for path in (
            "scripts/runtime/package.json",
            "scripts/runtime/pnpm-lock.yaml",
        ):
            with self.subTest(path=path):
                self.assertIn(f"- {path}", job)
        self.assertIn(
            "cd scripts/runtime && pnpm install --frozen-lockfile --ignore-scripts",
            job,
        )
        self.assertIn(
            "npm audit --prefix .cache/runtime-npm-audit --package-lock-only --audit-level=moderate",
            job,
        )
        self.assertIn("runtime-npm-audit.json", job)
        self.assertIn(
            "- scripts/security/reports/runtime-npm-audit.json",
            job,
        )

    def test_expensive_scans_remain_optional_in_unrelated_merge_requests(self) -> None:
        optional_rule = """- if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
      when: manual
      allow_failure: true"""
        for job_name in ("security_browser_sca", "security_python_sca"):
            with self.subTest(job=job_name):
                self.assertIn(optional_rule, ci_job(job_name))

    def test_retired_workspace_and_image_scans_do_not_return(self) -> None:
        source = (ROOT / ".gitlab/ci/sca.yml").read_text(encoding="utf-8")
        self.assertNotIn("security_deep_sca:", source)
        self.assertNotIn("security_image_sca:", source)
        self.assertNotIn("workspace/requirements.lock", source)


class PythonEnvironmentContractTests(unittest.TestCase):
    def test_pages_build_fails_early_through_the_shared_python_probe(self) -> None:
        source = (ROOT / "scripts/build/build_pages.sh").read_text(encoding="utf-8")
        probe = 'python3 "$T1/scripts/runtime/python_env_probe.py" --require-material-tools'
        self.assertIn(probe, source)
        self.assertLess(source.index(probe), source.index('rm -rf "$OUT"'))

    def test_agent_guidance_uses_a_compatible_isolated_pinned_environment(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs/lab_runtime_testing.md").read_text(encoding="utf-8")
        probe = (ROOT / "scripts/runtime/python_env_probe.py").read_text(encoding="utf-8")
        self.assertIn("Python 3.12", agents)
        self.assertIn("virtual environment", guide)
        self.assertIn("scripts/materials/requirements.lock", guide)
        self.assertIn("MINIMUM = (3, 11)", probe)
        self.assertIn("TESTED = (3, 12)", probe)

if __name__ == "__main__":
    unittest.main()
