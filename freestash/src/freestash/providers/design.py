"""3D, texture, font, and icon sources: Poly Haven, ambientCG, Fontsource, Iconify. All live-verified 2026-10-30.

Poly Haven and Fontsource have no keyword search, so the full catalog is fetched (cached 24h)
and ranked locally.
"""

from __future__ import annotations

from datetime import UTC, datetime

from freestash.licenses import normalize_license
from freestash.models import Asset, LicenseInfo, MediaType, Rendition, Trust
from freestash.providers.base import Provider, ProviderInfo, ProviderPage, SearchHints, extract_year, tokens

DAY = 86400


def _score(q_tokens: list[str], *fields: object) -> int:
    hay = " ".join(" ".join(f) if isinstance(f, (list, tuple, set)) else str(f or "") for f in fields).lower()
    return sum(3 if f" {t} " in f" {hay} " else (1 if t in hay else 0) for t in q_tokens)


# ===================================================================== Poly Haven
PH = "https://api.polyhaven.com"
_PH_TYPES = {MediaType.HDRI: ("hdris", 0), MediaType.TEXTURE: ("textures", 1), MediaType.MODEL: ("models", 2)}
_PH_MEDIA = {0: MediaType.HDRI, 1: MediaType.TEXTURE, 2: MediaType.MODEL}


def parse_polyhaven(asset_id: str, a: dict) -> Asset:
    published = a.get("date_published")
    return Asset(
        provider="polyhaven", source_id=asset_id, title=a.get("name") or asset_id,
        media_type=_PH_MEDIA.get(a.get("type", 1), MediaType.TEXTURE), license=normalize_license("CC0-1.0"),
        trust=Trust.CURATED, landing_url=f"https://polyhaven.com/a/{asset_id}",
        creator=", ".join((a.get("authors") or {}).keys()) or None,
        thumbnail_url=a.get("thumbnail_url"), preview_url=a.get("thumbnail_url"),
        width=(a.get("max_resolution") or [None])[0], height=(a.get("max_resolution") or [None, None])[1],
        year=datetime.fromtimestamp(published, UTC).year if published else None,
        tags=list(dict.fromkeys((a.get("tags") or []) + (a.get("categories") or []))),
        description=a.get("description") or a.get("category"), detail_required=True, raw=a,
    )


def flatten_polyhaven_files(files: dict) -> list[Rendition]:
    """Poly Haven nests files as map/resolution/format -> {url,size}. Flatten with a readable label."""
    out: list[Rendition] = []

    def walk(node: dict, path: list[str]) -> None:
        if isinstance(node, dict) and "url" in node and isinstance(node["url"], str):
            out.append(Rendition(url=node["url"], label="/".join(path), bytes=node.get("size")))
            return
        if isinstance(node, dict):
            for k, v in node.items():
                if k != "include":
                    walk(v, [*path, k])

    walk(files, [])
    res_rank = {"1k": 0, "2k": 1, "4k": 2, "8k": 3, "16k": 4}
    return sorted(out, key=lambda r: (res_rank.get(r.label.split("/")[1] if "/" in r.label else "", 9), r.label))


