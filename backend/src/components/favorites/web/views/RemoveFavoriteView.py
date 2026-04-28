from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, Response, status
from src.common.web.dependencies import get_current_user
from src.components.favorites.application.core.commands import IRemoveFromFavoritesCommand
from src.components.users.infrastructure.models import User


class RemoveFavoriteView:
    @inject
    async def __call__(
            self,
            chat_id: int,
            remove_command: FromDishka[IRemoveFromFavoritesCommand],
            current_user: User = Depends(get_current_user)):
        removed = await remove_command(user_id=current_user.id, chat_id=chat_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Favorite not found')
        return Response(status_code=status.HTTP_204_NO_CONTENT)
