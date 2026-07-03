# Contributing

This repository is the internal release-candidate workspace for proposed open-source NVIDIA
DLI course material. External publication remains pending OSRB approval; see
[`RELEASE_STATUS.json`](RELEASE_STATUS.json).
It packages authored content, shared services, deployment, and validation in one release
tree. Content is organized by execution surface: `web/` is browser-only and remote-service
aware, `cpu/` is the shared microservice stack, and `deploy/` is the operator surface for
standing the bundle up on DLI platform or local compute.

## Two Contribution Paths

The easy path contributes knowledge. The guarded path changes the release.

Use the issue path when you have expertise about the course, platform, security model,
source material, or learner experience but do not already have a release-ready patch.
File a focused Issue with the affected files or URLs, the observed behavior, the expected
behavior, and any source or runtime evidence. The issue anatomy and cadence live in
[`docs/issue_standards.md`](docs/issue_standards.md). This is the preferred path for
cross-cutting course claims, pedagogy, vendor/source concerns, and deployment assumptions.
Use structured Issues for actionable defects. After external intake is approved and enabled,
use Discussions for questions, brainstorms, learning friction, and ideas that do not yet have
a concrete defect. Neither route requires code. Report vulnerabilities privately through
[`SECURITY.md`](SECURITY.md).

Use the direct patch path when you can carry the change through the structured release
process. The full release and external-mirror model lives in [`docs/release_playbook.md`](docs/release_playbook.md). A direct MR should update the source, declared blast-radius files, and validators
when the failure class should not recur. Link the tracker with `Addresses #N` unless the
change fully closes the issue.

A patch is not trusted because a person or agent produced it, or because it passes one local
command. It becomes eligible to merge only after required CI runs on the submitted commit,
the MR or PR records concrete evidence and remaining risk, review ownership is clear, and
protected-ref policy accepts it. Release and deployment writes require a separate protected
operator action.

Keep the compact submission contract at the top of an MR. GitLab exposes only the leading
description window to CI, so Summary, Issue link, Surfaces touched, Blast radius checked,
Validation evidence, Human ownership, Risk and rollback, and Out of scope must appear before
long rationale, screenshots, or logs.

## Orientation

Read [`AGENTS.md`](AGENTS.md) first. Every directory carries a
`SKILL.html` whose `skill-meta` JSON block is the machine-readable brain for that
directory. [`SKILL_CONTRACT.md`](SKILL_CONTRACT.md) specifies that format. The root
`SKILL.html` tenets and validation suites set the content bar.

For localization, start at [`scripts/translate/SKILL.html`](scripts/translate/SKILL.html),
then open the target locale node, such as [`scripts/translate/locales/pt-BR/SKILL.html`](scripts/translate/locales/pt-BR/SKILL.html)
or [`scripts/translate/locales/es-ES/SKILL.html`](scripts/translate/locales/es-ES/SKILL.html).
Translate learner-facing prose in the sparse `i18n/<code>/` overlay. Do not copy standalone
runtime modules, assets, data, or machine-contract pages into it. Inline executable structure
must remain equivalent to English; localized UI strings may differ. Locale profiles also reject literal wording
that is grammatical but unnatural for the target student and developer audience.

## Structured Release Process

1. Start from a clean branch for one coherent release concern.
2. Read the relevant Issue or MR before editing.
3. Sign every commit under the Developer Certificate of Origin in [`DCO.md`](DCO.md).
4. Update the source surface and every declared blast-radius file.
5. Keep course title, abstract, and objectives verbatim from [`web/nemoclaw/COURSE_CANON.md`](web/nemoclaw/COURSE_CANON.md).
6. Add or update a validator when the same class of problem should not recur.
7. Run the validation ladder below.
8. Open an MR that names the issue relationship and lists validation results.

Use `git commit --signoff` to add a `Signed-off-by` trailer matching the commit author. CI checks
every commit in the proposed range. If the check fails, follow the repair guidance in `DCO.md`;
do not squash away another contributor's authorship or treat a signoff as permission to submit
third-party material.

For a stacked merge request whose target is another unmerged proposal branch, preserve the original
signed commits. Do not use the host's squash or merge button: its generated commits do not inherit
DCO trailers and will fail the parent proposal's complete-range check. Follow the maintainer-owned
fast-forward or deliberate rebase/cherry-pick procedure in [`DCO.md`](DCO.md).

## Install the Hooks

```bash
bash scripts/build/install-hooks.sh
```

This resolves Git's real hook directory, including linked worktrees, then installs two hooks:

- `pre-commit`: protected-branch refusal, contributor-local and sensitive-content boundaries,
  contribution audit, corruption guard, canvas-HTML validation, and page-runtime smoke checks.
- `pre-push`: behind-branch refusal, complete-history signoff and content checks, external release
  reminders, then one change-aware canonical ship gate. It may reuse only an identical clean local
  success; required CI always reruns on the submitted commit.

A local hook is feedback, not authority. Hooks are intentionally early and actionable, but
Git allows them to be bypassed. Required CI, branch or tag rulesets, protected human review,
and protected release actions close that gap.

## Validate Before Pushing

```bash
python3 scripts/validation/release_gate.py --tier fast --no-write --changed-since origin/main
```

Run `python3 scripts/validation/release_gate.py --tier ship --no-write --changed-since origin/main` once before
pushing a proposal. The gate always audits the complete current tree and skips only unaffected
detector mutation suites. Omit `--changed-since` for a release candidate. Use constituent commands
only for focused iteration or diagnosis; the shared gate already composes them. See
[`docs/release-test-plan.md`](docs/release-test-plan.md) for claim and evidence mapping.

Service-stack notebook tests need the lab services running:

```bash
python3 workspace/run_tests.py services --notebook <notebook>
```

For browser or Studio changes, also run the browser harness described in
[`docs/lab_runtime_testing.md`](docs/lab_runtime_testing.md).

## Conventions

The full operating creed is projected into the root `SKILL.html` skill-meta. Run
`python3 scripts/validation/tenets.py` to inspect the gate that enforces it. Highlights:

- Edit content in place. Scratch work goes to `/tmp` and is never committed.
- Authored prose avoids em-dashes. Rewrite the sentence rather than swap punctuation.
- `web/` stays browser-only and cannot assume student-provisioned microservices.
- `cpu/` owns the shared service stack a course may call through declared routes.
- `deploy/` owns compose and nginx configuration.
- Do not commit lab-generated runtime output, caches, or the `public/` Pages build.

## Contribution Terms

This repository is licensed under Apache-2.0. Unless you clearly mark a submission as
`Not a Contribution`, any contribution intentionally submitted for inclusion is offered
under Apache-2.0, with the contribution terms in [`LICENSE`](LICENSE).
This Apache-2.0 project does not require a separate contributor license agreement. Every commit
must carry the DCO 1.1 signoff defined in [`DCO.md`](DCO.md). The signoff certifies origin and
submission rights; it does not transfer copyright or replace review.

Do not submit material you do not have the right to contribute. Third-party text, images,
datasets, model artifacts, copied examples, cached web pages, and generated assets need
source and license disposition before they are committed. The governing process is
[`scripts/compliance/docs/vendor_policy.md`](scripts/compliance/docs/vendor_policy.md), and the required gate is:

```bash
python3 scripts/compliance/source_gate.py
```
