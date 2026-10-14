# Shared browser asset provenance

`vendor/browser-dependencies.json` records every third-party file, version, license, digest, byte count, and reviewed repository copy. Each file is byte-identical to the corresponding publisher asset already validated under `web/nemoclaw/vendor/`. The shared location lets independent courses use the reviewed files without linking one course to another.

`favicon.ico` is the unmodified NVIDIA corporate favicon used by the existing browser course. NVIDIA Logo and Brand Guidelines and trademark rights apply. It is not third-party software and is not offered under Apache-2.0.

`runtime-workbench.css` and `runtime-workbench.js` are NVIDIA-authored Apache-2.0 course interface primitives. They keep runtime-tool disclosure and focus behavior consistent across independent browser courses and the executable Pyodide reference. They do not contain a runtime, credential, service endpoint, or third-party source.

`activity-sdk.js` is NVIDIA-authored, hand-maintained browser JavaScript under the repository Apache-2.0 license. Courses import this ES module directly; it is not a packaged or generated SDK distribution. Course milestone definitions and producer evidence remain in `web/nemoclaw/activity_milestones.json`, documented by its course-home `ACTIVITY_MILESTONES.md`. The course adapter supplies the config URL at session initialization alongside consent policy. The shared client loads and validates this JSON, copies API definitions, scopes sessions to that snapshot, and binds configured success events to real page targets. It contains no course-specific definitions or event names.
