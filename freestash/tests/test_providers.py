"""Every adapter's parser against a real (or clearly marked synthetic) recorded response."""

from freestash.models import MediaType, Trust
from freestash.providers.archives import loc_license, parse_europeana, parse_ia_doc, parse_loc, parse_nasa
from freestash.providers.design import (
    flatten_polyhaven_files,
    parse_ambientcg,
    parse_font,
    parse_icons,
    parse_polyhaven,
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
from freestash.providers.stock import parse_freesound, parse_pexels_photo, parse_pixabay_image, parse_unsplash
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
