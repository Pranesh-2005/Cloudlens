import datetime as dt
import json
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.supervisor import handle_chat
from app.auth import get_current_user
from app.db import Message, Thread, User, get_session, get_sessionmaker
from app.ratelimit import limiter

router = APIRouter()


class ChatIn(BaseModel):
    message: str
    thread_id: str | None = None


async def _upsert_thread(session: AsyncSession, user: User, thread_id: str, message: str) -> None:
    result = await session.execute(select(Thread).where(Thread.user_id == user.id, Thread.thread_id == thread_id))
    row = result.scalar_one_or_none()
    if row is None:
        session.add(Thread(user_id=user.id, thread_id=thread_id, title=message[:60], updated_at=dt.datetime.utcnow()))
    else:
        row.updated_at = dt.datetime.utcnow()
    session.add(Message(user_id=user.id, thread_id=thread_id, role="user", content=message))
    await session.commit()


@router.post("/chat")
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    token = request.headers.get("authorization", "").removeprefix("Bearer ")
    thread_id = body.thread_id or uuid.uuid4().hex
    await _upsert_thread(session, user, thread_id, body.message)

    async def event_stream():
        # collect assistant text so the thread history survives a reload
        parts: list[str] = []
        async for event in handle_chat(request.app, user, token, body.message, thread_id):
            if event.get("type") == "message_delta":
                parts.append(event.get("content") or "")
            yield f"data: {json.dumps(event)}\n\n"
        if parts:
            # request-scoped session is closed by now; open a fresh one
            async with get_sessionmaker()() as s:
                s.add(Message(user_id=user.id, thread_id=thread_id, role="assistant", content="".join(parts)))
                await s.commit()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/threads")
@limiter.limit("60/minute")
async def threads(request: Request, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> list[dict]:
    result = await session.execute(select(Thread).where(Thread.user_id == user.id).order_by(Thread.updated_at.desc()))
    rows = result.scalars().all()
    return [{"thread_id": t.thread_id, "title": t.title, "updated_at": t.updated_at.isoformat()} for t in rows]


@router.get("/threads/{thread_id}/messages")
@limiter.limit("60/minute")
async def thread_messages(
    request: Request,
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    result = await session.execute(
        select(Message)
        .where(Message.user_id == user.id, Message.thread_id == thread_id)
        .order_by(Message.created_at.asc())
    )
    return [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in result.scalars().all()]


@router.delete("/threads/{thread_id}")
@limiter.limit("60/minute")
async def delete_thread(
    request: Request,
    thread_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await session.execute(delete(Message).where(Message.user_id == user.id, Message.thread_id == thread_id))
    await session.execute(delete(Thread).where(Thread.user_id == user.id, Thread.thread_id == thread_id))
    await session.commit()
    return {"ok": True}
