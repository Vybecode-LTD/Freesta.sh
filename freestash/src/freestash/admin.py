"""The site's own state, run from the admin screen (decision 0003, contract admin-shared-keys).

- Provider keys the admin stores once and every member's search uses (`providers/keys.py::settings_with_keys`).
- Site settings that override the env defaults at runtime: sign-up open, the per-member search cap, sources off.
- A usage meter: searches sent to each keyed source on the site's key, per UTC day.
- An append-only audit log of every admin change. It never holds a key value.
- Curated packs: packs the admin records by hand, with the license they read (contract github-and-curated-packs).

Everything is cached in-process and invalidated on write: the API runs as one replica (see ratelimit.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from threading import Lock
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, DateTime, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from freestash.accounts import AccountError, UserRow, _as_utc
from freestash.config import Settings
from freestash.models import CuratedPack
from freestash.providers.keys import KEY_CATALOG, KEY_NAMES, key_spec
from freestash.store import UUID, Base, JSONType, Store, _now


class ServerSecretRow(Base):
    __tablename__ = "server_secrets"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    hint: Mapped[str] = mapped_column(String(8))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_by: Mapped[str | None] = mapped_column(UUID, nullable=True)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SiteSettingRow(Base):
    __tablename__ = "site_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_by: Mapped[str | None] = mapped_column(UUID, nullable=True)


class ProviderUsageRow(Base):
    __tablename__ = "provider_usage"
    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)


class AdminAuditRow(Base):
    __tablename__ = "admin_audit"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    admin_id: Mapped[str | None] = mapped_column(UUID, nullable=True)  # None: `python -m freestash admin` on the server
    action: Mapped[str] = mapped_column(String(40))
    target: Mapped[str | None] = mapped_column(String(320), nullable=True)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class CuratedPackRow(Base):
    __tablename__ = "curated_packs"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    publisher: Mapped[str] = mapped_column(String(120))
    license_id: Mapped[str] = mapped_column(String(40))
    license_checked_on: Mapped[date] = mapped_column(Date)
    media_type: Mapped[str] = mapped_column(String(20))
    download_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    item_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    formats: Mapped[list[str]] = mapped_column(JSONType, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_by: Mapped[str | None] = mapped_column(UUID, nullable=True)


_PACK_FIELDS = [f for f in CuratedPack.model_fields if f not in ("id", "updated_at")]
MAX_IMPORT = 500


def _pack(row: CuratedPackRow) -> CuratedPack:
    return CuratedPack.model_validate({**{f: getattr(row, f) for f in _PACK_FIELDS}, "id": row.id,
                                       "updated_at": _as_utc(row.updated_at)})


def _write(row: CuratedPackRow, pack: CuratedPack, admin_id: str) -> dict[str, Any]:
    """Copy the pack onto the row; returns what changed (JSON-safe), for the audit log."""
    changed: dict[str, Any] = {}
    for f in _PACK_FIELDS:
        value = getattr(pack, f)
        stored = value.value if f == "media_type" else value
        if getattr(row, f) != stored:
            changed[f] = stored.isoformat() if f == "license_checked_on" else stored
            setattr(row, f, stored)
    if changed:
        row.updated_at, row.updated_by = _now(), admin_id
    return changed


class SiteSettings(BaseModel):
    """What the admin can change at runtime. Env gives the defaults; a stored value wins."""

    model_config = ConfigDict(extra="forbid")
    signup_open: bool = True
    searches_per_hour: int = Field(60, ge=1, le=10_000)
    disabled_providers: list[str] = Field(default_factory=list)


def _today() -> date:
    return datetime.now(UTC).date()


def _iso(dt: datetime | None) -> str | None:
    return _as_utc(dt).isoformat() if dt else None


class AdminService:
    def __init__(self, store: Store, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self._fernet = Fernet(settings.secrets_key) if settings.secrets_key else None
        self._lock = Lock()
        self._site: SiteSettings | None = None
        self._keys: dict[str, str] | None = None
        self._curated: list[CuratedPack] | None = None

    # ------------------------------------------------------------------ site settings
    def site(self) -> SiteSettings:
        with self._lock:
            if self._site is None:
                with self.store.session() as s:
                    stored = {r.key: r.value for r in s.scalars(select(SiteSettingRow))}
                defaults = {"signup_open": self.settings.signup_open}
                self._site = SiteSettings.model_validate({**defaults, **{k: v for k, v in stored.items()
                                                                          if k in SiteSettings.model_fields}})
            return self._site

    def update_site(self, admin_id: str, changes: dict[str, Any]) -> SiteSettings:
        from freestash.providers import (
            provider_class,  # the registry imports config only; keep this module light
        )

        current = self.site()
        merged = SiteSettings.model_validate({**current.model_dump(), **changes})  # raises on bad values
        unknown = [p for p in merged.disabled_providers if provider_class(p) is None]
        if unknown:
            raise AccountError(400, f"Unknown source: {', '.join(unknown)}")
        merged.disabled_providers = sorted(set(merged.disabled_providers))
        diff = {k: v for k, v in merged.model_dump().items() if v != getattr(current, k)}
        if diff:
            with self.store.session() as s, s.begin():
                for key, value in diff.items():
                    row = s.get(SiteSettingRow, key) or SiteSettingRow(key=key)
                    row.value, row.updated_at, row.updated_by = value, _now(), admin_id
                    s.add(row)
                s.add(AdminAuditRow(admin_id=admin_id, action="settings.update", detail=diff))
            with self._lock:
                self._site = None
        return self.site()

    # ------------------------------------------------------------------ the site's provider keys
    def _cipher(self) -> Fernet:
        if self._fernet is None:
            raise AccountError(503, "Key storage isn't configured on this server (FREESTASH_SECRETS_KEY).")
        return self._fernet

    def site_key_values(self) -> dict[str, str]:
        """Every stored site key, decrypted, for building members' search settings. Cached until the next write."""
        with self._lock:
            if self._keys is None:
                out: dict[str, str] = {}
                if self._fernet is not None:
                    with self.store.session() as s:
                        rows = list(s.scalars(select(ServerSecretRow)))
                    for r in rows:
                        try:
                            out[r.name] = self._fernet.decrypt(r.ciphertext.encode()).decode()
                        except InvalidToken:
                            continue  # FREESTASH_SECRETS_KEY changed: the screen says "save it again"
                self._keys = out
            return dict(self._keys)

    def keys_report(self) -> list[dict[str, Any]]:
        with self.store.session() as s:
            rows = {r.name: r for r in s.scalars(select(ServerSecretRow))}
        readable = self.site_key_values()
        out = []
        for spec in KEY_CATALOG:
            row = rows.get(spec.name)
            source = "admin" if row else ("env" if getattr(self.settings, spec.setting, None) else None)
            out.append({
                "name": spec.name, "provider": spec.provider, "provider_name": spec.provider_name, "label": spec.label,
                "limits": spec.limits, "optional": spec.optional, "source": source,
                "hint": row.hint if row else None, "updated_at": _iso(row.updated_at) if row else None,
                "unreadable": bool(row) and spec.name not in readable,
                "last_ok_at": _iso(row.last_ok_at) if row else None,
                "last_error": row.last_error if row else None, "last_error_at": _iso(row.last_error_at) if row else None,
            })
        return out

    def set_keys(self, admin_id: str, values: dict[str, str | None]) -> None:
        unknown = set(values) - KEY_NAMES
        if unknown:
            raise AccountError(400, f"Unknown key name: {', '.join(sorted(unknown))}")
        changed: dict[str, str] = {}
        with self.store.session() as s, s.begin():
            for name, value in values.items():
                row = s.get(ServerSecretRow, name)
                value = (value or "").strip()
                if not value:
                    if row:
                        s.delete(row)
                        changed[name] = "cleared"
                    continue
                if len(value) > 4096:
                    raise AccountError(400, f"{name} is too long to be an API key.")
                ciphertext = self._cipher().encrypt(value.encode()).decode()
                if row is None:
                    row = ServerSecretRow(name=name)
                    s.add(row)
                row.ciphertext, row.hint, row.updated_at, row.updated_by = ciphertext, value[-4:], _now(), admin_id
                row.last_ok_at = row.last_error = row.last_error_at = None  # a new key hasn't been tested
                changed[name] = "set"
            if changed:
                s.add(AdminAuditRow(admin_id=admin_id, action="keys.update", detail=changed))  # names only
        with self._lock:
            self._keys = None

    def has_site_key(self, name: str) -> bool:
        spec = key_spec(name)
        return bool(spec) and bool(self.site_key_values().get(name) or getattr(self.settings, spec.setting, None))

    def record_test(self, name: str, error: str | None) -> None:
        """Remember the latest Test result. Only a stored key has a row: an env key's result is returned, not kept."""
        with self.store.session() as s, s.begin():
            row = s.get(ServerSecretRow, name)
            if row is None:
                return
            if error is None:
                row.last_ok_at = _now()
            else:
                row.last_error, row.last_error_at = error[:500], _now()

    # ------------------------------------------------------------------ curated packs
    def curated(self) -> list[CuratedPack]:
        """Every curated pack, by title. Cached until the next write: every member's search reads it."""
        with self._lock:
            if self._curated is None:
                with self.store.session() as s:
                    rows = list(s.scalars(select(CuratedPackRow)))
                self._curated = sorted((_pack(r) for r in rows), key=lambda p: (p.title.lower(), p.url))
            return list(self._curated)

    def _forget_curated(self) -> None:
        with self._lock:
            self._curated = None

    def add_curated(self, admin_id: str, pack: CuratedPack) -> CuratedPack:
        try:
            with self.store.session() as s, s.begin():
                row = CuratedPackRow()
                _write(row, pack, admin_id)
                s.add(row)
                s.flush()
                s.add(AdminAuditRow(admin_id=admin_id, action="curated.add", target=pack.title,
                                    detail={"url": pack.url, "license": pack.license_id}))
                new_id = row.id
        except IntegrityError as exc:
            raise AccountError(409, f"{pack.url} is already in the curated list.") from exc
        self._forget_curated()
        return next(p for p in self.curated() if p.id == new_id)

    @staticmethod
    def _pack_id(pack_id: str) -> str:
        """The id as the database writes it. Postgres refuses a non-UUID outright, which would be a 500, not a 404."""
        try:
            return str(uuid.UUID(pack_id))
        except ValueError:
            raise AccountError(404, "No such curated pack.") from None

    def update_curated(self, admin_id: str, pack_id: str, pack: CuratedPack) -> CuratedPack:
        pack_id = self._pack_id(pack_id)
        try:
            with self.store.session() as s, s.begin():
                row = s.get(CuratedPackRow, pack_id)
                if row is None:
                    raise AccountError(404, "No such curated pack.")
                changed = _write(row, pack, admin_id)
                s.flush()
                if changed:
                    s.add(AdminAuditRow(admin_id=admin_id, action="curated.update", target=pack.title, detail=changed))
        except IntegrityError as exc:
            raise AccountError(409, f"{pack.url} is already in the curated list.") from exc
        self._forget_curated()
        return next(p for p in self.curated() if p.id == pack_id)

    def delete_curated(self, admin_id: str, pack_id: str) -> None:
        pack_id = self._pack_id(pack_id)
        with self.store.session() as s, s.begin():
            row = s.get(CuratedPackRow, pack_id)
            if row is None:
                raise AccountError(404, "No such curated pack.")
            s.add(AdminAuditRow(admin_id=admin_id, action="curated.delete", target=row.title, detail={"url": row.url}))
            s.delete(row)
        self._forget_curated()

    def import_curated(self, admin_id: str, packs: list[CuratedPack]) -> dict[str, int]:
        """Add or update by url, in one transaction: every pack was validated before this runs, so it's all or nothing."""
        if len(packs) > MAX_IMPORT:
            raise AccountError(400, f"Import at most {MAX_IMPORT} packs at a time.")
        urls = [p.url for p in packs]
        if len(set(urls)) != len(urls):
            dup = next(u for u in urls if urls.count(u) > 1)
            raise AccountError(400, f"{dup} is in the import twice.")
        added = updated = 0
        with self.store.session() as s, s.begin():
            existing = {r.url: r for r in s.scalars(select(CuratedPackRow).where(CuratedPackRow.url.in_(urls)))}
            for pack in packs:
                row = existing.get(pack.url)
                if row is None:
                    row = CuratedPackRow()
                    _write(row, pack, admin_id)
                    s.add(row)
                    added += 1
                elif _write(row, pack, admin_id):
                    updated += 1
            if added or updated:
                s.add(AdminAuditRow(admin_id=admin_id, action="curated.import",
                                    detail={"added": added, "updated": updated}))
        self._forget_curated()
        return {"added": added, "updated": updated}

    # ------------------------------------------------------------------ usage meter
    def record_usage(self, counts: dict[str, tuple[int, int]]) -> None:
        """Add (calls, errors) per provider to today's row, as one upsert each."""
        counts = {p: c for p, c in counts.items() if c[0] or c[1]}
        if not counts:
            return
        day = _today()
        with self.store.session() as s, s.begin():
            insert = pg_insert if s.get_bind().dialect.name == "postgresql" else sqlite_insert
            for provider, (calls, errors) in counts.items():
                stmt = insert(ProviderUsageRow).values(provider=provider, day=day, calls=calls, errors=errors)
                s.execute(stmt.on_conflict_do_update(
                    index_elements=["provider", "day"],
                    set_={"calls": ProviderUsageRow.calls + calls, "errors": ProviderUsageRow.errors + errors}))

    def usage_report(self) -> list[dict[str, Any]]:
        today = _today()
        month_start = today.replace(day=1)
        with self.store.session() as s:
            day_rows = {r.provider: r for r in s.scalars(select(ProviderUsageRow).where(ProviderUsageRow.day == today))}
            month = {p: (c or 0, e or 0) for p, c, e in s.execute(
                select(ProviderUsageRow.provider, func.sum(ProviderUsageRow.calls), func.sum(ProviderUsageRow.errors))
                .where(ProviderUsageRow.day >= month_start).group_by(ProviderUsageRow.provider))}
        out, seen = [], set()
        for spec in KEY_CATALOG:  # one row per keyed source, in catalog order
            if spec.provider in seen:
                continue
            seen.add(spec.provider)
            d = day_rows.get(spec.provider)
            m = month.get(spec.provider, (0, 0))
            out.append({"provider": spec.provider, "provider_name": spec.provider_name, "limits": spec.limits,
                        "today": {"calls": d.calls if d else 0, "errors": d.errors if d else 0},
                        "month": {"calls": int(m[0]), "errors": int(m[1])}})
        return out

    # ------------------------------------------------------------------ audit log
    def audit(self, admin_id: str | None, action: str, target: str | None, detail: dict[str, Any]) -> None:
        with self.store.session() as s, s.begin():
            s.add(AdminAuditRow(admin_id=admin_id, action=action, target=target, detail=detail))

    def audit_log(self, before: datetime | None = None, limit: int = 50) -> list[dict[str, Any]]:
        stmt = (select(AdminAuditRow, UserRow.email).outerjoin(UserRow, UserRow.id == AdminAuditRow.admin_id)
                .order_by(AdminAuditRow.at.desc()).limit(limit))
        if before:
            stmt = stmt.where(AdminAuditRow.at < before)
        with self.store.session() as s:
            rows = s.execute(stmt).all()
        return [{"at": _iso(r.at), "admin_email": email if r.admin_id else "server command", "action": r.action,
                 "target": r.target, "detail": r.detail} for r, email in rows]
