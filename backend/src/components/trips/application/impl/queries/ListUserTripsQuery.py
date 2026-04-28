from __future__ import annotations

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.trips.application.core.queries import IListUserTripsQuery
from src.components.trips.infrastructure.models.TripModel import Trip


class ListUserTripsQuery(IListUserTripsQuery):

    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(self, user_id: int) -> List[Trip]:
        result = await self._session.execute(
            select(Trip).where(Trip.user_id == user_id).order_by(Trip.id.desc())
        )
        return list(result.scalars().all())
