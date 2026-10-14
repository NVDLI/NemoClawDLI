// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const SESSION_ID_PATTERN = /^[0-9a-f-]{36}$/;
const REQUEST_TIMEOUT_MS = 10_000;
const initializationAttempts = new Map();
const storageIdentities = new WeakMap();
let nextStorageIdentity = 1;

export class ActivitySdkError extends Error {
  constructor(message, { code, operation, category, status } = {}) {
    super(message);
    this.name = 'ActivitySdkError';
    this.operation = operation;
    this.category = category || 'configuration';
    if (code !== undefined) this.code = code;
    if (status !== undefined) this.status = status;
  }
}

export class DLIActivityError extends Error {
  constructor(code, message, { cause, operation, category, status } = {}) {
    super(message, { cause });
    this.name = 'DLIActivityError';
    this.code = code;
    if (operation !== undefined) this.operation = operation;
    if (category !== undefined) this.category = category;
    if (status !== undefined) this.status = status;
  }
}

export function createMemoryActivityStorage(initialValue = null) {
  let value = initialValue;
  return {
    load: () => value,
    save: nextValue => { value = nextValue; },
    clear: () => { value = null; },
  };
}

export function createBrowserActivityStorage({ storage, key } = {}) {
  const memory = createMemoryActivityStorage();
  if (typeof key !== "string" || !key.trim()) return memory;
  let backing;
  try {
    backing = storage === void 0 ? globalThis.sessionStorage : storage;
    if (!backing || ["getItem", "setItem", "removeItem"].some((method) => typeof backing[method] !== "function")) backing = null;
  } catch (_) {
    backing = null;
  }
  return {
    load() {
      if (backing) {
        try {
          const raw = backing.getItem(key);
          memory.save(raw === null ? null : JSON.parse(raw));
        } catch (_) {
          backing = null;
        }
      }
      return memory.load();
    },
    save(value) {
      memory.save(value);
      if (backing) {
        try {
          if (value === null) backing.removeItem(key);
          else backing.setItem(key, JSON.stringify(value));
        } catch (_) {
          backing = null;
        }
      }
    },
    clear() {
      this.save(null);
    }
  };
}

function normalizeBaseUrl(raw) {
  let url;
  try { url = new URL(String(raw || '').trim()); }
  catch (_) { throw new ActivitySdkError('Activity API base URL is invalid'); }
  if (url.protocol !== 'https:') {
    throw new ActivitySdkError('Activity API base URL must use HTTPS');
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new ActivitySdkError('Activity API base URL cannot contain credentials, query, or fragment');
  }
  return url.href.replace(/\/+$/, '');
}

function normalizeDLIActivityBaseUrl(raw) {
  let url;
  try { url = new URL(String(raw || '').trim()); }
  catch (_) {
    throw new DLIActivityError('invalid_base_url', 'Activity API base URL is invalid');
  }
  if (url.protocol !== 'https:') {
    throw new DLIActivityError('invalid_base_url', 'Activity API base URL must use HTTPS');
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new DLIActivityError(
      'invalid_base_url',
      'Activity API base URL cannot contain credentials, query, or fragment',
    );
  }
  return url.href.replace(/\/+$/, '');
}

function translatePublicError(error) {
  if (error instanceof DLIActivityError) return error;
  if (!(error instanceof ActivitySdkError)) {
    return new DLIActivityError('activity_error', 'Activity operation failed', { cause: error });
  }
  const code = error.code || (['network', 'timeout'].includes(error.category)
    ? 'network_error'
    : error.category === 'idempotency-conflict'
      ? 'idempotency_conflict'
      : 'activity_error');
  const messages = {
    session_changed: 'Activity session changed; read state before retrying',
    invalid_configuration: 'Activity configuration is invalid',
    network_error: 'Activity request failed',
    request_rejected: 'Activity request was rejected',
    invalid_response: 'Activity response is invalid',
    idempotency_conflict: 'Activity idempotency key conflicts with an earlier request',
  };
  return new DLIActivityError(code, messages[code] || 'Activity operation failed', {
    cause: error,
    operation: error.operation,
    category: error.category,
    status: error.status,
  });
}

function storageIdentity(storage) {
  if (storage === undefined) return 'default';
  if ((typeof storage !== 'object' && typeof storage !== 'function') || storage === null) return 'invalid';
  if (!storageIdentities.has(storage)) storageIdentities.set(storage, nextStorageIdentity++);
  return storageIdentities.get(storage);
}

