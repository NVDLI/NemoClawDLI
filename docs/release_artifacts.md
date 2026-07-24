# Release artifacts and tags

This contract separates preview deployment from versioned publication. The repository is approved
for public release; `RELEASE_STATUS.json` records only that public-safe state.
The operator sequence and host settings live in
[`release_playbook.md`](release_playbook.md); verification lives in
[`release-test-plan.md`](release-test-plan.md), and Pages preview mechanics live in
[`pages_deploy.md`](pages_deploy.md).

## Ref and artifact lanes

| Lane | Ref | Artifact | Retention | Authority |
|---|---|---|---|---|
| Branch preview | topic branch commit | Combined classic-Pages preview | 3 days | Manual review environment |
| Internal production | protected `main` or approved production ref | Current Pages deployment | Replaced by next approved deploy | Protected production environment |
| Public release | protected annotated `vMAJOR.MINOR.PATCH` tag | Versioned archive, manifest, SBOMs, checksums | Published release lifetime | Protected tag plus release environment |

A Pages deployment proves a commit is previewable. It does not create a version. A public release
always starts from a protected tag and never from a branch name or an unreviewed workflow input.

## Tag contract

- Use SemVer tags such as `v1.2.3` or an explicit prerelease such as `v1.3.0-rc.1`.
- Create an annotated tag on a commit contained in protected `main`. Lightweight tags are refused.
- Protect `v*` creation, update, and deletion. Name eligible release operators directly.
- In one-operator mode, keep the protected-tag creator set equal to the sole production deployer.
  Change tag, deployment, and approval authority together when another operator becomes active.
- Never move, delete, or reuse a published version tag. Fix release defects under a new version.
- Prefer signed annotated tags after the external repository has a documented signing identity and
  trust-root rotation process. Do not claim signature verification before that trust path exists.

Example after approval and final validation:

```bash
git tag -a v1.0.0 -m "NemoClaw DLI course v1.0.0" <reviewed-main-sha>
git push origin v1.0.0
```

The release workflow verifies the tag name, annotated tag object, target commit, and containment
in `origin/main`. Host rules remain responsible for tag creation authority.

## Published asset set

Each public draft receives:

- `nemoclaw-vX.Y.Z.tar.gz`: deterministic built Pages tree under a versioned top-level directory
- `release-manifest.json`: schema, tag object, commit, source epoch, archive digest, file count,
  attached-asset digests, and the archives requiring external malware evidence
- `nemoclaw-vX.Y.Z.python-env.cdx.json`: CycloneDX SBOM for the resolved release environment
- `nemoclaw-vX.Y.Z.browser.cdx.json`: CycloneDX SBOM for JavaScript packages shipped to learners
- `nemoclaw-vX.Y.Z.python-sbom-evidence.json`: source commit, SBOM hash, component count,
  license summary, workflow URL, and retention for the resolved Python environment
- `nemoclaw-vX.Y.Z.python-license-appendix.md`: component licenses reconciled from the same
  Python SBOM without guessing unresolved metadata
- `nemoclaw-vX.Y.Z.sbom-evidence-catalog.json`: distribution-aware index for committed,
  CI-generated, and conditional component evidence
- `SHA256SUMS`: digest list for every published asset

Validation reports, the Sigstore bundle and verification log, and the full `pip-audit` result remain
workflow evidence. They are retained with the transfer artifact for 30 days but are not public release assets. This keeps operator evidence
available without publishing noisy scanner detail as a supported product interface.

The source-backed security architecture and generated SVG remain versioned under `docs/` so a reviewer
can trace system boundaries to the exact source tag. They are engineering evidence rather than
supported runtime interfaces and do not encode internal submissions or approval records.

The tagged source also versions `docs/product-design.md`, `docs/release-test-plan.md`, and
`docs/release-evidence.json`. Reviewers link those files at the exact release commit, then retain
private scanner, reviewer, and approval records in the authorized release system.

The workflow installs scanner tools in a separate environment, so scanner dependencies do not
pollute the runtime SBOM. Scanner versions are pinned in the workflow so the same environment is
serialized consistently until an explicit dependency update changes the tooling.

The static release does not include local-authoring images. If a later release adds one, the draft
must also carry that image's immutable registry digest, component SBOM, evidence manifest, and
license appendix.

## External artifact evidence

Packaging writes `external_evidence.policy` as `required-before-publication` and lists the course
archive, plus any additional executable or archive asset, under `malware_scan_required`. This field
is a release rule, not a scan result or current status. The authoritative system owns the disposition
and reviewer record; the public manifest identifies the exact filenames and the checksums bind them
to the tag.

After the protected workflow prepares a draft, the release owner submits every listed artifact to
the qualified scanner and records zero malicious and zero suspicious detections, or an authorized
false-positive disposition. Text-only manifests, SBOMs, and checksum files receive an explicit
applicability decision rather than being silently omitted. The public workflow does not hold private
scanner credentials or claim that repository validation satisfies this external control.

## Reproducibility rules

`scripts/build/package_release.py` normalizes file order, owner, group, mode, archive time, gzip
time, and top-level path. The commit time supplies `SOURCE_DATE_EPOCH` to generated branch metadata
and `source_date_epoch` to the packager. The release build disables live material refresh, so public
URLs changing during a run cannot alter the archive.

Run the deterministic self-test locally and in CI:

```bash
python3 scripts/build/package_release.py --self-test
```

The generated manifest binds the archive to both the tag object and peeled commit. `SHA256SUMS`
supports offline verification. Before the reserved external GitHub repository publishes its first
release, enable immutable releases. GitHub then locks the published tag and assets and emits a
release attestation.

## Promotion and recovery

1. Validate a topic commit and publish an ephemeral preview.
2. Merge through protected `main` after required CI and human acceptance.
3. Update `RELEASE_STATUS.json` only after OSRB approval.
4. Create the protected annotated version tag on the accepted `main` commit.
5. Dispatch from that tag. Validation emits evidence without signing authority; two clean jobs
   assemble and compare the static tree; a later job attests it and prepares a protected draft.
6. Review release notes, workflow evidence, manifest, SBOM, and checksums.
7. Publish once immutable-release settings are confirmed.

Draft assets may be replaced after a failed review. Published assets and tags are immutable. A bad
published artifact is superseded by a new patch version and a clear release note.

## GitHub release runbook

The checked-in `.github/workflows/release.yml` prepares a release but cannot authorize one.

1. Merge the candidate through protected `main` after required checks pass on the reviewed SHA.
2. A release manager creates a protected annotated SemVer tag on a commit contained in `main`.
3. Select that tag as workflow ref and input. Validation and scanning run without signing authority.
4. Two clean jobs install no packages while independently assembling the tree. A mismatch blocks.
5. A separate job attests and verifies every checksummed subject. It cannot publish a release.
6. The protected `github-release` job reverifies provenance before gaining write authority.
7. The workflow creates or refreshes a draft release; it never publishes directly.
8. Read `release-manifest.json.external_evidence`, submit every listed artifact, and retain the
   authoritative disposition against the exact checksums.
9. A release manager reviews the draft, verifies attached assets and external evidence, and publishes it.
10. Review deployment history and ruleset insight. Record any authorized bypass with owner and reason.

Enable immutable releases before the first publication. If validation fails, fix through a new
issue-linked change and create a new tag after merge. Never move or reuse a published tag.

Primary references: [Git annotated tags](https://git-scm.com/docs/git-tag),
[GitHub immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases),
and [GitHub artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).
