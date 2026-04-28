from __future__ import annotations
import logging
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import HTTPException, status
import httpx
from src.common.configs import settings
from src.components.users.application.core.commands import IGetOrCreateYandexUserCommand
from src.components.users.web.models.TokenResponse import TokenResponse
from src.infrastructure.auth import create_access_token

logger = logging.getLogger(__name__)

YANDEX_TOKEN_URL = 'https://oauth.yandex.ru/token'
YANDEX_USERINFO_URL = 'https://login.yandex.ru/info'


class YandexCallbackView:
    @inject
    async def __call__(
            self,
            code: str,
            get_or_create_yandex_user: FromDishka[IGetOrCreateYandexUserCommand]) -> TokenResponse:
        if not settings.yandex_client_id or not settings.yandex_client_secret:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail='Yandex OAuth is not configured')
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                YANDEX_TOKEN_URL,
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'client_id': settings.yandex_client_id,
                    'client_secret': settings.yandex_client_secret,
                },
                headers={'Content-Type': 'application/x-www-form-urlencoded'})
            if token_resp.status_code != 200:
                logger.error('Yandex token exchange failed: %s', token_resp.text)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Failed to exchange authorization code')
            token_data = token_resp.json()
            yandex_access_token = token_data['access_token']
            userinfo_resp = await client.get(
                YANDEX_USERINFO_URL,
                params={'format': 'json'},
                headers={'Authorization': f'OAuth {yandex_access_token}'})
            if userinfo_resp.status_code != 200:
                logger.error('Yandex userinfo failed: %s', userinfo_resp.text)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Failed to fetch user info from Yandex')
            userinfo = userinfo_resp.json()
        yandex_id = userinfo['id']
        email = userinfo.get('default_email', f'{yandex_id}@yandex.ru')
        user = await get_or_create_yandex_user(yandex_id=yandex_id, email=email)
        access_token = create_access_token(subject=user.id)
        return TokenResponse(access_token=access_token)
