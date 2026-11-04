"""Every adapter's parser against a real (or clearly marked synthetic) recorded response."""

from freestash.licenses import evaluate, normalize_license, strictest_license
from freestash.models import MediaType, Tier, Trust, UseCase
from freestash.providers.archives import (
    InternetArchiveProvider,
    loc_license,
    parse_europeana,
    parse_ia_doc,
    parse_loc,
    parse_nasa,
)
from freestash.providers.base import SearchHints
from freestash.providers.design import (
    IconifyProvider,
    flatten_polyhaven_files,
    parse_ambientcg,
    parse_font,
    parse_icon_set,
    parse_icons,
    parse_polyhaven,
    rank_sets,
)
from freestash.providers.museums import (
    parse_aic,
    parse_cleveland,
    parse_met_object,
    parse_smithsonian,
    parse_smk,
    parse_vam,
)
from freestash.providers.openverse import parse_result, trust_for_source
from freestash.providers.stock import (
    FreesoundProvider,
    parse_freesound,
    parse_pexels_photo,
    parse_pixabay_image,
    parse_unsplash,
)
from freestash.providers.wikimedia import parse_page


def test_met(fixture):
    pd = parse_met_object(fixture("met_object_pd"))
    assert pd and pd.license.id == "CC0-1.0" and pd.trust == Trust.INSTITUTION
    assert pd.renditions[0].label == "original" and pd.preview_url.startswith("https://images.metmuseum.org/")
    assert parse_met_object(fixture("met_object_nonpd")) is None  # no open-access image -> skipped
    assert fixture("met_search")["objectIDs"]


def test_artic(fixture):
    data = fixture("artic_search")
    assets = [parse_aic(i, data["config"]["iiif_url"]) for i in data["data"]]
    a = next(x for x in assets if x)
    assert a.license.id == "CC0-1.0"
    assert a.preview_url.endswith("/full/843,/0/default.jpg")
    assert a.landing_url.startswith("https://www.artic.edu/artworks/")


def test_cleveland(fixture):
    a = parse_cleveland(fixture("cleveland_search")["data"][0])
    assert a.license.id == "CC0-1.0" and a.creator.startswith("Edward Hopper")
    assert [r.label for r in a.renditions] == ["web", "print", "full"]
    assert a.year == 1929 and a.tips  # TIFF size warning


def test_smk(fixture):
    a = parse_smk(fixture("smk_search")["items"][0])
    assert a.license.id == "PDM-1.0" and a.year == 1846 and a.renditions


def test_vam_is_reference_only(fixture):
    a = parse_vam(fixture("vam_search")["records"][0])
    assert a.license.id == "VAM-TERMS" and "Constable" in a.creator


def test_smithsonian_synthetic(fixture):
    a = parse_smithsonian(fixture("smithsonian_search")["response"]["rows"][0])
    assert a.license.id == "CC0-1.0" and a.year == 1911 and len(a.renditions) == 2


def test_nasa_image_and_audio(fixture):
    img = parse_nasa(fixture("nasa_image_search")["collection"]["items"][0])
    assert img.license.id == "PD-US-GOV" and img.media_type == MediaType.IMAGE and img.renditions
    assert any("endorsement" in n for n in img.notes)
    audio = parse_nasa(fixture("nasa_audio_search")["collection"]["items"][0])
    assert audio.media_type == MediaType.AUDIO and audio.detail_required and audio.year == 2026


def test_loc(fixture):
    data = fixture("loc_search")
    a = parse_loc(data["results"][0], MediaType.IMAGE, "No known restrictions on publication.")
    assert a.license.id == "NKC" and a.detail_required
    assert loc_license("Publication may be restricted.").id == "RIGHTS-UNKNOWN"


def test_internet_archive_assertions_are_uploader_trust(fixture):
    docs = fixture("ia_search")["response"]["docs"]
    assets = [parse_ia_doc(d) for d in docs]
    assert all(a.license.id == "PDM-1.0" for a in assets)
    assert all(a.trust == Trust.UPLOADER for a in assets)
    assert any(a.year == 2025 for a in assets)  # the mislabeled TV clip the date heuristic exists for


