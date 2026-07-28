// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import cf from 'cloudfront';

var OPENCLAW_PATH = /^\/https\/([^/?#]+)(\/.*)?$/i;

function failure(statusCode, message, origin) {
  return {
    statusCode: statusCode,
    statusDescription: statusCode === 403 ? 'Forbidden' : 'Bad Request',
    headers: {
      'content-type': { value: 'application/json; charset=utf-8' },
      'cache-control': { value: 'no-store' },
      'access-control-allow-origin': { value: origin || '*' },
      'access-control-allow-methods': { value: 'GET, OPTIONS' },
      'access-control-allow-headers': { value: 'CF-Access-Jwt-Assertion, X-OpenClaw-Access-Provider, X-OpenClaw-Access-Session' },
      'vary': { value: 'Origin' }
    },
    body: JSON.stringify({ error: message })
  };
}

function oneValue(field) {
  if (!field) return '';
  if (field.multiValue && field.multiValue.length > 1) return null;
  return String(field.value || '');
}

function handler(event) {
  var request = event.request;
  var headers = request.headers || {};
  var origin = headers.origin ? headers.origin.value : '*';
  // CloudFront may omit viewer WebSocket handshake headers from a Function
  // event even though it forwards them to the origin. Enforce GET here and
  // reject a contradictory Upgrade value when one is visible; the allowlisted
  // upstream endpoint remains responsible for completing the 101 handshake.
  var upgrade = oneValue(headers.upgrade);
  if (request.method !== 'GET' || upgrade === null ||
      (upgrade && String(upgrade).toLowerCase() !== 'websocket')) {
    return failure(400, 'WebSocket upgrade required.', origin);
  }

  var match = OPENCLAW_PATH.exec(request.uri || '');
  var upstreamPath = match ? String(match[2] || '') : '';
  var supportedPath = upstreamPath.endsWith('/cli/gateway') ||
    upstreamPath.endsWith('/ws/terminal');
  if (!match || !supportedPath) {
    return failure(400, 'Use /https/<host>/cli/gateway or /https/<host>/ws/terminal.', origin);
  }

  var host = String(match[1] || '').toLowerCase();
  var cloudflareHost = host.length <= 253 &&
    /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*brevlab\.com$/.test(host);
  var pomeriumHost = host.length <= 253 &&
    /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*apps\.run\.brev\.nvidia\.com$/.test(host);
  if (!cloudflareHost && !pomeriumHost) return failure(403, 'Upstream host is not on the allowlist.', origin);
  var expectedProvider = pomeriumHost ? 'pomerium' : 'cloudflare';

  var query = request.querystring || {};
  var queryProvider = oneValue(query.access_provider);
  var headerProvider = oneValue(headers['x-openclaw-access-provider']);
  var headerSession = oneValue(headers['x-openclaw-access-session']);
  var querySession = oneValue(query.access_session);
  var legacyHeaderSession = oneValue(headers['cf-access-jwt-assertion']);
  var legacyQuerySession = oneValue(query.cf_access_jwt);
  if ([queryProvider, headerProvider, headerSession, querySession, legacyHeaderSession, legacyQuerySession].some(function (value) { return value === null; })) {
    return failure(400, 'Ambiguous access session.', origin);
  }
  if (queryProvider && headerProvider && String(queryProvider).toLowerCase() !== String(headerProvider).toLowerCase()) {
    return failure(400, 'Conflicting access providers.', origin);
  }
  var requestedProvider = queryProvider || headerProvider;
  requestedProvider = String(requestedProvider || '').toLowerCase();
  if (requestedProvider && requestedProvider !== 'cloudflare' && requestedProvider !== 'pomerium') {
    return failure(400, 'Unsupported access provider.', origin);
  }
  if (requestedProvider && requestedProvider !== expectedProvider) {
    return failure(400, 'Access provider does not match the upstream host.', origin);
  }
  var neutralSession = headerSession || querySession || '';
  var legacySession = legacyHeaderSession || legacyQuerySession || '';
  if (neutralSession && !requestedProvider) {
    return failure(400, 'Neutral access sessions require an explicit access provider.', origin);
  }
  if (legacySession && expectedProvider !== 'cloudflare') {
    return failure(400, 'Cloudflare access assertions are valid only for Cloudflare launchables.', origin);
  }
  if (headerSession && querySession && headerSession !== querySession) {
    return failure(400, 'Conflicting access sessions.', origin);
  }
  if (legacyHeaderSession && legacyQuerySession && legacyHeaderSession !== legacyQuerySession) {
    return failure(400, 'Conflicting access sessions.', origin);
  }
  if (neutralSession && legacySession && neutralSession !== legacySession) {
    return failure(400, 'Conflicting access sessions.', origin);
  }
  var accessSession = neutralSession || legacySession;
  if (accessSession.length > 8192) return failure(400, 'Access session is too large.', origin);
  if (accessSession && !/^[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*$/.test(accessSession)) {
    return failure(400, 'Access session contains invalid cookie characters.', origin);
  }

  delete headers['cf-access-jwt-assertion'];
  delete headers['x-openclaw-access-provider'];
  delete headers['x-openclaw-access-session'];
  delete headers['x-pomerium-authorization'];
  delete headers['cf-access-client-id'];
  delete headers['cf-access-client-secret'];
  delete query.cf_access_jwt;
  delete query.access_provider;
  delete query.access_session;
  request.cookies = {};
  if (accessSession && expectedProvider === 'cloudflare') request.cookies.CF_Authorization = { value: accessSession };
  if (accessSession && expectedProvider === 'pomerium') {
    request.cookies._pomerium = { value: accessSession };
  }

  request.uri = upstreamPath;
  request.headers.origin = { value: 'http://localhost:8088' };
  cf.updateRequestOrigin({
    domainName: host,
    hostHeader: host,
    sni: host,
    allowedCertificateNames: pomeriumHost
      ? ['apps.run.brev.nvidia.com', '*.apps.run.brev.nvidia.com']
      : ['brevlab.com', '*.brevlab.com'],
    customOriginConfig: {
      port: 443,
      protocol: 'https',
      sslProtocols: ['TLSv1.2']
    }
  });
  return request;
}
