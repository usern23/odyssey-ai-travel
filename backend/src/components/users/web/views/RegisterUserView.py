from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, status
from src.components.users.application.core.commands import IRegisterUserCommand
from src.components.users.application.impl.commands.RegisterUserCommand import UserAlreadyExistsError
from src.components.users.web.models.TokenResponse import TokenResponse
from src.components.users.web.models.UserCreateRequest import UserCreateRequest
from src.infrastructure.auth import create_access_token


class RegisterUserView:
    @inject
    async def __call__(
            self,
            payload: UserCreateRequest,
            register_command: FromDishka[IRegisterUserCommand]) -> TokenResponse:
        try:
            user = await register_command(payload)
        except UserAlreadyExistsError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='User with this email already exists')
        access_token = create_access_token(subject=user.id)
        return TokenResponse(access_token=access_token)
