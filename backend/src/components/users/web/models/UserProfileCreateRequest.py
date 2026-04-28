from typing import Any, Dict
from pydantic import BaseModel, Field, field_validator
from src.components.users.infrastructure.models import (
    ActivityLevel, BudgetLevel,
    DEFAULT_CATEGORY_PREFERENCES, DEFAULT_LANDSCAPE_PREFERENCES,
)

VALID_CATEGORIES = set(DEFAULT_CATEGORY_PREFERENCES.keys())
VALID_LANDSCAPES = set(DEFAULT_LANDSCAPE_PREFERENCES.keys())


class UserProfileCreateRequest(BaseModel):
    model_config = {'use_enum_values': True}

    activity_level: ActivityLevel
    budget_level: BudgetLevel
    category_preferences: Dict[str, int] = Field(
        default_factory=lambda: DEFAULT_CATEGORY_PREFERENCES.copy(),
        description='Интересы по категориям мест (0–10)')
    landscape_preferences: Dict[str, int] = Field(
        default_factory=lambda: DEFAULT_LANDSCAPE_PREFERENCES.copy(),
        description='Предпочтения по обстановке (0–10)')
    food_preferences: Dict[str, bool] = Field(
        default_factory=dict,
        description='Пищевые предпочтения: vegetarian, halal, local_cuisine, street_food')
    start_hour: int = Field(
        default=10, ge=7, le=12,
        description='Начало активного дня (7..12)')
    meal_count_per_day: int = Field(
        default=2, ge=1, le=3,
        description='Количество приёмов пищи в день (1..3)')

    @field_validator('activity_level', mode='before')
    @classmethod
    def normalize_activity_level(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return ActivityLevel(v.lower()).value
            except ValueError:
                pass
        return v

    @field_validator('budget_level', mode='before')
    @classmethod
    def normalize_budget_level(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return BudgetLevel(v.lower()).value
            except ValueError:
                pass
        return v

    @field_validator('category_preferences', mode='before')
    @classmethod
    def validate_category_preferences(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            return v
        for key, val in v.items():
            if key not in VALID_CATEGORIES:
                raise ValueError(f'Неизвестная категория: {key}. Допустимые: {VALID_CATEGORIES}')
            if not isinstance(val, (int, float)) or val < 0 or val > 10:
                raise ValueError(f'Значение для {key} должно быть от 0 до 10, получено: {val}')
        return {k: int(v) for k, v in v.items()}

    @field_validator('landscape_preferences', mode='before')
    @classmethod
    def validate_landscape_preferences(cls, v: Any) -> Any:
        if not isinstance(v, dict):
            return v
        for key, val in v.items():
            if key not in VALID_LANDSCAPES:
                raise ValueError(f'Неизвестный ландшафт: {key}. Допустимые: {VALID_LANDSCAPES}')
            if not isinstance(val, (int, float)) or val < 0 or val > 10:
                raise ValueError(f'Значение для {key} должно быть от 0 до 10, получено: {val}')
        return {k: int(v) for k, v in v.items()}
