from __future__ import annotations
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.components.trips.infrastructure.models import Trip


class TripRepository:

    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, trip: Trip) -> None:
        self.session.add(trip)

    async def list_by_user(self, user_id: int) -> List[Trip]:
        result = await self.session.execute(select(Trip).where(Trip.user_id == user_id).order_by(Trip.id.desc()))
        return list(result.scalars().all())

    async def get(self, user_id: int, trip_id: int) -> Optional[Trip]:
        result = await self.session.execute(select(Trip).where(Trip.user_id == user_id, Trip.id == trip_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, trip_id: int) -> Optional[Trip]:
        result = await self.session.execute(select(Trip).where(Trip.id == trip_id))
        return result.scalar_one_or_none()


def get_trip_repository(session: AsyncSession) -> TripRepository:
    return TripRepository(session)
