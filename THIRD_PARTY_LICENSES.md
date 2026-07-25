# Third-party software and material inventory

This checked-in inventory is the static, human-readable list for the proposed Apache-2.0 source release. It records exact package versions and SPDX license expressions for package rows. Container rows separately name the publisher terms that govern the image and the component-license families that also apply; they are not reduced to one invented SPDX expression.

The root [Apache-2.0 license](LICENSE) covers NVIDIA-authored project code. Per-package browser license texts are distributed under [`web/nemoclaw/vendor/licenses/`](web/nemoclaw/vendor/licenses/). Python wheels and container layers retain their upstream license metadata and files. A built-image SBOM remains required for exact operating-system packages and image-layer licenses.

External pages that are only linked or summarized are not software dependencies. They are listed separately at the end so redistribution and inspiration are not conflated.

## Reproducing license-evidence acquisition

The inventory is derived from exact repository inputs and immutable scan artifacts. Package names
are not discovered through web search, and search results are not license evidence. The complete,
copyable commands, tool versions, attachment contents, image applicability rule, evidence-retention
requirements, and metadata precedence live in the
[`SBOM generation and attachment runbook`](scripts/compliance/docs/sbom_generation.md).

Generated SBOM bodies are attached to the review record rather than committed here. This file stays
the human-readable static package, license, container-boundary, and material inventory.

### Reconciliation and precedence

1. Scanner-provided SPDX identifiers or expressions win.
2. A static mapping may fill scanner named/missing metadata only for the exact normalized package
   name and exact version, and is labeled `exact package/version static fallback`.
3. A named license without a reviewed exact-version mapping remains unresolved.
4. Missing scanner metadata must be resolved from exact package/version evidence before an SBOM is rendered or exported.
5. External-source terms remain descriptive when they are not an OSS SPDX license.

The deterministic CI gate reads committed evidence without network access. Live PyPI, registry,
and source retrieval is a separate acquisition/review activity so upstream drift cannot silently
change a release. This process produces review evidence; it does not replace open-source or legal
approval.

## Browser runtime and browser-build packages

Source of truth: [`scripts/browser-vendor/package-lock.json`](scripts/browser-vendor/package-lock.json). Rows marked `browser-runtime` also appear in the shipped browser manifest and have checked-in license text. Platform-specific esbuild packages are build-only optional packages.

| Scope | Package | Version | SPDX license | Evidence |
|---|---|---|---|---|
| browser-runtime | @cfworker/json-schema | 4.1.1 | MIT | [`licenses/@cfworker__json-schema--4.1.1.txt`](web/nemoclaw/vendor/licenses/@cfworker__json-schema--4.1.1.txt) |
| browser-runtime | @highlightjs/cdn-assets | 11.10.0 | BSD-3-Clause | [`licenses/@highlightjs__cdn-assets--11.10.0.txt`](web/nemoclaw/vendor/licenses/@highlightjs__cdn-assets--11.10.0.txt) |
| browser-build-only | @esbuild/aix-ppc64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/android-arm | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/android-arm64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/android-x64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/darwin-arm64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/darwin-x64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/freebsd-arm64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/freebsd-x64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/linux-arm | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/linux-arm64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/linux-ia32 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/linux-loong64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/linux-mips64el | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/linux-ppc64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/linux-riscv64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/linux-s390x | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/linux-x64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/netbsd-arm64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/netbsd-x64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/openbsd-arm64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/openbsd-x64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/openharmony-arm64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/sunos-x64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/win32-arm64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/win32-ia32 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-build-only | @esbuild/win32-x64 | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-runtime | @langchain/core | 1.1.48 | MIT | [`licenses/@langchain__core--1.1.48.txt`](web/nemoclaw/vendor/licenses/@langchain__core--1.1.48.txt) |
| browser-runtime | @langchain/langgraph | 1.4.7 | MIT | [`licenses/@langchain__langgraph--1.4.7.txt`](web/nemoclaw/vendor/licenses/@langchain__langgraph--1.4.7.txt) |
| browser-runtime | @langchain/langgraph-checkpoint | 1.1.3 | MIT | [`licenses/@langchain__langgraph-checkpoint--1.1.3.txt`](web/nemoclaw/vendor/licenses/@langchain__langgraph-checkpoint--1.1.3.txt) |
| browser-bundle-input | @langchain/langgraph-sdk | 1.9.25 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-bundle-input | @langchain/langgraph-sdk/node_modules/eventemitter3 | 5.0.4 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-bundle-input | @langchain/langgraph-sdk/node_modules/p-queue | 9.3.0 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-bundle-input | @langchain/langgraph-sdk/node_modules/p-timeout | 7.0.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-runtime | @langchain/openai | 1.4.7 | MIT | [`licenses/@langchain__openai--1.4.7.txt`](web/nemoclaw/vendor/licenses/@langchain__openai--1.4.7.txt) |
| browser-bundle-input | @langchain/protocol | 0.0.18 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-bundle-input | @standard-schema/spec | 1.1.0 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-bundle-input | @types/json-schema | 7.0.15 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-bundle-input | argparse | 2.0.1 | Python-2.0 | [lock](scripts/browser-vendor/package-lock.json) |
| browser-runtime | base64-js | 1.5.1 | MIT | [`licenses/base64-js--1.5.1.txt`](web/nemoclaw/vendor/licenses/base64-js--1.5.1.txt) |
| browser-runtime | codemirror | 5.65.21 | MIT | [`licenses/codemirror--5.65.21.txt`](web/nemoclaw/vendor/licenses/codemirror--5.65.21.txt) |
| browser-build-only | esbuild | 0.28.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-runtime | eventemitter3 | 4.0.7 | MIT | [`licenses/eventemitter3--4.0.7.txt`](web/nemoclaw/vendor/licenses/eventemitter3--4.0.7.txt) |
| browser-bundle-input | is-network-error | 1.3.2 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-runtime | js-tiktoken | 1.0.21 | MIT | [`licenses/js-tiktoken--1.0.21.txt`](web/nemoclaw/vendor/licenses/js-tiktoken--1.0.21.txt) |
| browser-runtime | js-yaml | 5.2.2 | MIT | [`licenses/js-yaml--5.2.2.txt`](web/nemoclaw/vendor/licenses/js-yaml--5.2.2.txt) |
| browser-runtime | langsmith | 0.7.14 | MIT | [`licenses/langsmith--0.7.14.txt`](web/nemoclaw/vendor/licenses/langsmith--0.7.14.txt) |
| browser-runtime | marked | 14.1.4 | MIT | [`licenses/marked--14.1.4.txt`](web/nemoclaw/vendor/licenses/marked--14.1.4.txt) |
| browser-runtime | mustache | 4.2.0 | MIT | [`licenses/mustache--4.2.0.txt`](web/nemoclaw/vendor/licenses/mustache--4.2.0.txt) |
| browser-runtime | openai | 6.45.0 | Apache-2.0 | [`licenses/openai--6.45.0.txt`](web/nemoclaw/vendor/licenses/openai--6.45.0.txt) |
| browser-runtime | p-finally | 1.0.0 | MIT | [`licenses/p-finally--1.0.0.txt`](web/nemoclaw/vendor/licenses/p-finally--1.0.0.txt) |
| browser-runtime | p-queue | 6.6.2 | MIT | [`licenses/p-queue--6.6.2.txt`](web/nemoclaw/vendor/licenses/p-queue--6.6.2.txt) |
| browser-bundle-input | p-retry | 7.1.1 | MIT | [lock](scripts/browser-vendor/package-lock.json) |
| browser-runtime | p-timeout | 3.2.0 | MIT | [`licenses/p-timeout--3.2.0.txt`](web/nemoclaw/vendor/licenses/p-timeout--3.2.0.txt) |
| browser-runtime | zod | 3.25.76 | MIT | [`licenses/zod--3.25.76.txt`](web/nemoclaw/vendor/licenses/zod--3.25.76.txt) |

