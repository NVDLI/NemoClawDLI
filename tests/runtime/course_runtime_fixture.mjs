// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const webRoot = path.join(root, 'web');
const isFile = file => {
  try { return fs.statSync(file).isFile(); }
  catch (_) { return false; }
};
const candidates = fs.readdirSync(webRoot, { withFileTypes:true })
  .filter(entry => entry.isDirectory())
  .map(entry => path.join(webRoot, entry.name))
  .filter(directory => [
    path.join(directory, 'scripts', '_shared.js'),
    path.join(directory, 'scripts', '_canvas.js'),
  ].every(isFile));

if (candidates.length !== 1) {
  throw new Error(`expected one helper-registry course form factor, found ${candidates.length}`);
}

const scripts = path.join(candidates[0], 'scripts');
export const sharedRuntime = await import(pathToFileURL(path.join(scripts, '_shared.js')));
export const canvasRuntime = await import(pathToFileURL(path.join(scripts, '_canvas.js')));
