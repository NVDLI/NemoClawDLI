#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source "$root/scripts/ci/publisher_binary_guard.sh"
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
binary="$fixture/root-owned"
: > "$binary"

make_stat() {
  local target=$1
  local body=$2
  {
    printf '%s\n' '#!/usr/bin/env bash' 'set -euo pipefail'
    printf '%s\n' "$body"
  } > "$target"
  chmod +x "$target"
}

make_stat "$fixture/stat-gnu" '
if [[ "${1:-}" == "--version" ]]; then echo "stat (GNU coreutils) 9.1"; exit 0; fi
if [[ "${1:-}" == "-c" && "${2:-}" == "%u" ]]; then echo 0; exit 0; fi
exit 1'
[[ $(dli_binary_owner_uid "$binary" "$fixture/stat-gnu") == 0 ]]

make_stat "$fixture/stat-bsd" '
if [[ "${1:-}" == "--version" ]]; then exit 1; fi
if [[ "${1:-}" == "-f" && "${2:-}" == "%u" ]]; then echo 0; exit 0; fi
exit 1'
[[ $(dli_binary_owner_uid "$binary" "$fixture/stat-bsd") == 0 ]]

make_stat "$fixture/stat-gnu-false-success" '
if [[ "${1:-}" == "--version" ]]; then exit 1; fi
if [[ "${1:-}" == "-f" && "${2:-}" == "%u" ]]; then echo "%u"; exit 0; fi
exit 1'
if dli_binary_owner_uid "$binary" "$fixture/stat-gnu-false-success" >/dev/null; then
  echo "GNU stat -f false-success was accepted" >&2
  exit 1
fi

make_stat "$fixture/stat-nonroot" '
if [[ "${1:-}" == "--version" ]]; then echo "stat (GNU coreutils) 9.1"; exit 0; fi
if [[ "${1:-}" == "-c" && "${2:-}" == "%u" ]]; then echo 1000; exit 0; fi
exit 1'
if dli_require_root_binary "$binary" "$fixture/stat-nonroot"; then
  echo "non-root ownership was accepted" >&2
  exit 1
fi

echo "publisher binary guard: PASS"
