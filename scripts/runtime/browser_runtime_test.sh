#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Run the browser harness with host Node.js, the pinned playwright-core API, and
# a contributor-installed Chromium/Chrome binary. Containerization is optional
# and belongs to the contributor or CI operator, not this repository.
# Live OpenClaw checks inherit CLAW_ACCESS_PROVIDER, CLAW_ACCESS_SESSION, and
# OPENCLAW_CORS_PROXY_BASE from the host process; the wrapper never persists them.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
NODE_BIN=${NODE_BIN:-$(command -v node || true)}
NODE_PATH=${NODE_PATH:-$ROOT/scripts/runtime/node_modules}

find_chrome() {
  if [[ -n "${CHROME_BIN:-}" && -x "$CHROME_BIN" ]]; then printf '%s\n' "$CHROME_BIN"; return; fi
  local candidate
  for candidate in \
    "$(command -v chromium 2>/dev/null || true)" \
    "$(command -v chromium-browser 2>/dev/null || true)" \
    "$(command -v google-chrome 2>/dev/null || true)" \
    "$(command -v google-chrome-stable 2>/dev/null || true)" \
    "/Applications/Chromium.app/Contents/MacOS/Chromium" \
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"; do
    if [[ -n "$candidate" && -x "$candidate" ]]; then printf '%s\n' "$candidate"; return; fi
  done
  return 1
}

if [[ -z "$NODE_BIN" || ! -x "$NODE_BIN" ]]; then
  echo "browser runtime: Node.js 20+ is required; install Node.js or set NODE_BIN" >&2
  exit 2
fi
if [[ ! -f "$NODE_PATH/playwright-core/package.json" ]]; then
  echo "browser runtime: playwright-core is missing" >&2
  echo "run: (cd scripts/runtime && corepack enable && pnpm install --frozen-lockfile --ignore-scripts)" >&2
  exit 2
fi
CHROME_BIN=$(find_chrome) || {
  echo "browser runtime: Chromium or a compatible Chrome binary is required" >&2
  echo "install Chromium/Chrome for your OS, or set CHROME_BIN to its executable" >&2
  exit 2
}
export NODE_PATH CHROME_BIN COURSE_ROOT="$ROOT"

args=("$@")
gateway_only=0
cron_contract=0
terminal_contract=0
chat_contract=0
assistant_artifacts=0
for arg in "${args[@]}"; do
  case "$arg" in
    --gateway-only) gateway_only=1 ;;
    --cron-contract) cron_contract=1 ;;
    --terminal-contract) terminal_contract=1 ;;
    --chat-contract) chat_contract=1 ;;
    --assistant-artifacts) assistant_artifacts=1 ;;
  esac
done
if (( cron_contract && ! gateway_only )); then echo "--cron-contract requires --gateway-only" >&2; exit 2; fi
if (( terminal_contract && ! gateway_only )); then echo "--terminal-contract requires --gateway-only" >&2; exit 2; fi
if (( chat_contract && ! gateway_only )); then echo "--chat-contract requires --gateway-only" >&2; exit 2; fi
if (( assistant_artifacts )) && [[ -z "${NVIDIA_API_KEY:-}" ]]; then
  echo "--assistant-artifacts requires NVIDIA_API_KEY" >&2
  exit 2
fi
if [[ " ${args[*]} " != *" --smoke "* && " ${args[*]} " != *" --serve-static "* ]]; then
  args+=(--serve-static)
fi
if [[ ${#args[@]} -eq 0 ]]; then
  args=(--render-only --serve-static http://127.0.0.1:4173/nemoclaw/01a-loop.html)
fi

exec "$NODE_BIN" "$ROOT/scripts/runtime/test_page_runtime.js" "${args[@]}"
