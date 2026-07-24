#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Vendor NVIDIA glossary pages into web/nemoclaw/mats/glossary_raw/ as markdown + local images.

For each glossary term it fetches the page, extracts the main article (the AEM
`div.root.responsivegrid` container, minus the header/nav/footer/script chrome),
converts it to GitHub-flavored markdown, downloads the page's content images into
`web/nemoclaw/mats/glossary_raw/images/`, rewrites the image references to those local files,
and records a version log (source URL, fetch date, content hash, image list) in
`web/nemoclaw/mats/glossary_raw/_versions.json`.

These pages are NVIDIA marketing content. See web/nemoclaw/mats/glossary_raw/README.md for why
they are vendored as primary sources to read critically, not quoted as ground truth.

Dependencies: requests, beautifulsoup4, markdownify, lxml
  pip install requests beautifulsoup4 markdownify lxml

Usage:
  python3 scripts/materials/vendor_glossary.py                 # vendor the default TERMS list
  python3 scripts/materials/vendor_glossary.py deep-agents      # vendor one or more named slugs
  python3 scripts/materials/vendor_glossary.py --list           # print the default TERMS and exit

Static-HTML limitation: images injected by client-side JavaScript (some inline
step diagrams) are not in the fetched HTML and are not captured. The hero image,
SVG figures, and card images that ship in the static markup are.
"""
from __future__ import annotations
import sys
import os
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root
import re
import glob
import json
import html
import hashlib
import datetime
import mimetypes
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as to_md

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = str(find_repo_root(Path(__file__).resolve()))
RAW = os.path.join(REPO, "web", "nemoclaw", "mats", "glossary_raw")
IMG = os.path.join(RAW, "images")
VERSIONS = os.path.join(RAW, "_versions.json")
BASE = "https://www.nvidia.com/en-us/glossary/{slug}/"
GLOSSARY_SOURCE_URL = "https://www.nvidia.com/en-us/glossary/?itemsPerPage=100"
UA = {"User-Agent": "Mozilla/5.0 (NVIDIA DLI course glossary vendoring)"}

# Deep-vendored glossary terms. Keep the default set lean.
TERMS = [
    "ai-agents",
    "ai-reasoning",
    "deep-agents",
    "retrieval-augmented-generation",
    "large-language-models",
    "ai-inference",
    "vector-database",
]

# Drop chrome before conversion. Keep <noscript>; it carries lazy-loaded images.
STRIP_SELECTORS = ["script", "style", "header", "nav", "iframe",
                   ".global-footer", ".page-footer-wrapper"]
STRIP_IDS = ["main-header", "brandFooter", "globalFooter", "country-selector-modal"]

INDEX_JSON = os.path.join(REPO, "web", "nemoclaw", "mats", "glossary_index.json")
# Static asset copy backs keyless client-side glossary search.
COURSE_INDEX = os.path.join(REPO, "web", "nemoclaw", "assets", "glossary_index.json")

# Full glossary index. --index fetches metadata and flags deep-vendored slugs.
INDEX_SLUGS = [
    "3d-reconstruction", "ai-agents", "ai-factory", "ai-grid", "ai-inference",
    "ai-infrastructure", "ai-reasoning", "ai-training", "ai-ran", "alphafold2",
    "mxnet", "apache-spark", "speech-to-text", "autonomous-networks", "autonomous-vehicles",
    "bert", "cot-prompting", "clustering", "computer-vision", "convolutional-neural-network",
    "dask", "data-flywheel", "deep-agents", "deep-learning", "digital-twin",
    "embodied-ai", "energy-efficiency", "frontier-models", "generative-ai", "graph-analytics",
    "high-performance-computing", "humanoid-robot", "imitation-learning", "industrial-ai", "k-means",
    "kubernetes", "large-language-models", "machine-learning", "mlops", "mixed-integer-programming",
    "mixture-of-transformers", "multi-agent-systems", "natural-language-processing", "networkx", "numba",
    "numpy", "omni-model", "pandas-python", "generative-physical-ai", "polars",
    "power-efficiency", "product-configurator", "pytorch", "quantum-computing", "random-forest",
    "reasoning-vision-language-action", "recommendation-system", "linear-regression-logistic-regression",
    "reinforcement-learning", "retrieval-augmented-generation", "robot-learning", "scikit-learn",
    "sensor-simulation", "sentiment-analysis", "simready", "hit-identification", "spatial-computing",
    "specialized-ai", "speech-ai", "stream-processing", "synthetic-data-generation", "tensorflow",
    "text-to-speech", "vector-database", "virtual-screening", "vision-language-models", "world-action-model",
    "world-models", "xgboost",
]

# Listing names beat SEO-shaped per-page titles.
NAMES = {
    "3d-reconstruction": "3D Reconstruction", "ai-agents": "AI Agents",
    "ai-factory": "AI Factory", "ai-grid": "AI Grid", "ai-inference": "AI Inference",
    "ai-infrastructure": "AI Infrastructure", "ai-reasoning": "AI Reasoning",
    "ai-training": "AI Training", "ai-ran": "AI-RAN", "alphafold2": "AlphaFold2",
    "mxnet": "Apache MXNet", "apache-spark": "Apache Spark",
    "speech-to-text": "Automatic Speech Recognition (ASR)", "autonomous-networks": "Autonomous Networks",
    "autonomous-vehicles": "Autonomous Vehicles", "bert": "BERT",
    "cot-prompting": "Chain of Thought Prompting", "clustering": "Cluster Analysis / Clustering",
    "computer-vision": "Computer Vision", "convolutional-neural-network": "Convolutional Neural Network",
    "dask": "Dask", "data-flywheel": "Data Flywheel", "deep-agents": "Deep Agents",
    "deep-learning": "Deep Learning", "digital-twin": "Digital Twin", "embodied-ai": "Embodied AI",
    "energy-efficiency": "Energy Efficiency", "frontier-models": "Frontier Models",
    "generative-ai": "Generative AI", "graph-analytics": "Graph Analytics",
    "high-performance-computing": "High-Performance Computing", "humanoid-robot": "Humanoid Robot",
    "imitation-learning": "Imitation Learning", "industrial-ai": "Industrial AI",
    "k-means": "K-Means Clustering Algorithm", "kubernetes": "Kubernetes",
    "large-language-models": "Large Language Models", "machine-learning": "Machine Learning",
    "mlops": "Machine Learning Operations (MLOps)", "mixed-integer-programming": "Mixed Integer Programming",
    "mixture-of-transformers": "Mixture-of-Transformers", "multi-agent-systems": "Multi-Agent Systems",
    "natural-language-processing": "Natural Language Processing", "networkx": "NetworkX",
    "numba": "Numba", "numpy": "NumPy", "omni-model": "Omni-Model", "pandas-python": "pandas",
    "generative-physical-ai": "Physical AI", "polars": "Polars", "power-efficiency": "Power Efficiency",
    "product-configurator": "Product Configurator", "pytorch": "PyTorch",
    "quantum-computing": "Quantum Computing", "random-forest": "Random Forest",
    "reasoning-vision-language-action": "Reasoning Vision Language Action",
    "recommendation-system": "Recommendation System",
    "linear-regression-logistic-regression": "Regression",
    "reinforcement-learning": "Reinforcement Learning",
    "retrieval-augmented-generation": "Retrieval-Augmented Generation (RAG)",
    "robot-learning": "Robot Learning", "scikit-learn": "Scikit-learn",
    "sensor-simulation": "Sensor Simulation", "sentiment-analysis": "Sentiment Analysis",
    "simready": "SimReady", "hit-identification": "Small-Molecule Hit Identification",
    "spatial-computing": "Spatial Computing", "specialized-ai": "Specialized AI",
    "speech-ai": "Speech AI", "stream-processing": "Stream Processing",
    "synthetic-data-generation": "Synthetic Data", "tensorflow": "TensorFlow",
    "text-to-speech": "Text-to-Speech", "vector-database": "Vector Database",
    "virtual-screening": "Virtual Screening", "vision-language-models": "Vision Language Models",
    "world-action-model": "World Action Model", "world-models": "World Foundation Models",
    "xgboost": "XGBoost",
}


def fetch(url: str) -> str:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.text


def page_title(soup: BeautifulSoup) -> str:
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        return og["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.split("|")[0].strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else "Untitled"


def clean_aem_image_url(src: str) -> str:
    # AEM emits responsive templates like `coreimg.100{.width}.jpeg`; strip the
    # width token so the URL resolves to a concrete asset.
    src = re.sub(r"\.\d+\{\.width\}", "", src)
    src = src.replace("{.width}", "")
    return src


def content_root(soup: BeautifulSoup):
    root = soup.select_one("div.root.responsivegrid")
    return root or soup.body


def vendor_images(node, slug: str, page_url: str) -> list[str]:
    # Drop any images from a previous run of this slug so re-fetches stay reproducible.
    for old in glob.glob(os.path.join(IMG, f"{slug}-*")):
        os.remove(old)
    saved: list[str] = []
    for img in node.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src or src.startswith("data:"):
            img.decompose()
            continue
        source_host = (urlparse(urljoin(page_url, src)).hostname or "").lower()
        if source_host == "img.youtube.com" or source_host.endswith(".img.youtube.com"):
            # video poster, not a representative diagram; leave the external ref as-is
            continue
        absu = urljoin(page_url, clean_aem_image_url(src))
        try:
            r = requests.get(absu, headers=UA, timeout=30)
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - a missing asset must not abort the page
            print(f"      ! image skipped ({exc}): {absu[:90]}")
            img.decompose()
            continue
        ext = os.path.splitext(urlparse(absu).path)[1].split("?")[0].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
            guessed = mimetypes.guess_extension((r.headers.get("content-type", "").split(";")[0]).strip())
            ext = guessed or ".img"
        fname = f"{slug}-{len(saved) + 1}{ext}"
        with open(os.path.join(IMG, fname), "wb") as fh:
            fh.write(r.content)
        img["src"] = f"images/{fname}"
        # srcset would re-introduce remote/templated URLs after markdown conversion
        if img.has_attr("srcset"):
            del img["srcset"]
        saved.append(fname)
    return saved


def absolutize_links(node, page_url: str) -> None:
    for a in node.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.startswith(("http://", "https://", "#", "mailto:")):
            a["href"] = urljoin(page_url, href)


def vendor(slug: str, versions: dict, today: str) -> None:
    url = BASE.format(slug=slug)
    soup = BeautifulSoup(fetch(url), "lxml")
    title = page_title(soup)
    node = content_root(soup)
    # Promote <noscript> image fallbacks into the tree (the real <img src> lives there).
    for ns in node.find_all("noscript"):
        ns.unwrap()
    for sel in STRIP_SELECTORS:
        for el in node.select(sel):
            el.decompose()
    for el_id in STRIP_IDS:
        el = node.find(id=el_id)
        if el:
            el.decompose()
    images = vendor_images(node, slug, url)
    absolutize_links(node, url)

    body = to_md(str(node), heading_style="ATX", bullets="-")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    out = f"# [{title}]({url})\n\n{body}\n"
    with open(os.path.join(RAW, f"{slug}.md"), "w", encoding="utf-8") as fh:
        fh.write(out)

    versions[slug] = {
        "url": url,
        "fetched": today,
        "sha256": hashlib.sha256(out.encode("utf-8")).hexdigest()[:16],
        "bytes": len(out),
        "images": images,
    }
    print(f"  {slug}: {len(out)} bytes, {len(images)} image(s)")


def _meta(html: str, key: str, attr: str = "name") -> str:
    # Extract a <meta> content value, tolerant of attribute order.
    pat1 = r'<meta[^>]*' + attr + r'=["\']' + re.escape(key) + r'["\'][^>]*content=["\']([^"\']*)'
    pat2 = r'<meta[^>]*content=["\']([^"\']*)["\'][^>]*' + attr + r'=["\']' + re.escape(key) + r'["\']'
    m = re.search(pat1, html, re.I) or re.search(pat2, html, re.I)
    return m.group(1).strip() if m else ""


def _clean_term(title: str, slug: str) -> str:
    # og:title comes in forms like "What are AI Agents?" or "Apache Spark"; reduce to the bare term, falling back to a title-cased slug.
    t = re.sub(r"^\s*what\s+(is|are)\s+", "", title, flags=re.I).strip().rstrip("?").strip()
    t = re.split(r"\s*[|·]\s*", t)[0].strip()
    return t or slug.replace("-", " ").title()


def index_one(slug: str) -> dict:
    url = BASE.format(slug=slug)
    page_html = fetch(url)
    title = html.unescape(_meta(page_html, "og:title", "property"))
    blurb = " ".join(html.unescape(_meta(page_html, "description")
                                   or _meta(page_html, "og:description", "property")).split())
    kw = html.unescape(_meta(page_html, "keywords"))
    _noise = {"nvidia glossary", "nvidia", "dictionary", "glossary"}
    tags = [k.strip() for k in kw.split(",")
            if k.strip() and k.strip().lower() not in _noise
            and not k.strip().lower().startswith(("definition of", "what is", "what are"))]
    return {"slug": slug, "term": NAMES.get(slug) or _clean_term(title, slug),
            "url": url, "blurb": blurb, "tags": tags}


def build_index(slugs: list[str]) -> int:
    versioned: set[str] = set()
    if os.path.exists(VERSIONS):
        with open(VERSIONS, encoding="utf-8") as fh:
            versioned = set(json.load(fh).keys())
    entries = []
    for slug in slugs:
        try:
            e = index_one(slug)
            e["deep"] = slug in versioned   # full vendored markdown in glossary_raw/<slug>.md
            entries.append(e)
            flag = " [deep]" if e["deep"] else ""
            print(f"  {slug}: {e['term']} ({len(e['blurb'])} chars, {len(e['tags'])} tags){flag}")
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"  {slug}: FAILED ({exc})")
    entries.sort(key=lambda e: e["term"].lower())
    payload = {
        "source": GLOSSARY_SOURCE_URL,
        "fetched": datetime.date.today().isoformat(),
        "count": len(entries),
        "terms": entries,
    }
    for path in (INDEX_JSON, COURSE_INDEX):
        if not os.path.isdir(os.path.dirname(path)):
            continue
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"  -> {path} ({len(entries)} terms)")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if "--list" in args:
        print("\n".join(TERMS))
        return 0
    if "--index" in args:
        slugs = [a for a in args if not a.startswith("-")] or INDEX_SLUGS
        return build_index(slugs)
    slugs = [a for a in args if not a.startswith("-")] or TERMS
    os.makedirs(IMG, exist_ok=True)
    versions = {}
    if os.path.exists(VERSIONS):
        with open(VERSIONS, encoding="utf-8") as fh:
            versions = json.load(fh)
    today = datetime.date.today().isoformat()
    for slug in slugs:
        try:
            vendor(slug, versions, today)
        except Exception as exc:  # noqa: BLE001 - report and continue with the rest
            print(f"  {slug}: FAILED ({exc})")
    with open(VERSIONS, "w", encoding="utf-8") as fh:
        json.dump(dict(sorted(versions.items())), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"  -> {VERSIONS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
