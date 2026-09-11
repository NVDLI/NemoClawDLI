// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ACTIVITY_MILESTONES,
  ACTIVITY_REFERRALS,
  createNemoClawActivity,
} from './_activity.js';
import { localizeCourseUiText } from './_locale.js';

const EVIDENCE_KEY_PREFIX = 'dli_activity:nemoclaw:evidence:v1';
const CHECKPOINT_CONTRACT_VERSION = '1';
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
      if (raw) {
        const parsed = JSON.parse(raw);
        memoryValue = parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
      }
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

function localProgress(evidence) {
  const completed = new Set(MILESTONE_ORDER.filter(item => evidence.has(`milestone:${item}`)));
  const latest = highestContiguousMilestone(completed);
  return latest ? ACTIVITY_MILESTONES[latest].progressPercent : 0;
}

function mountActivityInterface({ windowTarget, documentTarget, activity, evidence, syncLocal }) {
  const topbar = documentTarget.querySelector?.('.topbar');
  if (!topbar || typeof documentTarget.createElement !== 'function') return null;
  const text = value => localizeCourseUiText(value);
  const root = documentTarget.createElement('div');
  root.className = 'activity-control';
  root.innerHTML = `
    <button type="button" class="activity-control-toggle" aria-expanded="false" aria-controls="activity-control-panel">
      <span class="activity-control-dot" aria-hidden="true"></span><span data-activity-label></span>
    </button>
    <section id="activity-control-panel" class="activity-control-panel" hidden role="dialog" aria-label="${text('Course activity and privacy')}">
      <header><strong>${text('Course activity')}</strong><button type="button" data-activity-close aria-label="${text('Close activity panel')}">×</button></header>
      <p data-activity-notice>${text('Remote progress is off. Nothing is sent until you enable it.')}</p>
      <p data-activity-status role="status" aria-live="polite"></p>
      <label id="activity-progress-label" for="activity-progress"></label>
      <progress id="activity-progress" max="100" value="0" aria-labelledby="activity-progress-label"></progress>
      <p data-activity-sync></p>
      <p>${text('Progress records successful course activity checkpoints.')}</p>
      <div class="activity-control-actions">
        <button type="button" data-activity-enable>${text('Enable remote progress')}</button>
        <button type="button" data-activity-refresh hidden>${text('Refresh saved progress')}</button>
        <button type="button" data-activity-disable hidden>${text('Disconnect this tab')}</button>
      </div>
      <label class="activity-referral-choice"><input type="checkbox" data-activity-referrals disabled> ${text('Record selections of approved NVIDIA resources')}</label>
      <details>
        <summary>${text('Data, purpose, and retention')}</summary>
        <p><strong>${text('Sent to NVIDIA DLI Activity API')}</strong></p>
        <ul data-activity-data></ul>
        <p><strong>${text('Purpose')}</strong></p>
        <ul data-activity-purpose></ul>
        <p data-activity-browser-retention></p>
        <p data-activity-controller></p>
        <p data-activity-legal-basis></p>
        <p data-activity-service-retention></p>
        <p data-activity-sale-sharing></p>
        <p>${text('The course does not send API keys, prompts, model responses, terminal output, or workspace files to the Activity API.')}</p>
      </details>
      <details>
        <summary>${text('Service status')}</summary>
        <p data-activity-service-level></p>
        <p data-activity-observation>${text('No connection has been measured in this tab.')}</p>
      </details>
      <p class="activity-control-links"><a data-activity-policy target="_blank" rel="noopener noreferrer">${text('NVIDIA Privacy Policy')}</a><a data-activity-rights target="_blank" rel="noopener noreferrer">${text('Privacy choices and requests')}</a></p>
      <p data-activity-gpc hidden>${text('Global Privacy Control is enabled. Referral tracking remains off.')}</p>
    </section>`;
  const keyPill = topbar.querySelector('.key-pill');
  topbar.insertBefore(root, keyPill || null);

  const toggle = root.querySelector('.activity-control-toggle');
  const panel = root.querySelector('.activity-control-panel');
  const label = root.querySelector('[data-activity-label]');
  const notice = root.querySelector('[data-activity-notice]');
  const status = root.querySelector('[data-activity-status]');
  const progressBar = root.querySelector('#activity-progress');
  const progressLabel = root.querySelector('#activity-progress-label');
  const syncStatus = root.querySelector('[data-activity-sync]');
  const enable = root.querySelector('[data-activity-enable]');
  const refresh = root.querySelector('[data-activity-refresh]');
  const disable = root.querySelector('[data-activity-disable]');
  const referrals = root.querySelector('[data-activity-referrals]');
  const observation = root.querySelector('[data-activity-observation]');
  const gpc = windowTarget.navigator?.globalPrivacyControl === true;
  if (gpc) root.querySelector('[data-activity-gpc]').hidden = false;

  const setPanel = open => {
    panel.hidden = !open;
    toggle.setAttribute('aria-expanded', String(open));
    if (open) panel.querySelector('button, a')?.focus();
  };
  toggle.addEventListener('click', () => setPanel(panel.hidden));
  root.querySelector('[data-activity-close]').addEventListener('click', () => {
    setPanel(false); toggle.focus();
  });
  panel.addEventListener('keydown', event => {
    if (event.key === 'Escape') { setPanel(false); toggle.focus(); }
  });

  let policy = null;
  let refreshing = false;
  const render = state => {
    const progress = localProgress(evidence);
    const saved = state.enabled && Boolean(state.progressCheckedAt);
    const shownProgress = saved ? state.progressPercent : progress;
    const progressKind = saved
      ? (state.phase === 'connected' ? 'Saved progress:' : 'Last confirmed progress:')
      : 'Local verified progress:';
    root.dataset.state = state.phase;
    label.textContent = `${text(saved ? 'Activity' : 'Activity: local')} ${shownProgress}%`;
    progressLabel.textContent = `${text(progressKind)} ${shownProgress}%`;
    toggle.title = progressLabel.textContent;
    progressBar.value = shownProgress;
    progressBar.setAttribute('aria-valuetext', progressLabel.textContent);
    syncStatus.replaceChildren();
    if (saved && progress > state.progressPercent) {
      syncStatus.append(documentTarget.createTextNode(
        `${text('Local verified progress:')} ${progress}%. ${text('Waiting for API confirmation.')}`,
      ));
    } else if (saved && state.phase === 'connected') {
      syncStatus.textContent = text('Confirmed by the Activity API.');
    }
    disable.hidden = state.phase === 'off' || state.phase === 'blocked';
    enable.hidden = state.enabled;
    refresh.hidden = !state.enabled;
    refresh.disabled = refreshing || state.phase === 'connecting';
    referrals.disabled = state.phase !== 'connected' || gpc;
    referrals.checked = state.referralTracking && !gpc;
    if (state.phase === 'connecting') status.textContent = text('Connecting to the Activity API.');
    else if (state.phase === 'connected') status.textContent = state.completedAt ? text('Course completed') : '';
    else if (state.phase === 'unavailable') status.textContent = text('The Activity API is unavailable. Local course work is unchanged.');
    else if (state.reason === 'secure-context') status.textContent = text('Open this course over HTTPS to enable remote progress.');
    else if (state.reason === 'artifact') status.textContent = text('Remote progress is available only from a validated course build.');
    else if (state.phase === 'blocked') status.textContent = text('Remote progress is unavailable until its data policy is approved.');
    else status.textContent = '';
    status.hidden = !status.textContent;
    if (state.observedAt && Number.isInteger(state.observedLatencyMs)) {
      observation.replaceChildren(
        documentTarget.createTextNode(`${text('Last connection:')} `),
        documentTarget.createTextNode(`${state.observedLatencyMs} ms, `),
        Object.assign(documentTarget.createElement('time'), {
          dateTime: state.observedAt, textContent: state.observedAt,
        }),
      );
    } else observation.textContent = text('No connection has been measured in this tab.');
    const approved = policy?.collection_enabled === true
      && policy.publication_status === 'privacy-legal-reviewed'
      && policy.controller?.status === 'confirmed'
      && policy.service_retention?.status === 'confirmed'
      && policy.legal_basis?.status === 'confirmed'
      && ['confirmed', 'not-applicable'].includes(policy.sale_sharing?.status);
    enable.disabled = state.phase === 'connecting' || !approved;
    notice.hidden = state.phase === 'connecting';
    notice.textContent = approved
      ? text(state.enabled ? 'Remote progress is enabled.' : 'Remote progress is off. Nothing is sent until you enable it.')
      : text('Remote collection is disabled while privacy, legal, and service-owner review is incomplete.');
  };
  activity.subscribe(render);

  enable.addEventListener('click', async () => {
    if (await activity.enable()) await syncLocal();
  });
  refresh.addEventListener('click', async () => {
    if (refreshing) return;
    refreshing = true;
    refresh.disabled = true;
    try { if (await activity.getCourseActivityState()) await syncLocal(); }
    finally { refreshing = false; render(activity.snapshot()); }
  });
  disable.addEventListener('click', () => activity.disconnect());
  referrals.addEventListener('change', () => activity.setReferralTracking(referrals.checked && !gpc));

  void activity.getPolicy().then(value => {
    policy = value;
    if (!policy) return render(activity.snapshot());
    root.querySelector('[data-activity-data]').replaceChildren(...policy.data_categories.map(item => {
      const li = documentTarget.createElement('li'); li.textContent = text(item); return li;
    }));
    root.querySelector('[data-activity-purpose]').replaceChildren(...policy.purposes.map(item => {
      const li = documentTarget.createElement('li'); li.textContent = text(item); return li;
    }));
    root.querySelector('[data-activity-browser-retention]').textContent = text(policy.browser_retention);
    root.querySelector('[data-activity-controller]').textContent = policy.controller.status === 'confirmed'
      ? `${text('Service controller:')} ${text(policy.controller.name)}`
      : text('The service controller is not yet confirmed. Remote collection remains disabled.');
    root.querySelector('[data-activity-legal-basis]').textContent = policy.legal_basis.status === 'confirmed'
      ? `${text('Service legal basis:')} ${text(policy.legal_basis.basis)}`
      : text('The service legal basis is not yet confirmed. Remote collection remains disabled.');
    root.querySelector('[data-activity-service-retention]').textContent = policy.service_retention.status === 'confirmed'
      ? `${text('Service retention:')} ${text(policy.service_retention.period_or_criteria)}`
      : text('Service-specific retention is not yet confirmed. Remote collection remains disabled.');
    root.querySelector('[data-activity-sale-sharing]').textContent = ['confirmed', 'not-applicable'].includes(policy.sale_sharing.status)
      ? `${text('Service sale or sharing disposition:')} ${text(policy.sale_sharing.disposition)}`
      : text('The service sale or sharing disposition is not yet confirmed. Remote collection remains disabled.');
    root.querySelector('[data-activity-service-level]').textContent = policy.service_level.status === 'published'
      ? `${text('Published service target:')} ${text(policy.service_level.target)}`
      : text('No course-level availability or response-time target is published. Live status is an observation, not an SLA.');
    root.querySelector('[data-activity-policy]').href = policy.privacy_policy_url;
    root.querySelector('[data-activity-rights]').href = policy.privacy_center_url;
    render(activity.snapshot());
  });
  void activity.resume().then(connected => { if (connected) return syncLocal(); });
  return { root, refresh: () => render(activity.snapshot()) };
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
  const evidence = evidenceStorage(storageTarget, CHECKPOINT_CONTRACT_VERSION);
  const page = pageName();

  let activityInterface;
  const record = milestone => {
    evidence.add(`milestone:${milestone}`);
    activityInterface?.refresh();
    const completed = new Set(MILESTONE_ORDER.filter(item => evidence.has(`milestone:${item}`)));
    const latest = highestContiguousMilestone(completed);
    return latest ? activity.recordMilestone(latest) : Promise.resolve(false);
  };
  const syncLocal = () => {
    const latest = highestContiguousMilestone(
      new Set(MILESTONE_ORDER.filter(item => evidence.has(`milestone:${item}`))),
    );
    return latest ? activity.recordMilestone(latest) : Promise.resolve(false);
  };
  activityInterface = mountActivityInterface({
    windowTarget, documentTarget, activity, evidence, syncLocal,
  });
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

export {
  MILESTONE_ORDER as ACTIVITY_MILESTONE_ORDER,
  getInstalledNemoClawActivity as getInstalledCourseActivity,
  installNemoClawActivityTracking as installCourseActivityTracking,
};
