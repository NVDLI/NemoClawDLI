#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Refresh GitLab issues with the repo issue-standard anatomy.

This helper is intentionally under scripts/dev: it is an operator handoff for
tracker metadata, not a release gate. It does not print credentials.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable
from urllib import error, parse, request


DEFAULT_HOST = os.environ.get("CI_SERVER_HOST", "gitlab.com")
DEFAULT_PROJECT_ID = os.environ.get("CI_PROJECT_ID", "")
STANDARDS_ISSUE_TITLE = (
    "Standardize issue cadence for NemoClaw CPU release and reviewer-feedback tracker"
)


LABELS = {
    "area:web": "#428BCA",
    "area:cpu": "#1F77B4",
    "area:deploy": "#6F42C1",
    "area:docs": "#0E8A16",
    "area:materials": "#795548",
    "area:security": "#D93F0B",
    "kind:bug": "#D73A4A",
    "kind:course-content": "#0052CC",
    "kind:source-correction": "#FBCA04",
    "kind:accessibility": "#BFDADC",
    "kind:release": "#C2E0C6",
    "kind:validation": "#0366D6",
    "state:needs-triage": "#EDEDED",
    "state:needs-evidence": "#FBCA04",
    "state:accepted": "#0E8A16",
    "state:in-progress": "#1D76DB",
    "state:ready-for-review": "#5319E7",
    "state:blocked-external-source": "#B60205",
    "state:blocked-platform": "#B60205",
    "state:released": "#006B75",
    "risk:learner-facing": "#F9D0C4",
    "risk:deployment": "#C5DEF5",
    "risk:security-privacy": "#D93F0B",
    "risk:license-source": "#F9D0C4",
    "risk:generated-output": "#D4C5F9",
    "severity:blocker": "#B60205",
    "severity:major": "#D93F0B",
    "severity:minor": "#FBCA04",
}


@dataclass(frozen=True)
class IssueRefresh:
    iid: int
    summary: str
    scope: str
    evidence: tuple[str, ...]
    surfaces: tuple[str, ...]
    criteria: tuple[str, ...]
    validation: tuple[str, ...]
    out_of_scope: tuple[str, ...]
    labels: tuple[str, ...]
    close: bool = False
    title: str | None = None


