from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from src.common.web.dependencies import get_current_user
from src.components.users.application.core.commands import ICreateProfileCommand
from src.components.users.application.core.queries import IGetProfileQuery
from src.components.users.infrastructure.models.UserModel import User
from src.components.users.web.models.UserProfileCreateRequest import UserProfileCreateRequest
from src.components.users.web.models.UserProfileResponse import UserProfileResponse


class CreateProfileView:
    @inject
    async def __call__(
            self,
            payload: UserProfileCreateRequest,
            create_profile: FromDishka[ICreateProfileCommand],
            get_profile: FromDishka[IGetProfileQuery],
            current_user: User = Depends(get_current_user)) -> UserProfileResponse:
        existing = await get_profile(current_user.id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Profile already exists')
        profile = await create_profile(current_user.id, payload)
        return UserProfileResponse.model_validate(profile, from_attributes=True)
