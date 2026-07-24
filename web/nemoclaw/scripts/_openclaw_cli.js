// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// OpenClaw CLI artifact runtime.
// This module keeps gateway transport and session tabs out of the student editing surface.
// The exported mount function remains an inspectable boundary for lessons and tests.

import { localizeCourseUiText } from "./_locale.js";

const CALL_TIMEOUT_MS = 20000;
const CONNECT_TIMEOUT_MS = 15000;
const STORAGE_KEY = "nemoclaw_branches";
const WARMED_STORAGE_KEY = "nemoclaw_warmed";
const DEFAULT_SESSION = "main";
const FALLBACK_COMMANDS = [
  "/help", "/clear", "/branch", "/reset", "/new", "/compact", "/model", "/models",
  "/usage", "/status", "/context", "/think", "/config", "/agents", "/subagents",
  "/mcp", "/tasks", "/review", "/whoami", "/commands",
];
const SUGGESTIONS = [
  "/help", "/model", "/status", "/reset", "What can you do?",
  "Summarize your workspace and your SOUL.md",
  "Use exec to run ls -la /sandbox/.openclaw/workspace",
];

function uniqueId(prefix = "") {
  if (typeof crypto.randomUUID === "function") return prefix + crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return prefix + [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
}

function readStringList(key) {
  try {
    const value = JSON.parse(localStorage.getItem(key) || "[]");
    return Array.isArray(value) ? value.filter(item => typeof item === "string" && item) : [];
  } catch (_) {
    return [];
  }
}

function writeStringList(key, values) {
  try { localStorage.setItem(key, JSON.stringify(values)); } catch (_) {}
}

function createGatewayRpc(runtime) {
  let activeSocket = null;

  // Reject every outstanding RPC when its shared socket closes.
  function closePending(socket, error) {
    Object.values(socket.pending).forEach(item => {
      clearTimeout(item.timer);
      item.reject(error);
    });
    socket.pending = {};
  }

  function send(socket, method, params = {}, signal = null) {
    return new Promise((resolve, reject) => {
      const id = uniqueId("rpc-");
      let settled = false;
      let timer = null;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        signal?.removeEventListener("abort", stop);
        delete socket.pending[id];
        callback(value);
      };
      const stop = () => {
        finish(reject, new DOMException("stopped", "AbortError"));
      };
      timer = setTimeout(() => finish(reject, new Error(method + " timed out")), CALL_TIMEOUT_MS);
      if (signal?.aborted) return stop();
      signal?.addEventListener("abort", stop, { once: true });
      socket.pending[id] = {
        timer,
        resolve: value => finish(resolve, value),
        reject: error => finish(reject, error),
      };
      try {
        socket.ws.send(JSON.stringify({ type: "req", id, method, params }));
      } catch (error) {
        finish(reject, error);
      }
    });
  }

  function connect(signal = null) {
    const connection = runtime.getOpenClawConnection();
    if (!(connection.token && connection.rawUrl)) {
      return Promise.reject(new Error("Connect on Module 3a first (URL + token)."));
    }
    if (activeSocket?.ready && activeSocket.ws.readyState === WebSocket.OPEN) return Promise.resolve(activeSocket);

    return new Promise((resolve, reject) => {
      const endpoint = runtime.openclawGatewayWsUrl(connection.rawUrl, connection.accessSession, null, null, connection.accessProvider).url;
      const socket = { ws: new WebSocket(endpoint), pending: {}, ready: false };
      let settled = false;
      let connectTimer = null;
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(connectTimer);
        signal?.removeEventListener("abort", stop);
        callback(value);
      };
      const stop = () => {
        try { socket.ws.close(); } catch (_) {}
        finish(reject, new DOMException("stopped", "AbortError"));
      };
      connectTimer = setTimeout(() => {
        try { socket.ws.close(); } catch (_) {}
        finish(reject, new Error("gateway did not respond in 15s; reopen your launchable URL to re-authenticate."));
      }, CONNECT_TIMEOUT_MS);
      if (signal?.aborted) return stop();
      signal?.addEventListener("abort", stop, { once: true });

      // The gateway requires an authenticated connect request after its challenge event.
      socket.ws.onmessage = event => {
        let message;
        try { message = JSON.parse(event.data); } catch (_) { return; }
        if (!socket.ready && message.event === "connect.challenge") {
          send(socket, "connect", {
            minProtocol: 4,
            maxProtocol: 4,
            client: { id: "openclaw-control-ui", version: "0.1.0", platform: "browser", mode: "webchat" },
            caps: ["tool-events"],
            role: "operator",
            scopes: ["operator.read", "operator.write", "operator.admin"],
            auth: { token: connection.token },
          }, signal).then(() => {
            socket.ready = true;
            activeSocket = socket;
            finish(resolve, socket);
          }, error => finish(reject, error));
          return;
        }
        if (message.type !== "res" || !message.id || !socket.pending[message.id]) return;
        const pending = socket.pending[message.id];
        clearTimeout(pending.timer);
        delete socket.pending[message.id];
        if (message.ok) pending.resolve(message.payload);
        else pending.reject(new Error(message.error?.message || "gateway error"));
      };
      socket.ws.onerror = () => {};
      socket.ws.onclose = () => {
        if (activeSocket === socket) activeSocket = null;
        const opened = socket.ready;
        socket.ready = false;
        closePending(socket, new Error("gateway connection closed"));
        if (!opened) finish(reject, new Error("gateway connection closed before authentication completed"));
      };
    });
  }

  return {
    async call(method, params = {}, signal = null) {
      const socket = await connect(signal);
      return send(socket, method, params, signal);
    },
    close() {
      try { activeSocket?.ws.close(); } catch (_) {}
      activeSocket = null;
    },
  };
}

