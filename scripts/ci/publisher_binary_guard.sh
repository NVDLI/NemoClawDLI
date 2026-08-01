#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

dli_binary_owner_uid() {
  local binary=$1
  local stat_bin=${2:-}
  local dialect uid
  if [[ -z "$stat_bin" ]]; then
    stat_bin=$(command -v stat) || return 1
  fi

  if "$stat_bin" --version 2>/dev/null | head -n 1 | grep -q 'GNU coreutils'; then
    dialect=gnu
  elif uid=$("$stat_bin" -f '%u' "$binary" 2>/dev/null) && [[ "$uid" =~ ^[0-9]+$ ]]; then
    dialect=bsd
  else
    return 1
  fi

  if [[ "$dialect" == gnu ]]; then
    uid=$("$stat_bin" -c '%u' "$binary" 2>/dev/null) || return 1
  else
    uid=$("$stat_bin" -f '%u' "$binary" 2>/dev/null) || return 1
  fi
  [[ "$uid" =~ ^[0-9]+$ ]] || return 1
  printf '%s\n' "$uid"
}

dli_require_root_binary() {
  local binary=$1
  local stat_bin=${2:-}
  local uid
  [[ "$binary" = /* && -f "$binary" && ! -L "$binary" ]] || return 1
  uid=$(dli_binary_owner_uid "$binary" "$stat_bin") || return 1
  [[ "$uid" == 0 ]]
}
