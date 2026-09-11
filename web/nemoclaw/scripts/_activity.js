// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DLIActivity } from '../../shared/activity-sdk.js';

export const BUILD_SIGNUP_URL = 'https://build.nvidia.com/?ncid=ref-dli-146986';
const ACTIVITY_BASE_URL = 'https://activity-api.learn.nvidia.com';
const ACTIVITY_POLICY_URL = new URL('../activity-policy.json', import.meta.url);
const PAGES_MANIFEST = 'pages-sha256.txt';
const MATERIALIZED_MANIFEST = 'materialized-sha256.txt';

export const ACTIVITY_ARTIFACT_ID = 'artifact_nemoclaw_web';

export const ACTIVITY_MILESTONES = Object.freeze({
  '01a:model-call-verified': Object.freeze({ progressPercent: 10 }),
  '01b:react-loop-complete': Object.freeze({ progressPercent: 15 }),
  '01c:tool-roundtrip-complete': Object.freeze({ progressPercent: 25 }),
  '02a:routed-workflow-complete': Object.freeze({ progressPercent: 35 }),
  '02b:grounded-answer-complete': Object.freeze({ progressPercent: 45 }),
  '02c:deep-research-complete': Object.freeze({ progressPercent: 50 }),
  '03a:nemoclaw-connected': Object.freeze({ progressPercent: 60 }),
  '03b:workspace-inspected': Object.freeze({ progressPercent: 70 }),
  '03c:scheduled-run-complete': Object.freeze({ progressPercent: 80 }),
  '04a:policy-boundary-verified': Object.freeze({ progressPercent: 90 }),
  '04b:live-agent-operated': Object.freeze({ progressPercent: 100 }),
});

export const ACTIVITY_REFERRALS = Object.freeze({
  [BUILD_SIGNUP_URL]: 'build:nvidia-api-key',
  'https://brev.nvidia.com/launchable/deploy/now?launchableID=env-3Azt0aYgVNFEuz7opyx3gscmowS&ncid=ref-dli-759990': 'brev:nemoclaw-launchable',
  'https://build.nvidia.com/spark/nemoclaw-applications?ncid=ref-dli-146986': 'build:nemoclaw-applications',
  'https://build.nvidia.com/nvidia/nemoclaw-for-openclaw/nemoclawcard?ncid=ref-dli-146986': 'build:nemoclaw-card',
  'https://build.nvidia.com/blueprints?ncid=ref-dli-146986': 'build:ai-blueprints',
  'https://build.nvidia.com/nvidia/aiq?ncid=ref-dli-146986': 'build:aiq-blueprint',
  'https://developer.nvidia.com/topics/ai/agentic-ai-learning-path/how-to-build-an-ai-agent': 'developer:agentic-learning-path:build-agent',
  'https://developer.nvidia.com/topics/ai/agentic-ai-learning-path/how-to-build-agentic-ai-rag': 'developer:agentic-learning-path:agentic-rag',
  'https://developer.nvidia.com/topics/ai/agentic-ai-learning-path/how-to-evaluate-ai-agents': 'developer:agentic-learning-path:evaluate-agents',
  'https://developer.nvidia.com/topics/ai/agentic-ai-learning-path/how-to-customize-ai-agents': 'developer:agentic-learning-path:customize-agents',
  'https://developer.nvidia.com/topics/ai/agentic-ai-learning-path/how-to-build-deep-ai-agents': 'developer:agentic-learning-path:deep-agents',
  'https://developer.nvidia.com/topics/ai/agentic-ai-learning-path/how-to-build-safer-autonomous-agent-using-openclaw': 'developer:agentic-learning-path:safer-openclaw',
  'https://developer.nvidia.com/topics/ai/agentic-ai-learning-path': 'nvidia:agentic-ai-learning-path',
  'https://www.nvidia.com/en-us/ai/nemoclaw/': 'nvidia:nemoclaw',
  'https://docs.nvidia.com/nemoclaw/latest/get-started/prerequisites': 'nvidia:nemoclaw-prerequisites',
  'https://docs.nvidia.com/nim/': 'nvidia:nim',
  'https://developer.nvidia.com/nemo-retriever': 'nvidia:nemo-retriever',
  'https://github.com/NVIDIA/NemoClaw': 'nvidia:github:nemoclaw',
  'https://github.com/NVIDIA/OpenShell': 'nvidia:github:openshell',
  'https://github.com/NVIDIA/NeMo-Guardrails': 'nvidia:github:nemo-guardrails',
  'https://github.com/NVIDIA/NeMo-Curator': 'nvidia:github:nemo-curator',
});

