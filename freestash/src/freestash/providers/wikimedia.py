"""Wikimedia Commons (MediaWiki Action API).

Since March 2026 Wikimedia enforces global API rate limits; anonymous traffic from shared IPs
(cloud hosts, CI) gets 429s quickly. Set WIKIMEDIA_ACCESS_TOKEN to an OAuth 2.0 owner-only token
(https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose/oauth2) for real limits.
Without a token the adapter still runs, and Openverse keeps covering Commons as a fallback.

NOTE: fixture `wikimedia_search.json` was hand-built from the documented extmetadata shape because
the probe IP was throttled. Re-record it with a token (see IMPLEMENTATION.md, task P1).
"""

from __future__ import annotations

from freestash.licenses import normalize_license
from freestash.models import Asset, MediaType, Rendition, Trust
from freestash.providers.base import (
    Provider,
    ProviderInfo,
    ProviderPage,
    SearchHints,
    extract_year,
    strip_html,
)

API = "https://commons.wikimedia.org/w/api.php"
_FILETYPES = {MediaType.IMAGE: "bitmap|drawing", MediaType.AUDIO: "audio", MediaType.VIDEO: "video"}
_META_FIELDS = "LicenseShortName|LicenseUrl|License|Artist|Credit|UsageTerms|AttributionRequired|DateTimeOriginal|ImageDescription|ObjectName|Copyrighted"


def _meta(info: dict, key: str) -> str | None:
    return (info.get("extmetadata", {}).get(key) or {}).get("value")


def _media_type(mime: str) -> MediaType:
    if mime.startswith("audio/") or mime == "application/ogg":
        return MediaType.AUDIO
    if mime.startswith("video/"):
        return MediaType.VIDEO
    return MediaType.IMAGE


def parse_page(page: dict) -> Asset | None:
    infos = page.get("imageinfo") or []
    if not infos:
        return None
    info = infos[0]
    title = (_meta(info, "ObjectName") and strip_html(_meta(info, "ObjectName"))) or \
        page["title"].removeprefix("File:").rsplit(".", 1)[0]
    lic = normalize_license(_meta(info, "LicenseShortName") or _meta(info, "License"), _meta(info, "LicenseUrl"))
    notes = []
    if lic.id == "PDM-1.0":
        notes.append("Commons 'public domain' covers several templates (PD-old, PD-US, PD-self...); "
                     "the file page says which one applies.")
    mime = info.get("mime", "")
    return Asset(
        provider="wikimedia",
        source_id=str(page["pageid"]),
        title=title,
        media_type=_media_type(mime),
        license=lic,
        trust=Trust.COMMUNITY,
        landing_url=info.get("descriptionurl"),
        creator=strip_html(_meta(info, "Artist")),
        thumbnail_url=info.get("thumburl"),
        preview_url=info.get("thumburl") or info.get("url"),
        renditions=[Rendition(url=info["url"], label="original", width=info.get("width"), height=info.get("height"),
                              mime=mime, bytes=info.get("size"))] if info.get("url") else [],
        width=info.get("width"),
        height=info.get("height"),
        duration_seconds=info.get("duration"),
        date=strip_html(_meta(info, "DateTimeOriginal")),
        year=extract_year(strip_html(_meta(info, "DateTimeOriginal"))),
        description=strip_html(_meta(info, "ImageDescription")),
        notes=notes,
        raw=page,
    )


class WikimediaProvider(Provider):
    info = ProviderInfo(
        id="wikimedia",
        name="Wikimedia Commons",
        homepage="https://commons.wikimedia.org",
        media_types=frozenset({MediaType.IMAGE, MediaType.AUDIO, MediaType.VIDEO}),
        default_trust=Trust.COMMUNITY,
        key_setting="wikimedia_access_token",
        key_optional=True,
        key_signup_url="https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration/propose/oauth2",
        docs_url="https://www.mediawiki.org/wiki/API:Imageinfo",
        terms_url="https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use",
        verified_live=False,
        notes=("Anonymous requests are heavily rate limited since 2026; add an OAuth 2.0 token.",),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        kinds = "|".join(_FILETYPES[m] for m in (MediaType.IMAGE, MediaType.AUDIO, MediaType.VIDEO) if m in media_types)
        token = self.key()
        params = {
            "action": "query", "format": "json", "formatversion": "2", "generator": "search",
            "gsrsearch": f"{q} filetype:{kinds}", "gsrnamespace": "6", "gsrlimit": str(min(limit, 50)),
            "gsroffset": str((page - 1) * limit), "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "640", "iiextmetadatafilter": _META_FIELDS,
        }
        data = await self.http.get_json(API, params=params,
                                        headers={"Authorization": f"Bearer {token}"} if token else None)
        pages = sorted(data.get("query", {}).get("pages", []), key=lambda p: p.get("index", 0))
        assets = [a for p in pages if (a := parse_page(p))]
        return ProviderPage(assets=assets, total=data.get("query", {}).get("searchinfo", {}).get("totalhits"))

    async def get(self, source_id: str) -> Asset:
        token = self.key()
        data = await self.http.get_json(API, params={
            "action": "query", "format": "json", "formatversion": "2", "pageids": source_id, "prop": "imageinfo",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": "640", "iiextmetadatafilter": _META_FIELDS,
        }, headers={"Authorization": f"Bearer {token}"} if token else None)
        pages = data.get("query", {}).get("pages", [])
        if not pages or not (asset := parse_page(pages[0])):
            raise LookupError(f"Commons page {source_id} not found")
        return asset
