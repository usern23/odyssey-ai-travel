from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from src.components.users.infrastructure.models import (
    ActivityLevel, BudgetLevel, AccommodationPreference,
    DEFAULT_CATEGORY_PREFERENCES, DEFAULT_LANDSCAPE_PREFERENCES,
)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    timezone: str = 'UTC'


class UserRead(BaseModel):
    id: int
    email: EmailStr
    timezone: str
    created_at: datetime

    class Config:
        from_attributes = True


VALID_CATEGORIES = set(DEFAULT_CATEGORY_PREFERENCES.keys())
VALID_LANDSCAPES = set(DEFAULT_LANDSCAPE_PREFERENCES.keys())


class UserProfileBase(BaseModel):
    model_config = {'use_enum_values': True}
    activity_level: ActivityLevel
    budget_level: BudgetLevel
    category_preferences: Dict[str, int] = Field(
        default_factory=lambda: DEFAULT_CATEGORY_PREFERENCES.copy(),
        description='Интересы по категориям мест (0–10). Ключи: museum, landmark, park, restaurant, cafe, religious, entertainment, shopping, nightlife, nature, viewpoint, beach')
    landscape_preferences: Dict[str, int] = Field(
        default_factory=lambda: DEFAULT_LANDSCAPE_PREFERENCES.copy(),
        description='Предпочтения по обстановке (0–10). Ключи: sea, mountains, city, village, forest, desert')
    food_preferences: Dict[str, bool] = Field(
        default_factory=dict,
        description='Пищевые предпочтения: vegetarian, halal, local_cuisine, street_food')
    accommodation_preference: Optional[AccommodationPreference] = None

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


class UserProfileCreate(UserProfileBase):
    pass


class UserProfileRead(UserProfileBase):
    user_id: int
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    model_config = {'use_enum_values': True}
    activity_level: Optional[ActivityLevel] = None
    budget_level: Optional[BudgetLevel] = None
    category_preferences: Optional[Dict[str, int]] = None
    landscape_preferences: Optional[Dict[str, int]] = None
    food_preferences: Optional[Dict[str, bool]] = None
    accommodation_preference: Optional[AccommodationPreference] = None

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


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[datetime] = None
