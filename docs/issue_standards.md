# Issue standards and cadence

This document owns issue anatomy, labels, tracker state, and public discussion routing.
Agent execution guardrails live in [`agent_process.md`](agent_process.md); protected release
authority lives in [`release_playbook.md`](release_playbook.md).

This repo is a multi-course bundle in spirit, but the current release target is a static browser
course:

- Current course: `web/nemoclaw/`
- Production delivery: GitHub Pages or another static host, plus a co-located NemoClaw launchable
- Local tooling: host-native build, browser, security, and compliance checks under `scripts/`

Write issues so a future course can reuse the same structure without hiding the
current scope. Name the current course/runtime explicitly, then state whether the
finding is course-specific or bundle-wide.

## Issue-first contract

Issues are the preferred contribution path when the reporter has evidence but not
a release-ready patch. A good issue must let a maintainer or agent answer four
questions before editing:

1. What exact learner/operator problem exists?
2. Where does it live in the bundle?
3. What evidence proves this is real?
4. What validation would make the fix reviewable?

Use `Closes #N` from an MR that satisfies every acceptance criterion so the host closes the issue
on merge. A partial MR uses `Addresses #N` and includes a `Remaining issue work` section naming
the unmet criteria. Do not use `Closes #N` for exploratory cleanup, partial hygiene, or a broad pass
that only improves one slice of a composite issue. Recheck the relationship at handoff after the
final diff and validation evidence are known.

Use the general Bug form for reproducible defects and the Feature form for concrete improvements.
The course-content, runtime/deployment, and source/licensing forms collect deeper evidence for those
specialized surfaces. Questions and unbounded ideas belong in Discussions after public intake opens.

## Required issue shape

Every actionable issue should contain these sections:

```markdown
## Summary
One paragraph naming the defect or improvement.

## Current release target
- Course: `web/nemoclaw/`
- Production: static browser course, optionally co-located with a NemoClaw launchable
- Local tooling: `scripts/`
- Bundle scope: course-specific or bundle-wide

## Evidence
- Reviewer note, repro, source citation, command output, screenshot, or scanner result.
- Redact secrets, private URLs, tokens, and internal-only deploy details.

## Affected surfaces
- Files, directories, pages, services, or deploy paths.

## Acceptance criteria
- Observable outcomes, not implementation wishes.

## Validation
- Commands, harnesses, browser checks, SCA jobs, source gate, or deploy smoke required.

## Out of scope
- Neighboring work that should not be folded into this issue.
```

Optional sections: `Suggested approach`, `Risk`, `Dependencies`, `Resolution notes`.

## Composite reviewer-feedback issues

The reviewer PDFs produced cross-cutting feedback. Keep these as composite issues
rather than dozens of tiny tickets, but make each composite issue bounded:

- Keep one pedagogy/runtime theme per issue.
- Preserve representative reviewer evidence, but do not paste long PDF excerpts.
- Name affected `web/nemoclaw` pages and any CPU service assumptions.
- Add acceptance criteria that let work land in multiple MRs.
- Split only when one issue starts mixing unrelated owners, validators, or risk.

The current representative buckets are:

| Bucket | Purpose |
|---|---|
| Scaffolding reduction | Hide framework/runtime internals that distract learners. |
| Lab flow and ergonomics | Make run, reset, stop, and prerequisite state obvious. |
| Visual QA | Fix unreadable or misleading diagrams and SVGs. |
| Prose and terminology | Remove jargon, define acronyms, and tighten prerequisite assumptions. |
| Concept setup | Introduce ReAct, tools, workflow agents, and MCP before code depends on them. |
| RAG/index pedagogy | Clarify indexing, vector similarity, and agentic RAG. |
| Security/privacy | Remove private URLs, exposed keys, unsafe token/code affordances. |
| Product/reference accuracy | Fact-check OpenClaw, OpenShell, NemoClaw, Hermes, and CLI claims. |

## Label standard

Use this taxonomy in GitLab and mirror it to GitHub when external intake opens.

Area labels: `area:web`, `area:cpu`, `area:deploy`, `area:scripts`, `area:docs`,
`area:materials`, `area:security`, `area:translation`.

Kind labels: `kind:bug`, `kind:course-content`, `kind:source-correction`,
`kind:accessibility`, `kind:question`, `kind:feature`, `kind:release`, `kind:validation`.

Risk labels: `risk:learner-facing`, `risk:deployment`, `risk:security-privacy`,
`risk:license-source`, `risk:generated-output`.

Severity labels: `severity:blocker`, `severity:major`, `severity:minor`,
`severity:advisory`.

Minimum label set:

- One `area:*`
- One `kind:*`
- One `state:*`
- One `severity:*`
- Add `risk:*` when learner-facing, deployment, source/licensing, generated output,
  or security/privacy risk exists.

Preferred state cadence:

| State | Meaning |
|---|---|
| `state:needs-triage` | New issue needs owner/routing. |
| `state:needs-evidence` | Claim is plausible but evidence is missing. |
| `state:accepted` | Work is valid and can be picked up. |
| `state:in-progress` | MR/branch active. |
| `state:ready-for-review` | MR exists and validation is reported. |
| `state:blocked-platform` | Needs DLI/Brev/Cloudflare/runner access. |
| `state:blocked-external-source` | Needs source/license/fact confirmation. |
| `state:released` | Fix merged/deployed or issue intentionally complete. |

Board columns: Needs triage, Needs evidence, Accepted, In progress, Review, Ready for
release, Released, Closed no action.

## Validation mapping

| Issue kind | Expected validation |
|---|---|
| Course content/prose | `validate_layout.py --quiet`, `skill_consistency.py`, `validate_bundle.py --no-write --scope ship`; prose validator when changing broad copy. |
| Visual/runtime page | Static gate plus browser/runtime harness or local Pages smoke. For scaffolding/lab-flow work, include `learner_flow_audit.py --self-test` and `learner_flow_runtime_audit.py` so the detector and lifecycle are both exercised. |
| External runtime integration | Targeted browser contract test plus public-safe endpoint evidence or an explicit platform blocker. |
| Static deployment | Built-artifact validation, deployed preview, and integrity comparison. |
| Security/dependency | Dependency floor audit, waiver audit, resolved-environment SCA when a lock changes, and source gate when the public surface changes. |
| Source/licensing | `source_gate.py`, provenance/materials check, short source excerpts only. |

## Closing and splitting

Close an issue only when the acceptance criteria are met, or when it is explicitly
superseded by a better-scoped issue. If a composite issue is partly fixed, leave it
open and add a resolution note listing what landed and what remains.

Split an issue when:

- It needs different owners or permissions.
- It mixes content, runtime, deployment, and security in a way that blocks review.
- One part is actionable now and another part depends on platform/source access.

## Public mirror considerations

Public GitHub issues should assume students and external contributors can see the
content. Use GitHub Discussions for broad learning help; Issues for actionable work.
Security reports, secrets, private DLI URLs, Cloudflare headers, internal hostnames,
and confidential scanner output belong in private GitLab or the configured private
vulnerability reporting path, not public Issues.

Recommended Discussion categories: Announcements, Questions, Course feedback, Ideas,
Show and tell, Troubleshooting. Convert a Discussion to an Issue after it identifies a
reproducible defect, concrete source correction, file-specific wording problem, or
validated accessibility/runtime issue. Ask for locations and safe evidence; never ask a
student to expose credentials, private URLs, or access headers.
