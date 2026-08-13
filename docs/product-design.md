# Product design

This document defines the released course system. It describes the product boundary, supported
delivery paths, data handling, dependencies, and release behavior. The companion
[`release-test-plan.md`](release-test-plan.md) explains how each claim is verified.

The publication state remains machine-readable in [`RELEASE_STATUS.json`](../RELEASE_STATUS.json).
This design does not grant publication authority or record private review evidence.
Detailed trust boundaries and graph instructions live in [`security-design.md`](security-design.md); versioned
artifact behavior lives in [`release_artifacts.md`](release_artifacts.md).

The selected operating model for the NemoClaw DLI course repository is an NVIDIA-owned
Full-OSS-Project intended as OSS Type I. Once the approved cutover populates the reserved
repository, public GitHub is canonical for course source, planning, issues, contributions, CI, and
releases. Internal GitLab receives reviewed public course changes on the defined integration
cadence and adds internal validation or deployment without becoming a private development source.

The Type I subject is only the DLI course repository and its static course artifacts. The NemoClaw
product, launchable, runtime, relays, and operational configuration are outside this classification
and release scope. Those systems remain external integration dependencies with separate owners and
lifecycle records. The authoritative lifecycle record must still confirm the course repository
classification and publication decision.

## Purpose and users

The product teaches learners how agent loops, tools, retrieval, persistent runtimes, and sandbox
controls fit together. Learners use a browser. Instructors and reviewers use the same pages plus the
static validation report. Contributors edit the source tree. Release operators promote a reviewed
commit into a versioned static artifact.

The design favors a low-assumption interface. Course explanation, runnable examples, source
inspection, and validation results remain available through ordinary web pages without a learner-side
build toolchain.

## Release scope

The supported release contains:

- the source repository under the Apache License 2.0.
- one browser course assembled from `web/nemoclaw/` and sparse locale overlays under `i18n/`.
- a static Pages tree containing HTML, JavaScript, CSS, images, and course data.
- a deterministic tagged archive with a release manifest and checksums.
- material-tool Python and learner-delivered browser-package SBOMs.
- optional, history-free relay source whose deployment values and authority remain external.
- versioned design, architecture, source-governance, and test evidence.

The production course is a static browser application. It does not deploy a repository-operated API,
database, identity service, or learner-data store.

Contributors run integration checks with host Python, Node.js, and Chromium. The repository
distributes optional relay source but no configured or running service, workspace image, or
container topology. The source-backed graph in
[`security-architecture.json`](security-architecture.json) covers the static course and release
supply chain; operated relay instances remain external runtime context.

## Deployment model

The same validated static tree supports two learner paths.

| Path | Course hosting | Model route | NemoClaw route |
|---|---|---|---|
| Public site | Static Pages host, with a learning-site entry point able to link to it | Direct browser HTTPS by default; reviewed relay only for explicit iframe mode | Reviewed cross-origin relay for the separately hosted runtime |
| Co-located launchable | A NemoClaw release pins and vendors a course version into its landing page | Direct browser HTTPS using startup-provided credentials through the existing browser-storage entry | Same-origin route to the runtime created by the launchable |

The model service and NemoClaw runtime are required by the lessons that use them. Relays adapt the
transport boundary while preserving those service roles. See the
[`security design and architecture`](security-design.md) for detailed routes, trust zones, and evidence
anchors.

The default model route is NVIDIA's hosted API. The setup panel can persist one presenter-supplied,
OpenAI-compatible HTTPS base URL for capacity fallback. A URL parameter may prefill that field but
cannot activate it; the learner must review the destination and choose Save and verify. Iframe relay
mode applies only to the default endpoint.

## Component design

