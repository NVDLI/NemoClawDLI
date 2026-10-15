#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
have() { command -v "$1" >/dev/null 2>&1; }
node_path=${NODE_PATH:-$ROOT/scripts/runtime/node_modules}
node_bin=${NODE_BIN:-}
if [[ -z "$node_bin" ]] && have node; then node_bin=$(command -v node); fi
chrome_bin=""
if [[ -n "$node_bin" && -x "$node_bin" && -f "$node_path/playwright-core/package.json" ]]; then
  chrome_bin=$(NODE_PATH="$node_path" "$node_bin" "$ROOT/scripts/runtime/browser_environment.cjs" --chrome) || exit 2
fi

echo "browser_env_probe"
echo "  repo: $ROOT"
echo "  host node: $([[ -n "$node_bin" && -x "$node_bin" ]] && echo yes || echo no)"
echo "  playwright-core: $([[ -f "$node_path/playwright-core/package.json" ]] && echo yes || echo no)"
echo "  chromium/chrome: $([[ -n "$chrome_bin" ]] && echo yes || echo no)"
echo

if [[ -z "$node_bin" || ! -x "$node_bin" ]]; then echo "FAIL: install Node.js 20+ or set NODE_BIN" >&2; exit 2; fi
if [[ ! -f "$node_path/playwright-core/package.json" ]]; then
  echo "FAIL: run (cd scripts/runtime && corepack enable && pnpm install --frozen-lockfile --ignore-scripts)" >&2
  exit 2
fi
if [[ -z "$chrome_bin" ]]; then
  echo "FAIL: install Chromium/Chrome or set CHROME_BIN" >&2
  exit 2
fi

NODE_PATH="$node_path" CHROME_BIN="$chrome_bin" "$ROOT/scripts/runtime/browser_runtime_test.sh" --smoke

cat <<EOF

NEXT:
  browser render:
    scripts/runtime/browser_runtime_test.sh --render-only

  optional isolation:
    place Node.js, playwright-core, Chromium, and this read-only checkout in a
    container definition maintained outside this repository, then invoke the
    same test_page_runtime.js command.
EOF
