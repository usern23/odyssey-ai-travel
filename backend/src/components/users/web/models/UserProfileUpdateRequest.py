from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator
from src.components.users.infrastructure.models import (
    ActivityLevel, BudgetLevel,
    DEFAULT_CATEGORY_PREFERENCES, DEFAULT_LANDSCAPE_PREFERENCES,
)

VALID_CATEGORIES = set(DEFAULT_CATEGORY_PREFERENCES.keys())
VALID_LANDSCAPES = set(DEFAULT_LANDSCAPE_PREFERENCES.keys())


class UserProfileUpdateRequest(BaseModel):
    model_config = {'use_enum_values': True}

    activity_level: Optional[ActivityLevel] = None
    budget_level: Optional[BudgetLevel] = None
    category_preferences: Optional[Dict[str, int]] = None
    landscape_preferences: Optional[Dict[str, int]] = None
    food_preferences: Optional[Dict[str, bool]] = None
    start_hour: Optional[int] = Field(default=None, ge=7, le=12)
    meal_count_per_day: Optional[int] = Field(default=None, ge=1, le=3)

    @field_validator('activity_level', mode='before')
    @classmethod
    def normalize_activity_level(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, str):
            try:
                return ActivityLevel(v.lower()).value
            except ValueError:
                pass
        return v

    @field_validator('budget_level', mode='before')
    @classmethod
    def normalize_budget_level(cls, v: Any) -> Any:
        if v is None:
            return v
        if isinstance(v, str):
            try:
                return BudgetLevel(v.lower()).value
            except ValueError:
                pass
        return v

    @field_validator('category_preferences', mode='before')
    @classmethod
    def validate_category_preferences(cls, v: Any) -> Any:
        if v is None:
            return v
        if not isinstance(v, dict):
            return v
        for key, val in v.items():
            if key not in VALID_CATEGORIES:
                raise ValueError(f'Неизвестная категория: {key}')
            if not isinstance(val, (int, float)) or val < 0 or val > 10:
                raise ValueError(f'Значение для {key} должно быть от 0 до 10')
        return {k: int(v) for k, v in v.items()}

    @field_validator('landscape_preferences', mode='before')
    @classmethod
    def validate_landscape_preferences(cls, v: Any) -> Any:
        if v is None:
            return v
        if not isinstance(v, dict):
            return v
        for key, val in v.items():
            if key not in VALID_LANDSCAPES:
                raise ValueError(f'Неизвестный ландшафт: {key}')
            if not isinstance(val, (int, float)) or val < 0 or val > 10:
                raise ValueError(f'Значение для {key} должно быть от 0 до 10')
        return {k: int(v) for k, v in v.items()}