| Component | Responsibility | Release relationship |
|---|---|---|
| Authored course | Narrative, runnable browser artifacts, navigation, and safety guidance | Canonical source under `web/nemoclaw/` |
| Locale overlays | Reviewed translated prose and figures without runtime duplication | Sparse overlays assembled over canonical source |
| Build tools | Produce the standalone course, Pages tree, manifests, reports, and archive | Run in CI or a maintainer checkout |
| Static host | Serve immutable page and asset bytes over HTTPS | External hosting control |
| Learner browser | Render pages, keep selected local state, and call declared services | Untrusted client boundary |
| Model service | Process model requests for exercises | External service with its own processing controls |
| NemoClaw runtime | Hold agent sessions, workspace state, tools, and scheduled work | External or co-located runtime |
| Cross-origin relays | Adapt approved browser requests where direct headers or iframe policy require it | Separately operated deployment dependency |
| Optional relay source | Provide a parameterized reference deployment with request filtering and transport tests | Repository source; excluded from the static learner artifact and from live-control claims |
| Vendored browser packages | Provide syntax, editing, Markdown, model-client, tool, schema, and agent-graph code from the static course origin | Versioned release artifact |
| Validation system | Reject stale, unsafe, ungrounded, or unreproducible release states | Required CI and local feedback |

The course can render without model or agent connectivity. Interactive exercises that require an
external service must report connection or authorization failures without turning the static host into
a credential broker.

## Data, credentials, and privacy

| Data class | Storage or transfer | Retention owner | Design control |
|---|---|---|---|
| Model API credential | Tab-scoped browser `sessionStorage`; HTTPS to the selected model route | Learner browser and model-service operator | Password input, visible destination, explicit save and clear actions, discarded when the tab closes, never included in static files or repository CI |
| NemoClaw URL and gateway credential | URL and routing preferences in `localStorage`; gateway and access credentials in tab-scoped `sessionStorage`; HTTPS/WebSocket to the selected runtime route | Learner browser and runtime operator | Host validation, password input, route-specific authentication, replacement in the probe, tab close or explicit clearing |
| Prompt and model response | Transmitted to the selected model service; displayed in the current page | Model-service operator and learner browser | Visible action, declared endpoint, no repository-operated copy |
| Agent command, event, and workspace result | Transmitted to the selected NemoClaw runtime | Runtime operator | Authenticated gateway, runtime policy, learner-visible result |
| Course preferences and local progress | Browser storage | Learner browser | Local-only state; learner can clear site data |
| Static access logs | Host-dependent request metadata | Static-host operator | Outside course code; governed by the selected host |
| Vendored browser dependencies | Loaded from the same static course origin | Static-host operator | Exact lock, package/license inventory, committed artifact SHA-256, source-reference validation |
| Embedded media | HTTPS request metadata to privacy-enhanced video hosts | External content provider | No-cookie embeds and source validation |

The static Pages path adds no repository-operated database, server-side learner profile, or cookie.
Lab and launchable hosts can establish their own access cookies. Course code does not send credentials
to repository CI. Browser storage is not a secret vault and is not encrypted by the course. A learner
using a shared browser must clear stored credentials and site data. Each external service provider
remains responsible for its own logging, retention, access, and privacy controls. This boundary applies
to the model, runtime, relays, launchable, and static host.

The course does not require biometrics, health records, financial records, government identifiers, or
automated decisions about a person. Learners can still enter personal or sensitive text into an
exercise. Course guidance must tell them to use non-sensitive examples. A qualified privacy reviewer
decides whether the selected deployment needs an external privacy assessment.

## Cryptography and integrity

The production browser runtime implements no custom cryptographic algorithm and generates no
cryptographic key. It relies on platform services:

- HTTPS and WSS provide transport protection between browser, host, relays, model service, and runtime.
- Bearer and gateway credentials provide service authentication.
- SHA-256 binds each committed browser dependency asset to its generated public inventory.
- SHA-256 digests bind the release archive, manifest, SBOM, and attached assets.

Python packages used by local authoring or scanning may depend on standard cryptography libraries.
Those packages are not executed by the production static site and remain visible in the exact locks
and generated SBOM. The release owner supplies this inventory, distribution method, and principal use
to the qualified export reviewer. Repository documentation cannot approve an export classification.

## Third-party sources and licenses

The intended release license is Apache-2.0. Contributions use the DCO and the inbound terms in
[`CONTRIBUTING.md`](../CONTRIBUTING.md). The source inventory and provenance beacons record copied,
vendored, converted, and externally sourced material.

The publication-integrity contract classifies every direct course page, displayed course image,
and runtime-generated media surface. Search descriptions can name a product only when it appears in
learner-visible page content. Internal Pages, branch previews, and source mirrors remain `noindex`;
only the protected public build emits the canonical sitemap. Media records distinguish technical
diagrams, source-figure conversions, stylized illustrations, brand assets, and realistic synthetic
media. A realistic synthetic image, video, or audio requires an adjacent visible disclosure before
publication.

