from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.chats.application.core.commands.IAddMessageCommand import IAddMessageCommand
from src.components.chats.infrastructure.models.ChatMessageModel import ChatMessage, MessageRole


class AddMessageCommand(IAddMessageCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(
            self,
            chat_id: int,
            role: MessageRole,
            content: str,
            tool_name: Optional[str] = None,
            tool_call_id: Optional[str] = None) -> ChatMessage:
        message = ChatMessage(
            chat_id=chat_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id)
        self.db_session.add(message)
        await self.db_session.commit()
        await self.db_session.refresh(message)
        return message
