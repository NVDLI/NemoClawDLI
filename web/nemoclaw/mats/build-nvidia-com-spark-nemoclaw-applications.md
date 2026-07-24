[Skip to main content](https://build.nvidia.com/spark/nemoclaw-applications#main-content)

[View All Playbooks](https://build.nvidia.com/spark)

[View All Playbooks](https://build.nvidia.com/spark)

# 🦞 Set Up Example NemoClaw Agents 🦞

30 MINS

Ready-to-run application examples for your NemoClaw sandbox — policy, prompt, and personalization for each workflow

[AI Agent](https://build.nvidia.com/search?label=AI+Agent) [Applications](https://build.nvidia.com/search?label=Applications) [DGX Spark](https://build.nvidia.com/search?label=DGX+Spark) [NemoClaw](https://build.nvidia.com/search?label=NemoClaw) [OpenShell](https://build.nvidia.com/search?label=OpenShell) [Personal Assistant](https://build.nvidia.com/search?label=Personal+Assistant) [Productivity Agent](https://build.nvidia.com/search?label=Productivity+Agent) [Telegram](https://build.nvidia.com/search?label=Telegram) [Web Search](https://build.nvidia.com/search?label=Web+Search)

[NemoClaw on GitHub](https://github.com/NVIDIA/NemoClaw)

[OverviewOverview](https://build.nvidia.com/spark/nemoclaw-applications/overview) [Daily Personal News DigestDaily Personal News Digest](https://build.nvidia.com/spark/nemoclaw-applications/news-digest) [Software Development AgentSoftware Development Agent](https://build.nvidia.com/spark/nemoclaw-applications/developer-agent) [Deck ReviewerDeck Reviewer](https://build.nvidia.com/spark/nemoclaw-applications/deck-reviewer) [Calendar NegotiatorCalendar Negotiator](https://build.nvidia.com/spark/nemoclaw-applications/calendar-negotiator) [NemoClaw Policy SetupNemoClaw Policy Setup](https://build.nvidia.com/spark/nemoclaw-applications/policy-setup) [TroubleshootingTroubleshooting](https://build.nvidia.com/spark/nemoclaw-applications/troubleshooting)

## Basic idea

This playbook is a companion to the [NemoClaw on DGX Spark](https://build.nvidia.com/spark/nemoclaw) install playbook. It walks through **four ready-to-run applications** you can stand up on top of an existing NemoClaw sandbox — a personal morning news digest, a software development agent, a doc and deck red-team, and a calendar negotiation chief-of-staff.

Each application is presented as a self-contained tab with the same three sections:

- **Policy setup** — the exact NemoClaw / OpenShell sandbox policy changes the workflow needs (channels, network egress, filesystem mounts).
- **Agent prompt** — the full canonical prompt you copy-paste into the NemoClaw web UI or send to your Telegram bot. It defines the agent's complete behavior end-to-end and is the only configuration the workflow needs.
- **How to personalize** — the knobs to turn (paths, schedule, audience, persona) to adapt the recipe to your real use case.

All applications run inside the **OpenShell sandbox** that NemoClaw created during onboarding, so the agent's filesystem, network, process, and inference access stays bounded by the policy you grant.

## What you'll accomplish

You will run four practical NemoClaw workflows on your DGX Spark:

- **[Daily Personal News Digest](https://build.nvidia.com/spark/nemoclaw-applications/news-digest)** — a scheduled morning briefing that wakes up on a cron, sweeps the topics you care about across an allowlisted set of sources, and posts a structured digest (Top 3, headlines by topic, deep dive, skip-the-noise, on-your-radar, local) to your Telegram home channel.
- **[Software Development Agent](https://build.nvidia.com/spark/nemoclaw-applications/developer-agent)** — reads a single project directory, builds an execution plan for the features you specify, implements them, reviews its own work, and writes a `develop-and-review.md` you can read before merging. No outbound network beyond the local inference endpoint.
- **[Deck Reviewer](https://build.nvidia.com/spark/nemoclaw-applications/deck-reviewer)** — a Doc & Deck Red-Team that scans the artifact you're about to send for inconsistent numbers, unsourced claims, missing data, accessibility issues, and prior-version contradictions, then returns a severity-ranked punch list with proposed edits.
- **[Calendar Negotiator](https://build.nvidia.com/spark/nemoclaw-applications/calendar-negotiator)** — a scheduling chief-of-staff that turns "when can we meet?" threads into a confirmed meeting on your calendar, respecting your focus blocks, energy patterns, and time-zone fairness with the other party.

A separate **[NemoClaw Policy Setup](https://build.nvidia.com/spark/nemoclaw-applications/policy-setup)** tab covers the one-time Telegram channel wiring that two of the applications (News Digest and Calendar Negotiator) require and the other two (Software Development Agent and Deck Reviewer) can optionally use for "ready for review" notifications. The **Troubleshooting** tab collects symptom/cause/fix entries specific to these workflows.

For each application you will be able to read the live policy YAML (`openshell policy get --full`), apply or remove maintained presets with `nemoclaw policy-add` / `policy-remove` (no rebuild required for network changes), and bind host directories into the sandbox with `nemoclaw share mount` (hot — no rebuild required for mounts either). Tightening `filesystem_policy` itself, when you want a kernel-enforced write boundary inside the sandbox, is the only step that still requires `nemoclaw rebuild` (workspace state is preserved automatically).

## What to know before starting

- You have completed the [NemoClaw on DGX Spark](https://build.nvidia.com/spark/nemoclaw) playbook and have a working sandbox (the examples use `my-assistant`).
- Basic comfort with the Linux terminal and YAML files.
- Awareness of the agent risk surface — see the _Important: security and risks_ section in the NemoClaw overview.

## Prerequisites

**Hardware and access:**

- A DGX Spark (GB10) with a working NemoClaw install (see [NemoClaw on DGX Spark](https://build.nvidia.com/spark/nemoclaw)).
- A running OpenShell gateway and a sandbox created by the NemoClaw onboard wizard (`nemoclaw list` shows at least one sandbox).
- A Telegram bot wired into the sandbox at onboard time for the **Daily Personal News Digest** and **Calendar Negotiator** applications. If you skipped Telegram during onboard, re-run the NemoClaw installer to recreate the sandbox with Telegram enabled. See **[NemoClaw Policy Setup](https://build.nvidia.com/spark/nemoclaw-applications/policy-setup)** for the one-time wiring steps.

**Software:**

- Ollama serving the model you selected during NemoClaw onboard (Nemotron 3 Super 120B in the install playbook).
- A working public webhook tunnel (`nemoclaw tunnel start`) for any Telegram-driven application.

Verify the sandbox is healthy before you start:

Bash

CopiedCopy

```
nemoclaw list
nemoclaw my-assistant status
```

Expected: your sandbox appears in the list and `status` reports the sandbox as **Running** with the inference provider pointing at your local Ollama model.

## Have ready before you begin

| Item | Where to get it | Used by |
| --- | --- | --- |
| Sandbox name from NemoClaw onboard (e.g. `my-assistant`) | `nemoclaw list` | All applications |
| Telegram bot token and numeric user ID | [@BotFather](https://t.me/BotFather) (`/newbot`), `@userinfobot` on Telegram for your user ID | [Policy Setup](https://build.nvidia.com/spark/nemoclaw-applications/policy-setup), [News Digest](https://build.nvidia.com/spark/nemoclaw-applications/news-digest), [Calendar Negotiator](https://build.nvidia.com/spark/nemoclaw-applications/calendar-negotiator); optional for [Software Development Agent](https://build.nvidia.com/spark/nemoclaw-applications/developer-agent) and [Deck Reviewer](https://build.nvidia.com/spark/nemoclaw-applications/deck-reviewer) |
| Allowlist of news source hostnames to add under `network_policies` | Pick the sites you trust | [News Digest](https://build.nvidia.com/spark/nemoclaw-applications/news-digest) |
| A host directory containing the project you want built and reviewed | A copy/clone of the project, e.g. `~/nemoclaw-projects/my-app/` | [Software Development Agent](https://build.nvidia.com/spark/nemoclaw-applications/developer-agent) |
| A queue folder, a canonical corpus folder, and a `profile.yaml` for red-team rules | Curate from prior decks, brand guide, and canonical metric files, e.g. `~/nemoclaw-redteam/` | [Deck Reviewer](https://build.nvidia.com/spark/nemoclaw-applications/deck-reviewer) |
| A `calendar.ics` export and a `profile.yaml` with working hours, focus blocks, and timezone | Export from your real calendar (Google: _Settings → Import & export_) into `~/nemoclaw-calendar/` | [Calendar Negotiator](https://build.nvidia.com/spark/nemoclaw-applications/calendar-negotiator) |

## Ancillary files

All policy snippets and example prompts in this playbook are inline in the application tabs — there are no external assets to clone. The bundled sandbox policy is shipped with NemoClaw and OpenShell; the application tabs only **modify** it.

## Time and risk

- **Estimated time:** 30–45 minutes to walk through all four applications. Each application individually takes 5–10 minutes once the prerequisites are in place. Plan an extra 10 minutes for the one-time [Policy Setup](https://build.nvidia.com/spark/nemoclaw-applications/policy-setup) tab if you have not enabled Telegram yet.
- **Risk level:** **Medium.** Every application grants the agent additional capability beyond the default sandbox — outbound network for the news digest, filesystem access for code review, deck red-team, and calendar negotiation. Risk is reduced by tight per-application policies (host-level `chmod` on read-only source data backed by `share mount`'s SSHFS permission passthrough, scoped sandbox directories so the agent only sees one mounted tree at a time, explicit egress allowlists via `nemoclaw policy-add` presets, and in-prompt safety rules that survive single-message overrides) but is not eliminated. **Do not point these recipes at sensitive data, production accounts, or personal files** without reviewing the policy first.
- **Rollback:** Each application tab includes a rollback section that either reverts the policy (network changes are hot-reloadable) or destroys and recreates the sandbox with the original policy. The [Troubleshooting](https://build.nvidia.com/spark/nemoclaw-applications/troubleshooting) tab covers common stuck-state recovery. You can always run `nemoclaw uninstall` to remove everything.
- **Last Updated:**06/01/2026

  - Sync up to latest nemoclaw/openshell policy APIs

### Resources

- [NemoClaw](https://github.com/NVIDIA/NemoClaw)
- [NemoClaw Documentation](https://docs.nvidia.com/nemoclaw/latest/index.html)
- [OpenClaw Documentation](https://docs.openclaw.ai/)
- [OpenShell Documentation](https://github.com/NVIDIA/OpenShell)
- [DGX Spark Documentation](https://docs.nvidia.com/dgx/dgx-spark)
- [DGX Spark Forum](https://forums.developer.nvidia.com/c/accelerated-computing/dgx-spark-gb10)