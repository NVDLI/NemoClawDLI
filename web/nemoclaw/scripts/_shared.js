// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// ─── Shared runtime for the nemoclaw web course (frontend track) ─────────────

// Remote-service-only. Direct calls use the learner key. The published DLI CDN uses the
// bounded NVIDIA DLI relay by default because the upstream browser CORS response is not stable.
// Local file previews use the same relay; other origins stay direct unless the learner enables it.

export const DEFAULT_MODEL_API_BASE_URL = "https://integrate.api.nvidia.com/v1";
const IFRAME_PROXY_URL = "https://nvidia-api-cors-proxy.experiments.courses.nvidia.com/v1";
const IFRAME_PROXY_OPT_IN_KEY = "nemoclaw_iframe_proxy_opt_in";
const MODEL_RELAY_DEFAULT_ORIGINS = new Set(["https://cdn.dli.learn.nvidia.com"]);
const MODEL_API_BASE_URL_KEY = "nemoclaw_model_api_base_url_v1";
const MODEL_ID_KEY = "nemoclaw_model_id_v1";
const EMBEDDING_API_BASE_URL_KEY = "nemoclaw_embedding_api_base_url_v1";
const EMBEDDING_MODEL_ID_KEY = "nemoclaw_embedding_model_id_v1";
const EMBEDDING_API_KEY = "nemoclaw_embedding_api_key_v1";
// Billing attribution is sent on direct and iframe-proxy calls.
const BILLING_INVOKE_ORIGIN = "dli-nemoclaw-web";
// Web-cell model contract. All repository explorers delegate to this one default.
export const DEFAULT_MODEL = "nvidia/nemotron-3-nano-30b-a3b";
export const DEFAULT_EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-1b-v2";
export const REASONING_MODEL = DEFAULT_MODEL;

// ── Lab-only step detection ─────────────────────────────────────────────────
// Model calls and web search run from any page; the OpenClaw agent steps do not.
// They reach the NemoClaw launchable on Brev, so they get badged instead of failing.
const LAB_ONLY_RE = /\/lab\/openclaw|open(?:shell|claw):8995|\/lab\/svc\/sandbox-admin|sandbox-admin:8099/;
function _stepSource(node) { return node ? String(node.code || "") : ""; }
export function _stepLabOnly(node) { return LAB_ONLY_RE.test(_stepSource(node)); }
export function _labOnlyService(node) {
  const s = _stepSource(node);
  if (/\/lab\/openclaw|open(?:shell|claw):8995/.test(s))        return "OpenClaw, the sandboxed agent in your NemoClaw launchable";
  if (/sandbox-admin/.test(s))                                  return "the sandbox controller in your NemoClaw launchable";
  return "your NemoClaw launchable";
}

// ── Data-driven diagram grammar → _diagram.js ───────────────────────────────
// Re-export diagram helpers so page imports and helper menus stay stable.
import { diagramSVG, mountDiagram } from "./_diagram.js";
export { diagramSVG, mountDiagram };

// ── ganttBarsSVG (02c concurrency figure) → _figures.js ──────────────────────
// Re-export figure helpers so page imports and helper menus stay stable.
import { ganttBarsSVG, mountFigures, openFigureLightbox, wireFigureZoom } from "./_figures.js";
export { ganttBarsSVG, mountFigures, openFigureLightbox, wireFigureZoom };
import { mountLanguageMenu } from "./_locale.js";
export { mountLanguageMenu };
import { mountLearningView } from "./_learning.js";
export { mountLearningView };
import { mountCourseAssistant, mountCourseLicenseNote } from "./_course_assistant.js";
export { mountCourseAssistant, mountCourseLicenseNote };

const LAB_MODEL     = DEFAULT_MODEL; // legacy helper default; getConfig().model is the active course default
const CONFIG_KEY    = "__nv_slim_cfg_v1";

// The web course runs JavaScript only.
// The in-browser Python / JupyterLab-kernel path was removed; Python lives in the notebooks.

// Endpoint discovery
let _cfgPromise = null;

function _syncIframeProxyOptInFromUrl() {
  try {
    const params = new URLSearchParams(location.search || "");
    const val = params.get("iframe_proxy") || params.get("lms_proxy");
    if (val === "1" || val === "true") localStorage.setItem(IFRAME_PROXY_OPT_IN_KEY, "1");
    if (val === "0" || val === "false") localStorage.setItem(IFRAME_PROXY_OPT_IN_KEY, "0");
  } catch (_) {}
}

export function normalizeModelApiBaseUrl(raw) {
  const text = String(raw || "").trim();
  if (!text) return DEFAULT_MODEL_API_BASE_URL;
  const url = new URL(text);
  const localHttp = url.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
  if (url.protocol !== "https:" && !localHttp) throw new Error("Model API base URL must use HTTPS");
  const pageLocation = globalThis.location;
  if (localHttp && pageLocation?.protocol === "https:" && !["localhost", "127.0.0.1"].includes(pageLocation.hostname)) {
    throw new Error("localhost points to this browser, not the Brev VM. Expose port 5000 with Brev Using Tunnels and paste its HTTPS URL ending in /v1");
  }
  if (/\.brevlab\.com$/i.test(url.hostname) && /^\/lab(?:\/|$)/.test(url.pathname)) {
    throw new Error("A Brev Jupyter /lab URL is not a model API. Expose port 5000 with Brev Using Tunnels and paste its HTTPS URL ending in /v1");
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("Model API base URL cannot include credentials, query parameters, or a fragment");
  }
  return url.href.replace(/\/+$/, "");
}

export function normalizeModelId(raw, fallback = DEFAULT_MODEL) {
  const model = String(raw || "").trim();
  if (!model) return fallback;
  if (/\s/.test(model) || model.length > 240) throw new Error("Model ID must be one non-empty value without spaces");
  return model;
}

export function suggestedModelApiBaseUrl() {
  try {
    const params = new URLSearchParams(location.search || "");
    const raw = params.get("model_base_url") || params.get("base_url");
    return raw ? normalizeModelApiBaseUrl(raw) : getModelApiBaseUrl();
  } catch (_) { return getModelApiBaseUrl(); }
}

export function suggestedModelId() {
  try {
    const raw = new URLSearchParams(location.search || "").get("model");
    return raw ? normalizeModelId(raw) : getModelId();
  } catch (_) { return getModelId(); }
}

export function suggestedEmbeddingApiBaseUrl() {
  try {
    const raw = new URLSearchParams(location.search || "").get("embedding_base_url");
    return raw ? normalizeModelApiBaseUrl(raw) : getEmbeddingApiBaseUrl();
  } catch (_) { return getEmbeddingApiBaseUrl(); }
}

export function suggestedEmbeddingModelId() {
  try {
    const raw = new URLSearchParams(location.search || "").get("embedding_model");
    return raw ? normalizeModelId(raw, DEFAULT_EMBEDDING_MODEL) : getEmbeddingModelId();
  } catch (_) { return getEmbeddingModelId(); }
}

export function getModelApiBaseUrl() {
  try { return normalizeModelApiBaseUrl(localStorage.getItem(MODEL_API_BASE_URL_KEY)); }
  catch (_) { return DEFAULT_MODEL_API_BASE_URL; }
}

export function setModelApiBaseUrl(raw) {
  const normalized = normalizeModelApiBaseUrl(raw);
  try {
    if (normalized === DEFAULT_MODEL_API_BASE_URL) localStorage.removeItem(MODEL_API_BASE_URL_KEY);
    else localStorage.setItem(MODEL_API_BASE_URL_KEY, normalized);
    sessionStorage.removeItem(CONFIG_KEY);
    sessionStorage.removeItem("nvapi_ok");
  } catch (_) {}
  _cfgPromise = null;
  return normalized;
}

export function getModelId() {
  try { return normalizeModelId(localStorage.getItem(MODEL_ID_KEY)); }
  catch (_) { return DEFAULT_MODEL; }
}

export function setModelId(raw) {
  const model = normalizeModelId(raw);
  try {
    if (model === DEFAULT_MODEL) localStorage.removeItem(MODEL_ID_KEY);
    else localStorage.setItem(MODEL_ID_KEY, model);
    sessionStorage.removeItem(CONFIG_KEY);
  } catch (_) {}
  _cfgPromise = null;
  return model;
}

export function getEmbeddingApiBaseUrl() {
  try { return normalizeModelApiBaseUrl(localStorage.getItem(EMBEDDING_API_BASE_URL_KEY)); }
  catch (_) { return DEFAULT_MODEL_API_BASE_URL; }
}

export function setEmbeddingApiBaseUrl(raw) {
  const endpoint = normalizeModelApiBaseUrl(raw);
  try {
    if (endpoint === DEFAULT_MODEL_API_BASE_URL) localStorage.removeItem(EMBEDDING_API_BASE_URL_KEY);
    else localStorage.setItem(EMBEDDING_API_BASE_URL_KEY, endpoint);
  } catch (_) {}
  return endpoint;
}

