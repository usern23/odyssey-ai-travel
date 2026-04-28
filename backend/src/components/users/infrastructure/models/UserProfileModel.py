from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.db.base import Base


class ActivityLevel(str, Enum):
    CALM = 'calm'
    MODERATE = 'moderate'
    ACTIVE = 'active'


class BudgetLevel(str, Enum):
    ECONOMY = 'economy'
    COMFORT = 'comfort'
    UNLIMITED = 'unlimited'


TravelStyle = ActivityLevel
BudgetPreference = BudgetLevel

ACTIVITY_LEVEL_PARAMS = {
    # hours_per_day — верхняя граница «активного» времени (посещения + переезды).
    # Фактический бюджет капается (end_of_day − start_hour) в TravelPlanService.
    # places_per_day — целевое число мест в день (нижний порог для solver).
    ActivityLevel.CALM: {'hours_per_day': 8.0, 'places_per_day': 5},
    ActivityLevel.MODERATE: {'hours_per_day': 11.0, 'places_per_day': 8},
    ActivityLevel.ACTIVE: {'hours_per_day': 14.0, 'places_per_day': 10},
}

BUDGET_LEVEL_LIMITS = {
    BudgetLevel.ECONOMY: 8,
    BudgetLevel.COMFORT: 18,
    BudgetLevel.UNLIMITED: float('inf'),
}

DEFAULT_CATEGORY_PREFERENCES = {
    'museum': 5, 'landmark': 5, 'park': 5, 'restaurant': 5,
    'cafe': 5, 'religious': 5, 'entertainment': 5, 'shopping': 5,
    'nightlife': 5, 'nature': 5, 'viewpoint': 5, 'beach': 5,
}

DEFAULT_LANDSCAPE_PREFERENCES = {
    'sea': 5, 'mountains': 5, 'city': 5,
    'village': 5, 'forest': 5, 'desert': 5,
}


class UserProfile(Base):
    __tablename__ = 'user_profiles'
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    activity_level: Mapped[ActivityLevel] = mapped_column(
        SAEnum(ActivityLevel, name='activity_level_enum',
               values_callable=lambda obj: [e.value for e in obj]),
        nullable=False, default=ActivityLevel.MODERATE)
    budget_level: Mapped[BudgetLevel] = mapped_column(
        SAEnum(BudgetLevel, name='budget_level_enum',
               values_callable=lambda obj: [e.value for e in obj]),
        nullable=False, default=BudgetLevel.COMFORT)
    category_preferences: Mapped[dict] = mapped_column(
        JSONB, default=DEFAULT_CATEGORY_PREFERENCES.copy, nullable=False)
    landscape_preferences: Mapped[dict] = mapped_column(
        JSONB, default=DEFAULT_LANDSCAPE_PREFERENCES.copy, nullable=False)
    food_preferences: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False)
    start_hour: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default='10')
    meal_count_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default='2')
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped['User'] = relationship('User', back_populates='profile')

    def get_sa_user_preferences(self) -> dict[str, float]:
        prefs = self.category_preferences or DEFAULT_CATEGORY_PREFERENCES
        return {k: v / 10.0 for k, v in prefs.items()}

    def get_hours_per_day(self) -> float:
        return ACTIVITY_LEVEL_PARAMS.get(
            self.activity_level, ACTIVITY_LEVEL_PARAMS[ActivityLevel.MODERATE]
        )['hours_per_day']

    def get_places_per_day(self) -> int:
        return ACTIVITY_LEVEL_PARAMS.get(
            self.activity_level, ACTIVITY_LEVEL_PARAMS[ActivityLevel.MODERATE]
        )['places_per_day']

    def get_budget_limit(self) -> float:
        return BUDGET_LEVEL_LIMITS.get(
            self.budget_level, BUDGET_LEVEL_LIMITS[BudgetLevel.COMFORT]
        )


from src.components.users.infrastructure.models.UserModel import User  # noqa: E402, F401
