// Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/* _skill_explorer.js is a reusable, self-contained folder explorer for any SKILL.html.
 *
 * A folder's SKILL.html drops in a config and this script turns it into a live explorer:
 * an index that documents and points at every file in the folder (flat or grouped into
 * sections), an in-context source viewer (real file text, syntax-highlighted), guided
 * source tours, an LLM-assisted code explainer (through the active course model route),
 * and a self-assess pass that fetches every documented file and reports drift
 * against a recorded byte fingerprint. Read-only: it opens, tours, copies, and downloads
 * source; it never writes.
 *
 * One framer, parameterized. The validator UI, the course pages, and every folder explorer
 * share the course model registry. The explorer delegates the tab-scoped build.nvidia.com
 * key to that runtime; model URL, model ID, routing, and attribution stay there too.
 *
 * The renderer resolves the canonical course runtime from either deployed location. The config
 * lives inline as <script type="application/json" id="explorer-config">.
 * File paths are relative to the SKILL.html, so the same page works in the lab and on deploy.
 *
 * Config shape:
 *   {
 *     "title":   "Folder title",
 *     "summary": "What this folder is and why it exists.",
 *     "ties":    ["build"],                  // which SESSIONS to latch (default ["build"])
 *     "model":   "nvidia/nemotron-3-nano-30b-a3b",
 *     "files":   [{ "path":"x.js", "role":"...", "desc":"...", "bytes":123 }],   // flat, OR:
 *     "groups":  [{ "title":"Engine", "files":[ ...file entries... ] }],          // sectioned
 *     "tour":    [{ "title":"...", "file":"x.js", "lines":[10,24], "note":"..." }],
 *     "related": [{ "label":"...", "href":"..." }]
 *   }
 */