### Utility source embedded in `@langchain/core`

These four rows are code that LangChain copied into its own package before this project downloaded
`@langchain/core@1.1.48`. They are not additional npm installs, and this project does not patch
them. The exact LangChain tag, commit, source files, source hashes, full license evidence, and
esbuild-comment mappings are recorded in
[`embedded-component-evidence.json`](scripts/browser-vendor/embedded-component-evidence.json).

| Scope | Component | Version evidence | SPDX license | Evidence |
|---|---|---|---|---|
| browser-embedded-source | Fast JSON Patch | Snapshot in `@langchain/core@1.1.48`; upstream release number not stated | MIT | [`license`](web/nemoclaw/vendor/licenses/langchain-embedded-fast-json-patch.txt) · [`source record`](scripts/browser-vendor/embedded-component-evidence.json) |
| browser-embedded-source | js-sha256 | 0.11.1 in copied source header | MIT | [`license`](web/nemoclaw/vendor/licenses/langchain-embedded-js-sha256.txt) · [`source record`](scripts/browser-vendor/embedded-component-evidence.json) |
| browser-embedded-source | sax-js | Snapshot in `@langchain/core@1.1.48`; upstream release number not stated | ISC | [`combined upstream notice`](web/nemoclaw/vendor/licenses/langchain-embedded-sax-js-and-string-from-code-point.txt) · [`source record`](scripts/browser-vendor/embedded-component-evidence.json) |
| browser-embedded-source | String.fromCodePoint polyfill | 0.1.0 in copied source comment | MIT | [`combined upstream notice`](web/nemoclaw/vendor/licenses/langchain-embedded-sax-js-and-string-from-code-point.txt) · [`source record`](scripts/browser-vendor/embedded-component-evidence.json) |

The npm package graph and the generated `.LEGAL.txt` answer different questions. The package graph
records everything esbuild included from npm and shows which package required which dependency. For
example, `p-queue@6.6.2` requires `p-timeout@3.2.0`, which requires `p-finally@1.0.0`. The `.LEGAL.txt`
file contains only source comments specially marked for preservation. A package can therefore be in
the browser bundle without appearing in `.LEGAL.txt`; conversely, a copied utility inside LangChain
can appear there without being its own npm package. Full licenses come from the manifest links, not
from the preserved-comment file.

### Why a Python license appears in the browser table

`argparse@2.0.1` is a JavaScript npm package used transitively by `js-yaml@5.2.2`.
`Python-2.0` is the package's declared license identifier; no Python interpreter or Python package
is included in the browser bundle by that dependency.

## Browser-Python components fetched from upstream at runtime

The repository does not copy the components in this section into its static artifacts. The Pyodide
documentation page fetches pinned files from jsDelivr only after a reader runs Python.
[`scripts/pyodide/candidate-components.json`](scripts/pyodide/candidate-components.json)
records exact artifact filenames, SHA-256 values, runtime profiles, and the review boundary.

The documentation demonstration needs only the browser-Python runtime and standard library.
The network-profile rows remain candidates and are not loaded. Copying any runtime file
into the repository or an externally released learner artifact still requires the applicable
component, security, privacy, and distribution decisions. A version or package change requires
refreshed evidence.

The runnable documentation page under `scripts/pyodide/` fetches the pinned Core runtime from
jsDelivr after a reader selects Run. It executes those files in the browser but does not copy them
into this repository or the learner course artifact. The manifest records both loader entrypoints
and every supporting file with a SHA-256; `runtime_smoke.mjs --cdn` verifies the same runtime before
executing every example.

