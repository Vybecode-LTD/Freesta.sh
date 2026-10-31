"""Museum open-access APIs: The Met, Art Institute of Chicago, Cleveland, SMK, V&A, Smithsonian.

All live-verified 2026-10-30 except Smithsonian (DEMO_KEY was rate limited; adapter follows the
documented EDAN response shape). Museum rights determinations are published by the institution
itself, so trust is INSTITUTION.
"""

from __future__ import annotations

import asyncio

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

_IMG = frozenset({MediaType.IMAGE})


def _cc0(raw: str) -> LicenseInfo:
    return normalize_license("CC0-1.0").model_copy(update={"raw": raw})


def _copyrighted(raw: str) -> LicenseInfo:
    return LicenseInfo(id="IN-COPYRIGHT", label="In copyright", url="https://rightsstatements.org/vocab/InC/1.0/", raw=raw)


# ===================================================================== The Met
MET = "https://collectionapi.metmuseum.org/public/collection"


def parse_met_object(o: dict) -> Asset | None:
    if not o.get("primaryImage") and not o.get("primaryImageSmall"):
        return None  # non-open-access objects have no image URLs
    renditions = []
    if o.get("primaryImage"):
        renditions.append(Rendition(url=o["primaryImage"], label="original"))
    if o.get("primaryImageSmall"):
        renditions.append(Rendition(url=o["primaryImageSmall"], label="web-large"))
    renditions += [Rendition(url=u, label=f"additional-{i + 1}") for i, u in enumerate(o.get("additionalImages") or [])]
    pd = bool(o.get("isPublicDomain"))
    return Asset(
        provider="met",
        source_id=str(o["objectID"]),
        title=o.get("title") or "Untitled",
        media_type=MediaType.IMAGE,
        license=_cc0("isPublicDomain=true") if pd else _copyrighted("isPublicDomain=false"),
        trust=Trust.INSTITUTION,
        landing_url=o.get("objectURL"),
        creator=o.get("artistDisplayName") or None,
        thumbnail_url=o.get("primaryImageSmall") or o.get("primaryImage"),
        preview_url=o.get("primaryImageSmall") or o.get("primaryImage"),
        renditions=renditions,
        date=o.get("objectDate") or None,
        year=as_int(o.get("objectBeginDate")) if o.get("objectBeginDate") not in (None, 0) else extract_year(o.get("objectDate")),
        tags=[t["term"] for t in o.get("tags") or [] if t.get("term")],
        description=" · ".join(x for x in (o.get("medium"), o.get("department")) if x) or None,
        raw=o,
    )


