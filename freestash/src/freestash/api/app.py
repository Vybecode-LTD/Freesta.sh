"""Freestash web API (FastAPI). Run: `freestash serve` or `uvicorn freestash.api.app:app`.

Serves the built React UI from web/dist when present, so one Railway service hosts everything.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from freestash import __version__
from freestash.accounts import AccountService
from freestash.admin import AdminService
from freestash.api import account as account_routes
from freestash.api import admin as admin_routes
from freestash.api import auth as auth_routes
from freestash.api.auth import CurrentUser, current_user, limiter, optional_user
from freestash.api.csp import SecurityHeaders, content_security_policy
from freestash.config import Settings, get_settings
from freestash.export import attribution_markdown, credits_html, ledger_csv
from freestash.licenses import (
    build_attribution_html,
    evaluate_all,
    normalize_license,
    us_public_domain_cutoff,
)
from freestash.models import (
    Asset,
    LedgerEntry,
    MediaType,
    ProviderStatus,
    ScoredAsset,
    SearchQuery,
    SearchResponse,
    Tier,
    Trust,
    UseCase,
)
from freestash.providers import PROVIDERS
from freestash.providers.keys import settings_with_keys, site_keyed_providers
from freestash.search import Freestash
from freestash.store import Store, entry_from_scored

# Source checkout: <repo>/web/dist. Docker/non-editable installs set FREESTASH_WEB_DIST.
WEB_DIST = Path(os.environ.get("FREESTASH_WEB_DIST") or Path(__file__).resolve().parents[3] / "web" / "dist")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.engine = Freestash(settings)
    app.state.store = Store(settings=settings)
    admin = app.state.admin = AdminService(app.state.store, settings)
    app.state.accounts = AccountService(app.state.store, settings, signup_open=lambda: admin.site().signup_open)
    yield
    await app.state.engine.http.aclose()


app = FastAPI(title="Freestash", version=__version__, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
_INDEX = WEB_DIST / "index.html"
app.add_middleware(SecurityHeaders, csp=content_security_policy(_INDEX.read_text(encoding="utf-8") if _INDEX.is_file() else ""))

User = Annotated[CurrentUser, Depends(current_user)]
MaybeUser = Annotated[CurrentUser | None, Depends(optional_user)]

app.include_router(auth_routes.router)
app.include_router(account_routes.router)
app.include_router(admin_routes.router)


def engine(request: Request) -> Freestash:
    return request.app.state.engine


def store(request: Request) -> Store:
    return request.app.state.store


def search_settings(request: Request, user: CurrentUser | None) -> tuple[Settings, set[str]]:
    """Engine settings for this caller, and the providers they'd search on the site's key (the shared quota).

    In accounts mode: the member's own key, else the admin's stored key, else env (decision 0003), and the sources
    the admin turned off on top of env's."""
    settings = get_settings()
    if settings.auth_mode != "accounts":
        return settings, set()
    own = request.app.state.accounts.key_values(user.id) if user and not user.local else {}
    admin: AdminService = request.app.state.admin
    site = admin.site_key_values()
    off = sorted(set(settings.disabled_providers) | set(admin.site().disabled_providers))
    merged = settings_with_keys(settings, own, site).model_copy(update={"disabled_providers": off})
    return merged, site_keyed_providers(settings, own, site)


def user_settings(request: Request, user: CurrentUser | None) -> Settings:
    return search_settings(request, user)[0]


def before_search(request: Request, user: CurrentUser) -> None:
    """The per-member search cap (admins are exempt) and the user list's "last seen"."""
    if get_settings().auth_mode != "accounts" or user.local:
        return
    svc: AccountService = request.app.state.accounts
    svc.touch_seen(user.id)
    if svc.is_admin(user.id):
        return
    per_hour = request.app.state.admin.site().searches_per_hour
    if not limiter.allow(f"search:{user.id}", per_hour, 3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"You've reached this hour's limit of {per_hour} searches. Try again in a little while.")


async def record_usage(request: Request, shared: set[str], statuses: list[ProviderStatus]) -> None:
    counts = {st.provider: (1, 0 if st.ok else 1) for st in statuses if st.provider in shared}
    if counts:
        await run_in_threadpool(request.app.state.admin.record_usage, counts)


# --------------------------------------------------------------------------------- meta
@app.get("/api/health")
async def health(request: Request) -> dict[str, Any]:
    s = get_settings()
    return {"ok": True, "version": __version__, "auth_mode": s.auth_mode,
            "signup_open": s.auth_mode == "accounts" and request.app.state.admin.site().signup_open}


@app.get("/api/me")
async def me(user: User) -> dict[str, Any]:
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "team_id": user.team_id,
            "teams": user.teams}


