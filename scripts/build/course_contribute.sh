#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

case "${1:-}" in
  doctor|fast-gate|ship-gate|build-pages) ;;
  -h|--help)
    echo 'Usage: course_contribute.sh {doctor|fast-gate|ship-gate|build-pages} [OPTIONS]'
    echo 'See docs/lab_runtime_testing.md for dependencies, options, and execution environments.'
    exit 0 ;;
  *) echo 'Select a validation mode: doctor, fast-gate, ship-gate, or build-pages' >&2; exit 2 ;;
esac

# Orchestrate a contributor-selected executor without evaluating shell strings.
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
if [[ -n "${COURSE_CONTRIBUTE_RUNNER:-}" ]]; then
  runner=$COURSE_CONTRIBUTE_RUNNER
  if [[ "$runner" != /* || ! -f "$runner" || ! -x "$runner" || "$runner" -ef "${BASH_SOURCE[0]}" ]]; then
    echo 'COURSE_CONTRIBUTE_RUNNER must name a separate absolute executable file' >&2
    exit 2
  fi
  unset COURSE_CONTRIBUTE_RUNNER
  exec "$runner" --repo "$root" "$@"
fi
if [[ $(uname -s) != Linux ]]; then
  echo 'Run these checks in Linux, or set COURSE_CONTRIBUTE_RUNNER to an authorized executor. See docs/lab_runtime_testing.md.' >&2
  exit 2
fi
exec python3 "$root/scripts/build/course_contribute.py" --repo "$root" "$@"
