from __future__ import annotations
import enum
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.db.base import Base

if TYPE_CHECKING:
    from src.components.favorites.infrastructure.models.FavoriteModel import Favorite
    from src.components.trips.infrastructure.models import Trip
    from src.components.users.infrastructure.models import User


class ChatStatus(str, enum.Enum):
    ACTIVE = 'active'
    ARCHIVED = 'archived'
    DELETED = 'deleted'


class Chat(Base):
    __tablename__ = 'chats'
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False)
    trip_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey('trips.id', ondelete='SET NULL'), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default='Новый чат')
    status: Mapped[ChatStatus] = mapped_column(
        PgEnum(
            ChatStatus,
            name='chat_status_enum',
            create_type=False,
            values_callable=lambda x: [
                e.value for e in x]),
        default=ChatStatus.ACTIVE,
        nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(
            timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False)
    user: Mapped['User'] = relationship(back_populates='chats')
    trip: Mapped[Optional['Trip']] = relationship(back_populates='chats')
    messages: Mapped[List['ChatMessage']] = relationship(
        back_populates='chat', cascade='all, delete-orphan', order_by='ChatMessage.created_at')
    favorites: Mapped[List['Favorite']] = relationship(
        back_populates='chat', cascade='all, delete-orphan')

    def __repr__(self) -> str:
        return f"<Chat(id={self.id}, title='{self.title}', trip_id={self.trip_id})>"


# Import ChatMessage here so forward ref 'ChatMessage' in relationship resolves
from src.components.chats.infrastructure.models.ChatMessageModel import ChatMessage  # noqa: E402, F401
