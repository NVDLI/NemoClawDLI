# Agent process guardrails

This note guides agents and maintainers through repository changes. It is especially important for
broad course prose.
Issue anatomy and tracker cadence live in [`issue_standards.md`](issue_standards.md).
Runtime checks live in [`lab_runtime_testing.md`](lab_runtime_testing.md).
Contained cross-model changes use the frozen protocol and evidence boundary in
[`agent_model_experiment.md`](agent_model_experiment.md).

## Start from the tracker

- Use `docs/issue_standards.md` as the issue anatomy and label cadence. The production target is
  the static `web/nemoclaw/` course. Host-native tools under `scripts/` build and verify it.
- Read the issue or MR before editing. If network or auth blocks the read, say that and work from local evidence only.
- Tie a fully satisfying MR to the tracker with `Closes #N` so merge closes the justification
  issue automatically. A partial MR uses `Addresses #N` and includes `## Remaining issue work`
  with the unmet acceptance criteria. Before handoff, compare the final diff and evidence with the
  issue checklist. Do not write `Closes #N` for partial hygiene, exploratory prose, or a
  blast-radius pass.
- Keep branch and commit naming aligned with the MR note and issue scope. If the work
  intentionally touches related issues, name those as related. Reserve a solved relationship for
  work that satisfies the issue.

## Preserve contributor and locale ownership

- Preserve every signed contributor commit when practical. If integration requires a deliberate
  cherry-pick, keep the original author and signoff. Credit substantial learner-facing work in the
  Unreleased section of `CHANGELOG.md` without publishing private contact details.
- Canonical English owns meaning and executable structure. Translators own the target language's
  phrasing. A language reviewer may accept a new source hash without changing localized HTML when
  the meaning is stable.
- Changes to localized wording require a qualified language reviewer. Mixed English and locale
  changes record that review in the MR as `Localization-Review: locale=Public Reviewer Name`.

## Contribution authority

- Keep idea intake cheap. A Discussion or structured Issue can carry a question, correction,
  source, or design without requiring code.
- Treat every patch as untrusted input, including patches from maintainers and capable agents.
  Require issue linkage and named surfaces. Record blast-radius evidence, command results, human
  ownership, risk, rollback, and explicit out-of-scope work.
- Keep active-finding identifiers and narratives, private tracker or service locations, personal
  corporate addresses, and credentials in approved private records. Repository text may contain
  generic controls and opaque fingerprints only. Run `sensitive_content_audit.py` against the tree
  and submission metadata. Include the complete proposed commit range.
- Install the hooks, but never claim they secure a repository. Local hooks provide early feedback
  and can be bypassed. Required CI validates the submitted commit; protected refs and environments
  control merge, deploy, and release authority.
- A hook must refuse and explain. It must not rewrite history or resolve conflicts. It must not
  force-push, weaken a test, or mutate a contribution merely to make it pass.
- For contribution, hook, workflow, permission, or release changes, use the contribution audit for
  focused iteration. Run the shared ship gate once afterward. Its mutation suite and current-tree
  result belong in CI artifacts so a human can inspect the exact boundary that passed.
- For changes to deployment topology, browser proxies, services, or storage, update
  `docs/security-architecture.json` and regenerate its SVG. Apply the same rule to privilege,
  authentication, secret flow, and release pipelines. Run
  `python3 -m unittest -v tests/validation/test_embedded_validator_suites.py` plus the audit.
  Production nodes remain source-backed. Repository-owned container surfaces remain absent.
- Changes to product scope or data handling update `docs/product-design.md`. Changes to the
  cryptography inventory, release evidence, or lifecycle test plan do too. Update
  `docs/release-test-plan.md` and `docs/release-evidence.json` in the same patch. Run
  `python3 -m unittest discover -v -s tests/validation`, followed by
  `python3 scripts/validation/release_evidence_audit.py`. Keep internal ticket bodies
  and program identifiers outside the repo. Scanner details, reviewer records, and approval links
  also remain in approved private systems.
- Public repository policy and work-product changes update the applicability matrix in
  `docs/release-evidence.json`. Run `python3 -m unittest discover -v -s tests/validation`, followed
  by `python3 scripts/validation/repository_work_products_audit.py`. A missing required file blocks
  release. Unresolved evidence or an unwired validator has the same effect.
- A new threat or security requirement updates `docs/security-control-disposition.md` and its
  enforcement surface together. Run `python3 -m unittest discover -v -s tests/validation`, followed
  by `python3 scripts/validation/threat_control_audit.py`. Verify the report's embedded architecture
  fingerprint and flow/objective register before interpreting findings. Collapse duplicate
  requirements, keep human reviewers out of the deployed topology, and name the enforceable defense
  for every open item. A human referral is not a defense. Do not present a host or provider
  requirement as a client-side mitigation. Keep release blocked unless the defense is Verified.
  Risk acceptance remains in its governing system. The repository stores only the public-safe
  release state; protected environments and workflow provenance bind an authorized deployment to
  its exact source and artifact.

## Course title, abstract, and objectives

- `web/nemoclaw/COURSE_CANON.md` is canonical for the English source course title, abstract, and learning objectives. Do not rewrite, shorten, paraphrase, translate, retitle, or reorder that copy.
- Run `python3 scripts/validation/course_contract.py` after touching the course home, foyer, generated course metadata, title text, abstract text, or learning objectives.
- The required `course_contract` suite in `validate_bundle.py` must fail if this copy drifts. This
  drift blocks release even when the separate prose findings are advisory.

