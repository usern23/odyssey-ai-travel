from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from src.common.web.dependencies import get_current_user
from src.components.users.application.core.queries import IGetProfileQuery
from src.components.users.infrastructure.models.UserModel import User
from src.components.users.web.models.UserProfileResponse import UserProfileResponse


class ReadProfileView:
    @inject
    async def __call__(
            self,
            get_profile: FromDishka[IGetProfileQuery],
            current_user: User = Depends(get_current_user)) -> UserProfileResponse:
        profile = await get_profile(current_user.id)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Profile not found')
        return UserProfileResponse.model_validate(profile, from_attributes=True)
