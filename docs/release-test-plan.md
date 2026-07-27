# Release test plan

This plan verifies the product defined in [`product-design.md`](product-design.md). It applies to a
reviewed release candidate commit and its eventual protected tag. The machine-readable coverage map is
[`release-evidence.json`](release-evidence.json).
Detailed dependency procedures live in [`dependency_security.md`](dependency_security.md).
Security requirement dispositions live in
[`security-control-disposition.md`](security-control-disposition.md); the aggregate control,
mitigation, trigger, and verification register is
[`security-control-themes.json`](security-control-themes.json).
Artifact promotion lives in [`release_artifacts.md`](release_artifacts.md), and Pages assembly
lives in [`pages_deploy.md`](pages_deploy.md).
The [course prose writing contract](course-prose-style.md) defines durable learner-facing writing
and review rules. Page-specific dispositions remain in the reviewing Issue or merge request.

The plan separates repository checks from operator and external-review evidence. A passing pipeline
does not approve legal terms, privacy, export classification, malware disposition, host configuration,
or publication.

## Scope

Test these release surfaces:

- canonical and localized course source;
- generated static Pages output;
- browser interaction behavior affected by the release;
- source, dependency, SBOM, and provenance records;
- security architecture, contribution, deployment, and release controls; and
- deterministic tagged release assets.

Host authoring and validation tools are tested through their pinned locks and deterministic commands.

## Roles and evidence ownership

| Role | Responsibility |
|---|---|
| Contributor | Runs focused tests, updates affected contracts, and records failures honestly |
| CI | Repeats deterministic tests on the submitted commit and retains reports |
| Release owner | Selects the final commit/tag, reviews all evidence, runs manual host checks, and stops on missing evidence |
| External reviewer | Decides legal, license, privacy, export, malware, risk, or release approval within their authority |

Internal identifiers, reviewer records, and private scan details belong in the authorized lifecycle
record. Public repository evidence contains only the design, commands, result shape, and ownership
boundary.

## Entry criteria

- Work is on an issue-linked branch based on current protected `main`.
- The candidate diff is understood and its blast radius is declared.
- Required source and license provenance exists.
- Direct requirements and transitive locks agree.
- No known external approval is represented as complete by repository text.
- The candidate publication state matches `RELEASE_STATUS.json`.
- The OSS registration scope names the DLI course repository and excludes the separately owned
  NemoClaw product, launchable, runtime, and service deployments.

## Test environments

| Environment | Purpose |
|---|---|
| Source checkout | Fast structure, contract, source, and policy validation |
| Node-enabled validation runtime | Link projection and full static bundle checks |
| Python 3.12 virtual environment (3.11 minimum) | Exact dependency, vulnerability, and CycloneDX inventory checks for validation tooling |
| Built Pages tree | Generated English, Portuguese, and Spanish route and asset verification |
| Host-installed Chromium with pinned `playwright-core` | Rendered layout and interaction-state checks when browser behavior changes |
| Protected release workflow | Tag containment, deterministic packaging, evidence retention, and draft creation |
| External review systems | Registration, legal, license, export, privacy, secrets, vulnerability, malware, and final release decisions |

## Automated test matrix

Run the shared deterministic sequence from the repository root:

```bash
python3 scripts/validation/release_gate.py --tier ship
```

The matrix below explains its constituent claims and adds conditional browser, service,
host, and external-review work. Any applicable nonzero exit blocks the candidate.

