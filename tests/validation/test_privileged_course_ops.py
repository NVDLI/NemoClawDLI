# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import io
import hashlib
import importlib.util
import re
import subprocess
import tarfile
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch

from scripts.ci import (
    assert_unprivileged_environment,
    devbox_cdn_publisher,
    extract_trusted_archive,
    fetch_validated_candidate,
    live_interface_review,
    prepare_cdn_publication,
    privileged_request,
    trusted_gitlab_context,
)

TEST_PROJECT_ID = 12001
TEST_PROJECT_SHA256 = hashlib.sha256(str(TEST_PROJECT_ID).encode()).hexdigest()
ROOT = Path(__file__).resolve().parents[2]


class PrivilegedCiWiringTests(unittest.TestCase):
    def test_live_runtime_is_built_without_secrets_and_consumed_as_an_artifact(self) -> None:
        source = (ROOT / ".gitlab/ci/privileged-child.yml").read_text(encoding="utf-8")
        prepare, candidate = source.split("prepare_live_runtime:", 1)[1].split("live_candidate_interfaces:", 1)
        candidate, live = candidate.split("live_interface_review:", 1)
        live = live.split("cdn_prepare:", 1)[0]
        self.assertLess(
            prepare.index("-m scripts.ci.assert_unprivileged_environment"),
            prepare.index("pnpm install --frozen-lockfile --ignore-scripts"),
        )
        self.assertNotIn("scripts.validation.interface_inventory_browser_audit", prepare)
        self.assertIn("trusted-runtime/node-modules.tar.gz", prepare)
        self.assertIn("job: prepare_live_runtime", candidate)
        self.assertIn("artifacts: true", candidate)
        self.assertIn("artifacts: true", live)
        self.assertIn("trusted-runtime/node-modules.tar.gz", live)
        self.assertIn("test -f scripts/runtime/node_modules/playwright-core/package.json", live)
        self.assertNotIn("python3 - <<", source)
        self.assertEqual(
            2,
            source.count("python3 -m scripts.ci.extract_trusted_archive"),
        )

    def test_privileged_python_entries_are_importable_modules(self) -> None:
        source = (ROOT / ".gitlab/ci/privileged-child.yml").read_text(encoding="utf-8")
        direct_entries = re.findall(r"\bpython3\s+(scripts/[A-Za-z0-9_./-]+\.py)\b", source)
        self.assertEqual([], direct_entries, "privileged Python must run with python3 -m")
        modules = set(re.findall(r"\bpython3\s+-m\s+(scripts(?:\.[A-Za-z_][A-Za-z0-9_]*)+)\b", source))
        self.assertTrue(modules, "privileged child must declare repository Python modules")
        for module in modules:
            with self.subTest(module=module):
                self.assertIsNotNone(importlib.util.find_spec(module), f"missing module {module}")


class TrustedArchiveExtractionTests(unittest.TestCase):
    @staticmethod
    def _archive(path: Path, members: list[tuple[tarfile.TarInfo, bytes | None]]) -> None:
        with tarfile.open(path, "w:gz") as bundle:
            for member, body in members:
                bundle.addfile(member, io.BytesIO(body) if body is not None else None)

    def test_extracts_regular_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "runtime.tar.gz"
            member = tarfile.TarInfo("node_modules/example/package.json")
            body = b'{"name":"example"}\n'
            member.size = len(body)
            self._archive(archive, [(member, body)])
            destination = root / "runtime"

            extract_trusted_archive.extract(archive, destination)

            self.assertEqual(
                body,
                (destination / "node_modules/example/package.json").read_bytes(),
            )

    def test_rejects_paths_outside_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "runtime.tar.gz"
            member = tarfile.TarInfo("../outside")
            body = b"bad"
            member.size = len(body)
            self._archive(archive, [(member, body)])
            with self.assertRaisesRegex(ValueError, "escapes"):
                extract_trusted_archive.extract(archive, root / "runtime")

    def test_rejects_symlinks_outside_node_modules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "runtime.tar.gz"
            member = tarfile.TarInfo("node_modules/example/link")
            member.type = tarfile.SYMTYPE
            member.linkname = "../../../outside"
            self._archive(archive, [(member, None)])
            with self.assertRaisesRegex(ValueError, "escapes"):
                extract_trusted_archive.extract(archive, root / "runtime")


