from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends
from src.common.web.dependencies import get_current_user
from src.components.chats.application.core.queries import IGetUserChatsQuery
from src.components.chats.web.models.ChatListResponse import ChatListResponse
from src.components.chats.web.views.Mappers import chat_to_response
from src.components.favorites.application.core.queries import IGetUserFavoritesQuery
from src.components.users.infrastructure.models import User


class ListChatsView:
    @inject
    async def __call__(
            self,
            get_user_chats: FromDishka[IGetUserChatsQuery],
            get_favorites: FromDishka[IGetUserFavoritesQuery],
            current_user: User = Depends(get_current_user)) -> ChatListResponse:
        chats = await get_user_chats(current_user.id)
        favorites = await get_favorites(current_user.id)
        favorited_trip_ids = {f.trip_id for f in favorites}
        chat_responses = [
            chat_to_response(chat, is_favorited=chat.trip_id is not None and chat.trip_id in favorited_trip_ids)
            for chat in chats]
        return ChatListResponse(chats=chat_responses, total=len(chat_responses))
