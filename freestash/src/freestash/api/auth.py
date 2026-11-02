"""Auth for the web API.

AUTH_MODE=none      single local user, no team: the CLI-equivalent, and what the desktop's local engine runs
AUTH_MODE=accounts  open sign-up on this server. One account works on the website and the desktop app:
                    the desktop sends `Authorization: Bearer <token>` from /api/auth/login or /register; the website
                    asks for an HttpOnly cookie instead (`X-Freestash-Session: cookie`) and never sees the token.
                    Cookie-signed writes must come from the site itself (Origin check; contract web-cookie-session).
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from freestash.accounts import AccountError, AccountService, UserRow
from freestash.config import Settings, get_settings
from freestash.mailer import send_email
from freestash.ratelimit import RateLimiter

LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"  # AUTH_MODE=none

log = logging.getLogger("freestash.auth")

limiter = RateLimiter()

SESSION_COOKIE = "freestash_session"
_LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


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


def _wants_cookie(request: Request) -> bool:
    return request.headers.get("x-freestash-session", "").lower() == "cookie"


def _is_loopback(request: Request) -> bool:
    return (urlsplit(f"//{request.headers.get('host', '')}").hostname or "") in _LOOPBACK


def check_origin(request: Request, settings: Settings) -> None:
    """CSRF guard for cookie-signed writes: the Origin (else the Referer) must be this site.

    "This site" is the Host the request arrived on, the public URL, or a configured CORS origin (the Vite dev server).
    Browsers send Origin on every cross-site write, and SameSite=Lax already withholds the cookie from most of them;
    this catches the rest (a same-site subdomain, an old browser). A missing or "null" Origin is refused.
    """
    source = request.headers.get("origin") or request.headers.get("referer") or ""
    netloc = urlsplit(source).netloc.lower()
    allowed = {request.headers.get("host", "").lower(),
               *(urlsplit(u).netloc.lower() for u in (settings.public_url, *settings.cors_origins))} - {""}
    if not netloc or netloc not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cross-site request refused.")


def set_session_cookie(response: Response, request: Request, settings: Settings, token: str) -> None:
    """Secure everywhere but loopback: uvicorn behind Railway's edge sees plain http, so the scheme can't decide."""
    response.set_cookie(SESSION_COOKIE, token, max_age=settings.token_days * 86400, path="/api", httponly=True,
                        samesite="lax", secure=not _is_loopback(request))


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/api", httponly=True, samesite="lax", secure=not _is_loopback(request))


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
    if not token and (token := request.cookies.get(SESSION_COOKIE)) and request.method not in _SAFE_METHODS:
        check_origin(request, settings)  # a cross-site request can carry the cookie, never a bearer header
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    return _resolve(request, token, x_freestash_team)


async def optional_user(
    request: Request,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> CurrentUser | None:
    """The caller if they sent a valid token or session cookie, else None. For public endpoints that personalize."""
    if settings.auth_mode != "accounts":
        return CurrentUser(id=LOCAL_USER_ID, email=None, team_id=None, local=True)
    bearer = _bearer(authorization)
    token = bearer or request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        if not bearer and request.method not in _SAFE_METHODS:
            check_origin(request, settings)
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


def user_out(u: UserRow, is_admin: bool = False) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name,
            "created_at": u.created_at.isoformat() if u.created_at else None, "is_admin": is_admin}


def _user_out(request: Request, u: UserRow) -> dict:
    return user_out(u, accounts(request).is_admin(u.id, u.email))


def _auth_response(svc: AccountService, u: UserRow, request: Request, response: Response, settings: Settings) -> dict:
    """The desktop gets the token in the body; the website gets it only as an HttpOnly cookie."""
    token = svc.issue_token(u)
    if _wants_cookie(request):
        set_session_cookie(response, request, settings, token)
        return {"token_type": "cookie", "user": _user_out(request, u)}
    return {"access_token": token, "token_type": "bearer", "user": _user_out(request, u)}


def _check_cookie_request(request: Request, settings: Settings) -> None:
    """A cross-site page must not sign a browser into an account (login CSRF)."""
    if _wants_cookie(request):
        check_origin(request, settings)


def _require_accounts(settings: Settings) -> None:
    if settings.auth_mode != "accounts":
        raise HTTPException(404, "Accounts are off on this server (FREESTASH_AUTH_MODE=none).")


def _limit(key: str, limit: int, window: float) -> None:
    if not limiter.allow(key, limit, window):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Wait a few minutes and try again.")


def _ip(request: Request, settings: Settings) -> str:
    """The real client address behind Railway's edge (the peer address is the proxy, shared by everyone).

    The leftmost X-Forwarded-For (Railway's edge overwrites the header rather than appending to a client-supplied
    one, proven on production 2026-11-01), then the peer. CF-Connecting-IP comes first only with
    FREESTASH_TRUST_CF_CONNECTING_IP: without Cloudflare in front, any client can send it and dodge the limits.
    """
    cf = request.headers.get("cf-connecting-ip") if settings.trust_cf_connecting_ip else None
    for candidate in (cf, (request.headers.get("x-forwarded-for") or "").split(",")[0]):
        candidate = (candidate or "").strip()
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return request.client.host if request.client else "unknown"


async def _call(fn, *args):
    """Run an account call in the thread pool: bcrypt takes ~250 ms, and on the event loop it would stall
    every other request while it hashes."""
    try:
        return await run_in_threadpool(fn, *args)
    except AccountError as exc:
        raise HTTPException(exc.status, exc.message) from exc


async def _send_quietly(settings: Settings, to: str, subject: str, text: str) -> None:
    """Background send for /forgot: a mailer failure must not show up in the response, or only real accounts
    would see it. The log names the error type only, never the address or the link."""
    try:
        await send_email(settings, to, subject, text)
    except Exception as exc:  # noqa: BLE001 - anything from the mail provider
        log.error("Reset email failed (%s). Subject: %s", type(exc).__name__, subject)


@router.post("/register", status_code=201)
async def register(body: RegisterIn, request: Request, response: Response,
                   settings: Settings = Depends(get_settings)) -> dict:
    _require_accounts(settings)
    _check_cookie_request(request, settings)
    _limit(f"register:{_ip(request, settings)}", 5, 3600)
    svc = accounts(request)
    user = await _call(svc.register, body.email, body.password, body.display_name)
    return _auth_response(svc, user, request, response, settings)


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, settings: Settings = Depends(get_settings)) -> dict:
    _require_accounts(settings)
    _check_cookie_request(request, settings)
    _limit(f"login-ip:{_ip(request, settings)}", 30, 300)
    _limit(f"login:{_ip(request, settings)}:{body.email.strip().lower()}", 8, 300)
    svc = accounts(request)
    return _auth_response(svc, await _call(svc.authenticate, body.email, body.password), request, response, settings)


@router.get("/me")
async def me(user: User, request: Request) -> dict:
    if user.local:
        return {"id": user.id, "email": None, "display_name": "This computer", "created_at": None, "is_admin": False}
    row = accounts(request).get(user.id)
    assert row is not None
    return _user_out(request, row)


@router.patch("/me")
async def update_me(body: ProfileIn, user: User, request: Request, settings: Settings = Depends(get_settings)) -> dict:
    _require_accounts(settings)
    return _user_out(request, await _call(accounts(request).update_profile, user.id, body.display_name))


@router.post("/change-password")
async def change_password(body: ChangePasswordIn, user: User, request: Request, response: Response,
                          settings: Settings = Depends(get_settings)) -> dict:
    _require_accounts(settings)
    _check_cookie_request(request, settings)
    _limit(f"change-password:{user.id}", 8, 300)
    svc = accounts(request)
    changed = await _call(svc.change_password, user.id, body.current_password, body.new_password)
    return _auth_response(svc, changed, request, response, settings)


@router.post("/logout-all", status_code=204)
async def logout_all(user: User, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    _require_accounts(settings)
    accounts(request).sign_out_everywhere(user.id)
    response = Response(status_code=204)
    clear_session_cookie(response, request)
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request, settings: Settings = Depends(get_settings)) -> Response:
    """Signs this browser out by clearing its cookie. The token stays valid until it expires or "Sign out
    everywhere" revokes it: there's no server-side session to end (contract web-cookie-session §6)."""
    if request.cookies.get(SESSION_COOKIE):
        check_origin(request, settings)
    response = Response(status_code=204)
    clear_session_cookie(response, request)
    return response


