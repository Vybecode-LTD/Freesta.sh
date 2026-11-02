"""Shared data model. Every surface (CLI, MCP, API, web, future Avalonia app) speaks these shapes."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MediaType(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TEXTURE = "texture"  # PBR material sets
    HDRI = "hdri"
    MODEL = "model"  # 3D models
    FONT = "font"
    ICON = "icon"


class Trust(StrEnum):
    """How much the license claim can be relied on, independent of what the license says.

    A museum's own CC0 determination and an anonymous uploader ticking "public domain"
    are not the same thing, even when the license string is identical.
    """

    INSTITUTION = "institution"  # museum / library / archive publishes its own rights determination
    GOVERNMENT = "government"  # US federal work (17 U.S.C. §105)
    CURATED = "curated"  # platform publishes original, in-house content (Poly Haven, ambientCG)
    COMMUNITY = "community"  # community-reviewed uploads (Wikimedia Commons, Fontsource, Iconify)
    UPLOADER = "uploader"  # uploader-asserted, little or no review (Internet Archive, Freesound, Flickr)
    UNKNOWN = "unknown"


class UseCase(StrEnum):
    """What the asset is going to be used for. The same license gets a different verdict per use."""

    REFERENCE = "reference"  # mood boards, internal reference; never shipped or shown publicly
    DEMO = "demo"  # shown on demo/preview sites and mockups; files are NOT handed to customers
    CLIENT = "client"  # commercial client deliverable or production website
    BUNDLED = "bundled"  # redistributed inside a product: template download, factory library, app assets
    MERCH = "merch"  # printed or pressed onto goods for sale (print-on-demand, covers, posters)


class Tier(StrEnum):
    GREEN = "green"  # go; follow the listed obligations
    YELLOW = "yellow"  # possible, but a human has to check or decide something first
    RED = "red"  # don't

    @property
    def rank(self) -> int:
        return {"green": 0, "yellow": 1, "red": 2}[self.value]


class LicenseInfo(BaseModel):
    """A normalized license. `id` is a key into freestash.licenses.catalog.CATALOG."""

    id: str
    label: str
    url: str | None = None
    raw: str | None = None  # exactly what the provider said, for the ledger


class Rendition(BaseModel):
    """One downloadable/displayable file for an asset (size variants, formats, map types)."""

    url: str
    label: str = "original"
    width: int | None = None
    height: int | None = None
    mime: str | None = None
    bytes: int | None = None


class Asset(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    provider: str
    source_id: str
    title: str
    media_type: MediaType
    license: LicenseInfo
    trust: Trust
    landing_url: str | None = None  # the human-facing source page (keep this for provenance)
    source_name: str | None = None  # originating collection when `provider` is an aggregator (Openverse, Europeana)
    creator: str | None = None
    creator_url: str | None = None
    thumbnail_url: str | None = None
    preview_url: str | None = None
    renditions: list[Rendition] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None
    date: str | None = None  # free-form as the provider gives it ("ca. 1815", "1929", ISO dates)
    year: int | None = None  # best-effort numeric year, used by the public-domain date heuristic
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    attribution_hint: str | None = None  # provider-supplied attribution string, when it has one
    notes: list[str] = Field(default_factory=list)  # usage/legal caveats; surfaced as obligations
    tips: list[str] = Field(default_factory=list)  # practical, non-legal hints (file sizes, install commands)
    detail_required: bool = False  # True when renditions need a follow-up `get_asset` call
    extra: dict[str, Any] = Field(default_factory=dict)  # small provider-specific values that must survive JSON
    raw: dict[str, Any] | None = Field(default=None, exclude=True)

    @property
    def uid(self) -> str:
        return f"{self.provider}:{self.source_id}"


class Verdict(BaseModel):
    use_case: UseCase
    tier: Tier
    reasons: list[str] = Field(default_factory=list)
    obligations: list[str] = Field(default_factory=list)
    attribution: str | None = None


class ScoredAsset(BaseModel):
    """What a search returns: the asset plus its verdict for the requested use case."""

    uid: str
    asset: Asset
    verdict: Verdict


class SearchQuery(BaseModel):
    q: str
    media_types: list[MediaType] = Field(default_factory=lambda: [MediaType.IMAGE])
    use_case: UseCase = UseCase.DEMO
    max_tier: Tier = Tier.YELLOW  # include results at or below this tier
    providers: list[str] | None = None  # None = every enabled provider that covers the media types
    limit_per_provider: int = Field(default=12, ge=1, le=50)
    page: int = Field(default=1, ge=1)


class QueryPick(BaseModel):
    """A query word read as a category ("sfx" -> audio). `word` is exactly as typed, punctuation and all."""

    word: str
    media_type: MediaType


class ParsedQuery(BaseModel):
    """What `query_words.parse_query` made of the text: search `q` in `media_types` (empty = no pick)."""

    original: str
    q: str
    media_types: list[MediaType] = Field(default_factory=list)
    picks: list[QueryPick] = Field(default_factory=list)


class ProviderStatus(BaseModel):
    provider: str
    ok: bool
    count: int = 0
    total: int | None = None
    error: str | None = None
    elapsed_ms: int = 0


class SearchResponse(BaseModel):
    query: SearchQuery
    results: list[ScoredAsset]
    providers: list[ProviderStatus]
    hidden_by_tier: int = 0  # results dropped because they exceeded max_tier
    generated_at: datetime


class LedgerEntry(BaseModel):
    """A permanent record of an asset you actually took, with the license as it stood that day."""

    id: str | None = None
    asset_uid: str
    provider: str
    title: str
    creator: str | None = None
    landing_url: str | None = None
    file_url: str | None = None
    license_id: str
    license_label: str
    license_url: str | None = None
    license_raw: str | None = None
    trust: Trust
    use_case: UseCase
    tier: Tier
    attribution: str | None = None
    project: str | None = None
    sha256: str | None = None
    local_path: str | None = None
    bytes: int | None = None
    retrieved_at: datetime
    created_by: str | None = None
    team_id: str | None = None
    snapshot: dict[str, Any] = Field(default_factory=dict)  # full Asset + Verdict JSON at retrieval time