class PolyHavenProvider(Provider):
    info = ProviderInfo(
        id="polyhaven", name="Poly Haven", homepage="https://polyhaven.com",
        media_types=frozenset(_PH_TYPES), default_trust=Trust.CURATED, docs_url="https://redocly.github.io/redoc/?url=https://api.polyhaven.com/api-docs/swagger.json",
        terms_url="https://polyhaven.com/license",
        notes=("Everything is CC0. No search endpoint: the catalog is cached for 24h and ranked locally.",
               "Poly Haven asks commercial API users to support them (patreon.com/polyhaven)."),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        qt = tokens(q)
        scored: list[tuple[int, int, Asset]] = []
        for media in (m for m in _PH_TYPES if m in media_types):
            catalog = await self.http.get_json(f"{PH}/assets", params={"t": _PH_TYPES[media][0]}, cache_ttl=DAY)
            for aid, a in catalog.items():
                s = _score(qt, aid.replace("_", " "), a.get("name"), a.get("tags"), a.get("categories"), a.get("category"))
                if s:
                    scored.append((s, a.get("download_count", 0), parse_polyhaven(aid, a)))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        start = (page - 1) * limit
        return ProviderPage(assets=[a for *_, a in scored[start:start + limit]], total=len(scored))

    async def get(self, source_id: str) -> Asset:
        info = await self.http.get_json(f"{PH}/info/{source_id}", cache_ttl=DAY)
        asset = parse_polyhaven(source_id, info)
        asset.renditions = flatten_polyhaven_files(await self.http.get_json(f"{PH}/files/{source_id}", cache_ttl=DAY))
        asset.detail_required = False
        return asset


# ===================================================================== ambientCG
ACG = "https://ambientcg.com/api/v2/full_json"
_ACG_TYPES = {
    MediaType.TEXTURE: "Material,Atlas,Decal,PlainTexture,Terrain",
    MediaType.HDRI: "HDRI",
    MediaType.MODEL: "3DModel",
}
_ACG_MEDIA = {"HDRI": MediaType.HDRI, "3DModel": MediaType.MODEL}


def parse_ambientcg(a: dict) -> Asset:
    preview = a.get("previewImage") or {}
    downloads = []
    for folder in (a.get("downloadFolders") or {}).values():
        for cat in (folder.get("downloadFiletypeCategories") or {}).values():
            downloads += cat.get("downloads") or []
    return Asset(
        provider="ambientcg", source_id=a["assetId"], title=a.get("displayName") or a["assetId"],
        media_type=_ACG_MEDIA.get(a.get("dataType"), MediaType.TEXTURE), license=normalize_license("CC0-1.0"),
        trust=Trust.CURATED, landing_url=a.get("shortLink") or f"https://ambientcg.com/view?id={a['assetId']}",
        creator="ambientCG (Lennart Demes)", thumbnail_url=preview.get("256-PNG") or preview.get("512-PNG"),
        preview_url=preview.get("1024-PNG") or preview.get("512-PNG"),
        renditions=[Rendition(url=d["downloadLink"], label=d.get("attribute") or d.get("fileName", "zip"),
                              bytes=d.get("size"), mime="application/zip") for d in downloads if d.get("downloadLink")],
        year=extract_year(a.get("releaseDate")), date=a.get("releaseDate"), tags=a.get("tags") or [],
        description=a.get("description") or a.get("dataTypeName"), raw=a,
    )


class AmbientCgProvider(Provider):
    info = ProviderInfo(
        id="ambientcg", name="ambientCG", homepage="https://ambientcg.com",
        media_types=frozenset(_ACG_TYPES), default_trust=Trust.CURATED, docs_url="https://docs.ambientcg.com/api/",
        terms_url="https://docs.ambientcg.com/license/", notes=("Everything is CC0.",),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        kinds = ",".join(_ACG_TYPES[m] for m in _ACG_TYPES if m in media_types)
        data = await self.http.get_json(ACG, params={"q": q, "type": kinds, "limit": limit, "offset": (page - 1) * limit,
                                                     "include": "downloadData,previewData,tagData", "sort": "Popular"})
        return ProviderPage(assets=[parse_ambientcg(a) for a in data.get("foundAssets", [])], total=data.get("numberOfResults"))

    async def get(self, source_id: str) -> Asset:
        data = await self.http.get_json(ACG, params={"id": source_id, "include": "downloadData,previewData,tagData"})
        found = data.get("foundAssets") or []
        if not found:
            raise LookupError(f"ambientCG asset {source_id} not found")
        return parse_ambientcg(found[0])


# ===================================================================== Fontsource
FS = "https://api.fontsource.org/v1"
FS_CDN = "https://cdn.jsdelivr.net/fontsource/fonts"


def parse_font(f: dict) -> Asset:
    subset = f.get("defSubset") or "latin"
    weights = f.get("weights") or [400]
    w = 400 if 400 in weights else weights[0]
    woff2 = lambda wt, style="normal": f"{FS_CDN}/{f['id']}@latest/{subset}-{wt}-{style}.woff2"  # noqa: E731
    lic = normalize_license(f.get("license"))
    return Asset(
        provider="fontsource", source_id=f["id"], title=f.get("family") or f["id"], media_type=MediaType.FONT,
        license=lic, trust=Trust.CURATED if f.get("type") == "google" else Trust.COMMUNITY,
        landing_url=f"https://fontsource.org/fonts/{f['id']}", source_name="Google Fonts" if f.get("type") == "google" else None,
        preview_url=woff2(w),
        renditions=[Rendition(url=woff2(wt), label=f"{subset} {wt}", mime="font/woff2") for wt in weights]
        + ([Rendition(url=woff2(w, "italic"), label=f"{subset} {w} italic", mime="font/woff2")] if "italic" in (f.get("styles") or []) else []),
        date=f.get("lastModified"),
        tags=[t for t in [f.get("category"), "variable" if f.get("variable") else None, *(f.get("subsets") or [])] if t],
        description=f"{f.get('category', '')} · {len(weights)} weight(s)" + (" · variable" if f.get("variable") else ""),
        tips=["Install via npm: @fontsource/" + f["id"] + (" or @fontsource-variable/" + f["id"] if f.get("variable") else "")],
        raw=f,
    )


class FontsourceProvider(Provider):
    info = ProviderInfo(
        id="fontsource", name="Fontsource", homepage="https://fontsource.org", media_types=frozenset({MediaType.FONT}),
        default_trust=Trust.CURATED, docs_url="https://fontsource.org/docs/api/introduction",
        terms_url="https://github.com/fontsource/fontsource/blob/main/LICENSE",
        notes=("Open-source fonts (mostly Google Fonts, OFL-1.1). Catalog cached 24h, ranked locally.",),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        catalog = await self.http.get_json(f"{FS}/fonts", cache_ttl=DAY)
        qt = tokens(q)
        scored = [(s, f) for f in catalog if (s := _score(qt, f.get("family"), f.get("id", "").replace("-", " "), f.get("category")))]
        scored.sort(key=lambda x: (-x[0], x[1].get("family", "")))
        start = (page - 1) * limit
        return ProviderPage(assets=[parse_font(f) for _, f in scored[start:start + limit]], total=len(scored))

    async def get(self, source_id: str) -> Asset:
        catalog = await self.http.get_json(f"{FS}/fonts", cache_ttl=DAY)
        font = next((f for f in catalog if f.get("id") == source_id), None)
        if not font:
            raise LookupError(f"Fontsource font {source_id} not found")
        return parse_font(font)


# ===================================================================== Iconify
ICONIFY = "https://api.iconify.design"


def parse_icons(data: dict) -> list[Asset]:
    colls = data.get("collections") or {}
    out = []
    for full in data.get("icons") or []:
        prefix, name = full.split(":", 1)
        c = colls.get(prefix) or {}
        lic_meta = c.get("license") or {}
        lic = normalize_license(lic_meta.get("spdx") or lic_meta.get("title"), lic_meta.get("url"))
        if lic.id == "RIGHTS-UNKNOWN" and lic_meta.get("title"):
            lic = LicenseInfo(id="RIGHTS-UNKNOWN", label=f"Unrecognized license ({lic_meta['title']})",
                              url=lic_meta.get("url"), raw=lic_meta.get("title"))
        svg = f"{ICONIFY}/{prefix}/{name}.svg"
        author = c.get("author") or {}
        out.append(Asset(
            provider="iconify", source_id=full, title=f"{name} ({c.get('name', prefix)})", media_type=MediaType.ICON,
            license=lic, trust=Trust.COMMUNITY, landing_url=f"https://icon-sets.iconify.design/{prefix}/{name}/",
            source_name=c.get("name"), creator=author.get("name"), creator_url=author.get("url"),
            thumbnail_url=svg, preview_url=svg, renditions=[Rendition(url=svg, label="svg", mime="image/svg+xml")],
            tags=[t for t in [c.get("category"), *(c.get("tags") or [])] if t], raw={"icon": full, "collection": c},
        ))
    return out


class IconifyProvider(Provider):
    info = ProviderInfo(
        id="iconify", name="Iconify", homepage="https://icon-sets.iconify.design", media_types=frozenset({MediaType.ICON}),
        default_trust=Trust.COMMUNITY, docs_url="https://iconify.design/docs/api/search.html",
        terms_url="https://iconify.design/docs/icons/license.html",
        notes=("275k+ icons across ~255 sets. License is per set: mostly MIT/Apache/CC-BY; a few GPL and NC sets get flagged.",),
    )

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        want = page * limit
        data = await self.http.get_json(f"{ICONIFY}/search", params={"query": q, "limit": max(32, min(want, 999))})
        assets = parse_icons(data)[(page - 1) * limit:want]
        return ProviderPage(assets=assets, total=data.get("total"))

    async def get(self, source_id: str) -> Asset:
        prefix = source_id.split(":", 1)[0]
        colls = await self.http.get_json(f"{ICONIFY}/collections", params={"prefixes": prefix}, cache_ttl=DAY)
        return parse_icons({"icons": [source_id], "collections": colls})[0]
