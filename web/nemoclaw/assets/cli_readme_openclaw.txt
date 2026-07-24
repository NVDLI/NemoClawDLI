# OpenClaw (in NVIDIA NemoClaw)

OpenClaw is the agent runtime this course drives. It runs a model in a loop with tools, the
same application shape as the other CLI agents, with a few defaults turned up for unattended,
long-running operation.

- **Beacon.** Its configuration is the whole `workspace/` folder, not a single file: SOUL.md
  (persona), AGENTS.md, IDENTITY.md, MEMORY.md, skills, and cron definitions. The runtime folds
  these into the system prompt every turn.
- **Admin plane.** A JSON-RPC gateway at `/cli/gateway` exposes identity, config, crons, files,
  and chat. The same surface the Control UI uses, reachable programmatically.
- **Containment.** In NemoClaw it runs inside the kernel-level OpenShell sandbox (netns,
  Landlock, seccomp, and an OPA-evaluated egress proxy), so its tool palette is gated by policy
  regardless of what the model decides.
- **Built for unattended operation.** Cron and heartbeat triggers, persistent memory, and a
  fleet/sub-agent shape are first-class, so it is shaped for agents that run with nobody watching.

Self-modification is available the same way it is to any agent that can edit files: an OpenClaw
agent can rewrite its own SOUL.md or add a skill. Containment is what bounds the blast radius of
that, not the absence of the capability.
