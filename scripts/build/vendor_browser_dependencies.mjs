#!/usr/bin/env node
// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Copy publisher browser distributions and build the one compatibility bundle
// that cannot execute from upstream package files in a browser.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const workspace = path.join(root, "scripts/browser-vendor");
const modules = path.join(workspace, "node_modules");
const vendor = path.join(root, "web/nemoclaw/vendor");
const lockPath = path.join(workspace, "package-lock.json");
const packagePath = path.join(workspace, "package.json");
const exceptionPolicyRelative = "scripts/compliance/docs/browser_vendor_exceptions.json";
const exceptionPolicyPath = path.join(root, exceptionPolicyRelative);
const embeddedEvidenceRelative = "scripts/browser-vendor/embedded-component-evidence.json";
const embeddedEvidencePath = path.join(root, embeddedEvidenceRelative);

if (!fs.existsSync(lockPath) || !fs.existsSync(path.join(modules, "esbuild"))) {
  throw new Error("run npm ci under scripts/browser-vendor before regenerating");
}

const { build } = await import(pathToFileURL(path.join(modules, "esbuild/lib/main.js")));
const lock = JSON.parse(fs.readFileSync(lockPath, "utf8"));
const direct = JSON.parse(fs.readFileSync(packagePath, "utf8")).dependencies;
const exceptionPolicyBytes = fs.readFileSync(exceptionPolicyPath);
const exceptionPolicy = JSON.parse(exceptionPolicyBytes);
const embeddedEvidenceBytes = fs.readFileSync(embeddedEvidencePath);
const embeddedEvidence = JSON.parse(embeddedEvidenceBytes);
if (exceptionPolicy.schema !== "nemoclaw-browser-modification-exceptions/1"
    || exceptionPolicy.exceptions?.length !== 1) {
  throw new Error("browser vendor policy must declare exactly one modification exception");
}
const [langchainException] = exceptionPolicy.exceptions;
if (langchainException.asset !== "langchain-1.4.7.esm.js"
    || langchainException.entrypoint !== "scripts/browser-vendor/langchain-entry.js"
    || langchainException.publisher_provided_minified !== false) {
  throw new Error("the sole browser modification exception must remain the unminified LangChain interoperability bundle");
}
if (embeddedEvidence.schema !== "nemoclaw-embedded-browser-components/1"
    || embeddedEvidence.parent?.package !== "@langchain/core"
    || embeddedEvidence.parent?.version !== "1.1.48"
    || embeddedEvidence.parent?.source_commit !== "caad0914f068477293009dbf27a220fa96bdc4b8"
    || !Array.isArray(embeddedEvidence.components)
    || !embeddedEvidence.components.length
    || new Set(embeddedEvidence.components.map(component => component.id)).size !== embeddedEvidence.components.length) {
  throw new Error("embedded LangChain component evidence must remain pinned to the reviewed @langchain/core 1.1.48 source");
}
const codemirrorVersion = direct.codemirror;
const codemirrorBase = `codemirror-${codemirrorVersion}`;
fs.mkdirSync(vendor, { recursive: true });
for (const item of fs.readdirSync(vendor, { withFileTypes: true })) {
  if (item.name === "SKILL.html" || item.name === "licenses") continue;
  fs.rmSync(path.join(vendor, item.name), { recursive: true, force: true });
}
fs.mkdirSync(path.join(vendor, "licenses"), { recursive: true });
for (const item of fs.readdirSync(path.join(vendor, "licenses"), { withFileTypes: true })) {
  if (item.name === "SKILL.html") continue;
  fs.rmSync(path.join(vendor, "licenses", item.name), { recursive: true, force: true });
}

const output = name => path.join(vendor, name);
const buildResult = async (entry, outfile, options = {}) => build({
  entryPoints: [path.join(workspace, entry)],
  outfile: output(outfile),
  bundle: true,
  minify: false,
  platform: "browser",
  target: "es2022",
  legalComments: "external",
  metafile: true,
  ...options,
});

