# Security control disposition

This is the short human view of the canonical aggregate register in
[`security-control-themes.json`](security-control-themes.json). The generated review design embeds
the full register so exported reviewers do not need repository links. Private findings remain in the
authorized review system. Scope and trust-boundary detail remains in the
[`security design`](security-design.md).

## Status vocabulary

- **Verified:** repository evidence proves the control.
- **Partially verified:** repository evidence covers only part of the boundary.
- **External evidence required:** an operator must prove the live control.
- **Architecture decision required:** mitigation would change the static-client design.
- **Human approval required:** release remains blocked until the governing process authorizes the
  retained risk. That authorization does not implement the missing defense.
- **Not applicable:** the control cannot meet the stated objective in this product boundary.

Current status and evidence take precedence over future work. A future candidate is not
implemented and cannot support a Mitigated status. An external control without current operator
evidence remains Not Mitigated; contradictions resolve to the conservative status. A component
cannot mitigate a requirement it cannot enforce, and a route outside the architecture cannot
support a mitigation claim.

Repository evidence does not grant Legal, open-source, Export, Privacy, Product Security, source-host,
host, service, or release approval.

## Decision resistance

The safe default is no release. A human handoff does not defend a threat and cannot change an
Unknown or Not verified control into a pass. Implement and verify the enforceable defense first.
When policy permits residual-risk acceptance, the decision remains in its governing system. The
repository stores only the public-safe approval state, not identities, tickets, rationale, or
evidence. A risk exception records accountability; it does not pretend the missing control exists.
Protected environments require independent release authorization. Workflow manifests and
provenance bind the exact source commit and artifact digest.

## Review synthesis

Generated assessments can misclassify recommendations as current controls or expand the course
boundary. Correct scope, evidence, ownership, and status before accepting their risk output.

Public evidence stays aggregated by control theme. Do not version private review rows one-to-one.

## Assessment reconciliation

1. Compare the report's embedded diagram fingerprint and flow/objective register with the submitted
   design and diagram. Treat a missing or mismatched binding as Unknown input identity.
2. Normalize and compare the private report's threats, requirements, and architecture with the
   previous report. A new timestamp, layout, or submission wrapper is not a new finding.
3. Correct the Target of Evaluation, facts, and ownership before interpreting risk or status.
4. Check the security objective, enforcement owner, architecture route, and duplicates. Reject a
   requirement assigned to a component that cannot enforce it or to a route that does not exist.
5. Give each private requirement exactly one disposition: verified repository control, open
   repository action, external evidence required, architecture decision required, or not applicable
   with a recorded reason.
6. Name the enforceable defense and its owner for every open item. Referral to a reviewer is not a
   defense.
7. Keep a generated Mitigated label open when it depends on a live external control without current
   operator evidence. The label is not evidence.
8. Keep release blocked until the defense is Verified or the governing process authorizes retained
   risk. Keep that evidence outside the repository, then bind deployment through an independent
   protected environment and exact-artifact provenance.
9. Collapse exact and semantic duplicates to one disposition, then map repeats to the aggregate
   themes below. If scope, architecture, current controls, evidence, or open decisions changed,
   update the public sources. Regenerate the review package from those sources.

| Theme | State | Why it remains open |
|---|---|---|
| Source and CI trust | Shared verification required | Repository workflows are reviewable; live identity, branch, bypass, and reviewer settings are host evidence. |
| Build supply chain | Partially verified | Exact locks, inventories, SCA, and SBOM exist; hermetic or reproducible build assurance is a release-policy decision. |
| Artifact integrity | Partially verified | Byte continuity is verified; workflow-defined provenance has no live evidence, and the ordinary builder is not a trusted builder. |
| Static host and browser | Shared verification required | Static code checks are verified; response headers, WAF, cache policy, and availability are host controls. |
| Browser-held credentials | Architecture decision required | JavaScript-readable credentials are inherent to direct browser calls; a broker or proof-of-possession changes other systems. |
| Relay, model, launchable, and runtime | External evidence required | Relay source controls are tested, but the repository cannot attest deployed authorization, isolation, quotas, monitoring, or retention. |
| Assessment fidelity | Not verified and release-blocking | Generated scope, ownership, and statuses require evidence reconciliation; review alone cannot close them. |

## Source and contribution controls

- Verified: pull-request jobs are read-only, receive no deployment credentials, use immutable action
  pins, and run required validation with timeouts.
- Host evidence required: MFA, protected branches and tags, required reviewers, bypass restrictions,
  commit-signature policy, and immutable audit history.
- The intended OSS Type I classification applies only to the NemoClaw DLI course repository and its
  static course artifacts. It does not classify or release the NemoClaw product, launchable,
  runtime, relays, or services.

## Build and artifact controls

- Verified: exact dependency locks, dependency inventories, bounded artifacts, safe extraction,
  complete SHA-256 inventory, single-artifact promotion, and post-deploy byte comparison.
- Verified for source only: the optional relay projection is history-free, hash-bound, and
  Apache-2.0 marked. It has no package dependencies. Node and mutation tests cover
  its parameterized source. These checks do not attest a deployment.
- Workflow-defined, not live-verified: dependency-executing validation has no signing authority.
  Two clean jobs assemble and compare without package installation. The no-checkout signer receives
  only their manifest; the deploy job runs only a pinned action. Their identities remain separate.
- Residual risk: Python validation locks lack artifact hashes, runner egress is unrestricted, and
  two ordinary runners are not an approved trusted builder.
- Conditional next step: add a hermetic, reproducible builder and approved package mirror if release
  policy requires stronger dependency-origin assurance.

## Static hosting and browser controls

- Verified: no remote executable dependencies, reviewed URL policy, exact browser dependency
  inventory, and safe model-output rendering.
- Host evidence required: HTTPS and HSTS state, response-header CSP, immutable caching, WAF and
  bandwidth limits, availability, and incident response.
- Not applicable as independent controls: browser certificate pinning and same-origin Subresource
  Integrity. Browser trust stores own certificate validation; replacing same-origin HTML and assets
  together defeats an asset-only hash. Whole-artifact verification covers the repository boundary.
- Endpoint compromise or a malicious browser extension can read browser-visible credentials and
  content. Course code reduces injection opportunities but cannot make a compromised browser safe.

## Relay, model, launchable, and runtime controls

These systems are external dependencies. Their owners must prove, as applicable:

- destination, method, schema, body, frame, deserialization, and object-authorization enforcement;
- credential lifetime, audience, revocation, replay, binding, and mTLS decisions;
- request, token, concurrency, connection, compute, storage, spend, and egress quotas;
- instruction and tool authorization, tenant and sandbox isolation, logging, retention, alerting,
  patching, recovery, and incident response.

The course repository can test route selection and client behavior. It cannot convert missing live
service evidence into a mitigation.

## Publication blockers and retained risks

Before publication, authorized owners must resolve:

- Live source-host rules, identities, reviewers, bypasses, and scheduled public-to-internal sync.
- Live provenance evidence and the trusted-builder policy decision.
- Static-host security-header, cache, WAF, capacity, and availability decisions.
- Browser credential lifetime, audience, revocation, replay, storage, and shared-device behavior.
- Relay, model-service, launchable, and runtime evidence listed above.
- Authoritative secret, vulnerability, malware, license, privacy, and release reviews.
- Generated scope and status reconciliation against `security-control-themes.json`.

Unknown, partial, architecture-decision, shared-verification, and human-review states remain open.
