"""What follows the account between the website and the desktop app: preferences and provider keys."""

from __future__ import annotations

import secrets
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from freestash.accounts import AccountError
from freestash.api.auth import User, _limit, accounts
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


class OpenverseRegisterIn(BaseModel):
    email: str | None = None  # defaults to the account's email


OPENVERSE_REGISTER = "https://api.openverse.org/v1/auth_tokens/register/"


@router.post("/api/keys/openverse/register")
async def openverse_register(body: OpenverseRegisterIn, user: User, request: Request,
                             settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Openverse has no sign-up page, only this API. Register on the user's behalf and keep the result.

    Openverse emails a verification link to the address; until it's clicked the credentials work at
    anonymous limits. In accounts mode the pair is saved to the account; the response carries it either way
    (the desktop's local engine stores it on the machine).
    """
    hosted = not user.local and settings.auth_mode == "accounts"
    if hosted:
        # Sign-up is open, so a typed address can't be trusted: it would make Openverse mail anyone, on repeat.
        _limit(f"openverse:{user.id}", 3, 3600)
        email = (user.email or "").strip()
    else:
        email = (body.email or user.email or "").strip()
    if "@" not in email:
        raise HTTPException(400, "Enter the email address Openverse should send its verification link to.")
    payload = {"name": f"freesta.sh-{secrets.token_hex(4)}",
               "description": "Freesta.sh: search for public domain and openly licensed media.", "email": email}
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": settings.full_user_agent}) as client:
        r = await client.post(OPENVERSE_REGISTER, json=payload)
    if r.status_code >= 400:
        raise HTTPException(502, f"Openverse refused the registration ({r.status_code}): {r.text[:200]}")
    data = r.json()
    values = {"OPENVERSE_CLIENT_ID": data.get("client_id"), "OPENVERSE_CLIENT_SECRET": data.get("client_secret")}
    if not all(values.values()):
        raise HTTPException(502, "Openverse answered without credentials. Try again in a minute.")
    if hosted:
        _call(accounts(request).set_keys, user.id, values)
    return {"values": values, "email": email,
            "next": f"Click the verification link Openverse sent to {email}; until then searches use anonymous limits."}


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


def _with_site(request: Request, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each row says whether Freesta.sh has its own key for it (stored by an admin, or env): decision 0003."""
    admin = request.app.state.admin
    return [{**row, "site": admin.has_site_key(row["name"])} for row in rows]


@router.get("/api/me/keys")
async def get_keys(user: User, request: Request, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _accounts_only(user, settings)
    return {"keys": _with_site(request, accounts(request).keys_masked(user.id))}


@router.put("/api/me/keys")
async def put_keys(body: KeysIn, user: User, request: Request,
                   settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _accounts_only(user, settings)
    svc = accounts(request)
    _call(svc.set_keys, user.id, body.values)
    return {"keys": _with_site(request, svc.keys_masked(user.id))}


@router.get("/api/me/keys/{name}")
async def reveal_key(name: str, user: User, request: Request,
                     settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    _accounts_only(user, settings)
    if name not in KEY_NAMES:
        raise HTTPException(404, f"Unknown key name: {name}")
    return {"name": name, "value": _call(accounts(request).reveal, user.id, name)}
