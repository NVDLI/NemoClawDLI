# Host-native course testing

The course is static HTML, CSS, and JavaScript. Repository checks run directly on the contributor or CI host; this repository does not define or distribute a container image.

The [Activity checkpoint contract](activity_checkpoints.md) defines which successful runtime events may advance course progress and completion.

## Public validation entry point

The validation wrapper is included in the checkout; no separately installed agent skill or
corporate account is required. Prepare the dependencies below, then run:

```sh
bash scripts/build/course_contribute.sh doctor
bash scripts/build/course_contribute.sh fast-gate
bash scripts/build/course_contribute.sh ship-gate
bash scripts/build/course_contribute.sh build-pages
```

The Linux implementation is `scripts/build/course_contribute.py`. It uses Python's standard
library to call existing repository checks. It does not install tools, fetch materials, load
credentials, or perform forge operations. Pages builds run their full validation without reusing
an earlier report. Review generated changes and require a clean source tree before publication.
After changing document links, run `bash scripts/runtime/run_engine.sh --embed` and commit the
tracked graph projection. The public-contribution regression suite checks it before Pages assembly.
The direct commands in this guide and `CONTRIBUTING.md` remain supported.

For a contribution, `fast-gate` and `ship-gate` accept `--changed-since upstream/main` when that
ref names your fetched upstream base. No remote name is assumed; a fork can keep `origin` for its
own repository. Omit the option for release validation. Only `build-pages` accepts `--output`.

The reference Pages CI uses Python 3.11 and Node 24. The locally tested Python default below is
3.12. Use the CI versions when validating runtime compatibility; a newer local runtime does not
prove an older runner compatible.

## Prerequisites

- Python 3.11 or newer; Python 3.12 is the tested default
- Node.js 20 or newer
- Chromium, Google Chrome, or a compatible Chromium browser
- pnpm through Corepack

Install the pinned browser API without downloading another browser:

```sh
corepack enable
(cd scripts/runtime && corepack enable && pnpm install --frozen-lockfile --ignore-scripts)
```

Use a Python 3.12 virtual environment for Python tooling. This avoids changing host-managed packages,
keeps the validation dependency boundary reviewable, and prevents pip from hiding releases that no
longer support older interpreters. Verify the interpreter before installing a lock:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python scripts/runtime/python_env_probe.py
python -m pip install pip==26.2.1
python -m pip install --require-hashes --no-deps --only-binary=:all: --requirement scripts/materials/requirements.lock
python scripts/runtime/python_env_probe.py --require-material-tools
```

Do not substitute unpinned package names for a lock file. A newer Python is outside the tested
baseline until CI proves it. The probe rejects Python 3.10
and older and explains missing tooling before a long build starts.

Set `NODE_BIN` or `CHROME_BIN` only when the tools are not discoverable on `PATH`. Then probe the environment and run the browser smoke:

```sh
scripts/runtime/browser_env_probe.sh
scripts/runtime/browser_runtime_test.sh --smoke
```

The ship gate remains the authoritative full check:

```sh
python3 scripts/validation/release_gate.py --tier ship
```

Credentialed live checks are explicit and inherit credentials only for the process:

```sh
NVIDIA_API_KEY="$NVIDIA_API_KEY" scripts/runtime/browser_runtime_test.sh --assistant-artifacts
CLAW_URL="$NEMOCLAW_URL" CLAW_ACCESS_PROVIDER="$ACCESS_PROVIDER" \
  CLAW_ACCESS_SESSION="$ACCESS_SESSION" scripts/runtime/browser_runtime_test.sh \
  --gateway-only --terminal-contract
```

Omit `CLAW_ACCESS_SESSION` when the isolated browser can authenticate to a Pomerium launchable
directly. Supply it when testing a separately hosted course: the runtime puts that value in
tab-scoped storage and uses the provider-bound relay. A provider name or hostname alone is not
evidence that a browser session is available. The course repeats its live gateway check when the
window regains focus, so a learner can sign in on the launchable tab and return without editing
the connection fields.

## Optional external isolation

External isolation is operator-owned. It must preserve the required Python, Node, and Chromium
versions and run the commands above. This repository does not build, scan, support, or distribute that environment.
On macOS, run repository Python in an authorized Linux environment; the shell wrapper may
orchestrate it without running repository Python on the Mac.

Set `COURSE_CONTRIBUTE_RUNNER` to a trusted absolute executable to delegate execution. The shell
wrapper passes `--repo ABSOLUTE_CHECKOUT MODE [ARGUMENTS...]` as literal arguments and returns the
executor's exit status. It clears the variable before delegation, so the executor can call the
same wrapper in Linux without recursively delegating. An invalid or failing executor stops the
operation; there is no automatic fallback. Review the executor before granting it access.

The executor owns dependency preparation, source transfer, and isolation. Transfer only reviewed
repository files, reject escaping symlinks, and keep home directories, profiles, credentials,
private operator configuration, and raw logs outside the guest. A read-only home mount still
permits reading its contents. Do not pass forge credentials into validation. Bind transferred
source and returned evidence to the exact candidate tree and fail if a build changes tracked
source. Apple Container, an existing Linux VM, or an authorized remote host can supply execution;
installing a container runtime does not install a course facade. No adapter is implicitly trusted.

Credentialed live tests are separate from this baseline; they require their own narrowly scoped
authority and secret handling. The wrapper is orchestration, not a sandbox for untrusted code.

See [Dependency security](dependency_security.md) for the remaining lock, scan, and evidence boundaries.
