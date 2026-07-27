#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Auto-runnable validation cadence for the task1 bundle. This is the single CI entrypoint.

Composes the deterministic validators into one gate and writes a DURABLE static log
(the "failures-to-get" record) so an agent / CI / the DGX-spark watcher can read the
current health without a live lab:

  1. link_projection --check (ship scope)  → virtual-link failures-to-get + asset leaks
  2. validate_layout.py                     → static links, runtime boundary, SKILL beacons
  3. grounding.py                           → em-dash / ungrounded / mat-association sweep
  4. prose_variety.py                       → sentence-variety + buzz signals over the narrative
  5. reachability, foyer-release, page-audit (via link_projection)

Each suite also runs standalone for detail, e.g. `python3 scripts/validation/prose_variety.py`.

Exit 0 iff there are no SHIP-blocking link failures AND validate_layout passes. Breakage
outside the shipped surface (anything that is not the released nemoclaw course or its shared
infra) is LOGGED as advisory and never blocks the gate.

Outputs (overwritten each run, committable as "current known state"):
  docs/validation/latest.json   full machine report (blocking + advisory)
  docs/validation/latest.md     human summary

Usage:
  python3 scripts/validation/validate_bundle.py            # gate + write log
  python3 scripts/validation/validate_bundle.py --scope all  # gate on the whole tree, not just shipped (strict)
  python3 scripts/validation/validate_bundle.py --no-write   # gate only, no log file
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path


def _report_stamp(explicit: str | None) -> str:
    if explicit:
        return explicit
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is not None:
        try:
            epoch = int(raw)
        except ValueError as exc:
            raise SystemExit("SOURCE_DATE_EPOCH must be a non-negative integer") from exc
        if epoch < 0:
            raise SystemExit("SOURCE_DATE_EPOCH must be a non-negative integer")
        return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

HERE = Path(__file__).resolve()
TASK1 = find_repo_root(HERE)
SCRIPTS = TASK1 / "scripts"
add_script_paths(SCRIPTS)
import link_projection as lp  # noqa: E402
import grounding as gr  # noqa: E402

# prose_variety emits both buzz constructions and phrase-level redundancy in one example stream;
# these kinds are the redundancy half, routed to the redundancy suite (the rest are buzz cadence).
_REDUNDANT_KINDS = {"graphic-echoes-prose", "sentence-restated"}

# Per-rule fix for the grammar/composition suite.
# Every one says rewrite, never swap, because a word swap is exactly how these mistakes got introduced.
_GRAMMAR_FIX = {
    "weak-opener": "Open on the subject, not a conjunction or filler (And/But/So/Basically). Rewrite the "
                   "sentence; deleting the opener alone leaves it choppy.",
    "expletive": "Replace the weak 'There is/are…' or 'It is X that…' opener with the real subject and an active verb.",
    "wordy-phrase": "Cut the wordy phrase: 'in order to' becomes 'to', 'the fact that' drops out, 'a number of' becomes 'several'.",
    "run-on": "Break this run-on into two or three sentences, one idea each.",
    "choppy-run": "Connect these short sentences into one or two that flow; do not leave staccato fragments.",
    "filler-word": "Cut the filler word (very, really, quite, actually, basically): it adds emphasis but no information.",
    "tack-on": "Delete the hollow connector ('which is exactly', 'and that X is the…', 'it is worth noting'). Do NOT "
               "replace it with another connector; either add the real substance (the mechanism or the consequence) "
               "or end the sentence. The clause names what something 'is' instead of carrying content.",
    "and-then-chain": "A comma-welded step run ('X, and Y, then Z'); a serial comma-list plus a clause trips it too. "
                      "Split into separate sentences, or lift the steps into a list. Do NOT swap 'and' for 'or' or drop "
                      "the commas into 'a and b and c' to hide it; integrate the steps into the surrounding narrative.",
    "bare-and-chain": "Three items welded by bare 'and' ('a role label and a system prompt and a tool list'). Write it "
                      "as a proper comma-list ('a role label, a system prompt, and a tool list') or lift the items into "
                      "a <ul>. The bare-and run is the comma-list dodge in reverse and reads breathless.",
}
# Per-kind fix for the staccato suite. The reliable levers, learned the hard way: a paragraph under 5 clauses
# cannot trip uniform-breaks, lists are removed from the scan, and code/URL tokens inflate break-dense falsely.
_STACCATO_FIX = {
    "uniform-breaks": "Even, monotone clause lengths. The reliable structural fix: split the paragraph so each piece has "
                      "FEWER THAN 5 clauses, or lift a genuine enumeration into a SUBSTANTIVE <ul> (items that carry "
                      "real content, not stubs) framed by short, well-motivated sentences. One short complete sentence "
                      "among longer ones also breaks the cadence. Keep 3+ sentences between any two lists so they do not pileup.",
    "break-dense": "Short clauses welded together. Combine them into longer flowing sentences (mean clause length past "
                   "~7.5), or lift a crammed comma-list into a <ul>. If the short clauses are code/URL/filename tokens "
                   "(integrate.api.nvidia.com/v1, getConfig(), \"openai:gpt-4o\"), the prose already reads fine and the "
                   "splitter is miscounting punctuation: dismiss it.",
    "reveal-dense": "Two or more setup/payoff reveals stacked (mid-sentence colons, or 'X is the Y, a Z' comma-appositives). "
                    "Turn one into a list or fold it into plain prose. Swapping a colon for a comma does NOT clear it.",
    "colon-dense": "Two or more mid-sentence colons stacking 'setup: payoff'. Lift one into a list, or rewrite as plain prose.",
    "appositive-definition": "A copular definitional appositive ('This is the smallest X, a Y'). Rewrite as a direct "
                             "definition ('The smallest X is a Y'); the colon/comma/paragraph-split is not the issue, the "
                             "construction is, so re-punctuating or splitting will not clear it.",
}
_STRUCTURE_FIX = {
    "prose-run": "Break the run of paragraphs: pull one point into a list or a callout, lift a step sequence out, "
                 "or set a figure between them. A wall of same-shaped prose reads script-like.",
    "buried-list": "Lift the parallel colon-led clauses into a real list, with a lead-in sentence before and a "
                   "takeaway sentence after, so the enumeration is scannable.",
    "definition-dump": "Lift the term definitions into a focused list. Keep one lead sentence before the list, then one "
                       "composition/takeaway paragraph after it.",
    "list-pileup": "Two lists are stacked with almost no prose between. Merge them, convert one back to a sentence, "
                   "or put a paragraph between them so the page is not list-after-list.",
    "list-candidate": "Repeated prose structure is doing list work. Add a lead-in sentence, then lift the parallel pieces into a focused list.",
    "list-density": "Lists are packed too closely for a local edit. Refactor the surrounding section so each list has a distinct job, or merge/split the section at blast-radius scale.",
    "wall-of-text": "One paragraph is too long to read as a block. Split it into two or three, trim any over-detailed "
                    "recap, and lift an enumeration or step sequence into a list or callout.",
}
import prose_variety as pv  # noqa: E402
import code_hygiene as ch  # noqa: E402
import color_theme as ct  # noqa: E402
import figure_audit as fa  # noqa: E402
import cell_audit as ca  # noqa: E402
import learner_flow_audit as lfa  # noqa: E402
import contribution_safety_audit as csa  # noqa: E402
import sensitive_content_audit as sca  # noqa: E402
import localization_audit as la  # noqa: E402
from translate.locale_catalog import discover_locales  # noqa: E402
import helper_notebook_runtime_audit as hna  # noqa: E402
import studio_interface_audit as sia  # noqa: E402
import openclaw_fallback_audit as ofa  # noqa: E402
import agent_process_audit as apa  # noqa: E402
import course_contract as cca  # noqa: E402
import concept_order_audit as coa  # noqa: E402
import skill_contract as skc  # noqa: E402
import validate_layout as layout_validator  # noqa: E402
import course_content_contract as cc  # noqa: E402
import course_dependency_integrity as cdi  # noqa: E402
import html_structure_audit as hsa  # noqa: E402
import security_architecture_audit as saa  # noqa: E402
import threat_control_audit as tca  # noqa: E402
import release_evidence_audit as rea  # noqa: E402
import repository_work_products_audit as rwpa  # noqa: E402
from collections import defaultdict  # noqa: E402


