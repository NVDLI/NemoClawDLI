#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bundle web/nemoclaw/*.html into iframe-ready single-file HTMLs.

The canonical web source is the source of truth. This script
transforms each source page so that it works as a *standalone* file: no
sibling pages, no repository-operated services, no
topbar, no journey map, no foot-nav. Light theme so it reads inside an edX
iframe.

Every transform happens here. The canonical source files stay untouched.

What gets transformed:

  1. Inline styles/_style.css (so the file is self-contained)
  2. Append styles/_lite_overlay.css (flips theme to light, hides nav chrome)
  3. Inline scripts/_shared.js, with the import line removed
  4. Strip the topbar element entirely (auto-mount code bails when missing)
  5. Strip the #journey-map and .foot-nav containers (no cross-page nav)
  6. Inject an inline <div id="key-panel"></div> just inside <main> + lite-
     mode JS that renders an inline NVIDIA API key form (no redirect)
  7. Substitute dark-theme colors inside <svg> bodies so diagrams remain
     legible on a light background

Usage:
  python3 scripts/build/bundle_standalone.py --src web/nemoclaw
  python3 scripts/build/bundle_standalone.py --src web/nemoclaw --out /tmp/nemoclaw_iframe --clean
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from html import escape
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

TASK1 = find_repo_root(Path(__file__).resolve())
add_script_paths(TASK1 / "scripts")
import artifact_link_audit

WEB_DIR = TASK1 / "web"
DEFAULT_OUT = TASK1 / "web_standalone"
# The released course is web/nemoclaw/.
# Pass --src web/nemoclaw to bundle it into --out web/nemoclaw_standalone (the auto-derive convention below).


# ────────────────────────────────────────────────────────────────────────────
# Regex catalogue. Tested against every page in web/.
# ────────────────────────────────────────────────────────────────────────────
CSS_LINK_RE = re.compile(
    r'<link\s+rel="stylesheet"\s+href="(?:styles/)?_style\.css"\s*/?>',
    re.IGNORECASE,
)
IMPORT_LINE_RE = re.compile(
    r'^\s*import\s+\{[^}]*\}\s+from\s+["\']\./(?:scripts/)?_shared\.js["\'];?\s*$',
    re.MULTILINE,
)
TOPBAR_RE = re.compile(
    # The topbar contains nested divs (.spacer). Anchor the match to
    # whatever follows the topbar, namely the opening of <main> on module
    # pages or a <main> on index/cert pages, so .*? consumes past the inner </div>.
    r'<div class="topbar">.*?</div>\s*(?=<main\b)',
    re.DOTALL,
)
JOURNEY_RE = re.compile(
    r'<div id="journey-map"></div>\s*',
)
FOOTNAV_RE = re.compile(
    r'<div class="foot-nav">.*?</div>\s*',
    re.DOTALL,
)
MAIN_OPEN_RE = re.compile(r'(<main[^>]*>)')
# Some pages call mountJourneyMap("#journey-map", ...) in their inline script.
# The function bails if the target is missing, but kill the call to avoid the
# pointless log noise in the console. Match permits one level of nested parens
# (the calls often pass document.getElementById("…") as an argument).
_NESTED_ARGS = r'(?:[^()]|\([^()]*\))*'
MOUNT_JM_RE = re.compile(rf'^\s*mountJourneyMap\({_NESTED_ARGS}\);\s*$', re.MULTILINE)
UPDATE_PILL_RE = re.compile(rf'^\s*updateKeyPill\({_NESTED_ARGS}\);\s*$', re.MULTILINE)
BUILD_NAV_RE = re.compile(
    rf'^\s*document\.getElementById\("nav"\)\.innerHTML\s*=\s*buildNav\({_NESTED_ARGS}\);\s*$',
    re.MULTILINE,
)
FIGURE_SOURCE_RE = re.compile(
    r'(?P<prefix>\bdata-svg-src\s*=\s*)(?P<quote>["\'])(?P<url>[^"\']+)(?P=quote)',
    re.IGNORECASE,
)


