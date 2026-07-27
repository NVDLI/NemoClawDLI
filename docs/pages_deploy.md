# CI/CD and client-side delivery

This documents how the course tests itself and ships as a fully client-side site.
It owns both production publication and temporary branch-preview behavior. The
versioned tag and artifact contract lives in
[`release_artifacts.md`](release_artifacts.md); trust boundaries live in
[`security-design.md`](security-design.md).
This is the standalone repository, so `.gitlab-ci.yml` and
`.github/workflows/pages.yml` at the root are the live CI for this repo. Both run
the same static gate and then build the same client-side site. GitLab Pages serves
it as the private pre-release preview (access-controlled even on a private repo),
and GitHub Pages is the first-class external delivery mechanism. The planned
`docs.nvidia.com/learning/nemoclaw` integration will provide the NVIDIA learning
front door without changing the client-side course boundary.

Build and preview the site locally any time:

```
bash scripts/build/build_pages.sh public
python3 -m http.server -d public 8000      # then open http://localhost:8000
```

## The static site

`scripts/build/build_pages.sh` assembles a `public/` directory that runs entirely in a
browser, with no server logic:

| Path | What it is |
|---|---|
| `public/index.html` | the release picker, with Pages-relative links |
| `public/nemoclaw/` | the course as a self-contained standalone bundle |
| `public/link-graph.html` + `engine.js` | the link-graph viewer (engine runs in-browser; offline uses the embedded snapshot) |
| `public/tests.html` | the client-side test runner (below) |
| `public/validation.html` + `gate.json` | the CI gate report, rendered from `docs/validation/latest.json` |
| `public/source/github/` + `public/source/gitlab/` | public-safe routes for the projected workflow and host-configuration explorers |
| `public/LICENSE` + `THIRD_PARTY_LICENSES.md` | Apache-2.0 terms and the static third-party package/license/material inventory |

GitLab Pages does not preserve HTML responses under dot-prefixed directories byte-for-byte.
`project_source_tree.py` therefore moves `.github/` and `.gitlab/` to the two `source/` routes
above and rewrites local HTML and JSON evidence links before the exhaustive browser, artifact,
and deployed-byte checks run.
The source files remain at their normal repository paths; only the static projection changes.
Two sources may never claim one artifact route. A path-scoped policy decision resolves a `source/`
route back to the repository file it copies only when the artifact file's full bytes exactly match
that source file. Otherwise a reviewed file that satisfies the sensitive-content boundary in the
source tree could fail it for the first time inside the production deploy, under a spelling no
pre-merge check ever scanned. The pull-request job audits its own built artifact under that same
boundary for the same reason.

The course pages inline their own CSS and JS and use relative links, so the course directory works
from a Pages subpath. Live model calls use the student's own NVIDIA key and call NVIDIA model
services directly by default. An explicitly enabled iframe mode uses the NVIDIA API CORS relay.

Pages-hosted Cloudflare Access launchables use the OpenClaw relay. Pomerium launchables keep their
HttpOnly session in the signed-in browser: gateway and terminal WebSockets connect directly, and
the two fixed metadata reads use that authenticated terminal to read launchable loopback. A course
vendored beside its NemoClaw runtime uses the same-origin route.

The launchable supplies the startup NVIDIA API key through its approved bootstrap path and
populates the same tab-scoped `sessionStorage` entry used by the course key panel. It does not
introduce another credential channel. Lab-only steps badge themselves and short-circuit off-lab.

Each course directory is also validated as an independent deployment root. The build
discovers every HTML file and every local navigation or resource URL, then rejects
missing targets, missing fragments, root-absolute paths, and paths that leave that
directory. The same browser run checks every same-origin request and link response.
There is no page, path, or file exemption list.

## What gets tested, and where

The **static gate** runs in CI on every push, with no lab, GPU, or browser (the link
engine runs headless under node):

```bash
python3 scripts/validation/release_gate.py --tier fast --no-write
```

The complete release matrix and evidence expectations live in
[`release-test-plan.md`](release-test-plan.md).

The **client-side test runner** (`tests.html`) covers three layers in the browser:

1. an engine smoke test (loads `engine.js`, asserts the public surface used by the viewer and CI),
2. the course **SKILL self-tests**, which auto-run on load and badge their own pass/fail,
3. the CI gate summary, surfaced from `gate.json`.

Host-native browser audits exercise the built static artifact with the same Chromium contract used
for source pages. No service stack is part of this repository gate.

## Deployment

