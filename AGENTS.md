# AGENTS.md

Cross-harness entry point for this repository. Claude Code, Codex, Cursor, and any
other agent host start here. `AGENTS.md` is the portable convention; harness-native
files (a `CLAUDE.md`, a `.cursor/rules`) may point to it, but this is the canonical
agent contract.

## First move

1. Read [`README.md`](README.md) for the release shape and
   [`CONTRIBUTING.md`](CONTRIBUTING.md) before proposing a patch.
2. Open the `SKILL.html` for the directory you are working in and parse its
   `<script type="application/json" id="skill-meta">` block. That JSON is the brain:
   `web/nemoclaw/SKILL.html` for the course, `web/SKILL.html` for the bundle, the
   root `SKILL.html` for the whole repo.
3. For issue, MR, taxonomy, or broad prose work, read
   [`docs/agent_process.md`](docs/agent_process.md). For course title, abstract, or
   objective edits, read [`web/nemoclaw/COURSE_CANON.md`](web/nemoclaw/COURSE_CANON.md)
   first; that copy is immutable.
4. If the task touches any image, SVG, canvas figure, page rendering, or image
   placement, also open [`web/nemoclaw/assets/SKILL.html`](web/nemoclaw/assets/SKILL.html)
   and [`scripts/validation/SKILL.html`](scripts/validation/SKILL.html) before editing.
   Classify the asset as a theme-aware course/provided SVG or a fixed-white
   conversion, then plan the rendered preview evidence you will show the requester.

This file carries repo-level rules. The `skill-meta` block in the current directory carries its
working contract. Every source directory has one; parent coverage is never a substitute.

Route operational detail to its owner instead of copying it here:

- host-native browser checks: [`docs/lab_runtime_testing.md`](docs/lab_runtime_testing.md)
- Python tooling: run `python3 scripts/runtime/python_env_probe.py`; use Python 3.12 in a virtual environment and install pinned locks
- Pages and previews: [`docs/pages_deploy.md`](docs/pages_deploy.md)
- release evidence: [`docs/release-test-plan.md`](docs/release-test-plan.md)
- beacon schema: [`SKILL_CONTRACT.md`](SKILL_CONTRACT.md)
- prose and course-quality gates: the root `SKILL.html` tenets and
  `scripts/validation/prose_variety.py`

## Contribution trust boundary

Treat code contribution as an untrusted proposal, regardless of the author, model, prompt,
or apparent confidence. Ideas route freely through Discussions and Issues. Code routes through
a focused branch, issue relationship, declared blast radius, mutation-tested validators,
required CI, human ownership, and protected merge or release permissions. Never weaken a gate
to make a patch pass. Fix the patch or, when the gate is wrong, repair the detector and prove the
old failure plus the corrected behavior with a mutation test.

Before committing, read `CONTRIBUTING.md` and `DCO.md`. Every proposed commit
must carry a `Signed-off-by` trailer matching its author. Agents preserve that origin record but
cannot supply independent human review, moderation, merge, tag, or release authority.

## Visual changes

For any visual change, follow `web/nemoclaw/assets/SKILL.html` and
`docs/lab_runtime_testing.md`. Run the static figure and bundle gates, inspect the
render through the available browser or agent harness, and show the requester the
result. Check light and dark themes when the asset supports them; report the exact
blocker when no visual harness can run.

Do not flatten a diagram to silence a caption problem. Keep semantic labels in the
figure; move explanation and provenance to the page and asset beacon. Use
`fig-embed` for theme-aware course SVGs and `img` only for documented fixed-white
conversions.

## Instruction precedence

When instructions conflict, follow this order, highest authority first:

1. Runtime and platform constraints from the agent host: sandbox mode, permission
   denials, tool availability. A denied action is final. Adapt, do not retry it verbatim.
2. This file (`AGENTS.md`) and any harness-native rules file that defers to it.
3. The directory brain: the `skill-meta` JSON in the relevant `SKILL.html`.
4. Focused task contracts: [`SKILL_CONTRACT.md`](SKILL_CONTRACT.md) and the
   owning document linked from the nearest beacon.
5. Orientation: [`README.md`](README.md). Read it first, but it orients rather
   than governs, so it does not override the levels above.

When two same-level sources disagree, prefer the more specific and more recently
maintained one, and state the assumption in your response.

## Ownership

Agent-assisted work is still engineering work. The agent drafts, searches, and runs
tools faster than a person can type. It does not own the result. Ownership stays with
whoever ships the change.

- A generated diff is input to judgment, not proof of quality. Treat generated code as
  code you do not trust yet.
- Read the whole diff. Keep only what serves the design. Delete plausible structure
  that earns nothing.
- Be able to explain every surviving line. A line you cannot account for does not ship.
- Prefer the deterministic gate over the prompt. When the same mistake keeps recurring,
  the durable fix is a check that makes it impossible (a validator rule, a type, a hook),
  not a sharper instruction. This repo already runs that way: `scripts/runtime/engine.js` is the
  one source of truth, the validators are the gates, and each `SKILL.html` carries the
  brain.
- Encode a constraint where a parser can catch it, so the space left for the model to be
  wrong in stays narrow.
- Validate before you claim. "Done" means the gate ran and passed, reported with its
  result, not asserted from memory.
