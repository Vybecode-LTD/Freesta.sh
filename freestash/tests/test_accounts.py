"""Accounts mode: sign-up, sessions, per-account data, encrypted provider keys, synced preferences."""

import re
from email.utils import parseaddr

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
    monkeypatch.setenv("FREESTASH_DATABASE_URL", f"sqlite:///{tmp_path / 'freestash.db'}")
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


# ---------------------------------------------------------------- the website's cookie session (contract web-cookie-session)
WEB = {"X-Freestash-Session": "cookie", "Origin": "http://testserver"}


def _cookie(r: httpx.Response) -> tuple[str, str]:
    """(token, the whole Set-Cookie line) for freestash_session."""
    line = next(v for k, v in r.headers.multi_items() if k == "set-cookie" and v.startswith("freestash_session="))
    return line.split(";", 1)[0].split("=", 1)[1].strip('"'), line


def _web_signup(c: TestClient) -> dict[str, str]:
    r = c.post("/api/auth/register", headers=WEB, json={"email": "ada@example.com", "password": PASSWORD})
    assert r.status_code == 201, r.text
    return {"Cookie": f"freestash_session={_cookie(r)[0]}", "Origin": "http://testserver"}


def test_web_sign_in_sets_an_httponly_cookie_and_returns_no_token(client):
    r = client.post("/api/auth/register", headers=WEB, json={"email": "ada@example.com", "password": PASSWORD})
    assert r.status_code == 201 and r.json()["token_type"] == "cookie" and "access_token" not in r.json()
    token, line = _cookie(r)
    flags = {f.strip().lower() for f in line.split(";")[1:]}
    assert token and {"httponly", "secure", "samesite=lax", "path=/api"} <= flags
    assert f"max-age={30 * 86400}" in flags

    again = client.post("/api/auth/login", headers=WEB, json={"email": "ada@example.com", "password": PASSWORD})
    assert again.status_code == 200 and "access_token" not in again.json() and _cookie(again)[0]


def test_the_cookie_signs_requests_in(client):
    web = _web_signup(client)
    assert client.get("/api/auth/me", headers={"Cookie": web["Cookie"]}).json()["email"] == "ada@example.com"
    assert client.post("/api/collections", headers=web, json={"name": "Hero images"}).status_code in (200, 201)
    assert client.get("/api/collections", headers={"Cookie": "freestash_session=garbage"}).status_code == 401


def test_a_cross_site_write_with_the_cookie_is_refused(client):
    web = _web_signup(client)
    for origin in ({"Origin": "https://evil.example"}, {"Origin": "null"}, {}):
        r = client.post("/api/collections", headers={"Cookie": web["Cookie"], **origin}, json={"name": "x"})
        assert r.status_code == 403, origin
    referer = client.post("/api/collections", json={"name": "y"},
                          headers={"Cookie": web["Cookie"], "Referer": "http://testserver/#/collections"})
    assert referer.status_code in (200, 201)
    # the site's public URL counts as the site, whatever Host the edge forwards
    public = client.post("/api/collections", json={"name": "z"},
                         headers={"Cookie": web["Cookie"], "Origin": "https://freesta.sh"})
    assert public.status_code in (200, 201)
    # reads are not checked, and bearer callers (the desktop) never are
    assert client.get("/api/collections", headers={"Cookie": web["Cookie"], "Origin": "https://evil.example"}).status_code == 200
    bearer = signup(client, "bob@example.com")
    assert client.post("/api/collections", headers={**bearer, "Origin": "https://evil.example"},
                       json={"name": "b"}).status_code in (200, 201)
    # a cross-site page can't sign a browser into someone else's account either
    login = client.post("/api/auth/login", headers={**WEB, "Origin": "https://evil.example"},
                        json={"email": "ada@example.com", "password": PASSWORD})
    assert login.status_code == 403


def test_logout_clears_the_cookie(client):
    web = _web_signup(client)
    r = client.post("/api/auth/logout", headers=web)
    assert r.status_code == 204
    token, line = _cookie(r)
    assert token == "" and "max-age=0" in line.lower() and "path=/api" in line.lower()
    out = client.post("/api/auth/logout-all", headers=web)
    assert out.status_code == 204 and _cookie(out)[0] == ""
    assert client.get("/api/auth/me", headers={"Cookie": web["Cookie"]}).status_code == 401  # revoked


def test_desktop_sign_in_is_unchanged(client):
    r = client.post("/api/auth/register", json={"email": "ada@example.com", "password": PASSWORD})
    assert r.json()["token_type"] == "bearer" and r.json()["access_token"]
    assert not any(k == "set-cookie" for k, _ in r.headers.multi_items())


def test_cookie_is_not_secure_only_on_loopback(client):
    for host, secure in (("127.0.0.1:8790", False), ("localhost:5173", False), ("[::1]:8790", False),
                         ("freesta.sh", True), ("freestash-production.up.railway.app", True)):
        r = client.post("/api/auth/register", headers={**WEB, "Host": host, "Origin": f"http://{host}"},
                        json={"email": f"u{abs(hash(host))}@example.com", "password": PASSWORD})
        assert r.status_code == 201, (host, r.text)
        assert ("secure" in {f.strip().lower() for f in _cookie(r)[1].split(";")}) is secure, host


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