The deployment path has four ordered stages. Security SCA jobs also run in the test
stage when their rules select them.

1. **Static gate and candidate build** share the required `test` worker. After validation,
   that already-initialized worker assembles `candidate/` once and uploads it with the gate report.
   This avoids both a second proposal build and another runner startup.
2. **Pages publication** is manual. Production refs copy the candidate to the root site;
   ordinary branches copy it to an isolated preview path beside a root rebuilt from an approved
   production ref. Deployment-specific manifests and available CI evidence are then projected.
3. **Pages verification** checks the deployed manifest and every advertised course URL,
   then renders every generated HTML file at desktop and narrow widths in dark and light mode without an allowlist.
4. **Human review** becomes available only after the exact commit passes the static gate,
   live deployment smoke, and exhaustive theme rendering.

### GitLab Pages (private pre-release)

The inert `.gitlab-ci.yml` includes exact owner-gated core, SCA, and internal-operations modules. `.gitlab/ci/core.yml`
defines `test`, `deploy`, `verify`, and `review` stages. The required `test` job builds the
proposal candidate after its gates pass; the manual `pages` job copies those bytes into either a
production root or branch preview instead of rebuilding the proposal.

GitLab Pages serves the private pre-release review surface under repository access
controls. `pages_smoke` checks the live result and `theme_runtime` checks every generated
HTML file at desktop and narrow widths in dark and light mode before `human_review` can be played.
The protected review job shares the `pages-site` resource lock with publication and rechecks the
live branch manifest plus `gate.json` commit before recording approval. If another branch replaced
the classic-Pages artifact, retry only this pipeline's `pages` job, review the restored URL, and
retry `human_review`; the static gate, SCA, and artifact theme render do not need to run again.

#### Branch-preview behavior

- `pages` is the only deploy job because this GitLab instance supports classic GitLab
  Pages rather than parallel Pages deployments.
- Production refs publish the normal root course. Ordinary branches publish a combined
  artifact: a root rebuilt from an approved production ref plus branch content confined
  to `/<branch-slug>/web/nemoclaw/`.
- Root and branch foyers read `branches.json`, which lists only preview paths present in
  the artifact. The interface also sends a same-origin `HEAD` request before showing an
  option, so an unavailable target stays hidden.
- Branch previews assemble canonical English and accepted same-branch locale overlays.
  `languages.json` advertises only current reviewed translations; stale translations
  fall back to canonical English.
- Preview artifacts and review environments expire after three days. Preview URLs are
  review surfaces, not durable course links.

#### Storage and authority contract

Classic Pages keeps one project artifact active. Publishing branch B replaces branch A's
combined artifact, so only the latest staged branch is previewable and listed. A Git branch
or an unplayed manual Pages job does not make a preview available.

The preview job keeps both cleanup controls:

- `artifacts.expire_in: 3 days` prevents downloadable `public/` artifacts from accumulating.
- `environment.auto_stop_in: 3 days` bounds the review-environment list. Production uses
  `never`.

`scripts/validation/ci_storage_audit.py` enforces the retention shape.

#### Branch-preview guardrails

- Branch pushes cannot deploy automatically; the blocking `test` job must pass first.
- The deploy compares `CI_COMMIT_SHA` with the live branch head and refuses stale pipelines.
- The production root is rebuilt only from `PROD_PAGES_REF`, restricted to the default
  branch or `nemoclaw-only`; branch content stays under the validated branch slug.
- `branch_preview_manifest_audit.py` rejects missing artifact paths, unlisted previews,
  stale schemas, missing readiness flags, and absent dependency evidence.
- `pages_smoke` verifies the live root foyer, branch foyer, manifests, course URLs,
  dependency dashboard, package inventory, and browser SBOM.
- `theme_runtime` discovers every generated `.html` file recursively and renders both
  themes. In branch pipelines it audits the complete branch-owned preview subtree; production
  pipelines audit the complete production artifact. The protected production-root copy bundled
  beside a branch preview belongs to the already-published production ref and is not silently
  reclassified as branch output. There is no per-file opt-in, exclusion list, or non-blocking result.
- `resource_group: pages-site` serializes preview and production deployments.
- `build_pages.sh` rejects unsafe output, course, source-mirror, and branch-prefix paths.

This is not a parallel-preview system. Production refs and environments must remain
protected because a branch may still propose changes to the workflow itself. Migrate to a
separate staging project or true parallel Pages deployments when the host supports them.

### Protected live review and DLI CDN publication

