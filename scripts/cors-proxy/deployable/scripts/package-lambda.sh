#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build/lambda"
ZIP_PATH="$ROOT_DIR/build/cors-proxy-build-nvidia.zip"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR" "$(dirname "$ZIP_PATH")"
cp "$ROOT_DIR"/src/*.mjs "$BUILD_DIR/"

(
  cd "$BUILD_DIR"
  zip -qr "$ZIP_PATH" .
)

echo "$ZIP_PATH"
