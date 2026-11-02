"""Keyed "free to use" platforms: Freesound, Pexels, Pixabay, Unsplash.

These need API keys, so they were NOT live-verified from the build sandbox; adapters follow the
platforms' long-stable documented response shapes (verified_live=False). Re-record fixtures with
real keys (IMPLEMENTATION.md, task P1).

Pexels/Pixabay/Unsplash licenses are great for DEMO and CLIENT work but forbid redistributing the
files themselves, so the policy engine marks them RED for BUNDLED. That's the whole point of
having use-case tiers.
"""

from __future__ import annotations

import asyncio
import re

from freestash.licenses import normalize_license, strictest_license
from freestash.models import Asset, LicenseInfo, MediaType, Rendition, Trust
from freestash.providers.base import Provider, ProviderInfo, ProviderPage, SearchHints, extract_year

DAY = 86400


def _platform(lic_id: str, label: str, url: str) -> LicenseInfo:
    return LicenseInfo(id=lic_id, label=label, url=url, raw=label)


# ===================================================================== Freesound
FREESOUND = "https://freesound.org/apiv2"
_FS_FIELDS = "id,name,username,license,previews,duration,tags,url,type,samplerate,channels,filesize,created,description"
_FS_PACK = re.compile(r"/packs/(\d+)/?$")
MAX_PACKS = 6  # pack lookups per search: every member shares the site's daily Freesound quota


def _fs_license(raw: str | None) -> LicenseInfo:
    raw = raw or ""
    return normalize_license(None, raw) if raw.startswith("http") else normalize_license(raw)


def parse_freesound(s: dict) -> Asset:
    previews = s.get("previews") or {}
    return Asset(
        provider="freesound", source_id=str(s["id"]), title=s.get("name") or str(s["id"]), media_type=MediaType.AUDIO,
        license=_fs_license(s.get("license")),
        trust=Trust.UPLOADER, landing_url=s.get("url"), creator=s.get("username"),
        creator_url=f"https://freesound.org/people/{s.get('username')}/" if s.get("username") else None,
        preview_url=previews.get("preview-hq-mp3"),
        renditions=[Rendition(url=u, label=k, mime="audio/mpeg" if k.endswith("mp3") else "audio/ogg")
                    for k, u in previews.items() if k.startswith("preview-hq")],
        duration_seconds=s.get("duration"), date=s.get("created"), year=None,  # upload date, not recording date
        tags=(s.get("tags") or [])[:20], description=(s.get("description") or "")[:500] or None,
        tips=["Freesound previews are lossy; the original file needs a logged-in OAuth2 download from the sound page."],
        raw=s,
    )


def parse_freesound_pack(p: dict, sounds: list[dict], *, detail: bool = False) -> Asset:
    """A Freesound pack. Each sound has its own license, so the pack is cleared by the sounds read: from a search,
    the one that matched; from the detail, up to 150 (contract packs-and-new-kinds)."""
    lics: list[LicenseInfo] = []
    for s in sounds:
        lic = _fs_license(s.get("license"))
        if all(lic.id != seen.id for seen in lics):
            lics.append(lic)
    user = p.get("username")
    return Asset(
        provider="freesound", source_id=f"pack:{p['id']}", title=p.get("name") or f"Pack {p['id']}",
        media_type=MediaType.AUDIO,
        license=strictest_license(lics, Trust.UPLOADER, MediaType.AUDIO) if lics else
        LicenseInfo(id="RIGHTS-UNKNOWN", label="No license read yet"),
        trust=Trust.UPLOADER, landing_url=p.get("url"), creator=user,
        creator_url=f"https://freesound.org/people/{user}/" if user else None,
        preview_url=next(((s.get("previews") or {}).get("preview-hq-mp3") for s in sounds if s.get("previews")), None),
        date=p.get("created"), description=(p.get("description") or "")[:500] or None,
        tips=["Downloading the whole pack needs a Freesound login: open the pack's page."],
        detail_required=not detail, is_pack=True, item_count=p.get("num_sounds"),
        formats=list(dict.fromkeys(str(s["type"]).lower() for s in sounds if s.get("type"))),
        member_licenses=lics, members_checked=len(sounds), raw=p,
    )


