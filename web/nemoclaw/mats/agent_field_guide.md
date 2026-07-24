# The agent builder's field guide

*An annotated reading map for the NemoClaw "Securing Agents" course. The course teaches the moves; this guide points at the papers and standards each move came from, grouped the way the course unfolds, so you can read the primary sources alongside the modules.*

> **Companion read.** The two essays in this folder argue positions. [The Agentic Equilibrium](./agentic_equilibrium.md) reads where the substrate is settling and which failure modes recur. [Agentic Safety in Production](./agentic_safety_in_production.md) lays out the safety architecture that hardens that substrate. This guide makes no argument of its own; it is the bibliography underneath both essays, covering what each cited work actually did and why it matters when you are building or securing an agent. Use it to find your way to the sources rather than to be persuaded of anything. When a source carries an opinion worth flagging, it is flagged.

The course arc moves from a single reasoning loop, to tools, to retrieval, to memory and long-horizon autonomy, and finally to containment. The groups below follow that arc. For each source there is one line on the contribution and one or two on why it shows up where it does.

---

## Loop foundations

Module 1 starts with conventional search before replacing its decision rule with a model. These references define the algorithms and browser/API boundaries used in that comparison.

- [Artificial Intelligence: A Modern Approach resources](https://aima.cs.berkeley.edu) provide the agent taxonomy behind the introductory loop.
- [Breadth-first search](https://en.wikipedia.org/wiki/Breadth-first_search), [depth-first search](https://en.wikipedia.org/wiki/Depth-first_search), and [A* search](https://en.wikipedia.org/wiki/A*_search_algorithm) define the deterministic strategies used in the maze examples.
- The [Chat Completions](https://platform.openai.com/docs/api-reference/chat) and [Responses](https://platform.openai.com/docs/api-reference/responses) references document the two model request shapes compared in the course.
- The [MDN CORS guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS) explains the browser boundary that motivates the course relay.

---

## Reasoning and acting

The first modules build the agent loop itself: a model that reasons about what to do, takes an action, looks at the result, and decides again. These five papers are the moves inside that loop. They are short and worth reading in order.

- [**ReAct: Synergizing Reasoning and Acting in Language Models**](https://arxiv.org/abs/2210.03629) (Yao et al., 2022). Interleaves a reasoning trace and a tool action in the same decoding loop, so the model thinks, acts, observes, and thinks again rather than reasoning once and answering. This is the loop the course's `01b-react` module implements directly; almost every production agent is some elaboration of it. Reading it first makes the rest of the course legible, because every later pattern is either an optimization of this loop or a guardrail around it.

- [**Chain-of-Thought Prompting Elicits Reasoning in Large Language Models**](https://arxiv.org/abs/2201.11903) (Wei et al., 2022). Shows that prompting a model to produce intermediate reasoning steps before its answer sharply improves multi-step arithmetic, commonsense, and symbolic tasks. It is the reasoning half of ReAct on its own. The caution to carry into the course: the intermediate steps can be wrong while looking right, and the final answer compounds the error, which is why later modules gate reasoning with verification rather than trusting longer chains.

- [**ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models**](https://arxiv.org/abs/2305.18323) (Xu et al., 2023). Splits the loop into a planner that writes the full plan up front, workers that run the tool calls, and a solver that assembles the result, so the model is not re-fed every observation on every step. The paper reports roughly 5x fewer tokens and a small accuracy gain on multi-step QA. It matters when the action space is known in advance and the interleaved ReAct loop is paying for context it does not need; the course contrasts the two so you can pick per task.

- [**Plan-and-Solve Prompting**](https://arxiv.org/abs/2305.04091) (Wang et al., 2023). A zero-shot prompt that first asks the model to devise a plan of subtasks and then to carry them out, which fixes the "missing step" failures of plain chain-of-thought without any examples. It is the smallest possible version of plan-then-act, useful as a baseline before reaching for a full multi-agent planner. The course uses the planning/execution split it names as the conceptual bridge from a single reasoning call to an orchestrated agent.

- [**Self-Refine: Iterative Refinement with Self-Feedback**](https://arxiv.org/abs/2303.17651) (Madaan et al., 2023). The same model generates an answer, critiques its own answer, and revises, with no extra training. It is the self-correction primitive behind the course's critic and review steps. The structural warning the course inherits from it: a generator critiquing itself shares the generator's blind spots, so the gains are real but bounded, and a verifier that is independent of the generator is stronger where you can afford one.

---

## Tools and structure

Up to here the agent can only produce text. The next modules give it tools, and the question becomes how the model emits a tool call the runtime can actually execute. These three sources cover the idea, the open protocol, and the concrete wire format.

- [**Toolformer: Language Models Can Teach Themselves to Use Tools**](https://arxiv.org/abs/2302.04761) (Schick et al., 2023). Trains a model to decide which API to call, when, and with what arguments, learning the call sites in a self-supervised way from a handful of demonstrations per tool. It is the research root of tool use: the model treats an external call as part of generation rather than as a bolt-on. The course teaches the prompted, schema-driven descendant of this idea, but Toolformer is where the framing of "the tool call is part of the model's output distribution" comes from.

- [**Model Context Protocol**](https://modelcontextprotocol.io) (Anthropic, 2024). An open protocol that standardizes how a model connects to tools, data sources, and prompts through a single client/server convention rather than one bespoke integration per tool. It matters because once enough capabilities speak the same shape they compose without per-pair glue, which is the property the course relies on when it wires an agent to multiple services. Treat the spec as the interface contract; the specific server you connect to is replaceable behind it.
- [**MCP security best practices**](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices) (MCP project). Tool discovery is not trust establishment: clients need explicit consent, minimal scopes, audience-bound credentials, and SSRF controls before they connect a discovered capability to private data or execution.

- [**Function calling**](https://platform.openai.com/docs/guides/function-calling) (OpenAI platform documentation). The concrete request/response format for declaring tools as JSON schemas and getting back structured, parseable tool calls the runtime can dispatch. This is the wire format the course's tool modules use in practice; reading it removes the mystery from how a natural-language reasoning step becomes a deterministic function invocation. The schema is also the first place to enforce least privilege, since the model can only call tools it has been handed a schema for, and withholding the schema withholds the capability.

---

## Retrieval

Without a way to look things up, an agent is stuck with whatever its training cutoff and context window hold. The retrieval modules ground it in an external corpus instead. These four sources are the generation pattern, the retriever that powers it, a query-side improvement, and the index that makes it fast at scale.

- [**Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks**](https://arxiv.org/abs/2005.11401) (Lewis et al., 2020). Pairs a parametric model with a non-parametric retriever so the model conditions its answer on documents pulled at query time. This is the architecture behind every "answer from my documents" feature, and the course's index modules are a direct application. The durable point for a builder is the separation of concerns: the corpus can change without retraining the model, which is why most teams reach for retrieval before fine-tuning when an agent needs fresh knowledge.

- [**Dense Passage Retrieval for Open-Domain Question Answering**](https://arxiv.org/abs/2004.04906) (Karpukhin et al., 2020). Shows that learned dense embeddings of questions and passages beat sparse keyword retrieval (BM25) on open-domain QA by a wide margin. It is the retriever half of RAG made concrete: encode the query and the passages into the same vector space and rank by similarity. Once DPR clicks, embedding choice, chunking, and similarity search read as tunable engineering decisions with understandable failure modes.

- [**Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE)**](https://arxiv.org/abs/2212.10496) (Gao et al., 2022). Has the model write a hypothetical answer to the query first, then embeds that hypothetical document to retrieve real ones, which closes the vocabulary gap between short questions and long passages. It works with no relevance-labeled training data, which is the common case in practice. The course reaches for it when raw query embeddings under-retrieve; the hallucinated details in the hypothetical document get filtered out by the encoder, and the semantic shape is what survives to drive the search.

- [**Billion-scale similarity search with GPUs (FAISS)**](https://arxiv.org/abs/1702.08734) (Johnson et al., 2017). The library and methods for approximate nearest-neighbor search over very large vector sets on GPUs, which is what makes dense retrieval tractable past a toy corpus. It is the index sitting under the course's retrieval demos. The thing to internalize is that this layer is an approximation with a speed/recall knob, so when retrieval quality disappoints the cause can sit in the index tuning and not only in the embeddings.

---

## Memory and long-horizon autonomy

Once an agent runs for hours or persists across sessions, the hard part is no longer producing any single answer but managing its accumulated state: what it has retained, what it has learned to do, and what has dropped out of context without anyone noticing. The kickstart and always-on modules live here. Three of these works build long-horizon capability; the fourth explains the failure that bounds all of them.

- [**MemGPT: Towards LLMs as Operating Systems**](https://arxiv.org/abs/2310.08560) (Packer et al., 2023). Borrows virtual-memory management from operating systems: a fixed in-context "main memory" plus a larger external store, with the agent paging information in and out as needed to act as if it had unbounded context. This is the reference design for agent memory the always-on modules build toward. The framing matters because it turns "the context window is too small" from a hard wall into a memory-management problem with known techniques.

- [**Voyager: An Open-Ended Embodied Agent with Large Language Models**](https://arxiv.org/abs/2305.16291) (Wang et al., 2023). An agent in Minecraft that proposes its own curriculum, writes reusable skills as code into a growing library, and refines them with an iterative critic, all with no gradient updates. It is the canonical demonstration of an agent that gets better at a domain by accumulating its own tools. The skill-library idea is exactly what the course's persistent-agent modules operationalize: a successful trajectory becomes a saved recipe the next session retrieves and adapts.

- [**Generative Agents: Interactive Simulacra of Human Behavior**](https://arxiv.org/abs/2304.03442) (Park et al., 2023). A small simulated town of agents that remember events, reflect to form higher-level conclusions, and plan from those reflections, producing believable long-horizon behavior. Its contribution to a builder is the memory architecture: a stream of observations plus a retrieval scoring that weighs recency, importance, and relevance, plus periodic reflection. The course draws on this when an always-on agent needs to decide what is worth keeping rather than logging everything flat.

- [**Lost in the Middle: How Language Models Use Long Contexts**](https://arxiv.org/abs/2307.03172) (Liu et al., 2023). Demonstrates that models attend well to information at the start and end of their context and systematically under-attend to the middle, so a longer window does not mean uniform use of it. This is the empirical reason the memory designs above exist: you cannot fix drift by stuffing more into context, because the middle gets ignored. The course returns to this finding whenever it argues for pinned directives and structured compaction over bigger windows, and it sets up the later point that safety has to be enforced by containment, since a larger prompt is exactly the lever this paper shows does not work.

---

## Security and containment

The final modules accept that a capable agent with tools, a filesystem, and network access is an arbitrary program, so safety cannot be a prompt. It has to be enforced below the agent, in the runtime and the kernel. These sources are the threat models and the enforcement primitives. They are the intellectual core of the "securing" half of the course title.

- [**Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection**](https://arxiv.org/abs/2302.12173) (Greshake et al., 2023). Names indirect prompt injection: adversarial instructions planted in content the agent retrieves (a web page, an email, a document) that the agent then executes as if they were its own directives. It is the attack the course's containment modules are built against, because the agent has no reliable way to tell trusted instructions from injected ones in the text it reads. The lesson is that the input channel itself is hostile, so defenses have to assume the prompt is already poisoned.
- [**OWASP Top 10 for Agentic Applications**](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/) (OWASP GenAI Security Project, 2025). Separates goal hijack, tool misuse, identity abuse, supply-chain compromise, unexpected code execution, and memory poisoning so each failure can be assigned to the layer capable of enforcing its control.

- [**The lethal trifecta for AI agents**](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) (Simon Willison, 2025). Frames the dangerous combination crisply: an agent with access to private data, exposure to untrusted content, and a way to send data out is exploitable, and the danger is the composition, not any one part. It is the threat model the course uses to reason about what a sandbox must cut. The practical payoff is that you can audit an agent by checking which of the three legs it has, and break the trifecta by removing one rather than trying to make each leg individually safe.

- [**The Protection of Information in Computer Systems**](https://www.cs.virginia.edu/~evans/cs551/saltzer/) (Saltzer and Schroeder, 1975). The foundational statement of security design principles, including least privilege, fail-safe defaults, and complete mediation, written for time-sharing systems half a century ago. The course leans on it to make the point that agent containment is old engineering reapplied: deny by default, grant only what is needed, mediate every access. Reading the original is worth the time because the principles are stated more sharply there than in any modern restatement, and they map cleanly onto sandbox policy.

- [**Landlock: unprivileged access control**](https://docs.kernel.org/userspace-api/landlock.html) (Linux kernel documentation). A Linux security module that lets an unprivileged process restrict its own filesystem and network access by building a ruleset and locking itself into it, enforced by the kernel for the process and its children. This is one of the kernel primitives the course's sandbox uses to scope what files an agent can touch. It matters because the restriction holds regardless of what the model reasons or what an injected instruction tells it to do; the enforcement is below the application entirely.

- [**Seccomp BPF (SECure COMPuting with filters)**](https://docs.kernel.org/userspace-api/seccomp_filter.html) (Linux kernel documentation). Lets a process install a filter over the system calls it is allowed to make, so a sandboxed agent can be denied entire classes of operations at the syscall boundary. Paired with Landlock, it answers the other half of "what can this process do": Landlock scopes which files and hosts, seccomp scopes which kernel operations. Together they are how the course enforces containment that the agent cannot argue, inject, or reason its way around.

- [**Open Policy Agent**](https://www.openpolicyagent.org/docs/latest/) (CNCF project documentation). A general-purpose policy engine that decouples policy decisions from enforcement: your runtime asks OPA a question with structured input, OPA evaluates declarative Rego rules, and returns a decision the runtime acts on. The course uses this shape for egress and tool policy so that what the agent is allowed to reach is a reviewed, versioned artifact rather than a setting buried in code. **Opinion:** the decoupling is the whole value here. When the policy is data evaluated outside the agent, you can audit it, test it, and change it without touching the agent, which is exactly the property an agent's permissions should have.

---

## How to read this alongside the course

Take each group at the module where the course raises it, and read the one paper that names the move you are about to implement before you implement it. ReAct before the loop module, RAG and DPR before the retrieval modules, the trifecta and Saltzer-Schroeder before the containment modules. For the larger interpretation of what all of it adds up to, the two essays in this folder are the place to go. The sources collected here stay closer to the ground: each one records what was actually built and measured, so when a module simplifies something for teaching, you can find where the full version lives.