const langchain = await buildResult(
  path.relative(workspace, path.join(root, langchainException.entrypoint)),
  langchainException.asset,
  { format: "esm" },
);

const copies = [
  ["@highlightjs/cdn-assets/highlight.min.js", "highlight-11.10.0.min.js"],
  ["@highlightjs/cdn-assets/styles/github-dark.min.css", "highlight-github-dark-11.10.0.min.css"],
  ["js-yaml/dist/browser/js-yaml.esm.min.mjs", "js-yaml-5.2.1.esm.min.js"],
  ["codemirror/lib/codemirror.js", `${codemirrorBase}.js`],
  ["codemirror/lib/codemirror.css", `${codemirrorBase}.css`],
  ["codemirror/theme/monokai.css", `codemirror-monokai-${codemirrorVersion}.css`],
  ["codemirror/mode/xml/xml.js", `codemirror-mode-xml-${codemirrorVersion}.js`],
  ["codemirror/mode/javascript/javascript.js", `codemirror-mode-javascript-${codemirrorVersion}.js`],
  ["codemirror/mode/css/css.js", `codemirror-mode-css-${codemirrorVersion}.js`],
  ["codemirror/mode/htmlmixed/htmlmixed.js", `codemirror-mode-htmlmixed-${codemirrorVersion}.js`],
  ["codemirror/mode/python/python.js", `codemirror-mode-python-${codemirrorVersion}.js`],
  ["marked/lib/marked.esm.js", "marked-14.1.4.esm.js"],
];
for (const [source, target] of copies) {
  fs.copyFileSync(path.join(modules, source), output(target));
}

function packageRoot(input) {
  const parts = input.split("/");
  const indexes = parts.map((part, index) => part === "node_modules" ? index : -1).filter(index => index >= 0);
  const index = indexes.at(-1);
  if (index === undefined) return null;
  const first = indexes[0];
  const count = parts[index + 1]?.startsWith("@") ? 2 : 1;
  return parts.slice(first, index + 1 + count).join("/");
}

function packagesFromMeta(meta) {
  return new Set(Object.keys(meta.inputs).map(packageRoot).filter(Boolean));
}

const packageRoots = new Set([
  "node_modules/@highlightjs/cdn-assets",
  "node_modules/codemirror",
  "node_modules/js-yaml",
  "node_modules/marked",
  ...packagesFromMeta(langchain.metafile),
]);

const purposes = {
  "@highlightjs/cdn-assets": "Publisher-built Highlight.js browser distribution for course syntax highlighting.",
  "codemirror": "Editable and read-only code cells.",
  "marked": "Markdown rendering for chat output and repository documents.",
  "js-yaml": "Parsing the live OpenShell policy returned to sandbox exercises.",
  "@langchain/openai": "OpenAI-compatible browser model client used by agent exercises.",
  "@langchain/core": "Tool and message primitives used by agent exercises.",
  "@langchain/langgraph": "Agent construction and checkpoint memory used by agent exercises.",
  "zod": "Tool argument schemas used by agent exercises.",
};

function packageName(packageRootPath) {
  const parts = packageRootPath.split("node_modules/").at(-1).split("/");
  return parts[0].startsWith("@") ? `${parts[0]}/${parts[1]}` : parts[0];
}

function licenseSource(packageRootPath, name) {
  const base = path.join(workspace, packageRootPath);
  for (const candidate of fs.readdirSync(base)) {
    if (/^licen[cs]e(?:\.|$)/i.test(candidate)) return path.join(base, candidate);
  }
  const override = path.join(workspace, "license-overrides", `${name.replaceAll("/", "__")}.txt`);
  if (fs.existsSync(override)) return override;
  throw new Error(`missing license text for bundled package ${name}`);
}

