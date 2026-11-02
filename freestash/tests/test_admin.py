"""The admin screen and the site's shared keys (contract admin-shared-keys, decision 0003)."""

from contextlib import contextmanager

import httpx
import pytest
import respx
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from freestash.cli import app as cli
from freestash.config import Settings, get_settings
from freestash.providers.keys import KEY_CATALOG, settings_with_keys

from .conftest import load

PASSWORD = "correct horse battery"
OWNER = "owner@example.com"
PEXELS = "https://api.pexels.com/v1/search"
SMK = "https://api.smk.dk/api/v1/art/search/"


@contextmanager
def make_client(tmp_path, monkeypatch, auth_mode: str = "accounts", **env: str):
    monkeypatch.setenv("FREESTASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FREESTASH_DATABASE_URL", f"sqlite:///{tmp_path / 'freestash.db'}")
    monkeypatch.setenv("FREESTASH_AUTH_MODE", auth_mode)
    monkeypatch.setenv("FREESTASH_SECRET_KEY", "s" * 40)
    monkeypatch.setenv("FREESTASH_SECRETS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("FREESTASH_HTTP_RETRIES", "0")
    monkeypatch.setenv("FREESTASH_CACHE_TTL_SECONDS", "0")
    for spec in KEY_CATALOG:  # the developer's own .env/environment must not leak into these tests
        monkeypatch.delenv(spec.name, raising=False)
        monkeypatch.delenv(f"FREESTASH_{spec.name}", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)  # no stray .env file
    get_settings.cache_clear()
    from freestash.api.app import app
    from freestash.api.auth import limiter

    limiter.reset()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
def client(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch) as c:
        yield c


def signup(c: TestClient, email: str) -> dict[str, str]:
    r = c.post("/api/auth/register", json={"email": email, "password": PASSWORD})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def grant(email: str, *, revoke: bool = False):
    """The only way to make the first admin: a command run on the server (`railway ssh ... python -m freestash admin grant`)."""
    return CliRunner().invoke(cli, ["admin", "revoke" if revoke else "grant", email])


def signup_admin(c: TestClient, email: str = OWNER) -> dict[str, str]:
    hdr = signup(c, email)
    assert grant(email).exit_code == 0
    return hdr


def test_key_order_is_own_then_site_then_env():
    base = Settings(pexels_api_key="env-key", _env_file=None)
    assert settings_with_keys(base, {}, {}).pexels_api_key == "env-key"
    assert settings_with_keys(base, {}, {"PEXELS_API_KEY": "site-key"}).pexels_api_key == "site-key"
    assert settings_with_keys(base, {"PEXELS_API_KEY": " mine "}, {"PEXELS_API_KEY": "site-key"}).pexels_api_key == "mine"
    assert settings_with_keys(Settings(_env_file=None), {}, {}).pexels_api_key is None


def test_only_admins_reach_the_admin_routes(client):
    owner, ada = signup_admin(client), signup(client, "ada@example.com")
    assert client.get("/api/auth/me", headers=owner).json()["is_admin"] is True
    assert client.get("/api/auth/me", headers=ada).json()["is_admin"] is False
    login = client.post("/api/auth/login", json={"email": OWNER, "password": PASSWORD}).json()
    assert login["user"]["is_admin"] is True
    for path in ("/api/admin/keys", "/api/admin/settings", "/api/admin/usage", "/api/admin/users", "/api/admin/audit"):
        assert client.get(path, headers=ada).status_code == 403, path
        assert client.get(path, headers=owner).status_code == 200, path
    assert client.get("/api/admin/keys").status_code == 401


def test_an_email_address_alone_never_makes_an_admin(tmp_path, monkeypatch):
    """PR #6 review (Codex P1): sign-up doesn't prove an address is yours, so whoever first registered an address in
    the retired FREESTASH_ADMIN_EMAILS became an admin. Admins are now granted only by a command on the server."""
    with make_client(tmp_path, monkeypatch, FREESTASH_ADMIN_EMAILS=OWNER) as c:
        squatter = signup(c, OWNER)
        assert c.get("/api/auth/me", headers=squatter).json()["is_admin"] is False
        assert c.get("/api/admin/keys", headers=squatter).status_code == 403


def test_admins_are_granted_and_revoked_from_the_server_command(client):
    ada = signup(client, "ada@example.com")
    assert grant("ADA@example.com ").exit_code == 0  # normalised the way sign-in normalises
    assert client.get("/api/admin/keys", headers=ada).status_code == 200
    listed = CliRunner().invoke(cli, ["admin", "list"])
    assert listed.exit_code == 0 and "ada@example.com" in listed.output
    assert grant("ada@example.com", revoke=True).exit_code == 0
    assert client.get("/api/admin/keys", headers=ada).status_code == 403
    missing = grant("nobody@example.com")
    assert missing.exit_code == 1 and "sign up" in missing.output.lower()
    owner = signup_admin(client)
    audit = client.get("/api/admin/audit", headers=owner).json()
    assert audit[0]["admin_email"] == "server command" and audit[0]["target"] == OWNER
    assert audit[0]["detail"] == {"is_admin": True}


def test_admin_routes_are_off_without_accounts(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch, auth_mode="none") as c:
        assert c.get("/api/admin/keys").status_code == 404


def test_site_keys_are_encrypted_never_returned_and_audited_without_values(client):
    from freestash.admin import ServerSecretRow

    owner = signup_admin(client)
    r = client.put("/api/admin/keys", headers=owner, json={"values": {"PEXELS_API_KEY": "  site-pexels-9876 "}})
    assert r.status_code == 200
    row = next(k for k in r.json() if k["name"] == "PEXELS_API_KEY")
    assert row["source"] == "admin" and row["hint"] == "9876" and row["provider_name"] == "Pexels"
    assert "site-pexels" not in r.text and "site-pexels" not in client.get("/api/admin/keys", headers=owner).text
    with client.app.state.store.session() as s:
        assert "site-pexels" not in s.query(ServerSecretRow).one().ciphertext

    audit = client.get("/api/admin/audit", headers=owner).json()
    assert audit[0]["action"] == "keys.update" and audit[0]["admin_email"] == OWNER
    assert audit[0]["detail"] == {"PEXELS_API_KEY": "set"}

    assert client.put("/api/admin/keys", headers=owner, json={"values": {"NOT_A_KEY": "x"}}).status_code == 400
    cleared = client.put("/api/admin/keys", headers=owner, json={"values": {"PEXELS_API_KEY": None}}).json()
    assert next(k for k in cleared if k["name"] == "PEXELS_API_KEY")["source"] is None
    assert client.get("/api/admin/audit", headers=owner).json()[0]["detail"] == {"PEXELS_API_KEY": "cleared"}


@respx.mock
def test_member_search_runs_on_the_site_key_and_their_own_key_wins(tmp_path, monkeypatch):
    with make_client(tmp_path, monkeypatch, PEXELS_API_KEY="env-pexels") as client:
        owner, ada, bob = signup_admin(client), signup(client, "ada@example.com"), signup(client, "bob@example.com")
        route = respx.get(PEXELS).mock(return_value=httpx.Response(200, json=load("pexels_search")))

        def key_used(hdr: dict[str, str]) -> str:
            r = client.post("/api/search", headers=hdr, json={"q": "fog", "providers": ["pexels"]})
            assert r.status_code == 200 and r.json()["results"], r.text
            return route.calls.last.request.headers["Authorization"]

        sources = {k["name"]: k["source"] for k in client.get("/api/admin/keys", headers=owner).json()}
        assert sources["PEXELS_API_KEY"] == "env" and sources["UNSPLASH_ACCESS_KEY"] is None
        assert key_used(bob) == "env-pexels"  # the env key is the last fallback
        client.put("/api/admin/keys", headers=owner, json={"values": {"PEXELS_API_KEY": "site-pexels"}})
        assert key_used(bob) == "site-pexels"
        client.put("/api/me/keys", headers=ada, json={"values": {"PEXELS_API_KEY": "ada-pexels"}})
        assert key_used(ada) == "ada-pexels"  # a member's own key wins

        assert {p["id"]: p["enabled"] for p in client.get("/api/providers", headers=bob).json()}["pexels"] is True
        keys = {k["name"]: k for k in client.get("/api/me/keys", headers=bob).json()["keys"]}
        assert keys["PEXELS_API_KEY"]["site"] is True and keys["PEXELS_API_KEY"]["set"] is False
        assert keys["UNSPLASH_ACCESS_KEY"]["site"] is False

        usage = {u["provider"]: u for u in client.get("/api/admin/usage", headers=owner).json()}
        assert usage["pexels"]["today"] == {"calls": 2, "errors": 0}  # Bob's two; Ada's own key costs the site nothing
        assert usage["pexels"]["month"]["calls"] == 2 and usage["pexels"]["limits"]
        assert usage["unsplash"]["today"] == {"calls": 0, "errors": 0}


@respx.mock
def test_members_are_capped_per_hour_and_admins_are_not(client):
    owner, ada = signup_admin(client), signup(client, "ada@example.com")
    respx.get(SMK).mock(return_value=httpx.Response(200, json=load("smk_search")))
    assert client.put("/api/admin/settings", headers=owner, json={"searches_per_hour": 2}).json()["searches_per_hour"] == 2
    codes = [client.post("/api/search", headers=ada, json={"q": "x", "providers": ["smk"]}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    assert client.get("/api/search/stream", headers=ada, params={"q": "x", "providers": ["smk"]}).status_code == 429
    assert [client.post("/api/search", headers=owner, json={"q": "x", "providers": ["smk"]}).status_code
            for _ in range(3)] == [200, 200, 200]
    assert client.put("/api/admin/settings", headers=owner, json={"searches_per_hour": 0}).status_code == 422


def test_closing_sign_up_refuses_new_accounts(client):
    owner = signup_admin(client)
    assert client.put("/api/admin/settings", headers=owner, json={"signup_open": False}).json()["signup_open"] is False
    assert client.get("/api/health").json()["signup_open"] is False
    assert client.post("/api/auth/register", json={"email": "late@example.com", "password": PASSWORD}).status_code == 403
    client.put("/api/admin/settings", headers=owner, json={"signup_open": True})
    assert client.post("/api/auth/register", json={"email": "late@example.com", "password": PASSWORD}).status_code == 201
    actions = [a["action"] for a in client.get("/api/admin/audit", headers=owner).json()]
    assert actions[:3] == ["settings.update", "settings.update", "user.update"]  # the last one: the grant


@respx.mock
def test_a_source_the_admin_turns_off_is_not_searched(client):
    owner, ada = signup_admin(client), signup(client, "ada@example.com")
    route = respx.get(SMK).mock(return_value=httpx.Response(200, json=load("smk_search")))
    client.put("/api/admin/settings", headers=owner, json={"disabled_providers": ["smk"]})
    r = client.post("/api/search", headers=ada, json={"q": "x", "providers": ["smk"]}).json()
    assert r["providers"] == [] and route.call_count == 0
    assert {p["id"]: p["enabled"] for p in client.get("/api/providers", headers=ada).json()}["smk"] is False
    assert client.put("/api/admin/settings", headers=owner, json={"disabled_providers": ["nope"]}).status_code == 400


def test_admin_can_disable_a_member_and_promote_another(client):
    owner, ada, bob = signup_admin(client), signup(client, "ada@example.com"), signup(client, "bob@example.com")
    users = {u["email"]: u for u in client.get("/api/admin/users", headers=owner).json()}
    assert users[OWNER]["is_admin"] is True and "bootstrap" not in users[OWNER]
    assert users["ada@example.com"]["is_admin"] is False and users["ada@example.com"]["disabled"] is False
    ada_id, bob_id = users["ada@example.com"]["id"], users["bob@example.com"]["id"]

    assert client.patch(f"/api/admin/users/{ada_id}", headers=owner, json={"disabled": True}).json()["disabled"] is True
    assert client.get("/api/auth/me", headers=ada).status_code == 403
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 403
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": "wrong-guess"}).status_code == 401
    client.patch(f"/api/admin/users/{ada_id}", headers=owner, json={"disabled": False})
    assert client.get("/api/auth/me", headers=ada).status_code == 200

    assert client.patch(f"/api/admin/users/{bob_id}", headers=owner, json={"is_admin": True}).json()["is_admin"] is True
    assert client.get("/api/admin/keys", headers=bob).status_code == 200
    owner_id = users[OWNER]["id"]
    assert client.patch(f"/api/admin/users/{owner_id}", headers=owner, json={"disabled": True}).status_code == 400
    assert client.patch(f"/api/admin/users/{bob_id}", headers=bob, json={"is_admin": False}).status_code == 400
    assert client.patch("/api/admin/users/00000000-0000-0000-0000-00000000dead", headers=owner,
                        json={"disabled": True}).status_code == 404

    assert [u["email"] for u in client.get("/api/admin/users", headers=owner, params={"q": "ADA"}).json()] == ["ada@example.com"]
    audit = client.get("/api/admin/audit", headers=owner).json()
    assert audit[0]["action"] == "user.update" and audit[0]["target"] == "bob@example.com"
    assert audit[0]["detail"] == {"is_admin": True}


@respx.mock
def test_key_test_records_success_and_failure(client):
    owner = signup_admin(client)
    client.put("/api/admin/keys", headers=owner, json={"values": {"PEXELS_API_KEY": "site-pexels"}})
    route = respx.get(PEXELS).mock(return_value=httpx.Response(200, json=load("pexels_search")))
    ok = client.post("/api/admin/keys/PEXELS_API_KEY/test", headers=owner).json()
    assert ok["ok"] is True and ok["error"] is None and route.calls.last.request.headers["Authorization"] == "site-pexels"

    route.mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    bad = client.post("/api/admin/keys/PEXELS_API_KEY/test", headers=owner).json()
    assert bad["ok"] is False and bad["error"]
    row = next(k for k in client.get("/api/admin/keys", headers=owner).json() if k["name"] == "PEXELS_API_KEY")
    assert row["last_ok_at"] and row["last_error"] and row["last_error_at"]

    assert client.post("/api/admin/keys/UNSPLASH_ACCESS_KEY/test", headers=owner).status_code == 400  # nothing to test
    assert client.post("/api/admin/keys/NOT_A_KEY/test", headers=owner).status_code == 404


@respx.mock
def test_key_test_never_answers_from_the_cache(tmp_path, monkeypatch):
    """PR #6 review (Codex P2): with the hour-long HTTP cache on, a second Test got the first one's success back
    without asking the provider, so a key revoked in between still passed."""
    with make_client(tmp_path, monkeypatch, FREESTASH_CACHE_TTL_SECONDS="3600") as client:
        owner = signup_admin(client)
        client.put("/api/admin/keys", headers=owner, json={"values": {"PEXELS_API_KEY": "site-pexels"}})
        route = respx.get(PEXELS).mock(return_value=httpx.Response(200, json=load("pexels_search")))
        assert client.post("/api/admin/keys/PEXELS_API_KEY/test", headers=owner).json()["ok"] is True
        route.mock(return_value=httpx.Response(401, json={"error": "revoked"}))
        again = client.post("/api/admin/keys/PEXELS_API_KEY/test", headers=owner).json()
        assert again["ok"] is False and route.call_count == 2
