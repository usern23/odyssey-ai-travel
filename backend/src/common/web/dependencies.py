from __future__ import annotations
from typing import Annotated
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.security import HTTPAuthorizationCredentials
from src.infrastructure.auth import decode_access_token, bearer_scheme
from src.components.users.infrastructure.models import User
from src.infrastructure.db.session import get_db_session
from src.components.users.web.models.TokenPayload import TokenPayload
TokenDependency = Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)]
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
        credentials: TokenDependency,
        session: SessionDependency) -> User:
    payload = TokenPayload(**decode_access_token(credentials.credentials))
    if payload.sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Could not validate credentials',
            headers={
                'WWW-Authenticate': 'Bearer'})
    user_id = int(payload.sub)
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Could not validate credentials',
            headers={
                'WWW-Authenticate': 'Bearer'})
    return user
