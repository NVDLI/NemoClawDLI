# Relay source findings

`scripts/cors-proxy/cors-proxy-worker-build.js` and `scripts/cors-proxy/cors-proxy-worker-openclaw.js` are
compact teaching references. `scripts/cors-proxy/deployable/` is the complete, parameterized
Lambda, CloudFront, and Terraform projection. Neither is evidence of a hosted deployment.

Properties retained in both representations:

- The course client defaults to the model relay only on the exact published course origins, `https://cdn.dli.learn.nvidia.com` and `https://nvdli.github.io`, where the direct upstream CORS response is not reliable. A stored or query-string explicit direct override can force direct mode, all other origins remain direct by default, and custom endpoints never enter this relay.
- `cors-proxy-worker-build.js` reflects the request `Origin` into `Access-Control-Allow-Origin`. That keeps LMS/static iframe execution working, but it is broad. The hosted deployment must own and review its exact `ALLOWED_ORIGINS` policy.
- `cors-proxy-worker-build.js` forwards caller headers to `integrate.api.nvidia.com`. Keep `X-BILLING-INVOKE-ORIGIN` allowed and forwarded because direct and proxy paths both use it for tracking.
- The launchable relay restricts upstream hosts to the two supported Brev host families, binds each
  access provider to its host family, strips caller-supplied provider credentials, and keeps page
  origin policy operator-owned.
- Both references now replace the upstream CORS answer rather than adding to it. They drop an
  upstream `Access-Control-Allow-Credentials` grant and `Set-Cookie`, vary on `Origin`, and drop a
  redirect body length they no longer send. The projection enforces the same rules.
- The deployable projection contains no account, state, DNS, credential, resource-name, or deployed
  endpoint values. A hosted change requires deployment-owner review and live evidence.

Limits of the teaching references:

- Neither worker authenticates its caller at the edge, emits request logs, or exposes operator
  configuration. The projection adds a CloudFront shared-secret check, structured logging, and
  environment-driven upstream and allowlist settings.
- Neither worker is the source of a hosted relay. Reading one tells you the browser contract, not
  what is deployed. Reproduce or review behavior against `scripts/cors-proxy/deployable/`.
