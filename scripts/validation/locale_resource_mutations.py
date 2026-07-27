# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mutation fixtures for the key-based locale resource gate.

Each mutation breaks one property the gate claims to hold, on a synthetic repository that names no
real page or language. Adding a page or a locale is a mutation too: those cases must stay clean
without the validator learning anything about them.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Callable

from translate.locale_resource_render import render_overlay

LOCALE = "xx-YY"
URL_CODE = "xx"
TEMPLATE = "web/course/lesson.html"
SECOND_TEMPLATE = "web/course/second.html"
REPEAT_TEMPLATE = "web/course/repeat.html"
NESTED_TEMPLATE = "web/course/assets/nested-lesson.html"
FIGURE = "web/course/figures/loop.svg"
SHELL_SOURCE = "Need detail?"
SHELL_TARGET = "Xx detail xx?"

TEMPLATE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Loop lesson</title>
</head>
<body>
<h1>The agent loop</h1>
<p>Read the <a href="https://example.com/spec" rel="noopener" target="_blank">wire format</a> first.</p>
<p>Call <code>helpers.log</code> when the step finishes.</p>
<ul><li>Budget is ${limit} tokens.</li></ul>
<p><button type="button" aria-label="Start loop">Start loop</button></p>
<img alt="Agent loop diagram" src="figures/loop.svg"/>
<details class="learning-block" open data-learning-id="loop-detail" data-localization-scope="en-shell">
  <summary data-localization-scope="en">Need detail?</summary>
  <div class="learning-block-body">
    <p>The loop repeats until the budget runs out.</p>
  </div>
</details>
<div id="cell-loop"></div>
<script>
  const cell = {
    label: "Run the loop",
    code: `// Start the loop.
const plan = await state.call("agent.plan", {kind: "agentTurn"});
helpers.log("Run agent <command>");
return plan;`
  };
</script>
</body>
</html>
"""

SECOND_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Second lesson</title>
</head>
<body>
<h1>The second loop</h1>
<p>The loop repeats until the budget runs out.</p>
</body>
</html>
"""

# One template, one English source, two occurrences. A reviewer may render them differently, so the
# resource has to address the occurrence rather than the string.
REPEAT_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Second lesson</title>
</head>
<body>
<h1>The second loop</h1>
<p>The loop repeats until the budget runs out.</p>
<p>The loop repeats until the budget runs out.</p>
</body>
</html>
"""

TRANSLATIONS = {
    "Loop lesson": "Xx leccion xx",
    "The agent loop": "Xx ciclo xx",
    "The second loop": "Xx segundo ciclo xx",
    "Read the <a href=\"https://example.com/spec\" rel=\"noopener\" target=\"_blank\">wire format</a> first.":
        "Xx lea <a href=\"https://example.com/spec\" rel=\"noopener\" target=\"_blank\">formato xx</a> xx.",
    "Call <code>helpers.log</code> when the step finishes.":
        "Xx llame <code>helpers.log</code> xx termina xx.",
    "Budget is ${limit} tokens.": "Xx presupuesto xx ${limit} xx.",
    "<button type=\"button\" aria-label=\"Start loop\">Start loop</button>":
        "<button type=\"button\" aria-label=\"Xx inicia xx\">Xx inicia xx</button>",
    "Agent loop diagram": "Xx diagrama xx",
    "The loop repeats until the budget runs out.": "Xx repite xx hasta xx.",
    "Second lesson": "Xx segunda xx",
    "Run the loop": "Xx ejecute xx",
}

CODE_TARGET = """// Xx inicia xx.
const plan = await state.call("agent.plan", {kind: "agentTurn"});
helpers.log("Xx ejecute agent <command>");
return plan;"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _locale_files(root: Path, url_code: str, locale: str) -> None:
    locale_root = root / "i18n" / url_code
    profile_dir = root / "scripts" / "translate" / "locales" / locale
    _write(locale_root / "SKILL.html", "<!doctype html>")
    _write(profile_dir / "SKILL.html", "<!doctype html>")
    _write(locale_root / "locale.json", json.dumps({
        "schema": "nemoclaw-locale/1", "locale": locale, "url_code": url_code,
        "label": f"Language {locale}", "native_label": f"Native {locale}",
        "profile": f"scripts/translate/locales/{locale}/profile.json",
        "source_root": "web", "overlay_root": f"i18n/{url_code}/web",
    }))
    _write(profile_dir / "profile.json", json.dumps({
        "schema": "nemoclaw-locale-profile/1", "locale": locale, "url_code": url_code,
        "label": f"Language {locale}", "native_label": f"Native {locale}", "html_lang": locale,
    }))
    _write(profile_dir / "shell_translations.json", json.dumps({SHELL_SOURCE: SHELL_TARGET}))
    _write(locale_root / "localization_state.json", json.dumps({
        "schema": "nemoclaw-localization-state/1", "locale": locale, "url_code": url_code,
        "overlay_files": [], "asset_files": [],
    }))


