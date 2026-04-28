from __future__ import annotations
import logging
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, status
from src.common.web.dependencies import get_current_user
from src.components.agent.application.AgentHostService import AgentHostService
from src.components.chats.application.core.commands import ICreateChatCommand
from src.components.chats.web.models.AgentReplyResponse import AgentReplyResponse
from src.components.chats.web.models.ChatCreateRequest import ChatCreateRequest
from src.components.users.infrastructure.models import User

logger = logging.getLogger(__name__)


class CreateChatView:
    @inject
    async def __call__(
            self,
            payload: ChatCreateRequest,
            create_chat_command: FromDishka[ICreateChatCommand],
            agent_service: FromDishka[AgentHostService],
            current_user: User = Depends(get_current_user)) -> AgentReplyResponse:
        if payload.message:
            chat, response = await agent_service.create_chat_and_process(
                user_id=current_user.id, message=payload.message)
            return AgentReplyResponse(
                reply=response.reply,
                chat_id=chat.id,
                chat_title=chat.title,
                metadata=response.metadata)
        else:
            chat = await create_chat_command(current_user.id)
            return AgentReplyResponse(
                reply='',
                chat_id=chat.id,
                chat_title=chat.title,
                metadata={})
