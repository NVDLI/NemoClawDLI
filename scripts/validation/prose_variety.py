#!/usr/bin/env python3
# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Prose-variety static analysis: does the authored course narrative read like a person wrote it?

LLM prose has structural tells that have nothing to do with word choice: sentences cluster at one
length, ideas get forced into triads, and clauses get welded with colons and semicolons to sound
punchy. This check measures those signals per page over the narrative flow only and ranks the pages,
surfacing the ones that read machine-uniform so a human can go vary the rhythm. Narrative is the <p>
paragraph text. SKILL.html guidance also includes list items because those lists explain the project
to a reader; they are not course-data enumerations. Other list items, catalog cards, code, SVG,
headings, and nav chrome stay excluded. A paragraph break counts as a sentence boundary, so a
list-/cell-lead-in colon at a paragraph's end is not mistaken for a welded mid-sentence clause. It is
deterministic and advisory:
it points at pages and shows its work, it does not pass verdicts and never blocks the gate.

Per page it reports:

  cv        coefficient of variation of sentence length (sd / mean), the core variety signal.
            Human prose mixes short and long; a low cv means every sentence is about the same size.
  short%    share of sentences <= 7 words. Real writing breaks long stretches with short jabs.
  triad     runs of 3+ consecutive short sentences (<= 12 words, <= 4-word band) that share one
            opening word: the "It plans. It acts. It reflects." anaphoric staccato. Short sentences
            with varied openers are ordinary terse prose (spec fragments, captions), not a tell.
  ana       longest run of consecutive sentences opening with the same word.
  r3        exactly-three "A, B, and C" comma series per 1000 words (a 4+ item list is a real
            enumeration, not rule-of-three, so it does not count).
  :;/s      welded clauses per sentence: every semicolon, plus colons that sit mid-sentence; a
            trailing colon is a list-/cell-lead-in, not punch, so it does not count.
  score     a weighted sum of the above (weights in _score below, and printed in the legend), so
            the table sorts worst-first. A page at or above FLAG_AT is marked for a rhythm pass.

Usage:
  python3 scripts/validation/prose_variety.py                 # rank the course narrative pages (table)
  python3 scripts/validation/prose_variety.py --scope all     # also include the repo's prose .md docs
  python3 scripts/validation/prose_variety.py --page web/nemoclaw/01a-loop.html   # one page + its sentences
  python3 scripts/validation/prose_variety.py --text "..."    # score a snippet (handy while rewriting)
  python3 scripts/validation/prose_variety.py --json          # machine-readable (the gate reads this)