| ID | Claim | Command | Pass condition | Evidence |
|---|---|---|---|---|
| A01 | Design and test evidence remain complete and public-safe | `python3 scripts/validation/release_evidence_audit.py --self-test` then `python3 scripts/validation/release_evidence_audit.py` | Every mutation is detected; repository audit has zero findings | CI log and validation report |
| A01a | Public repository work products match their reviewed requirement and applicability levels | `python3 scripts/validation/repository_work_products_audit.py --self-test`; `python3 scripts/validation/repository_work_products_audit.py` | Mutation suite passes; required files, evidence paths, policy content, learner routes, public boundaries, intake templates, and gate wiring have zero findings | CI log, applicability matrix, and validation report |
| A02 | Product topology and endpoint controls match implementation | `python3 scripts/figures/render_security_architecture.py --check`; `python3 scripts/validation/security_architecture_audit.py --self-test`; `python3 scripts/validation/security_architecture_audit.py`; `python3 scripts/security/audit_iframe_proxy_opt_in.py --self-test`; `python3 scripts/security/audit_iframe_proxy_opt_in.py`; `python3 scripts/security/audit_cors_proxy_projection.py`; `python3 scripts/validation/public_infrastructure_audit.py`; `node --test scripts/cors-proxy/deployable/test/*.test.mjs`; `node scripts/cors-proxy/deployable/scripts/render-infrastructure.mjs`; `python3 scripts/validation/with_locale_pages.py -- bash scripts/runtime/run_node.sh scripts/validation/gateway_token_audit.mjs --self-test` | Generated graph is current; topology, endpoint-selection, credential-destination, relay, projection-integrity, environment-identifier, provider-binding, redirect, streaming, WebSocket, and complete gateway-token mutations are rejected | CI log and source-backed graph |
| A02a | Threat controls remain correctly assigned to repository, host, service, residual, or non-applicable ownership | `python3 scripts/validation/threat_control_audit.py --self-test`; `python3 scripts/validation/threat_control_audit.py`; `python3 scripts/validation/repository_sync_audit.py --self-test` | Mutation suites pass; repository controls are wired; unexecuted provenance, trusted-builder, and hosting gaps remain visible; provider controls are not claimed by client code; the dual-repository audit cannot write protected refs | CI log, disposition record, and authorized external evidence |
| A03 | Contribution, build, signing, and release authority remain separated | `python3 scripts/validation/contribution_safety_audit.py --self-test`; `python3 scripts/validation/contribution_safety_audit.py`; `python3 scripts/validation/gitlab_ci_policy.py --self-test`; `python3 scripts/validation/gitlab_ci_policy.py`; `python3 -m unittest -v tests.validation.test_privileged_course_ops` | A runnerless child-pipeline bridge drops arbitrary process variables; token-bearing acquisition and secret-free candidate execution are separate; the CDN preparer has no AWS authority; the root-installed publisher accepts only a complete hash plan, root-owned AWS identity, paginated exact tree, and completed cache invalidation; public GitHub receives no internal authority | CI report |
| A04 | Required public files, licenses, sources, material provenance, and contributor-local hygiene are intact | `python3 -m unittest discover -v -s tests/validation`; `python3 scripts/compliance/source_gate.py`; `python3 scripts/compliance/source_license_contract.py --verify-browser-upstream` after `npm ci --prefix scripts/browser-vendor --ignore-scripts`; `python3 scripts/validation/local_path_leak_audit.py`; `python3 scripts/validation/local_path_leak_audit.py --commit-range origin/main..HEAD`; `python3 scripts/materials/pull_materials.py --verify-committed` | The NVIDIA copyright precedes Apache-2.0; DCO 1.1 is complete; top-level third-party notices resolve; every authored Python and JavaScript file has the exact header; the unminified LangChain interoperability bundle is the sole transformed browser asset; every other browser asset is byte-identical to its pinned publisher input; CI regeneration leaves no diff; inventory resolves; framework path/retry/tamper tests pass; no forbidden private links or contributor workstation paths exist in the tree or any proposed commit; every committed material matches its manifest metadata, character count, and full SHA-256 without network access | CI log |
| A04a | Sensitive contribution content stays in approved private systems | `python3 -m unittest discover -v -s tests/validation`; `python3 scripts/validation/sensitive_content_audit.py`; `python3 scripts/validation/sensitive_content_audit.py --commit-range origin/main..HEAD`; `python3 scripts/validation/sensitive_content_audit.py --root <built artifact> --publication-source-root <source tree>` | Framework mutation tests pass; tree, complete proposed history, and the built publication artifact contain no restricted finding details, private service locations, ephemeral infrastructure identifiers, personal corporate addresses, or concrete credentials; a projected `source/` route inherits a source-file allowance only when its full bytes exactly match that repository file, so the artifact boundary agrees with the source boundary before the deploy | CI log |
| A04b | Security-relevant diffs notify the release operator | `python3 -m unittest discover -v -s tests/validation`; `python3 scripts/validation/release_change_reminder.py --commit-range origin/main..HEAD` | Framework mutation tests pass; applicable external assessment, scan, open-source/license, and final-artifact actions are listed without claiming completion | CI log and authorized release record |
| A04c | The static third-party list matches exact package locks, material provenance, and scanned component evidence | `python3 -m unittest discover -v -s tests/validation`; `python3 scripts/compliance/third_party_inventory_audit.py`; `python3 scripts/compliance/sbom_evidence.py --check` | Framework mutation tests pass; every shipped browser package and Python tool package is listed with a license identifier; external-source material rows remain visible; linked SBOM hashes and component counts match | `THIRD_PARTY_LICENSES.md`, filtered reviewer exports, SBOM catalog and runbook, attached scan set and CI log |
| A05 | Dependency manifests and locks agree | `python3 scripts/security/audit_dependency_locks.py --self-test`; `python3 scripts/security/audit_dependency_locks.py` | Mutation suite passes; every direct and transitive version is exact and carries a SHA-256 artifact hash | CI log |
| A06 | Direct dependencies and accepted exceptions meet repository policy | `python3 scripts/security/audit_python_dependencies.py`; `python3 scripts/security/audit_vulnerability_waivers.py` | No unhandled vulnerable floor/pin; every exception is fingerprinted, owned, controlled, scoped, and unexpired | CI log |
| A06a | CodeQL results and GitHub's host security state match reviewed source and browser boundaries | `python3 -m unittest -v tests.validation.test_codeql_sarif_audit tests.validation.test_github_code_scanning_audit`; `python3 scripts/security/audit_codeql_sarif.py --sarif <post-processed-results>`; after the upload finishes, run `python3 scripts/security/audit_github_code_scanning.py --repository <owner/repo> --pull-request <number> --head-sha <full-head-sha>` with a read-capable `GITHUB_TOKEN` | New authored or vendor findings fail; reviewed results match a stable CodeQL line fingerprint, exact artifact SHA-256, executable controls, owner, scope, and expiry; upload-only SARIF metadata cannot change the decision; the exact head's host-owned Advanced Security check is successful and the pull-request merge ref has zero open alerts | Uploaded SARIF, complete exact-head check runs, pull-request merge-ref alert state, CI log, and public disposition registry |
| A07 | Python material tools are scanned and inventoried | Run the isolated A07 procedure below, or the required `security_python_sca` CI job | pip-audit succeeds; the SBOM covers the pinned material-tool closure; runtime components remain absent; the same SBOM produces a commit-bound evidence manifest and reconciled license appendix | Retained scanner, SBOM, evidence-manifest, and license-appendix artifacts |
| A08 | Course structure, prose contracts, browser dependencies, localization, links, and directory contracts ship cleanly | `python3 -m unittest discover -v -s tests/validation`; `python3 scripts/validation/artifact_link_audit.py <standalone-root>`; `python3 scripts/validation/color_theme.py`; `python3 scripts/validation/course_dependency_integrity.py`; `python3 scripts/validation/cell_audit.py`; `python3 scripts/validation/validate_layout.py --quiet`; `python3 scripts/skills/skill_consistency.py`; `python3 scripts/skills/gen_directory_beacons.py --check`; `python3 scripts/skills/normalize_skill_headers.py --self-test`; `python3 scripts/skills/normalize_skill_headers.py --check`; `python3 scripts/skills/test_skill_contract.py`; `python3 scripts/skills/skill_contract.py`; run `skill_renderer_runtime_audit.py` in the standard browser runtime; `python3 scripts/validation/validate_bundle.py --scope ship --no-write` | Framework dependency, color-theme, editor-asset, missing-link, fragment, root-absolute, and root-escape mutations are rejected; every source directory has a valid beacon with no exemptions and one semantic navigation header; every generated HTML file and every local URL are discovered without an allowlist; all targets remain inside the exact standalone root and return successfully in the browser; narrow pages do not overflow; parameterized exports support multi-selection and two-way column sorting; the SBOM view verifies and renders linked component licenses; every package, license, asset hash, source reference, and browser CycloneDX component resolves; required and recommended findings are zero | Validation report, artifact-link report, all-HTML renderer log, public dependency inventory, and browser SBOM |
| A09 | Locale overlays and typed locale resources cannot ship stale, unsafe, structurally divergent, or through hidden fallback authority | `python3 scripts/build/assemble_locale_overlay.py --self-test`; `python3 scripts/validation/localization_audit.py --self-test`; `python3 scripts/validation/locale_resource_audit.py --self-test`; run both current-tree audits for every discovered locale/resource; `python3 scripts/validation/validate_bundle.py --scope ship --no-write` for the read-only projection check; build the exact Pages tree so the existing artifact and browser suites consume every assembled locale page | Overlay/resource mutation suites pass; every locale and resource audit passes; each locale's tracked drift manifest still matches the manifest its current inputs derive; assembled locale pages pass the existing link, accessibility, theme, narrow-layout, browser, and artifact gates | CI log, localization manifest, resource diagnostics, exact Pages artifact, and browser evidence |
| A10 | Release packaging is deterministic | `python3 scripts/build/package_release.py --self-test`; inspect the release comparison job | Fixture builds match; two clean jobs assemble identical complete static-tree manifests before attestation | CI log and both manifests |
| A11 | Proposed source and generated Pages output stay bounded and match the reviewed commit | Run `pages_artifact_integrity.py --source-root .`; then exercise source projection, two clean builds, manifest comparison, attestation, extraction, and deployed-byte checks | Bounds and browser fixtures pass; dot-prefixed host configuration is projected to public-safe routes without hiding files or links; builders install no packages or hold OIDC; manifests match; no-checkout signing and source-free deployment follow; live bytes agree. A protected live run is required before Verified. | Source preflight, both manifests, Pages artifact, Sigstore bundle/log, browser result, and post-deploy job |
| A12 | Browser state transitions remain usable | Run the applicable host-native browser audits named in `docs/lab_runtime_testing.md` against source and built output | Entry, success, error, reset/remount, reload, keyboard, and narrow-layout cases pass | Browser logs and screenshots |

