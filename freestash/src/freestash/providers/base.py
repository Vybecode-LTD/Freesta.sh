"""Provider contract. One adapter per source; adapters keep parsing in pure functions so fixtures can test them."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from html import unescape
from typing import ClassVar

from freestash.config import Settings
from freestash.http import HttpClient
from freestash.models import Asset, MediaType, Trust


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    homepage: str
    media_types: frozenset[MediaType]
    default_trust: Trust
    key_setting: str | None = None  # Settings attribute holding the credential
    key_optional: bool = False  # works anonymously, but a key raises limits
    key_signup_url: str | None = None
    docs_url: str | None = None
    terms_url: str | None = None
    verified_live: bool = True  # False = adapter written from docs, fixture not yet recorded from a real response
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class SearchHints:
    """Optional narrowing a provider *may* apply server-side to cut noise."""

    commercial_only: bool = False  # drop NC/ND/in-copyright at the source when the API supports it


@dataclass
class ProviderPage:
    assets: list[Asset]
    total: int | None = None


class Provider(ABC):
    info: ClassVar[ProviderInfo]

    def __init__(self, http: HttpClient, settings: Settings) -> None:
        self.http = http
        self.settings = settings

    @classmethod
    def is_enabled(cls, settings: Settings) -> bool:
        if cls.info.id in settings.disabled_providers:
            return False
        if cls.info.key_setting and not cls.info.key_optional:
            return bool(getattr(settings, cls.info.key_setting, None))
        return True

    def key(self) -> str | None:
        return getattr(self.settings, self.info.key_setting, None) if self.info.key_setting else None

    @abstractmethod
    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage: ...

    async def get(self, source_id: str) -> Asset:
        """Full detail with renditions. Default: providers whose search results are already complete."""
        raise NotImplementedError(f"{self.info.id} returns complete assets from search; no detail lookup")

    async def on_download(self, asset: Asset) -> None:  # noqa: B027 - optional hook
        """Called when a file is actually downloaded (Unsplash requires a download ping)."""


# ---------------------------------------------------------------- parsing helpers

_YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")
_TAGS = re.compile(r"<[^>]+>")


def extract_year(*values: object) -> int | None:
    for v in values:
        if v is None:
            continue
        if isinstance(v, int):
            return v if 1000 <= v <= 2099 else None
        if m := _YEAR.search(str(v)):
            return int(m.group(1))
    return None


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = unescape(_TAGS.sub("", value)).strip()
    return re.sub(r"\s+", " ", text) or None


def first(value: object) -> object:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def as_int(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def tokens(q: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", q.lower()) if t]
