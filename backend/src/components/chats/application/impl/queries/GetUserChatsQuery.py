from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from src.components.chats.application.core.queries.IGetUserChatsQuery import IGetUserChatsQuery
from src.components.chats.infrastructure.models.ChatModel import Chat, ChatStatus


class GetUserChatsQuery(IGetUserChatsQuery):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int, limit: int = 50) -> List[Chat]:
        result = await self.db_session.execute(
            select(Chat).options(selectinload(Chat.trip))
            .where(Chat.user_id == user_id, Chat.status != ChatStatus.DELETED)
            .order_by(Chat.updated_at.desc()).limit(limit))
        return list(result.scalars().all())