**Design goal:** a requested operation may choose a reviewed source branch and language subset,
but it cannot choose its executable code, credential destination, bucket, prefix, shell command,
or AWS identity.

Both operations start a new pipeline on protected internal GitLab `main`. `main` supplies the
trusted harness; the selected branch supplies only the exact successful `test` artifact named by
ref, full SHA, and job ID. The job metadata, archive bounds, candidate manifest, and commit binding
must all agree before any interface runs or any file enters a publication plan.

The parent job is runnerless. It maps only the documented request fields into a static child
pipeline and disables pipeline-variable forwarding. Process controls such as `BASH_ENV`, `PATH`,
tracing, checkout strategy, AWS variables, and secret file paths do not cross that boundary.

Configure these protected **file** variables on the `live-interface-review` environment; do not
pass their contents through `glab`:

- `COURSE_GITLAB_API_URL_FILE`, containing the internal GitLab `/api/v4` URL; scope it to
  `dli-source-review` and `live-interface-review`
- `COURSE_GITLAB_READ_TOKEN_FILE` with project-scoped `read_api` only; scope the same file variable
  to `dli-source-review` and `live-interface-review`
- `LIVE_NVIDIA_API_KEY_FILE`
- `LIVE_BUILD_API_KEY_FILE`
- `LIVE_CLAW_SESSION_1_FILE`
- `LIVE_CLAW_SESSION_2_FILE` when a second launchable is requested

Then request the fixed live matrix. It exercises candidate browser interfaces without credentials,
and exercises model request/stream plus OpenClaw gateway, terminal, chat, and cron transports from
trusted default-branch code. A separate credential-free job resolves the pinned browser runtime;
it never opens candidate content, and both browser jobs consume its short-lived artifact.

Before either operation handles a candidate, trusted code reads the owner-managed API origin file,
checks it against the pinned origin digest, rejects redirects, and verifies the actual child
pipeline, project, current `main` head, checkout, commit, and job name. The project also keeps **Minimum role to
use pipeline variables = Owner**.

Only the acquisition job receives the read-only GitLab token. It verifies the selected branch head,
latest paginated job evidence, and successful `test`, Pages, browser, and all three SCA jobs. Artifact
bytes use the narrower child job token. Candidate JavaScript runs later with a scrubbed environment
and receives only the verified archive and non-secret request record.

```bash
glab ci run -b main \
  --variables "COURSE_OP:live-interface-review" \
  --variables "CANDIDATE_REF:<reviewed-branch>" \
  --variables "CANDIDATE_SHA:<full-40-character-sha>" \
  --variables "CANDIDATE_TEST_JOB_ID:<successful-test-job-id>" \
  --variables "CLAW_URL_1:https://<launchable-host>/" \
  --variables "CLAW_ACCESS_PROVIDER_1:<cloudflare-or-pomerium>" \
  --variables "CLAW_URL_2:https://<optional-second-launchable-host>/" \
  --variables "CLAW_ACCESS_PROVIDER_2:<matching-provider>"
```

CDN publication accepts the same kind of source binding plus explicit course and language lists. `immutable`
publishes under `/course-static/<full-sha>/`; `stable` publishes under `/course-static/nemoclaw/`
and accepts only a branch in the devbox publisher's root-owned `stable_refs` allowlist. A branch
name never becomes an S3 destination. `PUBLISH_COURSES` must contain only `nemoclaw`. The
comma-separated language list controls which
NemoClaw language trees enter the operation; no hidden default adds a course or locale.

```bash
glab ci run -b main \
  --variables "COURSE_OP:cdn-publish" \
  --variables "PUBLISH_SOURCE_REF:<reviewed-branch>" \
  --variables "PUBLISH_SOURCE_SHA:<full-40-character-sha>" \
  --variables "PUBLISH_SOURCE_TEST_JOB_ID:<successful-test-job-id>" \
  --variables "PUBLISH_COURSES:nemoclaw" \
  --variables "PUBLISH_LANGUAGES:en,es" \
  --variables "PUBLISH_CHANNEL:immutable"
```

`cdn_prepare` has no AWS authority. It emits only selected bytes and a complete SHA-256 plan.
`cdn_publish` has no checkout, runs on the protected project-locked `dli-cdn-publisher` runner on
`vk-devbox-cpu-1`, and invokes only the root-owned
`/opt/dli-course-publisher/publish`. That program verifies every planned file, the configured AWS
account, root-owned destination bucket, key prefix, public base URL, and allowed channel.
Candidate CI receives no free-form shell, bucket, prefix, sync, or deletion input.

