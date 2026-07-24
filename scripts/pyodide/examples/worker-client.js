// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const DEFAULT_TIMEOUT_MS = 15_000;

export class PythonRunner {
  constructor(workerUrl, { timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
    this.workerUrl = workerUrl;
    this.timeoutMs = timeoutMs;
    this.nextId = 1;
    this.pending = new Map();
    this.reset();
  }

  reset() {
    this.worker?.terminate();
    for (const request of this.pending.values()) {
      request.reject(new Error("Python runtime reset."));
      clearTimeout(request.timer);
    }
    this.pending.clear();
    this.worker = new Worker(this.workerUrl, { type: "module" });
    this.worker.addEventListener("message", ({ data }) => this.finish(data));
    this.worker.addEventListener("error", (event) => this.failAll(event.message));
  }

  request(message) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        this.reset();
        reject(new Error(`Python stopped after ${this.timeoutMs} ms.`));
      }, this.timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      this.worker.postMessage({ id, ...message });
    });
  }

  preload(profile = "core") {
    return this.request({ type: "preload", profile });
  }

  run(source, { inputs = {}, profile = "core" } = {}) {
    return this.request({ type: "run", source, inputs, profile });
  }

  stop() {
    this.failAll("Python execution stopped.");
    this.reset();
  }

  finish(reply) {
    const request = this.pending.get(reply.id);
    if (!request) return;
    clearTimeout(request.timer);
    this.pending.delete(reply.id);
    request.resolve(reply);
  }

  failAll(message) {
    for (const request of this.pending.values()) {
      clearTimeout(request.timer);
      request.reject(new Error(message));
    }
    this.pending.clear();
  }
}
