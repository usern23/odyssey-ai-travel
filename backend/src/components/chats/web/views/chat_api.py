from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.web.dependencies import get_current_user
from src.components.agent.application.services import AgentHostServiceV3
from src.components.chats.application.chat_service import ChatService
from src.components.chats.infrastructure.models import MessageRole
from src.components.chats.web.models.dto import AgentReplyResponse, ChatCreate, ChatListResponse, ChatMessageRequest, ChatMessageResponse, ChatResponse, ChatUpdateRequest, ChatWithMessagesResponse, TripSummary
from src.components.favorites.application.favorites_service import FavoritesService
from src.components.users.infrastructure.models import User
from src.infrastructure.db.session import get_db_session
router = APIRouter(prefix='/chats', tags=['chats'])


def _trip_summary(trip) -> TripSummary | None:
    if not trip:
        return None
    return TripSummary(
        id=trip.id,
        name=trip.name,
        destination=trip.destination,
        origin=trip.origin,
        start_date=trip.start_date,
        end_date=trip.end_date,
        budget=trip.trip_profile.get('budget') if trip.trip_profile else None,
        has_plan=bool(
            trip.generated_plan))


def _chat_to_response(chat, is_favorited: bool = False) -> ChatResponse:
    return ChatResponse(
        id=chat.id,
        title=chat.title,
        status=chat.status.value,
        trip_id=chat.trip_id,
        trip=_trip_summary(
            getattr(
                chat,
                'trip',
                None)),
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        is_favorited=is_favorited)


def _message_to_response(msg) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=msg.id,
        role=msg.role.value,
        content=msg.content,
        tool_name=msg.tool_name,
        created_at=msg.created_at)


@router.post('', response_model=AgentReplyResponse,
             status_code=status.HTTP_201_CREATED)
async def create_chat(
        payload: ChatCreate,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> AgentReplyResponse:
    chat_service = ChatService(session)
    if payload.message:
        agent_service = AgentHostServiceV3(db_session=session)
        chat, response = await agent_service.create_chat_and_process(user_id=current_user.id, message=payload.message)
        return AgentReplyResponse(
            reply=response.reply,
            chat_id=chat.id,
            chat_title=chat.title,
            metadata=response.metadata)
    else:
        chat = await chat_service.create_chat(current_user.id)
        return AgentReplyResponse(
            reply='',
            chat_id=chat.id,
            chat_title=chat.title,
            metadata={})


@router.get('', response_model=ChatListResponse)
async def list_chats(
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> ChatListResponse:
    chat_service = ChatService(session)
    favorites_service = FavoritesService(session)
    chats = await chat_service.get_user_chats(current_user.id)
    favorites = await favorites_service.get_user_favorites(current_user.id)
    favorited_chat_ids = {f.chat_id for f in favorites}
    chat_responses = [
        _chat_to_response(
            chat,
            is_favorited=chat.id in favorited_chat_ids) for chat in chats]
    return ChatListResponse(chats=chat_responses, total=len(chat_responses))


@router.get('/{chat_id}', response_model=ChatWithMessagesResponse)
async def get_chat(
        chat_id: int,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> ChatWithMessagesResponse:
    chat_service = ChatService(session)
    favorites_service = FavoritesService(session)
    chat = await chat_service.get_chat_with_messages(chat_id, current_user.id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Chat not found')
    is_favorited = await favorites_service.is_favorited(current_user.id, chat_id)
    return ChatWithMessagesResponse(
        id=chat.id,
        title=chat.title,
        status=chat.status.value,
        trip_id=chat.trip_id,
        trip=_trip_summary(
            getattr(
                chat,
                'trip',
                None)),
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        is_favorited=is_favorited,
        messages=[
            _message_to_response(m) for m in chat.messages])


@router.post('/{chat_id}/messages', response_model=AgentReplyResponse)
async def send_message(
        chat_id: int,
        payload: ChatMessageRequest,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> AgentReplyResponse:
    chat_service = ChatService(session)
    chat = await chat_service.get_chat(chat_id, current_user.id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Chat not found')
    agent_service = AgentHostServiceV3(db_session=session)
    response = await agent_service.process_message(user_id=current_user.id, chat_id=chat_id, message=payload.message)
    chat = await chat_service.get_chat(chat_id, current_user.id)
    return AgentReplyResponse(
        reply=response.reply,
        chat_id=chat_id,
        chat_title=chat.title if chat else 'Новый чат',
        metadata=response.metadata)


@router.patch('/{chat_id}', response_model=ChatResponse)
async def update_chat(
        chat_id: int,
        payload: ChatUpdateRequest,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> ChatResponse:
    chat_service = ChatService(session)
    chat = await chat_service.get_chat(chat_id, current_user.id)
    if not chat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Chat not found')
    if payload.title:
        await chat_service.update_chat_title(chat_id, payload.title)
        chat = await chat_service.get_chat(chat_id, current_user.id)
    return _chat_to_response(chat)


@router.delete('/{chat_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat(
        chat_id: int,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> None:
    chat_service = ChatService(session)
    deleted = await chat_service.delete_chat(chat_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Chat not found')
