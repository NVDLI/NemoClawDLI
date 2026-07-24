<a href="https://www.youtube.com/watch?v=DUyE4mu0Yhw" target="_blank">How Edison’s Kosmos AI Scientist Does Six Months of Research in One Day with Nemotron</a>

The video highlights how **Edison Scientific’s *Kosmos***, an autonomous AI scientist, is revolutionizing the research cycle by compressing six months of scientific work into a single day. Powered by **NVIDIA’s GPU infrastructure** and **AI stack**, *Kosmos* functions as a coordinated system of agents capable of handling complex research tasks in fields like genetics, neuroscience, and drug discovery (0:08 - 0:22).

The platform utilizes a multi-agent architecture to perform specialized scientific workflows:

* **Literature Agent:** Uses **NVIDIA *Nemotron Parse*** to ingest and structure millions of scientific papers, patents, and clinical records, accurately separating text, figures, and formulas to extract insights from decades of research (0:39 - 0:55).
* **Analysis Agent:** Leverages **CUDA libraries**, **cuML**, and **QDF** to process massive biological datasets, identifying statistically significant genetic patterns linked to health conditions like Alzheimer's (0:58 - 1:10).
* **Molecules Agent:** Employs models trained with **NVIDIA *NeMo RL*** to reason over chemical structures and propose potential therapeutic molecules for disease prevention (1:13 - 1:20).

By automating these labor-intensive processes, *Kosmos* enables researchers to move past the bottlenecks of manual data processing and focus on high-level hypothesis testing and discovery, significantly accelerating the pace of scientific advancement (1:23 - 1:29).

Case study: [Scientific literature AI with NVIDIA Nemotron](https://developer.nvidia.com/case-studies/scientific-literature-ai-nvidia-nemotron)

=====

<a href="https://www.youtube.com/watch?v=KNd7T3MgqZc">Give Codex a Deep Research Skill With NVIDIA AI-Q</a>

This video demonstrates how to integrate **NVIDIA AI-Q** into agent harnesses like *Codex* to provide a specialized **deep research skill**. By offloading complex tasks (retrieval, reasoning, synthesis, and citation) to a dedicated AI-Q server, developers avoid rebuilding these pipelines for every individual agent.

### Key Highlights:
* **Architecture Overview (0:00 - 0:30):** The setup involves a developer workstation running *Codex*, a secondary host machine running the *AI-Q* server, and *NVIDIA's* inference models hosted on *build.nvidia.com* for planning and research.
* **Skill Installation (0:30 - 1:15):** The process is simplified by using a start script on the *AI-Q* server to get the necessary IP and port, which are then passed to *Codex* to perform the installation and environment configuration automatically.
* **Executing Deep Research (1:15 - 2:05):** Once the skill is installed, the user can submit a research query directly from *Codex*. The system handles the job asynchronously, managing interactions between various sub-agents to perform tool calls and reasoning.
* **Reviewing Results (3:15 - 4:05):** The final output is a structured, enterprise-ready report that includes detailed synthesis, recommendations, comparisons, and grounded citations, which are key differentiators of the *AI-Q* service.

### What is NVIDIA AI-Q?
**NVIDIA AI-Q** is a specialized tool designed to provide agent harnesses (like *Codex*) with a dedicated **deep research skill** (0:00 - 0:30). Instead of forcing developers to rebuild retrieval, reasoning, synthesis, and citation logic within every individual agent, *AI-Q* acts as a centralized server that manages these complex workflows asynchronously. It handles the heavy lifting of multi-source research and returns a structured, enterprise-ready report with grounded citations to the host agent (3:15 - 4:05).

### Necessary Setup Commands
The demo shows a streamlined installation process rather than manual configuration steps. The key commands/actions involved are:

1.  **Start Script:** The user runs the provided `start` script on the *AI-Q* host machine (0:40 - 0:45). This script initializes the front and back ends and outputs the required **IP address** and **ports**.
2.  **Codex Configuration:** Instead of manual setup, the user copies the installation instructions, IP address, and port, then pastes them into *Codex* (0:57 - 1:15). 
3.  **Automatic Installation:** By instructing *Codex* to use these details, the agent itself fetches the skill, performs the installation, and updates the necessary **environment variables** automatically (1:15 - 1:58).

For more detailed, manual installation instructions, the video references the official *GitHub* repository (1:36 - 1:47).

Repo: [NVIDIA-AI-Blueprints/aiq](https://github.com/NVIDIA-AI-Blueprints/aiq#getting-started)
Blog: [Add a specialized deep research skill to agent harnesses](https://developer.nvidia.com/blog/add-a-specialized-deep-research-skill-to-agent-harnesses/)