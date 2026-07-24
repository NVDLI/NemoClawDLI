// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Mount the shared runtime-tool palette used by browser-hosted Python courses.
 *
 * The controller owns only disclosure, focus, and view selection. Course-specific
 * runtime state remains with the course, so this module cannot start work, read a
 * credential, or invent a successful operation.
 */
export function mountRuntimeWorkbench(root, {
  defaultView = null,
  labels = {},
  onOpen = () => {},
} = {}) {
  if (!(root instanceof Element)) throw new TypeError("A runtime workbench root is required.");
  const panel = root.querySelector("[data-workbench-panel]");
  const title = root.querySelector("[data-workbench-title]");
  const closeButton = root.querySelector("[data-workbench-close]");
  const tools = [...root.querySelectorAll("[data-workbench-view]")];
  const views = [...root.querySelectorAll("[data-workbench-content]")];
  if (!panel || !title || !closeButton || !tools.length || !views.length) {
    throw new Error("Runtime workbench markup is incomplete.");
  }

  let activeView = null;
  let returnFocus = null;

  function setSelection(view) {
    for (const tool of tools) {
      tool.setAttribute("aria-pressed", String(tool.dataset.workbenchView === view));
    }
    for (const content of views) {
      content.hidden = content.dataset.workbenchContent !== view;
    }
  }

  function close({ restoreFocus = true } = {}) {
    panel.hidden = true;
    setSelection(null);
    activeView = null;
    root.dataset.workbenchOpen = "false";
    root.dispatchEvent(new CustomEvent("workbench:viewchange", { detail: { view: null } }));
    if (restoreFocus && returnFocus?.isConnected) returnFocus.focus();
  }

  function open(view, { focus = true, toggle = false, trigger = null } = {}) {
    const content = views.find(candidate => candidate.dataset.workbenchContent === view);
    if (!content) throw new Error(`Unknown runtime workbench view: ${view}`);
    if (toggle && !panel.hidden && activeView === view) {
      close();
      return;
    }
    returnFocus = trigger || document.activeElement;
    activeView = view;
    title.textContent = labels[view] || view;
    panel.hidden = false;
    root.dataset.workbenchOpen = "true";
    setSelection(view);
    onOpen(view);
    root.dispatchEvent(new CustomEvent("workbench:viewchange", { detail: { view } }));
    if (focus) panel.focus({ preventScroll: true });
  }

  for (const tool of tools) {
    tool.addEventListener("click", () => open(tool.dataset.workbenchView, {
      toggle: true,
      trigger: tool,
    }));
  }
  closeButton.addEventListener("click", () => close());
  panel.addEventListener("keydown", event => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    close();
  });

  root.dataset.workbenchReady = "true";
  if (defaultView) open(defaultView, { focus: false });
  return Object.freeze({
    close,
    open,
    get activeView() { return activeView; },
  });
}
