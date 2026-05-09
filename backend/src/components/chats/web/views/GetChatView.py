from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from src.common.web.dependencies import get_current_user
from src.components.chats.application.core.queries import IGetChatWithMessagesQuery
from src.components.chats.web.models.ChatWithMessagesResponse import ChatWithMessagesResponse
from src.components.chats.web.views.Mappers import trip_summary, message_to_response
from src.components.favorites.application.core.queries import IIsFavoritedQuery
from src.components.users.infrastructure.models import User


class GetChatView:
    @inject
    async def __call__(
            self,
            chat_id: int,
            get_chat_with_messages: FromDishka[IGetChatWithMessagesQuery],
            is_favorited_query: FromDishka[IIsFavoritedQuery],
            current_user: User = Depends(get_current_user)) -> ChatWithMessagesResponse:
        chat = await get_chat_with_messages(chat_id, current_user.id)
        if not chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Chat not found')
        is_favorited = await is_favorited_query(current_user.id, chat.trip_id) if chat.trip_id else False
        return ChatWithMessagesResponse(
            id=chat.id,
            title=chat.title,
            status=chat.status.value,
            trip_id=chat.trip_id,
            trip=trip_summary(getattr(chat, 'trip', None)),
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            is_favorited=is_favorited,
            messages=[message_to_response(m) for m in chat.messages])
