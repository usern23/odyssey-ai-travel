from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.common.configs.settings import settings
from src.common.events.rabbitmq import RabbitMQConsumer, QUEUE_FAVORITES_PROCESSOR, ROUTING_KEY_FAVORITES_ADDED
from src.common.events.types import AddToFavoritesEvent, Event
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite
from src.components.users.infrastructure.models import User  # noqa: F401
from src.components.chats.infrastructure.models import Chat  # noqa: F401
from src.components.trips.infrastructure.models import Trip  # noqa: F401
logger = logging.getLogger(__name__)


class FavoritesWorker(RabbitMQConsumer):
    queue_name = QUEUE_FAVORITES_PROCESSOR
    routing_keys = [ROUTING_KEY_FAVORITES_ADDED]

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
        logger.info('Favorites worker connected to database')

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
        await super().close()

    async def process_event(self, event: Event) -> None:
        async with self._session_factory() as session:
            if isinstance(event, AddToFavoritesEvent):
                await self._handle_add_favorite(session, event)
            else:
                logger.warning('Unknown event type: %s', event.event_type)

    async def _handle_add_favorite(
            self,
            session: AsyncSession,
            event: AddToFavoritesEvent) -> None:
        existing = await session.execute(
            select(Favorite).where(
                Favorite.user_id == event.user_id,
                Favorite.chat_id == event.chat_id))
        if existing.scalar_one_or_none():
            logger.info(
                'Favorite already exists: user=%d, chat=%d',
                event.user_id, event.chat_id)
            return
        favorite = Favorite(
            user_id=event.user_id, chat_id=event.chat_id)
        session.add(favorite)
        await session.commit()
        logger.info(
            'Added favorite: user=%d, chat=%d',
            event.user_id, event.chat_id)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    worker = FavoritesWorker()
    try:
        logger.info('Starting Favorites Worker...')
        await worker.run()
    except KeyboardInterrupt:
        logger.info('Shutting down...')
        worker.stop()
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
