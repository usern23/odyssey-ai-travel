from __future__ import annotations

from typing import List

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Depends, status

from src.common.web.dependencies import get_current_user
from src.components.trips.application.core.commands import ICreateTripCommand
from src.components.trips.web.models.TripCreateRequest import TripCreateRequest
from src.components.trips.web.models.TripResponse import TripResponse
from src.components.users.infrastructure.models import User


class CreateTripView:

    @inject
    async def __call__(
        self,
        payload: TripCreateRequest,
        command: FromDishka[ICreateTripCommand],
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip = await command.execute(
            user_id=current_user.id,
            name=payload.name,
            destination=payload.destination,
            origin=payload.origin,
            start_date=payload.start_date,
            end_date=payload.end_date,
            trip_profile=payload.trip_profile,
            generated_plan=payload.generated_plan,
        )
        return TripResponse.model_validate(trip, from_attributes=True)
