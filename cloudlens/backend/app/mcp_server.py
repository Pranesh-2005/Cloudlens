"""FastMCP server exposing READ-tier AWS tools at /mcp (streamable HTTP).

Tries the official `mcp` python SDK's FastMCP first. Auth is a Bearer JWT in the
Authorization header (checked by a thin ASGI middleware that resolves the tenant
and stashes it in a contextvar so tool functions - which the MCP client sees with
only their business args, no ctx param - can build a per-tenant ToolContext).

If the SDK import/mount fails, falls back to a minimal hand-rolled JSON POST
endpoint (not full streamable-HTTP semantics, but keeps read-tool access working).
"""
from __future__ import annotations

import contextvars
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.auth import decode_token
from app.aws import tools as aws_tools
from app.aws.tools import ToolContext, build_tool_context
from app.config import get_settings
from app.db import get_sessionmaker

_current_ctx: contextvars.ContextVar[ToolContext | None] = contextvars.ContextVar("_current_ctx", default=None)

READ_TOOLS: dict[str, Any] = {
    "get_cost_summary": aws_tools.get_cost_summary,
    "get_cost_by_service": aws_tools.get_cost_by_service,
    "get_cost_by_tag": aws_tools.get_cost_by_tag,
    "get_daily_costs": aws_tools.get_daily_costs,
    "forecast_costs": aws_tools.forecast_costs,
    "list_ec2": aws_tools.list_ec2,
    "list_s3": aws_tools.list_s3,
    "list_rds": aws_tools.list_rds,
    "list_lambda": aws_tools.list_lambda,
    "get_cloudwatch_metrics": aws_tools.get_cloudwatch_metrics,
    "audit_iam_users": aws_tools.audit_iam_users,
    "find_public_buckets": aws_tools.find_public_buckets,
    "find_open_security_groups": aws_tools.find_open_security_groups,
}


async def _resolve_ctx_from_token(token: str) -> ToolContext:
    user_id = decode_token(token)
    sm = get_sessionmaker()
    async with sm() as session:
        from app.db import User

        user = await session.get(User, user_id)
        if user is None:
            raise ValueError("unknown user")
        return build_tool_context(user, user.credential, get_settings().DEMO_SEED)


def _try_build_fastmcp_app():
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("cloudlens", stateless_http=True)

    def _make_tool(name: str, fn):
        async def _tool(**kwargs) -> dict:
            ctx = _current_ctx.get()
            if ctx is None:
                raise RuntimeError("missing tenant context - MCP auth middleware did not run")
            return await fn(ctx, **kwargs)

        _tool.__name__ = name
        _tool.__doc__ = fn.__doc__
        return _tool

    for name, fn in READ_TOOLS.items():
        server.tool(name=name)(_make_tool(name, fn))

    if hasattr(server, "streamable_http_app"):
        inner = server.streamable_http_app()
    else:  # older SDK versions
        inner = server.sse_app()

    async def auth_middleware(scope, receive, send):
        if scope["type"] != "http":
            await inner(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode()
        if not auth.startswith("Bearer "):
            resp = JSONResponse({"error": "missing bearer token"}, status_code=401)
            await resp(scope, receive, send)
            return
        try:
            ctx = await _resolve_ctx_from_token(auth.removeprefix("Bearer "))
        except Exception:
            resp = JSONResponse({"error": "invalid token"}, status_code=401)
            await resp(scope, receive, send)
            return
        token_ref = _current_ctx.set(ctx)
        try:
            await inner(scope, receive, send)
        finally:
            _current_ctx.reset(token_ref)

    return auth_middleware


async def _fallback_call_tool(request: StarletteRequest) -> JSONResponse:
    """Minimal hand-rolled fallback: POST {"tool": name, "args": {...}} -> result."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse({"error": "missing bearer token"}, status_code=401)
    try:
        ctx = await _resolve_ctx_from_token(auth.removeprefix("Bearer "))
    except Exception:
        return JSONResponse({"error": "invalid token"}, status_code=401)

    body = await request.json()
    tool = body.get("tool")
    if tool not in READ_TOOLS:
        return JSONResponse({"error": f"unknown or non-READ tool: {tool}"}, status_code=400)
    result = await READ_TOOLS[tool](ctx, **body.get("args", {}))
    return JSONResponse(result)


async def _fallback_list_tools(request: StarletteRequest) -> JSONResponse:
    return JSONResponse({"tools": list(READ_TOOLS)})


def build_mcp_app():
    """Returns an ASGI app to mount at /mcp. Prefers the official mcp SDK."""
    try:
        return _try_build_fastmcp_app()
    except Exception:
        # ponytail: hand-rolled fallback, upgrade path is fixing the `mcp` SDK install.
        return Starlette(
            routes=[
                Route("/", _fallback_list_tools, methods=["GET"]),
                Route("/call", _fallback_call_tool, methods=["POST"]),
            ]
        )
