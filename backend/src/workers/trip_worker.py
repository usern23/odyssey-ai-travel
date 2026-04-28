from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.common.configs.settings import settings
from src.common.events.rabbitmq import RabbitMQConsumer, QUEUE_TRIP_PROCESSOR, ROUTING_KEY_TRIP_DATA_COLLECTED, ROUTING_KEY_TRIP_PLAN_GENERATED
from src.common.events.types import Event, TripDataCollectedEvent, TravelPlanGeneratedEvent
from src.components.chats.infrastructure.models import Chat
from src.components.trips.infrastructure.models import Trip
from src.components.users.infrastructure.models import User  # noqa: F401 — needed for SQLAlchemy relationship resolution
from src.components.favorites.infrastructure.models.FavoriteModel import Favorite  # noqa: F401
logger = logging.getLogger(__name__)


class TripWorker(RabbitMQConsumer):
    queue_name = QUEUE_TRIP_PROCESSOR
    routing_keys = [
        ROUTING_KEY_TRIP_DATA_COLLECTED,
        ROUTING_KEY_TRIP_PLAN_GENERATED]

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
        logger.info('Trip worker connected to database')

    async def close(self) -> None:
        if self._engine:
            await self._engine.dispose()
        await super().close()

    async def process_event(self, event: Event) -> None:
        handlers = {
            'TripDataCollectedEvent': self._handle_trip_data_collected,
            'TravelPlanGeneratedEvent': self._handle_plan_generated}
        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)
        else:
            logger.warning(f'No handler for event type: {event.event_type}')

    async def _handle_trip_data_collected(
            self, event: TripDataCollectedEvent) -> None:
        async with self._session_factory() as session:
            start_date = datetime.fromisoformat(
                event.start_date).date() if event.start_date else None
            end_date = datetime.fromisoformat(
                event.end_date).date() if event.end_date else None
            trip_profile = {
                'budget': event.budget,
                'origin': event.origin,
                'travelers_count': event.travelers_count,
                'travel_style': event.travel_style}
            if event.interests:
                try:
                    trip_profile['interests'] = json.loads(event.interests)
                except json.JSONDecodeError:
                    trip_profile['interests'] = []
            if event.special_requirements:
                try:
                    trip_profile['special_requirements'] = json.loads(
                        event.special_requirements)
                except json.JSONDecodeError:
                    trip_profile['special_requirements'] = {}
            trip = Trip(
                user_id=event.user_id,
                name=f'Поездка в {event.destination}',
                destination=event.destination,
                origin=event.origin,
                start_date=start_date,
                end_date=end_date,
                trip_profile=trip_profile,
                generated_plan={})
            session.add(trip)
            await session.commit()
            await session.refresh(trip)
            logger.info(
                f'Created Trip {trip.id} for user {event.user_id}: {event.destination}, {start_date} - {end_date}')
            await self._link_chat_to_trip(session, event.chat_id, trip.id)

    async def _link_chat_to_trip(
            self,
            session: AsyncSession,
            chat_id: int,
            trip_id: int) -> None:
        chat = await session.get(Chat, chat_id)
        if chat:
            chat.trip_id = trip_id
            await session.commit()
            logger.info(f'Linked chat {chat_id} to trip {trip_id}')

    async def _handle_plan_generated(
            self, event: TravelPlanGeneratedEvent) -> None:
        async with self._session_factory() as session:
            trip = None
            if event.trip_id:
                trip = await session.get(Trip, event.trip_id)
            if not trip:
                result = await session.execute(select(Trip).where(Trip.user_id == event.user_id).order_by(Trip.id.desc()).limit(1))
                trip = result.scalar_one_or_none()
            if not trip:
                logger.warning(
                    f'No trip found for plan generated event: user={event.user_id}, trip_id={event.trip_id}')
                return
            try:
                plan_data = json.loads(
                    event.plan_data) if event.plan_data else {}
            except json.JSONDecodeError:
                plan_data = {'raw': event.plan_data}
            trip.generated_plan = plan_data
            await session.commit()
            logger.info(f'Updated Trip {trip.id} with generated plan')


async def main():
    import asyncio
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    worker = TripWorker()
    try:
        await worker.run()
    except KeyboardInterrupt:
        worker.stop()
if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
