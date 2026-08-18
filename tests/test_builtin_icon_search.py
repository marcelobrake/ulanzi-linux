"""Tests for the built-in icon catalogue's search ranking.

The ranking lives in ``app.js`` because it runs on a catalogue the browser
already holds — round-tripping ~4000 icons to the server per keystroke would
be absurd. It is still real logic worth pinning down, so these tests drive the
actual shipped file through node rather than reimplementing it in Python.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

APP_JS = (
    Path(__file__).resolve().parents[1]
    / "src/ulanzi_linux/interface/web/static/app.js"
)

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is needed to exercise the browser-side search",
)

#: A catalogue small enough to reason about, built around the case that drove
#: the ranking: "anatomical" contains "mic" just as surely as "microphone".
FIXTURE_ICONS = [
    {"asset_id": "a", "name": "anatomical heart", "family": "emoji", "style": "emoji",
     "search_terms": ["organ"]},
    {"asset_id": "b", "name": "microphone", "family": "emoji", "style": "emoji",
     "search_terms": ["mic", "audio"]},
    {"asset_id": "c", "name": "studio microphone", "family": "emoji", "style": "emoji",
     "search_terms": ["podcast"]},
    {"asset_id": "d", "name": "headset", "family": "fontawesome", "style": "solid",
     "search_terms": ["microphone", "gaming"]},
    {"asset_id": "e", "name": "volume-high", "family": "fontawesome", "style": "solid",
     "search_terms": ["audio"]},
]


def _search(query: str, *, style: str = "all", icons: list[dict] | None = None) -> list[str]:
    """Return the names the editor would show, in the order it would show them."""
    script = f"""
        global.window = {{ __I18N__: {{ catalog: {{}} }} }};
        const fs = require("fs");
        (0, eval)(fs.readFileSync({str(APP_JS)!r}, "utf8"));
        const app = window.editorApp();
        app.builtinIcons = {json.dumps(icons if icons is not None else FIXTURE_ICONS)};
        app.builtinIconQuery = {json.dumps(query)};
        app.builtinIconStyle = {json.dumps(style)};
        console.log(JSON.stringify(app.filteredBuiltinIcons.map((i) => i.name)));
    """
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_word_start_beats_a_match_buried_mid_word() -> None:
    """The whole point: "mic" must find the microphone, not the anatomy."""
    names = _search("mic")
    assert names[0] == "microphone"
    assert names.index("microphone") < names.index("anatomical heart")


def test_keyword_matches_rank_below_name_matches() -> None:
    names = _search("microphone")
    # "headset" only matches through its keywords, so it comes last.
    assert names[0] == "microphone"
    assert names[-1] == "headset"


def test_multi_word_names_match_on_any_word() -> None:
    assert "studio microphone" in _search("mic")


def test_non_matches_are_excluded() -> None:
    assert "volume-high" not in _search("mic")
    assert _search("zzzznope") == []


def test_style_filter_applies_before_ranking() -> None:
    assert _search("mic", style="solid") == ["headset"]


def test_an_empty_query_keeps_the_catalogue_order() -> None:
    assert _search("") == [icon["name"] for icon in FIXTURE_ICONS]


def test_results_are_capped() -> None:
    many = [
        {
            "asset_id": f"i{n}",
            "name": f"mic-{n}",
            "family": "fontawesome",
            "style": "solid",
            "search_terms": [],
        }
        for n in range(200)
    ]
    assert len(_search("mic", icons=many)) == 120
    assert len(_search("", icons=many)) == 120
