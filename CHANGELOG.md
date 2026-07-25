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
- Thanks to Vadim Kudlay for reviewing the coordinated English, Spanish, and Portuguese
  course entrypoint refresh.
- Thanks to Juan Jose Durillo Barrionuevo for the expert Spanish course translation and developer-language review.
- Refined Spanish runtime labels and course parity while retaining Juan Jose Durillo Barrionuevo's reviewed prose baseline.
- Removed the em-dashes from the Spanish and Portuguese course pages by reorganizing each sentence
  rather than substituting punctuation, following Juan Jose Durillo Barrionuevo's reviewed Spanish
  prose baseline for voice and bullet structure.
- Thanks to Vadim Kudlay for clarifying the CLI comparison and its application defaults.
- Added an optional, history-free relay source projection with parameterized infrastructure,
  request and WebSocket tests, license inventory, and public-source identifier gates.
- Applied initial public-review feedback: centralized the explorer model default, moved trusted
  archive extraction into tested source, normalized internal template names, made CLI
  authentication checks explicit, and upgraded the shipped YAML parser to `js-yaml` 5.2.2.
- Made fork and token checks apply to every discovered GitHub Actions workflow, including newly
  added `.yml` and `.yaml` files.
- Made locale builds and runtime gates discover every same-branch language from validated metadata,
  fail on incomplete declarations, and retire the unused translation-branch compatibility reader.
- Corrected the landing image source to its NVIDIA Build blueprint card and simplified the
  launchable and REST explanations in English, Spanish, and Brazilian Portuguese.
- Thanks to Vadim Kudlay for reviewing the Module 3a English, Spanish, and Portuguese copy and
  figure-fit corrections.

At release time, move accepted entries under the immutable version tag and keep the remaining work
under `Unreleased`.
