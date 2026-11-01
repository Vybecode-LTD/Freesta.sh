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


@respx.mock
def test_ledger_pages_past_the_first_page(client):
    """Downloads stopped at the newest 500 entries (PR #1 review). Every entry must be reachable, page by page."""
    respx.get("https://api.smk.dk/api/v1/art/search/").mock(return_value=httpx.Response(200, json=load("smk_search")))
    result = client.post("/api/search", json={"q": "x", "providers": ["smk"]}).json()["results"][0]
    made = [client.post("/api/ledger", json={"uid": result["uid"], "asset": result["asset"], "use_case": "demo",
                                             "file_url": f"https://example.org/{i}.jpg" if i % 2 else None}).json()["id"]
            for i in range(5)]

    seen: list[str] = []
    before = None
    for _ in range(5):  # bounded: a server that ignores `before` repeats page one forever
        page = client.get("/api/ledger", params={"limit": 2, **({"before": before} if before else {})}).json()
        seen += [e["id"] for e in page]
        if len(page) < 2:
            break
        before = page[-1]["id"]
    assert len(seen) == len(set(seen)) == 5 and set(seen) == set(made)

    files = client.get("/api/ledger", params={"files": "true", "limit": 1}).json()
    rest = client.get("/api/ledger", params={"files": "true", "limit": 5, "before": files[0]["id"]}).json()
    assert [e["file_url"] is not None for e in files + rest] == [True, True]

    assert client.get("/api/ledger", params={"limit": 501}).status_code == 422
    assert client.get("/api/ledger", params={"before": "not-an-entry"}).status_code == 400


def test_ledger_refuses_red(client):
    asset = load("pexels_search")["photos"][0]
    from freestash.providers.stock import parse_pexels_photo

    a = parse_pexels_photo(asset).model_dump(mode="json")
    r = client.post("/api/ledger", json={"uid": "pexels:photo-1234567", "asset": a, "use_case": "bundled"})
    assert r.status_code == 409



def test_spa_never_serves_files_outside_the_web_build(tmp_path):
    """`/..%2f..%2fpyproject.toml` read the server's own files on production (2026-11-01)."""
    from freestash.api.app import spa_file

    dist = tmp_path / "web" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "web" / "package.json").write_text("{}", encoding="utf-8")
    index = (dist / "index.html").resolve()

    assert spa_file(dist, "favicon.svg") == (dist / "favicon.svg").resolve()
    for path in ("../package.json", "assets/../../package.json", "../../web/package.json",
                 str(tmp_path / "web" / "package.json"), "", "settings", "assets",
                 "favicon.svg\x00", "..\x00/package.json"):  # %00: resolve() raises on Linux (CI), so a 500 before
        assert spa_file(dist, path) == index, path