| Evaluated use | Component | Version | SPDX license expression | Evidence |
|---|---|---|---|---|
| Future asset preparation | ws | 8.20.0 | MIT | [npm](https://www.npmjs.com/package/ws/v/8.20.0) |
| Separate demonstration runtime | pyodide | 0.27.7 | MPL-2.0 | [upstream license](https://github.com/pyodide/pyodide/blob/0.27.7/LICENSE) |
| Separate demonstration runtime | cpython-standard-library | 3.12.7 | PSF-2.0 | [upstream license](https://github.com/python/cpython/blob/v3.12.7/LICENSE) |
| Future HTTP/API support | annotated-types | 0.6.0 | MIT | [PyPI](https://pypi.org/project/annotated-types/0.6.0/) |
| Future HTTP/API support | anyio | 4.9.0 | MIT | [PyPI](https://pypi.org/project/anyio/4.9.0/) |
| Future HTTP/API support | certifi | 2024.12.14 | MPL-2.0 | [PyPI](https://pypi.org/project/certifi/2024.12.14/) |
| Future HTTP/API support | charset-normalizer | 3.3.2 | MIT | [PyPI](https://pypi.org/project/charset-normalizer/3.3.2/) |
| Future HTTP/API support | distro | 1.9.0 | Apache-2.0 | [PyPI](https://pypi.org/project/distro/1.9.0/) |
| Future HTTP/API support | httpx | 0.28.1 | BSD-3-Clause | [PyPI](https://pypi.org/project/httpx/0.28.1/) |
| Future HTTP/API support | idna | 3.7 | BSD-3-Clause | [PyPI](https://pypi.org/project/idna/3.7/) |
| Future HTTP/API support | jiter | 0.8.2 | MIT | [PyPI](https://pypi.org/project/jiter/0.8.2/) |
| Future HTTP/API support | openai | 1.68.2 | Apache-2.0 | [PyPI](https://pypi.org/project/openai/1.68.2/) |
| Future HTTP/API support | openssl | 1.1.1w | OpenSSL | [exact tag license](https://github.com/openssl/openssl/blob/OpenSSL_1_1_1w/LICENSE) |
| Future HTTP/API support | pydantic | 2.10.5 | MIT | [PyPI](https://pypi.org/project/pydantic/2.10.5/) |
| Future HTTP/API support | pydantic-core | 2.27.2 | MIT | [PyPI](https://pypi.org/project/pydantic-core/2.27.2/) |
| Future HTTP/API support | pyodide-http | 0.2.1 | MIT | [PyPI](https://pypi.org/project/pyodide-http/0.2.1/) |
| Future HTTP/API support | requests | 2.31.0 | Apache-2.0 | [PyPI](https://pypi.org/project/requests/2.31.0/) |
| Future HTTP/API support | sniffio | 1.3.1 | MIT OR Apache-2.0 | [PyPI](https://pypi.org/project/sniffio/1.3.1/) |
| Future HTTP/API support | ssl | 1.0.0 | PSF-2.0 AND OpenSSL | [Pyodide recipe](https://github.com/pyodide/pyodide/blob/0.27.7/packages/ssl/meta.yaml); [CPython license](https://github.com/python/cpython/blob/v3.12.7/LICENSE); [OpenSSL license](https://github.com/openssl/openssl/blob/OpenSSL_1_1_1w/LICENSE) |
| Future HTTP/API support | typing-extensions | 4.11.0 | PSF-2.0 | [PyPI](https://pypi.org/project/typing-extensions/4.11.0/) |
| Future HTTP/API support | urllib3 | 2.2.3 | MIT | [PyPI](https://pypi.org/project/urllib3/2.2.3/) |

The Pyodide 0.27.7 OpenSSL recipe labels OpenSSL 1.1.1w as Apache-2.0. The exact upstream
OpenSSL 1.1.1w tag instead carries the legacy OpenSSL and SSLeay terms, represented here by the
`OpenSSL` SPDX identifier. The authorized reviewer must resolve that metadata conflict before the
future HTTP/API support set is distributed.

## Python and Node repository-tool packages

Sources of truth are the exact lock files named in the Scope column. The same package/version is shown once with every applicable scope. License expressions were resolved from the exact-version PyPI metadata; legacy ambiguous `BSD` metadata was checked against the package license text.

| Scope | Package | Version | SPDX license expression | Evidence |
|---|---|---|---|---|
| security-tooling | arrow | 1.4.0 | Apache-2.0 | [PyPI](https://pypi.org/pypi/arrow/1.4.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | attrs | 26.1.0 | MIT | [PyPI](https://pypi.org/pypi/attrs/26.1.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling | beautifulsoup4 | 4.15.0 | MIT | [PyPI](https://pypi.org/pypi/beautifulsoup4/4.15.0/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock) |
| security-tooling | boolean-py | 5.0 | BSD-2-Clause | [PyPI](https://pypi.org/pypi/boolean-py/5.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | cachecontrol | 0.14.4 | Apache-2.0 | [PyPI](https://pypi.org/pypi/cachecontrol/0.14.4/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling, security-tooling | certifi | 2026.6.17 | MPL-2.0 | [PyPI](https://pypi.org/pypi/certifi/2026.6.17/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | chardet | 5.2.0 | LGPL-2.0-or-later | [PyPI](https://pypi.org/pypi/chardet/5.2.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling, security-tooling | charset-normalizer | 3.4.9 | MIT | [PyPI](https://pypi.org/pypi/charset-normalizer/3.4.9/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | cyclonedx-bom | 7.3.0 | Apache-2.0 | [PyPI](https://pypi.org/pypi/cyclonedx-bom/7.3.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | cyclonedx-python-lib | 11.11.0 | Apache-2.0 | [PyPI](https://pypi.org/pypi/cyclonedx-python-lib/11.11.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | defusedxml | 0.7.1 | PSF-2.0 | [PyPI](https://pypi.org/pypi/defusedxml/0.7.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | filelock | 3.29.7 | MIT | [PyPI](https://pypi.org/pypi/filelock/3.29.7/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | fqdn | 1.5.1 | MPL-2.0 | [PyPI](https://pypi.org/pypi/fqdn/1.5.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling, security-tooling | idna | 3.18 | BSD-3-Clause | [PyPI](https://pypi.org/pypi/idna/3.18/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | isoduration | 20.11.0 | ISC | [PyPI](https://pypi.org/pypi/isoduration/20.11.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | jsonpointer | 3.1.1 | BSD-3-Clause | [PyPI](https://pypi.org/pypi/jsonpointer/3.1.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | jsonschema | 4.26.0 | MIT | [PyPI](https://pypi.org/pypi/jsonschema/4.26.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | jsonschema-specifications | 2025.9.1 | MIT | [PyPI](https://pypi.org/pypi/jsonschema-specifications/2025.9.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | lark | 1.3.1 | MIT | [PyPI](https://pypi.org/pypi/lark/1.3.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | license-expression | 30.4.4 | Apache-2.0 | [PyPI](https://pypi.org/pypi/license-expression/30.4.4/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling, security-tooling | lxml | 6.1.1 | BSD-3-Clause | [PyPI](https://pypi.org/pypi/lxml/6.1.1/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | markdown-it-py | 4.2.0 | MIT | [PyPI](https://pypi.org/pypi/markdown-it-py/4.2.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling | markdownify | 1.2.3 | MIT | [PyPI](https://pypi.org/pypi/markdownify/1.2.3/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock) |
| security-tooling | mdurl | 0.1.2 | MIT | [PyPI](https://pypi.org/pypi/mdurl/0.1.2/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | msgpack | 1.2.1 | Apache-2.0 | [PyPI](https://pypi.org/pypi/msgpack/1.2.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | packageurl-python | 0.17.6 | MIT | [PyPI](https://pypi.org/pypi/packageurl-python/0.17.6/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | packaging | 26.2 | Apache-2.0 OR BSD-2-Clause | [PyPI](https://pypi.org/pypi/packaging/26.2/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| host-bootstrap, security-tooling | pip | 26.1.2 | MIT | [PyPI](https://pypi.org/pypi/pip/26.1.2/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock); [`docs/lab_runtime_testing.md`](docs/lab_runtime_testing.md) |
| security-tooling | pip-api | 0.0.34 | Apache-2.0 | [PyPI](https://pypi.org/pypi/pip-api/0.0.34/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | pip-audit | 2.10.1 | Apache-2.0 | [PyPI](https://pypi.org/pypi/pip-audit/2.10.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | pip-requirements-parser | 32.0.1 | MIT | [PyPI](https://pypi.org/pypi/pip-requirements-parser/32.0.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | platformdirs | 4.10.0 | MIT | [PyPI](https://pypi.org/pypi/platformdirs/4.10.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | py-serializable | 2.1.0 | Apache-2.0 | [PyPI](https://pypi.org/pypi/py-serializable/2.1.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | pygments | 2.20.0 | BSD-2-Clause | [PyPI](https://pypi.org/pypi/pygments/2.20.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | pyparsing | 3.3.2 | MIT | [PyPI](https://pypi.org/pypi/pyparsing/3.3.2/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | python-dateutil | 2.9.0.post0 | Apache-2.0 OR BSD-3-Clause | [PyPI](https://pypi.org/pypi/python-dateutil/2.9.0.post0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | referencing | 0.37.0 | MIT | [PyPI](https://pypi.org/pypi/referencing/0.37.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling, security-tooling | requests | 2.34.2 | Apache-2.0 | [PyPI](https://pypi.org/pypi/requests/2.34.2/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | rfc3339-validator | 0.1.4 | MIT | [PyPI](https://pypi.org/pypi/rfc3339-validator/0.1.4/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | rfc3986-validator | 0.1.1 | MIT | [PyPI](https://pypi.org/pypi/rfc3986-validator/0.1.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | rfc3987-syntax | 1.1.0 | MIT | [PyPI](https://pypi.org/pypi/rfc3987-syntax/1.1.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | rich | 15.0.0 | MIT | [PyPI](https://pypi.org/pypi/rich/15.0.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | rpds-py | 2026.6.3 | MIT | [PyPI](https://pypi.org/pypi/rpds-py/2026.6.3/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | setuptools | 83.0.0 | MIT | [PyPI](https://pypi.org/pypi/setuptools/83.0.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling, security-tooling | six | 1.17.0 | MIT | [PyPI](https://pypi.org/pypi/six/1.17.0/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | sortedcontainers | 2.4.0 | Apache-2.0 | [PyPI](https://pypi.org/pypi/sortedcontainers/2.4.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling | soupsieve | 2.8.4 | MIT | [PyPI](https://pypi.org/pypi/soupsieve/2.8.4/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock) |
| security-tooling | tomli | 2.4.1 | MIT | [PyPI](https://pypi.org/pypi/tomli/2.4.1/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | tomli-w | 1.2.0 | MIT | [PyPI](https://pypi.org/pypi/tomli-w/1.2.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling, security-tooling | typing-extensions | 4.16.0 | PSF-2.0 | [PyPI](https://pypi.org/pypi/typing-extensions/4.16.0/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | tzdata | 2026.3 | Apache-2.0 | [PyPI](https://pypi.org/pypi/tzdata/2026.3/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | uri-template | 1.3.0 | MIT | [PyPI](https://pypi.org/pypi/uri-template/1.3.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| material-tooling, security-tooling | urllib3 | 2.7.0 | MIT | [PyPI](https://pypi.org/pypi/urllib3/2.7.0/json); [`scripts/materials/requirements.lock`](scripts/materials/requirements.lock); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | webcolors | 25.10.0 | BSD-3-Clause | [PyPI](https://pypi.org/pypi/webcolors/25.10.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| security-tooling | wheel | 0.47.0 | MIT | [PyPI](https://pypi.org/pypi/wheel/0.47.0/json); [`scripts/security/requirements-sca.lock`](scripts/security/requirements-sca.lock) |
| browser-validation | playwright-core | 1.61.1 | Apache-2.0 | [npm](https://www.npmjs.com/package/playwright-core/v/1.61.1); [`scripts/runtime/pnpm-lock.yaml`](scripts/runtime/pnpm-lock.yaml) |

### Less common license families and their scope

The active tool locks include MPL-2.0 (`certifi`, `fqdn`), LGPL-2.0-or-later (`chardet`), PSF-2.0 (`defusedxml`, `typing-extensions`), and ISC (`isoduration`). These tools are not shipped to learners. Preserve their upstream terms in scanner evidence; their presence is not an Apache-2.0 relicensing claim. No active package row declares GPL.

## Host tools not distributed by this repository

Contributors need Python 3.11+, Node.js 20+, and Chromium or compatible Chrome. These are host prerequisites, not repository dependencies or learner artifacts. Organizations may place the same pinned tools in an externally maintained container, but this repository does not define, build, scan, or distribute that container.

## Document source evidence

This section covers documents rather than software. Paper licenses are the exact choices
shown by the official arXiv abstract pages at the recorded review date. The repository's
Apache-2.0 license applies to NVIDIA-authored course summaries and diagrams, not to the papers
they cite. NVIDIA document authors are recorded only when the official source publishes a byline.
A missing byline is reported as such and is not replaced with a guessed team or owner.

### Research papers cited by the course

| arXiv ID | Paper and authors | Exact source license | Reuse meaning | Evidence | Canonical course citations |
|---|---|---|---|---|---|
| [arXiv:1508.07909](https://arxiv.org/abs/1508.07909) | Neural Machine Translation of Rare Words with Subword Units<br>Authors: Sennrich, Rico, Haddow, Barry, Birch, Alexandra | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:1702.08734](https://arxiv.org/abs/1702.08734) | Billion-scale similarity search with GPUs<br>Authors: Johnson, Jeff, Douze, Matthijs, Jégou, Hervé | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/02b-rag.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md` |
| [arXiv:1706.03741](https://arxiv.org/abs/1706.03741) | Deep reinforcement learning from human preferences<br>Authors: Christiano, Paul, Leike, Jan, Brown, Tom B., Martic, Miljan, Legg, Shane, Amodei, Dario | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/04c-going-further.html` |
| [arXiv:1706.03762](https://arxiv.org/abs/1706.03762) | Attention Is All You Need<br>Authors: Vaswani, Ashish, Shazeer, Noam, Parmar, Niki, Uszkoreit, Jakob, Jones, Llion, Gomez, Aidan N., Kaiser, Lukasz, Polosukhin, Illia | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md`<br>`web/nemoclaw/mats/glossary_raw/large-language-models.md` |
| [arXiv:2004.04906](https://arxiv.org/abs/2004.04906) | Dense Passage Retrieval for Open-Domain Question Answering<br>Authors: Karpukhin, Vladimir, Oğuz, Barlas, Min, Sewon, Lewis, Patrick, Wu, Ledell, Edunov, Sergey, Chen, Danqi, Yih, Wen-tau | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/02b-rag.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md` |
| [arXiv:2005.11401](https://arxiv.org/abs/2005.11401) | Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks<br>Authors: Lewis, Patrick, Perez, Ethan, Piktus, Aleksandra, Petroni, Fabio, Karpukhin, Vladimir, Goyal, Naman, Küttler, Heinrich, Lewis, Mike, Yih, Wen-tau, Rocktäschel, Tim, Riedel, Sebastian, Kiela, Douwe | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/02b-rag.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/_materials.json`<br>`web/nemoclaw/mats/agent_field_guide.md`<br>`web/nemoclaw/mats/agentic_equilibrium.md`<br>`web/nemoclaw/mats/arxiv-2005.11401-rag.md`<br>`web/nemoclaw/mats/materials_index.json` |
| [arXiv:2005.14165](https://arxiv.org/abs/2005.14165) | Language Models are Few-Shot Learners<br>Authors: Brown, Tom B., Mann, Benjamin, Ryder, Nick, Subbiah, Melanie, Kaplan, Jared, Dhariwal, Prafulla, Neelakantan, Arvind, Shyam, Pranav, Sastry, Girish, Askell, Amanda, Agarwal, Sandhini, Herbert-Voss, Ariel, Krueger, Gretchen, Henighan, Tom, Child, Rewon, Ramesh, Aditya, Ziegler, Daniel M., Wu, Jeffrey, Winter, Clemens, Hesse, Christopher, Chen, Mark, Sigler, Eric, Litwin, Mateusz, Gray, Scott, Chess, Benjamin, Clark, Jack, Berner, Christopher, McCandlish, Sam, Radford, Alec, Sutskever, Ilya, Amodei, Dario | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md`<br>`web/nemoclaw/mats/glossary_raw/large-language-models.md` |
| [arXiv:2008.00325](https://arxiv.org/abs/2008.00325) | Bringing UMAP Closer to the Speed of Light with GPU Acceleration<br>Authors: Nolet, Corey J., Lafargue, Victor, Raff, Edward, Nanditale, Thejaswi, Oates, Tim, Zedlewski, John, Patterson, Joshua | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/mats/glossary_raw/vector-database.md` |
| [arXiv:2010.06467](https://arxiv.org/abs/2010.06467) | Pretrained Transformers for Text Ranking: BERT and Beyond<br>Authors: Lin, Jimmy, Nogueira, Rodrigo, Yates, Andrew | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/02b-rag.html` |
| [arXiv:2104.06357](https://arxiv.org/abs/2104.06357) | GPU Semiring Primitives for Sparse Neighborhood Methods<br>Authors: Nolet, Corey J., Gala, Divye, Raff, Edward, Eaton, Joe, Rees, Brad, Zedlewski, John, Oates, Tim | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/mats/glossary_raw/vector-database.md` |
| [arXiv:2201.11903](https://arxiv.org/abs/2201.11903) | Chain-of-Thought Prompting Elicits Reasoning in Large Language Models<br>Authors: Wei, Jason, Wang, Xuezhi, Schuurmans, Dale, Bosma, Maarten, Ichter, Brian, Xia, Fei, Chi, Ed, Le, Quoc, Zhou, Denny | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/01b-react.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2205.00445](https://arxiv.org/abs/2205.00445) | MRKL Systems: A modular, neuro-symbolic architecture that combines large language models, external knowledge sources and discrete reasoning<br>Authors: Karpas, Ehud, Abend, Omri, Belinkov, Yonatan, Lenz, Barak, Lieber, Opher, Ratner, Nir, Shoham, Yoav, Bata, Hofit, Levine, Yoav, Leyton-Brown, Kevin, Muhlgay, Dor, Rozen, Noam, Schwartz, Erez, Shachaf, Gal, Shalev-Shwartz, Shai, Shashua, Amnon, Tenenholtz, Moshe | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2210.03629](https://arxiv.org/abs/2210.03629) | ReAct: Synergizing Reasoning and Acting in Language Models<br>Authors: Yao, Shunyu, Zhao, Jeffrey, Yu, Dian, Du, Nan, Shafran, Izhak, Narasimhan, Karthik, Cao, Yuan | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/01b-react.html`<br>`web/nemoclaw/02a-routing.html`<br>`web/nemoclaw/02c-deep.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/_materials.json`<br>`web/nemoclaw/mats/agent_field_guide.md`<br>`web/nemoclaw/mats/agentic_equilibrium.md`<br>`web/nemoclaw/mats/arxiv-2210.03629-react.md`<br>`web/nemoclaw/mats/materials_index.json` |
| [arXiv:2211.09110](https://arxiv.org/abs/2211.09110) | Holistic Evaluation of Language Models<br>Authors: Liang, Percy, Bommasani, Rishi, Lee, Tony, Tsipras, Dimitris, Soylu, Dilara, Yasunaga, Michihiro, Zhang, Yian, Narayanan, Deepak, Wu, Yuhuai, Kumar, Ananya, Newman, Benjamin, Yuan, Binhang, Yan, Bobby, Zhang, Ce, Cosgrove, Christian, Manning, Christopher D., Ré, Christopher, Acosta-Navas, Diana, Hudson, Drew A., Zelikman, Eric, Durmus, Esin, Ladhak, Faisal, Rong, Frieda, Ren, Hongyu, Yao, Huaxiu, Wang, Jue, Santhanam, Keshav, Orr, Laurel, Zheng, Lucia, Yuksekgonul, Mert, Suzgun, Mirac, Kim, Nathan, Guha, Neel, Chatterji, Niladri, Khattab, Omar, Henderson, Peter, Huang, Qian, Chi, Ryan, Xie, Sang Michael, Santurkar, Shibani, Ganguli, Surya, Hashimoto, Tatsunori, Icard, Thomas, Zhang, Tianyi, Chaudhary, Vishrav, Wang, William, Li, Xuechen, Mai, Yifan, Zhang, Yuhui, Koreeda, Yuta | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2212.08073](https://arxiv.org/abs/2212.08073) | Constitutional AI: Harmlessness from AI Feedback<br>Authors: Bai, Yuntao, Kadavath, Saurav, Kundu, Sandipan, Askell, Amanda, Kernion, Jackson, Jones, Andy, Chen, Anna, Goldie, Anna, Mirhoseini, Azalia, McKinnon, Cameron, Chen, Carol, Olsson, Catherine, Olah, Christopher, Hernandez, Danny, Drain, Dawn, Ganguli, Deep, Li, Dustin, Tran-Johnson, Eli, Perez, Ethan, Kerr, Jamie, Mueller, Jared, Ladish, Jeffrey, Landau, Joshua, Ndousse, Kamal, Lukosuite, Kamile, Lovitt, Liane, Sellitto, Michael, Elhage, Nelson, Schiefer, Nicholas, Mercado, Noemi, DasSarma, Nova, Lasenby, Robert, Larson, Robin, Ringer, Sam, Johnston, Scott, Kravec, Shauna, Showk, Sheer El, Fort, Stanislav, Lanham, Tamera, Telleen-Lawton, Timothy, Conerly, Tom, Henighan, Tom, Hume, Tristan, Bowman, Samuel R., Hatfield-Dodds, Zac, Mann, Ben, Amodei, Dario, Joseph, Nicholas, McCandlish, Sam, Brown, Tom, Kaplan, Jared | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html` |
| [arXiv:2212.10496](https://arxiv.org/abs/2212.10496) | Precise Zero-Shot Dense Retrieval without Relevance Labels<br>Authors: Gao, Luyu, Ma, Xueguang, Lin, Jimmy, Callan, Jamie | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/02b-rag.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md` |
| [arXiv:2302.04761](https://arxiv.org/abs/2302.04761) | Toolformer: Language Models Can Teach Themselves to Use Tools<br>Authors: Schick, Timo, Dwivedi-Yu, Jane, Dessì, Roberto, Raileanu, Roberta, Lomeli, Maria, Zettlemoyer, Luke, Cancedda, Nicola, Scialom, Thomas | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/01b-react.html`<br>`web/nemoclaw/01c-tools.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2302.12173](https://arxiv.org/abs/2302.12173) | Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection<br>Authors: Greshake, Kai, Abdelnabi, Sahar, Mishra, Shailesh, Endres, Christoph, Holz, Thorsten, Fritz, Mario | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/04a-safety.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md` |
| [arXiv:2303.11366](https://arxiv.org/abs/2303.11366) | Reflexion: Language Agents with Verbal Reinforcement Learning<br>Authors: Shinn, Noah, Cassano, Federico, Berman, Edward, Gopinath, Ashwin, Narasimhan, Karthik, Yao, Shunyu | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2303.16634](https://arxiv.org/abs/2303.16634) | G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment<br>Authors: Liu, Yang, Iter, Dan, Xu, Yichong, Wang, Shuohang, Xu, Ruochen, Zhu, Chenguang | [CC-BY-NC-ND-4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) | Only attributed, noncommercial sharing of unadapted copies is allowed. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2303.17651](https://arxiv.org/abs/2303.17651) | Self-Refine: Iterative Refinement with Self-Feedback<br>Authors: Madaan, Aman, Tandon, Niket, Gupta, Prakhar, Hallinan, Skyler, Gao, Luyu, Wiegreffe, Sarah, Alon, Uri, Dziri, Nouha, Prabhumoye, Shrimai, Yang, Yiming, Gupta, Shashank, Majumder, Bodhisattwa Prasad, Hermann, Katherine, Welleck, Sean, Yazdanbakhsh, Amir, Clark, Peter | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/02a-routing.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md` |
| [arXiv:2304.03442](https://arxiv.org/abs/2304.03442) | Generative Agents: Interactive Simulacra of Human Behavior<br>Authors: Park, Joon Sung, O'Brien, Joseph C., Cai, Carrie J., Morris, Meredith Ringel, Liang, Percy, Bernstein, Michael S. | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/03a-kickstart.html`<br>`web/nemoclaw/03c-always-on.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2305.04091](https://arxiv.org/abs/2305.04091) | Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models<br>Authors: Wang, Lei, Xu, Wanyu, Lan, Yihuai, Hu, Zhiqiang, Lan, Yunshi, Lee, Roy Ka-Wei, Lim, Ee-Peng | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/02a-routing.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md` |
| [arXiv:2305.16291](https://arxiv.org/abs/2305.16291) | Voyager: An Open-Ended Embodied Agent with Large Language Models<br>Authors: Wang, Guanzhi, Xie, Yuqi, Jiang, Yunfan, Mandlekar, Ajay, Xiao, Chaowei, Zhu, Yuke, Fan, Linxi, Anandkumar, Anima | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/03c-always-on.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2305.18290](https://arxiv.org/abs/2305.18290) | Direct Preference Optimization: Your Language Model is Secretly a Reward Model<br>Authors: Rafailov, Rafael, Sharma, Archit, Mitchell, Eric, Ermon, Stefano, Manning, Christopher D., Finn, Chelsea | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html` |
| [arXiv:2305.18323](https://arxiv.org/abs/2305.18323) | ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models<br>Authors: Xu, Binfeng, Peng, Zhiyuan, Lei, Bowen, Mukherjee, Subhabrata, Liu, Yuchen, Xu, Dongkuan | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/01b-react.html`<br>`web/nemoclaw/02a-routing.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/_materials.json`<br>`web/nemoclaw/mats/agent_field_guide.md`<br>`web/nemoclaw/mats/agentic_equilibrium.md`<br>`web/nemoclaw/mats/arxiv-2305.18323-rewoo.md`<br>`web/nemoclaw/mats/materials_index.json` |
| [arXiv:2306.05685](https://arxiv.org/abs/2306.05685) | Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena<br>Authors: Zheng, Lianmin, Chiang, Wei-Lin, Sheng, Ying, Zhuang, Siyuan, Wu, Zhanghao, Zhuang, Yonghao, Lin, Zi, Li, Zhuohan, Li, Dacheng, Xing, Eric P., Zhang, Hao, Gonzalez, Joseph E., Stoica, Ion | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2306.16354](https://arxiv.org/abs/2306.16354) | cuSLINK: Single-linkage Agglomerative Clustering on the GPU<br>Authors: Nolet, Corey J., Gala, Divye, Fender, Alex, Doijade, Mahesh, Eaton, Joe, Raff, Edward, Zedlewski, John, Rees, Brad, Oates, Tim | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/mats/glossary_raw/vector-database.md` |
| [arXiv:2307.03172](https://arxiv.org/abs/2307.03172) | Lost in the Middle: How Language Models Use Long Contexts<br>Authors: Liu, Nelson F., Lin, Kevin, Hewitt, John, Paranjape, Ashwin, Bevilacqua, Michele, Petroni, Fabio, Liang, Percy | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/01b-react.html`<br>`web/nemoclaw/02c-deep.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2307.09702](https://arxiv.org/abs/2307.09702) | Efficient Guided Generation for Large Language Models<br>Authors: Willard, Brandon T., Louf, Rémi | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2308.00352](https://arxiv.org/abs/2308.00352) | MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework<br>Authors: Hong, Sirui, Zhuge, Mingchen, Chen, Jiaqi, Zheng, Xiawu, Cheng, Yuheng, Zhang, Ceyao, Wang, Jinlin, Wang, Zili, Yau, Steven Ka Shing, Lin, Zijuan, Zhou, Liyang, Ran, Chenyu, Xiao, Lingfeng, Wu, Chenglin, Schmidhuber, Jürgen | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2308.08155](https://arxiv.org/abs/2308.08155) | AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation<br>Authors: Wu, Qingyun, Bansal, Gagan, Zhang, Jieyu, Wu, Yiran, Li, Beibin, Zhu, Erkang, Jiang, Li, Zhang, Xiaoyun, Zhang, Shaokun, Liu, Jiale, Awadallah, Ahmed Hassan, White, Ryen W, Burger, Doug, Wang, Chi | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2308.15136](https://arxiv.org/abs/2308.15136) | CAGRA: Highly Parallel Graph Construction and Approximate Nearest Neighbor Search for GPUs<br>Authors: Ootomo, Hiroyuki, Naruse, Akira, Nolet, Corey, Wang, Ray, Feher, Tamas, Wang, Yong | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/mats/glossary_raw/vector-database.md` |
| [arXiv:2310.08560](https://arxiv.org/abs/2310.08560) | MemGPT: Towards LLMs as Operating Systems<br>Authors: Packer, Charles, Wooders, Sarah, Lin, Kevin, Fang, Vivian, Patil, Shishir G., Stoica, Ion, Gonzalez, Joseph E. | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/03b-openclaw.html`<br>`web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agent_field_guide.md` |
| [arXiv:2312.06674](https://arxiv.org/abs/2312.06674) | Llama Guard: LLM-based Input-Output Safeguard for Human-AI Conversations<br>Authors: Inan, Hakan, Upasani, Kartikeya, Chi, Jianfeng, Rungta, Rashi, Iyer, Krithika, Mao, Yuning, Tontchev, Michael, Hu, Qing, Fuller, Brian, Testuggine, Davide, Khabsa, Madian | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html` |
| [arXiv:2403.02419](https://arxiv.org/abs/2403.02419) | Are More LLM Calls All You Need? Towards Scaling Laws of Compound Inference Systems<br>Authors: Chen, Lingjiao, Davis, Jared Quincy, Hanin, Boris, Bailis, Peter, Stoica, Ion, Zaharia, Matei, Zou, James | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2404.06654](https://arxiv.org/abs/2404.06654) | RULER: What's the Real Context Size of Your Long-Context Language Models?<br>Authors: Hsieh, Cheng-Ping, Sun, Simeng, Kriman, Samuel, Acharya, Shantanu, Rekesh, Dima, Jia, Fei, Zhang, Yang, Ginsburg, Boris | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2404.16130](https://arxiv.org/abs/2404.16130) | From Local to Global: A Graph RAG Approach to Query-Focused Summarization<br>Authors: Edge, Darren, Trinh, Ha, Cheng, Newman, Bradley, Joshua, Chao, Alex, Mody, Apurva, Truitt, Steven, Metropolitansky, Dasha, Ness, Robert Osazuwa, Larson, Jonathan | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/02b-rag.html`<br>`web/nemoclaw/mats/_materials.json`<br>`web/nemoclaw/mats/arxiv-2404.16130-graphrag.md`<br>`web/nemoclaw/mats/materials_index.json` |
| [arXiv:2502.12110](https://arxiv.org/abs/2502.12110) | A-MEM: Agentic Memory for LLM Agents<br>Authors: Xu, Wujiang, Liang, Zujie, Mei, Kai, Gao, Hang, Tan, Juntao, Zhang, Yongfeng | [arXiv perpetual, non-exclusive distribution license 1.0](https://arxiv.org/licenses/nonexclusive-distrib/1.0/) | This grants arXiv distribution rights and does not grant third parties permission to reuse or adapt the paper. | 2026-07-08 | `web/nemoclaw/04c-going-further.html` |
| [arXiv:2503.13657](https://arxiv.org/abs/2503.13657) | Why Do Multi-Agent LLM Systems Fail?<br>Authors: Cemri, Mert, Pan, Melissa Z., Yang, Shuyi, Agrawal, Lakshya A., Chopra, Bhavya, Tiwari, Rishabh, Keutzer, Kurt, Parameswaran, Aditya, Klein, Dan, Ramchandran, Kannan, Zaharia, Matei, Gonzalez, Joseph E., Stoica, Ion | [CC-BY-NC-ND-4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/) | Only attributed, noncommercial sharing of unadapted copies is allowed. | 2026-07-08 | `web/nemoclaw/04c-going-further.html`<br>`web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2507.09089](https://arxiv.org/abs/2507.09089) | Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity<br>Authors: Becker, Joel, Rush, Nate, Barnes, Elizabeth, Rein, David | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/mats/agentic_equilibrium.md` |
| [arXiv:2510.09023](https://arxiv.org/abs/2510.09023) | The Attacker Moves Second: Stronger Adaptive Attacks Bypass Defenses Against Llm Jailbreaks and Prompt Injections<br>Authors: Nasr, Milad, Carlini, Nicholas, Sitawarin, Chawin, Schulhoff, Sander V., Hayes, Jamie, Ilie, Michael, Pluto, Juliette, Song, Shuang, Chaudhari, Harsh, Shumailov, Ilia, Thakurta, Abhradeep, Xiao, Kai Yuanqing, Terzis, Andreas, Tramèr, Florian | [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/) | Reuse and adaptation are allowed, including commercially, with attribution. | 2026-07-08 | `web/nemoclaw/mats/agentic_equilibrium.md` |

### NVIDIA documents used as course sources

| Document | Published author(s) | Source terms | Relationship | Repository items | Evidence checked |
|---|---|---|---|---|---|
| [NemoClaw for OpenClaw blueprint card](https://build.nvidia.com/nvidia/nemoclaw-for-openclaw/nemoclawcard)<br>[Displayed image](https://assets.ngc.nvidia.com/products/api-catalog/images/nemoclaw-for-openclaw.jpg) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | remote display | `web/nemoclaw/index.html`<br>`i18n/es/web/nemoclaw/index.html`<br>`i18n/pt/web/nemoclaw/index.html` | 2026-07-25 |
| [RAG 101: Demystifying Retrieval-Augmented Generation Pipelines](https://developer.nvidia.com/blog/rag-101-demystifying-retrieval-augmented-generation-pipelines/) | [Hayden Wolff](https://developer.nvidia.com/blog/author/hwolff/) | (c) NVIDIA; no reuse license stated on source page | recreation | `web/nemoclaw/assets/figures/02b-rag-1.svg` | 2026-07-10 |
| [Tips for Building a RAG Pipeline with NVIDIA AI LangChain AI Endpoints](https://developer.nvidia.com/blog/tips-for-building-a-rag-pipeline-with-nvidia-ai-langchain-ai-endpoints/) | Amit Bleiweiss | (c) NVIDIA; no reuse license stated on source page | recreation | `web/nemoclaw/assets/figures/02b-rag-1.svg` | 2026-07-10 |
| [Agentic AI Learning Path](https://developer.nvidia.com/topics/ai/agentic-ai-learning-path/) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | compilation | `web/nemoclaw/mats/agentic_ai_learning_path_links.md` | 2026-07-08 |
| [Run Hermes Agent with Local Models](https://build.nvidia.com/spark/hermes-agent/overview) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/build-nvidia-com-spark-hermes-agent-overview.md` | 2026-07-08 |
| [Set Up Example NemoClaw Agents](https://build.nvidia.com/spark/nemoclaw-applications) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/build-nvidia-com-spark-nemoclaw-applications.md` | 2026-07-08 |
| [Run NemoClaw with a Local LLM](https://build.nvidia.com/spark/nemoclaw/instructions) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/build-nvidia-com-spark-nemoclaw-instructions.md` | 2026-07-08 |
| [Deploy Self-Evolving Agents for Faster, More Secure Research with a Hermes Agent and NVIDIA NemoClaw](https://developer.nvidia.com/blog/deploy-self-evolving-agents-for-faster-more-secure-research-with-a-hermes-agent-and-nvidia-nemoclaw/) | [Sam Pastoriza](https://developer.nvidia.com/blog/author/spastoriza/) | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/developer-nvidia-com-blog-deploy-self-evolving-agents-for-fa.md` | 2026-07-08 |
| [NVIDIA AI glossary](https://www.nvidia.com/en-us/glossary/) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | compilation | `web/nemoclaw/mats/glossary_raw/README.md`<br>`web/nemoclaw/mats/glossary_raw/_versions.json`<br>`web/nemoclaw/mats/nvidia_agent_glossary.md` | 2026-07-08 |
| [AI Agents](https://www.nvidia.com/en-us/glossary/ai-agents/) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/glossary_raw/ai-agents.md`<br>`web/nemoclaw/mats/glossary_raw/images/ai-agents-1.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/ai-agents-2.svg`<br>`web/nemoclaw/mats/glossary_raw/images/ai-agents-3.svg`<br>`web/nemoclaw/mats/glossary_raw/images/ai-agents-4.svg` | 2026-07-08 |
| [AI Inference](https://www.nvidia.com/en-us/glossary/ai-inference/) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/glossary_raw/ai-inference.md`<br>`web/nemoclaw/mats/glossary_raw/images/ai-inference-1.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/ai-inference-2.svg`<br>`web/nemoclaw/mats/glossary_raw/images/ai-inference-3.jpeg` | 2026-07-08 |
| [AI Reasoning](https://www.nvidia.com/en-us/glossary/ai-reasoning/) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/glossary_raw/ai-reasoning.md`<br>`web/nemoclaw/mats/glossary_raw/images/ai-reasoning-1.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/ai-reasoning-2.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/ai-reasoning-3.jpeg` | 2026-07-08 |
| [Deep Agents](https://www.nvidia.com/en-us/glossary/deep-agents/) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/glossary_raw/deep-agents.md`<br>`web/nemoclaw/mats/glossary_raw/images/deep-agents-1.png`<br>`web/nemoclaw/mats/glossary_raw/images/deep-agents-2.png` | 2026-07-08 |
| [Large Language Models](https://www.nvidia.com/en-us/glossary/large-language-models/) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/glossary_raw/large-language-models.md`<br>`web/nemoclaw/mats/glossary_raw/images/large-language-models-1.svg`<br>`web/nemoclaw/mats/glossary_raw/images/large-language-models-2.svg`<br>`web/nemoclaw/mats/glossary_raw/images/large-language-models-3.svg` | 2026-07-08 |
| [Retrieval-Augmented Generation](https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/glossary_raw/retrieval-augmented-generation.md`<br>`web/nemoclaw/mats/glossary_raw/images/retrieval-augmented-generation-1.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/retrieval-augmented-generation-2.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/retrieval-augmented-generation-3.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/retrieval-augmented-generation-4.jpeg` | 2026-07-08 |
| [Vector Database](https://www.nvidia.com/en-us/glossary/vector-database/) | No author listed on the official source page | (c) NVIDIA; no reuse license stated on source page | conversion | `web/nemoclaw/mats/glossary_raw/vector-database.md`<br>`web/nemoclaw/mats/glossary_raw/images/vector-database-1.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/vector-database-2.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/vector-database-3.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/vector-database-4.jpeg`<br>`web/nemoclaw/mats/glossary_raw/images/vector-database-5.jpeg` | 2026-07-08 |

## Third-party course-material relationships

This is not a dependency table. It records every provenance row with an external source URL. `inspiration` and `summary` mean the external work is referenced but not copied; `recreation` or `conversion` requires the recorded redistribution disposition to be reviewed. The exact source labels are preserved rather than converted into SPDX identifiers when the source is not OSS.

| Repository file | Relationship | External source | Recorded terms | Source |
|---|---|---|---|---|
| web/nemoclaw/assets/favicon.ico | provided course asset | NVIDIA corporate favicon | NVIDIA Logo and Brand Guidelines; trademark rights reserved | [source](https://www.nvidia.com/favicon.ico); [terms](https://www.nvidia.com/en-us/about-nvidia/legal-info/logo-brand-usage/) |
| web/nemoclaw/index.html | remote display | NVIDIA NemoClaw for OpenClaw image | (c) NVIDIA; no reuse license stated on source page | [source](https://build.nvidia.com/nvidia/nemoclaw-for-openclaw/nemoclawcard) |
| i18n/es/web/nemoclaw/index.html | remote display | NVIDIA NemoClaw for OpenClaw image | (c) NVIDIA; no reuse license stated on source page | [source](https://build.nvidia.com/nvidia/nemoclaw-for-openclaw/nemoclawcard) |
| i18n/pt/web/nemoclaw/index.html | remote display | NVIDIA NemoClaw for OpenClaw image | (c) NVIDIA; no reuse license stated on source page | [source](https://build.nvidia.com/nvidia/nemoclaw-for-openclaw/nemoclawcard) |
| web/nemoclaw/assets/figures/01a-loop-1.svg | inspiration | Russell & Norvig, AIMA ch.1 | (c) Pearson; no reuse license stated | [source](https://aima.cs.berkeley.edu/) |
| web/nemoclaw/assets/figures/01a-loop-2.svg | inspiration | OpenAI API docs | OpenAI terms | [source](https://platform.openai.com/docs) |
| web/nemoclaw/assets/figures/01b-react-1.svg | original | original course diagram; ReAct (Yao et al. 2022) | CC-BY-4.0 | [source](https://arxiv.org/abs/2210.03629) |
| web/nemoclaw/assets/figures/01b-react-2.svg | recreation | Lilian Weng, LLM-Powered Autonomous Agents | no reuse license stated | [source](https://lilianweng.github.io/posts/2023-06-23-agent/) |
| web/nemoclaw/assets/figures/01b-react-3.svg | inspiration | original course diagram; ReAct (Yao et al. 2022) | CC-BY-4.0 | [source](https://arxiv.org/abs/2210.03629) |
| web/nemoclaw/assets/figures/01b-react-4.svg | inspiration | original course diagram; inspired by Liu et al. 2023 | arXiv perpetual, non-exclusive distribution license 1.0 | [source](https://arxiv.org/abs/2307.03172) |
| web/nemoclaw/assets/figures/01c-tools-2.svg | original | original course diagram; MCP | Apache-2.0 | [source](https://modelcontextprotocol.io) |
| web/nemoclaw/assets/figures/02b-rag-1.svg | recreation | NVIDIA developer blog diagrams by Hayden Wolff and Amit Bleiweiss | (c) NVIDIA; no reuse license stated on source page | [source](https://developer.nvidia.com/blog/rag-101-demystifying-retrieval-augmented-generation-pipelines/) |
| web/nemoclaw/assets/figures/02b-rag-3.svg | recreation | Edge et al. 2024 | CC-BY-4.0 | [source](https://arxiv.org/abs/2404.16130) |
| web/nemoclaw/assets/figures/fig2_react.svg | conversion | Xu et al. 2023, ReWOO Figure 2(a); ReAct concept from Yao et al. 2022 | CC-BY-4.0 | [source](https://arxiv.org/abs/2305.18323) |
| web/nemoclaw/assets/figures/fig2_rewoo.svg | conversion | Xu et al. 2023; figure conversion | CC-BY-4.0 | [source](https://arxiv.org/abs/2305.18323) |
| web/nemoclaw/assets/figures/lethal-trifecta.svg | original course graphic | course-provided graphic; Simon Willison lethal trifecta definition | Apache-2.0 | [source](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/) |
| web/nemoclaw/assets/figures/rag_arch_2021.svg | conversion | Lewis et al. 2020; figure conversion | arXiv perpetual, non-exclusive distribution license 1.0 | [source](https://arxiv.org/abs/2005.11401) |
| web/nemoclaw/mats/agentic_ai_learning_path_links.md | compilation | NVIDIA Agentic AI Learning Path | (c) NVIDIA; no reuse license stated on source page | [source](https://developer.nvidia.com/topics/ai/agentic-ai-learning-path/) |
| web/nemoclaw/mats/arxiv-2005.11401-rag.md | summary | Lewis et al. 2020 (RAG) | arXiv perpetual, non-exclusive distribution license 1.0 | [source](https://arxiv.org/abs/2005.11401) |
| web/nemoclaw/mats/arxiv-2210.03629-react.md | summary | Yao et al. 2022 (ReAct) | CC-BY-4.0 | [source](https://arxiv.org/abs/2210.03629) |
| web/nemoclaw/mats/arxiv-2305.18323-rewoo.md | summary | Xu et al. 2023 (ReWOO) | CC-BY-4.0 | [source](https://arxiv.org/abs/2305.18323) |
| web/nemoclaw/mats/arxiv-2404.16130-graphrag.md | summary | Edge et al. 2024 (GraphRAG) | CC-BY-4.0 | [source](https://arxiv.org/abs/2404.16130) |
| web/nemoclaw/mats/build-nvidia-com-spark-hermes-agent-overview.md | conversion | NVIDIA public page | (c) NVIDIA; no reuse license stated on source page | [source](https://build.nvidia.com/spark/hermes-agent/overview) |
| web/nemoclaw/mats/build-nvidia-com-spark-nemoclaw-applications.md | conversion | NVIDIA public page | (c) NVIDIA; no reuse license stated on source page | [source](https://build.nvidia.com/spark/nemoclaw-applications) |
| web/nemoclaw/mats/build-nvidia-com-spark-nemoclaw-instructions.md | conversion | NVIDIA public page | (c) NVIDIA; no reuse license stated on source page | [source](https://build.nvidia.com/spark/nemoclaw/instructions) |
| web/nemoclaw/mats/developer-nvidia-com-blog-deploy-self-evolving-agents-for-fa.md | conversion | NVIDIA public page | (c) NVIDIA; no reuse license stated on source page | [source](https://developer.nvidia.com/blog/deploy-self-evolving-agents-for-faster-more-secure-research-with-a-hermes-agent-and-nvidia-nemoclaw/) |
| web/nemoclaw/mats/glossary_raw/README.md | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/) |
| web/nemoclaw/mats/glossary_raw/_versions.json | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/) |
| web/nemoclaw/mats/glossary_raw/ai-agents.md | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-agents/) |
| web/nemoclaw/mats/glossary_raw/ai-inference.md | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-inference/) |
| web/nemoclaw/mats/glossary_raw/ai-reasoning.md | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-reasoning/) |
| web/nemoclaw/mats/glossary_raw/deep-agents.md | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/deep-agents/) |
| web/nemoclaw/mats/glossary_raw/images/ai-agents-1.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-agents/) |
| web/nemoclaw/mats/glossary_raw/images/ai-agents-2.svg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-agents/) |
| web/nemoclaw/mats/glossary_raw/images/ai-agents-3.svg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-agents/) |
| web/nemoclaw/mats/glossary_raw/images/ai-agents-4.svg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-agents/) |
| web/nemoclaw/mats/glossary_raw/images/ai-inference-1.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-inference/) |
| web/nemoclaw/mats/glossary_raw/images/ai-inference-2.svg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-inference/) |
| web/nemoclaw/mats/glossary_raw/images/ai-inference-3.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-inference/) |
| web/nemoclaw/mats/glossary_raw/images/ai-reasoning-1.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-reasoning/) |
| web/nemoclaw/mats/glossary_raw/images/ai-reasoning-2.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-reasoning/) |
| web/nemoclaw/mats/glossary_raw/images/ai-reasoning-3.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/ai-reasoning/) |
| web/nemoclaw/mats/glossary_raw/images/deep-agents-1.png | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/deep-agents/) |
| web/nemoclaw/mats/glossary_raw/images/deep-agents-2.png | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/deep-agents/) |
| web/nemoclaw/mats/glossary_raw/images/large-language-models-1.svg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/large-language-models/) |
| web/nemoclaw/mats/glossary_raw/images/large-language-models-2.svg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/large-language-models/) |
| web/nemoclaw/mats/glossary_raw/images/large-language-models-3.svg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/large-language-models/) |
| web/nemoclaw/mats/glossary_raw/images/retrieval-augmented-generation-1.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/) |
| web/nemoclaw/mats/glossary_raw/images/retrieval-augmented-generation-2.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/) |
| web/nemoclaw/mats/glossary_raw/images/retrieval-augmented-generation-3.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/) |
| web/nemoclaw/mats/glossary_raw/images/retrieval-augmented-generation-4.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/) |
| web/nemoclaw/mats/glossary_raw/images/vector-database-1.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/vector-database/) |
| web/nemoclaw/mats/glossary_raw/images/vector-database-2.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/vector-database/) |
| web/nemoclaw/mats/glossary_raw/images/vector-database-3.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/vector-database/) |
| web/nemoclaw/mats/glossary_raw/images/vector-database-4.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/vector-database/) |
| web/nemoclaw/mats/glossary_raw/images/vector-database-5.jpeg | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/vector-database/) |
| web/nemoclaw/mats/glossary_raw/large-language-models.md | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/large-language-models/) |
| web/nemoclaw/mats/glossary_raw/retrieval-augmented-generation.md | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/retrieval-augmented-generation/) |
| web/nemoclaw/mats/glossary_raw/vector-database.md | conversion | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/vector-database/) |
| web/nemoclaw/mats/nvidia_agent_glossary.md | compilation | NVIDIA AI glossary | (c) NVIDIA; no reuse license stated on source page | [source](https://www.nvidia.com/en-us/glossary/) |

## Deliberate exclusions

- Public URLs used only as links are not code dependencies and are not redistributed merely because the course links to them.
- NVIDIA-authored source files are governed by the root Apache-2.0 license and are not repeated in this third-party list.
- Exact transitive operating-system and container-layer packages are build outputs. Their authoritative list is the SBOM for the exact image digest, not an estimate copied from a mutable base image.
- This inventory records evidence; OSRB, Legal, and other accountable reviewers retain approval authority.
