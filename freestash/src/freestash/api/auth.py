"""Auth for the web API.

AUTH_MODE=none      single local user, no team: the CLI-equivalent, and what the desktop's local engine runs
AUTH_MODE=accounts  open sign-up on this server; clients send `Authorization: Bearer <token>` from
                    /api/auth/login or /api/auth/register. One account works on the website and the desktop app.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel

from freestash.accounts import AccountError, AccountService, UserRow
from freestash.config import Settings, get_settings
from freestash.mailer import send_email
from freestash.ratelimit import RateLimiter

LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"  # AUTH_MODE=none

limiter = RateLimiter()


@dataclass
class CurrentUser:
    id: str
    email: str | None
    team_id: str | None
    teams: list[str] = field(default_factory=list)
    display_name: str | None = None
    local: bool = False  # AUTH_MODE=none


def accounts(request: Request) -> AccountService:
    return request.app.state.accounts


def _bearer(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip() or None
    return None


def _resolve(request: Request, token: str, team_header: str | None) -> CurrentUser:
    try:
        user = accounts(request).user_for_token(token)
    except AccountError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    teams = request.app.state.store.team_ids_for(user.id)
    team = team_header if team_header in teams else (teams[0] if teams else None)
    return CurrentUser(id=user.id, email=user.email, team_id=team, teams=teams, display_name=user.display_name)


async def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_freestash_team: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if settings.auth_mode != "accounts":
        return CurrentUser(id=LOCAL_USER_ID, email=None, team_id=None, local=True)
    token = _bearer(authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    return _resolve(request, token, x_freestash_team)


async def optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> CurrentUser | None:
    """The caller if they sent a valid token, else None. For public endpoints that personalize."""
    if settings.auth_mode != "accounts":
        return CurrentUser(id=LOCAL_USER_ID, email=None, team_id=None, local=True)
    token = _bearer(authorization)
    if not token:
        return None
    try:
        return _resolve(request, token, None)
    except HTTPException:
        return None


User = Annotated[CurrentUser, Depends(current_user)]


# --------------------------------------------------------------------------------- routes
router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: str
    password: str
    display_name: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class ProfileIn(BaseModel):
    display_name: str | None = None


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class ForgotIn(BaseModel):
    email: str


class ResetIn(BaseModel):
    token: str
    new_password: str


def user_out(u: UserRow) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name,
            "created_at": u.created_at.isoformat() if u.created_at else None}


def _auth_response(svc: AccountService, u: UserRow) -> dict:
    return {"access_token": svc.issue_token(u), "token_type": "bearer", "user": user_out(u)}


def _require_accounts(settings: Settings) -> None:
    if settings.auth_mode != "accounts":
        raise HTTPException(404, "Accounts are off on this server (FREESTASH_AUTH_MODE=none).")


def _limit(key: str, limit: int, window: float) -> None:
    if not limiter.allow(key, limit, window):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Wait a few minutes and try again.")


def _ip(request: Request) -> str:
    """The real client address behind Railway's edge (the peer address is the proxy, shared by everyone).

    CF-Connecting-IP when Cloudflare fronts the domain, then the leftmost X-Forwarded-For (Railway's edge
    overwrites the header rather than appending to a client-supplied one), then the peer.
    """
    for candidate in (request.headers.get("cf-connecting-ip"),
                      (request.headers.get("x-forwarded-for") or "").split(",")[0]):
        candidate = (candidate or "").strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return request.client.host if request.client else "unknown"


def _call(fn, *args):
    try:
        return fn(*args)
    except AccountError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@router.post("/register", status_code=201)
async def register(body: RegisterIn, request: Request, settings: Settings = Depends(get_settings)) -> dict:
    _require_accounts(settings)
    _limit(f"register:{_ip(request)}", 5, 3600)
    svc = accounts(request)
    return _auth_response(svc, _call(svc.register, body.email, body.password, body.display_name))


@router.post("/login")
async def login(body: LoginIn, request: Request, settings: Settings = Depends(get_settings)) -> dict:
    _require_accounts(settings)
    _limit(f"login-ip:{_ip(request)}", 30, 300)
    _limit(f"login:{_ip(request)}:{body.email.strip().lower()}", 8, 300)
    svc = accounts(request)
    return _auth_response(svc, _call(svc.authenticate, body.email, body.password))


@router.get("/me")
async def me(user: User, request: Request) -> dict:
    if user.local:
        return {"id": user.id, "email": None, "display_name": "This computer", "created_at": None}
    row = accounts(request).get(user.id)
    assert row is not None
    return user_out(row)


@router.patch("/me")
async def update_me(body: ProfileIn, user: User, request: Request, settings: Settings = Depends(get_settings)) -> dict:
    _require_accounts(settings)
    return user_out(accounts(request).update_profile(user.id, body.display_name))


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, user: User, request: Request,
                          settings: Settings = Depends(get_settings)) -> dict:
    _require_accounts(settings)
    _limit(f"change-password:{user.id}", 8, 300)
    svc = accounts(request)
    return _auth_response(svc, _call(svc.change_password, user.id, body.current_password, body.new_password))


@router.post("/logout-all", status_code=204)
async def logout_all(user: User, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    _require_accounts(settings)
    accounts(request).sign_out_everywhere(user.id)
    return Response(status_code=204)


@router.post("/forgot")
async def forgot(body: ForgotIn, request: Request, settings: Settings = Depends(get_settings)) -> dict:
    """Always answers the same way, whether or not the email has an account (no account enumeration)."""
    _require_accounts(settings)
    _limit(f"forgot-ip:{_ip(request)}", 10, 3600)
    _limit(f"forgot:{body.email.strip().lower()}", 3, 3600)
    started = accounts(request).start_reset(body.email)
    if started:
        user, token = started
        link = f"{settings.public_url.rstrip('/')}/#/reset?token={token}"
        await send_email(settings, user.email, "Reset your Freesta.sh password",
                         "Someone asked to reset the password for your Freesta.sh account.\n\n"
                         f"Choose a new one here (the link works for one hour, once):\n{link}\n\n"
                         "If that wasn't you, ignore this email; your password hasn't changed.")
    return {"ok": True}


@router.post("/reset", status_code=204)
async def reset(body: ResetIn, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    _require_accounts(settings)
    _limit(f"reset:{_ip(request)}", 10, 3600)
    _call(accounts(request).finish_reset, body.token, body.new_password)
    return Response(status_code=204)
