"""Accounts: users, passwords, session tokens, encrypted provider keys and synced preferences.

App-level auth on the API's own database (Railway Postgres in production, SQLite locally), the model
Seeq'r uses: bcrypt password hashes and HS256 JWTs. Each user carries a `token_version`; tokens embed it,
so a password change or "sign out everywhere" kills every token issued before it.

Every account gets a personal team on sign-up, so the existing team-scoped collections and ledger work
unchanged and a shared team can be added later without a data migration.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from freestash.config import Settings
from freestash.models import MediaType, Tier, UseCase
from freestash.providers.keys import KEY_CATALOG, KEY_NAMES
from freestash.store import UUID, Base, JSONType, Store, TeamMemberRow, TeamRow, _now, _uuid

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt()).decode()
RESET_TTL = timedelta(hours=1)


class UserRow(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserStatusRow(Base):
    """Admin and moderation state, kept off `users` so adding it needed no migration (contract admin-shared-keys)."""

    __tablename__ = "user_status"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


SEEN_EVERY = timedelta(minutes=10)  # last_seen_at is written at most this often per user


class UserSecretRow(Base):
    __tablename__ = "user_secrets"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(String(8))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserPrefsRow(Base):
    __tablename__ = "user_prefs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PasswordResetRow(Base):
    __tablename__ = "password_resets"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserPrefs(BaseModel):
    """Preferences that follow the account between the website and the desktop app."""

    model_config = ConfigDict(extra="ignore")
    default_use_case: UseCase = UseCase.DEMO
    default_max_tier: Tier = Tier.YELLOW
    default_media: list[MediaType] = Field(default_factory=lambda: [MediaType.IMAGE], min_length=1)
    results_per_source: int = Field(12, ge=1, le=50)
    theme: Literal["dark", "light"] = "dark"
    accent: Literal["sodium", "iris", "teal", "cobalt"] = "sodium"


class AccountError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite returns naive datetimes


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _display_name(raw: str | None) -> str | None:
    """Trimmed, or None. Longer than the column (String(120)) is a 400: Postgres would refuse it with a 500."""
    name = (raw or "").strip() or None
    if name and len(name) > 120:
        raise AccountError(400, "Keep your display name to 120 characters or fewer.")
    return name


def check_password_rules(password: str) -> None:
    if len(password) < 8:
        raise AccountError(400, "Use at least 8 characters for your password.")
    if len(password.encode()) > 72:  # bcrypt ignores everything past 72 bytes
        raise AccountError(400, "Use at most 72 characters for your password.")


class AccountService:
    def __init__(self, store: Store, settings: Settings, signup_open: Callable[[], bool] | None = None) -> None:
        self.store = store
        self.settings = settings
        self._signup_open = signup_open or (lambda: settings.signup_open)  # the admin's switch (admin.py)
        self._seen: dict[str, datetime] = {}
        if settings.auth_mode == "accounts" and (not settings.secret_key or len(settings.secret_key) < 32):
            raise RuntimeError("FREESTASH_SECRET_KEY must be set (32+ characters) when FREESTASH_AUTH_MODE=accounts")
        if settings.auth_mode == "accounts" and not settings.database_configured:
            # The fallback SQLite file lives inside the container, and every deploy wipes it (production, 2026-11-01).
            raise RuntimeError("DATABASE_URL (or FREESTASH_DATABASE_URL) must be set when FREESTASH_AUTH_MODE=accounts")
        self._fernet = Fernet(settings.secrets_key) if settings.secrets_key else None

    # ------------------------------------------------------------------ users + tokens
    def issue_token(self, user: UserRow) -> str:
        now = datetime.now(UTC)
        claims = {"sub": user.id, "ver": user.token_version, "iat": now, "exp": now + timedelta(days=self.settings.token_days)}
        return jwt.encode(claims, self.settings.secret_key or "", algorithm="HS256")

    def user_for_token(self, token: str) -> UserRow:
        try:
            claims = jwt.decode(token, self.settings.secret_key or "", algorithms=["HS256"],
                                options={"require": ["sub", "exp", "ver"]})
        except jwt.PyJWTError as exc:
            raise AccountError(401, "Your session has expired. Sign in again.") from exc
        user = self.get(str(claims["sub"]))
        if user is None or user.token_version != claims["ver"]:
            raise AccountError(401, "Your session has expired. Sign in again.")
        self._check_active(user.id)
        return user

    def get(self, user_id: str) -> UserRow | None:
        with self.store.session() as s:
            return s.get(UserRow, user_id)

    def register(self, email: str, password: str, display_name: str | None = None) -> UserRow:
        if not self._signup_open():
            raise AccountError(403, "Sign-up is closed on this server.")
        email = normalize_email(email)
        if len(email) > 320 or not _EMAIL.match(email):
            raise AccountError(400, "Enter a valid email address.")
        check_password_rules(password)
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        with self.store.session() as s, s.begin():
            if s.scalar(select(UserRow.id).where(UserRow.email == email)):
                raise AccountError(409, "An account with that email already exists. Sign in instead.")
            user = UserRow(email=email, password_hash=hashed, display_name=_display_name(display_name))
            s.add(user)
            s.flush()
            team = TeamRow(name=f"{(user.display_name or email.split('@')[0])[:180]}'s library")  # String(200)
            s.add(team)
            s.flush()
            s.add(TeamMemberRow(team_id=team.id, user_id=user.id, role="owner"))
        return user

    def authenticate(self, email: str, password: str) -> UserRow:
        with self.store.session() as s:
            user = s.scalar(select(UserRow).where(UserRow.email == normalize_email(email)))
        stored = user.password_hash if user else _DUMMY_HASH  # same bcrypt cost either way: no user enumeration
        ok = bcrypt.checkpw(password.encode()[:72], stored.encode())
        if user is None or not ok:
            raise AccountError(401, "That email and password don't match an account.")
        self._check_active(user.id)  # only after the password: a wrong one mustn't learn the account is disabled
        return user

    # ------------------------------------------------------------------ admin + moderation state
    def _check_active(self, user_id: str) -> None:
        with self.store.session() as s:
            status = s.get(UserStatusRow, user_id)
        if status and status.disabled:
            raise AccountError(403, "This account is disabled.")

    def is_admin(self, user_id: str, email: str | None) -> bool:
        if email and email.strip().lower() in self.settings.admin_email_set:
            return True
        with self.store.session() as s:
            status = s.get(UserStatusRow, user_id)
        return bool(status and status.is_admin)

    def is_bootstrap_admin(self, email: str | None) -> bool:
        return bool(email) and email.strip().lower() in self.settings.admin_email_set

    def set_flags(self, user_id: str, *, is_admin: bool | None = None, disabled: bool | None = None) -> None:
        with self.store.session() as s, s.begin():
            status = s.get(UserStatusRow, user_id) or UserStatusRow(user_id=user_id, is_admin=False, disabled=False)
            s.add(status)
            if is_admin is not None:
                status.is_admin = is_admin
            if disabled is not None:
                status.disabled = disabled
            status.updated_at = _now()

    def touch_seen(self, user_id: str) -> None:
        """Record activity for the admin's user list, at most once per SEEN_EVERY per user."""
        now = _now()
        if (last := self._seen.get(user_id)) and now - last < SEEN_EVERY:
            return
        self._seen[user_id] = now
        with self.store.session() as s, s.begin():
            status = s.get(UserStatusRow, user_id) or UserStatusRow(user_id=user_id, is_admin=False, disabled=False)
            s.add(status)
            status.last_seen_at = now

    def list_users(self, q: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        stmt = (select(UserRow, UserStatusRow).outerjoin(UserStatusRow, UserStatusRow.user_id == UserRow.id)
                .order_by(UserRow.created_at.desc()).limit(limit))
        if q and q.strip():
            like = f"%{q.strip().lower()}%"
            stmt = stmt.where(or_(UserRow.email.like(like), UserRow.display_name.ilike(like)))
        with self.store.session() as s:
            rows = s.execute(stmt).all()
        return [self.user_admin_view(u, st) for u, st in rows]

    def user_admin_view(self, u: UserRow, st: UserStatusRow | None) -> dict[str, Any]:
        bootstrap = self.is_bootstrap_admin(u.email)
        return {"id": u.id, "email": u.email, "display_name": u.display_name,
                "created_at": _as_utc(u.created_at).isoformat() if u.created_at else None,
                "last_seen_at": _as_utc(st.last_seen_at).isoformat() if st and st.last_seen_at else None,
                "is_admin": bootstrap or bool(st and st.is_admin), "bootstrap": bootstrap,
                "disabled": bool(st and st.disabled)}

    def user_admin_row(self, user_id: str) -> dict[str, Any] | None:
        with self.store.session() as s:
            user = s.get(UserRow, user_id)
            status = s.get(UserStatusRow, user_id)
        return self.user_admin_view(user, status) if user else None

    def update_profile(self, user_id: str, display_name: str | None) -> UserRow:
        with self.store.session() as s, s.begin():
            user = s.get(UserRow, user_id)
            assert user is not None
            user.display_name = _display_name(display_name)
        return user

    def change_password(self, user_id: str, current: str, new: str) -> UserRow:
        user = self.get(user_id)
        if user is None or not bcrypt.checkpw(current.encode()[:72], user.password_hash.encode()):
            raise AccountError(403, "Your current password is incorrect.")
        check_password_rules(new)
        return self._set_password(user_id, new)

    def _set_password(self, user_id: str, new: str) -> UserRow:
        with self.store.session() as s, s.begin():
            user = s.get(UserRow, user_id)
            assert user is not None
            user.password_hash = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
            user.token_version += 1
        return user

    def sign_out_everywhere(self, user_id: str) -> None:
        with self.store.session() as s, s.begin():
            user = s.get(UserRow, user_id)
            if user:
                user.token_version += 1

    # ------------------------------------------------------------------ password reset
    def start_reset(self, email: str) -> tuple[UserRow, str] | None:
        with self.store.session() as s, s.begin():
            user = s.scalar(select(UserRow).where(UserRow.email == normalize_email(email)))
            if user is None:
                return None
            token = secrets.token_urlsafe(32)
            s.add(PasswordResetRow(token_hash=_hash_token(token), user_id=user.id, expires_at=_now() + RESET_TTL))
        return user, token

    def finish_reset(self, token: str, new_password: str) -> UserRow:
        check_password_rules(new_password)
        with self.store.session() as s, s.begin():
            row = s.get(PasswordResetRow, _hash_token(token))
            if row is None or row.used_at is not None or _as_utc(row.expires_at) < _now():
                raise AccountError(400, "That reset link is invalid or has expired. Request a new one.")
            row.used_at = _now()
            user_id = row.user_id
        return self._set_password(user_id, new_password)

    # ------------------------------------------------------------------ provider keys
    def _cipher(self) -> Fernet:
        if self._fernet is None:
            raise AccountError(503, "Key storage isn't configured on this server (FREESTASH_SECRETS_KEY).")
        return self._fernet

    def keys_masked(self, user_id: str) -> list[dict[str, Any]]:
        with self.store.session() as s:
            rows = {r.name: r for r in s.scalars(select(UserSecretRow).where(UserSecretRow.user_id == user_id))}
        return [{"name": k.name, "set": k.name in rows, "hint": rows[k.name].hint if k.name in rows else None,
                 "updated_at": _as_utc(rows[k.name].updated_at).isoformat() if k.name in rows else None}
                for k in KEY_CATALOG]

    def set_keys(self, user_id: str, values: dict[str, str | None]) -> None:
        unknown = set(values) - KEY_NAMES
        if unknown:
            raise AccountError(400, f"Unknown key name: {', '.join(sorted(unknown))}")
        with self.store.session() as s, s.begin():
            for name, value in values.items():
                row = s.get(UserSecretRow, (user_id, name))
                value = (value or "").strip()
                if not value:
                    if row:
                        s.delete(row)
                    continue
                if len(value) > 4096:
                    raise AccountError(400, f"{name} is too long to be an API key.")
                ciphertext = self._cipher().encrypt(value.encode()).decode()
                if row:
                    row.ciphertext, row.hint, row.updated_at = ciphertext, value[-4:], _now()
                else:
                    s.add(UserSecretRow(user_id=user_id, name=name, ciphertext=ciphertext, hint=value[-4:]))

    def reveal(self, user_id: str, name: str) -> str | None:
        with self.store.session() as s:
            row = s.get(UserSecretRow, (user_id, name))
        if row is None:
            return None
        try:
            return self._cipher().decrypt(row.ciphertext.encode()).decode()
        except InvalidToken as exc:  # the server's FREESTASH_SECRETS_KEY changed since this was saved
            raise AccountError(409, f"{name} can't be decrypted with the server's current key. Save it again.") from exc

    def key_values(self, user_id: str) -> dict[str, str]:
        """Every key the user has saved, decrypted, for building their search settings."""
        if self._fernet is None:
            return {}
        with self.store.session() as s:
            rows = list(s.scalars(select(UserSecretRow).where(UserSecretRow.user_id == user_id)))
        out = {}
        for r in rows:
            try:
                out[r.name] = self._fernet.decrypt(r.ciphertext.encode()).decode()
            except InvalidToken:
                continue  # surfaced through reveal(); search simply runs without it
        return out

    # ------------------------------------------------------------------ preferences
    def prefs(self, user_id: str) -> dict[str, Any]:
        with self.store.session() as s:
            row = s.get(UserPrefsRow, user_id)
        data = UserPrefs.model_validate(row.data if row else {}).model_dump(mode="json")
        return {"data": data, "updated_at": _as_utc(row.updated_at).isoformat() if row else None}

    def set_prefs(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        clean = UserPrefs.model_validate(data).model_dump(mode="json")
        with self.store.session() as s, s.begin():
            row = s.get(UserPrefsRow, user_id)
            if row:
                row.data, row.updated_at = clean, _now()
            else:
                s.add(UserPrefsRow(user_id=user_id, data=clean))
        return self.prefs(user_id)
