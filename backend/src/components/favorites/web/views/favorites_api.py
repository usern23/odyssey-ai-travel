from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.web.dependencies import get_current_user
from src.components.chats.application.chat_service import ChatService
from src.components.chats.web.models.dto import FavoriteCreate, FavoriteListResponse, FavoriteResponse, FavoriteUpdate
from src.components.favorites.application.favorites_service import FavoritesService
from src.components.users.infrastructure.models import User
from src.infrastructure.db.session import get_db_session
router = APIRouter(prefix='/favorites', tags=['favorites'])


def _favorite_to_response(favorite) -> FavoriteResponse:
    chat = favorite.chat
    trip = getattr(chat, 'trip', None) if chat else None
    return FavoriteResponse(
        id=favorite.id,
        chat_id=favorite.chat_id,
        chat_title=chat.title if chat else 'Удалённый чат',
        custom_name=favorite.custom_name,
        destination=trip.destination if trip else None,
        created_at=favorite.created_at)


@router.post('', response_model=FavoriteResponse,
             status_code=status.HTTP_201_CREATED)
async def add_to_favorites(
        payload: FavoriteCreate,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> FavoriteResponse:
    chat_service = ChatService(session)
    favorites_service = FavoritesService(session)
    chat = await chat_service.get_chat(payload.chat_id, current_user.id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Chat not found')
    favorite = await favorites_service.add_to_favorites(user_id=current_user.id, chat_id=payload.chat_id, custom_name=payload.custom_name)
    favorites = await favorites_service.get_user_favorites(current_user.id)
    for f in favorites:
        if f.id == favorite.id:
            return _favorite_to_response(f)
    return FavoriteResponse(
        id=favorite.id,
        chat_id=favorite.chat_id,
        chat_title=chat.title,
        custom_name=favorite.custom_name,
        destination=getattr(
            getattr(
                chat,
                'trip',
                None),
            'destination',
            None),
        created_at=favorite.created_at)


@router.get('', response_model=FavoriteListResponse)
async def list_favorites(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> FavoriteListResponse:
    favorites_service = FavoritesService(session)
    favorites = await favorites_service.get_user_favorites(current_user.id)
    return FavoriteListResponse(
        favorites=[
            _favorite_to_response(f) for f in favorites],
        total=len(favorites))


@router.patch('/{chat_id}', response_model=FavoriteResponse)
async def update_favorite(
        chat_id: int,
        payload: FavoriteUpdate,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> FavoriteResponse:
    favorites_service = FavoritesService(session)
    updated = await favorites_service.update_custom_name(user_id=current_user.id, chat_id=chat_id, custom_name=payload.custom_name)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Favorite not found')
    favorites = await favorites_service.get_user_favorites(current_user.id)
    for f in favorites:
        if f.chat_id == chat_id:
            return _favorite_to_response(f)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail='Favorite not found')


@router.delete('/{chat_id}')
async def remove_from_favorites(chat_id: int, current_user: User = Depends(
        get_current_user), session: AsyncSession = Depends(get_db_session)):
    favorites_service = FavoritesService(session)
    removed = await favorites_service.remove_from_favorites(user_id=current_user.id, chat_id=chat_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Favorite not found')
    return Response(status_code=status.HTTP_204_NO_CONTENT)
