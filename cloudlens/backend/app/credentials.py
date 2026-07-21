"""Fernet-encrypted AWS credential storage."""
from __future__ import annotations

from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import Credential, User


def _fernet() -> Fernet:
    return Fernet(get_settings().ENCRYPTION_KEY.encode())


async def store_credentials(
    session: AsyncSession, user: User, access_key_id: str, secret_access_key: str, region: str
) -> Credential:
    f = _fernet()
    cred = user.credential
    if cred is None:
        cred = Credential(user_id=user.id)
        session.add(cred)
    cred.access_key_id_enc = f.encrypt(access_key_id.encode()).decode()
    cred.secret_access_key_enc = f.encrypt(secret_access_key.encode()).decode()
    cred.region = region
    cred.last4 = access_key_id[-4:]
    await session.commit()
    await session.refresh(cred)
    return cred


async def delete_credentials(session: AsyncSession, user: User) -> None:
    if user.credential is not None:
        await session.delete(user.credential)
        await session.commit()


def decrypt(cred: Credential) -> tuple[str, str]:
    f = _fernet()
    access_key_id = f.decrypt(cred.access_key_id_enc.encode()).decode()
    secret_access_key = f.decrypt(cred.secret_access_key_enc.encode()).decode()
    return access_key_id, secret_access_key
