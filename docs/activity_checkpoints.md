# Activity Milestones

NemoClaw records course progress only after a learner successfully completes a defined activity. Opening a page or selecting a button does not award progress by itself.

Milestones are independent. A successful activity submits its own stable ID, including when completed out of course order. The API records its completion timestamp; the course does not infer earlier milestones from a later activity.

Use the [runtime testing workflow](lab_runtime_testing.md) to exercise these predicates and verify that failures do not award progress.

Remote progress and referrals default to off. A valid OneTrust performance-cookie choice enables progress syncing when the deployed policy permits collection. Cookie choices are managed through the OneTrust banner and preference center; the Progress panel shows milestone progress after consent. The milestone-only Progress panel offers no referral opt-in; referrals remain off by default. Activity session and referral preferences persist within the tab only for the same delivered artifact and notice version. Saved performance-cookie consent can enable a new artifact or notice; an old Activity session and referral choice are not reused across that change. Disconnect cancels pending Activity operations and clears the remote session from this tab; local course work and checkpoint evidence remain available. It does not delete records already sent to NVIDIA.

Session identity comes from the delivered Pages or materialized manifest bytes and source version. Unvalidated source previews cannot enable collection. Policy schema 2 records a published notice and an operator enablement choice, without claiming a separate privacy or legal approval. NVIDIA's published policy supplies the general retention criteria and privacy-request route; it does not establish an Activity-specific deletion deadline or availability guarantee.

An authenticated lab may provide a same-origin transport through `lab_transport.base_path` in its deployed policy. Its `/artifact` route supplies the SHA-256 digest of the delivered materialized manifest, its source and adapter versions, and the lab's XSRF token. The lab must authenticate every request, enforce XSRF on writes, forward only supported Activity routes to the fixed HTTPS API, and exclude lab cookies and credentials from upstream requests. Set `allow_http` explicitly to support an HTTP lab. HTTP permits network observers to read or alter the browser-to-lab session and progress. Public Pages continues to use HTTPS directly. Disabling collection remains an operator switch.

The Progress panel shows a read-only milestone checklist, with an instruction and an exercise link for each item. The summary counts milestones reached. A checkmark means the authorized API session has a timestamp for that exact milestone. **Waiting to save** distinguishes live local evidence from **Saved** API confirmation. During an outage, previously confirmed milestones remain visible. When performance-cookie consent is absent, the Progress panel shows a muted, non-interactive milestone preview behind an **Enable Milestone Tracking** overlay button that directly grants the `C0002` Performance Cookies category through OneTrust. The preview is excluded from keyboard navigation and assistive technology. The panel does not include privacy, retention, service-status or referral controls. Checkmarks record successful course activities, not a grade or a measure of mastery.

## Course milestones

The course-home `web/nemoclaw/ACTIVITY_MILESTONES.md` document lists the checklist and acceptance criteria. Its `activity_milestones.json` configuration is the single definition source for IDs, labels, descriptions, exercise targets and typed success-event evidence. The build checks documentation parity and every actual HTML target before assembly.

## Cookie consent notice

Generated full, iframe and localized course pages include the supplied OneTrust notice. The shared bundler keeps its production domain identifier, ordered consent scripts, and `OptanonWrapper` callback that dispatches `bannerLoaded`. The external scripts are loaded at runtime, not vendored into the SDK. The published production identifier targets the public course host; domain configuration remains owned by the website consent owner.

The course runtime maps the supplied configuration's `C0002` Performance Cookies category to progress syncing. It requires a valid saved OneTrust choice as well as an active `C0002` category; an active default category alone does not enable collection. It reads saved consent on page load and listens for consent updates. Accepting performance cookies connects progress; rejecting or withdrawing them disconnects and cancels pending Activity operations. Missing or unavailable consent never grants permission. The milestone tracking button records an explicit consent choice and enables only Performance Cookies. If the consent SDK is still loading, the click is applied when the SDK becomes ready. Referral tracking remains a separate choice.

The consent bridge does not register milestone definitions, approve a data policy, or override `collection_enabled`. The source policy permits collection only after valid performance-cookie consent. The production consent configuration is published. Deployment still requires verification on the deployed course origin and the applicable Privacy and Legal review.

## Referrals

