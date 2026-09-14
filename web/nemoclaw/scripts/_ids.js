// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export function randomId(prefix = "") {
  /* @doc <code>helpers.randomId(prefix?)</code> ::
       Create a cryptographically random UUID v4, optionally prefixed for a session or artifact.
       Uses getRandomValues, which is available on plain HTTP lab origins. */
  const crypto = globalThis.crypto;
  if (typeof crypto?.getRandomValues !== "function") {
    throw new Error("Cryptographic random values are unavailable in this browser.");
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map(value => value.toString(16).padStart(2, "0")).join("");
  return prefix + [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join("-");
}
