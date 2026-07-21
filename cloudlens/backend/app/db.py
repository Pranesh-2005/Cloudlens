"""SQLAlchemy async engine, models, session."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    credential: Mapped["Credential | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)
    access_key_id_enc: Mapped[str] = mapped_column(Text)
    secret_access_key_enc: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(32), default="us-east-1")
    last4: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)

    user: Mapped[User] = relationship(back_populates="credential")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    resource: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(64))
    agent: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_by_agent: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/approved/rejected
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)
    decided_at: Mapped[dt.datetime | None] = mapped_column(nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    agent: Mapped[str] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(64))
    args: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16))
    latency_ms: Mapped[int] = mapped_column(default=0)
    tokens: Mapped[int] = mapped_column(default=0)
    ts: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = (UniqueConstraint("user_id", "thread_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255), default="New conversation")
    updated_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user/assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(default=dt.datetime.utcnow)


class Preference(Base):
    __tablename__ = "preferences"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(String(255))


def _normalize_db_url(url: str) -> tuple[str, dict]:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    connect_args: dict = {}
    if url.startswith("postgresql+asyncpg://"):
        # Neon/Supabase connection strings default to "neondb"/"postgres" —
        # always target a database named "cloudlens" regardless of what's pasted.
        from urllib.parse import parse_qs, urlsplit, urlunsplit

        parts = urlsplit(url)
        if parts.path.lstrip("/") != "cloudlens":
            parts = parts._replace(path="/cloudlens")

        # asyncpg's dialect passes query params straight through as connect()
        # kwargs, but asyncpg has no "sslmode"/"channel_binding" kwargs (those
        # are libpq/psycopg names) — strip them and use "ssl" via connect_args.
        query = parse_qs(parts.query)
        sslmode = query.pop("sslmode", [None])[0]
        query.pop("channel_binding", None)
        if sslmode and sslmode != "disable":
            connect_args["ssl"] = "require"
        from urllib.parse import urlencode

        parts = parts._replace(query=urlencode(query, doseq=True))
        url = urlunsplit(parts)

    return url, connect_args


async def _ensure_cloudlens_database(raw_url: str) -> None:
    """Neon/Supabase hand you a default db (neondb/postgres) — auto-create "cloudlens" if it's missing."""
    from urllib.parse import urlsplit, urlunsplit

    from urllib.parse import parse_qs, urlencode

    plain = raw_url.replace("postgresql+asyncpg://", "postgresql://", 1).replace("postgres://", "postgresql://", 1)
    parts = urlsplit(plain)
    if parts.path.lstrip("/") == "cloudlens":
        return

    import logging

    import asyncpg

    query = parse_qs(parts.query)
    sslmode = query.pop("sslmode", [None])[0]
    query.pop("channel_binding", None)
    ssl = "require" if sslmode and sslmode != "disable" else None
    parts = parts._replace(path="/postgres", query=urlencode(query, doseq=True))
    maintenance_url = urlunsplit(parts)
    try:
        conn = await asyncpg.connect(maintenance_url, ssl=ssl)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("could not reach maintenance db to auto-create 'cloudlens': %s", exc)
        return
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'cloudlens'")
        if not exists:
            await conn.execute("CREATE DATABASE cloudlens")
            logging.getLogger(__name__).info("created database 'cloudlens'")
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning("could not auto-create 'cloudlens' database: %s", exc)
    finally:
        await conn.close()


_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine, _sessionmaker
    if _engine is None:
        settings = get_settings()
        if settings.DATABASE_URL:
            url, connect_args = _normalize_db_url(settings.DATABASE_URL)
        else:
            url, connect_args = "sqlite+aiosqlite:///./cloudlens.db", {}
        _engine = create_async_engine(url, echo=False, connect_args=connect_args)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def init_db() -> None:
    settings = get_settings()
    if settings.DATABASE_URL:
        await _ensure_cloudlens_database(settings.DATABASE_URL)
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    sm = get_sessionmaker()
    async with sm() as session:
        yield session


def reset_engine() -> None:
    """Test helper: drop cached engine/sessionmaker so get_settings() changes take effect."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
