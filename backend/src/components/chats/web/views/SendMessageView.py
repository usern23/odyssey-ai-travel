from __future__ import annotations
import logging
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from src.common.web.dependencies import get_current_user
from src.components.agent.application.AgentHostService import AgentHostService
from src.components.chats.application.core.queries import IGetChatQuery
from src.components.chats.web.models.AgentReplyResponse import AgentReplyResponse
from src.components.chats.web.models.ChatMessageRequest import ChatMessageRequest
from src.components.users.infrastructure.models import User

logger = logging.getLogger(__name__)


class SendMessageView:
    @inject
    async def __call__(
            self,
            chat_id: int,
            payload: ChatMessageRequest,
            get_chat: FromDishka[IGetChatQuery],
            agent_service: FromDishka[AgentHostService],
            current_user: User = Depends(get_current_user)) -> AgentReplyResponse:
        chat = await get_chat(chat_id, current_user.id)
        if not chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Chat not found')
        response = await agent_service.process_message(
            user_id=current_user.id, chat_id=chat_id, message=payload.message)
        chat = await get_chat(chat_id, current_user.id)
        return AgentReplyResponse(
            reply=response.reply,
            chat_id=chat_id,
            chat_title=chat.title if chat else 'Новый чат',
            metadata=response.metadata)
