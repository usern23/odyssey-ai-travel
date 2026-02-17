from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.db.base import Base
if TYPE_CHECKING:
    from src.components.chats.infrastructure.models import Chat
    from src.components.users.infrastructure.models import User


class Favorite(Base):
    __tablename__ = 'favorites'
    __table_args__ = (
        UniqueConstraint(
            'user_id',
            'chat_id',
            name='uq_user_chat_favorite'),
    )
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            'users.id',
            ondelete='CASCADE'),
        nullable=False)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey(
            'chats.id',
            ondelete='CASCADE'),
        nullable=False)
    custom_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    user: Mapped['User'] = relationship(back_populates='favorites')
    chat: Mapped['Chat'] = relationship(back_populates='favorites')

    def __repr__(self) -> str:
        return f'<Favorite(id={
            self.id}, user_id={
            self.user_id}, chat_id={
            self.chat_id})>'
