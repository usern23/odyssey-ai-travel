from __future__ import annotations
from typing import Optional
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.users.infrastructure.models import User, UserProfile


class UserRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def add(self, user: User) -> None:
        self.session.add(user)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()

    async def refresh(self, entity) -> None:
        await self.session.refresh(entity)

    async def get_profile(self, user_id: int) -> Optional[UserProfile]:
        result = await self.session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        return result.scalar_one_or_none()

    async def add_profile(self, profile: UserProfile) -> None:
        self.session.add(profile)


def get_user_repository(session: AsyncSession) -> UserRepository:
    return UserRepository(session)
