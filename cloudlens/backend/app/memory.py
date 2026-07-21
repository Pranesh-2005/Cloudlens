"""Memory layer: LangGraph checkpointer (short-term) + findings/preferences (long-term)."""
from __future__ import annotations

import contextlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import Finding, Preference, User


@contextlib.asynccontextmanager
async def build_checkpointer(settings: Settings):
    """Async context manager yielding a LangGraph checkpointer.

    AsyncPostgresSaver when DATABASE_URL set, AsyncSqliteSaver locally.
    thread_id per conversation persists across restarts when Postgres is used.
    """
    if settings.DATABASE_URL:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        conn_str = settings.DATABASE_URL
        if conn_str.startswith("postgresql+asyncpg://"):
            conn_str = conn_str.replace("postgresql+asyncpg://", "postgresql://", 1)
        elif conn_str.startswith("postgres://"):
            conn_str = conn_str.replace("postgres://", "postgresql://", 1)
        async with AsyncPostgresSaver.from_conn_string(conn_str) as saver:
            await saver.setup()
            yield saver
    else:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        async with AsyncSqliteSaver.from_conn_string(".langgraph_checkpoints.db") as saver:
            yield saver


async def write_finding(
    session: AsyncSession, user_id: str, kind: str, severity: str, resource: str, summary: str
) -> Finding:
    row = Finding(user_id=user_id, kind=kind, severity=severity, resource=resource, summary=summary)
    session.add(row)
    await session.commit()
    return row


async def get_recent_findings(
    session: AsyncSession, user_id: str, keyword: str | None = None, limit: int = 5
) -> list[Finding]:
    stmt = select(Finding).where(Finding.user_id == user_id)
    if keyword:
        stmt = stmt.where(Finding.summary.ilike(f"%{keyword}%") | Finding.resource.ilike(f"%{keyword}%"))
    stmt = stmt.order_by(Finding.detected_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def set_preference(session: AsyncSession, user_id: str, key: str, value: str) -> None:
    result = await session.execute(select(Preference).where(Preference.user_id == user_id, Preference.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        session.add(Preference(user_id=user_id, key=key, value=value))
    else:
        row.value = value
    await session.commit()


async def get_preferences(session: AsyncSession, user_id: str) -> dict[str, str]:
    result = await session.execute(select(Preference).where(Preference.user_id == user_id))
    return {row.key: row.value for row in result.scalars().all()}


def build_findings_context(findings: list[Finding]) -> str:
    if not findings:
        return ""
    lines = [f"- ({f.severity}/{f.kind}) {f.resource}: {f.summary}" for f in findings]
    return "Relevant recent findings:\n" + "\n".join(lines)
