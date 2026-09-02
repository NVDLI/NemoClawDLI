#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Discover course interfaces and reconcile them with course-owned SKILL contracts.

Discovery is exhaustive inside every web course that carries interface-inventory.json. A mount
call or explicit interface marker is an instance; manifest-backed templates cover generated
instances without copying hundreds of rows. There is no path, page, or interface exemption.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from runtime.html_document import script_body_by_id  # noqa: E402

SCHEMA = "dli-interface-inventory/1"
MOUNT = re.compile(
    r"(?P<factory>(?:helpers\.)?mount[A-Z][A-Za-z0-9_]*)\s*\(\s*"
    r"(?:[\"'](?P<hash>#[A-Za-z][\w:.-]*)[\"']|"
    r"document\.getElementById\(\s*[\"'](?P<id>[A-Za-z][\w:.-]*)[\"']\s*\))"
)
ID = re.compile(r"\bid=[\"']([^\"']+)[\"']")
MARKER = re.compile(r"\bdata-dli-interface=[\"']([^\"']+)[\"']")
EMPTY_ROOT = re.compile(
    r"<(?P<tag>div|section|article|figure)\b(?P<attrs>[^>]*\bid=[\"'](?P<id>[^\"']+)[\"'][^>]*)>\s*</(?P=tag)>",
    re.I | re.S,
)
INTERFACE_ID_HINT = re.compile(
    r"(?:^|[-_])(cell|artifact|probe|map|diagram|flow|mechanism|chat|console|policy|journey|panel)(?:$|[-_])",
    re.I,
)
FORBIDDEN_KEYS = {"exclude", "excludes", "skip", "skips", "allow_missing", "allowlist", "ignore"}
ENTRY_STATES = {"ready", "blocked", "empty", "loading", "preview", "idle"}
AUTHORITY = {
    "none", "bounded-browser", "learner-secret", "learner-model", "openclaw-operator", "remote-media",
}
VALIDATION_PROFILE_SCHEMA = "reacs-form-factor/1"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _forbidden_keys(value: object, prefix: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            here = f"{prefix}.{key}" if prefix else key
            if key.lower() in FORBIDDEN_KEYS:
                out.append(here)
            out.extend(_forbidden_keys(child, here))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            out.extend(_forbidden_keys(child, f"{prefix}[{index}]"))
    return out


def _skill_meta(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    body = script_body_by_id(text, "skill-meta")
    if body is None:
        raise ValueError("SKILL.html has no skill-meta block")
    return json.loads(body)


def _validated_mount_probe(
    course: Path,
    probe: object,
    findings: list[str],
    label: str,
    audit_root: Path,
) -> dict[str, Any] | None:
    required = {"module", "export", "argument", "mode"}
    if not isinstance(probe, dict) or set(probe) != required:
        findings.append(f"{label}: mount_probe needs module, export, argument, and mode")
        return None
    module = str(probe.get("module", ""))
    export = str(probe.get("export", ""))
    argument = probe.get("argument")
    mode = str(probe.get("mode", ""))
    module_path = (course / module).resolve()
    try:
        module_path.relative_to(course.resolve())
    except ValueError:
        findings.append(f"{label}: mount_probe module escapes its course")
    else:
        if module_path.suffix not in {".js", ".mjs"} or not module_path.is_file():
            findings.append(f"{label}: mount_probe module is missing")
        elif not re.fullmatch(r"[A-Za-z_$][\w$]*", export):
            findings.append(f"{label}: mount_probe export is invalid")
        elif not isinstance(argument, dict):
            findings.append(f"{label}: mount_probe argument must be an object")
        elif mode not in {"mount-target", "return-node"}:
            findings.append(f"{label}: mount_probe mode is invalid")
        else:
            return probe
    return None


def _manifest_instances(
    course: Path, contract: dict[str, Any], findings: list[str], audit_root: Path = ROOT,
) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    for template in contract.get("instance_templates", []):
        required = {"id", "source", "kind", "form_factor", "selector"}
        if not isinstance(template, dict) or not required <= set(template):
            findings.append(f"{course.relative_to(ROOT)}: malformed instance template")
            continue
        source = course / str(template["source"])
        if not source.is_file():
            findings.append(f"{source.relative_to(ROOT)}: interface template source is missing")
            continue
        try:
            data = _load(source)
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(f"{source.relative_to(ROOT)}: cannot parse template source: {exc}")
            continue
        kind = template["kind"]
        rows: list[tuple[str, str, str]]
        if kind == "course-code-cells":
            rows = [
                (
                    str(cell.get("id")),
                    f"index.html?lesson={lesson.get('id')}",
                    f'.xblock[data-cell-id="{cell.get("id")}"]',
                )
                for lesson in data.get("lessons", [])
                for cell in lesson.get("cells", [])
                if lesson.get("id") and cell.get("type") == "code" and cell.get("id")
            ]
        elif kind == "video-entries":
            rows = [
                (
                    str(item.get("id")),
                    f"index.html?lesson={item.get('lesson_id')}",
                    f'.lesson-video[data-video-id="{item.get("id")}"]',
                )
                for item in data.get("entries", []) if item.get("id") and item.get("lesson_id")
            ]
        elif kind == "course-cell-id":
            wanted = str(template.get("value", ""))
            lesson_id = wanted.rsplit(":", 1)[0]
            present = any(
                str(cell.get("id")) == wanted
                for lesson in data.get("lessons", []) for cell in lesson.get("cells", [])
            )
            rows = [(wanted, f"index.html?lesson={lesson_id}", str(template["selector"]))] if present else []
            if not rows:
                findings.append(f"{source.relative_to(ROOT)}: template value is absent: {wanted}")
        else:
            findings.append(f"{source.relative_to(ROOT)}: unknown interface template kind: {kind}")
            continue
        identities = [identity for identity, _route, _selector in rows]
        if not identities or len(identities) != len(set(identities)):
            findings.append(f"{source.relative_to(ROOT)}: {kind} identities are empty or not unique")
            continue
        for identity, route, selector in rows:
            instance = {
                "id": f"{template['id']}:{identity}",
                "entry": (course / route).relative_to(audit_root).as_posix(),
                "selector": selector,
                "form_factor": template["form_factor"],
                "factory": f"manifest:{kind}",
            }
            if kind == "course-cell-id":
                instance["trigger_selector"] = f'.xblock[data-cell-id="{identity}"]'
                instance["deferred"] = True
                probe = template.get("mount_probe")
                if probe is not None:
                    checked = _validated_mount_probe(
                        course, probe, findings, source.relative_to(audit_root).as_posix(), audit_root,
                    )
                    if checked is not None:
                        instance["mount_probe"] = checked
            instances.append(instance)
    return instances


def _validation_profile(course: Path) -> list[str]:
    """Infer applicable validation from structure, never from a course-name list."""
    source_files = [
        path for path in course.rglob("*")
        if path.is_file() and path.suffix.lower() in {".html", ".js", ".mjs", ".py", ".json"}
    ]
    text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in source_files)
    factors: set[str] = set()
    if (course / "index.html").is_file():
        factors.add("browser-course")
    if (course / "content-bundle.json").is_file() and (course / "course.json").is_file():
        factors.add("markdown-course")
    if "mountRunCell" in text or "xblock-marker" in text:
        factors.add("editable-code-cells")
    if "loadPyodide" in text or (course / "runtime" / "wheels.lock.json").is_file():
        factors.add("pyodide-kernel")
    if re.search(r"https://integrate\.api\.nvidia\.com(?:/|[\"'])", text, re.I) or "X-BILLING-INVOKE-ORIGIN" in text:
        factors.add("remote-model-client")
    if (course / "video-supplements.json").is_file() or "<video" in text:
        factors.add("video-supplements")
    if "/cli/gateway" in text:
        factors.add("openclaw-client")
    if "mountCanvasFlow" in text or "mountDiagram" in text:
        factors.add("interactive-diagrams")
    if "run_assessment" in text:
        factors.add("assessment")
    return sorted(factors)


def _live_capabilities(course: Path) -> list[str]:
    """Infer externally exercised capabilities from code, without a course-name switch."""
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in course.rglob("*")
        if path.is_file() and path.suffix.lower() in {".html", ".js", ".mjs", ".py"}
    )
    capabilities: set[str] = set()
    if re.search(r"https://integrate\.api\.nvidia\.com(?:/|[\"'])", text, re.I) or "X-BILLING-INVOKE-ORIGIN" in text:
        capabilities.update(("model-request", "model-stream"))
    if re.search(r"/(?:v1/)?embeddings(?=[\"'`/?#\s])", text, re.I):
        capabilities.add("embedding-request")
    if "/cli/gateway" in text:
        capabilities.add("openclaw-gateway")
    if "/ws/terminal" in text:
        capabilities.add("operator-terminal")
    if "openclawChat" in text or '"chat.send"' in text:
        capabilities.add("openclaw-chat")
    if '"cron.add"' in text or '"cron.remove"' in text:
        capabilities.add("openclaw-cron")
    if "run_assessment" in text:
        capabilities.add("assessment")
    return sorted(capabilities)


