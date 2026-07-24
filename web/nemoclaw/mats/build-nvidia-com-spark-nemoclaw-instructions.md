[Skip to main content](https://build.nvidia.com/spark/nemoclaw/instructions#main-content)

[View All Playbooks](https://build.nvidia.com/spark)

[View All Playbooks](https://build.nvidia.com/spark)

# Run NemoClaw with a Local LLM

30 MIN

Build your first local AI assistant on DGX Spark using NemoClaw and Ollama in a secure sandbox, with optional Telegram.

[Agentic Workflow](https://build.nvidia.com/search?label=Agentic+Workflow) [DGX Spark](https://build.nvidia.com/search?label=DGX+Spark) [NemoClaw](https://build.nvidia.com/search?label=NemoClaw) [Ollama](https://build.nvidia.com/search?label=Ollama) [OpenShell](https://build.nvidia.com/search?label=OpenShell) [Telegram](https://build.nvidia.com/search?label=Telegram)

[NemoClaw on GitHub](https://github.com/NVIDIA/NemoClaw)

[OverviewOverview](https://build.nvidia.com/spark/nemoclaw/overview) [InstructionsInstructions](https://build.nvidia.com/spark/nemoclaw/instructions) [TroubleshootingTroubleshooting](https://build.nvidia.com/spark/nemoclaw/troubleshooting)

## Phase 1: Install and Run NemoClaw

## Install NemoClaw

This single command handles everything: installs Node.js (if needed), installs OpenShell, clones the pinned NemoClaw **v0.0.55** release (set via `NEMOCLAW_INSTALL_TAG`; v0.0.55 is the version the NemoClaw team currently recommends as the most stable), builds the CLI, and runs the onboard wizard to create a sandbox.

Bash

CopiedCopy

```
curl -fsSL https://www.nvidia.com/nemoclaw.sh | NEMOCLAW_INSTALL_TAG=v0.0.55 bash
```

The installation wizard walks you through setup:

1. **Accept NemoClaw license** \-\- Confirm by entering `yes`
2. **Run express install** \-\- Confirm by entering `Y`

The installer requires **Node.js 22.16+** (installed automatically if missing). It walks you through Node.js, NemoClaw CLI and Onboarding phases. See more details of Onboarding configuration in the next step.

## NemoClaw Onboarding

NOTE

If you chose **express install** in Step 1, all settings are auto-configured with recommended defaults. Skip to Step 3.

During custom setup, the onboard wizard walks you through:

1. **Configuring inference** \-\- Choose to set up local inference on your Spark by selecting **`7) Local Ollama`**.
2. **Ollama models** \-\- Choose desired inference model. If no model is present locally, the installer will download **`qwen3.6:35b`** automatically.
3. **Sandbox name** \-\- Pick a name (e.g. my-assistant). Each sandbox requires a unique name.
4. **Apply this configuration** \-\- Enter `Y` to confirm setting up local inference.
5. **Enable Brave Web Search** \-\- Optional. If you enable it, paste a [Brave Search API](https://brave.com/search/api/) key when prompted.
6. **Messaging channels** \-\- Optional. If you enable it, choose your desired bot (`telegram`, `discord` or `slack`) and paste your bot token when prompted.
7. **Policy presets** \-\- Choose desired Policy tier (`Balanced` recommended) and accept/edit the suggested presets when prompted (confirm with **Enter**).

When complete you will see output like:

Text

CopiedCopy

```
──────────────────────────────────────────────────
Sandbox      my-assistant (Landlock + seccomp + netns)
Model        <your-selected-model> (Local Ollama)
──────────────────────────────────────────────────
Run:         nemoclaw my-assistant connect
Status:      nemoclaw my-assistant status
Logs:        nemoclaw my-assistant logs --follow
──────────────────────────────────────────────────
```

NOTE

- If `nemoclaw` is not found after install, run `source ~/.bashrc` to reload your shell path.
- Time to finish **Onboarding** can vary, depending on the model choice and internet speed.

NemoClaw Onboarding can be run repeatedly to create multiple sandboxes for independent usecases. Use `--name <new-name>` to create an additional sandbox alongside any existing ones:

Bash

CopiedCopy

```
nemoclaw onboard --gpu --name <new-name>
```

IMPORTANT

Use `--name <new-name>` to create an additional sandbox without affecting existing ones. The `--fresh` flag is a destructive option reserved for starting a completely new onboard session — if a sandbox with the same name already exists, `--fresh` will **destroy and recreate it**. Only use `--fresh` when you intend to wipe and re-onboard (see Step 4 for an example where re-prompting is required).

## Interact with OpenClaw

There are two ways to interact with your OpenClaw, Web UI or terminal UI.

### Option 1. Web UI

Get the full dashboard URL (includes the auto-assigned port and token):

Bash

CopiedCopy

```
nemoclaw my-assistant dashboard-url --quiet
```

This prints a URL like `http://127.0.0.1:18790/#token=<token>`. The port is auto-assigned (commonly 18789 or 18790) and may differ between installs.

**If accessing the Web UI directly on the Spark** (keyboard and monitor attached), open the dashboard URL in a browser.

**If accessing the Web UI from a remote machine**, you need to set up an SSH tunnel.

First, note the port number from the dashboard URL above (e.g. `18790`).

Find your Spark's IP address:

Bash

CopiedCopy

```
hostname -I | awk '{print $1}'
```

This prints the primary IP address (e.g. `192.168.1.42`). You can also find it in **Settings > Wi-Fi** or **Settings > Network** on the Spark's desktop, or check your router's connected-devices list.

From your remote machine, create an SSH tunnel using the port from above (replace `<port>` and `<your-spark-ip>`):

Bash

CopiedCopy

```
ssh -L <port>:127.0.0.1:<port> <your-user>@<your-spark-ip>
```

Now open the dashboard URL in your remote machine's browser.

IMPORTANT

Use `127.0.0.1`, not `localhost` \-\- the gateway origin check requires an exact match.

NOTE

If the Web UI fails to load and the port forward may be stale, get the port from `nemoclaw my-assistant dashboard-url --quiet` and reset:

Bash

CopiedCopy

```
openshell forward stop <port> my-assistant || true
openshell forward start <port> my-assistant --background
```

### Option 2. Terminal UI

Connect to the sandbox:

Bash

CopiedCopy

```
nemoclaw my-assistant connect
```

Then launch the terminal UI inside the sandbox:

Bash

CopiedCopy

```
openclaw tui
```

You can start chatting with OpenClaw. Press **Ctrl+C** to exit the terminal UI.

To exit the sandbox:

Bash

CopiedCopy

```
exit
```

* * *

## Phase 2: Modify NemoClaw Policy

## Enable Brave Search in sandbox

To add Brave Web Search to an existing sandbox, re-run the onboard wizard with `--fresh` to start a new session that re-prompts all options (including previously skipped features):

Bash

CopiedCopy

```
nemoclaw onboard --fresh --gpu
```

NOTE

Without `--fresh`, the onboard wizard **resumes** the previous session and will not re-prompt for features you already skipped.

When you reach **Enable Brave Web Search**, choose **yes** and paste the key from the [Brave Search API](https://brave.com/search/api/) console. Confirm the same sandbox name and inference choices where prompted. The wizard will **rebuild** the sandbox so the key is applied.

NOTE

Alternatively, set `BRAVE_API_KEY` in your environment before running the installer and Brave Search will be enabled automatically during onboard.

To confirm web search is enabled, relaunch your OpenClaw WebUI or terminal UI. Ask the agent for something that needs **live web search**. If requests still fail, recheck **`policy-list`** and re-read the onboard output for Brave/API errors.

## Set up Messaging Channel (Telegram Bot as an example)

These steps apply when your sandbox exists but **Telegram was never configured** (you skipped **Messaging channels** in Step 2, or the sandbox policy tier never included Telegram-related egress). Replace `<sandbox-name>` with your sandbox (for example `my-assistant`).

### 1\. Create a Telegram bot

In Telegram, open [@BotFather](https://t.me/BotFather), send `/newbot`, and complete the prompts. Copy the **bot token** BotFather returns and keep it ready for the next step.

### 2\. Register Telegram with NemoClaw and rebuild the sandbox

Bash

CopiedCopy

```
nemoclaw <sandbox-name> channels add telegram
```

Paste the token when prompted. NemoClaw persists credentials and **rebuilds** the sandbox so OpenClaw can use Telegram as a messaging channel.

### 3\. (If needed) Allow Telegram egress in the sandbox policy

If messages fail with network or policy errors after the channel is registered, inspect presets and add Telegram-related egress if your tier omitted it:

Bash

CopiedCopy

```
nemoclaw <sandbox-name> policy-list
nemoclaw <sandbox-name> policy-add telegram
```

Preset names follow your selected tier; confirm against [Network policies](https://docs.nvidia.com/nemoclaw/latest/reference/network-policies.html).

### 4\. Verify Telegram

Telegram uses long-polling (`getUpdates`) — the sandbox actively pulls messages from Telegram servers. **No public URL or cloudflared tunnel is required for Telegram to work.**

Open Telegram, find your bot, and send a message. The bot should forward traffic to the agent in your NemoClaw sandbox and reply.

NOTE

The first response may take longer depending on model size (30B models respond in a few seconds; larger models may take longer on first inference).

NOTE

If the bot does not respond:

- Run `nemoclaw <sandbox-name> status` to confirm the sandbox is running and inference is healthy.
- Run `nemoclaw <sandbox-name> logs --follow` and look for Telegram-related errors.
- If Telegram egress is missing, run `nemoclaw <sandbox-name> policy-add` and select `telegram`.
- If the channel was never registered, run `nemoclaw <sandbox-name> channels add telegram`.

NOTE

The `channels add telegram` wizard also prompts for an optional **Telegram User ID** to restrict who can DM the bot. Send `/start` to [@userinfobot](https://t.me/userinfobot) on Telegram to get your numeric user ID. If you skip this, the bot will require device pairing (a terminal-based code confirmation) before responding to messages.

NOTE

For details on restricting which Telegram chats can interact with the agent, see the [NemoClaw Telegram bridge documentation](https://docs.nvidia.com/nemoclaw/latest/deployment/set-up-telegram-bridge.html).

### 5\. (Optional) Install cloudflared for remote Web UI access

The cloudflared tunnel provides a **public URL for the Web UI dashboard** — it is not related to Telegram messaging.

Install cloudflared (DGX Spark is arm64):

Bash

CopiedCopy

```
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb
```

Start the tunnel:

Bash

CopiedCopy

```
nemoclaw tunnel start
```

Verify:

Bash

CopiedCopy

```
nemoclaw status
```

You should see `● cloudflared` with a `trycloudflare.com` public URL.

* * *

## Phase 3: Set Up NemoClaw Agent

## Set Up NemoClaw Agents

Set up NemoClaw Agents in general require three steps: Configure NemoClaw security policy, Run Agent Workflow Prompt, Personalize the Workflow for your own use case.

Checkout these [Example NemoClaw Agents](https://build.nvidia.com/spark/nemoclaw-applications) for reference. Consider sharing your NemoClaw agent setup with the community at [DGX Spark Developer Forum](https://forums.developer.nvidia.com/c/accelerated-computing/dgx-spark-gb10)

* * *

## Phase 4: Cleanup and Uninstall

## Stop services

Stop the cloudflared tunnel:

Bash

CopiedCopy

```
nemoclaw tunnel stop
```

Stop the port forward:

Bash

CopiedCopy

```
openshell forward list          # find active forwards and their ports
openshell forward stop <port>   # stop the dashboard forward (use the port shown above)
```

## Uninstall NemoClaw

The NemoClaw CLI includes a built-in uninstaller. It removes all sandboxes, the OpenShell gateway, Docker containers/images/volumes, the CLI, and all state files. Docker, Node.js, npm, and Ollama are preserved.

Bash

CopiedCopy

```
nemoclaw uninstall --yes
```

To remove everything including the Ollama model:

Bash

CopiedCopy

```
nemoclaw uninstall --yes --delete-models
```

**Uninstaller flags:**

| Flag | Effect |
| --- | --- |
| `--yes` | Skip the confirmation prompt |
| `--keep-openshell` | Leave the `openshell` binary in place |
| `--delete-models` | Also remove the Ollama models pulled by NemoClaw |

NOTE

If the `nemoclaw` CLI is not available (e.g. install failed partway), use the remote uninstaller as a fallback:

Bash

CopiedCopy

```
curl -fsSL https://raw.githubusercontent.com/NVIDIA/NemoClaw/refs/heads/main/uninstall.sh | bash -s -- --yes
```

The uninstaller runs 6 steps:

1. Stop NemoClaw helper services and port-forward processes
2. Delete all OpenShell sandboxes, the NemoClaw gateway, and providers
3. Remove the global `nemoclaw` npm package
4. Remove NemoClaw/OpenShell Docker containers, images, and volumes
5. Remove Ollama models (only with `--delete-models`)
6. Remove state directories (`~/.nemoclaw`, `~/.config/openshell`, `~/.config/nemoclaw`) and the OpenShell binary

NOTE

If you have a local clone at `~/.nemoclaw/source` you want to keep, move or back it up before running the uninstaller — it is removed as part of state cleanup in step 6.

## Useful commands

| Command | Description |
| --- | --- |
| `nemoclaw my-assistant connect` | Shell into the sandbox |
| `nemoclaw my-assistant status` | Show sandbox status and inference config |
| `nemoclaw my-assistant logs --follow` | Stream sandbox logs in real time |
| `nemoclaw list` | List all registered sandboxes |
| `nemoclaw tunnel start` | Start cloudflared tunnel (public URL for remote Web UI access) |
| `nemoclaw tunnel stop` | Stop the cloudflared tunnel |
| `nemoclaw my-assistant dashboard-url --quiet` | Print the full tokenized Web UI URL (includes auto-assigned port) |
| `openshell term` | Open the monitoring TUI on the host |
| `openshell forward list` | List active port forwards |
| `nemoclaw uninstall --yes` | Remove NemoClaw (preserves Docker, Node.js, Ollama) |
| `nemoclaw uninstall --yes --delete-models` | Remove NemoClaw and Ollama models |

### Resources

- [NemoClaw](https://github.com/NVIDIA/NemoClaw)
- [NemoClaw Documentation](https://docs.nvidia.com/nemoclaw/latest/index.html)
- [OpenClaw Documentation](https://docs.openclaw.ai/)
- [DGX Spark Documentation](https://docs.nvidia.com/dgx/dgx-spark)
- [DGX Spark Forum](https://forums.developer.nvidia.com/c/accelerated-computing/dgx-spark-gb10)