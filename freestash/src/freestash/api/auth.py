"""Auth for the web API.

AUTH_MODE=none      single local user, no team (CLI-equivalent; for running on your own machine)
AUTH_MODE=supabase  verify the Supabase access token sent as `Authorization: Bearer <jwt>`
                    * new projects (asymmetric signing keys): verified against the project's JWKS
                    * legacy projects: set SUPABASE_JWT_SECRET for HS256
                    Team = `X-Freestash-Team` header if the user belongs to it, else their first membership.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException, Request, status

from freestash.config import Settings, get_settings

LOCAL_USER_ID = "00000000-0000-0000-0000-000000000001"  # AUTH_MODE=none


@dataclass
class CurrentUser:
    id: str
    email: str | None
    team_id: str | None
    teams: list[str]


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True)


def _decode(token: str, settings: Settings) -> dict:
    if settings.supabase_jwt_secret:
        return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated")
    if not settings.supabase_url:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "AUTH_MODE=supabase needs SUPABASE_URL")
    key = _jwks_client(f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json").get_signing_key_from_jwt(token)
    return jwt.decode(token, key.key, algorithms=["RS256", "ES256"], audience="authenticated")


async def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_freestash_team: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if settings.auth_mode == "none":
        return CurrentUser(id=LOCAL_USER_ID, email=None, team_id=None, teams=[])

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = _decode(authorization.split(" ", 1)[1], settings)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {exc}") from exc

    store = request.app.state.store
    teams = store.team_ids_for(claims["sub"])
    if not teams:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "you're not in a Freestash team yet; ask an admin to add you")
    team = x_freestash_team if x_freestash_team in teams else teams[0]
    return CurrentUser(id=claims["sub"], email=claims.get("email"), team_id=team, teams=teams)
