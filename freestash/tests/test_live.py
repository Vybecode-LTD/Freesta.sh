"""Real-network smoke tests. Deselected by default; run with `python -m pytest -m live`."""

import pytest

from freestash.config import Settings
from freestash.models import MediaType, SearchQuery, UseCase
from freestash.providers import PROVIDERS
from freestash.search import Freestash

KEYLESS = [p.info.id for p in PROVIDERS if not p.info.key_setting or p.info.key_optional]
MEDIA_FOR = {"polyhaven": MediaType.TEXTURE, "ambientcg": MediaType.TEXTURE, "fontsource": MediaType.FONT,
             "iconify": MediaType.ICON}
QUERY_FOR = {"fontsource": "mono", "iconify": "arrow", "polyhaven": "wood", "ambientcg": "wood"}


@pytest.mark.live
@pytest.mark.parametrize("provider", KEYLESS)
async def test_provider_returns_results(provider, tmp_path):
    s = Settings(data_dir=tmp_path, provider_timeout=45, _env_file=".env")
    async with Freestash(s) as engine:
        resp = await engine.search(SearchQuery(q=QUERY_FOR.get(provider, "lighthouse"), media_types=[MEDIA_FOR.get(provider, MediaType.IMAGE)],
                                               use_case=UseCase.REFERENCE, providers=[provider], limit_per_provider=3,
                                               max_tier="red"))
    status = resp.providers[0]
    assert status.ok, status.error