def test_europeana_trust_mapping(fixture):
    items = fixture("europeana_search")["items"]
    commons, heritage = parse_europeana(items[0]), parse_europeana(items[1])
    assert commons.trust == Trust.COMMUNITY and commons.license.id == "CC-BY-SA-3.0"
    assert heritage.trust == Trust.INSTITUTION and heritage.license.id == "CC0-1.0"
    assert heritage.source_name == "Estonian National Heritage Board"


def test_openverse(fixture):
    img = parse_result(fixture("openverse_images")["results"][0], MediaType.IMAGE)
    assert img.provider == "openverse" and img.source_name and img.license.id in ("CC0-1.0", "PDM-1.0")
    audio = parse_result(fixture("openverse_audio")["results"][0], MediaType.AUDIO)
    assert audio.media_type == MediaType.AUDIO and audio.duration_seconds
    assert trust_for_source("smithsonian_american_art_museum") == Trust.INSTITUTION
    assert trust_for_source("flickr") == Trust.UPLOADER
    assert trust_for_source("katmai_nps") == Trust.GOVERNMENT


def test_wikimedia_synthetic(fixture):
    pages = fixture("wikimedia_search")["query"]["pages"]
    photo, old_map = parse_page(pages[0]), parse_page(pages[1])
    assert photo.license.id == "CC-BY-SA-4.0" and photo.creator == "Example Photographer" and photo.year == 2015
    assert old_map.license.id == "PDM-1.0" and old_map.year == 1720 and old_map.notes


def test_polyhaven(fixture):
    cat = fixture("polyhaven_textures")
    aid = next(iter(cat))
    a = parse_polyhaven(aid, cat[aid])
    assert a.media_type == MediaType.TEXTURE and a.license.id == "CC0-1.0" and a.detail_required
    hdri_cat = fixture("polyhaven_hdris")
    h = parse_polyhaven(next(iter(hdri_cat)), hdri_cat[next(iter(hdri_cat))])
    assert h.media_type == MediaType.HDRI
    rends = flatten_polyhaven_files(fixture("polyhaven_files"))
    assert rends and rends[0].label.split("/")[1] == "1k" and all(r.url.startswith("https://") for r in rends)


def test_ambientcg(fixture):
    a = parse_ambientcg(fixture("ambientcg_search")["foundAssets"][0])
    assert a.license.id == "CC0-1.0" and a.renditions and a.renditions[0].mime == "application/zip"


def test_fontsource(fixture):
    f = parse_font(fixture("fontsource_list")[0])
    assert f.media_type == MediaType.FONT and f.license.id == "OFL-1.1"
    assert f.preview_url.endswith(".woff2") and f.trust == Trust.CURATED


def test_iconify(fixture):
    icons = parse_icons(fixture("iconify_search"))
    assert len(icons) >= 30
    mdi = next(i for i in icons if i.source_id.startswith("mdi:"))
    assert mdi.license.id == "Apache-2.0" and mdi.preview_url.endswith(".svg")


def test_stock_synthetic(fixture):
    fs = parse_freesound(fixture("freesound_search")["results"][0])
    assert fs.license.id == "CC0-1.0" and fs.trust == Trust.UPLOADER and fs.renditions
    px = parse_pexels_photo(fixture("pexels_search")["photos"][0])
    assert px.license.id == "PEXELS" and px.creator == "Jane Doe"
    pb = parse_pixabay_image(fixture("pixabay_search")["hits"][0])
    assert pb.license.id == "PIXABAY" and pb.tags[0] == "lighthouse"
    us = parse_unsplash(fixture("unsplash_search")["results"][0])
    assert us.license.id == "UNSPLASH" and us.extra["download_location"].startswith("https://api.unsplash.com/")


# ----------------------------------------------------------------------------- packs (contract packs-and-new-kinds)

class FakeHttp:
    """Answers get_json from fixtures by URL fragment (first match); an Exception answer is raised. Records each call."""

    def __init__(self, routes: list[tuple[str, object]]):
        self.routes = routes
        self.calls: list[tuple[str, object]] = []
        self.headers: list[dict | None] = []

    async def get_json(self, url, params=None, headers=None, *, cache_ttl=None, retry_on=None):
        self.calls.append((url, params))
        self.headers.append(headers)
        for fragment, answer in self.routes:
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f"unexpected request {url}")


