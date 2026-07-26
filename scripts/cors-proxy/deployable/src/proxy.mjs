// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

const UPSTREAM_ORIGIN = 'https://build.nvidia.com';
const MODEL_UPSTREAM_HOSTS = new Set(['integrate.api.nvidia.com', 'build.nvidia.com']);

const ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS', 'HEAD'];
const DEFAULT_ALLOWED_HEADERS = [
  'Authorization',
  'Content-Type',
  'x-openclaw-session-key',
  // billing attribution from the DLI web clients (value e.g. dli-nemoclaw-web)
  'X-BILLING-INVOKE-ORIGIN',
  'Accept',
  'CF-Access-Jwt-Assertion',
  'X-OpenClaw-Access-Provider',
  'X-OpenClaw-Access-Session',
];

const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);
const RETIRED_BILLING_HEADER = ['x-billing', 'source'].join('-');

// CloudFront adds this operator secret so the Function URL can refuse direct
// callers. It authenticates the edge to this relay only, so it must never
// continue to an upstream origin.
const EDGE_SECRET_HEADER = 'x-dli-cors-proxy-secret';

const REQUEST_HEADERS_TO_STRIP = new Set([
  ...HOP_BY_HOP_HEADERS,
  'host',
  'content-length',
  'cookie',
  EDGE_SECRET_HEADER,
  'cf-connecting-ip',
  'cf-ipcountry',
  'cf-ray',
  'cf-visitor',
  'cf-access-client-id',
  'cf-access-client-secret',
  'cf-access-jwt-assertion',
  'x-openclaw-access-provider',
  'x-openclaw-access-session',
  'x-billing-invoke-origin',
  RETIRED_BILLING_HEADER,
  'x-pomerium-authorization',
  'x-forwarded-for',
  'x-forwarded-host',
  'x-forwarded-proto',
]);

const RESPONSE_HEADERS_TO_STRIP = new Set([
  ...HOP_BY_HOP_HEADERS,
  'access-control-allow-origin',
  'access-control-allow-methods',
  'access-control-allow-headers',
  'access-control-allow-credentials',
  'access-control-max-age',
  'set-cookie',
  'set-cookie2',
  'content-encoding',
  'content-length',
]);

const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);
const REDIRECT_BODY_HEADERS = ['content-encoding', 'content-language', 'content-location', 'content-type', 'content-length'];
const COOKIE_VALUE = /^[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]*$/;
const BILLING_INVOKE_ORIGIN = /^dli-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/;

export function getUpstreamOrigin() {
  return process.env.UPSTREAM_ORIGIN || UPSTREAM_ORIGIN;
}

export function getAllowedHeaders() {
  const configured = process.env.CORS_ALLOWED_HEADERS;
  return configured
    ? configured.split(',').map((header) => header.trim()).filter(Boolean)
    : DEFAULT_ALLOWED_HEADERS;
}

// PROXY_MODE selects how the upstream target is resolved:
//   'single-host'        forward every path to the one pinned UPSTREAM_ORIGIN (default).
//   'multihost-allowlist' accept the legacy /https/<host>/<path> form, but ONLY for hosts
//                         on UPSTREAM_HOST_ALLOWLIST. This is NOT an open relay: any host
//                         not on the allowlist is rejected with 403.
export function getProxyMode() {
  return process.env.PROXY_MODE === 'multihost-allowlist' ? 'multihost-allowlist' : 'single-host';
}

export function getHostAllowlist() {
  return (process.env.UPSTREAM_HOST_ALLOWLIST || '')
    .split(',').map((h) => h.trim().toLowerCase()).filter(Boolean);
}

// An entry beginning with '.' is a domain-suffix match (".brevlab.com" matches
// "nemoclaw-abc.brevlab.com" and the bare "brevlab.com"); otherwise it is an exact host.
export function isHostAllowed(host, allowlist = getHostAllowlist()) {
  const h = String(host || '').toLowerCase();
  if (
    !h || h.length > 253 ||
    !h.split('.').every((label) =>
      label.length > 0 && label.length <= 63 &&
      /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(label))
  ) return false;                                           // reject ports, userinfo, empty labels, junk
  return allowlist.some((entry) => entry.startsWith('.')
    ? (h === entry.slice(1) || h.endsWith(entry))
    : h === entry);
}

