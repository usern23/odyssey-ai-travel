from __future__ import annotations
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.trips.web.models.dto import TripCreate, TripUpdate
from src.components.trips.infrastructure.models import Trip
from src.components.trips.infrastructure.repositories import TripRepository, get_trip_repository


class TripNotFoundError(Exception):
    pass


class TripService:

    def __init__(
            self,
            session: AsyncSession,
            repository: Optional[TripRepository] = None):
        self.session = session
        self.repository = repository or get_trip_repository(session)

    async def create_trip(self, user_id: int, payload: TripCreate) -> Trip:
        trip = Trip(
            user_id=user_id,
            name=payload.name,
            start_date=payload.start_date,
            end_date=payload.end_date,
            trip_profile=payload.trip_profile,
            generated_plan=payload.generated_plan)
        await self.repository.add(trip)
        await self.session.commit()
        await self.session.refresh(trip)
        return trip

    async def list_trips(self, user_id: int) -> List[Trip]:
        return await self.repository.list_by_user(user_id)

    async def get_trip(self, user_id: int, trip_id: int) -> Optional[Trip]:
        return await self.repository.get(user_id, trip_id)

    async def update_trip(
            self,
            user_id: int,
            trip_id: int,
            payload: TripUpdate) -> Trip:
        trip = await self.repository.get(user_id, trip_id)
        if not trip:
            raise TripNotFoundError
        for field, value in payload.dict(exclude_unset=True).items():
            setattr(trip, field, value)
        await self.session.commit()
        await self.session.refresh(trip)
        return trip

    async def update_generated_plan(self, trip_id: int, plan: dict) -> Trip:
        trip = await self.repository.get_by_id(trip_id)
        if not trip:
            raise TripNotFoundError
        trip.generated_plan = plan
        await self.session.commit()
        await self.session.refresh(trip)
        return trip
