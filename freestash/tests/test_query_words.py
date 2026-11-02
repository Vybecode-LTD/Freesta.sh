"""Query words pick categories (contract dev plans/contracts/grouped-results.md): "rain sfx" searches "rain" in Audio."""

import pytest

from freestash.models import MediaType
from freestash.query_words import parse_query


def picks(text, keep=()):
    p = parse_query(text, keep)
    return p.q, [(k.word, k.media_type.value) for k in p.picks], [m.value for m in p.media_types]


def test_a_category_word_becomes_a_pick_and_leaves_the_query():
    assert picks("medieval sword sfx") == ("medieval sword", [("sfx", "audio")], ["audio"])


def test_nothing_to_pick_searches_the_text_as_typed():
    p = parse_query("  weathered   concrete ")
    assert (p.q, p.picks, p.media_types, p.original) == ("weathered concrete", [], [], "  weathered   concrete ")


def test_filler_left_at_either_end_goes():
    assert picks("sound of rain")[0] == "rain"
    assert picks("the lighthouse photo")[0] == "lighthouse"
    assert picks("photo of a lighthouse at night")[0] == "lighthouse at night"


def test_filler_in_the_middle_or_without_a_pick_stays():
    assert picks("rain on a tin roof sfx")[0] == "rain on a tin roof"
    assert picks("a lighthouse")[0] == "a lighthouse"


def test_a_phrase_matches_before_its_words():
    assert picks("door creak sound effects") == ("door creak", [("sound effects", "audio")], ["audio"])
    assert picks("castle 3d model") == ("castle", [("3d model", "model")], ["model"])
    assert picks("forest environment map") == ("forest", [("environment map", "hdri")], ["hdri"])


def test_case_and_punctuation_are_ignored_and_the_word_is_kept_as_typed():
    assert picks("Rain, SFX!") == ("Rain,", [("SFX!", "audio")], ["audio"])
    assert picks("(Font) serif") == ("serif", [("(Font)", "font")], ["font"])


def test_categories_come_out_in_display_order_once_each():
    q, found, media = picks("icons fonts ocean photo sfx sound")
    assert q == "ocean"
    assert media == ["image", "audio", "font", "icon"]
    assert [w for w, _ in found] == ["icons", "fonts", "photo", "sfx", "sound"]  # every pick, as typed, in text order


def test_keep_leaves_a_word_in_the_query():
    assert picks("brass sound sfx", keep=["SOUND"]) == ("brass sound", [("sfx", "audio")], ["audio"])
    assert picks("door creak sound effects", keep=["sound effects"])[1] == []


def test_kept_phrase_still_lets_a_shorter_word_inside_it_stay_literal():
    # keeping "sound effects" means the user wants those words searched, not "sound" picked on its own
    assert picks("sound effects", keep=["sound effects"]) == ("sound effects", [], [])


def test_only_category_words_means_no_pick():
    assert picks("sfx") == ("sfx", [], [])
    assert picks("photo of the") == ("photo of the", [], [])


def test_words_inside_other_words_never_match():
    assert picks("iconography soundscape fontaine")[1] == []


async def test_mcp_search_reads_words_only_when_no_media_is_given(monkeypatch):
    from datetime import UTC, datetime

    from freestash import mcp_server
    from freestash.models import SearchResponse

    seen = []

    class Engine:
        class recent:  # noqa: N801 - stands in for RecentCache
            @staticmethod
            def flush():
                pass

        async def search(self, query):
            seen.append(query)
            return SearchResponse(query=query, results=[], providers=[], generated_at=datetime.now(UTC))

    monkeypatch.setattr(mcp_server, "_engine", Engine())
    read = await mcp_server.search_assets("rain sfx")
    assert (read["searched_for"], read["read_as"]) == ("rain", [{"word": "sfx", "media_type": "audio"}])
    assert [m.value for m in seen[-1].media_types] == ["audio"]
    for kwargs in ({"media_types": [MediaType.VIDEO]}, {"literal": True}):
        out = await mcp_server.search_assets("rain sfx", **kwargs)
        assert (out["searched_for"], out["read_as"], seen[-1].q) == ("rain sfx", [], "rain sfx")


@pytest.mark.parametrize("media", list(MediaType))
def test_every_category_has_words_that_pick_it(media):
    from freestash.categories_data import CATEGORIES

    words = next(c["words"] for c in CATEGORIES if c["id"] == media.value)
    assert words and parse_query(f"ocean {words[0]}").media_types == [media]
