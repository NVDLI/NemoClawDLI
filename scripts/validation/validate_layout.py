#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministic layout and repository-boundary validator.

Runs a FIXED battery of static checks and exits nonzero naming the exact failing
item. No agent has to "look for" the problem: a check either passes or prints the
precise path that is wrong.

Checks
  links     every page and local link discovered by the shared static projection resolves
  boundary  retired repository-owned runtime directories remain absent
  skills    every SKILL.html beacon matches its directory (delegates to skill_audit).

Usage:
  python3 validate_layout.py            # all checks, human output, exit 1 on failure
  python3 validate_layout.py --quiet    # only print failures
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths

HERE = Path(__file__).resolve()


def _find_task1(start: Path) -> Path:
    for p in [start, *start.parents]:
        if (p / "AGENTS.md").is_file():
            return p
    return start.parents[1]


TASK1 = _find_task1(HERE)
class Result:
    def __init__(self): self.failures = []; self.notes = []
    def fail(self, check, msg): self.failures.append((check, msg))
    def note(self, msg): self.notes.append(msg)
    @property
    def ok(self): return not self.failures


def check_links(res: Result, report=None):
    """Verify local links through the shared projection engine."""
    try:
        if report is None:
            add_script_paths(TASK1 / "scripts")
            import link_projection as lp
            report = lp.check(lp.Projection())
        stats = report["stats"]
        res.note(f"links: static projection checked {stats['pages']} pages and {stats['links']} links")
        blocking = stats["blocking_failures"] + stats["blocking_asset_leaks"] + stats["blocking_cross_course"]
        if blocking:
            res.fail("links", f"{blocking} ship-blocking link issue(s); run: python3 scripts/runtime/link_projection.py --check")
    except Exception as exc:
        res.fail("links", f"static projection failed: {exc}")



# -- check: course runtime asset layout ---------------------------------------
def check_course_assets(res: Result):
    """The NemoClaw course runtime has an intentional interface: pages import browser modules
    from web/nemoclaw/scripts/ and styles from web/nemoclaw/styles/. Keep this in the
    layout gate so a future script or asset migration cannot leave a source page pointing at
    the old root-level _shared.js / _style.css paths while the files live elsewhere."""
    course = TASK1 / "web" / "nemoclaw"
    if not course.is_dir():
        return
    required = [
        course / "scripts" / "_shared.js",
        course / "scripts" / "_canvas.js",
        course / "scripts" / "SKILL.html",
        course / "styles" / "_style.css",
        course / "styles" / "_lite_overlay.css",
        course / "styles" / "SKILL.html",
    ]
    for path in required:
        if not path.is_file():
            res.fail("course-assets", f"missing course runtime asset: {path.relative_to(TASK1)}")

    stale = []
    patterns = (
        'href="_style.css"',
        'from "./_shared.js"',
        "from './_shared.js'",
        'src="studio_main.js"',
    )
    for html in sorted(course.glob("*.html")):
        text = html.read_text(errors="ignore")
        for pat in patterns:
            if pat in text:
                stale.append(f"{html.relative_to(TASK1)} still contains {pat}")
    for old in sorted(course.glob("_*.js")) + sorted(course.glob("_*.css")) + [course / "studio_main.js"]:
        if old.exists():
            stale.append(f"old root-level course asset still exists: {old.relative_to(TASK1)}")
    if stale:
        res.fail("course-assets", "; ".join(stale[:8]))



def check_runtime_boundary(res: Result):
    """Retired runtime surfaces must not return to the static-course repository."""
    stale = [name for name in ("cpu", "deploy", "workspace") if (TASK1 / name).exists()]
    if stale:
        res.fail("runtime-boundary", "retired repository-owned runtime surface: " + ", ".join(stale))


