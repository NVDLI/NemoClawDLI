# Securing Agents with OpenShell and NemoClaw

This repository contains an NVIDIA Deep Learning Institute course about building agent systems and
applying practical security boundaries with NemoClaw and OpenShell. The course progresses from a
model call to tools, workflows, retrieval, deep research, sandbox policy, and deployment choices.
It is available in English, Brazilian Portuguese, and Spanish.

This course is approved for public release at
[`NVDLI/NemoClawDLI`](https://github.com/NVDLI/NemoClawDLI).
[`RELEASE_STATUS.json`](RELEASE_STATUS.json) records that public-safe state without copying private
approval evidence into the repository. Passing repository checks does not replace required
security, license, review, or release controls.

## Take the course

Start at [`web/index.html`](web/index.html), then open the
[`NemoClaw course`](web/nemoclaw/index.html). Interactive model exercises require a user-supplied
NVIDIA API key. Modules 3 and 4 request a NemoClaw launchable when they need one. No
learner-managed GPU or repository-operated application server is required.

The learner release is a static browser site. It does not vendor learner credentials. The
NemoClaw product, launchable, and runtime are external dependencies, not releases of this course
repository.

## Run it locally

Install Python 3.11 or newer, Bash, Node.js 20 or newer, pnpm through Corepack, and Chromium or a
compatible Chrome browser. Python 3.12 is the tested default.

```bash
git clone https://github.com/NVDLI/NemoClawDLI.git
cd NemoClawDLI
bash scripts/build/build_pages.sh public
python3 -m http.server -d public 8000
```

Open `http://localhost:8000/nemoclaw/`. Before installing Python packages, run
`python3 scripts/runtime/python_env_probe.py`, use a virtual environment, and install the applicable
pinned lock. The repository does not prescribe a container topology.

## Contribute

Questions, corrections, teaching ideas, runtime observations, and source leads belong in structured
Issues. Discussions accept broader questions and early ideas. Security reports must use the
private route in [`SECURITY.md`](SECURITY.md), never a public
Issue or Discussion.

Code remains an untrusted proposal until required checks and an authorized human review accept it.
Every patch needs an Issue, a declared blast radius, validation evidence, and DCO signoff. No
contributor, maintainer, or agent may approve its own protected merge or release.
Human approval does not replace a missing control or resolve unverified release risk.

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md). It owns setup, issue and patch paths, signoff,
validation, localization ownership, and contributor credit. The
[`Code of Conduct`](CODE_OF_CONDUCT.md), [`support policy`](SUPPORT.md), and
[`DCO`](DCO.md) define the remaining contributor-facing terms.

## Verify a change

Install the local hooks, then run the fast gate:

```bash
bash scripts/build/install-hooks.sh
python3 scripts/validation/release_gate.py --tier fast --no-write
```

Use `--tier ship` before release or after a cross-cutting contract change. The
[`release test plan`](docs/release-test-plan.md) maps claims to evidence. Browser prerequisites and
render checks live in [`docs/lab_runtime_testing.md`](docs/lab_runtime_testing.md).

Release threat-model evidence lives in [`docs/security-design.md`](docs/security-design.md).
Its source-backed graph covers the learner runtime and release supply chain. CI rejects missing
services, unlabeled trust-boundary flows, broken evidence, connector collisions, and stale output.
The generated review design and diagram carry matching architecture fingerprints. A report that
does not preserve that binding remains Unknown until the submitted attachments are confirmed.
Repository-owned mitigations, unresolved host or provider requirements, residual risks, and
non-applicable recommendations are separated in
[`docs/security-control-disposition.md`](docs/security-control-disposition.md).

## How the repository guides agents

[`AGENTS.md`](AGENTS.md) is the cross-harness contract. Each source directory has a `SKILL.html`
that routes work to the relevant files and checks. Deterministic validators, protected host rules,
and human review remain authoritative when agent context, model behavior, or contributor experience
varies.

The compact design note
[`Rapidly-Evolving Agentic Compliance Suite`](docs/agentic-compliance-suite.md) explains this
workflow pattern, its limits, and how the repository implements it. The name describes an
engineering approach, not a certification, product, or substitute for approval.

## Project map

| Path | Purpose |
| --- | --- |
| [`web/`](web/SKILL.html) | Browser course, shared runtime, figures, materials, and dependency evidence |
| [`i18n/`](i18n/SKILL.html) | Reviewed locale overlays built with the canonical course |
| [`scripts/`](scripts/SKILL.html) | Build, validation, runtime, compliance, and material tooling |
| [`docs/`](docs/SKILL.html) | Design, test, deployment, security, and release contracts |
| [`SKILL.html`](SKILL.html) | Repository map for people and agents |

The repository ships the static course and its validation tools. It does not ship a lab operating
system, service stack, or base container. The
[`browser dependency inventory`](web/nemoclaw/dependencies.html) identifies code learners receive.
[`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) and
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) cover software and material relationships.

## Governance, release, and license

This NVIDIA-owned DLI course repository is a Full-OSS-Project, OSS Type I. That classification
applies only to this course repository and does not release or classify the NemoClaw product.

[`docs/release_playbook.md`](docs/release_playbook.md) owns maintainer roles, public GitHub setup,
protected publication, and internal integration cadence. [`CHANGELOG.md`](CHANGELOG.md) records
version history. [`docs/product-design.md`](docs/product-design.md) defines the release boundary,
and [`docs/security-design.md`](docs/security-design.md) defines its trust boundaries.

The public release uses the [Apache License 2.0](LICENSE). Contributions use the same
inbound license with DCO signoff; this project does not require a separate CLA.