For A07, scan the pinned material-tool requirements without installing the removed application runtime:

```bash
python3 -m venv /tmp/nemoclaw-release-scanner
/tmp/nemoclaw-release-scanner/bin/python -m pip install --require-hashes --no-deps --only-binary=:all: -r scripts/security/requirements-sca.lock
/tmp/nemoclaw-release-scanner/bin/pip-audit -r scripts/materials/requirements.lock --strict --no-deps --disable-pip \
  --format cyclonedx-json --output /tmp/nemoclaw-release-sca/python-env.raw.cdx.json
/tmp/nemoclaw-release-scanner/bin/python scripts/compliance/resolve_sbom_licenses.py \
  --input /tmp/nemoclaw-release-sca/python-env.raw.cdx.json \
  --output /tmp/nemoclaw-release-sca/python-env.cdx.json
/tmp/nemoclaw-release-scanner/bin/python scripts/security/audit_sbom_policy.py \
  --sbom /tmp/nemoclaw-release-sca/python-env.cdx.json \
  --report /tmp/nemoclaw-release-sca/sbom-policy.json
python3 scripts/compliance/sbom_evidence.py \
  --sbom /tmp/nemoclaw-release-sca/python-env.cdx.json \
  --artifact-name "python-material-tools-$(git rev-parse HEAD)" \
  --record-id python-material-tooling \
  --distribution not-distributed \
  --category validation \
  --source-commit "$(git rev-parse HEAD)" \
  --ci-job manual-review \
  --appendix-out /tmp/nemoclaw-release-sca/python-license-appendix.md \
  --manifest-out /tmp/nemoclaw-release-sca/sbom-evidence.json
```