# ────────────────────────────────────────────────────────────────────────────
# SVG dark→light color substitution table. Applied only inside <svg>…</svg>.
# Keep the substitutions limited and conservative. A diagram should read as "dark
# figure on light card" rather than get wrecked by over-aggressive recolor.
# ────────────────────────────────────────────────────────────────────────────
SVG_SUBS = [
    # Canvas backgrounds (inline style on the <svg> itself)
    ("background:#0d0d0d",          "background:#f6f8fa"),
    ("background: #0d0d0d",         "background:#f6f8fa"),
    ("border:1px solid #2a2a2a",    "border:1px solid #d0d7de"),
    # Fills / strokes that show up across most diagrams
    ('fill="#0d0d0d"',              'fill="#f6f8fa"'),
    ('fill="#1e1e1e"',              'fill="#f6f8fa"'),
    ('fill="#161616"',              'fill="#eef1f4"'),
    ('fill="#262626"',              'fill="#e1e6eb"'),
    ('stroke="#2a2a2a"',            'stroke="#d0d7de"'),
    ('stroke="#3a3a3a"',            'stroke="#b0b8c0"'),
    # Light-on-dark text fills → dark-on-light
    ('fill="#f2f2f2"',              'fill="#1a1a1a"'),
    ('fill="#e8e8e8"',              'fill="#1a1a1a"'),
    ('fill="#b0b0b0"',              'fill="#3b3b3b"'),
    ('fill="#a5a5a5"',              'fill="#57606a"'),
    ('fill="#6a6a6a"',              'fill="#57606a"'),
    ('fill="#6f6f6f"',              'fill="#57606a"'),
    # Highlighted greens (used as fills for "selected" rows)
    ('fill="#0d2a0d"',              'fill="#e6f3d4"'),
    ('fill="#1a3a2a"',              'fill="#daeec1"'),
    ('fill="#1e3a1e"',              'fill="#daeec1"'),
    ('fill="#141f04"',              'fill="#e6f3d4"'),
    ('fill="#111a11"',              'fill="#e6f3d4"'),
    # Generic dark grays used as neutral box backdrops
    ('fill="#131313"',              'fill="#eef1f4"'),
    # Mid-tone supporting text colors that were authored for a dark backdrop
    # but become unreadable on a light one. The pattern is: take whatever
    # mid-saturation hue was used and substitute the darker mate.
    ('fill="#7a5020"',              'fill="#8b6914"'),    # mid amber → dark amber
    ('fill="#2a6090"',              'fill="#0969da"'),    # mid blue → dark blue
    ('fill="#3a5a30"',              'fill="#4a7a00"'),    # mid green → dark green
    ('fill="#2a5020"',              'fill="#4a7a00"'),    # mid green → dark green
    ('fill="#3a4a5a"',              'fill="#0969da"'),    # mid blue-gray → blue
    ('fill="#285070"',              'fill="#0969da"'),    # mid blue → dark blue
    ('fill="#6a40b0"',              'fill="#6f42c1"'),    # mid purple → purple
    ('fill="#4a4a6a"',              'fill="#57606a"'),    # mid blue-gray → neutral gray
    # Bright green text → darker green (more legible on light)
    ('fill="#aee23a"',              'fill="#4a7a00"'),
    ('fill="#76b900"',              'fill="#4a7a00"'),
    ('fill="#8ec444"',               'fill="#4a7a00"'),
    ('fill="#e0eec8"',              'fill="#3b6500"'),
    # Bright blue text → darker blue
    ('fill="#7eb6ff"',              'fill="#0969da"'),
    ('fill="#7eb8ff"',              'fill="#0969da"'),
    ('fill="#c8d8f0"',              'fill="#0969da"'),
    ('fill="#3b82f6"',              'fill="#0969da"'),
    # Amber / warning text
    ('fill="#e8c87a"',              'fill="#8b6914"'),
    ('fill="#f2cc60"',              'fill="#8b6914"'),
    # Red / shutdown
    ('fill="#ff9a9a"',              'fill="#d1242f"'),
    # Purple
    ('fill="#a78bfa"',              'fill="#6f42c1"'),
    ('fill="#d2b9ff"',              'fill="#6f42c1"'),
    # Dark-themed box fills used as backdrops for boxes/labels
    ('fill="#1e1e3a"',              'fill="#dfeaf5"'),
    ('fill="#1a1a2e"',              'fill="#eadfff"'),    # dark navy → light lavender
    ('fill="#3a2e1e"',              'fill="#f7e3c5"'),
    ('fill="#3a1e1e"',              'fill="#fadcdc"'),
    ('fill="#1f1a2e"',              'fill="#eadfff"'),
    ('fill="#0d1828"',              'fill="#dfeaf5"'),
    ('fill="#141f3a"',              'fill="#cad7e8"'),
    ('fill="#1a2850"',              'fill="#b5c6db"'),
    ('fill="#0d2b40"',              'fill="#dfeaf5"'),
    ('fill="#1a2820"',              'fill="#daeec1"'),
    ('fill="#211b12"',              'fill="#f7e3c5"'),
    ('fill="#0f1a22"',              'fill="#dfeaf5"'),
    ('fill="#0b1524"',              'fill="#dfeaf5"'),
    # Dark accent strokes → mid-tone
    ('stroke="#3a6080"',            'stroke="#0969da"'),
    ('stroke="#4a4a6a"',            'stroke="#57606a"'),
    ('stroke="#4a7a30"',            'stroke="#4a7a00"'),
    ('stroke="#cc7a00"',            'stroke="#8b6914"'),
    ('stroke="#8250df"',            'stroke="#6f42c1"'),
    ('stroke="#a78bfa"',            'stroke="#6f42c1"'),
    ('stroke="#58a6ff"',            'stroke="#0969da"'),
    ('stroke="#76b900"',            'stroke="#4a7a00"'),
    ('stroke="#aee23a"',            'stroke="#4a7a00"'),
    ('stroke="#3b82f6"',            'stroke="#0969da"'),
    ('stroke="#d74e4e"',            'stroke="#d1242f"'),
    ('stroke="#d49c2c"',            'stroke="#8b6914"'),
    # White-on-amber labels (lethal trifecta diamond etc.)
    ('fill="#fef9ee"',              'fill="#fff8e1"'),
    # Arrow heads (already-colored polygons)
    ('fill="#88aacc"',              'fill="#0969da"'),
    ('fill="#5a5a5a"',              'fill="#57606a"'),
]

# Inline script that runs in the bundled page, after _shared.js, to render
# the lite-mode key form into #key-panel. Hand-written; no template substitution.
LITE_KEY_PANEL_JS = r"""
// ── Lite-mode key panel (iframe export only) ─────────────────────────────
(function _liteKeyPanel() {
  // The exported HTML wraps content in <main>. We inject #key-panel just
  // inside it, before the first <h2>, so the form appears above the
  // first runnable cell.
  function _renderForm(panel, message) {
    panel.innerHTML =
      '<div class="key-form">' +
        '<label for="_lite_key_in">NVIDIA API key (nvapi-…)</label>' +
        '<input id="_lite_key_in" type="password" placeholder="nvapi-…" autocomplete="off"/>' +
        '<button id="_lite_key_btn">Save & verify</button>' +
        '<div class="key-hint">Free key at <a href="https://build.nvidia.com/?ncid=ref-dli-146986" target="_blank" rel="noopener">build.nvidia.com</a>. Stored in sessionStorage; cleared when this tab closes.</div>' +
        (message ? '<div class="key-err">' + message + '</div>' : '') +
      '</div>';
    var inp = panel.querySelector("#_lite_key_in");
    var btn = panel.querySelector("#_lite_key_btn");
    btn.addEventListener("click", async function() {
      var raw = (inp.value || "").trim();
      if (!raw.startsWith("nvapi-")) {
        _renderForm(panel, "Key must start with 'nvapi-'");
        return;
      }
      sessionStorage.setItem("nvapi", raw);
      _renderOk(panel);
    });
    inp.addEventListener("keydown", function(e) { if (e.key === "Enter") btn.click(); });
  }
  function _renderOk(panel) {
    panel.innerHTML =
      '<div class="key-form">' +
        '<div class="key-ok">✓ Key saved for this tab. Run any cell to call the model.</div>' +
        '<div class="key-note">Wrong key? <a href="#" id="_lite_key_reset">Clear and re-enter</a></div>' +
      '</div>';
    var a = panel.querySelector("#_lite_key_reset");
    a.addEventListener("click", function(e) {
      e.preventDefault();
      sessionStorage.removeItem("nvapi");
      _renderForm(panel, "");
    });
  }
  function _mount() {
    var main = document.querySelector("main");
    if (!main) return;
    // Already mounted? skip.
    if (main.querySelector("#key-panel")) {
      // still wire up its initial state
    } else {
      var panel = document.createElement("div");
      panel.id = "key-panel";
      // Insert before the first <h2> if it is a direct child of <main>; else
      // before the first direct-child ancestor of that h2; else at the top.
      // `insertBefore(node, ref)` requires `ref` to be a direct child of
      // `node`, which the original `main.querySelector("h2")` did not
      // guarantee, because the h2 may be nested inside a wrapper div.
      var ref = null;
      var h2 = main.querySelector("h2");
      if (h2) {
        ref = h2;
        while (ref && ref.parentNode !== main) ref = ref.parentNode;
      }
      if (!ref) ref = main.firstChild;
      if (ref) main.insertBefore(panel, ref);
      else     main.appendChild(panel);
    }
    var panel = main.querySelector("#key-panel");
    if (sessionStorage.getItem("nvapi")) _renderOk(panel);
    else _renderForm(panel, "");
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _mount);
  } else {
    _mount();
  }
})();
"""


