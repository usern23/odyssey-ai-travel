from __future__ import annotations
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.db.base import Base
if TYPE_CHECKING:
    from src.components.chats.infrastructure.models.ChatModel import Chat


class MessageRole(str, enum.Enum):
    USER = 'user'
    ASSISTANT = 'assistant'
    SYSTEM = 'system'
    TOOL = 'tool'


class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chat_id: Mapped[int] = mapped_column(
        ForeignKey(
            'chats.id',
            ondelete='CASCADE'),
        nullable=False)
    role: Mapped[MessageRole] = mapped_column(
        PgEnum(
            MessageRole,
            name='message_role_enum',
            create_type=False,
            values_callable=lambda x: [
                e.value for e in x]),
        nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True)
    tool_call_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    chat: Mapped['Chat'] = relationship(back_populates='messages')

    def __repr__(self) -> str:
        content_preview = self.content[:50] + \
            '...' if len(self.content) > 50 else self.content
        return f"<ChatMessage(id={self.id}, role={self.role}, content='{content_preview}')>"
