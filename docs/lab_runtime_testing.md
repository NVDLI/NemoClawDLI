# Host-native course testing

The course is static HTML, CSS, and JavaScript. Repository checks run directly on the contributor or CI host; this repository does not define or distribute a container image.

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
python -m pip install pip==26.1.2
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

External isolation is operator-owned. It must preserve the pinned Python, Node, and Chromium versions and run the commands above. This repository does not build, scan, support, or distribute that environment.

See [Dependency security](dependency_security.md) for the remaining lock, scan, and evidence boundaries.
