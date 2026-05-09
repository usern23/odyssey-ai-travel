from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends
from src.common.web.dependencies import get_current_user
from src.components.favorites.application.core.queries import IGetUserFavoritesQuery
from src.components.favorites.web.models.FavoriteListResponse import FavoriteListResponse
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


class ListFavoritesView:
    @inject
    async def __call__(
            self,
            get_favorites_query: FromDishka[IGetUserFavoritesQuery],
            current_user: User = Depends(get_current_user)) -> FavoriteListResponse:
        favorites = await get_favorites_query(current_user.id)
        return FavoriteListResponse(
            favorites=[
                _favorite_to_response(f) for f in favorites],
            total=len(favorites))
