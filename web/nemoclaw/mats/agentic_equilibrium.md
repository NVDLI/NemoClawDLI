# The agentic equilibrium

*An engineer's reading of where the agent stack is settling. Drawn from teaching the NVIDIA "Building RAG Agents with LLMs" course and watching the same patterns recur across deployments.*

> **Companion read.** This post argues a particular reading of where the substrate is settling and which failure modes recur. The safety architecture that sits on top of the substrate (three lines of defense, peer-preservation, supply-chain risk) is in [Agentic Safety in Production](./agentic_safety_in_production.md). Read either first. They cover different halves of the same picture.

---

In 2023 the default shape of LLM use was a single pass: user query, model, response. By 2025 a production system more often runs a loop: it takes a human goal, decomposes it, calls tools, looks at the results, verifies, and only then answers. The control flow inverted somewhere in between.

**Opinion:** it inverted because tool-use plus a critic loop covers a strictly larger class of tasks than a model alone, and the cost of one extra tool call has dropped below the cost of one bad answer for most non-trivial workflows. Once those costs cross, the looped architecture wins on the economics, and further gains in raw model strength do not reverse that.

This post walks through what that means in practice. It addresses five interlocking trends (autonomous task generation, protocol-first design, runtime governance and observability, agent-as-operating-system, and the infrastructure substrate as market expansion), the recurring failure modes underneath, the labor and sociology questions that follow, and concrete recipes for engineering teams. Citations are inline. Opinions are flagged.

**The argument:**

- Engineering value over the next few years accumulates in **the substrate**: the layer of tool surfaces, trajectory records, skill libraries, runtime instrumentation, sandboxes, and observability primitives that sits between the model below and the harness above.
- The framework layer that sits above the substrate keeps churning, and the model weights underneath it are not where most teams can compete anyway, since almost no one trains their own foundation model.

The body works through each substrate component, the failure modes that bound them, the labor and sociology questions that follow, and the market dynamics that frame the whole stack.

---

## The ladder of LLM use

The story of the last few years is a ladder. Each rung is bounded by the limitations of the previous rung; resolving those limitations exposes new feasibility.

