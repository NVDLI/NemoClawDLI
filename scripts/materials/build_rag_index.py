#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build the prebuilt vector index for the Module 2b Index Agent (web/nemoclaw/02b-rag.html).

This is the "index built offline, once" step the page teaches, made real. It embeds the
default corpus and the example queries with the course's pinned embedding model and writes
a static manifest the browser cell loads instead of re-embedding on every page view.

The builder sends embeddings to the configured API route. By default it uses NVIDIA's
hosted API and reads the bearer key from ``NVIDIA_API_KEY``.

Usage:
    python3 scripts/materials/build_rag_index.py            # refresh the manifest
    python3 scripts/materials/build_rag_index.py --check     # verify the manifest matches the seed (CI)

If you edit the seed CORPUS / QUERIES below, keep them identical to the literals in
#rag-cell and rerun this script. The cell re-embeds any text the manifest does not cover,
so a drift degrades gracefully to a live embed rather than breaking.
"""
import sys, json, hashlib, os, urllib.request
from datetime import date
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import find_repo_root

ROOT = find_repo_root(Path(__file__).resolve())
EMBED_BASE_URL = os.environ.get(
    "NEMOCLAW_EMBEDDING_API_BASE_URL",
    "https://integrate.api.nvidia.com/v1",
).rstrip("/")
EMBED_URL = f"{EMBED_BASE_URL}/embeddings"
API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
MODEL = "nvidia/llama-nemotron-embed-1b-v2"
OUT = ROOT / "web" / "nemoclaw" / "assets" / "rag_index.json"

# Source of truth for the DEFAULT corpus + examples. Mirror these in #rag-cell verbatim.
CORPUS = [
    "An agent loop wraps a stateless model in a cycle: read the messages, decide, call a tool, append the result, repeat until finish_reason is stop.",
    "ReAct interleaves reasoning and acting: the model thinks, optionally calls a tool, reads the observation, and re-plans before answering.",
    "A tool is structured output plus an executor: the model emits a tool_calls request, your code runs the function, and the result returns as a tool message.",
    "Retrieval-augmented generation embeds a query and the documents into the same vector space, retrieves the nearest chunks, and feeds them to the model as grounding.",
    "Cosine similarity scores two embedding vectors by the angle between them; closer to 1 means more semantically related.",
    "A deep or research agent plans a task, spawns sub-agents in fresh contexts, and shares work through a virtual filesystem to avoid context overflow.",
    "OpenClaw is an agent harness whose configuration is a folder of markdown files the harness folds into the system prompt every turn.",
    "OpenShell is the kernel-level sandbox around the agent: netns, Landlock, seccomp, and an OPA-evaluated proxy decide what each tool call may touch.",
]
QUERIES = ["What is retrieval-augmented generation?", "Why use cosine similarity?", "How does the ReAct loop work?", "What is a tool, mechanically?", "What does the OpenShell sandbox do?", "What is a deep research agent?"]


def embed(texts, input_type):
    body = json.dumps({"input": texts, "model": MODEL, "input_type": input_type}).encode()
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(EMBED_URL, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    return [[round(x, 6) for x in row["embedding"]] for row in data["data"]]


def corpus_hash(corpus=CORPUS):
    return hashlib.sha256("\n".join(corpus).encode()).hexdigest()[:16]


def build():
    doc_vecs = embed(CORPUS, "passage")
    qry_vecs = embed(QUERIES, "query")
    dim = len(doc_vecs[0])
    manifest = {
        "model": MODEL,
        "dim": dim,
        "generated": date.today().isoformat(),
        "corpus_hash": corpus_hash(),
        "docs": [{"text": t, "vec": v} for t, v in zip(CORPUS, doc_vecs)],
        "queries": [{"text": t, "vec": v} for t, v in zip(QUERIES, qry_vecs)],
    }
    OUT.write_text(json.dumps(manifest, separators=(",", ":")))
    kb = OUT.stat().st_size / 1024
    print(f"wrote {OUT.relative_to(OUT.parents[2])}  ({len(CORPUS)} docs, {len(QUERIES)} queries, dim {dim}, {kb:.0f} KB, hash {manifest['corpus_hash']})")


CELL = OUT.parents[1] / "02b-rag.html"   # web/nemoclaw/02b-rag.html, where #rag-cell ships the same corpus


def cell_corpus():
    """Extract the CORPUS literal the #rag-cell actually ships, so a cell edit that skips a
    rebuild is caught here rather than silently degrading to live re-embeds in the browser."""
    import re
    html = CELL.read_text()
    seg = html[html.find('"#rag-cell"'):]   # scope past the mount: 02b has another CORPUS in the GraphRAG cell
    block = re.search(r"const CORPUS = \[(.*?)\];", seg, re.S)
    return re.findall(r'"((?:[^"\\]|\\.)*)"', block.group(1)) if block else []


def manifest_problems(manifest, corpus=CORPUS, cell_docs=None):
    """Return deterministic source/artifact drift without making a network request."""
    problems = []
    if manifest.get("model") != MODEL:
        problems.append(f"model id {manifest.get('model')!r} != pinned {MODEL!r}")
    if manifest.get("corpus_hash") != corpus_hash(corpus):
        problems.append("corpus_hash drift: the seed CORPUS changed since the last build; rerun build_rag_index.py")
    if {doc.get("text") for doc in manifest.get("docs", [])} != set(corpus):
        problems.append("manifest docs do not match the seed CORPUS in this script")
    if cell_docs is not None and set(cell_docs) != set(corpus):
        problems.append("the CORPUS in #rag-cell (02b-rag.html) differs from this script's seed; sync them and rerun build_rag_index.py")
    return problems


def check():
    if not OUT.exists():
        print(f"MISSING {OUT}"); return 1
    problems = manifest_problems(
        json.loads(OUT.read_text()),
        cell_docs=cell_corpus(),
    )
    for p in problems:
        print("DRIFT:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else (build() or 0))
