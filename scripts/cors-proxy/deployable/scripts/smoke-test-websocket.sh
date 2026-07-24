#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

if [[ -z "${OPENCLAW_GATEWAY_URL:-}" ]]; then
  echo "Set OPENCLAW_GATEWAY_URL to the full HTTPS gateway URL, including any cf_access_jwt query value." >&2
  exit 64
fi

case "$OPENCLAW_GATEWAY_URL" in
  https://*|wss://*) ;;
  *)
    echo "OPENCLAW_GATEWAY_URL must use https:// or wss://." >&2
    exit 64
    ;;
esac

if [[ "$OPENCLAW_GATEWAY_URL" == *$'\n'* || "$OPENCLAW_GATEWAY_URL" == *$'\r'* || "$OPENCLAW_GATEWAY_URL" == *'"'* ]]; then
  echo "OPENCLAW_GATEWAY_URL contains unsupported characters." >&2
  exit 64
fi

http_url="${OPENCLAW_GATEWAY_URL/#wss:\/\//https://}"
origin="${OPENCLAW_BROWSER_ORIGIN:-https://course.example}"
headers_file="$(mktemp)"
trap 'rm -f "$headers_file"' EXIT

set +e
printf 'url = "%s"\n' "$http_url" | curl \
  --config - \
  --http1.1 \
  --silent \
  --show-error \
  --dump-header "$headers_file" \
  --output /dev/null \
  --max-time 5 \
  --header 'Connection: Upgrade' \
  --header 'Upgrade: websocket' \
  --header 'Sec-WebSocket-Version: 13' \
  --header 'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==' \
  --header "Origin: $origin" \
  --user-agent 'Mozilla/5.0 Chrome/136.0.0.0'
curl_status=$?
set -e

if ! grep -Eq '^HTTP/[0-9.]+ 101([[:space:]]|$)' "$headers_file"; then
  sed -n '1,20p' "$headers_file" >&2
  echo "WebSocket upgrade failed (curl exit $curl_status)." >&2
  exit 1
fi

echo "PASS: WebSocket endpoint returned 101 Switching Protocols."
