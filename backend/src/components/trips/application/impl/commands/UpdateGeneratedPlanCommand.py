from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.trips.application.core.commands import IUpdateGeneratedPlanCommand
from src.components.trips.infrastructure.models.TripModel import Trip


class UpdateGeneratedPlanCommand(IUpdateGeneratedPlanCommand):

    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(self, trip_id: int, plan: dict) -> Trip:
        result = await self._session.execute(
            select(Trip).where(Trip.id == trip_id)
        )
        trip = result.scalar_one_or_none()
        if not trip:
            raise ValueError(f"Trip {trip_id} not found")

        trip.generated_plan = plan
        await self._session.commit()
        await self._session.refresh(trip)
        return trip
