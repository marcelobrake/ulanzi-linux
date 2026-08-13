"""Translation for the web editor, backed by GNU gettext ``.po`` catalogues.

Why ``.po`` is read directly rather than compiled to ``.mo``:
    ``.po`` is the file a translator edits, and keeping it as the only artifact
    removes the class of bug where a stale ``.mo`` silently wins over an edited
    ``.po``. The catalogues here are small (a couple of hundred entries), so
    parsing at startup costs nothing measurable and there is no build step to
    forget. ``msgfmt`` is never required.

Why the source language is Portuguese:
    The project was written in pt-BR and its UI shipped that way, so the
    Portuguese strings *are* the msgids. gettext places no constraint on the
    source language, and this keeps pt-BR working with no catalogue at all —
    an untranslated msgid simply falls through unchanged. English is therefore
    an ordinary translation like any other, and adding a third language means
    dropping in one more ``.po``.

The HTML is translated by parsing it, not by substring replacement: text nodes
and a whitelist of attributes are translated, while ``<script>`` bodies,
Alpine.js expression attributes, and everything else are left untouched. A
naive ``str.replace`` would happily corrupt JS inside ``<script>`` or rewrite
an attribute that merely happens to share a word with a UI label.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape
from html.parser import HTMLParser
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

LOCALES_DIR = Path(__file__).parent / "locales"

#: The language the msgids themselves are written in. Needs no catalogue.
SOURCE_LANGUAGE = "pt_BR"

DEFAULT_LANGUAGE = SOURCE_LANGUAGE

#: Attributes whose values are shown to the user and must be translated.
#: Deliberately narrow: ``x-text``, ``:class`` and friends hold JS expressions.
TRANSLATABLE_ATTRS = frozenset({"placeholder", "title", "aria-label"})

#: Element content that is code, not prose.
OPAQUE_ELEMENTS = frozenset({"script", "style"})

_VOID_ELEMENTS = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }
)


# --------------------------------------------------------------------------- #
# .po parsing                                                                  #
# --------------------------------------------------------------------------- #

_PO_LINE = re.compile(r'^\s*(msgid|msgstr)\s+"(.*)"\s*$')
_PO_CONTINUATION = re.compile(r'^\s*"(.*)"\s*$')
_PO_FLAGS = re.compile(r"^#,\s*(.*)$")

_ESCAPES = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    '\\"': '"',
    "\\\\": "\\",
}


def _unescape(raw: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(raw):
        pair = raw[index : index + 2]
        if pair in _ESCAPES:
            out.append(_ESCAPES[pair])
            index += 2
        else:
            out.append(raw[index])
            index += 1
    return "".join(out)


def parse_po(text: str) -> dict[str, str]:
    """Parse a ``.po`` file into a ``{msgid: msgstr}`` mapping.

    Handles multi-line strings and skips fuzzy entries, the header (empty
    msgid), and entries whose msgstr is empty — all three would otherwise
    translate a string into nothing.
    """
    catalog: dict[str, str] = {}
    msgid: list[str] = []
    msgstr: list[str] = []
    current: str | None = None
    fuzzy = False
    pending_fuzzy = False

    def flush() -> None:
        nonlocal fuzzy
        if current is not None and msgid:
            key = "".join(msgid)
            value = "".join(msgstr)
            if key and value and not fuzzy:
                catalog[key] = value
        fuzzy = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            flag_match = _PO_FLAGS.match(stripped)
            if flag_match and "fuzzy" in flag_match.group(1):
                pending_fuzzy = True
            continue

        keyword = _PO_LINE.match(line)
        if keyword:
            field, chunk = keyword.group(1), keyword.group(2)
            if field == "msgid":
                flush()
                msgid = [_unescape(chunk)]
                msgstr = []
                current = "msgid"
                fuzzy = pending_fuzzy
                pending_fuzzy = False
            else:
                msgstr = [_unescape(chunk)]
                current = "msgstr"
            continue

        continuation = _PO_CONTINUATION.match(line)
        if continuation and current is not None:
            chunk = _unescape(continuation.group(1))
            (msgid if current == "msgid" else msgstr).append(chunk)

    flush()
    return catalog


# --------------------------------------------------------------------------- #
# Catalogue loading                                                            #
# --------------------------------------------------------------------------- #


def available_languages() -> list[str]:
    """Every language with a catalogue on disk, plus the source language."""
    languages = {SOURCE_LANGUAGE}
    if LOCALES_DIR.is_dir():
        for entry in LOCALES_DIR.iterdir():
            if (entry / "LC_MESSAGES" / "ulanzi_web.po").is_file():
                languages.add(entry.name)
    return sorted(languages)


def load_catalog(language: str) -> dict[str, str]:
    """Load ``language``'s catalogue, or an empty one for the source language."""
    if not language or language == SOURCE_LANGUAGE:
        return {}
    po_path = LOCALES_DIR / language / "LC_MESSAGES" / "ulanzi_web.po"
    if not po_path.is_file():
        logger.warning("i18n_catalog_missing", language=language, path=str(po_path))
        return {}
    try:
        catalog = parse_po(po_path.read_text(encoding="utf-8"))
    except OSError as exc:
        logger.warning("i18n_catalog_unreadable", language=language, error=str(exc))
        return {}
    logger.info("i18n_catalog_loaded", language=language, entries=len(catalog))
    return catalog