ISSUES = [
    IssueRefresh(
        2,
        "Learner-facing pages expose too much implementation scaffolding, runtime plumbing, and raw code before the learner has the concepts needed to interpret it.",
        "course-specific now; pattern should stay reusable for future bundled courses",
        (
            "Part 1 flags massive ReAct code, tool-calling internals, framework details, and hard-to-read code surfaces.",
            "Part 2 repeats the concern for Workflow Agent code scrolling and token/runtime details.",
            "Part 3 flags WebSocket/OpenClaw harness code as too hard for the point where it appears.",
        ),
        ("`web/nemoclaw/` lesson pages and generated HTML", "`docs/agent_process.md` and `docs/issue_standards.md`"),
        (
            "Code-heavy examples have learner-facing explanation before implementation details.",
            "Implementation scaffolding is collapsed, linked, or moved behind progressive disclosure where appropriate.",
            "Future bundled courses can apply the same rule without assuming a GPU runtime.",
        ),
        (
            "`python3 scripts/validation/validate_layout.py --quiet`",
            "`python3 scripts/skills/skill_consistency.py`",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
            "Local Pages/browser smoke for changed code visibility or runtime panels",
        ),
        (
            "Do not rewrite canonical title, abstract, or learning objectives without approval.",
            "Do not remove necessary CPU runtime affordances; sequence or hide them when they distract.",
        ),
        ("area:web", "kind:course-content", "state:accepted", "severity:major", "risk:learner-facing", "risk:generated-output"),
        title="Reviewer feedback: reduce visible implementation scaffolding in learner-facing artifacts",
    ),
    IssueRefresh(
        3,
        "Interactive labs need clearer run, reset, stop, and prerequisite state so the NemoClaw CPU path behaves like a coherent course.",
        "course-specific plus CPU runtime ergonomics",
        (
            "Part 1 flags API-key verification, missed run-all results, scroll-after-run behavior, and no obvious stop affordance.",
            "Part 2 flags send-button availability before required code has run.",
            "Part 4 says NemoClaw is not perceived as launchable/sandboxed enough.",
        ),
        ("`web/nemoclaw/` runnable pages", "host-native browser validation", "external launchable and runtime integration assumptions"),
        (
            "Prerequisite state is visible before interactive steps.",
            "Run, reset, stop, and error states are consistent across affected pages.",
            "CPU-only expectations are explicit; no GPU availability is implied.",
        ),
        (
            "`bash scripts/runtime/run_engine.sh --self-test`",
            "`python3 scripts/validation/validate_layout.py --quiet`",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
            "Browser/runtime harness for changed runnable cells or OpenClaw panels",
        ),
        ("Do not add external hosted dependencies without ownership.", "Do not expose private DLI launch URLs or tokens."),
        ("area:web", "area:cpu", "kind:course-content", "state:accepted", "severity:major", "risk:learner-facing", "risk:deployment"),
    ),
    IssueRefresh(
        4,
        "Diagrams, SVGs, and embedded graphics need a visual QA pass so labels, layout, and explanatory intent survive desktop/mobile Pages rendering.",
        "course-specific visual QA with bundle-wide accessibility standard",
        (
            "Part 2 flags tiny images, fuzzy terminology around diagrams, and vector visualization confusion.",
            "Part 3 flags the Kickstart diagram as visually odd.",
            "Part 4 asks for clearer architecture framing and public-safe alternatives.",
        ),
        ("`web/nemoclaw/` images, SVGs, and diagram containers", "`web/nemoclaw/mats/` source/provenance records"),
        (
            "Diagrams are legible at common desktop and mobile widths.",
            "Graphics have clear surrounding prose and do not rely on internal-only references.",
            "Sourced replacements have provenance and license/source status recorded.",
        ),
        (
            "`python3 scripts/validation/validate_layout.py --quiet`",
            "`python3 scripts/compliance/source_gate.py`",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
            "Browser screenshot/smoke for edited visual pages",
        ),
        ("Do not import internal diagrams unless rights and public-safe status are confirmed.",),
        ("area:web", "area:materials", "kind:accessibility", "state:accepted", "severity:major", "risk:learner-facing", "risk:license-source"),
    ),
    IssueRefresh(
        5,
        "Confusing prose, undefined acronyms, product-name drift, and prerequisite assumptions weaken the learner path through the NemoClaw CPU course.",
        "course-specific prose now; bundle-wide editorial cadence",
        (
            "Part 1 asks for clearer setup around tools, skills, progressive disclosure, and code difficulty.",
            "Part 2 flags fuzzy terminology, acronym expansion such as TTFT, and objective placement.",
            "Part 3 asks to spell out TTFT and clarify OpenClaw/OpenShell/NemoClaw introduction timing.",
        ),
        ("`web/nemoclaw/` prose", "`docs/agent_process.md` terminology guardrails"),
        (
            "Acronyms are expanded before use.",
            "NemoClaw, OpenClaw, OpenShell, and related terms are used consistently.",
            "Prerequisite assumptions are stated before the learner needs them.",
        ),
        (
            "`python3 scripts/validation/validate_layout.py --quiet`",
            "`python3 scripts/skills/skill_consistency.py`",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
            "Targeted prose grep for renamed terms and acronyms",
        ),
        ("Do not change canonical course title, abstract, or learning objectives unless approved.", "Use #9 for claim accuracy."),
        ("area:web", "kind:course-content", "state:accepted", "severity:major", "risk:learner-facing"),
    ),
    IssueRefresh(
        6,
        "ReAct, tool calling, workflow-agent patterns, and MCP concepts need stronger setup before learners see code-heavy implementations.",
        "course-specific conceptual setup with reusable pedagogy pattern",
        (
            "Part 1 flags ReAct code as massive and asks to define tools/skills/progressive disclosure.",
            "Part 2 asks for workflow patterns beyond ReAct/ReWOO.",
            "Part 3 flags OpenClaw agent harness and WebSocket examples as heavy at their placement.",
        ),
        ("`web/nemoclaw/` concept pages and code examples", "Runtime examples that depend on OpenClaw or MCP naming"),
        (
            "Major concepts are introduced with purpose before API or harness code.",
            "Tool, skill, workflow, and MCP terms are distinguished consistently.",
            "Code examples are sequenced from observable behavior to internals.",
        ),
        (
            "`python3 scripts/validation/validate_layout.py --quiet`",
            "`python3 scripts/skills/skill_consistency.py`",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
            "Browser/runtime check if runnable examples change",
        ),
        ("Use #7 for RAG/index-agent material.", "Use #9 for product/reference claims."),
        ("area:web", "kind:course-content", "state:accepted", "severity:major", "risk:learner-facing"),
    ),
    IssueRefresh(
        7,
        "RAG, indexing, vector similarity, and agentic RAG need clearer scaffolding and visuals so learners separate retrieval mechanics from agent orchestration.",
        "course-specific RAG pedagogy with reusable visual/explanation pattern",
        (
            "Part 2 asks for clearer cosine/vector explanation, dimensionality-reduction visualization, and indexing versus agentic RAG separation.",
            "Part 2 also flags tiny images and fuzzy terminology.",
        ),
        ("`web/nemoclaw/` RAG/index-agent pages", "Vector or retrieval diagrams", "`web/nemoclaw/mats/` for sourced visuals"),
        (
            "Indexing, retrieval, vector similarity, and agent orchestration are distinct.",
            "Vector visualization is legible and labeled as projection/teaching aid where relevant.",
            "Examples assume CPU runtime and avoid implying GPU-specific behavior.",
        ),
        (
            "`python3 scripts/validation/validate_layout.py --quiet`",
            "`python3 scripts/compliance/source_gate.py` if visuals/sources change",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
            "Browser screenshot/smoke for edited diagram pages",
        ),
        ("Use #6 for ReAct/workflow-agent concept work.", "Do not add datasets or services without source/runtime approval."),
        ("area:web", "kind:course-content", "state:accepted", "severity:major", "risk:learner-facing"),
    ),
    IssueRefresh(
        8,
        "Security and privacy leaks in learner-facing material block public-readiness for the NemoClaw CPU course.",
        "course-specific security/privacy now; bundle-wide public-readiness blocker",
        (
            "Part 1 flags API-key verification and private URL exposure concerns.",
            "Part 3 flags API key showing, Access/Bearer token auto-fill, and unsafe WebSocket/runtime cues.",
            "Part 4 frames NemoClaw as a secure runtime blueprint.",
        ),
        ("`web/nemoclaw/` rendered pages and code blocks", "host-native validation docs", "Security/source gates"),
        (
            "No public surface exposes secrets, private URLs, internal hostnames, Cloudflare headers, or bearer-token material.",
            "Examples use placeholders and explain safe credential handling.",
            "Internal-only detail is moved to private GitLab or omitted from public mirror.",
        ),
        (
            "`python3 scripts/compliance/source_gate.py`",
            "`python3 scripts/security/audit_python_dependencies.py` when dependencies change",
            "`python3 scripts/security/audit_vulnerability_waivers.py` when waivers change",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
            "Targeted grep for token/Bearer/api_key/private host patterns in changed public surfaces",
        ),
        ("Do not paste confidential scanner output or exploit detail into public issues.",),
        ("area:web", "area:security", "kind:bug", "state:accepted", "severity:blocker", "risk:security-privacy", "risk:learner-facing"),
    ),
    IssueRefresh(
        9,
        "OpenClaw, OpenShell, NemoClaw, Hermes, DGX Spark packaging, CLI, and related claims need public-safe fact-checking.",
        "course-specific claim accuracy with bundle-wide source governance",
        (
            "Parts 1 and 3 flag NemoClaw/OpenClaw/OpenShell naming and timing confusion.",
            "Part 3 asks that references include OpenClaw and calls out Hermes-related claims.",
            "Part 4 says OpenShell is not simply this course plus OpenClaw.",
        ),
        ("`web/nemoclaw/` product/reference copy", "`web/nemoclaw/mats/` source records"),
        (
            "Affected product/platform claims are sourced, softened, or removed.",
            "Naming is consistent with current public-safe availability.",
            "Source-limited claims are marked blocked rather than guessed.",
        ),
        (
            "`python3 scripts/compliance/source_gate.py`",
            "`python3 scripts/validation/validate_layout.py --quiet`",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
            "Source/provenance review for changed claims",
        ),
        ("Use #5 for broad prose cleanup.", "Do not cite private-only source material in public-facing copy."),
        ("area:web", "area:materials", "kind:source-correction", "state:accepted", "severity:major", "risk:license-source", "risk:learner-facing"),
    ),
    IssueRefresh(
        13,
        "`claw-html-frame` can persist after cookie-warning resolution, leaving stale framing around the learner page.",
        "course-specific runtime bug; possible bundle-wide page-frame regression",
        (
            "Existing issue report names persistent `claw-html-frame` behavior after cookie warning resolution.",
            "Exact repro evidence should be attached before closing.",
        ),
        ("`web/nemoclaw/` runtime JS and generated HTML", "Cookie/warning handling paths", "Local Pages preview"),
        (
            "Cookie-warning resolution removes or hides the frame consistently.",
            "Frame state does not persist across reload/navigation after resolution.",
            "Regression check covers fresh and previously-seen browser state.",
        ),
        (
            "`python3 scripts/validation/validate_layout.py --quiet`",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
            "Browser repro/smoke across clean and persisted profiles",
            "Targeted search for frame cleanup, cookie warning, focus, and navigation paths",
        ),
        ("Do not redesign the full warning UX unless required.", "Do not conflate with unrelated scroll/focus issues."),
        ("area:web", "kind:bug", "state:accepted", "severity:major", "risk:learner-facing"),
    ),
    IssueRefresh(
        14,
        "Deploy the OpenClaw CORS worker WebSocket gateway fix and capture public-safe evidence that the external runtime integration is ready.",
        "external runtime gateway issue with an OpenClaw-specific course surface",
        (
            "Existing issue tracks an OpenClaw CORS worker WebSocket gateway deployment fix.",
            "Reviewer feedback reinforces that OpenClaw/NemoClaw runtime boundaries must be clear and launchable on CPU.",
        ),
        ("`scripts/cors-proxy/` reference workers", "course runtime assumptions", "launchable/runtime documentation"),
        (
            "Gateway fix is deployed or a precise platform blocker is recorded.",
            "CPU path works without implying GPU availability.",
            "No private URLs, Cloudflare headers, or bearer-token material are pasted into issue/MR.",
        ),
        (
            "`bash scripts/runtime/run_engine.sh --self-test`",
            "Browser gateway contract validation",
            "WebSocket smoke against the appropriate non-secret endpoint",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship` if web/docs change",
        ),
        ("Do not publish internal gateway details to a public mirror.",),
        ("cors-proxy", "openclaw", "ops", "area:deploy", "area:cpu", "area:security", "kind:release", "state:accepted", "severity:major", "risk:deployment", "risk:security-privacy"),
    ),
    IssueRefresh(
        15,
        "Remediate reported Starlette, protobuf, and MCP advisories in dependency floors used by the CPU course bundle.",
        "bundle-wide dependency security for current CPU release",
        (
            "Original confidential report covered Starlette, python-protobuf, and mcp versions on `main` as of the June 26, 2026 scan.",
            "Resolved by merged MR !44 without publishing confidential scanner detail.",
        ),
        ("Python dependency manifests", "`scripts/security/` audits", "CI SCA jobs and SBOM artifacts", "`docs/dependency_security.md`"),
        (
            "Vulnerable direct floors are no longer accepted by repo audit.",
            "Waiver audit passes with no expired/unowned exceptions.",
            "Resolved-environment SCA/SBOM job is available for validation tooling.",
        ),
        (
            "`python3 scripts/security/audit_python_dependencies.py`",
            "`python3 scripts/security/audit_vulnerability_waivers.py`",
            "`security_python_sca` CI job or equivalent",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
        ),
        ("Do not paste scanner internals or exploit detail into public issues.",),
        ("ops", "area:security", "kind:bug", "state:released", "severity:major", "risk:security-privacy"),
        close=True,
    ),
    IssueRefresh(
        16,
        "Add SBOM, full SCA, and vulnerability-waiver guardrails so known vulnerable dependencies are not reintroduced.",
        "bundle-wide security validation for current CPU release",
        (
            "Follow-up from the June 26, 2026 vulnerability report asked for an agent-discoverable mechanism.",
            "Resolved by merged MR !44 through dependency floor audit, waiver audit, resolved-environment SCA, SBOM generation, and playbook updates.",
        ),
        ("`scripts/security/` audits", "CI security jobs and SBOM artifacts", "`docs/dependency_security.md`", "`docs/release_playbook.md`"),
        (
            "Known-vulnerable direct floors fail locally and in CI.",
            "Waivers require owner, source, expiry, and rationale.",
            "Resolved-environment SCA can produce SBOM artifacts.",
        ),
        (
            "`python3 scripts/security/audit_python_dependencies.py`",
            "`python3 scripts/security/audit_vulnerability_waivers.py`",
            "`security_python_sca` CI job or equivalent",
            "`python3 scripts/validation/validate_bundle.py --no-write --scope ship`",
        ),
        ("CodeQL/SARIF upload, Dependabot rollout, CODEOWNERS, and public mirror enforcement remain roadmap items.",),
        ("ops", "area:security", "kind:validation", "state:released", "severity:major", "risk:security-privacy"),
        close=True,
    ),
]


def issue_body(issue: IssueRefresh) -> str:
    lines = [
        "## Summary",
        "",
        issue.summary,
        "",
        "## Current release target",
        "",
        "- Course: static browser course under `web/nemoclaw/`",
        "- Production: public static host or co-located NemoClaw launchable",
        "- Contributor validation: host Python, Node.js, and Chromium through `scripts/`",
        f"- Bundle scope: {issue.scope}",
        "",
        "## Evidence",
        "",
    ]
    lines.extend(f"- {item}" for item in issue.evidence)
    lines.extend(["", "## Affected surfaces", ""])
    lines.extend(f"- {item}" for item in issue.surfaces)
    lines.extend(["", "## Acceptance criteria", ""])
    lines.extend(f"- [ ] {item}" for item in issue.criteria)
    lines.extend(["", "## Validation", ""])
    lines.extend(f"- [ ] {item}" for item in issue.validation)
    lines.extend(["", "## Out of scope", ""])
    lines.extend(f"- {item}" for item in issue.out_of_scope)
    if issue.close:
        lines.extend(
            [
                "",
                "## Resolution notes",
                "",
                "- Resolved by merged MR !44.",
                "- Closing because this issue now represents completed security work; follow-up hardening remains tracked through the playbook/roadmap.",
            ]
        )
    return "\n".join(lines) + "\n"


def standards_issue_body() -> str:
    return """## Summary

Standardize issue cadence, labels, and tracker/MR expectations for the current static NemoClaw course while preserving the repo as a future multi-course bundle.

## Current release target

- Course: static browser course under `web/nemoclaw/`
- Production: public static host or co-located NemoClaw launchable
- Contributor validation: host Python, Node.js, and Chromium through `scripts/`
- Bundle scope: bundle-wide process standard with current-course examples

## Evidence

- README describes the repository as a course bundle rather than a single-purpose app.
- CONTRIBUTING asks contributors to file focused issues with evidence before patches when scope crosses content, deployment, validation, or licensing.
- Reviewer-feedback issues #2-#9 need consistent acceptance criteria, validation, and public-safe evidence handling.
- Recent security issues #15 and #16 showed the need for agent-discoverable validation expectations.

## Affected surfaces

- `docs/issue_standards.md`
- `.gitlab/issue_templates/` and `.github/ISSUE_TEMPLATE/`
- `.gitlab/merge_request_templates/Default.md` and `.github/PULL_REQUEST_TEMPLATE.md`
- `README.md`, `CONTRIBUTING.md`, `docs/SKILL.html`, `docs/agent_process.md`, and `docs/release_playbook.md`
- GitLab labels and open issue descriptions

## Acceptance criteria

- [ ] Issue standards name the current static browser target and future bundle scope.
- [ ] Issue and MR templates make course/runtime/bundle scope explicit.
- [ ] Open reviewer-feedback issues preserve the PDF critique as summarized, public-safe evidence.
- [ ] Open operational/security issues use the same issue anatomy and label cadence.
- [ ] Validation commands are recorded in the MR.

## Validation

- [ ] `git diff --check`
- [ ] `python3 scripts/skills/skill_consistency.py`
- [ ] `python3 scripts/validation/validate_layout.py --quiet`
- [ ] `python3 scripts/skills/skill_contract.py`
- [ ] `python3 scripts/compliance/source_gate.py`
- [ ] `bash scripts/runtime/run_engine.sh --self-test`
- [ ] `python3 scripts/validation/validate_bundle.py --no-write --scope ship`
- [ ] `BUILD_PAGES_LANGS=0 bash scripts/build/build_pages.sh /tmp/nemoclaw_issue_standards_public`

## Out of scope

- Rewriting course content to resolve the reviewer issues themselves.
- Publishing private scanner output, DLI URLs, internal hostnames, tokens, or Cloudflare headers.
- Enabling public GitHub automation before branch protection, owners, and mirror policy are ready.
"""


class GitLabClient:
    def __init__(self, host: str, project_id: str, token: str | None) -> None:
        self.host = host
        self.api_root = f"https://{host}/api/v4"
        self.base = f"{self.api_root}/projects/{project_id}"
        self.headers = self._headers(host, token)

    def _headers(self, host: str, token: str | None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if token:
            headers["PRIVATE-TOKEN"] = token
            return headers
        cred = subprocess.check_output(
            ["git", "credential", "fill"],
            input=f"protocol=https\nhost={host}\n\n".encode(),
            stderr=subprocess.DEVNULL,
        )
        fields = dict(line.split("=", 1) for line in cred.decode().splitlines() if "=" in line)
        username = fields.get("username")
        password = fields.get("password")
        if not username or not password:
            raise RuntimeError("git credential fill returned no username/password")
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
        return headers

    def request(self, method: str, path: str, data: dict[str, str] | None = None) -> dict:
        body = None
        headers = dict(self.headers)
        if data is not None:
            body = parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = request.Request(self.base + path, data=body, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode() or "{}")
        except error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            if exc.code == 409:
                return {"_status": 409, "message": body_text}
            raise RuntimeError(f"{method} {path} failed: {exc.code} {body_text[:500]}") from exc

    def user(self) -> dict:
        req = request.Request(self.api_root + "/user", headers=self.headers)
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode() or "{}")


def token_from_env() -> str | None:
    for name in ("GITLAB_TOKEN", "GITLAB_PRIVATE_TOKEN", "PRIVATE_TOKEN", "GL_TOKEN", "GITLAB_API_TOKEN"):
        value = os.environ.get(name)
        if value:
            return value
    return None


def create_labels(client: GitLabClient, dry_run: bool) -> None:
    for name, color in LABELS.items():
        if dry_run:
            print(f"DRY label {name}")
            continue
        client.request("POST", "/labels", {"name": name, "color": color})
        print(f"label ensured: {name}")


def refresh_issues(client: GitLabClient, dry_run: bool) -> None:
    for issue in ISSUES:
        data = {
            "description": issue_body(issue),
            "labels": ",".join(issue.labels),
        }
        if issue.title:
            data["title"] = issue.title
        if issue.close:
            data["state_event"] = "close"
        if dry_run:
            print(f"DRY issue !{issue.iid}: labels={data['labels']}")
            continue
        client.request("PUT", f"/issues/{issue.iid}", data)
        print(f"issue refreshed: #{issue.iid}")


def find_standards_issue(client: GitLabClient) -> int | None:
    encoded = parse.urlencode({"search": STANDARDS_ISSUE_TITLE, "state": "opened"})
    found = client.request("GET", f"/issues?{encoded}")
    for issue in found if isinstance(found, list) else []:
        if issue.get("title") == STANDARDS_ISSUE_TITLE:
            return int(issue["iid"])
    return None


def create_standards_issue(client: GitLabClient, dry_run: bool) -> None:
    labels = ("area:docs", "kind:validation", "state:accepted", "severity:minor", "risk:learner-facing")
    if dry_run:
        print(f"DRY create standards issue: {STANDARDS_ISSUE_TITLE}")
        return
    existing = find_standards_issue(client)
    if existing:
        print(f"standards issue exists: #{existing}")
        return
    issue = client.request(
        "POST",
        "/issues",
        {
            "title": STANDARDS_ISSUE_TITLE,
            "description": standards_issue_body(),
            "labels": ",".join(labels),
        },
    )
    print(f"standards issue created: #{issue.get('iid')} {issue.get('web_url')}")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Iterable[str] = sys.argv[1:]) -> int:
    args = parse_args(argv)
    if not args.project_id:
        raise SystemExit("--project-id or CI_PROJECT_ID is required")
    if args.dry_run:
        print(f"DRY target: {args.host}/projects/{args.project_id}")
        create_labels(None, True)  # type: ignore[arg-type]
        refresh_issues(None, True)  # type: ignore[arg-type]
        create_standards_issue(None, True)  # type: ignore[arg-type]
        return 0

    client = GitLabClient(args.host, args.project_id, token_from_env())
    user = client.user()
    print(f"api auth ok: {user.get('username') or user.get('name')}")
    create_labels(client, False)
    refresh_issues(client, False)
    create_standards_issue(client, False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
