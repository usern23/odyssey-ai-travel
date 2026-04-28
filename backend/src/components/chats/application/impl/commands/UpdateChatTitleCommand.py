from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.chats.application.core.commands.IUpdateChatTitleCommand import IUpdateChatTitleCommand
from src.components.chats.infrastructure.models.ChatModel import Chat


class UpdateChatTitleCommand(IUpdateChatTitleCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, chat_id: int, title: str) -> None:
        await self.db_session.execute(update(Chat).where(Chat.id == chat_id).values(title=title))
        await self.db_session.commit()
