from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.common.configs.settings import settings
from src.common.events.rabbitmq import RabbitMQConsumer, QUEUE_FAVORITES_PROCESSOR, ROUTING_KEY_FAVORITES_ADDED, ROUTING_KEY_FAVORITES_REMOVED
from src.common.events.types import AddToFavoritesEvent, Event, RemoveFromFavoritesEvent
from src.components.favorites.infrastructure.models import Favorite
logger = logging.getLogger(__name__)


class FavoritesWorker(RabbitMQConsumer):
    queue_name = QUEUE_FAVORITES_PROCESSOR
    routing_keys = [ROUTING_KEY_FAVORITES_ADDED, ROUTING_KEY_FAVORITES_REMOVED]

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
            elif isinstance(event, RemoveFromFavoritesEvent):
                await self._handle_remove_favorite(session, event)
            else:
                logger.warning(f'Unknown event type: {event.event_type}')

    async def _handle_add_favorite(
            self,
            session: AsyncSession,
            event: AddToFavoritesEvent) -> None:
        existing = await session.execute(select(Favorite).where(Favorite.user_id == event.user_id, Favorite.chat_id == event.chat_id))
        if existing.scalar_one_or_none():
            logger.info(
                f'Favorite already exists: user={
                    event.user_id}, chat={
                    event.chat_id}')
            return
        favorite = Favorite(user_id=event.user_id, chat_id=event.chat_id)
        session.add(favorite)
        await session.commit()
        logger.info(
            f'Added favorite: user={
                event.user_id}, chat={
                event.chat_id}')

    async def _handle_remove_favorite(
            self,
            session: AsyncSession,
            event: RemoveFromFavoritesEvent) -> None:
        await session.execute(delete(Favorite).where(Favorite.user_id == event.user_id, Favorite.chat_id == event.chat_id))
        await session.commit()
        logger.info(
            f'Removed favorite: user={
                event.user_id}, chat={
                event.chat_id}')


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