class LiveReviewBoundaryTests(unittest.TestCase):
    def test_candidate_capability_inventory_is_covered_by_trusted_probe_classes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory) / "web/sample"; course.mkdir(parents=True)
            (course / "interface-inventory.json").write_text(json.dumps({
                "live_capabilities": ["model-request", "openclaw-gateway", "assessment"],
            }))
            coverage = live_interface_review.assert_capabilities(Path(directory))
            self.assertEqual(["assessment"], coverage["candidate-required-gate"])
            self.assertEqual(["model-request", "openclaw-gateway"], coverage["trusted-live"])

    def test_candidate_capability_without_trusted_probe_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            course = Path(directory) / "web/sample"; course.mkdir(parents=True)
            (course / "interface-inventory.json").write_text(json.dumps({
                "live_capabilities": ["new-remote-authority"],
            }))
            with self.assertRaisesRegex(ValueError, "no trusted probe"):
                live_interface_review.assert_capabilities(Path(directory))

    def test_pages_origin_is_derived_from_ci_metadata(self) -> None:
        origin = live_interface_review.pages_origin({
            "CI_PAGES_URL": "https://course.gitlab-pages.example/group/project/",
            "CI_PAGES_DOMAIN": "gitlab-pages.example",
        })
        self.assertEqual("https://course.gitlab-pages.example", origin)

    def test_pages_origin_rejects_a_lookalike_host(self) -> None:
        with self.assertRaisesRegex(ValueError, "CI_PAGES_URL"):
            live_interface_review.pages_origin({
                "CI_PAGES_URL": "https://gitlab-pages.example.attacker.invalid/course/",
                "CI_PAGES_DOMAIN": "gitlab-pages.example",
            })

    def test_unprivileged_candidate_rejects_secret_scopes_by_name(self) -> None:
        self.assertEqual(
            ["AWS_DEFAULT_REGION", "LIVE_CLAW_SESSION_1_FILE"],
            assert_unprivileged_environment.findings({
                "CI_JOB_TOKEN": "allowed-fetch-token",
                "LIVE_CLAW_SESSION_1_FILE": "/tmp/protected",
                "AWS_DEFAULT_REGION": "us-west-2",
                "EMPTY_LIVE_VALUE": "",
            }),
        )

    def test_unprivileged_candidate_accepts_only_non_privileged_metadata(self) -> None:
        self.assertEqual([], assert_unprivileged_environment.findings({
            "CI_JOB_TOKEN": "bounded-to-artifact-fetch",
            "CANDIDATE_SHA": "a" * 40,
            "COURSE_OP": "live-interface-review",
        }))

    @patch("scripts.ci.live_interface_review.subprocess.run")
    def test_child_output_containing_exact_secret_is_rejected(self, run) -> None:
        run.return_value = subprocess.CompletedProcess([], 1, stdout=b"opaque-session", stderr=b"")
        with self.assertRaisesRegex(RuntimeError, "protected value"):
            live_interface_review._command("probe", {}, 5, ["opaque-session"])

    def test_encoded_secret_output_is_rejected(self) -> None:
        encoded = __import__("base64").b64encode(b"opaque-session")
        with self.assertRaisesRegex(RuntimeError, "protected value"):
            live_interface_review._scan(encoded, ["opaque-session"])

    @patch("scripts.ci.live_interface_review.MODEL_OPENER.open")
    def test_model_probe_preserves_browser_origin_and_course_attribution(self, model_open) -> None:
        model_open.return_value = _Response(
            b'{"choices":[{"message":{"role":"assistant","content":"OK"}}]}',
            headers={"Access-Control-Allow-Origin": "https://cdn.dli.learn.nvidia.com"},
        )
        result = live_interface_review._model(
            "model", "https://integrate.api.nvidia.com/v1/chat/completions", "key",
            "https://cdn.dli.learn.nvidia.com", "dli-nemoclaw-web", False,
        )
        request = model_open.call_args.args[0]
        headers = {name.lower(): value for name, value in request.header_items()}
        self.assertTrue(result["ok"])
        self.assertEqual("https://cdn.dli.learn.nvidia.com", headers["origin"])
        self.assertEqual("dli-nemoclaw-web", headers["x-billing-invoke-origin"])

    @patch("scripts.ci.live_interface_review.MODEL_OPENER.open")
    def test_model_probe_rejects_a_response_without_browser_cors(self, model_open) -> None:
        model_open.side_effect = [_Response(b"{}"), _Response(b"{}")]
        result = live_interface_review._model(
            "model", "https://integrate.api.nvidia.com/v1/chat/completions", "key",
            "https://cdn.dli.learn.nvidia.com", "dli-nemoclaw-web", False,
        )
        self.assertFalse(result["ok"])

    @patch("scripts.ci.live_interface_review.MODEL_OPENER.open")
    def test_model_probe_rejects_malformed_success_body(self, model_open) -> None:
        model_open.side_effect = [
            _Response(b"<html>upstream placeholder</html>", headers={"Access-Control-Allow-Origin": "*"}),
            _Response(b'{"choices":[]}', headers={"Access-Control-Allow-Origin": "*"}),
        ]
        result = live_interface_review._model(
            "model", "https://integrate.api.nvidia.com/v1/chat/completions", "key",
            "https://cdn.dli.learn.nvidia.com", "dli-nemoclaw-web", False,
        )
        self.assertFalse(result["ok"])

    def test_model_body_contract_requires_assistant_content_and_complete_sse(self) -> None:
        self.assertTrue(live_interface_review._valid_model_body(
            b'{"choices":[{"message":{"role":"assistant","content":"OK"}}]}', False,
        ))
        self.assertFalse(live_interface_review._valid_model_body(
            b'{"choices":[{"message":{"role":"assistant","content":""}}]}', False,
        ))
        complete = (
            b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
            b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n'
            b'data: [DONE]\n\n'
        )
        self.assertTrue(live_interface_review._valid_model_body(complete, True))
        self.assertFalse(live_interface_review._valid_model_body(
            b'data: {"choices":[{"delta":{"content":"OK"}}]}\n\n', True,
        ))
        self.assertFalse(live_interface_review._valid_model_body(b'data: [DONE]\n\n', True))

    def test_model_credential_redirects_are_never_followed(self) -> None:
        request = urllib.request.Request(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            headers={"Authorization": "Bearer protected"},
        )
        self.assertIsNone(live_interface_review.NoRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://attacker.invalid/collect",
        ))
        self.assertTrue(any(
            isinstance(handler, live_interface_review.NoRedirect)
            for handler in live_interface_review.MODEL_OPENER.handlers
        ))


