from __future__ import annotations
import json
import logging
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, status
from fastapi.responses import StreamingResponse
from src.common.web.dependencies import get_current_user
from src.components.agent.application.AgentHostService import AgentHostService
from src.components.chats.application.core.commands import ICreateChatCommand
from src.components.chats.web.models.ChatCreateRequest import ChatCreateRequest
from src.components.users.infrastructure.models import User

logger = logging.getLogger(__name__)


class StreamNewChatView:
    @inject
    async def __call__(
            self,
            payload: ChatCreateRequest,
            create_chat_command: FromDishka[ICreateChatCommand],
            agent_service: FromDishka[AgentHostService],
            current_user: User = Depends(get_current_user)):
        chat = await create_chat_command(current_user.id)
        if not payload.message:
            async def empty_gen():
                yield f"event: done\ndata: {json.dumps({'chat_id': chat.id, 'reply': ''})}\n\n"
            return StreamingResponse(
                empty_gen(),
                media_type='text/event-stream',
                headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})
        agent_service_ref = agent_service

        async def event_generator():
            yield f"event: chat_created\ndata: {json.dumps({'chat_id': chat.id})}\n\n"
            try:
                async for event in agent_service_ref.stream_message(
                        user_id=current_user.id, chat_id=chat.id, message=payload.message):
                    yield f"event: {event['event']}\ndata: {event['data']}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})
