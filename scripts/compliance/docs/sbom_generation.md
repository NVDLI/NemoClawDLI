# SBOM generation and attachment runbook

The repository does not define or distribute a container image. Its generated SBOMs cover the browser code shipped to learners and the small Python tool set used to verify course materials.

This runbook generates the SBOM evidence used for source and open-source review without adding
generated SBOM bodies to the repository. Run every command from the repository root at the exact
reviewed commit. Retain the command, tool version, commit SHA, component count, file size, and
SHA-256 alongside each output.

Its normal attachment set is the browser runtime, resolved Python validation environment, and exact
source tree. A separately managed container requires its own review; it is not part of this repository.

## Output directory

```bash
COMMIT=$(git rev-parse HEAD)
OUT=/tmp/nemoclaw-sbom-$COMMIT
mkdir -p "$OUT"
```

Do not commit `$OUT`. Attach its reviewed files to the issue or merge request, then retain the same
files in the authorized release evidence record.

## Evidence catalog and retention

[`scripts/compliance/docs/sbom_evidence.json`](sbom_evidence.json) is the compact index used by the license view. It records
two evidence states instead of presenting every missing aggregate license as the same problem:

- `available`: the linked SBOM is in the repository and the catalog pins its SHA-256 and component count;
- `ci-generated`: the SBOM, evidence manifest, and license appendix are produced for an exact commit;
GitLab SCA artifacts expire after 30 days. They support merge review but are not permanent release
evidence. A versioned public release copies its Python SBOM, evidence manifest, and license appendix
into release assets. It also composes a release catalog whose relative links resolve to the
versioned Python and browser SBOM filenames.
Verify the committed catalog and its linked browser SBOM with:

```bash
python3 scripts/compliance/sbom_evidence.py --check
python3 scripts/compliance/sbom_evidence.py --self-test
```

The offline check rejects missing repository declarations, malformed URLs, stale link-check dates,
and incomplete license hints. Scheduled CI and protected release preparation also read the official
external URLs with bounded retries:

```bash
python3 scripts/compliance/sbom_evidence.py --check-external-links
```

The source checkout carries `ci_sbom_evidence.json` with an explicit `unavailable` state. The deep
SCA job exports its numeric job ID as a dotenv report, and Pages receives that job's artifacts
through an explicit `needs` edge. Pages then reads one byte from each expected path through the
job-ID artifact API with `CI_JOB_TOKEN`. It emits clickable direct-job links only after the
manifest names the exact preview commit and every expected path succeeds. A missing producing job,
commit mismatch, or missing path stays visibly unavailable; a branch or job-name guess never turns
into an evidence link. The verified files are also copied beside the staged evidence catalog. That
same-origin CycloneDX copy is SHA-256 checked in the browser before the license view renders its
resolved Python component rows; the GitLab links remain the provenance and retention authority.

The scanner-original CycloneDX file is retained unchanged.
`scripts/compliance/resolve_sbom_licenses.py` then creates
the review SBOM consumed by the license UI. Every component must match an exact package/version row
in `THIRD_PARTY_LICENSES.md`; the result records the raw-SBOM and inventory SHA-256 values and keeps
the scanner's original license value on each component. Evidence emission creates the Markdown
appendix from that resolved SBOM through
`scripts/compliance/render_sbom_license_inventory.py`. A missing mapping fails the job.

## Browser runtime CycloneDX

The browser generator enumerates the packages actually included by the esbuild metafiles, copies
their license texts, and writes the deterministic CycloneDX document.

```bash
cd scripts/browser-vendor
npm ci
cd ../..
scripts/runtime/run_node.sh scripts/build/vendor_browser_dependencies.mjs
python3 scripts/validation/course_dependency_integrity.py --self-test
python3 scripts/validation/course_dependency_integrity.py
cp web/nemoclaw/vendor/browser-sbom.cdx.json "$OUT/browser-runtime.cdx.json"
```

The exact npm lock remains the authority for the wider build graph. An optional
`npm view <name>@<version> license dist.integrity repository --json` query may corroborate a row,
but it does not override the reviewed lock and installed license text.

## Python material-tool CycloneDX

The repository has no Python application runtime. Scan the small pinned material-tool closure with
the separate scanner lock. This is the same sequence used by `security_python_sca`.

```bash
python3 -m venv /tmp/nemoclaw-release-scanner
/tmp/nemoclaw-release-scanner/bin/python -m pip install --require-hashes --no-deps --only-binary=:all: -r scripts/security/requirements-sca.lock
mkdir -p "$OUT/python-scan"
/tmp/nemoclaw-release-scanner/bin/pip-audit -r scripts/materials/requirements.lock --strict --no-deps --disable-pip \
  --format cyclonedx-json --output "$OUT/python-scan/python-env.raw.cdx.json"
/tmp/nemoclaw-release-scanner/bin/python scripts/compliance/resolve_sbom_licenses.py \
  --input "$OUT/python-scan/python-env.raw.cdx.json" \
  --output "$OUT/python-scan/python-env.cdx.json"
/tmp/nemoclaw-release-scanner/bin/python scripts/security/audit_sbom_policy.py \
  --sbom "$OUT/python-scan/python-env.cdx.json" \
  --report "$OUT/python-scan/sbom-policy.json"
cp "$OUT/python-scan/python-env.cdx.json" "$OUT/python-env.cdx.json"
cp "$OUT/python-scan/python-env.raw.cdx.json" "$OUT/python-env.raw.cdx.json"
cp "$OUT/python-scan/sbom-policy.json" "$OUT/sbom-policy.json"
python3 scripts/compliance/sbom_evidence.py \
  --raw-sbom "$OUT/python-env.raw.cdx.json" \
  --sbom "$OUT/python-env.cdx.json" \
  --artifact-name "python-material-tools-$COMMIT" \
  --record-id python-material-tooling \
  --description "Pinned Python tools used to verify course materials; not distributed to learners" \
  --distribution not-distributed \
  --category validation \
  --source-commit "$COMMIT" \
  --ci-job manual-review \
  --appendix-out "$OUT/python-license-appendix.md" \
  --manifest-out "$OUT/python-sbom-evidence.json"
```