class _Response(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200, headers: dict[str, str] | None = None) -> None:
        super().__init__(body)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class _QueuedOpener:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.requests: list[urllib.request.Request] = []

    def open(self, request, timeout=0):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected request")
        return self.responses.pop(0)


class TrustedGitLabContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.project_pin = patch.object(trusted_gitlab_context, "PROJECT_ID_SHA256", TEST_PROJECT_SHA256)
        self.project_pin.start()

    def tearDown(self) -> None:
        self.project_pin.stop()

    @patch("scripts.ci.trusted_gitlab_context.detached_head")
    @patch("scripts.ci.trusted_gitlab_context._load")
    def test_real_job_and_project_settings_bind_trusted_execution(self, load, head) -> None:
        sha = "a" * 40
        load.side_effect = [
            {"name": "cdn_prepare", "ref": "main", "commit": {"id": sha},
             "pipeline": {"id": 9, "project_id": TEST_PROJECT_ID, "ref": "main", "sha": sha}},
            {"id": TEST_PROJECT_ID, "default_branch": "main",
             "ci_pipeline_variables_minimum_override_role": "owner"},
            {"id": 9, "source": "parent_pipeline", "ref": "main", "sha": sha},
            {"commit": {"id": sha}},
        ]
        head.return_value = sha
        result = trusted_gitlab_context.verify(
            expected_job="cdn_prepare", job_token="job", read_token="read",
            api="https://gitlab.example.nvidia.com/api/v4", root=Path("."),
        )
        self.assertEqual(sha, result["sha"])
        self.assertEqual("https://gitlab.example.nvidia.com/api/v4/job", load.call_args_list[0].args[0])

    @patch("scripts.ci.trusted_gitlab_context.detached_head")
    @patch("scripts.ci.trusted_gitlab_context._load")
    def test_weaker_pipeline_variable_role_fails_closed(self, load, head) -> None:
        sha = "a" * 40
        load.side_effect = [
            {"name": "cdn_prepare", "ref": "main", "commit": {"id": sha},
             "pipeline": {"id": 9, "project_id": TEST_PROJECT_ID, "ref": "main", "sha": sha}},
            {"id": TEST_PROJECT_ID, "default_branch": "main",
             "ci_pipeline_variables_minimum_override_role": "maintainer"},
            {"id": 9, "source": "parent_pipeline", "ref": "main", "sha": sha},
            {"commit": {"id": sha}},
        ]
        head.return_value = sha
        with self.assertRaisesRegex(ValueError, "project-policy:variable-override-role"):
            trusted_gitlab_context.verify(
                expected_job="cdn_prepare", job_token="job", read_token="read",
                api="https://gitlab.example.nvidia.com/api/v4", root=Path("."),
            )

    @patch("scripts.ci.trusted_gitlab_context.detached_head")
    @patch("scripts.ci.trusted_gitlab_context._load")
    def test_superseded_default_branch_harness_fails_closed(self, load, head) -> None:
        sha = "a" * 40
        load.side_effect = [
            {"name": "cdn_prepare", "ref": "main", "commit": {"id": sha},
             "pipeline": {"id": 9, "project_id": TEST_PROJECT_ID, "ref": "main", "sha": sha}},
            {"id": TEST_PROJECT_ID, "default_branch": "main",
             "ci_pipeline_variables_minimum_override_role": "owner"},
            {"id": 9, "source": "parent_pipeline", "ref": "main", "sha": sha},
            {"commit": {"id": "b" * 40}},
        ]
        head.return_value = sha
        with self.assertRaisesRegex(ValueError, "binding:branch-head"):
            trusted_gitlab_context.verify(
                expected_job="cdn_prepare", job_token="job", read_token="read",
                api="https://gitlab.example.nvidia.com/api/v4", root=Path("."),
            )

    def test_detached_head_reads_bounded_checkout_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            git_dir = Path(directory) / ".git"
            git_dir.mkdir()
            (git_dir / "HEAD").write_text("a" * 40 + "\n", encoding="ascii")
            self.assertEqual("a" * 40, trusted_gitlab_context.detached_head(Path(directory)))

    def test_detached_head_reads_bounded_gitdir_indirection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory)
            root = boundary / "checkout"
            git_dir = boundary / "runner-git" / "worktrees" / "checkout"
            root.mkdir()
            git_dir.mkdir(parents=True)
            (root / ".git").write_text("gitdir: ../runner-git/worktrees/checkout\n", encoding="ascii")
            (git_dir / "HEAD").write_text("a" * 40 + "\n", encoding="ascii")
            self.assertEqual("a" * 40, trusted_gitlab_context.detached_head(root))

    def test_gitdir_indirection_cannot_escape_checkout_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            root = Path(directory) / "checkout"
            root.mkdir()
            (root / ".git").write_text(f"gitdir: {outside}\n", encoding="ascii")
            (Path(outside) / "HEAD").write_text("a" * 40 + "\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "escapes"):
                trusted_gitlab_context.detached_head(root)

    def test_gitdir_indirection_rejects_symlinked_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            boundary = Path(directory)
            root = boundary / "checkout"
            source = boundary / "source-git"
            redirected = boundary / "redirected-git"
            root.mkdir()
            source.mkdir()
            (source / "HEAD").write_text("a" * 40 + "\n", encoding="ascii")
            redirected.symlink_to(source, target_is_directory=True)
            (root / ".git").write_text("gitdir: ../redirected-git\n", encoding="ascii")
            with self.assertRaisesRegex(ValueError, "symlink"):
                trusted_gitlab_context.detached_head(root)

    def test_symbolic_or_malformed_checkout_head_fails_closed(self) -> None:
        for value in ("ref: refs/heads/main\n", "A" * 40, "a" * 39, "../outside"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                git_dir = Path(directory) / ".git"
                git_dir.mkdir()
                (git_dir / "HEAD").write_text(value, encoding="ascii")
                with self.assertRaisesRegex(ValueError, "detached commit"):
                    trusted_gitlab_context.detached_head(Path(directory))

    def test_symlinked_checkout_head_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            git_dir = root / ".git"
            git_dir.mkdir()
            source = root / "source"
            source.write_text("a" * 40, encoding="ascii")
            (git_dir / "HEAD").symlink_to(source)
            with self.assertRaisesRegex(ValueError, "bounded detached HEAD"):
                trusted_gitlab_context.detached_head(root)

    def test_symlinked_git_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source-git"
            source.mkdir()
            (source / "HEAD").write_text("a" * 40, encoding="ascii")
            (root / ".git").symlink_to(source, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "bounded detached HEAD"):
                trusted_gitlab_context.detached_head(root)

    def test_protected_api_origin_is_https_nvidia_gitlab_api(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "api"
            expected = "https://gitlab.example.nvidia.com/api/v4"
            path.write_text(expected + "\n", encoding="utf-8")
            digest = hashlib.sha256(expected.encode()).hexdigest()
            with patch.object(trusted_gitlab_context, "API_SHA256", digest):
                self.assertEqual(expected, trusted_gitlab_context.protected_api_url(str(path)))
                path.write_text("https://attacker.invalid/api/v4\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "reviewed boundary"):
                    trusted_gitlab_context.protected_api_url(str(path))

    def test_context_binding_rejects_another_child_pipeline(self) -> None:
        current = {"schema": "dli-trusted-gitlab-context/1", "project_id": TEST_PROJECT_ID,
                   "ref": "main", "sha": "a" * 40, "pipeline_id": 10}
        with self.assertRaisesRegex(ValueError, "acquisition context"):
            trusted_gitlab_context.bind_prior(current, current | {"pipeline_id": 11})

    def test_failure_diagnostics_use_only_fixed_vocabulary(self) -> None:
        self.assertEqual(
            "binding:pipeline-source",
            trusted_gitlab_context.safe_failure_code(ValueError("binding:pipeline-source")),
        )
        self.assertEqual(
            "checkout-head",
            trusted_gitlab_context.safe_failure_code(
                ValueError("checkout Git metadata escapes /secret/build/path")
            ),
        )
        self.assertEqual(
            "value-error",
            trusted_gitlab_context.safe_failure_code(ValueError("token=do-not-print")),
        )


class PrivilegedRequestTests(unittest.TestCase):
    context = {
        "schema": "dli-trusted-gitlab-context/1", "project_id": TEST_PROJECT_ID,
        "ref": "main", "sha": "a" * 40, "job": "test", "pipeline_id": 1,
    }

    def setUp(self) -> None:
        self.project_pin = patch.object(trusted_gitlab_context, "PROJECT_ID_SHA256", TEST_PROJECT_SHA256)
        self.project_pin.start()

    def tearDown(self) -> None:
        self.project_pin.stop()

    def base(self) -> dict[str, str]:
        return {
            "COURSE_OP": "cdn-publish", "CI_PIPELINE_SOURCE": "web", "CI_COMMIT_BRANCH": "main",
            "CI_DEFAULT_BRANCH": "main", "CI_COMMIT_SHA": "a" * 40, "PUBLISH_SOURCE_REF": "main",
            "PUBLISH_SOURCE_SHA": "b" * 40, "PUBLISH_SOURCE_TEST_JOB_ID": "123", "PUBLISH_CHANNEL": "immutable",
            "PUBLISH_COURSES": prepare_cdn_publication.PRIMARY_COURSE, "PUBLISH_LANGUAGES": "en,es",
        }

    def test_bounded_cdn_request(self) -> None:
        result = privileged_request.validate("cdn-publish", self.base(), Path("."), self.context)
        self.assertEqual("b" * 40, result["destination"])
        self.assertEqual([prepare_cdn_publication.PRIMARY_COURSE], result["courses"])

    def test_cdn_request_never_infers_an_optional_course(self) -> None:
        with self.assertRaisesRegex(ValueError, "PUBLISH_COURSES"):
            privileged_request.validate(
                "cdn-publish", self.base() | {"PUBLISH_COURSES": ""}, Path("."), self.context,
            )

    def test_cdn_request_rejects_an_unreviewed_course(self) -> None:
        with self.assertRaisesRegex(ValueError, "PUBLISH_COURSES"):
            privileged_request.validate(
                "cdn-publish",
                self.base() | {"PUBLISH_COURSES": f"{prepare_cdn_publication.PRIMARY_COURSE},other"},
                Path("."),
                self.context,
            )

    def test_child_projection_drops_process_control_variables(self) -> None:
        projected = privileged_request.child_request_env({
            "DLI_REQUEST_COURSE_OP": "cdn-publish", "BASH_ENV": "/tmp/attack",
            "PATH": "/tmp/attack", "AWS_PROFILE": "attack",
        })
        self.assertEqual("cdn-publish", projected["COURSE_OP"])
        self.assertFalse({"BASH_ENV", "PATH", "AWS_PROFILE"} & set(projected))

    def test_stable_ref_is_deferred_to_root_owned_publisher_allowlist(self) -> None:
        env = self.base() | {"PUBLISH_SOURCE_REF": "feature/demo", "PUBLISH_CHANNEL": "stable"}
        result = privileged_request.validate("cdn-publish", env, Path("."), self.context)
        self.assertEqual("feature/demo", result["source_ref"])

    def test_provider_mismatch_is_rejected(self) -> None:
        env = self.base() | {
            "COURSE_OP": "live-interface-review", "CANDIDATE_REF": "feature/demo",
            "CANDIDATE_SHA": "b" * 40, "CANDIDATE_TEST_JOB_ID": "456",
            "CLAW_URL_1": "https://example.apps.run.brev.nvidia.com/", "CLAW_ACCESS_PROVIDER_1": "cloudflare",
        }
        with self.assertRaisesRegex(ValueError, "provider-matching"):
            privileged_request.validate("live-interface-review", env, Path("."), self.context)

    def test_two_provider_paths_are_bound_independently(self) -> None:
        env = self.base() | {
            "COURSE_OP": "live-interface-review", "CANDIDATE_REF": "feature/demo",
            "CANDIDATE_SHA": "b" * 40, "CANDIDATE_TEST_JOB_ID": "456",
            "CLAW_URL_1": "https://one.brevlab.com/", "CLAW_ACCESS_PROVIDER_1": "cloudflare",
            "CLAW_URL_2": "https://two.apps.run.brev.nvidia.com/", "CLAW_ACCESS_PROVIDER_2": "pomerium",
        }
        result = privileged_request.validate("live-interface-review", env, Path("."), self.context)
        self.assertEqual(["cloudflare", "pomerium"], [item["provider"] for item in result["targets"]])


class PublicationPreparationTests(unittest.TestCase):
    primary = prepare_cdn_publication.PRIMARY_COURSE

    def test_selected_languages_and_flat_course_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); candidate = root / "candidate"; output = root / "publication"
            primary = candidate / "web" / self.primary
            localized = candidate / "es" / self.primary
            primary.mkdir(parents=True); (primary / "index.html").write_text("course")
            localized.mkdir(parents=True); (localized / "index.html").write_text("curso")
            (candidate / "languages.json").write_text(json.dumps({
                "schema": "nemoclaw-languages/1", "languages": [
                    {"code": "en", "url": f"web/{self.primary}/"},
                    {"code": "es", "url": f"es/{self.primary}/"},
                ],
            }))
            plan_path = root / "publication-plan.json"
            plan = prepare_cdn_publication.prepare(candidate, output, plan_path, {
                "source_ref": "main", "source_sha": "a" * 40, "job_id": "1",
                "channel": "immutable", "destination": "a" * 40,
                "courses": [self.primary], "languages": ["en"],
            })
            self.assertTrue((output / self.primary / "index.html").is_file())
            self.assertFalse((output / "es").exists())
            self.assertTrue(plan_path.is_file())
            self.assertGreater(len(plan["files"]), 1)

    def test_unreviewed_course_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); candidate = root / "candidate"; output = root / "publication"
            primary = candidate / "web" / self.primary
            primary.mkdir(parents=True); (primary / "index.html").write_text("course")
            (candidate / "languages.json").write_text(json.dumps({
                "schema": "nemoclaw-languages/1",
                "languages": [{"code": "en", "url": f"web/{self.primary}/"}],
            }))
            with self.assertRaisesRegex(ValueError, "publication vocabulary"):
                prepare_cdn_publication.prepare(candidate, output, root / "plan.json", {
                    "source_ref": "main", "source_sha": "a" * 40, "job_id": "1",
                    "channel": "immutable", "destination": "a" * 40,
                    "courses": [self.primary, "other"], "languages": ["en"],
                })

    def test_non_english_subset_gets_a_working_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); candidate = root / "candidate"; output = root / "publication"
            localized = candidate / "es" / self.primary
            localized.mkdir(parents=True)
            (localized / "index.html").write_text("curso")
            (candidate / "languages.json").write_text(json.dumps({
                "schema": "nemoclaw-languages/1",
                "languages": [{"code": "es", "url": f"es/{self.primary}/"}],
            }))
            prepare_cdn_publication.prepare(candidate, output, root / "plan.json", {
                "source_ref": "feature/es", "source_sha": "a" * 40, "job_id": "1",
                "channel": "immutable", "destination": "a" * 40,
                "courses": [self.primary], "languages": ["es"],
            })
            self.assertIn(f"url=es/{self.primary}/", (output / "index.html").read_text())

    def test_stable_channel_preserves_the_flat_primary_course_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); candidate = root / "candidate"; output = root / "publication"
            primary = candidate / "web" / self.primary
            primary.mkdir(parents=True)
            (primary / "index.html").write_text("course")
            (primary / "01a-loop.html").write_text("lesson")
            (candidate / "languages.json").write_text(json.dumps({
                "schema": "nemoclaw-languages/1",
                "languages": [{"code": "en", "url": f"web/{self.primary}/"}],
            }))
            prepare_cdn_publication.prepare(candidate, output, root / "plan.json", {
                "source_ref": "main", "source_sha": "a" * 40, "job_id": "1",
                "channel": "stable", "destination": "course-static",
                "courses": [self.primary], "languages": ["en"],
            })
            self.assertTrue((output / self.primary / "01a-loop.html").is_file())

    def test_stable_locales_keep_the_site_root_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); candidate = root / "candidate"; output = root / "publication"
            primary = candidate / "web" / self.primary
            localized = candidate / "es" / self.primary
            primary.mkdir(parents=True)
            (primary / "index.html").write_text("course")
            localized.mkdir(parents=True)
            (localized / "index.html").write_text("curso")
            (candidate / "languages.json").write_text(json.dumps({
                "schema": "nemoclaw-languages/1", "languages": [
                    {"code": "en", "url": f"web/{self.primary}/"},
                    {"code": "es", "url": f"es/{self.primary}/"},
                ],
            }))
            prepare_cdn_publication.prepare(candidate, output, root / "plan.json", {
                "source_ref": "main", "source_sha": "a" * 40, "job_id": "1",
                "channel": "stable", "destination": "course-static",
                "courses": [self.primary], "languages": ["en", "es"],
            })
            self.assertTrue((output / self.primary / "index.html").is_file())
            self.assertTrue((output / "es" / self.primary / "index.html").is_file())


class PublisherBoundaryTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        publication = root / "publication"; publication.mkdir()
        (publication / "index.html").write_text("course")
        digest = __import__("hashlib").sha256(b"course").hexdigest()
        aws = Path("/usr/bin/true")
        aws_digest = __import__("hashlib").sha256(aws.read_bytes()).hexdigest()
        account_id = "".join(map(str, range(10))) + "01"
        plan = root / "plan.json"; config = root / "config.json"
        plan.write_text(json.dumps({
            "schema": "dli-cdn-publication/2", "source_ref": "topic", "source_sha": "a" * 40,
            "channel": "immutable", "destination": "a" * 40,
            "courses": [prepare_cdn_publication.PRIMARY_COURSE],
            "files": [{"path": "index.html", "bytes": 6, "sha256": digest}],
        }))
        config.write_text(json.dumps({
            "aws_account_id": account_id,
            "principal_arn": f"arn:aws:sts::{account_id}:assumed-role/DLICoursePublisher/",
            "aws_executable": str(aws), "aws_executable_sha256": aws_digest,
            "aws_config_file": "/etc/hosts", "aws_credentials_file": "/etc/hosts",
            "bucket_name": "example-course-bucket",
            "key_prefix": "course-static",
            "public_base_url": "https://course-cdn.example",
            "cloudfront_distribution_id": "E123456789",
        }))
        return publication, plan, config

    def test_plan_must_cover_every_and_only_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); publication, plan, config = self._fixture(root)
            devbox_cdn_publisher.validate(publication, plan, config)
            (publication / "extra.js").write_text("unexpected")
            with self.assertRaisesRegex(ValueError, "do not match"):
                devbox_cdn_publisher.validate(publication, plan, config)

    def test_destination_identifiers_must_come_from_root_owned_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); publication, plan, config = self._fixture(root)
            document = json.loads(config.read_text())
            for field in ("bucket_name", "key_prefix", "public_base_url"):
                mutated = dict(document)
                mutated.pop(field)
                config.write_text(json.dumps(mutated))
                with self.assertRaisesRegex(ValueError, "destination configuration"):
                    devbox_cdn_publisher.validate(publication, plan, config)
            config.write_text(json.dumps(document))

    def test_stable_ownership_rejects_an_unreviewed_course(self) -> None:
        primary = prepare_cdn_publication.PRIMARY_COURSE
        with self.assertRaisesRegex(ValueError, "invalid course selection"):
            devbox_cdn_publisher._stable_prefixes({"courses": [primary, "other"]})
        self.assertIn(f"{primary}/", devbox_cdn_publisher._stable_prefixes({"courses": [primary]}))

    @patch("scripts.ci.devbox_cdn_publisher._verify_cdn")
    @patch("scripts.ci.devbox_cdn_publisher._remote_owned")
    @patch("scripts.ci.devbox_cdn_publisher.subprocess.run")
    def test_publish_uses_only_configured_identity_and_fixed_target(self, run, remote, verify) -> None:
        with tempfile.TemporaryDirectory() as directory:
            publication, plan, config = self._fixture(Path(directory))
            account_id = json.loads(config.read_text())["aws_account_id"]
            run.side_effect = [
                subprocess.CompletedProcess([], 0, stdout=json.dumps({
                    "Account": account_id,
                    "Arn": f"arn:aws:sts::{account_id}:assumed-role/DLICoursePublisher/job-1",
                })),
                subprocess.CompletedProcess([], 0),
            ]
            remote.side_effect = [
                {},
                {"course-static/" + "a" * 40 + "/index.html": 6},
            ]
            with patch.dict("os.environ", {
                "HOME": "/home/publisher", "PATH": "/usr/bin",
                "AWS_ACCESS_KEY_ID": "must-not-propagate",
            }, clear=True):
                devbox_cdn_publisher.publish(publication, plan, config)
            identity_env = run.call_args_list[0].kwargs["env"]
            upload_command = run.call_args_list[1].args[0]
            self.assertNotIn("AWS_ACCESS_KEY_ID", identity_env)
            self.assertEqual("/var/empty", identity_env["HOME"])
            self.assertEqual("/etc/hosts", identity_env["AWS_CONFIG_FILE"])
            self.assertEqual("/usr/bin/true", upload_command[0])
            self.assertEqual(
                "s3" + "://" + "example-course-bucket/course-static/" + "a" * 40 + "/",
                upload_command[-1],
            )
            verify.assert_called_once()

    def test_plan_rejects_a_false_size_even_when_digest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            publication, plan, config = self._fixture(Path(directory))
            document = json.loads(plan.read_text())
            document["files"][0]["bytes"] = 999
            plan.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, "reviewed plan"):
                devbox_cdn_publisher.validate(publication, plan, config)

    @patch("scripts.ci.devbox_cdn_publisher._aws_json")
    def test_s3_inventory_follows_every_continuation_page(self, aws_json) -> None:
        aws_json.side_effect = [
            {"Contents": [{"Key": "course-static/a", "Size": 1}],
             "IsTruncated": True, "NextContinuationToken": "page-2"},
            {"Contents": [{"Key": "course-static/b", "Size": 2}], "IsTruncated": False},
        ]
        self.assertEqual(
            {"course-static/a": 1, "course-static/b": 2},
            devbox_cdn_publisher._list_prefix(
                "/usr/bin/aws", {}, "example-course-bucket", "course-static/",
            ),
        )
        self.assertIn("page-2", aws_json.call_args_list[1].args)

    def test_assumed_role_match_is_delimiter_bound(self) -> None:
        account = "".join(map(str, range(10))) + "01"
        configured = f"arn:aws:sts::{account}:assumed-role/DLICoursePublisher/"
        self.assertTrue(devbox_cdn_publisher._principal_matches(configured + "job-1", configured))
        self.assertFalse(devbox_cdn_publisher._principal_matches(
            f"arn:aws:sts::{account}:assumed-role/DLICoursePublisherAdmin/job-1", configured,
        ))


