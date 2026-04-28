from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Depends, HTTPException, status

from src.common.web.dependencies import get_current_user
from src.components.trips.application.core.queries import IGetTripQuery
from src.components.trips.web.models.TripResponse import TripResponse
from src.components.users.infrastructure.models import User


class GetTripView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        query: FromDishka[IGetTripQuery],
        current_user: User = Depends(get_current_user),
    ) -> TripResponse:
        trip = await query.execute(current_user.id, trip_id)
        if not trip:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Trip not found')
        return TripResponse.model_validate(trip, from_attributes=True)