def _values(template_raw: str) -> dict[str, Any]:
    from translate.code_localization import code_templates
    from translate.locale_resources import (
        authored_structure,
        code_copy_segments,
        fallback_identity,
        template_units,
    )
    from translate.translate_html_segments import extract_segments

    units = template_units(template_raw)
    prose_count = len(extract_segments(authored_structure(template_raw)))
    reviewed = [
        TRANSLATIONS[unit.source.strip()]
        for unit in units[:prose_count]
    ]
    target_bodies = [CODE_TARGET] if code_templates(template_raw) else []
    reviewed.extend(
        segment.text
        for body in target_bodies
        for segment in code_copy_segments(body)
    )
    if len(reviewed) != len(units):
        raise AssertionError(
            f"fixture review count differs: units={len(units)} reviewed={len(reviewed)}")
    values: dict[str, Any] = {}
    for unit, translated in zip(units, reviewed):
        entry = {
            "type": unit.value_type, "source": unit.source, "value": translated,
        }
        if fallback_identity(unit.value_type, translated) == fallback_identity(
                unit.value_type, unit.source):
            entry["untranslated"] = "fixture review keeps this canonical code term"
        values[unit.key] = entry
    return values


def _resource(root: Path, url_code: str, locale: str, template: str, template_raw: str) -> Path:
    path = root / "i18n" / url_code / "resources" / f"{template}.json"
    _write(path, json.dumps({
        "schema": "nemoclaw-locale-resource/1", "locale": locale, "template": template,
        "values": _values(template_raw),
    }, indent=2, ensure_ascii=False) + "\n")
    return path


def build_fixture(root: Path) -> None:
    """Write a self-contained repository whose one locale translates one interactive template."""
    _write(root / "SKILL_CONTRACT.md", "# contract\n")
    _write(root / "AGENTS.md", "# agents\n")
    _write(root / TEMPLATE, TEMPLATE_HTML)
    _write(root / FIGURE, "<svg><text>Agent loop</text></svg>")
    _locale_files(root, URL_CODE, LOCALE)
    _resource(root, URL_CODE, LOCALE, TEMPLATE, TEMPLATE_HTML)
    from translate.localization_scope import translation_sha

    state_path = root / "i18n" / URL_CODE / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["reviews"] = {
        TEMPLATE: {
            "translation_sha256": translation_sha(TEMPLATE_HTML),
        }
    }
    _write(state_path, json.dumps(state))


def resource_path(root: Path, template: str = TEMPLATE, url_code: str = URL_CODE) -> Path:
    return root / "i18n" / url_code / "resources" / f"{template}.json"


def read_resource(root: Path, template: str = TEMPLATE) -> dict[str, Any]:
    return json.loads(resource_path(root, template).read_text(encoding="utf-8"))


