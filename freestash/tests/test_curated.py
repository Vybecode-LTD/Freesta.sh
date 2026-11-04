"""Curated packs: the admin records them on #/admin, every member's search finds them (contract github-and-curated-packs)."""

from datetime import date

import httpx
import pytest
import respx

from freestash.licenses import evaluate_all
from freestash.models import CuratedPack, MediaType, Tier, Trust, UseCase
from freestash.providers.base import SearchHints
from freestash.providers.curated import CuratedProvider, curated_asset

from .conftest import load
from .test_admin import make_client, signup, signup_admin

GITHUB_SEARCH = "https://api.github.com/search/repositories"


def pack(**over) -> dict:
    base = {"title": "Space Shooter Redux", "url": "https://kenney.nl/assets/space-shooter-redux", "publisher": "Kenney",
            "license_id": "CC0", "license_checked_on": "2026-11-04", "media_type": "sprite",
            "download_url": "https://kenney.nl/media/pages/assets/space-shooter-redux/kenney_space-shooter-redux.zip",
            "item_count": 295, "formats": ["png", ".SVG"], "tags": ["space", "shooter", "Space"]}
    return {**base, **over}


def test_a_curated_pack_says_who_recorded_its_license_and_when():
    a = curated_asset(CuratedPack.model_validate({**pack(), "id": "p1"}))
    assert (a.uid, a.trust, a.is_pack, a.members_checked, a.source_name, a.creator) == (
        "curated:p1", Trust.CURATED, True, None, "Kenney", "Kenney")
    assert a.license.id == "CC0-1.0" and a.license.raw == (
        "CC0 1.0, recorded by Freesta.sh from https://kenney.nl/assets/space-shooter-redux on 2026-11-04")
    assert [(r.label, r.mime) for r in a.renditions] == [("kenney_space-shooter-redux.zip", "application/zip")]
    assert (a.item_count, a.formats, a.tags, a.tips) == (295, ["png", "svg"], ["space", "shooter"], [])
    assert all(v.tier == Tier.GREEN for v in evaluate_all(a).values())
    linked = curated_asset(CuratedPack.model_validate({**pack(download_url=None), "id": "p2"}))
    assert linked.renditions == [] and linked.tips == ["Download it from Kenney's page."]


@pytest.mark.parametrize("bad", [{"url": "http://kenney.nl/x"}, {"license_id": "free for personal use"},
                                 {"license_checked_on": "2999-01-01"}, {"title": "  "}, {"thumbnail_url": "ftp://x"},
                                 {"item_count": 0}, {"media_type": "poster"}, {"unknown": 1}])
def test_a_curated_pack_refuses_what_it_cant_stand_behind(bad):
    with pytest.raises(ValueError):
        CuratedPack.model_validate(pack(**bad))


async def test_curated_search_ranks_by_the_words_and_keeps_to_the_kinds(settings):
    packs = [CuratedPack.model_validate({**pack(**p), "id": str(i)}) for i, p in enumerate([
        {"title": "Space Kit", "url": "https://kenney.nl/assets/space-kit", "media_type": "model", "tags": []},
        {},
        {"title": "Ultimate Space Kit", "url": "https://quaternius.com/packs/ultimatespacekit.html",
         "publisher": "Quaternius", "media_type": "model", "tags": ["space", "shooter"]},
        {"title": "Impact Sounds", "url": "https://kenney.nl/assets/impact-sounds", "media_type": "audio", "tags": []},
    ])]
    assert not CuratedProvider.is_enabled(settings)  # off until the admin adds packs
    settings.curated_packs = packs
    assert CuratedProvider.is_enabled(settings)
    p = CuratedProvider(None, settings)
    page = await p.search("space shooter", {MediaType.MODEL, MediaType.SPRITE}, 12, 1, SearchHints())
    assert [a.title for a in page.assets] == ["Space Shooter Redux", "Ultimate Space Kit", "Space Kit"]
    assert (await p.search("space shooter", {MediaType.MODEL}, 1, 2, SearchHints())).assets[0].title == "Space Kit"
    assert (await p.search("quaternius", {MediaType.MODEL}, 12, 1, SearchHints())).total == 1  # the publisher counts
    assert (await p.search("forest", set(MediaType), 12, 1, SearchHints())).assets == []
    assert (await p.get("3")).title == "Impact Sounds"
    with pytest.raises(LookupError):
        await p.get("gone")


