# Changelog

This file records changes by public release. Release artifacts, integrity files, and rollback rules
are defined in [`docs/release_artifacts.md`](docs/release_artifacts.md).

## Unreleased

- Added lesson-grounded search metadata for the released NemoClaw course, canonical and locale URL
  projection, public-only sitemap generation, preview/source-mirror noindex handling, and a
  discovery-driven AI-content transparency contract covering authored text, figures, and
  runtime-generated media. Repository checks preserve the external human editorial-owner decision.
- Thanks to Vadim Kudlay for reviewing the final Module 3a connection guidance and its Spanish and
  Brazilian Portuguese course-readiness corrections for the aggregate internal integration.
- Thanks to Vadim Kudlay for the four-route Module 3a connection-audit interface feedback.
- Replaced Module 3a's transport controls with a Base URL and Access session check. Pomerium
  metadata uses the launchable's terminal loopback and its WebSockets stay direct; Cloudflare
  metadata uses the approved relay and its terminal can fall back to that relay. The check discovers
  the gateway token through `/api/agent`, verifies both WebSocket paths, then verifies `/healthz`.
- Thanks to Vadim Kudlay for reviewing the Spanish and Brazilian Portuguese browser-session
  availability guidance.
- Thanks to Vadim Kudlay for reviewing the corrected provider-specific connection guidance in
  Spanish and Brazilian Portuguese.
- Made an ephemeral launchable instance identifier uncommittable: the sensitive-content boundary now
  rejects a provisioned instance ID in either supported host family from the tree, the index, and
  proposed history, the remaining real identifier was replaced with synthetic fixtures, and every
  repository-owned publication path carries the same audit directly so a skipped hook cannot publish.
  A read-only trusted-base contribution check also scans proposed Git trees without checking out or
  executing pull-request code. The artifact boundary now resolves a projected `source/` route back
  to the repository file it copies only when their full bytes exactly match, the projection refuses
  to let two sources claim one route, and the pull-request job audits its own built artifact so an
  artifact-only route cannot fail for the first time inside the production deploy.
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
- Moved every translated page to key-based locale resources: typed per-locale JSON values addressed
  by keys derived from the English source, a renderer that builds self-contained static pages before
  publication, and a discovery-first gate that validates the rendered page rather than the JSON
  alone. All fifteen Spanish and fifteen Brazilian Portuguese pages now publish from a resource and
  their duplicated localized HTML is deleted; `overlay_files` is empty in both locales. Twenty-six
  of the thirty pages publish byte-identical output. The Spanish `03a-kickstart` and `03c-always-on`
  pages regain the `<!DOCTYPE html>` their hand-canonicalized overlays had dropped, which takes them
  out of browser quirks mode without changing any translated wording; Portuguese `03a-kickstart`
  adopts two shared-template blank-line placements. Spanish `04b-modern-clis` restores three
  translated `<comando>` tokens to the executable `agent <command>` placeholder. Runnable resources
  now store only comment and string copy: delimiters, regex literals, calls, identifiers, operators,
  and control flow remain authored once in the template. A read-only localization run also holds
  each locale's tracked drift manifest to the manifest its current inputs derive, so
  a generated projection left behind by a schema or input change fails in the fast gate instead of
  at the end of a build. Thanks to Lisa Guo for proposing the approach.
- Widened learner-facing text extraction so reviewed copy can no longer sit outside the translatable
  surface: `*Hint` fields, `fieldHelp` panel bodies, and `.textContent` assignments are covered, two
  name allowlists are gone, and a span scanner keeps runnable `code:` bodies out of translation.
  Spanish question and exclamation balance now ignores a named on-screen `?` glyph and the `?` that
  opens a URL query inside a `code` span, while an unbalanced Spanish question still fails.
- Two English UI fragments on the Spanish `04a-safety` page that the former extractor missed are
  now explicit `untranslated` entries, preserving the reviewed wording while exposing the remaining
  language-review work instead of silently treating it as translated.
- Replaced the fabricated Module 3a gateway-token recovery with the supported
  `openclaw dashboard --no-open` and `openclaw doctor --generate-gateway-token` path, separated the
  gateway token from the launchable access session, retired the presenter relay overrides in favor
  of provider-selected transport, and corrected the Brev launchable link to its `deploy/now` form.
- Thanks to Claude Opus 5 for independently reviewing the Spanish and Brazilian Portuguese Module
  3a launchable and gateway-credential updates.

At release time, move accepted entries under the immutable version tag and keep the remaining work
under `Unreleased`.
