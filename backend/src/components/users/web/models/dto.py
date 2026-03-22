from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, field_validator
from src.components.users.infrastructure.models import BudgetPreference, TravelStyle


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


class UserProfileBase(BaseModel):
    model_config = {'use_enum_values': True}
    travel_style: TravelStyle
    primary_interests: dict
    budget_preference: BudgetPreference
    preferred_activities: dict
    disliked_activities: dict

    @field_validator('travel_style', mode='before')
    @classmethod
    def normalize_travel_style(cls, v: str | TravelStyle):
        if isinstance(v, str):
            try:
                return TravelStyle(v.lower()).value
            except ValueError:
                pass
        return v

    @field_validator('budget_preference', mode='before')
    @classmethod
    def normalize_budget_preference(cls, v: str | BudgetPreference):
        if isinstance(v, str):
            try:
                return BudgetPreference(v.lower()).value
            except ValueError:
                pass
        return v


class UserProfileCreate(UserProfileBase):
    pass


class UserProfileRead(UserProfileBase):
    user_id: int
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserProfileUpdate(BaseModel):
    model_config = {'use_enum_values': True}
    travel_style: Optional[TravelStyle] = None
    primary_interests: Optional[dict] = None
    budget_preference: Optional[BudgetPreference] = None
    preferred_activities: Optional[dict] = None
    disliked_activities: Optional[dict] = None

    @field_validator('travel_style', mode='before')
    @classmethod
    def normalize_travel_style(cls, v: Any):
        if v is None:
            return v
        if isinstance(v, str):
            try:
                return TravelStyle(v.lower()).value
            except ValueError:
                pass
        return v

    @field_validator('budget_preference', mode='before')
    @classmethod
    def normalize_budget_preference(cls, v: Any):
        if v is None:
            return v
        if isinstance(v, str):
            try:
                return BudgetPreference(v.lower()).value
            except ValueError:
                pass
        return v


class Token(BaseModel):
    access_token: str
    token_type: str = 'bearer'


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[datetime] = None
