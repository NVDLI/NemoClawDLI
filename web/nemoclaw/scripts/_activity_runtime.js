// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ACTIVITY_ARTIFACT,
  ACTIVITY_REFERRALS,
  createNemoClawActivity,
} from './_activity.js';

const EVIDENCE_KEY_PREFIX = 'dli_activity:nemoclaw:evidence:v1';
const MILESTONE_ORDER = Object.freeze([
  '01a:model-call-verified',
  '01b:react-loop-complete',
  '01c:tool-roundtrip-complete',
  '02a:routed-workflow-complete',
  '02b:grounded-answer-complete',
  '02c:deep-research-complete',
  '03a:nemoclaw-connected',
  '03b:workspace-inspected',
  '03c:scheduled-run-complete',
  '04a:policy-boundary-verified',
  '04b:live-agent-operated',
]);

export function highestContiguousMilestone(completed) {
  let latest = null;
  for (const milestone of MILESTONE_ORDER) {
    if (!completed.has(milestone)) break;
    latest = milestone;
  }
  return latest;
}

export function getInstalledNemoClawActivity(windowTarget = globalThis.window) {
  return windowTarget?.__nemoclawActivity || null;
}

function pageName() {
  return globalThis.location?.pathname?.split('/').pop() || '';
}

function evidenceStorage(target, artifactVersion) {
  const storageKey = `${EVIDENCE_KEY_PREFIX}:${artifactVersion || 'unavailable'}`;
  let memoryValue = {};
  const read = () => {
    try {
      const raw = target?.getItem(storageKey);
      if (raw) memoryValue = JSON.parse(raw);
    } catch (_) {}
    return { ...memoryValue };
  };
  return {
    has: key => read()[key] === true,
    add(key) {
      const value = read(); value[key] = true;
      memoryValue = value;
      try { target?.setItem(storageKey, JSON.stringify(value)); } catch (_) {}
    },
  };
}

export function installNemoClawActivityTracking({
  windowTarget = globalThis.window,
  documentTarget = globalThis.document,
  storageTarget,
  activity,
} = {}) {
  if (!windowTarget || !documentTarget) return null;
  if (windowTarget.__nemoclawActivityTracking) return getInstalledNemoClawActivity(windowTarget);
  if (storageTarget === undefined) {
    try { storageTarget = globalThis.sessionStorage; } catch (_) { storageTarget = null; }
  }
  activity ||= createNemoClawActivity({ storageTarget });
  windowTarget.__nemoclawActivityTracking = true;
  windowTarget.__nemoclawActivity = activity;
  const evidence = evidenceStorage(storageTarget, ACTIVITY_ARTIFACT.artifact_version);
  const page = pageName();
  void activity.start();

  const record = milestone => {
    evidence.add(`milestone:${milestone}`);
    const completed = new Set(MILESTONE_ORDER.filter(item => evidence.has(`milestone:${item}`)));
    const latest = highestContiguousMilestone(completed);
    return latest ? activity.recordMilestone(latest) : Promise.resolve(false);
  };
  const markPair = (key, partner, milestone) => {
    evidence.add(key);
    if (evidence.has(partner)) record(milestone);
  };

  documentTarget.addEventListener('click', event => {
    const anchor = event.target?.closest?.('a[href]');
    if (!anchor) return;
    const destination = anchor.href;
    if (ACTIVITY_REFERRALS[destination]) void activity.trackReferral(destination);
  }, true);

  windowTarget.addEventListener('nemoclaw:run-succeeded', event => {
    const { cellId, hasContent, hasAgent } = event.detail || {};
    if (page === '01a-loop.html' && cellId === 'cell-onecall' && evidence.has('01a:key')
        && hasContent) {
      record('01a:model-call-verified');
    } else if (page === '03b-openclaw.html' && cellId === 'cell-introspect') {
      markPair('03b:introspect', '03b:workspace', '03b:workspace-inspected');
    } else if (page === '03b-openclaw.html' && cellId === 'cell-workspace-term') {
      markPair('03b:workspace', '03b:introspect', '03b:workspace-inspected');
    } else if (page === '04a-safety.html' && cellId === 'cell-live-policy' && hasAgent) {
      markPair('04a:policy', '04a:agreement', '04a:policy-boundary-verified');
    }
  });

  windowTarget.addEventListener('nemoclaw:api-key-verified', () => evidence.add('01a:key'));

  windowTarget.addEventListener('nemoclaw:chat-completed', event => {
    const { containerId, successCount, hasAnswer } = event.detail || {};
    if (!hasAnswer || successCount < 1) return;
    const milestones = {
      'react-artifact': '01b:react-loop-complete',
      'tools-artifact': '01c:tool-roundtrip-complete',
      'router-artifact': '02a:routed-workflow-complete',
      'rag-artifact': '02b:grounded-answer-complete',
      'deep-artifact': '02c:deep-research-complete',
    };
    if (milestones[containerId]) record(milestones[containerId]);
  });

  windowTarget.addEventListener('nemoclaw:connection-audit-passed', () => {
    record('03a:nemoclaw-connected');
  });

  windowTarget.addEventListener('nemoclaw:canvas-node-succeeded', event => {
    const { canvasId, nodeId, runObserved, cleanupSucceeded, policyAgreed } = event.detail || {};
    if (page === '03c-always-on.html' && canvasId === 'probe-cron' && nodeId === 'cr-watch'
        && runObserved) {
      markPair('03c:run', '03c:removed', '03c:scheduled-run-complete');
    }
    if (page === '03c-always-on.html' && canvasId === 'probe-cron' && nodeId === 'cr-rm'
        && cleanupSucceeded) {
      markPair('03c:removed', '03c:run', '03c:scheduled-run-complete');
    }
    if (page === '04a-safety.html' && canvasId === 'cell-predict-confirm' && nodeId === 'compare'
        && policyAgreed) {
      markPair('04a:agreement', '04a:policy', '04a:policy-boundary-verified');
    }
  });

  windowTarget.addEventListener('nemoclaw:live-agent-operated', () => {
    record('04b:live-agent-operated');
  });
  return activity;
}
