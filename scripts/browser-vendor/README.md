# Browser dependency vendoring

This workspace pins the JavaScript packages shipped to learner browsers. The generated files live
under `web/nemoclaw/vendor/`; Pages and launchable builds copy that directory without contacting a
package registry.

To propose an update, install exactly the committed lock, regenerate, inspect package and license
changes, then run the mutation-tested audit:

```bash
cd scripts/browser-vendor
npm ci
cd ../..
scripts/runtime/run_node.sh scripts/build/vendor_browser_dependencies.mjs
python3 -m unittest discover -v -s tests/validation
python3 scripts/validation/course_dependency_integrity.py
```

Run the install in the repository's disposable Node container when host Node.js is absent. Do not
hand-edit generated vendor files or the dependency inventory. Reviewers must inspect lock changes,
the dashboard, licenses, bundle size, and browser behavior before accepting an update.

Highlight.js and js-yaml use minified files only because those exact browser distributions are
published in their pinned packages. CodeMirror core, styles, and reviewed modes are copied from the
publisher package without minification. The LangChain compatibility bundle is not minified, but it
remains classified as transformed because browser execution requires ESM/CommonJS interoperability.
The source-license contract rejects any repository-minified browser artifact.

The LangChain output is assembled by esbuild from `langchain-entry.js`. esbuild follows imports
through the pinned npm graph, supplies CommonJS-to-ESM interoperability, and emits one unminified
browser file. The manifest's `required_by` and `depends_on` fields preserve that graph; for example,
`p-queue@6.6.2` brings in `p-timeout@3.2.0`, which brings in `p-finally@1.0.0`.

`@langchain/core` also contains utility source that LangChain copied into its package rather than
declaring as separate npm dependencies. `embedded-component-evidence.json` identifies those copies,
the exact official LangChain tag and commit, their full licenses, and their source hashes. The build
uses esbuild's `legalComments: "external"` option, so comments marked for legal preservation move to
the adjacent `.LEGAL.txt` file. That file is supplemental attribution evidence, not a complete
package list or a replacement for the full licenses. Generation fails if a preserved comment lacks a
component mapping or if an expected mapped comment disappears.

CodeMirror is intentionally limited to CSS, HTML-mixed, JavaScript, Python, and XML. Adding or
replacing a mode changes the reviewed browser surface and must first update the allowlist in
`course_dependency_integrity.py`; the mutation suite rejects an unreviewed mode. The same audit
enforces supported package security floors, so regenerating from a downgraded lock still fails.
Tracked standalone projections use exact-version fallbacks with pinned integrity; the audit checks
their version, asset allowlist, and SRI alongside the same-origin course bundle.
Merge requests that change these inputs run the required `security_browser_sca` job. It records the
npm advisory result and reruns the offline dependency-integrity contract before review.