const packageEntries = [...packageRoots].map(packageRootPath => {
  const locked = lock.packages[packageRootPath];
  if (!locked?.version || !locked?.license) throw new Error(`incomplete lock metadata for ${packageRootPath}`);
  const name = packageName(packageRootPath);
  const filename = `${name.replaceAll("/", "__")}--${locked.version}.txt`;
  fs.copyFileSync(licenseSource(packageRootPath, name), path.join(vendor, "licenses", filename));
  const packageJson = JSON.parse(fs.readFileSync(path.join(workspace, packageRootPath, "package.json"), "utf8"));
  return { packageRootPath, record: {
    name,
    version: locked.version,
    license: locked.license,
    direct: Object.hasOwn(direct, name),
    purpose: purposes[name] || "Transitive code included by the browser agent bundle.",
    package_url: `https://www.npmjs.com/package/${name}`,
    homepage: packageJson.homepage || packageJson.repository?.url || packageJson.repository || null,
    resolved: locked.resolved,
    integrity: locked.integrity,
    license_file: `licenses/${filename}`,
    required_by: [],
    depends_on: [],
  } };
});

const entryByRoot = new Map(packageEntries.map(entry => [entry.packageRootPath, entry]));
function resolveIncludedDependency(parentRoot, dependencyName) {
  let cursor = parentRoot;
  while (true) {
    const candidate = `${cursor ? `${cursor}/` : ""}node_modules/${dependencyName}`;
    if (entryByRoot.has(candidate)) return entryByRoot.get(candidate);
    const marker = cursor.lastIndexOf("/node_modules/");
    if (marker >= 0) cursor = cursor.slice(0, marker);
    else if (cursor) cursor = "";
    else return null;
  }
}
for (const parent of packageEntries) {
  const dependencyNames = Object.keys(lock.packages[parent.packageRootPath]?.dependencies || {});
  for (const dependencyName of dependencyNames) {
    const child = resolveIncludedDependency(parent.packageRootPath, dependencyName);
    if (!child) continue;
    const parentLabel = `${parent.record.name}@${parent.record.version}`;
    const childLabel = `${child.record.name}@${child.record.version}`;
    parent.record.depends_on.push(childLabel);
    child.record.required_by.push(parentLabel);
  }
}
for (const entry of packageEntries) {
  entry.record.depends_on.sort();
  entry.record.required_by.sort();
}
const packages = packageEntries.map(entry => entry.record)
  .sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version));

const copiedEmbeddedLicenses = new Set();
const embeddedComponents = embeddedEvidence.components.map(component => {
  if (!component.id || !component.name || !component.version || !component.license
      || !component.license_input || !component.license_file || !component.source_files?.length) {
    throw new Error(`incomplete embedded component evidence: ${component.id || component.name || "unnamed"}`);
  }
  const licenseInput = path.join(root, component.license_input);
  if (!licenseInput.startsWith(path.join(workspace, "license-overrides") + path.sep)
      || !fs.existsSync(licenseInput)) {
    throw new Error(`embedded component license input is missing or outside the reviewed evidence directory: ${component.id}`);
  }
  const licenseOutput = output(component.license_file);
  if (!copiedEmbeddedLicenses.has(component.license_file)) {
    fs.copyFileSync(licenseInput, licenseOutput);
    copiedEmbeddedLicenses.add(component.license_file);
  } else if (!fs.existsSync(licenseOutput)
      || !fs.readFileSync(licenseOutput).equals(fs.readFileSync(licenseInput))) {
    throw new Error(`shared embedded license evidence differs: ${component.license_file}`);
  }
  const sourceHashes = component.source_files.map(source => {
    const sourcePath = path.join(workspace, source);
    if (!fs.existsSync(sourcePath)) throw new Error(`embedded source is missing from the pinned npm package: ${source}`);
    return {
      file: `scripts/browser-vendor/${source}`,
      sha256: crypto.createHash("sha256").update(fs.readFileSync(sourcePath)).digest("hex"),
    };
  });
  return {
    ...component,
    parent_package: `${embeddedEvidence.parent.package}@${embeddedEvidence.parent.version}`,
    relationship: "embedded-source-copied-by-upstream",
    source_commit: embeddedEvidence.parent.source_commit,
    source_hashes: sourceHashes,
    license_sha256: crypto.createHash("sha256").update(fs.readFileSync(licenseInput)).digest("hex"),
  };
}).sort((a, b) => a.name.localeCompare(b.name) || a.version.localeCompare(b.version));