Final release evidence comes from the protected workflow's exact environment and retained artifact
paths.

Live source checks are separate from the deterministic matrix. Scheduled monitoring and protected
release preparation run a strict retried `pull_materials.py --check`. A production-ref push may
continue only when every live failure is classified as transient reachability; source drift,
malformed content, unsafe redirects, TLS failures, and committed-provenance mismatches still block.

## Manual and external evidence matrix

Store links, identifiers, named reviewers, and detailed reports outside the public repository.
Each retained certification or attestation must record the issuer role, exact subject and scope,
release binding, control claims, evidence fingerprints, observation and expiry times, result, and
limitations required by `security-control-themes.json`. Missing or mismatched context is Unknown,
not a pass.

| ID | Evidence | Procedure | Pass condition | Owner |
|---|---|---|---|---|
| M01 | Course program and release registration | Compare the NemoClaw DLI course purpose, intended OSS Type I class, attributes, contacts, version, course source, excluded product scope, and release status with the reviewed design | Required fields accurately identify the Full-OSS DLI course repository without claiming the NemoClaw product, launchable, or runtime | Release owner |
| M02 | Public course repository baseline | Confirm the course repository is in the approved organization and review README, LICENSE, verbatim SECURITY policy, contribution and coding guidance, conduct, changelog, maintainer plan, Feature and Bug issue forms, and pull-request template | Host location and required work products are accepted, and public GitHub is configured as the canonical course planning, issue, contribution, CI, and release home | Repository owner and approver |
| M03 | Product legal/open-source terms | Submit the final release request and answer follow-up questions | Authorized legal/open-source reviewer records approval | External reviewer |
| M04 | OSS license disposition | Review `THIRD_PARTY_LICENSES.md`, register the final source and released artifacts, correct inventory data, and review every actionable component | The static package/version/SPDX inventory matches the exact locks; zero released components lack required license disposition | Release owner and external reviewer |
| M05 | Export classification | Supply the cryptography inventory, distribution method, and principal use from the design; answer follow-up questions | Authorized export reviewer closes the review and the registration reflects it | External reviewer |
| M06 | Privacy applicability and review | Compare deployment data flows, browser storage, external recipients, logs, and retention ownership with the selected hosting configuration | Privacy marks the assessment complete, or the authorized process records that no assessment is required | Privacy reviewer |
| M07 | Authoritative secret scan | Scan the final registered source ref and review every finding | Zero verified secrets; any exposed credential was rotated before removal | Release owner |
| M08 | Authoritative vulnerability scan | Scan every final released artifact; review severity, age, fix availability, and artifact-specific dispositions | No overdue fixable Critical/High finding lacks an approved disposition, mitigation, and remediation plan | Release owner and risk authority |
| M09 | Malware scan | Read `release-manifest.json.external_evidence`; submit every file in `malware_scan_required` to the qualified scanner, and record applicability for the remaining text-only assets | Every listed artifact has zero malicious and zero suspicious detections, or an authorized false-positive disposition; the external record closes the manifest's `required-before-publication` policy | Release owner and malware reviewer |
| M10 | Live host controls | Verify HTTPS, protected default branch and tags, required checks, immutable release settings, private vulnerability intake, a `github-pages` environment with required reviewers and self-review prevention, the weekly public-to-internal integration schedule, and the recorded CSP/CDN/WAF decision | A host-issued, scoped, fingerprinted, current evidence record matches the design, disposition record, and release playbook | Host administrator and release owner |
| M10a | Generated threat-analysis reconciliation | Verify the embedded diagram fingerprint and flow/objective register against the submitted pair; reconcile TR-01 through TR-10 with private requirements and the prior assessment; use only the applicable edges and security objectives in `security-architecture.json`; reject stale attachments, inferred external internals, human-review actors modeled as components, impossible enforcement owners, nonexistent routes, and duplicates; assign each remaining requirement one canonical disposition; map repeats to `security-control-themes.json`. | Missing or mismatched attachment identity remains Unknown; metadata-only rerenders cause no public-document churn; the Target of Evaluation matches the canonical invariants; runtime and release-flow threats map to declared edges and objectives; TR-10 remains an evidence-workflow threat rather than an invented component or edge; exact and semantic duplicates receive one disposition; requirements match a real enforcement owner; every requirement is a verified repository control, open repository action, external evidence requirement, architecture decision, or reasoned Not Applicable; generated external mitigations remain open without operator evidence; the public repository contains no private row-by-row assessment | Product Security reviewer and release owner |
| M11 | Final release decision verification | Review the exact protected tag, pipeline, generated-tree browser results, downloadable Pages artifact, SHA-256 inventory, Sigstore bundle and verification log, Pages smoke, archive manifest, SBOM, checksums, known issues, external evidence, and rollback plan. Confirm the public-safe approval state against the governing system without copying private evidence into the repository. | The attestation verifier accepts only the expected subject, source digest/ref, signer workflow, and hosted runner before write authority. The protected environment requires an independent reviewer, and generated provenance binds the published artifact to the reviewed commit. | Release reviewer and release-guard owner |

