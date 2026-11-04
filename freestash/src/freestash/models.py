"""Shared data model. Every surface (CLI, MCP, API, web, future Avalonia app) speaks these shapes."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MediaType(StrEnum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TEXTURE = "texture"  # PBR material sets
    HDRI = "hdri"
    MODEL = "model"  # 3D models
    FONT = "font"
    ICON = "icon"
    BRUSH = "brush"  # Photoshop .abr, Procreate .brushset, Krita .bundle, GIMP .gbr
    SHAPE = "shape"  # Photoshop .csh custom shapes, SVG shape sets
    SPRITE = "sprite"  # 2D sprites, tilesets, UI kits


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
    # A pack is one result holding many files (an icon set, a sound pack, an archive). Contract packs-and-new-kinds.
    is_pack: bool = False
    item_count: int | None = None  # files in the pack, when known
    formats: list[str] = Field(default_factory=list)  # lowercase extensions inside: ["wav", "mp3"]
    # When the source licenses each file: their distinct licenses and how many files were read. None = `license`
    # covers the whole pack, stated by its publisher. For a per-file pack `license` is the strictest member's.
    member_licenses: list[LicenseInfo] = Field(default_factory=list)
    members_checked: int | None = None
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
    packs: bool = False  # also look for packs (sets, sound packs, archive bundles); not a filter


class QueryPick(BaseModel):
    """A query word read as a category ("sfx" -> audio) or as packs ("pack"). `word` is exactly as typed."""

    word: str
    media_type: MediaType | None = None
    packs: bool = False


class ParsedQuery(BaseModel):
    """What `query_words.parse_query` made of the text: search `q` in `media_types` (empty = no pick), with `packs`."""

    original: str
    q: str
    media_types: list[MediaType] = Field(default_factory=list)
    packs: bool = False
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


def _https(value: str | None) -> str | None:
    value = (value or "").strip() or None
    if value and not value.lower().startswith("https://"):
        raise ValueError("must be an https:// address")
    return value


def _words(values: list[str], strip: str = "") -> list[str]:
    return list(dict.fromkeys(v.strip().lower().lstrip(strip) for v in values if v.strip().lstrip(strip)))


class CuratedPack(BaseModel):
    """A pack the site's admin recorded by hand (contract github-and-curated-packs): `license_id` is what they read on
    the publisher's page on `license_checked_on`. Admin-only, so the desktop's Models.cs has no copy."""

    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(max_length=2048)  # the publisher's page for the pack; one entry per url
    publisher: str = Field(min_length=1, max_length=120)
    license_id: str = Field(max_length=40)
    license_checked_on: date
    media_type: MediaType
    download_url: str | None = Field(None, max_length=2048)
    thumbnail_url: str | None = Field(None, max_length=2048)
    item_count: int | None = Field(None, ge=1)
    formats: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    description: str | None = Field(None, max_length=2000)
    updated_at: datetime | None = None

    @field_validator("title", "publisher")
    @classmethod
    def _trim(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("can't be blank")
        return v.strip()

    @field_validator("url")
    @classmethod
    def _page(cls, v: str) -> str:
        page = _https(v)
        if page is None:
            raise ValueError("is required")
        return page

    @field_validator("download_url", "thumbnail_url")
    @classmethod
    def _optional_https(cls, v: str | None) -> str | None:
        return _https(v)

    @field_validator("license_id")
    @classmethod
    def _license(cls, v: str) -> str:
        from freestash.licenses.normalize import normalize_license  # licenses import this module

        lic = normalize_license(v.strip())
        if lic.id == "RIGHTS-UNKNOWN":
            raise ValueError(f"isn't a license Freesta.sh knows: {v!r}")
        return lic.id

    @field_validator("license_checked_on")
    @classmethod
    def _not_future(cls, v: date) -> date:
        if v > datetime.now(UTC).date():
            raise ValueError("can't be in the future")
        return v

    @field_validator("formats")
    @classmethod
    def _formats(cls, v: list[str]) -> list[str]:
        return _words(v, ".")

    @field_validator("tags")
    @classmethod
    def _tags(cls, v: list[str]) -> list[str]:
        return _words(v)

    @field_validator("description")
    @classmethod
    def _description(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


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