class FreesoundProvider(Provider):
    info = ProviderInfo(
        id="freesound", name="Freesound", homepage="https://freesound.org", media_types=frozenset({MediaType.AUDIO}),
        default_trust=Trust.UPLOADER, key_setting="freesound_api_key", key_signup_url="https://freesound.org/apiv2/apply/",
        docs_url="https://freesound.org/docs/api/", terms_url="https://freesound.org/help/tos_web/", verified_live=False,
        notes=("Without a key, Openverse still searches Freesound (CC0/CC-BY filterable).",),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        params: dict[str, str | int] = {"query": q, "token": self.key() or "", "fields": _FS_FIELDS,
                                        "page_size": min(limit, 150), "page": page}
        if hints.commercial_only:
            params["filter"] = 'license:("Creative Commons 0" OR "Attribution")'
        if hints.packs:  # one sound per pack comes back, carrying its pack's URI
            params["fields"] = f"{_FS_FIELDS},pack"
            params["group_by_pack"] = 1
        data = await self.http.get_json(f"{FREESOUND}/search/text/", params=params)
        results = data.get("results", [])
        packs = await self._packs(results) if hints.packs else []
        return ProviderPage(assets=packs + [parse_freesound(s) for s in results], total=data.get("count"))

    async def _packs(self, results: list[dict]) -> list[Asset]:
        """The packs the matching sounds belong to; a pack whose lookup fails is left out (its sound stays)."""
        firsts: dict[str, dict] = {}
        for s in results:
            if (m := _FS_PACK.search(s.get("pack") or "")) and m.group(1) not in firsts:
                firsts[m.group(1)] = s
        ids = list(firsts)[:MAX_PACKS]
        got = await asyncio.gather(*(self.http.get_json(f"{FREESOUND}/packs/{i}/", params={"token": self.key() or ""},
                                                        cache_ttl=DAY) for i in ids), return_exceptions=True)
        return [parse_freesound_pack(p, [firsts[i]]) for i, p in zip(ids, got, strict=True) if isinstance(p, dict)]

    async def get(self, source_id: str) -> Asset:
        kind, _, pack_id = source_id.partition(":")
        token = {"token": self.key() or ""}
        if kind == "pack":
            pack, sounds = await asyncio.gather(
                self.http.get_json(f"{FREESOUND}/packs/{pack_id}/", params=token, cache_ttl=DAY),
                self.http.get_json(f"{FREESOUND}/packs/{pack_id}/sounds/", cache_ttl=DAY,
                                   params={**token, "fields": "id,license,type,previews", "page_size": 150}))
            return parse_freesound_pack(pack, sounds.get("results") or [], detail=True)
        return parse_freesound(await self.http.get_json(f"{FREESOUND}/sounds/{source_id}/",
                                                        params={**token, "fields": _FS_FIELDS}))


# ===================================================================== Pexels
PEXELS = "https://api.pexels.com"
PEXELS_LIC = ("PEXELS", "Pexels License", "https://www.pexels.com/license/")


def parse_pexels_photo(p: dict) -> Asset:
    src = p.get("src") or {}
    return Asset(
        provider="pexels", source_id=f"photo-{p['id']}", title=p.get("alt") or f"Pexels photo {p['id']}",
        media_type=MediaType.IMAGE, license=_platform(*PEXELS_LIC), trust=Trust.COMMUNITY, landing_url=p.get("url"),
        creator=p.get("photographer"), creator_url=p.get("photographer_url"), thumbnail_url=src.get("medium"),
        preview_url=src.get("large"), width=p.get("width"), height=p.get("height"),
        renditions=[Rendition(url=src[k], label=k) for k in ("original", "large2x", "large", "landscape", "portrait")
                    if src.get(k)],
        notes=["Pexels API terms: show a prominent link to Pexels and credit the photographer where possible."],
        raw=p,
    )


def parse_pexels_video(v: dict) -> Asset:
    files = sorted(v.get("video_files") or [], key=lambda f: -(f.get("width") or 0))
    user = v.get("user") or {}
    return Asset(
        provider="pexels", source_id=f"video-{v['id']}", title=f"Pexels video {v['id']}", media_type=MediaType.VIDEO,
        license=_platform(*PEXELS_LIC), trust=Trust.COMMUNITY, landing_url=v.get("url"), creator=user.get("name"),
        creator_url=user.get("url"), thumbnail_url=v.get("image"), preview_url=v.get("image"),
        width=v.get("width"), height=v.get("height"), duration_seconds=v.get("duration"),
        renditions=[Rendition(url=f["link"], label=f"{f.get('quality', '')} {f.get('width')}x{f.get('height')}".strip(),
                              width=f.get("width"), height=f.get("height"), mime=f.get("file_type")) for f in files if f.get("link")],
        raw=v,
    )


class PexelsProvider(Provider):
    info = ProviderInfo(
        id="pexels", name="Pexels", homepage="https://www.pexels.com", media_types=frozenset({MediaType.IMAGE, MediaType.VIDEO}),
        default_trust=Trust.COMMUNITY, key_setting="pexels_api_key", key_signup_url="https://www.pexels.com/api/",
        docs_url="https://www.pexels.com/api/documentation/", terms_url="https://www.pexels.com/license/", verified_live=False,
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        headers = {"Authorization": self.key() or ""}
        assets: list[Asset] = []
        total = 0
        if MediaType.IMAGE in media_types:
            d = await self.http.get_json(f"{PEXELS}/v1/search", params={"query": q, "per_page": min(limit, 80), "page": page}, headers=headers)
            assets += [parse_pexels_photo(p) for p in d.get("photos", [])]
            total += d.get("total_results") or 0
        if MediaType.VIDEO in media_types:
            d = await self.http.get_json(f"{PEXELS}/videos/search", params={"query": q, "per_page": min(limit, 80), "page": page}, headers=headers)
            assets += [parse_pexels_video(v) for v in d.get("videos", [])]
            total += d.get("total_results") or 0
        return ProviderPage(assets=assets, total=total)

    async def get(self, source_id: str) -> Asset:
        kind, _, pid = source_id.partition("-")
        headers = {"Authorization": self.key() or ""}
        if kind == "video":
            return parse_pexels_video(await self.http.get_json(f"{PEXELS}/videos/videos/{pid}", headers=headers))
        return parse_pexels_photo(await self.http.get_json(f"{PEXELS}/v1/photos/{pid}", headers=headers))


# ===================================================================== Pixabay
PIXABAY = "https://pixabay.com/api"
PIXABAY_LIC = ("PIXABAY", "Pixabay Content License", "https://pixabay.com/service/license-summary/")
PIXABAY_NOTE = "Pixabay API terms: no hotlinking. Download files to your own server, and cache API results for 24h."


def parse_pixabay_image(h: dict) -> Asset:
    return Asset(
        provider="pixabay", source_id=f"image-{h['id']}", title=(h.get("tags") or f"Pixabay {h['id']}").split(",")[0].title(),
        media_type=MediaType.IMAGE, license=_platform(*PIXABAY_LIC), trust=Trust.COMMUNITY, landing_url=h.get("pageURL"),
        creator=h.get("user"), creator_url=f"https://pixabay.com/users/{h.get('user')}-{h.get('user_id')}/" if h.get("user") else None,
        thumbnail_url=h.get("previewURL"), preview_url=h.get("webformatURL"), width=h.get("imageWidth"), height=h.get("imageHeight"),
        renditions=[Rendition(url=h[k], label=k) for k in ("largeImageURL", "webformatURL") if h.get(k)],
        tags=[t.strip() for t in (h.get("tags") or "").split(",") if t.strip()], notes=[PIXABAY_NOTE], raw=h,
    )


def parse_pixabay_video(h: dict) -> Asset:
    vids = h.get("videos") or {}
    return Asset(
        provider="pixabay", source_id=f"video-{h['id']}", title=(h.get("tags") or f"Pixabay video {h['id']}").split(",")[0].title(),
        media_type=MediaType.VIDEO, license=_platform(*PIXABAY_LIC), trust=Trust.COMMUNITY, landing_url=h.get("pageURL"),
        creator=h.get("user"), thumbnail_url=(vids.get("medium") or {}).get("thumbnail"),
        preview_url=(vids.get("medium") or {}).get("thumbnail"), duration_seconds=h.get("duration"),
        renditions=[Rendition(url=v["url"], label=k, width=v.get("width"), height=v.get("height"), bytes=v.get("size"))
                    for k, v in vids.items() if isinstance(v, dict) and v.get("url")],
        tags=[t.strip() for t in (h.get("tags") or "").split(",") if t.strip()], notes=[PIXABAY_NOTE], raw=h,
    )


class PixabayProvider(Provider):
    info = ProviderInfo(
        id="pixabay", name="Pixabay", homepage="https://pixabay.com", media_types=frozenset({MediaType.IMAGE, MediaType.VIDEO}),
        default_trust=Trust.COMMUNITY, key_setting="pixabay_api_key", key_signup_url="https://pixabay.com/api/docs/",
        docs_url="https://pixabay.com/api/docs/", terms_url="https://pixabay.com/service/license-summary/", verified_live=False,
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        base = {"key": self.key() or "", "q": q[:100], "per_page": max(3, min(limit, 200)), "page": page, "safesearch": "true"}
        assets: list[Asset] = []
        total = 0
        if MediaType.IMAGE in media_types:
            d = await self.http.get_json(f"{PIXABAY}/", params=base, cache_ttl=DAY)
            assets += [parse_pixabay_image(h) for h in d.get("hits", [])]
            total += d.get("totalHits") or 0
        if MediaType.VIDEO in media_types:
            d = await self.http.get_json(f"{PIXABAY}/videos/", params=base, cache_ttl=DAY)
            assets += [parse_pixabay_video(h) for h in d.get("hits", [])]
            total += d.get("totalHits") or 0
        return ProviderPage(assets=assets, total=total)

    async def get(self, source_id: str) -> Asset:
        kind, _, pid = source_id.partition("-")
        url = f"{PIXABAY}/videos/" if kind == "video" else f"{PIXABAY}/"
        hits = (await self.http.get_json(url, params={"key": self.key() or "", "id": pid}, cache_ttl=DAY)).get("hits") or []
        if not hits:
            raise LookupError(f"Pixabay {source_id} not found")
        return parse_pixabay_video(hits[0]) if kind == "video" else parse_pixabay_image(hits[0])


# ===================================================================== Unsplash
UNSPLASH = "https://api.unsplash.com"


def parse_unsplash(p: dict) -> Asset:
    urls, links, user = p.get("urls") or {}, p.get("links") or {}, p.get("user") or {}
    return Asset(
        provider="unsplash", source_id=p["id"],
        title=p.get("description") or p.get("alt_description") or f"Unsplash photo {p['id']}",
        media_type=MediaType.IMAGE, license=_platform("UNSPLASH", "Unsplash License", "https://unsplash.com/license"),
        trust=Trust.COMMUNITY, landing_url=links.get("html"), creator=user.get("name"),
        creator_url=(user.get("links") or {}).get("html"), thumbnail_url=urls.get("small"), preview_url=urls.get("regular"),
        width=p.get("width"), height=p.get("height"),
        renditions=[Rendition(url=urls[k], label=k) for k in ("full", "regular", "raw") if urls.get(k)],
        date=p.get("created_at"), year=extract_year(p.get("created_at")),
        tags=[t.get("title") for t in p.get("tags") or [] if t.get("title")],
        extra={"download_location": links["download_location"]} if links.get("download_location") else {},
        notes=["Unsplash API guidelines: hotlink the returned image URLs, credit the photographer and Unsplash with links, "
               "and trigger the download endpoint when a file is downloaded (Freestash does this automatically)."],
        raw=p,
    )


class UnsplashProvider(Provider):
    info = ProviderInfo(
        id="unsplash", name="Unsplash", homepage="https://unsplash.com", media_types=frozenset({MediaType.IMAGE}),
        default_trust=Trust.COMMUNITY, key_setting="unsplash_access_key", key_signup_url="https://unsplash.com/developers",
        docs_url="https://unsplash.com/documentation", terms_url="https://unsplash.com/license", verified_live=False,
        notes=("Demo apps get 50 requests/hour until approved for production.",),
    )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Client-ID {self.key()}", "Accept-Version": "v1"}

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        d = await self.http.get_json(f"{UNSPLASH}/search/photos", params={"query": q, "per_page": min(limit, 30), "page": page},
                                     headers=self._headers())
        return ProviderPage(assets=[parse_unsplash(p) for p in d.get("results", [])], total=d.get("total"))

    async def get(self, source_id: str) -> Asset:
        return parse_unsplash(await self.http.get_json(f"{UNSPLASH}/photos/{source_id}", headers=self._headers()))

    async def on_download(self, asset: Asset) -> None:
        loc = asset.extra.get("download_location")
        if loc:
            await self.http.get_json(loc, headers=self._headers(), cache_ttl=0)