def _strip_dead_chrome(html: str) -> str:
    """Remove topbar, journey-map, foot-nav and any leftover script calls
    that referenced them. The auto-mount logic in _shared.js bails out
    when its target elements aren't found, so stripping is enough."""
    html = TOPBAR_RE.sub("", html, count=1)
    html = JOURNEY_RE.sub("", html)
    # foot-nav (prev/next at the bottom of each module page) is intentionally
    # kept: the lite link-bridge in LITE_AUTOSIZE_JS catches clicks and
    # routes them through the edX navigator's setActive(). The lab view
    # uses its own journey map; the bundled view leans on foot-nav as
    # the natural "continue to next module" surface.
    html = MOUNT_JM_RE.sub("", html)
    html = UPDATE_PILL_RE.sub("", html)
    html = BUILD_NAV_RE.sub("", html)
    return html


# When the bundle is iframed inside the edX navigator, we don't want the
# inner page to grow its own scrollbar (the dreaded "window-in-window"
# look). Each bundled HTML posts its full scrollHeight to its parent via
# postMessage; the navigator listens and grows the iframe to fit. Safe
# no-op when the page isn't iframed (window.parent === window) or when
# nobody is listening.
LITE_AUTOSIZE_JS = r"""
// ── Lite-mode bridge (iframe export only) ───────────────────────────────
// When iframed, the parent (edX navigator) listens for two message types:
//
//   { type: "fx43-iframe-size",  height: <px> }     ← from autosize loop
//   { type: "fx43-navigate",     file: "<x>.html" } ← from link interceptor
//
// The autosize keeps iframe.height == content height (no scrollbar). The
// link interceptor catches clicks on sibling .html anchors (foot-nav
// prev/next, in-prose cross-references, etc.) so the navigator routes
// them through its own setActive() and the journey bar stays in sync.
// Both IIFEs no-op when the page is loaded standalone (window.parent
// === window).
(function _liteAutosize() {
  if (window.parent === window) return;            // standalone tab, no parent

  // BREAK THE FEEDBACK LOOP: the lab CSS sets `body { min-height: 100vh }`.
  // Inside an iframe, 100vh == the iframe's own viewport. When the parent
  // grows the iframe (even by 1px), the body's min-height grows with it,
  // body.scrollHeight reports the new larger value, parent grows again …
  // we'd loop forever. Pin html/body to natural height inside the iframe.
  function pinSize() {
    if (document.documentElement) {
      document.documentElement.style.setProperty("min-height", "0", "important");
      document.documentElement.style.setProperty("height", "auto", "important");
    }
    if (document.body) {
      document.body.style.setProperty("min-height", "0", "important");
      document.body.style.setProperty("height", "auto", "important");
    }
  }
  pinSize();

  // Track only INCREASES that come from genuine content additions (a
  // CodeMirror mount, a helpers row open, a late image load). We never
  // shrink. Once we've reported a height, the parent owns it; subsequent
  // smaller measurements are ignored, which keeps us out of the loop
  // even if pinSize() races with a stylesheet that resets min-height.
  var reported = 0;
  function measureContent() {
    // Use the rendered content's bottom edge, not body.scrollHeight (which
    // is biased by min-height). We probe the actual children of <main> /
    // <body> and take the maximum bottom-y.
    var body = document.body;
    if (!body) return 0;
    var max = 0;
    var nodes = body.children;
    for (var i = 0; i < nodes.length; i++) {
      var r = nodes[i].getBoundingClientRect();
      var bottom = r.bottom + window.scrollY;
      if (bottom > max) max = bottom;
    }
    return Math.ceil(max);
  }
  function emit() {
    pinSize();                        // re-apply, defensive
    var h = measureContent();
    if (h > reported + 4) {           // grow-only, ignore tiny jitter
      reported = h;
      try {
        window.parent.postMessage({ type: "fx43-iframe-size", height: h, url: location.href }, "*");
      } catch (_) {}
    }
  }

  function start() {
    emit();
    window.addEventListener("load", emit);
    // ResizeObserver / MutationObserver catch real layout additions such as
    // CodeMirror mounts, <details> open, and helpers source-row reveal.
    // Throttled via requestAnimationFrame to coalesce bursts.
    var rafScheduled = false;
    function schedule() {
      if (rafScheduled) return;
      rafScheduled = true;
      requestAnimationFrame(function () { rafScheduled = false; emit(); });
    }
    try { new ResizeObserver(schedule).observe(document.body); } catch (_) {}
    try {
      new MutationObserver(schedule).observe(document.body, {
        childList: true, subtree: true, attributes: true,
        attributeFilter: ["open", "hidden", "class"]
      });
    } catch (_) {}
    // A short post-load burst for content that lands a beat after load
    // (highlight.js, CodeMirror, viz drawing). After that, observers
    // carry the rest. A long-running interval is avoided, since that is what
    // caused the indefinite-growth perception.
    var burst = 0;
    var bid = setInterval(function () {
      emit();
      if (++burst >= 15) clearInterval(bid);    // ~2.2s of 150ms ticks
    }, 150);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();

// ── Lite-mode link interceptor (iframe export only) ─────────────────────
// Catch clicks on sibling .html anchors and hand them up to the parent
// navigator. Source of truth for the link target is the actual <a href>
// in the page, so no separate map needs to be maintained. Capture-phase
// listener so we beat any page-level click handlers.
(function _liteLinkBridge() {
  if (window.parent === window) return;

  function fileFromHref(a) {
    if (!a || !a.href || a.target === "_blank") return null;
    var url;
    try { url = new URL(a.href, location.href); } catch (_) { return null; }
    if (url.origin !== location.origin) return null;     // external
    var dir = location.pathname.replace(/[^/]*$/, "");
    if (!url.pathname.startsWith(dir)) return null;      // out of bundle dir
    var rest = url.pathname.slice(dir.length);
    if (!rest || rest.indexOf("/") >= 0) return null;    // subdir, not a sibling
    if (!/\.html(\?.*)?$/i.test(rest)) return null;
    return { file: rest.replace(/\?.*$/, ""), hash: url.hash || "" };
  }

  document.addEventListener("click", function (ev) {
    if (ev.defaultPrevented) return;
    if (ev.button !== 0) return;                 // only left-click
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    var a = ev.target;
    while (a && a !== document.body && a.tagName !== "A") a = a.parentElement;
    if (!a || a.tagName !== "A") return;
    var t = fileFromHref(a);
    if (!t) return;
    // Self-link? Let it fall through to natural anchor scroll.
    if (t.file === location.pathname.split("/").pop()) return;
    ev.preventDefault();
    try {
      window.parent.postMessage({
        type: "fx43-navigate",
        file: t.file,
        hash: t.hash,
      }, "*");
    } catch (_) {}
  }, true);
})();
"""