const assetPackages = {
  "highlight-11.10.0.min.js": ["@highlightjs/cdn-assets"],
  "highlight-github-dark-11.10.0.min.css": ["@highlightjs/cdn-assets"],
  "js-yaml-5.2.1.esm.min.js": ["js-yaml"],
  [`${codemirrorBase}.js`]: ["codemirror"],
  [`${codemirrorBase}.css`]: ["codemirror"],
  [`codemirror-monokai-${codemirrorVersion}.css`]: ["codemirror"],
  [`codemirror-mode-xml-${codemirrorVersion}.js`]: ["codemirror"],
  [`codemirror-mode-javascript-${codemirrorVersion}.js`]: ["codemirror"],
  [`codemirror-mode-css-${codemirrorVersion}.js`]: ["codemirror"],
  [`codemirror-mode-htmlmixed-${codemirrorVersion}.js`]: ["codemirror"],
  [`codemirror-mode-python-${codemirrorVersion}.js`]: ["codemirror"],
  "marked-14.1.4.esm.js": ["marked"],
  [langchainException.asset]: [...packagesFromMeta(langchain.metafile)].map(packageName).sort(),
};

const assetProvenance = {
  "highlight-11.10.0.min.js": {
    distribution_form: "upstream-file-copy",
    modified_from_upstream: false,
    publisher_provided_minified: true,
    transformation: "Publisher-provided minified browser distribution copied byte-for-byte from the pinned npm package.",
    source_files: ["scripts/browser-vendor/node_modules/@highlightjs/cdn-assets/highlight.min.js"],
  },
  [langchainException.asset]: {
    distribution_form: "transformed-bundle",
    modified_from_upstream: true,
    publisher_provided_minified: false,
    modification_exception_id: langchainException.id,
    transformation: langchainException.transformation,
    source_files: [langchainException.entrypoint],
    embedded_components: embeddedComponents.map(component => component.id),
  },
  "js-yaml-5.2.1.esm.min.js": {
    distribution_form: "upstream-file-copy",
    modified_from_upstream: false,
    publisher_provided_minified: true,
    transformation: "Publisher-provided minified ESM browser distribution copied byte-for-byte from the pinned npm package; only the destination extension changes from .mjs to .js for portable static-host MIME handling.",
    source_files: ["scripts/browser-vendor/node_modules/js-yaml/dist/browser/js-yaml.esm.min.mjs"],
  },
  "highlight-github-dark-11.10.0.min.css": {
    distribution_form: "upstream-file-copy",
    modified_from_upstream: false,
    publisher_provided_minified: true,
    transformation: "Publisher-provided minified stylesheet copied byte-for-byte from the pinned npm package.",
    source_files: ["scripts/browser-vendor/node_modules/@highlightjs/cdn-assets/styles/github-dark.min.css"],
  },
  "marked-14.1.4.esm.js": {
    distribution_form: "upstream-file-copy",
    modified_from_upstream: false,
    publisher_provided_minified: false,
    transformation: "Copied byte-for-byte from the pinned npm package; only the destination filename is selected here.",
    source_files: ["scripts/browser-vendor/node_modules/marked/lib/marked.esm.js"],
  },
};

for (const [source, target] of copies) {
  if (assetProvenance[target]) continue;
  assetProvenance[target] = {
    distribution_form: "upstream-file-copy",
    modified_from_upstream: false,
    publisher_provided_minified: false,
    transformation: "Publisher-provided unminified source copied byte-for-byte from the pinned npm package.",
    source_files: [`scripts/browser-vendor/node_modules/${source}`],
  };
}

