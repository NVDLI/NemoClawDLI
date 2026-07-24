#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Vendor the framework READMEs the Module 4b "weigh the harnesses" artifact grounds on.

The Try-it should weigh the five CLI agents from their real docs, not from the model's
guesses. This fetches each framework's README to a static asset the browser cell loads, and
pulls a short grounding extract per framework into an index the system prompt is built from.
OpenClaw has no public repo, so its entry is authored here from the course's own description.

Pages-safe: assets are static and same-origin; the cell never calls GitHub at runtime.

Usage:
    python3 scripts/materials/build_cli_readmes.py            # refresh the vendored READMEs + index
    python3 scripts/materials/build_cli_readmes.py --check     # verify the index covers every framework
"""
import sys, json, re, urllib.request
from datetime import date
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

ASSETS = Path(__file__).resolve().parent.parent / "web" / "nemoclaw" / "assets"
CAP = 12000   # cap each README so a full multi-README injection stays a sane prompt size

FRAMEWORKS = [
    {"id": "claude-code", "name": "Claude Code",
     "url": "https://raw.githubusercontent.com/anthropics/claude-code/main/README.md",
     "note": "Anthropic. Beacon CLAUDE.md."},
    {"id": "codex", "name": "Codex CLI",
     "url": "https://raw.githubusercontent.com/openai/codex/main/README.md",
     "note": "OpenAI. Beacon AGENTS.md."},
    {"id": "cursor", "name": "Cursor",
     "url": None,
     "note": "Closed-source editor agent. No public repo; described from the course."},
    {"id": "hermes", "name": "Hermes",
     "url": "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/README.md",
     "note": "Nous Research. Self-modification and a messaging gateway turned on."},
    {"id": "openclaw", "name": "OpenClaw", "url": None,
     "note": "In NVIDIA NemoClaw. No public repo; described from the course."},
]

OPENCLAW_DOC = """# OpenClaw (in NVIDIA NemoClaw)

OpenClaw is the agent runtime this course drives. It runs a model in a loop with tools, the
same application shape as the other CLI agents, with a few defaults turned up for unattended,
long-running operation.

- **Beacon.** Its configuration is the whole `workspace/` folder, not a single file: SOUL.md
  (persona), AGENTS.md, IDENTITY.md, MEMORY.md, skills, and cron definitions. The runtime folds
  these into the system prompt every turn.
- **Admin plane.** A JSON-RPC gateway at `/cli/gateway` exposes identity, config, crons, files,
  and chat. The same surface the Control UI uses, reachable programmatically.
- **Containment.** In NemoClaw it runs inside the kernel-level OpenShell sandbox (netns,
  Landlock, seccomp, and an OPA-evaluated egress proxy), so its tool palette is gated by policy
  regardless of what the model decides.
- **Built for unattended operation.** Cron and heartbeat triggers, persistent memory, and a
  fleet/sub-agent shape are first-class, so it is shaped for agents that run with nobody watching.

Self-modification is available the same way it is to any agent that can edit files: an OpenClaw
agent can rewrite its own SOUL.md or add a skill. Containment is what bounds the blast radius of
that, not the absence of the capability.
"""

CURSOR_DOC = """# Cursor (editor-resident agent)

Cursor is a closed-source AI code editor with a built-in agent. It has no public repository, so
this description stands in for a README.

- **Beacon.** Project rules live in `.cursor/rules/*.mdc`; the agent reads them as standing
  instructions, the role CLAUDE.md or AGENTS.md play for the terminal CLIs.
- **Palette.** The agent runs through the editor, so its moves are editor-shaped: propose and
  apply a diff to a file, run a command in the integrated terminal, search the workspace.
- **Sandbox.** Whatever your editor and operating system already grant. There is no separate
  kernel policy, so the agent acts with your user's reach unless you constrain it yourself.
- **Shape.** The same model-in-a-loop-with-tools as the others, defaulted toward interactive,
  in-editor work with a human watching rather than unattended runs.
"""

AUTHORED = {"openclaw": OPENCLAW_DOC, "cursor": CURSOR_DOC}   # frameworks with no public repo


def first_prose(md):
    """A short grounding extract: the first real prose, badges / headings / link-ref defs / images
    skipped and inline HTML stripped, so the system prompt gets a clean grounded sentence."""
    para = []
    for ln in md.splitlines():
        s = ln.strip()
        if not s:
            if para:
                break
            continue
        if re.match(r"^(#|!\[|\[!\[|\||>|-{3,}|={3,}|```)", s):  # heading / image / table / rule / fence
            continue
        if re.match(r"^\[[^\]]+\]:\s", s):                        # markdown link-reference definition
            continue
        t = re.sub(r"<[^>]+>", " ", s)                            # strip inline HTML tags
        t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)          # md links/images -> their label
        t = re.sub(r"[*`_]", "", t).strip()
        if not t or len(re.sub(r"https?://\S+", "", t).strip()) < 8:  # skip badge/url-only lines
            continue
        if " | " in t:                                           # nav / table-row line, not prose
            continue
        if not para and (len(t) < 25 or " " not in t.rstrip(".")):  # a bare title line, not a sentence
            continue
        if t.startswith(("- ", "* ", "1.")) and not para:
            continue
        para.append(t)
        if len(" ".join(para)) >= 220:
            break
    text = re.sub(r"\s+", " ", " ".join(para)).strip()
    return (text[:400] + ("…" if len(text) > 400 else "")) or "(no prose summary found)"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "nemoclaw-course-build"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def build():
    index = {"generated": date.today().isoformat(), "frameworks": []}
    for fw in FRAMEWORKS:
        md = AUTHORED[fw["id"]] if fw["url"] is None else fetch(fw["url"])
        if len(md) > CAP:
            md = md[:CAP] + "\n\n…(README truncated for the course; see the source link for the full text)\n"
        (ASSETS / f"cli_readme_{fw['id']}.txt").write_text(md)
        index["frameworks"].append({
            "id": fw["id"], "name": fw["name"], "note": fw["note"],
            "source": fw["url"] or "course-authored (no public repo)",
            "bytes": len(md), "extract": first_prose(md),
        })
        print(f"  {fw['id']:16} {len(md):6}B  {index['frameworks'][-1]['extract'][:70]}…")
    (ASSETS / "cli_readmes.json").write_text(json.dumps(index, separators=(",", ":")))
    print(f"wrote assets/cli_readmes.json + {len(FRAMEWORKS)} README assets")


def check():
    idx = ASSETS / "cli_readmes.json"
    if not idx.exists():
        print("MISSING assets/cli_readmes.json"); return 1
    d = json.loads(idx.read_text())
    have = {f["id"] for f in d.get("frameworks", [])}
    want = {fw["id"] for fw in FRAMEWORKS}
    problems = []
    if have != want:
        problems.append(f"index frameworks {sorted(have)} != expected {sorted(want)}")
    for fw in FRAMEWORKS:
        if not (ASSETS / f"cli_readme_{fw['id']}.txt").exists():
            problems.append(f"missing asset cli_readme_{fw['id']}.md")
    for p in problems:
        print("DRIFT:", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(check() if "--check" in sys.argv else (build() or 0))
