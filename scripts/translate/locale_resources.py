# Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Typed, key-addressed locale resources derived from a canonical page template.

A resource holds one translated value per translatable unit the template consumes. Keys are
derived from the English source, so no page, locale, or key list is enumerated anywhere. A copy
edit changes the derived key of exactly the strings it touched, which localizes staleness to
those values instead of invalidating a whole page.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
import posixpath
import re
from pathlib import Path
from typing import Any, Iterable

from translate.code_localization import code_templates
from translate.localization_scope import translation_canonical
from translate.translate_html_segments import PLACEHOLDER_RE, extract_segments

RESOURCE_SCHEMA = "nemoclaw-locale-resource/1"
RESOURCE_DIR = "resources"
KEY_DIGITS = 12
# A template may consume the same English source more than once, and a language reviewer may
# legitimately render those occurrences differently. The reviewed unit is therefore the occurrence,
# not the string, so every occurrence after the first carries its ordinal.
OCCURRENCE_SEPARATOR = "~"
VALUE_TYPES = ("text", "attribute", "rich", "link", "placeholder")
ENTRY_REQUIRED = ("type", "source", "value")
ENTRY_OPTIONAL = ("untranslated",)
RESOURCE_REQUIRED = ("schema", "locale", "template", "values")
RESOURCE_OPTIONAL = ("media",)
GENERIC_UNTRANSLATED_REASONS = {
    "matches the canonical english term",
    "same as source",
    "untranslated",
}
TRANSLATABLE_MARKUP_ATTRS = {"alt", "aria-label", "placeholder", "title"}
SHELL_SCOPE_MARKER = 'data-localization-scope="en-shell"'

# Italics carry a foreign term, not document structure, so a translation may add them where the
# English source had none. Every other tag must already exist in the unit it translates.
NEUTRAL_TAGS = {"i", "em"}
EXECUTABLE_TAGS = {"script", "style", "iframe", "object", "embed", "form", "input", "button",
                   "link", "meta", "base", "template", "frame", "frameset"}
VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
    "source", "track", "wbr",
}
# The reviewed segment-token contract: only these tokens bind a translation to its source.
CONTRACT_PREFIXES = ("<code", "<kbd", "http", "${", "{{", "nvapi-")
ROUTE_RE = re.compile(r"(?<!\w)/(?:[A-Za-z0-9_.{}:<>-]+/?)+")
URL_RE = re.compile(r"https?://[^\s<\"']+", re.I)
TAG_RE = re.compile(r"<\s*(/?)\s*([A-Za-z][A-Za-z0-9-]*)((?:\s+[^<>]*?)?)/?\s*>")
ATTR_RE = re.compile(r"([A-Za-z-]+)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s\"'<>]+)")
HREF_RE = re.compile(r"""\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'<>]+))""", re.I)
ANCHOR_RE = re.compile(r"<\s*a\b", re.I)
MARKUP_RE = re.compile(r"<\s*[A-Za-z]")
INTERPOLATION_RE = re.compile(r"\$\{[^}]*\}|\{\{[^}]*\}\}")
UNSAFE_URL_RE = re.compile(r"^\s*(?:javascript|data|vbscript)\s*:", re.I)
EVENT_ATTR_RE = re.compile(r"^on[a-z]+$", re.I)
ASSET_REF_RE = re.compile(r"""(?:src|href|data-src)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
SCRIPT_END_RE = re.compile(r"</script(?=[\t\n\r\f />])", re.I)
NEUTRAL_TAG_RE = re.compile(r"</?\s*(?:i|em)\b[^>]*>", re.I)


class LocaleResourceError(ValueError):
    """A locale resource is malformed, unreachable, or unsafe to render."""


@dataclass(frozen=True)
class TemplateUnit:
    """One translatable unit a template consumes, addressed by its derived key."""

    key: str
    value_type: str
    source: str
    kind: str


@dataclass(frozen=True)
class CodeCopySegment:
    """One comment or string body inside template-owned runnable code."""

    start: int
    end: int
    text: str
    kind: str


@dataclass(frozen=True)
class LocaleResource:
    """One loaded resource file bound to the template it translates."""

    path: Path
    locale: str
    template: str
    values: dict[str, dict[str, Any]]
    media: tuple[str, ...]


def normalize(text: str) -> str:
    """Collapse authoring whitespace so formatting alone never changes a key."""
    return " ".join(text.split())


def source_identity(kind: str, source: str) -> str:
    """Return key identity without erasing whitespace that can change runnable behavior."""
    if kind.startswith("code-"):
        return source.replace("\r\n", "\n")
    return normalize(source)


def fallback_identity(value_type: str, text: str) -> str:
    """Compare reader-visible copy so emphasis or entities cannot disguise English fallback."""
    return normalize(html.unescape(NEUTRAL_TAG_RE.sub("", text)))


def derive_type(kind: str, source: str) -> str:
    """Classify one unit from its English source; the resource must declare the same type."""
    if kind == "attribute":
        return "attribute"
    if ANCHOR_RE.search(source):
        return "link"
    if MARKUP_RE.search(source):
        return "rich"
    if INTERPOLATION_RE.search(source):
        return "placeholder"
    return "text"


def unit_identity(kind: str, source: str) -> tuple[str, str]:
    """Return the typed content identity two occurrences must share to be the same unit."""
    return derive_type(kind, source), source_identity(kind, source)


def derive_key(kind: str, source: str, occurrence: int = 0) -> str:
    """Address a unit by type, English content, and its ordinal within the template.

    Moving a unit does not rename it, and editing English renames only the edited unit. Repeating
    the same English source inside one template yields distinct keys, so a reviewer who renders two
    occurrences differently is representable instead of being a migration blocker.
    """
    value_type, identity = unit_identity(kind, source)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    key = f"{value_type}.{digest[:KEY_DIGITS]}"
    return key if occurrence == 0 else f"{key}{OCCURRENCE_SEPARATOR}{occurrence}"


def base_key(key: str) -> str:
    """Return the content-derived address shared by every occurrence of one English source."""
    return key.split(OCCURRENCE_SEPARATOR, 1)[0]


def has_english_shell(source_raw: str) -> bool:
    """Report whether a template wraps its translatable body in an English-only shell."""
    return SHELL_SCOPE_MARKER in source_raw


def authored_structure(source_raw: str) -> str:
    """Return the exact document a locale's reviewed prose is substituted into.

    A shell-scoped page publishes by projecting its reviewed body back onto the full template, so
    its units live in the canonical body. Every other page publishes the localized document itself,
    so its units live in the template's own bytes. Deriving units from the canonicalized form of a
    page that publishes verbatim would silently reserialize the shipped HTML.
    """
    return translation_canonical(source_raw) if has_english_shell(source_raw) else source_raw


def _regex_literal_end(body: str, index: int) -> int | None:
    """Return the end of a JavaScript regex literal, or ``None`` for division.

    The runnable-copy scanner is deliberately small, but it still must not mistake quotes in a
    regex character class for localized strings. A slash can begin a regex only where JavaScript
    expects an expression; the preceding significant character is sufficient for the course-cell
    syntax and avoids swallowing ordinary division.
    """
    previous = index - 1
    while previous >= 0 and body[previous].isspace():
        previous -= 1
    if previous >= 0 and body[previous] not in "([{:;,=!?&|":
        return None
    cursor = index + 1
    in_class = False
    while cursor < len(body):
        char = body[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "[":
            in_class = True
        elif char == "]":
            in_class = False
        elif char == "/" and not in_class:
            cursor += 1
            while cursor < len(body) and body[cursor].isalpha():
                cursor += 1
            return cursor
        elif char in "\r\n":
            return None
        cursor += 1
    return None


def code_copy_segments(body: str) -> list[CodeCopySegment]:
    r"""Discover translatable copy inside runnable code without owning its syntax.

    Runnable bodies are JavaScript embedded in an outer template literal. Inner template-string
    delimiters are therefore encoded as ``\``` in the authored HTML. Comments and string bodies
    become resource values; delimiters, operators, calls, identifiers, and control flow stay only
    in the shared template.
    """
    out: list[CodeCopySegment] = []
    index = 0
    while index < len(body):
        if body.startswith("//", index):
            start = index + 2
            end = body.find("\n", start)
            end = len(body) if end < 0 else end
            if body[start:end].strip():
                out.append(CodeCopySegment(start, end, body[start:end], "code-line-comment"))
            index = end
            continue
        if body.startswith("/*", index):
            start = index + 2
            close = body.find("*/", start)
            if close < 0:
                raise LocaleResourceError("runnable code contains an unterminated block comment")
            if body[start:close].strip():
                out.append(CodeCopySegment(
                    start, close, body[start:close], "code-block-comment"))
            index = close + 2
            continue
        if body[index] == "/":
            regex_end = _regex_literal_end(body, index)
            if regex_end is not None:
                index = regex_end
                continue
        encoded_template = body.startswith("\\`", index)
        if encoded_template or body[index] in {'"', "'"}:
            delimiter = "\\`" if encoded_template else body[index]
            kind = {
                '"': "code-double-string",
                "'": "code-single-string",
                "\\`": "code-template-string",
            }[delimiter]
            start = index + len(delimiter)
            cursor = start
            while cursor < len(body):
                if delimiter == "\\`" and body.startswith("\\`", cursor):
                    break
                if delimiter != "\\`" and body[cursor] == delimiter:
                    break
                if body[cursor] == "\\":
                    cursor += 2
                else:
                    cursor += 1
            if cursor >= len(body):
                raise LocaleResourceError(
                    f"runnable code contains an unterminated {kind.replace('-', ' ')}")
            if body[start:cursor].strip():
                out.append(CodeCopySegment(start, cursor, body[start:cursor], kind))
            index = cursor + len(delimiter)
            continue
        index += 1
    return out


def template_units(source_raw: str) -> list[TemplateUnit]:
    """Return every translatable unit of one canonical template, in document order."""
    units: list[TemplateUnit] = []
    seen: dict[tuple[str, str], int] = {}
    sources: list[tuple[str, str]] = [
        (segment.kind, segment.text)
        for segment in extract_segments(authored_structure(source_raw))
    ]
    sources.extend(
        (segment.kind, segment.text)
        for body in code_templates(source_raw)
        for segment in code_copy_segments(body)
    )
    for kind, source in sources:
        identity = unit_identity(kind, source)
        occurrence = seen.get(identity, 0)
        seen[identity] = occurrence + 1
        units.append(TemplateUnit(
            derive_key(kind, source, occurrence), identity[0], source, kind))
    return units


def consumer_map(templates: dict[str, str]) -> dict[str, list[str]]:
    """Map each derived key, and each key's shared content address, to its consuming templates."""
    consumers: dict[str, list[str]] = {}
    identities: dict[str, tuple[str, str, str]] = {}
    for template, raw in sorted(templates.items()):
        for unit in template_units(raw):
            identity = (
                unit.value_type,
                source_identity(unit.kind, unit.source),
                template,
            )
            previous = identities.get(unit.key)
            if previous is not None and previous[:2] != identity[:2]:
                raise LocaleResourceError(
                    f"{unit.key}: derived key collision between templates "
                    f"{previous[2]} and {template}"
                )
            identities.setdefault(unit.key, identity)
            for address in {unit.key, base_key(unit.key)}:
                owners = consumers.setdefault(address, [])
                if template not in owners:
                    owners.append(template)
    return consumers


def contract_tokens(text: str) -> list[str]:
    """Return the protected tokens a translation must reproduce exactly, as the page gate does."""
    protected = [token for token in PLACEHOLDER_RE.findall(text)
                 if token.lower().startswith(CONTRACT_PREFIXES)]
    visible = re.sub(r"<[^>]+>", " ", text)
    return sorted(protected + URL_RE.findall(text) + ROUTE_RE.findall(visible))


def _markup_signature(
    text: str,
) -> list[tuple[str, str, tuple[tuple[str, str | None], ...], tuple[str, ...]]]:
    """Describe structural tags, attributes, and non-translatable attribute values."""
    signature = []
    for match in TAG_RE.finditer(text):
        if match.group(2).lower() in NEUTRAL_TAGS:
            continue
        raw_attributes = match.group(3) or ""
        attributes = []
        for attribute in ATTR_RE.finditer(raw_attributes):
            name = attribute.group(1).lower()
            value = html.unescape(attribute.group(2).strip("\"'"))
            attributes.append((
                name,
                None if name in TRANSLATABLE_MARKUP_ATTRS else value,
            ))
        residue = ATTR_RE.sub(" ", raw_attributes).replace("/", " ")
        signature.append((
            "/" if match.group(1) else "",
            match.group(2).lower(),
            tuple(sorted(attributes)),
            tuple(residue.split()),
        ))
    return signature


def _safe_tag_findings(
    value: str,
    template_executable_tags: set[str] | None = None,
) -> list[str]:
    out: list[str] = []
    allowed = template_executable_tags or set()
    for match in TAG_RE.finditer(value):
        tag = match.group(2).lower()
        if tag in EXECUTABLE_TAGS and tag not in allowed:
            out.append(f"tag <{tag}> is executable and is not allowed in a locale value")
        for attribute in ATTR_RE.finditer(match.group(3) or ""):
            name = attribute.group(1).lower()
            raw_value = html.unescape(attribute.group(2).strip("\"'"))
            if EVENT_ATTR_RE.fullmatch(name):
                out.append(f"attribute {name!r} on <{tag}> is executable")
            elif name in {"href", "src"} and UNSAFE_URL_RE.match(raw_value):
                out.append(f"attribute {name} uses an unsafe scheme: {raw_value!r}")
    return out


def _neutral_markup_findings(value: str) -> list[str]:
    """Allow locale-only i/em emphasis, but never attributes or malformed markup."""
    out = _safe_tag_findings(value)
    residue = TAG_RE.sub("", value)
    if "<" in residue or ">" in residue:
        out.append("plain text contains malformed or unsupported markup")
    stack: list[str] = []
    for match in TAG_RE.finditer(value):
        tag = match.group(2).lower()
        attrs = tuple(ATTR_RE.finditer(match.group(3) or ""))
        if tag not in NEUTRAL_TAGS:
            out.append(f"plain text may add <i> or <em> emphasis only, not <{tag}>")
        elif attrs or (match.group(3) or "").strip():
            out.append(f"locale-only <{tag}> emphasis may not carry attributes")
        if tag in NEUTRAL_TAGS:
            if match.group(1):
                if not stack or stack.pop() != tag:
                    out.append("locale-only emphasis tags must be balanced and properly nested")
            else:
                stack.append(tag)
    if stack:
        out.append("locale-only emphasis tags must be balanced and properly nested")
    return out


def _tag_balance_findings(value: str) -> list[str]:
    """Reject markup whose source-order nesting would be repaired differently by a browser."""
    stack: list[str] = []
    for match in TAG_RE.finditer(value):
        tag = match.group(2).lower()
        closing = bool(match.group(1))
        self_closing = match.group(0).rstrip().endswith("/>")
        if closing:
            if not stack or stack[-1] != tag:
                return [f"markup tags must be balanced and properly nested near </{tag}>"]
            stack.pop()
        elif tag not in VOID_TAGS and not self_closing:
            stack.append(tag)
    if stack:
        return [f"markup tags must be balanced and properly nested; unclosed <{stack[-1]}>"]
    return []


def _markup_findings(source: str, value: str) -> list[str]:
    """Preserve source tag and attribute-name structure, plus attribute-free emphasis."""
    template_executable_tags = {
        match.group(2).lower()
        for match in TAG_RE.finditer(source)
        if match.group(2).lower() in EXECUTABLE_TAGS
    }
    out = _safe_tag_findings(value, template_executable_tags)
    if _markup_signature(source) != _markup_signature(value):
        out.append(
            "markup tags, attributes, and structural attribute values must match the template "
            "unit exactly; only translated accessibility text and attribute-free <i>/<em> "
            "emphasis may differ"
        )
    # Canonical HTML can legally rely on optional end tags. Do not impose a stronger syntax rule on
    # such a unit, but when the template is explicitly balanced require the locale value to remain
    # balanced too. This catches locale-only emphasis crossing an anchor or other template tag,
    # which HTMLParser-based skeleton checks intentionally ignore as structure-neutral markup.
    if not _tag_balance_findings(source):
        out.extend(_tag_balance_findings(value))
    residue = TAG_RE.sub("", value)
    if "<" in residue or ">" in residue:
        out.append("rich value contains malformed or unsupported markup")
    for match in TAG_RE.finditer(value):
        tag = match.group(2).lower()
        if tag in NEUTRAL_TAGS and (
                tuple(ATTR_RE.finditer(match.group(3) or "")) or (match.group(3) or "").strip()):
            out.append(f"locale-only <{tag}> emphasis may not carry attributes")
    neutral_only = "".join(
        match.group(0) for match in TAG_RE.finditer(value)
        if match.group(2).lower() in NEUTRAL_TAGS
    )
    out.extend(item for item in _neutral_markup_findings(neutral_only)
               if "balanced" in item or "attributes" in item)
    return out


def _link_findings(source: str, value: str) -> list[str]:
    source_targets = sorted(_hrefs(source))
    value_targets = sorted(_hrefs(value))
    if source_targets != value_targets:
        return [f"link targets changed: template {source_targets} rendered {value_targets}"]
    return []


def _hrefs(text: str) -> list[str]:
    return [next(group for group in match.groups() if group is not None)
            for match in HREF_RE.finditer(text)]


def _code_copy_findings(unit: TemplateUnit, value: str) -> list[str]:
    """Reject a locale value that would escape its template-owned comment or string."""
    if SCRIPT_END_RE.search(value):
        return ["runnable code copy contains a raw script end tag"]
    if unit.kind == "code-line-comment" and ("\n" in value or "\r" in value):
        return ["a runnable line-comment value cannot add a line break"]
    if unit.kind == "code-block-comment" and "*/" in value:
        return ["a runnable block-comment value cannot close the template-owned comment"]
    delimiters = {
        "code-double-string": '"',
        "code-single-string": "'",
        "code-template-string": "\\`",
    }
    delimiter = delimiters.get(unit.kind)
    if delimiter is None:
        return []
    if delimiter != "\\`" and ("\n" in value or "\r" in value):
        return ["a quoted runnable string value cannot add a raw line break"]
    try:
        segments = code_copy_segments(f"{delimiter}{value}{delimiter}")
    except LocaleResourceError as exc:
        return [str(exc)]
    if len(segments) != 1 or segments[0].text != value or segments[0].kind != unit.kind:
        return [f"locale copy escapes its template-owned {unit.kind} delimiter"]
    return []


def _code_markup_findings(unit: TemplateUnit, value: str) -> list[str]:
    """Keep HTML-like syntax inside a runnable string identical to the shared template.

    Course cells construct trace rows from string fragments, so an individual quoted value can
    contain only an opening or closing tag and cannot be validated as a standalone rich fragment.
    Comparing the tag/attribute signature and raw angle-bracket counts preserves that syntax while
    still allowing its reader-visible text to be translated.
    """
    template_executable_tags = {
        match.group(2).lower()
        for match in TAG_RE.finditer(unit.source)
        if match.group(2).lower() in EXECUTABLE_TAGS
    }
    out = _safe_tag_findings(value, template_executable_tags)
    if _markup_signature(unit.source) != _markup_signature(value):
        out.append(
            "markup tags and attributes inside runnable copy must match the template exactly"
        )
    return out


def value_findings(unit: TemplateUnit, entry: dict[str, Any]) -> list[str]:
    """Return every typed-value defect for one resource entry against its template unit."""
    value = entry["value"]
    out: list[str] = []
    if entry["type"] != unit.value_type:
        out.append(f"declared type {entry['type']!r} but the template unit is {unit.value_type!r}")
    if source_identity(unit.kind, entry["source"]) != source_identity(unit.kind, unit.source):
        out.append("recorded English source no longer matches the template")
    if unit.kind.startswith("code-"):
        out.extend(_code_copy_findings(unit, value))
        out.extend(_code_markup_findings(unit, value))
    elif unit.value_type == "attribute" and any(char in value for char in "\"'<>"):
        out.append("an attribute value cannot contain quotes or angle brackets")
    elif unit.value_type in {"text", "placeholder"}:
        out.extend(_neutral_markup_findings(value))
    elif unit.value_type in {"rich", "link"}:
        out.extend(_markup_findings(unit.source, value))
    if unit.value_type == "link":
        out.extend(_link_findings(unit.source, value))
    if contract_tokens(unit.source) != contract_tokens(value):
        out.append(
            f"protected tokens differ: template {contract_tokens(unit.source)} "
            f"rendered {contract_tokens(value)}"
        )
    repeats_source = (
        fallback_identity(unit.value_type, value)
        == fallback_identity(unit.value_type, unit.source)
    )
    if repeats_source and not entry.get("untranslated"):
        out.append("value repeats the English source; declare 'untranslated' with a reason instead")
    if entry.get("untranslated") and not repeats_source:
        out.append("untranslated is allowed only when the locale value repeats the English source")
    return out


def template_assets(source_raw: str) -> set[str]:
    """Return every local asset reference a template makes, for media-override checks."""
    out: set[str] = set()
    for match in ASSET_REF_RE.finditer(source_raw):
        reference = (match.group(1) or match.group(2) or "").strip()
        if reference and "://" not in reference and not reference.startswith(("#", "data:", "mailto:")):
            out.add(reference.split("?", 1)[0].split("#", 1)[0])
    return out


def resolved_template_assets(template: str, source_raw: str) -> set[str]:
    """Resolve local references against a repository-relative template path."""
    base = Path(template).parent.as_posix()
    out: set[str] = set()
    for reference in template_assets(source_raw):
        if reference.startswith("/"):
            continue
        candidate = posixpath.normpath(posixpath.join(base, reference))
        if candidate == ".." or candidate.startswith("../"):
            continue
        out.add(candidate)
    return out


def applicable_media(template: str, source_raw: str, asset_files: Iterable[str]) -> tuple[str, ...]:
    """Return reviewed locale assets the template actually references."""
    declared = {Path(item).as_posix() for item in asset_files}
    return tuple(sorted(resolved_template_assets(template, source_raw) & declared))


def _entry_findings(key: str, entry: Any) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{key}: entry must be an object"]
    missing = [field for field in ENTRY_REQUIRED if field not in entry]
    extra = sorted(set(entry) - set(ENTRY_REQUIRED) - set(ENTRY_OPTIONAL))
    out = []
    if missing:
        out.append(f"{key}: entry is missing {missing}")
    if extra:
        out.append(f"{key}: entry has unsupported fields {extra}")
    for field in ENTRY_REQUIRED:
        if field in entry and not isinstance(entry[field], str):
            out.append(f"{key}: {field} must be a string")
        elif field in {"source", "value"} and field in entry and not entry[field].strip():
            out.append(f"{key}: {field} must be a non-empty string")
    if isinstance(entry.get("type"), str) and entry["type"] not in VALUE_TYPES:
        out.append(f"{key}: unsupported value type {entry['type']!r}; use one of {list(VALUE_TYPES)}")
    if "untranslated" in entry and (
            not isinstance(entry["untranslated"], str) or not entry["untranslated"].strip()):
        out.append(f"{key}: untranslated must be a non-empty reason")
    elif (
        isinstance(entry.get("untranslated"), str)
        and entry["untranslated"].strip().casefold() in GENERIC_UNTRANSLATED_REASONS
    ):
        out.append(f"{key}: untranslated reason is generic; record the reviewed locale decision")
    return out


def safe_template_path(raw: Any, source_root: str) -> Path:
    """Resolve a declared template reference or refuse it."""
    if not isinstance(raw, str) or not raw.strip():
        raise LocaleResourceError("template must be a non-empty string")
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != source_root:
        raise LocaleResourceError(f"template must stay inside {source_root}/: {raw}")
    return path


def bounded_tree_path(root: Path, raw: Any, *, source_root: str = "web") -> Path:
    """Resolve one repository-relative path without following a symlink boundary.

    Locale resources, templates, and media all become publication input. Checking only
    ``Path.is_file`` would follow a symlinked file or parent and let bytes outside the declared
    canonical or locale tree become part of the rendered course.
    """
    relative = safe_template_path(raw, source_root)
    if root.is_symlink():
        raise LocaleResourceError(f"{root}: publication root must not be a symlink")
    candidate = root / relative
    current = candidate
    while current != root:
        if current.is_symlink():
            raise LocaleResourceError(
                f"{candidate}: publication input must not use symlink {current}"
            )
        if root not in current.parents:
            raise LocaleResourceError(f"{candidate}: publication input escapes {root}")
        current = current.parent
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise LocaleResourceError(f"{candidate}: publication input escapes {root}") from exc
    return candidate


def load_resource(path: Path, *, source_root: str = "web") -> LocaleResource:
    """Load one resource file and reject any structural or schema defect."""
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise LocaleResourceError(f"{path}: locale resource must not use symlinks")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise LocaleResourceError(f"duplicate JSON key {key!r}")
            value[key] = item
        return value

    try:
        document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, json.JSONDecodeError, LocaleResourceError) as exc:
        raise LocaleResourceError(f"{path}: cannot read locale resource: {exc}") from exc
    if not isinstance(document, dict):
        raise LocaleResourceError(f"{path}: locale resource must be a JSON object")
    if document.get("schema") != RESOURCE_SCHEMA:
        raise LocaleResourceError(f"{path}: schema must be {RESOURCE_SCHEMA}")
    missing = [field for field in RESOURCE_REQUIRED if field not in document]
    extra = sorted(set(document) - set(RESOURCE_REQUIRED) - set(RESOURCE_OPTIONAL))
    if missing or extra:
        raise LocaleResourceError(f"{path}: fields invalid; missing={missing} unsupported={extra}")
    template = safe_template_path(document["template"], source_root)
    values = document["values"]
    if not isinstance(values, dict) or not values:
        raise LocaleResourceError(f"{path}: values must be a non-empty object")
    findings = [item for key, entry in values.items() for item in _entry_findings(key, entry)]
    if findings:
        raise LocaleResourceError(f"{path}: " + "; ".join(findings))
    media = document.get("media", [])
    if not isinstance(media, list) or not all(isinstance(item, str) and item for item in media):
        raise LocaleResourceError(f"{path}: media must be a list of locale asset paths")
    if len(media) != len(set(media)):
        raise LocaleResourceError(f"{path}: media contains duplicate asset paths")
    for item in media:
        safe_template_path(item, source_root)
    locale = document["locale"]
    if not isinstance(locale, str) or not locale.strip():
        raise LocaleResourceError(f"{path}: locale must be a non-empty string")
    return LocaleResource(path=path, locale=locale, template=template.as_posix(),
                          values=values, media=tuple(media))