const sourceRoots = [path.join(root, "web"), path.join(root, "i18n")];
const sourceFiles = [];
function walk(directory) {
  if (!fs.existsSync(directory)) return;
  for (const item of fs.readdirSync(directory, { withFileTypes: true })) {
    const full = path.join(directory, item.name);
    const rel = path.relative(root, full).replaceAll(path.sep, "/");
    if (item.isDirectory()) {
      if (!rel.includes("/vendor") && !rel.includes("/standalone") && !rel.includes("/mats")) walk(full);
    } else if (/\.(?:html|js|mjs|css)$/.test(item.name)) {
      sourceFiles.push([rel, fs.readFileSync(full, "utf8")]);
    }
  }
}
sourceRoots.forEach(walk);

const assets = Object.keys(assetPackages).sort().map(file => {
  const bytes = fs.readFileSync(output(file));
  const provenance = assetProvenance[file];
  const references = [];
  for (const [source, text] of sourceFiles) {
    text.split(/\r?\n/).forEach((line, index) => {
      if (line.includes(file)) references.push({ source, line: index + 1 });
    });
  }
  references.sort((a, b) => a.source.localeCompare(b.source) || a.line - b.line);
  return {
    file,
    ...provenance,
    ...(provenance.modified_from_upstream ? {} : {
      upstream_sha256: crypto.createHash("sha256").update(
        fs.readFileSync(path.join(root, provenance.source_files[0])),
      ).digest("hex"),
    }),
    media_type: file.endsWith(".css") ? "text/css" : "text/javascript",
    bytes: bytes.length,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    packages: assetPackages[file],
    references,
  };
});

