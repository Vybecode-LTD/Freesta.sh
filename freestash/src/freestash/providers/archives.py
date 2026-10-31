"""Government and archive sources: NASA, Library of Congress, Internet Archive, Europeana. All live-verified 2026-10-30."""

from __future__ import annotations

import asyncio
import re

from freestash.licenses import normalize_license
from freestash.models import Asset, LicenseInfo, MediaType, Rendition, Trust
from freestash.providers.base import (
    Provider,
    ProviderInfo,
    ProviderPage,
    SearchHints,
    as_int,
    extract_year,
    first,
    strip_html,
)

# ===================================================================== NASA Image and Video Library
NASA = "https://images-api.nasa.gov"
_NASA_TYPES = {MediaType.IMAGE: "image", MediaType.AUDIO: "audio", MediaType.VIDEO: "video"}
_THIRD_PARTY = re.compile(r"\b(ESA|©|copyright|Getty|AP Photo|Reuters|Roscosmos|JAXA)\b", re.I)
NASA_NOTES = [
    "NASA media guidelines: don't imply NASA endorsement and don't use the NASA insignia or logotype.",
    "Identifiable people (astronauts, staff) may have publicity rights; get releases for advertising use.",
]


def parse_nasa(item: dict) -> Asset:
    d = (item.get("data") or [{}])[0]
    media = {"image": MediaType.IMAGE, "audio": MediaType.AUDIO, "video": MediaType.VIDEO}.get(d.get("media_type"), MediaType.IMAGE)
    links = item.get("links") or []
    preview = next((lk for lk in links if lk.get("rel") == "preview"), None)
    renditions = [Rendition(url=lk["href"], label=lk["href"].rsplit("~", 1)[-1].split(".")[0] if "~" in lk["href"] else "file",
                            width=lk.get("width"), height=lk.get("height"), bytes=lk.get("size"))
                  for lk in links if lk.get("render") == "image" and lk.get("rel") in ("alternate", "canonical")]
    credit = " ".join(x for x in (d.get("secondary_creator"), d.get("photographer")) if x)
    third_party = bool(_THIRD_PARTY.search(credit + " " + (d.get("description") or "")[:400]))
    notes = list(NASA_NOTES)
    if third_party:
        notes.insert(0, f"Credit line ('{credit or 'see description'}') suggests a non-NASA rights holder; verify before use.")
    return Asset(
        provider="nasa", source_id=d.get("nasa_id", ""), title=(d.get("title") or "Untitled").strip(" -"),
        media_type=media,
        license=LicenseInfo(id="PD-US-GOV", label="Public domain (US federal government work)",
                            url="https://www.nasa.gov/nasa-brand-center/images-and-media/", raw="NASA media usage guidelines"),
        trust=Trust.UNKNOWN if third_party else Trust.GOVERNMENT,
        landing_url=f"https://images.nasa.gov/details/{d.get('nasa_id')}", source_name=d.get("center"),
        creator=credit or d.get("center"), thumbnail_url=preview["href"] if preview else None,
        preview_url=next((r.url for r in renditions if r.label == "medium"), preview["href"] if preview else None),
        renditions=renditions, date=d.get("date_created"), year=extract_year(d.get("date_created")),
        tags=(d.get("keywords") or [])[:20], description=d.get("description"), notes=notes,
        detail_required=media != MediaType.IMAGE or not renditions, raw=item,
    )


