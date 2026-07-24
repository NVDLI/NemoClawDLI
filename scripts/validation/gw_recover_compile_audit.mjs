#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import fs from 'node:fs';

const src = fs.readFileSync('web/nemoclaw/scripts/_openclaw.js', 'utf8');
const gwMatch = src.match(/export const GW_CONNECT = `([\s\S]*?)`;\n/);
if (!gwMatch) throw new Error('GW_CONNECT not found');
const quoteTemplate = value => value.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$\{/g, '\\${');
const gw = Function('return `' + quoteTemplate(gwMatch[1]) + '`')();
const cellBodies = [gw];
const re = /code:\s*GW_CONNECT\s*\+\s*`([\s\S]*?)`/g;
let m;
while ((m = re.exec(src))) cellBodies.push(gw + Function('return `' + quoteTemplate(m[1]) + '`')());
if (cellBodies.length < 4) throw new Error(`expected GW_CONNECT plus recover cells, saw ${cellBodies.length}`);
for (let i = 0; i < cellBodies.length; i++) {
  const code = cellBodies[i];
  if (/_uniqueId\s*\(/.test(code)) throw new Error(`cell ${i} references private _uniqueId`);
  new Function('state', 'helpers', 'h', 'console', '"use strict"; return (async () => {\n' + code + '\n})();');
}
console.log('gw recover compile audit: ok');
