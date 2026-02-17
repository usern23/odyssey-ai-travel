from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.common.configs.settings import settings
from src.common.events.rabbitmq import RabbitMQConsumer, QUEUE_CHAT_PROCESSOR, ROUTING_KEY_CHAT_MESSAGE_SAVED, ROUTING_KEY_CHAT_TITLE_UPDATED
from src.common.events.types import ChatTitleUpdateEvent, Event, MessageSavedEvent
from src.components.chats.infrastructure.models import Chat, ChatMessage, MessageRole
logger = logging.getLogger(__name__)


class ChatWorker(RabbitMQConsumer):
    queue_name = QUEUE_CHAT_PROCESSOR
    routing_keys = [
        ROUTING_KEY_CHAT_MESSAGE_SAVED,
        ROUTING_KEY_CHAT_TITLE_UPDATED]

    def __init__(
            self,
            rabbitmq_url: Optional[str] = None,
            database_url: Optional[str] = None):
        super().__init__(rabbitmq_url)
        self.database_url = database_url or settings.database_url
        self._engine = None
        self._session_factory = None

    async def connect(self) -> None:
        await super().connect()
        self._engine = create_async_engine(self.database_url)
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False)
        logger.info('Chat worker connected to database')

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
        await super().close()

    async def process_event(self, event: Event) -> None:
        async with self._session_factory() as session:
            if isinstance(event, MessageSavedEvent):
                await self._handle_message_saved(session, event)
            elif isinstance(event, ChatTitleUpdateEvent):
                await self._handle_title_update(session, event)
            else:
                logger.warning(f'Unknown event type: {event.event_type}')

    async def _handle_message_saved(
            self,
            session: AsyncSession,
            event: MessageSavedEvent) -> None:
        message = ChatMessage(
            chat_id=event.chat_id,
            role=MessageRole(
                event.role),
            content=event.content,
            metadata_=event.metadata or {})
        session.add(message)
        await session.commit()
        logger.info(
            f'Saved message to chat {
                event.chat_id}, role={
                event.role}')

    async def _handle_title_update(
            self,
            session: AsyncSession,
            event: ChatTitleUpdateEvent) -> None:
        from sqlalchemy import update
        await session.execute(update(Chat).where(Chat.id == event.chat_id).values(title=event.title))
        await session.commit()
        logger.info(f'Updated title for chat {event.chat_id}')


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    worker = ChatWorker()
    try:
        logger.info('Starting Chat Worker...')
        await worker.run()
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        worker.stop()
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
