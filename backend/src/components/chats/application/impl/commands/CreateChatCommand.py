from sqlalchemy.ext.asyncio import AsyncSession
from src.components.chats.application.core.commands.ICreateChatCommand import ICreateChatCommand
from src.components.chats.infrastructure.models.ChatModel import Chat, ChatStatus


class CreateChatCommand(ICreateChatCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, user_id: int) -> Chat:
        chat = Chat(
            user_id=user_id,
            title='Новый чат',
            status=ChatStatus.ACTIVE)
        self.db_session.add(chat)
        await self.db_session.commit()
        await self.db_session.refresh(chat)
        return chat
