from __future__ import annotations
from urllib.parse import urlencode
from fastapi import HTTPException, status
from src.common.configs import settings

YANDEX_AUTHORIZE_URL = 'https://oauth.yandex.ru/authorize'


class YandexLoginView:
    async def __call__(self) -> dict:
        if not settings.yandex_client_id:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail='Yandex OAuth is not configured')
        params = urlencode({
            'response_type': 'code',
            'client_id': settings.yandex_client_id,
        })
        return {'authorization_url': f'{YANDEX_AUTHORIZE_URL}?{params}'}