const noticeMappings = new Map();
for (const component of embeddedComponents) {
  for (const source of component.legal_notice_sources) {
    noticeMappings.set(source, { kind: "embedded-component", id: component.id, name: component.name });
  }
}
for (const mapping of embeddedEvidence.package_notice_mappings || []) {
  const pkg = packages.find(item => item.name === mapping.package && item.version === mapping.version);
  if (!pkg) throw new Error(`legal notice mapping refers to an unbundled package: ${mapping.package}@${mapping.version}`);
  for (const source of mapping.legal_notice_sources || []) {
    noticeMappings.set(source, { kind: "npm-package", name: pkg.name, version: pkg.version });
  }
}
const legalNotices = fs.readdirSync(vendor).filter(file => file.endsWith(".LEGAL.txt")).sort().map(file => {
  const bytes = fs.readFileSync(output(file));
  const text = bytes.toString("utf8");
  const sources = [...text.matchAll(/^([^\n]+):\n(?=\s{2}[/*])/gm)].map(match => match[1]);
  const unmapped = sources.filter(source => !noticeMappings.has(source));
  if (unmapped.length) throw new Error(`unmapped esbuild legal notice section(s): ${unmapped.join(", ")}`);
  return {
    file,
    bytes: bytes.length,
    sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
    explanation: "esbuild moved source comments marked for legal preservation into this file; it is supplemental attribution evidence, not the package or component inventory.",
    sources: sources.map(source => ({ source, ...noticeMappings.get(source) })),
  };
});
const observedNoticeSources = new Set(legalNotices.flatMap(notice => notice.sources.map(row => row.source)));
const missingNoticeSources = [...noticeMappings.keys()].filter(source => !observedNoticeSources.has(source));
if (missingNoticeSources.length) {
  throw new Error(`expected esbuild legal notice section(s) disappeared: ${missingNoticeSources.join(", ")}`);
}

function purl(name, version) {
  if (name.startsWith("@")) {
    const [scope, packageName] = name.split("/");
    return `pkg:npm/${encodeURIComponent(scope)}/${packageName}@${version}`;
  }
  return `pkg:npm/${name}@${version}`;
}

const sbomPath = output("browser-sbom.cdx.json");
const packageComponents = packages.map(item => ({
  type: "library",
  name: item.name,
  version: item.version,
  purl: purl(item.name, item.version),
  "bom-ref": purl(item.name, item.version),
  licenses: [{ license: { id: item.license } }],
  properties: [
    { name: "nemoclaw:relationship", value: item.direct ? "direct" : "transitive" },
    { name: "nemoclaw:required-by", value: item.required_by.join(", ") || "course browser entry" },
  ],
}));
const embeddedSbomComponents = embeddedComponents.map(item => ({
  type: "library",
  name: item.name,
  version: item.version,
  "bom-ref": `embedded:${item.id}`,
  licenses: [{ license: { id: item.license } }],
  externalReferences: [
    { type: "website", url: item.upstream_url },
    { type: "vcs", url: item.langchain_source_url },
    { type: "license", url: item.license_source_url },
  ],
  properties: [
    { name: "nemoclaw:relationship", value: item.relationship },
    { name: "nemoclaw:parent-package", value: item.parent_package },
    { name: "nemoclaw:version-note", value: item.version_note },
    { name: "nemoclaw:source-commit", value: item.source_commit },
  ],
}));
const packageByLabel = new Map(packages.map(item => [`${item.name}@${item.version}`, item]));
const sbomDependencies = [
  {
    ref: "nemoclaw-student-browser-runtime",
    dependsOn: packages.filter(item => item.direct).map(item => purl(item.name, item.version)).sort(),
  },
  ...packages.map(item => ({
    ref: purl(item.name, item.version),
    dependsOn: [
      ...item.depends_on.map(label => {
        const dependency = packageByLabel.get(label);
        return purl(dependency.name, dependency.version);
      }),
      ...(item.name === embeddedEvidence.parent.package && item.version === embeddedEvidence.parent.version
        ? embeddedComponents.map(component => `embedded:${component.id}`) : []),
    ].sort(),
  })),
  ...embeddedComponents.map(item => ({ ref: `embedded:${item.id}`, dependsOn: [] })),
];
const sbom = {
  bomFormat: "CycloneDX",
  specVersion: "1.6",
  version: 1,
  metadata: {
    component: {
      type: "application",
      name: "nemoclaw-student-browser-runtime",
      version: "source",
      "bom-ref": "nemoclaw-student-browser-runtime",
    },
  },
  components: [...packageComponents, ...embeddedSbomComponents],
  dependencies: sbomDependencies,
};
fs.writeFileSync(sbomPath, JSON.stringify(sbom, null, 2) + "\n");
const sbomBytes = fs.readFileSync(sbomPath);

const manifest = {
  schema: "nemoclaw-browser-dependencies/1",
  delivery: "same-origin-vendored",
  generated_from: [
    "scripts/browser-vendor/package.json",
    "scripts/browser-vendor/package-lock.json",
    "scripts/browser-vendor/langchain-entry.js",
    embeddedEvidenceRelative,
    exceptionPolicyRelative,
    "web/ and i18n/ runtime references",
  ],
  modification_exception_policy: {
    file: exceptionPolicyRelative,
    sha256: crypto.createHash("sha256").update(exceptionPolicyBytes).digest("hex"),
    exception_ids: exceptionPolicy.exceptions.map(item => item.id),
  },
  lock_sha256: crypto.createHash("sha256").update(fs.readFileSync(lockPath)).digest("hex"),
  packages,
  embedded_components: embeddedComponents,
  embedded_component_evidence: {
    file: embeddedEvidenceRelative,
    sha256: crypto.createHash("sha256").update(embeddedEvidenceBytes).digest("hex"),
    parent: embeddedEvidence.parent,
    explanation: embeddedEvidence.explanation,
  },
  assets,
  legal_notices: legalNotices,
  sbom: {
    file: "browser-sbom.cdx.json",
    bytes: sbomBytes.length,
    sha256: crypto.createHash("sha256").update(sbomBytes).digest("hex"),
    component_count: packages.length + embeddedComponents.length,
  },
};
fs.writeFileSync(output("browser-dependencies.json"), JSON.stringify(manifest, null, 2) + "\n");
console.log(`browser vendor: ${packages.length} npm packages + ${embeddedComponents.length} embedded components, ${assets.length} assets -> web/nemoclaw/vendor/`);