function createSessionStorageAdapter(target, artifactVersion, artifactDigest) {
  const storageKey = `dli_activity:nemoclaw:${artifactVersion}:${artifactDigest}`;
  let memoryValue = null;
  let disposed = false;
  return {
    load() {
      if (disposed) return null;
      try {
        const raw = target?.getItem(storageKey);
        return raw ? JSON.parse(raw) : memoryValue;
      } catch (_) { return memoryValue; }
    },
    save(value) {
      if (disposed) return;
      memoryValue = value;
      try { target?.setItem(storageKey, JSON.stringify(value)); } catch (_) {}
    },
    clear() {
      if (disposed) return;
      memoryValue = null;
      try { target?.removeItem(storageKey); } catch (_) {}
    },
    dispose() {
      if (disposed) return;
      this.clear();
      disposed = true;
    },
  };
}

export function resolveActivityBaseUrl() {
  return ACTIVITY_BASE_URL;
}

function manifestCandidates(locationHref) {
  const current = new URL(locationHref);
  const candidates = [];
  let directory = new URL('.', current);
  while (directory.origin === current.origin) {
    for (const name of [MATERIALIZED_MANIFEST, PAGES_MANIFEST]) {
      const candidate = new URL(name, directory);
      if (!candidates.some(item => item.href === candidate.href)) candidates.push(candidate);
    }
    if (directory.pathname === '/') break;
    directory = new URL('../', directory);
  }
  return candidates;
}