# The code/helpers panels are <details> elements built by _shared.js at
# runtime, so a static regex over the HTML doesn't catch them. Instead the
# lite bootstrap below watches the DOM for new panels and adds the `open`
# attribute. The lab view stays collapsed-by-default; only the export opens.
LITE_OPEN_PANELS_JS = r"""
// ── Lite-mode: open code/helpers panels by default ───────────────────────
// In the iframe export there is no obvious affordance for the disclosure
// triangle, and the whole point of the export is *reading the code*. So we
// auto-open .cf-panel-code-det as panels get mounted. Helpers stay closed
// by default (students open them on demand) and results panels stay
// collapsed (they're empty until a run).
(function _liteOpenPanels() {
  const SEL = ".cf-panel-code-det";
  function openAll(root) {
    (root || document).querySelectorAll(SEL).forEach(el => {
      if (!el.hasAttribute("open")) el.setAttribute("open", "");
    });
  }
  function start() {
    openAll(document);
    new MutationObserver(muts => {
      for (const m of muts) for (const n of m.addedNodes) {
        if (n.nodeType === 1) {
          if (n.matches && n.matches(SEL)) {
            if (!n.hasAttribute("open")) n.setAttribute("open", "");
          }
          if (n.querySelectorAll) openAll(n);
        }
      }
    }).observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
"""


# Legacy /lab/lab/... and /lab/static/... authoring URLs do not resolve in an external iframe.
# Convert any anchor with such an href into plain text so the prose still reads.
LAB_ANCHOR_RE = re.compile(
    r'<a([^>]*?)href="/lab/(?:lab|static)/[^"]*"([^>]*)>(.*?)</a>',
    re.DOTALL,
)


def _strip_lab_anchors(html: str) -> str:
    """Demote dead /lab/* anchor tags to plain text (keeps inner content)."""
    return LAB_ANCHOR_RE.sub(lambda m: m.group(3), html)


def _version_figure_sources(html: str, page_dir: Path) -> str:
    """Give local SVG figure requests a deterministic content cache key.

    CloudFront can retain an older object at an unchanged asset URL even after
    the referring HTML has refreshed. Because mountFigures fetches these SVGs
    and injects their markup into the page, stale SVG styles can affect the
    whole course. A content-derived query makes every changed figure a new
    request while preserving relative URLs and external references.
    """
    root = page_dir.resolve()

    def replace(match: re.Match[str]) -> str:
        raw_url = match.group("url")
        parsed = urlsplit(raw_url)
        if parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
            return match.group(0)
        if not parsed.path.lower().endswith(".svg"):
            return match.group(0)

        asset = (page_dir / parsed.path).resolve()
        try:
            asset.relative_to(root)
        except ValueError:
            return match.group(0)
        if not asset.is_file():
            return match.group(0)

        digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                 if key != "v"]
        query.append(("v", digest))
        versioned = urlunsplit(("", "", parsed.path, urlencode(query), parsed.fragment))
        return f'{match.group("prefix")}{match.group("quote")}{versioned}{match.group("quote")}'

    return FIGURE_SOURCE_RE.sub(replace, html)


SKILL_EXPLORER_REF_RE = re.compile(
    r'(?P<quote>["\'])(?:\.\.?/)+(?:web/)?_skill_explorer\.js(?P=quote)'
)
SKILL_HEADER_RE = re.compile(
    r'(?P<open><header\b[^>]*\bdata-skill-header=["\']1["\'][^>]*>).*?</header>',
    re.IGNORECASE | re.DOTALL,
)
STATIC_TOPBAR_RE = re.compile(
    r'<div\b[^>]*\bclass=["\'][^"\']*\bsx-topbar\b[^"\']*["\'][^>]*>.*?</div>',
    re.IGNORECASE | re.DOTALL,
)
def _rewrite_skill_explorer_paths(out: Path) -> int:
    """Keep every copied nested SKILL renderer inside the standalone bundle.

    Generated directory contracts carry paths relative to the source repository's
    ``web/`` root. A standalone course has a different root, so copied assets,
    materials, and vendor contracts must point to the explorer shipped at ``out``.
    """
    explorer = out / "_skill_explorer.js"
    if not explorer.is_file():
        return 0
    changed = 0
    for skill in out.rglob("SKILL.html"):
        relative = Path(os.path.relpath(explorer, skill.parent)).as_posix()
        source = skill.read_text(encoding="utf-8")
        updated = SKILL_EXPLORER_REF_RE.sub(
            lambda match: f'{match.group("quote")}{relative}{match.group("quote")}', source
        )
        if updated != source:
            skill.write_text(updated, encoding="utf-8")
            changed += 1
    return changed


