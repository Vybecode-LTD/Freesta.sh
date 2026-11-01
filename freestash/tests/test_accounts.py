"""Accounts mode: sign-up, sessions, per-account data, encrypted provider keys, synced preferences."""

import re

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from freestash.accounts import AccountService, UserSecretRow
from freestash.config import Settings, get_settings
from freestash.providers.keys import KEY_CATALOG, settings_with_keys

from .conftest import load

PASSWORD = "correct horse battery"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FREESTASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FREESTASH_AUTH_MODE", "accounts")
    monkeypatch.setenv("FREESTASH_SECRET_KEY", "s" * 40)
    monkeypatch.setenv("FREESTASH_SECRETS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("FREESTASH_HTTP_RETRIES", "0")
    monkeypatch.setenv("FREESTASH_CACHE_TTL_SECONDS", "0")
    for spec in KEY_CATALOG:  # the developer's own .env/environment must not leak into these tests
        monkeypatch.delenv(spec.name, raising=False)
        monkeypatch.delenv(f"FREESTASH_{spec.name}", raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env file
    get_settings.cache_clear()
    from freestash.api.app import app
    from freestash.api.auth import limiter

    limiter.reset()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def signup(c: TestClient, email: str = "ada@example.com", password: str = PASSWORD) -> dict[str, str]:
    r = c.post("/api/auth/register", json={"email": email, "password": password, "display_name": "Ada"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_register_login_me_and_personal_library(client):
    hdr = signup(client)
    assert client.get("/api/auth/me", headers=hdr).json()["email"] == "ada@example.com"
    me = client.get("/api/me", headers=hdr).json()
    assert me["team_id"] and me["teams"] == [me["team_id"]]

    ok = client.post("/api/auth/login", json={"email": " ADA@example.com ", "password": PASSWORD})
    assert ok.status_code == 200 and ok.json()["user"]["display_name"] == "Ada"
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "nope-nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}).status_code == 401
    dup = client.post("/api/auth/register", json={"email": "Ada@Example.com", "password": PASSWORD})
    assert dup.status_code == 409


def test_sign_up_validation(client):
    assert client.post("/api/auth/register", json={"email": "a@b.co", "password": "short"}).status_code == 400
    assert client.post("/api/auth/register", json={"email": "not-an-email", "password": PASSWORD}).status_code == 400
    assert client.post("/api/auth/register", json={"email": "a@b.co", "password": "x" * 73}).status_code == 400


def test_everything_needs_a_session(client):
    assert client.get("/api/collections").status_code == 401
    assert client.get("/api/collections", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/api/health").json()["signup_open"] is True
    assert client.get("/api/keys/catalog").status_code == 200  # public


def test_change_password_and_sign_out_everywhere_revoke_old_tokens(client):
    old = signup(client)
    r = client.post("/api/auth/change-password", headers=old,
                    json={"current_password": PASSWORD, "new_password": "a whole new phrase"})
    assert r.status_code == 200
    new = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert client.get("/api/auth/me", headers=new).status_code == 200
    wrong = client.post("/api/auth/change-password", headers=new,
                        json={"current_password": "not it at all", "new_password": "another phrase"})
    assert wrong.status_code == 403

    assert client.post("/api/auth/logout-all", headers=new).status_code == 204
    assert client.get("/api/auth/me", headers=new).status_code == 401


def test_collections_and_ledger_are_private_to_each_account(client):
    ada, bob = signup(client), signup(client, "bob@example.com")
    coll = client.post("/api/collections", headers=ada, json={"name": "Hero images"}).json()
    assert [c["id"] for c in client.get("/api/collections", headers=ada).json()] == [coll["id"]]
    assert client.get("/api/collections", headers=bob).json() == []
    assert client.get(f"/api/collections/{coll['id']}", headers=bob).status_code == 404
    assert client.delete(f"/api/collections/{coll['id']}", headers=bob).status_code == 404


def test_keys_are_encrypted_masked_and_only_revealed_to_their_owner(client):
    ada, bob = signup(client), signup(client, "bob@example.com")
    r = client.put("/api/me/keys", headers=ada, json={"values": {"PEXELS_API_KEY": "  pexels-secret-1234  "}})
    pexels = next(k for k in r.json()["keys"] if k["name"] == "PEXELS_API_KEY")
    assert pexels == {"name": "PEXELS_API_KEY", "set": True, "hint": "1234", "updated_at": pexels["updated_at"]}
    assert all(not k["set"] for k in client.get("/api/me/keys", headers=bob).json()["keys"])

    with client.app.state.store.session() as s:
        row = s.query(UserSecretRow).one()
    assert "pexels-secret" not in row.ciphertext

    assert client.get("/api/me/keys/PEXELS_API_KEY", headers=ada).json()["value"] == "pexels-secret-1234"
    assert client.get("/api/me/keys/PEXELS_API_KEY", headers=bob).json()["value"] is None
    assert client.put("/api/me/keys", headers=ada, json={"values": {"NOT_A_KEY": "x"}}).status_code == 400
    assert client.get("/api/me/keys/NOT_A_KEY", headers=ada).status_code == 404

    client.put("/api/me/keys", headers=ada, json={"values": {"PEXELS_API_KEY": None}})
    assert client.get("/api/me/keys/PEXELS_API_KEY", headers=ada).json()["value"] is None


@respx.mock
def test_search_runs_with_the_callers_own_key(client):
    ada, bob = signup(client), signup(client, "bob@example.com")
    client.put("/api/me/keys", headers=ada, json={"values": {"PEXELS_API_KEY": "ada-pexels-key"}})
    route = respx.get("https://api.pexels.com/v1/search").mock(return_value=httpx.Response(200, json=load("pexels_search")))

    enabled = {p["id"]: p["enabled"] for p in client.get("/api/providers", headers=ada).json()}
    assert enabled["pexels"] is True
    assert {p["id"]: p["enabled"] for p in client.get("/api/providers", headers=bob).json()}["pexels"] is False

    r = client.post("/api/search", headers=ada, json={"q": "fog", "providers": ["pexels"]}).json()
    assert r["results"] and route.calls.last.request.headers["Authorization"] == "ada-pexels-key"
    calls = route.call_count
    r = client.post("/api/search", headers=bob, json={"q": "fog", "providers": ["pexels"]}).json()
    assert r["results"] == [] and route.call_count == calls  # Bob has no key, so Pexels isn't asked


@respx.mock
def test_openverse_register_saves_the_pair_to_the_account(client):
    ada = signup(client)
    route = respx.post("https://api.openverse.org/v1/auth_tokens/register/").mock(return_value=httpx.Response(
        201, json={"name": "x", "client_id": "ov-id-1234", "client_secret": "ov-secret-9876"}))
    r = client.post("/api/keys/openverse/register", headers=ada, json={})
    assert r.status_code == 200 and r.json()["email"] == "ada@example.com"
    sent = route.calls.last.request
    assert b"ada@example.com" in sent.content and sent.headers["User-Agent"].startswith("Freestash/")
    keys = {k["name"]: k for k in client.get("/api/me/keys", headers=ada).json()["keys"]}
    assert keys["OPENVERSE_CLIENT_ID"]["hint"] == "1234" and keys["OPENVERSE_CLIENT_SECRET"]["hint"] == "9876"

    route.mock(return_value=httpx.Response(400, json={"name": ["taken"]}))
    assert client.post("/api/keys/openverse/register", headers=ada, json={}).status_code == 502


def test_server_keys_are_not_handed_to_users_unless_shared():
    base = Settings(pexels_api_key="owner-key", _env_file=None)
    assert settings_with_keys(base, {}, share_server_keys=False).pexels_api_key is None
    assert settings_with_keys(base, {}, share_server_keys=True).pexels_api_key == "owner-key"
    assert settings_with_keys(base, {"PEXELS_API_KEY": "mine"}, share_server_keys=True).pexels_api_key == "mine"


def test_preferences_follow_the_account(client):
    ada = signup(client)
    first = client.get("/api/me/settings", headers=ada).json()
    assert first["updated_at"] is None and first["data"]["theme"] == "dark" and first["data"]["accent"] == "sodium"
    saved = client.put("/api/me/settings", headers=ada, json={"data": {
        "theme": "light", "accent": "iris", "default_use_case": "bundled", "default_media": ["audio", "image"],
        "results_per_source": 20, "unknown_field": 1}}).json()
    assert saved["data"]["theme"] == "light" and saved["data"]["default_use_case"] == "bundled"
    assert saved["updated_at"] and "unknown_field" not in saved["data"]
    assert client.get("/api/me/settings", headers=ada).json()["data"] == saved["data"]
    assert client.put("/api/me/settings", headers=ada, json={"data": {"accent": "neon"}}).status_code == 422


def test_password_reset_is_single_use_and_revokes_sessions(client, monkeypatch):
    old = signup(client)
    sent: list[str] = []

    async def fake_send(settings, to, subject, text):
        sent.append(text)
        return True

    monkeypatch.setattr("freestash.api.auth.send_email", fake_send)
    assert client.post("/api/auth/forgot", json={"email": "nobody@example.com"}).json() == {"ok": True}
    assert sent == []  # same answer, no email, for an unknown address
    assert client.post("/api/auth/forgot", json={"email": "ada@example.com"}).json() == {"ok": True}
    token = re.search(r"token=([\w-]+)", sent[0]).group(1)

    assert client.post("/api/auth/reset", json={"token": token, "new_password": "fresh start phrase"}).status_code == 204
    assert client.post("/api/auth/reset", json={"token": token, "new_password": "again again"}).status_code == 400
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "fresh start phrase"}).status_code == 200


def test_login_is_rate_limited(client):
    signup(client)
    codes = [client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-guess"}).status_code
             for _ in range(9)]
    assert codes[:8] == [401] * 8 and codes[8] == 429


def test_rate_limit_keys_on_the_client_not_the_proxy(client):
    """Behind Railway's edge every request arrives from the proxy; the limit must follow the real client."""
    signup(client)

    def attempt(ip: str) -> int:
        return client.post("/api/auth/login", headers={"X-Forwarded-For": f"{ip}, 10.0.0.1"},
                           json={"email": "ada@example.com", "password": "wrong-guess"}).status_code

    assert [attempt("203.0.113.7") for _ in range(9)][-1] == 429
    assert attempt("198.51.100.4") == 401  # a different client isn't locked out by the first one


def test_a_forged_cloudflare_header_cannot_dodge_the_limit(client):
    """freesta.sh isn't behind Cloudflare, so nothing strips a CF-Connecting-IP the client sends itself.
    Rotating it got 9 failed logins past the 8-per-5-minutes limit on production (2026-11-01)."""
    signup(client)

    def attempt(i: int) -> int:
        return client.post("/api/auth/login", headers={"CF-Connecting-IP": f"198.51.100.{i}", "X-Forwarded-For": "203.0.113.7"},
                           json={"email": "ada@example.com", "password": "wrong-guess"}).status_code

    assert [attempt(i) for i in range(9)][-1] == 429


def test_cloudflare_header_counts_only_when_cloudflare_fronts_the_site(client, monkeypatch):
    monkeypatch.setenv("FREESTASH_TRUST_CF_CONNECTING_IP", "true")
    get_settings.cache_clear()
    signup(client)

    def attempt(ip: str) -> int:
        return client.post("/api/auth/login", headers={"CF-Connecting-IP": ip, "X-Forwarded-For": "192.0.2.9"},
                           json={"email": "ada@example.com", "password": "wrong-guess"}).status_code

    assert [attempt("203.0.113.7") for _ in range(9)][-1] == 429
    assert attempt("198.51.100.4") == 401  # Cloudflare's header names the client


def test_accounts_mode_refuses_to_start_without_a_signing_key(tmp_path):
    from freestash.store import Store

    s = Settings(data_dir=tmp_path, auth_mode="accounts", secret_key="short", _env_file=None)
    with pytest.raises(RuntimeError, match="FREESTASH_SECRET_KEY"):
        AccountService(Store(settings=s), s)


def test_railway_database_url_gets_the_psycopg_driver(monkeypatch):
    monkeypatch.delenv("FREESTASH_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.railway.internal:5432/railway")
    assert Settings(_env_file=None).resolved_database_url == "postgresql+psycopg://u:p@db.railway.internal:5432/railway"
    assert Settings(database_url="postgres://u:p@h/db", _env_file=None).resolved_database_url == "postgresql+psycopg://u:p@h/db"
