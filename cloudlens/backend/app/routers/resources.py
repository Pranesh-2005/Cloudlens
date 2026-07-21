from fastapi import APIRouter, Depends, Request

from app.auth import get_current_user
from app.aws.tools import build_tool_context, list_all_resources, list_ec2, list_lambda, list_rds, list_s3
from app.config import get_settings
from app.db import User
from app.ratelimit import limiter

router = APIRouter()


@router.get("/resources")
@limiter.limit("60/minute")
async def resources(request: Request, user: User = Depends(get_current_user)) -> dict:
    ctx = build_tool_context(user, user.credential, get_settings().DEMO_SEED)
    ec2 = await list_ec2(ctx)
    s3 = await list_s3(ctx)
    rds = await list_rds(ctx)
    lam = await list_lambda(ctx)
    try:
        everything = (await list_all_resources(ctx))["items"]
    except Exception:
        # tag:GetResources permission may not be granted yet — degrade gracefully
        everything = []
    return {
        "all": everything,
        "ec2": ec2["items"],
        "s3": s3["items"],
        "rds": rds["items"],
        "lambda": lam["items"],
        "demo": ctx.demo,
    }
