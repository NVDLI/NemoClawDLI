# Course prose writing contract

Use this contract for learner-facing explanations and instructions. It also governs captions and
helper text. Page-specific decisions belong in the reviewing Issue or merge request, where they stay
tied to the exact source revision. The broader workflow lives in
[`agent_process.md`](agent_process.md).

## Explain the mechanism

1. **Name the actor and action.** Write “the runtime executes the function” instead of hiding the
   behavior behind passive voice or abstract nouns.
2. **Assign each responsibility.** Distinguish the model from its harness and identify which
   runtime component performs each operation. Keep gateway, tool, and sandbox roles explicit.
3. **Use practitioner language.** Choose terms a developer would use during design or review.
   Examples include execution runtime, tool call, control boundary, and fan-out.
4. **Preserve identifiers.** Keep product names and routes exact. The same rule applies to methods,
   JSON values, and identifiers such as `finish_reason`.
5. **Lead with the useful fact.** State the behavior or decision before describing how the lesson
   demonstrates it.
6. **Split at a conceptual seam.** Keep related clauses together, then start a new sentence when
   the actor or mechanism changes. Give a separate sentence to a new recommendation.

## Teach directly

- Address the learner when asking for an action: “Run the cell” or “Try another prompt.” Use
  declarative language when describing system behavior.
- Keep contrasts that define a technical or security boundary. Simplify their wording while
  preserving the distinction.
- Prefer a concrete example or visible result over commentary about the course itself.
- Keep headings and transitions proportional to the task. Instructions should be equally direct.
  Learners should not have to decode slogans or repeated setup. They should not have to untangle a
  chain of near-synonyms either.

## Review with evidence

Automated signals identify passages that deserve review. Human judgment decides whether a rewrite
would improve them. Run both commands before recording the disposition in the Issue or merge request.

```bash
python3 scripts/validation/prose_variety.py --scope course
python3 scripts/validation/validate_bundle.py --scope ship --no-write
```

Review each proposed rewrite against these checks:

- Is the responsible component still correct, and does it perform the stated action?
- Are identifiers unchanged, and does the rewrite preserve every technical boundary?
- Would the intended audience say it naturally while the paragraph progresses as a whole?

A lower score alone never justifies a less precise sentence.

## Repository prose

README and operating documents use the same direct style with a stricter ownership rule: keep a
procedure in one canonical document and link to it elsewhere. The repository work-product audit
rejects an oversized README, missing newcomer routes, repeated cross-document paragraphs, repeated
headings, filler phrases, and paragraphs that exceed 140 words. These are structural limits, not a
word-substitution score. They protect a short entrypoint and make redundant guidance visible.

Run `python3 scripts/validation/repository_work_products_audit.py` after changing root policies or
direct `docs/` Markdown. Use `python3 scripts/validation/prose_variety.py --scope all` for the wider
advisory rhythm report. A reviewer still decides whether a flagged rewrite improves accuracy and
usefulness.

## Locale ownership

Canonical English prose does not control a translation's wording. When the meaning remains stable,
reviewers may accept a new source hash while keeping localized HTML byte-identical. Actual locale
wording changes require a language reviewer. They also require the contribution credit defined in
[`CONTRIBUTING.md`](../CONTRIBUTING.md).