When reusing the CI result, first verify the job SHA equals `$COMMIT`, download the complete
artifact with authenticated byte ranges, verify every `Content-Range`, and retain the artifact ZIP
SHA-256. Do not reuse an SBOM from an earlier green commit.

## Exact source-tree CycloneDX and SPDX

Install Syft 1.44.0 from the
[official release](https://github.com/anchore/syft/releases/tag/v1.44.0), verify the downloaded archive
against the publisher's checksum file, and put the executable on `PATH`. Retain the archive name,
checksum file, checksum result, and version output with the review evidence. The explicit source name
and full commit make the output identity reviewable.

```bash
syft scan dir:"$PWD" \
  --source-name NemoClawDLIOS \
  --source-version "$COMMIT" \
  -q \
  -o cyclonedx-json="$OUT/source-tree.cdx.json" \
  -o spdx-json="$OUT/source-tree.spdx.json"
```

Record the scanner identity:

```bash
syft version
```

## License metadata precedence

1. Preserve the scanner-original SBOM as evidence.
2. Resolve the review SBOM from exact normalized-name and exact-version rows in `THIRD_PARTY_LICENSES.md`.
3. Stop if any package/version lacks a corroborated SPDX mapping; do not publish a placeholder.
4. Keep descriptive external-content terms descriptive when they are not an OSS SPDX license.

For Python metadata review, use the exact-version endpoint
`https://pypi.org/pypi/<normalized-name>/<version>/json`. If it supplies only a legacy label or no
expression, inspect the license file from that exact wheel/source distribution and its source tag.

## Course-material source and terms retrieval

```bash
python3 scripts/materials/pull_materials.py --list
python3 scripts/materials/pull_materials.py --verify-committed
python3 scripts/materials/pull_materials.py --check
python3 scripts/compliance/third_party_inventory_audit.py
```

The materials vendorer uses typed extractors for NVIDIA article HTML, arXiv API paper metadata, and
the NVIDIA glossary. It enforces HTTPS, same-host redirects, bounded responses, and bounded retries,
then records the source URL, relationship, size, and SHA-256. Those extractors acquire content, not
permission. A reviewer determines the cited source's terms; when no explicit reuse grant exists,
the inventory continues to say so. Figure and material provenance come from their respective
`SKILL.html` beacons, and the inventory audit rejects a missing external-source row.

### Paper licenses and NVIDIA document authors

The document-source acquisition is separate from content vendoring. It scans canonical course and
material files for every arXiv ID, reads each official arXiv abstract page's “Rights to this article”
link, and records the title, full author list, selected license, license URL, reuse meaning, and every
canonical citation location. It reads published NVIDIA JSON-LD bylines when present. If an official
NVIDIA page publishes no byline, the record says `not-listed-on-source` instead of guessing an owner.

Generate a review candidate without overwriting the committed evidence:

```bash
python3 scripts/compliance/source_document_audit.py \
  --refresh \
  --output /tmp/document_sources.json
diff -u scripts/compliance/docs/document_sources.json /tmp/document_sources.json
```

After a human has checked source URLs, licenses, bylines, and repository-item mappings, replace the
committed JSON deliberately and project its static Markdown tables:

```bash
cp /tmp/document_sources.json scripts/compliance/docs/document_sources.json
python3 scripts/compliance/source_document_audit.py --update-markdown
python3 scripts/compliance/source_document_audit.py
python3 scripts/compliance/export_legal_scope_csv.py \
  --category all \
  --output /tmp/nemoclaw-document-and-legal-scope.csv
```

The normal audit and CI never use the network. They reject a missing or stale arXiv record, a license
label that disagrees with its evidence URL, citation-location drift, an NVIDIA material without an
author/source record, and Markdown that no longer matches the reviewed JSON. The arXiv non-exclusive
distribution license is recorded as a limited arXiv distribution grant, not an open reuse license.

## Attachment manifest

The normal attachment bundle contains:

- `browser-runtime.cdx.json`
- `python-env.raw.cdx.json` (scanner-original)
- `python-env.cdx.json` (exact-version SPDX-resolved)
- `sbom-policy.json`
- `python-license-appendix.md`
- `python-sbom-evidence.json`
- `source-tree.cdx.json`
- `source-tree.spdx.json`
- a short manifest naming the commit, commands, tools, counts, byte sizes, and SHA-256 values

Generate checksums only after the files have passed their format and policy checks:

```bash
shasum -a 256 \
  "$OUT/browser-runtime.cdx.json" \
  "$OUT/python-env.raw.cdx.json" \
  "$OUT/python-env.cdx.json" \
  "$OUT/sbom-policy.json" \
  "$OUT/python-license-appendix.md" \
  "$OUT/python-sbom-evidence.json" \
  "$OUT/source-tree.cdx.json" \
  "$OUT/source-tree.spdx.json"
```

Attachment is evidence transport, not approval. The accountable reviewer still decides license
disposition and whether any additional released artifact requires its own SBOM.
