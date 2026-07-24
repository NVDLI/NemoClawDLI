// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import http from 'node:http';
import { Readable } from 'node:stream';
import { pipeline } from 'node:stream/promises';
import { filteredRequestHeaders, filteredResponseHeaders } from '../src/proxy.mjs';

const upstream = http.createServer((req, res) => {
  res.writeHead(200, {
    'content-type': 'text/event-stream',
    'cache-control': 'no-cache',
  });
  let count = 0;
  const interval = setInterval(() => {
    count += 1;
    res.write(`data: chunk-${count}\n\n`);
    if (count === 3) {
      clearInterval(interval);
      res.end();
    }
  }, 250);
});

await new Promise((resolve) => upstream.listen(0, '127.0.0.1', resolve));
const upstreamPort = upstream.address().port;
process.env.UPSTREAM_ORIGIN = `http://127.0.0.1:${upstreamPort}`;
const localStreamUrl = new URL('/stream', `http://127.0.0.1:${upstreamPort}`);

const proxy = http.createServer(async (req, res) => {
  const upstreamResponse = await fetch(localStreamUrl, {
    method: req.method,
    headers: filteredRequestHeaders(req.headers),
    body: ['GET', 'HEAD'].includes(req.method) ? undefined : req,
    duplex: 'half',
  });
  const headers = filteredResponseHeaders(upstreamResponse.headers, req.headers.origin || '*');
  res.writeHead(upstreamResponse.status, Object.fromEntries(headers.entries()));
  await pipeline(Readable.fromWeb(upstreamResponse.body), res);
});

await new Promise((resolve) => proxy.listen(0, '127.0.0.1', resolve));
const proxyPort = proxy.address().port;
console.log(`Local streaming proxy: http://127.0.0.1:${proxyPort}/stream`);
console.log('Try: curl -N -H "Origin: https://course.example" http://127.0.0.1:' + proxyPort + '/stream');

process.on('SIGINT', () => {
  proxy.close();
  upstream.close();
  process.exit(0);
});