class MetProvider(Provider):
    info = ProviderInfo(
        id="met", name="The Metropolitan Museum of Art", homepage="https://www.metmuseum.org/art/collection",
        media_types=_IMG, default_trust=Trust.INSTITUTION,
        docs_url="https://metmuseum.github.io/", terms_url="https://www.metmuseum.org/policies/terms-and-conditions",
        notes=("v1 /search was retired 2026-10-01; this adapter uses /v1.1/search (offset/limit).",
               "v1.1 ignores isPublicDomain as a filter, so public-domain status is checked per object.",
               "Search returns IDs only; each object is a follow-up request (limit ~80 req/s)."),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        fetch = min(limit * 2, 40)  # over-fetch: some objects lack open-access images
        data = await self.http.get_json(f"{MET}/v1.1/search", params={
            "q": q, "hasImages": "true", "limit": fetch, "offset": (page - 1) * fetch})
        ids = data.get("objectIDs") or []
        sem = asyncio.Semaphore(8)

        async def one(oid: int) -> Asset | None:
            async with sem:
                try:
                    return parse_met_object(await self.http.get_json(f"{MET}/v1/objects/{oid}", cache_ttl=86400))
                except Exception:
                    return None

        objs = await asyncio.gather(*(one(i) for i in ids))
        assets = [a for a in objs if a and (not hints.commercial_only or a.license.id == "CC0-1.0")]
        return ProviderPage(assets=assets[:limit], total=data.get("total"))

    async def get(self, source_id: str) -> Asset:
        asset = parse_met_object(await self.http.get_json(f"{MET}/v1/objects/{source_id}"))
        if not asset:
            raise LookupError(f"Met object {source_id} has no open-access image")
        return asset


# ===================================================================== Art Institute of Chicago
AIC = "https://api.artic.edu/api/v1"
_AIC_FIELDS = "id,title,artist_display,artist_title,date_display,date_start,image_id,is_public_domain,thumbnail,medium_display,credit_line,term_titles"


def parse_aic(item: dict, iiif: str = "https://www.artic.edu/iiif/2") -> Asset | None:
    if not item.get("image_id"):
        return None
    base = f"{iiif}/{item['image_id']}"
    thumb = item.get("thumbnail") or {}
    pd = bool(item.get("is_public_domain"))
    return Asset(
        provider="artic", source_id=str(item["id"]), title=item.get("title") or "Untitled",
        media_type=MediaType.IMAGE,
        license=_cc0("is_public_domain=true") if pd else _copyrighted("is_public_domain=false"),
        trust=Trust.INSTITUTION, landing_url=f"https://www.artic.edu/artworks/{item['id']}",
        creator=item.get("artist_title") or (item.get("artist_display") or "").split("\n")[0] or None,
        thumbnail_url=f"{base}/full/400,/0/default.jpg", preview_url=f"{base}/full/843,/0/default.jpg",
        renditions=[
            Rendition(url=f"{base}/full/843,/0/default.jpg", label="843w (recommended)", mime="image/jpeg"),
            Rendition(url=f"{base}/full/1686,/0/default.jpg", label="1686w", mime="image/jpeg"),
            Rendition(url=f"{base}/full/max/0/default.jpg", label="max", mime="image/jpeg",
                      width=thumb.get("width"), height=thumb.get("height")),
        ],
        width=thumb.get("width"), height=thumb.get("height"),
        date=item.get("date_display"), year=as_int(item.get("date_start")) or extract_year(item.get("date_display")),
        tags=(item.get("term_titles") or [])[:15], description=item.get("medium_display"), raw=item,
    )


class ArticProvider(Provider):
    info = ProviderInfo(
        id="artic", name="Art Institute of Chicago", homepage="https://www.artic.edu/collection",
        media_types=_IMG, default_trust=Trust.INSTITUTION, docs_url="https://api.artic.edu/docs/",
        terms_url="https://www.artic.edu/image-licensing",
        notes=("Send an AIC-User-Agent header; bare requests can get 403.",
               "IIIF: 843px wide is the cached, recommended size."),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        params: dict[str, str | int] = {"q": q, "limit": limit, "page": page, "fields": _AIC_FIELDS}
        if hints.commercial_only:
            params["query[term][is_public_domain]"] = "true"
        data = await self.http.get_json(f"{AIC}/artworks/search", params=params,
                                        headers={"AIC-User-Agent": self.settings.full_user_agent})
        iiif = (data.get("config") or {}).get("iiif_url", "https://www.artic.edu/iiif/2")
        assets = [a for it in data.get("data", []) if (a := parse_aic(it, iiif))]
        return ProviderPage(assets=assets, total=(data.get("pagination") or {}).get("total"))

    async def get(self, source_id: str) -> Asset:
        data = await self.http.get_json(f"{AIC}/artworks/{source_id}", params={"fields": _AIC_FIELDS},
                                        headers={"AIC-User-Agent": self.settings.full_user_agent})
        asset = parse_aic(data.get("data") or {}, (data.get("config") or {}).get("iiif_url", "https://www.artic.edu/iiif/2"))
        if not asset:
            raise LookupError(f"AIC artwork {source_id} has no image")
        return asset


# ===================================================================== Cleveland Museum of Art
CMA = "https://openaccess-api.clevelandart.org/api"


def parse_cleveland(item: dict) -> Asset | None:
    images = item.get("images") or {}
    if not images:
        return None
    renditions = []
    for label in ("web", "print", "full"):
        img = images.get(label) or {}
        if img.get("url"):
            renditions.append(Rendition(url=img["url"], label=label, width=as_int(img.get("width")),
                                        height=as_int(img.get("height")), bytes=as_int(img.get("filesize"))))
    web = images.get("web") or {}
    creators = item.get("creators") or []
    status = item.get("share_license_status") or ""
    return Asset(
        provider="cleveland", source_id=str(item["id"]), title=item.get("title") or "Untitled",
        media_type=MediaType.IMAGE,
        license=_cc0(f"share_license_status={status}") if status.upper() == "CC0" else _copyrighted(f"share_license_status={status}"),
        trust=Trust.INSTITUTION, landing_url=item.get("url"),
        creator=creators[0].get("description") if creators else None,
        thumbnail_url=web.get("url"), preview_url=web.get("url"), renditions=renditions,
        width=as_int((images.get("print") or {}).get("width")), height=as_int((images.get("print") or {}).get("height")),
        date=item.get("creation_date"), year=as_int(item.get("creation_date_earliest")) or extract_year(item.get("creation_date")),
        description=" · ".join(x for x in (item.get("type"), item.get("technique")) if x) or None,
        tips=["The 'full' rendition is an uncompressed TIFF and can run to hundreds of MB."] if images.get("full") else [],
        raw=item,
    )


class ClevelandProvider(Provider):
    info = ProviderInfo(
        id="cleveland", name="Cleveland Museum of Art", homepage="https://www.clevelandart.org/open-access",
        media_types=_IMG, default_trust=Trust.INSTITUTION,
        docs_url="https://openaccess-api.clevelandart.org/", terms_url="https://www.clevelandart.org/open-access",
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        params: dict[str, str | int] = {"q": q, "limit": limit, "skip": (page - 1) * limit, "has_image": 1}
        if hints.commercial_only:
            params["cc0"] = 1
        data = await self.http.get_json(f"{CMA}/artworks/", params=params)
        assets = [a for it in data.get("data", []) if (a := parse_cleveland(it))]
        return ProviderPage(assets=assets, total=((data.get("info") or {}).get("total")))

    async def get(self, source_id: str) -> Asset:
        data = await self.http.get_json(f"{CMA}/artworks/{source_id}")
        asset = parse_cleveland(data.get("data") or {})
        if not asset:
            raise LookupError(f"Cleveland artwork {source_id} has no image")
        return asset


# ===================================================================== SMK (National Gallery of Denmark)
SMK = "https://api.smk.dk/api/v1"


def parse_smk(item: dict) -> Asset | None:
    if not item.get("image_thumbnail"):
        return None
    titles = item.get("titles") or []
    title = next((t["title"] for t in titles if (t.get("language") or "").lower() in ("engelsk", "english")), None) \
        or (titles[0]["title"] if titles else "Untitled")
    prod = (item.get("production") or [{}])[0]
    dates = item.get("production_date") or [{}]
    lic = normalize_license(None, item.get("rights")) if item.get("rights") else (
        normalize_license("PDM-1.0") if item.get("public_domain") else _copyrighted("public_domain=false"))
    renditions = [Rendition(url=item["image_native"], label="native", width=item.get("image_width"),
                            height=item.get("image_height"), mime=item.get("image_mime_type"),
                            bytes=item.get("image_size"))] if item.get("image_native") else []
    return Asset(
        provider="smk", source_id=item["object_number"], title=title, media_type=MediaType.IMAGE,
        license=lic, trust=Trust.INSTITUTION, landing_url=item.get("frontend_url"),
        creator=prod.get("creator"), thumbnail_url=item["image_thumbnail"], preview_url=item["image_thumbnail"],
        renditions=renditions, width=item.get("image_width"), height=item.get("image_height"),
        date=dates[0].get("period"), year=extract_year(dates[0].get("start"), dates[0].get("period")), raw=item,
    )


class SmkProvider(Provider):
    info = ProviderInfo(
        id="smk", name="SMK – National Gallery of Denmark", homepage="https://open.smk.dk",
        media_types=_IMG, default_trust=Trust.INSTITUTION, docs_url="https://www.smk.dk/article/smk-api/",
        terms_url="https://www.smk.dk/article/smk-api/",
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        filters = "[has_image:true]" + (",[public_domain:true]" if hints.commercial_only else "")
        data = await self.http.get_json(f"{SMK}/art/search/", params={
            "keys": q, "rows": limit, "offset": (page - 1) * limit, "filters": filters, "lang": "en"})
        assets = [a for it in data.get("items") or [] if (a := parse_smk(it))]
        return ProviderPage(assets=assets, total=data.get("found"))

    async def get(self, source_id: str) -> Asset:
        data = await self.http.get_json(f"{SMK}/art/", params={"object_number": source_id, "lang": "en"})
        items = data.get("items") or []
        if not items or not (asset := parse_smk(items[0])):
            raise LookupError(f"SMK object {source_id} not found or has no image")
        return asset


# ===================================================================== Victoria and Albert Museum
VAM = "https://api.vam.ac.uk/v2"


def parse_vam(rec: dict) -> Asset | None:
    images = rec.get("_images") or {}
    base = images.get("_iiif_image_base_url")
    if not base:
        return None
    maker = rec.get("_primaryMaker") or {}
    return Asset(
        provider="vam", source_id=rec["systemNumber"], title=rec.get("_primaryTitle") or rec.get("objectType") or "Untitled",
        media_type=MediaType.IMAGE,
        license=LicenseInfo(id="VAM-TERMS", label="V&A image terms (non-commercial)",
                            url="https://www.vam.ac.uk/info/va-websites-terms-conditions", raw="V&A terms"),
        trust=Trust.INSTITUTION, landing_url=f"https://collections.vam.ac.uk/item/{rec['systemNumber']}/",
        creator=maker.get("name") or None, thumbnail_url=images.get("_primary_thumbnail"),
        preview_url=f"{base}full/!800,800/0/default.jpg",
        renditions=[Rendition(url=f"{base}full/!1600,1600/0/default.jpg", label="1600px", mime="image/jpeg")],
        date=rec.get("_primaryDate"), year=extract_year(rec.get("_primaryDate")),
        description=rec.get("objectType"), raw=rec,
    )


class VamProvider(Provider):
    info = ProviderInfo(
        id="vam", name="Victoria and Albert Museum", homepage="https://collections.vam.ac.uk",
        media_types=_IMG, default_trust=Trust.INSTITUTION, docs_url="https://developers.vam.ac.uk/",
        terms_url="https://www.vam.ac.uk/info/va-websites-terms-conditions",
        notes=("Images are non-commercial: excellent for reference and mood boards, red for anything shipped.",),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        if hints.commercial_only:
            return ProviderPage(assets=[], total=0)  # nothing here is commercial-safe
        data = await self.http.get_json(f"{VAM}/objects/search", params={
            "q": q, "page_size": limit, "page": page, "images_exist": 1})
        assets = [a for r in data.get("records", []) if (a := parse_vam(r))]
        return ProviderPage(assets=assets, total=(data.get("info") or {}).get("record_count"))


# ===================================================================== Smithsonian Open Access
SI = "https://api.si.edu/openaccess/api/v1.0"


def parse_smithsonian(row: dict) -> Asset | None:
    content = row.get("content") or {}
    dnr = content.get("descriptiveNonRepeating") or {}
    media = [m for m in ((dnr.get("online_media") or {}).get("media") or []) if m.get("type") == "Images"]
    if not media:
        return None
    m0 = media[0]
    access = ((m0.get("usage") or {}).get("access") or "").strip()
    resources = m0.get("resources") or []
    renditions = [Rendition(url=r["url"], label=r.get("label") or "file", width=as_int(r.get("width")),
                            height=as_int(r.get("height"))) for r in resources if r.get("url")]
    if not renditions and m0.get("content"):
        renditions = [Rendition(url=m0["content"], label="screen")]
    freetext = content.get("freetext") or {}
    name = first(freetext.get("name") or [])
    date = first(freetext.get("date") or [])
    return Asset(
        provider="smithsonian", source_id=row.get("id") or dnr.get("record_ID", ""),
        title=row.get("title") or (dnr.get("title") or {}).get("content") or "Untitled", media_type=MediaType.IMAGE,
        license=_cc0(f"usage.access={access}") if access.upper() == "CC0" else
        normalize_license("RIGHTS-UNKNOWN").model_copy(update={"raw": f"usage.access={access or 'none'}"}),
        trust=Trust.INSTITUTION, landing_url=dnr.get("record_link"), source_name=dnr.get("data_source"),
        creator=strip_html(name.get("content")) if isinstance(name, dict) else None,
        thumbnail_url=m0.get("thumbnail"), preview_url=m0.get("content") or m0.get("thumbnail"),
        renditions=renditions, date=date.get("content") if isinstance(date, dict) else None,
        year=extract_year(date.get("content") if isinstance(date, dict) else None, first(
            (content.get("indexedStructured") or {}).get("date") or [])),
        raw=row,
    )


class SmithsonianProvider(Provider):
    info = ProviderInfo(
        id="smithsonian", name="Smithsonian Open Access", homepage="https://www.si.edu/openaccess",
        media_types=_IMG, default_trust=Trust.INSTITUTION, key_setting="smithsonian_api_key",
        key_signup_url="https://api.data.gov/signup/", docs_url="https://edan.si.edu/openaccess/apidocs/",
        terms_url="https://www.si.edu/termsofuse", verified_live=False,
        notes=("Free api.data.gov key. Without one, Openverse still covers ~25 Smithsonian units.",),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        data = await self.http.get_json(f"{SI}/search", params={
            "q": f"{q} AND online_media_type:Images", "rows": limit, "start": (page - 1) * limit,
            "api_key": self.key()})
        resp = data.get("response") or {}
        assets = [a for r in resp.get("rows") or [] if (a := parse_smithsonian(r))]
        if hints.commercial_only:
            assets = [a for a in assets if a.license.id == "CC0-1.0"]
        return ProviderPage(assets=assets, total=resp.get("rowCount"))
