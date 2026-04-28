from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.chats.application.core.queries.IGetRecentMessagesQuery import IGetRecentMessagesQuery
from src.components.chats.infrastructure.models.ChatMessageModel import ChatMessage


class GetRecentMessagesQuery(IGetRecentMessagesQuery):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, chat_id: int, limit: int = 20) -> List[ChatMessage]:
        result = await self.db_session.execute(
            select(ChatMessage).where(ChatMessage.chat_id == chat_id)
            .order_by(ChatMessage.created_at.desc()).limit(limit))
        return list(reversed(result.scalars().all()))
