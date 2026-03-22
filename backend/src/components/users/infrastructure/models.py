from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.db.base import Base
if TYPE_CHECKING:
    from src.components.chats.infrastructure.models import Chat
    from src.components.favorites.infrastructure.models import Favorite


class TravelStyle(str, Enum):
    RELAXED = 'relaxed'
    FAST_PACED = 'fast_paced'
    BALANCED = 'balanced'


class BudgetPreference(str, Enum):
    BUDGET = 'budget'
    MID_RANGE = 'mid_range'
    LUXURY = 'luxury'


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
    travel_style: Mapped[TravelStyle] = mapped_column(
        SAEnum(
            TravelStyle,
            name='travel_style_enum',
            values_callable=lambda obj: [
                e.value for e in obj]),
        nullable=False)
    primary_interests: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False)
    budget_preference: Mapped[BudgetPreference] = mapped_column(
        SAEnum(
            BudgetPreference,
            name='budget_preference_enum',
            values_callable=lambda obj: [
                e.value for e in obj]),
        nullable=False)
    preferred_activities: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False)
    disliked_activities: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user: Mapped[User] = relationship('User', back_populates='profile')
