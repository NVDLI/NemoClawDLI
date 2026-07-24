# Dependency security

The repository has four dependency boundaries:

1. `scripts/browser-vendor/package-lock.json` builds the browser code shipped to learners.
2. `scripts/materials/requirements.lock` supports material provenance checks and is not shipped.
3. `scripts/security/requirements-sca.lock` runs scanners and is not shipped.
4. `scripts/runtime/pnpm-lock.yaml` pins `playwright-core` for host-browser checks and is not shipped.

There is no repository-owned application environment, service stack, or container image.

## Fast offline checks

```sh
python3 scripts/security/audit_dependency_locks.py --self-test
python3 scripts/security/audit_dependency_locks.py
python3 scripts/security/audit_python_dependencies.py --self-test
python3 scripts/security/audit_python_dependencies.py
python3 scripts/validation/container_boundary_audit.py --self-test
python3 scripts/validation/container_boundary_audit.py
```

These checks require exact pins and SHA-256 artifact hashes, reject retired runtime packages, and
fail if a repository-owned Dockerfile, Containerfile, Compose file, or image build command returns.

## CI scans

- `security_browser_sca` runs automatically when the learner-browser graph, host-browser validation
  lock, or vendored output changes.
- `security_python_sca` runs automatically when material-tool or scanner inputs change.
- Both remain optional for unrelated merge requests and blocking on scheduled scans.

The Python job runs `pip-audit` against `scripts/materials/requirements.lock`, resolves every
license expression, evaluates SBOM policy, and retains the raw SBOM, resolved SBOM, appendix, and
evidence manifest. The release workflow repeats that scan for the tagged source.

## Updating a dependency

1. Change the direct input and regenerate its lock with pinned `uv`, Python 3.11 resolution, and
   `--generate-hashes`; review every direct and transitive change.
2. Run the fast checks above.
3. Rebuild browser vendor output when the browser lock changed.
4. Run the applicable SCA job and review the evidence rather than only its exit code. The browser
   job installs the frozen pnpm lock, then audits its exact Playwright declaration
   through npm's supported bulk-advisory endpoint. Both npm audit reports are retained.
5. Record a time-bounded waiver only when a specific finding has an accountable owner and control.

External isolation runs the same pinned commands and remains outside this repository's distributed
and supported dependency scope.

Every CI installation uses `--require-hashes --no-deps --only-binary=:all:`. This makes the lock the
complete resolution boundary and rejects an unrecorded archive, source distribution, or transitive
package. Advisory details stay in the authorized private scanner record; public changes contain
only ordinary version, lock, test, and evidence updates.
See [Host-native course testing](lab_runtime_testing.md) for the prerequisite and isolation boundary.