export function corsHeaders(origin) {
  const allowOrigin = origin || '*';
  return {
    'access-control-allow-origin': allowOrigin,
    'access-control-allow-methods': ALLOWED_METHODS.join(', '),
    'access-control-allow-headers': getAllowedHeaders().join(', '),
    'access-control-expose-headers': 'Content-Type, Date, Cache-Control, x-request-id',
    'access-control-max-age': '86400',
    'vary': 'Origin',
  };
}

export function buildTargetUrl(rawPath = '/', rawQueryString = '') {
  const safeQueryString = stripSensitiveQuery(rawQueryString);
  if (getProxyMode() === 'multihost-allowlist') {
    return buildAllowlistedTargetUrl(rawPath, safeQueryString);
  }
  const upstream = new URL(getUpstreamOrigin());
  if (
    upstream.protocol !== 'https:' ||
    !MODEL_UPSTREAM_HOSTS.has(upstream.hostname.toLowerCase()) ||
    upstream.username || upstream.password || upstream.search || upstream.hash
  ) {
    const error = new Error('Model upstream origin is not approved.');
    error.statusCode = 500;
    throw error;
  }
  const safePath = normalizePath(rawPath);
  upstream.pathname = joinPaths(upstream.pathname, safePath);
  upstream.search = safeQueryString ? `?${safeQueryString}` : '';
  return upstream;
}

export function stripSensitiveQuery(rawQueryString = '') {
  const query = new URLSearchParams(rawQueryString);
  query.delete('cf_access_jwt');
  query.delete('access_provider');
  query.delete('access_session');
  return query.toString();
}

export function accessProviderForHost(hostname) {
  const host = String(hostname || '').toLowerCase();
  if (host === 'brevlab.com' || host.endsWith('.brevlab.com')) return 'cloudflare';
  if (host === 'apps.run.brev.nvidia.com' || host.endsWith('.apps.run.brev.nvidia.com')) return 'pomerium';
  return '';
}

function accessError(message) {
  const error = new Error(message);
  error.statusCode = 400;
  return error;
}

