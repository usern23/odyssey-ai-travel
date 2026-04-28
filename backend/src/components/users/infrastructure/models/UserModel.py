from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.db.base import Base

if TYPE_CHECKING:
    from src.components.users.infrastructure.models.UserProfileModel import UserProfile
    from src.components.favorites.infrastructure.models.FavoriteModel import Favorite
    from src.components.chats.infrastructure.models import Chat
    from src.components.trips.infrastructure.models import Trip


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