def _json_script(source: str, element_id: str, update) -> str:
    pattern = re.compile(
        rf'(?P<open><script\b(?=[^>]*\bid=["\']{re.escape(element_id)}["\'])[^>]*>)'
        r'(?P<body>.*?)(?P<close></script>)',
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(source)
    if not match:
        return source
    try:
        value = json.loads(match.group("body"))
    except json.JSONDecodeError:
        return source
    updated = update(value)
    body = json.dumps(updated, indent=2, ensure_ascii=False)
    return source[:match.start()] + match.group("open") + "\n" + body + "\n" + match.group("close") + source[match.end():]


def _relative_url(target: Path, page: Path) -> str:
    return Path(os.path.relpath(target, page.parent)).as_posix()


def _local_target(out: Path, page: Path, raw: str) -> Path | None:
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return None
    if not parsed.path or parsed.path.startswith("/"):
        return page if not parsed.path else None
    target = (page.parent / parsed.path).resolve()
    try:
        target.relative_to(out.resolve())
    except ValueError:
        return None
    if target.is_dir():
        target = target / "index.html"
    return target


def _project_skill_config(config: dict, out: Path, skill: Path) -> dict:
    root_index = out / "index.html"
    root_skill = out / "SKILL.html"
    nav: dict[str, object] = {
        "home": _relative_url(root_index, skill),
        "map": {"label": "Course map", "href": _relative_url(root_skill, skill)},
    }
    if skill != root_skill:
        parent = skill.parent.parent
        while parent == out or out in parent.parents:
            candidate = parent / "SKILL.html"
            if candidate.is_file():
                label = "Course map" if candidate == root_skill else candidate.parent.name
                nav["up"] = {"label": label, "href": _relative_url(candidate, skill)}
                break
            if parent == out:
                break
            parent = parent.parent
    config["nav"] = nav

    def usable(item: dict) -> bool:
        raw = item.get("href") or item.get("path")
        if not isinstance(raw, str):
            return True
        parsed = urlsplit(raw)
        if parsed.scheme or parsed.netloc:
            return True
        target = _local_target(out, skill, raw)
        return bool(target and target.is_file())

    if isinstance(config.get("files"), list):
        config["files"] = [item for item in config["files"] if not isinstance(item, dict) or usable(item)]
    if isinstance(config.get("related"), list):
        config["related"] = [item for item in config["related"] if not isinstance(item, dict) or usable(item)]
    if isinstance(config.get("links"), list):
        for group in config["links"]:
            if isinstance(group, dict) and isinstance(group.get("items"), list):
                group["items"] = [item for item in group["items"] if not isinstance(item, dict) or usable(item)]
    return config


def _project_static_topbar(source: str, out: Path, page: Path) -> str:
    home = _relative_url(out / "index.html", page)
    up = _relative_url(out / "SKILL.html", page)

    def replace(block: re.Match[str]) -> str:
        value = block.group(0)
        for class_name, href in (("sx-logo", home), ("sx-up", up)):
            pattern = re.compile(
                rf'(?P<prefix><a\b(?=[^>]*\bclass=["\'][^"\']*\b{class_name}\b[^"\']*["\'])'
                r'[^>]*\bhref=)(?P<quote>["\'])[^"\']*(?P=quote)',
                re.IGNORECASE,
            )
            value = pattern.sub(
                lambda match: match.group("prefix") + match.group("quote") + escape(href, quote=True) + match.group("quote"),
                value,
                count=1,
            )
        return value

    return STATIC_TOPBAR_RE.sub(replace, source, count=1)


def project_artifact_navigation(out: Path) -> int:
    """Make every generated explorer/navigation surface truthful for this artifact root."""
    changed = 0
    root_skill = out / "SKILL.html"
    for skill in sorted(out.rglob("*.html")):
        source = skill.read_text(encoding="utf-8")
        if 'id="explorer-config"' not in source and "data-skill-header" not in source and "sx-topbar" not in source:
            continue
        updated = _json_script(
            source,
            "explorer-config",
            lambda config, current=skill: _project_skill_config(config, out, current),
        )
        links = [
            ("home", "Home", _relative_url(out / "index.html", skill)),
        ]
        if skill != root_skill:
            parent = skill.parent.parent
            while parent == out or out in parent.parents:
                candidate = parent / "SKILL.html"
                if candidate.is_file():
                    links.append(("up", "Up", _relative_url(candidate, skill)))
                    break
                if parent == out:
                    break
                parent = parent.parent
        links.append(("map", "Course map", _relative_url(root_skill, skill)))
        nav = " <span aria-hidden=\"true\">·</span> ".join(
            f'<a data-skill-nav="{kind}" href="{escape(href, quote=True)}">{label}</a>'
            for kind, label, href in links
        )
        header = f'<header data-skill-header="1"><nav class="skill-nav" aria-label="Skill navigation">{nav}</nav></header>'
        if SKILL_HEADER_RE.search(updated):
            updated = SKILL_HEADER_RE.sub(header, updated, count=1)
        elif STATIC_TOPBAR_RE.search(updated):
            updated = _project_static_topbar(updated, out, skill)
        else:
            updated = re.sub(r"<body([^>]*)>", rf"<body\1>\n{header}", updated, count=1, flags=re.IGNORECASE)
        if updated != source:
            skill.write_text(updated, encoding="utf-8")
            changed += 1
    for skill in sorted(out.rglob("SKILL.html")):
        index = skill.parent / "index.html"
        if index.exists():
            continue
        shutil.copy2(skill, index)
        changed += 1
    return changed


def _copy_compliance_review(out: Path) -> None:
    """Project the repository's evidence-backed license view into the course artifact."""
    destination = out / "compliance"
    shutil.copytree(TASK1 / "scripts" / "compliance", destination, dirs_exist_ok=True)
    shutil.copy2(TASK1 / "THIRD_PARTY_LICENSES.md", destination / "THIRD_PARTY_LICENSES.md")
    page = destination / "SKILL.html"
    source = page.read_text(encoding="utf-8")

    def configure(value: dict) -> dict:
        value["vendor_manifest"] = "../vendor/browser-dependencies.json"
        value["inventory"] = "THIRD_PARTY_LICENSES.md"
        return value

    page.write_text(_json_script(source, "third-party-export-config", configure), encoding="utf-8")

    evidence_path = destination / "docs" / "sbom_evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    repository = "https://github.com/NVDLI/NemoClawDLI/blob/main/"
    for record in evidence.get("records", []):
        if record.get("id") == "browser-runtime" and record.get("sbom"):
            record["sbom"]["href"] = "../../vendor/browser-sbom.cdx.json"
        for link in record.get("evidence_links", []):
            raw = link.get("href", "")
            if raw.endswith("THIRD_PARTY_LICENSES.md"):
                link["href"] = "../THIRD_PARTY_LICENSES.md"
            elif raw.startswith("../"):
                link["href"] = repository + raw.split("../../../", 1)[-1]
        for subject in record.get("subjects", []):
            raw = subject.get("declaration_href", "")
            if raw.startswith("../"):
                subject["declaration_href"] = repository + raw.split("../../../", 1)[-1]
    evidence_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    root_skill = out / "SKILL.html"
    root_source = root_skill.read_text(encoding="utf-8")

    def add_entry(config: dict) -> dict:
        groups = config.setdefault("links", [])
        group = next((item for item in groups if item.get("title") == "Tools"), None)
        if group is None:
            group = {"title": "Tools", "items": []}
            groups.append(group)
        items = group.setdefault("items", [])
        required = (
            {
                "label": "License and distribution review",
                "href": "compliance/SKILL.html",
                "desc": "Evidence-backed software, source, license, and distribution inventory.",
            },
            {
                "label": "Pyodide candidate review",
                "href": "pyodide/SKILL.html",
                "desc": "Runnable repository demonstration plus the exact candidate component and license boundary.",
            },
        )
        for entry in required:
            if not any(item.get("href") == entry["href"] for item in items):
                items.append(entry)
        return config

    root_source = _json_script(root_source, "explorer-config", add_entry)
    for required_href in ("compliance/SKILL.html", "pyodide/SKILL.html"):
        if required_href not in root_source:
            raise RuntimeError(f"failed to project {required_href} into the course map")
    root_skill.write_text(root_source, encoding="utf-8")


def _copy_pyodide_review(out: Path) -> None:
    """Ship the complete declared Pyodide review surface and keep its local assets in-bounds."""
    destination = out / "pyodide"
    shutil.copytree(TASK1 / "scripts" / "pyodide", destination, dirs_exist_ok=True)
    shared_destination = destination / "shared"
    shared_destination.mkdir(parents=True, exist_ok=True)
    for name in ("runtime-workbench.css", "runtime-workbench.js"):
        shutil.copy2(TASK1 / "web" / "shared" / name, shared_destination / name)
    page = destination / "SKILL.html"
    source = page.read_text(encoding="utf-8")
    source = source.replace("../../web/nemoclaw/", "../")
    source = source.replace("../../web/shared/", "./shared/")
    page.write_text(source, encoding="utf-8")


def _project_current_artifact_alias(out: Path) -> None:
    """Keep the source tree's standalone route truthful without nesting an older build."""
    destination = out / "standalone"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "SKILL.html").write_text(
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="refresh" content="0;url=../SKILL.html">'
        '<title>Current standalone artifact</title></head><body><p>'
        '<a href="../SKILL.html">Open the current standalone artifact map</a>'
        '</p></body></html>\n',
        encoding="utf-8",
    )