## Execution order

1. Run focused tests while editing.
2. Run `release_gate.py --tier ship --no-write --changed-since origin/main --jobs 4` once before pushing. A01 through
   A10 map claims inside that gate; they are not a second command checklist.
3. Build the complete multilingual Pages candidate on the gate worker and run A11. Reuse its report
   only when the fail-closed audit proves the same commit, ship scope, clean source tree, and required
   pass. Publication copies this candidate. It does not rebuild the proposal.
4. Run A12 when the diff touches browser behavior.
5. Push the issue-linked branch and require CI on the submitted commit.
6. Preview the tested commit and complete M01 through M06 far enough to expose review gaps.
7. Freeze the release candidate under a protected annotated tag only after repository review.
8. Run the protected release workflow and retain its archive, manifest, SBOM, checksums, and reports.
9. Complete M07 through M10 against the final source ref and packaged artifacts.
10. Complete M10a and M11. Publication remains blocked until the governing authorization is
    confirmed, the exact artifact binding passes, and the protected environment permits deployment.

Release candidates omit `--changed-since` so every detector mutation runs. Proposal selection also
runs every mutation after an add, delete, rename, copy, or change with no specialized owner. Standard
Python test discovery makes new validator modules executable without registry bookkeeping. CI retains per-command
timing evidence; recurring high-latency checks should be optimized at their canonical owner, not
copied into a second abbreviated gate.

