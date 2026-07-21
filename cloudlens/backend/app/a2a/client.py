"""A2A client used by the supervisor to delegate to specialists.

Calls POST /a2a/{agent} in-process over ASGI (httpx.ASGITransport) - real HTTP/JSON-RPC
shape and routing, no real network hop or port guessing needed for a same-process call.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx


async def send(app, agent: str, message: str, thread_id: str, token: str) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://cloudlens.local") as client:
        payload = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex,
            "method": "message/send",
            "params": {"message": message, "thread_id": thread_id},
        }
        resp = await client.post(f"/a2a/{agent}", json=payload, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        body = resp.json()
        if "error" in body:
            raise RuntimeError(body["error"])
        return body["result"]