def audit(root: Path = ROOT) -> tuple[list[str], list[dict[str, Any]]]:
    if not (root / "web").is_dir() and (root / "validated-source" / "web").is_dir():
        root = root / "validated-source"
    findings: list[str] = []
    instances: list[dict[str, Any]] = []
    web = root / "web"
    contracts = sorted(web.glob("*/interface-inventory.json"))
    if not contracts:
        return ["web/: no course interface inventories were discovered"], []

    for path in contracts:
        course = path.parent
        rel = path.relative_to(root)
        try:
            contract = _load(path)
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(f"{rel}: cannot parse inventory: {exc}")
            continue
        if not isinstance(contract, dict) or contract.get("schema") != SCHEMA:
            findings.append(f"{rel}: expected schema {SCHEMA}")
            continue
        if contract.get("course") != course.name:
            findings.append(f"{rel}: course name does not match directory")
        if contract.get("discovery") != {"html": "all", "mount_calls": "all", "markers": "all"}:
            findings.append(f"{rel}: discovery must remain exhaustive for HTML, mount calls, and markers")
        for key in _forbidden_keys(contract):
            findings.append(f"{rel}: opt-out vocabulary is forbidden at {key}")

        profiles = contract.get("form_factors")
        factories = contract.get("factory_profiles")
        markers = contract.get("marker_profiles")
        factory_mount_probes = contract.get("factory_mount_probes", {})
        if not isinstance(profiles, dict) or not profiles:
            findings.append(f"{rel}: form_factors must be a non-empty object")
            continue
        if not isinstance(factories, dict) or not isinstance(markers, dict) or not isinstance(factory_mount_probes, dict):
            findings.append(f"{rel}: factory_profiles, factory_mount_probes, and marker_profiles must be objects")
            continue
        checked_factory_probes: dict[str, dict[str, Any]] = {}
        for factory, probe in factory_mount_probes.items():
            if factory not in factories:
                findings.append(f"{rel}: mount probe selects undeclared factory {factory}")
                continue
            checked = _validated_mount_probe(course, probe, findings, rel.as_posix(), root)
            if checked is not None:
                checked_factory_probes[factory] = checked
        for name, profile in profiles.items():
            states = set(profile.get("states", [])) if isinstance(profile, dict) else set()
            if not states & ENTRY_STATES:
                findings.append(f"{rel}: form factor {name} needs an explicit entry state")
            if not isinstance(profile, dict) or profile.get("authority") not in AUTHORITY:
                findings.append(f"{rel}: form factor {name} has unknown authority")
            elif profile.get("authority") != "none" and "failed" not in states:
                findings.append(f"{rel}: authority-bearing form factor {name} must expose a failed state")
        for source, profile in {**factories, **markers}.items():
            if profile not in profiles:
                findings.append(f"{rel}: {source} selects unknown form factor {profile}")

        skill = course / "SKILL.html"
        try:
            meta = _skill_meta(skill)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            findings.append(f"{skill.relative_to(root)}: cannot read interface contract: {exc}")
        else:
            declared = meta.get("interface_inventory")
            if declared != {"schema": SCHEMA, "source": path.name}:
                findings.append(f"{skill.relative_to(root)}: skill-meta does not bind {path.name}")
            if path.name not in skill.read_text(encoding="utf-8"):
                findings.append(f"{skill.relative_to(root)}: human SKILL view does not link the interface inventory")
            profile = meta.get("validation_profile")
            inferred = _validation_profile(course)
            if profile != {"schema": VALIDATION_PROFILE_SCHEMA, "form_factors": inferred}:
                findings.append(
                    f"{skill.relative_to(root)}: validation profile must exactly match inferred form factors {inferred}"
                )
        if contract.get("validation_profile") != inferred:
            findings.append(f"{rel}: validation_profile must exactly match inferred form factors {inferred}")
        live = _live_capabilities(course)
        if contract.get("live_capabilities") != live:
            findings.append(f"{rel}: live_capabilities must exactly match inferred capabilities {live}")

        mount_targets: set[tuple[Path, str]] = set()
        marker_targets: set[tuple[Path, str]] = set()
        for page in sorted(course.rglob("*.html")):
            text = page.read_text(encoding="utf-8")
            ids = ID.findall(text)
            id_counts = {name: ids.count(name) for name in set(ids)}
            empty_ids = {match.group("id") for match in EMPTY_ROOT.finditer(text)}
            for match in MOUNT.finditer(text):
                factory = match.group("factory").split(".")[-1]
                selector = match.group("hash") or f"#{match.group('id')}"
                profile = factories.get(factory)
                if profile is None:
                    findings.append(f"{page.relative_to(root)}: undeclared mount factory {factory}")
                    continue
                target = selector[1:]
                if id_counts.get(target) != 1:
                    findings.append(f"{page.relative_to(root)}: {factory} target {selector} resolves {id_counts.get(target, 0)} times")
                    continue
                mount_targets.add((page, target))
                instance = {
                    "id": f"{course.name}.{page.relative_to(course).as_posix()}:{target}",
                    "entry": page.relative_to(root).as_posix(),
                    "selector": selector,
                    "form_factor": profile,
                    "factory": factory,
                }
                if target in empty_ids:
                    instance["deferred"] = True
                    if factory in checked_factory_probes:
                        instance["mount_probe"] = checked_factory_probes[factory]
                instances.append(instance)
            for marker in MARKER.finditer(text):
                marker_name = marker.group(1)
                profile = markers.get(marker_name)
                if profile is None:
                    findings.append(f"{page.relative_to(root)}: undeclared interface marker {marker_name}")
                    continue
                open_tag = text.rfind("<", 0, marker.start())
                close_tag = text.find(">", marker.end())
                tag = text[open_tag:close_tag + 1]
                target_match = re.search(r"\bid=[\"']([^\"']+)", tag)
                if not target_match or id_counts.get(target_match.group(1)) != 1:
                    findings.append(f"{page.relative_to(root)}: marker {marker_name} needs one stable id")
                    continue
                target = target_match.group(1)
                marker_targets.add((page, target))
                instances.append({
                    "id": f"{course.name}.{page.relative_to(course).as_posix()}:{target}",
                    "entry": page.relative_to(root).as_posix(),
                    "selector": f"#{target}",
                    "form_factor": profile,
                    "factory": f"marker:{marker_name}",
                })
            for empty in EMPTY_ROOT.finditer(text):
                target = empty.group("id")
                if INTERFACE_ID_HINT.search(target) and (page, target) not in mount_targets | marker_targets:
                    findings.append(f"{page.relative_to(root)}: empty interface-like root #{target} has no mount or marker")

        instances.extend(_manifest_instances(course, contract, findings, root))

    ids = [item["id"] for item in instances]
    if len(ids) != len(set(ids)):
        findings.append("interface inventory: expanded instance IDs are not unique")
    return findings, sorted(instances, key=lambda item: item["id"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    findings, instances = audit(args.root.resolve())
    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings, "instances": instances}, indent=2))
    elif findings:
        print(f"interface inventory: FAIL ({len(findings)})")
        for item in findings:
            print(f"  {item}")
    else:
        counts: dict[str, int] = {}
        for item in instances:
            counts[item["form_factor"]] = counts.get(item["form_factor"], 0) + 1
        print(f"interface inventory: OK ({len(instances)} instances, {len(counts)} form factors)")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
