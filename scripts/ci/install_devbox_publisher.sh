#!/usr/bin/env bash
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Run manually on vk-devbox-cpu-1 after reviewing this exact commit. This is not a CI job.
set -euo pipefail
if [[ $# -ne 4 || ! "$1" =~ ^[0-9]{12}$ || ! "$2" =~ ^arn:aws:(sts|iam)::$1:(assumed-role|user)/[A-Za-z0-9+=,.@_/-]+$ || ! "$3" =~ ^E[A-Z0-9]{8,20}$ || ! "$4" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]]; then
  echo "usage: $0 AWS_ACCOUNT_ID PRINCIPAL_ARN_OR_ASSUMED_ROLE_PREFIX CLOUDFRONT_DISTRIBUTION_ID RUNNER_GROUP" >&2
  exit 2
fi
getent group "$4" >/dev/null || { echo "runner group does not exist" >&2; exit 2; }
if [[ "$2" == *:assumed-role/* && "$2" != */ ]]; then
  echo "an assumed-role rule must end after the role name with /; the session is matched separately" >&2
  exit 2
fi
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
python_bin=$(readlink -f "$(command -v python3)")
aws_bin=$(readlink -f "$(command -v aws)")
for binary in "$python_bin" "$aws_bin"; do
  [[ "$binary" = /* && ! -L "$binary" && $(stat -f '%u' "$binary" 2>/dev/null || stat -c '%u' "$binary") = 0 ]] || {
    echo "python3 and aws must resolve to root-owned absolute regular files" >&2; exit 2;
  }
done
aws_sha=$(shasum -a 256 "$aws_bin" | awk '{print $1}')
aws_config_source=${DLI_AWS_CONFIG_SOURCE:-$HOME/.aws/config}
aws_credentials_source=${DLI_AWS_CREDENTIALS_SOURCE:-$HOME/.aws/credentials}
stable_refs=${DLI_STABLE_REFS:-main,nemoclaw-only}
[[ "$stable_refs" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]{0,126}(,[A-Za-z0-9][A-Za-z0-9._/-]{0,126})*$ && "$stable_refs" != *..* && "$stable_refs" != *//* ]] || {
  echo "DLI_STABLE_REFS must be a comma-separated root-owned branch allowlist" >&2; exit 2;
}
for source in "$aws_config_source" "$aws_credentials_source"; do
  [[ -f "$source" && ! -L "$source" ]] || { echo "AWS config sources must be regular files" >&2; exit 2; }
  if grep -Eiq '(^|[_.-])(endpoint_url|credential_process|web_identity_token_file|ca_bundle)[[:space:]]*=' "$source"; then
    echo "AWS config sources may not redirect credentials or service endpoints" >&2; exit 2
  fi
done
sudo install -d -o root -g root -m 0755 /opt/dli-course-publisher
sudo install -d -o root -g "$4" -m 0750 /etc/dli-course-publisher
sudo install -o root -g "$4" -m 0440 "$aws_config_source" /etc/dli-course-publisher/aws-config
sudo install -o root -g "$4" -m 0440 "$aws_credentials_source" /etc/dli-course-publisher/aws-credentials
sudo install -o root -g root -m 0444 "$root/scripts/ci/devbox_cdn_publisher.py" /opt/dli-course-publisher/publisher.py
wrapper=$(mktemp)
config=$(mktemp)
trap 'rm -f "$config" "$wrapper"' EXIT
printf '#!/bin/sh\nexec /usr/bin/env -i HOME=/var/empty PATH=/usr/bin:/bin %s -I /opt/dli-course-publisher/publisher.py "$@"\n' "$python_bin" > "$wrapper"
sudo install -o root -g root -m 0555 "$wrapper" /opt/dli-course-publisher/publish
stable_refs_json=$(printf '%s' "$stable_refs" | awk -F, '{printf "["; for (i=1;i<=NF;i++) printf "%s\"%s\"", (i>1?",":""), $i; printf "]"}')
printf '{"aws_account_id":"%s","principal_arn":"%s","stable_refs":%s,"aws_executable":"%s","aws_executable_sha256":"%s","aws_config_file":"/etc/dli-course-publisher/aws-config","aws_credentials_file":"/etc/dli-course-publisher/aws-credentials","cloudfront_distribution_id":"%s"}\n' "$1" "$2" "$stable_refs_json" "$aws_bin" "$aws_sha" "$3" > "$config"
sudo install -o root -g root -m 0444 "$config" /etc/dli-course-publisher.json
echo "Installed the fixed DLI publisher. Configure a protected, project-locked runner tagged dli-cdn-publisher on this host."