def _git_sha() -> str:
    try:
        # Abbreviation length changes when CI fetches another ref with the same prefix. Reports
        # are reused across jobs, so bind them to the stable full object ID.
        return subprocess.run(["git", "-C", str(TASK1), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or "?"
    except Exception:
        return "?"


# ── suite provenance: every check points at the code that runs it ────────────
# Single source of truth per suite: name, tier, the sentence it enforces, and where its logic lives.
# The report shows the resolved source inline; a suite with no resolvable impl fails the gate. (id, name, tier, why, file, symbol)
SUITE_META = [
    ("links", "Links & assets", "required",
     "Every internal link, image, and asset on every page must resolve, and no page may leak a reference into another course. A dead link is the breakage students hit first, so it blocks the ship. Each entry names the page and the broken target; the fix is to repair or remove it.",
     "scripts/runtime/engine.js", "check"),
    ("cross_course", "Cross-course links", "recommended",
     "Links pointing from one course's pages into another. A course must not depend on a sibling. If a link is a deliberate see-also, keep it and dismiss the entry; otherwise inline what the page needs and drop the link.",
     "scripts/runtime/engine.js", "check"),
    ("asset_leaks", "Asset leaks", "recommended",
     "A page referencing an asset that lives in another course's tree. Copy the asset into this course or drop the reference, so each course stays self-contained.",
     "scripts/runtime/engine.js", "check"),
    ("layout", "Layout & mounts", "required",
     "Each interactive cell's mount selector, every asset path, and the per-course SKILL beacon must be present and wired. Cells mount by CSS selector at runtime, so a typo'd id renders nothing with no console error. Only a static check catches it, so a failure blocks the ship.",
     "scripts/validation/validate_layout.py", "main"),
    ("grounding", "Grounding", "recommended",
     "No em-dashes (a machine-writing tell), and every load-bearing claim traces to a cited source. An em-dash means rewrite the sentence, never swap the glyph. An ungrounded claim is how confident-but-wrong material ships; cite it or add the source to mats/.",
     "scripts/validation/grounding.py", "sweep"),
    ("reachability", "Reachability", "recommended",
     "Every content page must be reachable by following links from a SKILL hub, or it is invisible to the navigation and to an agent's map of the course. Only real strays appear; fix one by linking it from the relevant hub.",
     "scripts/runtime/engine.js", "reachability"),
    ("foyer", "Release foyer", "required",
     "The student-facing foyer must surface only courses marked released. Surfacing an unreleased course leaks work-in-progress, so a violation blocks the ship.",
     "scripts/runtime/engine.js", "foyerReleaseCheck"),
    ("page_audit", "Page audit", "recommended",
     "Each page is held to the shared HTML contract: no stale tokens, no missing assets, no deploy course-code leaking into content. Each entry names the drifted token or asset to fix.",
     "scripts/runtime/engine.js", "pageAudit"),
    ("html_structure", "HTML structure", "required",
     "Canonical and localized learner pages must not contain nested anchors. Browsers repair that invalid structure by closing the outer link early, which splits cards and leaks their prose into the surrounding layout.",
     "scripts/validation/html_structure_audit.py", "audit"),
    ("release_evidence", "Product design and release test plan", "required",
     "The public product design, executable test plan, and machine-readable evidence map must cover the shipped static system, data and cryptography inventories, source and dependency controls, external-review ownership, release artifacts, and rollback without embedding private workflow metadata or claiming approval.",
     "scripts/validation/release_evidence_audit.py", "audit_contract"),
    ("repository_work_products", "Repository work products", "required",
     "Public repository work products must match their reviewed requirement and applicability levels. Required files, resolved evidence paths, policy content, issue intake, maintainer procedures, and validator wiring must remain complete.",
     "scripts/validation/repository_work_products_audit.py", "audit_contract"),
    ("course_content", "Course content contract", "required",
     "Course promises that generic validators cannot infer: retrieval and safety figures keep their teaching contracts, product comparisons cite public sources, automation semantics stay scoped to the demonstrated configuration, and alpha platform claims retain availability and hardware qualifiers. Each finding names the missing contract piece.",
     "scripts/validation/course_content_contract.py", "run"),
    ("course_dependency_integrity", "Course dependency integrity", "required",
     "Fixed third-party browser assets execute inside every learner page. Their URLs, expected bytes, and CORS mode must stay pinned with Subresource Integrity so an upstream response change cannot silently execute in the course.",
     "scripts/validation/course_dependency_integrity.py", "audit"),
    ("localization", "Localization integrity", "required",
     "Same-branch language overlays contain localized HTML only, retain canonical document and executable structure, share standalone runtime/assets and SKILL contracts, use locale-native terminology, and expose source drift before a translated page is published.",
     "scripts/validation/localization_audit.py", "scan"),
    ("prose_variety", "Prose rhythm", "consider",
     "Sentence-length spread, staccato triads, and over-enumeration, ranked. Monotone cadence is a machine-writing tell. This is a judgment call: the flagged pages are the ones to give a human rhythm pass if you agree.",
     "scripts/validation/prose_variety.py", "sweep"),
    ("prose_buzz", "Buzz cadence", "recommended",
     "Mirrored 'A is B; C is D', 'one X, many Y', 'a slice, not the whole', a sentence carrying two or more semicolons, and 'again and again' doubling, with the exact sentence to rewrite. These carry little information and read as marketing copy. Rewrite the sentence in plain prose; do not just swap the words.",
     "scripts/validation/prose_variety.py", "antithesis_hits"),
    ("redundancy", "Redundancy", "recommended",
     "Phrase-level repetition that pads the page: a figure whose label or caption restates the prose beside it (so the diagram adds nothing), or one sentence restating another. Measured as bag-of-words containment, so a near-duplicate with minor wording changes still surfaces. Cut the duplicate or differentiate it.",
     "scripts/validation/prose_variety.py", "redundancy"),
    ("grammar", "Grammar & composition", "recommended",
     "Plain rules-of-school mistakes that creep in when prose is patched to clear a metric instead of rewritten: a sentence opening on a conjunction or filler (And/But/So/Basically), a weak 'There is/are…' expletive, wordy phrases ('in order to', 'the fact that'), run-on sentences, choppy runs of very short sentences, filler words ('very', 'really', 'actually'), hollow expansionary tack-ons ('which is exactly', 'and that X is the…'), comma-welded 'X, and Y, then Z' step-chains, and bare-and item chains ('a X and a Y and a Z', the comma-list dodge in reverse). Each is a rewrite candidate, not a word swap; the tack-on, and-then-chain, and bare-and-chain entries carry the integration recipe so the fix is a narrative rewrite, not a glyph swap.",
     "scripts/validation/prose_variety.py", "grammar_hits"),
    ("comma_weight", "Comma weight", "consider",
     "A comma-bounded clause that splits a sentence's subject from its verb ('the fan-out you see, and the fresh context each sub-agent gets, is the mitigation'): hard to parse. A raw comma count is not used (a clean list has many commas and reads fine). Judgment call: a short appositive can be fine; lighten the ones that read heavy by splitting the sentence or moving the aside.",
     "scripts/validation/prose_variety.py", "comma_interruptions"),
    ("word_echo", "Word echo", "consider",
     "A content word repeated within five words of itself, no 'and/or' between (so not a deliberate parallel): a clumsy close echo that reads better lightened ('many patterns that leverage ideas from both patterns'). Judgment call: a technical term repeated on purpose is fine, so vary the wording only where it genuinely reads heavy.",
     "scripts/validation/prose_variety.py", "close_repeats"),
    ("assertions", "Bare assertions", "recommended",
     "Short 'X is a Y' copular assertions with no emphasis. A crisp definition is good but it is OVERUSED here, so it stops landing: each should be rare, bolded, and DEFENDED (a following sentence that says why it holds), or else cut. Each entry is a bare, undefended assertion to thin out, emphasize and justify, or remove. 'An agent is a loop.' is fine ONCE, bolded and explained; forty unbolded ones are wallpaper.",
     "scripts/validation/prose_variety.py", "bare_assertions"),
    ("headings", "Headings", "recommended",
     "Buzz parsed in HEADINGS, judged as their own class: a mirrored or numeric heading ('Five agents, one application layer', 'N X, one Y', 'A is B; C is D') is a marketing tell at the top of a section. Treat it as blast radius: a buzzy heading usually means the section it governs needs the same rewrite pass, so the fix is the heading AND a look at the body under it.",
     "scripts/validation/prose_variety.py", "nonprose_buzz"),
    ("structure", "Structural rhythm", "recommended",
     "Block-level monotony a sentence metric cannot see: prose runs, buried enumerations, repeated short subsection shapes that may want a focused list, and list clusters that are too close. Code and reference cards are excluded. Break the run, lift the buried list out, add a segued-into list where structure repeats, or refactor dense list clusters at section scale.",
     "scripts/validation/prose_variety.py", "structure_findings"),
    ("branding", "Brand naming", "recommended",
     "Product and brand names must use canonical casing in PROSE: NVIDIA, NemoClaw, OpenClaw, OpenShell, Nemotron. Code, URLs, paths, model-ids, and the lowercase CLI names (openshell, openclaw) are excluded, so only a real prose miscasing flags. Mostly a regression guard: it locks brand casing so future drift cannot ship.",
     "scripts/validation/prose_variety.py", "branding_hits"),
    ("defer_copula", "Deferred copula", "consider",
     "A sentence that defers its verb behind a copular abstraction: 'X is what lets Y' for 'X lets Y', 'that is what keeps ...', 'what an always-on agent is for'. The layer reads heavier than the direct statement and recurs as a machine tic across the course. Lead with the verb and the layer disappears.",
     "scripts/validation/prose_variety.py", "defer_copula"),
    ("dense_repeats", "Dense repetition", "consider",
     "One content word said three or more times in a single sentence: the sentence is circling one actor because it is doing too much ('each sub-agent is a brand-new agent invocation ... the sub-agent's context window'). Split it and the echo dissolves. Stronger than word-echo, which only sees a within-five-words pair.",
     "scripts/validation/prose_variety.py", "dense_repeats"),
    ("over_verbage", "Over-verbage", "consider",
     "A sentence overloading one breath: a clause-pile (30+ words welded with 3+ commas), a subordinator-chain (2+ of which/because/so-that/while), or a heavy parenthetical gloss it could fold in or drop. This is density, not raw length (the run-on rule caps length separately). Split it, or cut the aside.",
     "scripts/validation/prose_variety.py", "over_verbage"),
    ("padding", "Padding", "consider",
     "Emphasis or hedge phrases that add no information ('exactly', 'right here', 'on your own terms', 'under the hood', 'in plain view', 'outright'). Cut the phrase and the sentence is unchanged in meaning.",
     "scripts/validation/prose_variety.py", "padding_phrases"),
    ("code_comments", "Code comments", "consider",
     "Comment formatting across all our code (Python, JS, and the student-facing cells), held to a modern bar: a block comment over three lines, a comment that breaks a sentence mid-clause instead of at a period or colon (semantic line breaks), a trailing colon that opens no list or code, an inline comment that runs long, or extra spaces after an inline marker. Each entry names the file, line, and rule.",
     "scripts/validation/code_hygiene.py", "comment_findings"),
    ("code_walls", "Code walls", "consider",
     "Code that never stops to breathe: a run of 30+ source lines (16 in a teaching cell) with no blank line, or the same statement repeated line after line where a loop or a table belongs. A wall reads as one undifferentiated lump; the repeat means the intent is copied per case instead of stated once.",
     "scripts/validation/code_hygiene.py", "wall_findings"),
    ("code_dup", "Code duplication", "recommended",
     "Three faces of copy-paste: a block of code near-identical to another (normalized so renamed strings and numbers still match), the same interface defined in two files (a fix that must land twice), and a function that only forwards its arguments to another. Extract a shared helper, or note why the duplication is deliberate teaching.",
     "scripts/validation/code_hygiene.py", "duplication_findings"),
    ("code_size", "File size & comment density", "consider",
     "A source file past its line budget (split it along a seam), or a real file whose comment density sits outside a healthy band (over-documented, where names should carry the meaning; or a substantial file with almost no why-comments). Teaching cells are exempt from density, since they are taught, not just shipped.",
     "scripts/validation/code_hygiene.py", "size_findings"),
    ("code_const", "Hard-coded constants", "consider",
     "A value baked into the logic instead of surfaced as a named constant: the same magic number used three or more times, or a URL hard-coded where a config value belongs. Name it once so a change lands in one place, not hunted through the code.",
     "scripts/validation/code_hygiene.py", "constant_findings"),
    ("code_prose", "Prose tells in code", "recommended",
     "An em-dash anywhere in our code (a comment, a string, or UI copy a user reads) is an AI tell, as is self-congratulatory phrasing inside a user-facing string. Rewrite the whole phrase so no dash is needed; never swap the glyph for a colon, comma, or hyphen in place.",
     "scripts/validation/code_hygiene.py", "prose_findings"),
    ("hollow_intro", "Scaffolding openers", "consider",
     "A sentence that opens on scaffolding rather than content ('This page does X', 'Below, you...', 'Notice that...', 'In other words...'). The frame is usually cuttable; the clause after it carries the meaning. Course prose leans on these to stitch sections, so they accumulate.",
     "scripts/validation/prose_variety.py", "hollow_intro"),
    ("repeated_phrase", "Phrase repetition", "consider",
     "A three-word content phrase that recurs across the page (beyond word-echo's within-five-words pair): a crutch phrase a reader notices on the second pass. Vary or cut the second use. A deliberately repeated term of art is fine; judgment call.",
     "scripts/validation/prose_variety.py", "repeated_phrase"),
    ("vacuous_meta", "Vacuous meta-writing", "recommended",
     "Filler that comments on the course or the idea instead of conveying it ('where the real engineering lives', 'the shape this course chose', 'Don't X; do Y', 'first-class part', 'peer runtime'). It reads as marketing and carries no information. Cut the sentence, or replace it with the concrete fact.",
     "scripts/validation/prose_variety.py", "vacuous_meta"),
    ("staccato_cadence", "Staccato cadence", "consider",
     "Prose that reads choppy even when sentence lengths vary: a copular 'X is the Y, a Z' appositive, two-plus setup/payoff reveals (mid-sentence colons or comma-appositives), short clauses welded dense, or breaks spaced so evenly the cadence turns mechanical. The sentence-length rhythm score is blind to it. Resolution per kind: a paragraph under 5 clauses cannot trip uniform-breaks (split it), lists are removed from the scan (lift a real enumeration into a substantive <ul>), combine choppy clauses for break-dense, and dismiss break-dense that is only code/URL tokens. Each finding carries its specific recipe.",
     "scripts/validation/prose_variety.py", "staccato_cadence"),
    ("color_theme", "Color theme", "required",
     "Every DOM color must be theme-dynamic: no hard-coded literal in an inline style, no undefined CSS variable. An inline literal outranks the light-theme rules and stays dark in light mode. Each entry names the literal and the page; replace it with a theme var.",
     "scripts/validation/color_theme.py", "run"),
    ("figure_audit", "Figure audit", "required",
     "Every attributed SVG must have a provenance-derived rendering mode. Theme-aware figures must follow the course toggle; fixed-white conversions must remain on an explicit paper surface. The same audit checks legibility, bounds, accessibility, and mobile zoom without filename exemptions.",
     "scripts/validation/figure_audit.py", "run"),
    ("security_architecture", "Security architecture graph", "required",
     "The release threat-model graph must match source-derived CI and browser topology, reject repository-owned runtime services, source every production node and flow from repository evidence, label trust-boundary authentication and sensitive data, exclude internal workflow metadata, avoid node and connector collisions, and keep its generated SVG projection current.",
     "scripts/validation/security_architecture_audit.py", "audit"),
    ("threat_controls", "Threat control disposition", "required",
     "Repository-owned mitigations must remain automated while host, provider, residual, and non-applicable requirements stay explicit. Pages artifacts are bounded, safely extracted, deployed without rebuilding, verified byte-for-byte after publication, and reconciled across public GitHub and internal GitLab without force updates.",
     "scripts/validation/threat_control_audit.py", "audit"),
    ("cell_audit", "Cell & artifact contract", "recommended",

     "Every runnable cell shows its work in the panel, writes via helpers.log not console, awaits its model calls, inlines no key, keeps cell-only code in an editable cell, is syntax-highlighted by default, and keeps default-visible code and canvas copy readable. A hard-coded key is required-tier (it ships to every student); the rest are recommended.",

     "scripts/validation/cell_audit.py", "run"),
    ("learner_flow", "Learner interaction flow", "required",
     "Learner-facing implementation uses progressive disclosure; prerequisite state appears before launchable input; Run, Stop, Reset, error, and completion states stay visible and cancellable without moving the page viewport; the course explains how model endpoints support local reproduction without learner-managed GPU hardware.",
     "scripts/validation/learner_flow_audit.py", "audit_tree"),
    ("contribution_safety", "Contribution safety", "required",
     "Ideas remain easy to submit while code, merge, deploy, and release authority stay separated. Templates expose evidence and ownership; hooks refuse without mutating; pull-request CI is read-only; required checks and protected environments gate writes.",
     "scripts/validation/contribution_safety_audit.py", "audit_repo"),
    ("sensitive_content", "Sensitive content boundary", "required",
     "Repository files, staged bytes, proposed Git trees, commit additions, and host-supplied submission metadata must not publish security-finding identifiers, exploit-specific notes, private service locations, ephemeral infrastructure identifiers such as a provisioned launchable instance, corporate personal contacts, or concrete credentials. Private active-finding phrases are represented only by reviewed fingerprints.",
     "scripts/validation/sensitive_content_audit.py", "audit"),
    ("helper_notebook", "Helper notebook contract", "required",
     "The runnable helper notebook must use the helper API exposed by its actual runtime surface. Static examples must not mix CanvasFlow-only and RunCell-only log helpers, because that ships a TypeError directly to students.",
     "scripts/validation/helper_notebook_runtime_audit.py", "static_audit"),
    ("studio_interface", "Studio interface contract", "required",
     "Studio is the operator console for authoring and validation. Its controls must remain reachable at layout extremes, its sidebar lists must scroll internally, and its documented test commands must stay synchronized with the validators.",
     "scripts/validation/studio_interface_audit.py", "audit"),
    ("openclaw_fallback", "OpenClaw fallback and probe lifecycle contract", "required",
     "Credentialed OpenClaw tests must fail fast when the runtime is unreachable, the kickstart path must point learners to the Brev backup, and an HTML probe response must disappear before later JSON, error, or access-warning output.",
     "scripts/validation/openclaw_fallback_audit.py", "audit"),
    ("agent_process", "Agent process contract", "required",
     "Issue/MR, taxonomy, validation, and safe-auth guardrails must be discoverable from the repo beacons so broad agent work starts from a durable process instead of ad hoc transcript memory.",
     "scripts/validation/agent_process_audit.py", "audit"),
    ("course_contract", "Course title and abstract contract", "required",
     "The English source-course title, abstract, and learning objectives are canonical DLI copy. They must stay verbatim across the course home, foyer, and canonical contract files.",
     "scripts/validation/course_contract.py", "audit"),
    ("concept_order", "Concept order contract", "required",
     "Core vocabulary in the early agent curriculum must be defined before learner-facing prose or code relies on it. This prevents glossary-hover patches and keeps prerequisite fixes structural.",
     "scripts/validation/concept_order_audit.py", "audit"),
    ("skill_schema", "SKILL contract", "required",
     "Every SKILL.html skill-meta must be a well-formed contract of its kind: it classifies into one known kind (service-skill, service-index, dir-skill, hub, leaf), carries that kind's required keys, uses a known schema/node_type value and a semver version where the kind has one, and only valid notebook status values. An agent samples this block to work in a directory, so a malformed beacon is a contract an agent cannot trust. Each entry names the SKILL and the missing or invalid field.",
     "scripts/skills/skill_contract.py", "schema_findings"),
    ("skill_drift", "SKILL coverage and drift", "required",
     "Every tracked or proposed source directory and ancestor must contain SKILL.html, with no exemption mechanism. Each beacon must match its directory: source_dir / human_landing point at the real location, the notebook list is complete, and hub children exist on disk. Drift means the brain describes a directory it no longer reflects. python3 scripts/skills/gen_directory_beacons.py creates missing mechanical contracts and skill_contract.py --fix repairs metadata drift.",
     "scripts/skills/skill_contract.py", "run"),
    ("skill_renderer", "SKILL renderer", "required",
     "Every SKILL.html must provide meaningful human-readable content, resolve its local renderer assets, load the shared explorer it declares, and expose only configured source files that exist. Browser runtime validation then loads every beacon and rejects page errors, missing renderer resources, unmounted explorers, and unreadable file entries.",
     "scripts/skills/skill_contract.py", "renderer_findings"),
    ("diagram_geom", "Figure geometry", "recommended",
     "mountDiagram and the policy map are drawn by JavaScript at runtime, so the static figure audit never sees them. This renders each and flags overlapping text, text past the bounds, a connector crossing a box it does not link, and a relational diagram that draws no edges.",
     "scripts/figures/check_figures.mjs", "svgProblems"),
    ("materials", "Materials", "recommended",
     "Each vendored web source is recorded with its tier and last-fetch status. The course cites live external material; an unreachable source is surfaced with the one-line re-pull fix.",
     "scripts/materials/pull_materials.py", "main"),
]


def _span(lines: list[str], symbol: str, lang: str):
    """Locate a symbol's source span as [start, end] 1-based inclusive, language-aware.
    Returns None if not found, so the gate can flag the impl as unresolvable."""
    import re
    if not symbol:
        return None
    if lang == "py":
        import ast
        try:
            tree = ast.parse("\n".join(lines))
        except SyntaxError:
            return None
        matches = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol
        ]
        if matches:
            node = min(matches, key=lambda item: item.lineno)
            return [node.lineno, getattr(node, "end_lineno", node.lineno)]
        return None
    if lang in ("js", "mjs"):
        pat = re.compile(r"\bfunction\s+" + re.escape(symbol) + r"\b|\b"
                         + re.escape(symbol) + r"\s*[:=]\s*function\b")
        for i, ln in enumerate(lines):
            if not pat.search(ln):
                continue
            depth, started = 0, False
            for j in range(i, len(lines)):
                for ch in lines[j]:
                    if ch == "{":
                        depth += 1
                        started = True
                    elif ch == "}":
                        depth -= 1
                if started and depth <= 0:
                    return [i + 1, j + 1]
            return [i + 1, min(i + 80, len(lines))]
        return None
    if lang == "sh":
        pat = re.compile(r"^\s*(?:function\s+)?" + re.escape(symbol) + r"\s*\(\s*\)")
        for i, ln in enumerate(lines):
            if pat.search(ln):
                return [i + 1, min(i + 60, len(lines))]
        return None
    return None


def _resolve_impl(file_rel: str, symbol: str) -> dict:
    """Resolve a (file, symbol) to {file, symbol, lines:[a,b]|None}. The file path is
    repo-relative, which is exactly how it ships beside the report on the deploy."""
    lang = {"py": "py", "js": "js", "mjs": "mjs", "sh": "sh"}.get(file_rel.rsplit(".", 1)[-1], "")
    try:
        text = (TASK1 / file_rel).read_text(encoding="utf-8")
    except Exception:
        return {"file": file_rel, "symbol": symbol, "lines": None}
    return {"file": file_rel, "symbol": symbol, "lines": _span(text.splitlines(), symbol, lang)}


def _build_suites(findings_detail: dict):
    """Resolve the suite registry against the source tree and return (suites, gaps).
    A gap (a flagged suite with no declared or resolvable impl) is an opaque check, which
    the gate treats as a required failure: observability is a contract, not a courtesy."""
    declared = {sid for sid, *_ in SUITE_META}
    suites, gaps = [], []
    for sid, name, tier, why, f, sym in SUITE_META:
        impl = _resolve_impl(f, sym)
        suites.append({"id": sid, "name": name, "tag": tier, "why": why, "impl": impl})
        if impl["lines"] is None:
            gaps.append(f"{sid}: cannot locate `{sym}` in {f} (the report cannot show this check's code)")
    for sid in list(findings_detail.keys()) + ["layout", "foyer"]:
        if sid not in declared:
            gaps.append(f"{sid}: no SUITE_META impl declared (a flagged check with no auditable source)")
    return suites, gaps


# English-prose style suites: rhythm, buzz cadence, branding, grammar, the em-dash tell. These
# encode ENGLISH writing norms (an em-dash reads as an AI tell in English, but the dash is ordinary
# punctuation in Spanish, German, French, ...). On a translation branch they would false-positive on
# correct target-language text, so a non-English run marks them "n/a" instead of running them. The
# STRUCTURAL suites (links, layout, SKILL contract, modules, figures, cells, color, materials) are
# language-agnostic and always gate, so a translation must still keep the course structurally whole.
_EN_PROSE_SUITES = ("prose_variety", "prose_buzz", "redundancy", "grammar", "structure", "headings",
                    "assertions", "word_echo", "comma_weight", "branding", "defer_copula",
                    "dense_repeats", "over_verbage", "padding", "hollow_intro", "repeated_phrase",
                    "vacuous_meta", "staccato_cadence")


def run(scope: str = "ship", write: bool = True, stamp: str | None = None, lang: str = "en") -> int:
    # lang is the human language of the content under test. "en" (the source) runs the full gate;
    # any other code (es, fr, de, ...) is a translation branch and skips the English-prose suites.
    lang = (lang or "en").lower().split("-")[0]
    lang_en = lang == "en"
    na_suites = set() if lang_en else set(_EN_PROSE_SUITES)
    proj = lp.Projection(TASK1)
    engine_bundle = lp.bundle_snapshot(proj, include_graph=write)
    rep = engine_bundle["check"]
    s = rep["stats"]

    # validate_layout (static links + retired-runtime boundary + SKILL beacons). Reuse the exact
    # projection above; spawning the standalone CLI here used to crawl every page a second time.
    vl = layout_validator.run(quiet=True, link_report=rep)
    vl_ok = vl.ok
    vl_fail = [f"[{check}] {message}" for check, message in vl.failures]
    # which suites could NOT run (crashed / skipped). A degraded suite must never read as
    # "clean": the report shows it amber so a green checkmark always means the check truly ran.
    suite_errors = {}

    try:
        reach = engine_bundle["reachability"]
    except Exception as e:
        reach = {"pages": 0, "reachable": 0, "strays": [], "real_strays": -1, "expected_strays": -1}
        suite_errors["reachability"] = str(e); vl_fail.append(f"reachability error: {e}")

    # release-foyer contract: the foyer surfaces only RELEASED courses. This is ship-blocking
    # because the foyer IS the release surface, so leaking an unreleased course onto it is a real defect.
    try:
        foyer = engine_bundle["foyer_release"]
    except Exception as e:
        foyer = {"ok": False, "released": list(lp.RELEASED), "surfaced_courses": [],
                 "violations": [{"kind": "error", "detail": str(e)}]}
        suite_errors["foyer"] = str(e); vl_fail.append(f"foyer release check error: {e}")
    foyer_ok = foyer.get("ok", False)

    # per-.html drift audit (every page auto-verifies through the engine: stale tokens, missing
    # assets, skill-meta / foyer-release contract drift). Advisory: surfaced, never ship-blocking.
    try:
        audit = engine_bundle["page_audit"]
    except Exception as e:
        audit = {"pages": 0, "pages_with_findings": -1, "findings": []}
        suite_errors["page_audit"] = str(e); vl_fail.append(f"page audit error: {e}")

    block = s["blocking_failures"] + s["blocking_asset_leaks"] + s["blocking_cross_course"]
    total = s["failures"] + s["asset_leaks"] + s["cross_course"]
    gate_block = block if scope == "ship" else total
    ok = gate_block == 0 and vl_ok and foyer_ok

    # content contracts: narrow promises the generic page/figure validators cannot infer.
    try:
        cc_find = cc.run(verbose=False)
    except Exception as e:
        cc_find = []
        suite_errors["course_content"] = str(e)
        vl_ok = False
        ok = False
        vl_fail.append(f"course content contract error: {e}")
    if cc_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"course content contract: {path}: {detail}" for path, detail in cc_find)

    cdi_scanned = 0
    try:
        cdi_find = cdi.audit()
        cdi_scanned = cdi.inventory_size()
    except Exception as e:
        cdi_find = []
        suite_errors["course_dependency_integrity"] = str(e)
        vl_fail.append(f"course dependency integrity error: {e}")
    if cdi_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"course dependency integrity: {x}" for x in cdi_find)

    try:
        html_structure_find = hsa.audit()
    except Exception as e:
        html_structure_find = []
        suite_errors["html_structure"] = str(e)
        vl_ok = False
        ok = False
        vl_fail.append(f"HTML structure audit error: {e}")
    if html_structure_find:
        vl_ok = False
        ok = False
        vl_fail.extend(
            f"HTML structure: {item['path']}:{item['line']}:{item['column']}: {item['detail']}"
            for item in html_structure_find
        )

    try:
        security_model = json.loads(saa.MODEL.read_text(encoding="utf-8"))
        security_find = saa.audit_model(security_model)
        security_scanned = len(security_model.get("nodes", [])) + len(security_model.get("edges", []))
    except Exception as e:
        security_find, security_scanned = [], 0
        suite_errors["security_architecture"] = str(e)
        vl_ok = False
        ok = False
        vl_fail.append(f"security architecture audit error: {e}")
    if security_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"security architecture: {item['path']}: {item['detail']}" for item in security_find)

    try:
        threat_control_find = tca.audit()
        threat_control_scanned = sum(len(tokens) for tokens in tca.REQUIRED_TOKENS.values())
    except Exception as e:
        threat_control_find, threat_control_scanned = [], 0
        suite_errors["threat_controls"] = str(e)
        vl_ok = False
        ok = False
        vl_fail.append(f"threat control audit error: {e}")
    if threat_control_find:
        vl_ok = False
        ok = False
        vl_fail.extend(
            f"threat control: {item['path']}: [{item['code']}] {item['detail']}"
            for item in threat_control_find
        )

    try:
        release_contract = rea.load_contract()
        release_evidence_find = rea.audit_contract(release_contract)
        release_evidence_scanned = (len(release_contract.get("documents", {}))
                                    + len(release_contract.get("evidence_areas", [])))
    except Exception as e:
        release_evidence_find, release_evidence_scanned = [], 0
        suite_errors["release_evidence"] = str(e)
        vl_ok = False
        ok = False
        vl_fail.append(f"release evidence audit error: {e}")
    if release_evidence_find:
        vl_ok = False
        ok = False
        vl_fail.extend(
            f"release evidence: {item['path']}: [{item['code']}] {item['detail']}"
            for item in release_evidence_find
        )

    try:
        work_product_contract = rwpa.load_contract()
        repository_work_products_find = rwpa.audit_contract(work_product_contract)
        repository_work_products_scanned = len(work_product_contract.get("repository_work_products", []))
    except Exception as e:
        repository_work_products_find, repository_work_products_scanned = [], 0
        suite_errors["repository_work_products"] = str(e)
        vl_ok = False
        ok = False
        vl_fail.append(f"repository work-product audit error: {e}")
    if repository_work_products_find:
        vl_ok = False
        ok = False
        vl_fail.extend(
            f"repository work products: {item['path']}: [{item['code']}] {item['detail']}"
            for item in repository_work_products_find
        )

    # grounding reference sweep (fast, no-llm). Folds the em-dash / ungrounded / cross
    # signals into the durable log so the cadence reflects content health, not just links.
    try:
        grecs = gr.sweep(None, scope, limit=None, force=False)
        gfind = gr._findings(grecs)
        ungrounded = sum(1 for fo in gfind if any("ungrounded" in i for i in fo["issues"]))
        emdash = sum(1 for fo in gfind if any("em-dash" in i for i in fo["issues"]))
        vendored_emdash = gr.vendored_em_dash(grecs)   # external snapshots: surfaced, not advisory
        mat_assoc = {r["path"]: r["reference"]["mat_assoc"]
                     for r in grecs if r.get("reference", {}).get("mat_assoc")}
    except Exception as e:                       # grounding must never silently pass the gate
        grecs, gfind, ungrounded, emdash, vendored_emdash, mat_assoc = [], [], -1, -1, [], {}
        suite_errors["grounding"] = str(e); vl_fail.append(f"grounding sweep error: {e}")

    # prose variety (deterministic, advisory): rank the authored narrative by machine-uniformity
    # (sentence-length spread, staccato triads, enumeration, welded clauses) so monotone pages surface.
    try:
        pv_rows = pv.sweep(scope)
        pv_flagged = [r for r in pv_rows if r["flagged"]]
        # Antithesis/numeric-buzz constructions are surfaced for EVERY page, not just flagged ones.
        # A single mirrored "A is B; C is D" rarely tips a page, but hiding sub-threshold instances is the blind spot that let buzzed prose pass clean.
        # Each entry carries the exact sentence to rewrite.
        pv_antithesis = [{"page": r["path"], "kind": ex["kind"], "sentence": ex["sentence"]}
                         for r in pv_rows for ex in r["metrics"].get("antithesis_examples", [])]
        pv_grammar = [{"page": r["path"], "kind": ex["kind"], "sentence": ex["sentence"]}
                      for r in pv_rows for ex in r["metrics"].get("grammar_examples", [])]
        pv_structure = [{"page": rel, "kind": k, "detail": d}
                        for f, rel in pv._pages(scope) for k, d in pv.structure_findings(f)]
        # The same buzz failure modes, parsed OUTSIDE <p>: headings (their own class, with blast
        # radius onto the section they govern), and list items / cards.
        _nonprose = [{"page": rel, **x} for f, rel in pv._pages(scope) for x in pv.nonprose_buzz(f)]
        pv_heading = [x for x in _nonprose if x["where"] == "heading"]
        pv_listcard = [x for x in _nonprose if x["where"] in ("list", "card", "canvas")]
        pv_assert = [{"page": rel, "sentence": s} for f, rel in pv._pages(scope) for s in pv.bare_assertions(f)]
        pv_echo = [{"page": rel, "word": w, "sentence": s} for f, rel in pv._pages(scope) for w, s in pv.close_repeats(f)]
        pv_comma = [{"page": rel, "sentence": s} for f, rel in pv._pages(scope) for s in pv.comma_interruptions(f)]
        pv_brand = [{"page": rel, "wrong": w, "canon": c, "sentence": ctx}
                    for f, rel in pv._pages(scope) for (w, c, ctx) in pv.branding_hits(f)]
        # Higher-scrutiny structural signals the rhythm score is blind to.
        pv_defer = [{"page": rel, "sentence": s} for f, rel in pv._pages(scope) for s in pv.defer_copula(f)]
        pv_dense = [{"page": rel, "word": w, "sentence": s} for f, rel in pv._pages(scope) for w, s in pv.dense_repeats(f)]
        pv_verbose = [{"page": rel, "kind": k, "sentence": s} for f, rel in pv._pages(scope) for k, s in pv.over_verbage(f)]
        pv_padding = [{"page": rel, "phrase": p, "sentence": s} for f, rel in pv._pages(scope) for p, s in pv.padding_phrases(f)]
        pv_hollow = [{"page": rel, "sentence": s} for f, rel in pv._pages(scope) for s in pv.hollow_intro(f)]
        pv_phrase = [{"page": rel, "phrase": p, "sentence": s} for f, rel in pv._pages(scope) for p, s in pv.repeated_phrase(f)]
        pv_meta = [{"page": rel, "phrase": p, "sentence": s} for f, rel in pv._pages(scope) for p, s in pv.vacuous_meta(f)]
        pv_staccato = [{"page": rel, "kind": k, "detail": d, "sentence": c[:160]} for f, rel in pv._pages(scope) for k, d, c in pv.staccato_cadence(f)]
    except Exception as e:
        pv_rows, pv_flagged, pv_antithesis, pv_grammar, pv_structure, pv_heading, pv_listcard, pv_assert, pv_echo, pv_comma, pv_brand = [], [], [], [], [], [], [], [], [], [], []
        pv_defer, pv_dense, pv_verbose, pv_padding, pv_hollow, pv_phrase, pv_meta, pv_staccato = [], [], [], [], [], [], [], []
        for _s in ("prose_variety", "prose_buzz", "redundancy", "grammar", "structure", "headings", "assertions", "word_echo", "comma_weight", "branding", "defer_copula", "dense_repeats", "over_verbage", "padding", "hollow_intro", "repeated_phrase", "vacuous_meta", "staccato_cadence"):
            suite_errors[_s] = str(e)
        vl_fail.append(f"prose variety error: {e}")

    # code hygiene (deterministic, advisory): repo-wide comment, wall, duplication, size, and
    # constant checks over our Python, JS, and cell code, from the separate code_hygiene module.
    _CODE_FAMS = {"code_comments": "comments", "code_walls": "walls", "code_dup": "duplication",
                  "code_size": "size", "code_const": "constants", "code_prose": "prose"}
    try:
        ch_rows = ch.scan(scope)
        ch_scanned = len({u[0] for u in ch.units(scope)})
    except Exception as e:
        ch_rows, ch_scanned = [], 0
        for _s in _CODE_FAMS:
            suite_errors[_s] = str(e)
        vl_fail.append(f"code hygiene error: {e}")
    ch_fam = defaultdict(list)
    for r in ch_rows:
        ch_fam[r.get("family")].append(r)

    # Color theme (required): inline literals, undefined vars, and render-time color bakes block.
    try:
        ct_find = ct.run(verbose=False)
        ct_inline = len(ct_find["inline"])
        ct_undef = len(ct_find["undefined_var"])
        ct_bake = len(ct_find.get("bake", []))
        ct_palette = len(ct_find.get("palette", []))
        if ct_inline + ct_undef + ct_bake + ct_palette:
            vl_ok = False
            ok = False
            vl_fail.append(
                f"color theme: {ct_inline + ct_undef + ct_bake + ct_palette} non-theme-dynamic color use(s)"
            )
    except Exception as e:
        ct_find = {"inline": [], "undefined_var": [], "bake": [], "palette": []}
        ct_inline = ct_undef = ct_bake = ct_palette = 0
        suite_errors["color_theme"] = str(e); vl_fail.append(f"color theme error: {e}")

    # figure audit (advisory): render-aware tiny text, figure-bounds overflow, missing a11y affordances.
    try:
        fa_find = fa.run(verbose=False)
        fa_total = sum(len(v) for v in fa_find.values())
    except Exception as e:
        fa_find, fa_total = {}, 0
        suite_errors["figure_audit"] = str(e); vl_fail.append(f"figure audit error: {e}")

    # cell audit (advisory): runnable-cell contract (transparency, helpers.log, awaited calls, no inline key).
    try:
        ca_find = ca.run(verbose=False)
        ca_total = sum(len(v) for v in ca_find.values())
    except Exception as e:
        ca_find, ca_total = {}, 0
        suite_errors["cell_audit"] = str(e); vl_fail.append(f"cell audit error: {e}")

    # Learner interaction flow (required): objective disclosure, readiness, lifecycle, and CPU-baseline invariants.
    try:
        learner_flow_find = lfa.audit_tree()
    except Exception as e:
        learner_flow_find = [f"learner flow audit error: {e}"]
        suite_errors["learner_flow"] = str(e)
    if learner_flow_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"learner flow: {x}" for x in learner_flow_find)

    # Contribution safety (required): intake, submission, hook, CI permission, and release boundaries.
    try:
        contribution_safety_find = csa.audit_repo()
    except Exception as e:
        contribution_safety_find = [{"code": "audit-error", "path": "repository",
                                     "message": f"contribution safety audit error: {e}",
                                     "fix": "repair contribution_safety_audit.py"}]
        suite_errors["contribution_safety"] = str(e)
    if contribution_safety_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"contribution safety: {x.get('path')}: {x.get('message')}"
                       for x in contribution_safety_find)

    # Sensitive content (required): current-tree projection of the hook and host-event boundary.
    try:
        sensitive_rows, sensitive_scanned = sca.audit()
        sensitive_find = [item.__dict__ for item in sensitive_rows]
    except Exception as e:
        sensitive_scanned = 0
        sensitive_find = [{"path": "repository", "line": 0,
                           "kind": f"sensitive content audit error: {e}"}]
        suite_errors["sensitive_content"] = str(e)
    if sensitive_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"sensitive content: {x.get('path')}:{x.get('line')}: {x.get('kind')}"
                       for x in sensitive_find)

    # Same-branch localization contract (required): every declared locale is gated.
    localization_find = []
    localization_manifest: dict[str, dict] = {}
    try:
        for spec in discover_locales(TASK1):
            locale_find, locale_manifest = la.scan(TASK1, spec.locale)
            localization_find.extend(locale_find)
            localization_manifest[spec.locale] = locale_manifest
            if write:
                la.write_manifest(TASK1, spec.profile, locale_manifest)
            else:
                # A writing run refreshes the tracked projection, so only a read-only run can
                # report that the committed manifest no longer matches its inputs.
                localization_find.extend(la.manifest_drift(TASK1, spec.profile, locale_manifest))
    except Exception as e:
        localization_find = [{"code": "audit-error", "path": "i18n",
                              "detail": f"localization audit error: {e}"}]
        suite_errors["localization"] = str(e)
    localization_by_locale = {
        locale: manifest.get("counts", {})
        for locale, manifest in localization_manifest.items()
    }
    localization_counts: dict[str, int] = {}
    for counts in localization_by_locale.values():
        for state, count in counts.items():
            localization_counts[state] = localization_counts.get(state, 0) + count
    if localization_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"localization: {x.get('path')}: {x.get('detail')}" for x in localization_find)

    # helper notebook static contract (required): no container, catches CanvasFlow / RunCell API drift.
    try:
        helper_notebook_find = hna.static_audit()
    except Exception as e:
        helper_notebook_find = [f"helper notebook audit error: {e}"]
        suite_errors["helper_notebook"] = str(e)
    if helper_notebook_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"helper notebook: {x}" for x in helper_notebook_find)

    # Studio interface static contract (required): catches control/list layout drift and docs/test command skew.
    try:
        studio_interface_find = sia.audit()
    except Exception as e:
        studio_interface_find = [f"studio interface audit error: {e}"]
        suite_errors["studio_interface"] = str(e)
    if studio_interface_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"studio interface: {x}" for x in studio_interface_find)

    # OpenClaw fallback contract (required): credentialed harness fails hard and docs point to Brev backup.
    try:
        openclaw_fallback_find = ofa.audit()
    except Exception as e:
        openclaw_fallback_find = [f"OpenClaw fallback audit error: {e}"]
        suite_errors["openclaw_fallback"] = str(e)
    if openclaw_fallback_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"OpenClaw fallback: {x}" for x in openclaw_fallback_find)

    # Agent process contract (required): keep broad-work guardrails visible from repo beacons.
    try:
        agent_process_find = apa.audit()
    except Exception as e:
        agent_process_find = [f"agent process audit error: {e}"]
        suite_errors["agent_process"] = str(e)
    if agent_process_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"agent process: {x}" for x in agent_process_find)

    # Course contract (required): canonical DLI title, abstract, and objectives are immutable.
    try:
        course_contract_find = cca.audit()
    except Exception as e:
        course_contract_find = [f"course contract audit error: {e}"]
        suite_errors["course_contract"] = str(e)
    if course_contract_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"course contract: {x}" for x in course_contract_find)

    # Concept order contract (required): key terms should be defined before first use.
    try:
        concept_order_find = coa.audit()
    except Exception as e:
        concept_order_find = [f"concept order audit error: {e}"]
        suite_errors["concept_order"] = str(e)
    if concept_order_find:
        vl_ok = False
        ok = False
        vl_fail.extend(f"concept order: {x}" for x in concept_order_find)

    # SKILL contract (required): exhaustive directory coverage, valid metadata, accurate scope,
    # and a renderer that works for the human reader are one fail-closed contract.
    try:
        skc_find = skc.run(verbose=False)
        skc_scanned = sum(1 for _ in skc.sa.skills())   # skills() is a generator, not a list
    except Exception as e:
        skc_find, skc_scanned = {"schema": [], "drift": [], "renderer": []}, 0
        suite_errors["skill_schema"] = suite_errors["skill_drift"] = suite_errors["skill_renderer"] = str(e)
        vl_fail.append(f"skill contract error: {e}")

    # figure geometry (advisory): render the runtime figures (mountDiagram + mountPolicyMap) and flag overlapping text, out-of-bounds text, stray connectors, and edgeless diagrams.
    # figure_audit handles static inline/fetched SVGs; this suite covers JS-built runtime diagrams.
    # Self-tests each detector; host Chromium via scripts/figures/run_figcheck.sh.
    dg_find = []
    try:
        dg = subprocess.run(["bash", str(SCRIPTS / "figures" / "run_figcheck.sh"), "--json"],
                            capture_output=True, text=True)
        line = [l for l in dg.stdout.splitlines() if l.strip().startswith("{")]
        if line:
            dg_find = json.loads(line[-1]).get("findings", [])
        elif dg.returncode != 0:
            suite_errors["diagram_geom"] = (dg.stderr or dg.stdout).strip()[:120] or "figure check did not run"
            vl_fail.append(f"figure check: {(dg.stderr or dg.stdout).strip()[:120]}")
    except Exception as e:
        suite_errors["diagram_geom"] = str(e); vl_fail.append(f"figure check error: {e}")

    # materials provenance (offline, advisory): read committed _materials.json so gate/CI/validator
    # show the same health. Live re-fetch is `pull_materials.py --check` (needs network).
    materials = {"count": 0, "by_tier": {}, "unreachable": [], "generated": None, "fix": ""}
    try:
        mp = TASK1 / "web" / "nemoclaw" / "mats" / "_materials.json"
        if mp.is_file():
            doc = json.loads(mp.read_text())
            materials["generated"] = doc.get("generated")
            mats = doc.get("materials", [])
            materials["count"] = len(mats)
            for m in mats:
                t = m.get("tier", "?")
                materials["by_tier"][t] = materials["by_tier"].get(t, 0) + 1
                if m.get("status") != "ok":
                    materials["unreachable"].append(
                        {"name": m.get("name"), "url": m.get("url"), "host": m.get("host"),
                         "error": (m.get("error") or "")[:160]})
            if materials["unreachable"]:
                materials["fix"] = ("re-pull with: python3 scripts/materials/pull_materials.py "
                                    "[--only blogs|papers|glossary]  (then commit)")
    except Exception as e:                       # a broken provenance file must surface, not pass
        suite_errors["materials"] = str(e); vl_fail.append(f"materials read error: {e}")

    # ── severity gradient + inline fixes ─────────────────────────────────────────
    # Three tiers, not one flat "advisory" bucket: required blocks the ship, recommended is a real defect that still ships, consider is polish.
    # Every finding carries the concrete change to make.
    REQUIRED, RECOMMENDED, CONSIDER = "required", "recommended", "consider"

    def _pg(it):
        return it[0] if isinstance(it, (list, tuple)) else it

    def D(page, detail, severity, fix):
        return {"page": page, "detail": detail, "severity": severity, "fix": fix}

    def _ground_fix(issues):
        j = " ".join(issues)
        if "em-dash" in j:
            return ("Rewrite the whole sentence so the dash was never needed. Never swap ` — ` for "
                    "`:`/`;`/`,`/`()`: the glyph swap is the failure the rule names, not the fix.")
        if "ungrounded" in j:
            return ("Cite a canonical source for the page's load-bearing claims, or add that source to "
                    "web/nemoclaw/mats/ so the claim is traceable instead of asserted.")
        return "Make every load-bearing claim on the page trace to a cited source."

    _CELL_FIX = {
        "inline_key": (REQUIRED, "Delete the hard-coded key. The cell reaches the model through the proxy; "
                       "a key in static source ships to every student and into git."),
        "opaque": (RECOMMENDED, "Show the work in the panel: helpers.log the steps, finish_reason, and usage "
                   "(or surface the raw payload) so the run is observable, not a black box."),
        "console": (RECOMMENDED, "Write with helpers.log, not console.log, so the output lands in the cell "
                    "panel where the student is looking."),
        "unawaited": (RECOMMENDED, "await the model/network call. An unawaited promise swallows errors and "
                      "races the output ordering."),
        "dialog": (RECOMMENDED, "Replace alert/confirm/prompt with in-panel output (helpers.log or a rendered "
                   "element); a modal dialog blocks the whole lab tab."),
        "static_cell_code": (RECOMMENDED, "Move the cell-only code into an editable cell so the student can read "
                             "and run it, not just watch its output appear."),
        "unhighlighted": (RECOMMENDED, "The page mounts an editable cell but does not load the syntax highlighter, so "
                          "the editor degrades to a plain textarea. Load CodeMirror core, the javascript mode, and the "
                          "editor css (codemirror.min.css + codemirror.min.js + mode/javascript/javascript.min.js) so "
                          "every editable cell is syntax-highlighted by default."),
        "ui_contract": (RECOMMENDED, "Fix the shared cell UI contract instead of hiding the finding. Helpers and code "
                        "must remain discoverable above output, code must be collapsed by default unless a cell opts in, "
                        "reset must be local, and error paths must open the code only when line-level debugging matters."),
        "code_surface": (RECOMMENDED, "Collapse plumbing-heavy canvas code with showCode:false, or split it until the "
                         "default-open cell is short enough to teach from."),
        "readability": (RECOMMENDED, "Clean the default-visible learner code. Avoid tab indentation, giant opening "
                        "comment walls, extreme nesting, and lines too long to read in the cell editor."),
        "copy_surface": (RECOMMENDED, "Shorten learner-facing canvas chrome. Let the page heading carry module "
                         "coordinates, keep labels and titles task-focused, and move implementation inventories "
                         "into the expandable code rather than a second prose layer."),
        "run_cell_style": (RECOMMENDED, "Keep the editable RunCell small and legible, return its structured "
                           "outcome, use Stop-aware waits, and provide a commented diagnostic or alternate input "
                           "where it helps a learner inspect the result."),
        "prompt_experiment": (RECOMMENDED, "Address the learner directly in prompt-input cells and provide "
                              "two commented alternative assignments or an EXAMPLES selector."),
    }
    _FIG_FIX = {
        "tiny": (RECOMMENDED, "Raise the text to a rendered font-size of at least 11px; below that it is "
                 "unreadable at the figure's display scale."),
        "small_render": (RECOMMENDED, "Raise the figure's display cap or host width so full-width course diagrams render at "
                         "least 900px wide in the lesson column."),
        "flex_parent": (RECOMMENDED, "Do not wrap fetched SVG figures in an un-sized flex container. Use a block <figure> "
                        "or give the flex parent and flex item explicit widths so the SVG cannot shrink-wrap."),
        "overflow": (RECOMMENDED, "Widen the viewBox or wrap the label onto two centered lines so it stays "
                     "inside the frame."),
        "no_aria": (RECOMMENDED, "Add an aria-label (or role=img plus a <title>) that states what the figure shows."),
        "img_no_alt": (RECOMMENDED, "Add descriptive alt text to the image."),
        "blank_link": (RECOMMENDED, "Give the link visible text or an aria-label, and rel=\"noopener\" when it "
                       "opens a new tab."),
        "dark_mode": (RECOMMENDED, "Course-authored/provided SVG images must be dark-mode friendly. Remove white "
                      "page frames, convert white SVG path fills, hook embedded raster icons to a theme filter, and "
                      "render non-conversion SVGs through fig-embed/data-svg-src so theme variables and zoom work. "
                      "Fixed-white paper conversions must be marked that way in provenance."),
        "canvas": (RECOMMENDED, "Crop excess SVG viewBox whitespace or reduce the display cap so the rendered figure "
                   "does not consume too much vertical space."),
        "crowded": (RECOMMENDED, "Do not stack figures with only token prose between them. Move the figure or add "
                    "enough explanatory context so consecutive graphics do not read as a wall."),
        "mobile_zoom": (REQUIRED, "Restore the shared mobile figure contract: visible zoom and pan cues, a 720px "
                        "readable enlarged width, horizontal panning, and reachable close/Escape behavior."),
        "theme_contract": (REQUIRED, "Restore the provenance-derived rendering contract. Every attributed SVG "
                           "must be checked as theme-aware or fixed-white; do not add a filename exemption."),
    }

    def _fig(k, t):
        sev, fix = _FIG_FIX.get(k, (RECOMMENDED, "Fix the figure legibility / accessibility issue."))
        detail = k.replace("_", " ") + (f": {t[1]}" if isinstance(t, (list, tuple)) and len(t) > 1 else "")
        return D(_pg(t), detail, sev, fix)

    def _cell(k, t):
        sev, fix = _CELL_FIX.get(k, (RECOMMENDED, "Bring the cell back to the runnable-cell contract."))
        detail = t[1] if isinstance(t, (list, tuple)) and len(t) > 1 else k
        return D(_pg(t), detail, sev, fix)

    findings_detail = {
        "links": [D(f.get("page"), (f.get("link") or f.get("url") or "") + (f" · {f.get('reason')}" if f.get("reason") else ""),
                    REQUIRED if f.get("ship") else RECOMMENDED,
                    "Repair the target or remove the link so it resolves. A dead link is the breakage students hit first.")
                  for f in rep.get("failures", [])],
        "cross_course": [D(f.get("page"), f.get("link") or "", RECOMMENDED,
                           "If this see-also is deliberate, keep it; otherwise inline what the page needs and drop the link. "
                           "build_agents must not depend on a sibling course.")
                         for f in rep.get("cross_course", [])],
        "asset_leaks": [D(f.get("page"), f.get("link") or "", REQUIRED if f.get("ship") else RECOMMENDED,
                          (f"Copy the asset into this course or drop the reference. {f.get('isolate','')}").strip())
                        for f in rep.get("asset_leaks", [])],
        "page_audit": [D(x.get("page"), "; ".join((fi.get("detail") or fi.get("token") or "") for fi in x.get("findings", [])),
                         RECOMMENDED, "Update the flagged token or restore the missing asset so the page matches the shared HTML contract.")
                       for x in audit.get("findings", [])],
        "html_structure": [D(item["path"],
                             f"line {item['line']}, column {item['column']}: {item['detail']}", REQUIRED,
                             "Replace the outer card link with a non-interactive container and give each destination its own sibling link. Never nest one anchor inside another.")
                           for item in html_structure_find],
        "security_architecture": [D(item["path"], f"[{item['code']}] {item['detail']}", REQUIRED,
                     "Review the source-derived production contract, update docs/security-architecture.json from repository evidence, regenerate the SVG, and run security_architecture_audit.py plus its mutation self-test. Keep browser paths visible and local lab services classified without drawing them as production.")
                    for item in security_find],
        "threat_controls": [D(item["path"], f"[{item['code']}] {item['detail']}", REQUIRED,
                     "Restore the bounded artifact, safe extraction, post-deploy verification, repository synchronization, or explicit external-control disposition, then run threat_control_audit.py and its mutation self-test.")
                    for item in threat_control_find],
        "release_evidence": [D(item["path"], f"[{item['code']}] {item['detail']}", REQUIRED,
                     item["fix"])
                    for item in release_evidence_find],
        "repository_work_products": [D(item["path"], f"[{item['code']}] {item['detail']}", REQUIRED,
                     item["fix"])
                    for item in repository_work_products_find],
        "course_content": [D(path, detail, REQUIRED,
                             "Restore the source-backed teaching contract. Keep retrieval/safety explanations complete, product comparisons grounded in public sources, automation behavior scoped to the demonstrated configuration, and alpha platform claims qualified.")
                           for path, detail in cc_find],
        "course_dependency_integrity": [D("web/nemoclaw", detail, REQUIRED,
                                          "Regenerate from the exact lock, review package and license changes, then restore the expected same-origin asset hash and source-reference inventory.")
                                        for detail in cdi_find],
        "helper_notebook": [D("web/nemoclaw/scripts/SKILL.html", x, REQUIRED,
                              "Use the shared helper API exposed by both runtime surfaces: log, log.h, log.json, log.kv, log.details, log.html, log.svg, log.draw, and log.clear.")
                            for x in helper_notebook_find],
        "studio_interface": [D("web/nemoclaw/studio.html", x, REQUIRED,
                               "Keep Studio controls reachable at narrow/short viewports and keep validator commands synchronized across Studio and SKILL docs.")
                             for x in studio_interface_find],
        "openclaw_fallback": [D("web/nemoclaw/03a-kickstart.html", x, REQUIRED,
                                "Keep the credentialed harness fail-fast, keep the Brev backup path explicit, and preserve the probe iframe lifecycle: hide plus clear srcdoc before every non-HTML result.")
                              for x in openclaw_fallback_find],
        "agent_process": [D("docs/agent_process.md", x, REQUIRED,
                            "Keep issue/MR, taxonomy, validation, and safe-auth guardrails documented and linked from the repo beacons.")
                          for x in agent_process_find],
        "course_contract": [D("web/nemoclaw/COURSE_CANON.md", x, REQUIRED,
                              "Restore the canonical DLI title, abstract, and learning objectives verbatim. Do not paraphrase, retitle, reorder, or translate the English source copy.")
                            for x in course_contract_find],
        "concept_order": [D("web/nemoclaw/01b-react.html", x, REQUIRED,
                            "Define the term or prerequisite before the prose or runnable code depends on it; avoid hover-only definitions.")
                          for x in concept_order_find],
        "prose_variety": [D(r["path"], f"score {r['score']} · {', '.join(r['tells'])}", CONSIDER,
                            "Give the page a rhythm pass: vary sentence length, break the staccato triads, turn enumerations back into prose.")
                          for r in pv_flagged],
        # The prose_variety example stream carries two different defects, split into two discoverable
        # suites: buzz cadence (a construction to REWRITE) and redundancy (a duplicate to CUT or
        # differentiate). Each carries the fix that matches its kind.
        "prose_buzz": [D(a["page"], f"[{a['kind']}] {a['sentence']}", RECOMMENDED,
                         "Rewrite this sentence in plain prose. The mirrored / numeric / semicolon-welded "
                         "construction carries little information and reads as marketing; do not just swap the words.")
                       for a in pv_antithesis if a["kind"] not in _REDUNDANT_KINDS]
                      + [D(a["page"], f"[{a['where']}: {a['kind']}] {a['sentence']}", RECOMMENDED,
                          "Same buzz construction, in a list item or card rather than a paragraph. Rewrite it in plain "
                          "prose; a bullet that welds a rule-of-three or mirrors two clauses should be split or recast.")
                         for a in pv_listcard],
        "comma_weight": [D(c["page"], c["sentence"], CONSIDER,
                           "A comma-bounded clause splits the subject from its verb here, which is hard to parse. "
                           "If it reads heavy, split the sentence or move the aside; a short appositive can stay.")
                         for c in pv_comma],
        "word_echo": [D(e["page"], f"“{e['word']}” repeats: {e['sentence']}", CONSIDER,
                        f"The word “{e['word']}” repeats within a few words of itself. If it reads heavy, "
                        f"lighten it: vary the second use or drop it. A technical term repeated on purpose is fine.")
                      for e in pv_echo],
        "assertions": [D(a["page"], a["sentence"], RECOMMENDED,
                         "Bare 'X is a Y' assertion. The device is overused: cut this one, or merge it into the "
                         "sentence that follows, or keep it only if you bold the term and defend it with a reason. "
                         "Aim for at most one such definition per section.")
                       for a in pv_assert],
        "headings": [D(h["page"], f"[{h['kind']}] {h['sentence']}", RECOMMENDED,
                       "Rewrite this heading in plain words; the mirrored or numeric construction (\"N X, one Y\", "
                       "\"A is B; C is D\") is a marketing tell. A buzzy heading usually means the section it governs "
                       "needs the same pass, so review and de-buzz the body under it too, not just the heading.")
                     for h in pv_heading],
        "redundancy": [D(a["page"], a["sentence"], RECOMMENDED,
                         "A figure restates the prose beside it: cut the duplicated labels, or make the figure carry "
                         "something the sentence does not (a relationship, a sequence, a value)."
                         if a["kind"] == "graphic-echoes-prose" else
                         "Two passages carry the same content in different words: merge them or cut one, so the page "
                         "does not say the same thing twice.")
                       for a in pv_antithesis if a["kind"] in _REDUNDANT_KINDS],
        "grammar": [D(g["page"], f"[{g['kind']}] {g['sentence']}", RECOMMENDED, _GRAMMAR_FIX.get(g["kind"],
                      "Rewrite the sentence so it reads the way a person would write it."))
                    for g in pv_grammar],
        "branding": [D(b["page"], f"'{b['wrong']}' should be '{b['canon']}'. Context: …{b['sentence']}…", RECOMMENDED,
                       f"Write the brand name as '{b['canon']}' in prose. Lowercase CLI names and paths are fine in code; "
                       f"this is human-facing text, so use the canonical casing.")
                     for b in pv_brand],
        "defer_copula": [D(d["page"], d["sentence"], CONSIDER,
                           "The verb is deferred behind a copula ('is what lets', 'that is what keeps', 'what X is for'). "
                           "Lead with the verb: 'X is what lets a model take the slot' becomes 'X lets a model take the slot'.")
                         for d in pv_defer],
        "dense_repeats": [D(d["page"], f"“{d['word']}” x3+: {d['sentence']}", CONSIDER,
                            "One actor named three or more times in a sentence means it is doing too much. Split it into "
                            "two or three sentences and the repetition dissolves.")
                          for d in pv_dense],
        "over_verbage": [D(v["page"], f"[{v['kind']}] {v['sentence']}", CONSIDER,
                           "The sentence overloads one breath. Split the clause-pile, unchain the subordinators, or fold "
                           "the parenthetical into the clause or drop it.")
                         for v in pv_verbose],
        "padding": [D(p["page"], f"“{p['phrase']}”: {p['sentence']}", CONSIDER,
                      "Padding that adds no information. Cut the phrase; the sentence is unchanged in meaning.")
                    for p in pv_padding],
        "code_comments": [D(f"{r['path']}:{r['line']}", f"[{r['kind']}] {r['snippet']}", CONSIDER, r["detail"])
                          for r in ch_fam["comments"]],
        "code_walls": [D(f"{r['path']}:{r['line']}", f"[{r['kind']}] {r['snippet']}", CONSIDER, r["detail"])
                       for r in ch_fam["walls"]],
        "code_dup": [D(f"{r['path']}:{r['line']}", f"[{r['kind']}] {r['snippet']}", CONSIDER, r["detail"])
                     for r in ch_fam["duplication"]],
        "code_size": [D(f"{r['path']}:{r['line']}", f"[{r['kind']}] {r['snippet']}", CONSIDER, r["detail"])
                      for r in ch_fam["size"]],
        "code_const": [D(f"{r['path']}:{r['line']}", f"[{r['kind']}] {r['snippet']}", CONSIDER, r["detail"])
                       for r in ch_fam["constants"]],
        "code_prose": [D(f"{r['path']}:{r['line']}", f"[{r['kind']}] {r['snippet']}",
                         RECOMMENDED if r["kind"] == "em-dash" else CONSIDER, r["detail"])
                       for r in ch_fam["prose"]],
        "hollow_intro": [D(h["page"], h["sentence"], CONSIDER,
                           "Opens on scaffolding, not content. Cut the frame ('This page', 'Below,', 'Notice that') and "
                           "let the clause that follows lead.")
                         for h in pv_hollow],
        "repeated_phrase": [D(p["page"], f"“{p['phrase']}” recurs: {p['sentence']}", CONSIDER,
                              "A three-word phrase used more than once on the page. Vary or cut the second use; a "
                              "deliberate term of art is fine.")
                            for p in pv_phrase],
        "vacuous_meta": [D(m["page"], f"“{m['phrase']}”: {m['sentence']}", RECOMMENDED,
                           "Vacuous meta-writing that comments on the course or idea instead of conveying it. "
                           "Cut the sentence, or replace it with the concrete fact it dances around.")
                         for m in pv_meta],
        "staccato_cadence": [D(sc["page"], f"[{sc['kind']}] {sc['detail']}: {sc['sentence']}", CONSIDER,
                              _STACCATO_FIX.get(sc["kind"], "Choppy cadence the rhythm score misses. Merge the short "
                              "clauses into flowing sentences and cut the stacked mid-sentence colons."))
                             for sc in pv_staccato],
        "structure": [D(s["page"], f"[{s['kind']}] {s['detail']}", RECOMMENDED, _STRUCTURE_FIX.get(s["kind"],
                        "Vary the block rhythm: break the run, lift the buried list, or space the stacked lists."))
                      for s in pv_structure],
        "grounding": [D(fo.get("path"), "; ".join(fo.get("issues", [])), RECOMMENDED, _ground_fix(fo.get("issues", [])))
                      for fo in gfind],
        "color_theme": ([D(f, f"{tok} on {prop}", REQUIRED,
                           f"Replace {tok} with a theme variable (var(--g), var(--e1), var(--tx), …). A literal in an "
                           f"inline style outranks the light-theme rules and stays dark in light mode.")
                         for f, tok, prop in ct_find.get("inline", [])]
                        + [D(f, f"undefined var {n}", REQUIRED,
                             f"Define {n} in :root or switch to an existing theme var. An undefined var() resolves to "
                             f"nothing, so the color silently drops out.")
                           for f, n in ct_find.get("undefined_var", [])]
                        + [D(f, "render-time color bake", REQUIRED,
                             f"{reason}. {snippet} — this output ignores the theme toggle and freezes on the "
                             f"theme that was active when it rendered.")
                           for f, snippet, reason in ct_find.get("bake", [])]
                        + [D(f, "theme palette ignores the course toggle", REQUIRED,
                             f"{reason}. Add an explicit :root[data-theme=\"light\"] palette; keep the operating-system "
                             f"media query only as the no-preference fallback.")
                           for f, reason in ct_find.get("palette", [])]),
        "figure_audit": [_fig(k, t) for k, items in fa_find.items() for t in items],
        "cell_audit": [_cell(k, t) for k, items in ca_find.items() for t in items],
        "learner_flow": [D("web/nemoclaw", x, REQUIRED,
                           "Restore the shared learner interaction contract: focus before implementation, bounded default-open code, visible prerequisite status, cancellable Run/Stop/Reset/error states, stable viewport, and an explicit model-endpoint/no-GPU baseline.")
                         for x in learner_flow_find],
        "contribution_safety": [D(x.get("path", "repository"),
                                  f"[{x.get('code', 'finding')}] {x.get('message', '')}",
                                  REQUIRED, x.get("fix", "restore the contribution trust boundary"))
                                for x in contribution_safety_find],
        "sensitive_content": [D(x.get("path", "repository"),
                                f"line {x.get('line', '?')}: {x.get('kind', 'restricted content')}",
                                REQUIRED,
                                "Move the detail to the approved private record and retain only generic controls or fingerprints in the repository.")
                              for x in sensitive_find],
        "localization": [D(x.get("path", "i18n"),
                            f"[{x.get('code', 'finding')}] {x.get('detail', '')}",
                            REQUIRED,
                            "Open web/nemoclaw/localization.html, repair the named locale prose/structure/drift issue, then accept the reviewed source hash with localization_audit.py.")
                         for x in localization_find],
        "skill_schema": [D(p, d, REQUIRED,
                           "Make the skill-meta a valid contract of its kind: add the missing required key, "
                           "correct the schema/node_type value, give version a semver MAJOR.MINOR.PATCH, or set a "
                           "valid notebook status (ready/setup/wip/ref). See SKILL_CONTRACT.md.")
                         for p, d in skc_find.get("schema", [])],
        "skill_drift": [D(p, d, REQUIRED,
                          "The source directory lacks a beacon or its beacon no longer matches. Run python3 scripts/skills/gen_directory_beacons.py "
                          "to create missing contracts, then use skill_contract.py --fix for metadata drift or repair the hub child path by hand.")
                        for p, d in skc_find.get("drift", [])],
        "skill_renderer": [D(p, d, REQUIRED,
                             "Repair the human renderer, use directory-relative assets, load the declared shared explorer exactly once, and keep every configured file resolvable.")
                           for p, d in skc_find.get("renderer", [])],
        "diagram_geom": [D(d.get("page"), f"{d.get('sel','')}: {d.get('detail','')}", RECOMMENDED,
                           "Adjust the runtime figure: keep labels from overlapping, text inside the bounds, connectors "
                           "only crossing boxes they link, and a relational diagram actually drawing its edges.")
                         for d in dg_find],
        "materials": [D(u.get("name"), u.get("error") or "unreachable", RECOMMENDED,
                        materials.get("fix") or "Re-pull the source with python3 scripts/materials/pull_materials.py, then commit.")
                      for u in materials.get("unreachable", [])],
        "reachability": [D(x.get("page"), x.get("reason", "unreachable from a SKILL hub"), RECOMMENDED,
                           "Link this page from a SKILL hub so it appears in the navigation and the agent's map of the course.")
                         for x in reach.get("strays", []) if isinstance(x, dict) and not x.get("expected")],
    }

    # Translation branch: drop the English-prose suites' findings, which score English rhythm and
    # cadence and do not transfer to the target language. The structural suites are left untouched,
    # so a translation is still fully gated on links, layout, the SKILL contract, modules, figures,
    # and cells. The em-dash signal is NOT dropped: the dash is banned repository-wide in every
    # language, and a translator reintroducing one is the case this branch used to hide.
    if not lang_en:
        for sid in na_suites:
            findings_detail[sid] = []

    # Roll the per-finding severities up into the advertised gradient.
    # Layout and foyer failures are required-tier too, but live outside findings_detail.
    gradient = {REQUIRED: 0, RECOMMENDED: 0, CONSIDER: 0}
    for grp in findings_detail.values():
        for fo in grp:
            gradient[fo["severity"]] = gradient.get(fo["severity"], 0) + 1
    # Observability contract: every flagged suite must point at code the report can show.
    # An unresolvable impl is an opaque check, treated as a layout-tier (required) failure so
    # the gate refuses to ship a validator nobody can audit from the browser.
    suites, impl_gaps = _build_suites(findings_detail)
    if impl_gaps:
        vl_fail.extend("[suite-impl] " + g for g in impl_gaps)
        vl_ok = False
        ok = False

    # ── per-suite run status: did the check actually run, and on how much? ────────
    # A crashed or zero-input suite must NOT render as a green "clean": the report colours it amber.
    # "scanned" is the coverage count, so a clean result reads as "ran on N inputs, found nothing".
    _scanned = {
        "links": s["pages"], "cross_course": s["pages"], "asset_leaks": s["pages"],
        "reachability": reach.get("pages", 0), "page_audit": audit.get("pages", 0), "course_content": 8,
        "html_structure": len(hsa.source_pages(TASK1)),
        "security_architecture": security_scanned,
        "threat_controls": threat_control_scanned,
        "release_evidence": release_evidence_scanned,
        "repository_work_products": repository_work_products_scanned,
        "sensitive_content": sensitive_scanned,
        "course_dependency_integrity": cdi_scanned,
        "grounding": len(grecs), "prose_variety": len(pv_rows), "prose_buzz": len(pv_rows), "redundancy": len(pv_rows), "grammar": len(pv_rows), "structure": len(pv_rows), "headings": len(pv_rows), "assertions": len(pv_rows), "word_echo": len(pv_rows), "comma_weight": len(pv_rows), "branding": len(pv_rows),
        "defer_copula": len(pv_rows), "dense_repeats": len(pv_rows), "over_verbage": len(pv_rows), "padding": len(pv_rows),
        "hollow_intro": len(pv_rows), "repeated_phrase": len(pv_rows), "vacuous_meta": len(pv_rows),
        "staccato_cadence": len(pv_rows),
        "code_comments": ch_scanned, "code_walls": ch_scanned, "code_dup": ch_scanned,
        "code_size": ch_scanned, "code_const": ch_scanned,
        "helper_notebook": 1,
        "studio_interface": 1,
        "course_contract": 1,
        "concept_order": 1,
        "materials": materials.get("count", 0),
        "skill_schema": skc_scanned, "skill_drift": skc_scanned, "skill_renderer": skc_scanned,
        "localization": sum(
            len(item.get("pages", []))
            for item in localization_manifest.values()
            if isinstance(item, dict)
        ),
    }
    _layout_own = [x for x in vl_fail if x.startswith("[")]

    def _suite_status(sid):
        if sid in na_suites:
            return "skipped", f"not applicable to a '{lang}' translation (English-prose style check)", None
        if sid in suite_errors:
            return "degraded", suite_errors[sid], _scanned.get(sid)
        scanned = _scanned.get(sid)
        if scanned == 0:
            return "skipped", "examined 0 inputs (nothing found to check)", 0
        if sid == "layout":
            return ("flagged" if _layout_own else "clean"), None, None
        if sid == "foyer":
            return ("clean" if foyer_ok else "flagged"), None, None
        return ("flagged" if findings_detail.get(sid) else "clean"), None, scanned

    for su in suites:
        st, note, scanned = _suite_status(su["id"])
        su["status"] = st
        if note:
            su["note"] = note
        if scanned is not None:
            su["scanned"] = scanned
    # "degraded" is for checks that could not run cleanly. A suite deliberately skipped because it
    # does not apply to this language is not degraded, so keep na_suites out of that list.
    degraded = [su["id"] for su in suites
                if su["status"] in ("degraded", "skipped") and su["id"] not in na_suites]

    if not vl_ok:
        gradient[REQUIRED] += max(1, len(vl_fail))
    if not foyer_ok:
        gradient[REQUIRED] += max(1, len(foyer.get("violations", [])))
    advisory = gradient[RECOMMENDED] + gradient[CONSIDER]

    summary = {
        "schema": "bundle-validation/1",
        "generated": _report_stamp(stamp),
        "git_sha": _git_sha(), "scope": scope, "lang": lang,
        "translation_na_suites": sorted(na_suites), "ok": ok,
        "link_stats": s, "validate_layout_ok": vl_ok, "validate_layout_failures": vl_fail,
        "grounding": {"pages": len(grecs), "findings": len(gfind),
                      "ungrounded": ungrounded, "em_dash_pages": emdash,
                      "vendored_em_dash_pages": len(vendored_emdash),
                      "mat_associated": len(mat_assoc)},
        "reachability": reach,
        "foyer_release": foyer,
        "page_audit": audit,
        "html_structure": {"pages": len(hsa.source_pages(TASK1)), "findings": len(html_structure_find)},
        "security_architecture": {"findings": len(security_find), "graph_items": security_scanned},
        "threat_controls": {"findings": len(threat_control_find), "controls": threat_control_scanned},
        "release_evidence": {"findings": len(release_evidence_find),
                             "evidence_items": release_evidence_scanned},
        "repository_work_products": {"findings": len(repository_work_products_find),
                                     "work_products": repository_work_products_scanned},
        "course_content": {"findings": len(cc_find)},
        "course_dependency_integrity": {"findings": len(cdi_find)},
        "prose_variety": {"pages": len(pv_rows), "flagged": len(pv_flagged), "flag_at": pv.FLAG_AT,
                          "flagged_pages": [{"path": r["path"], "score": r["score"], "tells": r["tells"]}
                                            for r in pv_flagged],
                          "antithesis": pv_antithesis},
        "color_theme": {"inline": ct_inline, "undefined_var": ct_undef, "bake": ct_bake,
                        "palette": ct_palette},
        "code_hygiene": {"files": ch_scanned, "findings": len(ch_rows),
                         "by_kind": {k: sum(1 for r in ch_rows if r["kind"] == k)
                                     for k in sorted({r["kind"] for r in ch_rows})}},
        "figure_audit": {k: len(v) for k, v in fa_find.items()},
        "cell_audit": {k: len(v) for k, v in ca_find.items()},
        "learner_flow": {"findings": len(learner_flow_find)},
        "contribution_safety": {"findings": len(contribution_safety_find)},
        "sensitive_content": {"findings": len(sensitive_find), "scanned": sensitive_scanned},
        "localization": {"findings": len(localization_find),
                         "counts": localization_counts,
                         "by_locale": localization_by_locale},
        "diagram_geom": {"findings": len(dg_find)},
        "skill_contract": {"skills": skc_scanned,
                           "schema": len(skc_find.get("schema", [])),
                           "drift": len(skc_find.get("drift", []))},
        "materials": materials,
        "advisory_total": advisory,
        "degraded": degraded,
        "gradient": gradient,
        "report": rep,
        "findings_detail": findings_detail,
        "suites": suites,
    }

    print(f"validate_bundle [{summary['git_sha']}] scope={scope}"
          + ("" if lang_en else f" lang={lang} (translation: English-prose suites n/a)"))
    print(f"  links: {s['pages']} pages / {s['links']} links")
    print(f"  failures-to-get : {s['failures']} (blocking {s['blocking_failures']})")
    print(f"  asset leaks     : {s['asset_leaks']} (blocking {s['blocking_asset_leaks']})")
    print(f"  cross-course    : {s['cross_course']} (blocking {s['blocking_cross_course']})")
    print(f"  validate_layout : {'OK' if vl_ok else 'FAIL ' + '; '.join(vl_fail[:3])}")
    print(f"  grounding       : {len(gfind)} pages w/ issues "
          f"(ungrounded {ungrounded}, em-dash {emdash if lang_en else 'n/a'}) over {len(grecs)} pages")
    if vendored_emdash:
        print(f"  vendored em-dash: {len(vendored_emdash)} external snapshot(s) carry the source's "
              f"em-dashes (surfaced, not advisory)")
    print(f"  reachability    : {reach['reachable']}/{reach['pages']} pages reach a SKILL hub; "
          f"strays {len(reach['strays'])} (each is a real navigation gap, connected by neither a link nor a shared citation)")
    print(f"  foyer release   : {'OK' if foyer_ok else 'FAIL'} (surfaces {foyer.get('surfaced_courses', [])}; "
          f"released {foyer.get('released', [])})")
    for v in foyer.get("violations", []):
        print(f"    ✗ foyer {v.get('kind')}: {v.get('detail')}")
    print(f"  page audit      : {audit.get('pages_with_findings', '?')}/{audit.get('pages', '?')} .html show drift "
          f"(stale tokens / missing assets / contract)")
    print(f"  course content  : {len(cc_find)} required content contract finding(s) (teaching, product, platform)")
    print(f"  security arch.   : {len(security_find)} required finding(s) over {security_scanned} nodes and flows")
    print(f"  threat controls  : {len(threat_control_find)} required finding(s) over "
          f"{threat_control_scanned} repository control assertions")
    if not lang_en:
        print(f"  prose / buzz / branding : n/a for '{lang}' (English-prose style suites do not gate a translation)")
    if pv_rows and lang_en:
        print(f"  prose variety   : {len(pv_flagged)}/{len(pv_rows)} narrative pages flagged for a rhythm pass"
              + (f" (worst: {pv_rows[0]['path'].split('/')[-1]} @ score {pv_rows[0]['score']})" if pv_flagged else ""))
        if pv_antithesis:
            print(f"  buzz cadence    : {len(pv_antithesis)} antithesis/numeric construction(s) across "
                  f"{len({a['page'] for a in pv_antithesis})} page(s) (rewrite the sentence; see latest.md)")
            for a in pv_antithesis[:6]:
                snip = a["sentence"][:88] + ("…" if len(a["sentence"]) > 88 else "")
                print(f"      [{a['kind']}] {a['page'].split('/')[-1]}: {snip}")
    print(f"  color theme     : {ct_inline + ct_undef + ct_bake + ct_palette} non-theme-dynamic color(s) "
          f"(inline {ct_inline}, undefined-var {ct_undef}, render-bake {ct_bake}, palette {ct_palette})")
    print(f"  figure audit    : {fa_total} legibility/format finding(s) "
          f"(tiny-text {len(fa_find.get('tiny', []))}, small-render {len(fa_find.get('small_render', []))}, "
          f"flex-parent {len(fa_find.get('flex_parent', []))}, overflow {len(fa_find.get('overflow', []))}, "
          f"a11y {len(fa_find.get('no_aria', [])) + len(fa_find.get('img_no_alt', [])) + len(fa_find.get('blank_link', []))}, "
          f"dark-mode {len(fa_find.get('dark_mode', []))}, canvas {len(fa_find.get('canvas', []))}, "
          f"crowded {len(fa_find.get('crowded', []))})")
    print(f"  cell audit      : {ca_total} cell-contract finding(s) "
          f"(opaque {len(ca_find.get('opaque', []))}, console {len(ca_find.get('console', []))}, "
          f"unawaited {len(ca_find.get('unawaited', []))}, dialog {len(ca_find.get('dialog', []))}, "
          f"inline-key {len(ca_find.get('inline_key', []))}, static {len(ca_find.get('static_cell_code', []))}, "
          f"unhighlighted {len(ca_find.get('unhighlighted', []))}, "
          f"ui-contract {len(ca_find.get('ui_contract', []))}, "
          f"code-surface {len(ca_find.get('code_surface', []))}, "
          f"readability {len(ca_find.get('readability', []))}, "
          f"copy {len(ca_find.get('copy_surface', []))}, "
          f"run-cell-style {len(ca_find.get('run_cell_style', []))}, "
          f"prompt-experiment {len(ca_find.get('prompt_experiment', []))})")
    print(f"  learner flow    : {len(learner_flow_find)} required finding(s) "
          f"(progressive disclosure / prerequisites / lifecycle / model-endpoint/no-GPU baseline)")
    print(f"  contribution    : {len(contribution_safety_find)} required finding(s) "
          f"(intake / submissions / hooks / CI permissions / release authority)")
    print(f"  sensitive data  : {len(sensitive_find)} required finding(s) over {sensitive_scanned} text inputs")
    print(f"  release evidence: {len(release_evidence_find)} required finding(s) "
          f"over {release_evidence_scanned} design, test, and ownership items")
    print(f"  repository files: {len(repository_work_products_find)} required finding(s) "
          f"over {repository_work_products_scanned} reviewed work products")
    print(f"  localization    : {len(localization_find)} required finding(s) "
          f"({localization_by_locale})")
    print(f"  figure geometry : {len(dg_find)} runtime-figure finding(s) (text overlap / past bounds / connector-crosses-box / useless)")
    print(f"  course contract : {len(course_contract_find)} finding(s) (title / abstract / learning objectives)")
    print(f"  browser deps    : {len(cdi_find)} finding(s) over {cdi_scanned} package, asset, and notice records")
    print(f"  concept order   : {len(concept_order_find)} finding(s) (first-use definitions / prerequisite framing)")
    _cg = {k: len(v) for k, v in ch_fam.items()}
    print(f"  code hygiene    : {len(ch_rows)} finding(s) over {ch_scanned} code file(s) "
          f"(comments {_cg.get('comments', 0)}, walls {_cg.get('walls', 0)}, dup {_cg.get('duplication', 0)}, "
          f"size {_cg.get('size', 0)}, const {_cg.get('constants', 0)})")
    _tiers = ", ".join(f"{n} {t}" for t, n in sorted(materials["by_tier"].items())) or "none"
    print(f"  materials       : {materials['count']} vendored web sources ({_tiers}); "
          f"{len(materials['unreachable'])} unreachable at last pull")
    for u in materials["unreachable"]:
        print(f"    ✗ material {u['name']} ({u['host']}): {u['error'] or 'unreachable'}")
    if materials["unreachable"]:
        print(f"      fix: {materials['fix']}")
    if not ok:
        for x in (rep["failures"] + rep["asset_leaks"] + rep["cross_course"]):
            if scope == "all" or x.get("ship"):
                print(f"    ✗ {x['page']} -> {x.get('link')}  ({x.get('reason','leak/cross')})")

    if write:
        out = TASK1 / "docs" / "validation"
        out.mkdir(parents=True, exist_ok=True)
        (out / "latest.json").write_text(json.dumps(summary, indent=2))
        (out / "latest.md").write_text(_render_md(summary))
        # mat-association obs artifact: page -> {mat: [shared citation URLs]}.
        # The link graph reads this to draw page<->mat grounding edges (request: associate via URL).
        (out / "mat_association.json").write_text(json.dumps(
            {"generated": summary["generated"], "pages_associated": len(mat_assoc),
             "association": mat_assoc}, indent=2))
        # single source for the viewer: refresh the embedded DATA snapshot in link_graph.html
        # so its offline default reflects current reality (the in-lab Rescan still overrides).
        if not lp.embed_graph_snapshot(engine_bundle["graph"]):
            raise RuntimeError("link_graph.html has no DATA snapshot marker")
        print(f"  wrote docs/validation/latest.{{json,md}} plus mat_association.json "
              f"and the link_graph.html snapshot (via engine.js)")

    req, rec, con = gradient[REQUIRED], gradient[RECOMMENDED], gradient[CONSIDER]
    print(f"  gradient        : {req} required · {rec} recommended · {con} consider "
          f"(required blocks the ship; recommended is a known wrong; consider is a judgment call)")

    # honest, unhedged verdict. "clean" ONLY when nothing is outstanding at any tier.
    if not ok:
        verdict = (f"✗ FAIL · {req} hard requirement(s) block the ship. Fix these first; "
                   f"they are listed above and in validation.html under Required.")
    elif rec or con:
        verdict = (f"PASS · ships, but NOT done. {rec} recommended fix(es) and {con} polish item(s) "
                   f"are outstanding, each with the change to make. Work the recommended list down: "
                   f"docs/validation/latest.md or the validation.html report.")
    else:
        verdict = "✅ clean. Nothing outstanding at any tier (required, recommended, or consider)."
    print(f"validate_bundle: {verdict}")
    print("  detail: docs/validation/latest.md  ·  review UI: validation.html  ·  one suite: python3 scripts/validation/prose_variety.py")
    return 0 if ok else 1


