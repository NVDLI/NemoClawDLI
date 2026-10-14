// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Course-owned milestone definitions; the shared client has no course configuration dependency.
export const ACTIVITY_MILESTONES = Object.freeze(Object.fromEntries(
  [
  [
    "01a:model-call-verified",
    {
      "label": "Make your first model call",
      "description": "Verify your API key, then run the one-call exercise and receive a response.",
      "href": "01a-loop.html#cell-onecall"
    }
  ],
  [
    "01b:react-loop-complete",
    {
      "label": "Complete a ReAct loop",
      "description": "Run the ReAct activity with at least one successful step and a final answer.",
      "href": "01b-react.html#react-artifact"
    }
  ],
  [
    "01c:tool-roundtrip-complete",
    {
      "label": "Complete a tool round trip",
      "description": "Run the tool-calling activity with a successful step and a final answer.",
      "href": "01c-tools.html#tools-artifact"
    }
  ],
  [
    "02a:routed-workflow-complete",
    {
      "label": "Run a routed workflow",
      "description": "Complete the routing activity with a successful step and a final answer.",
      "href": "02a-routing.html#router-artifact"
    }
  ],
  [
    "02b:grounded-answer-complete",
    {
      "label": "Complete the retrieval activity",
      "description": "Run the RAG activity with a successful step and a final answer.",
      "href": "02b-rag.html#rag-artifact"
    }
  ],
  [
    "02c:deep-research-complete",
    {
      "label": "Complete a research run",
      "description": "Finish the deep-research activity with a successful step and a final answer.",
      "href": "02c-deep.html#deep-artifact"
    }
  ],
  [
    "03a:nemoclaw-connected",
    {
      "label": "Connect to NemoClaw",
      "description": "Pass the connection checks for metadata, gateway, terminal, and health.",
      "href": "03a-kickstart.html#probe-claw"
    }
  ],
  [
    "03b:workspace-inspected",
    {
      "label": "Inspect your workspace",
      "description": "Successfully run both the introspection and workspace terminal exercises.",
      "href": "03b-openclaw.html#cell-introspect"
    }
  ],
  [
    "03c:scheduled-run-complete",
    {
      "label": "Run and clean up a scheduled job",
      "description": "Observe a successful scheduled run, then confirm the job was removed.",
      "href": "03c-always-on.html#probe-cron"
    }
  ],
  [
    "04a:policy-boundary-verified",
    {
      "label": "Check the policy boundary",
      "description": "Read the live agent policy, then confirm the policy comparison agrees.",
      "href": "04a-safety.html#cell-live-policy"
    }
  ],
  [
    "04b:live-agent-operated",
    {
      "label": "Operate a live agent",
      "description": "Send a non-command message to the live agent and receive a successful response.",
      "href": "04b-modern-clis.html#agent-chat"
    }
  ]
].map(([id, value]) => [id, Object.freeze(value)]),
));
export const ACTIVITY_MILESTONE_ORDER = Object.freeze(Object.keys(ACTIVITY_MILESTONES));


export const ACTIVITY_SESSION_MILESTONES = Object.freeze(
  ACTIVITY_MILESTONE_ORDER.map(id => Object.freeze({
    id, label: ACTIVITY_MILESTONES[id].label, description: ACTIVITY_MILESTONES[id].description,
  })),
);
