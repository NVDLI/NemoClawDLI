# Security design record

This document explains the machine-readable
[`security-architecture.json`](security-architecture.json) and its deterministic
[`security-architecture.svg`](security-architecture.svg) projection. The broader product scope,
data and cryptography inventories, release behavior, and test mapping live in
[`product-design.md`](product-design.md) and [`release-test-plan.md`](release-test-plan.md).
Aggregate current controls, future candidates, triggers, and verification expectations live in
[`security-control-themes.json`](security-control-themes.json). The shorter human status view is
[`security-control-disposition.md`](security-control-disposition.md).
This record contains no internal workflow, program identifier, submission version, or approval.

## System scope

This security record covers the NemoClaw DLI course repository and the static course artifact it
builds. It does not classify or release the NemoClaw product, launchable, runtime, model service,
or relay deployments. Those systems appear below only as external dependencies and trust
boundaries exercised by course lessons.

The repository owns source and workflow definitions; an external source host and CI service execute
those workflows. They produce one static HTML, JavaScript, CSS, image, and locale artifact. A public
static host or co-located launchable serves that artifact. Course code then runs in the learner's
untrusted browser and connects to external model and NemoClaw services.
The co-located launchable may select a reviewed course release for vendoring, but its intake and
deployment remain external and unattested by this repository.

Contributors run the static checks with host Python, Node.js, and Chromium. External isolation is
operator-owned; the repository owns no container topology or image. The
architecture validator rejects unreviewed production dependencies.

The authoring and validation implementation may use host-native tools or containers without adding
either to the production boundary. A repository-owned service, image, or deployment path is a scope
change and requires architecture and security-control review before it can enter a release path.

## Threat-analysis invariants

These statements are the canonical Target of Evaluation summary. Correct any generated
contradiction before accepting its risk labels or requirement statuses.

- The subject is the DLI course repository and its static course artifact. The NemoClaw product,
  source host and CI service, static host, launchable, runtime, model service, browser environment,
  and relay deployments are external dependencies, not releases or security boundaries owned by
  this repository.
- The intended OSS Type I source and published course artifact are public. Their confidentiality
  after publication is not a security objective. Pre-publication confidentiality and Git transport
  configuration remain host-owned controls, and secrets are forbidden from source and build output.
- The learner browser is untrusted. Model, gateway, and access bearer credentials are JavaScript-readable
  values retained in tab-scoped `sessionStorage`; browser storage is not a vault. HttpOnly cookies
  need a same-origin broker; proof-of-possession needs issuer and service support.
- Untrusted code remains read-only and secret-free. Candidate interfaces run egress-denied after
  acquisition drops its read token. A runnerless child blocks pipeline variables; a separate
  secret-free job builds the pinned browser runtime without candidate content. Trusted code owns
  live probes and rejects unclassified capability. Public signing remains no-checkout. CDN
  preparation lacks AWS authority; only an exact plan reaches the isolated
  publisher. Protected-environment review remains host evidence.
  These jobs hold no signing key, model API credential, runtime credential, or deployment key.
- CI does not write Git refs or repository content. Logs and test results are job artifacts or
  external records. Branch and merge-request validation is normal; protected annotated tags only
  identify release candidates.
- A protected-environment reviewer is a human actor, not a component. Release owners and legal,
  export, privacy, or security reviewers are evidence-workflow actors too. They are not deployed
  components or runtime data flows. A static host serves bytes; repository workflows, not the host,
  enforce build and deployment gates.
- Human review identifies accountability but supplies no technical defense. An open concern remains
  release-blocking until its defense is Verified or the release owner accepts the residual risk
  through the governing process. Acceptance does not implement the missing control.
- Private authorization evidence remains in its governing system. `RELEASE_STATUS.json` records
  only the public-safe approval state. Protected environments authorize deployment, and generated
  provenance binds the deployed artifact to the exact reviewed commit.
- In the architecture diagram, only solid green nodes are Target of Evaluation components. Dashed
  gray nodes are external context with no live-control attestation. Edges state expected integration
  routes and data, not verified external configuration. External-to-external internals are excluded.
- Two package-free jobs assemble the same tree without OIDC; a later job compares them. Signing and
  deployment jobs execute no repository source. No live run has proved this, and ordinary runners
  are not trusted builders.
- Live host, launchable, relay, model-service, and runtime controls are Unknown until their owners
  supply evidence. This design does not assume mTLS, DPoP, zero-retention model processing,
  prompt-injection detection, private Git networking, or a curated private package registry.
- The submitted design and diagram form one evidence pair. The generated design records the full
  architecture-model and diagram digests, while the diagram shows the model fingerprint. A report
  with a missing or different fingerprint, flow register, or objective list has Unknown input
  identity and cannot support a current disposition.

## Threat register

These are security threats whether the triggering action is malicious, careless, or delegated to
an agent that produces plausible but unsupported output. The state is evidence status, not a risk
rating. A threat remains open until its defense is Verified or an implemented release guard
validates authoritative residual-risk acceptance. The latter path is not implemented.

