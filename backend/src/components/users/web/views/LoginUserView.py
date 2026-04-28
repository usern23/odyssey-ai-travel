from __future__ import annotations
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from src.components.users.application.core.queries import IAuthenticateUserQuery
from src.components.users.web.models.TokenResponse import TokenResponse
from src.infrastructure.auth import create_access_token


class LoginUserView:
    @inject
    async def __call__(
            self,
            authenticate_query: FromDishka[IAuthenticateUserQuery],
            form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
        user = await authenticate_query(email=form_data.username, password=form_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Incorrect email or password')
        access_token = create_access_token(subject=user.id)
        return TokenResponse(access_token=access_token)