function isAuthenticationStateKey(key) {
  const canonicalKey = key.replace(/[^a-z0-9]/gi, '').toLowerCase();
  return canonicalKey.startsWith('authorization') || canonicalKey.endsWith('token');
}

function normalizeStateJson(value) {
  if (Array.isArray(value)) return value.map(normalizeStateJson);
  if (!value || typeof value !== 'object' || Object.getPrototypeOf(value) !== Object.prototype) {
    return value;
  }
  return Object.fromEntries(Object.entries(value)
    .filter(([key]) => !isAuthenticationStateKey(key))
    .map(([key, entry]) => [
      key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()),
      normalizeStateJson(entry),
    ]));
}

function validateMarkerState(state) {
  const validTimestamp = (value) => {
    if (value === null) return true;
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value) || !Number.isFinite(Date.parse(value))) return false;
    const [year, month, day] = value.slice(0, 10).split("-").map(Number);
    return day >= 1 && day <= new Date(Date.UTC(year, month, 0)).getUTCDate();
  };
  const ids = /* @__PURE__ */ new Set();
  if (!state || Object.hasOwn(state, "progress_percent") || !Array.isArray(state.milestones) || !validTimestamp(state.completed_at) || state.milestones?.some((marker) => {
    if (!marker || typeof marker.milestone_id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(marker.milestone_id) || ids.has(marker.milestone_id) || !validTimestamp(marker.completed_at)) return true;
    ids.add(marker.milestone_id);
    return false;
  })) {
    throw new ActivitySdkError("Activity marker state is invalid", { code: "invalid_response", category: "response", operation: "state" });
  }
  return state;
}

function validateArtifact(artifact) {
  const digest = artifact?.artifact_digest;
  if (!artifact?.artifact_id || !artifact?.artifact_version || !/^sha256:[0-9a-f]{64}$/.test(digest || '')) {
    throw new ActivitySdkError('Activity artifact identity is invalid', {
      code: 'invalid_configuration', category: 'configuration',
    });
  }
  return {
    artifact_id: artifact.artifact_id,
    artifact_version: artifact.artifact_version,
    artifact_digest: digest,
  };
}

function validateMilestones(milestones) {
  if (milestones === undefined) return undefined;
  const ids = new Set();
  if (!Array.isArray(milestones) || milestones.length < 1 || milestones.length > 1000) {
    throw new ActivitySdkError('Activity milestones are invalid', {
      code: 'invalid_configuration', category: 'configuration',
    });
  }
  return Object.freeze(Array.from(milestones, marker => {
    if (!marker || typeof marker !== 'object' || Array.isArray(marker)
        || Object.keys(marker).some(key => !['id', 'label', 'description'].includes(key))
        || typeof marker.id !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(marker.id)
        || ids.has(marker.id) || typeof marker.label !== 'string'
        || marker.label.includes("\u0000") || !marker.label.trim() || Array.from(marker.label).length < 1 || Array.from(marker.label).length > 256
        || typeof marker.description !== 'string' || marker.description.includes("\u0000") || !marker.description.trim()
        || Array.from(marker.description).length > 4096) {
      throw new ActivitySdkError('Activity milestones are invalid', {
        code: 'invalid_configuration', category: 'configuration',
      });
    }
    ids.add(marker.id);
    return Object.freeze({ id: marker.id, label: marker.label, description: marker.description });
  }));
}

const milestoneConfigLoads = new Map();
const CONFIG_PAGE = /^[A-Za-z0-9][A-Za-z0-9_-]{0,127}\.html$/;
const CONFIG_TARGET = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/;
const CONFIG_EVENT = /^[A-Za-z][A-Za-z0-9_.-]{0,63}:[A-Za-z][A-Za-z0-9_.:-]{0,127}$/;

function invalidMilestoneConfig() {
  return new ActivitySdkError('Course milestone configuration is invalid', {
    code: 'invalid_configuration', category: 'configuration',
  });
}

function configObject(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value)
      || Object.keys(value).some(key => !keys.includes(key))) throw invalidMilestoneConfig();
}