| ID | Threat event | Boundary | Current state and control theme |
|---|---|---|---|
| TR-01 | Untrusted source changes inject executable course behavior or weaken its detectors. | Contributor to source and CI | Shared verification required; Source and CI trust |
| TR-02 | A dependency, build tool, package source, or runner changes the generated course. | Source and CI to build artifact | Partially verified; Build supply chain |
| TR-03 | A stale, substituted, replayed, or differently built artifact is promoted. | Build artifact to static host or release | Partially verified; Artifact integrity and publication |
| TR-04 | Hosting, cache, or same-origin script mutation changes code executed by learners. | Static host to learner browser | Shared verification required; Static host and browser execution |
| TR-05 | Browser-visible credentials are stolen, replayed, overscoped, or retained on a shared device. | Learner browser to external services | Architecture decision required; Browser-held credentials |
| TR-06 | Relay routing or authorization permits destination abuse, unsafe parsing, or cross-user access. | Browser through external relay | External evidence required; Relay boundary |
| TR-07 | Model credentials, prompts, or responses are misused, over-retained, or charged without adequate limits. | Browser to model service | External evidence required; Model-service boundary |
| TR-08 | Launchable or runtime authorization, isolation, or sandbox enforcement permits cross-tenant access or escape. | Browser to launchable and runtime | External evidence required; Launchable and runtime boundary |
| TR-09 | Requests exhaust host, relay, model, runtime, storage, or spend capacity. | All served and interactive routes | Shared verification required; Availability and resource controls |
| TR-10 | Generated analysis, stale evidence, a checkbox, or reviewer deference launders an open concern into approval. | Assessment and release decision | Not verified and release-blocking; Assessment fidelity |

A certification has effect only when its authority binds claims and evidence fingerprints to the
exact subject, environment, release, observation time, expiry, result, and limitations required by
`security-control-themes.json`. Repository tests cannot certify external systems. Checksums, HTTPS,
and review do not certify signing, provenance, SRI, CSP, mTLS, quotas, or external authorization.
Missing, stale, self-issued, unbound, or unverifiable evidence is Unknown and release-blocking.

## Threat enumeration boundary

Runtime and release-flow threat enumeration uses only the edges and security objectives declared
in [`security-architecture.json`](security-architecture.json). The list is exhaustive for deployed
and publication data flows. TR-10 is an evidence-workflow threat, not a deployed flow, so it is
controlled by the release decision guard rather than an invented architecture edge. Do not infer a
new course flow from external context or mechanically assign confidentiality, integrity, and
availability to every edge. Public source and released static assets have no confidentiality objective.

Direct and operator-relayed variants from course client code to the same external service are one
course boundary flow. Relay-to-upstream hops and launchable control-plane startup are external
operator internals, not additional course flows. A launchable-provided credential still travels on
the browser-to-model flow when course client code sends the model request. Human review and approval
are evidence workflows, not deployed components or runtime data flows.
Exact and semantic duplicate requirements receive one disposition. Repetition does not create a
new threat, mitigation, or evidence claim.

## Browser routing by host

| Course host | Model service | NemoClaw runtime |
|---|---|---|
| Public static host | Direct HTTPS to the selected model endpoint. The default is NVIDIA-hosted; a presenter may supply a compatible capacity fallback. | Header-authenticated launchables use the configured cross-origin relay. Browser-session launchables keep their HttpOnly session browser-to-launchable: direct WebSockets plus fixed read-only loopback bootstrap through the authenticated terminal. Live external controls require operator evidence. |
| Co-located launchable with a pinned course release | Direct HTTPS using the endpoint and credentials supplied through the launchable startup path and the course's existing browser credential mechanism. | Same-origin direct route to the launchable-created runtime; do not use the relay. |
| Either host embedded in an iframe | Model relay when explicit iframe proxy mode is enabled. | Follow the host-specific NemoClaw route above. |

Relays are transport choices, not substitute services. The host changes the route, not the learning
contract.

## Trust boundaries and data

| Boundary | Transport and data | Authentication | Primary controls |
|---|---|---|---|
| Course source to external CI | Public source and commit metadata | Developer identity; live policy requires operator evidence | Repository validators and DCO; live identity and review settings unverified |
| External CI to static host | Static bundle and SHA-256 inventory | Workflow-requested deployment identity; live rules unverified | Bounded artifact, manifest recheck, and post-deploy byte comparison |
| Static host to learner device | HTTPS pages and assets | Public or host-controlled access | Relative paths, locale integrity, preview isolation, URL checks |
| Browser to model service | HTTPS credential, prompts, and responses | Learner-provided bearer credential | TLS, password input, direct route by default, optional iframe relay |
| Browser to NemoClaw | HTTPS and WebSocket commands, events, and gateway credential | Gateway credential plus hosting identity | Host restriction, credential handling, sandbox policy, host-specific routing |
| Static host to browser | Same-origin vendored JavaScript and CSS | Host access policy | Exact lock, license inventory, artifact SHA-256, source-reference validation |