## Pass, failure, and exception rules

- Every applicable automated test must pass on the exact candidate commit.
- A skipped browser test requires a written applicability reason tied to the diff.
- A test crash, zero-input run, stale report, missing artifact, or mismatched SHA is a failure.
- Repository tests cannot convert missing external evidence into a pass.
- Human review is not a compensating control. Referral or attendance has no release effect. Neither
  does a checkbox or approval comment. An unresolved state remains unresolved.
- An authorized exception remains in the governing system. It records acceptance; it does not claim
  the missing control was implemented. The public repository records only the resulting release
  state and must not contain the private decision or its evidence.
- Protected-environment approval confirms release authority. Workflow manifests and provenance bind
  the exact source commit and artifact digest. A mismatch blocks publication.
- Requirements marked non-waivable by the governing process must be complete or explicitly Not
  Applicable through that process. The repository cannot grant a waiver.
- A failed external review blocks publication even when repository tests pass.

## Exit criteria

- Required CI is green for the final commit.
- Required browser tests passed or have an accepted applicability record.
- The Pages preview and smoke result match the final commit.
- The deployed HTTPS tree matches the reviewed Pages manifest byte-for-byte.
- The external integration audit has run on its declared cadence and any external-ahead or diverged state has a reviewed reconciliation record.
- The protected tag points to that commit and is contained in protected `main`.
- Archive, manifest, SBOM, checksums, and retained validation evidence agree on version and commit.
- M01 through M11, including M10a, are complete or formally Not Applicable through the authorized
  process.
- Known issues, mitigations, rollback, and support scope were reviewed.
- M11 confirmed the public-safe approval state against the governing system without copying private
  evidence into the repository. The protected environment and provenance match the exact source and
  artifact.

## Evidence record

Record this information in the authorized release system:

| Field | Value to record |
|---|---|
| Source | Canonical repository and final commit |
| Version | Protected annotated tag and tag object ID |
| Design | Link to `docs/product-design.md` at the final commit |
| Test plan | Link to this file at the final commit |
| Pipeline | Required CI URL and commit SHA |
| Preview | Pages URL and smoke job |
| Release assets | Archive, manifest, SBOM, checksums, and their digests |
| Automated results | Validation report, dependency scan, waiver audit, and browser evidence |
| External results | Registration, legal/license, export, privacy, secret, vulnerability, malware, and host-control evidence |
| Decision | Reviewer identity, date, outcome, remaining conditions, and rollback owner |

Re-run the complete plan when the release scope, hosting path, data handling, authentication,
external service, dependency environment, packaging format, or release authority changes materially.
