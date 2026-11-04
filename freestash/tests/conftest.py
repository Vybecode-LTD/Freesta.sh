import json
from pathlib import Path

import pytest

from freestash.config import Settings
from freestash.models import Asset, LicenseInfo, MediaType, Trust

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _fresh_github_budget():
    """GitHub's search budget and cool-down are per process; each test starts with a full minute."""
    from freestash.providers import github

    github._budget.reset()
    github._cool_down.clear()


@pytest.fixture
def fixture():
    return load


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(data_dir=tmp_path, contact_email="test@example.com", http_retries=0, provider_timeout=5,
                    cache_ttl_seconds=0, _env_file=None)


def make_asset(license_id: str, *, trust: Trust = Trust.INSTITUTION, media: MediaType = MediaType.IMAGE,
               year: int | None = None, label: str | None = None, notes: list[str] | None = None) -> Asset:
    from freestash.licenses import normalize_license

    lic = normalize_license(license_id)
    if lic.id == "RIGHTS-UNKNOWN" and license_id not in ("RIGHTS-UNKNOWN",):
        lic = LicenseInfo(id=license_id, label=label or license_id)
    return Asset(provider="test", source_id="1", title="Test Asset", media_type=media, license=lic, trust=trust,
                 year=year, creator="Someone", landing_url="https://example.com/a/1", notes=notes or [])
