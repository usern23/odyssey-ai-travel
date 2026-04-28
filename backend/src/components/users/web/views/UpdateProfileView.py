from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from src.common.web.dependencies import get_current_user
from src.components.users.application.core.commands import IUpdateProfileCommand
from src.components.users.infrastructure.models.UserModel import User
from src.components.users.web.models.UserProfileResponse import UserProfileResponse
from src.components.users.web.models.UserProfileUpdateRequest import UserProfileUpdateRequest


class UpdateProfileView:
    @inject
    async def __call__(
            self,
            payload: UserProfileUpdateRequest,
            update_profile: FromDishka[IUpdateProfileCommand],
            current_user: User = Depends(get_current_user)) -> UserProfileResponse:
        profile = await update_profile(current_user.id, payload)
        if not profile:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Profile not found')
        return UserProfileResponse.model_validate(profile, from_attributes=True)
