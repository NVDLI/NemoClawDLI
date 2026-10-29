#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Point the launchable's onboarded agent at Nebius Token Factory, or back to NVIDIA Build.
# This calls canonical `nemoclaw inference set`; NemoClaw registers the compatible endpoint,
# verifies a request from the sandbox, and rolls back on failure. Run it as the user who
# onboarded the sandbox, not as root, so NemoClaw reads that user's registry.
#
#   NEBIUS_API_KEY=... bash scripts/brev/provider.sh nebius [--model ID] [--sandbox NAME]
#   bash scripts/brev/provider.sh build [--model ID] [--sandbox NAME]
#   bash scripts/brev/provider.sh status

set -euo pipefail

readonly NEBIUS_ENDPOINT="https://api.tokenfactory.nebius.com/v1"
# Super VL keeps tool calls reliable with reasoning on or off; Lightning does not.
readonly NEBIUS_MODEL="nvidia/Nemotron-3.5-Super-VL"
readonly BUILD_MODEL="nvidia/nemotron-3.5-super-vl-120b-a12b"
readonly GATEWAY_ENV="/etc/nemoclaw/gateway-management.env"

fail() {
  echo "nemoclaw-dli provider: $*" >&2
  exit 1
}

[ "$(id -u)" -ne 0 ] || fail "run as the onboarding user, not root"
command -v nemoclaw >/dev/null 2>&1 || fail "nemoclaw CLI is not installed"

# Non-login shells may lack the image's declared gateway; load it the way brev-quickstart does.
if [ -z "${NEMOCLAW_GATEWAY_MANAGEMENT:-}" ] && [ -r "$GATEWAY_ENV" ]; then
  set -a
  # shellcheck disable=SC1090 # The image owns this fixed, secret-free environment file.
  . "$GATEWAY_ENV"
  set +a
fi

action="${1:-}"
shift || true
model=""
sandbox=""
sandbox_args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --model) model="${2:?--model needs a value}"; shift 2 ;;
    --sandbox) sandbox="${2:?--sandbox needs a value}"; sandbox_args=(--sandbox "$sandbox"); shift 2 ;;
    *) fail "unknown option: $1" ;;
  esac
done

case "$action" in
  nebius)
    nemoclaw inference set --help 2>&1 | grep -q -- "--endpoint-url" \
      || fail "this NemoClaw release cannot register a compatible endpoint; update the launchable image"
    key="${NEBIUS_API_KEY:-}"
    if [ -z "$key" ] && [ -t 0 ]; then
      read -r -s -p "Nebius Token Factory API key: " key
      echo
    fi
    [ -n "$key" ] || fail "set NEBIUS_API_KEY or run interactively"
    # The key reaches NemoClaw through the environment only, never argv.
    COMPATIBLE_API_KEY="$key" nemoclaw inference set \
      --provider custom \
      --endpoint-url "$NEBIUS_ENDPOINT" \
      --credential-env COMPATIBLE_API_KEY \
      --inference-api openai-completions \
      --model "${model:-$NEBIUS_MODEL}" \
      ${sandbox_args[@]+"${sandbox_args[@]}"}
    ;;
  build)
    nemoclaw inference set --provider build --model "${model:-$BUILD_MODEL}" \
      ${sandbox_args[@]+"${sandbox_args[@]}"}
    ;;
  status)
    # `inference get` reads the default sandbox; the named form reads another one.
    if [ -n "$sandbox" ]; then nemoclaw "$sandbox" inference get; else nemoclaw inference get; fi
    ;;
  *)
    fail "usage: provider.sh nebius|build|status [--model ID] [--sandbox NAME]"
    ;;
esac
