#!/bin/sh
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -eu

phase=${1:-session-start}

case "$phase" in
  session-start)
    message='NemoClawDLI continuity reminder: read AGENTS.md, .codex/continuity-contract.json, and the nemoclaw-contribution skill. Reconstruct the active plan, exact identifiers, current failure, verified evidence, authority, remaining actions, and one terminal owner from retained context plus current repository and host state before changing state.'
    ;;
  pre-compact)
    message='NemoClawDLI continuity reminder before compaction: ensure retained context includes every checkpoint field from .codex/continuity-contract.json, including the original terminal condition, exact issue/branch/PR/SHAs, current failed gate and full-trace location, verified evidence, constraints, remaining actions, and terminal owner. Do not compress the objective into the latest subtask.'
    ;;
  post-compact)
    message='NemoClawDLI continuity reminder after compaction: re-read AGENTS.md and the nemoclaw-contribution skill, then reconstruct and compare the retained checkpoint with local Git and current host state before the next write. Reset exact-head evidence after any commit, policy, PR metadata, merge, or deployment change. Current artifacts and host state override the summary.'
    ;;
  *)
    message='NemoClawDLI continuity reminder: unknown hook phase. Read .codex/continuity-contract.json and reconcile the active objective before continuing.'
    ;;
esac

printf '{"systemMessage":"%s"}\n' "$message"
