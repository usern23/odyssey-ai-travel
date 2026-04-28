from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.chats.application.core.queries.IGetUserProfileQuery import IGetUserProfileQuery
from src.components.users.infrastructure.models import UserProfile


class GetUserProfileQuery(IGetUserProfileQuery):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int) -> Optional[Dict[str, Any]]:
        result = await self.db_session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
        profile = result.scalar_one_or_none()
        if not profile:
            return None
        return {
            'user_id': profile.user_id,
            'activity_level': profile.activity_level.value if hasattr(profile.activity_level, 'value') else profile.activity_level,
            'budget_level': profile.budget_level.value if hasattr(profile.budget_level, 'value') else profile.budget_level,
            'category_preferences': profile.category_preferences,
            'landscape_preferences': profile.landscape_preferences,
            'food_preferences': profile.food_preferences,
            'start_hour': profile.start_hour,
            'meal_count_per_day': profile.meal_count_per_day,
        }
