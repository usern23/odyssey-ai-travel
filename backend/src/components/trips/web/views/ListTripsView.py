from __future__ import annotations

from typing import List

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Depends

from src.common.web.dependencies import get_current_user
from src.components.trips.application.core.queries import IListUserTripsQuery
from src.components.trips.web.models.TripResponse import TripResponse
from src.components.users.infrastructure.models import User


class ListTripsView:

    @inject
    async def __call__(
        self,
        query: FromDishka[IListUserTripsQuery],
        current_user: User = Depends(get_current_user),
    ) -> List[TripResponse]:
        trips = await query.execute(current_user.id)
        return [TripResponse.model_validate(t, from_attributes=True) for t in trips]
