# Hosted Relay Reference Findings

`scripts/cors-proxy/cors-proxy-worker-build.js` and `scripts/cors-proxy/cors-proxy-worker-openclaw.js` are
reference implementations, not the source of the hosted relay deployment. They retain the
security properties the course client depends on and remain useful review fixtures.

Properties retained in the references:

- The course client defaults to the model relay only on the exact `https://cdn.dli.learn.nvidia.com` origin, where the direct upstream CORS response is not reliable. A stored or query-string explicit direct override can force direct mode, all other course origins remain direct by default, and custom endpoints never enter this relay.
- `cors-proxy-worker-build.js` reflects the request `Origin` into `Access-Control-Allow-Origin`. That keeps LMS/static iframe execution working, but it is broad. The hosted deployment must own and review its exact `ALLOWED_ORIGINS` policy.
- `cors-proxy-worker-build.js` forwards caller headers to `integrate.api.nvidia.com`. Keep `X-BILLING-INVOKE-ORIGIN` allowed and forwarded because direct and proxy paths both use it for tracking.
- `cors-proxy-worker-openclaw.js` restricts upstream hosts to `brevlab.com` and subdomains. The hosted deployment must retain that boundary and own its page-origin policy.
- Any hosted-relay change belongs in its deployment repository with deployment-owner review.
