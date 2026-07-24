#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build a compact, self-contained security review design package."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

for _path in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_path / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_path / "scripts"))
        break
from _bootstrap import find_repo_root


ROOT = find_repo_root(Path(__file__).resolve())
OUTPUT = ROOT / "artifacts" / "security-review" / "security-review-design.md"
PACKAGE = ROOT / "artifacts" / "security-review" / "securing-agents-dli-course-security-review.zip"
DIAGRAM = ROOT / "docs" / "security-architecture.svg"
ANALYSIS_SOURCE = ROOT / "docs" / "security-design.md"
CONTROL_SOURCE = ROOT / "docs" / "security-control-themes.json"
ARCHITECTURE_SOURCE = ROOT / "docs" / "security-architecture.json"
CANONICAL_SOURCES = (
    "RELEASE_STATUS.json",
    "docs/product-design.md",
    "docs/security-design.md",
    "docs/security-control-disposition.md",
    "docs/security-control-themes.json",
    "docs/release-test-plan.md",
    "docs/release-evidence.json",
    "docs/security-architecture.json",
)


def section_body(markdown: str, heading: str) -> str:
    """Return the body under one level-two heading."""
    marker = f"## {heading}"
    lines = markdown.splitlines()
    try:
        start = lines.index(marker) + 1
    except ValueError as exc:
        raise ValueError(f"missing section: {heading}") from exc
    end = next(
        (index for index in range(start, len(lines)) if lines[index].startswith("## ")),
        len(lines),
    )
    body = "\n".join(lines[start:end]).strip()
    if not body:
        raise ValueError(f"empty section: {heading}")
    return body


def bullets(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values]


def evidence_list(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values)


def markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def human_list(values: list[str]) -> str:
    """Render a short list as readable prose."""
    labels = [value.title() for value in values]
    if len(labels) < 2:
        return "".join(labels)
    if len(labels) == 2:
        return " and ".join(labels)
    return ", ".join(labels[:-1]) + ", and " + labels[-1]


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest."""
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: dict) -> bytes:
    """Match the architecture renderer's canonical JSON encoding."""
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def render() -> str:
    control_data = json.loads(CONTROL_SOURCE.read_text(encoding="utf-8"))
    architecture = json.loads(ARCHITECTURE_SOURCE.read_text(encoding="utf-8"))
    target = control_data["target_of_evaluation"]
    nodes = {node["id"]: node for node in architecture["nodes"]}
    enumeration = architecture["system"]["threat_enumeration"]
    architecture_digest = sha256_bytes(canonical_json_bytes(architecture))
    diagram_bytes = DIAGRAM.read_bytes()
    if f"model-sha256:{architecture_digest}".encode() not in diagram_bytes:
        raise ValueError("security architecture SVG is stale relative to its canonical JSON model")
    diagram_digest = sha256_bytes(diagram_bytes)
    objective_count = sum(len(edge["security_objectives"]) for edge in architecture["edges"])
    ownership_names = {"toe": "course-owned", "external": "external"}
    flow_rows = []
    for edge in architecture["edges"]:
        source = nodes[edge["from"]]
        destination = nodes[edge["to"]]
        ownership = (
            f'{ownership_names[source["ownership"]]} to '
            f'{ownership_names[destination["ownership"]]}'
        )
        objective_values = edge["security_objectives"]
        objectives = human_list(objective_values)
        if "confidentiality" not in objective_values:
            objective_scope = (
                f"{objectives} are the only applicable objectives. Confidentiality is explicitly "
                "Not applicable because the transferred material is public."
            )
        else:
            objective_scope = f"{objectives} apply."
        flow_rows.append(
            "- `" + markdown_cell(edge["id"]) + "` carries " + markdown_cell(edge["data"])
            + " from " + markdown_cell(source["label"]) + " to "
            + markdown_cell(destination["label"]) + " using " + markdown_cell(edge["protocol"])
            + ". It crosses the " + markdown_cell(ownership) + " boundary. " + objective_scope
        )
    invariants = section_body(
        ANALYSIS_SOURCE.read_text(encoding="utf-8"), "Threat-analysis invariants"
    )
    threat_register = section_body(
        ANALYSIS_SOURCE.read_text(encoding="utf-8"), "Threat register"
    )
    parts = [
        "# Security review design for the DLI course Securing Agents with OpenShell and NemoClaw",
        "",
        "> Generated by `python3 scripts/build/build_security_review_package.py`. Do not edit this file directly.",
        "",
        "## Document contract",
        "",
        "This supporting design is self-contained. Repository paths below are evidence labels, not required reading. Submit `security-architecture.svg` separately. Keep private identifiers, findings, scans, credentials, reviews, and approvals in the authorized system.",
        "",
        "Generated risk and mitigation labels are advisory. Reviewers must correct scope or ownership drift; external controls require operator evidence.",
        "",
        "## Submission binding",
        "",
        "The design and diagram are one evidence pair. Reports must preserve the visible model fingerprint and flow/objective register. With missing or different values, report input identity is Unknown.",
        "",
        f"- Architecture model SHA-256: `{architecture_digest}`",
        f"- Diagram SHA-256: `{diagram_digest}`",
        f"- Declared flows: {len(architecture['edges'])}",
        f"- Applicable security objectives: {objective_count}",
        "",
        "## Target of Evaluation",
        "",
        "The Target of Evaluation contains only:",
        "",
        *bullets(target["owned"]),
        "",
        "The following are external dependencies and trust-boundary participants, not course-repository components:",
        "",
        *bullets(target["external_dependencies"]),
        "",
        f"Ownership rule: {target['ownership_rule']}",
        "",
        f"Open-source classification: {target['classification_rule']}",
        "",
        "Explicit facts that generated analysis must preserve:",
        "",
        *bullets(target["explicit_facts"]),
        "",
        ("Local authoring and test paths are not production services: " + evidence_list(target["local_only"]) + ".")
        if target["local_only"] else
        "Repository-owned local production services: none. Host Python, Node.js, and Chromium are authoring and validation dependencies only.",
        "",
        "## Threat-analysis invariants",
        "",
        invariants,
        "",
        "## Threat register",
        "",
        threat_register,
        "",
        "## Architecture and sensitive data",
        "",
        "- Public path: a protected workflow builds one static artifact, a static host serves it, and the learner browser calls model and NemoClaw services directly or through a reviewed relay route.",
        "- Co-located path: a launchable pins the same course artifact, serves it from its origin, starts the external runtime, and uses the documented direct runtime route.",
        "- Browser storage: model, gateway, and access bearer credentials are JavaScript-readable values in tab-scoped `sessionStorage`; non-secret route preferences may remain in `localStorage`. Explicit save, replace, and clear actions do not make browser storage a vault.",
        "- Sensitive transfers: credentials, prompts, responses, agent commands, events, and workspace results cross HTTPS or WSS boundaries selected by the learner or hosting path.",
        "- Server-side state: the public static course deploys no repository-operated API, database, identity service, credential broker, learner profile, relay, model service, launchable, or NemoClaw runtime.",
        "- Diagram semantics: solid green nodes are Target of Evaluation components. Dashed gray nodes are external context with no live-control attestation. Edges describe integration routes and data, not verified external configuration; external-to-external internals are excluded.",
        "- Cryptography: the course implements no custom cryptographic algorithm. TLS protects transport. SHA-256 inventories provide integrity continuity but are not signatures or provenance attestations.",
        "- Retention: browser state belongs to the learner browser. Host logs and service-side prompts, outputs, runtime state, and logs belong to their external operators and require separate evidence.",
        "",
        "## Interactions and Data Flow",
        "",
        "This section is the normative and exhaustive threat-enumeration boundary. "
        + enumeration["rule"],
        "",
        enumeration["route_consolidation"],
        "",
        "Apply only these objectives:",
        "",
        *bullets(enumeration["objective_rules"]),
        "",
        *flow_rows,
        "",
        "Do not create separate course threats for these excluded interactions:",
        "",
        *[
            f"- `{row['id']}`: {row['interaction']}. {row['reason']}."
            for row in enumeration["excluded_external_interactions"]
        ],
        "",
        "## Aggregate control and mitigation register",
        "Each theme covers recurring findings without copying private assessment rows into the public repository. Apply these status rules before interpreting any theme:",
        "",
        *bullets(control_data["assessment_status_rules"]),
        "",
        "## Assessment reconciliation procedure",
        *[f"{index}. {step}" for index, step in enumerate(control_data["assessment_review_steps"], 1)],
    ]
    for theme in control_data["themes"]:
        parts.extend(
            (
                "",
                f"### {theme['title']} — {theme['state']}",
                f"- Owner: {theme['owner']}",
                f"- Threat coverage: {', '.join(theme['threat_ids'])}",
                f"- Evidence-backed current control: {theme['current_control']}",
                f"- Future candidate: {theme['future_candidate']}",
                f"- Trigger: {theme['trigger']}",
                f"- Verification: {theme['verification']}",
                f"- Repository evidence: {evidence_list(theme['evidence'])}",
            )
        )
    parts.extend(
        (
            "",
            "## Release decision",
            "",
            "Repository validation covers source-tree and built-artifact controls only. Unresolved host, service, credential, signing, or scan controls remain release-blocking; human review does not substitute.",
            "",
            "Risk acceptance remains in its governing system. It records acceptance, not control implementation. The repository stores only the public-safe approval state. Protected environments require independent release authorization, and workflow provenance binds the published artifact to the reviewed source.",
        )
    )
    return "\n".join(parts).rstrip() + "\n"


