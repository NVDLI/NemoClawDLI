# OpenShell, NemoClaw, and the OpenClaw stack

*A reading of the security substrate the NemoClaw course teaches, distilled from NVIDIA's own writeups. The companion safety architecture (three lines of defense, the Manchurian agent, peer preservation) is in [Agentic Safety in Production](./agentic_safety_in_production.md). This post covers the runtime underneath that architecture: what OpenShell enforces, how it enforces it out of process, and how NemoClaw assembles the three pieces into something you can run on a single box.*

---

The course is built around a stack of three parts that are easy to conflate and worth separating cleanly. They sit at different layers and were built by different people for different reasons.

- **OpenClaw is the agent application.** It is an open-source project created by Peter Steinberger that reached 250,000 GitHub stars by early 2026 ([NVIDIA, "What OpenClaw agents mean for every organization"](https://blogs.nvidia.com/blog/what-openclaw-agents-mean-for-every-organization/)). It is the long-running assistant itself: a self-hosted, persistent agent that runs in the background, completes tasks on its own, and surfaces only what needs a human decision. In the NemoClaw deployment it is described as a "self-hosted gateway that connects messaging platforms to AI coding agents powered by open models," living inside the sandbox and managing chat platforms, memory, and tool integration ([NVIDIA, "Build a secure, always-on local AI agent with NVIDIA NemoClaw and OpenClaw"](https://developer.nvidia.com/blog/build-a-secure-always-on-local-ai-agent-with-nvidia-nemoclaw-and-openclaw/)). [Hermes Agent](https://github.com/NousResearch/hermes-agent) from Nous Research is the same shape of thing on the course's hardware: a self-improving terminal agent that creates skills from experience, persists memory across sessions, runs scheduled tasks via a built-in cron, and is reachable from messaging platforms through a gateway. The course treats OpenClaw and Hermes as instances of the agent-application layer, the part that holds the brain and the conversation.

- **OpenShell is the secure runtime.** It is the sandbox the agent application runs inside. Apache 2.0 licensed, it is described as a governance layer between autonomous agents and infrastructure, addressing the gap that traditional agent runtimes "lack core security primitives: sandboxing, permissions, and isolation" ([NVIDIA, "Run autonomous, self-evolving agents more safely with NVIDIA OpenShell"](https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/)). It is the layer that decides what the agent can reach, independent of what the agent decides it wants to reach.

- **NemoClaw is NVIDIA's reference stack.** It is the assembly that runs the agent application inside OpenShell with governed defaults. NVIDIA describes it as "an open-source reference stack that orchestrates NVIDIA OpenShell to run OpenClaw," providing "guided onboarding, lifecycle management, image hardening, and a versioned blueprint" ([NemoClaw blog](https://developer.nvidia.com/blog/build-a-secure-always-on-local-ai-agent-with-nvidia-nemoclaw-and-openclaw/)). The current [NemoClaw documentation](https://docs.nvidia.com/nemoclaw/latest/) labels the project alpha and early preview. Interfaces and behavior can change, so this course points readers to the current documentation for operational details.

The orchestration flows top to bottom: NemoClaw sets the stack up, OpenShell encloses it, OpenClaw (or Hermes) runs inside the enclosure. The rest of this post is about the middle layer, because that is where the course's security claims actually live.

---

## Why containment moves out of the prompt

The reason OpenShell exists is the same reason the safety post starts from infrastructure rather than instructions. An agent with persistent shell access, live credentials, and the ability to rewrite its own tooling is a different threat model from a stateless chatbot. Prompt-level rules are application-layer text sitting on top of broad ambient permissions, and a capable agent reasons its way around text.

OpenShell inverts the default. Its design principle is "out-of-process policy enforcement. Instead of relying on behavioral prompts, it enforces constraints on the environment the agent runs in, meaning the agent cannot override them, even if compromised" ([OpenShell blog](https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/)). The word that carries the weight is *out-of-process*: the policy engine is not a library the agent calls and could choose not to call. It is a separate enforcement boundary the agent's actions pass through whether the agent likes it or not.

NVIDIA reaches for the browser tab as the analogy: "Sessions are isolated, and permissions are verified by the runtime before any action executes." A tab cannot read another tab's cookies because the browser does not let it, not because the page promised to behave. OpenShell applies that model to agents.

---

## What the policy engine enforces

The enforcement spans three layers of the agent's environment. From the OpenShell blog: "The policy engine enforces constraints on the agent's environment across the filesystem, network, and process layers."

Three properties make that enforcement usable rather than just present.

**Granular evaluation.** The engine does not gate at a coarse "can this agent touch the network" level. It evaluates "every action at the binary, destination, method, and path level," so that "an agent can install a verified skill but cannot execute an unreviewed binary" ([OpenShell blog](https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/)). The distinction between a verified skill and an unreviewed binary is the kind of line a coarse sandbox cannot draw, and it is the line that matters when the agent writes its own tools.

**Deny-by-default.** OpenShell runs with "deny-by-default, live policy updates, and a full audit trail whether you're one developer or running an enterprise GPU cluster." Deny-by-default is the architectural philosophy the safety post names explicitly: the system grants capabilities one at a time rather than starting open and trying to claw permissions back with text.

**The Privacy Router.** This is the data-flow control. The router "keeps sensitive context on-device with local open models and routes to frontier models like Claude and GPT only when policy allows." The framing in the blog is sharp on whose decision this is: "The router makes decisions based on your cost and privacy policy, not the agent's." Whether a given piece of context is allowed to leave the device is not something the agent reasons about; it is a routing decision the runtime makes against a policy the operator wrote.

---

## Live policy and audit

Two operational properties keep the model practical over the life of a running agent.

Policy is not frozen at sandbox creation. "Policy updates happen live at sandbox scope as developer approvals are granted" ([OpenShell blog](https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/)). When the agent needs a capability it does not have, the developer grants it and the policy tightens or loosens at the scope of that one sandbox, while the agent keeps running. This is what makes deny-by-default livable: the starting envelope can be small because widening it does not require a restart.

Every decision is recorded. OpenShell maintains "a full audit trail of every allow and deny decision." The denies matter as much as the allows. A trail of what the agent tried to do and was stopped from doing is the raw material behavioral monitoring (the third line of defense in the safety post) needs to flag a deviation.

NVIDIA places OpenShell inside the broader NVIDIA Agent Toolkit, the framework that also carries "models, tools, evaluation, and runtimes," and lists integrations with agent applications beyond OpenClaw, including Claude Code, Codex, Cursor, and OpenCode ([OpenShell blog](https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/)). OpenShell is positioned as a runtime that hosts agents in general, not only the one the course happens to run.

---

## What the blog claims and what the course adds

A point of accuracy worth being explicit about. The OpenShell blog describes the enforcement model (out-of-process, deny-by-default, granular at the binary/destination/method/path level, the Privacy Router, live updates, audit trail) without naming the kernel mechanisms that implement it. It does not mention Landlock, seccomp, or network namespaces.

The specific kernel primitives surface in the course's own policy implementation, not in that blog. The NemoClaw onboarding output the course walks through labels each sandbox `Landlock + seccomp + netns`, and the policy presets choose a tier (Balanced recommended) whose network rules are added and removed per sandbox with commands like `policy-list` and `policy-add` ([course build instructions](./build-nvidia-com-spark-nemoclaw-instructions.md)). So when this material attributes filesystem confinement to Landlock, syscall filtering to seccomp, and network isolation to a network namespace, that mapping comes from the course implementation and NemoClaw's own output, not from the OpenShell announcement. The blog says *what* is enforced and *where* the enforcement sits (below the application, not overridable by the model). The course shows *which* Linux facilities carry the load. Keeping those two sources distinct matters: the safety post's control-type table credits the kernel (Landlock, seccomp, netns) as the enforcer for the infrastructure line, and that credit is grounded in the implementation, not in a marketing claim the blog never made.

---

## Why organizations care

The "What OpenClaw agents mean" post reads the same architecture from the buyer's side. The argument it makes for why an organization would run this stack rather than a cloud agent rests on three things the local-plus-sandbox design gives you.

- **Transparency.** "Organizations own the full agent harness. They can read, fork and modify every layer of how their agents are built and deployed" ([NVIDIA blog](https://blogs.nvidia.com/blog/what-openclaw-agents-mean-for-every-organization/)). The harness is not a vendor black box.
- **Runtime sandboxing.** OpenShell "defines precisely what the agent can and cannot do." This is the same enforcement boundary described above, restated as a governance property.
- **Local infrastructure.** Running on dedicated hardware such as NVIDIA DGX Spark keeps "sensitive workloads, including patient records, legal documents, financial transactions and proprietary research, within the organization's own environment."

The operational control argument is that organizations can "see what their agents are doing, inspect their reasoning at each step, audit their actions and intervene when needed," with trace data kept "under organizational control" rather than handed to a cloud API. The named use cases are concrete: financial-services agents that "continuously monitor trading systems and regulatory feeds, flagging material events," drug-discovery agents that "sweep new scientific literature, extracting relevant findings and updating internal databases in real time," and overnight engineering sweeps across "thousands of parameter combinations." NVIDIA's stated collaboration with Steinberger and the OpenClaw community focuses on "improving model isolation, better managing local data access and strengthening the processes for verifying community code contributions" ([NVIDIA blog](https://blogs.nvidia.com/blog/what-openclaw-agents-mean-for-every-organization/)).

The honest caveat the NemoClaw blog states directly: "no sandbox offers complete protection against advanced prompt injection." The runtime contains what the agent can physically do. It does not make the agent's reasoning trustworthy. That gap is exactly what the [Agentic Safety in Production](./agentic_safety_in_production.md) post addresses with its second and third lines of defense, and why the course teaches the runtime as the foundation rather than the whole answer.

---

## The stack on one box

DGX Spark is one documented deployment profile, not the product boundary. Current [prerequisites](https://docs.nvidia.com/nemoclaw/latest/get-started/prerequisites) cover Linux, macOS, Windows through WSL2, and DGX Spark, starting from a CPU and memory baseline rather than a universal GPU requirement. NemoClaw can use hosted or local inference; local Ollama, vLLM, and NIM are choices alongside hosted providers, with some GPU-managed paths still experimental ([inference options](https://docs.nvidia.com/nemoclaw/latest/reference/inference-profiles.html)). The DGX Spark playbook used by this companion material deliberately chooses local inference and dedicated hardware. Do not generalize that playbook into a requirement for every NemoClaw installation.

The single install command (`curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash`) installs the CLI and starts onboarding, which then prepares OpenShell, the blueprint, the chosen inference route, and the sandboxed OpenClaw instance. The exact lifecycle is versioned alpha behavior; follow the current official quickstart when reproducing it outside this course.

That is the substrate the course teaches on top of. The agent application supplies the brain and the skills. NemoClaw supplies the hardened assembly. OpenShell supplies the boundary that holds when the brain is wrong.

---

## Sources

- NVIDIA, "Run autonomous, self-evolving agents more safely with NVIDIA OpenShell." [https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/](https://developer.nvidia.com/blog/run-autonomous-self-evolving-agents-more-safely-with-nvidia-openshell/)
- NVIDIA, "Build a secure, always-on local AI agent with NVIDIA NemoClaw and OpenClaw." [https://developer.nvidia.com/blog/build-a-secure-always-on-local-ai-agent-with-nvidia-nemoclaw-and-openclaw/](https://developer.nvidia.com/blog/build-a-secure-always-on-local-ai-agent-with-nvidia-nemoclaw-and-openclaw/)
- NVIDIA, "What OpenClaw agents mean for every organization." [https://blogs.nvidia.com/blog/what-openclaw-agents-mean-for-every-organization/](https://blogs.nvidia.com/blog/what-openclaw-agents-mean-for-every-organization/)
- NVIDIA NemoClaw, current prerequisites and platform matrix. [https://docs.nvidia.com/nemoclaw/latest/get-started/prerequisites](https://docs.nvidia.com/nemoclaw/latest/get-started/prerequisites)
- NVIDIA NemoClaw, current inference options. [https://docs.nvidia.com/nemoclaw/latest/reference/inference-profiles.html](https://docs.nvidia.com/nemoclaw/latest/reference/inference-profiles.html)
- NVIDIA/NemoClaw source repository. [https://github.com/NVIDIA/NemoClaw](https://github.com/NVIDIA/NemoClaw)
- Course build instructions (kernel-mechanism attribution: Landlock, seccomp, netns; policy tiers). [build-nvidia-com-spark-nemoclaw-instructions.md](./build-nvidia-com-spark-nemoclaw-instructions.md)
- Hermes Agent, Nous Research. [https://github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
- Companion: "Agentic Safety in Production." [agentic_safety_in_production.md](./agentic_safety_in_production.md)