# ----------------------------------------------------------------------------- the admin API

def test_admins_add_edit_and_remove_curated_packs_and_every_change_is_audited(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as c:
        owner, ada = signup_admin(c), signup(c, "ada@example.com")
        r = c.post("/api/admin/curated", headers=owner, json=pack())
        assert r.status_code == 201, r.text
        made = r.json()
        assert made["id"] and made["license_id"] == "CC0-1.0" and made["formats"] == ["png", "svg"] and made["updated_at"]
        assert c.post("/api/admin/curated", headers=owner, json=pack(title="Again")).status_code == 409  # same url
        assert c.post("/api/admin/curated", headers=owner, json=pack(url="http://x.test")).status_code == 422
        assert c.post("/api/admin/curated", headers=owner, json=pack(license_id="?")).status_code == 422

        other = c.post("/api/admin/curated", headers=owner, json=pack(title="Tiny Ski", url="https://kenney.nl/assets/tiny-ski",
                                                                     media_type="model")).json()
        edited = c.put(f"/api/admin/curated/{made['id']}", headers=owner, json=pack(item_count=300, tags=["space"])).json()
        assert edited["item_count"] == 300 and edited["tags"] == ["space"]
        assert c.put(f"/api/admin/curated/{other['id']}", headers=owner, json=pack()).status_code == 409  # url taken
        assert c.put("/api/admin/curated/00000000-0000-0000-0000-000000000000", headers=owner, json=pack()).status_code == 404
        assert c.put("/api/admin/curated/not-a-uuid", headers=owner, json=pack()).status_code == 404  # not a 500
        assert c.delete("/api/admin/curated/not-a-uuid", headers=owner).status_code == 404
        assert [p["title"] for p in c.get("/api/admin/curated", headers=owner).json()] == ["Space Shooter Redux", "Tiny Ski"]

        assert c.delete(f"/api/admin/curated/{other['id']}", headers=owner).status_code == 204
        assert c.delete(f"/api/admin/curated/{other['id']}", headers=owner).status_code == 404
        for method, path in (("get", "/api/admin/curated"), ("post", "/api/admin/curated"),
                             ("post", "/api/admin/curated/import"), ("delete", f"/api/admin/curated/{made['id']}")):
            kwargs = {"json": pack()} if method == "post" else {}
            assert getattr(c, method)(path, headers=ada, **kwargs).status_code == 403, path

        audit = c.get("/api/admin/audit", headers=owner).json()
        log = [(a["action"], a["target"]) for a in audit if a["action"].startswith("curated.")]
        assert log == [("curated.delete", "Tiny Ski"), ("curated.update", "Space Shooter Redux"),
                       ("curated.add", "Tiny Ski"), ("curated.add", "Space Shooter Redux")]
        update = next(a for a in audit if a["action"] == "curated.update")
        assert update["detail"] == {"item_count": 300, "tags": ["space"]}


def test_import_adds_and_updates_by_url_all_or_nothing(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as c:
        owner = signup_admin(c)
        c.post("/api/admin/curated", headers=owner, json=pack())
        rows = [pack(item_count=296), pack(title="Tiny Ski", url="https://kenney.nl/assets/tiny-ski", media_type="model")]
        assert c.post("/api/admin/curated/import", headers=owner, json={"packs": rows}).json() == {"added": 1, "updated": 1}
        assert c.post("/api/admin/curated/import", headers=owner, json={"packs": rows}).json() == {"added": 0, "updated": 0}

        bad = c.post("/api/admin/curated/import", headers=owner,
                     json={"packs": [pack(title="New", url="https://kenney.nl/assets/new"), pack(license_id="?")]})
        assert bad.status_code == 422 and bad.json()["detail"][0]["loc"][:3] == ["body", "packs", 1]  # names the row
        twice = c.post("/api/admin/curated/import", headers=owner, json={"packs": [rows[1], rows[1]]})
        assert twice.status_code == 400 and "twice" in twice.json()["detail"]
        listed = c.get("/api/admin/curated", headers=owner).json()
        assert [(p["title"], p["item_count"]) for p in listed] == [("Space Shooter Redux", 296), ("Tiny Ski", 295)]
        audit = [a for a in c.get("/api/admin/audit", headers=owner).json() if a["action"] == "curated.import"]
        assert [a["detail"] for a in audit] == [{"added": 1, "updated": 1}]  # the no-op import isn't logged


def test_every_member_searches_the_curated_packs(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as c:
        owner, ada = signup_admin(c), signup(c, "ada@example.com")
        body = {"q": "space shooter", "media_types": ["sprite"], "providers": ["curated"], "use_case": "bundled"}
        assert c.post("/api/search", headers=ada, json=body).json()["providers"] == []  # none yet: the source is off
        made = c.post("/api/admin/curated", headers=owner, json=pack()).json()

        r = c.post("/api/search", headers=ada, json=body).json()  # Packs off: an entry shows whenever it matches
        assert [(x["uid"], x["verdict"]["tier"]) for x in r["results"]] == [(f"curated:{made['id']}", "green")]
        detail = c.get(f"/api/assets/curated:{made['id']}?use=bundled", headers=ada)
        assert detail.status_code == 200 and detail.json()["asset"]["license"]["raw"].startswith("CC0 1.0, recorded by")

        c.delete(f"/api/admin/curated/{made['id']}", headers=owner)
        assert c.post("/api/search", headers=ada, json=body).json()["results"] == []


@respx.mock
def test_members_search_github_on_the_sites_token_and_the_key_test_really_calls_it(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as c:
        owner, ada = signup_admin(c), signup(c, "ada@example.com")
        route = respx.get(GITHUB_SEARCH).mock(return_value=httpx.Response(200, json=load("github_search")))
        body = {"q": "space", "media_types": ["sprite", "model"], "providers": ["github"]}
        assert c.post("/api/search", headers=ada, json=body).json()["providers"] == []  # Packs off: not searched
        assert route.call_count == 0

        c.put("/api/admin/keys", headers=owner, json={"values": {"GITHUB_ACCESS_TOKEN": "site-token"}})
        r = c.post("/api/search", headers=ada, json={**body, "packs": True}).json()
        assert r["providers"][0]["ok"] and r["results"] and all(x["asset"]["is_pack"] for x in r["results"])
        assert route.calls.last.request.headers["Authorization"] == "Bearer site-token"
        assert "topic:game-assets" in route.calls.last.request.url.params["q"]
        usage = {u["provider"]: u for u in c.get("/api/admin/usage", headers=owner).json()}
        assert usage["github"]["today"]["calls"] == 1

        ok = c.post("/api/admin/keys/GITHUB_ACCESS_TOKEN/test", headers=owner).json()
        assert ok["ok"] is True and route.call_count == 2  # without packs the test would pass without calling GitHub
        route.mock(return_value=httpx.Response(401, json={"message": "Bad credentials"}))
        assert c.post("/api/admin/keys/GITHUB_ACCESS_TOKEN/test", headers=owner).json()["ok"] is False


def test_curated_checked_dates_are_dates():
    assert CuratedPack.model_validate(pack()).license_checked_on == date(2026, 11, 4)
    assert CuratedPack.model_validate(pack()).media_type == MediaType.SPRITE
    assert evaluate_all(curated_asset(CuratedPack.model_validate({**pack(), "id": "x"})))[UseCase.MERCH].tier == Tier.GREEN