@app.get("/api/providers")
async def providers(request: Request, user: MaybeUser) -> list[dict[str, Any]]:
    s = user_settings(request, user)
    return [{"id": c.info.id, "name": c.info.name, "homepage": c.info.homepage,
             "media_types": sorted(m.value for m in c.info.media_types), "enabled": c.is_enabled(s),
             "key_setting": c.info.key_setting, "key_optional": c.info.key_optional,
             "key_signup_url": c.info.key_signup_url, "verified_live": c.info.verified_live,
             "notes": list(c.info.notes)} for c in PROVIDERS]


@app.get("/api/pd-cutoff")
async def pd_cutoff() -> dict[str, int]:
    return {"works": us_public_domain_cutoff(MediaType.IMAGE), "sound_recordings": us_public_domain_cutoff(MediaType.AUDIO)}


# --------------------------------------------------------------------------------- search
@app.post("/api/search", response_model=SearchResponse)
async def search(query: SearchQuery, user: User, request: Request) -> SearchResponse:
    before_search(request, user)
    settings, shared = search_settings(request, user)
    response = await engine(request).search(query, settings=settings)
    await record_usage(request, shared, response.providers)
    return response


@app.get("/api/search/stream")
async def search_stream(
    request: Request,
    user: User,
    q: str,
    media: Annotated[list[MediaType], Query()] = [MediaType.IMAGE],  # noqa: B006
    use: UseCase = UseCase.DEMO,
    max_tier: Tier = Tier.YELLOW,
    providers: Annotated[list[str] | None, Query()] = None,
    limit: int = 12,
    page: int = 1,
) -> StreamingResponse:
    """Server-sent events: one `batch` event per provider as it finishes, then `done`."""
    query = SearchQuery(q=q, media_types=media, use_case=use, max_tier=max_tier, providers=providers,
                        limit_per_provider=limit, page=page)
    before_search(request, user)
    settings, shared = search_settings(request, user)

    async def events() -> AsyncIterator[str]:
        statuses: list[ProviderStatus] = []
        try:
            async for batch in engine(request).search_stream(query, settings=settings):
                statuses.append(batch.status)
                if await request.is_disconnected():
                    break
                payload = {"status": batch.status.model_dump(mode="json"), "hidden": batch.hidden,
                           "results": [r.model_dump(mode="json") for r in batch.results]}
                yield f"event: batch\ndata: {json.dumps(payload)}\n\n"
            yield "event: done\ndata: {}\n\n"
        finally:
            await record_usage(request, shared, statuses)  # what was sent counts, even if the reader left

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/assets/{uid:path}")
async def get_asset(uid: str, user: User, request: Request, use: UseCase = UseCase.DEMO) -> dict[str, Any]:
    try:
        scored = await engine(request).get_asset(uid, use, settings=user_settings(request, user))
    except (LookupError, KeyError, NotImplementedError) as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"uid": scored.uid, "asset": scored.asset.model_dump(mode="json"),
            "verdict": scored.verdict.model_dump(mode="json"),
            "verdicts": {u.value: v.model_dump(mode="json") for u, v in evaluate_all(scored.asset).items()},
            "attribution_html": build_attribution_html(scored.asset)}


class LicenseCheck(BaseModel):
    license: str
    trust: Trust = Trust.UNKNOWN
    media_type: MediaType = MediaType.IMAGE
    year: int | None = None


@app.post("/api/license/check")
async def license_check(body: LicenseCheck) -> dict[str, Any]:
    is_url = body.license.startswith("http")
    lic = normalize_license(None if is_url else body.license, body.license if is_url else None)
    asset = Asset(provider="manual", source_id="check", title="(license check)", media_type=body.media_type,
                  license=lic, trust=body.trust, year=body.year)
    return {"recognized_as": lic.model_dump(mode="json"),
            "verdicts": {u.value: v.model_dump(mode="json") for u, v in evaluate_all(asset).items()}}


# --------------------------------------------------------------------------------- collections
class CollectionIn(BaseModel):
    name: str
    description: str | None = None
    use_case: UseCase = UseCase.DEMO


class CollectionItemIn(BaseModel):
    uid: str
    asset: Asset | None = None  # send the asset from search results to avoid a provider round-trip
    note: str | None = None


@app.get("/api/collections")
async def list_collections(user: User, request: Request) -> list[dict[str, Any]]:
    return store(request).list_collections(team_id=user.team_id)


@app.post("/api/collections", status_code=201)
async def create_collection(body: CollectionIn, user: User, request: Request) -> dict[str, Any]:
    return store(request).create_collection(body.name, description=body.description, use_case=body.use_case,
                                            team_id=user.team_id, user_id=user.id)


