# Activity Checkpoints

NemoClaw records course progress only after a learner successfully completes a defined activity. Opening a page or selecting a button does not award progress by itself.

Milestones are independent. A successful activity submits its own stable ID, including when completed out of course order. The API records its completion timestamp; the course does not infer earlier milestones from a later activity.

Use the [runtime testing workflow](lab_runtime_testing.md) to exercise these predicates and verify that failures do not award progress.

Remote progress and referrals default to off. A valid OneTrust performance-cookie choice enables progress syncing when the deployed policy permits collection. Cookie choices are managed through the OneTrust banner and preference center; the Progress panel shows milestone progress after consent. The milestone-only Progress panel offers no referral opt-in; referrals remain off by default. Activity session and referral preferences persist within the tab only for the same delivered artifact and notice version. Saved performance-cookie consent can enable a new artifact or notice; an old Activity session and referral choice are not reused across that change. Disconnect cancels pending Activity operations and clears the remote session from this tab; local course work and checkpoint evidence remain available. It does not delete records already sent to NVIDIA.

Session identity comes from the delivered Pages or materialized manifest bytes and source version. Unvalidated source previews cannot enable collection. Policy schema 2 records a published notice and an operator enablement choice, without claiming a separate privacy or legal approval. NVIDIA's published policy supplies the general retention criteria and privacy-request route; it does not establish an Activity-specific deletion deadline or availability guarantee.

An authenticated lab may provide a same-origin transport through `lab_transport.base_path` in its deployed policy. Its `/artifact` route supplies the SHA-256 digest of the delivered materialized manifest, its source and adapter versions, and the lab's XSRF token. The lab must authenticate every request, enforce XSRF on writes, forward only supported Activity routes to the fixed HTTPS API, and exclude lab cookies and credentials from upstream requests. Set `allow_http` explicitly to support an HTTP lab. HTTP permits network observers to read or alter the browser-to-lab session and progress. Public Pages continues to use HTTPS directly. Disabling collection remains an operator switch.

The Progress panel shows a read-only milestone checklist, with an instruction and an exercise link for each item. The summary counts milestones reached. A checkmark means the authorized API session has a timestamp for that exact milestone. **Waiting to save** distinguishes live local evidence from **Saved** API confirmation. During an outage, previously confirmed milestones remain visible. When performance-cookie consent is absent, the Progress panel shows a muted, non-interactive milestone preview behind an **Enable Milestone Tracking** overlay button that directly grants the `C0002` Performance Cookies category through OneTrust. The preview is excluded from keyboard navigation and assistive technology. The panel does not include privacy, retention, service-status or referral controls. Checkmarks record successful course activities, not a grade or a measure of mastery.

## Progress checkpoints

| Section | Checkpoint | Learner action | Acceptance criteria |
| --- | --- | --- | --- |
| 1a | Model call verified | Configure an NVIDIA API key and run the one-call model exercise. | The API key passes verification, the `cell-onecall` exercise finishes successfully, and the model returns non-empty content. |
| 1b | ReAct loop complete | Complete the ReAct loop activity. | The `react-artifact` activity finishes with at least one successful step and produces an answer. |
| 1c | Tool round trip complete | Complete the tool-calling activity. | The `tools-artifact` activity finishes with at least one successful step and produces an answer. |
| 2a | Routed workflow complete | Complete the routing activity. | The `router-artifact` activity finishes with at least one successful step and produces an answer. |
| 2b | Grounded answer complete | Complete the retrieval-augmented generation activity. | The `rag-artifact` activity finishes with at least one successful step and produces an answer. |
| 2c | Deep research complete | Complete the deep-research activity. | The `deep-artifact` activity finishes with at least one successful step and produces an answer. |
| 3a | NemoClaw connected | Configure and test a NemoClaw connection. | The connection audit successfully validates the required metadata, gateway, terminal, and health routes. |
| 3b | Workspace inspected | Inspect the connected workspace and terminal. | Both the introspection exercise and the workspace terminal exercise finish successfully. |
| 3c | Scheduled run complete | Create, observe, and clean up a scheduled run. | The scheduled job reports a successful run and the cleanup exercise confirms that it was removed. |
| 4a | Policy boundary verified | Inspect the live policy and complete the policy comparison. | The live-policy exercise returns an agent, and the comparison exercise confirms agreement with the expected policy boundary. |
| 4b | Live agent operated | Send a message to the live agent. | A non-command message completes successfully and produces either a streamed response or a non-empty response. |

