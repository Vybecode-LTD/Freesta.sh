import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from freestash.config import get_settings

from .conftest import load


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FREESTASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FREESTASH_AUTH_MODE", "none")
    monkeypatch.setenv("FREESTASH_HTTP_RETRIES", "0")
    get_settings.cache_clear()
    from freestash.api.app import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_health_and_providers(client):
    assert client.get("/api/health").json()["ok"] is True
    ids = {p["id"] for p in client.get("/api/providers").json()}
    assert {"met", "openverse", "polyhaven", "iconify", "unsplash"} <= ids


def test_license_check(client):
    r = client.post("/api/license/check", json={"license": "https://www.pexels.com/license/"}).json()
    assert r["recognized_as"]["id"] == "PEXELS"
    assert r["verdicts"]["demo"]["tier"] == "green" and r["verdicts"]["bundled"]["tier"] == "red"


@respx.mock
def test_search_and_stream(client):
    respx.get("https://api.smk.dk/api/v1/art/search/").mock(return_value=httpx.Response(200, json=load("smk_search")))
    r = client.post("/api/search", json={"q": "lighthouse", "providers": ["smk"], "use_case": "bundled"}).json()
    assert r["results"] and r["results"][0]["verdict"]["tier"] == "green"
    with client.stream("GET", "/api/search/stream", params={"q": "lighthouse", "providers": ["smk"]}) as s:
        body = "".join(s.iter_text())
    assert "event: batch" in body and "event: done" in body


@respx.mock
def test_collections_and_ledger_flow(client):
    respx.get("https://api.smk.dk/api/v1/art/search/").mock(return_value=httpx.Response(200, json=load("smk_search")))
    result = client.post("/api/search", json={"q": "x", "providers": ["smk"]}).json()["results"][0]

    coll = client.post("/api/collections", json={"name": "Template hero images", "use_case": "bundled"}).json()
    added = client.post(f"/api/collections/{coll['id']}/items", json={"uid": result["uid"], "asset": result["asset"]}).json()
    assert added["item_count"] == 1 and added["items"][0]["verdict"]["use_case"] == "bundled"

    entry = client.post("/api/ledger", json={"uid": result["uid"], "asset": result["asset"], "use_case": "bundled",
                                             "project": "tpl-01"}).json()
    assert entry["tier"] == "green" and entry["project"] == "tpl-01"
    assert client.get("/api/ledger/projects").json() == ["tpl-01"]
    md = client.get("/api/ledger/export", params={"project": "tpl-01"}).text
    assert "# Asset credits — tpl-01" in md

    assert client.delete(f"/api/collections/{coll['id']}/items/{result['uid']}").status_code == 204
    assert client.delete(f"/api/collections/{coll['id']}").status_code == 204


def test_ledger_refuses_red(client):
    asset = load("pexels_search")["photos"][0]
    from freestash.providers.stock import parse_pexels_photo

    a = parse_pexels_photo(asset).model_dump(mode="json")
    r = client.post("/api/ledger", json={"uid": "pexels:photo-1234567", "asset": a, "use_case": "bundled"})
    assert r.status_code == 409