// Resolve the legacy /https/<host>/<path> form against the host allowlist. Throws a
// caller-facing 400 (malformed) or 403 (host not allowlisted) so the handler can return a
// CORS error rather than relaying. Only https upstreams; the host must pass the allowlist.
export function buildAllowlistedTargetUrl(rawPath = '/', rawQueryString = '') {
  const m = /^\/https\/([^/?#]+)(\/[^?#]*)?$/i.exec(rawPath || '');
  if (!m) {
    const err = new Error('Use /https/<host>/<path> (https targets only).');
    err.statusCode = 400;
    throw err;
  }
  const host = m[1].toLowerCase();
  if (!isHostAllowed(host)) {
    const err = new Error('Upstream host is not on the allowlist.');
    err.statusCode = 403;
    throw err;
  }
  const upstream = new URL(`https://${host}`);
  upstream.pathname = m[2] || '/';
  upstream.search = rawQueryString ? `?${rawQueryString}` : '';
  return upstream;
}

export function normalizePath(rawPath = '/') {
  let path = rawPath || '/';
  // Lambda Function URLs forward the original path as rawPath. Do not allow
  // absolute URL proxying tricks: this experiment forwards only to the
  // hardcoded upstream origin above.
  path = path.replace(/^https?:\/+/i, '/');
  path = path.replace(/^\/https\//i, '/');
  path = path.replace(/^\/http\//i, '/');
  return path.startsWith('/') ? path : `/${path}`;
}

function joinPaths(basePath, requestPath) {
  const left = basePath && basePath !== '/' ? basePath.replace(/\/$/, '') : '';
  const right = requestPath.startsWith('/') ? requestPath : `/${requestPath}`;
  return `${left}${right}` || '/';
}

export function filteredRequestHeaders(inputHeaders = {}, upstreamHost = '') {
  const headers = new Headers();
  const source = normalizeHeaders(inputHeaders);

  for (const [key, value] of Object.entries(source)) {
    const lower = key.toLowerCase();
    if (REQUEST_HEADERS_TO_STRIP.has(lower)) continue;
    if (Array.isArray(value)) {
      for (const entry of value) headers.append(key, String(entry));
    } else if (value !== undefined && value !== null) {
      headers.set(key, String(value));
    }
  }

  const billingOrigin = String(source['x-billing-invoke-origin'] || '').trim();
  if (billingOrigin) {
    const isNvidiaApiRelay = getProxyMode() === 'single-host' &&
      ['integrate.api.nvidia.com', 'build.nvidia.com'].includes(String(upstreamHost || '').toLowerCase());
    if (!isNvidiaApiRelay || billingOrigin.length > 64 || !BILLING_INVOKE_ORIGIN.test(billingOrigin)) {
      throw accessError('Invalid billing invoke origin.');
    }
    headers.set('X-BILLING-INVOKE-ORIGIN', billingOrigin);
  }

  // The browser cannot forward an HttpOnly launchable cookie across origins. It
  // supplies the opaque session through a neutral header. The relay maps it to
  // the provider-native upstream credential channel. Never accept a caller-
  // selected provider that disagrees with the target host.
  const expectedProvider = accessProviderForHost(upstreamHost);
  const requestedProvider = String(source['x-openclaw-access-provider'] || '').trim().toLowerCase();
  const neutralSession = String(source['x-openclaw-access-session'] || '').trim();
  const legacyCloudflareSession = String(source['cf-access-jwt-assertion'] || '').trim();

  if (neutralSession && !requestedProvider) {
    throw accessError('Neutral access sessions require an explicit access provider.');
  }
  if (requestedProvider && !['cloudflare', 'pomerium'].includes(requestedProvider)) {
    throw accessError('Unsupported access provider.');
  }
  if (requestedProvider && requestedProvider !== expectedProvider) {
    throw accessError('Access provider does not match the upstream host.');
  }
  if (legacyCloudflareSession && expectedProvider !== 'cloudflare') {
    throw accessError('Cloudflare access assertions are valid only for Cloudflare launchables.');
  }
  if (neutralSession && legacyCloudflareSession && neutralSession !== legacyCloudflareSession) {
    throw accessError('Conflicting access sessions.');
  }
  const accessSession = neutralSession || legacyCloudflareSession;
  if (accessSession.length > 8192) throw accessError('Access session is too large.');
  if (accessSession && !COOKIE_VALUE.test(accessSession)) {
    throw accessError('Access session contains invalid cookie characters.');
  }
  if (accessSession && expectedProvider === 'cloudflare') {
    headers.set('Cookie', `CF_Authorization=${accessSession}`);
  } else if (accessSession && expectedProvider === 'pomerium') {
    // Pomerium consumes and removes its signed session handle from this
    // dedicated header before forwarding upstream. Keep Authorization available
    // for the OpenClaw gateway token and avoid a synthesized Cookie header.
    headers.set('X-Pomerium-Authorization', accessSession);
  }

  return headers;
}

export async function fetchWithSameOriginRedirects(
  targetUrl,
  requestInit,
  fetchImpl = fetch,
  maxRedirects = 3,
) {
  let currentUrl = new URL(targetUrl);
  let currentInit = {
    ...requestInit,
    headers: new Headers(requestInit.headers || {}),
    redirect: 'manual',
  };

  for (let redirects = 0; ; redirects += 1) {
    const response = await fetchImpl(currentUrl, currentInit);
    if (!REDIRECT_STATUSES.has(response.status)) return response;

    const location = response.headers.get('location');
    if (!location) return response;
    try { await response.body?.cancel(); } catch { /* redirect body is intentionally discarded */ }
    if (redirects >= maxRedirects) {
      const error = new Error('Upstream redirect limit exceeded.');
      error.statusCode = 502;
      throw error;
    }

    const nextUrl = new URL(location, currentUrl);
    if (nextUrl.origin !== currentUrl.origin) {
      const error = new Error('Cross-origin upstream redirect blocked.');
      error.statusCode = 502;
      throw error;
    }

    const method = String(currentInit.method || 'GET').toUpperCase();
    if ((response.status === 303 && method !== 'HEAD') ||
        ((response.status === 301 || response.status === 302) && method === 'POST')) {
      const headers = new Headers(currentInit.headers);
      for (const name of REDIRECT_BODY_HEADERS) headers.delete(name);
      currentInit = { ...currentInit, method: 'GET', headers };
      delete currentInit.body;
    }
    currentUrl = nextUrl;
  }
}

export function filteredResponseHeaders(inputHeaders, origin) {
  const headers = new Headers();
  const source = inputHeaders instanceof Headers ? inputHeaders : new Headers(inputHeaders || {});

  for (const [key, value] of source.entries()) {
    if (RESPONSE_HEADERS_TO_STRIP.has(key.toLowerCase())) continue;
    headers.set(key, value);
  }

  for (const [key, value] of Object.entries(corsHeaders(origin))) {
    headers.set(key, value);
  }

  // Explicitly omit Access-Control-Allow-Credentials. Arbitrary-origin CORS
  // plus browser cookies is intentionally not supported for this experiment.
  headers.delete('access-control-allow-credentials');
  return headers;
}

export function preflightResponse(origin) {
  return {
    // Lambda response streaming + Function URLs can drop metadata on bodyless
    // 204 responses. A 200 preflight is valid CORS behavior and preserves the
    // metadata headers through the streaming response path.
    statusCode: 200,
    headers: {
      ...corsHeaders(origin),
      'content-type': 'text/plain; charset=utf-8',
      'cache-control': 'no-store',
    },
    body: 'OK\n',
  };
}

export function errorResponse(statusCode, message, origin, details = undefined) {
  const body = JSON.stringify({ error: message, ...(details ? { details } : {}) });
  return {
    statusCode,
    headers: {
      ...corsHeaders(origin),
      'content-type': 'application/json',
      'cache-control': 'no-store',
    },
    body,
  };
}

export function responseForProxyError(error, origin) {
  const statusCode = error.statusCode || 502;
  const callerError = statusCode === 400 || statusCode === 403;
  return errorResponse(
    statusCode,
    callerError ? error.message : 'Proxy request failed',
    origin,
    callerError ? undefined : error.message,
  );
}

export function assertCloudFrontSecret(headers = {}) {
  const expected = process.env.CLOUDFRONT_SHARED_SECRET;
  if (!expected) {
    const error = new Error('Relay edge secret is not configured');
    error.statusCode = 500;
    throw error;
  }
  const source = normalizeHeaders(headers);
  const actual = source[EDGE_SECRET_HEADER];
  if (actual !== expected) {
    const error = new Error('Direct Lambda Function URL access is disabled');
    error.statusCode = 403;
    throw error;
  }
}

export function normalizeHeaders(headers = {}) {
  const normalized = {};
  for (const [key, value] of Object.entries(headers || {})) {
    normalized[key.toLowerCase()] = value;
  }
  return normalized;
}

export function shouldSendBody(method) {
  return !['GET', 'HEAD'].includes(String(method || 'GET').toUpperCase());
}

export async function bodyFromEvent(event) {
  if (!shouldSendBody(event.requestContext?.http?.method)) return undefined;
  if (!event.body) return undefined;
  return event.isBase64Encoded ? Buffer.from(event.body, 'base64') : event.body;
}

export function logSafeRequest(event, targetUrl, statusCode, startedAt) {
  const method = event.requestContext?.http?.method || 'GET';
  const rawPath = event.rawPath || '/';
  const durationMs = Date.now() - startedAt;
  console.log(JSON.stringify({
    method,
    path: rawPath,
    upstream_host: targetUrl?.hostname || '-',
    status: statusCode,
    duration_ms: durationMs,
  }));
}
