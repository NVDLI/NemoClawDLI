#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 https://proxy.example/path [origin]" >&2
  exit 64
fi

BASE_URL="$1"
ORIGIN="${2:-https://example-course.local}"

echo "== CORS preflight =="
curl -i -X OPTIONS "$BASE_URL" \
  -H "Origin: $ORIGIN" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Authorization, Content-Type, x-openclaw-session-key, CF-Access-Jwt-Assertion"

echo
echo "== GET smoke =="
curl -i "$BASE_URL" -H "Origin: $ORIGIN" --max-time 30

echo
echo "== Streaming smoke (prints headers immediately, then streams body) =="
curl -N -i "$BASE_URL" -H "Origin: $ORIGIN" --max-time 60
