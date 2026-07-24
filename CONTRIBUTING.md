# Contributing

This NVIDIA DLI course repository is approved for public release; see
[`RELEASE_STATUS.json`](RELEASE_STATUS.json). It is a Full-OSS-Project, OSS Type I. Public GitHub
owns the canonical course workflow from planning through release. Internal GitLab consumes
reviewed public changes for additional validation and internal deployment. This scope excludes the
NemoClaw product, its launchable, and the product runtime.

The release tree packages authored browser content with build and validation tools. Browser work
belongs in `web/`; repository tooling belongs in `scripts/`. The repository does not own a service
stack, lab image, or container topology.

## Two Contribution Paths

The easy path contributes knowledge. The guarded path changes the release.

Use the issue path when you have relevant expertise but no release-ready patch. That expertise may
concern the course or its platform. Security observations and learner experience also belong here.
File a focused Issue that identifies the affected surface. Describe the observed behavior and the
expected result, then attach supporting evidence. The issue anatomy and cadence live in
[`docs/issue_standards.md`](docs/issue_standards.md). This path works best for cross-cutting course
claims and pedagogy. Use it for source concerns or deployment assumptions as well.
Use structured Issues for actionable defects. Use Discussions for questions or early ideas.
Learning friction without a concrete defect belongs
there as well. Neither route requires code. Report vulnerabilities privately through
[`SECURITY.md`](SECURITY.md).

Use the direct patch path when you can carry the change through the structured release
process. The full release and external-mirror model lives in [`docs/release_playbook.md`](docs/release_playbook.md).
A direct MR should update its source and declared blast-radius files. If recurrence is plausible,
include a validator. An issue-scoped change that satisfies every acceptance
criterion uses `Closes #N` so the host closes the issue on merge. A partial change uses
`Addresses #N` and includes a `Remaining issue work` section naming the unmet criteria. Compare
the final diff and evidence with the issue checklist before handoff; do not leave a fully satisfied
issue on a non-closing relationship.

A patch is not trusted because a person or agent produced it, or because it passes one local
command. It becomes eligible to merge only after required CI runs on the submitted commit. The
proposal must record concrete evidence and remaining risk. Review ownership must be clear, and
protected-ref policy must accept the result. Release and deployment writes require a separate
protected action.

Keep the compact submission contract at the top of an MR. GitLab exposes only the leading
description window to CI. Preserve the template order from Summary through Out of scope, and keep
every required heading inside the first 2,700 characters. Put longer rationale below that block.

## Orientation

Read [`AGENTS.md`](AGENTS.md) first. Every source directory carries a
`SKILL.html` whose `skill-meta` JSON block is the machine-readable brain for that
directory. [`SKILL_CONTRACT.md`](SKILL_CONTRACT.md) specifies that format. The root
`SKILL.html` tenets and validation suites set the content bar.

Adding a directory also adds its beacon. Run `python3 scripts/skills/gen_directory_beacons.py`,
then review the generated summary and links. CI derives the complete directory set from tracked
and proposed files and provides no exemption mechanism.

For localization, start at [`scripts/translate/SKILL.html`](scripts/translate/SKILL.html). Then open
either current locale profile:
[`pt-BR`](scripts/translate/locales/pt-BR/SKILL.html) or
[`es-ES`](scripts/translate/locales/es-ES/SKILL.html).
Translate learner-facing prose in the sparse `i18n/<code>/` overlay. Do not copy standalone
runtime modules or machine-contract pages into it. Assets and data remain shared too. Inline executable structure
must remain equivalent to English; localized UI strings may differ. Locale profiles also reject literal wording
that is grammatical but unnatural for the target student and developer audience.
For canonical learner-facing explanations, follow
[`docs/course-prose-style.md`](docs/course-prose-style.md). That contract also governs instructions
and supporting text. Record page-specific decisions in the Issue or MR instead of maintaining a
repository scorecard.

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

### Contributor credit and localization ownership

Preserve signed authorship when integrating another contributor's work. Add a public thank-you in
the Unreleased section of [`CHANGELOG.md`](CHANGELOG.md) when a learner-facing translation or other
substantial contribution lands, while keeping private contact details out of the repository.

Canonical English defines meaning and executable structure, while translators own the target
language's wording. If an English edit leaves that meaning unchanged, a language reviewer may accept the new
source hash without rewriting localized HTML. Changes to localized prose require review by someone
qualified in that locale. Record that review in the MR with a public name:

```text
Localization-Review: es-ES=Public Reviewer Name
```

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

