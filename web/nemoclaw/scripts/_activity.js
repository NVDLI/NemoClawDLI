// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DLIActivity } from '../../shared/activity-sdk.js';

export const BUILD_SIGNUP_URL = 'https://build.nvidia.com/?ncid=ref-dli-146986';
const ACTIVITY_BASE_URL = 'https://activity-api.learn.nvidia.com';

export const ACTIVITY_ARTIFACT = Object.freeze({
  artifact_id: 'artifact_nemoclaw_web',
  artifact_version: '1',
  artifact_digest: 'sha256:86340bccc4bc735e9db5971b5282887e9d65adfd068d613c386e02ccc1ce0ad9',
});

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

function createSessionStorageAdapter(target, artifactVersion) {
  const storageKey = `dli_activity:nemoclaw:${artifactVersion}`;
  let memoryValue = null;
  return {
    load() {
      try {
        const raw = target?.getItem(storageKey);
        return raw ? JSON.parse(raw) : memoryValue;
      } catch (_) { return memoryValue; }
    },
    save(value) {
      memoryValue = value;
      try { target?.setItem(storageKey, JSON.stringify(value)); } catch (_) {}
    },
    clear() {
      memoryValue = null;
      try { target?.removeItem(storageKey); } catch (_) {}
    },
  };
}

export function resolveActivityBaseUrl() {
  return ACTIVITY_BASE_URL;
}

export function createNemoClawActivity({
  fetchImpl = globalThis.fetch?.bind(globalThis),
  storageTarget = globalThis.sessionStorage,
  now,
  onDiagnostic = () => {},
  initialize = options => DLIActivity.initialize(options),
} = {}) {
  let initializedActivity;

  function initializeActivity() {
    if (initializedActivity) return initializedActivity;

    const attempt = Promise.resolve().then(() => initialize({
      baseUrl: resolveActivityBaseUrl(),
      artifact: ACTIVITY_ARTIFACT,
      storage: createSessionStorageAdapter(storageTarget, ACTIVITY_ARTIFACT.artifact_version),
      fetchImpl,
      now,
      onDiagnostic,
    }));
    initializedActivity = attempt;
    attempt.catch(() => {
      if (initializedActivity === attempt) initializedActivity = undefined;
    });
    return attempt;
  }

  async function attempt(operation, failureValue = false) {
    try {
      const activity = await initializeActivity();
      return await operation(activity);
    } catch (_) {
      return failureValue;
    }
  }

  return {
    start() {
      return attempt(() => true);
    },
    trackBuildReferral(destinationUrl) {
      return this.trackReferral(destinationUrl);
    },
    trackReferral(destinationUrl) {
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
      return attempt(activity => activity.getState(), null);
    },
    recordCompletion() {
      return attempt(async activity => {
        const state = await activity.getState();
        if (!Number.isInteger(state?.progressPercent) || state.progressPercent !== 100) return false;
        const result = await activity.complete({ idempotencyKey: 'nemoclaw:course:completed' });
        return result?.written !== false;
      });
    },
  };
}