function createArtifactView(target) {
  const output = target.querySelector(".da-out");
  let answer = null;
  const view = { streamed: false };
  view.token = delta => {
    view.streamed = true;
    if (!answer) { answer = document.createElement("div"); output.appendChild(answer); }
    answer.textContent += delta;
  };
  view.tool = (label, body) => {
    // Tool output stays collapsed so the agent answer remains the dominant artifact.
    answer = null;
    const detail = document.createElement("details");
    detail.style.cssText = "margin:3px 0;";
    const summary = document.createElement("summary");
    summary.textContent = "🔧 " + label;
    summary.style.cssText = "cursor:pointer;";
    const content = document.createElement("div");
    content.className = "chatui-tool-body";
    content.textContent = body || "";
    content.style.cssText = "white-space:pre-wrap;font-size:.8rem;opacity:.8;margin:3px 0 0 14px;max-height:240px;overflow:auto;";
    detail.append(summary, content);
    output.appendChild(detail);
    return detail;
  };
  view.usage = usage => {
    const line = document.createElement("div");
    line.className = "da-dim";
    line.textContent = "tokens " + (usage.context || "?")
      + (usage.window ? " / " + usage.window : "")
      + (usage.model ? " · " + usage.model : "");
    output.appendChild(line);
  };
  return view;
}

