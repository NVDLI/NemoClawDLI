# Activity Checkpoints

NemoClaw records course progress only after a learner successfully completes a defined activity. Opening a page or selecting a button does not award progress by itself.

Progress is cumulative and advances in course order. If a learner completes a later checkpoint before an earlier one, the course keeps the successful evidence in the current browser session and advances after the missing earlier checkpoint is completed.

Use the [runtime testing workflow](lab_runtime_testing.md) to exercise these predicates and verify that failures do not award progress.

Remote progress and referrals default to off. The Activity panel explains the proposed data use and permits connection only when the deployed service policy is approved. Referral tracking requires a separate choice. Choices persist within the tab only for the same delivered artifact and notice version; a changed build or notice requires enablement again. Disconnect cancels pending Activity operations and clears the remote session from this tab; local course work and checkpoint evidence remain available.

Session identity comes from the delivered Pages or materialized manifest bytes and source version. Unvalidated source previews cannot enable collection. Service retention and controller details remain unconfirmed in the checked-in policy, so production collection stays disabled.

The Activity panel shows a read-only progress bar. With remote progress enabled, **Saved progress** is the percentage returned by the Activity API. A successful write is followed by a state read; pending local checkpoints are shown separately until confirmed. During an outage, **Last confirmed progress** retains the last successful reading. **Refresh saved progress** retries the read and synchronizes local checkpoints. With remote progress off, the bar shows **Local verified progress** for this tab. These percentages record completed course activities, not a grade or a measure of mastery.

## Progress checkpoints

| Section | Checkpoint | Progress | Learner action | Acceptance criteria |
| --- | --- | ---: | --- | --- |
| 1a | Model call verified | 10% | Configure an NVIDIA API key and run the one-call model exercise. | The API key passes verification, the `cell-onecall` exercise finishes successfully, and the model returns non-empty content. |
| 1b | ReAct loop complete | 15% | Complete the ReAct loop activity. | The `react-artifact` activity finishes with at least one successful step and produces an answer. |
| 1c | Tool round trip complete | 25% | Complete the tool-calling activity. | The `tools-artifact` activity finishes with at least one successful step and produces an answer. |
| 2a | Routed workflow complete | 35% | Complete the routing activity. | The `router-artifact` activity finishes with at least one successful step and produces an answer. |
| 2b | Grounded answer complete | 45% | Complete the retrieval-augmented generation activity. | The `rag-artifact` activity finishes with at least one successful step and produces an answer. |
| 2c | Deep research complete | 50% | Complete the deep-research activity. | The `deep-artifact` activity finishes with at least one successful step and produces an answer. |
| 3a | NemoClaw connected | 60% | Configure and test a NemoClaw connection. | The connection audit successfully validates the required metadata, gateway, terminal, and health routes. |
| 3b | Workspace inspected | 70% | Inspect the connected workspace and terminal. | Both the introspection exercise and the workspace terminal exercise finish successfully. |
| 3c | Scheduled run complete | 80% | Create, observe, and clean up a scheduled run. | The scheduled job reports a successful run and the cleanup exercise confirms that it was removed. |
| 4a | Policy boundary verified | 90% | Inspect the live policy and complete the policy comparison. | The live-policy exercise returns an agent, and the comparison exercise confirms agreement with the expected policy boundary. |
| 4b | Live agent operated | 100% | Send a message to the live agent. | A non-command message completes successfully and produces either a streamed response or a non-empty response. |

## Referrals

The course also records a referral when a learner selects an approved link to an NVIDIA learning, product, documentation, or source-code resource. Each destination is mapped to a stable reference ID. Selecting a referral does not change course progress, and links outside the approved destination list are not recorded.

## Course completion

Reaching the final checkpoint sets progress to 100%, but it does not automatically mark the course complete. The learner finishes the course by selecting **Finish Course** on the Going Further page. Before recording completion, the course reads the current session state and confirms that the API reports exactly 100% progress.

## Data boundaries

Checkpoint events contain fixed activity identifiers and success evidence only. They do not include API keys, learner prompts, model responses, terminal output, or other learner-generated content.
