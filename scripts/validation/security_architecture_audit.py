#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Validate the release-owned security architecture graph and SVG projection."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts"))
        break
from _bootstrap import add_script_paths, find_repo_root  # noqa: E402

ROOT = find_repo_root(Path(__file__).resolve())
add_script_paths(ROOT / "scripts")
from render_security_architecture import edge_path, model_digest, render  # noqa: E402

MODEL = ROOT / "docs" / "security-architecture.json"
SVG = ROOT / "docs" / "security-architecture.svg"
DOC = ROOT / "docs" / "security-design.md"
CONTROL_REGISTER = ROOT / "docs" / "security-control-themes.json"
RELEASE_STAGES = {"deploy", "verify", "review"}
EXPECTED_SVG_TITLE = "Security architecture for the DLI course Securing Agents with OpenShell and NemoClaw"
TOE_NODE_IDS = {"source", "artifact", "browser"}
EXTERNAL_NODE_IDS = {"ci", "pages_host", "launchable_host", "model_api", "nemoclaw"}
TOE_ASSURANCE = "REPOSITORY EVIDENCE"
EXTERNAL_ASSURANCE = "NO LIVE EVIDENCE FROM EXTERNAL OPERATOR"
ALLOWED_SECURITY_OBJECTIVES = {"confidentiality", "integrity", "availability"}
EXPECTED_EDGE_IDS = {
    "source_to_ci",
    "ci_to_artifact",
    "artifact_to_pages",
    "artifact_to_launchable",
    "pages_to_browser",
    "launchable_to_browser",
    "browser_to_models",
    "browser_to_nemoclaw",
}
EXPECTED_EXCLUDED_INTERACTIONS = {
    "relay_to_model",
    "relay_to_nemoclaw",
    "launchable_to_nemoclaw",
    "launchable_to_model",
    "reviewer_handoff",
}
URL_HOST_RE = re.compile(r"(?:https?|wss?)://[A-Za-z0-9][A-Za-z0-9._-]*", re.I)
DECLARED_URL_RE = re.compile(
    r"(?:const|let|var)\s+[A-Z0-9_]*(?:URL|URI|BASE|ORIGIN|ENDPOINT|PROXY)[A-Z0-9_]*\s*=\s*[\"'`](?P<url>(?:https?|wss?)://[A-Za-z0-9][A-Za-z0-9._-]*)",
    re.I,
)
CALL_URL_RE = re.compile(r"(?:fetch|WebSocket|import|URL)\s*\(\s*[\"'`](?P<url>(?:https?|wss?)://[A-Za-z0-9][A-Za-z0-9._-]*)", re.I)
PROPERTY_URL_RE = re.compile(r"(?:proxyBase|defaultUrl|upstream)\s*[:=]\s*[\"'`](?P<url>(?:https?|wss?)://[A-Za-z0-9][A-Za-z0-9._-]*)", re.I)
IMPORT_ARRAY_RE = re.compile(r"(?:IMPORT_URLS|DEPENDENCY_URLS)\s*=\s*\[(.*?)\]", re.I | re.S)


