# NVIDIA agent glossary: a quick reference

*NVIDIA's canonical definitions for the terms this course leans on, distilled for quick lookup. Entries are grouped by what they do (agents and reasoning; models, inference, and serving; retrieval and grounding; safety and control), and each one gives the core definition with its source, a line on where the term lands in the course, and links to the related entries. The deeper reading map, with the primary papers behind each move, is in [the agent builder's field guide](./agent_field_guide.md).*

> **How to read this.** Treat this as a lookup table rather than a piece to read through. Each entry is paraphrased from NVIDIA's published pages, cited inline and listed in full under [Sources](#sources). The source pages are vendored under [`glossary_raw/`](./glossary_raw/README.md), so every definition keeps a primary source you can read in full and check the paraphrase against. The *Related* line under an entry points to the other terms it leans on, so you can follow a concept to its parts without leaving the page. For the research behind a term, follow the field guide; for the opinionated reading of where the stack is settling, read [the agentic equilibrium](./agentic_equilibrium.md).

---

## Agents and reasoning

### AI agents (autonomous agents)

NVIDIA defines autonomous agents as AI systems that reason, plan, and execute multi-step tasks toward a goal, built with security, privacy, and policy controls so they are safer to develop and deploy. The line that separates them from a plain model is orchestration: rather than the request-and-respond pattern of a standalone generative model, an agent is a system of models that coordinates with other agents and reaches for tools such as LLMs, retrieval-augmented generation, vector databases, APIs, and code. The glossary names the recurring parts: an LLM as the reasoning core that plans and selects tools, memory modules for short- and long-term context, planning modules that decompose work into steps, the tools themselves, and guardrails (sandboxes, identity controls, policy engines) that bound what the agent may do ([NVIDIA, "AI Agents"](https://www.nvidia.com/en-us/glossary/ai-agents/)).

*In the course:* this is the whole subject. The agent loop the early modules build (model reasons, calls a tool, observes, decides again) is exactly this definition assembled from parts, and the later containment modules are the guardrails layer made concrete.
*Related:* [Agentic AI](#agentic-ai), [AI reasoning](#ai-reasoning), [Deep agents](#deep-agents), [Large language model (LLM)](#large-language-model-llm), [Retrieval-augmented generation (RAG)](#retrieval-augmented-generation-rag), [Vector database](#vector-database), [Guardrails (NeMo Guardrails)](#guardrails-nemo-guardrails).

### Agentic AI

The standalone "What is agentic AI" blog now redirects to NVIDIA's AI Agents glossary, so its canonical definition is the same one above: AI systems that reason, plan, and act on a goal across multiple steps, distinguished from generative AI by the shift away from a single request-and-respond exchange toward orchestration over tools, memory, and other agents ([NVIDIA, "AI Agents"](https://www.nvidia.com/en-us/glossary/ai-agents/)). "Agentic" names the property, and an AI agent is the system that carries it. NVIDIA draws the line at what the system does with a prompt: a generative model returns an answer to it, while an agentic system treats the prompt as an objective and works out for itself which steps and tools get there.

*In the course:* "agentic" names the architecture shift the whole arc teaches, where a one-shot completion gives way to a plan-act-observe loop that the modules build up one capability at a time.
*Related:* [AI agents (autonomous agents)](#ai-agents-autonomous-agents), [AI reasoning](#ai-reasoning).

### AI reasoning

NVIDIA describes AI reasoning as how a system analyzes and solves a problem by weighing possible outcomes and choosing the best one, in a way that resembles human decision-making. The practical difference from a conventional LLM is where the work happens: a standard generative model answers quickly from statistical likelihood, while a reasoning model "thinks before speaking," spending several inference passes to work through a problem step by step. That extra deliberation is expensive. NVIDIA notes that a hard query can demand more than a hundred times the compute of a single pass on an ordinary LLM, and that on tasks like generating custom code a reasoning model may run for minutes or longer to reach its best answer ([NVIDIA, "AI Reasoning"](https://www.nvidia.com/en-us/glossary/ai-reasoning/)).

*In the course:* reasoning is the inner step of the agent loop, and the cost it carries is why the course gates reasoning chains with verification rather than simply asking for longer ones.
*Related:* [AI agents (autonomous agents)](#ai-agents-autonomous-agents), [Large language model (LLM)](#large-language-model-llm), [AI inference](#ai-inference).

### Deep agents

NVIDIA defines deep agents as AI agents designed for complex, long-running work, combining explicit planning, persistent memory, tool execution, reusable skills, and subagent delegation to decompose tasks, track progress, and act on their own over time. The contrast the glossary draws is with shallow agents, which run a reactive loop confined to the context window and fail once that window overflows or the goal degrades under accumulated noise. A deep agent instead maintains and updates a task list rather than blindly retrying, hands decomposed subtasks to specialized subagents with isolated context, uses a file system as external memory, and carries a system prompt that sets its decision thresholds. NVIDIA's framing: where a shallow agent reasons step by step inside its context window, a deep agent explicitly plans, tracks progress, and adapts like a project manager coordinating specialists, which lets it run reliably across hundreds of steps ([NVIDIA, "Deep Agents"](https://www.nvidia.com/en-us/glossary/deep-agents/)).

*In the course:* this is the long-horizon end of the arc. The memory and autonomy modules are the deep-agent pillars (planning, persistent file memory, subagent delegation) built one at a time, and the failure the definition names (context overflow and goal degradation) is the one the containment work is meant to survive.
*Related:* [AI agents (autonomous agents)](#ai-agents-autonomous-agents), [Retrieval-augmented generation (RAG)](#retrieval-augmented-generation-rag), [Guardrails (NeMo Guardrails)](#guardrails-nemo-guardrails).

---

## Models, inference, and serving

### Large language model (LLM)

NVIDIA defines large language models as deep learning algorithms that can recognize, summarize, translate, predict, and generate content using very large datasets. They are a class of transformer networks, the architecture introduced in Google's 2017 paper "Attention Is All You Need," which uses self-attention and positional encoding to track relationships across a sequence rather than processing it strictly in order. An LLM is trained by unsupervised learning over internet-scale text and can carry up to hundreds of billions of parameters, which is what lets a single model handle a wide range of tasks from a prompt alone, from drafting code to answering domain questions ([NVIDIA, "Large Language Models"](https://www.nvidia.com/en-us/glossary/large-language-models/)).

*In the course:* the LLM is the reasoning core the agent loop sits on. Every model call uses the configured chat route, so the course treats the model as a swappable component behind one interface rather than a fixed dependency.
*Related:* [AI reasoning](#ai-reasoning), [AI inference](#ai-inference), [Retrieval-augmented generation (RAG)](#retrieval-augmented-generation-rag).

### AI inference

NVIDIA defines inference as the application of a trained model to real-world data: the phase where the model generates new outputs by making predictions or classifications on inputs it has not seen before. It is the production half of a model's life, optimized for speed and efficiency with techniques such as speculative decoding, quantization, pruning, and layer fusion. For large language models, inference is the process of generating tokens, and the token rate sets the cost, latency, and feel of the system, which is why it runs on high-performance GPUs ([NVIDIA, "AI Inference"](https://www.nvidia.com/en-us/glossary/ai-inference/)).

*In the course:* every model call is an inference request. The default route reaches NVIDIA-hosted models through an OpenAI-compatible API, while the same interface can target another configured endpoint. The high per-query cost of reasoning-model inference is the reason the course verifies chains instead of just asking for longer ones.
*Related:* [Large language model (LLM)](#large-language-model-llm), [AI reasoning](#ai-reasoning).

---

## Retrieval and grounding

### Retrieval-augmented generation (RAG)

NVIDIA defines RAG as a technique that connects an external data source to an LLM so the model can produce domain-specific and up-to-date answers in real time. It addresses the LLM's built-in limit, that its knowledge stops at its pretraining data, by supplying fresh or proprietary information at answer time. The work happens in two phases: retrieval turns the query into a vector and searches a corpus for the most semantically relevant material, and generation folds that material into the model's prompt so the response is grounded in retrieved sources rather than memory alone. The payoff NVIDIA names is fewer hallucinations and better factual grounding, achieved without retraining the model ([NVIDIA, "Retrieval-Augmented Generation"](https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/)).

*In the course:* RAG is the retrieval rung the middle modules build, the move that turns an agent that only reasons into one that can ground its answers in a corpus it did not memorize.
*Related:* [Vector database](#vector-database), [Large language model (LLM)](#large-language-model-llm), [AI agents (autonomous agents)](#ai-agents-autonomous-agents).

### Vector database

NVIDIA defines a vector database as an organized collection of vector embeddings that can be created, read, updated, and deleted at any point in time, where an embedding represents a chunk of data such as text or an image as a list of numbers. The database stores each chunk alongside its vector and optional metadata, and uses index structures such as K-D trees and VP-trees so a lookup does not have to scan the whole set. A query is embedded the same way, and a similarity metric (Euclidean distance, cosine similarity, or Manhattan distance) returns the stored vectors closest to it ([NVIDIA, "Vector Database"](https://www.nvidia.com/en-us/glossary/vector-database/)). This is the mechanism behind retrieval-augmented generation: an embedding model turns a private corpus into vectors, and a semantic search returns the most relevant chunks as context for the model.

*In the course:* the vector store is what the retrieval rung builds on. The RAG module embeds a corpus, runs semantic search over it, and folds the top results into the prompt so the agent grounds its answer in material it never memorized.
*Related:* [Retrieval-augmented generation (RAG)](#retrieval-augmented-generation-rag), [Large language model (LLM)](#large-language-model-llm).

---

## Safety and control

### Guardrails (NeMo Guardrails)

In NVIDIA's agent definition, guardrails are the layer that bounds what an agent may do: the sandboxes, identity controls, and policy engines that sit around the reasoning core ([NVIDIA, "AI Agents"](https://www.nvidia.com/en-us/glossary/ai-agents/)). NVIDIA's concrete implementation of the idea is NeMo Guardrails, an open-source toolkit for adding programmable guardrails to LLM-based and agentic applications. It enforces policy between the user and the model across categories NVIDIA names directly: topical guardrails keep an app on its intended subject, safety guardrails check that responses stay accurate and appropriate (PII detection, jailbreak prevention, retrieval grounding), and security guardrails restrict which external systems the app may reach ([NVIDIA, "NeMo Guardrails"](https://docs.nvidia.com/nemo/guardrails/)).

*In the course:* this is the containment half of Securing Agents. Modules 3 and 4 drive the sandboxed OpenClaw agent and hot-swap its policy through sandbox-admin, which is the guardrails idea made concrete: a policy engine bounding the agent's network, filesystem, and process reach.
*Related:* [AI agents (autonomous agents)](#ai-agents-autonomous-agents), [Deep agents](#deep-agents), [Retrieval-augmented generation (RAG)](#retrieval-augmented-generation-rag).

---

## Sources

- NVIDIA, "AI Agents." [https://www.nvidia.com/en-us/glossary/ai-agents/](https://www.nvidia.com/en-us/glossary/ai-agents/)
- NVIDIA, "AI Reasoning." [https://www.nvidia.com/en-us/glossary/ai-reasoning/](https://www.nvidia.com/en-us/glossary/ai-reasoning/)
- NVIDIA, "Deep Agents." [https://www.nvidia.com/en-us/glossary/deep-agents/](https://www.nvidia.com/en-us/glossary/deep-agents/)
- NVIDIA, "Large Language Models." [https://www.nvidia.com/en-us/glossary/large-language-models/](https://www.nvidia.com/en-us/glossary/large-language-models/)
- NVIDIA, "AI Inference." [https://www.nvidia.com/en-us/glossary/ai-inference/](https://www.nvidia.com/en-us/glossary/ai-inference/)
- NVIDIA, "Retrieval-Augmented Generation." [https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/](https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/)
- NVIDIA, "Vector Database." [https://www.nvidia.com/en-us/glossary/vector-database/](https://www.nvidia.com/en-us/glossary/vector-database/)
- NVIDIA, "NeMo Guardrails" (documentation). [https://docs.nvidia.com/nemo/guardrails/](https://docs.nvidia.com/nemo/guardrails/)
- NVIDIA, "What is Agentic AI" (blog; redirects to the AI Agents glossary). [https://blogs.nvidia.com/blog/what-is-agentic-ai/](https://blogs.nvidia.com/blog/what-is-agentic-ai/)
