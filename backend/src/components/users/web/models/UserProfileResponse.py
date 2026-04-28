from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel
from src.components.users.infrastructure.models import ActivityLevel, BudgetLevel


class UserProfileResponse(BaseModel):
    model_config = {'from_attributes': True, 'use_enum_values': True}

    user_id: int
    activity_level: ActivityLevel
    budget_level: BudgetLevel
    category_preferences: Dict[str, int]
    landscape_preferences: Dict[str, int]
    food_preferences: Dict[str, bool]
    start_hour: int = 10
    meal_count_per_day: int = 2
    updated_at: Optional[datetime] = None