## Cookie consent notice

Generated full, iframe and localized course pages include the supplied OneTrust notice. The shared bundler keeps its test domain identifier, ordered consent scripts, and `OptanonWrapper` callback that dispatches `bannerLoaded`. The external scripts are loaded at runtime, not vendored into the SDK. A production identifier and domain configuration must come from the website consent owner before production use.

The course runtime maps the supplied configuration's `C0002` Performance Cookies category to progress syncing. It requires a valid saved OneTrust choice as well as an active `C0002` category; an active default category alone does not enable collection. It reads saved consent on page load and listens for consent updates. Accepting performance cookies connects progress; rejecting or withdrawing them disconnects and cancels pending Activity operations. Missing or unavailable consent never grants permission. The milestone tracking button records an explicit consent choice and enables only Performance Cookies. If the consent SDK is still loading, the click is applied when the SDK becomes ready. Referral tracking remains a separate choice.

The consent bridge does not register milestone definitions, approve a data policy, or override `collection_enabled`. The source policy permits collection only after valid performance-cookie consent. Production deployment still requires the production consent configuration and the applicable Privacy and Legal review.

## Referrals

The course also records a referral when a learner selects an approved link to an NVIDIA learning, product, documentation, or source-code resource. Each destination is mapped to a stable reference ID. Selecting a referral does not change course progress, and links outside the approved destination list are not recorded.

## Course completion

The learner selects **Finish Course** on the Going Further page after all 11 configured milestones have server-confirmed timestamps. The course reads the authorized session state and checks every configured ID before asking the SDK to record completion. A final activity alone cannot complete the course. The API enforces its registered required IDs independently.

## Data boundaries

Checkpoint events contain fixed activity identifiers and success evidence only. They do not include API keys, learner prompts, model responses, terminal output, or other learner-generated content.

## Bootstrap milestones in a web course

Define objectives in `ACTIVITY_MILESTONES` in `web/nemoclaw/scripts/_activity.js`. Keep IDs stable across wording changes. Each course-owned milestone contains a label, description and exercise link. The same definitions populate the checklist and the instructions beside each exercise.

The adapter uses the fixed public API URL and resolves artifact identity from the validated delivered manifest before SDK initialization. Course policy, consent and authenticated lab transport still control collection.

Before enabling collection for a new course build, an operator must register these milestone definitions against the resolved publication and delivered artifact identity in the Activity API. The adapter requires the server to return exactly the configured IDs.

Wire each ID to a verified success event in `_activity_runtime.js`. Keep acceptance predicates in the course, not in the SDK. Live multipart exercises must finish within the same authorized session; saved local flags do not create milestone records.

The course adapter calls `activity.completeMilestone(id)`. The SDK submits:

```json
{"type":"milestone_completed","payload":{"milestone_id":"01a:model-call-verified"}}
```

Only API timestamps produce the **Saved** state. A pending receipt does not confirm completion. Failed writes remain retryable within their authorized session, and switching sessions discards the previous session's pending evidence.

The course imports the hand-maintained ES module `web/shared/activity-sdk.js` directly, as on main. It uses native browser fetch and tab-scoped session storage; it requires no package installation, generated publisher bundle, schema, or release manifest. The course's shared module installs the Activity runtime, which connects only after saved Performance Cookie consent and validated policy and artifact identity.

The public facade uses `completeMilestone(id)`, `getState()` and `complete()`. It sends milestone IDs instead of progress percentages, confirms writes against server state and prevents work from an old session from being transferred to a replacement session. Completion requires a nonempty, fully confirmed milestone list. Test failed and successful activities, independent IDs, session replacement, API confirmation and consent withdrawal when editing this JavaScript client.