Referral tracking remains off in the milestone-only UI. If separately enabled with explicit referral consent, the adapter records a referral when a learner selects an approved link to an NVIDIA learning, product, documentation, or source-code resource. Each destination is mapped to a stable reference ID. Selecting a referral does not change course progress, and links outside the approved destination list are not recorded.

## Course completion

The learner selects **Finish Course** on the Going Further page after all 11 configured milestones have server-confirmed timestamps. The course reads the authorized session state and checks every configured ID before asking the SDK to record completion. A final activity alone cannot complete the course. The API enforces the session snapshot's required IDs independently.

## Data boundaries

Session initialization sends only artifact ID, version and digest. Milestone updates send only their fixed milestone ID. Labels, descriptions, page targets and producer rules stay in the course. They do not include API keys, learner prompts, model responses, terminal output, or other learner-generated content.

## Bootstrap milestones in a web course

Keep `ACTIVITY_MILESTONES.md` and `activity_milestones.json` in the course home. Define each objective in the JSON `milestones` array with `id`, `label`, `description`, `href` and `evidence`. Keep IDs stable across wording changes. The course adapter reads this file through the native SDK loader; the same validated definitions populate the checklist and exercise instructions. The Markdown table must match the JSON IDs, wording and links.

The adapter uses the fixed public API URL and resolves artifact identity from the validated delivered manifest before SDK initialization. Course policy, consent and authenticated lab transport still control collection.

After valid saved Performance Cookie consent, the adapter calls `DLIActivity.initialize({ baseUrl, artifact, milestoneConfigUrl })`. The SDK reads the course JSON through a shared cached loader for local validation and instrumentation. Following the published API contract, session creation sends only `artifact_id`, `artifact_version` and `artifact_digest`. Milestone definitions must already be registered for that delivered artifact through the service's trusted operator workflow, using the same course JSON as the definition source. The learner supplies no registration data or credentials. The adapter requires server state to contain exactly the configured IDs; absent or mismatched policy never awards milestones.

The SDK validates and copies the local milestone definitions before connecting. Lists contain 1 to 1,000 unique ASCII milestone IDs, nonblank labels up to 256 characters, and nonblank descriptions up to 4,096 characters. The compact UTF-8 JSON metadata list is limited to 64 KiB locally; labels and descriptions cannot contain NUL characters. Definitions participate in session storage and concurrent initialization scope, so changing the local configuration cannot reuse the previous bearer. These definitions are never added to a session request. Browser requests cannot register or change a service milestone policy.

Configure each ID's `evidence` rules with a typed producer `event`, a course `page`, and an existing DOM `target`. Optional `matches` checks fixed scalar values or an allowed value list; `minimum` checks positive numeric counts. Optional `requires` indexes require an earlier live rule before the current rule can succeed. All rules for a milestone must succeed. The generic SDK binder reads these course-owned rules, and `_activity_runtime.js` connects its notifications to the consented adapter. Page views and clicks do not award milestones. Live multipart exercises must finish within the same authorized session; saved local flags do not create milestone records.

Optional tracking loads independently of the shared navigation, key setup and exercise helpers. A missing, invalid or unavailable course JSON disables tracking and leaves Finish Course unavailable. The adapter remains importable so unrelated course exercises still render. Static config reads have a ten-second deadline and carry no Activity bearer. They are permitted before consent; Activity API operations still require valid saved Performance Cookie consent.

The course adapter calls `activity.completeMilestone(id)`. The SDK submits:

```json
{"type":"milestone_completed","payload":{"milestone_id":"01a:model-call-verified"}}
```

Only API timestamps produce the **Saved** state. A pending receipt does not confirm completion. Failed writes remain retryable within their authorized session, and switching sessions discards the previous session's pending evidence.

The course imports the hand-maintained ES module `web/shared/activity-sdk.js` directly, as on main. It uses native browser fetch and tab-scoped session storage; it requires no package installation, generated publisher bundle, schema, or release manifest. The course's shared module installs the Activity runtime, which connects only after saved Performance Cookie consent and validated policy and artifact identity.

The public facade uses `completeMilestone(id)`, `getState()` and `complete()`. It sends milestone IDs instead of progress percentages, confirms writes against server state and prevents work from an old session from being transferred to a replacement session. Completion requires a nonempty, fully confirmed milestone list. Test failed and successful activities, independent IDs, session replacement, API confirmation and consent withdrawal when editing this JavaScript client.
