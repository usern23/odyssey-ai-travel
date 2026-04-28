from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.chats.application.core.commands.ILinkTripToChatCommand import ILinkTripToChatCommand
from src.components.chats.infrastructure.models.ChatModel import Chat


class LinkTripToChatCommand(ILinkTripToChatCommand):

    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def __call__(self, chat_id: int, trip_id: int) -> None:
        await self.db_session.execute(update(Chat).where(Chat.id == chat_id).values(trip_id=trip_id))
        await self.db_session.commit()
