// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  ACTIVITY_CONFIG,
  ACTIVITY_MILESTONES,
  ACTIVITY_MILESTONE_ORDER as MILESTONE_ORDER,
  ACTIVITY_REFERRALS,
  createNemoClawActivity,
} from './_activity.js';
import { localizeCourseUiText } from '../nemoclaw/scripts/_locale.js';
import { bindActivityMilestones } from './activity-sdk.js';

const EVIDENCE_KEY_PREFIX = 'dli_activity:nemoclaw:evidence:v1';
const CHECKPOINT_CONTRACT_VERSION = '1';

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


// C0002 is Performance Cookies in the nvdli.github.io OneTrust configuration.
export function bindNemoClawProgressConsent({ windowTarget, activity, syncLocal }) {
  let lastConsent;
  let generation = 0;
  let registeredCmp;
  const consentChangeListeners = new Set();
  const allowsProgress = () => {
    try {
      return windowTarget.OneTrust?.IsAlertBoxClosed?.() === true
        && typeof windowTarget.OnetrustActiveGroups === 'string'
        && windowTarget.OnetrustActiveGroups.split(',').includes('C0002');
    } catch (_) { return false; }
  };
  const reconcile = () => {
    const cmp = windowTarget.OneTrust;
    if (cmp && cmp !== registeredCmp && typeof cmp.OnConsentChanged === 'function') {
      registeredCmp = cmp;
      cmp.OnConsentChanged(() => {
        for (const listener of consentChangeListeners) listener();
        reconcile();
      });
    }
    const ready = typeof cmp?.IsAlertBoxClosed === 'function'
      && typeof windowTarget.OnetrustActiveGroups === 'string';
    const consent = ready ? allowsProgress() : null;
    if (consent === lastConsent) return;
    const previousConsent = lastConsent;
    lastConsent = consent;
    const currentGeneration = ++generation;
    if (!consent) {
      // Also abort a connection that is still pending when consent is withdrawn.
      const state = activity.snapshot();
      if (consent === false || previousConsent === true || state.enabled || state.phase === 'connecting') activity.disconnect();
      return;
    }
    if (activity.snapshot().enabled) return;
    const connect = async () => {
      if (await activity.resume()) return true;
      if (currentGeneration !== generation || !allowsProgress()) return false;
      return activity.enable();
    };
    void connect().then(connected => {
      if (connected && currentGeneration === generation && allowsProgress()) return syncLocal();
    }).catch(() => {});
  };
  windowTarget.addEventListener('bannerLoaded', reconcile);
  windowTarget.addEventListener('OneTrustGroupsUpdated', reconcile);
  reconcile();
  return {
    allowsProgress,
    reconcile,
    async retry() {
      if (!allowsProgress()) return false;
      const currentGeneration = generation;
      const connected = activity.snapshot().enabled
        ? Boolean(await activity.getCourseActivityState()) : await activity.enable();
      if (connected && currentGeneration === generation && allowsProgress()) await syncLocal();
      return connected && currentGeneration === generation && allowsProgress();
    },
    subscribeConsentChanges(listener) {
      consentChangeListeners.add(listener);
      return () => consentChangeListeners.delete(listener);
    },
  };
}