def _render_md(summary: dict) -> str:
    s = summary["link_stats"]
    rep = summary["report"]
    g = summary.get("grounding", {})
    rc = summary.get("reachability", {})
    fy = summary.get("foyer_release", {})
    pa = summary.get("page_audit", {})
    adv = summary.get("advisory_total", 0)
    grad = summary.get("gradient", {})
    gq, gr_, gc = grad.get("required", 0), grad.get("recommended", 0), grad.get("consider", 0)
    if not summary["ok"]:
        gate = f"✗ FAIL · {gq} required (ship-blocking)"
    elif adv > 0:
        gate = f"PASS · ships, NOT done · {gr_} recommended + {gc} consider outstanding"
    else:
        gate = "✅ clean (nothing outstanding at any tier)"
    L = [f"# Bundle validation · {summary['generated']}  ·  `{summary['git_sha']}`",
         "", f"**Gate ({summary['scope']} scope): {gate}**", "",
         "| metric | total | blocking |", "|---|---|---|",
         f"| failures-to-get | {s['failures']} | {s['blocking_failures']} |",
         f"| asset leaks | {s['asset_leaks']} | {s['blocking_asset_leaks']} |",
         f"| cross-course | {s['cross_course']} | {s['blocking_cross_course']} |",
         f"| grounding issues | {g.get('findings','?')} | advisory |",
         f"| · ungrounded pages | {g.get('ungrounded','?')} | advisory |",
         f"| · em-dash pages | {g.get('em_dash_pages','?')} | advisory |",
         f"| prose variety (narrative pages flagged) | {summary.get('prose_variety',{}).get('flagged','?')} / {summary.get('prose_variety',{}).get('pages','?')} | advisory |",
         f"| · buzz cadence (antithesis/numeric) | {len(summary.get('prose_variety',{}).get('antithesis',[]))} | advisory |",
         f"| color theme (non-theme-dynamic colors) | {summary.get('color_theme',{}).get('inline',0) + summary.get('color_theme',{}).get('undefined_var',0) + summary.get('color_theme',{}).get('bake',0)} | blocking |",
         f"| figure audit (rendering contract / legibility) | {sum(summary.get('figure_audit',{}).values())} | theme-contract and mobile findings block |",
         f"| cell audit (runnable-cell contract) | {sum(summary.get('cell_audit',{}).values())} | advisory |",
         f"| learner interaction flow | {summary.get('learner_flow',{}).get('findings',0)} | blocking |",
         f"| contribution safety | {summary.get('contribution_safety',{}).get('findings',0)} | blocking |",
         f"| repository work products | {summary.get('repository_work_products',{}).get('findings',0)} | blocking |",
         f"| sensitive content boundary | {summary.get('sensitive_content',{}).get('findings',0)} | blocking |",
         f"| Security architecture graph | {summary.get('security_architecture',{}).get('findings',0)} | blocking |",
         f"| Threat control disposition | {summary.get('threat_controls',{}).get('findings',0)} | blocking |",
         f"| figure geometry (runtime figures) | {summary.get('diagram_geom',{}).get('findings',0)} | advisory |",
         f"| strays (unreachable from a SKILL hub) | {len(rc.get('strays',[]))} | {rc.get('real_strays','?')} real |",
         f"| release foyer (surfaces only RELEASED) | {'OK' if fy.get('ok') else 'FAIL'} | {len(fy.get('violations',[]))} blocking |",
         f"| page audit (.html drift) | {pa.get('pages_with_findings','?')} / {pa.get('pages','?')} | advisory |",
         f"| materials (vendored web sources) | {summary.get('materials',{}).get('count','?')} | {len(summary.get('materials',{}).get('unreachable',[]))} unreachable, advisory |",
         f"| validate_layout | {'OK' if summary['validate_layout_ok'] else 'FAIL'} | |", ""]

    # The proactive list: every finding, grouped by the advertised tier, WITH the change to
    # make. A maintainer works top-down (required, then recommended, then consider) and never
    # has to guess what "flagged" means, the fix is on the line. This is the actionable core.
    SUITE_LABEL = {"links": "Links & assets", "cross_course": "Cross-course links",
                   "asset_leaks": "Asset leaks", "page_audit": "Page audit", "prose_variety": "Prose rhythm",
                   "prose_buzz": "Buzz cadence", "redundancy": "Redundancy", "grammar": "Grammar & composition", "grounding": "Grounding", "color_theme": "Color theme",
                   "figure_audit": "Figure audit", "cell_audit": "Cell contract", "diagram_geom": "Figure geometry",
                   "materials": "Materials", "reachability": "Reachability", "contribution_safety": "Contribution safety",
                   "sensitive_content": "Sensitive content boundary",
                   "security_architecture": "Security architecture graph",
                   "threat_controls": "Threat control disposition",
                   "repository_work_products": "Repository work products",
                   "word_echo": "Word echo", "comma_weight": "Comma weight", "assertions": "Bare assertions",
                   "headings": "Headings", "structure": "Structural rhythm", "branding": "Brand naming",
                   "defer_copula": "Deferred copula", "dense_repeats": "Dense repetition", "over_verbage": "Over-verbage",
                   "padding": "Padding", "hollow_intro": "Scaffolding openers",
                   "repeated_phrase": "Phrase repetition", "vacuous_meta": "Vacuous meta-writing",
                   "staccato_cadence": "Staccato cadence",
                   "code_comments": "Code comments", "code_walls": "Code walls", "code_dup": "Code duplication",
                   "code_size": "File size & density", "code_const": "Hard-coded constants",
                   "code_prose": "Prose tells in code"}
    fd = summary.get("findings_detail", {})
    by_tier = {"required": [], "recommended": [], "consider": []}
    for suite, items in fd.items():
        for it in items:
            by_tier.setdefault(it.get("severity", "recommended"), []).append((suite, it))
    TIER_HEAD = {
        "required": "Required (ship-blocking · fix before shipping)",
        "recommended": "Recommended (a real defect · fix it)",
        "consider": "Consider (polish / judgment call)",
    }
    L.append("## What to fix")
    if not any(by_tier.values()):
        L.append("\nNothing outstanding at any tier. The narrative checks below are clean.\n")
    for tier in ("required", "recommended", "consider"):
        rows = by_tier.get(tier, [])
        if not rows:
            continue
        L.append(f"\n### {len(rows)} flagged in {TIER_HEAD[tier]}")
        # Per-signal tally, so a large tier is legible at a glance (which signal contributes what)
        # rather than an opaque count. The full per-item list lives in docs/validation/latest.json.
        if len(rows) > 12:
            tally = {}
            for s, _ in rows:
                tally[s] = tally.get(s, 0) + 1
            L.append("  by signal: " + " · ".join(f"{SUITE_LABEL.get(s, s)} {c}"
                                                   for s, c in sorted(tally.items(), key=lambda kv: -kv[1])))
        # Show a sample spread ACROSS signals (round-robin), not the first 80 of one suite, so every
        # signal is represented in the printed examples even when one signal dominates the count.
        from itertools import zip_longest
        buckets = {}
        for s, it in rows:
            buckets.setdefault(s, []).append((s, it))
        interleaved = [e for grp in zip_longest(*buckets.values()) for e in grp if e is not None]
        for suite, it in interleaved[:90]:
            L.append(f"- **{SUITE_LABEL.get(suite, suite)}** flagged `{it.get('page','')}`. {it.get('detail','')}")
            L.append(f"    - **fix:** {it.get('fix','')}")
        if len(rows) > 90:
            L.append(f"- … {len(rows) - 90} more (full list in docs/validation/latest.json)")
    L.append("")

    # per-.html drift audit: each page auto-verified against the engine (stale tokens, missing
    # assets, skill-meta / foyer-release contract). Advisory, but it is how drift gets caught.
    L.append(f"## Page audit (.html drift): {pa.get('pages_with_findings', 0)} of {pa.get('pages', 0)} pages")
    if pa.get("findings"):
        for pf in pa["findings"][:60]:
            for fnd in pf.get("findings", []):
                L.append(f"- `{pf['page']}` **{fnd.get('kind')}**: {fnd.get('detail') or fnd.get('asset') or fnd.get('token','')}")
    else:
        L.append("\nNo drift: every audited page passes stale-token, asset, and contract checks.")
    L.append("")

    # materials: the committed snapshot of each web source the bundle vendors. The student
    # validator screen renders this, so anyone (you, CI, a student) sees exactly which source is
    # unreachable and the one-line fix, in the same words.
    mt = summary.get("materials", {})
    L.append(f"## Materials ({mt.get('count', 0)} vendored web sources, last pulled {mt.get('generated') or '?'})")
    if mt.get("unreachable"):
        L.append(f"\n**{len(mt['unreachable'])} unreachable at the last pull.** Fix: `{mt.get('fix', '')}`\n")
        for u in mt["unreachable"]:
            L.append(f"- `{u['name']}` ({u.get('host')}) &lt;{u.get('url')}&gt;: {u.get('error') or 'unreachable'}")
    else:
        L.append("\nEvery vendored web source pulled cleanly. Refresh with "
                 "`python3 scripts/materials/pull_materials.py`; drift-check against the live web with "
                 "`python3 scripts/materials/pull_materials.py --check`.")
    L.append("")

    # release-foyer contract: the foyer is the student-facing release surface; it must
    # discover ONLY the released courses. A violation is ship-blocking, not advisory.
    L.append(f"## Release foyer (surfaces {fy.get('surfaced_courses', [])}; released {fy.get('released', [])})")
    if fy.get("violations"):
        L.append("\n_contract broken (ship-blocking)_:")
        for v in fy["violations"]:
            L.append(f"- **{v.get('kind')}**: {v.get('detail')}")
    else:
        L.append("\nContract honored: the foyer discovers exactly the released courses.")
    L.append("")

    def section(title, items, fmt):
        block = [x for x in items if x.get("ship")]
        adv = [x for x in items if not x.get("ship")]
        L.append(f"## {title}: {len(block)} blocking, {len(adv)} advisory")
        for label, group in (("blocking", block), ("advisory", adv)):
            if not group:
                continue
            L.append(f"\n_{label}_:")
            for x in group[:40]:
                L.append(f"- {fmt(x)}")
            if len(group) > 40:
                L.append(f"- … {len(group) - 40} more")
        L.append("")

    section("Failures-to-get", rep["failures"],
            lambda x: f"`{x['page']}` → `{x.get('link')}`  _{x.get('reason','')}_")
    section("Asset leaks (cross-contamination)", rep["asset_leaks"],
            lambda x: f"`{x['page']}` ({x['src_course']}) → `{x['link']}` ({x['tgt_course']}); isolate: {x.get('isolate','')}")
    section("Cross-course links", rep["cross_course"],
            lambda x: f"`{x['page']}` ({x['src_course']}) → `{x['link']}` ({x['tgt_course']})")

    # strays: pages no SKILL hub leads to. REAL = a content page that should be in the
    # hierarchy (a navigation gap). EXPECTED = mats / corpus data / demo internals / skill
    # configs / generated reports, which are detached by design and surfaced for honesty not action.
    sset = rc.get("strays", [])
    real = [x for x in sset if not x.get("expected")]
    exp = [x for x in sset if x.get("expected")]
    L.append(f"## Strays (unreachable from a SKILL hub): {len(real)} real, {len(exp)} expected-detached")
    if real:
        L.append("\n_real (a navigation gap; no hub path leads here)_:")
        for x in real[:40]:
            L.append(f"- `{x['page']}` ({x['course']}): {x['reason']}")
    if exp:
        L.append(f"\n_expected-detached (mats / data / demo internals / skill configs / generated)_:")
        for x in exp[:15]:
            L.append(f"- `{x['page']}`")
        if len(exp) > 15:
            L.append(f"- … {len(exp) - 15} more")
    L.append("")

    # prose variety: narrative pages that read machine-uniform (monotone length, staccato triads,
    # enumeration, welded clauses). Advisory; it points at pages to give a rhythm pass, not verdicts.
    pvd = summary.get("prose_variety", {})
    L.append(f"## Prose variety (machine-uniformity; advisory): {pvd.get('flagged', 0)} of {pvd.get('pages', 0)} narrative pages flagged")
    if pvd.get("flagged_pages"):
        L.append(f"\n_at or above score {pvd.get('flag_at')}; `python3 scripts/validation/prose_variety.py` for the full ranked table_:")
        for r in pvd["flagged_pages"][:20]:
            L.append(f"- `{r['path']}` score {r['score']}: {'; '.join(r['tells'])}")
    else:
        L.append("\nNo page is over the rhythm threshold. Full ranked metrics: `python3 scripts/validation/prose_variety.py`.")
    anti = pvd.get("antithesis", [])
    if anti:
        L.append(f"\n### Buzz cadence: {len(anti)} antithesis/numeric construction(s) to rewrite")
        L.append("_A mirrored 'A is B; C is D', a 'one X, many Y', or a 'not X. It is Y' carries little "
                 "information and reads as marketing. Rewrite the sentence; do not just swap words._\n")
        for a in anti[:40]:
            L.append(f"- `{a['page'].split('/')[-1]}` [{a['kind']}]: {a['sentence'][:140]}")
    L.append("")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scope", choices=["ship", "all"], default="ship")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--stamp", help="ISO timestamp to embed (for reproducible CI logs)")
    ap.add_argument("--lang", default="en",
                    help="content language. 'en' runs the full gate; a translation code (es, fr, de, ...) "
                         "skips the English-prose style suites that do not apply to the target language.")
    a = ap.parse_args()
    return run(scope=a.scope, write=not a.no_write, stamp=a.stamp, lang=a.lang)


if __name__ == "__main__":
    sys.exit(main())
