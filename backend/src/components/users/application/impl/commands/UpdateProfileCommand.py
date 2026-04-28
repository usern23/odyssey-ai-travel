from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.users.application.core.commands.IUpdateProfileCommand import IUpdateProfileCommand
from src.components.users.infrastructure.models.UserProfileModel import UserProfile
from src.components.users.web.models.UserProfileUpdateRequest import UserProfileUpdateRequest


class UpdateProfileCommand(IUpdateProfileCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int, payload: UserProfileUpdateRequest) -> Optional[UserProfile]:
        result = await self.db_session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id))
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(profile, field, value)
        await self.db_session.commit()
        await self.db_session.refresh(profile)
        return profile
