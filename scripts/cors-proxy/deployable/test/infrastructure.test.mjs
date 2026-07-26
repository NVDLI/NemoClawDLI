// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { renderInfrastructure } from '../scripts/render-infrastructure.mjs';

const templateText = readFileSync(new URL('../infrastructure/template.json', import.meta.url), 'utf8');
const functionCode = readFileSync(new URL('../src/openclaw-websocket-request.js', import.meta.url), 'utf8');
const terraformText = [
  'terraform.tf',
  'variables.tf',
  'main.tf',
  'outputs.tf',
].map((name) => readFileSync(new URL(`../infrastructure/${name}`, import.meta.url), 'utf8')).join('\n');
const template = JSON.parse(renderInfrastructure(templateText, functionCode));
const RETIRED_BILLING_HEADER = ['X-BILLING', 'SOURCE'].join('-');

test('infrastructure source is dependency-free and embeds the reviewed WebSocket router', () => {
  assert.equal(
    template.Resources.RuntimeWebSocketRequest.Properties.FunctionCode,
    functionCode,
  );
  assert.doesNotMatch(JSON.stringify(template), /__OPENCLAW_WEBSOCKET_FUNCTION_CODE__/);
});

test('both Lambda URLs stream and require distinct origin-only secrets', () => {
  for (const name of ['ModelFunctionUrl', 'RuntimeFunctionUrl']) {
    assert.equal(template.Resources[name].Properties.InvokeMode, 'RESPONSE_STREAM');
  }
  assert.equal(template.Parameters.ModelRelaySharedSecret.NoEcho, true);
  assert.equal(template.Parameters.RuntimeRelaySharedSecret.NoEcho, true);
  const modelHeader = template.Resources.ModelDistribution.Properties
    .DistributionConfig.Origins[0].OriginCustomHeaders[0];
  const runtimeHeader = template.Resources.RuntimeDistribution.Properties
    .DistributionConfig.Origins[0].OriginCustomHeaders[0];
  assert.deepEqual(modelHeader.HeaderValue, { Ref: 'ModelRelaySharedSecret' });
  assert.deepEqual(runtimeHeader.HeaderValue, { Ref: 'RuntimeRelaySharedSecret' });
});

test('portable infrastructure keeps operator deployment choices parameterized', () => {
  for (const name of [
    'ProjectPrefix',
    'LambdaArtifactBucket',
    'LambdaArtifactKey',
    'ModelRelaySharedSecret',
    'RuntimeRelaySharedSecret',
    'CachePolicyId',
    'OriginRequestPolicyId',
    'LogRetentionDays',
    'CloudFrontPriceClass',
  ]) {
    assert.equal(template.Parameters[name].Default, undefined, `${name} must have no default`);
  }
  assert.deepEqual(
    template.Resources.ModelDistribution.Properties.DistributionConfig.PriceClass,
    { Ref: 'CloudFrontPriceClass' },
  );
  assert.deepEqual(
    template.Resources.RuntimeDistribution.Properties.DistributionConfig.PriceClass,
    { Ref: 'CloudFrontPriceClass' },
  );
});

test('runtime HTTP forwarding remains constrained to both approved host families', () => {
  const variable = template.Resources.RuntimeFunction.Properties.Environment
    .Variables.UPSTREAM_HOST_ALLOWLIST;
  assert.deepEqual(variable, { Ref: 'RuntimeHostAllowlist' });
  assert.deepEqual(
    template.Parameters.RuntimeHostAllowlist.AllowedValues,
    ['.brevlab.com,.apps.run.brev.nvidia.com'],
  );
});

test('gateway and terminal WebSockets bypass Lambda through the reviewed router', () => {
  const config = template.Resources.RuntimeDistribution.Properties.DistributionConfig;
  assert.deepEqual(
    config.CacheBehaviors.map((behavior) => behavior.PathPattern).sort(),
    ['/https/*/cli/gateway', '/https/*/ws/terminal'],
  );
  for (const behavior of config.CacheBehaviors) {
    assert.equal(behavior.TargetOriginId, 'runtime-websocket-origin');
    assert.deepEqual(behavior.FunctionAssociations, [{
      EventType: 'viewer-request',
      FunctionARN: { 'Fn::GetAtt': ['RuntimeWebSocketRequest', 'FunctionARN'] },
    }]);
  }
  const websocketOrigin = config.Origins.find((origin) => origin.Id === 'runtime-websocket-origin');
  assert.equal(websocketOrigin.OriginCustomHeaders, undefined);
  assert.equal(config.Logging, undefined);
});