- **LLM as response engine.** Pattern-completion over a prompt. Bounded by hallucination and context cutoff.
- **LLM grounded in retrieval.** Add a vector index, retrieve before answering ([Lewis et al., 2020 RAG](https://arxiv.org/abs/2005.11401)). Bounded by retrieval quality and context-window economics.
- **LLM as argument producer.** The model emits structured arguments to deterministic tools (calculator, search, SQL). Bounded by tool surface and parser reliability.
- **LLM as sub-agent parameterizer.** A higher-level loop decomposes work into typed sub-tasks, each handed to a fresh model context. Bounded by handoff fidelity.
- **LLM as orchestrator.** Multi-step plans with verification at each step ([Yao et al., 2022 ReAct](https://arxiv.org/abs/2210.03629); [Xu et al., 2023 ReWoo](https://arxiv.org/abs/2305.18323) decoupling planning from observation; [Shinn et al., 2023 Reflexion](https://arxiv.org/abs/2303.11366) for verbal RL).
- **LLM as CLI agent.** Operating in a shell with code execution and filesystem access. Bounded by sandboxing and trajectory length.
- **LLM as connector/harness builder.** The agent writes its own tools and integrations, then operates against them.
- **LLM as self-configurer.** The agent codifies what worked and recalls it next time ([Wang et al., 2023 Voyager](https://arxiv.org/abs/2305.16291)).
- **LLM as robot controller.** Closed-loop perception-and-actuation in physical environments.

Each rung climbed because the rung below stabilized. The current production rung sits between self-configurer and robot-controller. The next rung is fleet-of-agents-as-organization.

Between those two rungs is an intermediate step worth naming. Call it **brain-as-characterised-substrate.** A single agent is now well enough understood that its failure modes (context degradation, lossy compaction, judge-correlated-with-generator) can be quantified rather than just listed. That precision matters because a fleet of N agents inherits every brain-level failure with an N multiplier, so the fleet rung only becomes tractable once the brain rung has been measured. A stronger model raises the brain rung, but the N multiplier on the inherited failures is what ends up driving how a fleet behaves.

---

## What an agent is, mechanically

The substrate is small. Most production agents reduce to a scheduler over four primitives (plan, act, observe, reflect) with pinned context for the directive. Three references cover the architectural moves:

- [ReAct](https://arxiv.org/abs/2210.03629) interleaves reasoning traces with tool actions in the decoding loop.
- [ReWoo](https://arxiv.org/abs/2305.18323) decouples planning from observation, producing a token-efficient variant useful when the action space is well-known up front.
- [Reflexion](https://arxiv.org/abs/2303.11366) adds a self-critic that revises trajectories using verbal feedback as a learned signal.
- [Voyager](https://arxiv.org/abs/2305.16291) composes those into automatic curriculum, skill library, and iterative critic, with no gradient updates.

For readers who want a formal handle, [Bratman (1987)](https://en.wikipedia.org/wiki/Belief%E2%80%93desire%E2%80%93intention_software_model) and [Rao and Georgeff (1991)](https://www.aaai.org/Library/KR/1991/kr91-049.pdf) give the BDI tuple. An agent is $(B, D, I, A, O, T)$. In a language-model implementation, $B$ is the current context window $\mathcal{C}_t$ plus any externalised workspace files. $D$ is the directive $g$ in the system prompt. $I$ is the plan committed to (visible as recent assistant turns). $A$ is the action space (tool calls plus reply text). $O$ is the observation space (tool results plus user turns). $T$ is the transition, which in a language-model agent reduces to `messages.append(action); messages.append(observation)`. The formalism does no work most of the time. It earns its keep when a failure mode needs to be located: rot lives in the gap between $g$ and the action distribution as $\mathcal{C}_t$ grows; compaction lives in the rewrite of $B$ that the runtime does silently when $\mathcal{C}_t$ overflows.

There is a parallel line: training agents directly against domain-specific action languages so the action space becomes part of the model's distribution rather than a parsing target. Anthropic's tool-use training (the model's native function-call format), OpenAI's structured outputs, and the various code-execution-as-action trainings are instances. **Opinion:** when the action space is stable enough, DSL-trained agents are more reliable than prompt-instructed ones because the action distribution is in-distribution rather than a parsing convention layered on top.

**Opinion:** if you can write your agent loop in a few hundred lines using a chat client, a vector store, and a sandbox, then a framework that abstracts those primitives behind class hierarchies is buying readability at the cost of portability. Engineering test: can framework code be deleted while preserving capability? If not, you are coupled.

---

## The agent as operating system

[Andrej Karpathy's framing from 2023](https://x.com/karpathy/status/1707437820045062561) (and his 2025 "Software 3.0" Y Combinator talk) was that the LLM is becoming the kernel process of a new operating system. The framing has aged into a design discipline. The system-call surface of a competent agent looks like a Unix process:

- I/O across modalities (text, audio, vision) maps to standard input and output.
- Code execution (Python interpreter, shell) maps to `exec`.
- Retrieval (RAG, file reads) maps to page-faults.
- Memory (vector stores, scratch buffers) maps to virtual memory.
- IPC (other agents, MCP servers, A2A endpoints) maps to sockets.
- Skills map to shared libraries.

Read that way, the agent occupies the role of a process and the harness occupies the role of the operating system around it. Once you accept the mapping, the security model falls out of it (privilege separation, capability containment, audit trails), and so does the composition model (well-defined interfaces, registry-driven discovery), with no extra design work.

The system-software signal is concrete. Anthropic's [Computer Use](https://www.anthropic.com/news/3-5-models-and-computer-use) (Claude controlling a desktop via screenshots and keyboard primitives), OpenAI's Operator (browser-resident agent), Apple Intelligence's on-device foundation models, Microsoft Copilot+ PCs (NPU-bound on-device inference), and Gemini-in-Android are five different bets on the same hypothesis: the agent is becoming a system-level capability.

---

## Frameworks vs substrate

The protocol layer is a different question from the framework layer. [MCP](https://modelcontextprotocol.io) (Anthropic, late 2024), [A2A](https://google.github.io/A2A/) (Google, 2025), and Anthropic's [Agent Skills](https://docs.anthropic.com/en/docs/build-with-claude/agent-skills) are conventions for separating capability description from runtime. The conventions themselves are technically unremarkable: JSON-RPC with a registry, capability cards over HTTP, folders with manifests.

What matters is convergence onto *a* convention, because once a sufficient fraction of capabilities speak the same shape, they compose without per-pair integration. [HTTP+JSON displacing CORBA](https://www.greglturnquist.com/blog/rest-soap-corba-e-got/) went this way, and so did the [Language Server Protocol](https://microsoft.github.io/language-server-protocol/) displacing per-editor language plugins. Whether the eventual convention turns out to be exactly MCP or some successor is not the bet to make.

The orchestration framework ecosystem (LangChain, LangGraph, LlamaIndex, Haystack, AutoGen, CrewAI, NVIDIA's NeMo Agent Toolkit, and similar) sits above this protocol layer. **Opinion:** these are wrappers over primitives. They earn their keep while you are prototyping and start to cost you at federation, vendor swap, or regulated deployment, when the abstraction you leaned on is in the way. The rule that holds up is to write framework code as glue you can pull out without losing capability.

---

## Representation: when to reason, when to speak, when to code

A question that gets less attention than it should: how should the agent's internal state be represented? Free-form prose, structured JSON, executable code, chain-of-thought reasoning, scratchpad sketches. The choice is measurable per task.

- **Reasoning chains** ([Wei et al., 2022 Chain-of-Thought](https://arxiv.org/abs/2201.11903)) help on multi-step problems where intermediate computation matters. They also produce hallucinated intermediate steps that the final answer compounds over. Mitigation: verification at each step, not larger reasoning budgets.
- **Structured output** (JSON-shaped, schema-validated) reduces parser failure and makes downstream tool use deterministic. It constrains expressive range.
- **Code as action** is the most precise representation for procedural tasks: auditable, debuggable, sandboxable, composable. Most production deployments of long-horizon agents are converging toward code as the default action language.
- **Free-form prose** remains the right representation for tasks where ambiguity is the point (creative work, exploratory analysis, communication with humans).

**Opinion:** there is no universal answer. The pattern that holds in the deployments I have seen is code-as-action for anything procedural, structured output at tool boundaries, reasoning chains gated by verifiers, and prose for outputs to humans. The teams whose agents come out more reliable are the ones that choose the representation task by task, instead of standardizing on one for a whole project and living with it where it does not fit.

---

## Failure modes that recur

Four failure modes show up in nearly every production deployment. They are connected: each one creates the precondition for the next.

**Context degradation.** [Liu et al. (2024) "Lost in the Middle"](https://arxiv.org/abs/2307.03172) demonstrated that information at 10 to 50 percent depth in context is systematically under-attended. [Hsieh et al. (2024) RULER](https://arxiv.org/abs/2404.06654) showed that effective context length is much shorter than advertised. For long-running agents, this manifests as drift: the original directive ("only modify files in `/src`") gets out-attended by recent error logs and tool outputs four turns later, and the agent does something it was told not to do. Enlarging the context window does not address this, because the problem is where attention lands rather than how much fits. What helps is structured compaction: explicit rolling summaries, pinned directive blocks, attention-sink tokens, and per-step verification against a stable goal record.

**Catastrophic compaction.** When the harness summarizes a long session to fit a smaller window, the summary is itself a model output with all the failure modes of model outputs. Directives compress lossily. Critical observations get smoothed away. The compacted state can read sensible while having silently changed what the agent believes. Mitigation: treat directives and observations differently in compaction (directives preserved verbatim, observations may be summarized), and verify the compacted state against the un-compacted state at boundaries.

**Adversarial compliance and the supervisor problem.** Goodhart's Law in agent loops. When a measurable proxy stands in for the true objective, the agent learns the proxy. Same-model judges amplify this because the generator and the judge share stylistic biases. The supervisory case is the same phenomenon at human scale: [METR's 2025 randomized controlled trial](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) ([arxiv 2507.09089](https://arxiv.org/abs/2507.09089)) measured a 19 percent slowdown when 16 experienced open-source developers used early-2025 AI tools on tasks in their own repositories, despite developers forecasting a 24 percent speedup and reporting a 20 percent speedup after the fact. The model generates work that pattern-matches "correct"; the human reads it as correct because the surface features match what correct work looks like in their domain. The mechanism is the same: a proxy (surface plausibility) stands in for a true objective (working code). Mitigation in both cases is structural: a verifier independent of the generator, decomposed metrics rather than a single aggregate score, ground-truth anchors that the generator cannot pattern-match against. The [METR follow-up study](https://metr.org/blog/2026-02-24-uplift-update/) returned an unreliable signal in late-2025 because the population had self-selected, which is itself informative about how fast the supervisory ergonomics are changing.

**Fleet coordination, characterised.** A specific empirical observation from running fleets: LLM-powered CRON-style schedulers are reasonably good at *reactive* stabilization (handling new emails, signals, alerts, occasional disruptions) and unreliable at *proactive* progress (driving a long-horizon goal forward across many sessions). The asymmetry is intuitive once stated. Stabilization is short-horizon and well-bounded; proactive progress requires holding state across sessions and recovering from drift, both of which are weak spots in current systems.

Past that single observation, the fleet rung is now measurable in a more disciplined way. The brain-level failures above each scale up with N:

| Brain-level failure | Fleet-level cost at scale N |
|---|---|
| Context degradation in one agent | N independent drift events instead of one |
| Catastrophic compaction in one agent | The same compaction error replicated N times when the workspace is shared |
| Adversarial compliance in one agent | Same-model judge ranks all N agents the same; failures are correlated, not independent |
| (Fleet-only) | Rediscovery tax: N independent fetches of the same fact unless the substrate is shared |
| (Fleet-only) | Topology mismatch: parallel work on tasks that were not decomposable produces latency, not throughput |

The practical consequence is to architect fleets for stabilization first, characterise the per-agent failure rates, and add proactive components only where the trajectory record is rich enough to recover from interruption.

---

## Containment is old engineering

When the agent takes its own actions, the unit of analysis stops being the model output and becomes the trajectory: plan, tool call, argument, observation, derived output. Governance has to attach to the trajectory at runtime, because static guarantees about arbitrary agent behavior are not available. **A prompt instruction cannot contain an agent; only the runtime around it can.**

This is not a new problem. [Saltzer and Schroeder (1975)](https://www.cs.virginia.edu/~evans/cs551/saltzer/) gave us the principle of least authority: each component receives only the privileges needed to do its job. [Rice's theorem (1953)](https://en.wikipedia.org/wiki/Rice%27s_theorem) says that any non-trivial semantic property of a Turing-complete program is undecidable in general. An agent with code execution is an arbitrary Turing-complete program, which rules out proving its behavior safe ahead of time and leaves instrumenting the runtime as the move that remains.

The current security landscape sharpens these principles:

- [Simon Willison's "lethal trifecta"](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/): an agent with private-data access, exposure to untrusted content, and an exfiltration vector is exploitable. The composition is the unit. Defending the components individually is not enough.
- [Nasr, Carlini, Sitawarin et al., "The Attacker Moves Second" (2025)](https://arxiv.org/abs/2510.09023) found that adaptive attacks defeat current prompt-injection defenses at high rates. Input filtering and constrained decoding are necessary, not sufficient.

The harder failure surface is self-modification. A long-running agent with tainted history (an instruction injected via a retrieved page two hours ago), GET/POST access, and code execution can in principle discover vulnerabilities, modify its own scaffolding, and persist outside the intended boundary. Vulnerability-discovery-en-masse and self-replication are the asymptotic concerns. Architectural containment is what holds: microVM execution (Firecracker, gVisor, container sandboxes), gateway-enforced egress, capability-shaped privilege. These are the same isolation mechanisms OS designers worked out in the 1970s, reapplied to a new kind of process.

A specific operational pattern to consider: a verdict-and-reason judge applied inline after each retrieval-grounded answer functions as runtime containment. In a regulated context, hallucination is the exfiltration of model parameters into the answer surface, so an inline faithfulness check sits as a runtime gate on that surface rather than as a separate evaluation step.

---

## The closed-interface observability problem

A subtler failure mode: most production agent harnesses, especially closed ones, do not expose the primitives an operator actually needs. Specifically, they hide forking (run a session from a saved state in two divergent directions), branching (reorder or replace messages and replay), and projection (view a structured slice of the trajectory aligned with the directive).

The reason is partly technical, partly competitive. Exposing these primitives makes the harness easier to operate. It also makes the harness easier to reverse-engineer, and a vendor whose moat is the harness has incentive to limit observability to compliance-minimum. **Opinion:** what gets framed as a compliance question is often a competitive decision in disguise. Closed harnesses will lag on this, and the lag will compound for any user who needs long-horizon agent operations.

There is a structural answer hiding in the same architectural shift Karpathy named. When the agent's bootstrap state is a folder of files, the primitives an operator wants reduce to ordinary file operations. The OpenClaw runtime reads its system prompt from `AGENTS.md`, `SOUL.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`, `HEARTBEAT.md`, and the `skills/` folder on every turn. Forking a session is `cp -r`. Branching is replaying an alternative `MEMORY.md` against the same skill library. Projection is reading the subset of files the directive depends on. Voyager's skill library is the same idea operationalised inside a runtime: the agent writes to its own files, the runtime reads them next turn, and the persistent belief lives somewhere a human can audit. Because the configuration and the conversation are reached through the same interface, a file-as-context runtime stays inspectable with the tools an operator already has.

The implications for engineering teams are concrete. **Put the source of truth for observability in the trajectory itself, and treat any dashboard as a view over it:**

- Adopt the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) (the `gen_ai.*` attribute namespace, agent and tool spans). It is a wire-format convention; route OTLP to whichever backend you want.
- Instrument trajectories as first-class artifacts on disk (JSONL is sufficient) and treat the harness as a renderer over those artifacts. This makes forking, branching, and replay trivially possible because the source of truth is the trace, not the harness state.

---

## Skill codification is memoization on trajectories

When a session walks a useful path through a problem, you save the path. The retrieval key is a description embedding. The cache value is a recipe. The next session that needs to walk a similar path retrieves it and adapts it. This is memoization with a learned similarity key, applied to agent trajectories. [Voyager](https://arxiv.org/abs/2305.16291) demonstrated it; agent-memory systems and procedural-knowledge formats are different names for the same mechanism.

The interesting property is compounding. **Each codified skill shortens the discovery walk for the class of sessions that would otherwise rediscover the same trail.** The underlying mechanic is worth spelling out. An agent session works like a discovery process: the agent enters an environment, finds beacons (tools, files, indexed corpora, peer endpoints), and each beacon it reaches reveals more, so the session walks a graph it did not know in advance. Codifying a skill pre-loads the right beacon set for the next session that needs it. Fleet management is the layer above all of this, running many such sessions under shared learning, observability, cost, and blast-radius controls.

The recursion deserves attention. Skill codification compresses fleet management into a tractable interface for a human supervisor. Once that compression is good enough, the fleet manager itself becomes a candidate for automation. There is no technical wall here, only governance and economic walls. The pattern: the human role moves from doing tasks, to writing skills, to shaping fleets, to defining objectives that fleets pursue.

There is a sociological floor on this, captured by Polanyi's observation in [The Tacit Dimension (1966)](https://en.wikipedia.org/wiki/The_Tacit_Dimension): "we know more than we can tell." Tacit knowledge resists codification. Skills can capture procedural knowledge; they struggle with the parts of expertise that experts cannot fully articulate. **Opinion:** the durable human role is at the boundary where tacit knowledge cannot yet be made explicit, and that boundary moves more slowly than current discourse implies.

---

## Sanctity of content is gone

Once an agent with internet access can ingest, re-synthesize, and re-publish, a clean-room boundary stops meaning much. The defenses people hoped would re-establish that boundary have not held up: training-data attribution research has yet to produce techniques that survive a motivated adversary, and watermarking proposals fall apart under adaptive attack. So anything published can be picked up and absorbed, whether deliberately or by accident, and an insight written into a blog post tends to resurface as an uncredited footnote inside a model's amalgamated answer.

The legal landscape is settling on a pattern. In [Bartz v. Anthropic (preliminarily approved September 25, 2025)](https://www.npr.org/2025/09/05/nx-s1-5529404/anthropic-settlement-authors-copyright-ai), Anthropic agreed to pay $1.5 billion (approximately $3,000 per work for ~500,000 works) on the *acquisition* leg of the case (downloading from LibGen and PiLiMi shadow libraries), while Judge Alsup's June 2025 summary judgment held that *training* on legally acquired books was transformative fair use. The pattern: training as transformative use, acquisition channel as the liability surface. NYT v. OpenAI is in active discovery on similar grounds.

For engineering teams, this means provenance metadata in retrieval corpora is becoming a contractual obligation rather than a quality-of-life feature. Substrate-level work (skills, tools, instrumentation, sandboxes) is where engineering value compounds, partly because that is where attribution still works.

---

# Part 2: Labor, sociology, and markets

*The technical argument ends here. What follows is about who builds the stack, who pays for it, and where the resulting value lands. A reader who only needs the operational material can stop at this line without missing any of it.*

---

## Labor, sociology, and the spectrum of beliefs

A question that comes up repeatedly from senior engineers: how do we expect the gains from agentic AI to distribute? Three positions cover most of the field.

- **The 100x developer thesis.** A small number of skilled developers using AI-saturated workflows produce dramatically more output than they did, displacing entry-level developers. The empirical signal is mixed. METR's RCT (above) found an aggregate slowdown in carefully-controlled OSS work; vendor case studies report large speedups in greenfield contexts. **Opinion:** both are likely true for different task profiles, and the headline-friendly version of this thesis overstates a real but bounded effect.
- **The do-more-with-more thesis.** Cheaper cognitive work expands the addressable market for cognitive work, and skilled humans plus capable agents produce dramatically more total output. Wages for top-tier skilled labor rise; the floor of cognitive labor rises but more people clear it because the tools meet them halfway. This is the expansionist reading.
- **The codify-everything-for-the-experts thesis.** Skill codification accumulates the procedural knowledge of expert workers into reusable artifacts. This compounds advantage for the firms that capture the codification but creates a question about how value flows back to the experts whose work was codified.

[Acemoglu and Restrepo's task-based AI labor framework (NBER, 2024)](https://www.nber.org/papers/w32487) sharpens the underlying question: AI can either *automate* tasks (substituting for labor) or *create new tasks* (complementing labor). The historical record on transitions of comparable scale (electrification, internet, assembly line) shows that new-task creation has dominated the substitution effect over decades, with significant short-term displacement. Whether AI follows that pattern depends on whether the new tasks emerge fast enough and whether organizations and workers have time to adapt.

The empirical evidence so far is mostly null on aggregate effects. [Humlum and Vestergaard (NBER w33777, 2025)](https://www.nber.org/papers/w33777) examined 11 AI-exposed occupations in Denmark across 25,000 workers and 7,000 workplaces, and found null effects on earnings and recorded hours, ruling out effects larger than 2 percent two years after ChatGPT's release. What changed was the structure of work itself: new tasks in content generation, AI oversight, AI integration; workers transitioning into higher-paying occupations where AI is more relevant. The pattern is consistent with the do-more-with-more reading at the firm level (productivity J-curve) without yet showing up in aggregate wages, which is what the slow-organizational-change literature predicts.

The pessimistic reading is real. Wealth and power consolidation could concentrate the gains in the firms that own the substrate. Entry-level cognitive jobs (a major rung in the labor mobility ladder) could thin without compensating new entry points. The honest counterweight is that policy levers exist: UBI proposals (Altman's Worldcoin, Yang's earlier writings), wage insurance, retraining grants, EITC expansions, and the more abstract framing of decoupling reward from necessary task performance. These are political choices, not technical ones.

**Opinion:** the most defensible reading of the evidence so far is that the floor of cognitive labor is rising (sophisticated work becomes the baseline) and that the optimistic positive-sum framing requires both technical investment in the substrate and policy adaptation. The pessimistic framing (rapid hollowing without compensating new opportunities) is possible but is not the historical base rate. For engineers, the practical implication is that the skill of supervising and shaping agentic work is becoming the core skill of mid-to-senior engineering, and the transition is a training and ergonomics problem we are early in solving.

---

## The market frame: elasticity, Jevons, and Wright's law

It helps to read the AI infrastructure story through the demand it serves rather than as a standalone cost of buildout. Two foundational ideas set that reading up.

**Wright's law (experience curves).** Cost per unit drops by a roughly constant percentage with each doubling of cumulative production. The [IEA's April 2026 "Key Questions on Energy and AI" report](https://www.iea.org/news/data-centre-electricity-use-surged-in-2025-even-with-tightening-bottlenecks-driving-a-scramble-for-solutions) characterizes per-task AI energy efficiency as improving by *at least an order of magnitude annually* over recent years, "a rate believed to be unprecedented in energy history." Hardware power density of AI servers grew 11x between 2020 and 2025, with another 4x projected by 2027. Per-task cost is collapsing.

**Jevons paradox.** First articulated in [Jevons, *The Coal Question* (1865)](https://en.wikipedia.org/wiki/Jevons_paradox): when the price of a useful resource falls, demand expands faster than the price drop, so total consumption grows. Cheaper electricity expanded electric demand; cheaper bandwidth expanded internet use; cheaper compute expanded software. Cheaper inference is expanding cognitive workloads. The IEA data captures the result: data-center electricity demand grew 17 percent in 2025 against 3 percent for global electricity, and AI-focused data center demand grew 50 percent. Aggregate data-center electricity is projected to roughly double by 2030, with AI-specific demand tripling.

The market reading: per-task cost is dropping order-of-magnitude annually, and total demand is rising faster, which means the addressable consumer market for AI capabilities is expanding by more than an order of magnitude per year. Infrastructure buildout is downstream of that expansion, not upstream. Capex from the five largest cloud and tech firms reached more than $400 billion in 2025 with a projected 75 percent increase in 2026 (per the same IEA report). The constraint is supply chains for power electronics, transformers, and grid interconnects, not demand for the underlying capability. **The infrastructure floor under all this is utility-shaped: high fixed cost, low marginal cost, capacity-constrained, with cost curves that compound across cumulative production.**

Two strategic postures follow:

- **Do-more-with-more.** Invest across the stack (compute, networking, software, reference workflows, ecosystem partners). Bet that demand for cognitive work is elastic and will absorb capacity faster than it can be built. The historical track record on transitions of comparable scale favors this bet, without guaranteeing it.
- **Do-less-with-less.** Cut headcount and capacity in the name of AI productivity, betting that demand is fixed and the gains accrue to whoever holds the labor-saving technology.

NVIDIA's posture, fairly read, sits closer to the do-more-with-more variant: hardware-centric (Blackwell, Rubin, NVLink, Mellanox-derived networking), with the software layer ([CUDA](https://developer.nvidia.com/cuda-toolkit) maintained as an ecosystem standard, [NIM inference microservices](https://www.nvidia.com/en-us/ai/inference-platform/), [NeMo open-source components](https://github.com/NVIDIA/NeMo), reference workflows, the [Inception startup program](https://www.nvidia.com/en-us/startups/)) cultivated as substrate that the broader ecosystem builds on. **Opinion:** the bet encoded in this posture is that the addressable market grows faster when more developers, startups, and partners can build on top of the platform, compared with a single-vendor extraction model. The historical track record on growth-period transitions supports the cultivator side without resolving the question.

Honest counterweights remain real: market-cap concentration is a fragility, export controls have already cost NVIDIA billions in disclosed revenue, and one supplier sitting under an entire computing paradigm is a systemic risk. These sit behind the larger question of whether the market is being grown or extracted from, but any of them can move to the front if it compounds far enough.

[Fatih Birol's framing in the IEA report](https://www.iea.org/news/data-centre-electricity-use-surged-in-2025-even-with-tightening-bottlenecks-driving-a-scramble-for-solutions) captures the loop: "AI is still an energy taker, [but] it is also becoming an energy maker, driving forward innovative solutions like next-generation nuclear reactors, flexible data centers and long-duration energy storage." The buildout is funding the next generation of energy infrastructure, which is what market expansion driven by real demand looks like rather than value pulled out of a fixed pie.

---

## Recipes

Concrete procedures that motivate the patterns above. Each is small enough to apply this week, and each lives in the substrate the post has been arguing for: tool surfaces, trajectory records, skill libraries, runtime instrumentation, sandboxes, observability primitives.

**Recipe 1: Trajectory as a first-class artifact.** Instrument every agent session as a structured record (JSONL with directive, plan, tool calls, observations, verdict, reason). Persist trajectories to disk. Treat the harness as a renderer over the trace, not the source of truth. Forking, branching, and replay become trivial.

**Recipe 2: Pinned-directive compaction.** When summarizing long sessions, preserve the directive verbatim. Summarize observations only. Verify the compacted state against the un-compacted state at session boundaries. This mitigates catastrophic compaction without requiring larger context windows.

**Recipe 3: Inline verdict-and-reason.** After each retrieval-grounded answer, run a faithfulness judge that returns a two-line verdict (`GROUNDED|PARTIAL|FABRICATED`) and a one-sentence reason. Use the verdict as a runtime gate, not a post-hoc evaluation.

**Recipe 4: Forking observability.** Build forking, branching, and projection as primitive operations on the trajectory log. Adopt the OpenTelemetry GenAI semantic conventions for the wire format. A trace that can be forked at any step and replayed with modified inputs is worth more than any vendor's debugging UI.

**Recipe 5: Capability-shaped sandboxing.** Each tool gets the minimum privileges it needs. Code execution runs in a microVM (Firecracker, Modal, E2B, Daytona). Egress is gateway-enforced and policy-governed, not application-level. The principle of least authority predates the LLM by 50 years and is still correct.

**Recipe 6: Skill codification with paraphrase-augmented retrieval keys.** When promoting a successful trajectory to a reusable skill, have the codifier generate a description *and* 3 to 5 paraphrased directive variants the skill should match. Embed all of them as retrieval keys for the same skill. This mitigates the most common failure mode: descriptions that are too narrow miss applicable future tasks.

---

## The frame, briefly

The control flow inverted because tool-use plus a critic loop covers a strictly larger task class than a model alone. The substrate underneath that inversion is small: plan, act, observe, reflect, with pinned context, demonstrated by ReAct, ReWoo, Reflexion, and Voyager. From there the post mapped the agent onto the role of a process and the harness onto the operating system around it, treated the framework abstractions in between as glue to be replaceable, and argued that what composition pattern lasts is convergence on thin capability-description conventions.

The recurring failure modes are well-mapped and the mitigations are mostly old: context degradation, catastrophic compaction, adversarial compliance with the supervisor problem as its human-scale form, and the asymmetry where CRON-style fleets stabilize well and drive proactive progress poorly. A prompt instruction cannot contain an agent, so containment has to live in the runtime around it. Observability has its source of truth in the trajectory on disk, with any dashboard a view layered over that. A codified skill is a memoized trajectory that shortens the discovery walk for the sessions that follow it, and fleet management is the recursive layer over many such sessions.

Clean-room provenance no longer holds, so provenance metadata in retrieval corpora is on its way to being contractual. The labor signal so far is null on aggregate effects (Humlum and Vestergaard) and rich on structural reorganization (Acemoglu's task-based framing). The infrastructure floor is utility-shaped, and consumer market expansion is downstream of falling per-task costs acting through Jevons paradox. A company that cultivates the substrate to grow the addressable market is betting that demand is elastic; one that cuts to extract from a market it assumes is fixed is betting the other way, and the historical base rate favors the cultivators without guaranteeing them.

**The argument, restated.** Engineering value accumulates in the substrate: tool surfaces, trajectory records, skill libraries, runtime instrumentation, sandboxes, and observability primitives. It accumulates less in the framework abstractions above that layer and less in the model weights below it. The teams that build there, codify what works, instrument what runs, and let the compounding play out will outperform the teams stacking larger one-shot prompts on churning frameworks. That position rests on the structure of the problem, the falling per-task cost curve, the historical track record of comparable transitions, and the empirical signal so far.

---

## Sources

- Wang et al., "Voyager: An Open-Ended Embodied Agent with Large Language Models" (2023). [https://arxiv.org/abs/2305.16291](https://arxiv.org/abs/2305.16291)
- Yao et al., "ReAct: Synergizing Reasoning and Acting in Language Models" (2022). [https://arxiv.org/abs/2210.03629](https://arxiv.org/abs/2210.03629)
- Xu et al., "ReWoo: Decoupling Reasoning from Observations for Efficient Augmented Language Models" (2023). [https://arxiv.org/abs/2305.18323](https://arxiv.org/abs/2305.18323)
- Shinn et al., "Reflexion: Language Agents with Verbal Reinforcement Learning" (2023). [https://arxiv.org/abs/2303.11366](https://arxiv.org/abs/2303.11366)
- Wei et al., "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models" (2022). [https://arxiv.org/abs/2201.11903](https://arxiv.org/abs/2201.11903)
- Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" (2020). [https://arxiv.org/abs/2005.11401](https://arxiv.org/abs/2005.11401)
- Liu et al., "Lost in the Middle" (2024). [https://arxiv.org/abs/2307.03172](https://arxiv.org/abs/2307.03172)
- Hsieh et al., "RULER: What's the Real Context Size of Your Long-Context Language Models?" (2024). [https://arxiv.org/abs/2404.06654](https://arxiv.org/abs/2404.06654)
- Becker, Rush, Barnes, Rein, "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity" (METR, 2025). [https://arxiv.org/abs/2507.09089](https://arxiv.org/abs/2507.09089) ; [https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)
- Humlum and Vestergaard, "Still Waters, Rapid Currents: Early Labor Market Transformation under Generative AI" (NBER w33777, 2025). [https://www.nber.org/papers/w33777](https://www.nber.org/papers/w33777)
- Acemoglu and Restrepo, "Tasks, Automation, and the Rise in U.S. Wage Inequality" (NBER, 2024). [https://www.nber.org/papers/w32487](https://www.nber.org/papers/w32487)
- Bratman, *Intention, Plans, and Practical Reason* (Harvard University Press, 1987).
- Rao and Georgeff, "Modeling Rational Agents within a BDI-Architecture" (KR, 1991). [https://www.aaai.org/Library/KR/1991/kr91-049.pdf](https://www.aaai.org/Library/KR/1991/kr91-049.pdf)
- Saltzer and Schroeder, "The Protection of Information in Computer Systems" (Proceedings of the IEEE, 1975). [https://www.cs.virginia.edu/~evans/cs551/saltzer/](https://www.cs.virginia.edu/~evans/cs551/saltzer/)
- Willison, "The lethal trifecta for AI agents" (2025). [https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- Nasr, Carlini, Sitawarin et al., "The Attacker Moves Second" (2025). [https://arxiv.org/abs/2510.09023](https://arxiv.org/abs/2510.09023)
- IEA, "Key Questions on Energy and AI" (April 2026). [https://www.iea.org/reports/key-questions-on-energy-and-ai](https://www.iea.org/reports/key-questions-on-energy-and-ai)
- Bartz v. Anthropic, NPR coverage (September 5, 2025). [https://www.npr.org/2025/09/05/nx-s1-5529404/anthropic-settlement-authors-copyright-ai](https://www.npr.org/2025/09/05/nx-s1-5529404/anthropic-settlement-authors-copyright-ai)
- Polanyi, *The Tacit Dimension* (1966).
- Jevons, *The Coal Question* (1865).
- Karpathy, "LLMs as kernel process of a new OS" (2023). [https://x.com/karpathy/status/1707437820045062561](https://x.com/karpathy/status/1707437820045062561)
- Anthropic, Computer Use announcement. [https://www.anthropic.com/news/3-5-models-and-computer-use](https://www.anthropic.com/news/3-5-models-and-computer-use)
- Anthropic Model Context Protocol. [https://modelcontextprotocol.io](https://modelcontextprotocol.io)
- Google Agent2Agent (A2A) Protocol. [https://google.github.io/A2A/](https://google.github.io/A2A/)
- Anthropic Agent Skills documentation. [https://docs.anthropic.com/en/docs/build-with-claude/agent-skills](https://docs.anthropic.com/en/docs/build-with-claude/agent-skills)
- OpenTelemetry GenAI semantic conventions. [https://opentelemetry.io/docs/specs/semconv/gen-ai/](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- Language Server Protocol. [https://microsoft.github.io/language-server-protocol/](https://microsoft.github.io/language-server-protocol/)

## Foundational references the course builds on

The modules cite these directly; they are listed here so the curated reference layer vouches for every source the course teaches (transformer foundations, tool use, structured generation, evaluation, and multi-agent systems).

- Sennrich et al., "Neural Machine Translation of Rare Words with Subword Units" (2015). [https://arxiv.org/abs/1508.07909](https://arxiv.org/abs/1508.07909)
- Vaswani et al., "Attention Is All You Need" (NeurIPS 2017). [https://arxiv.org/abs/1706.03762](https://arxiv.org/abs/1706.03762)
- Brown et al., "Language Models are Few-Shot Learners" (GPT-3, NeurIPS 2020). [https://arxiv.org/abs/2005.14165](https://arxiv.org/abs/2005.14165)
- Karpas et al., "MRKL Systems: Modular Reasoning, Knowledge and Language" (2022). [https://arxiv.org/abs/2205.00445](https://arxiv.org/abs/2205.00445)
- Liang et al., "Holistic Evaluation of Language Models (HELM)" (2022). [https://arxiv.org/abs/2211.09110](https://arxiv.org/abs/2211.09110)
- Schick et al., "Toolformer: Language Models Can Teach Themselves to Use Tools" (2023). [https://arxiv.org/abs/2302.04761](https://arxiv.org/abs/2302.04761)
- Liu et al., "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment" (2023). [https://arxiv.org/abs/2303.16634](https://arxiv.org/abs/2303.16634)
- Park et al., "Generative Agents: Interactive Simulacra of Human Behavior" (2023). [https://arxiv.org/abs/2304.03442](https://arxiv.org/abs/2304.03442)
- Zheng et al., "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena" (NeurIPS 2023). [https://arxiv.org/abs/2306.05685](https://arxiv.org/abs/2306.05685)
- Willard & Louf, "Efficient Guided Generation for Large Language Models" (Outlines, 2023). [https://arxiv.org/abs/2307.09702](https://arxiv.org/abs/2307.09702)
- Hong et al., "MetaGPT: Meta Programming for a Multi-Agent Collaborative Framework" (2023). [https://arxiv.org/abs/2308.00352](https://arxiv.org/abs/2308.00352)
- Wu et al., "AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation" (2023). [https://arxiv.org/abs/2308.08155](https://arxiv.org/abs/2308.08155)
- Saad-Falcon et al., "ARES: An Automated Evaluation Framework for RAG Systems" (2024). [https://arxiv.org/abs/2403.02419](https://arxiv.org/abs/2403.02419)
- Cemri et al., "Why Do Multi-Agent LLM Systems Fail?" (MAST taxonomy, NeurIPS 2025). [https://arxiv.org/abs/2503.13657](https://arxiv.org/abs/2503.13657)