@app.get("/api/collections/{collection_id}")
async def get_collection(collection_id: str, user: User, request: Request) -> dict[str, Any]:
    coll = store(request).get_collection(collection_id, team_id=user.team_id)
    if not coll:
        raise HTTPException(404, "collection not found")
    return coll


@app.delete("/api/collections/{collection_id}", status_code=204)
async def delete_collection(collection_id: str, user: User, request: Request) -> None:
    if not store(request).delete_collection(collection_id, team_id=user.team_id):
        raise HTTPException(404, "collection not found")


@app.post("/api/collections/{collection_id}/items")
async def add_item(collection_id: str, body: CollectionItemIn, user: User, request: Request) -> dict[str, Any]:
    coll = store(request).get_collection(collection_id, team_id=user.team_id)
    if not coll:
        raise HTTPException(404, "collection not found")
    use = UseCase(coll["use_case"])
    if body.asset:
        from freestash.licenses import evaluate

        scored = ScoredAsset(uid=body.asset.uid, asset=body.asset, verdict=evaluate(body.asset, use))
    else:
        scored = await engine(request).get_asset(body.uid, use, settings=user_settings(request, user))
    return store(request).add_to_collection(collection_id, scored, note=body.note, user_id=user.id, team_id=user.team_id)


@app.delete("/api/collections/{collection_id}/items/{uid:path}", status_code=204)
async def remove_item(collection_id: str, uid: str, user: User, request: Request) -> None:
    if not store(request).remove_from_collection(collection_id, uid, team_id=user.team_id):
        raise HTTPException(404, "item not found")


# --------------------------------------------------------------------------------- ledger
class LedgerIn(BaseModel):
    uid: str
    use_case: UseCase
    project: str | None = None
    file_url: str | None = None  # the rendition the user is taking
    asset: Asset | None = None


@app.get("/api/ledger", response_model=list[LedgerEntry])
async def list_ledger(user: User, request: Request, project: str | None = None,
                      limit: int = Query(500, ge=1, le=500), before: str | None = None,
                      files: bool = False) -> list[LedgerEntry]:
    """One page, newest first. For the next page pass the last entry's id as `before`; a page shorter than
    `limit` is the last. `files=true` keeps only entries with a file (the Downloads page)."""
    try:
        return store(request).list_entries(team_id=user.team_id, project=project, limit=limit,
                                           before=before, files_only=files)
    except KeyError:
        raise HTTPException(400, "unknown ledger cursor") from None


@app.get("/api/ledger/projects")
async def ledger_projects(user: User, request: Request) -> list[str]:
    return store(request).projects(team_id=user.team_id)


@app.post("/api/ledger", response_model=LedgerEntry, status_code=201)
async def add_ledger(body: LedgerIn, user: User, request: Request) -> LedgerEntry:
    """Record that the team is taking an asset (the browser downloads straight from the source)."""
    from freestash.licenses import evaluate

    if body.asset:
        scored = ScoredAsset(uid=body.asset.uid, asset=body.asset, verdict=evaluate(body.asset, body.use_case))
    else:
        scored = await engine(request).get_asset(body.uid, body.use_case, settings=user_settings(request, user))
    if scored.verdict.tier == Tier.RED:
        raise HTTPException(409, {"message": "RED for this use case", "reasons": scored.verdict.reasons})
    return store(request).add_entry(entry_from_scored(scored, project=body.project, file_url=body.file_url,
                                                      user_id=user.id, team_id=user.team_id))


@app.get("/api/ledger/export")
async def export_ledger(user: User, request: Request, format: str = "md", project: str | None = None) -> PlainTextResponse:
    entries = store(request).list_entries(team_id=user.team_id, project=project, limit=100_000)
    if format == "csv":
        return PlainTextResponse(ledger_csv(entries), media_type="text/csv")
    if format == "html":
        return PlainTextResponse(credits_html(entries), media_type="text/html")
    return PlainTextResponse(attribution_markdown(entries, project), media_type="text/markdown")


# --------------------------------------------------------------------------------- web UI
def spa_file(dist: Path, path: str) -> Path:
    """A real file inside the web build, else index.html (the client routes the rest). Never a file outside `dist`:
    the path arrives percent-decoded, so `/..%2f..%2fpyproject.toml` read the server's own files (2026-11-01)."""
    root = dist.resolve()
    if not path or "\x00" in path:  # a decoded %00 makes resolve() raise on Linux: a 500 instead of the page
        return root / "index.html"
    target = (root / path).resolve()
    return target if target.is_file() and target.is_relative_to(root) else root / "index.html"


if WEB_DIST.exists():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    # A plain def: FastAPI runs it in the threadpool, so resolve()'s per-component lstat calls never block the loop.
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "not found")
        return FileResponse(spa_file(WEB_DIST, path))
