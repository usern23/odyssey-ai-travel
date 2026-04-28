from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from src.common.web.dependencies import get_current_user
from src.components.chats.application.core.queries import IGetChatQuery
from src.components.favorites.application.core.commands import IAddToFavoritesCommand
from src.components.favorites.application.core.queries import IGetUserFavoritesQuery
from src.components.favorites.web.models.FavoriteCreateRequest import FavoriteCreateRequest
from src.components.favorites.web.models.FavoriteResponse import FavoriteResponse
from src.components.users.infrastructure.models import User


def _favorite_to_response(favorite) -> FavoriteResponse:
    chat = favorite.chat
    trip = getattr(chat, 'trip', None) if chat else None
    return FavoriteResponse(
        id=favorite.id,
        chat_id=favorite.chat_id,
        chat_title=chat.title if chat else 'Удалённый чат',
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
            get_chat: FromDishka[IGetChatQuery],
            current_user: User = Depends(get_current_user)) -> FavoriteResponse:
        chat = await get_chat(payload.chat_id, current_user.id)
        if not chat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Chat not found')
        favorite = await add_command(user_id=current_user.id, chat_id=payload.chat_id, custom_name=payload.custom_name)
        favorites = await get_favorites_query(current_user.id)
        for f in favorites:
            if f.id == favorite.id:
                return _favorite_to_response(f)
        return FavoriteResponse(
            id=favorite.id,
            chat_id=favorite.chat_id,
            chat_title=chat.title,
            custom_name=favorite.custom_name,
            destination=getattr(
                getattr(
                    chat,
                    'trip',
                    None),
                'destination',
                None),
            created_at=favorite.created_at)
