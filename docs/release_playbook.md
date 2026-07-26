# Release playbook

This playbook defines how the course operates in
[`NVDLI/NemoClawDLI`](https://github.com/NVDLI/NemoClawDLI), the canonical Full-OSS DLI course
repository after approved cutover. The repository keeps authored content,
deployment, validation, public planning, and governance together.

Current state: approved for public release and populated for protected review. See
[`RELEASE_STATUS.json`](../RELEASE_STATUS.json). Private approval evidence remains in its governing
system and is not copied into this repository.
The GitHub Pages and release workflows must run
`contribution_safety_audit.py --require-publication-approved` before external writes.
That guard validates the public-safe lifecycle state. Protected GitHub environments provide
independent release authorization, and workflow provenance binds each published artifact to its
tested commit.

## Public GitHub release boundary

Branch pushes and pull requests do not publish a release. Pages and release writes require a
protected ref, a passing exact-head workflow, the approved lifecycle state, and approval through
the named GitHub environment. The repository records only the authorization state. It must not
contain email, ticket, reviewer identity, or other private approval evidence.

Changing `RELEASE_STATUS.json` cannot bypass this boundary: the change still needs required checks,
independent protected-branch review, and the protected deployment environment. Generated manifests,
checksums, SBOMs, and provenance bind the resulting artifact to the tested commit.

## Scalable recommendation

Use a cutover and integration model:

1. **Reviewed internal source**: NVIDIA internal GitLab supplies the approved cutover snapshot.
2. **Approved public cutover**: populate GitHub from the reviewed release tree, activate the required
   host controls, and record GitHub as the canonical course repository.
3. **Full public operation**: manage planning, Issues, Discussions, pull requests, public CI, tags,
   and releases on GitHub. NVIDIA retains merge and release authority through protected review.
4. **Governed internal integration**: audit public `main` from trusted internal CI every week. Public changes
   enter GitLab only through `integration/github-main` and a normal reviewed MR; automation never
   writes a protected ref.
5. **Release train**: tag public releases and publish Pages from protected GitHub refs. Internal DLI
   deployment remains a separate manual promotion of the same reviewed public commit.

The selected public course repository, `NVDLI/NemoClawDLI`, is an NVIDIA-owned Full-OSS-Project
intended as **OSS Type I**. Prepublication staging in GitLab does not make the course repository
partially open source.
This classification is limited to `NVDLI/NemoClawDLI` and its static course artifacts. It does not
classify or release the NemoClaw product, launchable, runtime, or service deployments. The
governing system records the course classification and release authorization outside the
repository. Repository text and green CI cannot create that authorization.

Default rule: **issue-first, patch-second**. Students with domain evidence file structured Issues. Students who can carry a fix through validation open PRs using the structured release process.

## Contribution trust model

[`CONTRIBUTING.md`](../CONTRIBUTING.md) owns intake, submission evidence, signoff, and the
validation ladder. [`issue_standards.md`](issue_standards.md) owns issue shape and tracker
cadence. `README.md` owns maintainer authority; `CODE_OF_CONDUCT.md`, `SUPPORT.md`, and
`DCO.md` own their named public policies. This playbook owns host and release-operator
configuration.

Host settings are not versioned by this repository. Workflow files can request read-only tokens,
environments, and checks, but only a host administrator can activate rulesets, required reviewers,
prevent self-review, and restrict bypass. The operator must verify both halves: repository policy
with `contribution_safety_audit.py`, then live host settings and Rule Insights before public intake
or release.

For the internal GitLab project, run the read-only live audit before merging governance work and
before each release train:

```bash
python3 scripts/validation/gitlab_governance_audit.py --self-test
python3 scripts/validation/gitlab_governance_audit.py --project "$CI_PROJECT_ID" \
  --report docs/validation/gitlab-governance.json
```

The audit reports every weak host control with its exact setting. Its report is evidence, not a
substitute for the host audit log or a human review of who holds the named roles.

Surface ownership and task-specific gates live in the root `SKILL.html`, `docs/SKILL.html`,
and nearest directory beacon.
[`agentic-compliance-suite.md`](agentic-compliance-suite.md) explains why those discovery layers,
deterministic checks, evidence, and protected decisions remain separate.

## Maintainer operating plan

This playbook is the maintainer entry point. Detailed procedures remain with their executable or
reviewable owners:

| Responsibility | Canonical owner |
|---|---|
| Dependency management and software composition analysis | [`dependency_security.md`](dependency_security.md) |
| Issue triage and tracker state | [`issue_standards.md`](issue_standards.md) |
| CI/CD and protected publication | This playbook and [`pages_deploy.md`](pages_deploy.md) |
| Testing and evidence ownership | [`release-test-plan.md`](release-test-plan.md) |
| Release packaging, promotion, rollback, and recovery | [`release_artifacts.md`](release_artifacts.md) |
| Version history | [`../CHANGELOG.md`](../CHANGELOG.md) |

Maintainers review these owners when their related surface changes. Host assignments live in teams,
rulesets, protected environments, and `CODEOWNERS` after stable public handles exist.

## External repository population

The initial `NVDLI/NemoClawDLI` population must come only from the reviewed release tree. At
cutover, GitHub becomes canonical for project activity and GitLab becomes an integration,
validation, and internal deployment consumer.

Required constraints:

- Populate only reviewed protected branches and release tags at cutover. Enable public planning,
  Issues, Discussions, and pull requests as part of the same Type I launch instead of maintaining
  a read-only mirror phase.
- Keep divergent refs protected so integration failures stop instead of overwriting unexpected state.
- Use SSH or a scoped release-bot token, not a personal account.
- Protect `main`, `release/*`, and tags on the external host.
- Run `source_gate.py` and `local_path_leak_audit.py` before mirror publication.
- Approve the ancestry strategy before copying history. If internal ancestry is not approved for
  publication, initialize the external repository from the validated release tree instead of
  copying internal commit history.
- Do not mirror CI secrets, DLI deploy credentials, model keys, Cloudflare headers, or private launch URLs.

### Welcoming public entrypoint

Prepare and verify the entrypoint before announcing public intake.

1. Set the repository description to one plain sentence about the DLI course. Set the website to the
   reviewed course landing page and use only accurate NVIDIA-approved topics.
2. Confirm that the rendered README gives a newcomer three immediate routes: take the course, run it
   locally, or contribute. Keep detailed procedures in their canonical documents.
3. Enable the checked-in Issue forms and pull-request template. Pin a short Discussion welcome that
   links to contribution, support, conduct, and private security reporting.
4. Configure branch, tag, environment, dependency, code-scanning, and secret controls before
   announcing the repository. Do not invite contributions while required checks are advisory.
5. Review the repository in a signed-out browser. Every first-touch link must resolve without
   internal access, and no page may expose private hosts, credentials, or prepublication evidence.
6. Record the anonymous check, live ruleset state, and named owner in the cutover evidence. A green
   repository audit does not verify unversioned host settings.

## Dual-repository integration cadence

After external contribution opens, configure one GitLab schedule named `github-main-integration`
for **Monday at 09:00 UTC** on protected `main`, with `EXTERNAL_INTEGRATION_AUDIT=1`. This is the
weekly external integration audit. The job fetches public GitHub with a bounded, blob-filtered
history and runs `repository_sync_audit.py` from the trusted internal checkout. It never executes
code from the fetched ref.

The schedule detects work; it does not merge it:

1. Equivalent trees need no inbound MR.
2. An external-ahead state creates a maintainer task to update `integration/github-main` from the
   reviewed public commits and open an MR into internal `main`.
3. An internal-ahead state is policy drift after cutover. Do not publish GitLab-only history.
   Propose the source change through the public GitHub review flow, then import the reviewed commit.
4. A diverged state blocks integration until a maintainer reconciles from canonical GitHub and
   records the GitHub commit, GitLab commit, and resulting tree digest in the MR.
5. The integration MR runs the full internal contribution, secret, dependency, localization,
   browser, and release gates without privileged deployment credentials.
6. After cutover, internal GitLab does not publish source back to GitHub. Automation must
   **never force-push** GitHub or GitLab to hide divergence.

Repository schedules are host settings. The checked-in job and self-test prove the implementation,
while the release owner must verify the live cadence, protected schedule owner, notifications, and
last successful run before each release train.

Branch policy:

| Ref | Source | External writes | Purpose |
|---|---|---|---|
| `main` | protected GitHub review, then reviewed GitLab import | no direct pushes | canonical public source and internally validated integration copy |
| `release/*` | release manager | no direct pushes | frozen public release train |
| `integration/github-main` | reviewed public commits | internal maintainer branch only | external-to-internal reconciliation MR |
| `student/*` | forks | contributors write in forks | student work in progress |
| `localize/*` | contributor-owned | no protected-ref access | sparse same-branch locale work reviewed with Localization Studio |
| `v*` tags | release manager | no direct pushes | immutable public releases |

## External GitHub settings

Configure these controls on `NVDLI/NemoClawDLI` before the repository accepts public content or
community intake:

- Enable Issues at External intake.
- Enable Discussions for questions, learning friction, and broad ideas that are not actionable defects.
- Enable Projects for the triage/release board.
- Add `.github/CODEOWNERS` only after real NVIDIA org/team handles exist. Owners should cover `web/`, `scripts/`, `docs/`, and source-governance paths.
- Create an active branch ruleset for `main` and `release/*`. Require a pull request, one approval,
  dismissal of stale approvals, approval of the most recent push by someone else, resolved review
  threads, and the strict `test` status from the `pages` workflow. Block deletion and force pushes.
  Give no person an always-bypass lane; if automation needs bypass, scope it to a named GitHub App.
- Create an active tag ruleset for `v*`. Restrict tag creation, update, and deletion to the release
  manager or release App. A workflow consumes an existing protected tag; it does not mint one.
- Use GitHub Actions environments for public Pages. Use required reviewers for production and concurrency so only one deploy runs at a time.
- Configure both `github-pages` and `github-release` with required reviewers, prevent self-review,
  disallow administrator bypass, and restrict deployment branches or tags. Review environment and
  ruleset bypass events in Rule Insights after each release.
- Set the default workflow token to read-only and prevent workflows from approving pull requests.
- Require approval before a fork pull request runs. Never send fork workflows write tokens,
  repository secrets, or environment authority.

## Public GitHub security baseline

Enable the dependency graph, dependency review, Dependabot alerts, code scanning,
secret scanning, push protection, private vulnerability reporting, and protected
deployment environments before public intake. Fork jobs remain read-only and receive no
secrets. Keep private runtime names, credentials, internal topology, confidential findings,
and restricted scanner output in approved internal systems.

Host webhook checks fire after a ref already exists on GitHub, so an Actions run, a code-scanning
result, or a secret-scanning alert reports a problem rather than preventing it, and push protection
blocks only the patterns GitHub itself recognizes. Prevention for repository-defined classes such as
restricted finding details and ephemeral infrastructure identifiers comes from the local hooks and
from the direct `sensitive_content_audit.py` guard on every repository-owned publication path, which
refuse an ordinary commit or publish before those bytes leave the workstation. Neither is a merge
boundary: a hook can be skipped and a local guard can be edited, so required CI on the exact head
plus branch and tag rules stay authoritative for what may merge or deploy.

The stable `Trusted full-tree sensitive-content boundary` check runs through
`pull_request_target`, so GitHub loads its workflow and scanner from the trusted base branch. It
fetches the proposed head into the base repository's object database, verifies the event SHA, and
scans every proposed blob without checking out the head or loading candidate actions. The job has
only `contents: read`, receives no secrets, and cannot be disabled by a pull request that edits its
own workflow or validator. After this contribution merges, make that stable check required on
`main`; retain the ruleset's existing administrator bypass behavior.

Before calling a pull request security-green, inspect the complete check-run set on its exact head.
The repository-owned `analyze` jobs and SARIF policy do not replace GitHub's separate
`github-advanced-security/CodeQL` result. Run
`scripts/security/audit_github_code_scanning.py` and require both a successful host check and zero
open alerts on `refs/pull/<number>/merge`. Fix actionable findings. Dismiss only an exact,
source-bound reviewed result, using the accurate GitHub reason and a public-safe comment; the
repository disposition remains time-boxed and mutation-tested.

Repository dependency floors, exact locks, SCA layers, waiver handling, SBOM boundaries,
and the hardening backlog live in [`dependency_security.md`](dependency_security.md).
Publication assets and retention live in [`release_artifacts.md`](release_artifacts.md).
The complete release acceptance matrix lives in
[`release-test-plan.md`](release-test-plan.md).

## Internal GitLab settings

Use these for prepublication staging and the internal integration copy after cutover:

- Protect `main`, `nemoclaw-only`, `release/*`, and tags.
- Set `main` push access to No one, disable force push, and allow maintainers to merge only through MRs.
- Require Code Owner approval on `main`. `.gitlab/CODEOWNERS` assigns the inert root manifest,
  core and SCA modules, release gate, governance validators, hooks, and GitHub workflows to named
  owners. Keep this host setting enabled; a repository cannot protect a validator from an author
  who is allowed to replace both the validator and its workflow without owner approval.
- Require a successful pipeline and resolved discussions. In a one-operator project, require the
  protected manual `human_review` job after the exact commit's live preview smoke; restrict its
  environment to named human operators. With two active maintainers, prefer an independent MR
  approval and keep the protected action as release-owner acceptance.
- Protect `v*` tags and name the eligible human release operators explicitly instead of granting
  tag creation to every Maintainer-role bot.
- When pipeline-triggerer self-approval is enabled for one operator, make the `v*` creator set
  exactly match that sole production deployer. Add or remove operators across tag creation,
  protected production, deployment approval, and human review as one audited change.
- Keep production Pages deploy manual and protect the `production` environment with explicit
  human deployers. In a one-operator project, an environment approval rule naming that sole
  operator must also allow the pipeline triggerer to approve; otherwise every deployment
  deadlocks. When another active operator can supply independent review, disable self-approval
  and require that reviewer. Review environments remain isolated, manual, and short-lived
  without production authority.
- Keep branch preview deploys manual, isolated under branch slug paths, built with production root from a protected ref, and blocked by the required test gate. On classic Pages, expose only preview paths present in the latest combined artifact.
- Protect `live-interface-review` and `dli-cdn-production` environments. Limit both to named internal
  operators; limit `dli-cdn-production` to the project-locked devbox runner. Source branch, exact
  commit, successful gate job, language subset, and immutable/stable channel are the complete
  operator vocabulary. Keep the publisher binary and AWS account configuration root-owned.
- Keep protected live credentials and the read-only GitLab evidence token as environment-scoped
  file variables. Keep AWS credentials outside GitLab in the root-owned isolated publisher on the
  devbox. Owner-only `glab` inputs select reviewed refs and languages; they never carry credentials
  or free-form process settings. Public GitHub receives no secret, runner, or CDN authority edge.
- Use templates in `.gitlab/issue_templates/` and `.gitlab/merge_request_templates/`.
- Use labels and milestones as the project-management source. Mirror the same taxonomy to GitHub.
- Keep `docs/issue_standards.md` aligned with tracker labels, issue templates, and MR templates.

## Release workflow

Issue and patch flow live in [`issue_standards.md`](issue_standards.md) and
[`CONTRIBUTING.md`](../CONTRIBUTING.md). Tag, artifact, promotion, and recovery steps live in
[`release_artifacts.md`](release_artifacts.md). The acceptance sequence and evidence owners live
in [`release-test-plan.md`](release-test-plan.md). Use those contracts rather than maintaining a
second checklist here.

### Threat-driven release sequence

The threat IDs come from [`security-design.md`](security-design.md). Each step must preserve the
same candidate identity. Starting a new build, changing a ref, or replacing evidence restarts the
sequence.

| Order | Threats constrained | Required release behavior |
|---|---|---|
| 1. Freeze | TR-01, TR-10 | Select one protected commit. Record open threats and owners. A review comment or generated status cannot change their state. |
| 2. Build without authority | TR-01, TR-02, TR-09 | Bound source first. Validate dependencies without signing authority. Assemble twice in clean jobs that install no packages and hold no OIDC. Mismatch blocks. |
| 3. Bind evidence | TR-02, TR-03, TR-10 | After comparison, attest the commit and complete manifest; bind SBOM, scans, and architecture fingerprints. Evidence from another candidate is invalid. |
| 4. Verify external boundaries | TR-04 through TR-09 | Obtain current operator evidence for each applicable host or service control. Missing, stale, or ambiguous evidence remains blocking. |
| 5. Promote one artifact | TR-03, TR-04 | Transfer the reviewed artifact without rebuilding it. A no-checkout signer verifies its subject, source, ref, workflow, and hosted runner. The deploy job executes only a pinned action; a read-only job compares live bytes. |
| 6. Decide and publish | TR-10 | Confirm that the governing process still authorizes release, then require independent protected-environment approval. Private authorization evidence remains outside the repository; workflow provenance binds the published artifact to the reviewed commit. |

The protected environment reviewer confirms accountability and checks evidence. That action is a
separate signal, not a defense and not authority to skip an earlier step.
Every control certification or attestation must satisfy the evidence contract in
[`security-control-themes.json`](security-control-themes.json). A checklist, repository test, or
reviewer statement cannot certify an external host, service, launchable, relay, or runtime.

## Hotfix workflow

Use a hotfix only for an urgent defect in a supported tagged release. Security reports stay in the
private reporting route; public issues must not contain vulnerability detail.

1. Start from the affected protected tag and link the accepted issue or private incident record.
2. Limit the patch to the defect, its regression test, affected locale projections, and required
   release evidence.
3. Run the complete ship gate without change-aware skips, then require independent review and the
   protected release action.
4. Publish a new patch tag. Never move or replace the affected tag.
5. Add the fix to `CHANGELOG.md`, publish the deterministic artifacts, and verify the supported
   delivery paths before closing the issue.

If the fix changes architecture, dependencies, collected data, distribution, or security controls,
run the corresponding external review and scan steps again before publication.

## CI/CD policy

`scripts/validation/release_gate.py` owns the deterministic command sequence used by GitLab,
GitHub Pages, the protected release workflow, and local contributors:

```bash
python3 scripts/validation/release_gate.py --tier fast --no-write --changed-since origin/main --jobs 4
python3 scripts/validation/release_gate.py --tier ship --no-write --changed-since origin/main --jobs 4
```

Proposal gates always run complete current-tree audits. They skip only unaffected mutation suites.
Every add, delete, rename, copy, or unclaimed path selects the full mutation matrix; modified paths
may narrow only when a specialized detector explicitly owns them. CI records per-command timing and keeps exact history/metadata checks in host context. Local
pre-push may reuse an identical clean-commit success. CI never trusts that workstation cache.
Release-candidate and tagged-release workflows omit `--changed-since` and run every mutation.

The required GitLab test worker builds the Pages candidate after the gate passes. It reuses the
upstream report only after checking its schema, commit, ship scope, required findings, suite status,
and clean source tree. The manual Pages job copies that candidate rather than rebuilding it. This
keeps one worker startup and one proposal build without weakening artifact authorization.

Every shared gate verifies committed material snapshots and full SHA-256 provenance without network
access. Host workflows add bounded live-source retries: schedules and protected releases remain
strict, while production-ref pushes may tolerate only classified transient reachability. Drift,
malformed content, unsafe redirects, TLS failures, and committed-provenance mismatches always fail.
Jobs retry runner and control-plane failures, never validation script failures.

Host workflows also enforce submission shape, commit signoff ranges, protected tags, deployment
approval, and post-deploy smoke because those checks require host context. The full automated,
browser, service, and external-evidence matrix lives in
[`release-test-plan.md`](release-test-plan.md). Dependency resolution and SCA procedures live
in [`dependency_security.md`](dependency_security.md). Pages staging and deployment mechanics
live in [`pages_deploy.md`](pages_deploy.md). Host-native browser execution lives in
[`lab_runtime_testing.md`](lab_runtime_testing.md). Tracker labels and discussion routing
live in [`issue_standards.md`](issue_standards.md).

Protected approval identifies who is accountable; it is not a compensating control. When a release
still contains an unresolved concern, the release guard rejects a plain checkbox or author-supplied
approval claim. Risk acceptance must occur in its governing system before the public-safe release
state changes. The repository must not copy the private record. Protected-environment approval
confirms release authority, while manifests and provenance bind the exact source and artifact.

## Kickstart settings checklist

Before public mirror:

- [ ] Public README explains surface separation, local bring-up, and contribution routes.
- [ ] Repository description, website, topics, and signed-out README review match the approved public scope.
- [ ] `CONTRIBUTING.md` has issue-first and structured patch paths.
- [ ] This playbook is linked from docs SKILL and root SKILL.
- [ ] GitLab issue/MR templates exist.
- [ ] GitHub issue/PR templates exist.
- [ ] GitHub Feature and Bug issue forms exist and route sensitive reports privately.
- [ ] `CHANGELOG.md` records the pending release and is updated by the release-note owner.
- [x] Code of Conduct and a public-safe private platform reporting route are repository-defined; verify host moderation before intake.
- [ ] External repository protects `main` and `release/*`.
- [ ] Active `v*` tag rules restrict create, update, and deletion.
- [ ] Release workflow rejects lightweight tags and packages only annotated SemVer tags contained in `main`.
- [ ] Immutable releases are enabled before the first public version is published.
- [ ] External repository has required checks mapped to the static gate.
- [ ] Dependency graph, Dependabot alerts, dependency review, code scanning, and secret scanning are enabled or explicitly deferred with a reason.
- [x] Repo-owned Dependabot, dependency-review, and CodeQL workflows exist with immutable action pins; discovery-first validation rejects unsafe permissions or triggers in any added workflow.
- [ ] Host dependency graph, alerts, code-scanning upload, secret scanning, and push protection are enabled and smoke-tested.
- [ ] The exact pull-request head passes `audit_github_code_scanning.py`; the host-owned CodeQL check is green and the merge ref has zero open alerts.
- [ ] Release workflow is dispatched from the exact protected annotated tag; its draft contains the deterministic archive, manifest, resolved-environment SBOM, `SHA256SUMS`, and Sigstore bundle.
- [ ] External repository has Discussions enabled, with pinned welcome guidance.
- [ ] CODEOWNERS is added after org/team handles are real.
- [ ] Mirror is protected-branch/tag-only until public contribution intake is ready.
- [ ] `source_gate.py` and `local_path_leak_audit.py` pass on the mirrored ref; ancestry strategy is approved.
- [x] The repository contains a read-only, fail-closed external integration audit that never writes protected refs.
- [ ] The Monday 09:00 UTC GitLab schedule is enabled with a named reconciliation owner and notifications.
- [ ] Public Pages deploy uses environment protection and concurrency.
- [ ] `github-pages` and `github-release` require a reviewer, prevent self-review, and disallow admin bypass.
- [ ] The release guard retrieves the authorized private decision and compares its source and artifact bindings; until implemented, publication stays blocked.
- [ ] The no-checkout signer verifies the Pages inventory's Sigstore subject, source, ref, workflow, and hosted runner; the reviewer inspects it; the deploy job contains only the pinned deploy action.
- [ ] The read-only post-deployment job confirms every published object matches the reviewed manifest.
- [ ] A test release produced a Draft release, checksum, validation report, and Rule Insights record.

Before student PR intake:

- [ ] Fork PRs cannot access secrets.
- [ ] Dependency-review check blocks vulnerable dependency additions.
- [ ] Secret scanning push protection is enabled where available; custom patterns are approved before use.
- [ ] PR template asks for issue link, surfaces touched, validation, and source/licensing impact.
- [x] Public support policy states best-effort triage without an unsupported response SLA.
- [x] DCO 1.1 is documented and enforced over every proposed commit range.
- [ ] Labels and milestones are mirrored between GitLab and GitHub.
- [ ] Release note owner exists for each milestone.
- [ ] Security/private reports have a non-public contact path.

## Operator references

- [GitHub ruleset rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [GitHub ruleset management and Rule Insights](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository)
- [GitHub deployment environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
- [GitHub token least-privilege guidance](https://docs.github.com/en/actions/how-tos/security-for-github-actions/security-guides/use-github_token-in-workflows)
- [GitHub fork pull-request security behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