def normalize_language(requested: str | None) -> str:
    """Map a user/browser language tag onto a catalogue we actually have.

    Accepts ``en``, ``en-GB``, ``en_US``, ``pt-BR`` and similar. Falls back to
    the source language rather than raising, so a bad ``--lang`` degrades to
    the shipped UI instead of failing to start.
    """
    if not requested:
        return DEFAULT_LANGUAGE
    tag = requested.strip().replace("-", "_")
    if not tag:
        return DEFAULT_LANGUAGE
    known = available_languages()
    for candidate in (tag, tag.lower()):
        if candidate in known:
            return candidate
    # Match on the primary subtag: "en_GB" -> "en", "pt_PT" -> "pt_BR".
    primary = tag.split("_", 1)[0].lower()
    for candidate in known:
        if candidate.lower() == primary or candidate.lower().startswith(primary + "_"):
            return candidate
    logger.warning("i18n_language_unknown", requested=requested, known=known)
    return DEFAULT_LANGUAGE


def parse_accept_language(header: str | None) -> list[str]:
    """Return the tags in an ``Accept-Language`` header, best quality first."""
    if not header:
        return []
    entries: list[tuple[float, str]] = []
    for index, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, _, params = piece.partition(";")
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                quality = 0.0
        # Preserve header order within an equal q-value.
        entries.append((-quality + index * 1e-6, tag.strip()))
    return [tag for _, tag in sorted(entries) if tag and tag != "*"]


class Translator:
    """A loaded catalogue plus the helpers that apply it."""

    def __init__(self, language: str) -> None:
        self.language = language
        self.catalog = load_catalog(language)

    def gettext(self, message: str) -> str:
        return self.catalog.get(message, message)

    __call__ = gettext

    def translate_html(self, html: str) -> str:
        if not self.catalog:
            return html
        return _HtmlTranslator(self.gettext).run(html)


# --------------------------------------------------------------------------- #
# HTML translation                                                             #
# --------------------------------------------------------------------------- #


class _HtmlTranslator(HTMLParser):
    """Rebuild an HTML document with its user-visible strings translated."""

    def __init__(self, gettext: Callable[[str], str]) -> None:
        super().__init__(convert_charrefs=False)
        self._gettext = gettext
        self._out: list[str] = []
        self._stack: list[str] = []

    def run(self, html: str) -> str:
        self._out = []
        self._stack = []
        self.feed(html)
        self.close()
        return "".join(self._out)

    # -- tags ------------------------------------------------------------- #

    def _render_attrs(self, attrs: list[tuple[str, str | None]]) -> str:
        parts: list[str] = []
        for name, value in attrs:
            if value is None:
                parts.append(f" {name}")
                continue
            if name in TRANSLATABLE_ATTRS and value.strip():
                value = self._gettext(value.strip())
            parts.append(f' {name}="{escape(value, quote=True)}"')
        return "".join(parts)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._out.append(f"<{tag}{self._render_attrs(attrs)}>")
        if tag not in _VOID_ELEMENTS:
            self._stack.append(tag)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._out.append(f"<{tag}{self._render_attrs(attrs)}/>")

    def handle_endtag(self, tag: str) -> None:
        self._out.append(f"</{tag}>")
        if tag in self._stack:
            while self._stack:
                if self._stack.pop() == tag:
                    break

    # -- content ---------------------------------------------------------- #

    def handle_data(self, data: str) -> None:
        if self._stack and self._stack[-1] in OPAQUE_ELEMENTS:
            self._out.append(data)
            return
        stripped = data.strip()
        if not stripped or not any(ch.isalpha() for ch in stripped):
            self._out.append(data)
            return
        translated = self._gettext(stripped)
        if translated == stripped:
            self._out.append(data)
            return
        # Preserve the original surrounding whitespace so layout is unchanged.
        leading = data[: len(data) - len(data.lstrip())]
        trailing = data[len(data.rstrip()) :]
        self._out.append(f"{leading}{translated}{trailing}")

    # -- pass-through ------------------------------------------------------ #

    def handle_comment(self, data: str) -> None:
        self._out.append(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._out.append(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._out.append(f"<?{data}>")

    def handle_entityref(self, name: str) -> None:
        self._out.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._out.append(f"&#{name};")

    def unknown_decl(self, data: str) -> None:  # pragma: no cover - rare
        self._out.append(f"<![{data}]>")