def test_accounts_mode_refuses_to_start_without_a_database(tmp_path, monkeypatch):
    """With its Postgres service deleted, Railway left DATABASE_URL empty, and accounts went to a SQLite file inside
    the container, which every deploy wiped (production, 2026-11-01). Refuse to start instead."""
    from freestash.store import Store

    monkeypatch.delenv("FREESTASH_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "")  # a reference to a deleted service resolves to an empty string
    s = Settings(data_dir=tmp_path, auth_mode="accounts", secret_key="s" * 40, _env_file=None)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        AccountService(Store(settings=s), s)

    explicit = Settings(data_dir=tmp_path, auth_mode="accounts", secret_key="s" * 40, _env_file=None,
                        database_url=f"sqlite:///{tmp_path / 'chosen.db'}")  # a chosen SQLite file is fine (dev_accounts.py)
    AccountService(Store(settings=explicit), explicit)
    local = Settings(data_dir=tmp_path, _env_file=None)  # the single-user local mode keeps its default file
    AccountService(Store(settings=local), local)


def test_password_hashing_runs_off_the_event_loop(client, monkeypatch):
    """bcrypt takes ~250 ms; run on the event loop it stalls every other request while it hashes."""
    import asyncio

    seen: list[bool] = []
    real = AccountService.authenticate

    def spy(self, email, password):
        try:
            asyncio.get_running_loop()
            seen.append(False)
        except RuntimeError:
            seen.append(True)
        return real(self, email, password)

    signup(client)
    monkeypatch.setattr(AccountService, "authenticate", spy)
    assert client.post("/api/auth/login", json={"email": "ada@example.com", "password": PASSWORD}).status_code == 200
    assert seen == [True]


def test_forgot_answers_the_same_when_the_mailer_fails(client, monkeypatch):
    """A mail outage must not turn into a 500 that only real accounts get (that would reveal who has one)."""
    signup(client)

    async def broken(*_):
        raise ConnectionError("mail server down")

    monkeypatch.setattr("freestash.api.auth.send_email", broken)
    r = client.post("/api/auth/forgot", json={"email": "ada@example.com"})
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_rate_limiter_forgets_idle_keys():
    """Keys carry client-chosen emails and IPs; without a sweep the table grows for ever."""
    from freestash.ratelimit import RateLimiter

    now = [0.0]
    limiter = RateLimiter(clock=lambda: now[0])
    for i in range(500):
        limiter.allow(f"forgot:user{i}@example.com", 3, 3600)
    now[0] = 3600 * 2
    limiter.allow("login:203.0.113.7:ada@example.com", 8, 300)
    assert len(limiter._hits) == 1


def test_names_that_postgres_would_reject_are_refused_or_capped(client):
    long = "x" * 121
    r = client.post("/api/auth/register", json={"email": "ada@example.com", "password": PASSWORD, "display_name": long})
    assert r.status_code == 400
    ada = signup(client)
    assert client.patch("/api/auth/me", headers=ada, json={"display_name": long}).status_code == 400

    from sqlalchemy import select

    from freestash.store import TeamRow

    signup(client, email=f"{'a' * 250}@example.com")  # the team name falls back to the email's local part
    svc = client.app.state.accounts
    with svc.store.session() as s:
        assert max(len(n) for n in s.scalars(select(TeamRow.name))) <= 200


@respx.mock
def test_openverse_register_mails_only_the_account_and_is_limited(client):
    """Sign-up is open, so the email in the body can't be trusted: it would let anyone make Openverse mail
    any address, as often as they like."""
    ada = signup(client)
    route = respx.post("https://api.openverse.org/v1/auth_tokens/register/").mock(return_value=httpx.Response(
        201, json={"name": "x", "client_id": "ov-id-1234", "client_secret": "ov-secret-9876"}))
    r = client.post("/api/keys/openverse/register", headers=ada, json={"email": "someone-else@example.org"})
    assert r.status_code == 200
    assert b"someone-else@example.org" not in route.calls.last.request.content
    assert b"ada@example.com" in route.calls.last.request.content
    codes = [client.post("/api/keys/openverse/register", headers=ada, json={}).status_code for _ in range(3)]
    assert codes[-1] == 429


@pytest.mark.parametrize("mode", ["supabase", "Accounts", "account"])
def test_an_unknown_auth_mode_refuses_to_start(mode):
    """Every guard checks `!= "accounts"`, so a typo (or the retired "supabase") would serve everyone as one
    anonymous local user. It must fail at startup instead."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(auth_mode=mode, _env_file=None)


async def test_unsent_email_never_logs_the_reset_link_or_the_address(tmp_path, caplog):
    from freestash.mailer import send_email

    s = Settings(data_dir=tmp_path, _env_file=None)
    with caplog.at_level("DEBUG", logger="freestash.mail"):
        assert await send_email(s, "ada@example.com", "Reset your password", "https://freesta.sh/#/reset?token=SECRET") is False
    assert "Reset your password" in caplog.text
    assert "SECRET" not in caplog.text and "ada@example.com" not in caplog.text


async def test_dev_server_can_opt_in_to_logging_unsent_email(tmp_path, caplog):
    from freestash.mailer import send_email

    s = Settings(data_dir=tmp_path, log_emails=True, _env_file=None)
    with caplog.at_level("DEBUG", logger="freestash.mail"):
        await send_email(s, "ada@example.com", "Reset your password", "https://127.0.0.1/#/reset?token=LOCAL")
    assert "token=LOCAL" in caplog.text


class FakeSMTP:
    """Stands in for smtplib.SMTP / SMTP_SSL: records what a real server would have seen."""

    sessions: list["FakeSMTP"] = []
    refuse: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.tls_context, self.calls = host, port, context, []
        FakeSMTP.sessions.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")
        self.tls_context = context

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        if FakeSMTP.refuse:
            raise FakeSMTP.refuse
        self.calls.append(("send", msg))


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.sessions, FakeSMTP.refuse = [], None
    monkeypatch.setattr("freestash.mailer.smtplib.SMTP_SSL", FakeSMTP)
    monkeypatch.setattr("freestash.mailer.smtplib.SMTP", type("PlainSMTP", (FakeSMTP,), {}))
    return FakeSMTP


def _smtp_settings(tmp_path, **kw):
    return Settings(data_dir=tmp_path, smtp_username="hello@freesta.sh", smtp_password="mailbox-pw", _env_file=None, **kw)


async def test_reset_email_goes_out_over_implicit_tls_to_spacemail(tmp_path, smtp):
    from freestash.mailer import send_email

    assert await send_email(_smtp_settings(tmp_path), "ada@example.com", "Reset your password", "Open https://x/#/reset?token=T")
    session = smtp.sessions[0]
    assert (session.host, session.port, type(session).__name__) == ("mail.spacemail.com", 465, "FakeSMTP")
    assert session.tls_context is not None and session.calls[0] == ("login", "hello@freesta.sh", "mailbox-pw")
    msg = session.calls[1][1]
    assert parseaddr(msg["From"]) == ("Freesta.sh", "hello@freesta.sh")  # the header quotes the dotted name
    assert (msg["To"], msg["Subject"]) == ("ada@example.com", "Reset your password")
    assert msg["Message-ID"].endswith("@freesta.sh>") and "token=T" in msg.get_content()


async def test_port_587_upgrades_with_starttls_before_logging_in(tmp_path, smtp):
    from freestash.mailer import send_email

    assert await send_email(_smtp_settings(tmp_path, smtp_port=587), "ada@example.com", "Reset", "body")
    session = smtp.sessions[0]
    assert type(session).__name__ == "PlainSMTP" and session.calls[:2] == ["starttls", ("login", "hello@freesta.sh", "mailbox-pw")]


async def test_a_refused_email_logs_no_address_and_no_link(tmp_path, smtp, caplog):
    import smtplib

    from freestash.mailer import send_email

    smtp.refuse = smtplib.SMTPRecipientsRefused({"ada@example.com": (550, b"5.1.1 <ada@example.com> no such user")})
    with caplog.at_level("DEBUG", logger="freestash.mail"):
        assert await send_email(_smtp_settings(tmp_path), "ada@example.com", "Reset your password", "token=SECRET") is False
    assert "SMTPRecipientsRefused" in caplog.text
    assert "ada@example.com" not in caplog.text and "SECRET" not in caplog.text and "mailbox-pw" not in caplog.text


async def test_an_unreachable_smtp_server_is_a_failed_send_not_a_crash(tmp_path, smtp):
    from freestash.mailer import send_email

    smtp.refuse = TimeoutError("timed out")  # what Railway's Hobby plan does to outbound SMTP
    assert await send_email(_smtp_settings(tmp_path), "ada@example.com", "Reset", "body") is False


def test_dev_server_always_uses_its_own_throwaway_database(tmp_path):
    """An inherited DATABASE_URL (or one in .env) must never point the dev server, with its own fresh
    encryption key, at a real database."""
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "dev_accounts.py"
    spec = importlib.util.spec_from_file_location("dev_accounts", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    env = {"DATABASE_URL": "postgresql://prod.example/railway", "FREESTASH_DATABASE_URL": "postgresql://prod.example/railway"}

    mod.prepare_environment("8790", tmp_path, env)

    assert "DATABASE_URL" not in env
    assert env["FREESTASH_DATABASE_URL"] == f"sqlite:///{tmp_path / 'freestash.db'}"
    assert env["FREESTASH_AUTH_MODE"] == "accounts" and env["FREESTASH_LOG_EMAILS"] == "true"


def test_railway_database_url_gets_the_psycopg_driver(monkeypatch):
    monkeypatch.delenv("FREESTASH_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.railway.internal:5432/railway")
    assert Settings(_env_file=None).resolved_database_url == "postgresql+psycopg://u:p@db.railway.internal:5432/railway"
    assert Settings(database_url="postgres://u:p@h/db", _env_file=None).resolved_database_url == "postgresql+psycopg://u:p@h/db"