export function mountOpenClawCliRuntime(targetSel, runtime) {
  const target = typeof targetSel === "string" ? document.querySelector(targetSel) : targetSel;
  if (!target) return { mounted: false, reason: "target not found" };

  const connection = runtime.getOpenClawConnection();
  const connected = () => !!(connection.token && connection.rawUrl);
  const gateway = createGatewayRpc(runtime);
  const warmedSessions = new Set(readStringList(WARMED_STORAGE_KEY));
  const warming = new Map();
  let activeSession = DEFAULT_SESSION;

  function markWarmed(session) {
    warmedSessions.add(session);
    writeStringList(WARMED_STORAGE_KEY, [...warmedSessions]);
  }

  function warm(session) {
    if (warming.has(session)) return warming.get(session);
    if (warmedSessions.has(session) || !connected()) return Promise.resolve();
    // A quiet warm-up absorbs the launchable's first-session initialization cost.
    const pending = runtime.openclawChat("Hello", { session })
      .then(() => markWarmed(session))
      .finally(() => warming.delete(session));
    warming.set(session, pending);
    return pending;
  }

  const consoleApi = runtime.mountConsole(target, {
    prompt: "you",
    suggestions: SUGGESTIONS,
    disabled: !connected(),
    disabledMsg: localizeCourseUiText("Connect your launchable on Module 3a first (its URL and token), then your agent is reachable here."),
    greeting: connected()
      ? localizeCourseUiText("Connected to your agent over the gateway. Ask anything, type /help, click a prompt, or press Tab to autocomplete.")
      : "",
    onSubmit: async (input, consoleView, context) => {
      const message = input.trim();
      if (message === "/help" || message === "?") {
        consoleView.write(localizeCourseUiText("Use /commands for the live gateway list. /clear empties this screen; /new and /branch manage independent agent sessions. Text without a slash is sent to the active agent session."), "da-dim");
        return;
      }
      if (message === "/clear") return consoleView.clear();
      if (message === "/commands") {
        consoleView.write("commands.list ...", "da-dim");
        try {
          const result = await gateway.call("commands.list", {}, context.signal);
          const commands = result?.commands || [];
          if (!commands.length) return consoleView.write(localizeCourseUiText("No commands reported by the gateway."), "da-dim");
          commands.slice().sort((left, right) =>
            (left.category || "").localeCompare(right.category || "")
            || (left.name || "").localeCompare(right.name || "")
          ).forEach(command => {
            const alias = command.textAliases?.[0] || "/" + command.name;
            consoleView.write(alias + (command.acceptsArgs ? " <args>" : "")
              + (command.description ? "  " + command.description : ""), "da-dim");
          });
        } catch (error) {
          consoleView.write("commands.list failed: " + (error?.message || error), "da-err");
        }
        return;
      }
      if (message === "/new") return addBranch();
      if (message === "/branch" || message.startsWith("/branch ")) return handleBranch(message, consoleView);

      if (!message.startsWith("/") && !warmedSessions.has(activeSession)) {
        consoleView.write(localizeCourseUiText("setting up this session (the first reply takes a moment)…"), "da-dim");
        await warm(activeSession);
      }
      const command = message.startsWith("/");
      if (command) consoleView.write("running " + message.split(" ")[0] + " ...", "da-dim");
      const view = createArtifactView(target);
      try {
        const response = await runtime.openclawChat(input, {
          session: activeSession,
          view,
          signal: context.signal,
        });
        if (!view.streamed) consoleView.write(response || (command ? "(done)" : "(no reply)"));
      } catch (error) {
        consoleView.write(error?.message || String(error), "da-err");
        return { status: "error", message: "Agent request failed. Read the message, then retry." };
      }
      if (message === "/reset") {
        warmedSessions.delete(activeSession);
        writeStringList(WARMED_STORAGE_KEY, [...warmedSessions]);
        warm(activeSession);
      }
    },
  });

  const terminal = target.querySelector(".da-term");
  const output = target.querySelector(".da-out");
  const datalist = target.querySelector("datalist");
  let branches = [DEFAULT_SESSION, ...readStringList(STORAGE_KEY).filter(name => name !== DEFAULT_SESSION)];
  let branchNumber = 0;
  const branchLogs = Object.fromEntries(branches.map(name => [name, ""]));
  const tabBar = document.createElement("div");
  tabBar.style.cssText = "display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;";

  function saveBranches() { writeStringList(STORAGE_KEY, branches); }
  function switchBranch(name) {
    if (name === activeSession || !output) return;
    branchLogs[activeSession] = output.innerHTML;
    activeSession = name;
    output.innerHTML = branchLogs[name] || "";
    if (!branchLogs[name]) consoleApi.write("Branch '" + name + "': a fresh agent session.", "da-dim");
    renderTabs();
  }
  function addBranch() {
    do { branchNumber += 1; } while (branches.includes("branch-" + branchNumber));
    const name = "branch-" + branchNumber;
    branches.push(name);
    branchLogs[name] = "";
    saveBranches();
    switchBranch(name);
    warm(name);
  }
  async function closeBranch(name) {
    if (branches.length <= 1) return;
    // Local removal still succeeds when an older gateway lacks sessions.delete.
    try { await gateway.call("sessions.delete", { key: name }); } catch (_) {}
    branches = branches.filter(item => item !== name);
    delete branchLogs[name];
    saveBranches();
    if (activeSession === name) {
      activeSession = branches[0];
      if (output) output.innerHTML = branchLogs[activeSession] || "";
    }
    renderTabs();
  }
  function handleBranch(message, consoleView) {
    const argument = message.startsWith("/branch ") ? message.slice(8).trim() : "";
    if (!argument || argument === "new") return addBranch();
    if (argument === "list" || argument === "ls") {
      return consoleView.write("branches: " + branches.map(name => name === activeSession ? name + " (active)" : name).join(", "), "da-dim");
    }
    if (argument.startsWith("close")) {
      const name = argument.slice(5).trim() || activeSession;
      if (!branches.includes(name)) return consoleView.write("no branch named '" + name + "'", "da-err");
      if (branches.length <= 1) return consoleView.write("cannot close the last branch.", "da-err");
      return closeBranch(name);
    }
    if (!branches.includes(argument)) {
      branches.push(argument);
      branchLogs[argument] = "";
      saveBranches();
    }
    switchBranch(argument);
    warm(argument);
  }
  function renderTabs() {
    tabBar.innerHTML = "";
    branches.forEach(name => {
      const select = document.createElement("button");
      select.type = "button";
      select.className = "da-chip";
      select.textContent = name;
      select.style.fontWeight = name === activeSession ? "700" : "400";
      select.style.opacity = name === activeSession ? "1" : ".6";
      select.addEventListener("click", () => switchBranch(name));
      tabBar.appendChild(select);
      if (branches.length > 1) {
        const close = document.createElement("button");
        close.type = "button";
        close.className = "da-chip";
        close.textContent = "×";
        close.title = "close " + name;
        close.addEventListener("click", event => { event.stopPropagation(); closeBranch(name); });
        tabBar.appendChild(close);
      }
    });
    const add = document.createElement("button");
    add.type = "button";
    add.className = "da-chip";
    add.textContent = "+ branch";
    add.addEventListener("click", addBranch);
    tabBar.appendChild(add);
  }

  if (terminal && output) {
    terminal.insertBefore(tabBar, terminal.firstChild);
    renderTabs();
    if (connected()) warm(activeSession);
  }
  FALLBACK_COMMANDS.filter(command => !SUGGESTIONS.includes(command)).forEach(command => {
    if (!datalist) return;
    const option = document.createElement("option");
    option.value = command;
    datalist.appendChild(option);
  });

  if (connected()) gateway.call("commands.list").then(result => {
    // Live discovery supersedes the fallback list without making it a prerequisite.
    const commands = result?.commands || [];
    if (!(datalist && commands.length)) return;
    datalist.innerHTML = "";
    const aliases = new Set();
    commands.forEach(command => aliases.add(command.textAliases?.[0] || "/" + command.name));
    ["/clear", "/reset", "/model", "/models", "/status", "/config", "/help", "/commands"].forEach(command => aliases.add(command));
    aliases.forEach(alias => {
      const option = document.createElement("option");
      option.value = alias;
      datalist.appendChild(option);
    });
  }).catch(() => {});

  return {
    mounted: true,
    connected: connected(),
    get session() { return activeSession; },
    dispose: () => gateway.close(),
  };
}
