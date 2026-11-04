"""Curated packs: entries the site's admin recorded by hand on #/admin (contract github-and-curated-packs).

Nothing is fetched. The admin read each pack's license on its publisher's page (Kenney, Quaternius) and typed it in,
so a pack here is curated trust and its license says who recorded it and when. The API passes the list in
`Settings.curated_packs`; the CLI and MCP have no admin, so they never show any.
"""

from __future__ import annotations

from freestash.licenses.normalize import normalize_license
from freestash.models import Asset, CuratedPack, MediaType, Rendition, Trust
from freestash.providers.base import Provider, ProviderInfo, ProviderPage, SearchHints, tokens
from freestash.providers.design import _score


def curated_asset(pack: CuratedPack) -> Asset:
    lic = normalize_license(pack.license_id)
    lic = lic.model_copy(update={"raw": f"{lic.label}, recorded by Freesta.sh from {pack.url} "
                                        f"on {pack.license_checked_on.isoformat()}"})
    file_name = pack.download_url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] if pack.download_url else ""
    renditions = [Rendition(url=pack.download_url, label=file_name or "Download",
                            mime="application/zip" if file_name.lower().endswith(".zip") else None)] if pack.download_url else []
    return Asset(
        provider="curated", source_id=pack.id or "", title=pack.title, media_type=pack.media_type, license=lic,
        trust=Trust.CURATED, landing_url=pack.url, source_name=pack.publisher, creator=pack.publisher,
        thumbnail_url=pack.thumbnail_url, preview_url=pack.thumbnail_url, renditions=renditions, tags=pack.tags,
        description=pack.description, is_pack=True, item_count=pack.item_count, formats=pack.formats,
        tips=[] if renditions else [f"Download it from {pack.publisher}'s page."],
    )


class CuratedProvider(Provider):
    info = ProviderInfo(
        id="curated", name="Curated packs", homepage="https://freesta.sh", media_types=frozenset(MediaType),
        default_trust=Trust.CURATED,
        notes=("Packs the site's admin added by hand, with the license read on the publisher's page.",
               "Off until the admin adds some."),
    )

    @classmethod
    def is_enabled(cls, settings) -> bool:  # noqa: ANN001 - Settings, as in the base class
        return super().is_enabled(settings) and bool(settings.curated_packs)

    async def search(self, q: str, media_types: set[MediaType], limit: int, page: int,
                     hints: SearchHints) -> ProviderPage:
        """Not packs-only: matching costs no quota, so an entry shows whenever it matches, like an archive item."""
        qt = tokens(q)
        scored = [(s, p) for p in self.settings.curated_packs if p.media_type in media_types
                  and (s := _score(qt, p.title, p.publisher, p.tags, p.description, p.formats)) > 0]
        scored.sort(key=lambda sp: (-sp[0], sp[1].title.lower()))
        start = (page - 1) * limit
        return ProviderPage(assets=[curated_asset(p) for _, p in scored[start:start + limit]], total=len(scored))

    async def get(self, source_id: str) -> Asset:
        for pack in self.settings.curated_packs:
            if pack.id == source_id:
                return curated_asset(pack)
        raise LookupError(f"No curated pack {source_id}: the admin may have removed it.")
