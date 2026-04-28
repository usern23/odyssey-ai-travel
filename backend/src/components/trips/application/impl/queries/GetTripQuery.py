from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.trips.application.core.queries import IGetTripQuery
from src.components.trips.infrastructure.models.TripModel import Trip


class GetTripQuery(IGetTripQuery):

    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(self, user_id: int, trip_id: int) -> Optional[Trip]:
        result = await self._session.execute(
            select(Trip).where(Trip.user_id == user_id, Trip.id == trip_id)
        )
        return result.scalar_one_or_none()