def write_resource(root: Path, document: dict[str, Any], template: str = TEMPLATE) -> None:
    _write(resource_path(root, template),
           json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def key_for(document: dict[str, Any], value_type: str) -> str:
    """Return one key of the requested type without depending on a fixed key list."""
    return next(key for key, entry in document["values"].items() if entry["type"] == value_type)


def edit_value(root: Path, value_type: str, mutate: Callable[[str], str]) -> None:
    document = read_resource(root)
    key = key_for(document, value_type)
    document["values"][key]["value"] = mutate(document["values"][key]["value"])
    write_resource(root, document)


def code_copy_key(document: dict[str, Any], source: str | None = None) -> str:
    from translate.locale_resources import template_units

    return next(
        unit.key
        for unit in template_units(TEMPLATE_HTML)
        if unit.kind.startswith("code-") and (source is None or unit.source == source)
    )


def edit_code_copy(root: Path, source: str, mutate: Callable[[str], str]) -> None:
    document = read_resource(root)
    key = code_copy_key(document, source)
    document["values"][key]["value"] = mutate(document["values"][key]["value"])
    document["values"][key].pop("untranslated", None)
    write_resource(root, document)


def add_overlay(root: Path) -> None:
    """Publish the same page from a reviewed sparse overlay, as a migrating page does."""
    document = read_resource(root)
    overlay = render_overlay(TEMPLATE_HTML, document["values"], LOCALE)
    _write(root / "i18n" / URL_CODE / TEMPLATE, overlay)
    state_path = root / "i18n" / URL_CODE / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["overlay_files"] = [TEMPLATE]
    _write(state_path, json.dumps(state))


def declare_media(root: Path, *, present: bool = True, reviewed: bool = True) -> None:
    document = read_resource(root)
    document["media"] = [FIGURE]
    write_resource(root, document)
    if present:
        _write(root / "i18n" / URL_CODE / FIGURE, "<svg><text>Xx ciclo xx</text></svg>")
    if reviewed:
        state_path = root / "i18n" / URL_CODE / "localization_state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["asset_files"] = [FIGURE]
        review = {"source_sha256": _sha((root / FIGURE).read_text(encoding="utf-8"))}
        if present:
            review["target_sha256"] = _sha(
                (root / "i18n" / URL_CODE / FIGURE).read_text(encoding="utf-8")
            )
        state["asset_reviews"] = {FIGURE: review}
        _write(state_path, json.dumps(state))


def _review_resource(root: Path, url_code: str, template: str, template_raw: str) -> None:
    from translate.localization_scope import translation_sha

    state_path = root / "i18n" / url_code / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    scoped = 'data-localization-scope="en-shell"' in template_raw
    state.setdefault("reviews", {})[template] = {
        "translation_sha256" if scoped else "source_sha256": (
            translation_sha(template_raw) if scoped else _sha(template_raw)
        ),
    }
    _write(state_path, json.dumps(state))


def add_template_and_resource(root: Path) -> None:
    _write(root / SECOND_TEMPLATE, SECOND_HTML)
    _resource(root, URL_CODE, LOCALE, SECOND_TEMPLATE, SECOND_HTML)
    _review_resource(root, URL_CODE, SECOND_TEMPLATE, SECOND_HTML)


def add_formerly_skipped_template(root: Path) -> None:
    _write(root / NESTED_TEMPLATE, SECOND_HTML)
    _resource(root, URL_CODE, LOCALE, NESTED_TEMPLATE, SECOND_HTML)
    _review_resource(root, URL_CODE, NESTED_TEMPLATE, SECOND_HTML)


def add_locale(root: Path) -> None:
    second_locale, second_code = "zz-WW", "zz"
    _locale_files(root, second_code, second_locale)
    _resource(root, second_code, second_locale, TEMPLATE, TEMPLATE_HTML)
    _review_resource(root, second_code, TEMPLATE, TEMPLATE_HTML)


def drop_key(root: Path) -> None:
    document = read_resource(root)
    del document["values"][key_for(document, "text")]
    write_resource(root, document)


def delete_resource(root: Path) -> None:
    resource_path(root).unlink()


def rename_key(root: Path) -> None:
    document = read_resource(root)
    key = key_for(document, "text")
    document["values"][key.replace("text.", "text.0")] = document["values"].pop(key)
    write_resource(root, document)


def mistype_value(root: Path) -> None:
    document = read_resource(root)
    document["values"][key_for(document, "text")]["type"] = "rich"
    write_resource(root, document)


def unsupported_type(root: Path) -> None:
    document = read_resource(root)
    document["values"][key_for(document, "text")]["type"] = "html"
    write_resource(root, document)


def stale_source(root: Path) -> None:
    document = read_resource(root)
    document["values"][key_for(document, "text")]["source"] = "A heading that no longer exists"
    write_resource(root, document)


def hidden_fallback(root: Path, *, declared: bool = False) -> None:
    document = read_resource(root)
    entry = document["values"][key_for(document, "text")]
    entry["value"] = entry["source"]
    if declared:
        entry["untranslated"] = "product name stays in English"
    write_resource(root, document)


def emphasized_hidden_fallback(root: Path) -> None:
    document = read_resource(root)
    entry = document["values"][key_for(document, "text")]
    entry["value"] = f"<em>{entry['source']}</em>"
    write_resource(root, document)


def code_hidden_fallback(root: Path) -> None:
    document = read_resource(root)
    entry = document["values"][code_copy_key(document)]
    entry["value"] = entry["source"]
    write_resource(root, document)


def script_ui_injection(root: Path) -> None:
    from translate.locale_resources import template_units

    document = read_resource(root)
    key = next(unit.key for unit in template_units(TEMPLATE_HTML) if unit.kind == "script-ui")
    document["values"][key]["value"] += '"; globalThis.localeInjected = true; //'
    write_resource(root, document)


def missing_review_authority(root: Path) -> None:
    state_path = root / "i18n" / URL_CODE / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["reviews"].pop(TEMPLATE)
    _write(state_path, json.dumps(state))


def stale_review_authority(root: Path) -> None:
    state_path = root / "i18n" / URL_CODE / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["reviews"][TEMPLATE]["translation_sha256"] = "0" * 64
    _write(state_path, json.dumps(state))


def stale_target_authority(root: Path) -> None:
    profile_path = root / "scripts" / "translate" / "locales" / LOCALE / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["reviewed_target_hashes"] = True
    _write(profile_path, json.dumps(profile))
    state_path = root / "i18n" / URL_CODE / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["reviews"][TEMPLATE]["target_sha256"] = "0" * 64
    _write(state_path, json.dumps(state))


def boolean_fallback_reason(root: Path) -> None:
    document = read_resource(root)
    entry = document["values"][key_for(document, "text")]
    entry["value"] = entry["source"]
    entry["untranslated"] = True
    write_resource(root, document)


def generic_fallback_reason(root: Path) -> None:
    document = read_resource(root)
    entry = document["values"][key_for(document, "text")]
    entry["value"] = entry["source"]
    entry["untranslated"] = "matches the canonical English term"
    write_resource(root, document)


def unnecessary_fallback_reason(root: Path) -> None:
    document = read_resource(root)
    document["values"][key_for(document, "text")]["untranslated"] = (
        "This translated value does not need an English fallback."
    )
    write_resource(root, document)


def empty_value(root: Path) -> None:
    document = read_resource(root)
    document["values"][key_for(document, "attribute")]["value"] = ""
    write_resource(root, document)


def source_owned_button_drift(root: Path) -> None:
    document = read_resource(root)
    key = next(
        key for key, entry in document["values"].items()
        if "<button " in entry["source"]
    )
    document["values"][key]["value"] = document["values"][key]["value"].replace(
        'type="button"', 'type="submit"'
    )
    write_resource(root, document)


def rendered_locale_quality_failure(root: Path) -> None:
    profile_path = root / "scripts" / "translate" / "locales" / LOCALE / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["unfit_phrases"] = {
        "Xx ciclo xx": "replace the fixture phrase with reviewed locale wording",
    }
    _write(profile_path, json.dumps(profile))


def duplicate_json_key(root: Path) -> None:
    path = resource_path(root)
    raw = path.read_text(encoding="utf-8")
    raw = raw.replace(f'"locale": "{LOCALE}",', f'"locale": "{LOCALE}", "locale": "{LOCALE}",', 1)
    _write(path, raw)


def symlink_resource(root: Path) -> None:
    path = resource_path(root)
    outside = root / "outside-resource.json"
    shutil.move(str(path), outside)
    path.symlink_to(outside)


def symlink_template(root: Path) -> None:
    outside = root / "outside-template.html"
    _write(outside, SECOND_HTML)
    path = root / "web" / "course" / "symlinked.html"
    path.symlink_to(outside)


def omit_applicable_media(root: Path) -> None:
    declare_media(root)
    document = read_resource(root)
    document.pop("media")
    write_resource(root, document)


def stale_media_source_review(root: Path) -> None:
    declare_media(root)
    state_path = root / "i18n" / URL_CODE / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["asset_reviews"][FIGURE]["source_sha256"] = "0" * 64
    _write(state_path, json.dumps(state))


def stale_media_target_review(root: Path) -> None:
    declare_media(root)
    profile_path = root / "scripts" / "translate" / "locales" / LOCALE / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["reviewed_target_hashes"] = True
    _write(profile_path, json.dumps(profile))
    state_path = root / "i18n" / URL_CODE / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["asset_reviews"][FIGURE]["target_sha256"] = "0" * 64
    state["reviews"][TEMPLATE]["target_sha256"] = _sha(
        render_overlay(TEMPLATE_HTML, read_resource(root)["values"], LOCALE)
    )
    _write(state_path, json.dumps(state))


def symlink_localized_media(root: Path) -> None:
    declare_media(root)
    target = root / "i18n" / URL_CODE / FIGURE
    outside = root / "localized-media-outside.svg"
    shutil.move(str(target), outside)
    target.symlink_to(outside)


def symlink_localized_media_parent(root: Path) -> None:
    declare_media(root)
    parent = (root / "i18n" / URL_CODE / FIGURE).parent
    outside = root / "localized-media-parent-outside"
    shutil.move(str(parent), outside)
    parent.symlink_to(outside, target_is_directory=True)


def symlink_canonical_media(root: Path) -> None:
    declare_media(root)
    source = root / FIGURE
    outside = root / "canonical-media-outside.svg"
    shutil.move(str(source), outside)
    source.symlink_to(outside)


def _record_variant(root: Path, key: str, reason: str) -> None:
    state_path = root / "i18n" / URL_CODE / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.setdefault("shared_key_variants", {})[key] = reason
    _write(state_path, json.dumps(state))


def _repeated_key(document: dict[str, Any]) -> str:
    return next(
        key for key, entry in document["values"].items()
        if entry["source"].strip() == "The loop repeats until the budget runs out."
    )


def shared_key_conflict(root: Path) -> str:
    """Render one English source two ways across templates without recording the decision."""
    add_template_and_resource(root)
    document = read_resource(root, SECOND_TEMPLATE)
    key = _repeated_key(document)
    document["values"][key]["value"] += " different"
    write_resource(root, document, SECOND_TEMPLATE)
    return key


def recorded_shared_key_conflict(root: Path) -> None:
    """The same divergence, written down where the locale keeps its review decisions."""
    from translate.locale_resources import base_key

    key = shared_key_conflict(root)
    _record_variant(root, base_key(key),
                    "the reviewed locale renders this source differently on each page")


def stale_shared_key_record(root: Path) -> None:
    document = read_resource(root)
    _record_variant(root, key_for(document, "text"),
                    "a divergence that the locale has since reconciled")


def empty_shared_key_record(root: Path) -> None:
    document = read_resource(root)
    _record_variant(root, key_for(document, "text"), "   ")


def add_repeating_template(root: Path) -> None:
    """A template that consumes one English source twice, with one reviewed value per occurrence."""
    _write(root / REPEAT_TEMPLATE, REPEAT_HTML)
    _resource(root, URL_CODE, LOCALE, REPEAT_TEMPLATE, REPEAT_HTML)
    _review_resource(root, URL_CODE, REPEAT_TEMPLATE, REPEAT_HTML)


def _second_occurrence_key(document: dict[str, Any]) -> str:
    from translate.locale_resources import OCCURRENCE_SEPARATOR

    return next(key for key in document["values"] if OCCURRENCE_SEPARATOR in key)


def occurrence_divergence(root: Path) -> None:
    add_repeating_template(root)
    document = read_resource(root, REPEAT_TEMPLATE)
    document["values"][_second_occurrence_key(document)]["value"] += " xx otra vez xx"
    write_resource(root, document, REPEAT_TEMPLATE)


def recorded_occurrence_divergence(root: Path) -> None:
    from translate.locale_resources import base_key

    occurrence_divergence(root)
    document = read_resource(root, REPEAT_TEMPLATE)
    _record_variant(root, base_key(_second_occurrence_key(document)),
                    "the reviewed locale renders the two occurrences differently on this page")


def dropped_occurrence(root: Path) -> None:
    add_repeating_template(root)
    document = read_resource(root, REPEAT_TEMPLATE)
    del document["values"][_second_occurrence_key(document)]
    write_resource(root, document, REPEAT_TEMPLATE)


def add_verbatim_overlay(root: Path) -> None:
    """Publish a page with no English shell, which the assembler copies byte for byte."""
    add_template_and_resource(root)
    document = read_resource(root, SECOND_TEMPLATE)
    _write(root / "i18n" / URL_CODE / SECOND_TEMPLATE,
           render_overlay(SECOND_HTML, document["values"], LOCALE))
    state_path = root / "i18n" / URL_CODE / "localization_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["overlay_files"] = [SECOND_TEMPLATE]
    _write(state_path, json.dumps(state))


def verbatim_publication_drift(root: Path) -> None:
    add_verbatim_overlay(root)
    document = read_resource(root, SECOND_TEMPLATE)
    document["values"][_repeated_key(document)]["value"] += " xx cambiado xx"
    write_resource(root, document, SECOND_TEMPLATE)


def unsupported_file(root: Path) -> None:
    _write(root / "i18n" / URL_CODE / "resources" / "notes.txt", "scratch\n")


def unknown_template(root: Path) -> None:
    document = read_resource(root)
    document["template"] = "web/course/absent.html"
    write_resource(root, document)
    shutil.move(str(resource_path(root)), str(resource_path(root, "web/course/absent.html")))


def misplaced_resource(root: Path) -> None:
    shutil.move(str(resource_path(root)), str(resource_path(root, "web/course/other.html")))


def foreign_locale(root: Path) -> None:
    document = read_resource(root)
    document["locale"] = "zz-WW"
    write_resource(root, document)


def publication_drift(root: Path) -> None:
    add_overlay(root)
    edit_value(root, "text", lambda value: value + " xx cambiado xx")


MUTATIONS: tuple[tuple[str, Callable[[Path], None], str], ...] = (
    ("added template and resource", add_template_and_resource, ""),
    ("template in a formerly skipped directory", add_formerly_skipped_template, ""),
    ("added locale", add_locale, ""),
    ("reviewed overlay still published", add_overlay, ""),
    ("declared localized media", declare_media, ""),
    ("deleted resource file", delete_resource, "resource-missing"),
    ("deleted key", drop_key, "resource-key-missing"),
    ("renamed key", rename_key, "resource-key-unreachable"),
    ("wrong value type", mistype_value, "resource-value"),
    ("unsupported value type", unsupported_type, "resource-schema"),
    ("duplicate raw JSON key", duplicate_json_key, "resource-schema"),
    ("stale English source", stale_source, "resource-value"),
    ("unsafe markup", lambda root: edit_value(
        root, "rich", lambda value: value + "<script>alert(1)</script>"), "resource-value"),
    ("event handler markup", lambda root: edit_value(
        root, "link", lambda value: value.replace("<a ", "<a onclick=\"steal()\" ")), "resource-value"),
    ("event handler on neutral emphasis", lambda root: edit_value(
        root, "text", lambda value: f'<em onmouseover="steal()">{value}</em>'),
     "resource-value"),
    ("script UI string injection", script_ui_injection, "resource-render"),
    ("locale-only emphasis crossing a template tag", lambda root: edit_value(
        root, "link", lambda value: value.replace(
            ">formato xx</a>", "><em>formato xx</a></em>")),
     "resource-value"),
    ("broken link", lambda root: edit_value(
        root, "link", lambda value: value.replace("example.com/spec", "example.com/elsewhere")),
     "resource-value"),
    ("dropped protected code token", lambda root: edit_value(
        root, "rich", lambda value: value.replace("<code>helpers.log</code>", "el registro")),
     "resource-value"),
    ("dropped interpolation token", lambda root: edit_value(
        root, "placeholder", lambda value: value.replace("${limit}", "el limite")),
     "resource-value"),
    ("declared untranslated value", lambda root: hidden_fallback(root, declared=True), ""),
    ("boolean untranslated reason", boolean_fallback_reason, "resource-schema"),
    ("generic untranslated reason", generic_fallback_reason, "resource-schema"),
    ("unnecessary untranslated reason", unnecessary_fallback_reason, "resource-value"),
    ("hidden English fallback", hidden_fallback, "resource-value"),
    ("hidden English fallback wrapped in emphasis", emphasized_hidden_fallback, "resource-value"),
    ("hidden English fallback in runnable code", code_hidden_fallback, "resource-value"),
    ("missing resource publication review", missing_review_authority,
     "resource-hidden-fallback"),
    ("stale resource publication review", stale_review_authority,
     "resource-hidden-fallback"),
    ("unaccepted resource target", stale_target_authority,
     "resource-hidden-fallback"),
    ("empty attribute value", empty_value, "resource-schema"),
    ("markup in a plain text value", lambda root: edit_value(
        root, "text", lambda value: f"<strong>{value}</strong>"), "resource-value"),
    ("quote in an attribute value", lambda root: edit_value(
        root, "attribute", lambda value: f'{value} "xx"'), "resource-value"),
    ("single quote in an attribute value", lambda root: edit_value(
        root, "attribute", lambda value: f"{value} 'xx'"), "resource-value"),
    ("closing angle bracket in an attribute value", lambda root: edit_value(
        root, "attribute", lambda value: f"{value}>"), "resource-value"),
    ("link security attribute removed", lambda root: edit_value(
        root, "link", lambda value: value.replace(' rel="noopener"', "")), "resource-value"),
    ("link target behavior changed", lambda root: edit_value(
        root, "link", lambda value: value.replace('target="_blank"', 'target="_self"')),
     "resource-value"),
    ("template-owned button attribute drift", source_owned_button_drift, "resource-value"),
    ("runnable code contract drift", lambda root: edit_code_copy(
        root, "agent.plan", lambda value: "agente.plan"), "resource-render"),
    ("runnable string delimiter escape", lambda root: edit_code_copy(
        root, "Run agent <command>", lambda value: value + '"; globalThis.pwned = true; //'),
     "resource-value"),
    ("runnable code raw script escape", lambda root: edit_code_copy(
        root, "Run agent <command>", lambda value: value + "</script><script>alert(1)</script>"),
     "resource-value"),
    ("runnable placeholder renamed", lambda root: edit_code_copy(
        root, "Run agent <command>", lambda value: value.replace("<command>", "<comando>")),
     "resource-value"),
    ("undeclared localized media", lambda root: declare_media(root, reviewed=False),
     "resource-media-undeclared"),
    ("absent localized media", lambda root: declare_media(root, present=False),
     "resource-media-missing"),
    ("omitted applicable localized media", omit_applicable_media,
     "resource-media-missing-declaration"),
    ("stale localized media source review", stale_media_source_review,
     "resource-media-review-drift"),
    ("stale localized media target review", stale_media_target_review,
     "resource-media-target-drift"),
    ("symlinked localized media", symlink_localized_media,
     "resource-media-boundary"),
    ("symlinked localized media parent", symlink_localized_media_parent,
     "resource-media-boundary"),
    ("symlinked canonical media", symlink_canonical_media,
     "resource-media-boundary"),
    ("unsupported resource file", unsupported_file, "resource-unsupported-file"),
    ("resource for an unknown template", unknown_template, "resource-template-unreachable"),
    ("resource outside its template path", misplaced_resource, "resource-path"),
    ("resource declaring another locale", foreign_locale, "resource-locale"),
    ("template repeating one English source", add_repeating_template, ""),
    ("reviewed overlay with no English shell", add_verbatim_overlay, ""),
    ("unrecorded same-locale divergence across templates", shared_key_conflict,
     "resource-shared-key-unrecorded"),
    ("recorded same-locale divergence across templates", recorded_shared_key_conflict, ""),
    ("unrecorded divergence between two occurrences on one page", occurrence_divergence,
     "resource-shared-key-unrecorded"),
    ("recorded divergence between two occurrences on one page",
     recorded_occurrence_divergence, ""),
    ("dropped repeated-source occurrence", dropped_occurrence, "resource-key-missing"),
    ("shared-key record with no divergence", stale_shared_key_record,
     "resource-shared-key-record-unused"),
    ("empty shared-key record", empty_shared_key_record,
     "resource-shared-key-record-invalid"),
    ("rendered page drifts from a verbatim published overlay", verbatim_publication_drift,
     "resource-publication-drift"),
    ("rendered locale page quality failure", rendered_locale_quality_failure,
     "resource-rendered-quality"),
    ("symlinked resource", symlink_resource, "resource-discovery"),
    ("symlinked template", symlink_template, "resource-template-discovery"),
    ("rendered page drifts from the published overlay", publication_drift,
     "resource-publication-drift"),
)


def audit_findings(root: Path) -> list[dict[str, str]]:
    from locale_resource_audit import audit

    return audit(root)


def audit_codes(root: Path) -> list[str]:
    return [item["code"] for item in audit_findings(root)]


def run_mutations(build: Callable[[Path], None] = build_fixture) -> list[str]:
    """Apply every mutation to a pristine fixture and report the ones the gate misses."""
    import tempfile

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="locale-resource-") as directory:
        pristine = Path(directory) / "pristine"
        pristine.mkdir()
        build(pristine)
        baseline = audit_codes(pristine)
        if baseline:
            failures.append(f"clean fixture reported {baseline}")
        for index, (name, mutate, expected) in enumerate(MUTATIONS):
            case = Path(directory) / f"case-{index}"
            shutil.copytree(pristine, case)
            mutate(case)
            findings = audit_findings(case)
            codes = [item["code"] for item in findings]
            if expected and expected not in codes:
                failures.append(f"{name}: expected {expected}, gate reported {codes or 'nothing'}")
            elif expected:
                detail = next(item["detail"] for item in findings if item["code"] == expected)
                missing_context = [
                    token for token in (
                        "locale=", "rendered_page=", "consuming_templates=", "correction="
                    )
                    if token not in detail
                ]
                if missing_context:
                    failures.append(
                        f"{name}: {expected} diagnostic omitted {missing_context}"
                    )
            if not expected and codes:
                failures.append(f"{name}: supported change was rejected with {codes}")
    return failures