def check_release_scaffold(res: Result):
    """The external-release playbook and contribution templates are release infrastructure.
    Keep them present so public mirroring does not lose intake and review guardrails."""
    required = [
        TASK1 / "docs" / "release_playbook.md",
        TASK1 / "CHANGELOG.md",
        TASK1 / ".gitlab" / "issue_templates" / "BUG_REPORT.md",
        TASK1 / ".gitlab" / "issue_templates" / "FEATURE_REQUEST.md",
        TASK1 / ".gitlab" / "issue_templates" / "COURSE_CONTENT.md",
        TASK1 / ".gitlab" / "issue_templates" / "RUNTIME_OR_DEPLOYMENT.md",
        TASK1 / ".gitlab" / "issue_templates" / "SOURCE_OR_LICENSING.md",
        TASK1 / ".gitlab" / "merge_request_templates" / "Default.md",
        TASK1 / ".github" / "ISSUE_TEMPLATE" / "config.yml",
        TASK1 / ".github" / "ISSUE_TEMPLATE" / "bug.yml",
        TASK1 / ".github" / "ISSUE_TEMPLATE" / "feature.yml",
        TASK1 / ".github" / "ISSUE_TEMPLATE" / "course-content.yml",
        TASK1 / ".github" / "ISSUE_TEMPLATE" / "runtime-deploy.yml",
        TASK1 / ".github" / "ISSUE_TEMPLATE" / "source-licensing.yml",
        TASK1 / ".github" / "PULL_REQUEST_TEMPLATE.md",
    ]
    for path in required:
        if not path.is_file():
            res.fail("release-scaffold", f"missing external-release scaffold: {path.relative_to(TASK1)}")

def check_skill_asset_coverage(res: Result):
    """Verify assets/SKILL.html and mats/SKILL.html directly link every local file they govern.
    This keeps provenance pages usable as file indexes in the deployed course and catches the
    exact regression where a SKILL page names a class of files without providing direct tabs."""
    import subprocess
    r = subprocess.run([sys.executable, str(TASK1 / "scripts" / "validation" / "skill_asset_coverage.py"), "--quiet"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        lines = [ln.strip() for ln in (r.stdout + "\n" + r.stderr).splitlines() if ln.strip()]
        for line in lines or ["skill_asset_coverage.py failed without output"]:
            res.fail("skill-asset-coverage", line)

def check_skills(res: Result):
    """Verify every SKILL.html beacon still matches its directory, by delegating to scripts/skills/skill_audit.py. A
    drifted beacon (a file listed that no longer exists, or one present but undocumented) means the
    machine-readable directory map an agent ingests first is lying; this surfaces each such mismatch."""
    import subprocess
    r = subprocess.run([sys.executable, str(TASK1 / "scripts" / "skills" / "skill_audit.py")],
                       capture_output=True, text=True)
    if r.returncode != 0:                         # skill_audit exits nonzero and prints each mismatch
        for line in r.stderr.splitlines():
            line = line.strip()
            if line and not line.startswith("skill_audit:"):   # skip its summary line, keep the per-item failures
                res.fail("skills", line)


def run(*, quiet: bool = False, link_report=None) -> Result:
    """Run the fixed battery and return its result.

    ``link_report`` lets an orchestrator reuse an exact projection it already computed. The
    standalone command leaves it unset and therefore retains the same exhaustive discovery.
    """
    res = Result()
    check_links(res, report=link_report)          # local links through the shared static projection
    check_course_assets(res)                      # course runtime scripts/styles interface
    check_runtime_boundary(res)                    # repository-owned runtime surfaces stay retired
    check_release_scaffold(res)                    # external mirror intake/review scaffolding
    check_skill_asset_coverage(res)               # asset/mat SKILL pages directly link governed files
    check_skills(res)                             # SKILL.html beacons that drifted from their directory

    if not quiet:
        for nt in res.notes:
            print(f"  · {nt}")
    if res.ok:
        if not quiet:
            print("validate_layout: ✅ all checks pass")
        return res
    print("validate_layout: ✗ FAILURES", file=sys.stderr)
    for check, msg in res.failures:
        print(f"  [{check}] {msg}", file=sys.stderr)
    return res


def main():
    """Run the standalone fixed battery and return a process exit status."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    return 0 if run(quiet=a.quiet).ok else 1


if __name__ == "__main__":
    sys.exit(main())
