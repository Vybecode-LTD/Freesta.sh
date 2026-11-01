"""The web app's Content-Security-Policy (decision 0002): scripts only from the site plus the inline theme script."""

import base64
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from freestash.api.csp import content_security_policy
from freestash.config import get_settings

INDEX = Path(__file__).resolve().parents[1] / "web" / "index.html"


def test_policy_allows_exactly_the_inline_scripts_of_the_page():
    html = INDEX.read_text(encoding="utf-8")
    bodies = re.findall(r"<script>(.*?)</script>", html, flags=re.S)
    assert len(bodies) == 1  # the theme bootstrap; a second inline script needs a reason
    digest = base64.b64encode(hashlib.sha256(bodies[0].encode("utf-8")).digest()).decode()

    policy = dict(d.strip().split(" ", 1) for d in content_security_policy(html).split(";"))
    assert policy["script-src"] == f"'self' 'sha256-{digest}'"
    assert policy["connect-src"] == "'self'" and policy["object-src"] == "'none'" and policy["frame-ancestors"] == "'none'"
    assert "unsafe" not in content_security_policy(html)


def test_a_page_without_inline_scripts_allows_only_the_site():
    policy = content_security_policy('<script type="module" src="/assets/index.js"></script>')
    assert "script-src 'self';" in policy


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FREESTASH_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FREESTASH_AUTH_MODE", "none")
    get_settings.cache_clear()
    from freestash.api.app import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_every_response_carries_the_policy(client):
    r = client.get("/api/health")
    assert r.headers["content-security-policy"].startswith("default-src 'self'")
