import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.a2a.server import resume_specialist
from app.auth import get_current_user
from app.db import Approval, User, get_session
from app.ratelimit import limiter

router = APIRouter()


@router.get("/approvals")
@limiter.limit("60/minute")
async def list_approvals(request: Request, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    result = await session.execute(select(Approval).where(Approval.user_id == user.id).order_by(Approval.created_at.desc()))
    rows = result.scalars().all()
    return [
        {
            "id": a.id,
            "action": a.action,
            "params": a.params,
            "requested_by_agent": a.requested_by_agent,
            "reason": a.reason,
            "status": a.status,
            "created_at": a.created_at.isoformat(),
        }
        for a in rows
    ]


class DecideIn(BaseModel):
    decision: str  # "approve" | "reject"
    note: str | None = None


@router.post("/approvals/{approval_id}/decide")
@limiter.limit("60/minute")
async def decide_approval(
    approval_id: str,
    body: DecideIn,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if body.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'")

    approval = await session.get(Approval, approval_id)
    if approval is None or approval.user_id != user.id:
        raise HTTPException(status_code=404, detail="approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail=f"approval already {approval.status}")

    approval.status = "approved" if body.decision == "approve" else "rejected"
    approval.note = body.note
    approval.decided_at = dt.datetime.utcnow()
    await session.commit()

    # Resume the paused LangGraph run - this actually re-enters the graph at its
    # interrupt() call via the checkpointer, executing (or skipping) the tool.
    await resume_specialist(request, session, user, approval, body.decision, body.note)

    return {"ok": True, "status": approval.status}
