"""Freestash MCP server (MCP Python SDK 2.x `MCPServer`, stdio transport).

Claude Code:     claude mcp add freestash -- python -m freestash mcp
Claude Desktop:  {"mcpServers": {"freestash": {"command": "python", "args": ["-m", "freestash", "mcp"]}}}
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer

from freestash import __version__
from freestash.config import get_settings
from freestash.export import attribution_markdown, credits_html, ledger_csv
from freestash.licenses import evaluate_all, normalize_license, us_public_domain_cutoff
from freestash.models import Asset, MediaType, ScoredAsset, SearchQuery, Tier, Trust, UseCase
from freestash.providers import PROVIDERS

INSTRUCTIONS = """Freestash finds public domain and openly licensed assets (images, audio, video, PBR textures, HDRIs,
3D models, fonts, icons) across ~20 sources and scores each result GREEN / YELLOW / RED for a use case.

Always pass the use_case that matches what the asset is for. The same file can be GREEN for one and RED for another:
- reference: mood boards and internal reference; never shipped or shown publicly
- demo: shown on demo or preview sites and mockups; files are NOT handed to customers
- client: a commercial client deliverable or production website
- bundled: the file ships inside a product (template download, plugin factory library, app bundle)
- merch: printed onto goods for sale

GREEN means go, but always relay the obligations (credit lines, license files). YELLOW means a human must check
something; say what. Never present a RED result as usable for that use case. Use download_asset to fetch files;
it writes a .license.json sidecar and a ledger entry, and export_credits builds the ATTRIBUTION file at the end.
"""

server = MCPServer(name="freestash", title="Freestash asset finder", version=__version__, instructions=INSTRUCTIONS)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from freestash.search import Freestash

        _engine = Freestash(persist_recent=True)
    return _engine


def _compact(s: ScoredAsset) -> dict[str, Any]:
    a, v = s.asset, s.verdict
    return {
        "uid": s.uid, "title": a.title, "creator": a.creator, "media_type": a.media_type.value,
        "source": a.source_name or a.provider, "license": a.license.label, "license_id": a.license.id,
        "trust": a.trust.value, "tier": v.tier.value, "why": v.reasons[:2], "obligations": v.obligations,
        "attribution": v.attribution, "preview_url": a.preview_url or a.thumbnail_url, "landing_url": a.landing_url,
        "size": f"{a.width}x{a.height}" if a.width and a.height else None,
        "needs_detail": a.detail_required,
    }


@server.tool()
async def search_assets(
    query: str,
    media_types: list[MediaType] | None = None,
    use_case: UseCase = UseCase.DEMO,
    max_tier: Tier = Tier.YELLOW,
    providers: list[str] | None = None,
    limit_per_provider: int = 6,
    page: int = 1,
) -> dict[str, Any]:
    """Search every enabled source at once. media_types: image, audio, video, texture, hdri, model, font, icon.
    Results come back interleaved across sources, GREEN first, each with its license verdict for use_case."""
    engine = _get_engine()
    resp = await engine.search(SearchQuery(q=query, media_types=media_types or [MediaType.IMAGE], use_case=use_case,
                                           max_tier=max_tier, providers=providers,
                                           limit_per_provider=max(1, min(limit_per_provider, 25)), page=page))
    engine.recent.flush()
    return {
        "use_case": use_case.value,
        "results": [_compact(s) for s in resp.results],
        "hidden_by_tier": resp.hidden_by_tier,
        "sources": [{"provider": p.provider, "ok": p.ok, "count": p.count, "error": p.error} for p in resp.providers],
    }


@server.tool()
async def get_asset(uid: str) -> dict[str, Any]:
    """Full detail for one result (all renditions) plus a verdict for every use case. uid looks like 'artic:66144'."""
    scored = await _get_engine().get_asset(uid)
    a = scored.asset
    return {
        "asset": a.model_dump(mode="json"),
        "verdicts": {u.value: v.model_dump(mode="json") for u, v in evaluate_all(a).items()},
    }


@server.tool()
async def download_asset(
    uid: str,
    use_case: UseCase = UseCase.DEMO,
    project: str | None = None,
    dest_dir: str | None = None,
    rendition: str | None = None,
    prefer: str = "large",
    force: bool = False,
) -> dict[str, Any]:
    """Download the file into dest_dir (default: ~/.freestash/downloads/<project>), write <file>.license.json next to it,
    and record it in the license ledger. Refuses RED verdicts unless force=true."""
    from freestash.download import download_asset as _download
    from freestash.store import Store

    settings = get_settings()
    engine = _get_engine()
    scored = await engine.get_asset(uid, use_case)
    if scored.verdict.tier == Tier.RED and not force:
        return {"downloaded": False, "tier": "red", "reasons": scored.verdict.reasons}
    target = Path(dest_dir).expanduser() if dest_dir else settings.resolved_download_dir / (project or "unsorted")
    result = await _download(engine, scored, target, rendition_label=rendition, prefer=prefer, project=project,
                             store=Store(settings=settings))
    return {
        "downloaded": True, "path": str(result.path), "sidecar": str(result.sidecar), "bytes": result.entry.bytes,
        "rendition": result.rendition.label, "tier": scored.verdict.tier.value, "reasons": scored.verdict.reasons,
        "obligations": scored.verdict.obligations, "attribution": scored.verdict.attribution, "ledger_id": result.entry.id,
    }


@server.tool()
async def check_license(
    license: str,
    trust: Trust = Trust.UNKNOWN,
    media_type: MediaType = MediaType.IMAGE,
    year: int | None = None,
) -> dict[str, Any]:
    """Triage any license name, SPDX id, or URL (e.g. 'CC BY-NC 4.0', 'https://unsplash.com/license') across every
    use case. Pass year for 'public domain' claims so the date check can run."""
    is_url = license.startswith("http")
    lic = normalize_license(None if is_url else license, license if is_url else None)
    asset = Asset(provider="manual", source_id="check", title="(license check)", media_type=media_type, license=lic,
                  trust=trust, year=year)
    return {"recognized_as": lic.model_dump(mode="json"),
            "verdicts": {u.value: {"tier": v.tier.value, "reasons": v.reasons, "obligations": v.obligations}
                         for u, v in evaluate_all(asset).items()}}


@server.tool()
async def export_credits(project: str | None = None, format: str = "md") -> str:
    """Build the credits file for everything downloaded into a project: md (ATTRIBUTION.md), html, or csv."""
    from freestash.store import Store

    entries = Store().list_entries(project=project, limit=100_000)
    if format == "html":
        return credits_html(entries)
    if format == "csv":
        return ledger_csv(entries)
    return attribution_markdown(entries, project)


@server.tool()
async def list_providers() -> list[dict[str, Any]]:
    """Sources Freestash can search, the media they cover, and whether each is enabled (some need free API keys)."""
    settings = get_settings()
    return [{"id": c.info.id, "name": c.info.name, "media_types": sorted(m.value for m in c.info.media_types),
             "enabled": c.is_enabled(settings), "needs_key": c.info.key_setting.upper() if c.info.key_setting and not c.info.key_optional else None,
             "notes": list(c.info.notes)} for c in PROVIDERS]


@server.tool()
async def public_domain_cutoff() -> dict[str, Any]:
    """Latest publication years that are reliably public domain in the US today (works vs. sound recordings)."""
    return {"works_published_on_or_before": us_public_domain_cutoff(MediaType.IMAGE),
            "sound_recordings_published_on_or_before": us_public_domain_cutoff(MediaType.AUDIO),
            "note": "US only. Compositions inside recordings have their own copyright. Foreign works differ."}


def main() -> None:
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)  # keep stderr quiet in MCP clients
    server.run("stdio")


if __name__ == "__main__":
    main()
