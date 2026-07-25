---
name: nemoclaw-contribution
description: Execute NemoClawDLI issue, pull-request, CI, merge, Pages, and deployment work without losing the requested terminal condition. Use for substantial repository changes, GitHub-signed API commits, exact-head validation, protected review or environment gates, cross-thread coordination, and any task that may compact or resume.
---

# NemoClawDLI contribution

Read `AGENTS.md`, `CONTRIBUTING.md`, the owning `SKILL.html`, and
[`../../../.codex/continuity-contract.json`](../../../.codex/continuity-contract.json)
before changing state.

## Establish the checkpoint

Record the checkpoint fields from the continuity contract in the active plan. Keep one step in
progress. Update the record after every user correction, compaction, commit, push, rebase, merge,
policy change, or handoff.

- Preserve the user’s outcome and terminal condition. A diagnosis, commit, green local gate, merge,
  or deployment is not completion when later stages remain.
- Bind the issue, branch, pull request, commit, artifact, workflow run, deployment, and live URL by
  exact identifier.
- Record the current failed gate and its complete trace. A required failure remains a failure.
- Name one owner for each terminal action. Parallel work may split independent scopes, but two
  threads must not monitor or mutate the same merge or deployment.

## Apply the continuity invariants

- `preserve-terminal-condition`: Reconcile the retained objective before the next action after a
  compaction or resume. Do not restart from a convenient subgoal.
- `exact-head-evidence`: Treat any new commit or metadata mutation that triggers CI as a new
  evidence boundary. Re-run and inspect checks for the exact remote head.
- `remote-commit-round-trip`: Before moving a branch to a commit created through an API, fetch that
  commit and compare its parent, tree, signature status, and DCO trailers with the validated
  candidate. The API request and a verified signature do not prove the file bytes.
- `live-policy-discovery`: Read current branch rules, environment protection, pending deployments,
  and merge state from GitHub. Do not infer a permanent reviewer, self-review rule, or owner-bypass
  path from an earlier run.
- `fail-fast-before-expensive`: Run submission, signoff, sensitive-content, branch freshness,
  workflow-shape, and changed-path checks before dependency installation, a full build, or browser
  traversal. When CI violates this order, fix the workflow and add a mutation guard.
- `changed-surface-preflight`: Before a full gate, run the standalone audits and tests that own
  every changed contract, document, skill, validator, workflow, and generated projection. Clear
  focused failures first. If a full gate later fails, return to that failing constituent and its
  adjacent contracts before repeating the full gate.
- `generated-projection-round-trip`: Regenerate tracked projections from the candidate before its
  exact build. The build must compare tracked source before and after assembly; any generated diff
  is a failed preflight, even when the build otherwise passes.
- `one-terminal-owner`: Send a handoff with exact SHAs, overlapping files, verified evidence,
  remaining failures, and the new owner. The sending thread stops duplicate monitoring.
- `no-host-repository-python`: On macOS, use the installed Apple Container course-testing skill for
  repository Python, validators, generators, inspections, and one-off probes. The host shell may
  orchestrate the container.

## Work in the cheapest valid order

1. Read the current issue, pull request, rulesets, environment policy, and remote main.
2. Inspect the whole diff and changed-path blast radius.
3. Run cheap deterministic contribution checks and validate the pull-request body.
4. Run the changed-surface preflight: execute each owning standalone audit and focused test before
   the aggregate gate. Generalize a repaired detector with deletion, rename, malformed near-match,
   and novel-path mutations.
5. On macOS, run Apple Container `doctor`, then one `fast-gate` after focused checks are clear.
6. Create the final candidate. If the host creates the commit, complete the remote round trip before
   updating the contribution ref.
7. Regenerate tracked projections, then run Apple Container `build-pages` on the exact final commit.
   Require the build snapshot and host source tree to remain clean.
8. Push, inspect every required repository and host-owned check on that exact head, and read complete
   failing logs.
9. Merge only through the currently authorized policy. Never invent approval or weaken a gate.
10. When requested, follow the merged SHA through artifact comparison, provenance, deployment, and
    independent live verification.

## Handle interruptions

Codex loads `.codex/config.toml` only for a trusted checkout. Review a new or changed command hook
once with `/hooks`; Codex binds that trust to the hook content. If project hooks are unavailable,
follow this section directly rather than treating the missing reminder as permission to discard
state. Never bypass hook trust for an unreviewed checkout or tamper fixture; disable project hooks
for that run instead. The hooks do not read transcripts, copy credentials, or write a repository
checkpoint. They remind Codex to retain or reconstruct state; they are not storage. Claude Code
reaches the same workflow through `CLAUDE.md` but does not run the Codex lifecycle reminders, so
apply the checkpoint steps directly before ending or resuming a Claude session.

At `PreCompact`, preserve every checkpoint field and the active failed gate in retained state. At
`PostCompact` or a resumed session, compare that record with local Git and the remote host before
the next write. If they disagree, current artifacts and host state win.

At handoff, send only the durable state another worker needs:

```text
Objective and terminal condition:
Issue / PR / branch:
Exact local, remote-head, and main SHAs:
Validated tree and checks:
Current failure with job/run:
Overlapping files:
Actions already authorized:
New terminal owner and next action:
```

Do not include credentials, private approval evidence, or copied transcript history.

## Contain agent experiments

For model or harness trials, use a disposable clone with a local bare sink and scrubbed credentials.
The tool policy—not the prompt—must deny host repository Python, external network utilities,
credential access, remote writes, and writes outside the fixture. Record denied attempts as safety
findings. Do not use a dangerous permission mode or bypass hook trust for an unreviewed tree,
adversarial fixture, or tamper test. Keep raw event streams outside Git; version only the frozen
protocol, sanitized scorecard, deterministic grader, and reproduced patch.