## Broad prose and taxonomy passes

Follow [`course-prose-style.md`](course-prose-style.md) for learner-facing explanations and
instructions. Use the rules below when a change also affects repository-wide terminology.

- Define the vocabulary before rewriting pages. NemoClaw is the reference stack, while OpenClaw is the agent harness.
  OpenShell is the sandbox boundary for the stack, and the Brev launchable is the hosted course deployment used by learners.
- Grep every learner-facing surface for the terms being changed: course pages, generated SKILL descriptors, navigation helpers, edX helper pages, and script docs.
- Avoid replacement framing that creates new buzz. Patterns such as `not X; do Y`, `first-class part`, `peer runtime`, and `closest public sibling` need concrete nouns or should be cut.
- When a title, page order, or generated descriptor changes, update the generator and regenerated SKILL beacon together. Do not hand-edit generated SKILL output without updating its source.
- Run the prose validator on the affected snippets before the full gate when doing taxonomy work.

## Validation ladder

- Always run `git diff --check`.
- Run validator fixtures through `python3 -m unittest discover -v -s tests/validation`. Framework discovery
  owns test accounting and failure rendering. Do not print hand-maintained fractions, literal
  mutation totals, or fixed totals minus a failure count from validator code.
- Treat `docs/validation/latest.md` and `latest.json` as the current finding inventory.
  Do not maintain a second snapshot of counts or affected files in prose.
- Fix the learner or operator problem. Do not hide a surface, add decorative structure,
  flatten prose into stubs, or remove useful comments only to silence a detector.
- Use advisory findings to locate passages for review. A lower count matters only when the diff is
  clearer and preserves the underlying claim. The rewrite must preserve security and maintainability.
- For branch feedback, run
  `python3 scripts/validation/release_gate.py --tier fast --no-write --changed-since origin/main --jobs 4`.
  Before push, run the ship tier once while retaining complete current-tree audits.
  The `--changed-since` option skips only detector mutation suites whose implementation and contract
  inputs did not change. Adds, deletes, renames, copies, and paths with no declared detector ownership
  select the full mutation matrix automatically. Omit it for release-candidate validation.
- Use standalone validators while editing or to diagnose the named shared-gate failure. Do not run a
  full list of constituents and then rerun the gate that already composes them.
- Pre-push classifies external release follow-ups over `origin/main..HEAD`. Carry reported
  architecture and scan actions into the authorized release record. Do the same for license and
  final-artifact actions. A green repository pipeline does not complete those operator steps.
- For page title, navigation, or deploy-path changes, run `BUILD_PAGES_LANGS=0 scripts/build/build_pages.sh` before calling the MR ready.
- For Studio, runnable-cell, browser-runtime, or OpenClaw changes, also run the harness named in `lab_runtime_testing.md` and the relevant `scripts/validation/*_audit.py` file.
- For learner-facing code or lab-flow changes, run `learner_flow_audit.py`, its mutation self-test,
  and `learner_flow_runtime_audit.py` against source and built Pages output. A closure claim needs
  evidence for disclosure, prerequisite readiness, Run/Stop/Reset, error recovery, and viewport stability.
  A screenshot of one happy state is insufficient.
- For branch staging, require a passing blocking `test` job, confirm the Pages job SHA matches the live branch head, and probe the deployed course plus both branch manifests. Only paths present in the current classic-Pages artifact may appear in the foyer selector.
- For a stateful browser bug, test the whole lifecycle. Enter the state, then leave it through both
  a successful sibling result and an error. Remount the component before reloading or navigating.
  Run that matrix against both source and built Pages output.
- Pair lifecycle gates. A cheap static validator should catch missing selectors, cleanup calls, and CSS contracts; a real browser workflow must prove computed visibility and persisted-state behavior. Neither gate substitutes for the other.

## Visual changes

- `web/nemoclaw/assets/SKILL.html` owns mount and provenance rules. It also defines labels, themes,
  lightboxes, and rendered previews. Read it before changing an asset or its placement.
- Run `figure_audit.py`, `source_gate.py`, and the ship bundle gate. Show the requester
  the rendered result or name the exact harness blocker.

## Safe auth and metadata updates

- Do not print token-bearing environment variables. Never run `env | rg TOKEN`, `printenv | grep TOKEN`, or equivalent output-producing probes for GitLab or service credentials.
- Prefer `glab auth status` for GitLab CLI state. If API access is needed and CLI is unavailable, use `git credential fill` in a script that reads the credential and sends it directly to the request without printing the secret.
- If auth fails, report the exact `401`, `403`, host-key, or push-permission error and stop after one careful retry.

## Editing discipline

- Read the current diff before editing. Preserve user changes in touched files.
- Use repo-native tools from WSL for WSL worktrees. Do not use PowerShell `Set-Content` against WSL files.
- If `apply_patch` is unavailable, a short repo-local rewrite script is acceptable, but inspect `git diff` immediately after it runs.
- Never commit a contributor home, mounted drive, cache, tool-runtime, or absolute local file URI.
  Use repository-relative paths, environment variables, or `scripts/runtime/` discovery helpers.
  Then run `python3 -m unittest discover -v -s tests/validation` and the local-path audit itself.