class ArtifactFetchBoundaryTests(unittest.TestCase):
    API = "https://gitlab.example.nvidia.com/api/v4"

    def setUp(self) -> None:
        self.project_pin = patch.object(trusted_gitlab_context, "PROJECT_ID_SHA256", TEST_PROJECT_SHA256)
        self.project_pin.start()

    def tearDown(self) -> None:
        self.project_pin.stop()

    def _responses(
        self, *, branch_sha: str | None = None, pipeline_status: str = "success", pages: str = "success",
        security_sca: str = "success", security_allow_failure: bool = False,
        extra_jobs: list[dict[str, object]] | None = None,
    ) -> list[_Response]:
        sha = "b" * 40
        metadata = {
            "name": "test", "status": "success", "ref": "feature/demo",
            "commit": {"id": sha}, "pipeline": {"id": 999, "sha": sha},
        }
        jobs = [
            {"name": "test", "status": "success"},
            {"name": "pages", "status": pages},
            {"name": "pages_smoke", "status": "success"},
            {"name": "theme_runtime", "status": "success"},
            {"name": "security_browser_sca", "status": "success"},
            {"name": "security_python_sca", "status": "success"},
            {"name": "security_sca", "status": security_sca, "allow_failure": security_allow_failure},
        ] + (extra_jobs or [])
        return [
            _Response(json.dumps(metadata).encode()),
            _Response(json.dumps({"commit": {"id": branch_sha or sha}}).encode()),
            _Response(json.dumps({"id": 999, "ref": "feature/demo", "sha": sha, "status": pipeline_status}).encode()),
            _Response(json.dumps(jobs).encode()),
            _Response(b"reviewed-candidate"),
        ]

    @patch("scripts.ci.fetch_validated_candidate.urllib.request.build_opener")
    def test_fetch_requires_current_successful_exact_pipeline(self, build_opener) -> None:
        opener = _QueuedOpener(self._responses())
        build_opener.return_value = opener
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.tar.gz"
            result = fetch_validated_candidate.fetch(
                job="34", ref="feature/demo", sha="b" * 40,
                metadata_token="read-token", artifact_token="job-token",
                api=self.API, project_id=TEST_PROJECT_ID, output=output,
            )
            self.assertEqual(b"reviewed-candidate", output.read_bytes())
            self.assertEqual(999, result["pipeline_id"])
            self.assertEqual(5, len(opener.requests))
            self.assertNotIn("include_retried", opener.requests[3].full_url)

    @patch("scripts.ci.fetch_validated_candidate.urllib.request.build_opener")
    def test_fetch_rejects_failed_pipeline_even_when_named_gates_pass(self, build_opener) -> None:
        build_opener.return_value = _QueuedOpener(self._responses(pipeline_status="failed"))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "source pipeline"):
            fetch_validated_candidate.fetch(
                job="34", ref="feature/demo", sha="b" * 40,
                metadata_token="read-token", artifact_token="job-token",
                api=self.API, project_id=TEST_PROJECT_ID, output=Path(directory) / "candidate.tar.gz",
            )

    @patch("scripts.ci.fetch_validated_candidate.urllib.request.build_opener")
    def test_fetch_rejects_branch_head_drift(self, build_opener) -> None:
        build_opener.return_value = _QueuedOpener(self._responses(branch_sha="c" * 40))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "branch head"):
            fetch_validated_candidate.fetch(
                job="34", ref="feature/demo", sha="b" * 40, metadata_token="read-token", artifact_token="job-token",
                api=self.API, project_id=TEST_PROJECT_ID, output=Path(directory) / "candidate.tar.gz",
            )

    @patch("scripts.ci.fetch_validated_candidate.urllib.request.build_opener")
    def test_fetch_rejects_incomplete_pages_evidence(self, build_opener) -> None:
        build_opener.return_value = _QueuedOpener(self._responses(pages="manual"))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "pages"):
            fetch_validated_candidate.fetch(
                job="34", ref="feature/demo", sha="b" * 40, metadata_token="read-token", artifact_token="job-token",
                api=self.API, project_id=TEST_PROJECT_ID, output=Path(directory) / "candidate.tar.gz",
            )

    @patch("scripts.ci.fetch_validated_candidate.urllib.request.build_opener")
    def test_fetch_rejects_a_failed_latest_security_job(self, build_opener) -> None:
        build_opener.return_value = _QueuedOpener(self._responses(
            security_sca="failed", security_allow_failure=True,
        ))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "security evidence"):
            fetch_validated_candidate.fetch(
                job="34", ref="feature/demo", sha="b" * 40, metadata_token="read-token", artifact_token="job-token",
                api=self.API, project_id=TEST_PROJECT_ID, output=Path(directory) / "candidate.tar.gz",
            )

    @patch("scripts.ci.fetch_validated_candidate.urllib.request.build_opener")
    def test_fetch_rejects_an_unfinished_required_security_job(self, build_opener) -> None:
        build_opener.return_value = _QueuedOpener(self._responses(security_sca="running"))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "security evidence"):
            fetch_validated_candidate.fetch(
                job="34", ref="feature/demo", sha="b" * 40, metadata_token="read-token", artifact_token="job-token",
                api=self.API, project_id=TEST_PROJECT_ID, output=Path(directory) / "candidate.tar.gz",
            )

    @patch("scripts.ci.fetch_validated_candidate.urllib.request.build_opener")
    def test_fetch_rejects_an_unstarted_optional_security_job(self, build_opener) -> None:
        responses = self._responses()
        jobs = json.loads(responses[3].getvalue().decode())
        next(item for item in jobs if item["name"] == "security_browser_sca").update(
            status="manual", allow_failure=True,
        )
        responses[3] = _Response(json.dumps(jobs).encode())
        opener = _QueuedOpener(responses)
        build_opener.return_value = opener
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "security evidence"):
            fetch_validated_candidate.fetch(
                job="34", ref="feature/demo", sha="b" * 40, metadata_token="read-token", artifact_token="job-token",
                api=self.API, project_id=TEST_PROJECT_ID, output=Path(directory) / "candidate.tar.gz",
            )

    @patch("scripts.ci.fetch_validated_candidate.urllib.request.build_opener")
    def test_fetch_rejects_ambiguous_latest_gate_evidence(self, build_opener) -> None:
        build_opener.return_value = _QueuedOpener(self._responses(extra_jobs=[
            {"name": "pages", "status": "failed"},
        ]))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "ambiguous latest"):
            fetch_validated_candidate.fetch(
                job="34", ref="feature/demo", sha="b" * 40, metadata_token="read-token", artifact_token="job-token",
                api=self.API, project_id=TEST_PROJECT_ID, output=Path(directory) / "candidate.tar.gz",
            )

    @patch("scripts.ci.fetch_validated_candidate.urllib.request.build_opener")
    def test_fetch_follows_every_job_inventory_page(self, build_opener) -> None:
        responses = self._responses()
        final_jobs = responses[3]
        responses[3] = _Response(b"[]", headers={"X-Next-Page": "2"})
        responses.insert(4, final_jobs)
        opener = _QueuedOpener(responses)
        build_opener.return_value = opener
        with tempfile.TemporaryDirectory() as directory:
            fetch_validated_candidate.fetch(
                job="34", ref="feature/demo", sha="b" * 40,
                metadata_token="read-token", artifact_token="job-token", api=self.API,
                project_id=TEST_PROJECT_ID, output=Path(directory) / "candidate.tar.gz",
            )
        self.assertIn("page=2", opener.requests[4].full_url)

    def test_job_token_is_removed_from_cross_host_redirect(self) -> None:
        request = urllib.request.Request(
            "https://gitlab.example/api/v4/projects/1/jobs/2/artifacts/file",
            headers={"JOB-TOKEN": "protected"},
        )
        redirected = fetch_validated_candidate.SafeRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://objects.example/signed-artifact",
        )
        self.assertIsNotNone(redirected)
        self.assertFalse(any(name.lower() == "job-token" for name, _value in redirected.header_items()))

    def test_job_token_stays_on_same_gitlab_host(self) -> None:
        request = urllib.request.Request(
            "https://gitlab.example/api/v4/projects/1/jobs/2",
            headers={"JOB-TOKEN": "protected"},
        )
        redirected = fetch_validated_candidate.SafeRedirect().redirect_request(
            request, None, 302, "Found", {}, "https://gitlab.example/users/sign_in",
        )
        self.assertEqual(
            "protected",
            next(value for name, value in redirected.header_items() if name.lower() == "job-token"),
        )


if __name__ == "__main__":
    unittest.main()
