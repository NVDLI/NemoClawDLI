# Activity Checkpoints

NemoClaw records course progress only after a learner successfully completes a defined activity. Opening a page or selecting a button does not award progress by itself.

Progress is cumulative and advances in course order. If a learner completes a later checkpoint before an earlier one, the course keeps the successful evidence in the current browser session and advances after the missing earlier checkpoint is completed.

Use the [runtime testing workflow](lab_runtime_testing.md) to exercise these predicates and verify that failures do not award progress.

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