def package_bytes(document: str) -> bytes:
    """Return a deterministic ZIP with exactly the document and diagram."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in (
            ("security-review-design.md", document.encode("utf-8")),
            ("security-architecture.svg", DIAGRAM.read_bytes()),
        ):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    return output.getvalue()


def display(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def self_test() -> int:
    sample = "# Example\n\n## Chosen\n\nKeep me.\n\n## Other\n\nSkip me.\n"
    assert section_body(sample, "Chosen") == "Keep me."
    assert human_list(["integrity", "availability"]) == "Integrity and Availability"
    assert human_list(["confidentiality", "integrity", "availability"]) == (
        "Confidentiality, Integrity, and Availability"
    )
    assert sha256_bytes(b"example") == "50d858e0985ecc7f60418aaf0cc5ab587f42c2570a884095a9e8ccacd0f6545c"
    assert all((ROOT / path).is_file() for path in CANONICAL_SOURCES)
    assert DIAGRAM.is_file()
    document = render()
    assert document.startswith(
        "# Security review design for the DLI course Securing Agents with OpenShell and NemoClaw\n"
    )
    assert "# NemoClaw security review design" not in document
    assert "## Aggregate control and mitigation register" in document
    assert "## Assessment reconciliation procedure" in document
    assert "a metadata-only rerender does not justify public-document churn" in document
    assert "Check each security objective, enforcement owner, architecture route, and duplicate" in document
    assert "Assign every private requirement exactly one disposition" in document
    assert "A component cannot mitigate a requirement it cannot enforce" in document
    assert "Anticipated mitigation" not in document
    assert "A future candidate is not implemented and cannot support a Mitigated status." in document
    assert "An external control without current operator evidence remains Not Mitigated." in document
    assert "Generated risk and mitigation labels are advisory" in document
    assert "human review does not substitute" in document
    assert "It records acceptance, not control implementation." in document
    assert "The repository stores only the public-safe approval state" in document
    assert "## Submission binding" in document
    assert "report input identity is Unknown" in document
    assert "- Declared flows: 8" in document
    assert "- Applicable security objectives: 19" in document
    assert "Repository paths below are evidence labels, not required reading" in document
    assert "## Threat-analysis invariants" in document
    assert "## Threat register" in document
    assert all(f"TR-{index:02d}" in document for index in range(1, 11))
    assert "Repository tests cannot certify external systems" in document
    assert "Missing, stale, self-issued, unbound, or unverifiable evidence is Unknown" in document
    assert "## Interactions and Data Flow" in document
    architecture = json.loads(ARCHITECTURE_SOURCE.read_text(encoding="utf-8"))
    control_data = json.loads(CONTROL_SOURCE.read_text(encoding="utf-8"))
    assert architecture["system"]["target_of_evaluation"] == control_data["target_of_evaluation"]["owned"]
    for edge in architecture["edges"]:
        assert f"- `{edge['id']}` carries" in document
        assert all(value.title() in document for value in edge["security_objectives"])
        if "confidentiality" not in edge["security_objectives"]:
            assert (
                "Confidentiality is explicitly Not applicable because the transferred material "
                "is public."
            ) in document
    for row in architecture["system"]["threat_enumeration"]["excluded_external_interactions"]:
        assert f"`{row['id']}`" in document
    assert "This section is the normative and exhaustive threat-enumeration boundary" in document
    assert "Primary: GitHub Pages" not in document
    assert "bearer credentials are JavaScript-readable" in document
    assert "values retained in tab-scoped `sessionStorage`" in document
    assert "published course artifact are public" in document
    assert "hold no signing key, model API credential, runtime credential" in document
    assert "Builders hold no OIDC" in document
    assert "CI does not write Git refs or repository content" in document
    assert "reviewer is a human actor, not a system component" in document
    assert "static host serves bytes" in document
    assert "protected annotated tags identify release candidates only" in document
    assert "Repository-owned local production services: none" in document
    assert "solid green nodes are Target of Evaluation components" in document
    assert "external-to-external internals are excluded" in document
    assert "No live run has proved" in document
    assert "does not assume mTLS, DPoP, zero-retention model processing" in document
    assert "### Source and CI trust — shared-verification-required" in document
    assert "### Assessment fidelity — not-verified-release-blocking" in document
    for theme in json.loads(CONTROL_SOURCE.read_text(encoding="utf-8"))["themes"]:
        assert theme["future_candidate"].startswith(("NOT IMPLEMENTED. ", "NO LIVE EVIDENCE. "))
    assert "## Part 1:" not in document
    assert len(document.splitlines()) < 300
    assert len(document.split()) < 4000
    first = package_bytes(document)
    assert first == package_bytes(render())
    with zipfile.ZipFile(io.BytesIO(first)) as archive:
        assert archive.namelist() == ["security-review-design.md", "security-architecture.svg"]
        assert archive.testzip() is None
    print("security review package generator self-test: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument(
        "--package",
        nargs="?",
        const=PACKAGE,
        type=Path,
        help=(
            "Also write a deterministic two-file ZIP "
            "(default: artifacts/security-review/securing-agents-dli-course-security-review.zip)."
        ),
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    generated = render()
    if args.check:
        if not args.out.is_file() or args.out.read_text(encoding="utf-8") != generated:
            print(f"security review design is stale: run {Path(__file__).relative_to(ROOT)}", file=sys.stderr)
            return 1
        print("security review design: current")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(generated, encoding="utf-8")
    print(f"wrote {display(args.out)}")
    if args.package:
        args.package.parent.mkdir(parents=True, exist_ok=True)
        args.package.write_bytes(package_bytes(generated))
        print(f"wrote {display(args.package)} (security-review-design.md + security-architecture.svg)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