The course text is recorded as AI-assisted standard editing. Repository automation cannot decide
whether text concerns a matter of public interest or certify substantive human review. Before public
publication, an accountable editorial owner records that assessment and either confirms substantive
human review and editorial control or supplies the required visible disclosure through the
authorized external process. An unknown origin or missing decision blocks release.

Direct Python requirements are pinned. Transitive environments are locked. Browser packages use an
exact npm lock and are bundled into same-origin assets before release. The public browser dependency inventory
at `web/nemoclaw/dependencies.html` lists direct and bundled
transitive packages, versions, licenses, asset hashes, and source references. The source gate rejects
private links and unmanifested governed material. Generated inventories are evidence; an authorized
review process decides whether each component is acceptable for the distribution.

## Security and reliability controls

The release uses layered controls:

- protected proposals, DCO signoff, required CI, and restricted deployment or release authority;
- source, dependency, waiver, SBOM, architecture, localization, learner-flow, and content validators;
- mutation tests that prove high-value detectors reject known bad states;
- browser tests for rendered layout and state transitions when runtime code changes;
- deterministic build and packaging rules; and
- human inspection of the exact commit, preview, evidence, and external controls.

Expected failure behavior:

| Failure | Required behavior |
|---|---|
| Static host unavailable | Browser receives a normal host failure; no alternate unreviewed content is loaded |
| Model service unavailable or unauthorized | Exercise shows an actionable error and preserves editable input |
| NemoClaw unavailable or unauthorized | Probe fails quickly, clears stale output state, and keeps setup guidance visible |
| Relay unavailable | Route-specific error is visible; course does not silently widen the allowed host set |
| Stale browser credential | Learner can replace or clear it; no credential is copied into logs or source |
| Validation or packaging failure | Promotion stops before deploy or draft release creation |
| Required external artifact evidence missing | Draft may exist, but publication remains blocked |
| Bad published version | Release owner publishes a new patch version; published tags and assets are not moved |

## Release, versioning, and rollback

Protected `main` is the reviewed source line, while branch previews are temporary review artifacts. A
public release starts from an existing protected annotated semantic tag contained in `main`.

The release workflow validates the tag, runs a strict retried live material-provenance check, then
rebuilds with live material refresh disabled. It resolves the locked material-tool Python environment,
emits Python-tooling and learner-delivered browser-package CycloneDX SBOMs, generates a commit-bound
evidence manifest and component license appendix, packages the Pages tree,
and writes checksums. A protected write
step creates a draft release. A human release owner reviews the evidence and publishes it only after
the external approval state allows publication.

Published versions are immutable. Recovery uses a new patch tag and a clear release note. Preview and
draft artifacts may be replaced before publication. The complete artifact contract lives in
[`release_artifacts.md`](release_artifacts.md).

## Traceability

| Design concern | Source of truth | Verification |
|---|---|---|
| Publication boundary | `RELEASE_STATUS.json` | `contribution_safety_audit.py` |
| Production topology | `security-architecture.json` | `security_architecture_audit.py` |
| Product and data design | This document | `release_evidence_audit.py` |
| Test execution and evidence ownership | `release-test-plan.md` | `release_evidence_audit.py` plus CI |
| Source, license, and path hygiene | `scripts/compliance/docs/source_inventory.json`, provenance beacons, and repository-relative path policy | `source_gate.py` and `local_path_leak_audit.py` |
| Dependencies and SBOM | manifests, locks, browser package inventory, waiver registry, generated CycloneDX documents | dependency, browser integrity, waiver, and SBOM policy audits |
| Search and AI-content publication integrity | `web/nemoclaw/publication-integrity.json`, image provenance | `publication_integrity_audit.py` on source and built Pages |
| Release bytes | protected tag, archive, manifest, SBOM, checksums | release workflow and `package_release.py` |

Reviewers must combine this repository evidence with live host configuration and external approval
records. Keep program identifiers, ticket URLs, reviewer names, scan details, and approval records in
the authorized review system rather than this public design.