def test_iconify_set_is_a_pack_with_one_license(fixture):
    colls = fixture("iconify_collections")
    s = parse_icon_set("game-icons", colls["game-icons"])
    assert (s.source_id, s.title, s.is_pack, s.item_count, s.formats) == ("set:game-icons", "Game Icons", True, 4133,
                                                                          ["svg", "json"])
    assert s.license.id == "CC-BY-3.0" and s.members_checked is None and s.trust == Trust.COMMUNITY
    assert s.renditions[0].url == "https://cdn.jsdelivr.net/npm/@iconify-json/game-icons/icons.json"
    assert s.landing_url == "https://icon-sets.iconify.design/game-icons/"
    assert s.thumbnail_url.endswith("/game-icons/diamond-trophy.svg")
    assert parse_icon_set("gridicons", colls["gridicons"]).license.id.startswith("GPL")


def test_iconify_sets_rank_by_the_query_and_skip_hidden_sets(fixture):
    colls = fixture("iconify_collections")
    assert [p for p, _ in rank_sets(colls, "game")][:1] == ["game-icons"]
    assert "whh" not in [p for p, _ in rank_sets(colls, "icons")]  # hidden: archived by Iconify
    assert rank_sets(colls, "zzzz") == []


async def test_iconify_looks_for_sets_only_with_packs(fixture, settings):
    http = FakeHttp([("/collections", fixture("iconify_collections")), ("/search", fixture("iconify_search"))])
    p = IconifyProvider(http, settings)
    plain = await p.search("game", {MediaType.ICON}, 12, 1, SearchHints())
    assert not any(a.is_pack for a in plain.assets) and all("/collections" not in u for u, _ in http.calls)
    packs = await p.search("game", {MediaType.ICON}, 12, 1, SearchHints(packs=True))
    assert packs.assets[0].source_id == "set:game-icons" and not packs.assets[-1].is_pack
    assert (await p.get("set:tabler")).item_count == 6257


async def test_freesound_groups_by_pack_and_adds_the_packs(fixture, settings):
    fx = fixture("freesound_packs_synthetic")
    http = FakeHttp([("/packs/9876/", fx["pack"]), ("/packs/4321/", RuntimeError("gone")), ("/search/text/", fx["search"])])
    settings.freesound_api_key = "k"
    page = await FreesoundProvider(http, settings).search("sword", {MediaType.AUDIO}, 12, 1, SearchHints(packs=True))
    search_params = next(params for url, params in http.calls if "/search/text/" in url)
    assert search_params["group_by_pack"] == 1 and "pack" in search_params["fields"].split(",")
    packs = [a for a in page.assets if a.is_pack]
    assert [a.source_id for a in packs] == ["pack:9876"]  # 4321's lookup failed: its pack is left out, its sound stays
    pack = packs[0]
    assert (pack.title, pack.item_count, pack.members_checked, pack.formats) == ("Medieval Swords", 4, 1, ["wav"])
    assert pack.detail_required and pack.preview_url.endswith("512001_1-hq.mp3") and not pack.renditions
    assert pack.landing_url == "https://freesound.org/people/ArmouryFoley/packs/9876/"
    assert len([a for a in page.assets if not a.is_pack]) == 3
    assert evaluate(pack, UseCase.DEMO).tier == Tier.YELLOW  # 1 of 4 files read

    http.calls.clear()
    await FreesoundProvider(http, settings).search("sword", {MediaType.AUDIO}, 12, 1, SearchHints())
    assert [u for u, _ in http.calls if "/packs/" in u] == [] and "group_by_pack" not in http.calls[0][1]


