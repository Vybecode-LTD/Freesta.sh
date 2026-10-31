"""Federated search orchestration (mocked HTTP), downloads, ledger, collections, exports."""

import json

import httpx
import pytest
import respx

from freestash.download import pick_rendition
from freestash.export import attribution_markdown, credits_html, ledger_csv
from freestash.http import HttpClient
from freestash.models import MediaType, Rendition, SearchQuery, Tier, UseCase
from freestash.search import Freestash
from freestash.store import Store, entry_from_scored

from .conftest import load


@pytest.fixture
def engine(settings):
    return Freestash(settings, HttpClient(settings))


@respx.mock
async def test_federated_search_merges_scores_and_survives_failures(engine):
    respx.get("https://openaccess-api.clevelandart.org/api/artworks/").mock(
        return_value=httpx.Response(200, json=load("cleveland_search")))
    respx.get("https://api.smk.dk/api/v1/art/search/").mock(return_value=httpx.Response(200, json=load("smk_search")))
    respx.get(url__startswith="https://api.artic.edu/").mock(return_value=httpx.Response(500, text="boom"))

    resp = await engine.search(SearchQuery(q="lighthouse", media_types=[MediaType.IMAGE], use_case=UseCase.BUNDLED,
                                           providers=["cleveland", "smk", "artic"], limit_per_provider=5))
    by_provider = {p.provider: p for p in resp.providers}
    assert by_provider["cleveland"].ok and by_provider["smk"].ok
    assert not by_provider["artic"].ok and "500" in by_provider["artic"].error
    assert {r.asset.provider for r in resp.results} == {"cleveland", "smk"}
    assert resp.results[0].asset.provider != resp.results[1].asset.provider  # interleaved
    assert all(r.verdict.tier == Tier.GREEN for r in resp.results)
    await engine.http.aclose()


@respx.mock
async def test_max_tier_hides_and_counts(engine):
    respx.get("https://api.vam.ac.uk/v2/objects/search").mock(return_value=httpx.Response(200, json=load("vam_search")))
    q = SearchQuery(q="lighthouse", media_types=[MediaType.IMAGE], use_case=UseCase.REFERENCE, providers=["vam"],
                    max_tier=Tier.GREEN)
    resp = await engine.search(q)
    assert resp.results == [] and resp.hidden_by_tier >= 1  # V&A is YELLOW even for reference
    resp = await engine.search(q.model_copy(update={"max_tier": Tier.YELLOW}))
    assert resp.results and resp.results[0].verdict.tier == Tier.YELLOW
    await engine.http.aclose()


@respx.mock
async def test_stream_yields_per_provider(engine):
    respx.get("https://openaccess-api.clevelandart.org/api/artworks/").mock(
        return_value=httpx.Response(200, json=load("cleveland_search")))
    respx.get("https://api.smk.dk/api/v1/art/search/").mock(return_value=httpx.Response(200, json=load("smk_search")))
    batches = [b async for b in engine.search_stream(SearchQuery(q="x", providers=["cleveland", "smk"]))]
    assert sorted(b.status.provider for b in batches) == ["cleveland", "smk"]
    await engine.http.aclose()


@respx.mock
async def test_get_asset_uses_recent_cache_then_provider(engine):
    respx.get("https://openaccess-api.clevelandart.org/api/artworks/").mock(
        return_value=httpx.Response(200, json=load("cleveland_search")))
    resp = await engine.search(SearchQuery(q="x", providers=["cleveland"]))
    uid = resp.results[0].uid
    route = respx.get(url__startswith="https://openaccess-api.clevelandart.org/api/artworks/1")
    scored = await engine.get_asset(uid, UseCase.MERCH)
    assert scored.uid == uid and scored.verdict.use_case == UseCase.MERCH
    assert not route.called  # served from the recent-results cache
    await engine.http.aclose()


def test_pick_rendition():
    r = [Rendition(url="a", label="web", bytes=100), Rendition(url="b", label="print", bytes=2_000),
         Rendition(url="c", label="full", bytes=900_000_000)]
    assert pick_rendition(r, "large", max_bytes=10_000).label == "print"
    assert pick_rendition(r, "original", max_bytes=10_000).label == "print"  # full is over the cap
    assert pick_rendition(r, "original", max_bytes=None).label == "full"
    assert pick_rendition(r, "small").label == "web"


@respx.mock
async def test_download_writes_file_sidecar_and_ledger(engine, settings, tmp_path):
    from freestash.download import download_asset
    from freestash.licenses import evaluate
    from freestash.models import ScoredAsset
    from freestash.providers.museums import parse_cleveland

    asset = parse_cleveland(load("cleveland_search")["data"][0])
    scored = ScoredAsset(uid=asset.uid, asset=asset, verdict=evaluate(asset, UseCase.BUNDLED))
    web = next(r for r in asset.renditions if r.label == "web")
    respx.get(web.url).mock(return_value=httpx.Response(200, content=b"\xff\xd8fakejpeg", headers={"content-type": "image/jpeg"}))
    store = Store(settings=settings)
    result = await download_asset(engine, scored, tmp_path / "out", prefer="small", project="tpl", store=store)
    assert result.path.read_bytes() == b"\xff\xd8fakejpeg"
    side = json.loads(result.sidecar.read_text(encoding="utf-8"))
    assert side["license"]["id"] == "CC0-1.0" and side["use_case"] == "bundled" and len(side["asset"]["renditions"]) == 1
    entries = store.list_entries(project="tpl")
    assert len(entries) == 1 and entries[0].sha256 == result.entry.sha256
    await engine.http.aclose()


def test_collections_and_team_scoping(settings):
    from freestash.licenses import evaluate
    from freestash.models import ScoredAsset
    from freestash.providers.museums import parse_cleveland

    store = Store(settings=settings)
    asset = parse_cleveland(load("cleveland_search")["data"][0])
    scored = ScoredAsset(uid=asset.uid, asset=asset, verdict=evaluate(asset, UseCase.DEMO))
    coll = store.create_collection("Hero images", use_case=UseCase.DEMO)
    store.add_to_collection(coll["id"], scored, note="for the landing page")
    store.add_to_collection(coll["id"], scored)  # idempotent
    got = store.get_collection(coll["id"])
    assert got["item_count"] == 1 and got["items"][0]["note"] == "for the landing page"
    assert store.get_collection(coll["id"], team_id="someone-else") is None  # scoping
    assert store.remove_from_collection(coll["id"], asset.uid)
    assert store.delete_collection(coll["id"])


def test_exports(settings):
    from freestash.licenses import evaluate
    from freestash.models import ScoredAsset
    from freestash.providers.museums import parse_cleveland
    from freestash.providers.stock import parse_pexels_photo

    store = Store(settings=settings)
    for asset, use in ((parse_cleveland(load("cleveland_search")["data"][0]), UseCase.DEMO),
                       (parse_pexels_photo(load("pexels_search")["photos"][0]), UseCase.BUNDLED)):
        store.add_entry(entry_from_scored(ScoredAsset(uid=asset.uid, asset=asset, verdict=evaluate(asset, use)), project="p"))
    entries = store.list_entries(project="p")
    md = attribution_markdown(entries, "p")
    assert "## CC0 1.0" in md and "## Pexels License" in md and "## Needs review" in md  # Pexels is RED for bundled
    assert credits_html(entries).count("<li>") == 2
    assert ledger_csv(entries).splitlines()[0].startswith("retrieved_at,project,title")
