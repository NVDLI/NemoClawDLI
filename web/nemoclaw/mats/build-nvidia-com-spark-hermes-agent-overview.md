[Skip to main content](https://build.nvidia.com/spark/hermes-agent/overview#main-content)

[View All Playbooks](https://build.nvidia.com/spark)

[View All Playbooks](https://build.nvidia.com/spark)

# Run Hermes Agent with Local Models

30 MIN

Install and run the Hermes self-improving AI agent on DGX Spark.

[AI Agent](https://build.nvidia.com/search?label=AI+Agent) [LLM](https://build.nvidia.com/search?label=LLM) [Nous Research](https://build.nvidia.com/search?label=Nous+Research)

[View on GitHub](https://github.com/NousResearch/hermes-agent)

[OverviewOverview](https://build.nvidia.com/spark/hermes-agent/overview) [InstructionsInstructions](https://build.nvidia.com/spark/hermes-agent/instructions) [TroubleshootingTroubleshooting](https://build.nvidia.com/spark/hermes-agent/troubleshooting)

## Basic idea

[Hermes Agent](https://github.com/NousResearch/hermes-agent) is a **self-improving** AI agent built by [Nous Research](https://nousresearch.com/). It runs as a terminal TUI on your machine and, through a built-in gateway, can also be reached from messaging platforms like Telegram, Discord, and Slack. It creates skills from experience, improves them during use, persists memory across sessions, and can run scheduled tasks via its built-in cron.

Running Hermes and its LLM **fully on your DGX Spark** keeps your conversations and data private and avoids ongoing cloud API costs. DGX Spark is well suited for this: it runs Linux, is designed to stay on, and has **128GB memory**, so you can serve large local models for better reasoning quality and connect to the agent from your phone over Telegram while the heavy work runs locally.

## What you'll accomplish

You will have Hermes installed on your DGX Spark and connected to a local LLM served by Ollama. You can chat with the agent from the DGX Spark terminal and from Telegram on your phone or laptop. The gateway runs as a system service, so the agent stays reachable across reboots without anyone logging in.

- Install Ollama and pull a local model
- Install Hermes and configure it against the local Ollama endpoint
- Set up a Telegram bot so you can message Hermes from any Telegram client
- Resume past sessions, switch models, update, and uninstall using the `hermes` CLI

## Popular use cases

- **Personal assistant from your phone**: Chat with Hermes via Telegram while the model runs on your Spark — manage email drafts, summarize docs, or answer questions on the go.
- **Multi-step task automation**: Ask the agent to walk you through configurations (e.g., setting up email); on non-trivial tasks Hermes can autonomously persist a reusable skill for next time.
- **Scheduled checks**: Use the built-in cron to watch a product price online or run a daily check, and have results delivered to your Telegram home channel.
- **Reasoning-visible problem solving**: Use `/reasoning show` in the TUI to follow the agent's intermediate reasoning on complex problems.

## What to know before starting

- Basic use of the Linux terminal and a text editor
- Familiarity with Ollama or willingness to follow the [Ollama on Spark playbook](https://build.nvidia.com/spark/ollama) first
- A Telegram account if you want to use the messaging gateway
- Awareness of the security considerations below

## Important: security and risks

AI agents that can execute commands and reach external services introduce real risks. Read the upstream guidance, especially the dedicated security topics: [Hermes Agent — Security](https://hermes-agent.nousresearch.com/docs/user-guide/security).

Main risks:

1. **Data exposure**: Personal information or files on your DGX Spark may be leaked through agent actions or messaging channels.
2. **Unauthorized access**: A Telegram bot left open to anyone who finds it can be misused; a model endpoint exposed beyond `localhost` can be abused.

You cannot eliminate all risk; proceed at your own risk. **Recommended security measures:**

- **Restrict the Telegram bot** by entering one or more numeric Telegram user IDs at the _"Allowed user IDs"_ prompt during install. Leaving this blank allows anyone who finds the bot to use it.
- Keep the Ollama endpoint bound to **`localhost` only**; do not expose `http://<spark-ip>:11434` to your LAN or the public internet without strong authentication.
- Run Hermes on a Spark dedicated to this purpose where possible, and only place files on it that the agent is allowed to access.
- **Monitor activity**: Periodically review the gateway service logs (`sudo journalctl -u <hermes-gateway-unit> -e`) and the Hermes session history.

## Prerequisites

- DGX Spark running Linux, connected to your network
- Terminal (SSH or local) access to the Spark
- `curl` and `git` installed (verified in Step 1 of the instructions)
- Interactive terminal access for the setup wizard and any `sudo` password prompts. Non-interactive SSH is supported with the config-command fallback in the Instructions tab.
- Enough disk and GPU memory for the Ollama model you plan to serve (the playbook uses `qwen3.6:27b` as the example; pick a smaller model if you want a faster first install)
- A Telegram account and the ability to create a bot via [@BotFather](https://t.me/BotFather) if you plan to use the messaging gateway

## Time and risk

- **Duration**: About 30 minutes for install and first-time setup; model download time depends on size and network speed.
- **Risk level**: **Medium** — the agent can execute commands, persist skills, and is reachable from Telegram. Risk increases if you skip the allowed-user-IDs restriction or expose the local model endpoint beyond `localhost`. Always follow the security measures above.
- **Rollback**: Run `hermes uninstall` (with `sudo` if you installed the gateway as a system service) to remove Hermes, the gateway service, and the shell-profile entry. The data directory `~/.hermes` may still be present afterward; remove it manually if you want a full reset (see the Cleanup and Troubleshooting tabs). Uninstall Ollama separately if desired.
- **Last Updated**: 2026-05-08

  - First Publication

### Resources

- [Hermes Agent Documentation](https://hermes-agent.nousresearch.com/docs/)
- [Hermes Agent — Security](https://hermes-agent.nousresearch.com/docs/user-guide/security)
- [Hermes Agent GitHub Repository](https://github.com/NousResearch/hermes-agent)
- [Nous Research](https://nousresearch.com/)
- [DGX Spark Documentation](https://docs.nvidia.com/dgx/dgx-spark)
- [DGX Spark Forum](https://forums.developer.nvidia.com/c/accelerated-computing/dgx-spark-gb10)