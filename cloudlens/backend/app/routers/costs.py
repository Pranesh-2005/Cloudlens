from fastapi import APIRouter, Depends, Request

from app.auth import get_current_user
from app.aws.tools import build_tool_context, forecast_costs, get_cost_summary, get_daily_costs
from app.config import get_settings
from app.db import User
from app.ratelimit import limiter

router = APIRouter()


@router.get("/costs/summary")
@limiter.limit("60/minute")
async def costs_summary(request: Request, days: int = 30, user: User = Depends(get_current_user)) -> dict:
    ctx = build_tool_context(user, user.credential, get_settings().DEMO_SEED)
    return await get_cost_summary(ctx, days)


@router.get("/costs/forecast")
@limiter.limit("60/minute")
async def costs_forecast(request: Request, days: int = 30, user: User = Depends(get_current_user)) -> dict:
    ctx = build_tool_context(user, user.credential, get_settings().DEMO_SEED)
    return await forecast_costs(ctx, days)
