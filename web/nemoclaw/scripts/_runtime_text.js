// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Text normalization shared by live OpenClaw chat, gateway cells, and launchable terminals.

const OOM_SCORE_ADJ_NOISE = /^(?:(?:\/usr)?\/bin\/)?(?:ba|da|z)?sh:\s*(?:line\s+)?\d+:\s*cannot create \/proc\/self\/oom_score_adj:\s*Permission denied\s*$/;

export function filterOpenClawRuntimeNoise(value) {
  return String(value == null ? "" : value)
    .split(/\r?\n/)
    .filter(line => !OOM_SCORE_ADJ_NOISE.test(line.trim()))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trimEnd();
}

export function filterOpenClawRuntimeValue(value) {
  if (typeof value === "string") return filterOpenClawRuntimeNoise(value);
  if (Array.isArray(value)) return value.map(filterOpenClawRuntimeValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, filterOpenClawRuntimeValue(item)]));
  }
  return value;
}

export function openclawMessageText(message) {
  const content = message?.content;
  if (typeof content === "string") return filterOpenClawRuntimeNoise(content);
  if (!Array.isArray(content)) return "";
  return filterOpenClawRuntimeNoise(content.map(block => {
    if (typeof block === "string") return block;
    return block?.text == null ? "" : String(block.text);
  }).filter(Boolean).join("\n"));
}

export function openclawResultText(result) {
  if (result == null) return "";
  if (typeof result === "string") return filterOpenClawRuntimeNoise(result);
  if (Array.isArray(result.content)) {
    return filterOpenClawRuntimeNoise(result.content.map(block => {
      if (typeof block === "string") return block;
      return block?.text == null ? "" : String(block.text);
    }).filter(Boolean).join("\n"));
  }
  return filterOpenClawRuntimeNoise(JSON.stringify(result));
}
