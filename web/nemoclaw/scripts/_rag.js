// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// RAG retrieval helpers: remote embeddings plus cosine scoring.

import {
  DEFAULT_EMBEDDING_MODEL, fetchRetry, getEmbeddingConfig, getEmbeddingKey,
  getModelRequestPolicy, isDefaultModelApiBaseUrl, modelRequestCredentials, _apiHeaders,
} from "./_shared.js";

// Embed one or more strings and always return a list of vectors.
export async function embed(input, { model = null, inputType = "query" } = {}) {
  /* @doc <code>helpers.embed(text, {model, inputType})</code> ::
       POST to the persistent embedding route <code>{cfg.url}/embeddings</code>.
       Returns an array of vectors (numbers[]). NVIDIA embed models require <code>inputType:
       "query"</code> or <code>"passage"</code>.
  */
  const cfg = await getEmbeddingConfig();
  const key = getEmbeddingKey();
  if (cfg.needsKey && !key) {
    throw new Error("Embedding key missing. Open the course setup and configure the persistent embedding route.");
  }
  const headers = _apiHeaders(cfg, key);
  const useModel = isDefaultModelApiBaseUrl(cfg.url) && cfg.model === DEFAULT_EMBEDDING_MODEL
    ? (model || cfg.model) : cfg.model;
  const body = {
    input: Array.isArray(input) ? input : [input],
    model: useModel,
    input_type: inputType,
  };
  const r = await fetchRetry(`${cfg.url}/embeddings`, {
    method: "POST", headers, body: JSON.stringify(body), credentials: modelRequestCredentials(cfg.url),
  }, getModelRequestPolicy());
  if (!r.ok) {
    const reason = r.status === 429 ? "rate limited" :
      r.status === 401 || r.status === 403 ? "credential rejected" :
      r.status >= 500 ? "upstream unavailable or starting" : "request rejected";
    throw new Error(`Embedding request failed: HTTP ${r.status} (${reason}). Check Request handling in course setup.`);
  }
  const data = await r.json();
  return data.data.map(d => d.embedding);
}

// Score equal-length vectors; closer to 1 means closer match.
export function cosineSim(a, b) {
  /* @doc <code>helpers.cosineSim(a, b)</code> ::
       Cosine similarity between two vectors. Closer to 1 = closer match. The standard retrieval
       primitive.
  */
  let dot = 0, na = 0, nb = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
  return dot / (Math.sqrt(na) * Math.sqrt(nb) + 1e-12);
}