export function getEmbeddingModelId() {
  try { return normalizeModelId(localStorage.getItem(EMBEDDING_MODEL_ID_KEY), DEFAULT_EMBEDDING_MODEL); }
  catch (_) { return DEFAULT_EMBEDDING_MODEL; }
}

export function setEmbeddingModelId(raw) {
  const model = normalizeModelId(raw, DEFAULT_EMBEDDING_MODEL);
  try {
    if (model === DEFAULT_EMBEDDING_MODEL) localStorage.removeItem(EMBEDDING_MODEL_ID_KEY);
    else localStorage.setItem(EMBEDDING_MODEL_ID_KEY, model);
  } catch (_) {}
  return model;
}

function billingAttributionEnabled(url) {
  try {
    const host = new URL(url, location.href).hostname;
    return host === "integrate.api.nvidia.com" || host === "nvidia-api-cors-proxy.experiments.courses.nvidia.com";
  } catch (_) { return false; }
}

export function iframeProxyModeEnabled() {
  _syncIframeProxyOptInFromUrl();
  // A file origin cannot call the hosted NVIDIA API directly. Keep this route usable even when
  // an older local preview saved an explicit direct-mode preference. Custom endpoints still
  // bypass the relay in getConfig().
  if (globalThis.location?.protocol === "file:") return true;
  try {
    const stored = localStorage.getItem(IFRAME_PROXY_OPT_IN_KEY);
    if (stored === "1") return true;
    if (stored === "0") return false;
  } catch (_) {}
  return defaultIframeProxyModeForLocation(globalThis.location);
}

export function setIframeProxyMode(enabled) {
  try {
    localStorage.setItem(IFRAME_PROXY_OPT_IN_KEY, enabled ? "1" : "0");
    sessionStorage.removeItem(CONFIG_KEY);
  } catch (_) {}
  _cfgPromise = null;
}

export function defaultIframeProxyModeForLocation(locationLike) {
  try {
    const url = new URL(String(locationLike?.href || locationLike?.origin || locationLike));
    return url.protocol === "file:" || MODEL_RELAY_DEFAULT_ORIGINS.has(url.origin);
  } catch (_) { return false; }
}

export async function getConfig() {
  /* @doc <code>helpers.getConfig()</code> ::
       Returns the active chat config <code>{ mode, url, model, needsKey, iframeProxy }</code>.
       A presenter can save one compatible chat endpoint and model on the course home page.
       Embeddings retain their own route. The DLI CDN and local file previews default to the
       bounded NVIDIA DLI relay; other origins stay direct, and a custom chat endpoint always
       bypasses the relay. */
  if (_cfgPromise) return _cfgPromise;
  _cfgPromise = (async () => {
    const modelApiBaseUrl = getModelApiBaseUrl();
    const model = getModelId();
    const useIframeProxy = iframeProxyModeEnabled() && modelApiBaseUrl === DEFAULT_MODEL_API_BASE_URL;
    try {
      const c = sessionStorage.getItem(CONFIG_KEY);
      if (c) {
        const cached = JSON.parse(c);
        if (!!cached.iframeProxy === useIframeProxy && cached.model === model &&
            cached.url === (useIframeProxy ? IFRAME_PROXY_URL : modelApiBaseUrl)) return cached;
      }
    } catch (_) {}

    const cfg = useIframeProxy
      ? { mode: "direct", url: IFRAME_PROXY_URL, model, needsKey: true, iframeProxy: true }
      : { mode: "direct", url: modelApiBaseUrl, model, needsKey: true, iframeProxy: false };

    try { sessionStorage.setItem(CONFIG_KEY, JSON.stringify(cfg)); } catch (_) {}
    return cfg;
  })();
  return _cfgPromise;
}

export async function getEmbeddingConfig() {
  /* @doc <code>helpers.getEmbeddingConfig()</code> ::
       Returns the persistent embedding <code>{ url, model }</code> route. It defaults to NVIDIA's
       hosted API and does not change when a presenter selects a Brev chat endpoint. */
  return {
    mode: "direct",
    url: getEmbeddingApiBaseUrl(),
    model: getEmbeddingModelId(),
    needsKey: true,
    iframeProxy: false,
  };
}

// Key management
export function getKey() {
  /* @doc <code>helpers.getKey()</code> ::
       Returns the model bearer key held for this browser tab (<code>sessionStorage</code>), or
       <code>null</code>. NVIDIA keys start with <code>nvapi-</code>. Model calls use the tab-scoped
       value automatically; closing the tab discards it. */
  try { return sessionStorage.getItem("nvapi"); }
  catch (_) { return null; }
}
export function setKey(k) {
  const key = String(k || "").trim();
  try {
    if (key) sessionStorage.setItem("nvapi", key);
    else sessionStorage.removeItem("nvapi");
    sessionStorage.removeItem("nvapi_ok");
  } catch (_) {}
}
export function hasKey() { return !!getKey(); }

export function getEmbeddingKey() {
  try {
    const stored = sessionStorage.getItem(EMBEDDING_API_KEY);
    if (stored) return stored;
    const active = getKey();
    return active?.startsWith("nvapi-") ? active : null;
  } catch (_) { return null; }
}

export function setEmbeddingKey(k) {
  const key = String(k || "").trim();
  try {
    if (key) sessionStorage.setItem(EMBEDDING_API_KEY, key);
    else sessionStorage.removeItem(EMBEDDING_API_KEY);
  } catch (_) {}
}

export function isDefaultModelApiBaseUrl(url) {
  try {
    const host = new URL(url, location.href).hostname;
    return host === "integrate.api.nvidia.com" || host === "nvidia-api-cors-proxy.experiments.courses.nvidia.com";
  } catch (_) { return false; }
}

export function modelRequestCredentials(url) {
  return isDefaultModelApiBaseUrl(url) ? "same-origin" : "include";
}

// The OpenAI JS SDK (what ChatOpenAI uses) attaches x-stainless-* headers.
// Strip x-stainless-* headers for browser hosts that reject them during preflight.
export function browserChatFetch() {
  /* @doc <code>helpers.browserChatFetch()</code> ::
       Returns a <code>fetch</code> that strips the OpenAI SDK's <code>x-stainless-*</code>
       headers. NVIDIA model routes also receive the <code>X-BILLING-INVOKE-ORIGIN</code> tracking tag.
       Custom routes include their browser session credentials. Pass it as
       <code>configuration.fetch</code> when constructing a browser <code>ChatOpenAI</code>. */
  return async (url, init = {}) => {
    const h = init.headers instanceof Headers ? init.headers : new Headers(init.headers || {});
    for (const k of [...h.keys()]) { if (k.startsWith("x-stainless")) h.delete(k); }
    if (billingAttributionEnabled(url)) h.set("X-BILLING-INVOKE-ORIGIN", BILLING_INVOKE_ORIGIN);
    else h.delete("X-BILLING-INVOKE-ORIGIN");
    const r = await fetchRetry(url, { ...init, headers: h, credentials: modelRequestCredentials(url) },
      { retries: 2, backoffMs: 250, timeoutMs: 60000 });
    // Wrap non-JSON HTTP errors so the SDK surfaces the real status and body.
    if (!r.ok && !(r.headers.get("content-type") || "").toLowerCase().includes("application/json")) {
      const txt = await r.text().catch(() => "");
      return new Response(
        JSON.stringify({ error: { message: "HTTP " + r.status + " " + r.statusText + ": " + txt.slice(0, 300), type: "http_error", code: r.status } }),
        { status: r.status, statusText: r.statusText, headers: { "Content-Type": "application/json" } },
      );
    }
    return r;
  };
}

export function requireKey(returnUrl) {
  // Both direct and iframe-proxy modes use the learner's nvapi key.
  getConfig().then(cfg => {
    if (!cfg.needsKey) return;
    if (!hasKey()) location.href = `index.html?next=${encodeURIComponent(returnUrl || location.pathname)}`;
  });
}

