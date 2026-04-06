from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.db.base import Base
if TYPE_CHECKING:
    from src.components.chats.infrastructure.models import Chat
    from src.components.favorites.infrastructure.models import Favorite


class ActivityLevel(str, Enum):
    """Какой отдых вам ближе?"""
    CALM = 'calm'           # Спокойный: 3-5 мест/день, ~6ч, 3.5 км/ч
    MODERATE = 'moderate'   # Умеренный: 5-8 мест/день, ~8ч, 5 км/ч
    ACTIVE = 'active'       # Насыщенный: 8-12 мест/день, ~10ч, 6 км/ч


class BudgetLevel(str, Enum):
    """Как вы относитесь к тратам на отдыхе?"""
    ECONOMY = 'economy'       # Бесплатные места, недорогие кафе
    COMFORT = 'comfort'       # Музеи, хорошие рестораны
    UNLIMITED = 'unlimited'   # Без ограничений


class AccommodationPreference(str, Enum):
    HOSTEL = 'hostel'
    HOTEL = 'hotel'
    APARTMENT = 'apartment'


# Обратная совместимость (для импортов в других модулях)
TravelStyle = ActivityLevel
BudgetPreference = BudgetLevel


# Маппинг activity_level → параметры для планировщика
ACTIVITY_LEVEL_PARAMS = {
    ActivityLevel.CALM: {'hours_per_day': 6.0, 'walking_speed_kmh': 3.5},
    ActivityLevel.MODERATE: {'hours_per_day': 8.0, 'walking_speed_kmh': 5.0},
    ActivityLevel.ACTIVE: {'hours_per_day': 10.0, 'walking_speed_kmh': 6.0},
}

# Маппинг budget_level → b_max (сумма price_levels за день) для SA-солвера
BUDGET_LEVEL_LIMITS = {
    BudgetLevel.ECONOMY: 8,
    BudgetLevel.COMFORT: 18,
    BudgetLevel.UNLIMITED: float('inf'),
}

# Категории по умолчанию для слайдеров (0–10)
DEFAULT_CATEGORY_PREFERENCES = {
    'museum': 5,
    'landmark': 5,
    'park': 5,
    'restaurant': 5,
    'cafe': 5,
    'religious': 5,
    'entertainment': 5,
    'shopping': 5,
    'nightlife': 5,
    'nature': 5,
    'viewpoint': 5,
    'beach': 5,
}

DEFAULT_LANDSCAPE_PREFERENCES = {
    'sea': 5,
    'mountains': 5,
    'city': 5,
    'village': 5,
    'forest': 5,
    'desert': 5,
}


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(
        String(1024), nullable=True)
    yandex_id: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True, index=True)
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default='UTC')
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    profile: Mapped[Optional['UserProfile']] = relationship(
        'UserProfile', back_populates='user', uselist=False, cascade='all, delete-orphan')
    trips: Mapped[list['Trip']] = relationship(
        'Trip', back_populates='user', cascade='all, delete-orphan')
    chats: Mapped[List['Chat']] = relationship(
        'Chat', back_populates='user', cascade='all, delete-orphan')
    favorites: Mapped[List['Favorite']] = relationship(
        'Favorite', back_populates='user', cascade='all, delete-orphan')


class UserProfile(Base):
    __tablename__ = 'user_profiles'
    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        primary_key=True)
    activity_level: Mapped[ActivityLevel] = mapped_column(
        SAEnum(
            ActivityLevel,
            name='activity_level_enum',
            values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=ActivityLevel.MODERATE)
    budget_level: Mapped[BudgetLevel] = mapped_column(
        SAEnum(
            BudgetLevel,
            name='budget_level_enum',
            values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=BudgetLevel.COMFORT)
    category_preferences: Mapped[dict] = mapped_column(
        JSONB, default=DEFAULT_CATEGORY_PREFERENCES.copy, nullable=False)
    landscape_preferences: Mapped[dict] = mapped_column(
        JSONB, default=DEFAULT_LANDSCAPE_PREFERENCES.copy, nullable=False)
    food_preferences: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False)
    accommodation_preference: Mapped[Optional[AccommodationPreference]] = mapped_column(
        SAEnum(
            AccommodationPreference,
            name='accommodation_preference_enum',
            values_callable=lambda obj: [e.value for e in obj]),
        nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped[User] = relationship('User', back_populates='profile')

    def get_sa_user_preferences(self) -> dict[str, float]:
        """Конвертирует category_preferences (0–10) → dict(str, float 0.0–1.0) для SA-солвера."""
        prefs = self.category_preferences or DEFAULT_CATEGORY_PREFERENCES
        return {k: v / 10.0 for k, v in prefs.items()}

    def get_hours_per_day(self) -> float:
        return ACTIVITY_LEVEL_PARAMS.get(
            self.activity_level, ACTIVITY_LEVEL_PARAMS[ActivityLevel.MODERATE]
        )['hours_per_day']

    def get_walking_speed(self) -> float:
        return ACTIVITY_LEVEL_PARAMS.get(
            self.activity_level, ACTIVITY_LEVEL_PARAMS[ActivityLevel.MODERATE]
        )['walking_speed_kmh']

    def get_budget_limit(self) -> float:
        return BUDGET_LEVEL_LIMITS.get(
            self.budget_level, BUDGET_LEVEL_LIMITS[BudgetLevel.COMFORT]
        )