function mountActivityInterface({ windowTarget, documentTarget, activity, evidence, consent }) {
  const topbar = documentTarget.querySelector?.('.topbar');
  if (!topbar || typeof documentTarget.createElement !== 'function') return null;
  const text = value => localizeCourseUiText(value);
  const root = documentTarget.createElement('div');
  root.className = 'activity-control';
  root.innerHTML = `
    <button type="button" class="activity-control-toggle" aria-expanded="false" aria-controls="activity-control-panel" aria-label="${text('Progress')}" title="${text('Progress')}">
      <span data-activity-label></span>
    </button>
    <section id="activity-control-panel" class="activity-control-panel" hidden role="dialog" aria-label="${text('Course progress')}">
      <header><strong>${text('Progress')}</strong><button type="button" data-activity-close aria-label="${text('Close progress panel')}">×</button></header>
      <p data-activity-status role="status" aria-live="polite" hidden></p>
      <button type="button" data-activity-retry hidden>${text('Reconnect')}</button>
      <div class="activity-progress-stage" data-tracking="off">
      <div data-activity-milestones inert aria-hidden="true">
      <p class="milestone-summary" data-milestone-summary role="status" aria-live="polite"></p>
      <p class="milestone-intro">${text('Complete the exercises below. Checkmarks appear after each milestone is saved.')}</p>
      <ol class="course-milestones" aria-label="${text('Course milestones')}"></ol>
      </div>
      <div class="activity-progress-overlay" data-activity-overlay>
      <div class="activity-control-actions">
        <button type="button" data-activity-enable>${text('Enable Milestone Tracking')}</button>
      </div>
      <p data-activity-explanation>${text('This enables Performance Cookies to measure website visits and interactions, recognize returning visitors, and improve website performance.')}</p>
      </div>
      </div>
    </section>`;
  const keyPill = topbar.querySelector('.key-pill');
  topbar.insertBefore(root, keyPill || null);

  const toggle = root.querySelector('.activity-control-toggle');
  const label = root.querySelector('[data-activity-label]');
  const panel = root.querySelector('.activity-control-panel');
  const summary = root.querySelector('[data-milestone-summary]');
  const status = root.querySelector('[data-activity-status]');
  const retry = root.querySelector('[data-activity-retry]');
  const milestones = root.querySelector('[data-activity-milestones]');
  const enable = root.querySelector('[data-activity-enable]');
  const stage = root.querySelector('.activity-progress-stage');
  const overlay = root.querySelector('[data-activity-overlay]');
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

  const rows = MILESTONE_ORDER.map(id => {
    const milestone = ACTIVITY_MILESTONES[id];
    const row = documentTarget.createElement('li');
    row.dataset.milestone = id;
    const icon = documentTarget.createElement('span');
    icon.className = 'milestone-icon';
    icon.setAttribute('aria-hidden', 'true');
    const content = documentTarget.createElement('div');
    const link = documentTarget.createElement('a');
    link.href = milestone.href;
    link.textContent = text(milestone.label);
    const description = documentTarget.createElement('p');
    description.textContent = text(milestone.description);
    const stateLabel = documentTarget.createElement('span');
    stateLabel.className = 'milestone-state';
    content.append(link, description, stateLabel);
    row.append(icon, content);
    root.querySelector('.course-milestones').append(row);
    let callout;
    const [lesson, anchor] = milestone.href.split('#');
    const target = lesson === pageName() && documentTarget.getElementById(anchor);
    if (target) {
      callout = documentTarget.createElement('aside');
      callout.className = 'course-milestone-callout';
      callout.setAttribute('aria-label', text('Course milestone'));
      const heading = documentTarget.createElement('strong');
      heading.textContent = text(milestone.label);
      const instruction = documentTarget.createElement('p');
      instruction.textContent = text(milestone.description);
      const badge = documentTarget.createElement('span');
      badge.className = 'milestone-state';
      callout.append(heading, instruction, badge);
      target.before(callout);
    }
    return { id, milestone, row, icon, stateLabel, callout };
  });

  let retryInProgress = false;
  const render = state => {
    const saved = state.enabled && Boolean(state.milestonesCheckedAt);
    let count = 0;
    rows.forEach(({ id, milestone, row, icon, stateLabel, callout }) => {
      const confirmed = saved && state.milestones?.some(marker => marker.milestoneId === id && marker.completedAt !== null);
      const local = evidence.has(`milestone:${id}`);
      const reached = confirmed;
      if (reached) count++;
      const caption = confirmed ? 'Saved' : local ? 'Waiting to save' : 'Not yet reached';
      row.dataset.completed = String(reached);
      row.setAttribute('aria-label', `${text(milestone.label)}: ${text(caption)}`);
      icon.textContent = reached ? '✓' : '○';
      stateLabel.textContent = text(caption);
      if (callout) {
        callout.hidden = !consent.allowsProgress();
        callout.dataset.completed = String(reached);
        callout.querySelector('.milestone-state').textContent = reached
          ? `✓ ${text(caption)}` : text('Course milestone');
      }
    });
    root.dataset.state = state.phase;
    const optedIn = consent.allowsProgress();
    label.textContent = optedIn ? `${text('Progress')} ${count}/${rows.length}` : text('Progress');
    toggle.setAttribute('aria-label', optedIn ? `${text('Progress')}: ${count} / ${rows.length}` : text('Progress'));
    toggle.title = text('Progress');
    summary.textContent = state.completedAt ? text('✓ Course complete')
      : `${count} / ${rows.length} ${text('milestones reached')}`;
    stage.dataset.tracking = optedIn ? 'on' : 'off';
    milestones.inert = !optedIn;
    milestones.setAttribute('aria-hidden', String(!optedIn));
    overlay.hidden = optedIn;
    enable.hidden = optedIn;
    const cmpReady = typeof windowTarget.OneTrust?.UpdateConsent === 'function'
      && typeof windowTarget.OneTrust?.SetAlertBoxClosed === 'function';
    const failed = optedIn && ['blocked', 'unavailable'].includes(state.phase);
    status.hidden = cmpReady && !failed;
    status.textContent = text(!cmpReady ? 'Remote progress is unavailable for this course deployment.'
      : state.reason === 'artifact' ? 'Open a validated course build before enabling remote progress.'
      : state.reason === 'policy' || state.reason === 'notice-unavailable'
        ? 'Remote progress is unavailable until its data policy is approved.'
        : state.reason === 'secure-context' ? 'Remote progress requires a secure browser context.'
        : 'The Activity API is unavailable. Local course work is unchanged.');
    retry.hidden = !optedIn || (!failed && !retryInProgress);
    retry.disabled = retryInProgress;
    enable.disabled = !cmpReady && !windowTarget.OneTrust;
  };
  activity.subscribe(render);
  let pendingOptIn = false;
  consent.subscribeConsentChanges(() => { pendingOptIn = false; });
  const applyOptIn = () => {
    const cmp = windowTarget.OneTrust;
    if (!pendingOptIn || typeof cmp?.UpdateConsent !== 'function'
        || typeof cmp?.SetAlertBoxClosed !== 'function') return;
    pendingOptIn = false;
    cmp.SetAlertBoxClosed();
    cmp.UpdateConsent('Category', 'C0002:1');
    consent.reconcile();
    render(activity.snapshot());
  };
  const consentReady = () => {
    applyOptIn();
    render(activity.snapshot());
  };
  windowTarget.addEventListener('bannerLoaded', consentReady);
  windowTarget.addEventListener('OneTrustGroupsUpdated', consentReady);
  enable.addEventListener('click', () => {
    pendingOptIn = true;
    applyOptIn();
  });
  retry.addEventListener('click', async () => {
    retryInProgress = true;
    retry.disabled = true;
    try { await consent.retry(); }
    finally {
      const focused = documentTarget.activeElement === retry;
      retryInProgress = false;
      render(activity.snapshot());
      if (focused && retry.hidden) toggle.focus();
    }
  });
  return { root, refresh: () => render(activity.snapshot()) };
}

