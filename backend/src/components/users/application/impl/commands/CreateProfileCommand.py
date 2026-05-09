from sqlalchemy.ext.asyncio import AsyncSession
from src.components.users.application.core.commands.ICreateProfileCommand import ICreateProfileCommand
from src.components.users.infrastructure.models.UserProfileModel import UserProfile
from src.components.users.web.models.UserProfileCreateRequest import UserProfileCreateRequest


class CreateProfileCommand(ICreateProfileCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int, payload: UserProfileCreateRequest) -> UserProfile:
        profile = UserProfile(
            user_id=user_id,
            activity_level=payload.activity_level,
            budget_level=payload.budget_level,
            category_preferences=payload.category_preferences,
            landscape_preferences=payload.landscape_preferences,
            food_preferences=payload.food_preferences,
            start_hour=payload.start_hour,
            end_hour=payload.end_hour,
            meal_count_per_day=payload.meal_count_per_day)
        self.db_session.add(profile)
        await self.db_session.commit()
        await self.db_session.refresh(profile)
        return profile