export function validateActivityMilestoneConfig(value) {
  configObject(value, ['schemaVersion', 'milestones']);
  if (value.schemaVersion !== 1) throw invalidMilestoneConfig();
  // Only this projection belongs in the Activity API request.
  validateMilestones(Array.isArray(value.milestones) ? Array.from(value.milestones, marker => ({
    id: marker?.id, label: marker?.label, description: marker?.description,
  })) : value.milestones);
  const milestones = Array.from(value.milestones, marker => {
    configObject(marker, ['id', 'label', 'description', 'href', 'evidence']);
    if (typeof marker.href !== 'string') throw invalidMilestoneConfig();
    const [page, target, extra] = marker.href.split('#');
    if (!CONFIG_PAGE.test(page) || !CONFIG_TARGET.test(target || '') || extra !== undefined
        || !Array.isArray(marker.evidence) || !marker.evidence.length || marker.evidence.length > 16) {
      throw invalidMilestoneConfig();
    }
    const evidence = Array.from(marker.evidence, (rule, index) => {
      configObject(rule, ['event', 'page', 'target', 'matches', 'minimum', 'requires']);
      if (typeof rule.event !== 'string' || !CONFIG_EVENT.test(rule.event)
          || typeof rule.page !== 'string' || !CONFIG_PAGE.test(rule.page)
          || typeof rule.target !== 'string' || !CONFIG_TARGET.test(rule.target)) throw invalidMilestoneConfig();
      const fields = (entries, minimum) => {
        if (entries === undefined) return Object.freeze({});
        if (!entries || typeof entries !== 'object' || Array.isArray(entries)) throw invalidMilestoneConfig();
        configObject(entries, Object.keys(entries));
        if (Object.keys(entries).length > 16) throw invalidMilestoneConfig();
        const scalar = item => typeof item === 'boolean' || (typeof item === 'string' && CONFIG_TARGET.test(item))
          || (typeof item === 'number' && Number.isFinite(item) && Math.abs(item) <= 1000000);
        return Object.freeze(Object.fromEntries(Object.entries(entries).map(([key, item]) => {
          if (!/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(key) || ['constructor', 'prototype', '__proto__'].includes(key)
              || (minimum ? !Number.isInteger(item) || item < 1 || item > 1000000
                : Array.isArray(item) ? !item.length || item.length > 16 || Array.from(item).some(entry => !scalar(entry)) : !scalar(item))) {
            throw invalidMilestoneConfig();
          }
          return [key, Array.isArray(item) ? Object.freeze([...item]) : item];
        })));
      };
      const requires = rule.requires === undefined ? [] : rule.requires;
      if (!Array.isArray(requires) || requires.length > 16 || new Set(requires).size !== requires.length
          || Array.from(requires).some(prior => !Number.isInteger(prior) || prior < 0 || prior >= index)) {
        throw invalidMilestoneConfig();
      }
      return Object.freeze({ event: rule.event, page: rule.page, target: rule.target,
        matches: fields(rule.matches, false), minimum: fields(rule.minimum, true), requires: Object.freeze([...requires]) });
    });
    return Object.freeze({ id: marker.id, label: marker.label, description: marker.description,
      href: marker.href, evidence: Object.freeze(evidence) });
  });
  return Object.freeze({ schemaVersion: 1, milestones: Object.freeze(milestones) });
}

export function loadActivityMilestoneConfig(configUrl, { fetchImpl = globalThis.fetch?.bind(globalThis) } = {}) {
  let url;
  try { url = new URL(configUrl, globalThis.location?.href); } catch (_) { throw invalidMilestoneConfig(); }
  const localFile = url.protocol === 'file:' && typeof globalThis.window === 'undefined';
  if ((!localFile && !['https:', 'http:'].includes(url.protocol)) || url.username || url.password || url.search || url.hash
      || (!localFile && globalThis.location?.origin && url.origin !== globalThis.location.origin)
      || typeof fetchImpl !== 'function') throw invalidMilestoneConfig();
  if (milestoneConfigLoads.has(url.href)) return milestoneConfigLoads.get(url.href);
  const attempt = Promise.resolve().then(async () => {
    const controller = new AbortController();
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => { controller.abort(); reject(invalidMilestoneConfig()); }, 10000);
    });
    const read = async () => {
      const response = await fetchImpl(url, { credentials: 'same-origin', redirect: 'error',
        referrerPolicy: 'no-referrer', cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw invalidMilestoneConfig();
      const text = await response.text();
      if (text.length > 8 * 1024 * 1024) throw invalidMilestoneConfig();
      return validateActivityMilestoneConfig(JSON.parse(text));
    };
    try { return await Promise.race([read(), deadline]); }
    finally { clearTimeout(timer); }
  }).catch(() => { milestoneConfigLoads.delete(url.href); throw invalidMilestoneConfig(); });
  milestoneConfigLoads.set(url.href, attempt);
  return attempt;
}