async function sha256(value, cryptoImpl) {
  if (!cryptoImpl?.subtle?.digest) throw new Error('Secure artifact hashing is unavailable');
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  const digest = new Uint8Array(await cryptoImpl.subtle.digest('SHA-256', bytes));
  return [...digest].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

export async function resolveActivityArtifact({
  fetchImpl = globalThis.fetch?.bind(globalThis),
  locationHref = globalThis.location?.href,
  cryptoImpl = globalThis.crypto,
  secureContext = globalThis.isSecureContext,
} = {}) {
  if (secureContext === false) {
    throw Object.assign(new Error('Remote progress requires a secure browser context'), { code: 'secure-context' });
  }
  if (!cryptoImpl?.subtle?.digest) throw new Error('Secure artifact hashing is unavailable');
  if (typeof fetchImpl !== 'function' || !locationHref) {
    throw new Error('Exact activity artifact identity is unavailable');
  }
  for (const url of manifestCandidates(locationHref)) {
    try {
      const response = await fetchImpl(url, {
        credentials: 'same-origin', cache: 'no-store', redirect: 'error', referrerPolicy: 'no-referrer',
      });
      if (!response.ok || response.url !== url.href) continue;
      const bytes = new Uint8Array(await response.arrayBuffer());
      const header = new TextDecoder().decode(bytes.slice(0, 256)).split('\n', 1)[0];
      const match = url.pathname.endsWith(`/${MATERIALIZED_MANIFEST}`)
        ? header.match(/^# nemoclaw-materialized-sha256\/1 commit=([0-9a-f]{40}) adapter=([0-9a-f]{64})$/)
        : header.match(/^# nemoclaw-pages-sha256\/1 commit=([0-9a-f]{40})$/);
      if (!match) continue;
      return Object.freeze({
        artifact_id: ACTIVITY_ARTIFACT_ID,
        artifact_version: `git-${match[1]}${match[2] ? `-adapter-${match[2]}` : ''}`,
        artifact_digest: `sha256:${await sha256(bytes, cryptoImpl)}`,
      });
    } catch (_) {}
  }
  throw new Error('Open a validated course build before enabling remote progress');
}

function isNonEmptyString(value) {
  return typeof value === 'string' && value.trim().length > 0;
}

function isHttpsUrl(value) {
  try { return new URL(value).protocol === 'https:'; }
  catch (_) { return false; }
}

function isNvidiaHttpsUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && (url.hostname === 'nvidia.com' || url.hostname.endsWith('.nvidia.com'));
  } catch (_) { return false; }
}

export function validateActivityPolicy(policy) {
  const strings = value => Array.isArray(value) && value.length > 0 && value.every(isNonEmptyString);
  if (policy?.schema !== 'dli-activity-policy/1'
      || !isNonEmptyString(policy.notice_version)
      || !['pending-privacy-legal-review', 'privacy-legal-reviewed'].includes(policy.publication_status)
      || typeof policy.collection_enabled !== 'boolean'
      || policy.api_base_url !== ACTIVITY_BASE_URL
      || !isNonEmptyString(policy.recipient)
      || policy.collection_defaults?.progress_sync !== 'off'
      || policy.collection_defaults?.referral_tracking !== 'off'
      || !strings(policy.data_categories)
      || !strings(policy.excluded_course_payloads)
      || !strings(policy.purposes)
      || !isNonEmptyString(policy.browser_retention)
      || !['unconfirmed', 'confirmed'].includes(policy.controller?.status)
      || !['unconfirmed', 'confirmed'].includes(policy.service_retention?.status)
      || !['unconfirmed', 'confirmed'].includes(policy.legal_basis?.status)
      || !['unconfirmed', 'confirmed', 'not-applicable'].includes(policy.sale_sharing?.status)
      || !isNonEmptyString(policy.sale_sharing?.course_code_behavior)
      || !['unpublished', 'published'].includes(policy.service_level?.status)
      || !isNvidiaHttpsUrl(policy.privacy_policy_url)
      || !isNvidiaHttpsUrl(policy.privacy_center_url)
      || !strings(policy.review_required)
      || !['privacy', 'legal', 'activity-service-owner'].every(role => policy.review_required.includes(role))) {
    throw new Error('Activity data notice is invalid');
  }
  if (policy.collection_enabled && (
    policy.publication_status !== 'privacy-legal-reviewed'
    || policy.controller.status !== 'confirmed'
    || !isNonEmptyString(policy.controller.name)
    || !isNonEmptyString(policy.controller.owner)
    || policy.service_retention.status !== 'confirmed'
    || !isNonEmptyString(policy.service_retention.period_or_criteria)
    || !isNonEmptyString(policy.service_retention.owner)
    || policy.legal_basis.status !== 'confirmed'
    || !isNonEmptyString(policy.legal_basis.basis)
    || !isNonEmptyString(policy.legal_basis.owner)
    || !['confirmed', 'not-applicable'].includes(policy.sale_sharing.status)
    || !isNonEmptyString(policy.sale_sharing.disposition)
    || !isNonEmptyString(policy.sale_sharing.owner)
  )) throw new Error('Enabled activity collection requires a reviewed data policy');
  if (policy.service_level.status === 'published' && (
    !isNonEmptyString(policy.service_level.target)
    || !isHttpsUrl(policy.service_level.source_url)
  )) throw new Error('Published activity service levels require a source');
  return Object.freeze(policy);
}

export function isActivityPolicyApproved(policy) {
  try {
    validateActivityPolicy(policy);
    return policy.collection_enabled === true;
  } catch (_) { return false; }
}

export async function loadActivityPolicy(fetchImpl = globalThis.fetch?.bind(globalThis)) {
  if (typeof fetchImpl !== 'function') throw new Error('Activity data notice is unavailable');
  const response = await fetchImpl(ACTIVITY_POLICY_URL, {
    credentials: 'same-origin', cache: 'no-store', redirect: 'error',
  });
  if (!response.ok || response.url !== ACTIVITY_POLICY_URL.href) {
    throw new Error('Activity data notice is unavailable');
  }
  return validateActivityPolicy(await response.json());
}

export function createNemoClawActivity({
  fetchImpl = globalThis.fetch?.bind(globalThis),
  storageTarget = globalThis.sessionStorage,
  locationHref = globalThis.location?.href,
  cryptoImpl = globalThis.crypto,
  now,
  performanceImpl = globalThis.performance,
  globalPrivacyControl = globalThis.navigator?.globalPrivacyControl === true,
  onDiagnostic = () => {},
  policyLoader = () => loadActivityPolicy(fetchImpl),
  artifactResolver = () => resolveActivityArtifact({ fetchImpl, locationHref, cryptoImpl }),
  initialize = options => DLIActivity.initialize(options),
} = {}) {
  let initializedActivity;
  let enabled = false;
  let referralTracking = false;
  let policy;
  let artifact;
  let enableAttempt;
  let connectionGeneration = 0;
  let connectionAbort;
  const listeners = new Set();
  let storage;
  let state = Object.freeze({ phase: 'off', enabled, referralTracking, progressPercent: 0 });
  const preferenceKey = 'dli_activity:progress-preference';
  const preference = () => {
    try { return JSON.parse(storageTarget?.getItem(preferenceKey) || 'null'); }
    catch (_) { return null; }
  };
  const savePreference = () => {
    try {
      if (enabled) storageTarget?.setItem(preferenceKey, JSON.stringify({
        digest: artifact.artifact_digest, notice: policy.notice_version, referralTracking,
      }));
      else storageTarget?.removeItem(preferenceKey);
    } catch (_) {}
  };

  function publish(next) {
    state = Object.freeze({ ...state, ...next, enabled, referralTracking });
    for (const listener of listeners) {
      try { listener(state); } catch (_) {}
    }
    return state;
  }

  function initializeActivity() {
    if (initializedActivity) return initializedActivity;
    if (!isActivityPolicyApproved(policy) || !artifact) {
      return Promise.reject(new Error('Activity collection is not ready'));
    }
    storage ||= createSessionStorageAdapter(storageTarget, artifact.artifact_version, artifact.artifact_digest);
    const attemptStorage = storage;
    const generation = connectionGeneration;
    connectionAbort ||= new AbortController();
    const connectionSignal = connectionAbort.signal;
    const connectionFetch = async (url, options = {}) => {
      if (generation !== connectionGeneration || connectionSignal.aborted) {
        throw new Error('Activity connection is closed');
      }
      const requestAbort = new AbortController();
      const signals = [connectionSignal, options.signal].filter(Boolean);
      const abort = () => requestAbort.abort();
      for (const signal of signals) {
        if (signal.aborted) abort();
        else signal.addEventListener('abort', abort, { once: true });
      }
      try { return await fetchImpl(url, { ...options, signal: requestAbort.signal }); }
      finally {
        for (const signal of signals) signal.removeEventListener('abort', abort);
      }
    };
    const attempt = Promise.resolve().then(() => initialize({
      baseUrl: resolveActivityBaseUrl(), artifact, storage: attemptStorage,
      fetchImpl: connectionFetch, now, onDiagnostic,
    }));
    initializedActivity = attempt;
    attempt.catch(() => {
      if (initializedActivity === attempt) initializedActivity = undefined;
    });
    return attempt;
  }

  async function attempt(operation, failureValue = false) {
    const generation = connectionGeneration;
    const isCurrent = () => generation === connectionGeneration;
    try {
      const activity = await initializeActivity();
      if (!isCurrent()) return failureValue;
      const result = await operation(activity, isCurrent);
      return isCurrent() ? result : failureValue;
    } catch (_) {
      if (enabled && isCurrent()) publish({ phase: 'unavailable', reason: 'service' });
      return failureValue;
    }
  }

  return {
    snapshot() { return state; },
    subscribe(listener) {
      if (typeof listener !== 'function') return () => {};
      listeners.add(listener);
      listener(state);
      return () => listeners.delete(listener);
    },
    async getPolicy() {
      const generation = connectionGeneration;
      try {
        policy ||= validateActivityPolicy(await policyLoader());
        if (generation === connectionGeneration) publish({ phase: enabled ? state.phase : 'off', policy });
        return policy;
      } catch (_) {
        if (generation === connectionGeneration) publish({ phase: 'blocked', reason: 'notice-unavailable' });
        return null;
      }
    },
    resume() {
      return preference() ? this.enable({ resume: true }) : Promise.resolve(false);
    },
    async enable({ resume = false } = {}) {
      if (enableAttempt) return enableAttempt;
      const generation = connectionGeneration;
      const currentAttempt = (async () => {
        const currentPolicy = await this.getPolicy();
        if (generation !== connectionGeneration) return false;
        if (!isActivityPolicyApproved(currentPolicy)) {
          publish({ phase: 'blocked', reason: 'policy' });
          return false;
        }
        try { artifact ||= await artifactResolver(); }
        catch (error) {
          if (generation !== connectionGeneration) return false;
          publish({ phase: 'blocked', reason: error?.code === 'secure-context' ? 'secure-context' : 'artifact' });
          return false;
        }
        if (generation !== connectionGeneration) return false;
        const previous = resume ? preference() : null;
        if (resume && (previous?.digest !== artifact.artifact_digest
            || previous?.notice !== currentPolicy.notice_version)) return false;
        publish({ phase: 'connecting', reason: null });
        const startedAt = performanceImpl?.now?.() ?? Date.now();
        const activityPromise = initializeActivity();
        const attemptStorage = storage;
        let activity;
        try { activity = await activityPromise; }
        catch (_) { activity = null; }
        if (generation !== connectionGeneration) {
          if (initializedActivity === activityPromise) initializedActivity = undefined;
          attemptStorage?.dispose();
          if (storage === attemptStorage) storage = undefined;
          return false;
        }
        const remote = activity ? await attempt(value => value.getState(), null) : null;
        if (generation !== connectionGeneration) {
          initializedActivity = undefined;
          attemptStorage?.dispose();
          if (storage === attemptStorage) storage = undefined;
          return false;
        }
        if (!remote) {
          publish({ phase: 'unavailable', reason: 'service' });
          return false;
        }
        enabled = true;
        referralTracking = previous?.referralTracking === true && !globalPrivacyControl;
        savePreference();
        const endedAt = performanceImpl?.now?.() ?? Date.now();
        publish({
          phase: 'connected',
          progressPercent: Number(remote.progressPercent) || 0,
          completedAt: remote.completedAt || null,
          observedLatencyMs: Math.max(0, Math.round(endedAt - startedAt)),
          observedAt: (now ? now() : new Date()).toISOString(),
        });
        return true;
      })();
      enableAttempt = currentAttempt;
      try { return await currentAttempt; }
      finally { if (enableAttempt === currentAttempt) enableAttempt = undefined; }
    },
    disconnect() {
      connectionGeneration += 1;
      enabled = false;
      referralTracking = false;
      savePreference();
      initializedActivity = undefined;
      storage?.dispose();
      storage = undefined;
      connectionAbort?.abort();
      connectionAbort = undefined;
      return publish({ phase: 'off', reason: null, progressPercent: 0, completedAt: null, observedLatencyMs: null, observedAt: null });
    },
    setReferralTracking(value) {
      referralTracking = enabled && value === true && !globalPrivacyControl;
      savePreference();
      publish({});
      return referralTracking;
    },
    trackBuildReferral(destinationUrl) {
      return this.trackReferral(destinationUrl);
    },
    trackReferral(destinationUrl) {
      if (!enabled || !referralTracking) return Promise.resolve(false);
      const referenceId = ACTIVITY_REFERRALS[destinationUrl];
      if (!referenceId) return Promise.resolve(false);
      return attempt(async activity => {
        await activity.referral({
          referenceId,
          destinationUrl,
          idempotencyKey: `nemoclaw:referral:${referenceId}`,
        });
        return true;
      });
    },
    recordMilestone(milestoneRef) {
      if (!enabled) return Promise.resolve(false);
      const milestone = ACTIVITY_MILESTONES[milestoneRef];
      if (!milestone) return Promise.resolve(false);
      return attempt(async activity => {
        await activity.progress(milestone.progressPercent, {
          idempotencyKey: `nemoclaw:milestone:${milestoneRef}`,
        });
        return true;
      });
    },
    getCourseActivityState() {
      if (!enabled) return Promise.resolve(null);
      return attempt(activity => activity.getState(), null);
    },
    recordCompletion() {
      if (!enabled) return Promise.resolve(false);
      return attempt(async (activity, isCurrent) => {
        const state = await activity.getState();
        if (!isCurrent()) return false;
        if (!Number.isInteger(state?.progressPercent) || state.progressPercent !== 100) return false;
        const result = await activity.complete({ idempotencyKey: 'nemoclaw:course:completed' });
        return result?.written !== false;
      });
    },
  };
}

export { createNemoClawActivity as createCourseActivity };
