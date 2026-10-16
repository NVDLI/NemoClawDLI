# Activity Milestones

NemoClaw records course progress only after a learner successfully completes a defined activity. Opening a page or selecting a button does not award progress by itself.

Milestones are independent. A successful activity submits its own stable ID, including when completed out of course order. The API records its completion timestamp; the course does not infer earlier milestones from a later activity.

Use the [runtime testing workflow](lab_runtime_testing.md) to exercise these predicates and verify that failures do not award progress.

Remote progress and referrals default to off. A valid saved OneTrust Performance Cookie choice enables both when the deployed policy permits collection. Global Privacy Control blocks referrals. Cookie choices are managed through the OneTrust banner and preference center; the Progress panel shows milestone progress after consent. No separate referral toggle is required.

Activity session and referral preferences persist within the tab only for the same delivered artifact and notice version. Saved performance-cookie consent can enable a new artifact or notice; an old Activity session and referral choice are not reused across that change. Disconnect cancels pending Activity operations and clears the remote session from this tab; local course work and checkpoint evidence remain available. It does not delete records already sent to NVIDIA.

Session identity comes from the delivered Pages or materialized manifest bytes and source version. Unvalidated source previews cannot enable collection. Policy schema 2 records a published notice and an operator enablement choice, without claiming a separate privacy or legal approval. NVIDIA's published policy supplies the general retention criteria and privacy-request route; it does not establish an Activity-specific deletion deadline or availability guarantee.

An authenticated lab may provide a same-origin transport through `lab_transport.base_path` in its deployed policy. Its `/artifact` route supplies the SHA-256 digest of the delivered materialized manifest, its source and adapter versions, and the lab's XSRF token. The lab must authenticate every request, enforce XSRF on writes, forward only supported Activity routes to the fixed HTTPS API, and exclude lab cookies and credentials from upstream requests. Set `allow_http` explicitly to support an HTTP lab. HTTP permits network observers to read or alter the browser-to-lab session and progress. Public Pages continues to use HTTPS directly. Disabling collection remains an operator switch.

The Progress panel shows a read-only milestone checklist, with an instruction and an exercise link for each item. The summary counts milestones reached. A checkmark means the authorized API session has a timestamp for that exact milestone. **Waiting to save** distinguishes live local evidence from **Saved** API confirmation. During an outage, previously confirmed milestones remain visible, with a failure message and a **Reconnect** action. When performance-cookie consent is absent, the Progress panel shows a muted, non-interactive milestone preview behind an **Enable Milestone Tracking** overlay button that directly grants the `C0002` Performance Cookies category through OneTrust. Without an available CMP, that button is disabled and collection stays off. The preview is excluded from keyboard navigation and assistive technology. The panel does not include privacy, retention or referral controls. Checkmarks record successful course activities, not a grade or a measure of mastery.

## Canonical milestone configuration

This document is the definition source for IDs, labels, descriptions, exercise targets and typed success-event evidence. Edit the single JSON block below, then run `python3 scripts/validation/activity_milestone_contract.py --write` to regenerate `web/activity/activity_milestones.json`. The build audits the projection and actual HTML targets before assembly. Targets in the configuration resolve against `web/nemoclaw/`.

