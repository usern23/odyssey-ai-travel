from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.components.chats.application.core.queries.IGetChatQuery import IGetChatQuery
from src.components.chats.infrastructure.models.ChatModel import Chat, ChatStatus


class GetChatQuery(IGetChatQuery):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, chat_id: int, user_id: int) -> Optional[Chat]:
        result = await self.db_session.execute(
            select(Chat).options(selectinload(Chat.trip))
            .where(Chat.id == chat_id, Chat.user_id == user_id, Chat.status != ChatStatus.DELETED))
        return result.scalar_one_or_none()
