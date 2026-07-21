from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, get_current_user, get_user_by_email, hash_password, verify_password
from app.db import User, get_session
from app.ratelimit import limiter

router = APIRouter()


class RegisterIn(BaseModel):
    email: str
    password: str


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    token: str


@router.post("/auth/register", response_model=TokenOut)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    existing = await get_user_by_email(session, body.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    user = User(email=body.email, password_hash=hash_password(body.password))
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return TokenOut(token=create_access_token(user.id))


@router.post("/auth/login", response_model=TokenOut)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    user = await get_user_by_email(session, body.email)
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return TokenOut(token=create_access_token(user.id))


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "email": user.email,
        "created_at": user.created_at.isoformat(),
        "has_aws_credentials": user.credential is not None,
        "demo_mode": user.credential is None,
    }
