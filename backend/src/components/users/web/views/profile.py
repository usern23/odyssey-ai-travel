from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.web.dependencies import get_current_user
from src.components.users.web.models.dto import UserProfileCreate, UserProfileRead, UserProfileUpdate
from src.components.users.application.services import UserService
from src.components.users.infrastructure.models import User
from src.infrastructure.db.session import get_db_session
router = APIRouter(prefix='/users', tags=['users'])


@router.post('/me/profile', response_model=UserProfileRead,
             status_code=status.HTTP_201_CREATED)
async def create_profile(
        payload: UserProfileCreate,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> UserProfileRead:
    service = UserService(session)
    existing = await service.get_profile(current_user.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Profile already exists')
    profile = await service.create_profile(current_user.id, payload)
    return UserProfileRead.model_validate(profile, from_attributes=True)


@router.get('/me/profile/status')
async def profile_status(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)):
    service = UserService(session)
    profile = await service.get_profile(current_user.id)
    return {'has_profile': profile is not None}


@router.get('/me/profile', response_model=UserProfileRead)
async def read_profile(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> UserProfileRead:
    service = UserService(session)
    profile = await service.get_profile(current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Profile not found')
    return UserProfileRead.model_validate(profile, from_attributes=True)


@router.put('/me/profile', response_model=UserProfileRead)
async def update_profile(
        payload: UserProfileUpdate,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> UserProfileRead:
    service = UserService(session)
    profile = await service.update_profile(current_user.id, payload)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Profile not found')
    return UserProfileRead.model_validate(profile, from_attributes=True)