export function bindActivityMilestones({ config, eventTarget, documentTarget, page,
  sessionId = null, onMilestone } = {}) {
  config = validateActivityMilestoneConfig(config);
  if (!eventTarget?.addEventListener || !documentTarget?.getElementById || typeof onMilestone !== 'function') {
    throw invalidMilestoneConfig();
  }
  const partial = new Map();
  let boundSession = sessionId;
  const bindings = new Map();
  for (const marker of config.milestones) marker.evidence.forEach((rule, index) => {
    if (rule.page !== page || !documentTarget.getElementById(rule.target)) return;
    if (!bindings.has(rule.event)) bindings.set(rule.event, []);
    bindings.get(rule.event).push({ marker, rule, index });
  });
  const listeners = [];
  for (const [event, rules] of bindings) {
    const listener = signal => {
      const detail = signal.detail || {};
      for (const { marker, rule, index } of rules) {
        if (!Object.entries(rule.matches).every(([key, expected]) => Array.isArray(expected)
          ? expected.includes(detail[key]) : detail[key] === expected)
            || !Object.entries(rule.minimum).every(([key, minimum]) => typeof detail[key] === 'number'
              && Number.isFinite(detail[key]) && detail[key] >= minimum)) continue;
        const reached = partial.get(marker.id) || new Set();
        if (!rule.requires.every(prior => reached.has(prior))) continue;
        reached.add(index);
        partial.set(marker.id, reached);
        if (marker.evidence.every((_, position) => reached.has(position))) {
          void Promise.resolve(onMilestone(marker.id)).catch(() => {});
        }
      }
    };
    eventTarget.addEventListener(event, listener);
    listeners.push([event, listener]);
  }
  return {
    bindSession(state) {
      const next = state.sessionId;
      if (next !== boundSession) {
        // Fresh evidence collected before enablement binds once, never across replacement.
        if (boundSession !== null) partial.clear();
        boundSession = next;
      }
    },
    dispose() { for (const [event, listener] of listeners) eventTarget.removeEventListener(event, listener); partial.clear(); },
  };
}

function validateSession(value) {
  const expiresAt = Date.parse(value?.expires_at || '');
  if (!SESSION_ID_PATTERN.test(value?.session_id || '') ||
      typeof value?.session_token !== 'string' || value.session_token.length < 16 ||
      !Number.isFinite(expiresAt)) {
    throw new ActivitySdkError('Activity session response is invalid', {
      code: 'invalid_response', operation: 'session', category: 'validation',
    });
  }
  return {
    session_id: value.session_id,
    session_token: value.session_token,
    expires_at: value.expires_at,
  };
}

function categoryForStatus(status, idempotencyKey) {
  if (status === 401 || status === 403) return 'authentication';
  if (status === 409 && idempotencyKey) return 'idempotency-conflict';
  if (status === 422) return 'validation';
  return status >= 500 ? 'server' : 'request';
}