@router.post("/forgot")
async def forgot(body: ForgotIn, request: Request, background: BackgroundTasks,
                 settings: Settings = Depends(get_settings)) -> dict:
    """Always answers the same way and as fast, whether or not the email has an account (no account
    enumeration): the email goes out in the background, after the response."""
    _require_accounts(settings)
    _limit(f"forgot-ip:{_ip(request, settings)}", 10, 3600)
    _limit(f"forgot:{body.email.strip().lower()}", 3, 3600)
    started = accounts(request).start_reset(body.email)
    if started:
        user, token = started
        link = f"{settings.public_url.rstrip('/')}/#/reset?token={token}"
        background.add_task(_send_quietly, settings, user.email, "Reset your Freesta.sh password",
                            "Someone asked to reset the password for your Freesta.sh account.\n\n"
                            f"Choose a new one here (the link works for one hour, once):\n{link}\n\n"
                            "If that wasn't you, ignore this email; your password hasn't changed.")
    return {"ok": True}


@router.post("/reset", status_code=204)
async def reset(body: ResetIn, request: Request, settings: Settings = Depends(get_settings)) -> Response:
    _require_accounts(settings)
    _limit(f"reset:{_ip(request, settings)}", 10, 3600)
    await _call(accounts(request).finish_reset, body.token, body.new_password)
    return Response(status_code=204)
