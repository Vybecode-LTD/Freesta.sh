"""Persistence: license ledger + collections. SQLite locally, Railway Postgres for the hosted app.

The API is the only thing that talks to the database, and every query here is scoped to a team, so
there is no row-level security to keep in sync. Each account owns a personal team (see accounts.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Uuid, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from freestash.config import Settings, get_settings
from freestash.models import LedgerEntry, ScoredAsset, Tier, Trust, UseCase

JSONType = JSON().with_variant(JSONB(), "postgresql")
UUID = Uuid(as_uuid=False)  # native uuid on Postgres, CHAR(32) on SQLite


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TeamRow(Base):
    __tablename__ = "teams"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TeamMemberRow(Base):
    __tablename__ = "team_members"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(UUID, primary_key=True)
    role: Mapped[str] = mapped_column(String(20), default="member")  # owner | admin | member


class LedgerRow(Base):
    __tablename__ = "ledger_entries"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=_uuid)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(UUID, nullable=True)
    asset_uid: Mapped[str] = mapped_column(String(300), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(Text)
    creator: Mapped[str | None] = mapped_column(Text, nullable=True)
    landing_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_id: Mapped[str] = mapped_column(String(60))
    license_label: Mapped[str] = mapped_column(Text)
    license_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    trust: Mapped[str] = mapped_column(String(20))
    use_case: Mapped[str] = mapped_column(String(20))
    tier: Mapped[str] = mapped_column(String(10))
    attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    project: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)


class CollectionRow(Base):
    __tablename__ = "collections"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=_uuid)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(UUID, nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    use_case: Mapped[str] = mapped_column(String(20), default=UseCase.DEMO.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    items: Mapped[list[CollectionItemRow]] = relationship(back_populates="collection", cascade="all, delete-orphan",
                                                          order_by="CollectionItemRow.added_at")


class CollectionItemRow(Base):
    __tablename__ = "collection_items"
    id: Mapped[str] = mapped_column(UUID, primary_key=True, default=_uuid)
    collection_id: Mapped[str] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"), index=True)
    asset_uid: Mapped[str] = mapped_column(String(300))
    asset: Mapped[dict[str, Any]] = mapped_column(JSONType)
    verdict: Mapped[dict[str, Any]] = mapped_column(JSONType)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_by: Mapped[str | None] = mapped_column(UUID, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    collection: Mapped[CollectionRow] = relationship(back_populates="items")


def _entry_from_row(r: LedgerRow) -> LedgerEntry:
    return LedgerEntry(
        id=r.id, asset_uid=r.asset_uid, provider=r.provider, title=r.title, creator=r.creator, landing_url=r.landing_url,
        file_url=r.file_url, license_id=r.license_id, license_label=r.license_label, license_url=r.license_url,
        license_raw=r.license_raw, trust=Trust(r.trust), use_case=UseCase(r.use_case), tier=Tier(r.tier),
        attribution=r.attribution, project=r.project, sha256=r.sha256, local_path=r.local_path, bytes=r.bytes,
        retrieved_at=r.retrieved_at, created_by=r.created_by, team_id=r.team_id, snapshot=r.snapshot or {},
    )


def entry_from_scored(s: ScoredAsset, *, project: str | None = None, file_url: str | None = None,
                      sha256: str | None = None, local_path: str | None = None, size: int | None = None,
                      user_id: str | None = None, team_id: str | None = None) -> LedgerEntry:
    a, v = s.asset, s.verdict
    return LedgerEntry(
        asset_uid=a.uid, provider=a.provider, title=a.title, creator=a.creator, landing_url=a.landing_url,
        file_url=file_url, license_id=a.license.id, license_label=a.license.label, license_url=a.license.url,
        license_raw=a.license.raw, trust=a.trust, use_case=v.use_case, tier=v.tier, attribution=v.attribution,
        project=project, sha256=sha256, local_path=local_path, bytes=size, retrieved_at=_now(),
        created_by=user_id, team_id=team_id,
        snapshot={"asset": a.model_dump(mode="json"), "verdict": v.model_dump(mode="json")},
    )


class Store:
    def __init__(self, url: str | None = None, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.url = url or settings.resolved_database_url
        connect_args = {"check_same_thread": False} if self.url.startswith("sqlite") else {}
        self.engine = create_engine(self.url, connect_args=connect_args, pool_pre_ping=True)
        self._session = sessionmaker(self.engine, expire_on_commit=False)
        import freestash.accounts  # noqa: F401  (registers the account tables on Base)

        Base.metadata.create_all(self.engine)  # idempotent; move to Alembic before the first breaking change

    def session(self) -> Session:
        return self._session()

    # ------------------------------------------------------------------ teams
    def team_ids_for(self, user_id: str) -> list[str]:
        with self.session() as s:
            return list(s.scalars(select(TeamMemberRow.team_id).where(TeamMemberRow.user_id == user_id)))

    # ------------------------------------------------------------------ ledger
    def add_entry(self, entry: LedgerEntry) -> LedgerEntry:
        with self.session() as s, s.begin():
            row = LedgerRow(**entry.model_dump(exclude={"id"}, mode="python"))
            row.trust, row.use_case, row.tier = entry.trust.value, entry.use_case.value, entry.tier.value
            s.add(row)
        return _entry_from_row(row)

    def list_entries(self, *, team_id: str | None = None, project: str | None = None, limit: int = 500) -> list[LedgerEntry]:
        with self.session() as s:
            stmt = select(LedgerRow).order_by(LedgerRow.retrieved_at.desc()).limit(limit)
            stmt = stmt.where(LedgerRow.team_id == team_id) if team_id else stmt.where(LedgerRow.team_id.is_(None))
            if project:
                stmt = stmt.where(LedgerRow.project == project)
            return [_entry_from_row(r) for r in s.scalars(stmt)]

    def projects(self, *, team_id: str | None = None) -> list[str]:
        with self.session() as s:
            stmt = select(LedgerRow.project).distinct().where(LedgerRow.project.is_not(None))
            stmt = stmt.where(LedgerRow.team_id == team_id) if team_id else stmt.where(LedgerRow.team_id.is_(None))
            return sorted(p for p in s.scalars(stmt) if p)

    # ------------------------------------------------------------------ collections
    def create_collection(self, name: str, *, description: str | None = None, use_case: UseCase = UseCase.DEMO,
                          team_id: str | None = None, user_id: str | None = None) -> dict[str, Any]:
        with self.session() as s, s.begin():
            row = CollectionRow(name=name, description=description, use_case=use_case.value, team_id=team_id, created_by=user_id)
            s.add(row)
        return self._collection_dict(row, items=[])

    def list_collections(self, *, team_id: str | None = None) -> list[dict[str, Any]]:
        with self.session() as s:
            stmt = select(CollectionRow).order_by(CollectionRow.created_at.desc())
            stmt = stmt.where(CollectionRow.team_id == team_id) if team_id else stmt.where(CollectionRow.team_id.is_(None))
            return [self._collection_dict(r, items=None, count=len(r.items)) for r in s.scalars(stmt)]

    def get_collection(self, collection_id: str, *, team_id: str | None = None) -> dict[str, Any] | None:
        with self.session() as s:
            row = s.get(CollectionRow, collection_id)
            if not row or row.team_id != team_id:
                return None
            return self._collection_dict(row, items=list(row.items))

    def add_to_collection(self, collection_id: str, scored: ScoredAsset, *, note: str | None = None,
                          user_id: str | None = None, team_id: str | None = None) -> dict[str, Any] | None:
        with self.session() as s, s.begin():
            coll = s.get(CollectionRow, collection_id)
            if not coll or coll.team_id != team_id:
                return None
            if any(i.asset_uid == scored.uid for i in coll.items):
                return self._collection_dict(coll, items=list(coll.items))
            coll.items.append(CollectionItemRow(asset_uid=scored.uid, asset=scored.asset.model_dump(mode="json"),
                                                verdict=scored.verdict.model_dump(mode="json"), note=note, added_by=user_id))
        return self.get_collection(collection_id, team_id=team_id)

    def remove_from_collection(self, collection_id: str, asset_uid: str, *, team_id: str | None = None) -> bool:
        with self.session() as s, s.begin():
            coll = s.get(CollectionRow, collection_id)
            if not coll or coll.team_id != team_id:
                return False
            for item in list(coll.items):
                if item.asset_uid == asset_uid:
                    s.delete(item)
                    return True
        return False

    def delete_collection(self, collection_id: str, *, team_id: str | None = None) -> bool:
        with self.session() as s, s.begin():
            coll = s.get(CollectionRow, collection_id)
            if not coll or coll.team_id != team_id:
                return False
            s.delete(coll)
            return True

    @staticmethod
    def _collection_dict(row: CollectionRow, items: list[CollectionItemRow] | None, count: int | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": row.id, "name": row.name, "description": row.description, "use_case": row.use_case,
            "team_id": row.team_id, "created_by": row.created_by,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "item_count": count if count is not None else len(items or []),
        }
        if items is not None:
            out["items"] = [{"uid": i.asset_uid, "asset": i.asset, "verdict": i.verdict, "note": i.note,
                             "added_by": i.added_by, "added_at": i.added_at.isoformat() if i.added_at else None} for i in items]
        return out
