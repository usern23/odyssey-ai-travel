from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends
from src.common.web.dependencies import get_current_user
from src.components.users.application.core.queries import IGetProfileQuery
from src.components.users.infrastructure.models.UserModel import User


class ProfileStatusView:
    @inject
    async def __call__(
            self,
            get_profile: FromDishka[IGetProfileQuery],
            current_user: User = Depends(get_current_user)):
        profile = await get_profile(current_user.id)
        return {'has_profile': profile is not None}