export function installNemoClawActivityTracking({
  windowTarget = globalThis.window,
  documentTarget = globalThis.document,
  storageTarget,
  activity,
} = {}) {
  if (!windowTarget || !documentTarget) return null;
  if (!ACTIVITY_CONFIG) {
    windowTarget.__nemoclawActivityConfigUnavailable = true;
    return null;
  }
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
  // Stored exercise flags are hints; only new success events are eligible to send.
  const pending = new Map();
  let instrumentation;
  const bindSession = state => {
    const sessionId = state.sessionId;
    instrumentation?.bindSession(state);
    if (state.enabled && sessionId) {
      for (const [id, boundSessionId] of pending) {
        if (boundSessionId === null) pending.set(id, sessionId);
        else if (boundSessionId !== sessionId) pending.delete(id);
      }
    }
  };
  activity.subscribe(bindSession);
  const syncLocal = async () => {
    bindSession(activity.snapshot());
    if (!activity.snapshot().enabled || !activity.snapshot().sessionId || !pending.size) return false;
    if (!await activity.getCourseActivityState()) return false;
    for (const [id, sessionId] of pending) {
      if (sessionId !== activity.snapshot().sessionId) { pending.delete(id); continue; }
      if (!await activity.recordMilestone(id, { sessionId })) return false;
      pending.delete(id);
    }
    return true;
  };

  const record = milestone => {
    if (!ACTIVITY_MILESTONES[milestone]) return Promise.resolve(false);
    evidence.add(`milestone:${milestone}`);
    pending.set(milestone, activity.snapshot().sessionId);
    activityInterface?.refresh();
    return syncLocal();
  };
  const consent = bindNemoClawProgressConsent({ windowTarget, activity, syncLocal });
  activityInterface = mountActivityInterface({
    windowTarget, documentTarget, activity, evidence, consent,
  });
  instrumentation = bindActivityMilestones({
    config: ACTIVITY_CONFIG, eventTarget: windowTarget, documentTarget, page,
    sessionId: activity.snapshot().sessionId, onMilestone: record,
  });

  documentTarget.addEventListener('click', event => {
    const anchor = event.target?.closest?.('a[href]');
    if (!anchor) return;
    const destination = anchor.href;
    if (ACTIVITY_REFERRALS[destination]) void activity.trackReferral(destination);
  }, true);

  return activity;
}

export {
  MILESTONE_ORDER as ACTIVITY_MILESTONE_ORDER,
  getInstalledNemoClawActivity as getInstalledCourseActivity,
  installNemoClawActivityTracking as installCourseActivityTracking,
};