async def test_freesound_pack_detail_reads_every_files_license(fixture, settings):
    fx = fixture("freesound_packs_synthetic")
    http = FakeHttp([("/packs/9876/sounds/", fx["pack_sounds"]), ("/packs/9876/", fx["pack"])])
    pack = await FreesoundProvider(http, settings).get("pack:9876")
    assert (pack.members_checked, pack.item_count, pack.formats, pack.detail_required) == (4, 4, ["wav", "mp3"], False)
    assert sorted(lic.id for lic in pack.member_licenses) == ["CC-BY-4.0", "CC0-1.0"]
    assert pack.license.id == "CC-BY-4.0"  # the strictest member, for the card and the ledger
    v = evaluate(pack, UseCase.BUNDLED)
    assert v.tier == Tier.YELLOW and any("Credit required" in o for o in v.obligations)  # uploader trust; CC BY credit
    sounds_params = next(params for url, params in http.calls if url.endswith("/sounds/"))
    assert sounds_params["page_size"] == 150


def test_internet_archive_items_holding_an_archive_are_packs(fixture):
    docs = {d["identifier"]: parse_ia_doc(d) for d in fixture("ia_packs")["audio_packs"]["response"]["docs"]}
    celeste = docs["lena-raine-celeste-original-soundtrack"]
    assert celeste.is_pack and celeste.formats == ["zip"] and celeste.item_count is None
    assert docs["06-kyousei-inyou-03-06-ongeshu"].formats == ["rar"]
    assert set(docs["small-songs-full-archive"].formats) >= {"zip", "rar", "mp3"}
    rainstick = docs["maxrainstick"]  # only IA's own derived zips ("VBR ZIP"): an album, not a pack
    assert not rainstick.is_pack and {"mp3", "ogg", "aiff"} <= set(rainstick.formats) and "zip" not in rainstick.formats


async def test_internet_archive_searches_each_new_kind_and_packs(fixture, settings):
    fx = fixture("ia_packs")

    class Http(FakeHttp):
        async def get_json(self, url, params=None, headers=None, *, cache_ttl=None):
            self.calls.append((url, params))
            q = dict(params)["q"]
            key = ("brush" if "brushes" in q else "sprite" if "spritesheet" in q
                   else "audio_packs" if "format:" in q else None)
            return {"response": fx[key]["response"]} if key else {"response": {"docs": [], "numFound": 0}}

    http = Http([])
    page = await InternetArchiveProvider(http, settings).search(
        "grunge", {MediaType.AUDIO, MediaType.BRUSH, MediaType.SPRITE}, 6, 1, SearchHints(packs=True))
    queries = [dict(p)["q"] for _, p in http.calls]
    assert len(queries) == 4  # audio, audio packs, brushes, sprites
    assert all("mediatype:(image OR data)" in q for q in queries if "brushes" in q or "spritesheet" in q)
    brushes = [a for a in page.assets if a.media_type == MediaType.BRUSH]
    assert brushes and all(a.source_id.startswith("brush:") and a.is_pack for a in brushes)
    assert any(a.media_type == MediaType.SPRITE for a in page.assets)
    assert len({a.uid for a in page.assets}) == len(page.assets)

    http.calls.clear()
    await InternetArchiveProvider(http, settings).search("grunge", {MediaType.AUDIO}, 6, 1, SearchHints())
    assert len(http.calls) == 1 and "format:" not in dict(http.calls[0][1])["q"]


async def test_internet_archive_detail_keeps_the_kind(fixture, settings):
    http = FakeHttp([("/metadata/", fixture("ia_metadata"))])
    a = await InternetArchiveProvider(http, settings).get("sprite:lighthouse-keeping-1932")
    assert (a.media_type, a.source_id, a.landing_url) == (
        MediaType.SPRITE, "sprite:lighthouse-keeping-1932", "https://archive.org/details/lighthouse-keeping-1932")
    assert http.calls[0][0].endswith("/metadata/lighthouse-keeping-1932")
    assert a.renditions and not a.is_pack and "mp4" in a.formats


def test_strictest_license_picks_the_member_that_clears_least():
    lics = [normalize_license("CC0-1.0"), normalize_license("CC-BY-NC-4.0"), normalize_license("CC-BY-4.0")]
    assert strictest_license(lics, Trust.UPLOADER).id == "CC-BY-NC-4.0"
    assert strictest_license(lics[::2], Trust.UPLOADER).id == "CC-BY-4.0"  # same tiers: the one with obligations
