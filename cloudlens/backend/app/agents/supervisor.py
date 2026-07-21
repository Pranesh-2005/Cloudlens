"""supervisor: routes user intent to specialist agents via the A2A client.

# ponytail: intent classification is keyword-based, not an LLM call - deterministic,
# free, and testable without a fake-LLM contract for routing. Swap for an LLM router
# if routing accuracy on ambiguous phrasing becomes a real problem.
"""
from __future__ import annotations

import re

from app.agents.graph import AGENT_NAMES

_KEYWORDS: dict[str, list[str]] = {
    "deploy_operator": ["start", "stop", "scale", "deploy", "launch", "shutdown", "restart"],
    "forecaster": ["forecast", "predict", "projection", "trend", "next month", "will cost"],
    "security_auditor": ["security", "iam", "public bucket", "vulnerab", "audit", "open port", "exposed", "insecure"],
    "resource_monitor": ["ec2", "s3", "rds", "lambda", "instance", "bucket", "resource", "inventory", "cpu", "metric"],
    "cost_analyst": ["cost", "spend", "bill", "expense", "price", "budget"],
}


def classify_intent(message: str) -> str:
    text = message.lower()
    for agent, keywords in _KEYWORDS.items():
        if any(re.search(re.escape(kw), text) for kw in keywords):
            return agent
    return "general"  # small talk / unclear intent: supervisor answers directly


assert set(_KEYWORDS) == set(AGENT_NAMES)


async def handle_chat(app, user, token: str, message: str, thread_id: str):
    """Async generator of SSE-ready event dicts for POST /chat.

    Delegates to the chosen specialist over the real A2A route (in-process ASGI call),
    then synthesizes step-level events from the JSON-RPC result. The call itself is
    blocking (A2A's message/send isn't itself a stream), so message_delta arrives as
    one chunk rather than token-by-token - see llm.py for where true token streaming
    would plug in if this becomes a problem.
    """
    import time

    from app.a2a.client import send as a2a_send

    agent = classify_intent(message)
    start = time.monotonic()
    yield {"type": "agent_started", "agent": agent if agent != "general" else "supervisor"}

    if agent == "general":
        # no cloud intent detected: answer directly, don't waste a specialist round-trip
        try:
            resp = await app.state.llm.acomplete(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are CloudLens, an AWS operations assistant. Reply briefly. "
                            "You can report costs, forecasts, resources, security findings, and run "
                            "approval-gated actions when the user asks about their AWS account."
                        ),
                    },
                    {"role": "user", "content": message},
                ]
            )
            yield {"type": "message_delta", "agent": "supervisor", "content": resp.content}
        except Exception as exc:  # noqa: BLE001
            yield {"type": "error", "error": str(exc)}
            return
        yield {
            "type": "done",
            "thread_id": thread_id,
            "usage": {"tokens": getattr(resp, "tokens", 0), "latency_ms": int((time.monotonic() - start) * 1000)},
        }
        return

    try:
        result = await a2a_send(app, agent, message, thread_id, token)
    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "error": str(exc)}
        return

    for entry in result.get("tool_trace", []):
        yield {"type": "tool_called", "agent": agent, "tool": entry["tool"], "args": entry["args"]}
        yield {"type": "tool_result", "agent": agent, "tool": entry["tool"], "status": entry["status"]}

    if result.get("status") == "input-required":
        yield {
            "type": "approval_required",
            "agent": agent,
            "approval_id": result["approval_id"],
            "action": result["action"],
            "params": result["params"],
            "reason": result["reason"],
        }
        yield {
            "type": "done",
            "thread_id": thread_id,
            "usage": {"tokens": 0, "latency_ms": int((time.monotonic() - start) * 1000)},
        }
        return

    content = result.get("message", "")
    yield {"type": "message_delta", "agent": agent, "content": content}
    yield {
        "type": "done",
        "thread_id": thread_id,
        "usage": {"tokens": 0, "latency_ms": int((time.monotonic() - start) * 1000)},
    }
