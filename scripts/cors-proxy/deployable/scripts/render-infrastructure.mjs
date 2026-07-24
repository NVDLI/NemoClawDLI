// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { existsSync } from 'node:fs';

// A mounted course workspace may resolve to a host-only path through getcwd().
// Prefer the explicit override and the course container's logical mount, then
// support execution from either the repository root or this package root.
const candidates = [
  process.env.CORS_PROXY_SOURCE_ROOT,
  '/workspace/scripts/cors-proxy/deployable',
  process.env.PWD,
  process.cwd(),
].filter(Boolean).flatMap((candidate) => [
  resolve(candidate),
  resolve(candidate, 'scripts/cors-proxy/deployable'),
]);
const root = candidates.find((candidate) =>
  existsSync(resolve(candidate, 'infrastructure/template.json')));
if (!root) throw new Error('Cannot locate the deployable relay source root');
const templatePath = resolve(root, 'infrastructure/template.json');
const functionPath = resolve(root, 'src/openclaw-websocket-request.js');
const outputPath = resolve(
  process.env.CORS_PROXY_INFRASTRUCTURE_OUTPUT || resolve(root, 'build/infrastructure.json'),
);
const marker = '__OPENCLAW_WEBSOCKET_FUNCTION_CODE__';

export function renderInfrastructure(templateText, functionCode) {
  const template = JSON.parse(templateText);
  const resource = template?.Resources?.RuntimeWebSocketRequest;
  if (resource?.Properties?.FunctionCode !== marker) {
    throw new Error('Infrastructure template has no exact WebSocket source marker');
  }
  resource.Properties.FunctionCode = functionCode;
  return JSON.stringify(template, null, 2) + '\n';
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [templateText, functionCode] = await Promise.all([
    readFile(templatePath, 'utf8'),
    readFile(functionPath, 'utf8'),
  ]);
  await mkdir(dirname(outputPath), { recursive: true });
  await writeFile(outputPath, renderInfrastructure(templateText, functionCode), 'utf8');
  console.log(outputPath);
}
