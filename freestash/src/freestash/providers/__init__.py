"""Provider registry. Add a source: write an adapter, add its class to PROVIDERS, add a fixture test."""

from __future__ import annotations

from freestash.config import Settings
from freestash.http import HttpClient
from freestash.models import MediaType
from freestash.providers.archives import EuropeanaProvider, InternetArchiveProvider, LocProvider, NasaProvider
from freestash.providers.base import Provider, ProviderInfo, ProviderPage, SearchHints
from freestash.providers.design import (
    AmbientCgProvider,
    FontsourceProvider,
    IconifyProvider,
    PolyHavenProvider,
)
from freestash.providers.museums import (
    ArticProvider,
    ClevelandProvider,
    MetProvider,
    SmithsonianProvider,
    SmkProvider,
    VamProvider,
)
from freestash.providers.openverse import OpenverseProvider
from freestash.providers.stock import FreesoundProvider, PexelsProvider, PixabayProvider, UnsplashProvider
from freestash.providers.wikimedia import WikimediaProvider

PROVIDERS: list[type[Provider]] = [
    # open culture / public domain first: they're the reason this tool exists
    MetProvider, ArticProvider, ClevelandProvider, SmithsonianProvider, SmkProvider, NasaProvider, LocProvider,
    EuropeanaProvider, WikimediaProvider, OpenverseProvider, InternetArchiveProvider,
    # CC0 3D / textures / design resources
    PolyHavenProvider, AmbientCgProvider, FontsourceProvider, IconifyProvider,
    # reference-only
    VamProvider,
    # keyed "free to use" platforms
    FreesoundProvider, UnsplashProvider, PexelsProvider, PixabayProvider,
]

_BY_ID = {p.info.id: p for p in PROVIDERS}


def provider_class(provider_id: str) -> type[Provider] | None:
    return _BY_ID.get(provider_id)


def get_provider_info(provider_id: str) -> ProviderInfo | None:
    cls = _BY_ID.get(provider_id)
    return cls.info if cls else None


def all_provider_info() -> list[ProviderInfo]:
    return [p.info for p in PROVIDERS]


def select_providers(settings: Settings, media_types: set[MediaType], only: list[str] | None = None) -> list[type[Provider]]:
    chosen = []
    for cls in PROVIDERS:
        if only and cls.info.id not in only:
            continue
        if not cls.is_enabled(settings):
            continue
        if not (cls.info.media_types & media_types):
            continue
        chosen.append(cls)
    return chosen


def build(provider_id: str, http: HttpClient, settings: Settings) -> Provider:
    cls = _BY_ID.get(provider_id)
    if not cls:
        raise KeyError(f"unknown provider '{provider_id}'. Known: {', '.join(_BY_ID)}")
    return cls(http, settings)


__all__ = [
    "PROVIDERS",
    "Provider",
    "ProviderInfo",
    "ProviderPage",
    "SearchHints",
    "all_provider_info",
    "build",
    "get_provider_info",
    "provider_class",
    "select_providers",
]
