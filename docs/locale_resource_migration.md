# Key-based locale resources

This document records what a key-addressed locale resource is, how the migration went on real pages,
and how a page moves between a reviewed HTML overlay and a resource. It answers
[issue #3](https://github.com/NVDLI/NemoClawDLI/issues/3).

Start at [`scripts/translate/README.md`](../scripts/translate/README.md) for the overlay model this
replaces. Every page both published locales ship now publishes from a resource: `overlay_files` is
empty in each `localization_state.json`, and no reviewed localized HTML remains under `i18n/`.
Translated wording stays owned by its language reviewer under
[`course-prose-style.md`](course-prose-style.md), whichever representation holds it.

## The shape

A resource is one JSON file per template per locale:

```text
i18n/<url-code>/resources/<template path>.json
```

It carries the schema, the locale tag, the template it translates, and one entry per translatable
unit the template consumes:

```json
{
  "schema": "nemoclaw-locale-resource/1",
  "locale": "es-ES",
  "template": "web/nemoclaw/01a-loop.html",
  "values": {
    "text.7d1f0c9a2b34": {
      "type": "text",
      "source": "The agent loop",
      "value": "El bucle del agente"
    }
  }
}
```

`media` is the one optional field. It names canonical assets this template overrides with a reviewed
locale file, so a localized figure stays an explicit decision rather than an accident of file layout.

## Derived keys

A prose key is `<type>.<first twelve hex digits of the SHA-256 of the whitespace-normalized English
source>`. A runnable comment or string-copy key uses the same type prefix but hashes its exact body
after line-ending normalization because whitespace inside a comment or string can change runnable
behavior. The resource never stores the surrounding quote, comment delimiter, operator, call,
identifier, regex, or control flow. A template that consumes the same English source more than once
addresses each later occurrence as `<key>~<ordinal>` in document order.
Nothing enumerates pages, languages, or key counts. Four properties follow:

- Moving a paragraph does not rename its key, so reordering a page costs no translation work.
- Editing English changes the key of exactly the strings that were edited. Staleness lands on those
  values instead of invalidating a whole page, which is the main gain over the per-page source hash.
- The reviewed unit is the occurrence, not the string. A reviewer who renders two occurrences of one
  English source differently on the same page is representable, so migration never has to reconcile
  wording the release already publishes.
- Two templates that share an English string share the same base key. Each page resource records its
  own value. The same locale can render one source differently on different pages only when that
  decision is recorded in the locale's `shared_key_variants`.

The cost is that a key is not human-readable. Every entry therefore records the English `source`
next to the translated `value`, and every failure quotes it. The consumer-map build rejects two
distinct source units if their truncated digests ever collide.

## Recorded divergence

`scripts/translate/locales/<locale>/profile.json` states that an agent or maintainer must not
normalize a style PIC's wording. Requiring one translation per English source would demand exactly
that at migration time, so the gate does not require agreement. It requires the divergence to be
written down beside the locale's other review decisions:

```json
"shared_key_variants": {
  "text.67a5bdf2a82d": "Reviewed Spanish renders the 'NVIDIA · Securing Agents' brand line as ..."
}
```

`resource-shared-key-unrecorded` fails an undeclared divergence and names every consuming template
and value. `resource-shared-key-record-unused` fails a record whose divergence no longer exists, so
a reconciliation cleans up its own entry. `resource-shared-key-record-invalid` fails an empty or
mistyped record. Each locale records both prose variants and context-specific runnable-copy variants
its reviewed corpus already shipped. That list is the language reviewer's worklist, not a permanent
exemption.

## Typed values

`scripts/translate/locale_resources.py` derives the type from the English source and requires the
resource to declare the same type. A declared type that disagrees with the template is an error.

| Type | Source shape | What the value may do |
| --- | --- | --- |
| `text` | prose with no markup | add `i` or `em` emphasis only |
| `attribute` | `alt`, `aria-label`, `placeholder`, `title` | plain text, no single or double quote and no angle bracket |
| `rich` | prose with inline or list markup | preserve the unit's tag and attribute-name structure; add only attribute-free `i` or `em` emphasis |
| `link` | prose containing an anchor | everything `rich` allows, and every link target must stay identical |
| `placeholder` | prose carrying `${...}` or `{{...}}` | plain text that reproduces every token |

Runnable comments and string bodies use those same five reader-copy types. Their template-owned
delimiters are never resource data. A runnable value cannot close its comment or string, add a raw
line break to a quoted string, or contain a raw script end tag. HTML-like syntax inside a runnable
string must keep the template's tags and attributes exactly; this preserves trace-row markup while
still allowing its visible wording to change. The renderer then proves that the complete script
shape and protocol literals still match `scripts/translate/code_localization.py`.

All values must reproduce protected tokens (`code` and `kbd` spans, URLs, routes, `${...}`,
`{{...}}`, `nvapi-`) exactly, which is the same contract the page gate already enforces on reviewed
overlays.

Template-owned interactive tags such as `button` may remain in a rich value only with the same tag
and attribute structure. A resource cannot add an executable tag, event handler, unsafe URL, or
different button behavior.

A value of any type that is identical to its English source is a hidden fallback and fails. Declaring
`"untranslated": "<reviewed reason>"` on that entry makes the decision explicit and passes.
Rendered language-residue and locale-punctuation checks exclude only that exact declared value;
structure, protected tokens, links, code shape, and every other locale-quality rule still inspect
the page.

The migrator never invents a rationale, but it does record provenance. `build` reaches extraction
only after the reviewed overlay's accepted source digest matches the tree. A locale that requires
target hashes must also match its accepted target digest. At that point the English wording at that
unit is bytes a language reviewer already accepted, so the migrator writes that fact:

```text
kept English: the reviewed es-ES overlay of web/nemoclaw/04c-going-further.html carries the
canonical source at this unit unchanged
```

A reason already present in a resource is retained ahead of the provenance record, so a reviewer's
own wording is never overwritten. A hand-authored resource has no reviewed overlay to derive from
and still fails closed until a reviewer records the decision. These entries expose the corpus's real
untranslated surface in one greppable place instead of hiding it behind a successful page hash.

## Rendered output, not JSON

Valid JSON proves nothing about a page, so the gate renders and then checks the page:

- `render_page` rebuilds the static page at build time. No page fetches a translation at runtime.
- Rendering follows the assembler's own branch. A page carrying `data-localization-scope="en-shell"`
  publishes the projection of its reviewed body onto the full template; a page without that shell
  publishes the localized document itself, exactly as the assembler copies a non-scoped overlay
  verbatim. Deriving a non-scoped page's units from the canonicalized form would reserialize the
  shipped HTML, so `authored_structure` picks the representation the publication path uses.
- The rendered page runs through `page_quality`, the same function that gates a reviewed overlay:
  language tag, segment parity, protected tokens, citation titles, identifiers, local dependencies,
  tag skeleton, script shape, code contracts, and the locale prose rules.
- The rendered tag skeleton must equal the template's. Resource values supply wording while the
  shared template retains structure.
- While a page still has a reviewed overlay, the page rendered from the resource must equal the page
  published from that overlay, byte for byte. Migration cannot quietly change shipped prose.
- Once a resource owns publication, its accepted source and target hashes must match the rendered
  bytes. The assembler retains its safe canonical fallback, but the resource gate reports that use
  as a hidden-fallback failure instead of letting the release proceed.
- Localized media named by the resource must still match its accepted canonical source and, for a
  locale that requires target hashes, its accepted locale bytes.

The resource audit checks every discovered consumer in memory. The existing full artifact and
browser gates then discover the assembled locale pages from the Pages tree and run theme,
narrow-layout, accessibility, link, browser, and artifact checks against those published bytes.
Those controller-owned gates remain required; the in-memory resource check does not replace them.

## What the migration changed

Each locale now publishes fifteen reviewed pages from resources, for thirty pages total. Twenty-six
publish bytes identical to the previous overlay build. Four changed, and every change is accounted
for:

| Page | Change | Kind |
| --- | --- | --- |
| es `web/nemoclaw/03a-kickstart.html` | `<!DOCTYPE html>` restored; `&#x27;` in two inline `onclick` attributes back to `'`; `<meta/>` and `<link/>` spacing; one indentation | structural |
| es `web/nemoclaw/03c-always-on.html` | `<!DOCTYPE html>` restored; the same two `onclick` attributes; one indentation | structural |
| es `web/nemoclaw/04b-modern-clis.html` | three translated `<comando>` tokens restored to the executable `agent <command>` CLI placeholder | contract correction |
| pt `web/nemoclaw/03a-kickstart.html` | two blank lines in one runnable cell follow the shared template | structural |

The two Spanish overlays had been written by an HTML canonicalizer that dropped the doctype, so
those pages were shipping in browser quirks mode. Publishing from the shared template restores the
canonical structure, which is the structural parity this issue asked for. The Portuguese change is
formatting only. The Spanish 04b correction keeps a machine placeholder executable instead of
translating it as prose.

Three limitations the prototype recorded were extractor defects, not locale exceptions, and are
fixed here rather than documented as permanent overrides:

- The Spanish 03a overlay renders the repeated `tool` fallback label two ways. Occurrence-addressed
  keys represent that directly; the divergence is recorded in `shared_key_variants`.
- `failureHint`, `unexpectedHtmlHint`, `helpHint`, and the `fieldHelp` panel bodies were reviewed
  learner text that `translate_html_segments.py` did not extract. The `*Hint` field shape and any
  template-literal object value are now covered, replacing two name allowlists. Runnable `code:`
  values are excluded by a span scanner that understands helper calls, comments, and nested
  mentions, so executable bodies are never offered to the generic HTML translator. The resource
  layer separately discovers comment and string bodies, ignores regex literals, and keeps every
  surrounding executable token in the shared template.
- `web/index.html` assigns learner-visible text through `.textContent`, which the Portuguese overlay
  translated and the extractor missed. Those assignments are now extracted.

Widening extraction surfaced learner-visible English that the reviewed corpus had never translated:
two fragments on the Spanish 04a page, and untranslated strings on `02c-deep`, `web/index.html`, and
the glossary that stay within the locale quality thresholds. They are now recorded as
`untranslated` entries with review provenance, so migration preserves the reviewed wording and
makes every remaining language-review item visible for a future pass.

The corpus is mostly `text` values, then `rich` and `link`, with a small number of `attribute`
units. No page carries a `placeholder` unit today. Complete runnable-cell bodies are not resource
values.

## Migrating one page

Migration never retranslates. It records the wording a language reviewer already accepted.

```bash
# 1. Derive the resource from the reviewed overlay.
python3 scripts/translate/migrate_locale_resource.py \
  --locale es-ES --template web/nemoclaw/01a-loop.html

# 2. Prove the resource still matches that overlay.
python3 scripts/translate/migrate_locale_resource.py \
  --locale es-ES --template web/nemoclaw/01a-loop.html --check

# 3. Prove the rendered page, the typed values, and the discovery rules.
python3 scripts/validation/locale_resource_audit.py
python3 scripts/validation/locale_resource_audit.py --self-test

# 4. Regenerate the directory beacons the new resource paths need.
python3 scripts/skills/gen_directory_beacons.py
```

Step 2 is the round trip: while both representations exist, the resource is a generated projection
of the overlay and any drift is a failed preflight. Every page in this repository has already been
through these steps; the sequence stays here for a new page or a new locale.

## Flipping authority

A page publishes from its resource only when the locale has no reviewed overlay for it. To flip one
page, a maintainer with locale review authority:

1. Confirms `locale_resource_audit` reports no publication drift for that page and locale.
2. Confirms every entry whose value repeats the English source carries an `untranslated` reason,
   and records any same-locale divergence under `shared_key_variants`.
3. Deletes `i18n/<code>/<template>` and removes it from `overlay_files`. Keep the existing
   `reviews[template]` entry so the accepted source identity and review history remain attached.
4. Runs `python3 scripts/validation/localization_audit.py --locale <locale> --accept <template>`.
   This locale-authorized step rebinds `target_sha256` to the resource representation. Whitespace
   outside translatable units can differ from the former sparse HTML even when the published page
   is byte-identical, so copying the old target hash is not sufficient.
5. Re-runs the localization audit, the resource audit, and the assembler self-test. Rebuilds and
   inspects the page in a browser under both themes.

Keep localized figures as they are. They stay declared in `asset_files` and keep their reviewed
source hash; the resource's `media` list only records that this template depends on them.

## Override eligibility

A page is eligible for a resource only when the shared template can preserve its reviewed locale
behavior. Locale-specific link targets, layout, interaction, or teaching structure remain explicit
HTML overrides. Do not migrate such a page until a dedicated typed override schema can represent
and validate that difference. Localized figures remain explicit asset overrides and must appear in
both `asset_files` and the consuming resource's `media` list.

**No page currently claims an override.** Every page in both published locales is covered by a
shared template, so `overlay_files` is empty in each locale. An extractor gap or a wording
inconsistency is not an override: it is a defect in the model or a language reviewer's worklist
item, and both classes were closed by migrating rather than by exempting a page.

The HTML file itself owns authority. While it exists, even when its review hash is stale, the
resource stays shadow-only and the existing assembler behavior falls back to canonical English.
Deleting the HTML file is therefore the deliberate authority flip.

## Rollback

Restore the reviewed HTML file, add the page back to `overlay_files`, and retain its existing review
entry. File presence immediately shadows the resource again. Run the locale-authorized
`localization_audit.py --accept` command to bind the target hash back to the restored HTML, then
re-run the localization and resource audits. The resource may remain for diagnosis or be deleted if
the migration is abandoned.

## Adding a locale or a page

Nothing in the gate enumerates pages, languages, or keys, so a new locale needs a `locale.json`, a
profile, a `localization_state.json`, and one resource per page it translates. A new page needs one
resource per locale that publishes it. The mutation suite proves both cases pass without a validator
edit, and that a missing, renamed, mistyped, unsafe, unreachable, or fallback-only key still fails.

Migrate in this order when a batch is large enough to stage:

1. Low-risk static pages first: `web/courses.html`, `web/index.html`, and the course index.
2. Then lesson pages with few runnable cells.
3. Then cell-heavy lessons, one locale at a time, so a regression is attributable.

## Open questions

- Shell wording still lives in `scripts/translate/locales/<locale>/shell_translations.json`, keyed
  by normalized English. That file predates this work, and its normalized-English keys make it an
  earlier untyped form of the same model. Folding it into the typed schema is a later change.
- A future English edit changes a key. The audit reports the old key as unreachable and the new key
  as missing, which is correct but does not carry the previous translation forward. A helper that
  proposes the previous value for a near-match would make copy edits cheaper to re-review.
