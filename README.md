# Securing Agents with OpenShell and NemoClaw

This repository contains the source, browser runtime, and release tooling for an NVIDIA Deep
Learning Institute course on building and securing agent systems. The planned public home is
[`NVDLI/NemoClawDLI`](https://github.com/NVDLI/NemoClawDLI). That repository is reserved but not
yet populated. External publication remains pending OSRB approval; see
[`RELEASE_STATUS.json`](RELEASE_STATUS.json) for the canonical state.

The course starts with a model call and builds toward tool use, workflows, retrieval, deep
research, OpenClaw, and OpenShell sandbox policy. English, Brazilian Portuguese, and Spanish are
built from one branch and checked for translation drift.

## Requirements

- Learners: a modern browser and a user-supplied NVIDIA API key for interactive model exercises.
- Modules 3 and 4: a NemoClaw launchable created when the course requests it.
- Local builds: Python 3, Bash, and Node.js.
- Hardware: no learner-managed GPU is required.

The learner release is a static website. It does not require a repository-operated application
server and never vendors a learner credential.

## Getting Started

After the public repository is populated, build and serve the same site used by Pages:

```bash
git clone https://github.com/NVDLI/NemoClawDLI.git
cd NemoClawDLI
bash scripts/build/build_pages.sh public
python3 -m http.server -d public 8000
```

Open `http://localhost:8000/nemoclaw/`. The course runs entirely in the browser and introduces
external services only when an exercise needs them.

For repository work, install the local checks with `bash scripts/build/install-hooks.sh`, then run
`python3 scripts/validation/release_gate.py --tier fast --no-write` before proposing a change.

## Repository Design

The core release tenet is **surface separation**: content is organized by the environment it can
assume, and no surface may borrow runtime assumptions from another surface without declaring that
dependency.

## Surface Separation

Each top-level surface states its execution contract before any learner or operator runs
it. This keeps browser-only content portable, lets shared services support a bundle of
courses, and makes higher-compute variants explicit rather than accidental.

| Surface | Contract | Current role |
|---|---|---|
| [`web/`](web/) | Browser plus a lab or hosted proxy. Static pages cannot assume student-provisioned microservices or local keys. | Released browser course, foyer, course scripts, and course-scoped reference packets under [`web/nemoclaw/mats/`](web/nemoclaw/mats/). |
| [`cpu/`](cpu/) | CPU lab box that can run shared microservices for one or more courses. | `llm_client`, OpenClaw/OpenShell, sandbox policy control, Docker lifecycle bridge, and service notebooks. |
| `spark/` | Spark-level compute budget and data-plane assumptions. | Reserved for future courses or labs that need Spark rather than a CPU service stack. |
| `l40s/` or other GPU surfaces | GPU-backed lab capacity with explicit image, driver, and scheduling assumptions. | Reserved for future releases that need GPU runtime rather than a browser or CPU contract. |
| [`deploy/`](deploy/) | Operator surface for standing up the course bundle. | Compose overlays and nginx route config for DLI platform and local compute. |

A page under `web/` should use browser APIs, static assets, and declared proxy routes. It
should not assume that a learner has created a service container. A service under `cpu/`
can assume the compose network and shared volumes. A future `spark/` or GPU surface must
state its own compute contract instead of hiding it in page code.

## Release Flow

The repository keeps curated source and projects it into release formats:

- browser course served through Jupyter static paths and nginx
- standalone bundle generated from the same source
- client-side Pages site for preview or external release
- validation reports that use the same link engine as the browser viewer

Versioned public releases use protected annotated SemVer tags and deterministic archives with a
manifest, resolved-environment SBOM, and checksums. See
[`CHANGELOG.md`](CHANGELOG.md) for version history and
[`docs/release_artifacts.md`](docs/release_artifacts.md) for packaging and integrity rules.
The released system boundary and its executable verification plan live in
[`docs/product-design.md`](docs/product-design.md) and
[`docs/release-test-plan.md`](docs/release-test-plan.md). Their machine-readable coverage map is
[`docs/release-evidence.json`](docs/release-evidence.json).
The public [`browser dependency inventory`](web/nemoclaw/dependencies.html) lists every direct and
bundled transitive JavaScript package, exact version, license, same-origin asset, hash, and runtime
reference used by learners.

Students enter through the release foyer, [`web/index.html`](web/index.html). It surfaces
only released courses. Today that is [`web/nemoclaw/`](web/nemoclaw/).

For a presentation-led review, open the hosted
[`repository overview`](docs/repository-overview.html). It connects the learner route,
browser artifacts, runtime boundaries, contribution controls, localization workflow, and
release evidence. The downloadable PowerPoint version lives beside it at
[`docs/repository-overview.pptx`](docs/repository-overview.pptx).

Localized course prose lives as a sparse same-branch overlay under [`i18n/`](i18n/).
Canonical `web/` runtime modules, assets, machine-contract pages, and untranslated pages remain shared.
Open [`web/nemoclaw/localization.html`](web/nemoclaw/localization.html) to compare English
with Brazilian Portuguese or Spanish page state, then read [`scripts/translate/SKILL.html`](scripts/translate/SKILL.html)
for the review workflow and locale-specific language guidance.

## Deployment

Production ships a static browser artifact. It is published to a public static host or pinned and
vendored by a co-located NemoClaw launchable. [`docs/pages_deploy.md`](docs/pages_deploy.md) owns
those delivery paths and preview behavior.

The Compose files under [`deploy/`](deploy/) support local authoring and compatibility testing; they
are not the production course topology. Bring-up and browser-test commands live in
[`docs/lab_runtime_testing.md`](docs/lab_runtime_testing.md). Artifact and tag rules live in
[`docs/release_artifacts.md`](docs/release_artifacts.md).

## Agent Visor

The repo is intentionally agent-readable. Every agent-addressable directory carries a
`SKILL.html` with a `skill-meta` JSON block. The root [`SKILL.html`](SKILL.html) is the
ontology beacon for the bundle. It points to execution surfaces, deployment, tooling,
and process docs. Agents should read [`AGENTS.md`](AGENTS.md), then the relevant
`SKILL.html` before changing files.

## Ideas are easy; code is gated

The contribution boundary is intentionally asymmetric. Questions, corrections, teaching
ideas, runtime observations, and source leads should be cheap to submit through structured
Issues. Discussions become available when the external mirror and its intake features are
approved and enabled. No local checkout or patch is required. Security reports use the private path
described in [`SECURITY.md`](SECURITY.md), never a public Issue.

Code is an untrusted proposal until the repository and a human owner accept it. A direct
patch must name an Issue, declare every touched surface and blast radius, produce validation
evidence, and survive local hooks, required CI, protected-ref rules, owner review, and gated
release environments. Local hooks provide early feedback; protected refs and required checks
are the authority because hooks can be skipped. The contract and operator controls live in
[`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/release_playbook.md`](docs/release_playbook.md).

## Governance and Maintainers

Public governance is explicit: [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) sets behavior and
enforcement, [`SUPPORT.md`](SUPPORT.md) defines support and lifecycle boundaries, and
[`DCO.md`](DCO.md) defines per-commit origin signoff.
The consolidated maintainer plan begins in
[`docs/release_playbook.md`](docs/release_playbook.md) and links dependency management, issue
triage, hotfixes, CI/CD, testing, release operations, and rollback without duplicating those owners.

### Maintainer authority

Repository maintainers route reviews and moderate intake. Surface owners review technical and
learner impact. Release managers own protected tags, publication, and rollback. Security
responders own private intake and coordinated remediation. Assignments live in host teams,
rulesets, protected environments, and `CODEOWNERS` once stable public handles exist.
Nobody approves their own final push or protected release. Agents may prepare patches and
evidence; they cannot supply independent review, merge authority, or release approval.

## Security

Report vulnerabilities through the private NVIDIA Product Security routes in
[`SECURITY.md`](SECURITY.md). Never place vulnerability details, credentials, private URLs, or
exploit paths in a public Issue or Discussion.

## Support

The latest tagged release receives best-effort maintenance without a response-time guarantee.
Use structured Issues for actionable defects and Discussions for questions after community intake
is enabled. [`SUPPORT.md`](SUPPORT.md) defines the full lifecycle and triage boundary.

## Verification

Run the static release gate before pushing:

```bash
python3 scripts/validation/release_gate.py --tier fast --no-write
```

Before release or when changing a cross-cutting contract, run `--tier ship`. The complete
command and evidence matrix lives in
[`docs/release-test-plan.md`](docs/release-test-plan.md).

Release threat-model evidence lives in [`docs/security-design.md`](docs/security-design.md).
Its source-backed graph covers the learner runtime and release supply chain. CI rejects missing
services, unlabeled trust-boundary flows, broken evidence, connector collisions, and stale output.

For browser or Studio changes, also use the containerized browser harness:

```bash
scripts/runtime/browser_env_probe.sh
CONTAINER_ENGINE=podman scripts/runtime/lab_runtime_test.sh --render-only
```

For full lab-network checks, start the deploy stack first, then run the page harness
against `http://nginx/lab/static/...`.

## Contributing

If you have domain expertise, contribute first by lodging focused Issues with evidence:
what is wrong, where it appears, what the learner or operator impact is, and what source
or runtime behavior supports the claim. Issue-first contribution helps preserve the course
release process when the right fix crosses content, deployment, validation, or licensing.
Issue shape and label cadence are defined in [`docs/issue_standards.md`](docs/issue_standards.md).

If you are contributing a direct patch, follow the structured release path:

1. Create a branch for one coherent release concern.
2. Update the source surface and every declared blast-radius file.
3. Add or update validators when the same class of problem should not recur.
4. Run the validation ladder above.
5. Open an MR that says `Addresses #N` unless the change truly closes the issue.

The full external-release operating model lives in [`docs/release_playbook.md`](docs/release_playbook.md). Source and licensing rules live in [`scripts/compliance/docs/vendor_policy.md`](scripts/compliance/docs/vendor_policy.md)
and [`scripts/compliance/docs/open_source_readiness.md`](scripts/compliance/docs/open_source_readiness.md).

## Layout

```text
.
├── web/                    browser courses and browser-owned runtime assets
├── cpu/                    CPU service stack and service notebooks
├── deploy/                 compose overlays and nginx route config
├── docs/                   operating docs
├── scripts/                build, validation, runtime, compliance, and material tooling
├── workspace/              lab image, entrypoint, requirements, and test runner
├── SKILL.html              root ontology beacon served at /lab/static/SKILL.html
└── AGENTS.md               cross-harness agent contract
```

## License

The proposed external release uses the [Apache License 2.0](LICENSE). Contributions use the same
inbound license plus [Developer Certificate of Origin](DCO.md) signoff; this Apache-2.0 project does
not require a separate CLA.
