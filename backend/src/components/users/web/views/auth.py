from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.auth import create_access_token
from src.infrastructure.db.session import get_db_session
from src.components.users.web.models.dto import Token, UserCreate
from src.components.users.application.services import UserAlreadyExistsError, UserService
router = APIRouter(prefix='/auth', tags=['auth'])


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