"""
from __future__ import annotations
import argparse
import html
import json
import re
import statistics
import sys
from pathlib import Path

for _p in (Path(__file__).resolve(), *Path(__file__).resolve().parents):
    if (_p / "scripts" / "_bootstrap.py").exists():
        sys.path.insert(0, str(_p / "scripts")); break
from _bootstrap import add_script_paths, find_repo_root

HERE = Path(__file__).resolve()
TASK1 = find_repo_root(HERE)
SCRIPTS = TASK1 / "scripts"
add_script_paths(SCRIPTS)
from html_document import raw_text_blocks, without_elements  # noqa: E402
import link_projection as lp  # noqa: E402

FLAG_AT = 3.0   # score at or above this marks a page for a rhythm pass (advisory)

# Do not split after a citation/abbreviation period ("Yao et al. (2022)", "e.g.", "i.e.", "vs."):
# in an academic course those are mid-sentence, and a false split fabricates short fragments that
# skew length variance and triad detection. Each guard is fixed-width (Python lookbehind rule).
_ABBR_GUARD = (r"(?<!\bal\.)(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\bvs\.)(?<!\betc\.)(?<!\bcf\.)"
               r"(?<!\bFig\.)(?<!\bEq\.)(?<!\bNo\.)(?<!\bDr\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bProf\.)")
_SENT_SPLIT = re.compile(r'(?<=[.!?])' + _ABBR_GUARD + r'["\'’)\]]*\s+(?=[A-Z(0-9"\'“])')
_WORD = re.compile(r"[A-Za-z0-9']+")
# function words only: a shared CONTENT word across short sentences signals a parallel triad
# ("A thermostat PUTS... A car PUTS... Every agent PUTS..."), so verbs/nouns must NOT be in here.
_STOP = {"the", "a", "an", "of", "to", "in", "on", "at", "is", "are", "be", "it", "this", "that",
         "and", "or", "with", "for", "as", "by", "from", "its", "you", "your", "we", "our", "they",
         "their", "he", "she", "but", "so", "if", "then", "into", "out", "up", "no", "not"}
_TAG = re.compile(r"<[^>]+>")
_SVG = re.compile(r"<svg\b.*?</svg>", re.I | re.S)
_SVGTEXT = re.compile(r"<text\b[^>]*>(.*?)</text>", re.I | re.S)        # label text rendered inside a figure
_FIGCAP = re.compile(r"<figcaption\b[^>]*>(.*?)</figcaption>", re.I | re.S)
# Reference/navigation tiles carry terse captions, not narrative flow, so they are excluded like
# list items: any link-card (the whole card is an <a> -- url-card, sys-card, path-card, the foyer's
# course cards) and the step-card catalog tile. Content cards that hold teaching prose (pattern-card,
# a <div>) are kept and measured.
_CARDS = (
    re.compile(r'<a\b[^>]*\bclass="[^"]*\bcard\b[^"]*"[^>]*>.*?</a>', re.I | re.S),
    re.compile(r'<div\b[^>]*\bclass="[^"]*\bstep-card\b[^"]*"[^>]*>.*?</div>', re.I | re.S),
)
_PARA = re.compile(r"<p\b[^>]*>(.*?)</p>", re.I | re.S)   # narrative flow only; list items are enumerative by nature
_SKILL_ITEM = re.compile(r"<li\b[^>]*>(.*?)</li>", re.I | re.S)
_SKILL_CATALOG = re.compile(
    r'<(?P<tag>ul|ol)\b[^>]*\bclass="[^"]*\bfile-index\b[^"]*"[^>]*>.*?</(?P=tag)>',
    re.I | re.S,
)
# The course contract owns this verbatim canonical copy. Exclude it from style advice: a validator
# must not flag prose that authors are forbidden to rewrite. Content and presence remain release-gated
# by course_content_contract.py.
_IMMUTABLE_CANON = re.compile(
    r'<p\b[^>]*\bid=["\']course-abstract["\'][^>]*>.*?</p>', re.I | re.S)
# Teaching prose also lives OUTSIDE <p>: a <div class="callout"> (or note/lead/takeaway, and the
# warn/info variants) wraps a <strong> lead-in and running sentences with no inner <p>. These were
# never measured, which is how a buzzy callout passed the check. Scan them like paragraphs; the
# <p> pass still handles any inner <p>, so each chunk is counted once.
_CALLOUT = re.compile(
    r'<(?:div|aside)\b[^>]*\bclass="[^"]*\b(?:callout|note|lead|takeaway)\b[^"]*"[^>]*>(.*?)</(?:div|aside)>',
    re.I | re.S)
_SERIES3 = re.compile(r"(?<!, )\b[\w][\w'\-]*(?:\s+[\w'\-]+){0,3},\s+[^,.;:]{2,40},\s+(?:and|or)\s+[^,.;:]{2,40}", re.I)  # exactly-three series; a 4+ item enumeration is not rule-of-three
# Negative parallelism / antithesis (HUMANIZE #9): the negate-then-affirm cadence. The strongest
# form is "not X, but Y"; bare "rather than" is usually an ordinary preference contrast, not a tell,
# so it is not counted (it only ever fired on legitimate technical comparisons here).
_NEGPAR = re.compile(
    r"\bnot only\b[^.]{1,60}?\bbut\b"                       # not only X but (also) Y
    r"|\bnot\b[^,.;:]{2,35}?,?\s+but\b"                     # not X(,) but Y
    r"|\bit(?:'?s| is) not\b[^.]{1,60}?\bit(?:'?s| is)\b"   # it's not X, it's Y
    r"|\b(?:not|isn'?t) just\b"                             # not just / isn't just (soft antithesis cue)
    r"|\bnot merely\b",
    re.I)

# ── Parallel / numeric antithesis: the marketing-cadence class ───────────────
# The buzz an LLM most often leaves is not staccato or anaphora; it is rhetorical
# mirroring that carries little information: "A is B; C is D", "one X, many Y",
# "the X that makes it Y is also Z", "not the brand. It is ...". Each is a named
# construction below, and the sweep surfaces the exact sentence so a human judges
# it instead of trusting a number. These are the tells the old score was blind to.
_PAR_COPULA = re.compile(r"\b(?:is|are|was|were)\b[^;.?!]{1,45};\s+[^;.?!]{1,45}\b(?:is|are|was|were)\b", re.I)
_COUNTED_NOUN = r"[\w-]+(?:\s+[\w-]+){0,2}"
_NUM_ANTI = re.compile(
    rf"\b(?:one(?!\s+of\b)|a single)\b\s+{_COUNTED_NOUN},\s+(?:many|all|every|no|none|countless|swappable|infinite|any|each)\s+{_COUNTED_NOUN}\b"
    # Counted punches often use multiword noun phrases ("One workflow idea, two implementations"
    # and "Five agents, one application layer"). The old one-word left side missed the first form.
    rf"|\b(?:same|one|a single|both|each|every)\s+{_COUNTED_NOUN},\s+(?:two|three|four|five|six|seven|eight|nine|ten|\d+|many|all|both|one|no|none|every)\s+{_COUNTED_NOUN}\b"
    rf"|\b(?:two|three|four|five|six|seven|eight|nine|ten|\d+)\s+{_COUNTED_NOUN},\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+|many)\s+{_COUNTED_NOUN}\b",
    re.I,
)
_REPEATED_COUNT = re.compile(
    rf"\b(?P<count>one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+{_COUNTED_NOUN},\s+"
    rf"(?P=count)\s+{_COUNTED_NOUN},\s+(?P=count)\s+{_COUNTED_NOUN}\b",
    re.I,
)
_ONE_PUNCH = re.compile(r"(?:^|[.!?]\s+)(?:One|A single)\s+[\w-]+\.(?:\s|$)")
_SAME_X = re.compile(r"\bthe\s+[\w-]+\s+that\s+(?:makes|made|lets|gives|drives|enables|powers)\s+[^.;,]{2,45}?\s+is\s+(?:also\s+)?", re.I)
_NEG_SPLIT = re.compile(r"\bis not\b[^.?!:;]{2,50}[:;,.?!]\s+[Ii]t(?:'s| is)\b", re.I)  # "is not X: it is Y" reveal (colon/comma/period)
_TWO_DIFF = re.compile(r"\b(?:are|is)\s+two\s+different\b", re.I)
_ANTI_PATS = [("parallel-copula", _PAR_COPULA), ("numeric-antithesis", _NUM_ANTI),
              ("repeated-count-list", _REPEATED_COUNT),
              ("one-word-punch", _ONE_PUNCH), ("same-X-reversal", _SAME_X),
              ("not-X-it-is-Y", _NEG_SPLIT), ("two-different", _TWO_DIFF)]

# Three more constructions the copula/numeric patterns above were blind to, all in the flagged
# example from 01a ("a slice, not the whole environment; ... one bounded update, not arbitrary
# power; ..."):
#   negate-parallel   a clause that affirms then negates ("a slice, not the whole environment"),
#                     counted only when it REPEATS in one sentence (2+), which is the rhetorical
#                     mirror. A lone "X, not Y" is ordinary contrast and is left alone.
#   triad-semicolons  one sentence carrying two or more semicolons: a rule-of-three welded into a
#                     single breath, the punchy-list cadence a person rarely writes.
#   doubled-word      "run again and again", "more and more": filler intensifier by repetition.
_COMMA_NEG = re.compile(r",\s+(?:not|no|never|nor)\b", re.I)
_DOUBLED = re.compile(r"\b(\w{3,})\s+and\s+\1\b", re.I)
#   repeated-pivot    one sentence that swings the same transformation verb across two coordinated
#                     clauses ("perceiving becomes observing a tool result, acting becomes a tool
#                     call"). The echoed pivot is the mechanical-parallel tell; a person varies the
#                     second verb or drops it. Counted only when the pivot repeats (2+) in a sentence.
_PIVOT = re.compile(r"\b(?:becomes?|turns?\s+into|turned\s+into|is\s+now|are\s+now)\b", re.I)
#   paired-parenthetical  two short glosses in parentheses in one sentence ("index small chunks
#                     (precise retrieval), but fetch the parent document (full context)"): the
#                     label-each-side cadence. Surfaced even when it reads fine, so a human decides
#                     whether to fold the gloss into the clause or drop the symmetry. Citation
#                     parentheticals ("(NVIDIA, 2023)") are a publication form, not a gloss, so a
#                     parenthetical carrying a year is not counted.
_PAREN = re.compile(r"\(([^)]{1,28})\)")
_CITE_YEAR = re.compile(r"\b(?:19|20)\d\d\b")
#   what-looks-like   the "what looks like X is really Y" reveal-cliche, a hedge framing that a person
#                     rarely writes twice on a page ("What looks like memory is a list your code keeps").
#   echo-aphorism     a two-word content phrase repeated inside one sentence ("control over ... control
#                     over", "a SQL agent over ... a code agent over"): an echo that sounds deep and
#                     adds little, or a repetition that should be varied. Surfaced broadly on purpose.
_WHATLOOKS = re.compile(r"\bwhat (?:looks? like|seems?(?: like)?|appears?|feels? like)\b", re.I)
#   stub-assertion    a copular sentence whose predicate points or hedges instead of informing ("is the
#                     part to stare at", "is what makes X useful", "is a capability you grant or withhold").
_STUB_ASSERT = re.compile(
    r"\b(?:is|are)\s+the\s+(?:part|point|key|thing|trick|gist|crux|reason|idea|spot|place)\b"
    r"|\b(?:is|are)\s+what\s+(?:makes|matters|counts|happens)\b"
    r"|\b(?:is|are)\s+a\s+[\w-]+\b[^.,;:]{0,25}\byou\b[^.;:]{0,20}\bor\b", re.I)
#   meta-emphasis     prose that announces its own importance instead of earning it ("worth
#                     remembering", "the whole point", "what matters is"): cut the wind-up, state it.
_META_EMPH = re.compile(r"\bworth (?:remembering|noting|knowing|keeping)\b"
                        r"|\bthe (?:key|important|crucial|main|whole) (?:thing|point|takeaway|idea)\b"
                        r"|\bwhat matters (?:here|is)\b", re.I)


def _echo_hit(s: str) -> bool:
    ws = [w.lower() for w in _WORD.findall(s) if len(w) >= 4 and w.lower() not in _STOP]
    seen = set()
    for i in range(len(ws) - 1):
        bg = ws[i] + " " + ws[i + 1]
        if bg in seen:
            return True
        seen.add(bg)
    return False
#   terse-fragment    a very short (<= 6 words) verbless, noun/adjective comma fragment used as a
#                     standalone antithesis punch ("Same primitives, two levels.", "Static prediction
#                     first, kernel reality second."). The verbless noun-pile is the tell. A finite or
#                     imperative verb means it is an ordinary short sentence or a process-step list
#                     ("Observe, reason, act, repeat."), not this tell, so those are left alone; and a
#                     citation caption ("Paper: …") is a resource line, handled as a link elsewhere.
_TERSE_VERB = re.compile(r"\b(?:is|are|was|were|be|been|do|does|did|has|have|had|can|could|will|would|"
                         r"should|put|puts|hold|holds|make|makes|run|runs|give|gives|get|gets|read|reads|"
                         r"see|sees|need|needs|use|uses|keep|keeps|let|lets|turn|turns|fill|fills|carry|"
                         r"carries|map|maps|swap|swaps|sit|sits|stay|stays|live|lives|go|goes|reach|reaches|"
                         # imperative / process-step verbs: an action sequence is not a verbless punch
                         r"observe|reason|act|repeat|think|plan|perceive|retrieve|embed|generate|search|"
                         r"route|wrap|build|builds|call|calls|choose|chooses|decide|decides)\b", re.I)
_CITE_CAP = re.compile(r"^\s*(?:paper|source|see|ref|fig|figure|cf|via)\b[:.]?", re.I)

# ── Rules-of-school: plain grammar/composition rules a teacher marks in red ───
# These are not cadence tells; they are the basic-composition mistakes that creep in when prose is
# patched to satisfy a metric instead of being rewritten. Each is precise enough that a trigger is
# worth a full rewrite, not a word swap. grammar_hits() surfaces the exact sentence for each.
_WEAK_OPEN = re.compile(r"^(?:and|but|or|so|yet|nor|plus|basically|essentially|simply put|of course"
                        r"|what(?:'s| is| are| was| were))\b", re.I)   # incl. the "What is X is Y" cleft opener
_WEAK_OPEN_OK = re.compile(r"^so(?:\s+that\b|-called\b)", re.I)          # "So that …" / "so-called" are fine
#   question-as-statement  a short interrogative-opening lead punctuated with a period ("Why not both.")
#                          that wants a question mark, or a rewrite into a plain statement.
_QSTMT = re.compile(r"^(?:why|how|when|where|who|which)\b[^.?!]{0,44}\.$", re.I)
_EXPLETIVE = re.compile(r"^(?:there\s+(?:is|are|was|were|'s|will\s+be|has|have)\b|it\s+(?:is|was|'s)\s+\w+\s+(?:that|to)\b)", re.I)
_WORDY = re.compile(r"\b(in order to|the fact that|due to the fact|at this point in time|for the purpose of|"
                    r"in the event that|in spite of the fact|with regard to|in terms of|a number of)\b", re.I)
_FILLER_WORD = re.compile(r"\b(?:very|really|quite|actually|basically)\b", re.I)
_RUN_ON_WORDS = 45      # one sentence longer than this is a run-on; break it
_CHOPPY_LEN = 7         # a run of 3+ sentences this short or shorter reads choppy; connect them
# Hollow expansionary tack-ons: connective phrases that pad a sentence by naming what something
# "is" (the abstraction, the point, the reason) rather than adding content. Inflation must carry real
# substance (the actual mechanism or consequence), never one of these. Extend as new ones surface.
_TACKON = re.compile(
    r"\b(?:which is (?:exactly|precisely|why|what|the reason|the point|the whole point)"
    r"|and (?:that|this)\b[\w' ]{0,28}?\bis (?:the|a|an|what|why|how|exactly|precisely)"
    r"|this is (?:exactly|precisely) (?:why|what|the)"
    r"|it is worth noting|needless to say|as it turns out|when it comes to"
    r"|at the end of the day|that is to say)\b",
    re.I,
)
# A comma-chained sequential clause run ("X, and Y, then Z", "do X, then do Y, then ..."): two or more
# clause boundaries welded with and/or/then/so reads as a breathless list of steps. Split or subordinate.
# 'or' is in the set so the chain cannot be hidden by swapping one coordinator ("X, results, or Y, so Z").
_ANDTHEN = re.compile(r",\s+(?:and|then|so|or)\b[^.!?:;]*?,\s+(?:and|then|so|or)\b", re.I)
# A bare-and item chain: three article-led items welded by 'and' with no commas ("a role label and a
# system prompt and a tool list"). This is the comma-list dodge in reverse, dropping the commas to evade
# and-then-chain. Narrow on purpose (repeated a/an/the), so it misses no-article chains but never floods.
_BARE_AND = re.compile(
    r"\b(?:a|an|the)\s+[\w-]+(?:\s+[\w-]+){0,2}\s+and\s+(?:a|an|the)\s+[\w-]+(?:\s+[\w-]+){0,2}\s+and\s+(?:a|an|the)\b",
    re.I,
)
_STUB_CONTINUATION = re.compile(r"\b(?:starts? to|begins? to|pays? off|matters? when|works? when)\b", re.I)
_STUB_SUBJECT = re.compile(r"^(?:This|That|The|A|An|Workflow|Agent|Model|Runtime|Loop|Structure)\b")


def antithesis_hits(prose) -> list:
    """(construction, sentence) for each antithesis / numeric-buzz construction, deduped, so the
    sweep can show the exact offending line instead of a bare count. Most patterns are scoped to a
    single sentence; not-X-it-is-Y straddles a sentence break, so it runs on the joined text. A
    repeated-phrase semicolon test was tried and dropped: it could not tell a buzzy mirror from a
    legitimate compare-and-contrast ('the non-vision route sends X; the vision route attaches Y'),
    and flagging good prose is worse than missing one form."""
    out, seen = [], set()

    def add(label, s):
        if (label, s) not in seen:
            seen.add((label, s)); out.append((label, s))

    for s, n in _sentences(prose):
        for name, pat in _ANTI_PATS:
            if name == "not-X-it-is-Y":      # cross-sentence; handled on the joined text below
                continue
            if pat.search(s):
                add(name, s)
        if s.count(";") >= 2:                            # rule-of-three welded into one sentence
            add("triad-semicolons", s)
        if s.count(";") == 1:                            # two short clauses welded by one semicolon AND a negation =
            _a, _b = s.split(";", 1)                      # a do/don't contrast mirror ("Nothing here writes; it measures
            if (len(_WORD.findall(_a)) <= 7 and len(_WORD.findall(_b)) <= 7  # scope."), not a plain parallel caption
                    and re.search(r"\b(?:nothing|never|not|no|cannot|can't|n't|without|neither|none)\b", s, re.I)):
                add("welded-clauses", s)
        if len(_COMMA_NEG.findall(s)) >= 2:              # repeated affirm-then-negate mirror
            add("negate-parallel", s)
        if _DOUBLED.search(s):                           # "again and again" filler doubling
            add("doubled-word", s)
        if len(_PIVOT.findall(s)) >= 2:                  # same transformation verb echoed across clauses
            add("repeated-pivot", s)
        if len([p for p in _PAREN.findall(s) if not _CITE_YEAR.search(p)]) >= 2:  # two short gloss parentheticals (not citations): label-each-side cadence
            add("paired-parenthetical", s)
        if n <= 6 and "," in s and not _TERSE_VERB.search(s) and not _CITE_CAP.match(s):  # verbless short comma fragment = antithesis punch
            add("terse-fragment", s)
        if _WHATLOOKS.search(s):                         # "what looks like X is really Y" reveal-cliche
            add("what-looks-like", s)
        if _STUB_ASSERT.search(s):                       # copular that points/hedges instead of informing
            add("stub-assertion", s)
        if _META_EMPH.search(s):                         # announces its own importance instead of earning it
            add("meta-emphasis", s)
        if _COMMA_NEG.search(s):                         # affirm-then-negate "X, not Y" (even a lone one)
            add("affirm-then-negate", s)
        if _echo_hit(s):                                 # a two-word content phrase echoed within the sentence
            add("echo-aphorism", s)
        if _NEGPAR.search(s):                            # "not only X but Y" / "not X but Y" negate-then-affirm
            add("not-X-but-Y", s)
    text = " ".join([prose] if isinstance(prose, str) else prose)
    for m in _NEG_SPLIT.finditer(text):
        add("not-X-it-is-Y", m.group(0).strip())
    return out


def _skill_list_chunks(body: str) -> list[str]:
    """Extract reader guidance from SKILL lists without treating code samples as prose."""
    body = _SKILL_CATALOG.sub(" ", body)
    chunks = []
    for match in _SKILL_ITEM.finditer(body):
        item = re.sub(r"<(?:code|pre)\b.*?</(?:code|pre)>", " ", match.group(1), flags=re.I | re.S)
        text = html.unescape(re.sub(r"\s+", " ", _TAG.sub(" ", item))).strip()
        # File catalogs and nav labels are list-shaped interface chrome, not sentences. Keep list
        # guidance only when it is punctuated as prose.
        if (text and " " in text and re.search(r"[.!?]", text)
                and len(re.findall(r"\b[A-Za-z]{2,}\b", text)) >= 4):
            chunks.append(text)
    return chunks


def pattern_contract() -> list[str]:
    """Return detector misses that would reopen known numeric-cadence gaps."""
    cases = {
        "One workflow idea, two implementations": "numeric-antithesis",
        "Four stages, one research result": "numeric-antithesis",
        "4 workers, 4 contexts": "numeric-antithesis",
        "One model call, one deterministic step, one specialist loop": "repeated-count-list",
    }
    misses = []
    for text, expected in cases.items():
        kinds = {kind for kind, _ in antithesis_hits(text)}
        if expected not in kinds:
            misses.append(f"{expected}: {text}")
    controls = (
        "Every exercise reaches one of three self-contained systems, all from the browser.",
    )
    for text in controls:
        kinds = {kind for kind, _ in antithesis_hits(text)}
        noisy = kinds & {"numeric-antithesis", "repeated-count-list"}
        if noisy:
            misses.append(f"false positive {sorted(noisy)}: {text}")
    canonical = '<p class="lead" id="course-abstract">locked copy</p><p>editable copy</p>'
    canonical_clean = _IMMUTABLE_CANON.sub(" ", canonical)
    if "locked copy" in canonical_clean or "editable copy" not in canonical_clean:
        misses.append("immutable course abstract exclusion")
    skill_sample = "<ol><li>Check the learner-facing result. Open its evidence link.</li></ol>"
    if _skill_list_chunks(skill_sample) != ["Check the learner-facing result. Open its evidence link."]:
        misses.append("SKILL.html list-prose extraction")
    if (TASK1 / "scripts/compliance/SKILL.html").is_file() and not any(
            rel == "scripts/compliance/SKILL.html" for _, rel in _pages("ship")):
        misses.append("SKILL.html default prose scope")
    course_paths = {rel for _, rel in _pages("course")}
    expected_course_paths = {
        path.relative_to(TASK1).as_posix()
        for path in (TASK1 / "web/nemoclaw").glob("[0-9][0-9][a-z]-*.html")
    }
    expected_course_paths.add("web/nemoclaw/index.html")
    if course_paths != expected_course_paths or any(path.endswith("SKILL.html") for path in course_paths):
        misses.append("canonical learner-course prose scope")
    mechanical_slot = (
        "Start with How this project uses it. Included in the course means learners receive the code. "
        "Used only to build the course, Used only to check the course, and Optional authoring tool "
        "mean learners do not receive that package. Use Where it comes from only when you need more "
        "detail. It tells you whether this project chose the package directly, another package brought "
        "it in, or it belongs to a particular build, check, or authoring task. License or terms shows "
        "the exact recorded result. Combine choices naturally. The table and download always match."
    )
    mechanical_metrics = metrics(mechanical_slot)
    if not mechanical_metrics or _score(mechanical_metrics) < FLAG_AT:
        misses.append("mechanical instructional-slot detection")
    answer_echoes = _vacuous_meta_text(
        "What happened to the source gives the answer. How it was used names the recorded action."
    )
    echo_phrases = {phrase.lower() for phrase, _ in answer_echoes}
    if not {"gives the answer", "names the recorded action"} <= echo_phrases:
        misses.append("answer-announcing redundancy detection")
    return misses


def grammar_hits(prose) -> list:
    """(rule, sentence) for each plain grammar/composition mistake, the kind a teacher marks in red.
    These catch prose that was patched to clear a metric rather than rewritten, so each trigger is a
    rewrite candidate, not a word swap:
      weak-opener     a sentence opening on a conjunction or filler (And/But/Or/So/Basically/...).
      expletive       a weak 'There is/are …' or 'It is X that …' opener that buries the subject.
      wordy-phrase    'in order to', 'the fact that', 'due to the fact', and friends.
      run-on          a single sentence past ~45 words; break it.
      choppy-run      3+ very short sentences in a row that should be connected.
      filler-word     'very', 'really', 'quite', 'actually', 'basically': cut it.
      tack-on         a hollow expansionary connector ('which is exactly', 'and that X is the …') that
                      pads the sentence by naming what something is instead of adding substance.
      and-then-chain  a comma-welded 'X, and Y, then Z' step sequence; split it or subordinate.
      bare-and-chain  three article-led items welded by bare 'and' ('a X and a Y and a Z'); make it a list.
      stub-split      a short setup sentence followed by a continuation sentence that should have
                      been one subordinate sentence."""
    out, seen = [], set()

    def add(label, s):
        k = (label, s[:60])
        if k not in seen:
            seen.add(k); out.append((label, s))

    sents = _sentences(prose)
    lens = [n for _, n in sents]
    for s, n in sents:
        if _WEAK_OPEN.match(s) and not _WEAK_OPEN_OK.match(s):
            add("weak-opener", s)
        if n <= 8 and _QSTMT.match(s.strip()):
            add("question-as-statement", s)
        if _EXPLETIVE.match(s):
            add("expletive", s)
        if _WORDY.search(s):
            add("wordy-phrase", s)
        if n > _RUN_ON_WORDS:
            add("run-on", s)
        if _FILLER_WORD.search(s):
            add("filler-word", s)
        if _TACKON.search(s):
            add("tack-on", s)
        if _ANDTHEN.search(s):
            add("and-then-chain", s)
        if _BARE_AND.search(s):
            add("bare-and-chain", s)
    for (a, na), (b, nb) in zip(sents, sents[1:]):
        if 6 <= na <= 13 and 8 <= nb <= 36 and _STUB_SUBJECT.match(b) and _STUB_CONTINUATION.search(b):
            add("stub-split", f"{a} {b}")
    i = 0                                                 # runs of consecutive very-short sentences
    while i < len(sents):
        j = i
        while j < len(sents) and lens[j] <= _CHOPPY_LEN:
            j += 1
        if j - i >= 3:
            add("choppy-run", " ".join(x for x, _ in sents[i:j]))
        i = j + 1 if j > i else i + 1
    return out


_MD_LIST_START = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_MD_SKIP = re.compile(r"^\s*(?:#{1,6}\s|[>|])")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]+\)")


def _markdown_chunks(body: str) -> list[str]:
    """Return complete Markdown paragraphs and list items without orphaning wrapped lines."""
    chunks: list[str] = []
    paragraph: list[str] = []
    lines = body.splitlines()

    def flush() -> None:
        if paragraph:
            chunks.append(_MD_LINK.sub(r"\1", " ".join(paragraph)))
            paragraph.clear()

    index = 0
    while index < len(lines):
        line = lines[index]
        item = _MD_LIST_START.match(line)
        if item:
            flush()
            parts = [item.group(1).strip()]
            index += 1
            while index < len(lines):
                continuation = lines[index]
                if not continuation.strip() or _MD_LIST_START.match(continuation):
                    break
                if re.match(r"^\s{2,}\S", continuation):
                    parts.append(continuation.strip())
                    index += 1
                    continue
                break
            chunks.append(_MD_LINK.sub(r"\1", " ".join(parts)))
            continue
        if not line.strip() or _MD_SKIP.match(line):
            flush()
        else:
            paragraph.append(line.strip())
        index += 1
    flush()
    return chunks


def narrative(f: Path) -> list:
    """The authored narrative of a page as a list of paragraph chunks (each <p>, or each markdown
    paragraph). Kept as separate chunks so a paragraph break counts as a sentence boundary and a
    list-/cell-lead-in colon at a paragraph's end is not mistaken for a welded mid-sentence clause.
    Lists, code, SVG, and markup are removed from course pages. Reader guidance in SKILL.html list
    items is retained, while code samples inside those items are removed."""
    raw, suf = lp._read_for_links(f)
    body = lp._strip_noncontent(raw, suf)
    if suf in (".html", ".htm"):
        body = _SVG.sub(" ", body)
        body = _IMMUTABLE_CANON.sub(" ", body)
        for _c in _CARDS:             # drop reference/navigation tile captions (not narrative flow)
            body = _c.sub(" ", body)
        if f.name == "SKILL.html":
            body = _SKILL_CATALOG.sub(" ", body)
        ordered_chunks = [(m.start(), _TAG.sub(" ", m.group(1))) for m in _PARA.finditer(body)]
        if f.name == "SKILL.html":
            for m in _SKILL_ITEM.finditer(body):
                for item in _skill_list_chunks(f"<li>{m.group(1)}</li>"):
                    ordered_chunks.append((m.start(), item))
        for m in _CALLOUT.finditer(body):                 # prose callouts (not <p>): scan their running text too
            inner = re.sub(r"<p\b[^>]*>.*?</p>", " ", m.group(1), flags=re.I | re.S)   # inner <p> counted by the pass above
            inner = re.sub(r"<(?:ul|ol|table)\b.*?</(?:ul|ol|table)>", " ", inner, flags=re.I | re.S)  # lists are enumerative
            ordered_chunks.append((m.start(), _TAG.sub(" ", inner)))
        raw_chunks = [text for _, text in sorted(ordered_chunks)]
    else:
        raw_chunks = _markdown_chunks(body)
    chunks = []
    for c in raw_chunks:
        c = html.unescape(re.sub(r"\s+", " ", c)).strip()
        if c:
            chunks.append(c)
    return chunks


_BLOCK = re.compile(r"<h[1-3]\b|<p\b[^>]*>|<ul\b|<ol\b|<table\b|<figure\b|<svg\b|<img\b|<pre\b"
                    r"|<div\b[^>]*class=\"[^\"]*callout|<div\b[^>]*id=\"[a-z0-9-]+\"", re.I)
_COLON_LED = re.compile(r"(?:^|[.!?]\s+)(?:The|A|An|Each|Every|One)\s+[\w ,'-]{2,45}?:")
_LIST_LEAD = re.compile(r"^(?:The|A|An|Each|Every|One|This|That)\b")
_DEFINITIONAL = re.compile(r"\b(?:is|are|means|gives|runs|stores|wraps|starts|holds|carries|calls|routes|returns)\b", re.I)


def _parallel_list_candidate(run: list[str]) -> str | None:
    """Return a detail string when consecutive prose blocks have the same teaching shape and
    should probably become a segued-into focused list. Kept narrow: it needs three nearby
    short paragraphs with lead-in grammar, similar lengths, and no existing list break."""
    if len(run) < 3:
        return None
    samples = []
    for text in run:
        words = _WORD.findall(text)
        if not (12 <= len(words) <= 90):
            return None
        first = _sentences(text)[0][0] if _sentences(text) else text
        if not (_LIST_LEAD.search(first) and _DEFINITIONAL.search(first)):
            return None
        samples.append(first[:72])
    lens = [len(_WORD.findall(x)) for x in run]
    if max(lens) - min(lens) > 55:
        return None
    return f"{len(run)} adjacent similarly shaped paragraphs; introduce the group, then make a focused list (examples: {samples[0]!r}; {samples[1]!r})"


def _list_density_findings(bl: list[tuple[str, str]]) -> list:
    """Find list clusters that are too close. A pair is handled by list-pileup; this catches
    section-scale list density where the fix is usually to refactor the surrounding section, not
    shuffle one paragraph."""
    out = []
    section = []
    for kind, text in bl + [("heading", "")]:
        if kind == "heading":
            out.extend(_list_density_section(section))
            section = []
        else:
            section.append((kind, text))
    return out


def _list_density_section(section: list[tuple[str, str]]) -> list:
    content = [(k, t) for k, t in section if k in {"para", "para_styled", "list", "callout", "figure", "table", "cell"}]
    list_pos = [i for i, (k, _) in enumerate(content) if k == "list"]
    if len(list_pos) < 3:
        return []
    out = []
    span = list_pos[-1] - list_pos[0] + 1
    if span <= 10:
        out.append(("list-density", f"{len(list_pos)} lists within {span} nearby content blocks; refactor the section so lists do distinct jobs instead of stacking"))
    for a, b, c in zip(list_pos, list_pos[1:], list_pos[2:]):
        if c - a <= 7:
            out.append(("list-density", "three lists appear within seven content blocks; merge, split the section, or convert one list back into prose"))
            break
    return out


def _page_list_density(bl: list[tuple[str, str]]) -> list:
    content = [(k, t) for k, t in bl if k in {"para", "para_styled", "list", "callout", "figure", "table", "cell"}]
    pos = [i for i, (k, _) in enumerate(content) if k == "list"]
    if len(pos) < 7:
        return []
    gaps = [b - a for a, b in zip(pos, pos[1:])]
    tight = sum(1 for g in gaps if g <= 4)
    if tight >= 4:
        return [("list-density", f"{len(pos)} lists on the page, with {tight} close gaps; refactor at section scale so lists alternate with explanatory prose")]
    return []


_ENUM_INTRO = re.compile(r"\b(?:two|three|four|five|six|several|many|parts|steps|patterns|mechanisms|axes|knobs|conditions|questions|arguments)\b", re.I)


def _heading_para_candidates(bl: list[tuple[str, str]]) -> list:
    out = []
    i = 0
    while i < len(bl) - 1:
        if bl[i][0] != "heading" or bl[i + 1][0] not in {"para", "para_styled"}:
            i += 1
            continue
        j = i
        paras = []
        while j < len(bl) - 1 and bl[j][0] == "heading" and bl[j + 1][0] in {"para", "para_styled"}:
            txt = bl[j + 1][1]
            nw = len(_WORD.findall(txt))
            if not (12 <= nw <= 85):
                break
            paras.append(txt)
            j += 2
        if len(paras) >= 3:
            intro = " ".join(t for _, t in bl[max(0, i - 4):i] if t)
            if _ENUM_INTRO.search(intro):
                out.append(("list-candidate", f"{len(paras)} short heading-plus-paragraph entries follow an enumerating lead-in; make them a focused list, or expand each subsection enough to earn its heading"))
        i = max(j, i + 1)
    return out


def _strip_between_ids(body: str, start_id: str, end_id: str) -> str:
    start = re.search(r'<div\b[^>]*\bid="' + re.escape(start_id) + r'"[^>]*>', body, re.I)
    end = re.search(r'<div\b[^>]*\bid="' + re.escape(end_id) + r'"[^>]*>', body, re.I)
    if start and end and start.start() < end.start():
        return body[:start.start()] + " " + body[end.start():]
    return body


def _strip_div_by_id(body: str, div_id: str) -> str:
    m = re.search(r'<div\b[^>]*\bid="' + re.escape(div_id) + r'"[^>]*>', body, re.I)
    if not m:
        return body
    depth = 1
    cur = m.end()
    tag = re.compile(r'</?div\b[^>]*>', re.I)
    for tm in tag.finditer(body, cur):
        if tm.group(0).startswith('</'):
            depth -= 1
        else:
            depth += 1
        cur = tm.end()
        if depth == 0:
            return body[:m.start()] + " " + body[cur:]
    return body[:m.start()]


def _strip_divs_by_class(body: str, class_word: str) -> str:
    out = []
    pos = 0
    pat = re.compile(r'<div\b[^>]*\bclass="[^"]*\b' + re.escape(class_word) + r'\b[^"]*"[^>]*>', re.I)
    while True:
        m = pat.search(body, pos)
        if not m:
            out.append(body[pos:])
            break
        out.append(body[pos:m.start()])
        depth = 1
        cur = m.end()
        tag = re.compile(r'</?div\b[^>]*>', re.I)
        for tm in tag.finditer(body, cur):
            if tm.group(0).startswith('</'):
                depth -= 1
            else:
                depth += 1
            cur = tm.end()
            if depth == 0:
                break
        pos = cur
    return " ".join(out)


def _strip_reference_scaffolds(body: str) -> str:
    """Remove non-narrative catalogs before structural rhythm checks.

    Reference hubs and learning-path card grids are navigation/catalog surfaces. Their
    close lists are intentional metadata, not a prose section that needs refactoring.
    """
    body = _strip_between_ids(body, "refs", "learning-path")
    body = _strip_div_by_id(body, "learning-path")
    body = _strip_divs_by_class(body, "references")
    body = _strip_divs_by_class(body, "card-grid")
    body = _strip_divs_by_class(body, "layers")
    return body


def _blocks(f: Path):
    """The page body as an ordered list of (kind, text) blocks, so structural rhythm (not just prose)
    can be judged. Code, SVG, and scripts are removed first: their colons/braces are syntax, not
    prose. A bare <p> is narrative flow; a <p style=…>/<p class=…> is a card/caption/lead and is NOT
    a narrative-run member. kinds: heading | para | para_styled | list | figure | callout | table |
    code | cell."""
    raw, suf = lp._read_for_links(f)
    if suf not in (".html", ".htm"):
        return []
    body = raw[raw.lower().find("<body"):] if "<body" in raw.lower() else raw
    body = _strip_reference_scaffolds(body)
    body = _SVG.sub(" ", body)
    body = re.sub(r"<pre\b.*?</pre>", " ", body, flags=re.S | re.I)
    body = without_elements(body, {"script"})
    if f.name == "SKILL.html":
        body = _SKILL_CATALOG.sub(" ", body)
    # List bodies are enumerative by structure. Preserve the list block, but keep
    # nested headings and paragraphs from being counted as narrative flow.
    body = re.sub(r"<li\b[^>]*>.*?</li>", "<li></li>", body, flags=re.S | re.I)
    out = []
    for m in _BLOCK.finditer(body):
        t = m.group(0).lower()
        if t.startswith("<h"):
            kind = "heading"; text = ""
        elif t.startswith("<p"):
            kind = "para_styled" if ("style" in t or "class" in t) else "para"
            end = body.find("</p>", m.end()); seg = body[m.end():end] if end > 0 else ""
            seg = re.sub(r"<code\b.*?</code>", " ", seg, flags=re.S | re.I)   # inline code is syntax, not prose
            text = html.unescape(re.sub(r"\s+", " ", _TAG.sub(" ", seg))).strip()
        else:
            text = ""
            kind = ("list" if t.startswith(("<ul", "<ol")) else "table" if t.startswith("<table")
                    else "code" if t.startswith("<pre") else "callout" if "callout" in t
                    else "figure" if t.startswith(("<figure", "<svg", "<img")) else "cell")
        out.append((kind, text))
    return out


def structure_findings(f: Path) -> list:
    """(kind, detail) for STRUCTURAL monotony a sentence-level metric cannot see. Three precise tells,
    each measured to fire on real defects only (a per-paragraph colon/semicolon count was rejected:
    it flags code, reference cards, and ordinary good prose using normal punctuation at the same
    threshold as the one bad paragraph, so it cannot tell signal from noise).
      prose-run        a run of narrative <p> with no list/figure/callout/code/heading break: 3+
                       paragraphs, or 2+ where each is a long (>=4-sentence) block. Reads script-like.
      buried-list      one paragraph carrying 2+ parallel colon-led clauses ("The index is …: … The
                       live request is …: …"): an enumeration hiding in prose that wants to be a list.
      definition-dump  one paragraph defining three or more named terms with is/are/means: a glossary
                       hiding in prose that should become a focused list.
      list-pileup      two lists with only one or two short paragraphs between them: list-heavy, no
                       prose to pace them.
      list-candidate   three adjacent similarly shaped prose blocks that probably want a lead-in
                       sentence plus a focused list.
      list-density     three or more lists packed into one short section: a local shuffle is not
                       enough; refactor the surrounding section so lists do distinct jobs.
      wall-of-text     one paragraph (lead included) of 7+ sentences or 130+ words: a visually bereft
                       block a reader skips. Split it, or lift part into a list or callout."""
    bl = _blocks(f)
    out = []
    for kind, text in bl:
        if kind in ("para", "para_styled") and text:
            nw, ns = len(_WORD.findall(text)), len(_sentences(text))
            if ns >= 7 or nw >= 130:
                out.append(("wall-of-text", f"one paragraph of {nw} words / {ns} sentences; split it, or lift part into a list or callout"))
            defs = re.findall(r"(?:^|[.!?]\s+)(?:[A-Z][A-Za-z0-9 /+-]{2,48})\s+(?:is|are|means)\s+", text)
            if len(defs) >= 3 and nw >= 55:
                out.append(("definition-dump", f"{len(defs)} term definitions packed into one paragraph; introduce the group, then make a focused list"))
    run = []
    for kind, text in bl + [("heading", "")]:               # sentinel flushes a trailing run
        if kind == "para":
            run.append(text)
            continue
        if len(run) >= 3 or (len(run) >= 2 and sum(1 for c in run if len(_sentences(c)) >= 4) >= 2):
            out.append(("prose-run", f"{len(run)} narrative paragraphs with no list, figure, callout, or break between them"))
        for i in range(0, max(0, len(run) - 2)):
            detail = _parallel_list_candidate(run[i:i + 3])
            if detail:
                out.append(("list-candidate", detail))
                break
        run = []
    for kind, text in bl:
        if kind.startswith("para") and len(_COLON_LED.findall(text)) >= 2:
            out.append(("buried-list", f"{len(_COLON_LED.findall(text))} parallel colon-led clauses in one paragraph; make it a list"))
    idx = [i for i, (k, _) in enumerate(bl) if k == "list"]
    for a, b in zip(idx, idx[1:]):
        between = bl[a + 1:b]
        if between and all(k.startswith("para") for k, _ in between) and len(between) <= 2 \
           and all(len(_sentences(t)) <= 2 for _, t in between):
            out.append(("list-pileup", "two lists separated only by a sentence or two; space them with prose or merge"))
    out += _heading_para_candidates(bl)
    out += _list_density_findings(bl)
    out += _page_list_density(bl)
    out += _grid_findings(f)
    return out


def _grid_cols(css: str, cls: str) -> int | None:
    m = re.search(r"\." + re.escape(cls) + r"\s*\{[^}]*grid-template-columns:\s*([^;}]+)", css)
    if not m:
        return 2
    if re.search(r"\brepeat\(\s*auto-(?:fill|fit)\b", m.group(1)):
        return None
    rep = re.search(r"repeat\(\s*(\d+)", m.group(1))
    return int(rep.group(1)) if rep else max(2, len(m.group(1).split()))


def _grid_findings(f: Path) -> list:
    """Card-grid layout tells. A grid is a styled tile layout, not prose, so it is scanned on the raw
    HTML. Three failure modes:
      orphan-grid    item count does not fill the columns, leaving a floating incomplete final row
                     (5 cards in 2 columns). Use a count that fills the grid, or make it a list.
      linkless-cards a grid of titled reference tiles with no link in any card: it looks clickable but
                     points nowhere. Make it a list, or give each tile its documentation URL.
      flashy-page    a page built mostly of cards and button-styled CTAs (a 'buzz pile'): convert the
                     reference grids to plain lists with inline links so the page is scannable."""
    raw, suf = lp._read_for_links(f)
    if suf not in (".html", ".htm"):
        return []
    css = "\n".join(re.findall(r"<style>(.*?)</style>", raw, re.S | re.I))
    body = raw[raw.lower().find("<body"):] if "<body" in raw.lower() else raw
    out = []
    for gm in re.finditer(r'<div\b[^>]*class="([\w-]*(?:grid|pair))\b[^"]*"[^>]*>', body):
        cls = gm.group(1)
        nxt = body.find("<h2", gm.end())
        seg = body[gm.end(): nxt if nxt > 0 else gm.end() + 4000]
        ncards = len(re.findall(r'class="[\w-]*card\b', seg))
        if ncards < 2:
            continue
        nlinks = len(re.findall(r"<a\b[^>]*\bhref", seg))   # any anchor with href, regardless of attr order
        cols = _grid_cols(css, cls)
        if cols is not None and ncards > cols and ncards % cols != 0:
            out.append(("orphan-grid", f"a {cls} of {ncards} cards in {cols} columns leaves a floating incomplete row; fill the grid or make it a list"))
        if nlinks == 0:
            out.append(("linkless-cards", f"a {cls} of {ncards} titled cards with no link in any of them; make it a list, or give each its documentation URL"))
    nbtn = len(re.findall(r'class="(?:btn|action-btn)\b', body))
    evidence_cards = re.findall(
        r'<article\b[^>]*class="[^"]*\bpv-card\b[^"]*"[^>]*>(.*?)</article>',
        body, re.S | re.I,
    )
    evidence_count = sum(
        1 for card in evidence_cards
        if ("pv-prev" in card or "md-wrap" in card) and "pv-meta" in card
        and re.search(r"<a\b[^>]*\bhref", card)
    )
    ncard = len(re.findall(r'class="[\w-]*card\b', body)) - evidence_count
    if nbtn >= 10 or ncard >= 10:
        out.append(("flashy-page", f"{ncard} cards and {nbtn} button-styled links on one page reads as a buzz pile; convert the reference grids to plain lists with inline links"))
    return out


# ── Brand naming: canonical casing of product names in PROSE (not code, URLs, paths, model-ids) ──
# Mined from the Elements Vale "Branding" rule. Bare all-lowercase CLI / slug names (openclaw,
# openshell, nemoclaw) are legitimate identifiers and are NOT flagged; only wrong-CASE forms and the
# always-caps brand are. Lookarounds exclude slugs / paths / emails (03b-openclaw, web/nemoclaw,
# .openclaw). A 0-finding regression guard today: it locks brand casing so future drift cannot ship.
_BRAND_CODE_HTML = re.compile(r"<(script|style|pre|code)\b[^>]*>.*?</\1>", re.I | re.S)
_BRAND_CODE_MD = re.compile(r"```.*?```|`[^`\n]*`", re.S)
_BRAND_URL = re.compile(r"https?://\S+|\b[\w.-]+\.(?:com|org|io|dev|ai|net|gov|html|md|js|css|py)\b[^\s<>\"']*", re.I)
_BRAND_PATH = re.compile(r"\b[\w.-]*/[\w./-]+|\.\w[\w./-]*")     # web/nemoclaw, nvidia/nemotron-..., .openclaw/...
_BRAND_LA, _BRAND_RA = r"(?<![\w./@-])", r"(?!\.\w)(?![\w@/-])"   # RA allows a trailing sentence period, still blocks path-dots (.workspace) and slashes
_BRAND_RULES = [
    ("NVIDIA",    re.compile(_BRAND_LA + r"(?:nvidia|Nvidia|NVidia)" + _BRAND_RA)),
    ("OpenClaw",  re.compile(_BRAND_LA + r"(?:Openclaw|openClaw|OPENCLAW)" + _BRAND_RA)),
    ("OpenShell", re.compile(_BRAND_LA + r"(?:Openshell|openShell|OPENSHELL)" + _BRAND_RA)),
    ("NemoClaw",  re.compile(_BRAND_LA + r"(?:Nemoclaw|nemoClaw|NEMOCLAW)" + _BRAND_RA)),
    ("Nemotron",  re.compile(_BRAND_LA + r"(?:nemotron|NemoTron|NEMOTRON)" + _BRAND_RA)),
]


def branding_hits(f: Path) -> list:
    """(wrong, canonical, context) for each product / brand name in PROSE that is not in canonical
    casing. Code, scripts, URLs, paths, and model-ids are stripped first, so a lowercase CLI name
    ('openshell policy get') or a path ('web/nemoclaw') is never flagged, only prose miscasings are."""
    raw, suf = lp._read_for_links(f)
    if not raw:
        return []
    t = _BRAND_CODE_HTML.sub(" ", raw)
    t = _BRAND_CODE_MD.sub(" ", t)
    t = _TAG.sub(" ", t)
    t = _BRAND_URL.sub(" ", t)
    t = _BRAND_PATH.sub(" ", t)
    out, seen = [], set()
    for canon, pat in _BRAND_RULES:
        for m in pat.finditer(t):
            w = m.group(0)
            ctx = re.sub(r"\s+", " ", t[max(0, m.start() - 40):m.start() + len(w) + 25]).strip()
            k = (w, canon)
            if k not in seen:
                seen.add(k); out.append((w, canon, ctx))
    return out


def graphics(f: Path) -> list:
    """Text rendered INSIDE figures: each <svg> (its <text> labels joined) and each <figcaption>.
    narrative() strips these out, but the redundancy check needs them to compare a figure's wording
    against the prose around it. A figure that just restates the sentence beside it adds nothing, so
    surfacing that overlap is the point. Only figures with enough words to be a phrase are kept."""
    raw, suf = lp._read_for_links(f)
    if suf not in (".html", ".htm"):
        return []
    units = []
    for sm in _SVG.finditer(raw):
        txt = " ".join(_TAG.sub(" ", t) for t in _SVGTEXT.findall(sm.group(0)))
        txt = html.unescape(re.sub(r"\s+", " ", txt)).strip()
        if len(_WORD.findall(txt)) >= 4:
            units.append(txt)
    for cm in _FIGCAP.finditer(raw):
        txt = html.unescape(re.sub(r"\s+", " ", _TAG.sub(" ", cm.group(1)))).strip()
        if len(_WORD.findall(txt)) >= 4:
            units.append(txt)
    return units


def graphic_prose(f: Path) -> list:
    """Caption-like sentences rendered INSIDE figures: each individual <text> or <figcaption> that
    reads as a sentence (>= 8 words), kept SEPARATE rather than joined. graphics() joins every label
    in a figure into one redundancy blob, which destroys sentence structure; this keeps the long
    caption lines intact so the buzz detectors can read them. A figure caption is authored prose and
    earns the same scrutiny as a paragraph, so a buzzy caption ('perceiving becomes observing a tool
    result, acting becomes a tool call') is surfaced like any other. Short node labels are excluded;
    only the grammar/buzz-bearing caption sentences are returned."""
    raw, suf = lp._read_for_links(f)
    if suf not in (".html", ".htm"):
        return []
    units = []
    for sm in _SVG.finditer(raw):
        for tm in _SVGTEXT.findall(sm.group(0)):
            txt = html.unescape(re.sub(r"\s+", " ", _TAG.sub(" ", tm))).strip()
            if len(_WORD.findall(txt)) >= 8:
                units.append(txt)
    for cm in _FIGCAP.finditer(raw):
        txt = html.unescape(re.sub(r"\s+", " ", _TAG.sub(" ", cm.group(1)))).strip()
        if len(_WORD.findall(txt)) >= 8:
            units.append(txt)
    return units


def _bag(text: str) -> set:
    """Content-word bag for one unit: lowercased words >= 3 letters, function words dropped, a
    trailing plural -s folded so 'tools' and 'tool' match. This is the bag-of-words an overlap is
    measured on, so a near-restatement with minor wording changes still registers."""
    out = set()
    for w in _WORD.findall(text.lower()):
        if len(w) >= 3 and w not in _STOP:
            out.add(w[:-1] if len(w) > 4 and w.endswith("s") else w)
    return out


def redundancy(prose_chunks, graphic_units):
    """Phrase-level (bag-of-words) redundancy. A unit whose content words are almost entirely the
    same as another nearby unit is a restatement that pads the page. Two targets:
      graphic-echoes-prose  a figure's label/caption text duplicates a sentence beside it (with
                            minor deviations), so the diagram carries no information the prose lacks.
      sentence-restated     one sentence repeats another's content words in different order.
    Containment (shared / smaller bag) is used, not Jaccard, so a short figure label fully echoed by
    a long sentence still scores high. The bar is high and a word floor applies, so incidental shared
    keywords ('agent', 'model') do not trip it; only a genuine near-duplicate does. Returns
    (kind, a, b) triples for the report."""
    prose = [(s, _bag(s)) for s, n in _sentences(prose_chunks) if n >= 4]
    gfx = [(g, _bag(g)) for g in graphic_units]

    def contain(a, b):
        return len(a & b) / min(len(a), len(b)) if a and b else 0.0

    hits, seen = [], set()
    for gt, gb in gfx:                                    # a figure that restates the prose beside it
        for pt, pb in prose:
            # Both sides must be a substantial phrase (>= 6 content words) with high overlap, so a
            # figure label sharing one noun with a short sentence ("The tool call is the action
            # interface.") no longer trips it; only a near word-for-word restatement does.
            if min(len(gb), len(pb)) >= 6 and contain(gb, pb) >= 0.8:
                k = ("g", gt[:50])
                if k not in seen:
                    seen.add(k); hits.append(("graphic-echoes-prose", gt, pt))
                break
    for i in range(len(prose)):                           # one sentence restating another
        for j in range(i + 1, len(prose)):
            a, b = prose[i][1], prose[j][1]
            if min(len(a), len(b)) >= 6 and contain(a, b) >= 0.8:
                hits.append(("sentence-restated", prose[i][0], prose[j][0]))
    return hits


def _sentences(prose):
    """(sentence, word-count) pairs. Accepts a chunk list (paragraph breaks are sentence
    boundaries) or a single string."""
    chunks = [prose] if isinstance(prose, str) else prose
    out = []
    for ch in chunks:
        for p in _SENT_SPLIT.split(ch):
            p = p.strip()
            n = len(_WORD.findall(p))
            if n >= 2:
                out.append((p, n))
    return out


_HEADING = re.compile(r"<(h[1-3])\b[^>]*>(.*?)</\1>", re.I | re.S)
_LI = re.compile(r"<li\b[^>]*>(.*?)</li>", re.I | re.S)
# Buzz kinds that are real tells ANYWHERE (heading, list item, card, caption), vs prose-only ones.
# terse-fragment is excluded outside <p>: a heading or list item is terse by design, not a buzz punch.
_NONPROSE_DROP = {"terse-fragment"}


def nonprose_buzz(f: Path) -> list:
    """Buzz/numeric/antithesis tells in authored text OUTSIDE <p>: headings, list items, and reference
    cards. The same failure modes ("Five agents, one application layer", "one X, many Y") show up in a
    heading or a card just as in a sentence, and the <p>-only scan missed them. Returns dicts with a
    `where` class (heading | list | card) so headings can be judged as their own class and a buzzy
    heading can flag its section (blast radius). Headings/list items skip terse-fragment (terse by
    design); code, svg, and scripts are stripped first."""
    raw, suf = lp._read_for_links(f)
    if suf not in (".html", ".htm"):
        return []
    out, seen = [], set()

    def scan(text, where):
        text = html.unescape(re.sub(r"\s+", " ", _TAG.sub(" ", re.sub(r"<code\b.*?</code>", " ", text, flags=re.S | re.I)))).strip()
        if not text:
            return
        for k, s in antithesis_hits(text):
            if k in _NONPROSE_DROP:
                continue
            key = (where, k, s)
            if key not in seen:
                seen.add(key); out.append({"where": where, "kind": k, "sentence": s})

    # Canvas documentation lives in <script>: the human-readable intro/summary/caption/aria strings
    # and @doc comments of a mountCanvasFlow / mountDiagram / helper spec. It is authored prose a
    # student reads, so it gets the same buzz scan as the page body, not a free pass for being in JS.
    body = raw[raw.lower().find("<body"):] if "<body" in raw.lower() else raw
    for script in raw_text_blocks(body, "script"):
        js = script.body
        for fm in re.finditer(
            r'\b(?:intro|summary|caption|aria|blurb)\s*:\s*(?:"((?:\\.|[^"\\])*)"|\'((?:\\.|[^\'\\])*)\'|`((?:\\.|[^`\\])*)`)',
            js,
            re.S,
        ):
            scan(next(value for value in fm.groups() if value is not None).replace("\\n", " "), "canvas")
        for dm in re.finditer(r"@doc\b(.*?)\*/", js, re.S):
            scan(dm.group(1), "canvas")
    # Body: headings, list items, cards (code/svg/scripts stripped so their syntax is not prose).
    body = _SVG.sub(" ", body)
    body = re.sub(r"<pre\b.*?</pre>", " ", body, flags=re.S | re.I)
    body = without_elements(body, {"script"})
    for m in _HEADING.finditer(body):
        scan(m.group(2), "heading")
    # list items and reference cards: scan the ones that are NOT inside a heading (already covered)
    for m in _LI.finditer(body):
        if f.name == "SKILL.html" and not _skill_list_chunks(f"<li>{m.group(1)}</li>"):
            continue
        scan(m.group(1), "list")
    for m in re.finditer(r'<div\b[^>]*class="[\w-]*card[\w-]*"[^>]*>(.*?)</div>', body, re.S | re.I):
        scan(m.group(1), "card")
    return out


_COMMA_INTERRUPT = re.compile(
    r",\s+[^,]{8,70},\s+(?:is|are|was|were|will|would|can|could|comes?|gives?|makes?|takes?|"
    r"becomes?|stays?|remains?|means?|does)\b", re.I)


def comma_interruptions(f: Path) -> list:
    """Sentences where a comma-bounded clause splits the subject from its verb ('the fan-out you see,
    and the fresh context each sub-agent gets, is the mitigation'). A raw comma count is no good (a
    clean five-item list has many commas and reads fine); this targets the hard-to-parse interruption.
    Advisory / judgment: a short appositive can be fine, so it surfaces rather than blocks."""
    return [s for c in narrative(f) for s, _ in _sentences(c) if _COMMA_INTERRUPT.search(s)]


def close_repeats(f: Path) -> list:
    """(word, sentence) where a content word (>=5 letters) repeats within five words of itself, with
    no 'and/or/but' between the two (which would mark a deliberate parallel). A clumsy close echo
    ("many patterns that leverage ideas from both patterns") that reads better lightened. Advisory /
    judgment: a technical term repeated on purpose is fine, so this surfaces rather than blocks."""
    out = []
    for c in narrative(f):
        for s, _ in _sentences(c):
            low = [w.lower() for w in _WORD.findall(s)]
            last = {}
            for i, w in enumerate(low):
                if len(w) >= 5 and w not in _STOP:
                    if w in last and i - last[w] <= 5 and not (set(low[last[w] + 1:i]) & {"and", "or", "nor", "but"}):
                        out.append((w, s)); break
                    last[w] = i
    return out


# ── Higher-scrutiny structural signals ───────────────────────────────────────
# The rhythm score (cv, triads, anaphora) catches uniform CADENCE but is blind to the over-writing
# that pervades AI-drafted course prose: verbs deferred behind copulas, one actor named three times
# in a breath, clause piles, padding, and unread-but-shipped cell-code comments. These detectors
# raise the scrutiny so every page surfaces concrete instances rather than passing on cadence alone.

# Deferred copula: the verb hides behind a copular abstraction. "X is what lets Y" for "X lets Y",
# "that is what keeps ...", "what an always-on agent is for". The layer reads heavier than the
# direct statement and recurs across the course as a machine tic; lead with the verb and it goes.
_DEFER_COPULA = re.compile(
    r"\b(?:is|are|was|were)\s+(?:what|where|why|how)\s+\w"
    r"|\bwhat\s+(?:an?\s+|the\s+)?[\w-]+(?:\s+[\w-]+){0,4}\s+(?:is|are)\s+for\b"
    r"|\b(?:that|this|which|it)\s+(?:is|was)\s+what\b", re.I)


def defer_copula(f: Path) -> list:
    """Sentences that defer the verb behind a copular abstraction ('X is what lets Y' for 'X lets Y';
    'that is what keeps ...'; 'what an always-on agent is for'). Reads heavier than the direct form
    and recurs as a machine tic. Advisory: lead with the verb and the layer disappears."""
    return [s for c in narrative(f) for s, _ in _sentences(c) if _DEFER_COPULA.search(s)]


def dense_repeats(f: Path) -> list:
    """(word, sentence) where one content word (>=5 letters) appears three or more times in a single
    sentence: the sentence is circling one actor because it is doing too much ('each sub-agent is a
    brand-new agent invocation ... the sub-agent's context window'). Split it and the echo dissolves.
    Stronger than close_repeats, which only sees a within-five-words pair."""
    out = []
    for c in narrative(f):
        for s, _ in _sentences(c):
            counts = {}
            for w in (w.lower() for w in _WORD.findall(s)):
                if len(w) >= 5 and w not in _STOP:
                    counts[w] = counts.get(w, 0) + 1
            heavy = sorted(w for w, k in counts.items() if k >= 3)
            if heavy:
                out.append((heavy[0], s))
    return out


# Over-verbage: a sentence carrying too much at once. Any one signal fires.
_SUBORD = re.compile(r"\b(?:which|because|so that|while|whereas|even though|in order to|so as to|"
                     r"rather than|instead of|as long as|given that)\b", re.I)
_PAREN_GLOSS = re.compile(r"\(([^)]{16,})\)")


def over_verbage(f: Path) -> list:
    """(kind, sentence) for sentences that overload one breath: a clause-pile (>=30 words welded with
    >=3 commas), a subordinator-chain (>=2 of which/because/so-that/while...), or a heavy parenthetical
    gloss the sentence could fold in or drop. Distinct from grammar's run-on (a single >45-word length
    cap); this is about density, not just length."""
    out = []
    for c in narrative(f):
        for s, n in _sentences(c):
            commas = s.count(",")
            subs = len(_SUBORD.findall(s))
            glosses = [p for p in _PAREN_GLOSS.findall(s) if not _CITE_YEAR.search(p)]
            if n >= 30 and commas >= 3:
                out.append(("clause-pile", s))
            elif subs >= 2:
                out.append(("subordinator-chain", s))
            elif glosses and n >= 22:
                out.append(("heavy-gloss", s))
    return out


# Padding: emphasis/hedge phrases that add no information. Cut them.
_PADDING = re.compile(r"\b(?:exactly|simply|right here|right now|on your own terms|for yourself|"
                      r"end to end|under the hood|no matter what|regardless of what|of course|"
                      r"it turns out|as it happens|in plain view|straight off disk|outright|"
                      r"needless to say|when you get down to it)\b", re.I)


def padding_phrases(f: Path) -> list:
    """(phrase, sentence) for emphasis/hedge padding that adds no information ('exactly', 'right here',
    'on your own terms', 'under the hood'). Extends grammar's filler list with the course's recurring
    padding; cut the phrase and the sentence is unchanged in meaning."""
    out = []
    for c in narrative(f):
        for s, _ in _sentences(c):
            m = _PADDING.search(s)
            if m:
                out.append((m.group(0).strip(), s))
    return out


# ── Cell-code hygiene MOVED to scripts/validation/code_hygiene.py ──
# The code validator lives in its own module now; the prose and code bars are separate concerns.
# This thin re-export keeps older pv.code_hygiene callers working; the gate calls scan() directly.
def code_hygiene(f: Path) -> list:
    """Deprecated shim: code hygiene moved to scripts/validation/code_hygiene.py. Forwards one page's cell
    comments and walls to code_hygiene.cell_hygiene; the full suite is code_hygiene.scan()."""
    import code_hygiene as _ch
    return _ch.cell_hygiene(f)


# Scaffolding openers: throat-clearing that frames instead of saying ('This page does X', 'Below,
# you...', 'Notice that...'). Often the sentence works with the opener cut.
_HOLLOW = re.compile(
    r"^(?:this (?:page|section|cell|module|part|chapter)\b|in this (?:page|section|module|part)\b"
    r"|here (?:you|we|is|are)\b|below[,.]|above[,.]|notice that\b|note that\b|recall that\b"
    r"|as (?:you|we) (?:saw|will|can|have|already)\b|let'?s\b|let us\b|keep in mind\b"
    r"|it is worth\b|that is to say\b|in other words\b|put (?:simply|differently)\b"
    r"|modern \w+ (?:is|are)\b|today[, ]|these days\b|nowadays\b|at a high level\b"
    r"|fundamentally,|essentially,|basically,|the truth is\b|it turns out\b)", re.I)


def hollow_intro(f: Path) -> list:
    """Sentences that open on scaffolding rather than content ('This page does X', 'Below, you...',
    'Notice that...', 'In other words...'). The frame is usually cuttable: the sentence after the
    comma carries the meaning. High-yield in course prose, which leans on these to stitch sections."""
    return [s for c in narrative(f) for s, _ in _sentences(c) if _HOLLOW.match(s.strip())]


# Vacuous meta-writing: filler that comments on the course or the idea instead of conveying it.
# These clichés read as marketing and carry no information. Keep this phrase-level and strict:
# a single "Don't X; do Y" frame or unsupported category/status label can make a paragraph sound
# researched when it only gestures at authority.
_FILLER = re.compile(
    r"\b(?:where the (?:real|hard|interesting|actual) \w+ (?:lives|happens|is)\b"
    r"|the shape (?:this|the|that) \w+ chose\b"
    r"|one of the (?:shapes|ways|forms|kinds|things) (?:a |an |the )?\w+ can\b"
    r"|worth pulling\b|something (?:more|truly|genuinely|quite) (?:fundamental|profound|powerful|deeper)\b"
    r"|quietly (?:drops|ignores|skips|hides|sheds)\b|(?:boils|comes) down to\b"
    r"|at its (?:core|heart)\b|the (?:real|hard) (?:work|engineering) (?:lives|happens|is)\b"
    r"|the (?:whole|entire) (?:point|thing|shape|story|idea|picture|game)\b"
    r"|everything (?:\w+ ){0,5}lives in\b"
    r"|(?:do not|don['’]t)\s+[^.;!?]{3,160}?[;.]\s*(?:do|treat|use|call|write|replace|say|name)\b"
    r"|(?:closest|clearest|natural)\s+(?:public\s+)?(?:sibling|example)\b"
    r"|first[- ]class\s+(?:part|parts|citizen|feature|features)\b"
    r"|peer\s+runtime\b|makes?\s+[^.;!?]{1,80}?\s+explicit\b"
    r"|(?:gives?|provides?)\s+(?:you\s+)?the answer\b"
    r"|names?\s+the\s+(?:precise|recorded|exact)\s+(?:action|result|role)\b"
    r"|shipping\s+product\s+categor(?:y|ies)\b)", re.I)


def _vacuous_meta_text(chunks) -> list:
    out = []
    seen = set()
    for c in chunks if isinstance(chunks, (list, tuple)) else [chunks]:
        for s, _ in _sentences(c):
            for m in _FILLER.finditer(s):
                key = (m.group(0).strip(), s)
                if key not in seen:
                    out.append(key); seen.add(key)
    return out


def vacuous_meta(f: Path) -> list:
    """(phrase, sentence) for vacuous meta-writing: filler that comments on the course or the idea
    instead of conveying it ('where the real engineering lives', 'Don't X; do Y', 'first-class part').
    Reads as marketing and carries no information; cut the sentence or replace it with the fact."""
    return _vacuous_meta_text(narrative(f))


# A copular definitional appositive ("This is the smallest artifact in the course, a single chat() call",
# "It is the kernel sandbox: a policy on every syscall") is a setup/payoff reveal whether it is punctuated
# with a colon or a comma. Keying only on the colon let the structure be hidden by swapping the colon for a
# comma (the em-dash glyph-swap dodge in another costume) and by splitting the trailing clause into its own
# short paragraph. _APPOS_DEF fires on the word pattern so neither the punctuation nor the split can hide it.
_APPOS_DEF = re.compile(
    r"\b(?:this|that|it|here|these|those)\s+(?:is|are|was|were)\s+(?:the|a|an|one)\b[^.;!?]*?[:,]\s+(?:a|an|one|the)\b",
    re.I,
)
# The same swap defeats the colon count itself: "X is the Y, a Z" reads as one mid-sentence reveal even
# though the glyph is a comma. Count those comma-appositives alongside real colons toward the reveal tally.
_REVEAL_COMMA = re.compile(r"\b(?:is|are|was|were)\b[^.;:!?]*?,\s+(?:a|an|one|the)\b", re.I)


def staccato_cadence(f: Path) -> list:
    """(kind, detail, paragraph) for prose that reads choppy even when sentence LENGTHS vary, which
    the rhythm score is blind to. Tells: a copular 'X is the Y, a Z' definitional appositive (the same
    reveal whether the glyph is a colon, a comma, or split across paragraphs), two-plus mid-sentence
    reveals stacking 'setup: payoff', breaks (comma/colon/semicolon) so dense the prose is short clauses
    welded together, or breaks spaced so evenly the cadence turns mechanical."""
    out = []
    for c in narrative(f):
        if _APPOS_DEF.search(c):
            out.append(("appositive-definition", "copular 'X is the Y, a Z' reveal (colon or comma, even when split)", c))
            continue
        nw = len(_WORD.findall(c))
        if nw < 24:
            continue
        reveals = len(re.findall(r"\S:\s", c)) + len(_REVEAL_COMMA.findall(c))
        clauses = [cl for cl in re.split(r"[,;:.!?]+", c) if _WORD.findall(cl)]
        if len(clauses) < 4:
            continue
        clen = [len(_WORD.findall(cl)) for cl in clauses]
        mean = sum(clen) / len(clen)
        sd = (sum((x - mean) ** 2 for x in clen) / len(clen)) ** 0.5
        cv = sd / mean if mean else 1.0
        bd = (len(clauses) - 1) / nw     # internal breaks per word
        if reveals >= 2:
            out.append(("reveal-dense", f"{reveals} setup/payoff reveals (colon or appositive comma)", c))
        elif bd >= 0.11 and mean <= 7.5:
            out.append(("break-dense", f"a break every {nw / len(clauses):.1f} words over {len(clauses)} clauses", c))
        elif len(clauses) >= 5 and cv <= 0.50:
            out.append(("uniform-breaks", f"{len(clauses)} clauses spaced evenly (cv {cv:.2f})", c))
    return out


def repeated_phrase(f: Path) -> list:
    """(phrase, sentence) for a three-word content phrase that recurs across the page (beyond
    close_repeats' within-five-words pair). A crutch phrase a reader notices on the second pass;
    vary or cut it. Page-scoped: the second occurrence in a different sentence is what surfaces."""
    seen, out, fired = {}, [], set()
    for c in narrative(f):
        for s, _ in _sentences(c):
            ws = [w.lower() for w in _WORD.findall(s) if len(w) >= 4 and w.lower() not in _STOP]
            for i in range(len(ws) - 2):
                tri = " ".join(ws[i:i + 3])
                if tri in seen and seen[tri] != s and tri not in fired:
                    out.append((tri, s)); fired.add(tri)
                seen.setdefault(tri, s)
    return out


_ASSERT_DET = re.compile(r"^(?:the|this|that|these|those|it|a|an|each|every)\b", re.I)
_ASSERT_COP = re.compile(r"\b(?:is|are|was|were)\b", re.I)


def bare_assertions(f: Path) -> list:
    """Short copular "X is a Y" assertions that are NOT emphasized in the source. A crisp definition is
    good, but the device is overused here: each should be RARE, bolded, and defended (a following
    sentence that says why it holds), or else cut. This flags the bare, undefended ones, so they get
    thinned, emphasized, and justified. A sentence is bare if it opens on a determiner/pronoun, runs
    3 to 10 words, has a copular main verb, and carries no <strong>/<em>/<code> emphasis. Code, svg,
    and scripts are stripped first."""
    raw, suf = lp._read_for_links(f)
    if suf not in (".html", ".htm"):
        return []
    body = re.sub(r"<(svg|pre|script)\b.*?</\1>", " ", raw[raw.lower().find("<body"):], flags=re.S | re.I)
    out = []
    for bm in re.finditer(r"<(p|li)\b[^>]*>(.*?)</\1>", body, re.S | re.I):
        # Split on sentence-final punctuation followed by whitespace/end, so a '.' inside a URL
        # (href="https://json-schema.org/") or a decimal does not create a fake short "sentence".
        for seg in re.split(r"(?<=[.!?])\s+", bm.group(2)):
            txt = html.unescape(re.sub(r"\s+", " ", _TAG.sub(" ", seg))).strip()
            nw = len(_WORD.findall(txt))
            if 3 <= nw <= 10 and _ASSERT_DET.match(txt) and _ASSERT_COP.search(txt) \
               and "<strong" not in seg and "<em" not in seg and "<code" not in seg:
                out.append(txt)
    return out


def metrics(prose, gfx=(), gfx_prose=()):
    """Compute every prose-variety signal for one page in a single pass. This is the heart of the
    check: if these numbers were wrong the gate would either miss machine-uniform writing or flag
    good prose, so each metric mirrors a specific named LLM tell (uniform length, staccato triads,
    same-opener anaphora, rule-of-three, welded clauses, antithesis, phrase-level redundancy).
    Returns None on too-short text, where the spread metrics are statistical noise. gfx is the page's
    figure text (from graphics()), compared against the prose for graphic-restates-prose redundancy."""
    sents = _sentences(prose)
    text = " ".join([prose] if isinstance(prose, str) else prose)
    n = len(sents)
    if n < 5:
        return None                               # too few sentences for variance to mean anything
    anti = antithesis_hits(prose)
    for cap in gfx_prose:                         # figure captions are authored prose: scan them for buzz too,
        for k, s in antithesis_hits(cap):         # so a mirror cadence in a caption surfaces like one in a paragraph
            if (k, s) not in anti:
                anti.append((k, s))
    for ch in ([prose] if isinstance(prose, str) else prose):   # a paragraph welding 2+ semicolons reads dense and
        if ch.count(";") >= 2 and ("semicolon-heavy", ch[:140]) not in anti:   # aphoristic: split the mirrored clauses
            anti.append(("semicolon-heavy", ch[:140]))
    lens = [w for _, w in sents]                  # word count per sentence
    mean = statistics.fmean(lens)
    sd = statistics.pstdev(lens)                  # spread of sentence length; cv = sd/mean is the core signal

    firsts, toks = [], []
    for s, _ in sents:
        w = _WORD.findall(s)
        firsts.append(w[0].lower() if w else "")  # first word, for anaphora / shared-opener detection
        toks.append({t.lower() for t in w if len(t) >= 3 and t.lower() not in _STOP})  # content words for parallelism

    # A staccato triad is 3+ consecutive short sentences (<=12 words, <=4-word band) that are
    # PARALLEL: they share one opening word ("It plans. It acts. It reflects.") OR a content word
    # repeated across all of them ("A thermostat PUTS X. A car PUTS Y. Every agent PUTS Z."). Short
    # sentences sharing neither are ordinary terse prose (spec fragments, captions), not a tell.
    def _parallel(a, b):
        return len(set(firsts[a:b])) == 1 or bool(set.intersection(*toks[a:b]))
    triads, i, triad_runs = 0, 0, []
    while i < n:
        j = i
        while (j + 1 < n and lens[j + 1] <= 12 and lens[i] <= 12
               and max(lens[i:j + 2]) - min(lens[i:j + 2]) <= 4
               and _parallel(i, j + 2)):
            j += 1
        if j - i + 1 >= 3:
            triads += 1
            triad_runs.append(" ".join(sents[k][0] for k in range(i, j + 1)))   # surface the exact run
        i = j + 1 if j > i else i + 1

    best = run = 1
    for k in range(1, n):
        run = run + 1 if firsts[k] and firsts[k] == firsts[k - 1] else 1
        best = max(best, run)

    words = sum(lens)
    series3 = len(_SERIES3.findall(text))

    welded = 0                                                # a semicolon always welds; a colon only
    for s, _ in sents:                                        # when text follows it within the sentence.
        welded += s.count(";")                                # a trailing colon is a list-/cell-lead-in,
        body_s = s.rstrip()                                   # not punch, so it does not count.
        welded += sum(1 for mt in re.finditer(":", body_s) if mt.end() < len(body_s))

    # Phrase-level (bag-of-words) redundancy: a figure that restates the prose beside it, or one
    # sentence restating another. This replaces the old single-word echo (which fired on every page
    # the moment a topic word recurred); containment of whole content-word bags only triggers on a
    # genuine near-duplicate, so a diagram that adds nothing or a doubled sentence surfaces while
    # ordinary keyword reuse does not.
    redun = redundancy(prose, gfx)

    gram = grammar_hits(prose)                               # rules-of-school grammar/composition

    ex = [{"kind": k, "sentence": s} for k, s in anti][:8]
    for tr in triad_runs[:3]:                                 # the staccato anaphora run, as a fixable example
        ex.append({"kind": "staccato-triad", "sentence": tr})
    for kind, a, b in redun[:4]:                              # surface each redundancy as its own example
        tag = "figure restates prose" if kind == "graphic-echoes-prose" else "sentence restated"
        ex.append({"kind": kind, "sentence": f"[{tag}] “{a[:80]}” ⟂ “{b[:80]}”"})

    return {
        "sentences": n, "words": words,
        "mean": round(mean, 1), "sd": round(sd, 1), "cv": round(sd / mean if mean else 0.0, 3),
        "short_ratio": round(sum(1 for w in lens if w <= 7) / n, 3),
        "long_ratio": round(sum(1 for w in lens if w >= 30) / n, 3),
        "triads": triads,
        "anaphora_run": best,
        "series3": series3,
        "series3_density": round(series3 / (words / 1000), 1) if words else 0.0,
        "neg_parallel": len(_NEGPAR.findall(text)),
        "colon_semi_per_sent": round(welded / n, 3),
        "antithesis": len(anti),
        "redundancy": len(redun),
        "grammar": len(gram),
        "antithesis_examples": ex,
        "grammar_examples": [{"kind": k, "sentence": s} for k, s in gram][:12],
    }


def _score(m: dict) -> float:
    """Weighted buzz score; higher is worse. Each term is a named tell scaled to comparable size."""
    s = 0.0
    s += 1.5 * m["triads"]                                   # staccato parallels (the strongest, most direct tell)
    s += 1.5 * max(0, m["anaphora_run"] - 3)                 # same-opener runs beyond 3 sentences
    s += 20.0 * max(0.0, 0.50 - m["cv"])                     # uniform sentence length below cv 0.50
    s += 5.0 * max(0.0, 0.10 - m["short_ratio"])            # no short sentences to break the rhythm
    s += 0.4 * max(0.0, m["series3_density"] - 7)            # dense three-item series
    s += 6.0 * max(0.0, m["colon_semi_per_sent"] - 0.32)     # welded clauses
    s += 1.0 * max(0, m["neg_parallel"] - 1)                 # negative parallelisms beyond one
    s += 1.2 * m["antithesis"]                               # parallel/numeric antithesis (marketing cadence)
    s += 1.5 * m.get("redundancy", 0)                        # a figure restating the prose, or a doubled sentence
    s += 1.0 * m.get("grammar", 0)                           # rules-of-school grammar/composition mistakes
    return round(s, 1)


def tells(m: dict) -> list[str]:
    """The named tells that contribute to the score, each shown at the SAME threshold the score
    uses, so a nonzero score is always explained by a visible tell (never a black box)."""
    t = []
    if m["triads"] >= 1:                     t.append(f"staccato triad x{m['triads']}")
    if m["anaphora_run"] >= 4:               t.append(f"anaphora run {m['anaphora_run']}")
    if m["cv"] < 0.50:                        t.append(f"monotone length (cv {m['cv']:.2f})")
    if m["short_ratio"] < 0.10:              t.append(f"no short sentences ({m['short_ratio']:.0%})")
    if m["series3_density"] > 7:             t.append(f"rule-of-three dense ({m['series3_density']}/1k)")
    if m["neg_parallel"] >= 2:               t.append(f"negative parallelism x{m['neg_parallel']}")
    if m["colon_semi_per_sent"] > 0.32:      t.append(f"welded clauses ({m['colon_semi_per_sent']:.2f} :;/sent)")
    if m["antithesis"] >= 1:                 t.append(f"antithesis x{m['antithesis']}")
    if m.get("redundancy", 0) >= 1:          t.append(f"redundant phrasing x{m['redundancy']}")
    if m.get("grammar", 0) >= 1:             t.append(f"grammar/composition x{m['grammar']}")
    return t


def _pages(scope: str):
    """Select the requested authored prose surface.

    ``course`` is the canonical learner journey: its landing page and numbered modules only.
    ``ship`` adds other authored browser pages and every repository SKILL contract. ``all`` also
    considers root policies and direct ``docs/`` Markdown. Generated reports, script references,
    vendored materials, and the license use different genres and stay outside this prose signal.
    """
    if scope == "course":
        course_root = TASK1 / "web" / "nemoclaw"
        candidates = {course_root / "index.html", *course_root.glob("[0-9][0-9][a-z]-*.html")}
    else:
        candidates = set(lp._iter_pages(TASK1))
        candidates.update(TASK1.rglob("SKILL.html"))
    for f in sorted(candidates):
        rel = f.relative_to(TASK1).as_posix()
        if set(f.relative_to(TASK1).parts) & {".git", "i18n", "node_modules", ".venv", "venv", "artifacts"}:
            continue
        suf = f.suffix.lower()
        if f.name in ("studio.html", "courses.html", "LICENSE"):
            continue
        # vendored mats (now course-scoped under web/nemoclaw/mats/, both .md and .html snapshots)
        # are external reference packets, never authored narrative, so they are excluded by segment.
        if lp.is_mat_path(rel) and f.name != "SKILL.html":
            continue
        if suf in (".html", ".htm"):
            if f.name != "SKILL.html" and not rel.startswith("web/"):
                continue
        elif suf == ".md":
            if scope != "all" or rel.startswith("scripts/"):
                continue
            if rel.startswith("docs/") and f.parent != TASK1 / "docs":
                continue
        else:
            continue
        yield f, rel


def sweep(scope: str = "ship"):
    """Score every authored narrative page and rank worst-first, so a human can see at a glance which
    pages read machine-uniform and deserve a rhythm pass. This is the page-level driver the gate and
    the table both consume; a page at or above FLAG_AT is marked, but nothing here blocks (advisory)."""
    misses = pattern_contract()
    if misses:
        raise RuntimeError("prose detector regression: " + "; ".join(misses))
    rows = []
    for f, rel in _pages(scope):
        try:
            m = metrics(narrative(f), graphics(f), graphic_prose(f))   # prose + figure text (redundancy) + caption sentences (buzz)
        except Exception:
            m = None                              # unreadable / too-short page: skip rather than crash
        if m:
            sc = _score(m)                        # weighted buzz score; higher is more machine-uniform
            rows.append({"path": rel, "score": sc, "flagged": sc >= FLAG_AT,
                         "metrics": m, "tells": tells(m)})
    rows.sort(key=lambda r: -r["score"])          # worst-first so the report leads with the pages to fix
    return rows


def _print_table(rows):
    print("prose-variety . authored narrative (advisory; higher score = more machine-uniform)")
    print(f"  {'page':<34} {'score':>5} {'sent':>4} {'mean±sd':>8} {'cv':>5} {'shrt':>5} {'tri':>3} {'ana':>3} {'r3':>4} {':;/s':>5} {'ant':>3}  tells")
    flagged = 0
    for r in rows:
        m = r["metrics"]
        mark = "* " if r["flagged"] else "  "
        flagged += 1 if r["flagged"] else 0
        print(f"{mark}{r['path']:<34} {r['score']:>5.1f} {m['sentences']:>4} "
              f"{str(m['mean'])+'±'+str(m['sd']):>8} {m['cv']:>5.2f} {m['short_ratio']*100:>4.0f}% "
              f"{m['triads']:>3} {m['anaphora_run']:>3} {m['series3_density']:>4.1f} "
              f"{m['colon_semi_per_sent']:>5.2f} {m['antithesis']:>3}  {'; '.join(r['tells'])}")
    print(f"\n  {len(rows)} pages ranked . {flagged} at/above score {FLAG_AT} (marked *), worth a rhythm pass")
    print("  score = 1.5*triads + 1.5*(anaphora-3) + 20*(0.50-cv below) + 5*(0.10-short% below)"
          " + 0.4*(r3/1k over 7) + 6*(:;/sent over 0.32) + 1*(neg-parallel over 1) + 1.2*antithesis")
    print("  legend: cv=length variation (higher is more varied); shrt=% sentences <=7 words; tri=staccato "
          "triads; ana=longest same-opener run; r3=three-item series per 1k words; ant=parallel/numeric antithesis")
    # Show the exact antithesis sentences for the worst pages, because a count is not actionable;
    # the offending line is. A human reads these and rewrites the construction (not a glyph swap).
    shown = [r for r in rows if r["metrics"].get("antithesis_examples")][:6]
    if shown:
        print("\n  antithesis constructions (rewrite the sentence, do not just reword):")
        for r in shown:
            print(f"  - {r['path']}")
            for ex in r["metrics"]["antithesis_examples"]:
                snip = ex["sentence"][:108] + ("…" if len(ex["sentence"]) > 108 else "")
                print(f"      [{ex['kind']}] {snip}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Measure human-like prose variety (sentence-length spread, enumeration, clause welding).",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--scope", choices=["course", "ship", "all"], default="ship",
                    help=("course = the landing page and numbered learner modules; ship = all authored "
                          "browser/SKILL prose (default); all = also eligible repository Markdown"))
    ap.add_argument("--page", help="analyze one page (relative path) and print its sentences with word counts")
    ap.add_argument("--text", help="score a snippet of prose directly (handy while rewriting)")
    ap.add_argument("--json", action="store_true", help="machine-readable output (the gate reads this)")
    a = ap.parse_args()

    if a.text is not None:
        m = metrics(a.text)
        meta = [{"phrase": p, "sentence": sent} for p, sent in _vacuous_meta_text(a.text)]
        if not m:
            out = {"score": None, "flagged": bool(meta), "metrics": None, "tells": [], "vacuous_meta": meta}
            if a.json:
                print(json.dumps(out, indent=2))
            else:
                print("(need at least 5 sentences to measure variety)")
                for x in meta:
                    print(f"  vacuous-meta: {x['phrase']} -> {x['sentence']}")
            return 0
        out = {"score": _score(m), "flagged": _score(m) >= FLAG_AT or bool(meta),
               "metrics": m, "tells": tells(m), "vacuous_meta": meta}
        if a.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"score {out['score']}  {m}\n  tells: {out['tells'] or 'none'}")
            for x in meta:
                print(f"  vacuous-meta: {x['phrase']} -> {x['sentence']}")
            if m["sentences"] < 12:
                print(f"  note: only {m['sentences']} sentences; cv and rule-of-three density are noisy "
                      f"on short snippets, so read this as a rough signal, not a verdict")
        return 0

    if a.page:
        f = TASK1 / a.page
        if not f.is_file():
            print(f"no such page: {a.page}", file=sys.stderr); return 2
        prose = narrative(f)
        m = metrics(prose, graphics(f), graphic_prose(f))
        if a.json:
            print(json.dumps({"path": a.page, "score": _score(m) if m else None,
                              "metrics": m, "tells": tells(m) if m else []}, indent=2)); return 0
        if not m:
            print(f"{a.page}: too little narrative to measure (need 5+ sentences)"); return 0
        print(f"{a.page}  score {_score(m)}\n  {m}\n  tells: {tells(m) or 'none'}\n")
        for s, w in _sentences(prose):
            print(f"  [{w:>2}] {s}")
        return 0

    rows = sweep(a.scope)
    if a.json:
        print(json.dumps({"scope": a.scope, "pages": len(rows),
                          "flagged": sum(1 for r in rows if r["flagged"]),
                          "flag_at": FLAG_AT, "rows": rows}, indent=2))
    else:
        _print_table(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