export function createActivityClient({
  baseUrl,
  artifact,
  milestones,
  storage = createMemoryActivityStorage(),
  fetchImpl = globalThis.fetch?.bind(globalThis),
  now = () => new Date(),
  onDiagnostic = () => {},
} = {}) {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  const normalizedArtifact = validateArtifact(artifact);
  const normalizedMilestones = validateMilestones(milestones);
  const scope = JSON.stringify([normalizedBaseUrl, normalizedArtifact, normalizedMilestones]);
  if (typeof fetchImpl !== 'function') throw new ActivitySdkError('Fetch API is unavailable', {
    code: 'invalid_configuration', category: 'configuration',
  });
  if (!storage || typeof storage.load !== 'function' || typeof storage.save !== 'function') {
    throw new ActivitySdkError('Activity storage adapter is invalid', {
      code: 'invalid_configuration', category: 'configuration',
    });
  }

  let initializing = null;
  let refreshing = null;

  function diagnostic(operation, category, status) {
    const event = { operation, category };
    if (status !== undefined) event.status = status;
    try { onDiagnostic(event); } catch (_) {}
  }

  async function requestJson(operation, path, { body, session, idempotencyKey, method = 'POST' } = {}) {
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (session) headers.Authorization = `Bearer ${session.session_token}`;
    if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;
    const controller = new AbortController();
    let timer;
    let response;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(new ActivitySdkError('Activity request failed', {
          code: 'network_error', operation, category: 'timeout',
        }));
      }, REQUEST_TIMEOUT_MS);
    });
    const request = async () => {
      response = await fetchImpl(`${normalizedBaseUrl}${path}`, {
        method, headers, body: body === undefined ? undefined : JSON.stringify(body),
        cache: 'no-store', credentials: 'omit', keepalive: operation === 'referral',
        mode: 'cors', redirect: 'error', referrerPolicy: 'no-referrer', signal: controller.signal,
      });
      if (!response.ok) {
        const category = categoryForStatus(response.status, idempotencyKey);
        throw new ActivitySdkError('Activity request was rejected', {
          code: category === 'idempotency-conflict' ? 'idempotency_conflict' : 'request_rejected',
          operation, category, status: response.status,
        });
      }
      try { return { result: await response.json(), replayed: response.status === 200 }; }
      catch (_) {
        throw new ActivitySdkError('Activity response is invalid', {
          code: 'invalid_response', operation, category: 'validation', status: response.status,
        });
      }
    };
    try { return await Promise.race([request(), deadline]); }
    catch (error) {
      const failure = error instanceof ActivitySdkError ? error : new ActivitySdkError('Activity request failed', {
        code: 'network_error', operation, category: controller.signal.aborted ? 'timeout' : 'network',
      });
      diagnostic(operation, failure.category, failure.status);
      throw failure;
    } finally { clearTimeout(timer); }
  }

  async function createSession() {
    const { result } = await requestJson('session', '/v1/activity-sessions', {
      body: { ...normalizedArtifact, ...(normalizedMilestones === undefined ? {} : { milestones: normalizedMilestones }) },
    });
    const session = validateSession(result);
    storage.save({ ...session, scope });
    return session;
  }

  async function ensureSession() {
    const stored = storage.load();
    if (stored?.scope === scope) {
      try {
        const session = validateSession(stored);
        if (Date.parse(session.expires_at) > now().getTime()) return session;
      } catch (_) {}
      if (typeof storage.clear === 'function') storage.clear();
    }
    if (!initializing) {
      initializing = createSession().finally(() => { initializing = null; });
    }
    return initializing;
  }

  function sameSession(left, right) {
    return left?.session_id === right?.session_id && left?.session_token === right?.session_token;
  }

  function clearSessionIfCurrent(rejectedSession) {
    const saved = storage.load();
    if (saved?.scope !== scope || !sameSession(saved, rejectedSession)) return;
    if (typeof storage.clear === 'function') storage.clear();
    else storage.save(null);
  }

  async function refreshSession(rejectedSession) {
    const current = storage.load();
    if (current?.scope === scope && !sameSession(current, rejectedSession)) {
      try {
        const validated = validateSession(current);
        if (Date.parse(validated.expires_at) > now().getTime()) return validated;
      } catch (_) {}
    }
    if (!refreshing) {
      refreshing = Promise.resolve().then(() => {
        const latest = storage.load();
        if (latest?.scope === scope && !sameSession(latest, rejectedSession)) {
          try {
            const validated = validateSession(latest);
            if (Date.parse(validated.expires_at) > now().getTime()) return validated;
          } catch (_) {}
        }
        clearSessionIfCurrent(rejectedSession);
        return ensureSession();
      }).finally(() => { refreshing = null; });
    }
    return refreshing;
  }

  async function withAuthenticationRefresh(request) {
    const session = await ensureSession();
    try {
      return await request(session);
    } catch (error) {
      if (!(error instanceof ActivitySdkError) || error.category !== 'authentication') throw error;
      const replacement = await refreshSession(session);
      try {
        return await request(replacement);
      } catch (retryError) {
        if (retryError instanceof ActivitySdkError && retryError.category === 'authentication') {
          clearSessionIfCurrent(replacement);
        }
        throw retryError;
      }
    }
  }

  function requireIdempotencyKey(value) {
    const key = String(value || '').trim();
    if (!key || key.length > 255) {
      throw new ActivitySdkError('Activity idempotency key is invalid', {
        code: 'invalid_configuration', category: 'configuration',
      });
    }
    return key;
  }

  async function authenticatedWrite(operation, suffix, body, idempotencyKey, expectedSessionId) {
    const key = requireIdempotencyKey(idempotencyKey);
    const write = async session => {
      if (expectedSessionId !== undefined && session.session_id !== expectedSessionId) {
        throw new ActivitySdkError('Activity session changed; read state before retrying completion', {
          code: 'session_changed', category: 'session', operation,
        });
      }
      return requestJson(operation, `/v1/activity-sessions/${encodeURIComponent(session.session_id)}/${suffix}`,
        { body, session, idempotencyKey: key });
    };
    return withAuthenticationRefresh(write);
  }

  return {
    get sessionId() { const saved = storage.load(); return saved?.scope === scope ? saved.session_id : undefined; },
    ensureSession,
    recordReferral({ referenceId, destinationUrl, idempotencyKey }) {
      return authenticatedWrite('referral', 'referrals', {
        reference_id: referenceId,
        destination_url: destinationUrl,
      }, idempotencyKey);
    },
    recordMilestoneCompleted({ milestoneId, idempotencyKey, expectedSessionId }) {
      return authenticatedWrite('milestone', 'updates', {
        type: 'milestone_completed', payload: { milestone_id: milestoneId },
      }, idempotencyKey, expectedSessionId);
    },
    recordCompleted({ idempotencyKey, expectedSessionId }) {
      return authenticatedWrite('completion', 'updates', {
        type: 'completed', payload: {},
      }, idempotencyKey, expectedSessionId);
    },
    async getState() {
      const read = async session => ({ ...await requestJson(
        'state', `/v1/activity-sessions/${encodeURIComponent(session.session_id)}/state`,
        { session, method: 'GET' },
      ), sessionId: session.session_id });
      const response = await withAuthenticationRefresh(read);
      const { result } = response;
      return validateMarkerState({ ...result, session_id: response.sessionId });
    },
  };
}

