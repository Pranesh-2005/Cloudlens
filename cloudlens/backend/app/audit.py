"""Audit log writer + query. Every tool call -> DB row, secrets redacted."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AuditLog

_SECRET_KEYS = {"access_key_id", "secret_access_key", "password", "token", "secret", "authorization"}


def redact(args: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in args.items():
        if k.lower() in _SECRET_KEYS:
            out[k] = "***redacted***"
        else:
            out[k] = v
    return out


async def write_audit(
    session: AsyncSession,
    user_id: str,
    agent: str,
    tool: str,
    args: dict[str, Any],
    status: str,
    latency_ms: int = 0,
    tokens: int = 0,
) -> AuditLog:
    row = AuditLog(
        user_id=user_id,
        agent=agent,
        tool=tool,
        args=redact(args),
        status=status,
        latency_ms=latency_ms,
        tokens=tokens,
    )
    session.add(row)
    await session.commit()
    return row


async def query_audit(session: AsyncSession, user_id: str, limit: int = 100) -> list[AuditLog]:
    result = await session.execute(
        select(AuditLog).where(AuditLog.user_id == user_id).order_by(AuditLog.ts.desc()).limit(limit)
    )
    return list(result.scalars().all())
