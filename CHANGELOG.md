# Changelog

This file records changes by public release. Release artifacts, integrity files, and rollback rules
are defined in [`docs/release_artifacts.md`](docs/release_artifacts.md).

## Unreleased

- Initial public release candidate.
- No public version has been published.
- Retired the repository-owned container/service stack in favor of pinned host-native validation tooling.
- Replaced the duplicated checked-in standalone build with deterministic release-time generation and
  added a compact public entrypoint, agent workflow design note, and repository-prose checks.
- Separated validation, duplicate artifact assembly, attestation, and deployment authority in the
  public workflows; mismatched manifests block provenance, and privileged Pages jobs execute no
  repository-controlled source.
- Thanks to Vadim Kudlay for reviewing the Portuguese and Spanish course updates.
- Thanks to Juan Jose Durillo Barrionuevo for the expert Spanish course translation and developer-language review.
- Refined Spanish runtime labels and course parity while retaining Juan Jose Durillo Barrionuevo's reviewed prose baseline.
- Thanks to Vadim Kudlay for clarifying the CLI comparison and its application defaults.

At release time, move accepted entries under the immutable version tag and keep the remaining work
under `Unreleased`.
