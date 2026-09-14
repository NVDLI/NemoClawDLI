// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import fs from 'node:fs';
import path from 'node:path';
import { createRequire, isBuiltin } from 'node:module';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(path.join(root, 'scripts/browser-vendor/package.json'));
const { build, version } = require('esbuild');
const expected = JSON.parse(fs.readFileSync(path.join(root, 'scripts/browser-vendor/package.json'), 'utf8')).devDependencies.esbuild;
if (version !== expected) throw new Error(`module linkage requires esbuild ${expected}; found ${version}`);
const entries = JSON.parse(fs.readFileSync(0, 'utf8'));
const findings = [];
let modules = 0;
const external = new Set();

const packageOwners = new Map();
function runtimePackageOwner(importer, specifier) {
  let directory = path.dirname(importer);
  while (true) {
    const manifest = path.join(directory, 'package.json');
    if (fs.existsSync(manifest)) {
      if (!packageOwners.has(manifest)) {
        const metadata = JSON.parse(fs.readFileSync(manifest, 'utf8'));
        for (const field of ['dependencies', 'optionalDependencies']) {
          if (metadata[field] !== undefined && (!metadata[field] || typeof metadata[field] !== 'object'
              || Array.isArray(metadata[field]) || Object.values(metadata[field]).some(value => typeof value !== 'string' || !value))) {
            throw new Error(`Invalid ${field} in owning package manifest: ${manifest}`);
          }
        }
        packageOwners.set(manifest, {...metadata.dependencies, ...metadata.optionalDependencies});
      }
      // A declaration proves the package root, not its exports or arbitrary subpaths.
      return Object.hasOwn(packageOwners.get(manifest), specifier) ? manifest : null;
    }
    const parent = path.dirname(directory);
    if (parent === directory) return null;
    directory = parent;
  }
}

function describe(entry, message) {
  const at = message.location;
  return `${at?.file || entry.file}:${at?.line || 1}:${at?.column || 0}: ${message.text}`;
}

for (const entry of entries) {
  const options = {
    stdin: { contents: entry.source, sourcefile: entry.file, resolveDir: path.dirname(entry.file), loader: 'js' },
    absWorkingDir: root, write: false, metafile: true, logLevel: 'silent',
    platform: 'browser', treeShaking: false,
  };
  try {
    const parsed = await build({ ...options, bundle: false });
    for (const warning of parsed.warnings) findings.push(describe(entry, warning));
    const isModule = entry.module || Object.values(parsed.metafile.inputs).some(input => input.format === 'esm')
      || Object.values(parsed.metafile.outputs).some(output => output.imports.length);
    if (!isModule) continue;
    modules++;
    const linked = await build({ ...options, format: 'esm', bundle: true, plugins: [{
      name: 'remote-browser-imports', setup(builder) {
        builder.onResolve({ filter: /.*/ }, args => {
          if (!['dynamic-import', 'require-call', 'require-resolve'].includes(args.kind)) return;
          if (isBuiltin(args.path)) {
            external.add(`${args.importer || entry.file}: ${args.kind} ${args.path} (Node runtime required)`);
            return { path: args.path, external: true };
          }
          if (/^(?:\.{1,2}\/|\/|[a-z][a-z0-9+.-]*:)/i.test(args.path)) return;
          const owner = runtimePackageOwner(args.importer || entry.file, args.path);
          if (owner) {
            external.add(`${args.importer || entry.file}: ${args.kind} ${args.path} (declared by ${owner}; runtime environment required)`);
            return { path: args.path, external: true };
          }
        });
        builder.onResolve({ filter: /^(?:https?:|data:|blob:)/ }, args => {
          external.add(`${entry.file}: ${args.path}`);
          return { path: args.path, external: true };
        });
      },
    }] });
    for (const warning of linked.warnings) findings.push(describe(entry, warning));
  } catch (error) {
    if (!Array.isArray(error.errors)) throw error;
    for (const message of error.errors) findings.push(describe(entry, message));
  }
}
process.stdout.write(JSON.stringify({ findings: [...new Set(findings)], modules, external: [...external].sort() }));