def _self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        asset = root / "assets" / "figure.svg"
        asset.parent.mkdir(parents=True)
        asset.write_text("<svg>first</svg>", encoding="utf-8")
        first_digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
        source = (
            '<div data-svg-src="assets/figure.svg"></div>'
            '<div data-svg-src="assets/figure.svg?mode=full#detail"></div>'
            '<div data-svg-src="https://example.com/figure.svg"></div>'
            '<div data-svg-src="assets/missing.svg"></div>'
        )
        first = _version_figure_sources(source, root)
        assert f'assets/figure.svg?v={first_digest}' in first
        assert f'assets/figure.svg?mode=full&amp;' not in first
        assert f'assets/figure.svg?mode=full&v={first_digest}#detail' in first
        assert 'https://example.com/figure.svg' in first
        assert 'assets/missing.svg' in first
        assert _version_figure_sources(source, root) == first

        asset.write_text("<svg>second</svg>", encoding="utf-8")
        second_digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
        second = _version_figure_sources(source, root)
        assert second_digest != first_digest
        assert f'assets/figure.svg?v={second_digest}' in second
        assert first_digest not in second

        bundle = root / "public" / "nemoclaw"
        nested = bundle / "assets" / "figures" / "SKILL.html"
        nested.parent.mkdir(parents=True)
        (bundle / "_skill_explorer.js").write_text("fixture", encoding="utf-8")
        nested.write_text(
            '<script type="application/json" id="skill-meta">'
            '{"explorer":"../../../_skill_explorer.js"}</script>'
            '<script src="../../../_skill_explorer.js"></script>',
            encoding="utf-8",
        )
        assert _rewrite_skill_explorer_paths(bundle) == 1
        rewritten = nested.read_text(encoding="utf-8")
        assert rewritten.count('"../../_skill_explorer.js"') == 2

        (bundle / "index.html").write_text('<a href="SKILL.html">map</a>', encoding="utf-8")
        (bundle / "SKILL.html").write_text(
            '<body><header data-skill-header="1"><nav><a href="../SKILL.html">bad</a></nav></header>'
            '<script type="application/json" id="explorer-config">'
            '{"title":"fixture","nav":{"home":"../index.html"},"files":[]}'
            '</script></body>',
            encoding="utf-8",
        )
        child = bundle / "docs" / "SKILL.html"
        child.parent.mkdir()
        child.write_text(
            '<script type="application/json" id="explorer-config">'
            '{"title":"docs","files":[]}</script>', encoding="utf-8",
        )
        project_artifact_navigation(bundle)
        assert '"label": "Course map"' in child.read_text(encoding="utf-8")
        assert bundle.name not in child.read_text(encoding="utf-8")
        assert not artifact_link_audit.audit(bundle)
        broken = (bundle / "SKILL.html").read_text(encoding="utf-8").replace('href="index.html"', 'href="../index.html"', 1)
        (bundle / "SKILL.html").write_text(broken, encoding="utf-8")
        assert any("escapes the deployment root" in str(item) for item in artifact_link_audit.audit(bundle))

        source_course = root / "source-course"
        linked_out = root / "linked-out"
        source_course.mkdir(); linked_out.mkdir()
        (source_course / "SKILL.html").write_text(
            '<a href="interface-inventory.json">inventory</a>'
            '<a href="learning-profile.json">profile</a>'
            '<a href="../outside.json">outside</a>',
            encoding="utf-8",
        )
        (source_course / "interface-inventory.json").write_text('{"schema":"fixture"}\n', encoding="utf-8")
        (source_course / "learning-profile.json").write_text('{"schema":"fixture-profile"}\n', encoding="utf-8")
        (root / "outside.json").write_text("not copied\n", encoding="utf-8")
        assert _copy_linked_course_files(source_course, linked_out) == [
            "interface-inventory.json",
            "learning-profile.json",
        ]
        assert (linked_out / "interface-inventory.json").is_file()
        assert (linked_out / "learning-profile.json").is_file()
        assert not (linked_out / "outside.json").exists()
    print("bundle_standalone self-test: PASS")
    return 0


def _copy_linked_course_files(source: Path, destination: Path) -> list[str]:
    """Ship relative files linked by the course root SKILL without a filename allowlist."""
    skill = source / "SKILL.html"
    if not skill.is_file():
        return []
    copied: list[str] = []
    refs = re.findall(r'\b(?:href|src)=["\']([^"\']+)["\']', skill.read_text(encoding="utf-8"), re.I)
    for ref in refs:
        parsed = urlsplit(ref)
        relative = Path(parsed.path)
        if parsed.scheme or parsed.netloc or not parsed.path or relative.is_absolute() or ".." in relative.parts:
            continue
        candidate = source / relative
        target = destination / relative
        if candidate.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)
            copied.append(relative.as_posix())
    return sorted(copied)


def _apply_svg_subs(html: str) -> str:
    """Replace dark-theme inline colors inside SVG element bodies. The match
    is scoped to real SVG element spans so prose, code, and inline color
    references outside diagrams are untouched.

    The opening-tag character class is `[^<>]` (not the looser `[^>]`) so
    the regex cannot start at a literal `<svg>` inside a CSS comment or
    code-string context. A real SVG opening tag never contains an unescaped
    `<` in its attributes; the broken `[^>]` form would happily consume
    across `</style>` and onward, accidentally rewriting unrelated CSS
    (notably `background: #0d0d0d` inside a CodeMirror theme block).

    The opening tag must also carry a `viewBox` attribute. Every real figure
    this course emits (mountDiagram output, the inline file-trees, log.draw
    frames) declares one; a bare `<svg>` token sitting in prose or a CSS
    comment does not. Without this guard such a token matches as an empty
    opening tag and `.*?</svg>` swallows everything up to the next real
    closing tag, dragging the head `<style>` (and its CodeMirror dark theme)
    into the recolor pass and flipping the code background to light."""
    out = []
    cursor = 0
    for m in re.finditer(r'<svg\b[^<>]*\bviewBox[^<>]*>.*?</svg>', html, re.DOTALL | re.IGNORECASE):
        out.append(html[cursor:m.start()])
        svg = m.group(0)
        for old, new in SVG_SUBS:
            svg = svg.replace(old, new)
        svg = svg.replace(' class="gfx-dark"', "")  # GFX graphics use light defaults in the light standalone
        out.append(svg)
        cursor = m.end()
    out.append(html[cursor:])
    return "".join(out)


