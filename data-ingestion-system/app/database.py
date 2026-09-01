"""app/database.py — SQLAlchemy async ORM models and database utilities.

This module defines the three core tables:
  - raw_items: Unified storage for all ingested data from all sources.
  - ingestor_logs: Audit log of every ingestor run.
  - scheduling_metadata: Per-ingestor scheduling state.

Supports both SQLite (development) and PostgreSQL (production) via
the DATABASE_URL environment variable.
"""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ORM Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all ORM models."""
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class RawItemModel(Base):
    """Stores a single ingested item from any data source.

    The (source_name, source_id) pair is unique and used for upsert /
    idempotent ingestion. Running any ingestor twice produces the same
    database state.
    """

    __tablename__ = "raw_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    date_published: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    date_ingested: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("source_name", "source_id", name="uq_source_name_source_id"),
        Index("ix_raw_items_date_ingested", "date_ingested"),
        Index("ix_raw_items_source_url", "source_url"),
    )

    @property
    def metadata_dict(self) -> Dict[str, Any]:
        """Deserialise the metadata JSON field."""
        if self.metadata_json is None:
            return {}
        try:
            return json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return {}

    @metadata_dict.setter
    def metadata_dict(self, value: Dict[str, Any]) -> None:
        """Serialise and store metadata as JSON."""
        self.metadata_json = json.dumps(value, ensure_ascii=False, default=str)

    def __repr__(self) -> str:
        title_summary = (self.title[:40] + "...") if self.title and len(self.title) > 40 else (self.title or "")
        return (
            f"<RawItemModel source={self.source_name!r} "
            f"source_id={self.source_id!r} title={title_summary!r}>"
        )


class IngestorLogModel(Base):
    """Audit log of every ingestor run (success or failure)."""

    __tablename__ = "ingestor_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ingestor_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    run_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    items_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_stored: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_cursor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<IngestorLogModel name={self.ingestor_name!r} "
            f"success={self.success} fetched={self.items_fetched}>"
        )


class SchedulingMetadataModel(Base):
    """Tracks scheduling state for each ingestor."""

    __tablename__ = "scheduling_metadata"

    ingestor_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_run_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_scheduled_run: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    run_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=1440)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_cursor: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return (
            f"<SchedulingMetadataModel name={self.ingestor_name!r} "
            f"enabled={self.is_enabled} interval={self.run_interval_minutes}m>"
        )


# ---------------------------------------------------------------------------
# Engine + Session factory
# ---------------------------------------------------------------------------

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def create_db_engine(db_url: Optional[str] = None) -> AsyncEngine:
    """Create the SQLAlchemy async engine from settings or url."""
    settings = get_settings()
    url = db_url or settings.database_url
    is_sqlite = url.startswith("sqlite")

    connect_args: Dict[str, Any] = {}
    extra_kwargs: Dict[str, Any] = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False
        extra_kwargs["poolclass"] = NullPool

    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        connect_args=connect_args,
        **extra_kwargs,
    )

    if is_sqlite:
        @event.listens_for(engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_conn, _conn_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine() -> AsyncEngine:
    """Return the global async engine, creating it if necessary."""
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the global session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async context manager that provides a database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db(engine: Optional[AsyncEngine] = None) -> None:
    """Create all tables if they do not already exist."""
    eng = engine or get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified")


async def close_db() -> None:
    """Dispose the engine connection pool on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database connections closed")


# ---------------------------------------------------------------------------
# Database helper functions
# ---------------------------------------------------------------------------


async def upsert_raw_item(
    session: AsyncSession,
    source_name: str,
    source_id: str,
    source_url: Optional[str],
    title: Optional[str],
    raw_content: Optional[str],
    date_published: Optional[datetime],
    metadata: Optional[Dict[str, Any]] = None,
    is_active: bool = True,
) -> bool:
    """Insert or update a RawItemModel.

    Uses (source_name, source_id) as the natural key. If the item already
    exists it is updated in-place; otherwise a new row is inserted.

    Returns:
        True if a new row was inserted, False if an existing row was updated.
    """
    stmt = select(RawItemModel).where(
        RawItemModel.source_name == source_name,
        RawItemModel.source_id == source_id,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    is_new = existing is None

    if is_new:
        item = RawItemModel(
            id=str(uuid.uuid4()),
            source_name=source_name,
            source_id=source_id,
            source_url=source_url,
            title=title,
            raw_content=raw_content,
            date_published=date_published,
            date_ingested=now,
            is_active=is_active,
        )
        item.metadata_dict = metadata or {}
        session.add(item)
    else:
        existing.source_url = source_url
        existing.title = title
        existing.raw_content = raw_content
        existing.date_published = date_published
        existing.date_ingested = now
        existing.metadata_dict = metadata or {}
        existing.is_active = is_active

    return is_new


async def store_ingestor_log(session: AsyncSession, log: IngestorLogModel) -> None:
    """Persist an IngestorLogModel to the database."""
    session.add(log)


async def get_scheduling_metadata(
    session: AsyncSession, ingestor_name: str
) -> Optional[SchedulingMetadataModel]:
    """Retrieve scheduling metadata for the given ingestor."""
    result = await session.execute(
        select(SchedulingMetadataModel).where(
            SchedulingMetadataModel.ingestor_name == ingestor_name
        )
    )
    return result.scalar_one_or_none()


async def upsert_scheduling_metadata(
    session: AsyncSession,
    ingestor_name: str,
    **kwargs: Any,
) -> SchedulingMetadataModel:
    """Insert or update a SchedulingMetadataModel row."""
    existing = await get_scheduling_metadata(session, ingestor_name)
    if existing is None:
        row = SchedulingMetadataModel(ingestor_name=ingestor_name, **kwargs)
        session.add(row)
        return row
    for key, value in kwargs.items():
        setattr(existing, key, value)
    return existing


async def get_last_cursor(session: AsyncSession, ingestor_name: str) -> Optional[str]:
    """Return the last pagination cursor stored for an ingestor."""
    meta = await get_scheduling_metadata(session, ingestor_name)
    return meta.last_cursor if meta else None