class NasaProvider(Provider):
    info = ProviderInfo(
        id="nasa", name="NASA Image and Video Library", homepage="https://images.nasa.gov",
        media_types=frozenset(_NASA_TYPES), default_trust=Trust.GOVERNMENT,
        docs_url="https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf",
        terms_url="https://www.nasa.gov/nasa-brand-center/images-and-media/",
        notes=("Includes ambisonic and broadcast audio (e.g. Artemis II launch audio, 2026).",),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        kinds = ",".join(v for k, v in _NASA_TYPES.items() if k in media_types)
        data = await self.http.get_json(f"{NASA}/search", params={"q": q, "media_type": kinds, "page_size": limit, "page": page})
        coll = data.get("collection") or {}
        return ProviderPage(assets=[parse_nasa(i) for i in coll.get("items", [])],
                            total=(coll.get("metadata") or {}).get("total_hits"))

    async def get(self, source_id: str) -> Asset:
        data = await self.http.get_json(f"{NASA}/search", params={"nasa_id": source_id})
        items = (data.get("collection") or {}).get("items") or []
        if not items:
            raise LookupError(f"NASA id {source_id} not found")
        asset = parse_nasa(items[0])
        manifest = await self.http.get_json(f"{NASA}/asset/{source_id}")
        hrefs = [i["href"] for i in (manifest.get("collection") or {}).get("items", []) if i.get("href")]
        files = [h for h in dict.fromkeys(hrefs) if not h.endswith((".json", ".srt", ".vtt"))]
        asset.renditions = [Rendition(url=h.replace("http://", "https://"), label=h.rsplit("~", 1)[-1] if "~" in h else h.rsplit("/", 1)[-1])
                            for h in files]
        asset.detail_required = False
        return asset


# ===================================================================== Library of Congress
LOC = "https://www.loc.gov"
_LOC_PATHS = {MediaType.IMAGE: "photos", MediaType.AUDIO: "audio", MediaType.VIDEO: "film-and-videos"}


def loc_license(advisory: str | None) -> LicenseInfo:
    text = strip_html(advisory) or ""
    if "no known restrictions" in text.lower():
        return LicenseInfo(id="NKC", label="No known restrictions on publication (LoC)",
                           url="https://www.loc.gov/legal/", raw=text)
    return LicenseInfo(id="RIGHTS-UNKNOWN", label="Rights vary (see LoC rights advisory)", raw=text or None)


def parse_loc(r: dict, media: MediaType, advisory: str | None = None) -> Asset:
    images = [u.split("#")[0] for u in r.get("image_url") or []]
    return Asset(
        provider="loc", source_id=(r.get("id") or "").rstrip("/").rsplit("/", 1)[-1],
        title=first(r.get("title")) or "Untitled", media_type=media, license=loc_license(advisory),
        trust=Trust.INSTITUTION, landing_url=r.get("url") or r.get("id"),
        creator=first(r.get("contributor")) or None, thumbnail_url=images[0] if images else None,
        preview_url=images[-1] if images else None,
        renditions=[Rendition(url=u, label="largest listed") for u in images[-1:]],
        date=r.get("date"), year=extract_year(r.get("date")), tags=(r.get("subject") or [])[:15],
        description=first(r.get("description")), detail_required=True, raw=r,
    )


class LocProvider(Provider):
    info = ProviderInfo(
        id="loc", name="Library of Congress", homepage="https://www.loc.gov/free-to-use/",
        media_types=frozenset(_LOC_PATHS), default_trust=Trust.INSTITUTION,
        docs_url="https://www.loc.gov/apis/json-and-yaml/", terms_url="https://www.loc.gov/legal/",
        notes=("Search results lack rights info; the adapter reads each item's rights_advisory (N+1 requests).",
               "Rate limits are strict (burst ~20 requests); results are cached."),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        limit = min(limit, 10)  # every result costs an extra request
        sem = asyncio.Semaphore(4)
        assets: list[Asset] = []
        total = 0
        for media in (m for m in _LOC_PATHS if m in media_types):
            data = await self.http.get_json(f"{LOC}/{_LOC_PATHS[media]}/", params={
                "q": q, "fo": "json", "c": limit, "sp": page, "fa": "access-restricted:false", "at": "results,pagination"})
            total += (data.get("pagination") or {}).get("total") or 0

            async def enrich(r: dict, media: MediaType = media) -> Asset:
                async with sem:
                    try:
                        item = await self.http.get_json(r["id"], params={"fo": "json", "at": "item"}, cache_ttl=86400)
                        return parse_loc(r, media, (item.get("item") or {}).get("rights_advisory"))
                    except Exception:
                        return parse_loc(r, media)

            assets += await asyncio.gather(*(enrich(r) for r in data.get("results", []) if r.get("id")))
        if hints.commercial_only:
            assets = [a for a in assets if a.license.id != "RIGHTS-UNKNOWN"]
        return ProviderPage(assets=assets, total=total)


# ===================================================================== Internet Archive
IA = "https://archive.org"
_IA_TYPES = {MediaType.VIDEO: "movies", MediaType.AUDIO: "audio", MediaType.IMAGE: "image"}
_IA_SKIP_FORMATS = {"Thumbnail", "Item Tile", "Metadata", "Archive BitTorrent", "JSON", "Columbia Peaks", "Spectrogram",
                    "PNG", "Text", "Item Image", "Animated GIF"}
_CURATED_COLLECTIONS = {"prelinger", "prelinger_library", "fedflix", "nasa", "usgovernmentdocuments"}


def parse_ia_doc(doc: dict) -> Asset:
    ident = doc["identifier"]
    mediatype = doc.get("mediatype")
    media = {"movies": MediaType.VIDEO, "audio": MediaType.AUDIO, "etree": MediaType.AUDIO}.get(mediatype, MediaType.IMAGE)
    collections = set(doc.get("collection") or []) if isinstance(doc.get("collection"), list) else {doc.get("collection")}
    curated = bool(collections & _CURATED_COLLECTIONS)
    return Asset(
        provider="internet_archive", source_id=ident, title=first(doc.get("title")) or ident, media_type=media,
        license=normalize_license(None, doc.get("licenseurl")) if doc.get("licenseurl") else
        LicenseInfo(id="RIGHTS-UNKNOWN", label="No license stated", raw=None),
        trust=Trust.CURATED if curated else Trust.UPLOADER, landing_url=f"{IA}/details/{ident}",
        source_name=", ".join(sorted(c for c in collections if c)) or None,
        creator=first(doc.get("creator")), thumbnail_url=f"{IA}/services/img/{ident}",
        preview_url=f"{IA}/services/img/{ident}", date=first(doc.get("date")), year=extract_year(first(doc.get("date"))),
        description=(strip_html(first(doc.get("description"))) or "")[:500] or None,
        detail_required=True, raw=doc,
    )


class InternetArchiveProvider(Provider):
    info = ProviderInfo(
        id="internet_archive", name="Internet Archive", homepage="https://archive.org",
        media_types=frozenset(_IA_TYPES), default_trust=Trust.UPLOADER,
        docs_url="https://archive.org/developers/", terms_url="https://archive.org/about/terms",
        notes=("Licenses are uploader-asserted. Live probe found a 2025 TV clip marked 'Public Domain'; "
               "the date heuristic flags cases like that.",),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        kinds = " OR ".join(_IA_TYPES[m] for m in _IA_TYPES if m in media_types)
        query = f"({q}) AND mediatype:({kinds})"
        if hints.commercial_only:
            query += " AND (licenseurl:*publicdomain* OR licenseurl:*licenses/by/* OR licenseurl:*licenses/by-sa/*)"
        params = [("q", query), ("rows", limit), ("page", page), ("output", "json")] + [
            ("fl[]", f) for f in ("identifier", "title", "creator", "licenseurl", "mediatype", "date", "description", "collection")]
        data = await self.http.get_json(f"{IA}/advancedsearch.php", params=params)
        resp = data.get("response") or {}
        return ProviderPage(assets=[parse_ia_doc(d) for d in resp.get("docs", [])], total=resp.get("numFound"))

    async def get(self, source_id: str) -> Asset:
        meta = await self.http.get_json(f"{IA}/metadata/{source_id}")
        md = meta.get("metadata") or {}
        asset = parse_ia_doc({**md, "identifier": source_id})
        asset.renditions = [
            Rendition(url=f"{IA}/download/{source_id}/{f['name']}", label=f.get("format") or f["name"],
                      bytes=as_int(f.get("size")), width=as_int(f.get("width")), height=as_int(f.get("height")))
            for f in meta.get("files", [])
            if f.get("format") not in _IA_SKIP_FORMATS and not f["name"].endswith((".xml", ".sqlite", ".torrent"))
        ]
        asset.detail_required = False
        return asset


# ===================================================================== Europeana
EUROPEANA = "https://api.europeana.eu/record/v2"
_EU_TYPES = {MediaType.IMAGE: "IMAGE", MediaType.AUDIO: "SOUND", MediaType.VIDEO: "VIDEO", MediaType.MODEL: "3D"}


def parse_europeana(it: dict) -> Asset:
    provider_name = first(it.get("dataProvider")) or first(it.get("provider"))
    if "wikimedia" in (provider_name or "").lower():
        trust = Trust.COMMUNITY  # Europeana flags Commons as ugc, but Commons has review processes
    elif first(it.get("ugc")) in (True, "true"):
        trust = Trust.UPLOADER
    else:
        trust = Trust.INSTITUTION
    media = {v: k for k, v in _EU_TYPES.items()}.get(it.get("type"), MediaType.IMAGE)
    full = first(it.get("edmIsShownBy"))
    notes = ["Europeana marks this preview as not for redistribution."] if it.get("previewNoDistribute") else []
    guid = (it.get("guid") or "").split("?")[0] or None
    return Asset(
        provider="europeana", source_id=it["id"].lstrip("/"), title=first(it.get("title")) or "Untitled",
        media_type=media, license=normalize_license(None, first(it.get("rights"))), trust=trust,
        landing_url=guid or first(it.get("edmIsShownAt")), source_name=provider_name,
        creator=first(it.get("dcCreator")), thumbnail_url=first(it.get("edmPreview")),
        preview_url=first(it.get("edmPreview")),
        renditions=[Rendition(url=full, label="provider file")] if full else [],
        date=first(it.get("year")), year=extract_year(first(it.get("year"))),
        description=first(it.get("dcDescription")), notes=notes, raw=it,
    )


class EuropeanaProvider(Provider):
    info = ProviderInfo(
        id="europeana", name="Europeana", homepage="https://www.europeana.eu",
        media_types=frozenset(_EU_TYPES), default_trust=Trust.INSTITUTION, key_setting="europeana_api_key",
        key_optional=True, key_signup_url="https://pro.europeana.eu/pages/get-api",
        docs_url="https://pro.europeana.eu/page/search", terms_url="https://www.europeana.eu/en/rights",
        notes=("Runs on the shared 'api2demo' key without your own key (fine for testing, low limits).",
               "Aggregates 3,000+ European institutions; source_name holds the original institution."),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        kinds = " OR ".join(_EU_TYPES[m] for m in _EU_TYPES if m in media_types)
        params: dict[str, str | int] = {"query": q, "wskey": self.key() or "api2demo", "rows": limit,
                                        "start": (page - 1) * limit + 1, "media": "true", "qf": f"TYPE:({kinds})"}
        if hints.commercial_only:
            params["reusability"] = "open"
        data = await self.http.get_json(f"{EUROPEANA}/search.json", params=params)
        return ProviderPage(assets=[parse_europeana(i) for i in data.get("items") or []], total=data.get("totalResults"))