// Retry a fetch on transient failure (network error, 502 / 503 / 504 / 524), backing off 250ms, 500ms, 1000ms; streaming calls retry only the headers phase.
// `timeoutMs` aborts the fetch when no headers arrive, so a Cloudflare 524 cannot hang the cell for 100+ seconds.
async function fetchRetry(url, opts = {}, { retries = 2, backoffMs = 250, timeoutMs = 60000 } = {}) {
  /* @doc <code>helpers.fetchRetry(url, opts)</code> ::
       Like <code>helpers.fetch</code>, but retries up to 2 times on 5xx or network errors
       with exponential backoff (250 / 500 / 1000 ms). Use it when calling an endpoint by
       hand (e.g. the Responses API) and you want resilience without writing the loop. */
  let lastErr = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    // Stitch in an AbortController so we don't sit on a half-dead socket.
    // Honour any external signal the caller passed in too.
    const ac = new AbortController();
    const onAbort = () => ac.abort();
    if (opts.signal) opts.signal.addEventListener("abort", onAbort, { once: true });
    const timer = setTimeout(() => ac.abort(new Error(`timeout after ${timeoutMs}ms`)), timeoutMs);
    try {
      const r = await fetch(url, { ...opts, signal: ac.signal });
      clearTimeout(timer);
      if (r.ok) return r;
      // 5xx (including Cloudflare's 524 origin-timeout) is transient upstream.
      // 4xx is the caller's fault, don't retry.
      if (r.status >= 500 && r.status < 600 && attempt < retries) {
        await new Promise(res => setTimeout(res, backoffMs * (2 ** attempt)));
        continue;
      }
      return r;  // 4xx or a final 5xx. The caller handles these.
    } catch (e) {
      clearTimeout(timer);
      lastErr = e;
      // Aborted by caller? Don't retry, because they asked us to stop.
      if (opts.signal && opts.signal.aborted) throw e;
      if (attempt < retries) {
        await new Promise(res => setTimeout(res, backoffMs * (2 ** attempt)));
        continue;
      }
      if (globalThis.location?.protocol === "file:" && billingAttributionEnabled(url)) {
        throw new Error(
          "The local course preview could not reach the model. Enable ‘Use the NVIDIA DLI browser relay’ " +
          "in the API key panel, or serve the course with ‘python3 -m http.server -d web 8000’ and open " +
          "http://localhost:8000/nemoclaw/. " + (e?.message || String(e))
        );
      }
      throw e;
    }
  }
  throw lastErr || new Error("fetchRetry exhausted");
}
export { fetchRetry };

// Headers shared by model requests. NVIDIA routes receive course attribution; a presenter-selected
// compatible endpoint receives only standard content and authorization headers.
export function _apiHeaders(cfg, keyOverride = null) {
  const h = { "Content-Type": "application/json" };
  if (billingAttributionEnabled(cfg.url)) h["X-BILLING-INVOKE-ORIGIN"] = BILLING_INVOKE_ORIGIN;
  if (cfg.needsKey) h["Authorization"] = `Bearer ${keyOverride || getKey()}`;
  return h;
}

// ── Core API call ─────────────────────────────────────────────────────────────
// The default model reasons on a private channel before writing content.
// A small max_tokens leaves content empty (finish_reason "length"), so the default keeps headroom.
export async function chat({ messages, tools = null, model = null, temperature = 0.1, max_tokens = 8196, response_format = null, tool_choice = null, signal = null }) {
  /* @doc <code>helpers.chat(opts)</code> ::
       One-shot, non-streaming chat completion. Returns the raw OpenAI-shape response. Use
       when you just want the final message. */
  const cfg = await getConfig();
  const useModel = isDefaultModelApiBaseUrl(cfg.url) ? (model || cfg.model) : cfg.model;
  const body = { model: useModel, messages, temperature, max_tokens };
  if (tools?.length)   body.tools           = tools;
  if (response_format) body.response_format = response_format;
  if (tool_choice)     body.tool_choice     = tool_choice;

  const headers = _apiHeaders(cfg);

  const resp = await fetchRetry(`${cfg.url}/chat/completions`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    credentials: modelRequestCredentials(cfg.url),
    signal,
  });
  if (!resp.ok) {
    const txt = await resp.text();
    // 524 is Cloudflare's origin-timeout.
    // The generic "524: <html>..." body does not help a student debug their cell, so surface it explicitly with next steps.
    if (resp.status === 524) {
      throw new Error(
        "524 origin timeout: the model took too long to respond (Cloudflare cut the connection). " +
        "This usually clears on retry; if it persists, the upstream model may be cold-starting. " +
        "Try again in 10–20 seconds."
      );
    }
    throw new Error(`${resp.status}: ${txt.slice(0, 400)}`);
  }
  return resp.json();
}

// Streaming wrapper. `onChunk(text)` receives each user-facing content delta.
// An optional third arg, chatStream(opts, onContent, { onReasoning, onMeta }), adds more.

// `onReasoning(text)` fires per reasoning_content delta.
// `onMeta(obj)` fires once at the end with { usage, finish_reason, model, raw }.
// The same fields are also returned as a summary, so callers can read totals callback-free.
export async function chatStream(opts, onChunk, extra = {}) {
  /* @doc <code>helpers.chatStream(opts)</code> ::
       Streaming chat completion; tokens flow into this panel's results view as they arrive.
       Returns a summary with <code>.content</code>, <code>.reasoning</code>,
       <code>.tool_calls</code>, <code>.finish_reason</code>, <code>.usage</code>. */
  const { messages, model = null, temperature = 0.1, max_tokens = 8196, tools = null, response_format = null, tool_choice = null, signal = null } = opts;
  const onReasoning = extra.onReasoning || null;
  const onMeta = extra.onMeta || null;
  const cfg = await getConfig();
  const useModel = isDefaultModelApiBaseUrl(cfg.url) ? (model || cfg.model) : cfg.model;

  const headers = _apiHeaders(cfg);

  const body = { model: useModel, messages, temperature, max_tokens, stream: true };
  if (tools?.length)    body.tools           = tools;
  if (response_format)  body.response_format = response_format;
  if (tool_choice)      body.tool_choice     = tool_choice;
  if (opts.extra_body)  Object.assign(body, opts.extra_body);

  const resp = await fetchRetry(`${cfg.url}/chat/completions`, {
    method: "POST", headers, body: JSON.stringify(body), credentials: modelRequestCredentials(cfg.url), signal,
  });
  if (!resp.ok) {
    const txt = await resp.text();
    if (resp.status === 524) {
      throw new Error(
        "524 origin timeout (streaming): the model didn't start responding in time. " +
        "Try again in 10–20 seconds. This usually clears on retry."
      );
    }
    throw new Error(`${resp.status}: ${txt.slice(0, 400)}`);
  }

  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let usage = null, finishReason = null, lastRaw = null;
  let content = "", reasoning = "";
  // tool_calls arrive fragmented across frames: the streaming API splits function.arguments JSON into deltas, each tagged with an `index` for the call it belongs to.
  // Accumulate by index here so the caller ends with a flat [{id, function: {name, arguments}}] array.
  const toolCalls = [];
  function accumulateToolCalls(deltaTcs) {
    if (!deltaTcs) return;
    for (const tc of deltaTcs) {
      const i = tc.index ?? 0;
      const cur = (toolCalls[i] ||= { index: i, id: "", type: "function",
                                       function: { name: "", arguments: "" } });
      if (tc.id) cur.id = tc.id;
      if (tc.type) cur.type = tc.type;
      if (tc.function?.name) cur.function.name += tc.function.name;
      if (tc.function?.arguments) cur.function.arguments += tc.function.arguments;
    }
  }

  // Boundary-safe SSE frame parser: consume only complete "data: ...\n\n" frames.
  // Partial frames stay buffered for the next read.
  outer: while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const raw of frame.split("\n")) {
        if (!raw.startsWith("data: ")) continue;
        const payload = raw.slice(6).trim();
        if (payload === "[DONE]") break outer;
        let obj;
        try { obj = JSON.parse(payload); } catch (_) { continue; }
        lastRaw = obj;
        const choice = obj?.choices?.[0];
        const delta = choice?.delta;
        if (delta?.content) { content += delta.content; if (onChunk) onChunk(delta.content); }
        if (delta?.reasoning_content) {
          reasoning += delta.reasoning_content;
          if (onReasoning) onReasoning(delta.reasoning_content);
        }
        if (delta?.tool_calls) accumulateToolCalls(delta.tool_calls);
        if (choice?.finish_reason) finishReason = choice.finish_reason;
        if (obj?.usage) usage = obj.usage;
      }
    }
  }

  const summary = {
    content, reasoning,
    tool_calls: toolCalls.filter(Boolean),
    finish_reason: finishReason, usage, model: useModel, raw: lastRaw,
  };
  if (onMeta) onMeta(summary);
  return summary;
}


// ── Canvas + cell runtime → _canvas.js ───────────────────────────────────────

// mountCanvasFlow, mountRunCell, the helper-menu builders, and error/log helpers live there.
// _canvas.js is a leaf that uses the registries and primitives only at call time, so re-exporting the two mount* entry points adds no load-time cycle.
import { mountCanvasFlow, mountRunCell } from "./_canvas.js";
export { mountCanvasFlow, mountRunCell };

// ── glossary → _glossary.js ─────────────────────────────────────────
// Re-exported here so the helper registry/menu and existing page imports are unchanged.
import {
  webSearch, instantAnswer, glossaryScore, loadGlossaryIndex, loadMaterialsCatalog,
} from "./_glossary.js";
export {
  webSearch, instantAnswer, glossaryScore, loadGlossaryIndex, loadMaterialsCatalog,
};

