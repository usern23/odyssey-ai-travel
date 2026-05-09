from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.fastapi import inject
from fastapi import Depends, HTTPException, status

from src.common.web.dependencies import get_current_user
from src.components.trips.application.core.commands import IDeleteTripCommand
from src.components.users.infrastructure.models import User


class DeleteTripView:

    @inject
    async def __call__(
        self,
        trip_id: int,
        command: FromDishka[IDeleteTripCommand],
        current_user: User = Depends(get_current_user),
    ) -> None:
        deleted = await command.execute(current_user.id, trip_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Trip not found',
            )
        # Returning None lets FastAPI emit a proper 204 with empty body.
        return None
