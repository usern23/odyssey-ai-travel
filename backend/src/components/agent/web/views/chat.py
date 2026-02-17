from __future__ import annotations
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.common.web.dependencies import get_current_user
from src.components.agent.application.services import AgentHostServiceV3
from src.components.agent.web.models.dto import AgentChatResponse
from src.components.chats.application.chat_service import ChatService
from src.components.users.infrastructure.models import User
from src.infrastructure.db.session import get_db_session
router = APIRouter(prefix='/agent', tags=['agent'])


class AgentChatRequest(BaseModel):
    chat_id: Optional[UUID] = None
    message: str


@router.post('/chat', response_model=AgentChatResponse)
async def chat_with_agent(
        payload: AgentChatRequest,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session)) -> AgentChatResponse:
    chat_service = ChatService(session)
    if payload.chat_id:
        chat = await chat_service.get_chat(payload.chat_id)
        if not chat or chat.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail='Chat not found')
    else:
        chat = await chat_service.create_chat(current_user.id)
    agent_host = AgentHostServiceV3(db_session=session)
    response = await agent_host.process_message(user_id=current_user.id, chat_id=chat.id, message=payload.message)
    return response
