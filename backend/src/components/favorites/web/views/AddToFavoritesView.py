from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from src.common.web.dependencies import get_current_user
from src.components.trips.application.core.queries import IGetTripQuery
from src.components.favorites.application.core.commands import IAddToFavoritesCommand
from src.components.favorites.application.core.queries import IGetUserFavoritesQuery
from src.components.favorites.web.models.FavoriteCreateRequest import FavoriteCreateRequest
from src.components.favorites.web.models.FavoriteResponse import FavoriteResponse
from src.components.users.infrastructure.models import User


def _favorite_to_response(favorite) -> FavoriteResponse:
    trip = favorite.trip
    return FavoriteResponse(
        id=favorite.id,
        trip_id=favorite.trip_id,
        trip_name=trip.name if trip else 'Удалённый маршрут',
        custom_name=favorite.custom_name,
        destination=trip.destination if trip else None,
        created_at=favorite.created_at)


class AddToFavoritesView:
    @inject
    async def __call__(
            self,
            payload: FavoriteCreateRequest,
            add_command: FromDishka[IAddToFavoritesCommand],
            get_favorites_query: FromDishka[IGetUserFavoritesQuery],
            get_trip: FromDishka[IGetTripQuery],
            current_user: User = Depends(get_current_user)) -> FavoriteResponse:
        trip = await get_trip.execute(current_user.id, payload.trip_id)
        if not trip:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Trip not found')
        favorite = await add_command(user_id=current_user.id, trip_id=payload.trip_id, custom_name=payload.custom_name)
        favorites = await get_favorites_query(current_user.id)
        for f in favorites:
            if f.id == favorite.id:
                return _favorite_to_response(f)
        return FavoriteResponse(
            id=favorite.id,
            trip_id=favorite.trip_id,
            trip_name=trip.name,
            custom_name=favorite.custom_name,
            destination=getattr(trip, 'destination', None),
            created_at=favorite.created_at)