```json
{
  "schemaVersion": 1,
  "milestones": [
    {
      "id": "01a:model-call-verified",
      "label": "Make your first model call",
      "description": "Verify your API key, then run the one-call exercise and receive a response.",
      "href": "01a-loop.html#cell-onecall",
      "evidence": [
        {
          "event": "nemoclaw:api-key-verified",
          "page": "01a-loop.html",
          "target": "cell-onecall"
        },
        {
          "event": "nemoclaw:run-succeeded",
          "page": "01a-loop.html",
          "target": "cell-onecall",
          "matches": {
            "cellId": "cell-onecall",
            "hasContent": true
          },
          "requires": [
            0
          ]
        }
      ]
    },
    {
      "id": "01b:react-loop-complete",
      "label": "Complete a ReAct loop",
      "description": "Run the ReAct activity with at least one successful step and a final answer.",
      "href": "01b-react.html#react-artifact",
      "evidence": [
        {
          "event": "nemoclaw:chat-completed",
          "page": "01b-react.html",
          "target": "react-artifact",
          "matches": {
            "containerId": "react-artifact",
            "hasAnswer": true
          },
          "minimum": {
            "successCount": 1
          }
        }
      ]
    },
    {
      "id": "01c:tool-roundtrip-complete",
      "label": "Complete a tool round trip",
      "description": "Run the tool-calling activity with a successful step and a final answer.",
      "href": "01c-tools.html#tools-artifact",
      "evidence": [
        {
          "event": "nemoclaw:chat-completed",
          "page": "01c-tools.html",
          "target": "tools-artifact",
          "matches": {
            "containerId": "tools-artifact",
            "hasAnswer": true
          },
          "minimum": {
            "successCount": 1
          }
        }
      ]
    },
    {
      "id": "02a:routed-workflow-complete",
      "label": "Run a routed workflow",
      "description": "Complete the routing activity with a successful step and a final answer.",
      "href": "02a-routing.html#router-artifact",
      "evidence": [
        {
          "event": "nemoclaw:chat-completed",
          "page": "02a-routing.html",
          "target": "router-artifact",
          "matches": {
            "containerId": "router-artifact",
            "hasAnswer": true
          },
          "minimum": {
            "successCount": 1
          }
        }
      ]
    },
    {
      "id": "02b:grounded-answer-complete",
      "label": "Complete the retrieval activity",
      "description": "Run the RAG activity with a successful step and a final answer.",
      "href": "02b-rag.html#rag-artifact",
      "evidence": [
        {
          "event": "nemoclaw:chat-completed",
          "page": "02b-rag.html",
          "target": "rag-artifact",
          "matches": {
            "containerId": "rag-artifact",
            "hasAnswer": true
          },
          "minimum": {
            "successCount": 1
          }
        }
      ]
    },
    {
      "id": "02c:deep-research-complete",
      "label": "Complete a research run",
      "description": "Finish the deep-research activity with a successful step and a final answer.",
      "href": "02c-deep.html#deep-artifact",
      "evidence": [
        {
          "event": "nemoclaw:chat-completed",
          "page": "02c-deep.html",
          "target": "deep-artifact",
          "matches": {
            "containerId": "deep-artifact",
            "hasAnswer": true
          },
          "minimum": {
            "successCount": 1
          }
        }
      ]
    },
    {
      "id": "03a:nemoclaw-connected",
      "label": "Connect to NemoClaw",
      "description": "Pass the connection checks for metadata, gateway, terminal, and health.",
      "href": "03a-kickstart.html#probe-claw",
      "evidence": [
        {
          "event": "nemoclaw:connection-audit-passed",
          "page": "03a-kickstart.html",
          "target": "probe-claw"
        }
      ]
    },
    {
      "id": "03b:workspace-inspected",
      "label": "Inspect your workspace",
      "description": "Successfully run both the introspection and workspace terminal exercises.",
      "href": "03b-openclaw.html#cell-introspect",
      "evidence": [
        {
          "event": "nemoclaw:run-succeeded",
          "page": "03b-openclaw.html",
          "target": "cell-introspect",
          "matches": {
            "cellId": "cell-introspect"
          }
        },
        {
          "event": "nemoclaw:run-succeeded",
          "page": "03b-openclaw.html",
          "target": "cell-workspace-term",
          "matches": {
            "cellId": "cell-workspace-term"
          }
        }
      ]
    },
    {
      "id": "03c:scheduled-run-complete",
      "label": "Run and clean up a scheduled job",
      "description": "Observe a successful scheduled run, then confirm the job was removed.",
      "href": "03c-always-on.html#probe-cron",
      "evidence": [
        {
          "event": "nemoclaw:canvas-node-succeeded",
          "page": "03c-always-on.html",
          "target": "probe-cron",
          "matches": {
            "canvasId": "probe-cron",
            "nodeId": [
              "cr-run",
              "cr-rm"
            ],
            "runObserved": true
          }
        },
        {
          "event": "nemoclaw:canvas-node-succeeded",
          "page": "03c-always-on.html",
          "target": "probe-cron",
          "matches": {
            "canvasId": "probe-cron",
            "nodeId": [
              "cr-run",
              "cr-rm"
            ],
            "cleanupSucceeded": true
          }
        }
      ]
    },
    {
      "id": "04a:policy-boundary-verified",
      "label": "Check the policy boundary",
      "description": "Read the live agent policy, then confirm the policy comparison agrees.",
      "href": "04a-safety.html#cell-live-policy",
      "evidence": [
        {
          "event": "nemoclaw:run-succeeded",
          "page": "04a-safety.html",
          "target": "cell-live-policy",
          "matches": {
            "cellId": "cell-live-policy",
            "hasAgent": true
          }
        },
        {
          "event": "nemoclaw:canvas-node-succeeded",
          "page": "04a-safety.html",
          "target": "cell-predict-confirm",
          "matches": {
            "canvasId": "cell-predict-confirm",
            "nodeId": "compare",
            "policyAgreed": true
          }
        }
      ]
    },
    {
      "id": "04b:live-agent-operated",
      "label": "Operate a live agent",
      "description": "Send a non-command message to the live agent and receive a successful response.",
      "href": "04b-modern-clis.html#agent-chat",
      "evidence": [
        {
          "event": "nemoclaw:live-agent-operated",
          "page": "04b-modern-clis.html",
          "target": "agent-chat"
        }
      ]
    }
  ]
}
```

## Cookie consent notice

Generated full, iframe and localized course pages include the supplied OneTrust notice. The shared bundler keeps its production domain identifier, ordered consent scripts, and `OptanonWrapper` callback that dispatches `bannerLoaded`. The external scripts are loaded at runtime, not vendored into the SDK. The published production identifier targets the public course host; domain configuration remains owned by the website consent owner.

