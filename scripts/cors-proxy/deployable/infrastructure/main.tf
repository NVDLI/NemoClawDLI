# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

locals {
  model_function_name   = "${var.project_prefix}-model"
  runtime_function_name = "${var.project_prefix}-runtime"
  model_function_domain = trimsuffix(
    trimprefix(aws_lambda_function_url.model.function_url, "https://"),
    "/",
  )
  runtime_function_domain = trimsuffix(
    trimprefix(aws_lambda_function_url.runtime.function_url, "https://"),
    "/",
  )
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "relay" {
  name               = "${var.project_prefix}-relay"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.resource_tags
}

resource "aws_cloudwatch_log_group" "model" {
  name              = "/aws/lambda/${local.model_function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.resource_tags
}

resource "aws_cloudwatch_log_group" "runtime" {
  name              = "/aws/lambda/${local.runtime_function_name}"
  retention_in_days = var.log_retention_days
  tags              = var.resource_tags
}

data "aws_iam_policy_document" "relay_logs" {
  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "${aws_cloudwatch_log_group.model.arn}:*",
      "${aws_cloudwatch_log_group.runtime.arn}:*",
    ]
  }
}

resource "aws_iam_role_policy" "relay_logs" {
  name   = "write-bounded-relay-logs"
  role   = aws_iam_role.relay.id
  policy = data.aws_iam_policy_document.relay_logs.json
}

resource "aws_lambda_function" "model" {
  function_name = local.model_function_name
  description   = "Streaming browser relay pinned to one approved model origin."
  role          = aws_iam_role.relay.arn
  runtime       = "nodejs20.x"
  handler       = "handler.handler"
  memory_size   = 512
  timeout       = 300
  s3_bucket     = var.lambda_artifact_bucket
  s3_key        = var.lambda_artifact_key
  tags          = var.resource_tags

  environment {
    variables = {
      PROXY_MODE                 = "single-host"
      UPSTREAM_ORIGIN            = var.model_upstream_origin
      UPSTREAM_HOST_ALLOWLIST    = ""
      CORS_ALLOWED_HEADERS       = "Authorization, Content-Type, Accept, X-BILLING-INVOKE-ORIGIN"
      CLOUDFRONT_SHARED_SECRET   = var.model_relay_shared_secret
    }
  }

  logging_config {
    log_format = "JSON"
  }

  depends_on = [
    aws_cloudwatch_log_group.model,
    aws_iam_role_policy.relay_logs,
  ]
}

resource "aws_lambda_function" "runtime" {
  function_name = local.runtime_function_name
  description   = "Streaming browser relay constrained to approved launchable hosts."
  role          = aws_iam_role.relay.arn
  runtime       = "nodejs20.x"
  handler       = "handler.handler"
  memory_size   = 512
  timeout       = 300
  s3_bucket     = var.lambda_artifact_bucket
  s3_key        = var.lambda_artifact_key
  tags          = var.resource_tags

  environment {
    variables = {
      PROXY_MODE               = "multihost-allowlist"
      UPSTREAM_ORIGIN          = ""
      UPSTREAM_HOST_ALLOWLIST  = var.runtime_host_allowlist
      CORS_ALLOWED_HEADERS     = "Authorization, Content-Type, x-openclaw-session-key, Accept, CF-Access-Jwt-Assertion, X-OpenClaw-Access-Provider, X-OpenClaw-Access-Session"
      CLOUDFRONT_SHARED_SECRET = var.runtime_relay_shared_secret
    }
  }

  logging_config {
    log_format = "JSON"
  }

  depends_on = [
    aws_cloudwatch_log_group.runtime,
    aws_iam_role_policy.relay_logs,
  ]
}

resource "aws_lambda_function_url" "model" {
  function_name      = aws_lambda_function.model.function_name
  authorization_type = "NONE"
  invoke_mode        = "RESPONSE_STREAM"
}

resource "aws_lambda_function_url" "runtime" {
  function_name      = aws_lambda_function.runtime.function_name
  authorization_type = "NONE"
  invoke_mode        = "RESPONSE_STREAM"
}

resource "aws_lambda_permission" "model_function_url" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.model.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "runtime_function_url" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.runtime.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