Credentials are entered through password fields and retained only for the current browser tab.
Non-secret route preferences may persist in `localStorage`. Credentials are not built into the
static artifact or sent to repository CI. The model destination is visible and requires an explicit
save; a query parameter can only prefill it. Prompts, responses, agent commands, and events cross
the selected service boundaries. The repository adds no production application database or
server-side learner-data store.

Any service URL embedded in browser code is observable in the published artifact and network
traffic. It is not a secret or an authorization boundary. Operator account, state, bucket, DNS,
generated distribution, and credential values remain outside public source; the public middleware
projection uses only operator-supplied deployment parameters. An operated relay must remain safe
when its URL and protocol are known.

Startup-provided material in the co-located path populates the same storage entry consumed by the
course helpers. The course separately caches only a non-authoritative verification result for the
browser session.

An attacker who already executes code in the learner's browser context can read JavaScript-accessible
credentials and observe prompts or responses before transport encryption. The static course cannot
create a stronger secret boundary inside that compromised context. Moving credentials to HttpOnly
cookies would require a same-origin credential broker, while proof-of-possession tokens require
credential-issuer and service support. Those are hosting and service architecture decisions, not a
client-only mitigation. Repository controls instead prevent unreviewed executable dependencies,
constrain credential destinations, render untrusted output safely, and give learners explicit save,
replace, and clear actions.

## Security controls

- Static validation covers page structure, learner flow, provenance, localization, dependency
  pins, architecture drift, contribution boundaries, and release artifacts.
- The repository contains no Dockerfile, Containerfile, Compose topology, or image-build command.
  A fail-closed boundary audit rejects their reintroduction because it would expand the reviewed scope.
- GitHub Pages builds in a read-only job, rejects unexpected executable references and artifact
  substitution, records every generated file by SHA-256, and exercises the exact tree in Chromium.
- Browser dependencies require exact versions, a generated integrity inventory, and same-origin delivery.
- Course code selects reviewed relay routes and authentication behavior. The optional deployable
  source is hash-bound, parameterized, and tested; live relay enforcement is Unknown until
  the operator supplies evidence for the deployed instance.
- Course code expects launch authentication, gateway checks, and sandbox policy; their deployed state is Unknown until launchable and runtime owners supply evidence.
- Secrets, live credentials, internal deployment identifiers, scan output, and approval records do
  not belong in this document or graph.

Operational relay deployment, launchable configuration, identity policy, protected environments,
and provider controls live outside this repository. Optional source under
`scripts/cors-proxy/deployable/` carries no environment identifiers or deployment authority.
Operators compare live configuration with this design before release.

## Release controls

Repository workflow definitions validate source, build the static artifact, check configured URLs,
and record human ownership. They request isolated branch previews and manifest-preserving Pages
deployment; live source-host enforcement remains operator evidence. A separate tag workflow produces
deterministic archives, a release manifest, an SBOM, and checksums.

Internal GitLab may prepare a language-selected CDN plan from an exact successful artifact without
AWS authority. The isolated publisher accepts neither destination nor command input from candidate
CI, uses a root-owned parameterized destination and AWS configuration, paginates fixed course roots,
invalidates caches, and compares served bytes.
Protected environments, runner state, AWS identity, and installation still require live evidence.

Host Python, Node.js, and Chromium support local authoring and tests; they are not production nodes.
Direct Python dependencies support material and validation tools, not the production browser runtime. Direct
manifests and transitive locks are checked for parity. Scanner tooling uses a separate locked
environment. Time-limited exceptions remain in the waiver register and are guarded by reachability
checks.

## Evidence and reconstruction

The JSON graph is the source of truth; the SVG is generated. Every production node and flow names
repository evidence. Validation also derives CI stages, release jobs, browser host roles, dynamic
remote-host suffixes, and relay sources from code. Substantial drift fails CI until the graph and
this design are reviewed.

The public record contains component roles, trust zones, data and authentication classes, control
intent, repository evidence paths, and source-derived topology fingerprints.
Keep internal program identifiers and review-system URLs outside the repository. The same boundary
applies to submission versions, scan output, credentials, deployment identifiers, and approval records.

An authorized reviewer can reconstruct a private submission from the reviewed commit:

1. Run the renderer and architecture audit.
2. Review the SVG with this design and the product design.
3. Add live-control evidence and private identifiers only in the approved internal workflow.

Repository validators support human analysis; they do not replace it or claim external-host
configuration, provider controls, publication approval, or completion of a security process.

### Regenerate and verify

```bash
python3 scripts/figures/render_security_architecture.py --check
python3 -m unittest -v tests/validation/test_embedded_validator_suites.py
python3 scripts/validation/security_architecture_audit.py
```

After an intentional graph change, run
`python3 scripts/figures/render_security_architecture.py`. Inspect the source-derived view with
`python3 scripts/validation/security_architecture_audit.py --observed-contract`.

The audit rejects stale projections, unclassified local services or volumes, missing production
nodes, dangling edges, undocumented trust-boundary crossings, unlabeled sensitive flows, broken
evidence anchors, overlaps, and ambiguous collinear flows. The flow register uses three lines per
edge: endpoints, transport and data, then authentication and trust boundary.
