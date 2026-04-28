from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, Response, status
from src.common.web.dependencies import get_current_user
from src.components.chats.application.core.commands import IDeleteChatCommand
from src.components.users.infrastructure.models import User


class DeleteChatView:
    @inject
    async def __call__(
            self,
            chat_id: int,
            delete_chat: FromDishka[IDeleteChatCommand],
            current_user: User = Depends(get_current_user)):
        deleted = await delete_chat(chat_id, current_user.id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Chat not found')
        return Response(status_code=status.HTTP_204_NO_CONTENT)
