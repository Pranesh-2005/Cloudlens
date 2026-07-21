import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.credentials import delete_credentials, store_credentials
from app.db import User, get_session

router = APIRouter()


class CredentialsIn(BaseModel):
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-1"


@router.put("/credentials")
async def put_credentials(
    body: CredentialsIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> dict:
    # AWS access key IDs are 16-32 uppercase alphanumeric chars (AKIA.../ASIA...).
    # Catches the classic mistake of pasting the secret key into the ID field.
    if not re.fullmatch(r"[A-Z0-9]{16,32}", body.access_key_id):
        raise HTTPException(
            status_code=422,
            detail="access_key_id doesn't look like an AWS Access Key ID (expected e.g. AKIA...). "
            "Did you paste the Secret Access Key in the wrong field?",
        )
    cred = await store_credentials(session, user, body.access_key_id, body.secret_access_key, body.region)
    return {"ok": True, "last4": cred.last4}


@router.delete("/credentials")
async def remove_credentials(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)) -> dict:
    await delete_credentials(session, user)
    return {"ok": True}
