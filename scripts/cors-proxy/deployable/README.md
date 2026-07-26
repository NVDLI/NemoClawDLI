# Deployable CORS relay snapshot

This directory contains the deployable source for two browser relays used by DLI course
integrations:

- a single-host model relay pinned to an approved NVIDIA API origin;
- an allowlisted runtime relay for HTTP, gateway WebSocket, and terminal WebSocket traffic.

It is an optional middleware package. The course build does not run, provision, or publish it.
Operators own AWS accounts, state, DNS, certificates, resource names, credentials, monitoring, and
deployment approval.

The smaller workers in the parent directory remain teaching examples. This directory is the
complete CloudFront, Lambda, Terraform, packaging, smoke-test, and unit-test implementation. A
renderable JSON infrastructure template remains beside Terraform as a dependency-free review
projection of the same topology.

## Security boundary

The stack provides these controls:

- response streaming through a Lambda Function URL;
- a CloudFront-generated shared header that rejects direct Function URL requests and never
  continues to an upstream origin;
- a pinned model upstream and an explicit host allowlist for runtime traffic;
- provider-to-host binding for Cloudflare Access and Pomerium browser sessions;
- removal of browser cookies, upstream cookies, service-token headers, and session transport
  fields before ordinary origin forwarding;
- bounded same-origin redirects;
- non-credentialed CORS;
- direct CloudFront routing for supported WebSocket paths;
- request logs that exclude authorization values and bodies.

The public Brev host families appear in the routing code because they are protocol inputs. No
operator account, state bucket, hosted zone, DNS name, resource prefix, or deployed endpoint is
committed.

## Requirements

- Node.js 20 or newer
- Terraform 1.10 or newer
- AWS credentials supplied outside this repository

Run the tests:

```bash
npm test
npm run render:infrastructure
terraform -chdir=infrastructure fmt -check
```

Package the Lambda:

```bash
./scripts/package-lambda.sh
```

## Prepare an operator deployment

Package the Lambda, create ignored operator inputs from the examples, and initialize the partial
Terraform backend:

```bash
./scripts/package-lambda.sh
cp infrastructure/backend.hcl.example infrastructure/backend.hcl
cp infrastructure/terraform.tfvars.example infrastructure/terraform.tfvars
terraform -chdir=infrastructure init -backend-config=backend.hcl
terraform -chdir=infrastructure validate
terraform -chdir=infrastructure plan -var-file=terraform.tfvars
```

Replace every angle-bracket value before initialization. The partial backend deliberately contains
no bucket, key, region, credentials, or locking topology. The operator supplies those values in
the ignored `backend.hcl`. Region, resource prefix, artifact location, secrets, cache policies,
log retention, price class, tags, DNS aliases, and certificates are required Terraform inputs.
Public model origins and the two launchable host families are defaults because the relay enforces
them as protocol facts.

Upload the archive to an operator-owned artifact location, then run the reviewed Terraform plan.
Operators that need the portable review projection may run `npm run render:infrastructure`; set
`CORS_PROXY_INFRASTRUCTURE_OUTPUT` when that JSON must be written outside the source tree.
Account, artifact location, state, DNS, certificates, resource names, shared secrets, monitoring,
and approval remain outside this repository. Pass the two shared secrets through an approved
protected secret mechanism and review the complete change set before execution.

## Smoke tests

Use outputs from the operator's applied stack:

```bash
MODEL_RELAY_URL="https://<operator-model-relay>"
./scripts/smoke-test.sh "$MODEL_RELAY_URL/v1/chat/completions?stream=true" \
  "https://course.example"
```

For a runtime host on the configured allowlist:

```bash
RUNTIME_RELAY_URL="https://<operator-runtime-relay>"
LAUNCHABLE_HOST="example.brevlab.com"
./scripts/smoke-test.sh "$RUNTIME_RELAY_URL/https/$LAUNCHABLE_HOST/api/agent" \
  "https://course.example"
```

Keep browser-session values out of shell history:

```bash
read -rs OPENCLAW_ACCESS_SESSION
export OPENCLAW_ACCESS_PROVIDER="cloudflare"
export OPENCLAW_GATEWAY_URL="$RUNTIME_RELAY_URL/https/$LAUNCHABLE_HOST/cli/gateway?access_provider=$OPENCLAW_ACCESS_PROVIDER&access_session=$OPENCLAW_ACCESS_SESSION"
npm run smoke:websocket
unset OPENCLAW_ACCESS_PROVIDER OPENCLAW_ACCESS_SESSION OPENCLAW_GATEWAY_URL
```

Run the same WebSocket smoke against `/ws/terminal` when validating the operator terminal route.

## Projection record

`PROJECTION.json` binds every projected source file in this directory to a SHA-256 digest and
records the reviewed source revision. Ignored build, dependency, and operator-input paths are not
source and cannot be expanded through `.gitignore`. An authorized maintainer refreshes the snapshot
from an approved local checkout, removes environment-specific values, runs the middleware tests,
updates the manifest, and submits the result through the normal Issue and pull-request flow.

`projection_transformations` also records corrections made after review in this repository. Carry
each one forward when re-projecting, or the next refresh reverts it. The current list covers the
edge shared secret that must not continue upstream and the handler tests added here.

After reviewing every projected change, refresh and immediately re-audit the file hashes:

```bash
python3 scripts/security/audit_cors_proxy_projection.py --refresh-manifest
```

The public repository intentionally does not record a private source location. The authorized
release record retains that acquisition evidence.

## Rollback

Remove this optional snapshot and restore the parent directory's teaching-only beacon. No course
runtime endpoint changes are required because this repository never deploys or operates a relay.
