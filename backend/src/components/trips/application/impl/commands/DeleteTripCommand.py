from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.trips.application.core.commands import IDeleteTripCommand
from src.components.trips.infrastructure.models.TripModel import Trip


class DeleteTripCommand(IDeleteTripCommand):

    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(self, user_id: int, trip_id: int) -> bool:
        existing = await self._session.execute(
            select(Trip.id).where(Trip.user_id == user_id, Trip.id == trip_id)
        )
        if existing.scalar_one_or_none() is None:
            return False
        await self._session.execute(
            delete(Trip).where(Trip.user_id == user_id, Trip.id == trip_id)
        )
        await self._session.commit()
        return True