# Injected into <head>. The favicon ships under assets/ (relative, both builds). The theme init
# runs before first paint in the full build: it sets data-theme on <html> from a saved choice or
# the OS preference, so the page opens in the right palette with no flash. _style.css carries the
# matching :root[data-theme="light"] palette; the toggle button is mounted by _shared.js.
FAVICON_LINK = '<link rel="icon" type="image/x-icon" href="./assets/favicon.ico"/>'
THEME_INIT_JS = (
    '<script>(function(){try{var t=localStorage.getItem("theme")'
    '||(matchMedia("(prefers-color-scheme: light)").matches?"light":"dark");'
    'document.documentElement.setAttribute("data-theme",t);}catch(e){}})();</script>'
)


def _first_file(*paths: Path) -> Path:
    for path in paths:
        if path.is_file():
            return path
    names = ", ".join(str(p) for p in paths)
    raise FileNotFoundError(names)


def bundle_one(html_path: Path, css_text: str, lite_css: str, shared_js: str,
               full: bool = False) -> str:
    """Bundle one page into a self-contained file.

    The default (lite) build is the light, chrome-free iframe export for the edX navigator.
    With full=True it is the dark, fully navigable standalone for a self-hosted Pages site:
    the same content the lab serves, made self-contained, with the off-lab key panel added.
    """
    html = html_path.read_text(encoding="utf-8")

    # 0) Version local fetched SVGs by content. This applies to full and lite
    #    exports and to every locale assembled through the same bundler.
    html = _version_figure_sources(html, html_path.parent)

    # 0b) A generated SKILL hub loads ../_skill_explorer.js (the renderer lives one dir up so it serves
    #    every surface). The bundle is flat, so point it at the sibling copy shipped alongside the pages.
    html = html.replace('src="../_skill_explorer.js"', 'src="_skill_explorer.js"')

    # 1) Inline styles/_style.css. The lite export appends styles/_lite_overlay.css to flip the page to a
    #    light background and hide the nav chrome; the full build keeps the lab's dark theme,
    #    so it inlines styles/_style.css on its own.
    if full:
        style_block = "<style>\n" + css_text + "\n</style>"
    else:
        style_block = (
            "<style>\n" + css_text + "\n\n/* ── lite overlay ── */\n" + lite_css + "\n</style>"
        )
    new_html, n_css = CSS_LINK_RE.subn(style_block, html, count=1)
    if n_css == 0:
        # Page has no <link rel="stylesheet" href="styles/_style.css"/> (e.g. courses.html).
        # Insert the style block right before </head>.
        new_html = html.replace("</head>", style_block + "\n</head>", 1)

    # 1b) Favicon on every bundled page. In the full build also inject the pre-paint theme init so
    #     the page opens in the saved/OS palette without a flash; the lite iframe export stays baked.
    head_inject = FAVICON_LINK + ("\n" + THEME_INIT_JS if full else "")
    new_html = new_html.replace("</head>", head_inject + "\n</head>", 1)

    # 2) The lite export strips the lab-only chrome (topbar / journey map / the JS that mounts
    #    them) because the edX navigator supplies its own; the full build keeps the chrome so
    #    the course navigates itself. Both demote dead /lab/* anchors, which never resolve
    #    off-lab.
    if not full:
        new_html = _strip_dead_chrome(new_html)
    new_html = _strip_lab_anchors(new_html)

    # 3) Keep the `import {...} from "./scripts/_shared.js"` line and ship scripts/_shared.js as a real file
    #    alongside the pages (copied in main). The imports then resolve, and ES module caching
    #    loads the module once even across multiple module blocks, exactly as the lab serves
    #    it, so each page stays small. The lite export injects its own sessionStorage key form
    #    and auto-opens the code panels for reading. The full build injects NOTHING here: each
    #    page already has a native key panel (mountKeyPanel on module pages, the static form on
    #    the landing) that works off-lab and is styled by _style.css, so injecting the lite form
    #    would only collide with it on #key-panel and render unstyled.
    if not full:
        new_html, n_js = IMPORT_LINE_RE.subn(
            lambda m: m.group(0) + "\n" + LITE_KEY_PANEL_JS + LITE_OPEN_PANELS_JS,
            new_html,
            count=1,
        )
    # Pages without _shared.js (e.g. courses.html) get no key panel either.

    # 4) The lite export re-themes the SVG figures to read on a light background; the full
    #    build keeps them dark, their .gfx-dark class resolving against the dark palette in
    #    _style.css, so it skips the recolor.
    if not full:
        new_html = _apply_svg_subs(new_html)

    # 5) The lite export posts its height to the edX navigator and bridges sibling-page clicks
    #    back through it. The full build navigates with ordinary relative anchors, so it skips
    #    the autosize beacon, whose link bridge would otherwise swallow that navigation.
    if not full:
        autosize_tag = f"<script>{LITE_AUTOSIZE_JS}</script>\n</body>"
        new_html = new_html.replace("</body>", autosize_tag, 1)

    return new_html


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--self-test",
        action="store_true",
        help="Exercise deterministic SVG content versioning and exit.",
    )
    ap.add_argument(
        "--src",
        type=Path,
        default=WEB_DIR,
        help="Source directory of *.html + _shared.js + _style.css. "
             "Default is web/. Pass a relative name (e.g. 'web/nemoclaw') "
             "or an absolute path. The default --out is auto-derived from --src "
             "by appending _standalone, so --src web/nemoclaw → --out web/nemoclaw_standalone.",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory. Default derives from --src by appending _standalone.",
    )
    ap.add_argument(
        "--clean",
        action="store_true",
        help="Wipe the output directory before bundling.",
    )
    ap.add_argument(
        "--full",
        action="store_true",
        help="Build the full standalone for a self-hosted Pages site: the lab's dark theme, "
             "full nav chrome, and interactive panels, made self-contained. The default is the "
             "light, chrome-free iframe export for the edX navigator.",
    )
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    # Resolve --src: accept either an absolute path or a name relative to the task1/ root.
    web = args.src
    if not web.is_absolute():
        web = TASK1 / web
    if args.out is not None:
        out = args.out
    else:
        # Auto-derive: web → web_standalone, web/nemoclaw → web/nemoclaw_standalone.
        out = web.parent / (web.name + "_standalone")
    if not web.is_dir():
        print(f"web/ not found at {web}", file=sys.stderr)
        return 1

    if args.clean and out.exists():
        # Walk and unlink only generated files; skip paths the current user cannot remove.
        for p in sorted(out.rglob("*"), key=lambda x: len(x.parts), reverse=True):
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink()
                elif p.is_dir():
                    p.rmdir()
            except (PermissionError, OSError):
                pass
    out.mkdir(parents=True, exist_ok=True)

    # Normal source uses styles/ and scripts/. Translation overlays staged under
    # i18n/<lang>/ may be flat (_style.css, _shared.js) after archive filtering.
    # Support both so language builds do not silently disappear from Pages.
    css_text = _first_file(web / "styles" / "_style.css", web / "_style.css").read_text(encoding="utf-8")
    lite_css = _first_file(web / "styles" / "_lite_overlay.css", web / "_lite_overlay.css").read_text(encoding="utf-8")
    shared_js = _first_file(web / "scripts" / "_shared.js", web / "_shared.js").read_text(encoding="utf-8")

    pages = sorted(p for p in web.glob("*.html") if not p.name.startswith("."))
    if not pages:
        print(f"no *.html under {web}", file=sys.stderr)
        return 1

    mode = "full standalone (dark theme, full nav)" if args.full else "lite iframe export (light)"
    print(f"  mode: {mode}")
    for src in pages:
        bundled = bundle_one(src, css_text, lite_css, shared_js, full=args.full)
        dst = out / src.name
        dst.write_text(bundled, encoding="utf-8")
        kb = len(bundled.encode("utf-8")) / 1024
        print(f"  bundled {src.name:<28} → {dst.name}  ({kb:5.1f} KB)")

    linked_course_files = _copy_linked_course_files(web, out)
    if linked_course_files:
        print(f"  copied SKILL-linked course files ({', '.join(linked_course_files)})")

    # Ship the shared ES modules as real files so the pages' kept `./scripts/_shared.js` import and the
    # per-section modules scripts/_shared.js imports in turn (e.g. _openshell.js) all resolve as siblings,
    # loaded once via ES-module caching exactly as the lab serves them. Globbing _*.js carries any
    # module the split adds without a per-module edit here.
    script_dirs = [(web / "scripts", out / "scripts", "scripts/")]
    if any((web / name).is_file() for name in ("_shared.js", "_canvas.js")):
        script_dirs.append((web, out, ""))
    for src_dir, dst_dir, label_prefix in script_dirs:
        if not src_dir.is_dir():
            continue
        for mod in sorted(src_dir.glob("_*.js")):
            dst = dst_dir / mod.name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(mod, dst)
            print(f"  shipped {label_prefix}{mod.name}  ({dst.stat().st_size // 1024} KB)")

    # The SKILL hubs render via web/_skill_explorer.js, which lives one level ABOVE --src (one renderer
    # serves every surface). Subdir SKILLs live at scripts/SKILL.html, styles/SKILL.html, assets/SKILL.html,
    # and mats/SKILL.html, and they link ../styles/_style.css plus ../_skill_explorer.js. Ship those paths
    # exactly; a flat _style.css at the bundle root makes the link checker happy nowhere and becomes a
    # Pages 404 when strict MIME checking rejects the HTML fallback as a stylesheet.
    explorer = web.parent / "_skill_explorer.js"
    if explorer.is_file() and not (out / explorer.name).exists():
        shutil.copy2(explorer, out / explorer.name)
        print(f"  shipped {explorer.name}")

    styles = web / "styles"
    if styles.is_dir():
        dst_styles = out / "styles"
        dst_styles.mkdir(parents=True, exist_ok=True)
        for f in sorted(styles.glob("*")):
            if f.is_file():
                shutil.copy2(f, dst_styles / f.name)
        print(f"  copied styles/      ({sum(1 for p in dst_styles.iterdir() if p.is_file())} files)")
    else:
        flat_styles = [f for f in (web / "_style.css", web / "_lite_overlay.css") if f.is_file()]
        for f in flat_styles:
            shutil.copy2(f, out / f.name)
        if flat_styles:
            print(f"  copied flat styles  ({len(flat_styles)} files)")

    scripts_skill = web / "scripts" / "SKILL.html"
    if scripts_skill.is_file():
        (out / "scripts").mkdir(parents=True, exist_ok=True)
        shutil.copy2(scripts_skill, out / "scripts" / "SKILL.html")
        print("  copied scripts/SKILL.html")

    # Ship any LOCAL js a bundled page loads by relative <script src> (tool modules such as
    # studio.html's studio_main.js) so the page resolves its scripts and works standalone. Found by
    # scanning the pages rather than by naming the files, so a new tool module needs no edit here.
    # CDN srcs (http...) do not match the local pattern; _shared.js is already shipped above.
    js_refs = set()
    for src in pages:
        for m in re.finditer(r'<script[^>]+src=["\']\.?/?([\w./-]+\.m?js)["\']', src.read_text(encoding="utf-8")):
            js_refs.add(m.group(1))
    for ref in sorted(js_refs):
        cand = web / ref
        if cand.is_file() and not (out / ref).exists():
            (out / ref).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cand, out / ref)
            print(f"  shipped {ref}  ({cand.stat().st_size // 1024} KB)")

    # Carry non-inlined assets (images, SVGs) the pages reference by relative path, so the
    # bundle in --out is complete on its own and callers need no separate asset copy.
    assets = web / "assets"
    if assets.is_dir():
        shutil.copytree(assets, out / "assets", dirs_exist_ok=True)
        n_assets = sum(1 for p in (out / "assets").rglob("*") if p.is_file())
        print(f"  copied assets/      ({n_assets} files)")

    # Browser packages are resolved and bundled before release, then served from the same origin.
    # Copy the exact hashed assets, package inventory, and license evidence into every projection.
    vendor = web / "vendor"
    if vendor.is_dir():
        shutil.copytree(vendor, out / "vendor", dirs_exist_ok=True)
        n_vendor = sum(1 for p in (out / "vendor").rglob("*") if p.is_file())
        print(f"  copied vendor/      ({n_vendor} files)")

    # Ship the complete mats directory. mats/SKILL.html is a direct file index now, so every linked
    # cached markdown body, JSON index, and companion SVG must resolve in the deployed bundle.
    matsdir = web / "mats"
    if matsdir.is_dir():
        shutil.copytree(matsdir, out / "mats", dirs_exist_ok=True)
        n_mats = sum(1 for p in (out / "mats").rglob("*") if p.is_file())
        print(f"  copied mats/        ({n_mats} files)")

    _project_current_artifact_alias(out)
    print("  projected current-artifact alias")

    _copy_pyodide_review(out)
    print("  projected Pyodide review")

    _copy_compliance_review(out)
    print("  projected compliance review")

    rewritten_skills = _rewrite_skill_explorer_paths(out)
    if rewritten_skills:
        print(f"  rebased SKILL renderers ({rewritten_skills} files)")

    projected_skills = project_artifact_navigation(out)
    print(f"  projected artifact-local navigation ({projected_skills} files)")

    link_findings = artifact_link_audit.audit(out)
    if link_findings:
        print("artifact link audit: FAIL", file=sys.stderr)
        for finding in link_findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print("  artifact link audit: PASS")

    print(f"\n{len(pages)} pages → {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