(function () {
  "use strict";

  var EXPLORER_URL = document.currentScript && document.currentScript.src
    ? document.currentScript.src : document.baseURI;
  function vendorUrl(file) {
    var path = new URL(EXPLORER_URL).pathname;
    var directory = /\/nemoclaw\/_skill_explorer\.js$/.test(path) ? "vendor/" : "nemoclaw/vendor/";
    return new URL(directory + file, EXPLORER_URL).href;
  }

  var COURSE_RUNTIME_PROMISE = null;
  function courseRuntime() {
    if (COURSE_RUNTIME_PROMISE) return COURSE_RUNTIME_PROMISE;
    var path = new URL(EXPLORER_URL).pathname;
    var relative = /\/nemoclaw\/_skill_explorer\.js$/.test(path)
      ? "scripts/_shared.js"
      : "nemoclaw/scripts/_shared.js";
    COURSE_RUNTIME_PROMISE = import(new URL(relative, EXPLORER_URL).href);
    return COURSE_RUNTIME_PROMISE;
  }

  // Explorer-only presentation for shared course credentials. Endpoint and model ownership
  // stays in web/nemoclaw/scripts/_shared.js; ask() calls that runtime instead of rebuilding it.
  var SESSIONS = {
    build: {
      kind: "key", keyVar: "nvapi", label: "build.nvidia.com key", placeholder: "nvapi-...",
      note: "Model calls use the chat route and model saved on the course home page or in Module 1a."
    },
    service: {
      kind: "proxy", label: "in-network services",
      note: "Reached over the lab proxy routes (/lab/svc/...). No browser credential, and only inside the lab."
    }
  };

  var HLJS_CSS = vendorUrl("highlight-github-dark-11.10.0.min.css");
  var HLJS_JS = vendorUrl("highlight-11.10.0.min.js");

  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return c === "&" ? "&amp;" : c === "<" ? "&lt;" : c === ">" ? "&gt;" :
        c === '"' ? "&quot;" : "&#39;";
    });
  }
  function langOf(path) {
    var ext = (path.split(".").pop() || "").toLowerCase();
    return { js: "javascript", mjs: "javascript", ts: "typescript", py: "python", sh: "bash",
             json: "json", html: "xml", htm: "xml", css: "css", md: "markdown", tf: "hcl",
             yml: "yaml", yaml: "yaml", toml: "ini", txt: "plaintext", dockerfile: "plaintext" }[ext] || "plaintext";
  }
  function isMarkdown(path) { return /\.(?:md|markdown)$/i.test(path || ""); }
  function safeMarkdownHtml(html) {
    var t = document.createElement("template");
    t.innerHTML = html;
    t.content.querySelectorAll("script,style,iframe,object,embed,link,meta,base,form,input,button,textarea,select").forEach(function (n) { n.remove(); });
    t.content.querySelectorAll("*").forEach(function (n) {
      Array.prototype.slice.call(n.attributes || []).forEach(function (a) {
        var name = a.name.toLowerCase(), value = String(a.value || "").trim().toLowerCase();
        if (name.indexOf("on") === 0 || ((name === "href" || name === "src" || name === "xlink:href") && /^(?:javascript|data):/.test(value))) {
          n.removeAttribute(a.name);
        }
      });
      if (n.tagName === "A" && n.getAttribute("target") === "_blank") n.setAttribute("rel", "noopener noreferrer");
    });
    return t.innerHTML;
  }
  function headingSlug(text, used) {
    var base = String(text || "").toLowerCase().normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "section";
    var slug = base, n = 2;
    while (used[slug]) { slug = base + "-" + n; n++; }
    used[slug] = true;
    return slug;
  }

  function injectChrome(loadSourceHighlighter) {
    // Apply a saved manual theme choice before any content is built (the framer renders its body in JS, so this is flash-free).
    // With no saved choice the palette below follows the OS.
    try { var _t = localStorage.getItem("theme"); if (_t) document.documentElement.setAttribute("data-theme", _t); } catch (e) {}
    if (loadSourceHighlighter && !document.head.querySelector('link[data-hljs]')) {
      var css = el("link"); css.rel = "stylesheet"; css.href = HLJS_CSS; css.dataset.hljs = "1";
      document.head.appendChild(css);
    }
    if (loadSourceHighlighter && !window.hljs) { var js = el("script"); js.src = HLJS_JS; js.defer = true; document.head.appendChild(js); }
    if (document.head.querySelector('style[data-skill-chrome]')) return;
    var s = el("style");
    s.dataset.skillChrome = "1";
    var LIGHT = "--g:#3f6900;--gs:#3f6900;--bg:#ffffff;--e1:#f6f8fa;--e2:#eef1f4;--e3:#e1e6eb;--tx:#1a1a1a;--td:#3b3b3b;--tf:#4b5563;--acc:#0969da;--reason:#8250df;--artifact-text:#0969da;--err:#a31520;--warn:#9a6700;color-scheme:light";
    s.textContent = [
      ":root{--g:#76b900;--gs:#aee23a;--bg:#0d0d0d;--e1:#161616;--e2:#1e1e1e;--e3:#2a2a2a;",
      "--tx:#f2f2f2;--td:#b0b0b0;--tf:#8a8a8a;--acc:#3b82f6;--reason:#c4b5fd;--artifact-text:#9bdcff;--err:#ff7b72;--warn:#e3b341;--mono:ui-monospace,Consolas,monospace}",
      // Light palette: the same shared tokens flipped. Forced by the topbar toggle (data-theme), and
      // applied automatically when the OS prefers light and the reader has made no manual choice.
      // Same contract and token values as the course pages, so the whole stack themes as one.
      ":root[data-theme=\"light\"]{" + LIGHT + "}",
      "@media(prefers-color-scheme:light){:root:not([data-theme=\"dark\"]):not([data-theme=\"light\"]){" + LIGHT + "}}",
      "*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.55 system-ui,sans-serif}",
      "a{color:var(--g)}code{font-family:var(--mono);max-width:100%;overflow-wrap:anywhere;word-break:break-word}",
      "body>main{width:100%;max-width:88rem;margin:0 auto;padding:1rem clamp(1rem,4vw,2rem);min-width:0}body>main pre{max-width:100%;overflow:auto}body>main pre code{white-space:pre-wrap;word-break:break-word}",
      ":root[data-theme=\"light\"] body h2,:root[data-theme=\"light\"] body h3{color:var(--tx)!important}",
      ":root[data-theme=\"light\"] body th{color:var(--tx)!important}",
      ":root[data-theme=\"light\"] .console button:not(.danger){color:#fff!important}",
      // shared sticky topbar (the equivalent of the course nav, for every framer page):
      // always a way back (home + up); links are real <a href> so the link graph sees them.
      ".sx-topbar{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:14px;flex-wrap:wrap;",
      "padding:.7rem clamp(1rem,4vw,2rem);background:var(--bg);border-bottom:1px solid var(--e3)}",
      ".sx-topbar .sx-logo{font-weight:700;color:var(--g);letter-spacing:.04em;text-decoration:none}",
      ".sx-topbar .sx-up{color:var(--td);font-size:.88rem;text-decoration:none}.sx-topbar .sx-up:hover{color:var(--gs)}",
      ".sx-topbar .sx-crumb{color:var(--tf);font-size:.86rem;font-family:var(--mono);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
      ".sx-topbar .sx-theme{margin-left:auto;flex:0 0 auto;width:30px;height:30px;display:inline-flex;align-items:center;justify-content:center;font-size:15px;line-height:1;cursor:pointer;background:transparent;color:var(--td);border:1px solid var(--e3);border-radius:7px}",
      ":root[data-theme=\"light\"] .sx-topbar{background:var(--bg)}",
      "@media(prefers-color-scheme:light){:root:not([data-theme=\"dark\"]) .sx-topbar{background:var(--bg)}}",
      ".sx-page-topbar{background:var(--bg)!important;color:var(--tx)!important;border-color:var(--e3)!important}",
      ".sx-page-topbar .sx-page-nav{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:0}",
      ".sx-page-topbar .sx-page-nav a{color:var(--td)!important;border:0!important;padding:0!important;text-decoration:none}",
      ".sx-page-topbar .sx-page-nav a:first-child{color:var(--gs)!important;font-weight:700;letter-spacing:.04em}",
      ".sx-page-topbar .sx-page-nav a:hover{color:var(--gs)!important}",
      // Hand-authored and generated static SKILL bodies remain useful without JS. Once the
      // shared renderer loads, bind them to its palette so one theme choice colors whole page.
      ".skill-static{background:var(--bg)!important;color:var(--tx)!important;border-color:var(--e3)!important}",
      ".skill-static p,.skill-static .skill-card span,.skill-static .skill-link span,.skill-static .export-status,.skill-static .filter-field legend,.skill-static .export-controls>label{color:var(--td)!important}",
      ".skill-static h1,.skill-static a,.skill-static .skill-card b,.skill-static .skill-link b,.skill-static .skill-cmd b{color:var(--gs)!important}",
      ".skill-static h2,.skill-static h3,.skill-static .skill-cmd code,.skill-static code.skill-cmd{color:var(--tx)!important}",
      ".skill-static .skill-card,.skill-static .skill-link,.skill-static .skill-cmd,.skill-static .filter-field,.skill-static .export-table-wrap{background:var(--e1)!important;border-color:var(--e3)!important}",
      ".skill-static .skill-note{background:rgba(118,185,0,.08)!important;color:var(--tx)!important}",
      ".skill-static input,.skill-static select,.skill-static button{background:var(--bg)!important;color:var(--tx)!important;border-color:var(--e3)!important}",
      ".skill-static .filter-chip{background:var(--e1)!important;color:var(--td)!important;border-color:var(--e3)!important}",
      ".skill-static .filter-chip:has(input:checked){background:rgba(118,185,0,.14)!important;color:var(--tx)!important;border-color:var(--g)!important}",
      ".skill-static .export-table th{background:var(--e2)!important;color:var(--gs)!important;border-color:var(--e3)!important}",
      ".skill-static .export-table td{color:var(--td)!important;border-color:var(--e3)!important}",
      ".skill-static .filter-guide,.skill-static .filter-guide li{color:var(--td)!important}",
      ".skill-static .filter-guide strong,.skill-static .filter-guide code{color:var(--tx)!important}",
      ".skill-static pre,.skill-static code{max-width:100%;overflow-wrap:anywhere}.skill-static pre{overflow:auto}.skill-static pre code{white-space:pre-wrap;word-break:break-word}",
      ".skill-static .skill-cmds,.skill-static .skill-grid,.skill-static .skill-list,.skill-static .skill-cmd,.skill-static .skill-card,.skill-static .skill-link{min-width:0;max-width:100%}",
      // Shared wide-screen frame. Existing tables/source panels keep their own overflow behavior.
      ".skill-static,.sx-head,.sx-wrap,.rp-head,.rp-wrap{width:100%;max-width:88rem;margin-left:auto;margin-right:auto}",
      ".sx-head{padding:1.1rem clamp(1rem,4vw,2rem) .6rem;border-bottom:1px solid var(--e3)}",
      ".sx-head h1{margin:.1em 0;font-size:1.45rem;color:var(--g)}",
      ".sx-lead{color:var(--td);max-width:64rem;font-size:.95rem}",
      ".sx-wrap{display:grid;grid-template-columns:320px 1fr;min-height:70vh}",
      "@media(max-width:820px){.sx-wrap{grid-template-columns:1fr}.skill-static nav,.skill-static .skill-nav{display:flex;flex-wrap:wrap;gap:8px;min-width:0}.skill-static h1,.skill-static h2,.skill-static p,.skill-static a,.skill-static code,.skill-static span,.sx-card .nm,.sx-card .ds{overflow-wrap:anywhere;word-break:break-word}.skill-static table,.sx-readme table{display:block;width:100%;max-width:100%;overflow-x:auto}}",
      ".sx-rail{border-right:1px solid var(--e3);padding:1rem .7rem 4rem;min-width:0}",
      ".sx-rail h3{font-size:.7rem;text-transform:uppercase;letter-spacing:.07em;color:var(--tf);margin:1.2em 0 .5em}",
      ".sx-file{display:block;width:100%;text-align:left;background:none;border:0;border-radius:7px;color:var(--td);",
      "padding:8px 10px;cursor:pointer;font:inherit}",
      ".sx-file:hover{background:var(--e1);color:var(--tx)}.sx-file.sel{background:var(--e1);color:var(--gs)}",
      ".sx-file .nm{font-family:var(--mono);font-size:.85rem;display:flex;justify-content:space-between;gap:8px}",
      ".sx-file .nm>*{min-width:0;overflow-wrap:anywhere;word-break:break-word}",
      ".sx-file .rl{font-size:.76rem;color:var(--tf)}",
      ".sx-dot{width:8px;height:8px;border-radius:999px;flex:none;align-self:center}",
      ".sx-dot.ok{background:var(--g)}.sx-dot.drift{background:var(--warn)}.sx-dot.gone{background:var(--err)}",
      ".sx-tour{display:block;width:100%;text-align:left;background:var(--e1);border:1px solid var(--e3);",
      "border-left:3px solid var(--g);border-radius:7px;color:var(--td);padding:7px 10px;margin:6px 0;cursor:pointer;font:inherit;font-size:.84rem}",
      ".sx-tour:hover{color:var(--tx)}.sx-tour b{color:var(--gs);display:block;font-size:.82rem}",
      ".sx-main{padding:1rem clamp(1rem,4vw,2rem) 4rem;min-width:0}",
      ".sx-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:.5em}",
      ".sx-bar .fn{font-family:var(--mono);font-size:.9rem;color:var(--gs)}.sx-bar .rl{font-size:.8rem;color:var(--tf)}.sx-bar .sp{flex:1}",
      ".sx-btn{background:var(--e2);border:1px solid var(--e3);color:var(--td);border-radius:7px;padding:6px 12px;line-height:1;font:inherit;font-size:.78rem;cursor:pointer;transition:background .15s,border-color .15s,color .15s}",
      ".sx-btn:hover{border-color:var(--g);color:var(--gs)}a.sx-btn{text-decoration:none}a.sx-btn.on{border-color:var(--g);color:var(--gs);background:rgba(118,185,0,.08)}",
      ".sx-note{background:rgba(118,185,0,.07);border-left:3px solid var(--g);border-radius:0 7px 7px 0;padding:9px 13px;margin:.5em 0;font-size:.9rem;color:var(--tx)}",
      ".sx-code{margin:0;border:1px solid var(--e3);border-radius:8px;overflow:auto;max-height:62vh;background:var(--bg)}",
      ".sx-code table{border-collapse:collapse;width:100%;font-family:var(--mono);font-size:.82rem}",
      ".sx-code td{padding:0;vertical-align:top}",
      ".sx-code .ln{text-align:right;color:var(--tf);padding:0 12px;user-select:none;width:1%;white-space:nowrap;border-right:1px solid var(--e3)}",
      ".sx-code .lc{padding:0 14px;white-space:pre}",
      ".sx-code tr.hl .lc{background:rgba(118,185,0,.10)}.sx-code tr.hl .ln{color:var(--gs)}",
      ".sx-ask{margin-top:1.2em;border-top:1px solid var(--e3);padding-top:1em}",
      ".sx-ask textarea{width:100%;background:var(--e2);color:var(--tx);border:1px solid var(--e3);border-radius:8px;",
      "padding:9px 11px;font:inherit;font-size:.9rem;resize:vertical;min-height:54px}",
      ".sx-ask textarea:focus{outline:none;border-color:var(--g)}",
      ".sx-tie{display:flex;gap:8px;align-items:center;margin:.4em 0;font-size:.82rem;color:var(--tf);flex-wrap:wrap}",
      ".sx-tie .lab{min-width:9rem}",
      ".sx-tie input{flex:1;min-width:12rem;background:var(--e2);color:var(--tx);border:1px solid var(--e3);border-radius:6px;padding:6px 9px;font-family:var(--mono);font-size:.8rem}",
      ".sx-tie .svc{color:var(--td)}",
      ".sx-answer{background:var(--e1);border:1px solid var(--e3);border-radius:8px;padding:11px 14px;margin-top:.7em;white-space:pre-wrap;font-size:.92rem;line-height:1.6}",
      ".sx-answer.err{border-color:var(--err);color:var(--err)}",
      ".sx-send{background:var(--g);color:#0a0a0a;border:0;border-radius:8px;padding:8px 16px;font-weight:700;cursor:pointer;margin-top:.5em}",
      ":root[data-theme=\"light\"] .sx-send{color:#fff}",
      ".sx-send:disabled{opacity:.5;cursor:wait}",
      ".sx-related a{display:inline-block;margin:0 12px 6px 0;font-size:.84rem}",
      "a.sx-file{text-decoration:none}a.sx-file:hover{text-decoration:none}",
      ".sx-readme{max-width:62rem;font-size:.95rem}",
      ".sx-readme h1{font-size:1.5rem;color:var(--g);margin:.2em 0 .4em}",
      ".sx-readme h2{font-size:1.2rem;border-bottom:1px solid var(--e3);padding-bottom:.2em;margin:1.4em 0 .5em}",
      ".sx-readme h3{font-size:1.02rem;margin:1em 0 .3em}",
      ".sx-readme p,.sx-readme li{color:var(--td)}.sx-readme strong{color:var(--tx)}",
      ".sx-readme a,.sx-readme code{overflow-wrap:anywhere;word-break:break-word}",
      ".sx-readme code{background:var(--e1);border:1px solid var(--e3);border-radius:4px;padding:1px 5px;font-size:.86em;font-family:var(--mono)}",
      ".sx-readme pre{background:var(--bg);border:1px solid var(--e3);border-radius:8px;padding:12px;overflow:auto}.sx-readme pre code{border:0;background:none;padding:0}",
      ".sx-readme table{border-collapse:collapse;font-size:.88rem;margin:.6em 0}.sx-readme td,.sx-readme th{border:1px solid var(--e3);padding:4px 10px;text-align:left}",
      ".sx-readme a{color:var(--g)}.sx-readme blockquote{border-left:3px solid var(--e3);margin:.6em 0;padding-left:1em;color:var(--tf)}",
      ".sx-readme img{max-width:100%;height:auto}.sx-readme hr{border:0;border-top:1px solid var(--e3);margin:1.4em 0}",
      ".sx-readme h1,.sx-readme h2,.sx-readme h3,.sx-readme h4,.sx-readme h5,.sx-readme h6{scroll-margin-top:4.5rem}",
      ":root[data-theme=\"light\"] .hljs{color:var(--tx)!important}:root[data-theme=\"light\"] .hljs-comment,:root[data-theme=\"light\"] .hljs-quote,:root[data-theme=\"light\"] .hljs-meta{color:var(--tf)!important}",
      ":root[data-theme=\"light\"] .hljs-string,:root[data-theme=\"light\"] .hljs-attr,:root[data-theme=\"light\"] .hljs-addition,:root[data-theme=\"light\"] .hljs-emphasis,:root[data-theme=\"light\"] .hljs-name,:root[data-theme=\"light\"] .hljs-bullet,:root[data-theme=\"light\"] .hljs-strong{color:var(--g)!important}",
      ".hljs-section{color:var(--artifact-text)!important}",
      ":root[data-theme=\"light\"] .hljs-keyword,:root[data-theme=\"light\"] .hljs-type,:root[data-theme=\"light\"] .hljs-doctag{color:var(--reason)!important}",
      ":root[data-theme=\"light\"] .hljs-number,:root[data-theme=\"light\"] .hljs-literal,:root[data-theme=\"light\"] .hljs-attr,:root[data-theme=\"light\"] .hljs-variable{color:var(--acc)!important}",
      ":root[data-theme=\"light\"] .hljs-built_in,:root[data-theme=\"light\"] .hljs-operator,:root[data-theme=\"light\"] .hljs-attribute,:root[data-theme=\"light\"] .hljs-template-variable,:root[data-theme=\"light\"] .hljs-symbol,:root[data-theme=\"light\"] .hljs-bullet,:root[data-theme=\"light\"] .hljs-selector-attr{color:var(--acc)!important}",
      ":root[data-theme=\"light\"] .hljs-regexp,:root[data-theme=\"light\"] .hljs-subst,:root[data-theme=\"light\"] .hljs-selector-tag,:root[data-theme=\"light\"] .hljs-selector-pseudo{color:var(--reason)!important}",
      ":root[data-theme=\"light\"] .hljs-title,:root[data-theme=\"light\"] .hljs-section,:root[data-theme=\"light\"] .hljs-selector-class,:root[data-theme=\"light\"] .hljs-selector-id{color:var(--acc)!important}:root[data-theme=\"light\"] .hljs-code{color:var(--tf)!important}",
      ".sx-heading-link{margin-left:.45em;color:var(--tf)!important;text-decoration:none;font-size:.72em;opacity:0}.sx-readme h1:hover .sx-heading-link,.sx-readme h2:hover .sx-heading-link,.sx-readme h3:hover .sx-heading-link,.sx-readme h4:hover .sx-heading-link,.sx-heading-link:focus{opacity:1}",
      ".sx-hubsec{margin:0 0 1.4em}.sx-hubsec h2{font-size:1.05rem;color:var(--tx);border-bottom:1px solid var(--e3);padding-bottom:.3em;margin:0 0 .6em}",
      ".sx-hubgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(15rem,100%),1fr));gap:10px;min-width:0;max-width:100%}",
      ".sx-card{display:block;min-width:0;max-width:100%;background:var(--e1);border:1px solid var(--e3);border-radius:8px;padding:11px 13px;text-decoration:none}",
      ".sx-card:hover{border-color:var(--g);text-decoration:none}",
      ".sx-card .nm{font-family:var(--mono);font-size:.9rem;color:var(--gs);display:block;margin-bottom:.2em;word-break:break-word}",
      ".sx-card .ds{font-size:.82rem;color:var(--td);line-height:1.5}",
      // report mode (validation gate review) + tests mode (client-side runner)
      ".rp-head{padding:1.1rem clamp(1rem,4vw,2rem) .6rem;border-bottom:1px solid var(--e3)}",
      ".rp-head h1{margin:.1em 0;font-size:1.45rem;color:var(--g)}.rp-lead{color:var(--td);max-width:62rem;font-size:.93rem}",
      ".rp-verdict{display:inline-block;font-weight:700;border-radius:8px;padding:7px 14px;margin:.7em 0 .2em;border:1px solid var(--e3)}",
      ".rp-verdict.ok{background:rgba(118,185,0,.12);border-color:var(--g);color:var(--gs)}",
      ".rp-verdict.warn{background:rgba(227,179,65,.12);border-color:var(--warn);color:var(--warn)}",
      ".rp-verdict.fail{background:rgba(209,36,47,.14);border-color:var(--err);color:var(--err)}",
      ".rp-legend{display:flex;gap:14px;flex-wrap:wrap;margin:.5em 0 .2em;font-size:.8rem;color:var(--td)}.rp-legend span{display:inline-flex;align-items:center;gap:6px}",
      ".rp-dot{width:9px;height:9px;border-radius:999px;flex:none}.rp-dot.pass{background:var(--g)}.rp-dot.req{background:var(--err)}.rp-dot.rec{background:var(--warn)}.rp-dot.con{background:var(--tf)}.rp-dot.warn{background:var(--warn);box-shadow:0 0 0 2px rgba(227,160,8,.25)}",
      ".rp-cover{font-family:var(--mono);font-size:.7rem;color:var(--tf);margin-left:10px;font-weight:400}.rp-cover.degraded,.rp-cover.skipped{color:var(--warn)}",
      ".rp-degraded{color:var(--tx);background:rgba(227,160,8,.09);border:1px solid var(--warn);border-left-width:3px;border-radius:0 8px 8px 0;padding:13px 15px}.rp-degraded b{color:var(--warn);display:block;margin-bottom:3px}",
      ".rp-degnote{font-family:var(--mono);font-size:.78rem;color:var(--td);margin-top:8px;white-space:pre-wrap;word-break:break-word}",
      ".rp-wrap{display:grid;grid-template-columns:264px 1fr;min-height:60vh}@media(max-width:760px){.rp-wrap{grid-template-columns:1fr}}",
      ".rp-rail{border-right:1px solid var(--e3);padding:1rem .6rem 5rem}",
      ".rp-rail button{display:flex;width:100%;align-items:center;gap:8px;background:none;border:0;color:var(--td);text-align:left;padding:8px 10px;border-radius:7px;cursor:pointer;font:inherit;font-size:.9rem}",
      ".rp-rail button:hover{background:var(--e1);color:var(--tx)}.rp-rail button.sel{background:var(--e1);color:var(--gs)}",
      ".rp-rail .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.rp-rail .ct{font-family:var(--mono);font-size:.72rem;color:var(--tf)}",
      ".rp-main{padding:1.1rem clamp(1rem,4vw,2rem) 6rem;min-width:0}.rp-main h2{font-size:1.2rem;margin:.1em 0 .2em}",
      ".sev{font-family:var(--mono);font-size:.64rem;text-transform:uppercase;letter-spacing:.06em;border-radius:999px;padding:2px 8px;font-weight:700}",
      ".sev.req{background:rgba(209,36,47,.16);color:var(--err);border:1px solid var(--err)}.sev.rec{background:rgba(227,179,65,.14);color:var(--warn);border:1px solid var(--warn)}.sev.con{background:rgba(138,138,138,.14);color:var(--td);border:1px solid var(--tf)}",
      ".rp-why{color:var(--td);background:var(--e1);border-left:3px solid var(--g);border-radius:0 8px 8px 0;padding:11px 15px;margin:.7em 0 1.1em;font-size:.92rem}",
      ".rp-impl{margin:0 0 1.2em;border:1px solid var(--e3);border-radius:8px;background:var(--e1);overflow:hidden}",
      ".rp-impl>summary{cursor:pointer;list-style:none;padding:9px 14px;font-size:.86rem;color:var(--td);display:flex;align-items:center;gap:9px;flex-wrap:wrap}",
      ".rp-impl>summary::-webkit-details-marker{display:none}",
      ".rp-impl>summary:hover{color:var(--tx)}",
      ".rp-impl[open]>summary{border-bottom:1px solid var(--e3);background:var(--e2)}",
      ".rp-impl-tag{font-family:var(--mono);font-size:.74rem;color:var(--gs);background:rgba(118,185,0,.10);border:1px solid var(--g);border-radius:5px;padding:1px 6px}",
      ".rp-impl-loc{font-family:var(--mono);font-size:.74rem;color:var(--tf);margin-left:auto}",
      ".rp-code{padding:0}",
      ".rp-codebar{display:flex;align-items:center;gap:12px;padding:7px 13px;font-family:var(--mono);font-size:.74rem;color:var(--tf);border-bottom:1px solid var(--e3);background:var(--bg)}",
      ".rp-codebar a{margin-left:auto;color:var(--gs);text-decoration:none;white-space:nowrap}.rp-codebar a:hover{text-decoration:underline}",
      ".rp-code .sx-code{border:none;border-radius:0;max-height:48vh}",
      ".rp-coderr{padding:12px 14px;color:var(--err);font-size:.85rem}",
      ".rp-srcbtn{margin-right:auto}",
      ".rp-srcbox{display:none;margin:.6em 0 0;border:1px solid var(--e3);border-radius:8px;overflow:hidden}.rp-srcbox.open{display:block}",
      ".rp-srcnote{padding:7px 13px;font-size:.78rem;color:var(--tf);font-family:var(--mono)}",
      ".rp-srcbox .sx-code{border:none;border-radius:0;max-height:42vh}",
      ".rp-fb{display:flex;gap:8px;margin:.7em 0 1.2em;flex-wrap:wrap}.rp-fb button{background:var(--e1);border:1px solid var(--e3);color:var(--td);border-radius:7px;padding:6px 13px;line-height:1;font:inherit;font-size:.8rem;cursor:pointer;transition:background .15s,border-color .15s,color .15s}.rp-fb button:hover{background:var(--e2)}.rp-fb button.on{border-color:var(--g);color:var(--gs)}",
      ".rp-off{background:var(--e1);border:1px solid var(--e3);border-left:3px solid var(--e3);border-radius:9px;padding:11px 14px;margin:10px 0}.rp-off.agree{border-left-color:var(--g)}.rp-off.dismiss{border-left-color:var(--tf);opacity:.65}",
      ".rp-off .pg{font-family:var(--mono);font-size:.82rem;color:var(--gs);word-break:break-word}.rp-off .dt{font-family:var(--mono);font-size:.8rem;color:var(--td);margin:.3em 0;word-break:break-word}",
      ".rp-off .fix{background:rgba(118,185,0,.07);border-left:3px solid var(--g);border-radius:0 7px 7px 0;padding:8px 12px;margin:.45em 0;font-size:.86rem;color:var(--tx)}.rp-off .fix b{color:var(--gs);font-family:var(--mono);font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:2px}",
      ".rp-off .acts{display:flex;gap:8px;margin:.8em 0 .5em;flex-wrap:wrap}.rp-off .acts button{background:var(--e2);border:1px solid var(--e3);color:var(--td);border-radius:7px;padding:6px 12px;line-height:1;font:inherit;font-size:.78rem;cursor:pointer;transition:background .15s,border-color .15s,color .15s}.rp-off .acts button:hover{background:var(--e3)}",
      ".rp-off .acts button.on-agree{background:var(--g);color:#0a0a0a;border-color:var(--g)}.rp-off .acts button.on-dismiss{background:var(--tf);color:#0a0a0a;border-color:var(--tf)}",
      ".rp-off textarea{width:100%;margin-top:.45em;background:var(--bg);color:var(--tx);border:1px solid var(--e3);border-radius:6px;padding:7px 9px;font:inherit;font-size:.84rem;resize:vertical;min-height:36px}",
      ".rp-clean{color:var(--gs);background:rgba(118,185,0,.08);border:1px solid var(--g);border-radius:8px;padding:13px 15px}",
      ".rp-bar{position:fixed;bottom:0;left:0;right:0;background:var(--e1);border-top:1px solid var(--e3);padding:9px clamp(1rem,4vw,2rem);display:flex;align-items:center;gap:12px;flex-wrap:wrap;font-size:.85rem;z-index:5}.rp-bar .sp{flex:1}.rp-bar .nt{color:var(--tf);font-size:.78rem}",
      ".rp-bar button{background:var(--e2);border:1px solid var(--e3);color:var(--tx);border-radius:7px;padding:7px 14px;font:inherit;font-weight:600;cursor:pointer}.rp-bar button.prim{background:var(--g);color:#0a0a0a;border-color:var(--g)}",
      ".ts-row{display:flex;align-items:center;gap:10px;margin:.5em 0}.ts-badge{font-family:var(--mono);font-size:.76rem;padding:2px 9px;border-radius:999px;border:1px solid var(--e3);color:var(--td)}",
      ".ts-badge.ok{background:var(--g);color:#000;border-color:var(--g)}.ts-badge.err{background:var(--err);color:#fff;border-color:var(--err)}.ts-badge.run{color:var(--gs)}",
      ":root[data-theme=\"light\"] .rp-bar button.prim,:root[data-theme=\"light\"] .ts-badge.ok{color:#fff}",
      ".ts-pre{background:var(--e1);border:1px solid var(--e3);border-radius:8px;padding:12px;font:12px/1.5 var(--mono);overflow:auto;white-space:pre-wrap;margin:.4em 0}",
      ".ts-grid{display:grid;grid-template-columns:auto 1fr;gap:0;border:1px solid var(--e3);border-radius:8px;overflow:hidden;margin:.5em 0;font-size:.86rem}",
      ".ts-grid div{padding:6px 12px;border-bottom:1px solid var(--e3)}.ts-grid .k{font-family:var(--mono);color:var(--gs);font-size:.8rem;background:var(--e1)}"
    ].join("");
    document.head.appendChild(s);
  }

  function highlight(code, lang) {
    if (window.hljs) { try { return window.hljs.highlight(code, { language: lang }).value; } catch (e) {} }
    return esc(code);
  }

  // Markdown for the hub mode (the README reflection).
  // Loads the same-origin vendored Marked module once; raw text remains readable if loading fails.
  function loadMarked() {
    if (!window.__sxMarkedP) {
      window.__sxMarkedP = import(vendorUrl("marked-14.1.4.esm.js"))
        .then(function (m) { return m.marked || m.default; }).catch(function () { return null; });
    }
    return window.__sxMarkedP;
  }

  function App(cfg, mount) {
    this.cfg = cfg;
    this.mount = mount;
    this.ties = (cfg.ties && cfg.ties.length ? cfg.ties : ["build"]).filter(function (t) { return SESSIONS[t]; });
    this.cache = {};
    this.current = null;
    this.currentView = null;
    this.health = {};
    this.viewerEl = null;
    this.railEl = null;
    this.answerEl = null;
    this._key = "";
  }

  // The first key-bearing tie drives the LLM explainer credential.
  App.prototype.keyTie = function () {
    for (var i = 0; i < this.ties.length; i++) { var s = SESSIONS[this.ties[i]]; if (s.kind === "key") return s; }
    return SESSIONS.build;
  };
  App.prototype.key = function () { return this._key || ""; };

  App.prototype.files = function () {
    if (this.cfg.groups) {
      var out = [];
      this.cfg.groups.forEach(function (g) { (g.files || []).forEach(function (f) { out.push(f); }); });
      return out;
    }
    return this.cfg.files || [];
  };

  App.prototype.fileEntry = function (path) {
    var files = this.files();
    for (var i = 0; i < files.length; i++) if (files[i].path === path) return files[i];
    return null;
  };
  App.prototype.defaultView = function (path) {
    return isMarkdown(path) && this.cfg.render_markdown ? "render" : "source";
  };
  App.prototype.urlRequest = function () {
    var params = new URLSearchParams(location.search || ""), path = params.get("file"), view = params.get("view");
    if (!this.fileEntry(path)) path = null;
    if (view !== "render" && view !== "source") view = null;
    return { path: path, view: view };
  };
  App.prototype.fileHref = function (path, view, hash) {
    var u = new URL(location.href);
    u.searchParams.set("file", path);
    if (view && view !== this.defaultView(path)) u.searchParams.set("view", view);
    else u.searchParams.delete("view");
    u.hash = hash || "";
    return u.href;
  };
  App.prototype.writeFileUrl = function (path, view, hash, replace) {
    var href = this.fileHref(path, view, hash);
    try { history[replace ? "replaceState" : "pushState"]({ file: path, view: view }, "", href); } catch (e) {}
  };
  App.prototype.scrollToHash = function () {
    if (!location.hash) return;
    var id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch (e) { return; }
    requestAnimationFrame(function () {
      var target = document.getElementById(id);
      if (target) target.scrollIntoView({ block: "start" });
    });
  };

  App.prototype.fetchText = function (path) {
    var self = this;
    if (this.cache[path] != null) return Promise.resolve(this.cache[path]);
    return fetch(path).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.text();
    }).then(function (t) { self.cache[path] = t; return t; });
  };

  App.prototype.showFile = function (path, range, note, options) {
    var self = this, opts = options || {}, f = this.fileEntry(path);
    if (!f) return;
    var view = opts.view || (range ? "source" : this.defaultView(path));
    if (!isMarkdown(path) || (view !== "render" && view !== "source")) view = "source";
    var hash = opts.hash == null ? "" : opts.hash;
    this.current = path;
    this.currentView = view;
    document.title = path + " · " + (this.cfg.title || "explore");
    if (opts.updateUrl !== false) this.writeFileUrl(path, view, hash, !!opts.replace);
    this.paintRail();
    var main = this.viewerEl;
    main.innerHTML = "";
    var bar = el("div", "sx-bar");
    bar.appendChild(el("span", "fn", esc(path)));
    if (f.role) bar.appendChild(el("span", "rl", "&middot; " + esc(f.role)));
    bar.appendChild(el("span", "sp"));
    if (isMarkdown(path)) {
      ["render", "source"].forEach(function (mode) {
        var a = el("a", "sx-btn" + (view === mode ? " on" : ""), mode === "render" ? "Rendered" : "Source");
        a.href = self.fileHref(path, mode, "");
        a.onclick = function (e) { e.preventDefault(); self.showFile(path, null, note, { view: mode }); };
        bar.appendChild(a);
      });
    }
    var link = el("button", "sx-btn", "Copy link");
    link.onclick = function () {
      var href = self.fileHref(path, view, location.hash);
      if (navigator.clipboard) navigator.clipboard.writeText(href).then(function () { link.textContent = "Copied"; setTimeout(function () { link.textContent = "Copy link"; }, 1200); }).catch(function () { window.prompt("Copy this document URL", href); });
      else window.prompt("Copy this document URL", href);
    };
    var copy = el("button", "sx-btn", "Copy"); copy.onclick = function () { self.copy(path); };
    var dl = el("button", "sx-btn", "Download"); dl.onclick = function () { self.download(path); };
    bar.appendChild(link); bar.appendChild(copy); bar.appendChild(dl);
    main.appendChild(bar);
    if (note) main.appendChild(el("div", "sx-note", esc(note)));
    if (view === "render") {
      var doc = el("article", "sx-readme");
      doc.innerHTML = "<div class='sx-note'>Rendering " + esc(path) + "...</div>";
      main.appendChild(doc);
      Promise.all([this.fetchText(path), loadMarked()]).then(function (result) {
        var text = result[0], marked = result[1];
        if (!marked) {
          doc.innerHTML = "<div class='sx-note'>The Markdown renderer could not load. Showing source text.</div><pre>" + esc(text) + "</pre>";
          return;
        }
        doc.innerHTML = safeMarkdownHtml(marked.parse(text));
        var used = {};
        doc.querySelectorAll("h1,h2,h3,h4,h5,h6").forEach(function (h) {
          var id = headingSlug(h.textContent, used); h.id = id;
          var anchor = el("a", "sx-heading-link", "#");
          anchor.href = self.fileHref(path, "render", "#" + id);
          anchor.setAttribute("aria-label", "Link to " + h.textContent.trim());
          h.appendChild(anchor);
        });
        doc.querySelectorAll("a[href]").forEach(function (a) {
          var raw = a.getAttribute("href");
          if (!raw || /^(?:mailto:|https?:)/i.test(raw)) return;
          var target;
          try { target = new URL(raw, new URL(path, location.href)); } catch (e) { return; }
          var files = self.files(), match = null;
          for (var i = 0; i < files.length; i++) {
            var candidate = new URL(files[i].path, location.href);
            if (candidate.pathname === target.pathname) { match = files[i]; break; }
          }
          if (!match) return;
          var nextView = self.defaultView(match.path);
          a.href = self.fileHref(match.path, nextView, target.hash);
          a.onclick = function (e) {
            if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
            e.preventDefault();
            self.showFile(match.path, null, null, { view: nextView, hash: target.hash });
          };
        });
        doc.querySelectorAll("pre code").forEach(function (b) { try { if (window.hljs) window.hljs.highlightElement(b); } catch (e) {} });
        self.scrollToHash();
      }).catch(function (e) {
        doc.innerHTML = "<div class='sx-note'>Could not render " + esc(path) + ": " + esc(e.message) + "</div>";
      });
      return;
    }
    var pre = el("pre", "sx-code", "<table><tbody></tbody></table>");
    main.appendChild(pre);
    this.fetchText(path).then(function (text) {
      var lines = highlight(text, langOf(path)).split("\n");
      var html = "";
      for (var i = 0; i < lines.length; i++) {
        var n = i + 1;
        var hl = range && n >= range[0] && n <= range[1] ? " class=hl" : "";
        html += "<tr" + hl + "><td class=ln>" + n + "</td><td class=lc>" + (lines[i] || " ") + "</td></tr>";
      }
      pre.querySelector("tbody").innerHTML = html;
      if (range) { var row = pre.querySelector("tr.hl"); if (row) row.scrollIntoView({ block: "center" }); }
    }).catch(function (e) {
      pre.innerHTML = "<div style='padding:14px;color:var(--err)'>Could not load " + esc(path) + ": " + esc(e.message) +
        ". Source ships beside this page on the deploy and is served from the repo in the lab.</div>";
    });
  };

  App.prototype.copy = function (path) {
    this.fetchText(path).then(function (t) { if (navigator.clipboard) navigator.clipboard.writeText(t); });
  };
  App.prototype.download = function (path) {
    this.fetchText(path).then(function (t) {
      var a = el("a"); a.href = URL.createObjectURL(new Blob([t], { type: "text/plain" }));
      a.download = path.split("/").pop(); document.body.appendChild(a); a.click(); a.remove();
    });
  };

  App.prototype.selfAssess = function () {
    var self = this, files = this.files();
    return Promise.all(files.map(function (f) {
      return self.fetchText(f.path).then(function (t) {
        var bytes = new Blob([t]).size;
        self.health[f.path] = (f.bytes != null && Math.abs(bytes - f.bytes) > Math.max(8, f.bytes * 0.02)) ? "drift" : "ok";
      }).catch(function () { self.health[f.path] = "gone"; });
    })).then(function () { self.paintRail(); });
  };

  App.prototype.ask = function (question) {
    var self = this, ans = this.answerEl, tie = this.keyTie();
    ans.className = "sx-answer"; ans.textContent = "thinking...";
    var k = this.key();
    if (!k) { ans.className = "sx-answer err"; ans.textContent = "Add a " + tie.label + " above first."; return; }
    if (!this.current) { ans.className = "sx-answer err"; ans.textContent = "Open a file first, then ask."; return; }
    this.fetchText(this.current).then(function (code) {
      var hub = self.cfg.mode === "hub";
      var sys = hub
        ? "You answer questions about this repository for someone navigating it, using the README shown and " +
          "the linked structure. Be concrete and brief, and point to the right folder, file, or explorer. " +
          "If the README does not cover it, say so."
        : "You explain source code to a learner reading it in context. Answer ONLY about the file shown. " +
          "Be concrete and brief. Reference line numbers and identifiers from the file. If the question is not " +
          "answerable from this file, say so.";
      var user = (hub ? "REPOSITORY README (" : "FILE: ") + self.current + (hub ? ")" : "") + "\n\n" + code + "\n\nQUESTION: " + question;
      return courseRuntime().then(function (shared) {
        return shared.chat({
          model: self.cfg.model || null,
          messages: [{ role: "system", content: sys }, { role: "user", content: user }],
          max_tokens: 1024,
          temperature: 0.2
        });
      });
    }).then(function (j) {
      var msg = j && j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content;
      ans.className = "sx-answer"; ans.textContent = msg || "(no answer)";
    }).catch(function (e) { ans.className = "sx-answer err"; ans.textContent = "Request failed: " + e.message; });
  };

  App.prototype.fileButton = function (f) {
    var self = this, h = this.health[f.path];
    var b = el("a", "sx-file" + (this.current === f.path ? " sel" : ""));
    b.href = this.fileHref(f.path, this.defaultView(f.path), "");
    if (this.current === f.path) b.setAttribute("aria-current", "page");
    b.innerHTML = "<span class=nm><span>" + esc(f.path) + "</span>" +
      (h ? "<span class='sx-dot " + h + "' title='" + h + "'></span>" : "") + "</span>" +
      (f.role ? "<span class=rl>" + esc(f.role) + "</span>" : "");
    b.onclick = function (e) {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault(); self.showFile(f.path);
    };
    return b;
  };

  // Hub mode: render the README as the main view and a linkage map of the repo in the rail,
  // so the SKILL.html is a live reflection of the README that links the whole substrate.
  App.prototype.renderReadme = function () {
    var self = this, main = this.viewerEl;
    this.current = this.cfg.readme;
    main.innerHTML = "<div class='sx-note'>Loading " + esc(this.cfg.readme) + "...</div>";
    Promise.all([this.fetchText(this.cfg.readme), loadMarked()]).then(function (r) {
      var text = r[0], marked = r[1];
      var d = el("div", "sx-readme");
      d.innerHTML = marked ? safeMarkdownHtml(marked.parse(text)) : "<pre>" + esc(text) + "</pre>";
      d.querySelectorAll("pre code").forEach(function (b) { try { if (window.hljs) window.hljs.highlightElement(b); } catch (e) {} });
      main.innerHTML = ""; main.appendChild(d);
    }).catch(function (e) {
      main.innerHTML = "<div class='sx-note'>Could not load " + esc(self.cfg.readme) + ": " + esc(e.message) + "</div>";
    });
  };

  // Hub with no README (surface / course hubs): the link groups ARE the content, rendered as
  // card sections in the main column, so every hub is interactive (query + self-assess) without
  // needing a README. The rail still carries the same links for navigation.
  App.prototype.renderHubCards = function () {
    var main = this.viewerEl; main.innerHTML = "";
    (this.cfg.links || []).forEach(function (sec) {
      var s = el("div", "sx-hubsec");
      var heading = el("h2");
      heading.textContent = sec.title || "";
      s.appendChild(heading);
      var g = el("div", "sx-hubgrid");
      (sec.items || []).forEach(function (it) {
        var a = el("a", "sx-card"); a.href = it.href;
        var name = el("span", "nm");
        name.textContent = it.label || "";
        a.appendChild(name);
        if (it.desc) {
          var description = el("span", "ds");
          description.textContent = it.desc;
          a.appendChild(description);
        }
        g.appendChild(a);
      });
      s.appendChild(g); main.appendChild(s);
    });
  };

  App.prototype.paintRail = function () {
    var self = this, r = this.railEl, cfg = this.cfg;
    r.innerHTML = "";
    if (cfg.mode === "hub") {
      (cfg.links || []).forEach(function (sec) {
        var heading = el("h3");
        heading.textContent = sec.title || "";
        r.appendChild(heading);
        (sec.items || []).forEach(function (it) {
          var a = el("a", "sx-file"); a.href = it.href;
          var name = el("span", "nm");
          var label = el("span");
          label.textContent = it.label || "";
          name.appendChild(label);
          a.appendChild(name);
          if (it.desc) {
            var role = el("span", "rl");
            role.textContent = it.desc;
            a.appendChild(role);
          }
          r.appendChild(a);
        });
      });
      return;
    }
    if (cfg.groups) {
      cfg.groups.forEach(function (g) {
        r.appendChild(el("h3", null, esc(g.title)));
        (g.files || []).forEach(function (f) { r.appendChild(self.fileButton(f)); });
      });
    } else {
      r.appendChild(el("h3", null, "Files in this folder"));
      (cfg.files || []).forEach(function (f) { r.appendChild(self.fileButton(f)); });
    }
    if ((cfg.tour || []).length) {
      r.appendChild(el("h3", null, "Guided tour"));
      cfg.tour.forEach(function (t) {
        var b = el("button", "sx-tour", "<b>" + esc(t.title) + "</b>" + esc(t.file) + (t.lines ? " :" + t.lines[0] + "-" + t.lines[1] : ""));
        b.onclick = function () { self.showFile(t.file, t.lines, t.note, { view: "source" }); };
        r.appendChild(b);
      });
    }
    var sa = el("button", "sx-btn", "Self-assess files"); sa.style.marginTop = "1em";
    sa.onclick = function () { sa.textContent = "checking..."; self.selfAssess().then(function () { sa.textContent = "Self-assess files"; }); };
    r.appendChild(sa);
    if ((cfg.related || []).length) {
      r.appendChild(el("h3", null, "Related"));
      var rel = el("div", "sx-related");
      cfg.related.forEach(function (x) {
        var link = el("a");
        link.textContent = x.label || "";
        link.href = x.href;
        rel.appendChild(link);
      });
      r.appendChild(rel);
    }
  };

  // Render one credential row per tie. The course runtime owns the tab-scoped key.
  App.prototype.mountTies = function (parent) {
    var self = this;
    this.ties.forEach(function (name) {
      var s = SESSIONS[name];
      var row = el("div", "sx-tie");
      row.appendChild(el("span", "lab", esc(s.label) + ":"));
      if (s.kind === "key") {
        var inp = el("input"); inp.type = "password"; inp.placeholder = s.placeholder;
        courseRuntime().then(function (shared) {
          self._key = shared.getKey() || "";
          inp.value = self._key;
        });
        inp.oninput = function () {
          self._key = inp.value.trim();
          courseRuntime().then(function (shared) { shared.setKey(self._key); });
        };
        row.appendChild(inp);
      }
      parent.appendChild(row);
      parent.appendChild(el("div", "sx-tie", "<span class=svc style='font-size:.78rem'>" + esc(s.note) + "</span>"));
    });
  };

  // The dark/light theme the page currently shows: an explicit data-theme wins, else the OS.
  function curTheme() {
    var a = document.documentElement.getAttribute("data-theme");
    if (a) return a;
    return (window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches) ? "light" : "dark";
  }
  // Wire the topbar's theme button: flip data-theme, remember the choice, repaint the icon. The
  // palette (injectChrome) and the course pages' toggle share this exact data-theme + localStorage
  // contract, so the whole bundle themes from one rule and one stored preference.
  function wireThemeToggle(btn) {
    if (!btn) return;
    function paint() { var t = curTheme(); btn.textContent = t === "light" ? "☾" : "☀"; btn.title = t === "light" ? "Switch to dark theme" : "Switch to light theme"; }
    btn.addEventListener("click", function () {
      var next = curTheme() === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("theme", next); } catch (e) {}
      paint();
    });
    paint();
  }

  // The shared sticky topbar: a logo home-link and an "up" breadcrumb, so every framer page
  // (hub, explorer, report, tests) has the same persistent nav and always a way back. Prepended
  // so it survives the modes that set mount.innerHTML. nav = { home, up:{label,href} } from config.
  App.prototype.mountTopbar = function () {
    var nav = this.cfg.nav || {}, home = nav.home || "index.html";
    var existing = document.querySelector('header[data-skill-header="1"]');
    if (existing) {
      existing.classList.add("sx-topbar", "sx-page-topbar");
      var existingNav = existing.querySelector("nav");
      if (existingNav) existingNav.classList.add("sx-page-nav");
      if (!existing.querySelector(".sx-theme")) {
        var theme = el("button", "sx-theme");
        theme.type = "button";
        theme.setAttribute("aria-label", "Toggle dark or light theme");
        existing.appendChild(theme);
      }
      if (existing !== document.body.firstElementChild) document.body.insertBefore(existing, document.body.firstChild);
      wireThemeToggle(existing.querySelector(".sx-theme"));
      return existing;
    }
    var bar = el("div", "sx-topbar");
    var logo = el("a", "sx-logo");
    logo.href = home;
    logo.textContent = "NVIDIA DLI";
    bar.appendChild(logo);
    if (nav.up) {
      var up = el("a", "sx-up");
      up.href = nav.up.href;
      up.textContent = "↑ " + (nav.up.label || "");
      bar.appendChild(up);
    }
    if (nav.map) {
      var map = el("a", "sx-map");
      map.href = nav.map.href;
      map.textContent = nav.map.label || "Map";
      bar.appendChild(map);
    }
    var crumb = el("span", "sx-crumb");
    crumb.textContent = this.cfg.title || "";
    bar.appendChild(crumb);
    var themeButton = el("button", "sx-theme");
    themeButton.type = "button";
    themeButton.setAttribute("aria-label", "Toggle dark or light theme");
    bar.appendChild(themeButton);
    this.mount.insertBefore(bar, this.mount.firstChild);
    wireThemeToggle(this.mount.querySelector(".sx-theme"));
  };

  App.prototype.mountUI = function () {
    var self = this, cfg = this.cfg;
    if (cfg.mode === "report") return this.mountReport();
    if (cfg.mode === "tests") return this.mountTests();
    this.mountTopbar();
    if (!document.querySelector(".skill-static")) {
      var head = el("header", "sx-head");
      head.appendChild(el("p", null, "<a href='#' onclick='history.length>1?history.back():null;return false'>&larr; back</a>"));
      head.appendChild(el("h1", null, esc(cfg.title || "Folder explorer")));
      if (cfg.summary) head.appendChild(el("p", "sx-lead", esc(cfg.summary)));
      this.mount.appendChild(head);
    }

    var wrap = el("div", "sx-wrap");
    this.railEl = el("nav", "sx-rail");
    var main = el("main", "sx-main");
    wrap.appendChild(this.railEl); wrap.appendChild(main);
    this.mount.appendChild(wrap);

    this.viewerEl = el("div"); main.appendChild(this.viewerEl);

    var hub = cfg.mode === "hub";
    var ask = el("section", "sx-ask");
    ask.appendChild(el("h3", null, hub ? "Ask about this repository" : "Ask about the open file"));
    this.mountTies(ask);
    var ta = el("textarea");
    ta.placeholder = hub ? "e.g. where does the browser course reach the model, and what validates a page before it ships?"
                         : "e.g. what does this file do, and where is the load-bearing logic?";
    ask.appendChild(ta);
    var send = el("button", "sx-send", "Explain");
    send.onclick = function () { var q = ta.value.trim(); if (q) self.ask(q); };
    ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send.click(); } });
    ask.appendChild(send);
    this.answerEl = el("div", "sx-answer");
    this.answerEl.textContent = "Open a file, then ask. Answers use the course model route and browser-stored key.";
    ask.appendChild(this.answerEl);
    main.appendChild(ask);

    this.answerEl.textContent = hub
      ? "Ask about the repo, or follow a link to explore a folder. Answers use the course model route and browser-stored key."
      : this.answerEl.textContent;

    this.paintRail();
    if (hub) {
      if (cfg.readme) this.renderReadme(); else this.renderHubCards();
    } else {
      var request = this.urlRequest(), first = request.path ? this.fileEntry(request.path) : this.files()[0];
      if (first) {
        var initialView = request.view || this.defaultView(first.path);
        if (!isMarkdown(first.path)) initialView = "source";
        this.showFile(first.path, null, null, { view: initialView, updateUrl: false, hash: location.hash });
        this.writeFileUrl(first.path, initialView, location.hash, true);
      }
      window.addEventListener("popstate", function () {
        var next = self.urlRequest(), fallback = self.files()[0], file = next.path ? self.fileEntry(next.path) : fallback;
        if (file) self.showFile(file.path, null, null, { view: isMarkdown(file.path) ? (next.view || self.defaultView(file.path)) : "source", updateUrl: false, hash: location.hash });
      });
      window.addEventListener("hashchange", function () { self.scrollToHash(); });
      this.selfAssess();
    }
  };

  // ── report mode: the validation gate review (formerly validation.html) ───────
  // The suite list (id, name, tier, the sentence describing what it enforces, and a pointer
  // to the code that runs it) comes from the gate report's `suites` block, which validate_bundle
  // builds from its SUITE_META single source of truth. The report reflects the gate; it does not
  // re-describe the checks here. This slim fallback only keeps the rail rendering against a stale
  // gate.json built before suites/ existed (no `why`, no code panel until the report is rebuilt).
  var FALLBACK_SUITES = [
    { id: "links", name: "Links & assets", tag: "required" },
    { id: "cross_course", name: "Cross-course links", tag: "recommended" },
    { id: "asset_leaks", name: "Asset leaks", tag: "recommended" },
    { id: "layout", name: "Layout & mounts", tag: "required" },
    { id: "grounding", name: "Grounding", tag: "recommended" },
    { id: "reachability", name: "Reachability", tag: "recommended" },
    { id: "foyer", name: "Release foyer", tag: "required" },
    { id: "page_audit", name: "Page audit", tag: "recommended" },
    { id: "prose_variety", name: "Prose rhythm", tag: "consider" },
    { id: "prose_buzz", name: "Buzz cadence", tag: "recommended" },
    { id: "color_theme", name: "Color theme", tag: "recommended" },
    { id: "figure_audit", name: "Figure audit", tag: "recommended" },
    { id: "cell_audit", name: "Cell & artifact contract", tag: "recommended" },
    { id: "diagram_geom", name: "Figure geometry", tag: "recommended" },
    { id: "materials", name: "Materials", tag: "recommended" }
  ];
  var TIER = { required: { label: "Required" }, recommended: { label: "Recommended" }, consider: { label: "Consider" } };
  var SEVRANK = { required: 3, recommended: 2, consider: 1 };
  function sevc(x) { return x === "required" ? "req" : x === "consider" ? "con" : "rec"; }
  function normalizedVerdict(value) { return value === "agree" || value === "dismiss" ? value : ""; }
  function normalizedSuiteStatus(value) { return value === "degraded" || value === "skipped" ? value : ""; }
  function normalizedTier(value) { return Object.prototype.hasOwnProperty.call(TIER, value) ? value : "recommended"; }
  function normalizedCritique(value) {
    var record = value && typeof value === "object" ? value : {};
    return {
      verdict: normalizedVerdict(record.verdict),
      comment: typeof record.comment === "string" ? record.comment.slice(0, 12000) : ""
    };
  }

  App.prototype.mountReport = function () {
    var mount = this.mount, GATE = this.cfg.gate || null, CRIT = {}, sel = "links", filter = "all";
    var LS = "nemoclaw-gate-critique-v1";
    var gd = document.getElementById("gate-data");
    if (!GATE && gd && gd.textContent.trim()) { try { GATE = JSON.parse(gd.textContent); } catch (e) {} }
    try {
      var savedCritique = JSON.parse(localStorage.getItem(LS) || "{}");
      CRIT = savedCritique && typeof savedCritique === "object" ? savedCritique : {};
      Object.keys(CRIT).forEach(function (key) { CRIT[key] = normalizedCritique(CRIT[key]); });
    } catch (e) { CRIT = {}; }
    var self = this;
    function suiteList() { return (GATE && GATE.suites && GATE.suites.length) ? GATE.suites : FALLBACK_SUITES; }
    mount.innerHTML =
      '<div class="rp-head"><p><a href="index.html">&larr; back</a></p><h1>Validation gate</h1>' +
      '<p class="rp-lead">The automated quality gate, opened for review. Each check states what it enforces and lists the entries it flagged, every one tagged by severity and carrying the change to make. Work top-down: Required blocks the ship, Recommended is a real defect, Consider is a judgment call. Disagree? Mark it expected and leave a note; Export writes a gate-critique.json your agent can act on.</p>' +
      '<div id="rp-verdict" class="rp-verdict">loading...</div>' +
      '<div class="rp-legend"><span><span class="rp-dot req"></span>Required &middot; ship-blocking</span><span><span class="rp-dot rec"></span>Recommended &middot; a real defect</span><span><span class="rp-dot con"></span>Consider &middot; non-critical improvement</span><span><span class="rp-dot warn"></span>Did not run &middot; not trustworthy</span><span><span class="rp-dot pass"></span>Ran, clean</span></div></div>' +
      '<div class="rp-wrap"><nav class="rp-rail" id="rp-rail"></nav><main class="rp-main" id="rp-main"></main></div>' +
      '<div class="rp-bar"><span id="rp-counts">&mdash;</span><span class="sp"></span><span class="nt" id="rp-note"></span>' +
      '<button id="rp-copy">Copy for agent</button><button class="prim" id="rp-export">Export critique</button><button id="rp-clear">Clear</button></div>';
    this.mountTopbar();
    function saveCrit() { try { localStorage.setItem(LS, JSON.stringify(CRIT)); } catch (e) {} paintCounts(); }
    function offenders(s) {
      if (!GATE) return [];
      if (s.id === "layout") return GATE.validate_layout_ok ? [] : (GATE.validate_layout_failures || []).filter(function (x) { return String(x).charAt(0) === "["; }).map(function (x) { return { page: "layout", detail: String(x), severity: "required", fix: "Repair the mount selector, asset path, or SKILL beacon so the static layout check passes." }; });
      if (s.id === "foyer") { var f = GATE.foyer_release || {}; return f.ok ? [] : (f.violations || []).map(function (v) { return { page: "foyer", detail: (v.kind || "") + ": " + (v.detail || ""), severity: "required", fix: "Remove the unreleased course from the foyer, or mark it released." }; }); }
      var offs = ((GATE.findings_detail || {})[s.id]) || [];
      return offs.slice().sort(function (a, b) { return (SEVRANK[b.severity || "recommended"] || 2) - (SEVRANK[a.severity || "recommended"] || 2); });
    }
    function dotClass(s, offs) {
      if (!GATE) return "pass";
      if (s.status === "degraded" || s.status === "skipped") return "warn";
      if (s.id === "layout") return GATE.validate_layout_ok ? "pass" : "req";
      if (s.id === "foyer") return (GATE.foyer_release || {}).ok ? "pass" : "req";
      if (!offs.length) return "pass";
      var w = 0, t = "rec"; offs.forEach(function (o) { var r = SEVRANK[o.severity || "recommended"] || 2; if (r > w) { w = r; t = o.severity || "recommended"; } });
      return sevc(t);
    }
    function fkey(sid, o) { return sid + "::" + (o.page || "") + "::" + (o.detail || ""); }
    // The code that runs the check, surfaced inline. impl.{file,symbol,lines} comes from the gate;
    // the source ships read-only beside this report on the deploy, so a reviewer audits the actual
    // logic here, in the browser, instead of trusting the description. Opaque checks cannot ship:
    // the gate fails any suite whose impl it cannot resolve, so this panel is always backed.
    function implDisclosure(s) {
      var im = s.impl; if (!im || !im.file) return "";
      var loc = esc(im.file) + (im.symbol ? " &middot; " + esc(im.symbol) + "()" : "") +
        (im.lines ? " &middot; lines " + im.lines[0] + "–" + im.lines[1] : "");
      return '<details class="rp-impl"><summary><span class="rp-impl-tag">&#10216;/&#10217;</span> the code that runs this check ' +
        '<span class="rp-impl-loc">' + loc + '</span></summary>' +
        '<div class="rp-code" data-file="' + esc(im.file) + '">loading source…</div></details>';
    }
    // Preview the offending content where it lives. The validated source ships read-only beside
    // this report (same repo-relative path), so a reviewer opens the actual file, sees the chunk
    // around the issue with the offending line highlighted, and judges it in context.
    function isFilePage(p) { return !!p && p.indexOf("/") >= 0 && /\.(html?|md|ipynb|css|js|mjs|py|sh|svg|json)$/i.test(p); }
    function deriveNeedle(sid, detail) {
      if (!detail) return null;
      if (sid === "grounding" && detail.indexOf("em-dash") >= 0) return "—";       // the glyph itself
      if (sid === "color_theme") { var m = detail.match(/^(\S+) on /); if (m) return m[1]; }   // the color literal
      if (sid === "prose_buzz") { var b = detail.match(/^\[[^\]]+\]\s*(.+)$/); if (b) return b[1].slice(0, 80); }  // the sentence
      if (sid === "redundancy") {                                  // detail is “figure/A” ⟂ “prose/B”; locate the prose half (a real sentence in the file)
        var q = detail.match(/“([^”]{6,})”/g);
        if (q && q.length) { var last = q[q.length - 1].replace(/[“”]/g, ""); return last.slice(0, 60); }
      }
      if (sid === "links" || sid === "cross_course" || sid === "asset_leaks") return detail.split(" · ")[0].trim();  // the href
      var g = detail.split(" · ")[0].split(";")[0].trim();   // generic: the first clause before a separator
      return g.length >= 4 ? g.slice(0, 80) : null;
    }
    // Some findings are about a SPECIFIC line (a color literal, an em-dash, a link, a buzz
    // sentence); others are about the file AS A WHOLE (it is not linked from a hub; its overall
    // rhythm). The preview always states which, so it never shows a bare file with no "where".
    var WHOLE_FILE = {
      reachability: "Whole-file finding: this page is not reached by following links from any SKILL hub. The problem is the file's place in the navigation, not a line inside it; the fix is to link it from the relevant hub. The page is shown below so you can confirm what it is.",
      prose_variety: "Whole-file finding: this is a score over the page's whole narrative (sentence-length spread, staccato runs), not one line. Read the page below for its cadence.",
      page_audit: "Whole-file finding: the page drifted from the shared HTML contract. The detail above names the drifted token or missing asset; search the file below for it."
    };
    function previewOffender(box, page, sid, detail) {
      if (box.dataset.loaded) return; box.dataset.loaded = "1";
      box.innerHTML = '<div class="rp-srcnote">loading ' + esc(page) + '…</div>';
      self.fetchText(page).then(function (text) {
        var whole = WHOLE_FILE[sid];
        var raw = text.split("\n"), needle = whole ? null : deriveNeedle(sid, detail), hit = -1;
        if (needle) { for (var i = 0; i < raw.length; i++) { if (raw[i].indexOf(needle) >= 0) { hit = i; break; } } }
        var hi = highlight(text, langOf(page)).split("\n");
        var a, b, note;
        if (hit >= 0) { a = Math.max(0, hit - 6); b = Math.min(hi.length - 1, hit + 6); note = "Flagged at line " + (hit + 1) + " (highlighted). The whole file is one click away."; }
        else if (whole) { a = 0; b = Math.min(hi.length - 1, 34); note = whole; }
        else { a = 0; b = Math.min(hi.length - 1, 28); note = needle ? "The flagged text (" + esc(needle) + ") was not found at this path; the file may have changed since the gate ran. Showing the head." : "Showing the file head; open the whole file to review."; }
        var rows = "";
        for (var j = a; j <= b; j++) rows += "<tr" + (j === hit ? " class=hl" : "") + "><td class=ln>" + (j + 1) + "</td><td class=lc>" + (hi[j] || " ") + "</td></tr>";
        box.innerHTML = '<div class="rp-codebar"><span>' + esc(page) + (hit >= 0 ? " &middot; line " + (hit + 1) : "") + '</span>' +
          '<a href="' + esc(page) + '" target="_blank" rel="noopener">open whole file &rarr;</a></div>' +
          '<div class="rp-srcnote">' + note + '</div><pre class="sx-code"><table><tbody>' + rows + '</tbody></table></pre>';
      }).catch(function (e) {
        box.innerHTML = '<div class="rp-coderr">Could not load ' + esc(page) + ": " + esc(e.message) +
          ". The validated source ships beside this report on the deploy; serve over http, not file://.</div>";
      });
    }
    function wireImpl(m, s) {
      var det = m.querySelector(".rp-impl"); if (!det) return;
      var box = det.querySelector(".rp-code"), im = s.impl;
      det.addEventListener("toggle", function () {
        if (!det.open || box.dataset.loaded) return;
        box.dataset.loaded = "1";
        self.fetchText(im.file).then(function (text) {
          var all = highlight(text, langOf(im.file)).split("\n");
          var a = im.lines ? Math.max(1, im.lines[0]) : 1;
          var b = im.lines ? Math.min(all.length, im.lines[1]) : Math.min(all.length, 60);
          var rows = "";
          for (var i = a; i <= b; i++) rows += "<tr><td class=ln>" + i + "</td><td class=lc>" + (all[i - 1] || " ") + "</td></tr>";
          box.innerHTML = '<div class="rp-codebar"><span>' + esc(im.file) +
            (im.symbol ? " &middot; " + esc(im.symbol) + "()" : "") + '</span>' +
            '<a href="' + esc(im.file) + '" target="_blank" rel="noopener">open whole file &rarr;</a></div>' +
            '<pre class="sx-code"><table><tbody>' + rows + "</tbody></table></pre>";
        }).catch(function (e) {
          box.innerHTML = '<div class="rp-coderr">Could not load ' + esc(im.file) + ": " + esc(e.message) +
            ". The validator source ships beside this report on the deploy; serve over http, not file://.</div>";
        });
      });
    }
    function paintRail() {
      var r = document.getElementById("rp-rail"); r.innerHTML = "";
      suiteList().forEach(function (s) {
        var offs = offenders(s), st = dotClass(s, offs);
        var b = el("button", s.id === sel ? "sel" : "");
        var ct = (st === "warn") ? "!" : (offs.length || "");
        b.innerHTML = '<span class="rp-dot ' + st + '"></span><span class="nm">' + esc(s.name) + '</span><span class="ct">' + ct + '</span>';
        b.onclick = function () { sel = s.id; filter = "all"; paint(); };
        r.appendChild(b);
      });
    }
    function paintMain() {
      var s = null; suiteList().forEach(function (x) { if (x.id === sel) s = x; });
      var offs = offenders(s), m = document.getElementById("rp-main");
      var cover = (s.scanned != null) ? ("examined " + s.scanned + " input" + (s.scanned === 1 ? "" : "s")) : "ran";
      var suiteTier = normalizedTier(s.tag), suiteStatus = normalizedSuiteStatus(s.status);
      var h = '<h2>' + esc(s.name) + '<span class="sev ' + sevc(suiteTier) + '">' + TIER[suiteTier].label + '</span>' +
        '<span class="rp-cover ' + suiteStatus + '">' + esc(cover) + '</span></h2>' +
        (s.why ? '<div class="rp-why">' + esc(s.why) + '</div>' : '') + implDisclosure(s);
      // A degraded / skipped check did NOT actually run: never let it read as a clean pass.
      if (s.status === "degraded" || s.status === "skipped") {
        var why = s.status === "skipped"
          ? "This check examined nothing, so a clean result proves nothing. Confirm there were inputs to check (pages, figures, materials) and that the suite is wired to find them."
          : "This check could not run, so it tells you nothing about what it covers. Do not read the absence of findings here as a pass.";
        m.innerHTML = h + '<div class="rp-degraded"><b>Did not run &mdash; not a clean result.</b> ' + esc(why) +
          (s.note ? '<div class="rp-degnote">' + esc(s.note) + '</div>' : '') + '</div>';
        wireImpl(m, s); return;
      }
      if (!offs.length) {
        m.innerHTML = h + '<div class="rp-clean">&#10003; Ran and found nothing to flag. The code above is what it looked for over the ' +
          esc(cover) + '. If you hit something this check should have caught, that gap is worth reporting.</div>';
        wireImpl(m, s); return;
      }
      h += '<div class="rp-fb"><button data-f="all" class="' + (filter === "all" ? "on" : "") + '">All (' + offs.length + ')</button>' +
        '<button data-f="unrev" class="' + (filter === "unrev" ? "on" : "") + '">Needs review</button>' +
        '<button data-f="agree" class="' + (filter === "agree" ? "on" : "") + '">Flagged real</button></div>';
      offs.forEach(function (o) {
        var k = fkey(s.id, o), c = normalizedCritique(CRIT[k]);
        if (filter === "unrev" && c.verdict) return; if (filter === "agree" && c.verdict !== "agree") return;
        var sv = normalizedTier(o.severity);
        h += '<div class="rp-off ' + c.verdict + '" data-k="' + esc(k) + '">' +
          '<div class="pg"><span class="sev ' + sevc(sv) + '">' + TIER[sv].label + '</span> ' + esc(o.page) + '</div>' +
          '<div class="dt">' + esc(o.detail) + '</div>' +
          (o.fix ? '<div class="fix"><b>fix</b>' + esc(o.fix) + '</div>' : "") +
          '<div class="acts">' + (isFilePage(o.page) ? '<button class="rp-srcbtn">show in source</button>' : '') +
          '<button data-v="agree" class="' + (c.verdict === "agree" ? "on-agree" : "") + '">Agree it\'s real</button>' +
          '<button data-v="dismiss" class="' + (c.verdict === "dismiss" ? "on-dismiss" : "") + '">Expected / dismiss</button></div>' +
          '<div class="rp-srcbox"></div>' +
          '<textarea placeholder="Why? (note for the agent)">' + esc(c.comment) + '</textarea></div>';
      });
      m.innerHTML = h;
      m.querySelectorAll(".rp-fb button").forEach(function (b) { b.onclick = function () { filter = b.dataset.f; paintMain(); }; });
      m.querySelectorAll(".rp-off").forEach(function (card) {
        var k = card.dataset.k;
        card.querySelectorAll(".acts button[data-v]").forEach(function (b) { b.onclick = function () { var cur = normalizedCritique(CRIT[k]); cur.verdict = cur.verdict === b.dataset.v ? "" : normalizedVerdict(b.dataset.v); CRIT[k] = cur; saveCrit(); paintMain(); }; });
        var ta = card.querySelector("textarea"); ta.oninput = function () { var cur = normalizedCritique(CRIT[k]); cur.comment = ta.value.slice(0, 12000); CRIT[k] = cur; saveCrit(); };
        var o = offs.filter(function (x) { return fkey(s.id, x) === k; })[0];
        var sb = card.querySelector(".rp-srcbtn"), sx = card.querySelector(".rp-srcbox");
        if (sb && o) sb.onclick = function () {
          var open = sx.classList.toggle("open"); sb.textContent = open ? "hide source" : "show in source";
          if (open) previewOffender(sx, o.page, s.id, o.detail);
        };
      });
      wireImpl(m, s);
    }
    function paintCounts() {
      var rev = 0, agr = 0, com = 0;
      Object.keys(CRIT).forEach(function (k) { var c = CRIT[k]; if (c && c.verdict) rev++; if (c && c.verdict === "agree") agr++; if (c && c.comment && c.comment.trim()) com++; });
      document.getElementById("rp-counts").textContent = rev + " reviewed · " + agr + " flagged real · " + com + " with notes";
    }
    function setVerdict() {
      var v = document.getElementById("rp-verdict");
      if (!GATE) { v.className = "rp-verdict fail"; v.textContent = "Could not load the gate. Serve over http (python3 -m http.server -d public), not file://."; return; }
      var g = GATE.gradient || {}, req = g.required || 0, rec = g.recommended || 0, con = g.consider || 0;
      var deg = (GATE.degraded || []).length;
      var degTxt = deg ? " " + deg + " check(s) did not run (amber); their clean-looking result is not trustworthy until they do." : "";
      if (GATE.ok === false) { v.className = "rp-verdict fail"; v.textContent = "FAIL. " + req + " critical issue(s) block the ship; start with the Required checks below." + degTxt; }
      else if (rec || con || deg) { v.className = "rp-verdict warn"; v.textContent = "No critical issues. " + rec + " recommended fix(es) and " + con + " non-critical improvement(s) to consider, each with the change to make." + degTxt; }
      else { v.className = "rp-verdict ok"; v.textContent = "Every check ran and found nothing outstanding at any tier. Open any check to see what it looked for."; }
    }
    function critiqueDoc() {
      var items = [];
      suiteList().forEach(function (s) { offenders(s).forEach(function (o) { var c = CRIT[fkey(s.id, o)]; if (c && (c.verdict || (c.comment || "").trim())) items.push({ suite: s.id, page: o.page, detail: o.detail, severity: o.severity || s.tag, fix: o.fix || "", verdict: c.verdict || null, note: (c.comment || "").trim() }); }); });
      return { generated: (GATE || {}).generated, git_sha: (GATE || {}).git_sha, reviewed_at: new Date().toISOString(), critiques: items };
    }
    function paint() { paintRail(); paintMain(); paintCounts(); }
    document.getElementById("rp-export").onclick = function () {
      var blob = new Blob([JSON.stringify(critiqueDoc(), null, 2)], { type: "application/json" });
      var a = el("a"); a.href = URL.createObjectURL(blob); a.download = "gate-critique.json"; document.body.appendChild(a); a.click(); a.remove();
      document.getElementById("rp-note").textContent = "downloaded gate-critique.json. Save it as docs/validation/critique.json for your agent.";
    };
    document.getElementById("rp-copy").onclick = function () {
      try { navigator.clipboard.writeText(JSON.stringify(critiqueDoc(), null, 2)); document.getElementById("rp-note").textContent = "copied. Paste it to your agent."; }
      catch (e) { document.getElementById("rp-note").textContent = "copy blocked; use Export instead"; }
    };
    document.getElementById("rp-clear").onclick = function () { if (window.confirm("Clear all your verdicts and notes?")) { CRIT = {}; saveCrit(); paint(); } };
    // pre-load a saved critique.json (an agent's prior verdicts) without overwriting local edits
    if (typeof fetch === "function") {
      fetch("critique.json").then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (j && Array.isArray(j.critiques)) { j.critiques.forEach(function (it) { var k = String(it.suite || "") + "::" + String(it.page || "") + "::" + String(it.detail || ""); if (!CRIT[k]) CRIT[k] = normalizedCritique({ verdict: it.verdict, comment: it.note }); }); saveCrit(); paint(); }
      }).catch(function () {});
    }
    if (GATE) { setVerdict(); paint(); }
    else if (typeof fetch === "function") {
      document.getElementById("rp-verdict").textContent = "loading gate.json...";
      fetch("gate.json").then(function (r) { return r.json(); }).then(function (j) { GATE = j; setVerdict(); paint(); }).catch(function () { setVerdict(); paint(); });
    } else { setVerdict(); paint(); }
  };

  // ── tests mode: the client-side runner (formerly tests.html), de-opaqued ─────
  App.prototype.mountTests = function () {
    var mount = this.mount;
    mount.innerHTML =
      '<div class="rp-head"><p><a href="index.html">&larr; back</a></p><h1>Test harness</h1>' +
      '<p class="rp-lead">Runs in your browser, no server. The engine smoke test runs live here; the full gate (links, layout, grounding, reachability) is computed by CI and surfaced below with its severity gradient.</p></div>' +
      '<div class="rp-main">' +
      '<h2>1 &middot; Engine smoke test <span id="ts-eng" class="ts-badge run">running</span></h2><pre id="ts-engout" class="ts-pre">checking engine.js exports...</pre>' +
      '<h2>2 &middot; CI gate <span id="ts-gate" class="ts-badge run">loading</span></h2><div id="ts-gateout"></div></div>';
    this.mountTopbar();
    // Layer 1: engine smoke. engine.js (UMD) attaches to the global; assert the surface
    // the viewer and CI both depend on is present and callable.
    var out = document.getElementById("ts-engout"), badge = document.getElementById("ts-eng");
    var E = (window.engine || window.LinkEngine) || (typeof globalThis !== "undefined" ? (globalThis.engine || globalThis.LinkEngine) : null);
    var checks = [], pass = 0;
    function ck(n, ok) { checks.push([n, !!ok]); if (ok) pass++; }
    if (!E) ck("engine module is exposed on the page", false);
    else { ck("engine module loaded", true); ["selfTest", "check", "pageAudit", "iterPages", "readForLinks"].forEach(function (fn) { ck("exports " + fn + "()", typeof E[fn] === "function"); }); }
    out.textContent = checks.map(function (c) { return (c[1] ? "✓" : "✗") + "  " + c[0]; }).join("\n") + "\n\nengine smoke: " + pass + "/" + checks.length + " pass";
    var ok = pass === checks.length && checks.length > 0;
    badge.textContent = ok ? (pass + "/" + checks.length + " pass") : (pass + "/" + checks.length + " FAIL");
    badge.className = "ts-badge " + (ok ? "ok" : "err");
    // Layer 2: the CI gate, surfaced with its full gradient (severity tiers), not just a few rows.
    var gb = document.getElementById("ts-gate"), go = document.getElementById("ts-gateout");
    function renderGate(d) {
      if (!d || d.note) { gb.textContent = "no report"; gb.className = "ts-badge"; go.innerHTML = "<p style='color:var(--tf)'>" + esc((d && d.note) || "No gate report yet; CI writes it.") + "</p>"; return; }
      var g = d.gradient || {}, rows = "";
      function row(k, v) { rows += '<div class="k">' + esc(k) + "</div><div>" + esc(v) + "</div>"; }
      row("verdict", d.ok === false ? "FAIL (ship-blocking)" : ((g.recommended || g.consider) ? "ships, not done" : "clean"));
      row("required", (g.required || 0)); row("recommended", (g.recommended || 0)); row("consider", (g.consider || 0));
      if (d.reachability) row("real strays", d.reachability.real_strays);
      if (d.git_sha) row("commit", d.git_sha);
      go.innerHTML = '<div class="ts-grid">' + rows + "</div><p><a href='validation.html'>open the full validation report &rarr;</a></p>";
      var bad = d.ok === false;
      gb.textContent = bad ? "FAIL" : "loaded"; gb.className = "ts-badge " + (bad ? "err" : "ok");
    }
    var gd = document.getElementById("gate-data");
    if (gd && gd.textContent.trim()) { try { renderGate(JSON.parse(gd.textContent)); } catch (e) { renderGate(null); } }
    else if (typeof fetch === "function") { fetch("gate.json").then(function (r) { return r.json(); }).then(renderGate).catch(function () { renderGate(null); }); }
    else { renderGate(null); }
  };

  function boot() {
    var cfgEl = document.getElementById("explorer-config");
    var metaEl = document.getElementById("skill-meta");
    if (!cfgEl && !metaEl) return;
    injectChrome(!!cfgEl);
    if (!cfgEl) {
      var meta = {};
      try { meta = JSON.parse(metaEl.textContent); } catch (e) {}
      new App({ title: meta.title || meta.course || meta.service || "Directory" }, document.body).mountTopbar();
      return;
    }
    var cfg;
    try { cfg = JSON.parse(cfgEl.textContent); } catch (e) {
      document.body.appendChild(el("pre", null, "explorer-config JSON did not parse: " + esc(e.message)));
      return;
    }
    var mount = document.getElementById("explorer") || document.body;
    new App(cfg, mount).mountUI();
  }

  // Expose the registry so the validator and course pages can latch the same keys.
  window.SKILL_SESSIONS = SESSIONS;

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