test('model preflight allows invoke-origin but no retired billing header', () => {
  const headers = template.Resources.ModelFunction.Properties.Environment
    .Variables.CORS_ALLOWED_HEADERS;
  assert.match(headers, /X-BILLING-INVOKE-ORIGIN/);
  assert.doesNotMatch(headers, new RegExp(RETIRED_BILLING_HEADER));
});

test('template contains no operator account, bucket, DNS, or deployment value', () => {
  assert.doesNotMatch(templateText, /\barn:aws[^:]*:[^:]*:\d{12}:/);
  assert.doesNotMatch(templateText, /\bs3:\/\/[a-z0-9]/i);
  assert.doesNotMatch(templateText, /\b[a-z0-9-]+\.cloudfront\.net\b/i);
  assert.doesNotMatch(templateText, /\.experiments\.courses\.nvidia\.com\b/i);
});

test('Terraform provisions both streaming relays and direct-origin protection', () => {
  assert.match(terraformText, /backend "s3" \{\}/);
  assert.match(terraformText, /provider "aws"[\s\S]*region = var\.aws_region/);
  assert.match(terraformText, /resource "aws_lambda_function" "model"/);
  assert.match(terraformText, /resource "aws_lambda_function" "runtime"/);
  assert.match(terraformText, /invoke_mode\s*=\s*"RESPONSE_STREAM"/);
  assert.match(terraformText, /resource "aws_cloudfront_distribution" "model"/);
  assert.match(terraformText, /resource "aws_cloudfront_distribution" "runtime"/);
  assert.match(terraformText, /name\s*=\s*"x-dli-cors-proxy-secret"/);
  assert.match(terraformText, /CLOUDFRONT_SHARED_SECRET\s*=\s*var\.model_relay_shared_secret/);
  assert.match(terraformText, /CLOUDFRONT_SHARED_SECRET\s*=\s*var\.runtime_relay_shared_secret/);
});

test('Terraform routes both WebSocket paths through the reviewed edge function', () => {
  assert.match(terraformText, /path_pattern\s*=\s*"\/https\/\*\/cli\/gateway"/);
  assert.match(terraformText, /path_pattern\s*=\s*"\/https\/\*\/ws\/terminal"/);
  assert.match(terraformText, /code\s*=\s*file\("\$\{path\.module\}\/\.\.\/src\/openclaw-websocket-request\.js"\)/);
  assert.match(terraformText, /function_arn\s*=\s*aws_cloudfront_function\.runtime_websocket\.arn/);
});

test('Terraform keeps environment topology operator-supplied', () => {
  for (const name of [
    'aws_region',
    'project_prefix',
    'lambda_artifact_bucket',
    'lambda_artifact_key',
    'model_relay_shared_secret',
    'runtime_relay_shared_secret',
    'cache_policy_id',
    'origin_request_policy_id',
    'log_retention_days',
    'cloudfront_price_class',
    'model_dns_names',
    'runtime_dns_names',
    'model_acm_certificate_arn',
    'runtime_acm_certificate_arn',
    'resource_tags',
  ]) {
    const block = new RegExp(`variable "${name}" \\{([\\s\\S]*?)\\n\\}`, 'm').exec(terraformText);
    assert.ok(block, `missing variable ${name}`);
    assert.doesNotMatch(block[1], /\bdefault\s*=/, `${name} must have no default`);
  }
  assert.doesNotMatch(terraformText, /\barn:aws[^:]*:[^:]*:\d{12}:/);
  assert.doesNotMatch(terraformText, /\b[a-z0-9-]+\.cloudfront\.net\b/i);
  assert.doesNotMatch(terraformText, /\.experiments\.courses\.nvidia\.com\b/i);
});
