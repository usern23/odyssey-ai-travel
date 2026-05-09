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

    @staticmethod
    def _is_manual_trip(trip: Trip) -> bool:
        """A trip is considered manual when its persisted plan has
        ``source == 'manual'`` (set by CreateManualTripView).

        Manual trips were explicitly created by the user with a chosen
        destination, so the agent must NOT silently overwrite that
        destination via collect/generate when it differs.
        """
        plan_outer = trip.generated_plan or {}
        plan_data = plan_outer.get('plan_data') or {}
        return plan_data.get('source') == 'manual'

    @staticmethod
    def _build_trip_profile(event: TripDataCollectedEvent) -> dict:
        profile = {
            'budget': event.budget,
            'origin': event.origin,
            'travelers_count': event.travelers_count,
            'travel_style': event.travel_style,
        }
        if event.interests:
            try:
                profile['interests'] = json.loads(event.interests)
            except json.JSONDecodeError:
                profile['interests'] = []
        if event.special_requirements:
            try:
                profile['special_requirements'] = json.loads(
                    event.special_requirements)
            except json.JSONDecodeError:
                profile['special_requirements'] = {}
        return profile

    async def _handle_trip_data_collected(
            self, event: TripDataCollectedEvent) -> None:
        async with self._session_factory() as session:
            start_date = datetime.fromisoformat(
                event.start_date).date() if event.start_date else None
            end_date = datetime.fromisoformat(
                event.end_date).date() if event.end_date else None
            trip_profile = self._build_trip_profile(event)

            # ── Find existing trip linked to this chat ──────────────
            chat = None
            existing_trip: Optional[Trip] = None
            if event.chat_id:
                chat = await session.get(Chat, event.chat_id)
                if chat and chat.trip_id:
                    existing_trip = await session.get(Trip, chat.trip_id)

            # ── Branch: chat already has a trip → update in place ──
            if existing_trip is not None:
                # Safety guard: don't silently overwrite a manual trip's
                # destination. The agent should have asked the user
                # first (system prompt enforces this). If it did not,
                # we keep the trip intact and only log.
                if (
                    self._is_manual_trip(existing_trip)
                    and existing_trip.destination
                    and event.destination
                    and existing_trip.destination.strip().lower()
                    != event.destination.strip().lower()
                ):
                    logger.warning(
                        f'Skipping trip-data update for manual trip '
                        f'{existing_trip.id}: destination differs '
                        f'(trip="{existing_trip.destination}", '
                        f'event="{event.destination}"). Agent should '
                        f'ask user before changing direction.',
                    )
                    return

                # Merge profile (don't drop unrelated keys already set).
                merged_profile = dict(existing_trip.trip_profile or {})
                merged_profile.update(trip_profile)

                if not self._is_manual_trip(existing_trip):
                    # Chat-only trip: free to overwrite destination as
                    # the user iterates.
                    existing_trip.destination = (
                        event.destination or existing_trip.destination
                    )
                    if not existing_trip.name or existing_trip.name.startswith('Поездка в '):
                        existing_trip.name = f'Поездка в {event.destination}'
                if event.origin:
                    existing_trip.origin = event.origin
                if start_date:
                    existing_trip.start_date = start_date
                if end_date:
                    existing_trip.end_date = end_date
                existing_trip.trip_profile = merged_profile
                await session.commit()
                logger.info(
                    f'Updated existing Trip {existing_trip.id} from '
                    f'chat {event.chat_id} (manual={self._is_manual_trip(existing_trip)})',
                )
                return

            # ── Branch: no linked trip → create a new one ───────────
            trip = Trip(
                user_id=event.user_id,
                name=f'Поездка в {event.destination}',
                destination=event.destination,
                origin=event.origin,
                start_date=start_date,
                end_date=end_date,
                trip_profile=trip_profile,
                generated_plan={},
            )
            session.add(trip)
            await session.commit()
            await session.refresh(trip)
            logger.info(
                f'Created Trip {trip.id} for user {event.user_id}: '
                f'{event.destination}, {start_date} - {end_date}',
            )
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
            trip: Optional[Trip] = None

            # Priority 1: chat.trip_id (the most reliable link, set
            # either by AskAiForTripView or _handle_trip_data_collected).
            if event.chat_id:
                chat = await session.get(Chat, event.chat_id)
                if chat and chat.trip_id:
                    trip = await session.get(Trip, chat.trip_id)

            # Priority 2: explicit trip_id on the event.
            if trip is None and event.trip_id:
                trip = await session.get(Trip, event.trip_id)

            # Priority 3 (legacy fallback): latest trip for this user.
            if trip is None:
                result = await session.execute(
                    select(Trip)
                    .where(Trip.user_id == event.user_id)
                    .order_by(Trip.id.desc())
                    .limit(1),
                )
                trip = result.scalar_one_or_none()

            if not trip:
                logger.warning(
                    f'No trip found for plan generated event: '
                    f'user={event.user_id}, chat={event.chat_id}, '
                    f'trip_id={event.trip_id}',
                )
                return

            try:
                plan_data = json.loads(
                    event.plan_data) if event.plan_data else {}
            except json.JSONDecodeError:
                plan_data = {'raw': event.plan_data}

            # Safety guard for manual trips: don't overwrite when
            # destination in the agent-generated plan differs from the
            # one the user picked manually.
            is_manual = self._is_manual_trip(trip)
            if is_manual:
                plan_dest = (plan_data.get('destination') or '').strip().lower()
                trip_dest = (trip.destination or '').strip().lower()
                if plan_dest and trip_dest and plan_dest != trip_dest:
                    logger.warning(
                        f'Skipping plan write for manual trip {trip.id}: '
                        f'plan destination "{plan_data.get("destination")}" '
                        f'differs from trip destination "{trip.destination}".',
                    )
                    return

                # Duration guard: manual trips have an explicit
                # date range chosen by the user. If the agent generated
                # a plan with a different number of days (e.g. user
                # said "на неделю" in chat, but the trip is 6 days),
                # do NOT overwrite — that would silently extend the
                # trip behind the user's back. The agent is expected
                # to ask for confirmation first (see SystemPrompt
                # «TRIP DURATION IS FIXED» rule).
                if trip.start_date and trip.end_date:
                    expected_days = (trip.end_date - trip.start_date).days + 1
                    plan_days = plan_data.get('days') or []
                    actual_days = len(plan_days)
                    if expected_days > 0 and actual_days and actual_days != expected_days:
                        logger.warning(
                            f'Skipping plan write for manual trip {trip.id}: '
                            f'plan has {actual_days} day(s) but the trip '
                            f'is {expected_days} day(s) '
                            f'({trip.start_date}..{trip.end_date}). '
                            f'Agent must confirm a date change before '
                            f'regenerating with a different duration.',
                        )
                        return

            if is_manual:
                # Preserve manual-builder wrapped format ({plan_data: ...,
                # version, source}) but refresh inner plan with the
                # newly generated one. Mark it as 'mixed' so the UI
                # badge reflects that both manual and agent contributed.
                outer = dict(trip.generated_plan or {})
                if 'source' not in plan_data:
                    plan_data['source'] = 'mixed'
                outer['plan_data'] = plan_data
                trip.generated_plan = outer
            else:
                # Legacy chat-only trip format: unwrapped plan dict.
                trip.generated_plan = plan_data
            await session.commit()
            logger.info(
                f'Updated Trip {trip.id} with generated plan '
                f'(via chat={event.chat_id}, manual={is_manual})',
            )


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
