# Same-branch localization

Translations live beside English on the same branch as sparse overlays under `i18n/<url-code>/`.
Current locale profiles include Brazilian Portuguese (`pt-BR`, URL code `pt`) and neutral technical
Spanish (`es-ES`, URL code `es`). Each locale owns its terminology, rhythm, and calque rules.
`locale_catalog.py` discovers every directory under `i18n/` and rejects missing metadata, conflicting
locale tags, orphaned profiles, unsafe paths, and missing directory beacons before any build proceeds.

This shape keeps review honest. One commit can change English, its translations, the drift metadata,
and the validator that protects the relationship. A translation branch cannot hide an old runtime,
and a language build cannot replace current code with a copied JavaScript or asset tree.

## The overlay boundary

`web/` remains canonical for page structure and executable logic, and it is the only home for
standalone runtime modules, styles, data, machine-contract pages, and untranslated pages.
Each `i18n/<code>/localization_state.json` allow-lists localized HTML and reviewed SVGs whose embedded text
differs by language. Other assets stay canonical.
During a build, `assemble_locale_overlay.py` copies canonical `web/` and applies only those declared
files. The audit requires equivalent HTML, executable structure, identifiers, routes, and protocol
literals. Reviewed prompts, logs, errors, and comments inside runnable cells remain localized.
Everything else is inherited verbatim.

Do not copy runtime files into `i18n/`. If a localized page needs different behavior, make the
canonical runtime locale-aware and test both languages. Localized SVGs are the narrow asset
exception: preserve non-text geometry, add `data-locale`, declare them under `asset_files`, and
accept the exact canonical source hash only after rendered review.

## Drift model

Each accepted localized file records the SHA-256 of the English source that a reviewer actually
read. `localization_audit.py` compares that hash with the current source and classifies every page:

- `current`: target exists, source hash matches, locale checks pass;
- `stale`: English changed after the last review;
- `blocked`: hash matches but language, structure, or terminology checks fail;
- `needs-review`: translated file exists but has no accepted source hash;
- `missing`: no localized overlay exists, so the build inherits English.

The generated `web/nemoclaw/assets/localization-<code>.json` drives Localization Studio and the Pages
language menu. The menu offers a same-page switch only for `current` pages.

## Locale review

Read the target locale SKILL first. Locale profiles cite public NVIDIA material, record
preferred terminology, permits established developer terms such as `workflow`, `runtime`, `sandbox`,
and `stack`, and blocks known literal-translation artifacts. Static checks cannot certify natural
prose; Studio keeps English and the selected locale side by side so a human can make that judgment efficiently.

## Contributor loop

```bash
# 1. See every same-branch state and refresh Studio data.
python3 scripts/validation/localization_audit.py

# 2. Optionally generate a draft. Use a fresh cache when changing the prompt or model.
#    The API key may be in NVIDIA_API_KEY or untracked .env-dev.
python3 scripts/translate/translate_html_segments.py \
  web/nemoclaw/02c-deep.html \
  --cache /tmp/nemoclaw-pt-draft.json \
  --usage-report /tmp/nemoclaw-pt-generate-usage.json

# 3. Run the bounded editorial pass before making manual corrections.
python3 scripts/translate/translate_html_segments.py \
  web/nemoclaw/02c-deep.html --polish \
  --cache /tmp/nemoclaw-pt-draft.json \
  --usage-report /tmp/nemoclaw-pt-polish-usage.json

# 4. Add the HTML path to localization_state.json. Review every block in Studio.
#    Repair calques manually and add reusable failures to profile.json unfit_phrases.
#    Keep executable structure, identifiers, URLs, product names, cited titles,
#    API/config literals, and skill-meta canonical. Translate learner-facing prompts and output.

# 5. Accept only the exact English base that a human reviewed.
python3 scripts/validation/localization_audit.py \
  --locale pt-BR --accept web/nemoclaw/02c-deep.html

# 6. Prove the detector and build the combined site.
python3 scripts/translate/translate_svg_text.py \
  web/nemoclaw/assets/figures/FIGURE.svg --no-api
python3 scripts/build/assemble_locale_overlay.py --self-test
python3 scripts/validation/localization_audit.py --self-test
BUILD_PAGES_PULL_MATERIALS=0 bash scripts/build/build_pages.sh /tmp/nemoclaw-pages
```

The generator translates semantic HTML blocks rather than isolated text nodes. It protects tags,
`code`/`kbd` spans, URLs, entities, placeholders, and executable code; retries invalid model output;
and refuses a result whose protected-token sequence changes. `--polish` edits the localized blocks
without re-reading the English source. Neither mode accepts a review hash: generation and acceptance
remain separate authority boundaries.

`--usage-report` writes secret-free JSON with request attempts, failures, elapsed request-seconds,
and provider-reported prompt/completion tokens per page. Keep reports in `/tmp`; summarize them in the
merge request rather than committing transient telemetry. A failed or timed-out request has unknown
provider metering and must be reported separately from completed-request token totals.

### Reproduce with Codex

Ask Codex to read `scripts/translate/SKILL.html` and the locale SKILL first, translate only the named
pages with the commands above, stop before accepting hashes, and open the built Localization Studio
for a side-by-side review. Then direct it to fix every observed language defect, add only generalizable
defects to `profile.json`, run the mutation/build/browser gates, and report both usage JSON files.
Codex must not translate additional pages, accept a source hash, commit, or push unless those actions
were explicitly included in the requested scope.

Open `/nemoclaw/localization.html` in the built site. Filters expose current, stale, blocked,
needs-review, and missing pages. Each row shows source/review/target hashes and the acceptance command.

## Files

- `locales/pt-BR/profile.json`: public terminology sources and machine-readable language rules.
- `locales/pt-BR/SKILL.html`: Portuguese first-touch node for students, reviewers, and agents.
- `locales/es-ES/profile.json`: public Spanish terminology sources, neutral technical vocabulary, rhythm limits, and calque rules.
- `locales/es-ES/SKILL.html`: Spanish first-touch node for students, reviewers, and agents.
- `translate_html_segments.py`: protected semantic-block drafting, polish, cache, and usage telemetry.
- `translate_svg_text.py`: geometry-preserving SVG label/accessibility translation.
- `locales/pt-BR/svg_translations.json`: reviewed, provider-free SVG translation map.
- `locales/es-ES/svg_translations.json`: reviewed, provider-free Spanish SVG translation map.
- `locale_catalog.py`: required discovery and cross-file identity contract for every locale.
- `scripts/validation/localization_audit.py`: required drift and language gate with mutation tests.
- `scripts/build/assemble_locale_overlay.py`: deterministic canonical-plus-prose assembly.
- `web/nemoclaw/localization.html`: same-branch comparison Studio.
