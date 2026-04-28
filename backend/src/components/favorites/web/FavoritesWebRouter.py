from fastapi import FastAPI, status
from src.components.favorites.web.views.AddToFavoritesView import AddToFavoritesView
from src.components.favorites.web.views.ListFavoritesView import ListFavoritesView
from src.components.favorites.web.views.UpdateFavoriteView import UpdateFavoriteView
from src.components.favorites.web.views.RemoveFavoriteView import RemoveFavoriteView
from src.components.favorites.web.models.FavoriteResponse import FavoriteResponse
from src.components.favorites.web.models.FavoriteListResponse import FavoriteListResponse

__all__ = ['FavoritesWebRouter']


class FavoritesWebRouter:

    def __call__(self, app: FastAPI, prefix: str = ''):
        add_view = AddToFavoritesView()
        list_view = ListFavoritesView()
        update_view = UpdateFavoriteView()
        remove_view = RemoveFavoriteView()

        app.add_api_route(
            path=f'{prefix}/favorites',
            methods=['POST'],
            tags=['favorites'],
            response_model=FavoriteResponse,
            status_code=status.HTTP_201_CREATED,
            summary='Добавить чат в избранное',
            description='Добавляет указанный чат в избранное текущего пользователя.',
            endpoint=add_view.__call__,
        )

        app.add_api_route(
            path=f'{prefix}/favorites',
            methods=['GET'],
            tags=['favorites'],
            response_model=FavoriteListResponse,
            summary='Получить список избранного',
            description='Возвращает список всех избранных чатов текущего пользователя.',
            endpoint=list_view.__call__,
        )

        app.add_api_route(
            path=f'{prefix}/favorites/{{chat_id}}',
            methods=['PATCH'],
            tags=['favorites'],
            response_model=FavoriteResponse,
            summary='Обновить название избранного',
            description='Обновляет пользовательское название избранного чата.',
            endpoint=update_view.__call__,
        )

        app.add_api_route(
            path=f'{prefix}/favorites/{{chat_id}}',
            methods=['DELETE'],
            tags=['favorites'],
            status_code=status.HTTP_204_NO_CONTENT,
            summary='Удалить из избранного',
            description='Удаляет указанный чат из избранного.',
            endpoint=remove_view.__call__,
        )
