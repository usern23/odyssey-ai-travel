from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.components.trips.application.core.commands import ICreateTripCommand
from src.components.trips.infrastructure.models.TripModel import Trip


class CreateTripCommand(ICreateTripCommand):

    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(
        self,
        user_id: int,
        name: str,
        destination: Optional[str],
        origin: Optional[str],
        start_date: Optional[date],
        end_date: Optional[date],
        trip_profile: dict,
        generated_plan: dict,
    ) -> Trip:
        trip = Trip(
            user_id=user_id,
            name=name,
            destination=destination,
            origin=origin,
            start_date=start_date,
            end_date=end_date,
            trip_profile=trip_profile,
            generated_plan=generated_plan,
        )
        self._session.add(trip)
        await self._session.commit()
        await self._session.refresh(trip)
        return trip