def resource_root(locale_root: Path) -> Path:
    """Return the directory that holds one locale's key-based resources."""
    return locale_root / RESOURCE_DIR


def resource_files(locale_root: Path) -> list[Path]:
    """Discover every candidate resource file without an opt-in list."""
    root = resource_root(locale_root)
    if not root.is_dir():
        return []
    if root.is_symlink():
        raise LocaleResourceError(f"{root}: resource directory must not be a symlink")
    entries = sorted(root.rglob("*"))
    symlinks = [path for path in entries if path.is_symlink()]
    if symlinks:
        raise LocaleResourceError(
            f"{symlinks[0]}: locale resources must be regular files inside {root}"
        )
    root_resolved = root.resolve()
    files: list[Path] = []
    for path in entries:
        if not path.is_file():
            continue
        try:
            path.resolve().relative_to(root_resolved)
        except ValueError as exc:
            raise LocaleResourceError(f"{path}: locale resource escapes {root}") from exc
        files.append(path)
    return files


def unsupported_files(locale_root: Path) -> list[Path]:
    """Return discovered files a resource directory is not allowed to carry."""
    return [path for path in resource_files(locale_root)
            if path.suffix != ".json" and path.name != "SKILL.html"]


def json_resources(locale_root: Path) -> list[Path]:
    return [path for path in resource_files(locale_root) if path.suffix == ".json"]