The publisher uses a root-owned AWS executable, configuration, credentials, exact IAM user or
delimiter-bound assumed-role rule, and fixed CloudFront distribution. It inventories every S3 page;
malformed or repeated keys fail the operation. Immutable prefixes
must contain only the exact reviewed manifest. Stable publication removes stale objects only from
the fixed roots owned by the explicitly selected courses, then requires the remote key/size inventory
to match. It waits for a CloudFront
invalidation before comparing every served byte. The language list is the complete stable language
set for NemoClaw, not an additive hint.

Provision that runner once, outside CI, after reviewing the exact source commit. Supply destination
identifiers in the operator environment; do not add them to source or workflow YAML:

```bash
DLI_PUBLISH_BUCKET=<operator-bucket> \
DLI_CDN_KEY_PREFIX=<operator-prefix> \
DLI_PUBLIC_BASE_URL=https://<public-host> \
bash scripts/ci/install_devbox_publisher.sh \
  <expected-12-digit-aws-account-id> \
  <exact-user-arn-or-assumed-role-prefix-ending-in-slash> \
  <cloudfront-distribution-id> \
  <project-locked-runner-group>
```

Set `DLI_STABLE_REFS` only during this root-owned installation when another reviewed branch may
publish stable URLs. Set `DLI_AWS_CONFIG_SOURCE` and `DLI_AWS_CREDENTIALS_SOURCE` when the reviewed
files are not under the installer account's default AWS directory.

This capability is deliberately **internal GitLab only**. The reviewable source remains in the
shared repository, but GitHub receives no workflow edge to it, protected variables, protected
environment, devbox runner, root-owned publisher, AWS identity, or live-launchable session. The CI
policy rejects internal authority vocabulary in public workflows. Host policy must not trust GitHub
OIDC for the DLI CDN role or attach an internal runner to the public repository. GitHub may validate
and publish its own public release artifacts; source availability never transfers DLI CDN or
live-launchable authority.

### GitHub Pages (external release)

`.github/workflows/pages.yml` runs the identical gate, then separates artifact creation
from deployment on pushes to the default branch. The read-only `build-and-verify` job
builds `public/`, verifies that `gate.json` names the same commit, rejects symlinks and
remote executable references, writes a SHA-256 inventory, and exercises the generated tree in
Chromium. A second clean runner independently assembles the tree without package installation.
Neither builder has OIDC or attestation authority. A later job requires identical manifests,
then passes only that inventory to a no-checkout signing job. The signer verifies its subject,
source/ref, workflow, and hosted runner without executing repository source. Only then can the
protected `deploy` job request authority.

Protect the `github-pages` environment with required reviewers and prevent self-review.
The reviewer inspects the build, browser logs, artifact, and provenance verification before
approving deployment. The deploy job has no checkout or shell step; with write and OIDC permissions
it invokes only the commit-pinned `deploy-pages` action on the previously uploaded artifact. A
separate read-only job then waits for HTTPS, safely extracts that artifact, requires the live
manifest to equal the reviewed manifest, and downloads every listed object to compare its digest.
This proves repeatability, workflow identity, and byte continuity, not that two ordinary runners
behaved honestly. Trusted-builder policy remains open; human review cannot replace it.

This is the first-class public course. A future `docs.nvidia.com/learning/nemoclaw` entry
will route learners into this low-friction static experience.

### NemoClaw launchable (same-origin alternative)

The second supported interaction path is assembled by the production NemoClaw GitHub
repository. Its release selects a version or tag of this course repository, vendors the
resulting static tree, and registers it as a new-tab kickstart option beside the TUI,
consoles, and other launchable surfaces. The NemoClaw deployment already serves its
landing page and microservices from one origin, so course-to-runtime traffic is
same-origin and does not use the OpenClaw relay. Its approved startup interface also
receives the NVIDIA API key and seeds the existing tab-scoped `sessionStorage` entry consumed
by `getKey()` and the key panel. This repository supplies the versioned course input;
the NemoClaw repository owns the production launchable integration and deployment.

Both providers call the same `scripts/build/build_pages.sh`, so the GitLab pre-release and
the GitHub external site are byte-identical builds. Only one course ships: the
`web/nemoclaw/` browser course, bundled into `public/nemoclaw/`.

Deploy jobs build only committed material snapshots. The preceding gate verifies their complete
digests and performs the policy-appropriate live drift check; the assembler then reuses that
same-commit report without changing tracked source bytes. A fresh local build may refresh materials
only when it also regenerates validation.
