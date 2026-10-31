"""Openverse (WordPress Foundation): one index over ~50 openly licensed image sources plus
Freesound/Jamendo/Wikimedia audio. Doubles as a fallback for sources whose native API needs a key
or is rate limited (Smithsonian, Rijksmuseum, Wikimedia).

Live-verified 2026-10-30:
* anonymous: page_size <= 20 and at most 240 results per query; responses are sometimes slow
  (>40s) or an empty 200, so the shared client retries.
* `license_type=commercial` drops NC licenses server-side; `excluded_source` works.
* Registered apps (client credentials) get higher limits: POST /v1/auth_tokens/token/.
"""

from __future__ import annotations

import time

from freestash.licenses import normalize_license
from freestash.models import Asset, MediaType, Rendition, Trust
from freestash.providers.base import Provider, ProviderInfo, ProviderPage, SearchHints

API = "https://api.openverse.org/v1"

# Sources whose native adapters are on by default; excluded here to avoid duplicates.
NATIVE_DUPES = {"met": "met", "clevelandmuseum": "cleveland", "smk": "smk", "nasa": "nasa"}

_INSTITUTION = {
    "met", "clevelandmuseum", "smk", "rijksmuseum", "brooklynmuseum", "nypl", "wellcome_collection",
    "sciencemuseum", "museumsvictoria", "digitaltmuseum", "finnish_heritage_agency", "finnish_satakunnan_museum",
    "national_museum_of_finland", "bib_gulbenkian", "europeana", "animaldiversity", "bio_diversity", "WoRMS",
}
_GOVERNMENT = {"nasa", "katmai_nps"}
_COMMUNITY = {"wikimedia", "wikimedia_audio"}
_CURATED = {"rawpixel"}


def trust_for_source(source: str) -> Trust:
    if source in _GOVERNMENT:
        return Trust.GOVERNMENT
    if source in _INSTITUTION or source.startswith("smithsonian"):
        return Trust.INSTITUTION
    if source in _COMMUNITY:
        return Trust.COMMUNITY
    if source in _CURATED:
        return Trust.CURATED
    return Trust.UPLOADER


def parse_result(item: dict, media: MediaType) -> Asset:
    source = item.get("source") or item.get("provider") or "openverse"
    lic = normalize_license(item.get("license"), item.get("license_url"), item.get("license_version"))
    renditions = []
    if item.get("url"):
        renditions.append(Rendition(url=item["url"], label="file", width=item.get("width"), height=item.get("height"),
                                    mime=f"{media.value}/{item['filetype']}" if item.get("filetype") else None,
                                    bytes=item.get("filesize")))
    tips = []
    if media == MediaType.AUDIO and source == "freesound":
        tips.append("Openverse links Freesound's preview MP3; the original file is on the Freesound page.")
    duration = item.get("duration")
    return Asset(
        provider="openverse",
        source_id=item["id"],
        title=item.get("title") or "Untitled",
        media_type=media,
        license=lic,
        trust=trust_for_source(source),
        landing_url=item.get("foreign_landing_url"),
        source_name=source,
        creator=item.get("creator"),
        creator_url=item.get("creator_url"),
        thumbnail_url=item.get("thumbnail"),
        preview_url=item.get("url"),
        renditions=renditions,
        width=item.get("width"),
        height=item.get("height"),
        duration_seconds=duration / 1000 if duration else None,
        year=None,  # Openverse has no creation date (indexed_on is when it was crawled)
        tags=[t["name"] for t in item.get("tags") or [] if t.get("name")][:20],
        attribution_hint=item.get("attribution"),
        tips=tips,
        raw=item,
    )


class OpenverseProvider(Provider):
    info = ProviderInfo(
        id="openverse",
        name="Openverse",
        homepage="https://openverse.org",
        media_types=frozenset({MediaType.IMAGE, MediaType.AUDIO}),
        default_trust=Trust.UPLOADER,
        key_setting="openverse_client_id",
        key_optional=True,
        key_signup_url="https://api.openverse.org/v1/#tag/auth/operation/register",
        docs_url="https://api.openverse.org/v1/",
        terms_url="https://docs.openverse.org/terms_of_service.html",
        notes=("Aggregator: trust is set per original source (museum vs. Flickr uploader).",),
    )

    _token: str | None = None
    _token_expiry: float = 0.0

    async def _auth_headers(self) -> dict[str, str]:
        cid, secret = self.settings.openverse_client_id, self.settings.openverse_client_secret
        if not (cid and secret):
            return {}
        if not self._token or time.monotonic() > self._token_expiry:
            data = await self.http.get_json(f"{API}/auth_tokens/token/", method="POST", cache_ttl=0, data={
                "grant_type": "client_credentials", "client_id": cid, "client_secret": secret})
            type(self)._token = data["access_token"]
            type(self)._token_expiry = time.monotonic() + float(data.get("expires_in", 3600)) - 60
        return {"Authorization": f"Bearer {self._token}"}

    def _excluded_sources(self) -> list[str]:
        from freestash.providers import provider_class  # lazy

        excluded = [src for src, pid in NATIVE_DUPES.items() if (cls := provider_class(pid)) and cls.is_enabled(self.settings)]
        if self.settings.wikimedia_access_token:
            excluded.append("wikimedia")
        return excluded

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        headers = await self._auth_headers()
        page_size = min(limit, 50 if headers else 20)
        assets: list[Asset] = []
        total = 0
        for media in (m for m in (MediaType.IMAGE, MediaType.AUDIO) if m in media_types):
            params: dict[str, str | int] = {"q": q, "page_size": page_size, "page": page, "mature": "false"}
            if hints.commercial_only:
                params["license_type"] = "commercial"
            if media == MediaType.IMAGE and (excluded := self._excluded_sources()):
                params["excluded_source"] = ",".join(excluded)
            path = "images" if media == MediaType.IMAGE else "audio"
            data = await self.http.get_json(f"{API}/{path}/", params=params, headers=headers or None)
            total += data.get("result_count") or 0
            assets.extend(parse_result(item, media) for item in data.get("results", []))
        return ProviderPage(assets=assets, total=total)

    async def get(self, source_id: str) -> Asset:
        headers = await self._auth_headers()
        for media, path in ((MediaType.IMAGE, "images"), (MediaType.AUDIO, "audio")):
            try:
                return parse_result(await self.http.get_json(f"{API}/{path}/{source_id}/", headers=headers or None), media)
            except Exception:  # noqa: BLE001 - try the other media type
                continue
        raise LookupError(f"Openverse id {source_id} not found")
