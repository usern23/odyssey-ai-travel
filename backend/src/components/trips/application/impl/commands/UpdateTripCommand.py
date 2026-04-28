from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.trips.application.core.commands import IUpdateTripCommand
from src.components.trips.infrastructure.models.TripModel import Trip


class TripNotFoundError(Exception):
    pass


class UpdateTripCommand(IUpdateTripCommand):

    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(
        self,
        user_id: int,
        trip_id: int,
        name: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        trip_profile: Optional[dict] = None,
        generated_plan: Optional[dict] = None,
    ) -> Trip:
        result = await self._session.execute(
            select(Trip).where(Trip.user_id == user_id, Trip.id == trip_id)
        )
        trip = result.scalar_one_or_none()
        if not trip:
            raise TripNotFoundError

        updates = {
            'name': name,
            'start_date': start_date,
            'end_date': end_date,
            'trip_profile': trip_profile,
            'generated_plan': generated_plan,
        }
        for field, value in updates.items():
            if value is not None:
                setattr(trip, field, value)

        await self._session.commit()
        await self._session.refresh(trip)
        return trip
