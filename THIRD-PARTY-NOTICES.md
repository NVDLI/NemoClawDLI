# Third-party notices

This repository contains NVIDIA-authored course content and tooling under Apache-2.0 together with
third-party software and referenced or redistributed materials under their own terms.

Use these records to review the third-party scope:

- [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md) is the top-level inventory of software,
  source materials, license identifiers, attribution, distribution relationships, and evidence.
- [`web/nemoclaw/vendor/browser-dependencies.json`](web/nemoclaw/vendor/browser-dependencies.json)
  records each browser-delivered artifact, its packages, digest, source references, and whether the
  output is a transformed bundle or a byte-for-byte upstream copy.
- [`web/nemoclaw/vendor/licenses/`](web/nemoclaw/vendor/licenses/) contains the license text copied
  for every browser package and embedded source component represented in the generated vendor manifest.
- [`web/shared/vendor/browser-dependencies.json`](web/shared/vendor/browser-dependencies.json)
  records the course-neutral CodeMirror, Highlight.js, and Marked copies, including exact versions,
  licenses, digests, byte counts, and the already-reviewed publisher copy for each file.
- [`web/shared/vendor/licenses/`](web/shared/vendor/licenses/) contains the corresponding complete
  upstream license texts.
- [`scripts/browser-vendor/embedded-component-evidence.json`](scripts/browser-vendor/embedded-component-evidence.json)
  identifies utility source that LangChain copied into `@langchain/core`, pins the official LangChain
  tag and commit, and maps esbuild-preserved comments to full license evidence.
- [`scripts/compliance/docs/vendor_policy.md`](scripts/compliance/docs/vendor_policy.md) explains how
  to reproduce the vendor output and how new software or materials enter the repository.
- [`scripts/compliance/docs/browser_vendor_exceptions.json`](scripts/compliance/docs/browser_vendor_exceptions.json)
  is the machine-enforced record of the sole browser-code transformation exception.

## Browser vendor modification status

The browser vendor directory is generated from exact npm inputs. Each asset row records both
`modified_from_upstream` and `publisher_provided_minified`. A `.min.js`, `.min.mjs`, or `.min.css`
file is permitted only when that exact minified file was published in the pinned package and is
copied byte-for-byte. Repository tooling does not minify third-party browser code.

Publisher-provided minified files copied byte-for-byte:

- `highlight-11.10.0.min.js`
- `highlight-github-dark-11.10.0.min.css`
- `js-yaml-5.2.2.esm.min.js` (publisher `.mjs` bytes, renamed for portable static-host MIME handling)

Publisher-provided unminified files copied byte-for-byte:

- `codemirror-5.65.21.js` and `codemirror-5.65.21.css`
- `codemirror-mode-{xml,javascript,css,htmlmixed,python}-5.65.21.js`
- `codemirror-monokai-5.65.21.css`
- `marked-14.1.4.esm.js`

One browser compatibility exception remains: `langchain-1.4.7.esm.js`. Learner exercises need
`ChatOpenAI`, `tool`, `createReactAgent`, `MemorySaver`, and `z` through one same-origin ESM module.
The locked graph contains bare package imports and CommonJS-only dependencies (`base64-js@1.5.1`,
`eventemitter3@4.0.7`, `p-finally@1.0.0`, `p-queue@6.6.2`, and `p-timeout@3.2.0`) that a static
browser cannot resolve or execute directly. esbuild therefore supplies package resolution and
CommonJS-to-ESM interoperability. It does not minify the result, and no manual patch is permitted.
The manifest marks the file `modified_from_upstream: true` and binds it to the exact exception ID.

The generated `langchain-1.4.7.esm.js.LEGAL.txt` is not a dependency inventory. esbuild creates it
because the build sets `legalComments: "external"`; that setting moves specially marked source
comments into an adjacent file. Packages such as `p-timeout` have no such marked comment, but remain
fully inventoried through the npm dependency graph and CycloneDX SBOM. LangChain also embeds copied
Fast JSON Patch, js-sha256, sax-js, and String.fromCodePoint source. Those components and their full
licenses are recorded separately even when no preserved comment names them.

CI installs the pinned npm graph, byte-compares every non-exception asset with its publisher file,
regenerates the LangChain bundle, and fails if the working tree changes. The source-license gate
also fails unless the modified-asset set is exactly this one LangChain file.

This notice is an index, not a replacement for the license texts or source-specific evidence.
