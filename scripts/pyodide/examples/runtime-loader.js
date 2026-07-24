// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const RUNTIME = Object.freeze({
  pyodide: "0.27.7",
  python: "3.12.7",
  assetRoot: "assets/pyodide/0.27.7/",
});

let runtimePromise;

export function runtimeInfo() {
  return RUNTIME;
}

export function loadRuntime() {
  if (!runtimePromise) {
    runtimePromise = (async () => {
      const baseUrl = new URL(RUNTIME.assetRoot, self.location.href).href;
      const module = await import(`${baseUrl}pyodide.mjs`);
      return module.loadPyodide({ indexURL: baseUrl });
    })();
  }
  return runtimePromise;
}
