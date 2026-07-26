# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

variable "aws_region" {
  description = "Operator-selected AWS region for regional relay resources."
  type        = string
}

variable "project_prefix" {
  description = "Operator-selected prefix for every named resource."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$", var.project_prefix))
    error_message = "project_prefix must be 3 to 40 lowercase letters, digits, or hyphens."
  }
}

variable "lambda_artifact_bucket" {
  description = "Operator-owned bucket containing the reviewed Lambda archive."
  type        = string
}

variable "lambda_artifact_key" {
  description = "Operator-selected object key for the reviewed Lambda archive."
  type        = string
}

variable "model_relay_shared_secret" {
  description = "Random value sent only from the model CloudFront distribution to Lambda."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.model_relay_shared_secret) >= 32
    error_message = "model_relay_shared_secret must contain at least 32 characters."
  }
}

variable "runtime_relay_shared_secret" {
  description = "Random value sent only from the runtime CloudFront distribution to Lambda."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.runtime_relay_shared_secret) >= 32
    error_message = "runtime_relay_shared_secret must contain at least 32 characters."
  }
}

variable "cache_policy_id" {
  description = "Operator-reviewed CloudFront policy that disables caching for relay traffic."
  type        = string
}

variable "origin_request_policy_id" {
  description = "Operator-reviewed CloudFront policy that forwards viewer headers except Host."
  type        = string
}

variable "log_retention_days" {
  description = "Operator-selected CloudWatch log retention."
  type        = number

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90], var.log_retention_days)
    error_message = "log_retention_days must use a supported CloudWatch retention value."
  }
}

variable "cloudfront_price_class" {
  description = "Operator-selected CloudFront price class."
  type        = string

  validation {
    condition = contains(
      ["PriceClass_100", "PriceClass_200", "PriceClass_All"],
      var.cloudfront_price_class,
    )
    error_message = "cloudfront_price_class must be a supported CloudFront price class."
  }
}

variable "model_dns_names" {
  description = "Operator-owned DNS aliases for the model relay, or an empty list."
  type        = list(string)
}

variable "runtime_dns_names" {
  description = "Operator-owned DNS aliases for the runtime relay, or an empty list."
  type        = list(string)
}

variable "model_acm_certificate_arn" {
  description = "Operator-owned CloudFront-compatible certificate ARN, or null for the default domain."
  type        = string
  nullable    = true
}

variable "runtime_acm_certificate_arn" {
  description = "Operator-owned CloudFront-compatible certificate ARN, or null for the default domain."
  type        = string
  nullable    = true
}

variable "resource_tags" {
  description = "Operator-selected tags applied to regional resources."
  type        = map(string)
}

variable "model_upstream_origin" {
  description = "Approved public model API origin."
  type        = string
  default     = "https://integrate.api.nvidia.com"

  validation {
    condition = contains(
      ["https://integrate.api.nvidia.com", "https://build.nvidia.com"],
      var.model_upstream_origin,
    )
    error_message = "model_upstream_origin must be an approved public model API origin."
  }
}

variable "runtime_host_allowlist" {
  description = "Public launchable host families enforced by the runtime relay."
  type        = string
  default     = ".brevlab.com,.apps.run.brev.nvidia.com"

  validation {
    condition     = var.runtime_host_allowlist == ".brevlab.com,.apps.run.brev.nvidia.com"
    error_message = "runtime_host_allowlist must retain both reviewed public host families."
  }
}
