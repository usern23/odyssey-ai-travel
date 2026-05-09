from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from src.common.web.dependencies import get_current_user
from src.components.favorites.application.core.commands import IUpdateFavoriteCommand
from src.components.favorites.application.core.queries import IGetUserFavoritesQuery
from src.components.favorites.web.models.FavoriteUpdateRequest import FavoriteUpdateRequest
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


class UpdateFavoriteView:
    @inject
    async def __call__(
            self,
            trip_id: int,
            payload: FavoriteUpdateRequest,
            update_command: FromDishka[IUpdateFavoriteCommand],
            get_favorites_query: FromDishka[IGetUserFavoritesQuery],
            current_user: User = Depends(get_current_user)) -> FavoriteResponse:
        updated = await update_command(user_id=current_user.id, trip_id=trip_id, custom_name=payload.custom_name)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Favorite not found')
        favorites = await get_favorites_query(current_user.id)
        for f in favorites:
            if f.trip_id == trip_id:
                return _favorite_to_response(f)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Favorite not found')