def expected_resource_path(locale_root: Path, template: str) -> Path:
    """Return the one path a template's resource may occupy inside a locale."""
    return resource_root(locale_root) / f"{template}.json"


def dump_resource(resource: dict[str, Any]) -> str:
    """Serialize a resource with stable ordering so regeneration is byte-reproducible."""
    ordered = {
        field: resource[field]
        for field in RESOURCE_REQUIRED
        if field in resource and field != "values"
    }
    ordered.update({field: resource[field] for field in RESOURCE_OPTIONAL if field in resource})
    ordered["values"] = {key: resource["values"][key] for key in sorted(resource["values"])}
    return json.dumps(ordered, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def validate_values(source_raw: str, values: Any) -> dict[str, TemplateUnit]:
    """Fail closed unless values are a complete, typed, safe rendering of the template."""
    if not isinstance(values, dict) or not values:
        raise LocaleResourceError("values must be a non-empty object")
    entry_errors = [
        detail
        for key, entry in values.items()
        for detail in _entry_findings(key, entry)
    ]
    if entry_errors:
        raise LocaleResourceError("; ".join(entry_errors))
    required: dict[str, TemplateUnit] = {}
    for unit in template_units(source_raw):
        previous = required.get(unit.key)
        if previous is not None and (
                previous.value_type != unit.value_type
                or source_identity(previous.kind, previous.source)
                != source_identity(unit.kind, unit.source)):
            raise LocaleResourceError(
                f"{unit.key}: two distinct template units collide on one derived key"
            )
        required[unit.key] = unit
    missing = sorted(set(required) - set(values))
    extra = sorted(set(values) - set(required))
    if missing or extra:
        raise LocaleResourceError(
            f"resource keys differ from the template; missing={missing} unused={extra}"
        )
    findings = [
        f"{key}: {detail}"
        for key, unit in required.items()
        for detail in value_findings(unit, values[key])
    ]
    if findings:
        raise LocaleResourceError("; ".join(findings))
    return required
