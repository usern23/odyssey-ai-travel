from fastapi import FastAPI, status
from src.components.users.web.views.RegisterUserView import RegisterUserView
from src.components.users.web.views.LoginUserView import LoginUserView
from src.components.users.web.views.YandexLoginView import YandexLoginView
from src.components.users.web.views.YandexCallbackView import YandexCallbackView
from src.components.users.web.views.CreateProfileView import CreateProfileView
from src.components.users.web.views.ProfileStatusView import ProfileStatusView
from src.components.users.web.views.ReadProfileView import ReadProfileView
from src.components.users.web.views.UpdateProfileView import UpdateProfileView
from src.components.users.web.models.TokenResponse import TokenResponse
from src.components.users.web.models.UserProfileResponse import UserProfileResponse

__all__ = ['UsersWebRouter']


class UsersWebRouter:

    def __call__(self, app: FastAPI, prefix: str = ''):
        app.add_api_route(
            path=f'{prefix}/auth/register',
            methods=['POST'],
            tags=['auth'],
            response_model=TokenResponse,
            status_code=status.HTTP_201_CREATED,
            endpoint=RegisterUserView().__call__)

        app.add_api_route(
            path=f'{prefix}/auth/login',
            methods=['POST'],
            tags=['auth'],
            response_model=TokenResponse,
            endpoint=LoginUserView().__call__)

        app.add_api_route(
            path=f'{prefix}/auth/yandex/login',
            methods=['GET'],
            tags=['auth'],
            endpoint=YandexLoginView().__call__)

        app.add_api_route(
            path=f'{prefix}/auth/yandex/callback',
            methods=['POST'],
            tags=['auth'],
            response_model=TokenResponse,
            endpoint=YandexCallbackView().__call__)

        app.add_api_route(
            path=f'{prefix}/users/me/profile',
            methods=['POST'],
            tags=['users'],
            response_model=UserProfileResponse,
            status_code=status.HTTP_201_CREATED,
            endpoint=CreateProfileView().__call__)

        app.add_api_route(
            path=f'{prefix}/users/me/profile/status',
            methods=['GET'],
            tags=['users'],
            endpoint=ProfileStatusView().__call__)

        app.add_api_route(
            path=f'{prefix}/users/me/profile',
            methods=['GET'],
            tags=['users'],
            response_model=UserProfileResponse,
            endpoint=ReadProfileView().__call__)

        app.add_api_route(
            path=f'{prefix}/users/me/profile',
            methods=['PUT'],
            tags=['users'],
            response_model=UserProfileResponse,
            endpoint=UpdateProfileView().__call__)
