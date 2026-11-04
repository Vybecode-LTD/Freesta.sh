"""Federated search: fan out to providers concurrently, score every result for the use case, merge.

A slow or broken provider never sinks the search: each one has a hard timeout and reports its
own status. `search_stream` yields each provider's batch the moment it lands (the web UI uses it
over SSE, so museums show up in ~1s even while Openverse is still thinking).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from freestash.config import Settings, get_settings
from freestash.http import HttpClient
from freestash.licenses import evaluate
from freestash.models import (
    Asset,
    MediaType,
    ProviderStatus,
    ScoredAsset,
    SearchQuery,
    SearchResponse,
    Tier,
    UseCase,
)
from freestash.providers import Provider, SearchHints, build, select_providers


def _dedupe_key(a: Asset) -> str:
    """The same page found as two kinds (a sprite and a brush) is two results, so the kind is part of the key."""
    url = (a.landing_url or a.preview_url or a.uid).lower().rstrip("/").replace("http://", "https://")
    return f"{a.media_type.value}|{url}"


def _interleave(groups: list[list[ScoredAsset]]) -> list[ScoredAsset]:
    """Round-robin across providers (so one chatty source can't bury the rest), greens first."""
    out: list[ScoredAsset] = []
    for tier in (Tier.GREEN, Tier.YELLOW, Tier.RED):
        queues = [[s for s in g if s.verdict.tier == tier] for g in groups]
        while any(queues):
            for q in queues:
                if q:
                    out.append(q.pop(0))
    return out


class RecentCache:
    """uid -> last ScoredAsset seen. Lets `get`/`download` resolve IDs from an earlier search, across CLI runs too."""

    def __init__(self, path: Path | None = None, max_items: int = 1500) -> None:
        self.path = path
        self.max_items = max_items
        self._data: OrderedDict[str, dict] = OrderedDict()
        if path and path.exists():
            try:
                self._data.update(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass

    def put(self, scored: ScoredAsset) -> None:
        self._data[scored.uid] = scored.asset.model_dump(mode="json")
        self._data.move_to_end(scored.uid)
        while len(self._data) > self.max_items:
            self._data.popitem(last=False)

    def get(self, uid: str) -> Asset | None:
        raw = self._data.get(uid)
        return Asset.model_validate(raw) if raw else None

    def forget_provider(self, provider: str) -> None:
        """Drop one source's cached assets, so the next lookup asks it again (the admin changed a curated pack)."""
        for uid in [u for u in self._data if u.startswith(f"{provider}:")]:
            del self._data[uid]

    def flush(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data), encoding="utf-8")


@dataclass
class ProviderBatch:
    status: ProviderStatus
    results: list[ScoredAsset] = field(default_factory=list)
    hidden: int = 0


class Freestash:
    """The engine. Hold one per process (or per request in the API) and close it when done."""

    def __init__(self, settings: Settings | None = None, http: HttpClient | None = None,
                 *, persist_recent: bool = False) -> None:
        self.settings = settings or get_settings()
        self.http = http or HttpClient(self.settings)
        self.recent = RecentCache(self.settings.data_dir / "recent.json" if persist_recent else None)

    async def __aenter__(self) -> Freestash:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.recent.flush()
        await self.http.aclose()

    async def _run(self, cls: type[Provider], query: SearchQuery, settings: Settings,
                   http: HttpClient | None = None) -> tuple[ProviderStatus, list[Asset]]:
        media = set(query.media_types)
        hints = SearchHints(commercial_only=query.use_case != UseCase.REFERENCE, packs=query.packs)
        provider = cls(http or self.http, settings)
        started = time.perf_counter()
        try:
            page = await asyncio.wait_for(
                provider.search(query.q, media & cls.info.media_types, query.limit_per_provider, query.page, hints),
                timeout=self.settings.provider_timeout,
            )
            assets = [a for a in page.assets if a.media_type in media]
            return ProviderStatus(provider=cls.info.id, ok=True, count=len(assets), total=page.total,
                                  elapsed_ms=int((time.perf_counter() - started) * 1000)), assets
        except TimeoutError:
            err = f"timed out after {self.settings.provider_timeout:.0f}s"
        except Exception as exc:  # noqa: BLE001 - provider failures are reported, never raised
            err = str(exc) or exc.__class__.__name__
        return ProviderStatus(provider=cls.info.id, ok=False, error=err,
                              elapsed_ms=int((time.perf_counter() - started) * 1000)), []

    async def run_provider(self, cls: type[Provider], query: SearchQuery, settings: Settings,
                           http: HttpClient | None = None) -> tuple[ProviderStatus, list[Asset]]:
        """One provider on its own, outside a federated search (the admin's key test). `http` replaces the engine's
        shared client, e.g. a fresh one whose empty cache can't answer for the provider."""
        return await self._run(cls, query, settings, http)

    async def search_stream(self, query: SearchQuery, settings: Settings | None = None) -> AsyncIterator[ProviderBatch]:
        """`settings` overrides the engine's own for one call: the API passes each user's keys this way."""
        settings = settings or self.settings
        classes = select_providers(settings, set(query.media_types), query.providers, query.packs)
        seen: set[str] = set()
        tasks = [asyncio.create_task(self._run(c, query, settings)) for c in classes]
        try:
            for fut in asyncio.as_completed(tasks):
                status, assets = await fut
                batch = ProviderBatch(status=status)
                for a in assets:
                    key = _dedupe_key(a)
                    if key in seen:
                        continue
                    seen.add(key)
                    verdict = evaluate(a, query.use_case)
                    if verdict.tier.rank > query.max_tier.rank:
                        batch.hidden += 1
                        continue
                    scored = ScoredAsset(uid=a.uid, asset=a, verdict=verdict)
                    self.recent.put(scored)
                    batch.results.append(scored)
                batch.results.sort(key=lambda s: s.verdict.tier.rank)
                yield batch
        finally:
            for t in tasks:
                t.cancel()

    async def search(self, query: SearchQuery, settings: Settings | None = None) -> SearchResponse:
        settings = settings or self.settings
        order = {c.info.id: i for i, c in enumerate(select_providers(settings, set(query.media_types), query.providers, query.packs))}
        batches = [b async for b in self.search_stream(query, settings)]
        batches.sort(key=lambda b: order.get(b.status.provider, 99))  # stable, registry order
        return SearchResponse(
            query=query, results=_interleave([b.results for b in batches]), providers=[b.status for b in batches],
            hidden_by_tier=sum(b.hidden for b in batches), generated_at=datetime.now(UTC),
        )

    async def get_asset(self, uid: str, use_case: UseCase = UseCase.DEMO, *, fresh: bool = False,
                        settings: Settings | None = None) -> ScoredAsset:
        """Resolve a uid ('provider:source_id'). Uses the recent-results cache unless the asset needs detail."""
        cached = self.recent.get(uid)
        if cached and not cached.detail_required and not fresh:
            return ScoredAsset(uid=uid, asset=cached, verdict=evaluate(cached, use_case))
        provider_id, _, source_id = uid.partition(":")
        provider = build(provider_id, self.http, settings or self.settings)
        try:
            asset = await provider.get(source_id)
        except Exception:
            if cached:  # provider has no detail endpoint or it failed: the search copy is still valid
                return ScoredAsset(uid=uid, asset=cached, verdict=evaluate(cached, use_case))
            raise
        scored = ScoredAsset(uid=asset.uid, asset=asset, verdict=evaluate(asset, use_case))
        self.recent.put(scored)
        return scored


async def quick_search(q: str, media: list[MediaType] | None = None, use_case: UseCase = UseCase.DEMO,
                       **kwargs) -> SearchResponse:
    async with Freestash() as engine:
        return await engine.search(SearchQuery(q=q, media_types=media or [MediaType.IMAGE], use_case=use_case, **kwargs))
