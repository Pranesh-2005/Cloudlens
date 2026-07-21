from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import query_audit
from app.auth import get_current_user
from app.db import User, get_session
from app.ratelimit import limiter

router = APIRouter()


@router.get("/audit")
@limiter.limit("60/minute")
async def audit_trail(
    request: Request, limit: int = 100, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = await query_audit(session, user.id, limit)
    return [
        {"ts": r.ts.isoformat(), "agent": r.agent, "tool": r.tool, "status": r.status, "latency_ms": r.latency_ms, "tokens": r.tokens}
        for r in rows
    ]
