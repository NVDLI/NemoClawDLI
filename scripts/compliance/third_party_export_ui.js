// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/* Interactive SWIPAT preview for scripts/compliance/SKILL.html. */
(function () {
  "use strict";

  var HEADER = [
    "Package / Component Name",
    "Version",
    "License",
    "Link to Component's License",
    "Method of Distribution",
    "Usage Method with NV proprietary code",
    "Comments",
    "Location where component was downloaded from",
    "Link to internal IT Controlled Repository"
  ];
  var OTHER = "Other (Please describe in Comments)";
  var INTERNAL = "Internal Use Only";
  var SCOPE_HEADER = [
    "Repository Item", "Scope Category", "Artifact Relationship",
    "Distributed by NVIDIA in This Repository", "Executed in Learner Browser",
    "External Source or Package", "Recorded License or Terms",
    "Source Author(s)", "License or Author Evidence",
    "Corroborating Repository Evidence", "Legal Scope Note"
  ];

  function parseLinks(text) {
    var out = [], pattern = /\[([^\]]+)]\(([^)]+)\)/g, match;
    while ((match = pattern.exec(text || ""))) out.push({ label: match[1], url: match[2] });
    return out;
  }

  function section(markdown, heading) {
    var marker = "## " + heading;
    var start = markdown.indexOf(marker);
    if (start < 0) return "";
    var body = markdown.slice(start + marker.length);
    var end = body.indexOf("\n## ");
    return end < 0 ? body : body.slice(0, end);
  }

  function tableRows(markdown, heading) {
    return section(markdown, heading).split(/\r?\n/).filter(function (line) {
      return line.charAt(0) === "|" && !/^\|[|\s:-]+\|?$/.test(line);
    }).map(function (line) {
      return line.replace(/^\||\|$/g, "").split("|").map(function (value) { return value.trim(); });
    }).filter(function (row) {
      return row[0] !== "Scope" && row[0] !== "Repository file" && row[0] !== "Identifier";
    });
  }

  function repoFile(config, path) {
    var blob = /github\.com/i.test(config.repository) ? "/blob/" : "/-/blob/";
    return config.repository.replace(/\/$/, "") + blob +
      encodeURIComponent(config.project_ref).replace(/%2F/g, "/") + "/" +
      path.split("/").map(encodeURIComponent).join("/");
  }

  function npmPage(name, version) {
    return "https://www.npmjs.com/package/" + name.split("/").map(encodeURIComponent).join("/") +
      "/v/" + encodeURIComponent(version);
  }

  function assetIndex(manifest) {
    var out = {};
    (manifest.assets || []).forEach(function (asset) {
      (asset.packages || []).forEach(function (name) {
        if (!out[name]) out[name] = [];
        out[name].push(asset.file);
      });
    });
    return out;
  }

  function vendoredRows(manifest, config) {
    var assets = assetIndex(manifest);
    var packages = (manifest.packages || []).map(function (pkg) {
      var licensePath = "web/nemoclaw/vendor/" + pkg.license_file;
      var relationship = pkg.direct ? "direct" : "transitive";
      var source = pkg.direct ? "This project selected it directly." : "Another browser package requires it.";
      return {
        category: "vendored",
        relationship: relationship,
        cells: [
          pkg.name,
          String(pkg.version),
          pkg.license,
          repoFile(config, licensePath),
          OTHER,
          OTHER,
          "Learners receive this code as part of the browser course. " + source +
            " Relationship: " + relationship + ". Used for: " + pkg.purpose + " Browser file(s): " +
            ((assets[pkg.name] || []).sort().join(", ") || "shared browser bundle") + ". " +
            "Used with NVIDIA-authored Apache-2.0 course source; no proprietary-code claim.",
          npmPage(pkg.name, String(pkg.version)),
          repoFile(config, licensePath)
        ]
      };
    });
    var embedded = (manifest.embedded_components || []).map(function (component) {
      var licensePath = "web/nemoclaw/vendor/" + component.license_file;
      return {
        category: "vendored",
        relationship: "embedded-source",
        cells: [
          component.name,
          String(component.version),
          component.license,
          repoFile(config, licensePath),
          OTHER,
          OTHER,
          "Learners receive this code inside the LangChain browser bundle. LangChain copied the utility source into " +
            component.parent_package + " before publishing that npm package; this project does not patch it. " +
            "Relationship: embedded-source. Used for: " + component.purpose + " " + component.version_note + " " +
            "The adjacent .LEGAL.txt contains only comments that esbuild was instructed to preserve; the complete " +
            "license and pinned source evidence are linked here. Used with NVIDIA-authored Apache-2.0 course source; " +
            "no proprietary-code claim.",
          component.upstream_url,
          repoFile(config, licensePath)
        ]
      };
    });
    return packages.concat(embedded);
  }

  function buildRows(markdown, config) {
    return tableRows(markdown, "Browser runtime and browser-build packages").filter(function (row) {
      return row.length >= 5 && (row[0] === "browser-bundle-input" || row[0] === "browser-build-only");
    }).map(function (row) {
      var scope = row[0], name = row[1], version = row[2];
      return {
        category: "build-input",
        relationship: scope,
        cells: [
          name, version, row[3], npmPage(name, version), INTERNAL, OTHER,
          "Category: " + scope + ". Course authors download this package while building the browser course. " +
            (scope === "browser-bundle-input" ? "Some of its code becomes part of a generated browser file, but learners do not receive the package as a separate dependency." : "It runs only during the build; learners do not receive it.") +
            " No proprietary-code claim.",
          npmPage(name, version), repoFile(config, "scripts/browser-vendor/package-lock.json")
        ]
      };
    });
  }

  function validationRows(markdown, config) {
    return tableRows(markdown, "Python and Node repository-tool packages").filter(function (row) {
      return row.length >= 5;
    }).map(function (row) {
      var links = parseLinks(row[4]);
      var upstream = (links.find(function (link) { return link.label === "PyPI" || link.label === "npm"; }) || {}).url || "";
      var lock = (links.find(function (link) { return !/^https?:/.test(link.url); }) || {}).url || "THIRD_PARTY_LICENSES.md";
      return {
        category: "validation",
        relationship: row[0],
        cells: [
          row[1], row[2], row[3], upstream, INTERNAL, OTHER,
          "Course authors or CI use this package to prepare or check the course (" + row[0] + "). " +
            "Learners do not receive it from the static course. No proprietary-code claim.",
          upstream, repoFile(config, lock)
        ]
      };
    });
  }

  function evaluatedCandidateRows(document, config) {
    var liveDemo = document.live_demo || {};
    var profiles = document.profiles || {};
    var useLabels = {
      acquisition: "Future asset-preparation helper",
      core: "Separate browser-Python demonstration",
      network: "Future outbound HTTP and model-API support"
    };
    var roleLabels = {
      "build-input": "download helper used while preparing browser files",
      "runtime-core": "runtime required by the separate demonstration",
      direct: "package selected for the proposed capability",
      transitive: "dependency brought in by a selected package"
    };
    return (document.components || []).map(function (component) {
      var profile = component.profile;
      var download = component.license_evidence_url;
      if (profile === "core") download = liveDemo.base_url || download;
      var profileDescription = profiles[profile] && profiles[profile].description ? profiles[profile].description :
        "This software was evaluated for possible future use and is not included in the learner course.";
      var comments = "Evaluated use: " + (useLabels[profile] || "Possible future capability") + ". Component role: " +
        (roleLabels[component.relationship] || component.relationship) + ". " + profileDescription +
        " Human approval remains required before distribution.";
      if (component.review_note) comments += " Review note: " + component.review_note;
      return {
        category: "evaluated-candidate",
        relationship: "candidate-" + profile + "-" + component.relationship,
        cells: [
          component.name, String(component.version), component.license_expression,
          component.license_evidence_url, INTERNAL, OTHER, comments, download,
          repoFile(config, "scripts/pyodide/candidate-components.json")
        ]
      };
    });
  }

  function bytesToHex(buffer) {
    return Array.from(new Uint8Array(buffer)).map(function (value) {
      return value.toString(16).padStart(2, "0");
    }).join("");
  }

  function verifiedSbom(href, metadata, label) {
    return fetch(href).then(function (response) {
      if (!response.ok) throw new Error(label + " SBOM HTTP " + response.status);
      return response.arrayBuffer();
    }).then(function (raw) {
      if (!window.crypto || !window.crypto.subtle) throw new Error("browser SHA-256 is unavailable");
      return window.crypto.subtle.digest("SHA-256", raw).then(function (hash) {
        if (bytesToHex(hash) !== metadata.sha256) throw new Error(label + " SBOM SHA-256 mismatch");
        var sbom = JSON.parse(new TextDecoder("utf-8").decode(raw));
        if (sbom.bomFormat !== "CycloneDX" || !Array.isArray(sbom.components)) {
          throw new Error(label + " is not a CycloneDX component inventory");
        }
        if (sbom.components.length !== metadata.component_count) {
          throw new Error(label + " component count does not match its evidence record");
        }
        return {href:href, components:sbom.components};
      });
    });
  }

  function linkedSbomComponents(config) {
    var catalogUrl = new URL(config.sbom_evidence, document.baseURI).href;
    return fetch(catalogUrl).then(function (response) {
      if (!response.ok) throw new Error("SBOM evidence catalog HTTP " + response.status);
      return response.json();
    }).then(function (catalog) {
      if (catalog.schema !== "nemoclaw-sbom-evidence/1" || !Array.isArray(catalog.records)) {
        throw new Error("unsupported SBOM evidence catalog");
      }
      catalog._catalogUrl = catalogUrl;
      (catalog.records || []).forEach(function (record) {
        (record.evidence_links || []).forEach(function (link) {
          link._resolvedHref = new URL(link.href, catalogUrl).href;
        });
        (record.subjects || []).forEach(function (subject) {
          subject._declarationHref = new URL(subject.declaration_href, catalogUrl).href;
        });
      });
      return Promise.all(catalog.records.map(function (record) {
        if (record.state !== "available" || !record.sbom || !record.sbom.href) return record;
        var href = new URL(record.sbom.href, catalogUrl).href;
        return verifiedSbom(href, record.sbom, record.id).then(function (verified) {
          record._resolvedHref = verified.href;
          record._components = verified.components;
          record._integrity = "verified";
          return record;
        });
      })).then(function () {
        if (!config.ci_sbom_evidence) return catalog;
        var runtimeUrl = new URL(config.ci_sbom_evidence, document.baseURI).href;
        return fetch(runtimeUrl).then(function (response) {
          if (!response.ok) throw new Error("CI SBOM evidence HTTP " + response.status);
          return response.json();
        }).then(function (runtime) {
          if (runtime.schema !== "nemoclaw-ci-evidence-links/1") {
            throw new Error("unsupported CI SBOM evidence link catalog");
          }
          catalog._ciEvidence = runtime;
          var artifact = (runtime.artifacts || []).find(function (item) {
            return item.label === "CycloneDX SBOM" && item.status === "available" && item.preview_href;
          });
          if (!artifact) return catalog;
          var previewHref = new URL(artifact.preview_href, runtimeUrl).href;
          return verifiedSbom(previewHref, artifact, "CI-generated Python environment").then(function (verified) {
            runtime._resolvedPreviewHref = verified.href;
            runtime._components = verified.components;
            runtime._integrity = "verified";
            return catalog;
          });
        });
      });
    });
  }

  function evidenceRecord(catalog, row) {
    return (catalog.records || []).find(function (record) {
      var selected = (record.selectors || []).some(function (selector) {
        return selector.category === row.category;
      });
      if (!selected) return false;
      if (!record.subjects) return true;
      return record.subjects.some(function (subject) {
        return subject.component === row.cells[0] && String(subject.version) === String(row.cells[1]);
      });
    }) || null;
  }

  function evidenceSubject(record, row) {
    return (record && record.subjects || []).find(function (subject) {
      return subject.component === row.cells[0] && String(subject.version) === String(row.cells[1]);
    }) || null;
  }

  function componentLicense(component) {
    var values = [];
    (component.licenses || []).forEach(function (item) {
      var data = item.license || {};
      var value = item.expression || data.id || data.name;
      if (value && values.indexOf(value) < 0) values.push(value);
    });
    return values.join("; ") || "Missing license evidence";
  }

  function spdxHref(value) {
    return /^[A-Za-z0-9.+-]+$/.test(value) ?
      "https://spdx.org/licenses/" + encodeURIComponent(value) + ".html" : "";
  }

  function csvCell(value) {
    var text = String(value == null ? "" : value);
    return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  function csv(rows, baseContainer) {
    var all = [
      ["Base Container used (if applicable):", "", baseContainer, "", "", "", "", "", ""],
      ["", "", "", "", "", "", "", "", ""],
      HEADER
    ].concat(rows.map(function (row) { return row.cells; }));
    return all.map(function (row) { return row.map(csvCell).join(","); }).join("\n") + "\n";
  }

  function plainCsv(header, rows) {
    return [header].concat(rows.map(function (row) { return row.cells; }))
      .map(function (row) { return row.map(csvCell).join(","); }).join("\n") + "\n";
  }

  function sourceMetadata(repositoryFile, sourceUrl, documents) {
    var paper = (documents.arxiv_papers || []).find(function (item) { return item.source_url === sourceUrl; });
    if (paper) return {
      authors:paper.authors.join(", "), evidence:paper.license_url, note:paper.reuse_summary
    };
    var nvidia = (documents.nvidia_documents || []).find(function (item) {
      return (item.repository_items || []).indexOf(repositoryFile) >= 0;
    });
    if (nvidia) return {
      authors:nvidia.authors.length ? nvidia.authors.join(", ") : "No author listed on official source page",
      evidence:nvidia.author_evidence_url, note:""
    };
    return {authors:"Not recorded for this source", evidence:sourceUrl, note:""};
  }

  function materialScopeRows(markdown, documents, config) {
    return tableRows(markdown, "Third-party course-material relationships").filter(function (row) {
      return row.length >= 5;
    }).map(function (row) {
      var relationship = row[1];
      var links = parseLinks(row[4]);
      var source = links.length ? links[0].url : row[4];
      var metadata = sourceMetadata(row[0], source, documents);
      var category, distributed, note;
      if (relationship === "recreation") {
        category = "recreated-asset"; distributed = "Yes";
        note = "A repository-authored recreation is distributed; review the recorded source terms before release.";
      } else if (relationship === "conversion" || relationship === "provided course asset") {
        category = "vendored-material"; distributed = "Yes";
        note = "A copied or format-shifted material artifact is distributed; the source terms remain controlling.";
      } else if (relationship === "remote display") {
        category = "referenced-source"; distributed = "No - the browser loads the image from NVIDIA's host";
        note = "The repository stores the source link and caption. The learner's browser requests the image from NVIDIA's host; the image is not copied into this repository.";
      } else {
        category = "referenced-source"; distributed = "Yes - repository-authored item";
        note = "The repository item is distributed, but the external work is cited, summarized, used as inspiration, or compiled as links rather than vendored wholesale.";
      }
      return { category:category, relationship:relationship, terms:row[3], cells:[
        row[0], category, relationship, distributed, "No", source, row[3], metadata.authors,
        metadata.evidence, repoFile(config, row[0]),
        "Source label: " + row[2] + ". " + note + (metadata.note ? " " + metadata.note : "")
      ]};
    });
  }

  function documentScopeRows(documents, markdown, config) {
    var relationshipByItem = {};
    tableRows(markdown, "Third-party course-material relationships").forEach(function (row) {
      if (row.length >= 2) relationshipByItem[row[0]] = row[1];
    });
    var rows = (documents.arxiv_papers || []).map(function (item) {
      var evidencePath = item.cited_from[0] || "THIRD_PARTY_LICENSES.md";
      return {category:"external-source-record", relationship:"paper citation", terms:item.license, cells:[
        "arXiv:" + item.arxiv_id, "external-source-record", "paper citation",
        "No - this row records an external paper cited from " + item.cited_from.length + " repository item(s); it does not distribute the paper", "No", item.source_url, item.license,
        item.authors.join(", "), item.license_url, repoFile(config, evidencePath),
        "Official arXiv license checked " + item.verified_on + ". " + item.reuse_summary +
          " Canonical citations: " + item.cited_from.join(", ")
      ]};
    });
    (documents.nvidia_documents || []).forEach(function (item) {
      var repositoryItems = item.repository_items || [];
      var missing = repositoryItems.filter(function (path) { return !relationshipByItem[path]; });
      if (missing.length) throw new Error("NVIDIA document has unclassified repository items: " + item.title + ": " + missing.join(", "));
      var counts = {};
      repositoryItems.forEach(function (path) {
        var relationship = relationshipByItem[path];
        counts[relationship] = (counts[relationship] || 0) + 1;
      });
      var copied = (counts.conversion || 0) + (counts["provided course asset"] || 0);
      var recreated = counts.recreation || 0;
      var remote = counts["remote display"] || 0;
      var category = copied ? "vendored-material" : recreated ? "recreated-asset" : "referenced-source";
      var distributed = copied ? "Yes - copied or converted into " + copied + " repository item(s)" :
        recreated ? "Yes - represented by " + recreated + " repository-authored recreation(s)" :
        remote ? "No - " + remote + " course page(s) load the image from NVIDIA's host; the repository stores links and captions only" :
        "Yes - represented by " + repositoryItems.length + " repository-authored reference item(s); the external document is not copied wholesale";
      var evidencePath = repositoryItems[0] || "THIRD_PARTY_LICENSES.md";
      var uses = Object.keys(counts).sort().map(function (name) { return name + ": " + counts[name]; }).join(", ");
      rows.push({category:category, relationship:"document use roll-up", terms:item.terms, cells:[
        item.title, category, "document use roll-up", distributed, "No",
        item.source_url, item.terms,
        item.authors.length ? item.authors.join(", ") : "No author listed on official source page",
        item.author_evidence_url, repoFile(config, evidencePath),
        "Official source checked " + item.verified_on + ". Classified uses: " + uses +
          ". Repository items: " + repositoryItems.join(", ")
      ]});
    });
    return rows;
  }

  function legalSoftwareRows(manifest, markdown, candidates, config) {
    var rows = vendoredRows(manifest, config).map(function (row) {
      return {category:"vendored-browser-code", relationship:row.relationship, terms:row.cells[2], cells:[
        row.cells[0] + "@" + row.cells[1], "vendored-browser-code", row.relationship,
        "Yes", "Yes", row.cells[7], row.cells[2], "Not applicable to software package", row.cells[3], row.cells[8],
        "Copied into the same-origin static course; the repository license text and package source corroborate scope."
      ]};
    });
    buildRows(markdown, config).filter(function (row) {
      return row.relationship === "browser-build-only";
    }).concat(validationRows(markdown, config), evaluatedCandidateRows(candidates, config)).forEach(function (row) {
      var browserExecution = row.category === "evaluated-candidate" && row.relationship.indexOf("candidate-core-") === 0 ?
        "Only if a repository-documentation reader selects Run; not in the learner course" : "No";
      rows.push({category:"tooling-not-distributed", relationship:row.relationship, terms:row.cells[2], cells:[
        row.cells[0] + "@" + row.cells[1], "tooling-not-distributed", row.relationship,
        "No", browserExecution, row.cells[7], row.cells[2], "Not applicable to software package", row.cells[3] || row.cells[7],
        row.cells[8], row.cells[6]
      ]});
    });
    return rows;
  }

  function text(node, value) {
    node.textContent = String(value == null ? "" : value);
  }

  function selectedValues(container) {
    return new Set(Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map(function (input) {
      return input.value;
    }));
  }

  var FILTER_LABELS = {
    softwareCategory: {
      "vendored": "Included in the course",
      "build-input": "Used only to build the course",
      "validation": "Used only to check the course",
      "evaluated-candidate": "Evaluated option, not shipped"
    },
    softwareRelationship: {
      "direct": "Chosen directly by this project",
      "transitive": "Required by another package",
      "embedded-source": "Copied into a package by its publisher",
      "browser-bundle-input": "Built into the browser course",
      "browser-build-only": "Runs only while building browser files",
      "browser binary": "Browser used for automated checks",
      "host-bootstrap": "Prepares the checked Python environment",
      "material-tooling": "Processes course materials",
      "security-tooling": "Checks dependencies and security"
    },
    scopeCategory: {
      "external-source-record": "External document citation record",
      "referenced-source": "Repository-authored reference to an external source",
      "tooling-not-distributed": "Used by authors or checks, not given to learners",
      "recreated-asset": "Recreated by the course authors",
      "vendored-material": "Copied into the course",
      "vendored-browser-code": "Browser code shipped to learners"
    },
    scopeRelationship: {
      "recreation": "Recreated from a source",
      "conversion": "Copied into another format",
      "remote display": "Displayed from NVIDIA's host",
      "summary": "Summarized",
      "inspiration": "Used as inspiration",
      "compilation": "Collected as links or references",
      "original": "Original source",
      "original course graphic": "Original course graphic",
      "paper citation": "Research paper citation",
      "document use roll-up": "External document and every related repository use",
      "direct": "Chosen directly by this project",
      "transitive": "Required by another package",
      "embedded-source": "Copied into a package by its publisher",
      "browser-build-only": "Used only to build browser files",
      "validation dependency": "Used to check the course"
    },
    license: {
      "Missing license evidence": "License evidence missing"
    }
  };

  function friendlyChoice(value, kind) {
    var labels = FILTER_LABELS[kind] || {};
    var main = labels[value];
    if (!main && kind === "softwareRelationship" && value.indexOf("candidate-") === 0) {
      var candidateParts = value.split("-");
      var profile = candidateParts[1] || "unknown";
      var role = candidateParts.slice(2).join("-");
      main = profile === "core" ? "Separate browser-Python demo runtime" :
        profile === "network" && role === "direct" ? "Selected package for future HTTP/API support" :
        profile === "network" ? "Dependency for future HTTP/API support" :
        "Future asset-preparation helper";
    }
    if (!main && kind === "scopeRelationship" && value.indexOf("candidate-") === 0) {
      main = "Evaluated software option, not distributed";
    }
    if (!main && kind === "softwareRelationship" && value.indexOf(",") >= 0) {
      main = value.split(",").map(function (part) {
        var clean = part.trim(); return labels[clean] || clean;
      }).join(" + ");
    }
    return { main:main || value, detail:main ? value : "" };
  }

  function preferredOrder(values, preferred) {
    var rank = new Map(preferred.map(function (value, index) { return [value, index]; }));
    return values.slice().sort(function (left, right) {
      var a = rank.has(left) ? rank.get(left) : preferred.length;
      var b = rank.has(right) ? rank.get(right) : preferred.length;
      return a - b || left.localeCompare(right);
    });
  }

  function choiceGroup(container, values, selected, onChange, kind) {
    container.replaceChildren();
    var actions = document.createElement("span"); actions.className = "filter-actions";
    var all = document.createElement("button"); all.type = "button"; text(all, "Select all");
    var none = document.createElement("button"); none.type = "button"; text(none, "Clear");
    actions.append(all, none); container.appendChild(actions);
    var chips = document.createElement("span"); chips.className = "filter-chips"; container.appendChild(chips);
    values.forEach(function (value) {
      var label = document.createElement("label"); label.className = "filter-chip";
      var input = document.createElement("input"); input.type = "checkbox"; input.value = value;
      input.checked = selected.has(value); input.addEventListener("change", onChange);
      var words = friendlyChoice(value, kind);
      var caption = document.createElement("span"); caption.className = "filter-label";
      var main = document.createElement("span"); text(main, words.main); caption.appendChild(main);
      if (words.detail) {
        var detail = document.createElement("small"); text(detail, words.detail); caption.appendChild(detail);
      }
      label.append(input, caption); chips.appendChild(label);
    });
    function updateSummary() {
      var summary = container.closest("details");
      var count = summary && summary.querySelector("[data-filter-count]");
      if (count) text(count, selectedValues(container).size + "/" + values.length);
    }
    container.querySelectorAll('input[type="checkbox"]').forEach(function (input) {
      input.addEventListener("change", updateSummary);
    });
    updateSummary();
    all.addEventListener("click", function () {
      chips.querySelectorAll('input[type="checkbox"]').forEach(function (input) { input.checked = true; });
      updateSummary(); onChange();
    });
    none.addEventListener("click", function () {
      chips.querySelectorAll('input[type="checkbox"]').forEach(function (input) { input.checked = false; });
      updateSummary(); onChange();
    });
  }

  function sortedRows(rows, state) {
    if (state.index == null) return rows.slice();
    var direction = state.direction === "desc" ? -1 : 1;
    return rows.map(function (row, index) { return {row:row, index:index}; }).sort(function (left, right) {
      var compared = String(left.row.cells[state.index] || "").localeCompare(
        String(right.row.cells[state.index] || ""), undefined, {numeric:true, sensitivity:"base"}
      );
      return compared ? compared * direction : left.index - right.index;
    }).map(function (item) { return item.row; });
  }

  function sortableHeaders(table, state, onChange, sortIndexes) {
    table.querySelectorAll("thead th").forEach(function (th, index) {
      var sortIndex = sortIndexes ? sortIndexes[index] : index;
      var label = th.textContent.trim(); th.replaceChildren(); th.setAttribute("aria-sort", "none");
      var button = document.createElement("button"); button.type = "button"; button.dataset.sortIndex = String(sortIndex);
      button.className = "sort-button"; button.setAttribute("aria-label", "Sort by " + label);
      var caption = document.createElement("span"); text(caption, label);
      var arrow = document.createElement("span"); arrow.className = "sort-arrow"; text(arrow, "↕");
      button.append(caption, arrow); th.appendChild(button);
      button.addEventListener("click", function () {
        if (state.index === sortIndex) state.direction = state.direction === "asc" ? "desc" : "asc";
        else { state.index = sortIndex; state.direction = "asc"; }
        table.querySelectorAll("thead th").forEach(function (item) { item.setAttribute("aria-sort", "none"); });
        table.querySelectorAll(".sort-arrow").forEach(function (item) { text(item, "↕"); });
        th.setAttribute("aria-sort", state.direction === "asc" ? "ascending" : "descending");
        text(arrow, state.direction === "asc" ? "↑" : "↓"); onChange();
      });
    });
  }

  function externalLink(url, label, evidenceKind) {
    var anchor = document.createElement("a"); anchor.href = url; anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    if (evidenceKind) anchor.dataset.evidenceLink = evidenceKind;
    text(anchor, label || url); return anchor;
  }

  function tableCell(label) {
    var td = document.createElement("td"); td.dataset.label = label; return td;
  }

  function stacked(primary, secondary) {
    var wrapper = document.createElement("span"); wrapper.className = "cell-stack";
    var top = document.createElement("strong"); text(top, primary); wrapper.appendChild(top);
    if (secondary) { var small = document.createElement("small"); text(small, secondary); wrapper.appendChild(small); }
    return wrapper;
  }

  function evidenceDetails(summary, lines) {
    var details = document.createElement("details"); details.className = "row-evidence";
    var heading = document.createElement("summary"); text(heading, summary); details.appendChild(heading);
    lines.forEach(function (line) {
      var paragraph = document.createElement("p");
      if (line.url) paragraph.appendChild(externalLink(line.url, line.label, line.kind || "external"));
      else text(paragraph, line.label);
      if (line.note) {
        var note = document.createElement("small"); text(note, line.note); paragraph.appendChild(note);
      }
      details.appendChild(paragraph);
    });
    return details;
  }

  function appendFacts(card, facts) {
    var list = document.createElement("ul"); list.className = "sbom-facts";
    facts.forEach(function (fact) {
      var item = document.createElement("li");
      if (fact.key) item.dataset.sbomFact = fact.key;
      if (fact.attention) item.className = "needs-review";
      var value = document.createElement("strong"); text(value, fact.value); item.appendChild(value);
      var label = document.createElement("span"); text(label, fact.label); item.appendChild(label);
      list.appendChild(item);
    });
    card.appendChild(list);
  }

  function auditLabel(label) {
    return {
      "CycloneDX SBOM":"Machine-readable package list",
      "Evidence manifest":"Scan record",
      "License appendix":"License report",
      "CI job definition":"How the package scan runs",
      "SBOM generation and retrieval runbook":"Step-by-step reproduction guide",
      "Checked Python package inventory":"Repository package declarations"
    }[label] || label;
  }

  function appendComponentPreview(card, components, summaryLabel) {
    var details = document.createElement("details");
    var summary = document.createElement("summary"); text(summary, summaryLabel); details.appendChild(summary);
    var wrap = document.createElement("div"); wrap.className = "sbom-components";
    var table = document.createElement("table"), head = document.createElement("thead"), headRow = document.createElement("tr");
    ["Component", "Version", "License"].forEach(function (label) {
      var th = document.createElement("th"); text(th, label); headRow.appendChild(th);
    });
    head.appendChild(headRow); table.appendChild(head);
    var body = document.createElement("tbody");
    (components || []).forEach(function (component) {
      var tr = document.createElement("tr");
      [component.name || "<unnamed>", component.version || "<unversioned>"].forEach(function (value) {
        var td = document.createElement("td"); text(td, value); tr.appendChild(td);
      });
      var license = componentLicense(component), licenseCell = document.createElement("td");
      var licenseHref = spdxHref(license);
      if (licenseHref) licenseCell.appendChild(externalLink(licenseHref, license, "external"));
      else text(licenseCell, license);
      tr.appendChild(licenseCell); body.appendChild(tr);
    });
    table.appendChild(body); wrap.appendChild(table); details.appendChild(wrap); card.appendChild(details);
    return details;
  }

  function evidenceLines(row, catalog) {
    var lines = [];
    if (/^https?:/.test(row.cells[7])) lines.push({url:row.cells[7], label:"Upstream package"});
    else if (row.cells[7]) lines.push({label:"Declared source: " + row.cells[7]});
    if (row.cells[8]) lines.push({url:row.cells[8], label:"Repository evidence"});
    var record = evidenceRecord(catalog, row);
    if (!record) return lines;
    var subject = evidenceSubject(record, row);
    if (record.state === "available") {
      lines.push({url:record._resolvedHref, label:"Machine-readable package list", kind:"local",
        note:"The page checks this file against the recorded integrity hash before using it."});
    } else if (record.state === "ci-generated") {
      (record.evidence_links || []).forEach(function (link) {
        lines.push({url:link._resolvedHref, label:auditLabel(link.label), kind:"local"});
      });
      if (catalog._ciEvidence && catalog._ciEvidence.record_id === record.id) {
        (catalog._ciEvidence.artifacts || []).filter(function (artifact) {
          return artifact.status === "available" && artifact.href;
        }).forEach(function (artifact) {
          lines.push({url:artifact.href, label:auditLabel(artifact.label), kind:"ci-artifact"});
        });
        if (catalog._ciEvidence.state !== "available") {
          lines.push({label:"CI artifact links flagged " + catalog._ciEvidence.state + ": " + catalog._ciEvidence.reason});
        }
      }
    } else {
      if (subject) {
        lines.push({url:subject._declarationHref, label:"Where this project declares it", kind:"local"});
        lines.push({url:subject.upstream_href, label:"Official source", kind:"external"});
        lines.push({url:subject.license_hint_href, label:"License information", kind:"external",
          note:subject.license_hint + " Sources checked " + subject.verified_on + "."});
      }
      lines.push({label:"Learners do not receive this tool. Scan the exact image before any future distribution."});
    }
    return lines;
  }

  function renderSoftwareRow(row, catalog) {
    var tr = document.createElement("tr"), td;
    td = tableCell("Component"); td.appendChild(stacked(row.cells[0], row.cells[1])); tr.appendChild(td);
    td = tableCell("License");
    if (row.cells[3]) td.appendChild(externalLink(row.cells[3], row.cells[2]));
    else td.appendChild(stacked(row.cells[2], friendlyChoice(row.cells[2], "license").main));
    tr.appendChild(td);
    td = tableCell("Learner delivery"); td.appendChild(stacked(friendlyChoice(row.category, "softwareCategory").main,
      friendlyChoice(row.relationship, "softwareRelationship").main)); tr.appendChild(td);
    td = tableCell("Purpose"); text(td, row.cells[6]); tr.appendChild(td);
    td = tableCell("Evidence"); td.appendChild(evidenceDetails("Open evidence", evidenceLines(row, catalog))); tr.appendChild(td);
    return tr;
  }

  function renderSbomEvidence(catalog, target) {
    target.replaceChildren();
    target.dataset.sbomExpectedCards = String((catalog.records || []).length);
    target.dataset.sbomExpectedSubjects = String((catalog.records || []).reduce(function (count, record) {
      return count + (record.subjects || []).length;
    }, 0));
    (catalog.records || []).forEach(function (record) {
      var card = document.createElement("article"); card.className = "sbom-card";
      var title = document.createElement("h3"); text(title, record.description); card.appendChild(title);
      var state = document.createElement("span"); state.className = "sbom-state";
      state.dataset.distribution = record.distribution;
      if (record.id === "browser-runtime") text(state, "Learners receive these " + record.sbom.component_count + " packages");
      else if (record.id === "python-validation-environment") text(state, "Learners do not receive these packages");
      else text(state, "Learners do not receive these tools");
      card.appendChild(state);
      var explanation = document.createElement("p");
      if (record.state === "available") {
        text(explanation, "Every browser package has a recorded license identifier.");
        card.appendChild(explanation);
        appendComponentPreview(card, record._components, "Review all " + record.sbom.component_count + " package licenses");
        card.appendChild(evidenceDetails("Files for auditors and automation", [
          {url:record._resolvedHref, label:"Machine-readable package list (CycloneDX JSON)", kind:"local",
            note:"The page checks this file against its recorded integrity hash before displaying package data."}
        ]));
      } else if (record.state === "ci-generated") {
        text(explanation, "Automated checks and contributor tools share a separate Python environment.");
        card.appendChild(explanation);
        var runtime = catalog._ciEvidence && catalog._ciEvidence.record_id === record.id ? catalog._ciEvidence : null;
        var auditLines = (record.evidence_links || []).map(function (item) {
          return {url:item._resolvedHref, label:auditLabel(item.label), kind:"local"};
        });
        if (runtime && runtime.job_url) {
          auditLines.push({url:runtime.job_url, label:"Build that produced this package list", kind:"ci-job",
            note:runtime.source_commit ? "Source commit " + runtime.source_commit.slice(0, 12) : ""});
        }
        var artifactLines = runtime && runtime.artifacts && runtime.artifacts.length ? runtime.artifacts.map(function (artifact) {
          return artifact.status === "available" && artifact.href ?
            {url:artifact.href, label:auditLabel(artifact.label), kind:"ci-artifact", note:artifact.repository_path} :
            {label:auditLabel(artifact.label) + " unavailable", note:artifact.repository_path + ". " + (artifact.reason || "No link is available for this build.")};
        }) : [
          {label:"Machine-readable package list unavailable", note:record.ci.sbom_artifact_path},
          {label:"Scan record unavailable", note:record.ci.manifest_artifact_path},
          {label:"License report unavailable", note:record.ci.appendix_artifact_path}
        ];
        auditLines = auditLines.concat(artifactLines);
        if (runtime && runtime._integrity === "verified") {
          var sbomArtifact = runtime.artifacts.find(function (artifact) { return artifact.label === "CycloneDX SBOM"; });
          var metadata = sbomArtifact.license_metadata || {};
          var recorded = (metadata.spdx || 0) + (metadata.named || 0);
          var unresolved = runtime._components.filter(function (component) {
            return componentLicense(component) === "Missing license evidence";
          });
          appendFacts(card, [
            {key:"checked", value:runtime._components.length, label:"packages checked"},
            {key:"recorded", value:recorded, label:"have recorded license information"},
            {key:"unresolved", value:unresolved.length, label:"need package-by-package review", attention:unresolved.length > 0}
          ]);
          if (unresolved.length) {
            var unresolvedPreview = appendComponentPreview(card, unresolved,
              "Review " + unresolved.length + " packages needing license clarification");
            unresolvedPreview.dataset.licenseClarification = "1";
          }
          var ciPreview = appendComponentPreview(card, runtime._components, "Review all " + runtime._components.length + " Python package licenses");
          ciPreview.dataset.ciComponentPreview = "1";
          auditLines.unshift({url:runtime._resolvedPreviewHref, label:"Machine-readable package list served with this preview", kind:"local"});
        } else {
          var unavailable = document.createElement("p"); unavailable.className = "sbom-notice";
          text(unavailable, "This preview does not include the generated Python package list. The repository declarations and reproduction guide remain available below.");
          card.appendChild(unavailable);
        }
        var auditFiles = evidenceDetails("Files for auditors and automation", auditLines);
        auditFiles.dataset.ciLinksState = runtime ? runtime.state : "unavailable";
        card.appendChild(auditFiles);
      } else {
        text(explanation, "These " + (record.subjects || []).length +
          " entries support local development and compatibility checks. Containers and operating systems combine software from many sources, so the review keeps their license information separate.");
        card.appendChild(explanation);
        var future = document.createElement("p"); future.className = "sbom-notice";
        text(future, "If one of these tools is ever distributed, scan that exact version before release.");
        card.appendChild(future);
        var subjectDetails = document.createElement("details");
        var subjectSummary = document.createElement("summary");
        text(subjectSummary, "Review " + (record.subjects || []).length + " optional tools and source terms");
        subjectDetails.appendChild(subjectSummary);
        var subjectWrap = document.createElement("div"); subjectWrap.className = "sbom-subjects";
        var subjectTable = document.createElement("table");
        var subjectHead = document.createElement("thead"), subjectHeadRow = document.createElement("tr");
        ["Tool or image", "What the license evidence says", "Check the source"].forEach(function (label) {
          var th = document.createElement("th"); text(th, label); subjectHeadRow.appendChild(th);
        });
        subjectHead.appendChild(subjectHeadRow); subjectTable.appendChild(subjectHead);
        var subjectBody = document.createElement("tbody");
        (record.subjects || []).forEach(function (subject) {
          var tr = document.createElement("tr"); tr.dataset.sbomSubject = "1";
          var name = document.createElement("td"); name.appendChild(stacked(subject.component, subject.version)); tr.appendChild(name);
          var hint = document.createElement("td"); hint.dataset.licenseHint = "1"; text(hint, subject.license_hint); tr.appendChild(hint);
          var links = document.createElement("td"); links.className = "sbom-subject-links";
          links.appendChild(externalLink(subject._declarationHref, "Where this project declares it", "local"));
          links.appendChild(externalLink(subject.upstream_href, "Official source", "external"));
          links.appendChild(externalLink(subject.license_hint_href, "License information", "external"));
          var checked = document.createElement("small"); text(checked, "Sources checked " + subject.verified_on); links.appendChild(checked);
          tr.appendChild(links); subjectBody.appendChild(tr);
        });
        subjectTable.appendChild(subjectBody); subjectWrap.appendChild(subjectTable); subjectDetails.appendChild(subjectWrap); card.appendChild(subjectDetails);
      }
      target.appendChild(card);
    });
    target.dataset.sbomEvidenceReady = "1";
  }

  function renderScopeRow(row) {
    var tr = document.createElement("tr"), td;
    td = tableCell("Item"); td.appendChild(stacked(row.cells[0], friendlyChoice(row.relationship, "scopeRelationship").main)); tr.appendChild(td);
    td = tableCell("Use and delivery"); td.appendChild(stacked(friendlyChoice(row.category, "scopeCategory").main,
      row.cells[3] + (row.cells[4] === "Yes" ? "; runs in learner browser" : ""))); tr.appendChild(td);
    td = tableCell("Source and terms");
    if (/^https?:/.test(row.cells[5])) td.appendChild(externalLink(row.cells[5], row.cells[6]));
    else td.appendChild(stacked(row.cells[6], row.cells[5]));
    tr.appendChild(td);
    td = tableCell("Author(s)"); text(td, row.cells[7]); tr.appendChild(td);
    td = tableCell("Evidence and notes"); td.appendChild(evidenceDetails("Open review details", [
      {url:row.cells[8], label:"Source terms or byline"}, {url:row.cells[9], label:"Repository evidence"},
      {label:row.cells[10]}
    ])); tr.appendChild(td);
    return tr;
  }

  function mount(config, target, evidencePromise) {
    return Promise.all([
      fetch(config.vendor_manifest).then(function (response) {
        if (!response.ok) throw new Error("vendor manifest HTTP " + response.status);
        return response.json();
      }),
      fetch(config.inventory).then(function (response) {
        if (!response.ok) throw new Error("inventory HTTP " + response.status);
        return response.text();
      }),
      fetch(config.pyodide_candidates).then(function (response) {
        if (!response.ok) throw new Error("Pyodide candidate inventory HTTP " + response.status);
        return response.json();
      }),
      evidencePromise || linkedSbomComponents(config)
    ]).then(function (sources) {
      var rows = vendoredRows(sources[0], config)
        .concat(buildRows(sources[1], config))
        .concat(validationRows(sources[1], config))
        .concat(evaluatedCandidateRows(sources[2], config));
      var category = target.querySelector("[data-export-category-group]");
      var relationship = target.querySelector("[data-export-relationship-group]");
      var license = target.querySelector("[data-export-license-group]");
      var search = target.querySelector("[data-export-search]");
      var base = target.querySelector("[data-export-base]");
      var body = target.querySelector("tbody");
      var count = target.querySelector("[data-export-count]");
      var sortState = {index:null, direction:"asc"};
      var categories = preferredOrder(Array.from(new Set(rows.map(function (row) { return row.category; }))), [
        "vendored", "build-input", "validation", "evaluated-candidate"
      ]);

      function visibleRows() {
        var query = search.value.trim().toLowerCase();
        var selectedCategories = selectedValues(category);
        var selectedRelationships = selectedValues(relationship);
        var selectedLicenses = selectedValues(license);
        return rows.filter(function (row) {
          return selectedCategories.has(row.category) && selectedRelationships.has(row.relationship) &&
            selectedLicenses.has(row.cells[2]) &&
            (!query || row.cells.join(" ").toLowerCase().indexOf(query) >= 0);
        });
      }

      function relationshipOptions() {
        var selectedCategories = selectedValues(category);
        var categoryRows = Array.from(new Set(rows.filter(function (row) {
          return selectedCategories.has(row.category);
        }).map(function (row) { return row.relationship; }))).sort();
        var licenses = Array.from(new Set(rows.filter(function (row) {
          return selectedCategories.has(row.category);
        }).map(function (row) { return row.cells[2]; }))).sort();
        choiceGroup(relationship, categoryRows, new Set(categoryRows), paint, "softwareRelationship");
        choiceGroup(license, licenses, new Set(licenses), paint, "license");
      }

      function paint() {
        var visible = sortedRows(visibleRows(), sortState);
        body.replaceChildren();
        visible.forEach(function (row) {
          body.appendChild(renderSoftwareRow(row, sources[3]));
        });
        text(count, visible.length + " component" + (visible.length === 1 ? "" : "s"));
        target.dataset.exportReady = "1";
      }

      search.addEventListener("input", paint);
      target.querySelector("[data-export-download]").addEventListener("click", function () {
        var blob = new Blob([csv(sortedRows(visibleRows(), sortState), base.value)], { type: "text/csv;charset=utf-8" });
        var link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = "nemoclaw-third-party-components-filtered.csv";
        document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(link.href);
      });
      choiceGroup(category, categories, new Set(["vendored"]), function () { relationshipOptions(); paint(); }, "softwareCategory");
      relationshipOptions(); sortableHeaders(target.querySelector("table"), sortState, paint, [0, 2, 4, 6, 8]); paint();
      return rows;
    }).catch(function (error) {
      target.dataset.exportError = error.message;
      var status = target.querySelector("[data-export-count]");
      text(status, "Preview failed: " + error.message);
      throw error;
    });
  }

  function mountScope(config, target) {
    return Promise.all([
      fetch(config.vendor_manifest).then(function (response) {
        if (!response.ok) throw new Error("vendor manifest HTTP " + response.status);
        return response.json();
      }),
      fetch(config.inventory).then(function (response) {
        if (!response.ok) throw new Error("inventory HTTP " + response.status);
        return response.text();
      }),
      fetch(config.document_sources).then(function (response) {
        if (!response.ok) throw new Error("document source inventory HTTP " + response.status);
        return response.json();
      }),
      fetch(config.pyodide_candidates).then(function (response) {
        if (!response.ok) throw new Error("Pyodide candidate inventory HTTP " + response.status);
        return response.json();
      })
    ]).then(function (sources) {
      var rows = documentScopeRows(sources[2], sources[1], config)
        .concat(materialScopeRows(sources[1], sources[2], config))
        .concat(legalSoftwareRows(sources[0], sources[1], sources[3], config));
      var category = target.querySelector("[data-scope-category-group]");
      var relationship = target.querySelector("[data-scope-relationship-group]");
      var terms = target.querySelector("[data-scope-terms-group]");
      var search = target.querySelector("[data-scope-search]");
      var body = target.querySelector("tbody");
      var count = target.querySelector("[data-scope-count]");
      var sortState = {index:null, direction:"asc"};
      var categories = preferredOrder(Array.from(new Set(rows.map(function (row) { return row.category; }))), [
        "vendored-browser-code", "vendored-material", "recreated-asset", "referenced-source", "external-source-record", "tooling-not-distributed"
      ]);
      function visibleRows() {
        var query = search.value.trim().toLowerCase();
        var selectedCategories = selectedValues(category);
        var selectedRelationships = selectedValues(relationship);
        var selectedTerms = selectedValues(terms);
        return rows.filter(function (row) {
          return selectedCategories.has(row.category) && selectedRelationships.has(row.relationship) &&
            selectedTerms.has(row.terms) &&
            (!query || row.cells.join(" ").toLowerCase().indexOf(query) >= 0);
        });
      }
      function dependentOptions() {
        var selectedCategories = selectedValues(category);
        var categoryRows = rows.filter(function (row) { return selectedCategories.has(row.category); });
        var relationships = Array.from(new Set(categoryRows.map(function (row) { return row.relationship; }))).sort();
        var recordedTerms = Array.from(new Set(categoryRows.map(function (row) { return row.terms; }))).sort();
        choiceGroup(relationship, relationships, new Set(relationships), paint, "scopeRelationship");
        choiceGroup(terms, recordedTerms, new Set(recordedTerms), paint, "license");
      }
      function paint() {
        var visible = sortedRows(visibleRows(), sortState); body.replaceChildren();
        visible.forEach(function (row) {
          body.appendChild(renderScopeRow(row));
        });
        text(count, visible.length + " relationship" + (visible.length === 1 ? "" : "s"));
        target.dataset.exportReady = "1";
      }
      search.addEventListener("input", paint);
      target.querySelector("[data-scope-download]").addEventListener("click", function () {
        var blob = new Blob([plainCsv(SCOPE_HEADER, sortedRows(visibleRows(), sortState))], {type:"text/csv;charset=utf-8"});
        var link = document.createElement("a"); link.href = URL.createObjectURL(blob);
        link.download = "nemoclaw-legal-scope-filtered.csv";
        document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(link.href);
      });
      choiceGroup(category, categories, new Set(["external-source-record", "referenced-source", "recreated-asset", "vendored-material"]), function () { dependentOptions(); paint(); }, "scopeCategory");
      dependentOptions(); sortableHeaders(target.querySelector("table"), sortState, paint, [0, 1, 6, 7, 10]); paint(); return rows;
    }).catch(function (error) {
      target.dataset.exportError = error.message;
      text(target.querySelector("[data-scope-count]"), "Preview failed: " + error.message);
      throw error;
    });
  }

  function boot() {
    var target = document.getElementById("third-party-export-preview");
    var scopeTarget = document.getElementById("legal-scope-preview");
    var sbomTarget = document.getElementById("sbom-evidence-preview");
    var configNode = document.getElementById("third-party-export-config");
    if ((!target && !scopeTarget) || !configNode) return;
    try {
      var config = JSON.parse(configNode.textContent);
      var evidencePromise = linkedSbomComponents(config);
      if (sbomTarget) evidencePromise.then(function (catalog) {
        renderSbomEvidence(catalog, sbomTarget);
      }).catch(function (error) {
        sbomTarget.dataset.sbomEvidenceError = error.message;
        text(sbomTarget, "SBOM evidence failed: " + error.message);
      });
      if (target) mount(config, target, evidencePromise);
      if (scopeTarget) mountScope(config, scopeTarget);
    } catch (error) {
      if (target) target.dataset.exportError = error.message;
      if (scopeTarget) scopeTarget.dataset.exportError = error.message;
    }
  }

  window.ThirdPartyExportUI = { mount: mount, mountScope:mountScope, renderSbomEvidence:renderSbomEvidence,
    linkedSbomComponents:linkedSbomComponents, csv: csv, header: HEADER.slice(), scopeHeader:SCOPE_HEADER.slice() };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
