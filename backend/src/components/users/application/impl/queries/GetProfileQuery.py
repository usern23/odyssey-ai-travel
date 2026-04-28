from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.users.application.core.queries.IGetProfileQuery import IGetProfileQuery
from src.components.users.infrastructure.models.UserProfileModel import UserProfile


class GetProfileQuery(IGetProfileQuery):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int) -> Optional[UserProfile]:
        result = await self.db_session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id))
        return result.scalar_one_or_none()