The course runtime maps the supplied configuration's `C0002` Performance Cookies category to both progress syncing and referral tracking. It requires a valid saved OneTrust choice as well as an active `C0002` category; an active default category alone does not enable collection. It reads saved consent on page load and listens for consent updates. Accepting performance cookies connects progress and enables referral tracking unless Global Privacy Control is active. Rejecting or withdrawing them disables both and cancels pending Activity operations. Missing or unavailable consent never grants permission. The milestone tracking button records an explicit consent choice and enables only Performance Cookies. If the consent SDK is still loading, the click is applied when the SDK becomes ready. No separate referral toggle is required.

The consent bridge does not register milestone definitions, approve a data policy, or override `collection_enabled`. The source policy permits collection only after valid performance-cookie consent. The production consent configuration is published. Deployment still requires verification on the deployed course origin and the applicable Privacy and Legal review.

## Referrals

Referral tracking stays off until the learner has valid saved Performance Cookie consent and an authorized Activity session. The same consent enables progress syncing and referral tracking without a separate toggle. Global Privacy Control blocks referral tracking even with Performance Cookie consent. The adapter records a referral when a learner selects an approved link to an NVIDIA learning, product, documentation, or source-code resource. Each destination is mapped to a stable reference ID. Selecting a referral does not change course progress, and links outside the approved destination list are not recorded.

## Course completion

The learner selects **Finish Course** on the Going Further page after all 11 configured milestones have server-confirmed timestamps. The course reads the authorized session state and checks every configured ID before asking the SDK to record completion. A final activity alone cannot complete the course. The API enforces the session snapshot's required IDs independently.

## Data boundaries

Session initialization sends only artifact ID, version and digest. Milestone updates send only their fixed milestone ID. Labels, descriptions, page targets and producer rules stay in the course. They do not include API keys, learner prompts, model responses, terminal output, or other learner-generated content.

## Bootstrap milestones in a web course

Keep this document in `docs/` and its generated configuration in `web/activity/`. Define each objective in the JSON block's `milestones` array with `id`, `label`, `description`, `href` and `evidence`. Keep IDs stable across wording changes. The course adapter reads this file through the native SDK loader; the same validated definitions populate the checklist and exercise instructions. Do not edit the generated runtime JSON directly.

The adapter uses the fixed public API URL and resolves artifact identity from the validated delivered manifest before SDK initialization. Course policy, consent and authenticated lab transport still control collection.

After valid saved Performance Cookie consent, the adapter calls `DLIActivity.initialize({ baseUrl, artifact, milestoneConfigUrl })`. The SDK reads the course JSON through a shared cached loader for local validation and instrumentation. Following the published API contract, session creation sends only `artifact_id`, `artifact_version` and `artifact_digest`. Milestone definitions must already be registered for that delivered artifact through the service's trusted operator workflow, using the runtime JSON generated from this document. The learner supplies no registration data or credentials. The adapter requires server state to contain exactly the configured IDs; absent or mismatched policy never awards milestones.

The SDK validates and copies the local milestone definitions before connecting. Lists contain 1 to 1,000 unique ASCII milestone IDs, nonblank labels up to 256 characters, and nonblank descriptions up to 4,096 characters. The compact UTF-8 JSON metadata list is limited to 64 KiB locally; labels and descriptions cannot contain NUL characters. Definitions participate in session storage and concurrent initialization scope, so changing the local configuration cannot reuse the previous bearer. These definitions are never added to a session request. Browser requests cannot register or change a service milestone policy.

Configure each ID's `evidence` rules with a typed producer `event`, a course `page`, and an existing DOM `target`. Optional `matches` checks fixed scalar values or an allowed value list; `minimum` checks positive numeric counts. Optional `requires` indexes require an earlier live rule before the current rule can succeed. All rules for a milestone must succeed. The generic SDK binder reads these course-owned rules, and `_activity_runtime.js` connects its notifications to the consented adapter. Page views and clicks do not award milestones. Live multipart exercises must finish within the same authorized session; saved local flags do not create milestone records.

Optional tracking loads independently of the shared navigation, key setup and exercise helpers. A missing, invalid or unavailable course JSON disables tracking and leaves Finish Course unavailable. The adapter remains importable so unrelated course exercises still render. Static config reads have a ten-second deadline and carry no Activity bearer. They are permitted before consent; Activity API operations still require valid saved Performance Cookie consent.

The course adapter calls `activity.completeMilestone(id)`. The SDK submits:

`{"type":"milestone_completed","payload":{"milestone_id":"01a:model-call-verified"}}`

Only API timestamps produce the **Saved** state. A pending receipt does not confirm completion. Failed writes remain retryable within their authorized session, and switching sessions discards the previous session's pending evidence.

The course imports the hand-maintained ES module `web/activity/activity-sdk.js` directly, as on main. It uses native browser fetch and tab-scoped session storage; it requires no package installation, generated publisher bundle, schema, or release manifest. The course's shared module installs the Activity runtime, which connects only after saved Performance Cookie consent and validated policy and artifact identity.

The public facade uses `completeMilestone(id)`, `getState()` and `complete()`. It sends milestone IDs instead of progress percentages, confirms writes against server state and prevents work from an old session from being transferred to a replacement session. Completion requires a nonempty, fully confirmed milestone list. Test failed and successful activities, independent IDs, session replacement, API confirmation and consent withdrawal when editing this JavaScript client.
