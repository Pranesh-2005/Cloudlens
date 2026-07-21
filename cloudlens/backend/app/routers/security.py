from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import User, get_session
from app.ratelimit import limiter

router = APIRouter()


@router.get("/security/findings")
@limiter.limit("60/minute")
async def security_findings(request: Request, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    from app.memory import get_recent_findings

    findings = await get_recent_findings(session, user.id, limit=100)
    return [
        {
            "id": f.id,
            "severity": f.severity,
            "kind": f.kind,
            "resource": f.resource,
            "summary": f.summary,
            "detected_at": f.detected_at.isoformat(),
        }
        for f in findings
    ]
