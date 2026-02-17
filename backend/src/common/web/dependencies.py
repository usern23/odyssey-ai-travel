from __future__ import annotations
from typing import Annotated
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.auth import decode_access_token, oauth2_scheme
from src.components.users.infrastructure.models import User
from src.components.users.infrastructure.repositories import get_user_repository
from src.infrastructure.db.session import get_db_session
from src.components.users.web.models.dto import TokenPayload
TokenDependency = Annotated[str, Depends(oauth2_scheme)]
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
        token: TokenDependency,
        session: SessionDependency) -> User:
    payload = TokenPayload(**decode_access_token(token))
    if payload.sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Could not validate credentials',
            headers={
                'WWW-Authenticate': 'Bearer'})
    user_id = int(payload.sub)
    repo = get_user_repository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Could not validate credentials',
            headers={
                'WWW-Authenticate': 'Bearer'})
    return user
