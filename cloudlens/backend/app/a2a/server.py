"""A2A protocol: agent cards + JSON-RPC message/send per agent.

POST /a2a/{agent} is also where the guardrails actually bite: prompt-injection
screening, tool-call auditing, EXECUTE-tier approval creation on interrupt, and
long-term finding writes all happen here (not in the supervisor), because this
is the one place every specialist invocation - from chat or from an external
A2A caller - passes through.
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from langgraph.types import Command
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import AGENT_NAMES, all_agent_cards, get_agent_module, initial_state
from app.audit import write_audit
from app.auth import get_current_user
from app.aws.tools import build_tool_context
from app.config import get_settings
from app.db import Approval, User, get_session
from app.guardrails import screen_text
from app.memory import build_findings_context, get_recent_findings, write_finding

router = APIRouter()

# security_auditor tool -> how to turn its JSON result into Finding rows.
_FINDING_EXTRACTORS = {
    "audit_iam_users": lambda r: [(f["kind"], f["severity"], f["resource"], f["summary"]) for f in r.get("findings", [])],
    "find_public_buckets": lambda r: [
        ("s3_public", "high", b["bucket"], "Bucket is publicly accessible.") for b in r.get("public_buckets", [])
    ],
    "find_open_security_groups": lambda r: [
        ("security_group", "high", f.get("group_id", "?"), f.get("summary", "")) for f in r.get("findings", [])
    ],
}


@router.get("/.well-known/agent-card.json")
async def platform_card() -> dict:
    return {
        "name": "CloudLens",
        "description": "Agentic cloud operations platform - cost, resources, security, deploys.",
        "agents": all_agent_cards(),
    }


@router.get("/a2a/{agent}/card")
async def agent_card(agent: str) -> dict:
    if agent not in AGENT_NAMES:
        raise HTTPException(status_code=404, detail="unknown agent")
    return get_agent_module(agent).card()


async def invoke_specialist(
    request: Request,
    session: AsyncSession,
    user: User,
    agent_name: str,
    input_: Any,
    thread_id: str,
) -> dict[str, Any]:
    settings = get_settings()
    ctx = build_tool_context(user, user.credential, settings.DEMO_SEED)
    module = get_agent_module(agent_name)
    graph = module.build(ctx, request.app.state.llm).compile(checkpointer=request.app.state.checkpointer)
    config = {"configurable": {"thread_id": f"{agent_name}:{thread_id}"}}

    start = time.monotonic()
    result = await graph.ainvoke(input_, config=config)
    latency_ms = int((time.monotonic() - start) * 1000)

    # This langgraph version doesn't surface a pending interrupt in the ainvoke()
    # return value itself - it has to be read back off the checkpointed state.
    pending_interrupt = None
    state = await graph.aget_state(config)
    for task in state.tasks:
        if task.interrupts:
            pending_interrupt = task.interrupts[0]
            break

    if pending_interrupt is not None:
        payload = pending_interrupt.value
        approval = Approval(
            user_id=user.id,
            thread_id=thread_id,
            agent=agent_name,
            action=payload["tool"],
            params=payload["args"],
            requested_by_agent=payload["agent"],
            reason=payload["reason"],
            status="pending",
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)
        await write_audit(session, user.id, agent_name, payload["tool"], payload["args"], "pending_approval", latency_ms)
        return {
            "status": "input-required",
            "approval_id": approval.id,
            "action": payload["tool"],
            "params": payload["args"],
            "reason": payload["reason"],
        }

    for entry in result.get("tool_trace", []):
        await write_audit(session, user.id, agent_name, entry["tool"], entry["args"], entry["status"], latency_ms)

    if agent_name == "security_auditor":
        for msg in result.get("messages", []):
            if msg.get("role") != "tool" or msg["name"] not in _FINDING_EXTRACTORS:
                continue
            try:
                parsed = json.loads(msg["content"])
            except (TypeError, ValueError, KeyError):
                continue
            for kind, severity, resource, summary in _FINDING_EXTRACTORS[msg["name"]](parsed):
                await write_finding(session, user.id, kind, severity, resource, summary)

    return {"status": "completed", "message": result.get("final_answer", ""), "tool_trace": result.get("tool_trace", [])}


@router.post("/a2a/{agent}")
async def a2a_message_send(
    agent: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    body = await request.json()
    rpc_id = body.get("id")
    if agent not in AGENT_NAMES:
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": "unknown agent"}}
    if body.get("method") != "message/send":
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32601, "message": "unsupported method"}}

    params = body.get("params", {})
    message = params.get("message", "")
    thread_id = params.get("thread_id") or rpc_id

    safe_message, flagged, reason = screen_text(message)
    if flagged:
        await write_audit(session, user.id, agent, "prompt_injection_screen", {"reason": reason}, "flagged")

    findings = await get_recent_findings(session, user.id, keyword=agent)
    findings_ctx = build_findings_context(findings)
    prefixed = f"{findings_ctx}\n\n{safe_message}" if findings_ctx else safe_message

    try:
        result = await invoke_specialist(request, session, user, agent, initial_state(prefixed), thread_id)
    except Exception as exc:  # noqa: BLE001
        return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": -32000, "message": str(exc)}}

    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


async def resume_specialist(
    request: Request, session: AsyncSession, user: User, approval: Approval, decision: str, note: str | None
) -> dict[str, Any]:
    return await invoke_specialist(
        request,
        session,
        user,
        approval.agent,
        Command(resume={"decision": decision, "note": note}),
        approval.thread_id,
    )
