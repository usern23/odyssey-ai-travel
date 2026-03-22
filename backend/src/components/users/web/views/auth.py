from __future__ import annotations
import logging
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.configs import settings
from src.infrastructure.auth import create_access_token
from src.infrastructure.db.session import get_db_session
from src.components.users.web.models.dto import Token, UserCreate
from src.components.users.application.services import UserAlreadyExistsError, UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/auth', tags=['auth'])

YANDEX_AUTHORIZE_URL = 'https://oauth.yandex.ru/authorize'
YANDEX_TOKEN_URL = 'https://oauth.yandex.ru/token'
YANDEX_USERINFO_URL = 'https://login.yandex.ru/info'


@router.post('/register', response_model=Token,
             status_code=status.HTTP_201_CREATED)
async def register_user(
        payload: UserCreate,
        session: AsyncSession = Depends(get_db_session)) -> Token:
    service = UserService(session)
    try:
        user = await service.create_user(payload)
    except UserAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='User with this email already exists')
    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token)


@router.post('/login', response_model=Token)
async def login_user(
        form_data: OAuth2PasswordRequestForm = Depends(),
        session: AsyncSession = Depends(get_db_session)) -> Token:
    service = UserService(session)
    user = await service.authenticate(email=form_data.username, password=form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Incorrect email or password')
    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token)


@router.get('/yandex/login')
async def yandex_login() -> dict:
    if not settings.yandex_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail='Yandex OAuth is not configured')
    params = urlencode({
        'response_type': 'code',
        'client_id': settings.yandex_client_id,
    })
    return {'authorization_url': f'{YANDEX_AUTHORIZE_URL}?{params}'}


@router.post('/yandex/callback', response_model=Token)
async def yandex_callback(
        code: str,
        session: AsyncSession = Depends(get_db_session)) -> Token:
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
    service = UserService(session)
    user = await service.get_or_create_yandex_user(
        yandex_id=yandex_id, email=email)
    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token)
