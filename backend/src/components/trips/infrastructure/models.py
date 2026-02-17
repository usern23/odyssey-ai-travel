from __future__ import annotations
from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.db.base import Base
if TYPE_CHECKING:
    from src.components.chats.infrastructure.models import Chat


class Trip(Base):
    __tablename__ = 'trips'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False,
        index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    destination: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True)
    origin: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    trip_profile: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False)
    generated_plan: Mapped[Optional[dict]
                           ] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(
            timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False)
    user: Mapped['User'] = relationship('User', back_populates='trips')
    chats: Mapped[List['Chat']] = relationship('Chat', back_populates='trip')

    def __repr__(self) -> str:
        return f"<Trip(id={
            self.id}, destination='{
            self.destination}', user_id={
            self.user_id})>"