export class DLIActivity {
  #client;
  #writeQueue = Promise.resolve();

  /**
   * Creates the lesson-facing activity facade. Storage, fetchImpl, now, and
   * onDiagnostic are integration and test adapters, not lesson-facing options.
   */
  constructor({ baseUrl, artifact, milestones, storage, fetchImpl, now, onDiagnostic, ...unsupported } = {}) {
    try {
      if (Object.keys(unsupported).length > 0) {
        throw new ActivitySdkError('Activity configuration contains unsupported options', {
          code: 'invalid_configuration', category: 'configuration',
        });
      }
      this.#client = createActivityClient({
        baseUrl: normalizeDLIActivityBaseUrl(baseUrl), artifact, milestones, storage, fetchImpl, now, onDiagnostic,
      });
    } catch (error) {
      throw translatePublicError(error);
    }
  }

  static async initialize(options) {
    if (options?.milestoneConfigUrl !== undefined) {
      try {
        if (options.milestones !== undefined) throw invalidMilestoneConfig();
        const { milestoneConfigUrl, ...adapters } = options;
        const config = await loadActivityMilestoneConfig(milestoneConfigUrl, { fetchImpl: options.fetchImpl });
        options = { ...adapters, milestones: config.milestones.map(({ id, label, description }) => ({ id, label, description })) };
      } catch (error) { throw translatePublicError(error); }
    }
    let instance;
    let key;
    try {
      instance = new DLIActivity(options);
      const normalizedArtifact = validateArtifact(options?.artifact);
      key = JSON.stringify([
        normalizeDLIActivityBaseUrl(options?.baseUrl), normalizedArtifact, validateMilestones(options?.milestones),
        storageIdentity(options?.storage),
      ]);
    } catch (error) {
      throw translatePublicError(error);
    }
    if (initializationAttempts.has(key)) return initializationAttempts.get(key);
    const attempt = instance.#client.ensureSession()
      .then(() => instance)
      .catch(error => { throw translatePublicError(error); })
      .finally(() => initializationAttempts.delete(key));
    initializationAttempts.set(key, attempt);
    return attempt;
  }

  async completeMilestone(milestoneId, { idempotencyKey } = {}) {
    if (typeof milestoneId !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(milestoneId)) {
      throw new DLIActivityError("invalid_milestone", "Activity milestone ID is invalid");
    }
    return this.#serialize(async (expectedSessionId) => {
      const state = await this.#getState();
      this.#requireSession(expectedSessionId);
      const marker = state.milestones?.find((item) => item.milestoneId === milestoneId);
      if (!marker) throw new DLIActivityError("invalid_milestone", "Activity milestone ID is not registered");
      this.#requireSession(state.sessionId);
      if (marker.completedAt !== null) return { written: false, state };
      await this.#client.recordMilestoneCompleted({
        milestoneId,
        idempotencyKey: idempotencyKey ?? `dli-activity:milestone:${milestoneId}`,
        expectedSessionId: state.sessionId
      });
      return { written: true, state: await this.#confirm(
        state.sessionId,
        (next) => next.milestones?.some((item) => item.milestoneId === milestoneId && item.completedAt !== null)
      ) };
    });
  }
  async #serialize(operation) {
    const sessionId = this.#client.sessionId;
    const authorization = sessionId === void 0 ? this.#client.ensureSession().then((session) => ({ sessionId: session.session_id }), (error) => ({ error })) : Promise.resolve({ sessionId });
    const run = async () => {
      const authorized = await authorization;
      if ("error" in authorized) throw authorized.error;
      this.#requireSession(authorized.sessionId);
      return operation(authorized.sessionId);
    };
    const result = this.#writeQueue.then(run, run);
    this.#writeQueue = result.then(() => void 0, () => void 0);
    try {
      return await result;
    } catch (error) {
      throw translatePublicError(error);
    }
  }
  #requireSession(sessionId) {
    if (this.#client.sessionId !== sessionId) {
      throw new DLIActivityError("session_changed", "Activity session changed; read state before retrying");
    }
  }
  async #confirm(sessionId, confirmed) {
    let active = true;
    let timer;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new DLIActivityError(
        "confirmation_pending",
        "Activity update is pending server confirmation; check state before retrying"
      )), 3e4);
    });
    const poll = async () => {
      while (active) {
        this.#requireSession(sessionId);
        const state = await this.#getState();
        this.#requireSession(sessionId);
        if (state.sessionId !== sessionId) {
          throw new DLIActivityError("session_changed", "Activity session changed; read state before retrying");
        }
        if (confirmed(state)) return state;
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
    };
    try {
      return await Promise.race([poll(), deadline]);
    } finally {
      active = false;
      clearTimeout(timer);
    }
  }
  async referral({ referenceId, destinationUrl, idempotencyKey } = {}) {
    const normalizedReferenceId = String(referenceId || "").trim();
    let destination;
    try {
      destination = new URL(String(destinationUrl || "").trim());
    } catch (_) {
      throw new DLIActivityError("invalid_referral", "Activity referral destination URL is invalid");
    }
    if (!normalizedReferenceId || destination.protocol !== "https:") {
      throw new DLIActivityError("invalid_referral", "Activity referral is invalid");
    }
    try {
      return await this.#client.recordReferral({
        referenceId: normalizedReferenceId,
        destinationUrl: destination.href,
        idempotencyKey: idempotencyKey || `dli-activity:referral:${normalizedReferenceId}`
      });
    } catch (error) {
      throw translatePublicError(error);
    }
  }
  async #getState() {
    const raw = await this.#client.getState();
    return {
      ...normalizeStateJson(raw),
      sessionId: raw.session_id,
      completedAt: raw.completed_at,
      milestones: raw.milestones?.map((marker) => ({ milestoneId: marker.milestone_id, completedAt: marker.completed_at })) ?? null
    };
  }
  async getState() {
    try {
      return await this.#getState();
    } catch (error) {
      throw translatePublicError(error);
    }
  }
  async complete({ idempotencyKey } = {}) {
    return this.#serialize(async (expectedSessionId) => {
      const state = await this.#getState();
      this.#requireSession(expectedSessionId);
      this.#requireSession(state.sessionId);
      if (state.completedAt !== null || !state.milestones.length || state.milestones.some((marker) => marker.completedAt === null)) {
        return { written: false, state };
      }
      await this.#client.recordCompleted({
        idempotencyKey: idempotencyKey ?? "dli-activity:completed",
        expectedSessionId: state.sessionId
      });
      return { written: true, state: await this.#confirm(state.sessionId, (next) => next.completedAt !== null) };
    });
  }
};
