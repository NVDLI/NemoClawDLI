# Rapidly-Evolving Agentic Compliance Suite

This name describes a repository design pattern. It is not a product, certification, compliance
claim, or replacement for NVIDIA review. The pattern helps a repository remain understandable and
safe when work may begin from different agents, model versions, tools, or levels of contributor
experience.

## The problem it addresses

An agent starts with incomplete context. A contributor may understand the lesson but not the release
system, or the build system but not licensing. Model quality and tool access also change. A workflow
that relies on one prompt, one model, or a contributor remembering every layer will eventually miss
an important dependency.

This repository therefore keeps durable decisions in versioned files and verifies the important
ones with deterministic checks. Instructions help work begin correctly. Checks decide whether a
proposal satisfies repository-owned rules. Authorized people still make protected decisions.

## The workflow

1. **Discover.** `AGENTS.md` and the nearest `SKILL.html` identify the relevant owner, source files,
   generated outputs, and checks.
2. **Bound.** An Issue states the problem and expected outcome. The proposed change names its
   surfaces, sources, and blast radius.
3. **Change.** Source files remain the editing surface. Generated or localized results are updated
   through their declared process.
4. **Check.** Deterministic validators test the complete current tree. Mutation tests show that a
   broken rule produces a failure. Browser checks inspect behavior that static analysis cannot.
5. **Explain.** The proposal records commands, results, residual uncertainty, and any external
   evidence still needed.
6. **Decide.** Required CI, protected refs, owners, and release environments control acceptance.
   An agent may prepare evidence but cannot provide independent approval.

The sequence guides work without assuming that the person or agent understands every software
layer at initialization. It also makes a missed dependency repairable: update the owning contract
and its detector so the next contributor receives the same guidance.

## Design rules

- Keep the released boundary small. Repository checks should cover what the repository actually
  builds and distributes.
- Put each rule in one owning document or machine-readable contract. Other pages link to it.
- Prefer deterministic evidence over a model's statement that work is complete.
- Test detectors with realistic breakage. A gate that cannot demonstrate failure is not a gate.
- Keep guidance readable. Checks should protect important outcomes, not freeze incidental wording.
- Separate repository evidence from external approval. Host configuration, legal decisions,
  product security review, and release authority need their actual owners.
- Fail closed when a new release surface appears. Expanding scope requires an explicit contract and
  review, not an exception that makes the new surface invisible.

## Implementation in this repository

The root contracts route work to source-specific `SKILL.html` files. Structured Issues and change
templates capture intent and blast radius. The release gate composes static, browser, dependency,
localization, licensing, and security checks. CI binds those results to a commit and artifact.
Protected human review controls merges and publication.

These layers are deliberately independent. Better prompts can improve a proposal, but cannot relax
the gate. A stronger model can find more issues, but cannot approve its own work. A new contributor
can follow a short path while the repository retains the deeper evidence needed by reviewers.

For the concrete operating contracts, use:

- [`agent_process.md`](agent_process.md) for change execution and handoff;
- [`release-test-plan.md`](release-test-plan.md) for claims and evidence;
- [`release_playbook.md`](release_playbook.md) for protected host and release controls; and
- [`security-design.md`](security-design.md) for the reviewed system boundary.
