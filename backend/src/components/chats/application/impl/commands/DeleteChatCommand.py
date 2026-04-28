from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.chats.application.core.commands.IDeleteChatCommand import IDeleteChatCommand
from src.components.chats.infrastructure.models.ChatModel import Chat, ChatStatus


class DeleteChatCommand(IDeleteChatCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, chat_id: int, user_id: int) -> bool:
        result = await self.db_session.execute(
            update(Chat).where(Chat.id == chat_id, Chat.user_id == user_id).values(status=ChatStatus.DELETED))
        await self.db_session.commit()
        return result.rowcount > 0