resource "aws_lambda_permission" "model_function_url_invoke" {
  statement_id             = "AllowPublicInvokeViaFunctionUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.model.function_name
  principal                = "*"
  invoked_via_function_url = true
}

resource "aws_lambda_permission" "runtime_function_url_invoke" {
  statement_id             = "AllowPublicInvokeViaFunctionUrl"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.runtime.function_name
  principal                = "*"
  invoked_via_function_url = true
}

resource "aws_cloudfront_function" "runtime_websocket" {
  name    = "${var.project_prefix}-runtime-websocket"
  comment = "Validate and route launchable WebSocket upgrades."
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/../src/openclaw-websocket-request.js")
}

resource "aws_cloudfront_distribution" "model" {
  enabled         = true
  is_ipv6_enabled = true
  http_version    = "http2and3"
  price_class     = var.cloudfront_price_class
  aliases         = var.model_dns_names

  origin {
    domain_name = local.model_function_domain
    origin_id   = "model-lambda-url"

    custom_header {
      name  = "x-dli-cors-proxy-secret"
      value = var.model_relay_shared_secret
    }

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id         = "model-lambda-url"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD", "OPTIONS"]
    compress                 = false
    cache_policy_id          = var.cache_policy_id
    origin_request_policy_id = var.origin_request_policy_id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.model_acm_certificate_arn == null
    acm_certificate_arn            = var.model_acm_certificate_arn
    ssl_support_method             = var.model_acm_certificate_arn == null ? null : "sni-only"
    minimum_protocol_version       = var.model_acm_certificate_arn == null ? "TLSv1" : "TLSv1.2_2021"
  }

  lifecycle {
    precondition {
      condition = (
        (length(var.model_dns_names) == 0 && var.model_acm_certificate_arn == null) ||
        (length(var.model_dns_names) > 0 && var.model_acm_certificate_arn != null)
      )
      error_message = "Model DNS aliases and an ACM certificate must be supplied together."
    }
  }
}

resource "aws_cloudfront_distribution" "runtime" {
  enabled         = true
  is_ipv6_enabled = true
  http_version    = "http2and3"
  price_class     = var.cloudfront_price_class
  aliases         = var.runtime_dns_names

  origin {
    domain_name = local.runtime_function_domain
    origin_id   = "runtime-lambda-url"

    custom_header {
      name  = "x-dli-cors-proxy-secret"
      value = var.runtime_relay_shared_secret
    }

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  origin {
    domain_name = "brevlab.com"
    origin_id   = "runtime-websocket-origin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id         = "runtime-lambda-url"
    viewer_protocol_policy   = "redirect-to-https"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD", "OPTIONS"]
    compress                 = false
    cache_policy_id          = var.cache_policy_id
    origin_request_policy_id = var.origin_request_policy_id
  }

  ordered_cache_behavior {
    path_pattern             = "/https/*/cli/gateway"
    target_origin_id         = "runtime-websocket-origin"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD", "OPTIONS"]
    compress                 = false
    cache_policy_id          = var.cache_policy_id
    origin_request_policy_id = var.origin_request_policy_id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.runtime_websocket.arn
    }
  }

  ordered_cache_behavior {
    path_pattern             = "/https/*/ws/terminal"
    target_origin_id         = "runtime-websocket-origin"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD", "OPTIONS"]
    cached_methods           = ["GET", "HEAD", "OPTIONS"]
    compress                 = false
    cache_policy_id          = var.cache_policy_id
    origin_request_policy_id = var.origin_request_policy_id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.runtime_websocket.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = var.runtime_acm_certificate_arn == null
    acm_certificate_arn            = var.runtime_acm_certificate_arn
    ssl_support_method             = var.runtime_acm_certificate_arn == null ? null : "sni-only"
    minimum_protocol_version       = var.runtime_acm_certificate_arn == null ? "TLSv1" : "TLSv1.2_2021"
  }

  lifecycle {
    precondition {
      condition = (
        (length(var.runtime_dns_names) == 0 && var.runtime_acm_certificate_arn == null) ||
        (length(var.runtime_dns_names) > 0 && var.runtime_acm_certificate_arn != null)
      )
      error_message = "Runtime DNS aliases and an ACM certificate must be supplied together."
    }
  }
}
