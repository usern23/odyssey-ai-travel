from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from src.common.web.dependencies import get_current_user
from src.components.chats.application.core.commands import IUpdateChatTitleCommand
from src.components.chats.application.core.queries import IGetChatQuery
from src.components.chats.web.models.ChatResponse import ChatResponse
from src.components.chats.web.models.ChatUpdateRequest import ChatUpdateRequest
from src.components.chats.web.views.Mappers import chat_to_response
from src.components.users.infrastructure.models import User


class UpdateChatView:
    @inject
    async def __call__(
            self,
            chat_id: int,
            payload: ChatUpdateRequest,
            get_chat: FromDishka[IGetChatQuery],
            update_title: FromDishka[IUpdateChatTitleCommand],
            current_user: User = Depends(get_current_user)) -> ChatResponse:
        chat = await get_chat(chat_id, current_user.id)
        if not chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Chat not found')
        if payload.title:
            await update_title(chat_id, payload.title)
            chat = await get_chat(chat_id, current_user.id)
        return chat_to_response(chat)