// ── rag → _rag.js ─────────────────────────────────────────
// Re-exported here so the helper registry/menu and existing page imports are unchanged.
import {
  embed, cosineSim,
} from "./_rag.js";
export {
  embed, cosineSim,
};

// ── OpenShell policy engine + launchable terminal → _openshell.js ────────────
// Used by 04a/04b only.
// Re-exported here so the helper registry/menu resolve these names and pages keep importing them from _shared.js.
import {
  terminal, openclawLoopbackProbe, evalSandboxNetwork, evalSandboxFs, OPENSHELL_POLICY_HARDENED,
  sandboxExec, policyGet, policyToYaml, annotatePolicyYaml, mountPolicyMap,
} from "./_openshell.js";
export {
  terminal, openclawLoopbackProbe, evalSandboxNetwork, evalSandboxFs, OPENSHELL_POLICY_HARDENED,
  sandboxExec, policyGet, policyToYaml, annotatePolicyYaml, mountPolicyMap,
};

// ── langchain → _langchain.js ─────────────────────────────────────────
// Re-exported here so the helper registry/menu and existing page imports are unchanged.
import {
  COURSE_PAGES, coursePage, CONTEXT_WINDOWS, contextWindow, estimateTokens, coursePages,
} from "./_langchain.js";
export {
  COURSE_PAGES, coursePage, CONTEXT_WINDOWS, contextWindow, estimateTokens, coursePages,
};

// ── A live chat artifact → _chat.js ──────────────────────────────────────────

// The chat-artifact widgets (ensureChatStyles / mountChatUI / mountAgentChat) live in _chat.js.
// The _chat.js -> _shared.js import cycle is load-safe because the refs sit inside function bodies, which run only after both modules finish loading.
import { ensureChatStyles, markLiveArtifacts, mountChatUI, mountAgentChat, mountConsole } from "./_chat.js";
export { ensureChatStyles, markLiveArtifacts, mountChatUI, mountAgentChat, mountConsole };
import { mountOpenClawCliRuntime } from "./_openclaw_cli.js";

export function mountOpenClawCli(target) {
  /* @doc <code>helpers.mountOpenClawCli(target)</code> ::
       Mount the live OpenClaw command/chat artifact without copying gateway RPC,
       session-tab, autocomplete, and rendering plumbing into a learner cell. */
  return mountOpenClawCliRuntime(target, {
    mountConsole,
    getOpenClawConnection,
    openclawGatewayWsUrl,
    openclawChat,
  });
}

// Render search results into one text blob (numbered snippets with title + body + url) that the LLM can read as a tool result.
export function formatSearchResults(searchOut) {
  /* @doc <code>helpers.formatSearchResults(out)</code> ::
       Turn a <code>webSearch</code> or <code>instantAnswer</code> result into a numbered
       text block the LLM can read as a tool message. */
  if (searchOut.unreachable) {
    const api = searchOut.source === "glossary-term" ? "NVIDIA glossary term lookup" : "NVIDIA glossary index";
    return `(search unavailable: ${searchOut.error || "HTTP " + searchOut.status}. ` +
           `The ${api} ships with the course as a static file; this is usually a transient load error, so try again.)`;
  }
  if (!searchOut.results.length) {
    return `(no results for "${searchOut.query}". Tell the user you could not find current information on this; do not answer from memory.)`;
  }
  return searchOut.results.map((r, i) => {
    const tier = r.tier === "on_demand" ? "  (on-demand: open the link for the full source)"
               : r.tier === "cached" ? "  (cached)" : "";
    return `[${i + 1}] ${r.title}${tier}\n    ${r.body}\n    ${r.href}`;
  }).join("\n\n");
}

export function delay(ms, signal = null) {
  /* @doc <code>helpers.delay(ms)</code> ::
       Wait without trapping the learner in a running cell. CanvasFlow and RunCell
       automatically connect this helper to their Stop button; pass another
       <code>AbortSignal</code> only when the wait belongs to a different lifecycle. */
  const waitMs = Number(ms);
  if (!Number.isFinite(waitMs) || waitMs < 0) throw new TypeError("helpers.delay expects a non-negative number of milliseconds");
  if (signal?.aborted) return Promise.reject(new DOMException("stopped", "AbortError"));
  return new Promise((resolve, reject) => {
    const timer = setTimeout(done, waitMs);
    function cleanup() { signal?.removeEventListener("abort", stop); }
    function done() { cleanup(); resolve(); }
    function stop() { clearTimeout(timer); cleanup(); reject(new DOMException("stopped", "AbortError")); }
    signal?.addEventListener("abort", stop, { once: true });
  });
}

// ── viz.* builders → _viz.js ─────────────────────────────────────────────────

// The canvas visualization builders (makeViz) live in _viz.js, imported here because both mountCanvasFlow and the VIZ_BUILDERS registry below use it.
// The _viz.js -> _shared.js cycle is load-safe: a builder calls diagramSVG/ganttBarsSVG only when a cell invokes a viz helper, never at load.
import { makeViz } from "./_viz.js";
export const VIZ_BUILDERS = makeViz(() => {});

// ── Helper registry (single source of truth for the canvas helper menu) ───────

// The menu enumerates these and reads each one's source via Function.toString(), so the source cannot drift from the definition.
// `viz.*` source comes from the live viz object once a node has run; `state`, `fetch`, `trace`, and `log` are described by SPECIALS, since they are values and closures, not module functions.
export const HELPER_FNS = {
  chat, chatStream, webSearch, instantAnswer, formatSearchResults,
  embed, cosineSim, fetchRetry, delay, getConfig, getKey, getModelApiBaseUrl, setModelApiBaseUrl, isDefaultModelApiBaseUrl, terminal, openclawLoopbackProbe,
  coursePage, coursePages, contextWindow, estimateTokens, browserChatFetch, diagramSVG, ganttBarsSVG, mountFigures, openFigureLightbox, wireFigureZoom, mountChatUI, mountAgentChat, mountConsole, mountOpenClawCli, mountKeyPanel, mountModelEndpointProbe, openclawChat, openclawGatewayWsUrl, refreshOpenClawGatewayToken, getOpenClawConnection, setOpenClawConnection, getOpenClawProxyConfig, setOpenClawProxyConfig,
  filterOpenClawRuntimeNoise, filterOpenClawRuntimeValue, openclawMessageText, openclawResultText,
  evalSandboxNetwork, evalSandboxFs, sandboxExec, policyGet, mountPolicyMap,
};
// Menu entries that are values or closures rather than plain exported functions.
// Each row owns one signature, description, and source example.
export const SPECIALS = {
  state: {
    sig: "<code>state</code>",
    desc: `Plain object shared across every node. Set a field in one node (e.g. <code>state.question = "…"</code>) and any later node reads it. Reset when you click <strong>▶ Run all</strong>.`,
    src: `// Shared object for this Run-all.
// Write in one node, read in later nodes.
state.docVectors = await helpers.embed(chunks, { inputType: "passage" });
const hits = rank(state.docVectors, queryVector);`,
  },
  fetch: {
    sig: "<code>helpers.fetch(url, opts)</code>",
    desc: `The browser's native <code>fetch</code>, exposed unchanged so a node can call any HTTP endpoint directly. Same arguments and same <code>Response</code> as the platform API. It does <em>not</em> retry and does <em>not</em> attach a key: for flaky upstreams use <code>helpers.fetchRetry</code>, and for model, search, or embedding calls prefer the dedicated helpers above (they add the route and the key for you).`,
    src: `// Browser fetch, unchanged. You own retries and auth.
const r = await helpers.fetch("https://api.example.com/v1/items", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ q: "hello" }),
});
if (!r.ok) throw new Error("HTTP " + r.status);
const data = await r.json();

// Prefer helpers.chat, webSearch, embed, or fetchRetry when they fit.`,
  },
  trace: {
    sig: "<code>helpers.trace(name, attrs)</code>",
    desc: `Emit an OTel-shaped span event into a per-canvas trace store. Instrument any step that does work, not just LLM calls. Read <code>state.__trace</code> from a later node to inspect every emit.`,
    src: `// Add a span to state.__trace.
helpers.trace("retrieve", { k: 5, ms: 42, hits: hits.length });
console.table(state.__trace);`,
  },
  log: {
    sig: "<code>helpers.log(...args)</code>",
    desc: `Append to this cell's <em>log</em> area. Plain values append as text; objects render as highlighted JSON. CanvasFlow and RunCell share the same surfaces: <code>log(...args)</code>, <code>log.h(title)</code>, <code>log.json(label?, value)</code>, <code>log.kv(object)</code>, <code>log.details(summary, body)</code>, <code>log.html(html)</code>, <code>log.svg(svgString)</code>, <code>log.draw(W, H, body, opts)</code>, and <code>log.clear()</code>.`,
    src: `// Write to this cell's output; strings stay text and objects render as JSON.
helpers.log.h("retrieval");                         // section heading
helpers.log("retrieved", hits.length, "chunks");   // text line; extra args are space-joined
helpers.log.json("usage", res.usage);               // labeled JSON rendering
helpers.log.kv({ k: 5, hits: hits.length });         // compact key/value row
helpers.log.details("raw response", res);           // collapsible block (object or string body)
helpers.log.html("<b>done</b>");                    // trusted HTML
helpers.log.svg("<svg viewBox='0 0 80 80'>...</svg>");  // inline SVG
helpers.log.draw(320, 120, '<circle cx="60" cy="60" r="40" fill="var(--gfx-green)"/>', { title: "demo" });
helpers.log.clear();                                 // clear this cell's log/output`,
  },
  signal: {
    sig: "<code>helpers.signal</code>",
    desc: `The <code>AbortSignal</code> for this run, wired to the Stop button. <code>helpers.delay</code>, <code>helpers.chat</code>, and <code>chatStream</code> use it automatically. Pass it to <code>helpers.fetch</code> or to your own <code>WebSocket</code> cleanup so a long run actually cancels when the student hits Stop.`,
    src: `// AbortSignal for this run.
const r = await helpers.fetch(url, { signal: helpers.signal });
helpers.signal.addEventListener("abort", () => ws.close(), { once: true });`,
  },
};

