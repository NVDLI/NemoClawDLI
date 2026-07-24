#!/usr/bin/env bash
# Run a repo node script headless against the REAL host tree (CI + python shims).
# Resolution, each running the script against THIS repo's files:
#   1. explicit NODE_BIN, including a Windows node.exe reached from WSL.
#   2. host `node` on PATH.
#   3. fail with an explicit host installation recommendation.
# Fails LOUD if none reachable. Usage: run_node.sh <script> [args...]  (script abs or repo-relative)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
SCRIPT="${1:?usage: run_node.sh <script> [args...]}"; shift
case "$SCRIPT" in /*) ABS="$SCRIPT";; *) ABS="$REPO/$SCRIPT";; esac
REL="${ABS#"$REPO"/}"

if [ -n "${NODE_BIN:-}" ]; then
  if [ ! -x "$NODE_BIN" ]; then
    echo "run_node: NODE_BIN is not executable: $NODE_BIN" >&2
    exit 2
  fi
  case "$NODE_BIN" in
    *.exe)
      if ! command -v wslpath >/dev/null 2>&1; then
        echo "run_node: NODE_BIN points to node.exe but wslpath is unavailable." >&2
        exit 2
      fi
      exec "$NODE_BIN" "$(wslpath -w "$ABS")" "$@"
      ;;
    *) exec "$NODE_BIN" "$ABS" "$@" ;;
  esac
fi

if command -v node >/dev/null 2>&1; then
  exec node "$ABS" "$@"
fi

echo "run_node: no host Node.js found. Install Node.js 20+ or set NODE_BIN." >&2
exit 2
