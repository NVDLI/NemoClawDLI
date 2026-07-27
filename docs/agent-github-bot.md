# GitHub identity and public agent status

The devbox worker may use a dedicated bot account as its GitHub actor. The human contributor remains
the commit author and signs the Developer Certificate of Origin trailer. The bot authenticates the
feature-branch push and publishes bounded progress; it does not make a legal attestation. The
ordinary issue, validation, and handoff rules remain in the [agent process](agent_process.md).

## Create the account and token

Create one machine user with a recognizable name such as `nvdli-course-agent`. Add it to this
repository with the Write role. Do not grant the account administrator or maintainer authority,
organization ownership, ruleset bypass, protected-environment access, or release authority.

Create a fine-grained personal access token owned by that account. Select one repository,
`NVDLI/NemoClawDLI`, and grant:

| Permission | Level | Purpose |
| --- | --- | --- |
| Checks | Read and write | Maintain one lifecycle Check per commit |
| Contents | Read and write | Push feature branches |
| Issues | Read and write | Maintain one issue or pull-request status comment |

Do not grant Actions, Administration, Deployments, Environments, Pull requests, Secrets, Workflows,
or organization permissions. Set a short expiration and record its rotation owner outside the
repository. GitHub's [fine-grained token guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
describes repository selection and expiration.

Keep the human name and NVIDIA email in the commit author and matching `Signed-off-by` trailer.
Register the human signing key on the human account. A signed commit is still required before the
bot may publish it.

## Configure the devbox

Store the token outside the checkout in a regular file with mode `0600`. Set only:

```text
AGENT_GITHUB_LOGIN=nvdli-course-agent
AGENT_GITHUB_TOKEN_FILE=$HOME/.config/nemoclaw-agent/github-bot.token
AGENT_GITHUB_REPOSITORY=NVDLI/NemoClawDLI
```

Do not put the token value in an environment variable, command, Git configuration, dashboard,
event receipt, issue, pull request, or CI artifact. The bridge reads the token file for one
operation and never persists another copy.

Verify the identity and repository role before enabling publication:

```bash
python3 scripts/ci/github_agent_bridge.py verify
```

The command fails when the token belongs to another account, the repository does not match, the
token is not fine-grained, the file is group-readable, or the account has administrator or
maintainer authority. GitHub does not expose a reliable fine-grained permission manifest to the
client, so the operator must also compare the token settings with the table above.

After the controller creates a clean, linear, cryptographically signed commit with a matching human
`Signed-off-by` trailer, publish the feature branch as the bot actor:

```bash
python3 scripts/ci/github_agent_bridge.py push \
  --worktree "$COURSE_WORKTREE" \
  --branch "$COURSE_BRANCH"
```

The command never rewrites a remote ref. It refuses `main`, `master`, release refs, tags, a dirty
worktree, a branch-name mismatch, an unsigned commit, a merge commit, or a mismatched DCO trailer.
The token exists only in the child Git process environment. Git tracing is removed, the credential
is not written to Git configuration, and the bridge checks GitHub's signature result after the push.

## Broadcast lifecycle state

The controller writes one event conforming to
[`scripts/ci/agent-transparency.schema.json`](../scripts/ci/agent-transparency.schema.json), then runs:

```bash
python3 scripts/ci/github_agent_bridge.py publish \
  --event "$AGENT_STATE/public-event.json" \
  --state "$AGENT_STATE/github-state.json"
```

Before a commit exists, the bridge updates one issue comment. Once an exact head exists, it also
maintains one `Agent contribution / lifecycle` Check for that head. When a pull request exists, the
status moves to one pull-request comment. Repeated updates edit those records.

Publish phase changes, terminal changes, and at most one heartbeat every five minutes. A public event
contains only the issue or pull request, branch, exact head, attempt, phase, short status, next action,
blocker, and GitHub evidence links. Keep these details in the local dashboard only:

- prompts, model messages, tool arguments, tool output, and private reasoning;
- credentials, cookies, tokens, environment values, and internal hosts;
- model cost, private reviewer records, and private tracker references.

The local receipt remains the complete operational record. GitHub provides a durable public summary,
not a second raw transcript.

## Failure and recovery

- A rejected event is not published. Fix the source event; do not weaken the filter.
- An event sequence must increase. This prevents an old retry from replacing newer state.
- A new commit gets a new Check. Evidence from an earlier head never moves forward.
- If local state is lost, the bridge discovers the existing marked comment before creating one.
- If GitHub is unavailable, preserve the event locally and retry with the same sequence.
- Rotate the token before expiration and immediately after suspected exposure. Delete the old token
  only after the worker verifies the replacement. Removing repository access revokes the bot.

The controller may retry status publication. It must not use this bridge to merge, approve, deploy,
edit workflows, or change repository protections.
