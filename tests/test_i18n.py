"""Tests for the web editor's gettext-backed translation layer."""

from __future__ import annotations

import re
from pathlib import Path

from ulanzi_linux.interface.web.i18n import (
    DEFAULT_LANGUAGE,
    SOURCE_LANGUAGE,
    Translator,
    available_languages,
    normalize_language,
    parse_accept_language,
    parse_po,
)

STATIC_DIR = Path(__file__).resolve().parents[1] / "src/ulanzi_linux/interface/web/static"

# --- .po parsing -----------------------------------------------------------


def test_parses_simple_entries() -> None:
    catalog = parse_po(
        '''
msgid "Recarregar"
msgstr "Reload"

msgid "Validar"
msgstr "Validate"
'''
    )
    assert catalog == {"Recarregar": "Reload", "Validar": "Validate"}


def test_joins_multiline_strings() -> None:
    catalog = parse_po(
        '''
msgid ""
"uma frase "
"partida em duas"
msgstr ""
"one sentence "
"split in two"
'''
    )
    assert catalog == {"uma frase partida em duas": "one sentence split in two"}


def test_skips_header_comments_and_empty_translations() -> None:
    """A header, a comment, and an untranslated entry must not become entries."""
    catalog = parse_po(
        '''
# a translator comment
msgid ""
msgstr "Content-Type: text/plain; charset=UTF-8\\n"

msgid "Traduzido"
msgstr "Translated"

msgid "Ainda nao traduzido"
msgstr ""
'''
    )
    assert catalog == {"Traduzido": "Translated"}


def test_skips_fuzzy_entries() -> None:
    """Fuzzy means 'a machine guessed this' — it must not reach the UI."""
    catalog = parse_po(
        '''
#, fuzzy
msgid "Duvidoso"
msgstr "Doubtful"

msgid "Confirmado"
msgstr "Confirmed"
'''
    )
    assert catalog == {"Confirmado": "Confirmed"}


def test_unescapes_quotes_and_newlines() -> None:
    catalog = parse_po(
        '''
msgid "linha\\numa \\"citada\\""
msgstr "line\\none \\"quoted\\""
'''
    )
    assert catalog == {'linha\numa "citada"': 'line\none "quoted"'}


# --- language negotiation --------------------------------------------------


def test_shipped_english_catalog_is_discovered() -> None:
    assert "en" in available_languages()
    assert SOURCE_LANGUAGE in available_languages()


def test_normalizes_tag_variants_onto_shipped_catalogs() -> None:
    assert normalize_language("en") == "en"
    assert normalize_language("en-GB") == "en"
    assert normalize_language("en_US") == "en"
    assert normalize_language("pt-BR") == "pt_BR"


def test_unknown_language_degrades_to_source() -> None:
    """A bad --lang must show the shipped UI, never fail to start."""
    assert normalize_language("zz") == DEFAULT_LANGUAGE
    assert normalize_language("") == DEFAULT_LANGUAGE
    assert normalize_language(None) == DEFAULT_LANGUAGE


def test_accept_language_is_ordered_by_quality() -> None:
    assert parse_accept_language("pt-BR;q=0.8,en;q=0.9") == ["en", "pt-BR"]
    assert parse_accept_language("en-GB,en;q=0.9,*;q=0.1") == ["en-GB", "en"]
    assert parse_accept_language(None) == []
    assert parse_accept_language("") == []


# --- translation -----------------------------------------------------------


def test_source_language_needs_no_catalog() -> None:
    translator = Translator(SOURCE_LANGUAGE)
    assert translator.catalog == {}
    assert translator("Recarregar") == "Recarregar"


def test_english_catalog_translates_known_strings() -> None:
    translator = Translator("en")
    assert translator("Recarregar") == "Reload"
    assert translator("Ação") == "Action"
    # Unknown msgids fall through rather than becoming empty.
    assert translator("uma string que nao existe") == "uma string que nao existe"


# --- HTML translation ------------------------------------------------------


def test_translates_text_nodes_and_whitelisted_attributes() -> None:
    translator = Translator("en")
    html = '<p title="Ex.: streaming">Recarregar</p>'
    out = translator.translate_html(html)
    assert ">Reload<" in out
    assert 'title="e.g. streaming"' in out


def test_translates_alt_text() -> None:
    """``alt`` is what the reader sees when an image fails to load."""
    translator = Translator("en")
    out = translator.translate_html('<img src="x.png" alt="Prévia do ícone" />')
    assert 'alt="Icon preview"' in out


def test_leaves_script_bodies_alone() -> None:
    """A substring replace would corrupt JS that mentions a UI string."""
    translator = Translator("en")
    html = '<script>const label = "Recarregar";</script><p>Recarregar</p>'
    out = translator.translate_html(html)
    assert 'const label = "Recarregar";' in out
    assert "<p>Reload</p>" in out


def test_leaves_expression_attributes_alone() -> None:
    """Alpine bindings hold JS, not prose — translating them breaks the page."""
    translator = Translator("en")
    html = '<span x-text="Recarregar">Recarregar</span>'
    out = translator.translate_html(html)
    assert 'x-text="Recarregar"' in out
    assert ">Reload<" in out


def test_preserves_surrounding_whitespace() -> None:
    translator = Translator("en")
    out = translator.translate_html("<p>\n  Recarregar\n</p>")
    assert out == "<p>\n  Reload\n</p>"


# --- catalogue coverage ----------------------------------------------------

#: Literals that read the same in every language — status words, tile
#: geometry, a strftime pattern — so wrapping them in ``t()`` would only add
#: catalogue noise.
LANGUAGE_NEUTRAL_LITERALS = frozenset(
    {"online", "offline", " btn", "1x1", "2x1", "%H:%M"}
)


def _template_t_calls() -> set[str]:
    """Every string passed to ``t()`` from the editor's HTML and JS."""
    sources = (STATIC_DIR / "index.html", STATIC_DIR / "app.js")
    pattern = re.compile(r"""\bt\(\s*(['"])((?:[^'"\\]|\\.)*)\1""")
    return {
        match.group(2)
        for source in sources
        for match in pattern.finditer(source.read_text(encoding="utf-8"))
    }


def test_english_catalog_covers_every_translated_call() -> None:
    """A ``t()`` call with no catalogue entry silently ships Portuguese."""
    catalog = Translator("en").catalog
    missing = sorted(msgid for msgid in _template_t_calls() if msgid not in catalog)
    assert missing == []


def test_display_text_in_alpine_expressions_goes_through_t() -> None:
    """``x-text`` holds JS, so the server-side translator cannot see inside it.

    A bare literal there ships untranslated no matter how complete the
    catalogue is — the only way through is a ``t()`` call.
    """
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    literal = re.compile(r"""(t\(\s*)?'([^']*)'""")

    bare: list[str] = []
    for expression in re.findall(r'x-text="([^"]*)"', html):
        for match in literal.finditer(expression):
            text = match.group(2)
            if not any(char.isalpha() for char in text):
                continue  # punctuation placeholders like '?'
            if text in LANGUAGE_NEUTRAL_LITERALS or match.group(1):
                continue
            bare.append(text)

    assert bare == []


def test_source_language_returns_html_untouched() -> None:
    translator = Translator(SOURCE_LANGUAGE)
    html = '<p title="Ex.: streaming">Recarregar</p>'
    assert translator.translate_html(html) == html