class RuntimeHTMLParser(HTMLParser):
    """Collect browser-active URLs and inline JavaScript, excluding ordinary links."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []
        self.scripts: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script":
            self._in_script = True
            if values.get("src"):
                self.urls.append(values["src"] or "")
        elif tag == "iframe" and values.get("src"):
            self.urls.append(values["src"] or "")
        elif tag == "link" and values.get("href") and values.get("rel", "").lower() in {"stylesheet", "preload", "modulepreload"}:
            self.urls.append(values["href"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self.scripts.append(data)


def ci_contract(text: str) -> tuple[list[str], dict[str, str]]:
    stages_match = re.search(r"^stages:\s*\[([^]]+)\]", text, re.M)
    stages = [item.strip() for item in stages_match.group(1).split(",")] if stages_match else []
    jobs: dict[str, str] = {}
    current = ""
    reserved = {"stages", "variables", "workflow", "default", "include", "image", "services", "cache", "before_script", "after_script"}
    for line in text.splitlines():
        top = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*):\s*", line)
        if top:
            current = "" if top.group(1) in reserved else top.group(1)
            continue
        stage = re.fullmatch(r"  stage:\s*([A-Za-z0-9_-]+)\s*", line)
        if current and stage and stage.group(1) in RELEASE_STAGES:
            jobs[current] = stage.group(1)
    return stages, jobs


def runtime_contract(root: Path) -> tuple[list[str], list[str]]:
    urls: list[str] = []
    scripts: list[str] = []
    for path in sorted((root / "web/nemoclaw").glob("*.html")):
        parser = RuntimeHTMLParser()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        urls.extend(parser.urls)
        scripts.extend(parser.scripts)
    for folder in (root / "web/nemoclaw/scripts", root / "scripts/cors-proxy"):
        for path in sorted(folder.glob("*.js")):
            scripts.append(path.read_text(encoding="utf-8", errors="replace"))
    for text in scripts:
        urls.extend(match.group("url") for pattern in (DECLARED_URL_RE, CALL_URL_RE, PROPERTY_URL_RE) for match in pattern.finditer(text))
        for block in IMPORT_ARRAY_RE.finditer(text):
            urls.extend(match.group(0) for match in URL_HOST_RE.finditer(block.group(1)))
    hosts: set[str] = set()
    for value in urls:
        host = (urlsplit(value).hostname or "").lower()
        if not host or host in {"localhost", "nginx", "www.w3.org"}:
            continue
        if "example" in host or "your-subdomain" in host or host.endswith("-"):
            continue
        hosts.add(host)
    suffixes = {
        match.group(1).lower()
        for text in scripts
        for match in re.finditer(r"\.endsWith\(\s*[\"'](\.[A-Za-z0-9-]+\.[A-Za-z]{2,})[\"']\s*\)", text)
    }
    return sorted(hosts), sorted(suffixes)


def observe_system(root: Path = ROOT) -> dict:
    stages, jobs = ci_contract("\n".join(
        (root / rel).read_text(encoding="utf-8")
        for rel in (".gitlab/ci/core.yml", ".gitlab/ci/sca.yml")
    ))
    hosts, suffixes = runtime_contract(root)
    workers = sorted(path.relative_to(root).as_posix() for path in (root / "scripts/cors-proxy").glob("*worker*.js"))
    return {
        "ci_stages": stages,
        "release_jobs": jobs,
        "browser_hosts": hosts,
        "dynamic_host_suffixes": suffixes,
        "cors_worker_sources": workers,
    }


def contract_digest(contract: dict) -> str:
    payload = json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def finding(code: str, path: str, detail: str) -> dict[str, str]:
    return {"code": code, "path": path, "detail": detail}


def public_metadata_findings(contents: dict[str, str]) -> list[dict[str, str]]:
    patterns = (
        ("internal-review-name", re.compile(r"\bTA" r"VA\b|\bnS" r"pect\b", re.I)),
        ("internal-program-id", re.compile(r"\bNSP" r"ECT-[A-Z0-9-]+\b", re.I)),
        ("internal-release-state", re.compile(r"pending-" r"osrb-approval", re.I)),
        ("internal-version", re.compile(r"\bv[0-9]+\.[0-9]+(?:\.[0-9]+)?\b", re.I)),
        ("provider-detail", re.compile(r"Cloudflare\s+Access|NVIDIA\s+model\s+services", re.I)),
    )
    out: list[dict[str, str]] = []
    for path, text in contents.items():
        for code, pattern in patterns:
            match = pattern.search(text)
            if match:
                out.append(finding(code, path, f"review-neutral artifact exposes restricted metadata: {match.group(0)}"))
    return out


def yaml_top_level_children(text: str, section: str) -> set[str]:
    active = False
    children: set[str] = set()
    for line in text.splitlines():
        if re.fullmatch(rf"{re.escape(section)}:\s*", line):
            active = True
            continue
        if active and line and not line.startswith((" ", "#")):
            break
        if active:
            match = re.match(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$", line)
            if match:
                children.add(match.group(1))
    return children


def rectangles_overlap(a: dict, b: dict) -> bool:
    return (
        a["x"] < b["x"] + b["width"]
        and b["x"] < a["x"] + a["width"]
        and a["y"] < b["y"] + b["height"]
        and b["y"] < a["y"] + a["height"]
    )


def segment_crosses_node(a: tuple[float, float], b: tuple[float, float], node: dict, pad: float = 4) -> bool:
    left, right = node["x"] + pad, node["x"] + node["width"] - pad
    top, bottom = node["y"] + pad, node["y"] + node["height"] - pad
    if a[0] == b[0]:
        return left < a[0] < right and max(min(a[1], b[1]), top) < min(max(a[1], b[1]), bottom)
    if a[1] == b[1]:
        return top < a[1] < bottom and max(min(a[0], b[0]), left) < min(max(a[0], b[0]), right)
    return False


def segments_overlap(a1: tuple[float, float], a2: tuple[float, float], b1: tuple[float, float], b2: tuple[float, float]) -> bool:
    if a1[1] == a2[1] == b1[1] == b2[1]:
        return max(min(a1[0], a2[0]), min(b1[0], b2[0])) < min(max(a1[0], a2[0]), max(b1[0], b2[0]))
    if a1[0] == a2[0] == b1[0] == b2[0]:
        return max(min(a1[1], a2[1]), min(b1[1], b2[1])) < min(max(a1[1], a2[1]), max(b1[1], b2[1]))
    return False


def project_doc_findings(text: str) -> list[dict[str, str]]:
    tokens = (
        "## System scope",
        "## Browser routing by host",
        "## Trust boundaries and data",
        "## Security controls",
        "## Release controls",
        "## Evidence and reconstruction",
        "security-architecture.svg",
        "may select a reviewed course release",
        "external and unattested",
        "existing browser credential mechanism",
        "Same-origin direct route",
        "only solid green nodes are Target of Evaluation components",
        "External-to-external internals are excluded",
        "Repository validators support human analysis",
    )
    return [
        finding("project-doc", "docs/security-design.md", f"missing security-design token: {token}")
        for token in tokens if token and token not in text
    ]


def audit_model(model: dict, *, root: Path = ROOT, svg_text: str | None = None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if model.get("schema") != "nemoclaw-security-architecture/2":
        out.append(finding("schema", "docs/security-architecture.json", "schema must be nemoclaw-security-architecture/2"))
    system = model.get("system", {})
    try:
        control_target = json.loads(CONTROL_REGISTER.read_text(encoding="utf-8"))["target_of_evaluation"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        out.append(finding("ownership-source", "docs/security-control-themes.json", str(exc)))
        control_target = {}
    if system.get("target_of_evaluation") != control_target.get("owned"):
        out.append(finding(
            "toe-cross-document", "docs/security-architecture.json",
            "diagram Target of Evaluation differs from the canonical control register",
        ))
    if system.get("external_context") != control_target.get("external_dependencies"):
        out.append(finding(
            "external-cross-document", "docs/security-architecture.json",
            "diagram external context differs from the canonical control register",
        ))
    if "Only Target of Evaluation entries are course-owned components" not in str(
        system.get("ownership_rule", "")
    ):
        out.append(finding(
            "ownership-rule", "docs/security-architecture.json",
            "diagram does not state the fail-closed ownership rule",
        ))
    threat_enumeration = system.get("threat_enumeration") or {}
    if "only for the declared edges" not in str(threat_enumeration.get("rule", "")) or "Do not infer" not in str(
        threat_enumeration.get("rule", "")
    ):
        out.append(finding(
            "threat-enumeration", "docs/security-architecture.json",
            "threat enumeration is not limited to the canonical declared edges",
        ))
    if "remain one Target of Evaluation boundary flow" not in str(
        threat_enumeration.get("route_consolidation", "")
    ):
        out.append(finding(
            "route-consolidation", "docs/security-architecture.json",
            "direct and relayed route variants are not consolidated",
        ))
    objective_rules = threat_enumeration.get("objective_rules") or []
    objective_text = " ".join(str(value) for value in objective_rules)
    if not all(token in objective_text for token in (
        "Confidentiality is not a security objective for public course source",
        "Integrity applies to course source",
        "Availability applies to course validation",
    )):
        out.append(finding(
            "objective-rules", "docs/security-architecture.json",
            "security objectives do not preserve the public-source and external-ownership boundary",
        ))
    excluded = threat_enumeration.get("excluded_external_interactions") or []
    excluded_ids = {row.get("id") for row in excluded if isinstance(row, dict)}
    if excluded_ids != EXPECTED_EXCLUDED_INTERACTIONS or len(excluded_ids) != len(excluded):
        out.append(finding(
            "excluded-interactions", "docs/security-architecture.json",
            "external-internal and human-workflow exclusions changed",
        ))
    for row in excluded:
        if not isinstance(row, dict) or not str(row.get("interaction", "")).strip() or not str(row.get("reason", "")).strip():
            out.append(finding(
                "excluded-interaction-shape", "docs/security-architecture.json",
                "each excluded interaction needs an id, interaction, and reason",
            ))
    forbidden_metadata = {"program", "nspect_id", "version", "release_type"}
    leaked = sorted(forbidden_metadata.intersection(model) | forbidden_metadata.intersection(system))
    if leaked:
        out.append(finding("internal-metadata", "docs/security-architecture.json", f"public graph contains internal workflow metadata: {leaked}"))
    model_text = json.dumps(model, ensure_ascii=False).casefold()
    for phrase in (
        "secure course delivery architecture",
        "hardened pipeline",
        "immutable, verified build artifact",
    ):
        if phrase in model_text:
            out.append(finding(
                "architecture-overclaim", "docs/security-architecture.json",
                f"diagram makes an unsupported assurance claim: {phrase}",
            ))

    zones_list = model.get("zones", [])
    nodes_list = model.get("nodes", [])
    edges = model.get("edges", [])
    zones = {zone.get("id"): zone for zone in zones_list if zone.get("id")}
    nodes = {node.get("id"): node for node in nodes_list if node.get("id")}
    if len(zones) != len(zones_list):
        out.append(finding("duplicate-zone", "docs/security-architecture.json", "zone ids must be present and unique"))
    if len(nodes) != len(nodes_list):
        out.append(finding("duplicate-node", "docs/security-architecture.json", "node ids must be present and unique"))

    canvas = model.get("canvas", {})
    canvas_w, canvas_h = canvas.get("width", 0), canvas.get("height", 0)
    edge_region_bottom = min((zone["y"] + zone["height"] for zone in zones_list), default=0)
    if canvas_w < 1200 or canvas_h <= edge_region_bottom:
        out.append(finding("canvas", "docs/security-architecture.json", "canvas must leave room for zones and the flow register"))

    for node in nodes_list:
        node_id = node.get("id", "?")
        zone = zones.get(node.get("zone"))
        if not zone:
            out.append(finding("node-zone", "docs/security-architecture.json", f"{node_id} names unknown zone {node.get('zone')}"))
            continue
        for key in ("label", "detail", "kind", "ownership", "assurance", "x", "y", "width", "height"):
            if node.get(key) in (None, ""):
                out.append(finding("node-field", "docs/security-architecture.json", f"{node_id}.{key} is required"))
        if not (
            node.get("x", 0) >= zone["x"]
            and node.get("y", 0) >= zone["y"]
            and node.get("x", 0) + node.get("width", 0) <= zone["x"] + zone["width"]
            and node.get("y", 0) + node.get("height", 0) <= zone["y"] + zone["height"]
        ):
            out.append(finding("node-bounds", "docs/security-architecture.json", f"{node_id} escapes zone {zone['id']}"))
        ownership = node.get("ownership")
        if ownership not in {"toe", "external"}:
            out.append(finding("node-ownership", "docs/security-architecture.json", f"{node_id} has invalid ownership {ownership}"))
        if ownership == "toe" and node.get("assurance") != TOE_ASSURANCE:
            out.append(finding("toe-assurance", "docs/security-architecture.json", f"{node_id} lacks repository-evidence assurance"))
        if ownership == "external" and node.get("assurance") != EXTERNAL_ASSURANCE:
            out.append(finding("external-assurance", "docs/security-architecture.json", f"{node_id} lacks the no-live-evidence warning"))
        if ownership == "external" and node.get("controls"):
            out.append(finding("external-control-claim", "docs/security-architecture.json", f"{node_id} presents external controls as current"))
        if ownership == "toe" and not node.get("controls"):
            out.append(finding("toe-controls", "docs/security-architecture.json", f"{node_id} has no evidence-backed repository controls"))
        if node.get("privileged") and ownership == "toe" and len(node.get("controls", [])) < 2:
            out.append(finding("privileged-controls", "docs/security-architecture.json", f"{node_id} needs at least two explicit controls"))
        if node.get("sensitive") and ownership == "toe" and not node.get("controls"):
            out.append(finding("sensitive-controls", "docs/security-architecture.json", f"{node_id} handles sensitive data without controls"))
        if not node.get("evidence"):
            out.append(finding("node-evidence", "docs/security-architecture.json", f"{node_id} has no repository evidence"))

    for index, left in enumerate(nodes_list):
        for right in nodes_list[index + 1:]:
            if left.get("zone") == right.get("zone") and rectangles_overlap(left, right):
                out.append(finding("node-overlap", "docs/security-architecture.json", f"{left.get('id')} overlaps {right.get('id')}"))

    edge_ids: set[str] = set()
    edge_segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    connected: set[str] = set()
    for edge in edges:
        edge_id = edge.get("id", "?")
        if edge_id in edge_ids or edge_id == "?":
            out.append(finding("duplicate-edge", "docs/security-architecture.json", f"edge id {edge_id} must be present and unique"))
        edge_ids.add(edge_id)
        source, target = nodes.get(edge.get("from")), nodes.get(edge.get("to"))
        if not source or not target or source is target:
            out.append(finding("dangling-edge", "docs/security-architecture.json", f"{edge_id} has missing or identical endpoints"))
            continue
        connected.update((source["id"], target["id"]))
        for key in ("protocol", "data", "auth", "trust_boundary"):
            if not str(edge.get(key, "")).strip():
                out.append(finding("edge-field", "docs/security-architecture.json", f"{edge_id}.{key} is required"))
        objectives = edge.get("security_objectives")
        if (
            not isinstance(objectives, list)
            or not objectives
            or len(objectives) != len(set(objectives))
            or not set(objectives).issubset(ALLOWED_SECURITY_OBJECTIVES)
        ):
            out.append(finding(
                "edge-objectives", "docs/security-architecture.json",
                f"{edge_id} must list unique applicable confidentiality, integrity, or availability objectives",
            ))
        elif "confidentiality" in objectives and not edge.get("sensitive"):
            out.append(finding(
                "public-confidentiality", "docs/security-architecture.json",
                f"{edge_id} assigns confidentiality to public, non-sensitive course data",
            ))
        elif edge.get("sensitive") and "confidentiality" not in objectives:
            out.append(finding(
                "sensitive-confidentiality", "docs/security-architecture.json",
                f"{edge_id} carries sensitive data without a confidentiality objective",
            ))
        if source.get("zone") != target.get("zone") and edge.get("auth") in (None, "", "unknown"):
            out.append(finding("boundary-auth", "docs/security-architecture.json", f"{edge_id} crosses zones without explicit authentication"))
        if edge.get("sensitive") and (not edge.get("data") or edge.get("auth") in (None, "", "none")):
            out.append(finding("sensitive-flow", "docs/security-architecture.json", f"{edge_id} must name protected data and authentication"))
        if not edge.get("evidence"):
            out.append(finding("edge-evidence", "docs/security-architecture.json", f"{edge_id} has no repository evidence"))
        route = edge.get("route", {})
        if route:
            valid_sides = {"top", "right", "bottom", "left"}
            if not route.get("from_point") and route.get("from_side") not in valid_sides:
                out.append(finding("edge-route", "docs/security-architecture.json", f"{edge_id} route needs a valid from_side or from_point"))
            if not route.get("to_point") and route.get("to_side") not in valid_sides:
                out.append(finding("edge-route", "docs/security-architecture.json", f"{edge_id} route needs a valid to_side or to_point"))
            if route.get("from_point") and route.get("from_side"):
                out.append(finding("edge-route", "docs/security-architecture.json", f"{edge_id} cannot declare both from_side and from_point"))
            if route.get("to_point") and route.get("to_side"):
                out.append(finding("edge-route", "docs/security-architecture.json", f"{edge_id} cannot declare both to_side and to_point"))
            for field in ("from_fraction", "to_fraction"):
                value = route.get(field, 0.5)
                if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                    out.append(finding("edge-port", "docs/security-architecture.json", f"{edge_id}.{field} must be between 0 and 1"))
            for point in [*( [route["from_point"]] if route.get("from_point") else []), *route.get("via", []), *( [route["to_point"]] if route.get("to_point") else []), *( [route["badge_point"]] if route.get("badge_point") else [])]:
                if not isinstance(point, list) or len(point) != 2 or not (0 <= point[0] <= canvas_w and 0 <= point[1] <= canvas_h):
                    out.append(finding("edge-route", "docs/security-architecture.json", f"{edge_id} has an invalid route point: {point}"))
        path_text, _mx, _my = edge_path(source, target, route)
        points = [tuple(map(float, point.split(","))) for point in path_text.split()]
        edge_segments[edge_id] = list(zip(points, points[1:]))
        for a, b in zip(points, points[1:]):
            if a[0] != b[0] and a[1] != b[1]:
                out.append(finding("edge-route", "docs/security-architecture.json", f"{edge_id} contains a diagonal segment {a} to {b}"))
        for node_id, node in nodes.items():
            if node_id in {source["id"], target["id"]}:
                continue
            if any(segment_crosses_node(a, b, node) for a, b in zip(points, points[1:])):
                out.append(finding("edge-cross-node", "docs/security-architecture.json", f"{edge_id} crosses unrelated node {node_id}"))

    allowed_overlaps: set[tuple[str, str]] = set()
    for pair in model.get("layout", {}).get("allowed_edge_overlaps", []):
        if not isinstance(pair, list) or len(pair) != 2 or pair[0] not in edge_ids or pair[1] not in edge_ids or pair[0] == pair[1]:
            out.append(finding("edge-overlap-allowance", "docs/security-architecture.json", f"invalid allowed edge overlap: {pair}"))
            continue
        allowed_overlaps.add(tuple(sorted(pair)))
    used_allowances: set[tuple[str, str]] = set()
    segment_items = sorted(edge_segments.items())
    for index, (left_id, left_segments) in enumerate(segment_items):
        for right_id, right_segments in segment_items[index + 1:]:
            if not any(segments_overlap(a1, a2, b1, b2) for a1, a2 in left_segments for b1, b2 in right_segments):
                continue
            pair = (left_id, right_id)
            if pair in allowed_overlaps:
                used_allowances.add(pair)
            else:
                out.append(finding("edge-overlap", "docs/security-architecture.json", f"{left_id} overlaps {right_id}"))
    for pair in sorted(allowed_overlaps - used_allowances):
        out.append(finding("edge-overlap-allowance", "docs/security-architecture.json", f"stale edge overlap allowance: {pair}"))

    trunk_branch_edges: set[str] = set()
    trunk_ids: set[str] = set()
    indexed_edges = {edge.get("id"): edge for edge in edges}
    for trunk in model.get("layout", {}).get("shared_trunks", []):
        trunk_id = trunk.get("id", "")
        source_id = trunk.get("source_node", "")
        points = trunk.get("points", [])
        if not trunk_id or trunk_id in trunk_ids or source_id not in nodes or len(points) < 2:
            out.append(finding("trunk-contract", "docs/security-architecture.json", f"invalid shared trunk {trunk_id or '?'}"))
            continue
        trunk_ids.add(trunk_id)
        source = nodes[source_id]
        first = points[0]
        on_boundary = (
            source["x"] <= first[0] <= source["x"] + source["width"]
            and source["y"] <= first[1] <= source["y"] + source["height"]
            and (first[0] in {source["x"], source["x"] + source["width"]} or first[1] in {source["y"], source["y"] + source["height"]})
        )
        if not on_boundary:
            out.append(finding("trunk-contract", "docs/security-architecture.json", f"{trunk_id} must start on {source_id}'s boundary"))
        trunk_segments = [(tuple(a), tuple(b)) for a, b in zip(points, points[1:])]
        if any(a[0] != b[0] and a[1] != b[1] for a, b in trunk_segments):
            out.append(finding("trunk-contract", "docs/security-architecture.json", f"{trunk_id} contains a diagonal segment"))
        for edge_id, branch in trunk.get("branches", {}).items():
            edge = indexed_edges.get(edge_id)
            branch_tuple = tuple(branch)
            on_trunk = any(
                (a[0] == b[0] == branch_tuple[0] and min(a[1], b[1]) <= branch_tuple[1] <= max(a[1], b[1]))
                or (a[1] == b[1] == branch_tuple[1] and min(a[0], b[0]) <= branch_tuple[0] <= max(a[0], b[0]))
                for a, b in trunk_segments
            )
            if not edge or edge.get("from") != source_id or edge.get("route", {}).get("from_point") != branch or not on_trunk:
                out.append(finding("trunk-coverage", "docs/security-architecture.json", f"{trunk_id} branch {edge_id} does not match its source edge and route point"))
            trunk_branch_edges.add(edge_id)
    for edge in edges:
        if edge.get("route", {}).get("from_point") and edge.get("id") not in trunk_branch_edges:
            out.append(finding("trunk-coverage", "docs/security-architecture.json", f"{edge.get('id')} starts from an unregistered shared-trunk point"))

    for node_id in sorted(set(nodes) - connected):
        out.append(finding("isolated-node", "docs/security-architecture.json", f"{node_id} has no data-flow edge"))

    for node_id in ("model_api", "nemoclaw"):
        if node_id not in nodes or nodes[node_id].get("conditional"):
            out.append(finding("required-service", "docs/security-architecture.json", f"{node_id} must remain a required, non-conditional service"))
    route_contract = {edge_id: False for edge_id in EXPECTED_EDGE_IDS}
    indexed_edges = {edge.get("id"): edge for edge in edges}
    if set(indexed_edges) != EXPECTED_EDGE_IDS:
        out.append(finding(
            "threat-edge-scope", "docs/security-architecture.json",
            "declared threat edges differ from the reviewed course boundary",
        ))
    for edge_id, conditional in route_contract.items():
        edge = indexed_edges.get(edge_id)
        if not edge or bool(edge.get("conditional")) != conditional:
            out.append(finding("routing-contract", "docs/security-architecture.json", f"{edge_id} must exist with conditional={conditional}"))

    evidence_rows = []
    for owner in [*nodes_list, *edges]:
        evidence_rows.extend((owner.get("id", "?"), row) for row in owner.get("evidence", []))
    for owner_id, row in evidence_rows:
        rel = row.get("path", "")
        path = root / rel
        if not rel or not path.is_file():
            out.append(finding("evidence-path", rel or "docs/security-architecture.json", f"{owner_id} evidence path does not resolve"))
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in row.get("contains", []):
            if token not in text:
                out.append(finding("evidence-token", rel, f"{owner_id} evidence token not found: {token}"))

    coverage = model.get("coverage", {})
    if coverage.get("local_only_compose_services") or coverage.get("local_only_volumes"):
        out.append(finding("retired-runtime-coverage", "docs/security-architecture.json", "removed local runtime surfaces remain in the reviewed model"))
    for retired in ("cpu", "deploy", "workspace"):
        if (root / retired).exists():
            out.append(finding("retired-runtime-surface", retired, "repository-owned runtime surface returned"))
    if set(coverage.get("toe_nodes", [])) != TOE_NODE_IDS:
        out.append(finding("toe-node-coverage", "docs/security-architecture.json", "TOE node inventory changed"))
    if set(coverage.get("external_context_nodes", [])) != EXTERNAL_NODE_IDS:
        out.append(finding("external-node-coverage", "docs/security-architecture.json", "external-context node inventory changed"))
    actual_toe = {node["id"] for node in nodes_list if node.get("ownership") == "toe"}
    actual_external = {node["id"] for node in nodes_list if node.get("ownership") == "external"}
    if actual_toe != TOE_NODE_IDS or actual_external != EXTERNAL_NODE_IDS:
        out.append(finding("node-ownership-coverage", "docs/security-architecture.json", "node ownership does not match the reviewed boundary"))
    for node in nodes_list:
        if node.get("compose_service"):
            out.append(finding("local-only-node", "docs/security-architecture.json", f"{node.get('id')} represents a retired local runtime service in the architecture graph"))
    for surface, node_id in coverage.get("repository_surfaces", {}).items():
        if not (root / surface).exists():
            out.append(finding("surface-path", "docs/security-architecture.json", f"repository surface {surface} does not exist"))
        if node_id not in nodes:
            out.append(finding("coverage-node", "docs/security-architecture.json", f"repository surface {surface} maps to unknown node {node_id}"))
        elif nodes[node_id].get("ownership") != "toe":
            out.append(finding("surface-ownership", "docs/security-architecture.json", f"repository surface {surface} maps to external node {node_id}"))
    references = coverage.get("non_deployed_reference_sources", {})
    if set(references) != {"scripts/cors-proxy"} or not (root / "scripts/cors-proxy").is_dir():
        out.append(finding("reference-source-boundary", "docs/security-architecture.json", "relay examples are not explicitly non-deployed reference sources"))

    observed_digest = contract_digest(observe_system(root))
    reviewed_digest = coverage.get("observed_contract_sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", reviewed_digest):
        out.append(finding("contract-fingerprint", "docs/security-architecture.json", "observed_contract_sha256 must be a lowercase SHA-256 digest"))
    elif reviewed_digest != observed_digest:
        out.append(finding("contract-drift", "docs/security-architecture.json", "source-derived production topology changed; inspect --observed-contract and review the graph"))

    try:
        expected_svg = render(model)
    except (KeyError, TypeError, ValueError) as exc:
        expected_svg = None
        out.append(finding("projection-render", "docs/security-architecture.json", f"graph cannot render: {exc}"))
    if svg_text is None:
        svg_text = SVG.read_text(encoding="utf-8") if SVG.is_file() else ""
    if expected_svg is not None and svg_text != expected_svg:
        out.append(finding("stale-svg", "docs/security-architecture.svg", "projection differs from the canonical JSON graph"))
    for token in (
        'role="img"',
        'aria-labelledby="title desc"',
        'data-architecture-schema="nemoclaw-security-architecture/2"',
        "COURSE-OWNED",
        "EXTERNAL DEPENDENCY",
        "LIVE CONTROLS NOT ATTESTED",
        "THREAT ENUMERATION BOUNDARY · DECLARED FLOWS ONLY",
        "Only numbered flows and listed objectives are enumerated",
        f"model fingerprint: {model_digest(model)[:16]}",
        f'<title id="title">{EXPECTED_SVG_TITLE}</title>',
        f'<text class="title" x="48" y="48">{EXPECTED_SVG_TITLE}</text>',
    ):
        if token not in svg_text:
            out.append(finding("svg-accessibility", "docs/security-architecture.svg", f"missing {token}"))
    if "NemoClaw course security architecture" in svg_text:
        out.append(finding(
            "scope-title",
            "docs/security-architecture.svg",
            "diagram title conflates the DLI course review with the NemoClaw product",
        ))

    doc_text = DOC.read_text(encoding="utf-8") if DOC.is_file() else ""
    for token in ("security-architecture.json", "security-architecture.svg", "render_security_architecture.py --check", "tests/validation/test_embedded_validator_suites.py", "Browser routing by host", "embedded in an iframe", "do not use the relay", "internal program identifiers"):
        if token not in doc_text:
            out.append(finding("operator-doc", "docs/security-design.md", f"missing operator instruction: {token}"))
    project_doc_path = root / "docs" / "security-design.md"
    project_doc_text = project_doc_path.read_text(encoding="utf-8") if project_doc_path.is_file() else ""
    out.extend(project_doc_findings(project_doc_text))
    out.extend(public_metadata_findings({
        "docs/security-design.md": project_doc_text,
        "docs/security-architecture.svg": svg_text,
    }))
    return out


def audit() -> list[dict[str, str]]:
    try:
        model = json.loads(MODEL.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [finding("model-load", "docs/security-architecture.json", str(exc))]
    return audit_model(model)


def self_test() -> list[str]:
    base = json.loads(MODEL.read_text(encoding="utf-8"))
    expected_svg = render(base)
    cases = []

    mutation = copy.deepcopy(base)
    mutation["coverage"]["local_only_compose_services"] = {"nginx": "retired"}
    cases.append(("retired runtime coverage", mutation, expected_svg, "retired-runtime-coverage"))

    mutation = copy.deepcopy(base)
    mutation["coverage"]["toe_nodes"].remove("artifact")
    cases.append(("TOE node coverage", mutation, expected_svg, "toe-node-coverage"))

    mutation = copy.deepcopy(base)
    mutation["system"]["target_of_evaluation"] = mutation["system"]["target_of_evaluation"][1:]
    cases.append(("cross-document TOE", mutation, expected_svg, "toe-cross-document"))

    mutation = copy.deepcopy(base)
    mutation["system"].pop("threat_enumeration")
    cases.append(("missing threat enumeration boundary", mutation, expected_svg, "threat-enumeration"))

    mutation = copy.deepcopy(base)
    mutation["system"]["threat_enumeration"]["excluded_external_interactions"].pop()
    cases.append(("missing external interaction exclusion", mutation, expected_svg, "excluded-interactions"))

    mutation = copy.deepcopy(base)
    external = next(node for node in mutation["nodes"] if node["id"] == "model_api")
    external["controls"] = ["provider guarantees tenant isolation"]
    cases.append(("external control claim", mutation, expected_svg, "external-control-claim"))

    mutation = copy.deepcopy(base)
    next(node for node in mutation["nodes"] if node["id"] == "nemoclaw")["assurance"] = "VERIFIED"
    cases.append(("external assurance promotion", mutation, expected_svg, "external-assurance"))

    mutation = copy.deepcopy(base)
    next(node for node in mutation["nodes"] if node["id"] == "pages_host")["ownership"] = "toe"
    cases.append(("external node ownership promotion", mutation, expected_svg, "node-ownership-coverage"))

    mutation = copy.deepcopy(base)
    mutation["coverage"].pop("non_deployed_reference_sources")
    cases.append(("relay example deployment boundary", mutation, expected_svg, "reference-source-boundary"))

    mutation = copy.deepcopy(base)
    mutation["nodes"][0]["detail"] = "secure course delivery architecture"
    cases.append(("unsupported architecture assurance", mutation, expected_svg, "architecture-overclaim"))

    mutation = copy.deepcopy(base)
    next(node for node in mutation["nodes"] if node["id"] == "nemoclaw")["conditional"] = True
    cases.append(("required NemoClaw service", mutation, expected_svg, "required-service"))

    mutation = copy.deepcopy(base)
    next(edge for edge in mutation["edges"] if edge["id"] == "browser_to_nemoclaw")["conditional"] = True
    cases.append(("hosting route contract", mutation, expected_svg, "routing-contract"))

    mutation = copy.deepcopy(base)
    next(edge for edge in mutation["edges"] if edge["id"] == "browser_to_models")["route"]["to_fraction"] = 1.5
    cases.append(("edge port bounds", mutation, expected_svg, "edge-port"))

    mutation = copy.deepcopy(base)
    dependency_edge = next(edge for edge in mutation["edges"] if edge["id"] == "browser_to_nemoclaw")
    dependency_edge["route"]["via"] = [[800, 917.5], [800, 767.5]]
    cases.append(("edge overlap", mutation, expected_svg, "edge-overlap"))

    mutation = copy.deepcopy(base)
    mutation["layout"]["shared_trunks"][0]["branches"].pop("browser_to_nemoclaw")
    cases.append(("shared trunk coverage", mutation, expected_svg, "trunk-coverage"))

    mutation = copy.deepcopy(base)
    mutation["coverage"].pop("observed_contract_sha256")
    cases.append(("missing source contract fingerprint", mutation, expected_svg, "contract-fingerprint"))

    mutation = copy.deepcopy(base)
    mutation["coverage"]["observed_contract_sha256"] = "not-a-digest"
    cases.append(("invalid source contract fingerprint", mutation, expected_svg, "contract-fingerprint"))

    mutation = copy.deepcopy(base)
    mutation["coverage"]["observed_contract_sha256"] = "0" * 64
    cases.append(("source contract drift", mutation, expected_svg, "contract-drift"))

    mutation = copy.deepcopy(base)
    mutation["system"]["version"] = "internal"
    cases.append(("internal metadata", mutation, expected_svg, "internal-metadata"))

    mutation = copy.deepcopy(base)
    next(node for node in mutation["nodes"] if node["id"] == "pages_host")["compose_service"] = "lab"
    cases.append(("local-only node", mutation, expected_svg, "local-only-node"))

    mutation = copy.deepcopy(base)
    next(edge for edge in mutation["edges"] if edge["id"] == "source_to_ci")["to"] = "missing"
    cases.append(("dangling edge", mutation, expected_svg, "dangling-edge"))

    mutation = copy.deepcopy(base)
    next(edge for edge in mutation["edges"] if edge["id"] == "browser_to_models")["auth"] = ""
    cases.append(("boundary authentication", mutation, expected_svg, "edge-field"))

    mutation = copy.deepcopy(base)
    next(edge for edge in mutation["edges"] if edge["id"] == "source_to_ci").pop("security_objectives")
    cases.append(("missing edge objectives", mutation, expected_svg, "edge-objectives"))

    mutation = copy.deepcopy(base)
    next(edge for edge in mutation["edges"] if edge["id"] == "source_to_ci")["security_objectives"].append("confidentiality")
    cases.append(("public source confidentiality", mutation, expected_svg, "public-confidentiality"))

    mutation = copy.deepcopy(base)
    extra_edge = copy.deepcopy(next(edge for edge in mutation["edges"] if edge["id"] == "browser_to_models"))
    extra_edge.update({"id": "relay_to_model", "from": "model_api", "to": "nemoclaw", "route": {}})
    mutation["edges"].append(extra_edge)
    cases.append(("inferred external-to-external edge", mutation, expected_svg, "threat-edge-scope"))

    mutation = copy.deepcopy(base)
    next(edge for edge in mutation["edges"] if edge["id"] == "browser_to_nemoclaw")["data"] = ""
    cases.append(("sensitive flow", mutation, expected_svg, "sensitive-flow"))

    mutation = copy.deepcopy(base)
    next(node for node in mutation["nodes"] if node["id"] == "model_api")["evidence"][0]["contains"] = ["token-that-does-not-exist"]
    cases.append(("evidence token", mutation, expected_svg, "evidence-token"))

    mutation = copy.deepcopy(base)
    pages_edge = next(edge for edge in mutation["edges"] if edge["id"] == "artifact_to_pages")
    pages_workflow = next(row for row in pages_edge["evidence"] if row["path"] == ".github/workflows/pages.yml")
    pages_workflow["contains"] = ["actions/upload-pages-artifact", "actions/deploy-pages"]
    cases.append(("obsolete Pages upload evidence", mutation, expected_svg, "evidence-token"))

    mutation = copy.deepcopy(base)
    overlap = next(node for node in mutation["nodes"] if node["id"] == "model_api")
    target = next(node for node in mutation["nodes"] if node["id"] == "nemoclaw")
    overlap["x"], overlap["y"] = target["x"], target["y"]
    cases.append(("node overlap", mutation, expected_svg, "node-overlap"))

    mutation = copy.deepcopy(base)
    next(edge for edge in mutation["edges"] if edge["id"] == "browser_to_models")["route"] = {"from_point": [550, 760], "to_side": "left", "to_fraction": 0.35, "via": [[800, 760], [800, 677.5], [1300, 677.5], [1300, 816.75]]}
    cases.append(("edge crosses node", mutation, expected_svg, "edge-cross-node"))

    failures = []
    for label, model, svg, wanted in cases:
        codes = {row["code"] for row in audit_model(model, svg_text=svg)}
        if wanted not in codes:
            failures.append(f"detector missed {label}: expected {wanted}, got {sorted(codes)}")
    if "stale-svg" not in {row["code"] for row in audit_model(base, svg_text=expected_svg.replace("Flow register", "Flow registry", 1))}:
        failures.append("detector missed stale SVG")
    missing_fingerprint = expected_svg.replace(f"model fingerprint: {model_digest(base)[:16]}", "model fingerprint: missing", 1)
    if "svg-accessibility" not in {row["code"] for row in audit_model(base, svg_text=missing_fingerprint)}:
        failures.append("detector missed visible model-fingerprint drift")
    wrong_title = expected_svg.replace(EXPECTED_SVG_TITLE, "NemoClaw course security architecture")
    if "scope-title" not in {row["code"] for row in audit_model(base, svg_text=wrong_title)}:
        failures.append("detector missed product-like diagram title")
    probe_stages, probe_jobs = ci_contract("stages: [test, deploy, review]\n\npages:\n  stage: deploy\n\nrelease_check:\n  stage: review\n")
    if probe_stages != ["test", "deploy", "review"] or probe_jobs != {"pages": "deploy", "release_check": "review"}:
        failures.append(f"CI observer missed a release topology change: {probe_stages}, {probe_jobs}")
    parser = RuntimeHTMLParser()
    parser.feed('<script src="https://new.cdn.test/app.js"></script>')
    declared = DECLARED_URL_RE.search('const MODEL_API_URL = `wss://new.model.test/v1`;')
    suffix = re.search(r"\.endsWith\(\s*[\"'](\.[A-Za-z0-9-]+\.[A-Za-z]{2,})[\"']\s*\)", 'host.endsWith(".new-runtime.test")')
    if parser.urls != ["https://new.cdn.test/app.js"] or not declared or declared.group("url") != "wss://new.model.test" or not suffix:
        failures.append("runtime observer missed an active resource, endpoint, or dynamic host suffix")
    project_doc = DOC.read_text(encoding="utf-8")
    missing_project_doc = project_doc.replace("## Trust boundaries and data", "## Data", 1)
    if "project-doc" not in {row["code"] for row in project_doc_findings(missing_project_doc)}:
        failures.append("detector missed project-document drift")
    leaked = {row["code"] for row in public_metadata_findings({"fixture": "TA" "VA report for nS" "pect program NSP" "ECT-TEST-ID"})}
    if leaked != {"internal-review-name", "internal-program-id"}:
        failures.append(f"public metadata detector missed internal workflow language: {sorted(leaked)}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--observed-contract", action="store_true", help="print the production topology derived from repository sources")
    args = parser.parse_args()
    if args.observed_contract:
        print(json.dumps(observe_system(), indent=2))
        return 0
    if args.self_test:
        failures = self_test()
        if failures:
            for detail in failures:
                print(f"FAIL {detail}")
            return 1
        print("security_architecture_audit self-test: PASS")
        return 0
    findings = audit()
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, indent=2))
    else:
        for row in findings:
            print(f"FAIL [{row['code']}] {row['path']}: {row['detail']}")
        print(f"security_architecture_audit: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