// Helper docs live beside the helper bodies, then fall back to SPECIALS here.

// ── UI helpers ────────────────────────────────────────────────────────────────
export function $ (sel) { return document.querySelector(sel); }
export function $$ (sel) { return [...document.querySelectorAll(sel)]; }

export function renderOutput(el, content, type = "text") {
  if (!el) return;
  el.innerHTML = "";
  el.className = `output ${type}`;
  if (type === "json") {
    const pre = document.createElement("pre");
    pre.textContent = typeof content === "string" ? content : JSON.stringify(content, null, 2);
    el.appendChild(pre);
  } else {
    el.textContent = content;
  }
}

export function setRunning(btn, running) {
  btn.disabled = running;
  btn.textContent = running ? "⏳ Running…" : "▶ Run";
}

export function showError(el, msg) {
  if (!el) return;
  el.innerHTML = `<span class="err">⚠ ${escHtml(msg)}</span>`;
  el.className = "output error";
}

export function escHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// ── Page nav ──────────────────────────────────────────────────────────────────

// In-course navigation lives in the journey-map widget below the topbar: current section, prev/next links, and a "Course map" toggle for the full staircase.
// The topbar carries the brand and the key-pill only.
export function buildNav(currentFile) {
  /* @doc <code>helpers.buildNav(currentFile)</code> ::
       The persistent course menu for the sticky topbar: one compact pill per page (its id),
       the current page marked, every pill a real link so the jump bar stays visible and the
       link graph sees the edges. The in-body journey map is the rich view; this is the
       always-there way back and forward. */
  return (_JM_STEPS || []).filter(function (s) { return s.href; }).map(function (s) {
    var cur = s.href === currentFile ? " cur" : "";
    var t = (s.title || "").replace(/"/g, "&quot;");
    return '<a class="navpill' + cur + '" href="' + s.href + '" title="' + t + '">' + s.id + '</a>';
  }).join("");
}

// ── Journey map ─────────────────────────────────────────────────────────────

// Per-page progression: one box per sub-page, three per row, each row offset right by STAIR pixels so the figure cascades down a staircase. Call mountJourneyMap(sel, id) with the current step id to highlight its box.
// Done boxes get a dim "✓ Done"; the current box a green "★ You are here"; pending boxes stay neutral. A missing target element makes the call a no-op.
const _JM_STEPS = [
  // Row 1 · Module 1 · Agent basics
  { id: "1a",   href: "01a-loop.html",        title: "The Agent",       sub: "loop · LLM as function" },
  { id: "1b",   href: "01b-react.html",       title: "The ReAct Loop",  sub: "tools · finish_reason" },
  { id: "1c",   href: "01c-tools.html",       title: "Tools at Scale",  sub: "JSON · MCP · routing" },
  // Row 2 · Module 2 · Advanced patterns
  { id: "2a",   href: "02a-routing.html",     title: "Workflows",       sub: "router · planner · ReWOO" },
  { id: "2b",   href: "02b-rag.html",         title: "The Index Agent", sub: "embed · retrieve · bundle" },
  { id: "2c",   href: "02c-deep.html",        title: "Deep Agents",     sub: "planner · sub-agents · VFS" },
  // Row 3 · Module 3 · NemoClaw + OpenClaw
  { id: "3a",   href: "03a-kickstart.html",   title: "Connect NemoClaw", sub: "launchable · first call" },
  { id: "3b",   href: "03b-openclaw.html",    title: "OpenClaw",        sub: "file-as-context · paste URL" },
  { id: "3c",   href: "03c-always-on.html",   title: "Always-On",       sub: "skills · cron" },
  // Row 4 · Module 4 · Safety + Modern CLIs
  { id: "4a",   href: "04a-safety.html",      title: "OpenShell",       sub: "sandbox · policy · CI gate" },
  { id: "4b",   href: "04b-modern-clis.html", title: "Modern CLIs",     sub: "Claude Code · Codex · Cursor" },
  { id: "4c",   href: "04c-going-further.html", title: "Going Further", sub: "Brev · NIMs · Blueprints" },
];

// Friendly label for the banner on the left of the bar.
// Sections 1-4 get a "Section N" label; Going Further is the end of the course.
// The short course has no separate assessment, so the cert belongs to the long course.
function _jmSectionLabel(stepId) {
  if (stepId === "next") return "Going Further";
  const m = String(stepId).match(/^(\d)/);
  return m ? `Section ${m[1]}` : "";
}

export function _escAttr(s) {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

export function mountJourneyMap(targetSel, current) {
  const target = typeof targetSel === "string" ? document.querySelector(targetSel) : targetSel;
  if (!target) return;
  target.dataset.state = "ready";
  const idx  = _JM_STEPS.findIndex(s => s.id === current);
  const cur  = idx >= 0 ? _JM_STEPS[idx] : null;
  const prev = idx > 0                       ? _JM_STEPS[idx - 1] : null;
  const next = idx >= 0 && idx < _JM_STEPS.length - 1 ? _JM_STEPS[idx + 1] : null;
  const sectionLabel = cur ? _jmSectionLabel(cur.id) : "Section";

  // ── Full-staircase SVG (revealed when the section banner is clicked) ──
  const W      = 210;
  const H      = 56;
  const GAP_X  = 16;
  const GAP_Y  = 16;
  const PAD    = 12;
  const STAIR  = 64;
  const perRow = 3;
  const rows   = Math.ceil(_JM_STEPS.length / perRow);
  const viewW  = PAD * 2 + perRow * W + (perRow - 1) * GAP_X + (rows - 1) * STAIR;
  const viewH  = PAD * 2 + rows * H + (rows - 1) * GAP_Y;

  const boxes = _JM_STEPS.map((step, i) => {
    const row = Math.floor(i / perRow);
    const col = i % perRow;
    const x = PAD + col * (W + GAP_X) + row * STAIR;
    const y = PAD + row * (H + GAP_Y);
    const isCurrent = i === idx;
    const isDone    = idx >= 0 && i < idx;
    const fill   = isCurrent ? "rgba(118,185,0,0.16)" : (isDone ? "rgba(118,185,0,0.07)" : "var(--e1,#161616)");
    const stroke = isCurrent ? "var(--g,#76b900)" : (isDone ? "var(--gd,#4a7a00)" : "var(--bd,#2a2a2a)");
    const sw     = isCurrent ? 2.2 : 1.1;
    const titleColor = isCurrent ? "var(--gs,#aee23a)" : (isDone ? "var(--td,#b0b0b0)" : "var(--tx,#f2f2f2)");
    const subColor   = isCurrent ? "var(--g,#76b900)" : (isDone ? "var(--tf,#6a6a6a)" : "var(--td,#a5a5a5)");
    const titlePrefix = isCurrent ? "★ " : (isDone ? "✓ " : "");
    return `
      <a href="${step.href}" style="text-decoration:none;">
        <g>
          <rect x="${x}" y="${y}" width="${W}" height="${H}" rx="8"
                style="fill:${fill};stroke:${stroke};stroke-width:${sw};"/>
          <text x="${x + W/2}" y="${y + 24}" text-anchor="middle"
                style="font:700 13.5px -apple-system,'Segoe UI',sans-serif;fill:${titleColor};">${titlePrefix}${step.title}</text>
          <text x="${x + W/2}" y="${y + 42}" text-anchor="middle"
                style="font:400 10.5px -apple-system,'Segoe UI',sans-serif;fill:${subColor};">${step.sub || ""}</text>
        </g>
      </a>`;
  }).join("");

  // Right-arrows between consecutive boxes within the same row.
  const arrows = [];
  for (let i = 0; i < _JM_STEPS.length - 1; i++) {
    const row1 = Math.floor(i / perRow), col1 = i % perRow;
    const row2 = Math.floor((i + 1) / perRow);
    if (row1 !== row2) continue;
    const x1 = PAD + col1 * (W + GAP_X) + row1 * STAIR + W;
    const x2 = x1 + GAP_X;
    const cy = PAD + row1 * (H + GAP_Y) + H / 2;
    arrows.push(`<path d="M ${x1} ${cy} L ${x2} ${cy}" style="stroke:var(--tf,#6f6f6f);stroke-width:1.4;fill:none" marker-end="url(#jm-arr)"/>`);
  }
  const fullSvg = `
    <svg viewBox="0 0 ${viewW} ${viewH}" preserveAspectRatio="xMidYMid meet"
         xmlns="http://www.w3.org/2000/svg"
         role="img" aria-label="Course progression; current step highlighted."
         class="cf-jm-svg" style="display:block;width:100%;height:auto;">
      <defs>
        <marker id="jm-arr" viewBox="0 0 10 10" refX="9" refY="5"
                markerWidth="6" markerHeight="6" orient="auto">
          <path d="M0,0 L10,5 L0,10 Z" style="fill:var(--tf,#6f6f6f)"/>
        </marker>
      </defs>
      ${arrows.join("")}
      ${boxes}
    </svg>`;

  // ── Slim bar: [Section banner] [current page info] [prev] [next] ──
  // Pages with no known current id (e.g. index.html passes null) collapse to one "Course map" banner with no prev/next stubs.
  let barInner;
  if (!cur) {
    barInner = `
      <button class="cf-jm-mod cf-jm-mod-wide" type="button" aria-expanded="false"
              title="Show the whole course map">
        <span class="cf-jm-mod-label">Course map</span>
        <span class="cf-jm-current-title" style="color:var(--td);font-weight:500;font-size:.92rem;margin-left:14px;">click to see all sections</span>
        <span class="cf-jm-mod-chevron" aria-hidden="true" style="margin-left:auto;">▾</span>
      </button>`;
  } else {
    const curId    = cur.id;
    const curTitle = cur.title;
    const curSub   = cur.sub || "";
    const prevLink = prev
      ? `<a class="cf-jm-prev" href="${_escAttr(prev.href)}" title="Previous: ${_escAttr(prev.title)}">
           <span class="cf-jm-nav-arrow">←</span>
           <span class="cf-jm-nav-text">
             <span class="cf-jm-nav-id">${prev.id}</span>
             <span class="cf-jm-nav-title">${prev.title}</span>
           </span>
         </a>`
      : `<span class="cf-jm-prev cf-jm-disabled" aria-hidden="true">
           <span class="cf-jm-nav-arrow">←</span>
           <span class="cf-jm-nav-text"><span class="cf-jm-nav-id">start</span></span>
         </span>`;
    const nextLink = next
      ? `<a class="cf-jm-next" href="${_escAttr(next.href)}" title="Next: ${_escAttr(next.title)}">
           <span class="cf-jm-nav-text">
             <span class="cf-jm-nav-id">${next.id}</span>
             <span class="cf-jm-nav-title">${next.title}</span>
           </span>
           <span class="cf-jm-nav-arrow">→</span>
         </a>`
      : `<span class="cf-jm-next cf-jm-disabled" aria-hidden="true">
           <span class="cf-jm-nav-text"><span class="cf-jm-nav-id">end</span></span>
           <span class="cf-jm-nav-arrow">→</span>
         </span>`;
    barInner = `
      <button class="cf-jm-mod" type="button" aria-expanded="false"
              title="Show the whole course map">
        <span class="cf-jm-mod-label">${sectionLabel}</span>
        <span class="cf-jm-mod-chevron" aria-hidden="true">▾</span>
      </button>
      <div class="cf-jm-current">
        <span class="cf-jm-current-id">${curId.toUpperCase()}</span>
        <span class="cf-jm-current-title">${curTitle}</span>
        ${curSub ? `<span class="cf-jm-current-sub">${curSub}</span>` : ""}
      </div>
      <div class="cf-jm-nav-group">
        ${prevLink}
        ${nextLink}
      </div>`;
  }

  target.innerHTML = `
    <div class="cf-jm-wrap">
      <div class="cf-jm-bar">
        ${barInner}
      </div>
      <div class="cf-jm-full" hidden>
        ${fullSvg}
      </div>
    </div>`;

  // Click handler: toggle the full staircase.
  const modBtn = target.querySelector(".cf-jm-mod");
  const full   = target.querySelector(".cf-jm-full");
  const chev   = target.querySelector(".cf-jm-mod-chevron");
  if (modBtn && full) {
    modBtn.addEventListener("click", () => {
      const expanded = full.hidden;
      full.hidden = !expanded;
      modBtn.setAttribute("aria-expanded", String(expanded));
      if (chev) chev.textContent = expanded ? "▴" : "▾";
    });
  }
}

// ── Mode indicator. Call on page load to update key-pill ────────────────────

// Verify the saved bearer key is accepted (GET /models, the cheapest authenticated call), not merely present. Cached per tab session so navigation does not re-hit the API.
// Only a hard 401/403 marks the key bad, so a network blip never downgrades a working key.
async function keyAccepted() {
  const cached = sessionStorage.getItem("nvapi_ok");
  if (cached) return cached === "1";
  const cfg = await getConfig();
  try {
    const r = await fetchRetry(`${cfg.url}/models`, {
      headers: _apiHeaders(cfg), credentials: modelRequestCredentials(cfg.url),
    }, { retries: 0, timeoutMs: 7000 });
    if (r.status === 401 || r.status === 403) { sessionStorage.setItem("nvapi_ok", "0"); return false; }
    if (r.ok) sessionStorage.setItem("nvapi_ok", "1");
    return r.ok;
  } catch (_) { return true; }   // network blip: do not cry wolf on a key that may be fine
}

export async function updateKeyPill(pill) {
  if (!pill) return;
  const cfg = await getConfig();
  if (cfg.needsKey && !hasKey()) {
    pill.textContent = "No API key"; pill.classList.remove("set"); return;
  }
  pill.textContent = "Key …"; pill.classList.add("set");
  const ok = await keyAccepted();
  if (ok) { pill.textContent = "Key set ✓"; pill.classList.add("set"); pill.title = "model key verified this session"; }
  else { pill.textContent = "Key rejected ✗"; pill.classList.remove("set"); pill.title = "the saved nvapi key was refused (401/403). Re-enter it on Module 1a."; }
}

// Is the launchable's gateway reachable right now?
// The connect.challenge frame arrives only when the browser's launchable access session is valid, so this detects an expired session that mere URL and token presence cannot.
// Best-effort, ~6s cap.
function clawSessionOk(timeoutMs = 6000) {
  const connection = getOpenClawConnection();
  if (!connection.rawUrl) return Promise.resolve(false);
  const wsUrl = openclawGatewayWsUrl(connection.rawUrl, connection.accessSession, null, null, connection.accessProvider).url;
  return new Promise(res => {
    let done = false, ws;
    const finish = ok => { if (done) return; done = true; try { ws.close(); } catch (_) {} res(ok); };
    try { ws = new WebSocket(wsUrl); } catch (_) { return res(false); }
    const t = setTimeout(() => finish(false), timeoutMs);
    ws.onmessage = ev => { try { if (JSON.parse(ev.data).event === "connect.challenge") { clearTimeout(t); finish(true); } } catch (_) {} };
    ws.onerror = () => { clearTimeout(t); finish(false); };
    ws.onclose = () => { clearTimeout(t); finish(false); };
  });
}

// ── OpenClaw indicator. Re-validates the live session on every page load, because a
// Stored URL and token say nothing about whether the launchable access session still works.
export async function updateClawPill(pill) {
  if (!pill) return;
  const connection = getOpenClawConnection();
  const url = connection.rawUrl;
  const token = connection.token;
  if (!(url && token)) { pill.textContent = "No OpenClaw"; pill.classList.remove("set"); pill.title = ""; return; }
  const host = url.replace(/^https?:\/\//, "").replace(/\/.*$/, "");
  pill.textContent = "OpenClaw …"; pill.classList.add("set"); pill.title = host + " · checking session";
  const ok = await clawSessionOk();
  if (ok) {
    pill.textContent = "OpenClaw ✓"; pill.classList.add("set"); pill.title = host + " · session live";
    try { localStorage.setItem("nemoclaw_claw_verified_at", String(Date.now())); } catch (_) {}
  } else {
    pill.textContent = "OpenClaw ⚠"; pill.classList.remove("set");
    pill.title = host + " · session expired or unreachable. Open the launchable and reconnect on Kickstart.";
  }
}

// ── Inline API-key setup panel → _keypanel.js ───────────────────────────────
// mountKeyPanel lives in _keypanel.js.
// Re-exported here so HELPER_FNS, the menu, and 01a's import are unchanged.
import { mountKeyPanel } from "./_keypanel.js";
export { mountKeyPanel };

// ── openclaw → _openclaw.js ─────────────────────────────────────────
// Re-exported here so the helper registry/menu and existing page imports are unchanged.
import {
  gatewayTokenFromAgentMetadata, getOpenClawConnection, getOpenClawProxyConfig, mountClawGateway, mountClawProbe,
  mountEndpointProbe, mountModelEndpointProbe, openclawChat, openclawGatewayWsUrl, refreshOpenClawGatewayToken,
  filterOpenClawRuntimeNoise, filterOpenClawRuntimeValue, openclawMessageText, openclawResultText,
  setOpenClawConnection, setOpenClawProxyConfig, GW_CONNECT, mountGwRecover,
} from "./_openclaw.js";
export {
  gatewayTokenFromAgentMetadata, getOpenClawConnection, getOpenClawProxyConfig, mountClawGateway, mountClawProbe,
  mountEndpointProbe, mountModelEndpointProbe, openclawChat, openclawGatewayWsUrl, refreshOpenClawGatewayToken,
  filterOpenClawRuntimeNoise, filterOpenClawRuntimeValue, openclawMessageText, openclawResultText,
  setOpenClawConnection, setOpenClawProxyConfig, GW_CONNECT, mountGwRecover,
};


// ── Theme toggle ─────────────────────────────────────────────────────────────

// A dark/light switch in the topbar. The active theme is data-theme on <html>, remembered in localStorage.
// The standalone sets data-theme before paint (a <head> script injected by bundle_standalone.py) so the page opens in the right palette with no flash; styles/_style.css carries the matching light palette.
// No-ops in the topbar-less iframe.
export function mountThemeToggle() {
  /* @doc <code>helpers.mountThemeToggle()</code> ::
       Adds a dark/light toggle to the <code>.topbar</code>, saving the choice in
       <code>localStorage</code> under <code>theme</code>. No-ops with no topbar (the iframe
       export) or if one is already mounted. */
  const bar = document.querySelector(".topbar");
  if (!bar || bar.querySelector(".theme-toggle")) return;
  const root = document.documentElement;
  // The rendered theme is whatever data-theme says (set pre-paint in the standalone), or the dark :root default.
  // The OS-preference default lives only in that pre-paint init.
  const current = () => root.getAttribute("data-theme") || "dark";
  const btn = document.createElement("button");
  btn.className = "theme-toggle";
  btn.type = "button";
  btn.setAttribute("aria-label", "Toggle dark or light theme");
  btn.style.cssText = "flex:0 0 auto;margin-left:10px;width:30px;height:30px;display:inline-flex;" +
    "align-items:center;justify-content:center;font-size:15px;line-height:1;cursor:pointer;" +
    "background:transparent;color:var(--td);border:1px solid var(--bd);border-radius:7px;";
  function paint() {
    const t = current();
    // Show the icon for the theme the click switches TO.
    btn.textContent = t === "light" ? "☾" : "☀"; // moon -> go dark, sun -> go light
    btn.title = t === "light" ? "Switch to dark theme" : "Switch to light theme";
  }
  btn.addEventListener("click", () => {
    const next = current() === "light" ? "dark" : "light";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("theme", next); } catch (_) {}
    paint();
  });
  paint();
  const pill = bar.querySelector(".key-pill");
  if (pill) bar.insertBefore(btn, pill);
  else bar.appendChild(btn);
}

function headingId(text, occupied) {
  const base = String(text || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "section";
  let candidate = base;
  let suffix = 2;
  while (occupied.has(candidate)) candidate = `${base}-${suffix++}`;
  occupied.add(candidate);
  return candidate;
}

function headingLinkIcon() {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", "M10.6 13.4a4.5 4.5 0 0 0 6.36.01l2.12-2.12a4.5 4.5 0 0 0-6.36-6.36l-1.21 1.2m1.9 4.47a4.5 4.5 0 0 0-6.37-.01l-2.12 2.12a4.5 4.5 0 1 0 6.37 6.36l1.2-1.2");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  icon.append(path);
  return icon;
}

const LEARNING_PATH_IMAGES = Object.freeze({
  "how-to-build-an-ai-agent": "how-to-build-ai-agent-ari.jpg",
  "how-to-build-agentic-ai-rag": "agentic-rag-application-ari.jpg",
  "how-to-evaluate-ai-agents": "how-to-evaluate-ai-agents.jpg",
  "how-to-customize-ai-agents": "how-to-customize-ai-agents.jpg",
  "how-to-build-deep-ai-agents": "how-to-build-deep-ai-agents.jpg",
  "how-to-build-safer-autonomous-agent-using-openclaw": "how-to-build-a-safer-autonomous-agent-using-nemo-claw.jpg",
});
const LEARNING_PATH_IMAGE_ROOT = "https://developer.download.nvidia.com/images/learning-pathways/";

const RESOURCE_FIGURES = Object.freeze({
  "https://build.nvidia.com/spark/nemoclaw-applications?ncid=ref-dli-146986": {
    image: "https://build.nvidia.com/opengraph-image.jpg?6ec102a0470b935b&ncid=ref-dli-146986",
    fit: "cover",
  },
  "https://developer.nvidia.com/nemo-retriever": {
    image: "https://developer.download.nvidia.com/images/nemo-retriever/nemo-retriever-diagram-1920x1080.jpg",
    fit: "contain",
  },
});

const FIGURE_SOURCE_LABELS = Object.freeze({
  en: "Image source",
  es: "Fuente de la imagen",
  pt: "Fonte da imagem",
});

const GOING_FURTHER_TEXT = Object.freeze({
  en: {
    assistantPrompt: "Want to inspect this page or trace a concept across modules?",
    assistantButton: "Ask about this course",
    knowledgeIntro: "The Index Agent in Module 2b used a small in-page corpus. These resources show how to prepare, retrieve, and guard production data.",
    interfaceHeading: "Carry the browser interface forward",
  },
  es: {
    assistantPrompt: "¿Quieres consultar esta página o seguir un concepto entre módulos?",
    assistantButton: "Pregunta sobre el curso",
    knowledgeIntro: "El agente de índice del Módulo 2b utilizó un corpus pequeño dentro de la página. Estos recursos muestran cómo preparar, recuperar y proteger datos de producción.",
    interfaceHeading: "Lleva la interfaz del navegador a otros entornos",
  },
  pt: {
    assistantPrompt: "Quer consultar esta página ou acompanhar um conceito entre módulos?",
    assistantButton: "Pergunte sobre o curso",
    knowledgeIntro: "O agente de índice do Módulo 2b usou um pequeno corpus na própria página. Estes recursos mostram como preparar, recuperar e proteger dados de produção.",
    interfaceHeading: "Leve a interface do navegador para outros ambientes",
  },
});

function canonicalResourceUrl(href) {
  try {
    const url = new URL(href, globalThis.location?.href);
    const base = `${url.origin}${url.pathname.replace(/\/$/, "")}`;
    const ncid = url.searchParams.get("ncid");
    return ncid ? `${base}?ncid=${encodeURIComponent(ncid)}` : base;
  } catch (_) {
    return "";
  }
}

export function learningPathImageUrl(href) {
  try {
    const slug = new URL(href, globalThis.location?.href).pathname.split("/").filter(Boolean).pop();
    const file = LEARNING_PATH_IMAGES[slug];
    return file ? `${LEARNING_PATH_IMAGE_ROOT}${file}` : "";
  } catch (_) {
    return "";
  }
}

export function mountLearningPathCards(root = document) {
  root.querySelectorAll("#learning-path .step-card").forEach((card) => {
    if (card.querySelector(":scope > .step-card-media")) return;
    const heading = card.querySelector("h3");
    const button = card.querySelector("a.btn[href]");
    const imageUrl = learningPathImageUrl(button?.href);
    if (!heading || !button || !imageUrl) return;

    const title = heading.textContent.split("·").slice(1).join("·").trim() || heading.textContent.trim();
    const media = document.createElement("a");
    media.className = "step-card-media";
    media.href = button.href;
    media.target = button.target;
    media.rel = button.rel;
    media.setAttribute("aria-label", `${button.textContent.replace("→", "").trim()}: ${title}`);
    const image = document.createElement("img");
    image.src = imageUrl;
    image.alt = title;
    image.loading = "lazy";
    image.decoding = "async";
    image.referrerPolicy = "no-referrer";
    media.append(image);

    const body = document.createElement("div");
    body.className = "step-card-body";
    while (card.firstChild) body.append(card.firstChild);
    card.append(media, body);
  });
}

export function mountResourceFigures(root = document) {
  root.querySelectorAll('a[href^="https://"]').forEach((sourceLink) => {
    const resource = RESOURCE_FIGURES[canonicalResourceUrl(sourceLink.href)];
    const section = sourceLink.closest(".section");
    if (!resource || !section || section.querySelector(":scope > .resource-aside-figure")) return;

    const title = sourceLink.textContent.trim();
    if (!title) return;

    const media = document.createElement("a");
    media.className = `resource-aside-media resource-aside-media--${resource.fit}`;
    media.href = sourceLink.href;
    media.target = sourceLink.target;
    media.rel = sourceLink.rel;
    media.setAttribute("aria-label", title);

    const image = document.createElement("img");
    image.src = resource.image;
    image.alt = title;
    image.loading = "lazy";
    image.decoding = "async";
    image.referrerPolicy = "no-referrer";
    media.append(image);

    const locale = root.documentElement?.lang?.split("-")[0] || "en";
    const caption = document.createElement("figcaption");
    caption.append(`${FIGURE_SOURCE_LABELS[locale] || FIGURE_SOURCE_LABELS.en}: `);
    const captionLink = sourceLink.cloneNode(true);
    captionLink.textContent = title;
    caption.append(captionLink);

    const figure = document.createElement("figure");
    figure.className = "resource-aside-figure";
    figure.append(media, caption);
    section.classList.add("resource-aside-section");
    section.querySelector(":scope > h2")?.insertAdjacentElement("afterend", figure);
  });
}

function trimAfterFirstSentence(element) {
  if (!element) return;
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  const trailing = [];
  let foundEnd = false;
  while (walker.nextNode()) {
    const text = walker.currentNode;
    if (foundEnd) {
      trailing.push(text);
      continue;
    }
    const sentenceEnd = text.data.indexOf(".");
    if (sentenceEnd < 0) continue;
    text.data = text.data.slice(0, sentenceEnd + 1);
    foundEnd = true;
  }
  trailing.forEach(text => text.remove());
}

export function mountGoingFurtherLayout(root = document) {
  const main = root.querySelector("main");
  const learningPath = root.querySelector("#learning-path");
  const whereNext = root.querySelector('details[data-learning-id="production-divergence"]');
  const readingList = root.querySelector('details[data-learning-id="course-reading-list"]');
  const deploy = root.querySelector('a[href*="/spark/nemoclaw-applications"]')?.closest(".section");
  const addKnowledge = root.querySelector('a[href="https://developer.nvidia.com/nemo-retriever"]')?.closest(".section");
  const carryInterface = root.querySelector('a[href*="use-live-artifacts-in-claude-cowork"]')?.closest(".section");
  const built = root.querySelector('a[href*="building-effective-agents"]')?.closest(".section");
  const deploymentLessons = root.querySelector(".pattern-list")?.closest(".section");
  const helperList = root.querySelector(".lp-helpers");
  const assistantButton = root.querySelector("#open-course-assistant");
  const whereSection = whereNext?.querySelector(".section");
  if (!main || !learningPath || !whereNext || !readingList || !deploy || !addKnowledge
      || !carryInterface || !built || !deploymentLessons || !helperList || !assistantButton || !whereSection) return;
  if (main.dataset.goingFurtherLayout === "ready") return;

  const helperHeading = helperList.previousElementSibling;
  if (helperHeading?.matches("h2, h3, h4")) whereSection.append(helperHeading, helperList);

  const lessonEyebrow = deploymentLessons.querySelector(":scope > .section-eyebrow");
  const lessonHeading = deploymentLessons.querySelector(":scope > h2");
  const lessonDisclosure = root.createElement("details");
  lessonDisclosure.className = "learning-block deployment-lessons";
  const lessonSummary = root.createElement("summary");
  const lessonScope = root.createElement("span");
  lessonScope.className = "learning-scope";
  lessonScope.textContent = lessonEyebrow?.textContent.trim() || "Lessons";
  const lessonQuestion = root.createElement("span");
  lessonQuestion.className = "learning-question";
  lessonQuestion.textContent = lessonHeading?.textContent.trim() || "Review before deployment";
  lessonSummary.append(lessonScope, lessonQuestion);
  lessonEyebrow?.remove();
  lessonHeading?.remove();
  lessonDisclosure.append(lessonSummary, deploymentLessons);
  whereSection.append(lessonDisclosure);

  const assistantButtonRow = assistantButton.closest("p");
  const assistantCallout = assistantButtonRow?.previousElementSibling;
  const assistantParagraph = assistantCallout?.previousElementSibling;
  const assistantHeading = assistantParagraph?.previousElementSibling;
  const builtParagraphs = [...built.querySelectorAll(":scope > p")];
  trimAfterFirstSentence(builtParagraphs.at(-1));
  const locale = root.documentElement?.lang?.split("-")[0] || "en";
  const pageText = GOING_FURTHER_TEXT[locale] || GOING_FURTHER_TEXT.en;
  const knowledgeIntro = addKnowledge.querySelector(":scope > p");
  const interfaceHeading = carryInterface.querySelector(":scope > h2");
  if (knowledgeIntro) knowledgeIntro.textContent = pageText.knowledgeIntro;
  if (interfaceHeading) interfaceHeading.textContent = pageText.interfaceHeading;
  if (assistantParagraph && assistantCallout && assistantButtonRow) {
    assistantParagraph.textContent = pageText.assistantPrompt;
    assistantButton.textContent = pageText.assistantButton;
    const handoff = root.createElement("div");
    handoff.className = "going-further-assistant";
    handoff.append(assistantParagraph, assistantButtonRow);
    built.append(assistantCallout, handoff);
  }
  if (assistantHeading?.matches("h2")) assistantHeading.remove();

  built.dataset.goingFurtherSection = "built";
  deploy.dataset.goingFurtherSection = "deploy";
  addKnowledge.dataset.goingFurtherSection = "knowledge";
  carryInterface.dataset.goingFurtherSection = "interface";
  whereSection.dataset.goingFurtherSection = "next";
  learningPath.dataset.goingFurtherSection = "learning-path";
  readingList.dataset.goingFurtherSection = "sources";
  readingList.removeAttribute("data-learning-always-open");
  readingList.open = false;

  whereNext.replaceWith(whereSection);

  main.insertBefore(built, deploy);
  deploy.insertAdjacentElement("afterend", addKnowledge);
  addKnowledge.insertAdjacentElement("afterend", carryInterface);
  carryInterface.insertAdjacentElement("afterend", whereSection);
  whereSection.insertAdjacentElement("afterend", learningPath);
  learningPath.insertAdjacentElement("afterend", readingList);
  main.dataset.goingFurtherLayout = "ready";
}

export function mountCourseFavicon(root = document) {
  if (root.head?.querySelector('link[rel~="icon"]')) return;
  const link = root.createElement("link");
  link.rel = "icon";
  link.type = "image/x-icon";
  link.href = new URL("../assets/favicon.ico", import.meta.url).href;
  root.head?.append(link);
}

export function mountHeadingLinks() {
  const main = document.querySelector("main");
  if (!main) return;
  const occupied = new Set([...document.querySelectorAll("[id]")].map((node) => node.id));
  main.querySelectorAll("h1, h2, h3, h4, h5, h6").forEach((heading) => {
    if (heading.classList.contains("heading-link-target")) return;
    // A heading inside any interactive surface already inherits that surface's
    // action. Adding a permalink would create competing nested controls: linked
    // cards would scroll instead of opening, and summary/button clicks would be
    // ambiguous for keyboard and pointer users.
    if (heading.closest('a[href], button, summary, [role="button"], [role="link"]')) return;
    if (!heading.id) heading.id = headingId(heading.textContent, occupied);
    else occupied.add(heading.id);

    heading.classList.add("heading-link-target");
    const label = heading.textContent.trim();
    heading.setAttribute("aria-label", label);
    const icon = document.createElement("a");
    icon.className = "heading-anchor";
    icon.href = `#${heading.id}`;
    icon.setAttribute("aria-label", `Link to ${label}`);
    icon.title = "Copy link to this section";
    icon.append(headingLinkIcon());
    heading.prepend(icon);

    if (!heading.querySelector("a:not(.heading-anchor)")) {
      const title = document.createElement("a");
      title.className = "heading-permalink";
      title.href = `#${heading.id}`;
      while (heading.lastChild && heading.lastChild !== icon) title.prepend(heading.lastChild);
      heading.append(title);
    }
  });
}

// Auto-mount on any page that ships a topbar (the lab and the full standalone).
if (typeof document !== "undefined") {
  mountCourseFavicon();
  const _boot = () => { mountLearningView(); mountThemeToggle(); mountLanguageMenu(); mountLearningPathCards(); mountResourceFigures(); mountGoingFurtherLayout(); mountHeadingLinks(); mountFigures(); markLiveArtifacts(); mountCourseLicenseNote(); mountCourseAssistant({ embed }); };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _boot);
  } else {
    _boot();
  }
}