Local hooks provide early feedback. Required CI and protected refs remain authoritative because Git
allows hooks to be bypassed. Human review identifies accountability but is not a compensating
control. An unresolved release concern stays blocked until its defense is verified or the protected
release owner accepts the residual risk through the governing process. The repository does not
store that private decision. Protected environments authorize deployment, while workflow
provenance binds the deployed artifact to the exact reviewed commit.

## Validate Before Pushing

```bash
python3 scripts/validation/release_gate.py --tier fast --no-write --changed-since origin/main --jobs 4
```

Run `python3 scripts/validation/release_gate.py --tier ship --no-write --changed-since origin/main --jobs 4` once before
pushing a proposal. The gate always audits the complete current tree and skips only unaffected
detector mutation suites. New, deleted, renamed, copied, and otherwise unclaimed paths automatically
select the full mutation matrix, regardless of directory or extension. Omit `--changed-since` for a release candidate. Use constituent commands
only for focused iteration or diagnosis; the shared gate already composes them. See
[`docs/release-test-plan.md`](docs/release-test-plan.md) for claim and evidence mapping.

Python validator fixtures use standard-library `unittest` discovery, while JavaScript fixtures use
Node's built-in `node:test`. Add framework-visible tests under `tests/validation`; the shared gate
discovers them without a registry edit whenever tests change and on every release candidate. Do not maintain numeric totals in CLI output; the harness rejects fixed
denominators in shared fast and ship gates.

For browser or Studio changes, also run the browser harness described in
[`docs/lab_runtime_testing.md`](docs/lab_runtime_testing.md).

## Conventions

The full operating creed is projected into the root `SKILL.html` skill-meta. Run
`python3 scripts/validation/tenets.py` to inspect the gate that enforces it. Highlights:

- Edit content in place. Scratch work goes to `/tmp` and is never committed.
- Authored prose avoids em-dashes. Rewrite the sentence rather than swap punctuation.
- `web/` stays browser-only and cannot assume student-provisioned microservices.
- Host Python, Node.js, and Chromium run repository checks; external isolation is operator-owned.
- Do not commit lab-generated runtime output, caches, or the `public/` Pages build.

### Student-visible code

Runnable cells are teaching surfaces. Keep application plumbing behind named helpers.

- Keep an editable RunCell at or below 120 nonblank lines. Move transport and rendering machinery
  behind a named helper. Session and compatibility code belongs there too. The cell should expose
  the helper's contract and return its result.
- Use descriptive names. Single letters are reserved for familiar local coordinates or tiny loop
  indexes; a cell must not make the learner decode a collection of unrelated one-letter variables.
- Put one logical statement on a line. A compact expression may be readable, but repeated
  multi-statement lines are not an acceptable substitute for structure.
- Return the structured outcome. Use `helpers.log` to show progress and evidence. Keep the value
  computed by the exercise as its return result; the runtime must display both when both exist.
- Use the RunCell or CanvasFlow Stop signal for every long operation. Prefer `helpers.delay(ms)`
  to raw timer promises, and combine a cell signal with any timeout-specific AbortController.
- When an intermediate value or alternate input helps the lesson, include one clearly labeled,
  commented-out `helpers.log.json(...)`, `helpers.log.details(...)`, or alternate assignment at
  the relevant line so a learner can reveal it without inventing instrumentation from scratch.
- Name cross-cell `state` inputs and outputs near the top of the cell. Guard missing prerequisites,
  then return a compact summary of the state written for the next step.

`python3 -m unittest discover -v -s tests/validation` mutation-tests these rules; the normal
`cell_audit.py` run enforces their deterministic subset across every numbered lesson.

## Contribution Terms

This repository is licensed under Apache-2.0. Unless you clearly mark a submission as
`Not a Contribution`, any contribution intentionally submitted for inclusion is offered
under Apache-2.0, with the contribution terms in [`LICENSE`](LICENSE).
This Apache-2.0 project does not require a separate contributor license agreement. Every commit
must carry the DCO 1.1 signoff defined and reproduced verbatim in [`DCO.md`](DCO.md). The signoff
certifies origin and submission rights. It does not transfer copyright or replace review.

Do not submit material you do not have the right to contribute. Third-party text, images,
datasets, model artifacts, copied examples, cached web pages, and generated assets need
source and license disposition before they are committed. The governing process is
[`scripts/compliance/docs/vendor_policy.md`](scripts/compliance/docs/vendor_policy.md), and the required gate is:

```bash
python3 scripts/compliance/source_gate.py
```
