"""The admin screen's API (contract admin-shared-keys). Admins only; off entirely without accounts."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from freestash.accounts import AccountError
from freestash.admin import AdminService
from freestash.api.auth import CurrentUser, User, accounts
from freestash.config import Settings, get_settings
from freestash.http import HttpClient
from freestash.models import CuratedPack, MediaType, SearchQuery
from freestash.providers import provider_class
from freestash.providers.keys import key_spec, settings_with_keys

router = APIRouter(prefix="/api/admin", tags=["admin"])


def admin_service(request: Request) -> AdminService:
    return request.app.state.admin


async def require_admin(user: User, request: Request, settings: Settings = Depends(get_settings)) -> CurrentUser:
    if settings.auth_mode != "accounts" or user.local:
        raise HTTPException(404, "There's no admin screen without accounts (FREESTASH_AUTH_MODE=none).")
    if not accounts(request).is_admin(user.id):
        raise HTTPException(403, "Admins only.")
    return user


Admin = Annotated[CurrentUser, Depends(require_admin)]


async def _call(fn, *args, **kwargs):
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except AccountError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    except ValidationError as exc:
        raise HTTPException(422, exc.errors(include_url=False, include_context=False)) from exc


# --------------------------------------------------------------------------------- keys
class KeysIn(BaseModel):
    values: dict[str, str | None]


@router.get("/keys")
async def get_keys(admin: Admin, request: Request) -> list[dict[str, Any]]:
    return await _call(admin_service(request).keys_report)


@router.put("/keys")
async def put_keys(body: KeysIn, admin: Admin, request: Request) -> list[dict[str, Any]]:
    svc = admin_service(request)
    await _call(svc.set_keys, admin.id, body.values)
    return await _call(svc.keys_report)


@router.post("/keys/{name}/test")
async def test_key(name: str, admin: Admin, request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """A one-result search on the site's key alone (a member's own key never takes part)."""
    spec = key_spec(name)
    if spec is None:
        raise HTTPException(404, f"Unknown key name: {name}")
    svc = admin_service(request)
    if not svc.has_site_key(name):
        raise HTTPException(400, f"There's no {spec.label} for {spec.provider_name} to test yet.")
    cls = provider_class(spec.provider)
    assert cls is not None
    run_settings = settings_with_keys(settings, {}, svc.site_key_values())
    media = sorted(cls.info.media_types, key=lambda m: m != MediaType.IMAGE)[:1]  # images when it has them
    # A packs-only source (GitHub) is only called for packs: without them the test would pass without calling it.
    query = SearchQuery(q="landscape", media_types=media, providers=[spec.provider], limit_per_provider=1,
                        packs=cls.info.packs_only)
    started = time.perf_counter()
    http = HttpClient(run_settings)  # a fresh, empty cache: an hour-old success must not pass a key revoked since
    try:
        status, _ = await request.app.state.engine.run_provider(cls, query, run_settings, http)
    finally:
        await http.aclose()
    error = None if status.ok else (status.error or "failed")
    await run_in_threadpool(svc.record_test, name, error)
    return {"ok": status.ok, "elapsed_ms": int((time.perf_counter() - started) * 1000), "error": error}


# --------------------------------------------------------------------------------- site settings
@router.get("/settings")
async def get_site_settings(admin: Admin, request: Request) -> dict[str, Any]:
    return admin_service(request).site().model_dump()


@router.put("/settings")
async def put_site_settings(body: dict[str, Any], admin: Admin, request: Request) -> dict[str, Any]:
    return (await _call(admin_service(request).update_site, admin.id, body)).model_dump()


# --------------------------------------------------------------------------------- curated packs
class CuratedImportIn(BaseModel):
    packs: list[CuratedPack] = Field(max_length=500)


@router.get("/curated")
async def get_curated(admin: Admin, request: Request) -> list[CuratedPack]:
    return await _call(admin_service(request).curated)


@router.post("/curated", status_code=201)
async def add_curated(body: CuratedPack, admin: Admin, request: Request) -> CuratedPack:
    return await _call(admin_service(request).add_curated, admin.id, body)


def _curated_changed(request: Request) -> None:
    """The engine's recent results would keep serving a pack's old license to the drawer and the ledger (PR #9
    review). Called here, on the event loop, where the cache is written, not from the worker thread of the write."""
    request.app.state.engine.recent.forget_provider("curated")


@router.put("/curated/{pack_id}")
async def put_curated(pack_id: str, body: CuratedPack, admin: Admin, request: Request) -> CuratedPack:
    pack = await _call(admin_service(request).update_curated, admin.id, pack_id, body)
    _curated_changed(request)
    return pack


@router.delete("/curated/{pack_id}", status_code=204)
async def delete_curated(pack_id: str, admin: Admin, request: Request) -> None:
    await _call(admin_service(request).delete_curated, admin.id, pack_id)
    _curated_changed(request)


@router.post("/curated/import")
async def import_curated(body: CuratedImportIn, admin: Admin, request: Request) -> dict[str, int]:
    counts = await _call(admin_service(request).import_curated, admin.id, body.packs)
    _curated_changed(request)
    return counts


# --------------------------------------------------------------------------------- usage, users, audit
@router.get("/usage")
async def get_usage(admin: Admin, request: Request) -> list[dict[str, Any]]:
    return await _call(admin_service(request).usage_report)


@router.get("/users")
async def get_users(admin: Admin, request: Request, q: str | None = None) -> list[dict[str, Any]]:
    return await _call(accounts(request).list_users, q)


class UserFlagsIn(BaseModel):
    is_admin: bool | None = None
    disabled: bool | None = None


@router.patch("/users/{user_id}")
async def patch_user(user_id: str, body: UserFlagsIn, admin: Admin, request: Request) -> dict[str, Any]:
    svc = accounts(request)
    if user_id == admin.id:
        raise HTTPException(400, "You can't change your own admin or disabled flags. Ask another admin.")
    target = await _call(svc.user_admin_row, user_id)
    if target is None:
        raise HTTPException(404, "No such user.")
    changes = body.model_dump(exclude_none=True)
    if changes:
        await _call(svc.set_flags, user_id, **changes)
        await _call(admin_service(request).audit, admin.id, "user.update", target["email"], changes)
    return await _call(svc.user_admin_row, user_id)


@router.get("/audit")
async def get_audit(admin: Admin, request: Request, before: datetime | None = None) -> list[dict[str, Any]]:
    return await _call(admin_service(request).audit_log, before)
