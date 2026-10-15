# Activity Milestones

`activity_milestones.json` is the course-owned definition source. The shared JavaScript SDK reads it during initialization for local instrumentation and binds each configured success event to its page and target element. The checklist uses those same definitions. Clicking or viewing a page never awards a milestone.

| Milestone ID | Milestone and exercise | Acceptance criteria |
| --- | --- | --- |
| `01a:model-call-verified` | [Make your first model call](01a-loop.html#cell-onecall) | Verify your API key, then run the one-call exercise and receive a response. |
| `01b:react-loop-complete` | [Complete a ReAct loop](01b-react.html#react-artifact) | Run the ReAct activity with at least one successful step and a final answer. |
| `01c:tool-roundtrip-complete` | [Complete a tool round trip](01c-tools.html#tools-artifact) | Run the tool-calling activity with a successful step and a final answer. |
| `02a:routed-workflow-complete` | [Run a routed workflow](02a-routing.html#router-artifact) | Complete the routing activity with a successful step and a final answer. |
| `02b:grounded-answer-complete` | [Complete the retrieval activity](02b-rag.html#rag-artifact) | Run the RAG activity with a successful step and a final answer. |
| `02c:deep-research-complete` | [Complete a research run](02c-deep.html#deep-artifact) | Finish the deep-research activity with a successful step and a final answer. |
| `03a:nemoclaw-connected` | [Connect to NemoClaw](03a-kickstart.html#probe-claw) | Pass the connection checks for metadata, gateway, terminal, and health. |
| `03b:workspace-inspected` | [Inspect your workspace](03b-openclaw.html#cell-introspect) | Successfully run both the introspection and workspace terminal exercises. |
| `03c:scheduled-run-complete` | [Run and clean up a scheduled job](03c-always-on.html#probe-cron) | Observe a successful scheduled run, then confirm the job was removed. |
| `04a:policy-boundary-verified` | [Check the policy boundary](04a-safety.html#cell-live-policy) | Read the live agent policy, then confirm the policy comparison agrees. |
| `04b:live-agent-operated` | [Operate a live agent](04b-modern-clis.html#agent-chat) | Send a non-command message to the live agent and receive a successful response. |

Local milestone metadata is bounded to 64 KiB of compact UTF-8 JSON across the list. Labels and descriptions exclude NUL characters. Session creation sends only artifact ID, version and digest; a completed milestone update sends its ID. The service's trusted registration workflow consumes the same course definitions separately.

All evidence rules for a milestone must succeed. Fixed event detail matches and minimum counts describe each producer's success evidence; `requires` indexes require earlier live evidence. Multipart evidence stays within one authorized session. Fresh work collected before consent can bind once, while stored hints and a replaced session cannot supply a partner. No keys, prompts, model responses or terminal output enter Activity payloads. These browser interactions do not establish certification or entitlement evidence.

A valid saved OneTrust `C0002` Performance Cookies choice and an enabled deployed collection policy precede every Activity API request. Withdrawal aborts pending operations. See [the Activity bootstrap guide](../../docs/activity_checkpoints.md) for artifact identity, transport, completion and consent boundaries.
