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

function categoryForStatus(status) {
  if (status === 401 || status === 403) return 'authentication';
  if (status === 409) return 'idempotency-conflict';
  if (status === 422) return 'validation';
  return status >= 500 ? 'server' : 'request';
}

export function createActivityClient({
  baseUrl,
  artifact,
  storage = createMemoryActivityStorage(),
  fetchImpl = globalThis.fetch?.bind(globalThis),
  now = () => new Date(),
  onDiagnostic = () => {},
} = {}) {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  const normalizedArtifact = validateArtifact(artifact);
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
    const controller = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = controller ? setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS) : null;
    let response;
    try {
      response = await fetchImpl(`${normalizedBaseUrl}${path}`, {
        method, headers,
        body: body === undefined ? undefined : JSON.stringify(body),
        cache: 'no-store',
        credentials: 'omit',
        keepalive: operation === 'referral',
        mode: 'cors',
        redirect: 'error',
        referrerPolicy: 'no-referrer',
        signal: controller?.signal,
      });
    } catch (error) {
      const category = error?.name === 'AbortError' ? 'timeout' : 'network';
      diagnostic(operation, category);
      throw new ActivitySdkError('Activity request failed', {
        code: 'network_error', operation, category,
      });
    } finally {
      if (timer) clearTimeout(timer);
    }
    if (!response.ok) {
      const category = categoryForStatus(response.status);
      diagnostic(operation, category, response.status);
      throw new ActivitySdkError('Activity request was rejected', {
        code: category === 'idempotency-conflict' ? 'idempotency_conflict' : 'request_rejected',
        operation, category, status: response.status,
      });
    }
    let result;
    try { result = await response.json(); }
    catch (_) {
      diagnostic(operation, 'validation', response.status);
      throw new ActivitySdkError('Activity response is invalid', {
        code: 'invalid_response', operation, category: 'validation', status: response.status,
      });
    }
    return { result, replayed: response.status === 200 };
  }

  async function createSession() {
    const { result } = await requestJson('session', '/v1/activity-sessions', {
      body: normalizedArtifact,
    });
    const session = validateSession(result);
    storage.save(session);
    return session;
  }

  async function ensureSession() {
    const stored = storage.load();
    if (stored) {
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
    if (!sameSession(storage.load(), rejectedSession)) return;
    if (typeof storage.clear === 'function') storage.clear();
    else storage.save(null);
  }

  async function refreshSession(rejectedSession) {
    const current = storage.load();
    if (current && !sameSession(current, rejectedSession)) {
      try {
        const validated = validateSession(current);
        if (Date.parse(validated.expires_at) > now().getTime()) return validated;
      } catch (_) {}
    }
    if (!refreshing) {
      refreshing = Promise.resolve().then(() => {
        const latest = storage.load();
        if (latest && !sameSession(latest, rejectedSession)) {
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

  async function authenticatedWrite(operation, suffix, body, idempotencyKey) {
    const key = requireIdempotencyKey(idempotencyKey);
    const write = async session => requestJson(
      operation,
      `/v1/activity-sessions/${encodeURIComponent(session.session_id)}/${suffix}`,
      { body, session, idempotencyKey: key },
    );
    return withAuthenticationRefresh(write);
  }

  return {
    ensureSession,
    recordReferral({ referenceId, destinationUrl, idempotencyKey }) {
      return authenticatedWrite('referral', 'referrals', {
        reference_id: referenceId,
        destination_url: destinationUrl,
      }, idempotencyKey);
    },
    recordProgress({ progressPercent, idempotencyKey }) {
      return authenticatedWrite('progress', 'updates', {
        type: 'progress', payload: { progress_percent: progressPercent },
      }, idempotencyKey);
    },
    recordCompleted({ idempotencyKey }) {
      return authenticatedWrite('completion', 'updates', {
        type: 'completed', payload: {},
      }, idempotencyKey);
    },
    async getState() {
      const read = async session => requestJson(
        'state', `/v1/activity-sessions/${encodeURIComponent(session.session_id)}/state`,
        { session, method: 'GET' },
      );
      const response = await withAuthenticationRefresh(read);
      const { result } = response;
      return result;
    },
  };
}

export class DLIActivity {
  #client;
  #progressPercent = 0;
  #progressHydrated = false;
  #progressQueue = Promise.resolve();

  /**
   * Creates the lesson-facing activity facade. Storage, fetchImpl, now, and
   * onDiagnostic are integration and test adapters, not lesson-facing options.
   */
  constructor({ baseUrl, artifact, storage, fetchImpl, now, onDiagnostic, ...unsupported } = {}) {
    try {
      if (Object.keys(unsupported).length > 0) {
        throw new ActivitySdkError('Activity configuration contains unsupported options', {
          code: 'invalid_configuration', category: 'configuration',
        });
      }
      this.#client = createActivityClient({
        baseUrl: normalizeDLIActivityBaseUrl(baseUrl), artifact, storage, fetchImpl, now, onDiagnostic,
      });
    } catch (error) {
      throw translatePublicError(error);
    }
  }

  static async initialize(options) {
    let instance;
    let key;
    try {
      instance = new DLIActivity(options);
      const normalizedArtifact = validateArtifact(options?.artifact);
      key = JSON.stringify([
        normalizeDLIActivityBaseUrl(options?.baseUrl), normalizedArtifact, storageIdentity(options?.storage),
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

  async progress(progressPercent, { idempotencyKey } = {}) {
    if (!Number.isInteger(progressPercent) || progressPercent < 0 || progressPercent > 100) {
      throw new DLIActivityError(
        'invalid_progress',
        'Activity progress must be an integer from 0 through 100',
      );
    }
    const operation = async () => {
      if (!this.#progressHydrated) await this.#getState();
      if (progressPercent < this.#progressPercent) {
        return { written: false, progressPercent: this.#progressPercent };
      }
      const response = await this.#client.recordProgress({
        progressPercent,
        idempotencyKey: idempotencyKey || `dli-activity:progress:${progressPercent}`,
      });
      const recordedProgress = response.result?.state?.progress_percent;
      this.#progressPercent = Math.max(
        this.#progressPercent,
        Number.isInteger(recordedProgress) ? recordedProgress : progressPercent,
      );
      return response;
    };
    const result = this.#progressQueue.then(operation, operation);
    this.#progressQueue = result.then(() => undefined, () => undefined);
    try { return await result; }
    catch (error) { throw translatePublicError(error); }
  }

  async referral({ referenceId, destinationUrl, idempotencyKey } = {}) {
    const normalizedReferenceId = String(referenceId || '').trim();
    let destination;
    try { destination = new URL(String(destinationUrl || '').trim()); }
    catch (_) {
      throw new DLIActivityError('invalid_referral', 'Activity referral destination URL is invalid');
    }
    if (!normalizedReferenceId || destination.protocol !== 'https:') {
      throw new DLIActivityError('invalid_referral', 'Activity referral is invalid');
    }
    try {
      return await this.#client.recordReferral({
        referenceId: normalizedReferenceId,
        destinationUrl: destination.href,
        idempotencyKey: idempotencyKey || `dli-activity:referral:${normalizedReferenceId}`,
      });
    } catch (error) { throw translatePublicError(error); }
  }

  async #getState() {
    const state = normalizeStateJson(await this.#client.getState());
    this.#progressHydrated = true;
    if (Number.isInteger(state.progressPercent)) {
      this.#progressPercent = Math.max(this.#progressPercent, state.progressPercent);
    }
    return state;
  }

  async getState() {
    try { return await this.#getState(); }
    catch (error) { throw translatePublicError(error); }
  }

  async complete({ idempotencyKey } = {}) {
    const state = await this.getState();
    if (!Number.isInteger(state.progressPercent) || state.progressPercent !== 100) {
      return { written: false, state };
    }
    try {
      return await this.#client.recordCompleted({
        idempotencyKey: idempotencyKey || 'dli-activity:completed',
      });
    } catch (error) { throw translatePublicError(error); }
  }
}
