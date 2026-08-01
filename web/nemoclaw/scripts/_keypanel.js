// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// _keypanel.js holds the inline API-key setup panel (mountKeyPanel) that used to live in _shared.js.
import {
  DEFAULT_MODEL, DEFAULT_MODEL_API_BASE_URL, browserChatFetch, chat,
  getEmbeddingApiBaseUrl, getEmbeddingKey, getEmbeddingModelId, getKey, getModelApiBaseUrl, getModelId,
  getModelRequestPolicy, hasKey, normalizeModelApiBaseUrl, normalizeModelId,
  normalizeModelRequestRetries, normalizeModelRequestTimeoutMs, setEmbeddingApiBaseUrl, setEmbeddingKey,
  setEmbeddingModelId, setKey, setModelApiBaseUrl, setModelId, updateKeyPill,
  iframeProxyModeEnabled, setIframeProxyMode, setModelRequestRetries, setModelRequestTimeoutMs,
} from "./_shared.js";

const BUILD_SIGNUP_URL = "https://build.nvidia.com/?ncid=ref-dli-146986";

export function mountKeyPanel(container, opts = {}) {
  /* @doc <code>helpers.mountKeyPanel(el)</code> ::
       Renders an inline API-key setup panel using the existing <code>.key-panel</code> CSS
       classes. When a key is saved it shows a compact "? saved" row with a Change button. On
       save, strips invisible Unicode, verifies live, then updates the topbar
       <code>#key-status</code> pill.
  */
  const el = typeof container === "string" ? document.querySelector(container) : container;
  if (!el) return null;
  const _clean = raw => raw.trim().replace(/[^ -~]/g, "");
  const _attr = raw => String(raw).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const _setState = state => {
    el.dataset.state = state;
    el.setAttribute("aria-busy", state === "running" ? "true" : "false");
  };
  function _draw() {
    const keySaved = hasKey();
    _setState(keySaved ? "ready" : "empty");
    const modelApiBaseUrl = getModelApiBaseUrl();
    const modelId = getModelId();
    const embeddingApiBaseUrl = getEmbeddingApiBaseUrl();
    const embeddingModelId = getEmbeddingModelId();
    const customEndpoint = modelApiBaseUrl !== DEFAULT_MODEL_API_BASE_URL;
    const filePreview = globalThis.location?.protocol === "file:";
    const proxyChecked = !customEndpoint && iframeProxyModeEnabled();
    const requestPolicy = getModelRequestPolicy();
    const timeoutSeconds = Math.round(requestPolicy.timeoutMs / 1000);
    if (keySaved) {
      el.innerHTML = `<div class="key-panel key-panel-saved">
        <span class="key-saved-label">&#10003; API key available in this tab</span>
        <span class="key-endpoint-label">Chat route: <code>${_attr(modelApiBaseUrl)}</code> · <code>${_attr(modelId)}</code></span>
        <span class="key-endpoint-label">Embedding route: <code>${_attr(embeddingApiBaseUrl)}</code> · <code>${_attr(embeddingModelId)}</code></span>
        <label class="iframe-proxy-toggle-row">
          <input type="checkbox" class="iframe-proxy-toggle" ${proxyChecked ? "checked" : ""} ${customEndpoint || filePreview ? "disabled" : ""}/>
          ${customEndpoint ? "Custom endpoint uses direct browser requests" : filePreview ? "Local file preview uses the NVIDIA DLI browser relay" : "Use the NVIDIA DLI browser relay"}
        </label>
        <details class="request-settings">
          <summary>Request handling: wait ${timeoutSeconds}s · ${requestPolicy.retries} automatic ${requestPolicy.retries === 1 ? "retry" : "retries"}</summary>
          <p>Failures stay visible. Retries apply only to network failures, HTTP 429, and transient 5xx responses.</p>
          <label>Wait for response headers or the next stream chunk (seconds)</label>
          <input type="number" class="request-timeout" min="5" max="300" step="5" value="${timeoutSeconds}"/>
          <label>Automatic retries before streaming starts</label>
          <input type="number" class="request-retries" min="0" max="5" step="1" value="${requestPolicy.retries}"/>
          <button class="btn request-save-btn" type="button">Save request handling</button>
          <span class="request-status" role="status"></span>
        </details>
        <button class="btn key-change-btn">Change</button>
      </div>`;
      const toggle = el.querySelector(".iframe-proxy-toggle");
      if (toggle) toggle.onchange = () => {
        setIframeProxyMode(toggle.checked);
        const pill = document.getElementById("key-status");
        if (pill) updateKeyPill(pill);
      };
      el.querySelector(".request-save-btn").onclick = () => {
        const status = el.querySelector(".request-status");
        try {
          setModelRequestTimeoutMs(Number(el.querySelector(".request-timeout").value) * 1000);
          setModelRequestRetries(Number(el.querySelector(".request-retries").value));
          status.textContent = "Saved. Rerun the cell.";
          setTimeout(_draw, 900);
        } catch (error) {
          status.textContent = error.message;
        }
      };
      el.querySelector(".key-change-btn").onclick = () => {
        setKey("");
        const pill = document.getElementById("key-status");
        if (pill) updateKeyPill(pill);
        if (opts.onClear) opts.onClear();
        _draw();
      };
    } else {
      el.innerHTML = `<div class="key-panel">
        <label>Chat API base URL</label>
        <input type="url" class="model-api-base-url" value="${_attr(modelApiBaseUrl)}"
               placeholder="https://integrate.api.nvidia.com/v1" autocomplete="off" spellcheck="false"/>
        <label>Chat model ID</label>
        <input type="text" class="model-id" value="${_attr(modelId)}"
               placeholder="model/provider-id" autocomplete="off" spellcheck="false"/>
        <label>Chat API bearer key (NVIDIA keys start with <code>nvapi-</code>)</label>
        <input type="password" class="model-api-key" placeholder="nvapi-&hellip;" autocomplete="off" spellcheck="false"/>
        <label class="iframe-proxy-toggle-row">
          <input type="checkbox" class="iframe-proxy-toggle" ${proxyChecked ? "checked" : ""} ${filePreview ? "disabled" : ""}/>
          ${filePreview ? "Local file preview uses the NVIDIA DLI browser relay" : "Use the NVIDIA DLI browser relay"}
        </label>
        <details class="embedding-route">
          <summary>Embedding route (persistent and independent)</summary>
          <p>Embedding exercises keep this route when the chat route changes.</p>
          <label>Embedding API base URL</label>
          <input type="url" class="embedding-api-base-url" value="${_attr(embeddingApiBaseUrl)}"
                 placeholder="https://integrate.api.nvidia.com/v1" autocomplete="off" spellcheck="false"/>
          <label>Embedding model ID</label>
          <input type="text" class="embedding-model-id" value="${_attr(embeddingModelId)}"
                 placeholder="nvidia/llama-nemotron-embed-1b-v2" autocomplete="off" spellcheck="false"/>
          <label>Embedding API bearer key</label>
          <input type="password" class="embedding-api-key" placeholder="${getEmbeddingKey() ? "saved separately" : "nvapi-&hellip;"}" autocomplete="off" spellcheck="false"/>
        </details>
        <details class="request-settings">
          <summary>Request handling</summary>
          <p>Failures remain visible. Retries are off by default and apply only before a stream starts.</p>
          <label>Wait for response headers or the next stream chunk (seconds)</label>
          <input type="number" class="request-timeout" min="5" max="300" step="5" value="${timeoutSeconds}"/>
          <label>Automatic retries for network, HTTP 429, or transient 5xx failures</label>
          <input type="number" class="request-retries" min="0" max="5" step="1" value="${requestPolicy.retries}"/>
        </details>
        <button class="btn">Save &amp; verify</button>
        <div class="status"></div>
        <p style="margin:.8em 0 0;font-size:.8rem;color:var(--tf,#8a8a8a)">
          No key yet? <a href="${BUILD_SIGNUP_URL}" target="_blank" rel="noopener">Sign up at build.nvidia.com &rarr;</a>
          then open API Keys and generate one. This tab reuses the keys across lessons and discards them when it closes.
        </p>
      </div>`;
      const input = el.querySelector(".model-api-key");
      const endpointInput = el.querySelector(".model-api-base-url");
      const modelInput = el.querySelector(".model-id");
      const embeddingEndpointInput = el.querySelector(".embedding-api-base-url");
      const embeddingModelInput = el.querySelector(".embedding-model-id");
      const embeddingKeyInput = el.querySelector(".embedding-api-key");
      const timeoutInput = el.querySelector(".request-timeout");
      const retriesInput = el.querySelector(".request-retries");
      const status = el.querySelector(".status");
      const btn = el.querySelector(".btn");
      const toggle = el.querySelector(".iframe-proxy-toggle");
      const syncEndpointMode = () => {
        let custom = true;
        try { custom = normalizeModelApiBaseUrl(endpointInput.value) !== DEFAULT_MODEL_API_BASE_URL; } catch (_) {}
        toggle.disabled = custom || filePreview;
        if (custom) toggle.checked = false;
        else if (filePreview) toggle.checked = true;
      };
      endpointInput.addEventListener("input", syncEndpointMode);
      syncEndpointMode();
      async function save() {
        const key = _clean(input.value);
        let endpoint, model, embeddingEndpoint, embeddingModel, timeoutMs, retries;
        try {
          endpoint = normalizeModelApiBaseUrl(endpointInput.value);
          model = normalizeModelId(modelInput.value);
          embeddingEndpoint = normalizeModelApiBaseUrl(embeddingEndpointInput.value);
          embeddingModel = normalizeModelId(embeddingModelInput.value, getEmbeddingModelId());
          timeoutMs = normalizeModelRequestTimeoutMs(Number(timeoutInput.value) * 1000);
          retries = normalizeModelRequestRetries(Number(retriesInput.value));
        }
        catch (e) { _setState("failed"); status.className = "status err"; status.textContent = e.message; return; }
        const defaultEndpoint = endpoint === DEFAULT_MODEL_API_BASE_URL;
        if ((defaultEndpoint && !key.startsWith("nvapi-")) || (!defaultEndpoint && !key)) {
          _setState("failed");
          status.className = "status err";
          status.textContent = defaultEndpoint ? "Key should start with nvapi-" : "Enter the key for this endpoint";
          return;
        }
        let embeddingKey = _clean(embeddingKeyInput.value) || getEmbeddingKey() || (defaultEndpoint ? key : "");
        if (!embeddingKey) {
          _setState("failed");
          status.className = "status err";
          status.textContent = "Enter the key for the embedding route";
          return;
        }
        if (embeddingEndpoint === DEFAULT_MODEL_API_BASE_URL && !embeddingKey.startsWith("nvapi-")) {
          _setState("failed");
          status.className = "status err";
          status.textContent = "The default embedding route needs an nvapi- key";
          return;
        }
        _setState("running");
        status.className = "status"; status.textContent = "Discovering models and verifying…";
        const previousEndpoint = getModelApiBaseUrl();
        const previousModel = getModelId();
        const previousKey = getKey();
        const previousEmbeddingEndpoint = getEmbeddingApiBaseUrl();
        const previousEmbeddingModel = getEmbeddingModelId();
        const previousEmbeddingKey = getEmbeddingKey();
        const previousProxyMode = iframeProxyModeEnabled();
        const previousRequestPolicy = getModelRequestPolicy();
        try {
          setModelRequestTimeoutMs(timeoutMs);
          setModelRequestRetries(retries);
          if (!defaultEndpoint) {
            const response = await browserChatFetch()(endpoint + "/models", {
              headers: { Authorization: "Bearer " + key },
            });
            if (!response.ok) throw new Error("model discovery failed: HTTP " + response.status);
            let payload;
            try { payload = await response.json(); }
            catch (_) {
              throw new Error("Model discovery did not return JSON. Confirm this endpoint serves the OpenAI-compatible /models route, then try again");
            }
            const models = (payload.data || []).map(item => item?.id).filter(Boolean);
            if (!models.length) throw new Error("model discovery returned no model IDs");
            if (models.length === 1 && (!modelInput.value.trim() || model === DEFAULT_MODEL || !models.includes(model))) {
              model = models[0];
              modelInput.value = model;
            } else if (!models.includes(model)) {
              throw new Error("Model ID is not served by this endpoint. Choose one of: " + models.join(", "));
            }
          }
          if (embeddingEndpoint !== DEFAULT_MODEL_API_BASE_URL) {
            const response = await browserChatFetch()(embeddingEndpoint + "/models", {
              headers: { Authorization: "Bearer " + embeddingKey },
            });
            if (!response.ok) throw new Error("embedding model discovery failed: HTTP " + response.status);
            const payload = await response.json().catch(() => null);
            const models = (payload?.data || []).map(item => item?.id).filter(Boolean);
            if (!models.length) throw new Error("embedding model discovery returned no model IDs");
            if (models.length === 1 && !models.includes(embeddingModel)) {
              embeddingModel = models[0];
              embeddingModelInput.value = embeddingModel;
            } else if (!models.includes(embeddingModel)) {
              throw new Error("Embedding model ID is not served by this endpoint. Choose one of: " + models.join(", "));
            }
          }
          if (previousKey?.startsWith("nvapi-") && !previousEmbeddingKey) setEmbeddingKey(previousKey);
          setModelApiBaseUrl(endpoint);
          setModelId(model);
          setIframeProxyMode(defaultEndpoint && !!toggle?.checked);
          setKey(key);
          setEmbeddingApiBaseUrl(embeddingEndpoint);
          setEmbeddingModelId(embeddingModel);
          setEmbeddingKey(embeddingKey);
          // Give the reasoning-model probe enough tokens to reach its final answer.
          const r = await chat({ messages: [{ role: "user", content: "Reply with the single word: ready" }], max_tokens: 1024 });
          const reply = r.choices?.[0]?.message?.content?.trim();
          status.className = "status ok";
          status.textContent = reply ? `✓ Connected. Model replied: "${reply}"` : "✓ Connected.";
          _setState("ready");
          const pill = document.getElementById("key-status");
          if (pill) updateKeyPill(pill);
          if (opts.onSave) opts.onSave(key);
          setTimeout(_draw, 1400);
        } catch (e) {
          setKey(previousKey || "");
          setModelApiBaseUrl(previousEndpoint);
          setModelId(previousModel);
          setEmbeddingApiBaseUrl(previousEmbeddingEndpoint);
          setEmbeddingModelId(previousEmbeddingModel);
          setEmbeddingKey(previousEmbeddingKey || "");
          setIframeProxyMode(previousProxyMode);
          setModelRequestTimeoutMs(previousRequestPolicy.timeoutMs);
          setModelRequestRetries(previousRequestPolicy.retries);
          _setState("failed");
          status.className = "status err"; status.textContent = `Connection failed: ${e.message}`;
        }
      }
      btn.addEventListener("click", save);
      input.addEventListener("keydown", ev => { if (ev.key === "Enter") save(); });
    }
  }
  _draw();
  try {
    sessionStorage.removeItem("nemoclaw_open_key_panel");
    const params = new URLSearchParams(location.search || "");
    const openKeyPanel = params.get("openKeyPanel") === "1";
    if (openKeyPanel) {
      params.delete("openKeyPanel");
      const qs = params.toString();
      history.replaceState(null, "", location.pathname + (qs ? `?${qs}` : "") + location.hash);
      requestAnimationFrame(() => el.scrollIntoView({ behavior: "smooth", block: "center" }));
    } else if (location.hash === "#key-panel" && hasKey()) {
      history.replaceState(null, "", location.pathname + location.search);
      requestAnimationFrame(() => scrollTo({ top: 0, behavior: "auto" }));
    }
  } catch (_) {}
  return { update: _draw };
}
