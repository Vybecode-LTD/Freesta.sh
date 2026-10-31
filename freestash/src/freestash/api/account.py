"""What follows the account between the website and the desktop app: preferences and provider keys."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from freestash.accounts import AccountError
from freestash.api.auth import User, accounts
from freestash.config import Settings, get_settings
from freestash.providers.keys import KEY_CATALOG, KEY_NAMES

router = APIRouter(tags=["account"])


class PrefsIn(BaseModel):
    data: dict[str, Any]


class KeysIn(BaseModel):
    values: dict[str, str | None]


def _accounts_only(user: User, settings: Settings) -> None:
    if user.local or settings.auth_mode != "accounts":
        raise HTTPException(404, "Account sync is off on this server (FREESTASH_AUTH_MODE=none).")


def _call(fn, *args):
    try:
        return fn(*args)
    except AccountError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.get("/api/keys/catalog")
async def key_catalog() -> list[dict[str, Any]]:
    """Where to get every provider key, step by step. Public: the sign-in screen links to it too."""
    return [k.as_json() for k in KEY_CATALOG]


@router.get("/api/me/settings")
async def get_prefs(user: User, request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _accounts_only(user, settings)
    return accounts(request).prefs(user.id)


@router.put("/api/me/settings")
async def put_prefs(body: PrefsIn, user: User, request: Request,
                    settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _accounts_only(user, settings)
    try:
        return accounts(request).set_prefs(user.id, body.data)
    except ValueError as exc:  # pydantic ValidationError
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/me/keys")
async def get_keys(user: User, request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _accounts_only(user, settings)
    return {"keys": accounts(request).keys_masked(user.id)}


@router.put("/api/me/keys")
async def put_keys(body: KeysIn, user: User, request: Request,
                   settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _accounts_only(user, settings)
    svc = accounts(request)
    _call(svc.set_keys, user.id, body.values)
    return {"keys": svc.keys_masked(user.id)}


@router.get("/api/me/keys/{name}")
async def reveal_key(name: str, user: User, request: Request,
                     settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _accounts_only(user, settings)
    if name not in KEY_NAMES:
        raise HTTPException(404, f"Unknown key name: {name}")
    return {"name": name, "value": _call(accounts(request).reveal, user.id, name)}
