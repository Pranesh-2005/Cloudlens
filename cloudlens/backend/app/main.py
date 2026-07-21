"""FastAPI app factory, CORS, middleware, routers."""
from __future__ import annotations

from contextlib import asynccontextmanager

from botocore.exceptions import ClientError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.db import init_db
from app.llm import build_llm
from app.mcp_server import build_mcp_app
from app.memory import build_checkpointer
from app.ratelimit import limiter
from app.routers import approvals, audit as audit_router, auth, chat, costs, credentials, health, resources, security


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db()
    app.state.llm = build_llm(settings)
    async with build_checkpointer(settings) as checkpointer:
        app.state.checkpointer = checkpointer
        yield


async def _aws_client_error_handler(request: Request, exc: ClientError) -> JSONResponse:
    code = exc.response.get("Error", {}).get("Code", "AWSError")
    message = exc.response.get("Error", {}).get("Message", str(exc))
    status = 403 if "AccessDenied" in code or "UnauthorizedOperation" in code else 502
    return JSONResponse(status_code=status, content={"detail": f"AWS error ({code}): {message}"})


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="CloudLens", lifespan=lifespan)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_exception_handler(ClientError, _aws_client_error_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.FRONTEND_ORIGIN],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # root-level: exempt from auth per guardrails (healthz, .well-known/*, a2a, mcp)
    app.include_router(health.router)

    api = "/api/v1"
    app.include_router(auth.router, prefix=api)
    app.include_router(chat.router, prefix=api)
    app.include_router(costs.router, prefix=api)
    app.include_router(resources.router, prefix=api)
    app.include_router(security.router, prefix=api)
    app.include_router(approvals.router, prefix=api)
    app.include_router(audit_router.router, prefix=api)
    app.include_router(credentials.router, prefix=api)

    # a2a mounted lazily so tests can override app.state before agent cards render
    from app.a2a.server import router as a2a_router

    app.include_router(a2a_router)
    app.mount("/mcp", build_mcp_app())

    return app


app = create_app()
