# Securing Agents with OpenShell and NemoClaw

> Go from one model call to coordinated agents, grounded retrieval, deep planning, and safer execution. NemoClaw provides the reference stack; OpenShell provides the sandbox.

| Start learning | Prepare the lab | Access models |
| --- | --- | --- |
| **[Open the course](https://nvdli.github.io/NemoClawDLI/nemoclaw/)** | **[Launch NemoClaw on Brev](https://brev.nvidia.com/launchable/deploy?launchableID=env-3Azt0aYgVNFEuz7opyx3gscmowS&ncid=ref-dli-759990)** | **[Open NVIDIA Build](https://build.nvidia.com/?ncid=ref-dli-146986)** |
| Work through the four modules. | Keep it running for the live-agent exercises. | Create an API key when prompted. |

[![Course deployment](https://github.com/NVDLI/NemoClawDLI/actions/workflows/pages.yml/badge.svg?branch=main)](https://github.com/NVDLI/NemoClawDLI/actions/workflows/pages.yml?query=branch%3Amain)
[![Code scanning](https://github.com/NVDLI/NemoClawDLI/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/NVDLI/NemoClawDLI/actions/workflows/codeql.yml?query=branch%3Amain)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-76B900)](LICENSE)

The workflow indicators report the current `main` deployment and CodeQL results. The license indicator is grounded in this repository’s [`LICENSE`](LICENSE).

## About the course

Modern agents connect a model to tools and memory, then work until a routing decision ends the task. This course builds those parts before introducing OpenClaw and Hermes.

Editable browser exercises move from model calls to tools, multi-agent routing, retrieval, deep research, persistent skills, and sandbox policy. Later modules use NemoClaw to bootstrap a working agent and OpenShell to inspect what it may access.

> [!NOTE]
> This repository releases the course and validation tools. NemoClaw and its runtime remain external dependencies.

## Course path

### Build the agent loop

![Observations flow from an environment to an agent, and the agent sends actions back to the environment.](web/nemoclaw/assets/figures/01a-agent-environment.svg)

Start with the observation-action loop. Add model calls, state, tools, and a clear stop condition.

### Ground responses in evidence

![A knowledge base is indexed offline, then a live query retrieves context for a grounded model response.](web/nemoclaw/assets/figures/02b-rag-1.svg)

Add retrieval, explicit routing, parallel work, and deeper planning.

### Constrain the running agent

![Three overlapping circles show untrusted input, access to secrets, and an outbound communication channel.](web/nemoclaw/assets/figures/lethal-trifecta.svg)

Connect the design to NemoClaw, then use OpenShell to constrain tools, files, and network access.

## What you will learn

- Build an agent loop and identify its core components.
- Implement reliable tool use and function calling.
- Coordinate agents with structured routing patterns.
- Use grounded retrieval and deeper planning.
- Configure agent identity, persistent skills, and safer execution with NemoClaw and OpenShell.

## Take the course

1. Open the **[GitHub Pages course](https://nvdli.github.io/NemoClawDLI/nemoclaw/)**.
2. Start the **[NemoClaw Brev launchable](https://brev.nvidia.com/launchable/deploy?launchableID=env-3Azt0aYgVNFEuz7opyx3gscmowS&ncid=ref-dli-759990)** before the live-agent modules.
3. Open **[NVIDIA Build](https://build.nvidia.com/?ncid=ref-dli-146986)** and create an API key when requested.
4. Run the supplied examples, inspect their behavior, and change one input at a time.

The static browser site is available in **[English](https://nvdli.github.io/NemoClawDLI/nemoclaw/)**, **[Spanish](https://nvdli.github.io/NemoClawDLI/es/nemoclaw/)**, and **[Brazilian Portuguese](https://nvdli.github.io/NemoClawDLI/pt/nemoclaw/)**. Its canonical entrypoint is the [course source](web/nemoclaw/index.html).

## Run the course locally

Install Python 3.11+, Bash, Node.js 20+, pnpm through Corepack, and Chromium. Python 3.12 is the tested default.

```bash
git clone https://github.com/NVDLI/NemoClawDLI.git
cd NemoClawDLI
bash scripts/build/build_pages.sh public
python3 -m http.server -d public 8000
```

Open `http://localhost:8000/nemoclaw/`. Before installing Python packages, run `python3 scripts/runtime/python_env_probe.py`, use a virtual environment, and install the applicable pinned lock.

## Contribute

Corrections, teaching ideas, runtime observations, and source leads are welcome through [Issues](https://github.com/NVDLI/NemoClawDLI/issues). Broader questions belong in [Discussions](https://github.com/NVDLI/NemoClawDLI/discussions).

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md). Each patch needs an Issue, declared blast radius, validation evidence, and DCO signoff. See the [`Code of Conduct`](CODE_OF_CONDUCT.md), [`support policy`](SUPPORT.md), and [`DCO`](DCO.md).

> [!IMPORTANT]
> Report security issues through [`SECURITY.md`](SECURITY.md). Do not place vulnerabilities, credentials, or access sessions in a public Issue or Discussion.

## Verify a change

```bash
bash scripts/build/install-hooks.sh
python3 scripts/validation/release_gate.py --tier fast --no-write
```

Use `--tier ship` before release or after a cross-cutting contract change. The [`release test plan`](docs/release-test-plan.md) maps claims to evidence; browser setup lives in [`docs/lab_runtime_testing.md`](docs/lab_runtime_testing.md).

Code remains an untrusted proposal until checks and an authorized reviewer accept it. No contributor, maintainer, or agent may approve its own protected merge or release, and approval does not replace a missing control.

## Agent guidance

[`AGENTS.md`](AGENTS.md) is the cross-harness contract. Directory-level `SKILL.html` beacons route people and agents to the relevant files and checks. The compliance suite supports review; it does not replace required security, license, review, or release controls.

## Repository map

| Path | Purpose |
| --- | --- |
| [`web/`](web/SKILL.html) | Browser course, runtime, figures, materials, and dependency evidence |
| [`i18n/`](i18n/SKILL.html) | Reviewed Spanish and Brazilian Portuguese overlays |
| [`scripts/`](scripts/SKILL.html) | Build, validation, runtime, compliance, and material tooling |
| [`docs/`](docs/SKILL.html) | Design, test, deployment, security, and release contracts |
| [`SKILL.html`](SKILL.html) | Repository-wide map |

The [`Rapidly-Evolving Agentic Compliance Suite`](docs/agentic-compliance-suite.md) design note explains the repository’s workflow pattern and limits.

<details>
<summary><strong>Security, dependencies, and release integrity</strong></summary>

The threat model lives in [`docs/security-design.md`](docs/security-design.md). The [`browser dependency inventory`](web/nemoclaw/dependencies.html), [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md), and [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md) distinguish shipped code, tools, and sourced materials.

Optional parameterized relay source is documented under [`scripts/cors-proxy/deployable/`](scripts/cors-proxy/deployable/SKILL.html). It is not part of the learner artifact and contains no deployed account, DNS, credential, or endpoint state.

</details>

## Governance and license

This NVIDIA-owned DLI course repository is approved for public release as a Full-OSS-Project, OSS Type I. That classification does not apply to the NemoClaw product.

[`RELEASE_STATUS.json`](RELEASE_STATUS.json) records the public-safe release state. [`docs/release_playbook.md`](docs/release_playbook.md) owns maintainer roles and publication; [`CHANGELOG.md`](CHANGELOG.md) records version history.

The project uses the [Apache License 2.0](LICENSE). Contributions use the same inbound license with DCO signoff; no separate CLA is required.
