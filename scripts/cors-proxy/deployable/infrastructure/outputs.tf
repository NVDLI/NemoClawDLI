# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

output "model_relay_url" {
  description = "Generated model relay URL. An operator alias may resolve to the same distribution."
  value       = "https://${aws_cloudfront_distribution.model.domain_name}"
}

output "runtime_relay_url" {
  description = "Generated runtime relay URL. An operator alias may resolve to the same distribution."
  value       = "https://${aws_cloudfront_distribution.runtime.domain_name}"
}
