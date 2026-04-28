from __future__ import annotations
import json
import logging
from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from src.common.web.dependencies import get_current_user
from src.components.agent.application.AgentHostService import AgentHostService
from src.components.chats.application.core.queries import IGetChatQuery
from src.components.chats.web.models.ChatMessageRequest import ChatMessageRequest
from src.components.users.infrastructure.models import User

logger = logging.getLogger(__name__)


class StreamMessageView:
    @inject
    async def __call__(
            self,
            chat_id: int,
            payload: ChatMessageRequest,
            get_chat: FromDishka[IGetChatQuery],
            agent_service: FromDishka[AgentHostService],
            current_user: User = Depends(get_current_user)):
        chat = await get_chat(chat_id, current_user.id)
        if not chat:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Chat not found')

        async def event_generator():
            try:
                async for event in agent_service.stream_message(
                        user_id=current_user.id, chat_id=chat_id, message=payload.message):
                    yield f"event: {event['event']}\ndata: {event['data']}\n\n"
            except Exception as e:
                import traceback
                logger.error('SSE stream error for chat %s: %s\n%s', chat_id, e, traceback.format_exc())
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})
